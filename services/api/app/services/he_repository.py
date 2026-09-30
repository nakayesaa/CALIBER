"""HE-3301 source adapter sharing the existing governed workflow persistence."""

from __future__ import annotations

from pathlib import Path

import numpy as np
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
from services.api.app.schemas.canonical import EffectivenessCheck
from services.api.app.schemas.effectiveness import EffectivenessMetric, EffectivenessReview
from services.api.app.schemas.equipment import EquipmentInvestigation
from services.api.app.schemas.rca import RCARecord
from services.api.app.schemas.retrieval import (
    IncidentRetrievalConfig,
    IncidentRetrievalResult,
    RAGEvidencePackage,
    RetrievalQuery,
)
from services.api.app.services.artifacts import ArtifactNotFoundError, KO3201ArtifactRepository
from services.api.app.services.he_analytics import active_snapshot, snapshot_alerts, validation_note
from services.api.app.services.production_impact import calculate_production_impact
from services.api.app.services.rca.incident_retrieval import (
    build_incident_documents,
    retrieve_incidents,
)


class HE3301ArtifactRepository(KO3201ArtifactRepository):
    asset_key = "he_3301"

    def pipeline_status(self) -> dict[str, bool]:
        canonical = self._path("data/normalized/he_3301/equipment.json").is_file()
        promoted = active_snapshot(self.root) is not None
        return {
            "canonical": canonical,
            "features": self._path("data/features/he_3301/v1/feature_manifest.json").is_file(),
            "model_scores": promoted,
            "alerts": canonical,
            "retrieval": canonical
            and self._path("data/normalized/ko_3201/incidents.csv").is_file(),
            "rca": self._rca_path().is_file(),
            "actions": bool(self._action_plan_paths()),
        }

    def effectiveness_check(self, asset_id: str) -> EffectivenessCheck:
        self.get_asset(asset_id)
        review = self.effectiveness_review()
        return EffectivenessCheck(
            effectiveness_check_id=review.effectiveness_check_id,
            rca_case_id=review.rca_case_id,
            incident_id=review.incident_id,
            asset_id=asset_id,
            monitoring_start=review.monitoring_start,
            monitoring_end=review.monitoring_end,
            baseline_window=review.baseline_window,
            comparison_metrics={
                **{metric.signal_key: {"before": metric.before, "after": metric.after}
                   for metric in review.metrics},
                "post_repair_normal_weeks": review.monitoring_periods,
            },
            recurrence_detected=review.recurrence_detected,
            result=review.result,
            explanation=review.explanation,
            source_type="DERIVED_FEATURE",
            source_reference=review.source_reference,
        )

    def production_impact(self, asset_id: str, alert, policy):
        self.get_asset(asset_id)
        operation = self._operation_frame()
        # May production is not extended backwards to the February condition warning.
        operation["operating_mode"] = np.where(operation.run_status.eq("ON"), "RUNNING_STEADY", "OFFLINE")
        operation["event_marker"] = None
        decisions = operation[["timestamp"]].assign(decision_state="NORMAL")
        impact = calculate_production_impact(operation, decisions, alert, policy)
        if impact is None:
            return None
        bundle = self.equipment()
        return impact.model_copy(update={
            "reported_downtime_hours": bundle.reported_downtime_hours,
            "reported_production_loss_tonnes": bundle.reported_production_loss_tonnes,
        })

    def _operation_frame(self) -> pd.DataFrame:
        bundle = self.equipment()
        frames = [
            pd.DataFrame({"timestamp": [point.timestamp for point in signal.points],
                          column: [point.value for point in signal.points]})
            for key, column in [("feed_rate", "feed_rate_tph"), ("plant_rate", "plant_rate_tph")]
            for signal in bundle.signals if signal.key == key
        ]
        if len(frames) != 2:
            raise ArtifactNotFoundError("HE production feed and plant rate are required")
        operation = frames[0].merge(frames[1], on="timestamp", validate="one_to_one")
        states = pd.DataFrame([{"timestamp": item.timestamp, "run_status": item.state}
                               for item in bundle.operating_states])
        return operation.merge(states, on="timestamp", validate="one_to_one")

    def equipment(self) -> EquipmentInvestigation:
        from services.api.app.services.data.he_3301 import load_he_3301

        return load_he_3301(self.root)

    def list_assets(self) -> list[AssetSummary]:
        return [self.equipment().asset]

    def list_alerts(self) -> list[AlertEvent]:
        directory = active_snapshot(self.root)
        if directory:
            return snapshot_alerts(directory)
        return [self.equipment().alert]

    def get_alert(self, alert_id: str) -> AlertEvent:
        for alert in [*self.list_alerts(), self.equipment().alert]:
            if alert.alert_id == alert_id:
                return alert
        # Historical snapshot IDs retain their original evidence and human records.
        for path in self._path("data/alerts/he_3301/bundles").glob("*/events.json"):
            directory = path.parent
            for alert in snapshot_alerts(directory):
                if alert.alert_id == alert_id:
                    return alert
        raise ArtifactNotFoundError(f"HE alert not found: {alert_id}")

    def _alert_snapshot(self, alert_id: str) -> Path | None:
        if alert_id == self.equipment().alert.alert_id:
            return None
        for path in self._path("data/alerts/he_3301/bundles").glob("*/events.json"):
            directory = path.parent
            if any(alert.alert_id == alert_id for alert in snapshot_alerts(directory)):
                return directory
        raise ArtifactNotFoundError(f"HE analytics snapshot not found: {alert_id}")

    def get_rca(self, alert_id: str) -> RCARecord | None:
        self.get_alert(alert_id)
        path = self._record_path(alert_id)
        return self._read_model(path, RCARecord) if path.is_file() else None

    def save_rca(self, record: RCARecord) -> None:
        self.get_alert(record.alert_id)
        self._write_model(self._record_path(record.alert_id), record)

    def _record_path(self, alert_id: str) -> Path:
        if alert_id == self.equipment().alert.alert_id:
            return self._rca_path()
        return self._path(f"data/rca/he_3301/v1/records/{alert_id}.json")

    def get_alert_transitions(self, alert_id: str) -> list[AlertStateTransition]:
        self.get_alert(alert_id)
        directory = self._alert_snapshot(alert_id)
        if directory:
            import json

            payload = json.loads((directory / "events.json").read_text())
            return [
                AlertStateTransition.model_validate(item)
                for item in payload["transitions"]
                if item["alert_id"] == alert_id
            ]
        return self.equipment().transitions

    def get_opening_snapshot(self, alert: AlertEvent) -> dict[str, object]:
        bundle = self.equipment()
        opened = pd.Timestamp(alert.opened_at).to_pydatetime()
        directory = self._alert_snapshot(alert.alert_id)
        if directory:
            scenario = pd.read_csv(directory / "hourly_scenario.csv")
            decisions = pd.read_csv(directory / "hourly_alert_decisions.csv")
            row = scenario.loc[pd.to_datetime(scenario.timestamp).eq(opened)].iloc[0]
            decision = decisions.loc[pd.to_datetime(decisions.timestamp).eq(opened)].iloc[0]
            values = {
                signal.key: {
                    "value": float(row[signal.key]),
                    "timestamp": opened.isoformat(),
                    "unit": signal.unit,
                    "cadence": "HOURLY_SCENARIO",
                    "source_reference": (
                        f"Reconstructed HE hour · {row[f'{signal.key}_previous_anchor']} → "
                        f"{row[f'{signal.key}_following_anchor']} · snapshot {directory.name}"
                    ),
                }
                for signal in bundle.signals
                if signal.direction
            }
            breached = (
                [] if pd.isna(decision.breached_signals) else decision.breached_signals.split(";")
            )
            return {
                "timestamp": opened.isoformat(),
                "decision_state": decision.decision_state,
                "decision_reason": decision.decision_reason,
                "anomaly_score": float(decision.anomaly_score)
                if pd.notna(decision.anomaly_score)
                else None,
                "alarm_breadth": len(breached),
                "breached_signals": breached,
                "condition_values": values,
                "analytics_version": directory.name,
                "score_basis": "Independent HE Isolation Forest and engineering policy",
            }
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
        if (
            alert.policy_id != config.input_alert_policy_id
            and alert.policy_id != "he-3301-hourly-alert-policy-v1"
        ):
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
                "Hourly condition values are retrospective reconstructions between dated weekly anchors, not measurements observed at opening."
                if "analytics_version" in snapshot
                else "Only measurements available at alert opening are included.",
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
        directory = active_snapshot(self.root)
        if directory:
            frame = pd.read_csv(directory / "hourly_alert_decisions.csv")
            return (
                pd.Timestamp(frame.timestamp.iloc[0]),
                pd.Timestamp(frame.timestamp.iloc[-1]),
                str(frame.decision_state.iloc[-1]),
            )
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
        directory = active_snapshot(self.root)
        if directory:
            scenario = pd.read_csv(directory / "hourly_scenario.csv")
            scores = pd.read_csv(directory / "hourly_anomaly_scores.csv")
            decisions = pd.read_csv(directory / "hourly_alert_decisions.csv")
            for frame in (scenario, scores, decisions):
                frame["timestamp"] = pd.to_datetime(frame.timestamp, errors="raise")
            timeline = scenario[["timestamp", "operating_mode", "run_status", "tube_dp", "heat_duty", "cold_outlet_temp", "heavy_ends"]].merge(
                scores[["timestamp", "anomaly_score", "anomaly_threshold", "is_anomaly"]],
                on="timestamp", validate="one_to_one",
            ).merge(
                decisions[["timestamp", "decision_state", "severity_rank", "alarm_breadth", "breached_signals"]],
                on="timestamp", validate="one_to_one",
            )
            if len(timeline) != len(scenario):
                raise ValueError("Incomplete HE telemetry snapshot")
            import json

            evaluation = json.loads((directory / "evaluation_report.json").read_text())
            note = validation_note(evaluation)
        else:
            bundle = self.equipment()
            rows = []
            for assessment in bundle.assessments:
                rows.append({
                    "timestamp": assessment.timestamp, "operating_mode": "WEEKLY_ASSESSMENT",
                    "run_status": "UNKNOWN", "anomaly_score": assessment.score,
                    "anomaly_threshold": 50.0, "is_anomaly": bool(assessment.breached_signals),
                    "decision_state": assessment.state,
                    "severity_rank": {"NORMAL": 0, "WATCH": 1, "WARNING": 2, "HIGH": 3, "CRITICAL": 4}[assessment.state],
                    "alarm_breadth": len(assessment.breached_signals),
                    "breached_signals": ";".join(assessment.breached_signals),
                    **{signal.key: next(point.value for point in signal.points if point.timestamp == assessment.timestamp)
                       for signal in bundle.signals if signal.direction},
                })
            timeline = pd.DataFrame(rows)
            timeline["timestamp"] = pd.to_datetime(timeline.timestamp)
            note = "Weekly engineering assessment; no hourly model is active."
        timeline = timeline.merge(
            self._operation_frame().drop(columns=["run_status"]),
            on="timestamp", how="left", validate="one_to_one",
        )
        if start:
            timeline = timeline.loc[timeline.timestamp.ge(pd.Timestamp(start))]
        if end:
            timeline = timeline.loc[timeline.timestamp.le(pd.Timestamp(end))]
        total = len(timeline)
        if total > max_points:
            timeline = timeline.iloc[np.unique(np.linspace(0, total - 1, max_points, dtype=int))]
        points = [self._telemetry_point({key: None if pd.isna(value) else value
                                       for key, value in record.items()})
                  for record in timeline.to_dict("records")]
        return TelemetrySeries(asset_id=asset_id, total_points=total,
                               returned_points=len(points), points=points, validation_note=note)

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
