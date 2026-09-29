"""HE-3301 source adapter sharing the existing governed workflow persistence."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

from services.api.app.schemas.alerts import AlertEvent, AlertStateTransition
from services.api.app.schemas.api import (
    AssetSummary,
    InvestigationEvidenceEvent,
    PlantRateDailyPoint,
    PlantRateSeries,
    TelemetrySeries,
)
from services.api.app.schemas.effectiveness import EffectivenessMetric, EffectivenessReview
from services.api.app.schemas.equipment import EquipmentInvestigation
from services.api.app.schemas.retrieval import (
    IncidentRetrievalConfig,
    IncidentRetrievalResult,
    RAGEvidencePackage,
    RetrievalQuery,
)
from services.api.app.services.artifacts import ArtifactNotFoundError, KO3201ArtifactRepository
from services.api.app.services.rca.incident_retrieval import (
    build_incident_documents,
    retrieve_incidents,
)


class HE3301ArtifactRepository(KO3201ArtifactRepository):
    asset_key = "he_3301"

    def pipeline_status(self) -> dict[str, bool]:
        canonical = self._path("data/normalized/he_3301/equipment.json").is_file()
        return {
            "canonical": canonical,
            "features": False,
            "model_scores": False,
            "alerts": canonical,
            "retrieval": canonical
            and self._path("data/normalized/ko_3201/incidents.csv").is_file(),
            "rca": self._rca_path().is_file(),
            "actions": bool(self._action_plan_paths()),
        }

    def effectiveness_check(self, asset_id: str):
        self.get_asset(asset_id)
        return None

    def production_impact(self, asset_id: str, alert, policy):
        self.get_asset(asset_id)
        return None

    def equipment(self) -> EquipmentInvestigation:
        from services.api.app.services.data.he_3301 import load_he_3301

        return load_he_3301(self.root)

    def list_assets(self) -> list[AssetSummary]:
        return [self.equipment().asset]

    def list_alerts(self) -> list[AlertEvent]:
        return [self.equipment().alert]

    def get_alert_transitions(self, alert_id: str) -> list[AlertStateTransition]:
        self.get_alert(alert_id)
        return self.equipment().transitions

    def get_opening_snapshot(self, alert: AlertEvent) -> dict[str, object]:
        bundle = self.equipment()
        opened = pd.Timestamp(alert.opened_at).to_pydatetime()
        assessment = next(item for item in bundle.assessments if item.timestamp == opened)
        visible = {}
        for signal in bundle.signals:
            points = [point for point in signal.points if point.timestamp <= opened]
            if signal.direction and points:
                point = points[-1]
                visible[signal.key] = {
                    "value": point.value,
                    "timestamp": point.timestamp.isoformat(),
                    "unit": signal.unit,
                    "source_reference": point.source_reference,
                    "cadence": signal.cadence,
                }
        return {
            "timestamp": opened.isoformat(),
            "decision_state": assessment.state,
            "decision_reason": assessment.reason,
            "anomaly_score": assessment.score,
            "alarm_breadth": len(assessment.breached_signals),
            "breached_signals": assessment.breached_signals,
            "condition_values": visible,
            "score_basis": "Engineering limit severity, evaluated at weekly source cadence",
        }

    def get_evidence_package(self, alert_id: str) -> RAGEvidencePackage:
        alert = self.get_alert(alert_id)
        asset = self.get_asset(alert.asset_id)
        snapshot = self.get_opening_snapshot(alert)
        config = IncidentRetrievalConfig.model_validate(
            yaml.safe_load(self._path("data/catalog/he_3301_retrieval_config.yaml").read_text())
        )
        if alert.policy_id != config.input_alert_policy_id:
            raise ValueError("HE alert policy does not match retrieval configuration")
        signals = snapshot["breached_signals"]
        supporting = [key for key in snapshot["condition_values"] if key not in signals]
        mappings = [config.signal_mappings[key] for key in signals]
        narrative = "; ".join(item.narrative for item in mappings)
        query = RetrievalQuery(
            query_id=f"query-{alert_id}-open",
            alert_id=alert_id,
            as_of=pd.Timestamp(alert.opened_at).to_pydatetime(),
            asset_id=asset.asset_id,
            asset_tag=asset.tag,
            plant_id=asset.plant_id,
            equipment_family=asset.equipment_family,
            discipline="STATIC",
            components=list(dict.fromkeys(item.component for item in mappings)),
            observed_symptoms=list(dict.fromkeys(item.symptom for item in mappings)),
            breached_signals=signals,
            supporting_signals=supporting,
            primary_driver=signals[0] if signals else "undetermined",
            narrative=narrative,
            search_text=f"heat exchanger static tube bundle {narrative}",
        )
        documents = build_incident_documents(
            self._read_csv("data/normalized/ko_3201/incidents.csv"),
            self._read_csv("data/normalized/ko_3201/incident_labels.csv"),
        )
        documents = [
            document
            for document in documents
            if document.component == "TUBE_BUNDLE"
            or document.failure_family == "FOULING_PERFORMANCE_DEGRADATION"
        ]
        return RAGEvidencePackage(
            package_id=f"package-{alert_id}-open",
            created_for_stage="ALERT_OPEN",
            query=query,
            alert_snapshot=snapshot,
            historical_analogues=retrieve_incidents(documents, query, config),
            evidence_boundaries=[
                "Only measurements available at alert opening are included.",
                "Weekly condition measurements and hourly production measurements retain their separate cadence.",
                "Inspection, cleaning findings and the HE anchor incident are excluded from opening retrieval.",
                "Incident labels are normalized historical descriptors and require review.",
            ],
            requested_output=[
                "Rank plausible mechanisms",
                "Cite available signal and incident identifiers",
                "Specify disconfirming checks and missing evidence",
            ],
        )

    def get_similar_incidents(self, alert_id: str) -> list[IncidentRetrievalResult]:
        return self.get_evidence_package(alert_id).historical_analogues

    def investigation_events(self, alert: AlertEvent) -> list[InvestigationEvidenceEvent]:
        self.get_alert(alert.alert_id)
        return self.equipment().events

    def timeline_summary(self, asset_id: str) -> tuple[pd.Timestamp, pd.Timestamp, str]:
        self.get_asset(asset_id)
        assessments = self.equipment().assessments
        return (
            pd.Timestamp(assessments[0].timestamp),
            pd.Timestamp(assessments[-1].timestamp),
            assessments[-1].state,
        )

    def telemetry(
        self, asset_id: str, start: str | None, end: str | None, max_points: int
    ) -> TelemetrySeries:
        self.get_asset(asset_id)
        raise ArtifactNotFoundError(
            "HE condition and operation have separate cadences; use /assets/{id}/investigation"
        )

    def plant_rate_daily(self, asset_id: str) -> PlantRateSeries:
        asset = self.get_asset(asset_id)
        signal = next(item for item in self.equipment().signals if item.key == "plant_rate")
        frame = pd.DataFrame(
            [{"date": point.timestamp.date(), "value": point.value} for point in signal.points]
        )
        daily = frame.groupby("date")["value"].agg(["mean", "count"])
        return PlantRateSeries(
            plant_id=asset.plant_id,
            unit=signal.unit,
            aggregation="DAILY_MEAN_INCLUDING_OFFLINE",
            source_key=signal.source_key,
            source_reference="he_production:Sheet2:PLANT_RATE",
            source_rows=len(frame),
            points=[
                PlantRateDailyPoint(
                    date=day, average_rate_tph=float(row["mean"]), sample_count=int(row["count"])
                )
                for day, row in daily.iterrows()
            ],
        )

    def effectiveness_review(self) -> EffectivenessReview:
        bundle = self.equipment()
        cleaning = next(event for event in bundle.events if event.event_id == "he-evidence-4")
        metrics = []
        post_times = set()
        recurrence = False
        before_times = []
        for signal in bundle.signals:
            if not signal.direction:
                continue
            before = [point for point in signal.points if point.timestamp < cleaning.occurred_at]
            after = [point for point in signal.points if point.timestamp > cleaning.occurred_at][:5]
            if not before or not after:
                raise ArtifactNotFoundError(f"Recovery comparison unavailable: {signal.key}")
            before_times.append(before[-1].timestamp)
            post_times.update(point.timestamp for point in after)
            original, recovered = before[-1].value, sum(point.value for point in after) / len(after)
            improvement = (
                original - recovered if signal.direction == "HIGH" else recovered - original
            )
            recurrence |= any(
                point.value >= signal.alarm_limit
                if signal.direction == "HIGH"
                else point.value <= signal.alarm_limit
                for point in after
            )
            metrics.append(
                EffectivenessMetric(
                    signal_key=signal.key,
                    label=signal.label,
                    unit=signal.unit,
                    direction_of_concern=signal.direction,
                    before=original,
                    after=recovered,
                    improvement_percent=round(improvement / abs(original) * 100, 1)
                    if original
                    else 0,
                    outcome="IMPROVED"
                    if improvement > 0
                    else "DETERIORATED"
                    if improvement < 0
                    else "STABLE",
                )
            )
        improved = all(metric.outcome == "IMPROVED" for metric in metrics) and not recurrence
        return EffectivenessReview(
            effectiveness_check_id="effectiveness-he-3301-001",
            rca_case_id=f"rca-{bundle.alert.alert_id}",
            incident_id="incident-0004",
            asset_id=bundle.asset.asset_id,
            monitoring_start=min(post_times),
            monitoring_end=max(post_times),
            monitoring_periods=len(post_times),
            baseline_window=f"Last weekly readings before cleaning: {min(before_times).isoformat()}",
            result="INITIAL_EFFECTIVE" if improved else "INCONCLUSIVE",
            recurrence_detected=recurrence,
            recovery_confirmed=improved,
            approval_status="PENDING_REVIEW",
            closure_eligible=False,
            explanation="Compare the final pre-cleaning weekly measurements with the mean of five post-cleaning readings. Signal recovery supports initial effectiveness; an assigned reviewer must accept the evidence before closure.",
            approved_by=None,
            approved_at=None,
            source_reference=cleaning.source_reference,
            metrics=metrics,
        )

    def _rca_path(self) -> Path:
        return self._path("data/rca/he_3301/v1/rca_record.json")

    def _action_plan_directory(self) -> Path:
        return self._path("data/actions/he_3301/v1/plans")

    def _action_plan_paths(self):
        return sorted(self._action_plan_directory().glob("*.json"))
