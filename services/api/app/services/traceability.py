"""Build traceability views from governed source and workflow artifacts."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from services.api.app.schemas.alerts import AlertEvent
from services.api.app.schemas.api import ProductionImpact
from services.api.app.schemas.effectiveness import EffectivenessReview
from services.api.app.schemas.traceability import (
    DataSourceDetail,
    DataSourceSummary,
    SourceFieldMapping,
    SourceQualityIssue,
    TraceClaim,
    TraceLineageStep,
    TraceRecordPreview,
    TraceSource,
)


class TraceabilityNotFoundError(KeyError):
    pass


class TraceabilityService:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def list_sources(self) -> list[DataSourceSummary]:
        return [self._source_summary(source) for source in self._manifest_sources()]

    def source_detail(self, source_key: str) -> DataSourceDetail:
        source = self._manifest_source(source_key)
        return DataSourceDetail(
            source=self._source_summary(source),
            local_path=str(source["local_path"]),
            parser=str(source["parser"]),
            checksum=str(source["sha256"]),
            mappings=self._field_mappings(source_key),
            quality_issues=self._quality_issues([source_key]),
        )

    def claim(
        self,
        trace_id: str,
        alert: AlertEvent,
        production_impact: ProductionImpact | None,
        effectiveness: EffectivenessReview | None,
    ) -> TraceClaim:
        builders: dict[str, Callable[[], TraceClaim]] = {
            "health-trajectory": lambda: self._health_claim(alert),
            "condition-insights": lambda: self._condition_claim(alert),
            "production-shortfall": lambda: self._production_claim(
                alert, production_impact
            ),
            "event-progression": lambda: self._event_claim(alert),
            "rca-indication": lambda: self._rca_claim(alert),
            "capa-plan": lambda: self._capa_claim(alert),
            "recovery-effectiveness": lambda: self._effectiveness_claim(
                alert, effectiveness
            ),
        }
        builder = builders.get(trace_id)
        if builder is None:
            raise TraceabilityNotFoundError(
                f"Traceability claim not found: {trace_id}"
            )
        return builder()

    def _effectiveness_claim(
        self,
        alert: AlertEvent,
        review: EffectivenessReview | None,
    ) -> TraceClaim:
        if review is None:
            raise TraceabilityNotFoundError("Effectiveness evidence is unavailable")
        preview = pd.DataFrame(
            [
                {
                    "signal": metric.label,
                    "before": metric.before,
                    "after": metric.after,
                    "unit": metric.unit,
                    "outcome": metric.outcome,
                }
                for metric in review.metrics
            ]
        )
        return self._claim(
            trace_id="recovery-effectiveness",
            title="Recovery and effectiveness evidence",
            value="Recovery confirmed" if review.recovery_confirmed else "Review required",
            unit=None,
            provenance="HUMAN_VERIFIED" if review.approval_status == "APPROVED" else "CALCULATED",
            summary="Post-repair condition observations are compared with the pre-intervention state, while recurrence and authorization remain separate closure decisions.",
            as_of=review.monitoring_end.isoformat(),
            calculation=[
                "Compare each anchor signal before intervention with its post-repair monitoring result.",
                f"Confirm signal direction across {review.monitoring_periods} normal weekly observations.",
                "Check for a recurring multi-signal degradation pattern before requesting closure approval.",
            ],
            source_keys=["equipment_performance_ko_3201"],
            lineage=[
                ("SOURCE", "Post-repair condition history", "equipment_performance_ko_3201"),
                ("CANONICAL", "Effectiveness check", "effectiveness_checks.csv"),
                ("VIEW", "Effectiveness review", "actions.effectiveness-review"),
            ],
            preview=self._preview(preview, list(preview.columns)),
        )

    def _health_claim(self, alert: AlertEvent) -> TraceClaim:
        scores = self._read_csv("data/scored/ko_3201/v1/hourly_anomaly_scores.csv")
        peak = scores.nlargest(5, "anomaly_score")
        return self._claim(
            trace_id="health-trajectory",
            title="Equipment health trajectory",
            value=f"{alert.peak_anomaly_score:.1f}",
            unit="peak anomaly score",
            provenance="MODEL_OUTPUT",
            summary="Hourly condition and operating context are standardized, transformed into model features, and scored by the approved KO-3201 anomaly model.",
            as_of=alert.peak_score_at,
            calculation=[
                "Canonical hourly observations are filtered by operating mode.",
                "Model-independent features are evaluated by KO-3201 Isolation Forest v1.",
                "Scores are calibrated to a 0–100 risk scale with threshold 50.",
            ],
            source_keys=["production_ko_3201", "equipment_performance_ko_3201"],
            lineage=[
                ("SOURCE", "Production and equipment records", "source_manifest.yaml"),
                ("CANONICAL", "Canonical hourly observations", "hourly_scenario.csv"),
                ("RULE", "Feature pipeline", "ko_3201_feature_config.yaml"),
                ("MODEL", "Isolation Forest v1", "ko_3201_anomaly_model.yaml"),
                ("VIEW", "Health trajectory", "overview.health-trajectory"),
            ],
            preview=self._preview(
                peak,
                ["timestamp", "anomaly_score", "anomaly_threshold", "is_anomaly"],
            ),
        )

    def _condition_claim(self, alert: AlertEvent) -> TraceClaim:
        observations = self._read_csv(
            "data/normalized/ko_3201/signal_observations.csv"
        )
        recent = observations.sort_values("timestamp").tail(8)
        return self._claim(
            trace_id="condition-insights",
            title="Condition insights",
            value="4 correlated signals",
            unit=None,
            provenance="STANDARDIZED",
            summary="Weekly engineering observations and hourly monitoring context are kept as separate representations and aligned to canonical signal names.",
            as_of=alert.last_evidence_at,
            calculation=[
                "Original units and cadence are retained in the signal mapping.",
                "Startup and excluded operating modes are separated before scoring.",
                "Known unit, cadence, and source disagreements remain visible.",
            ],
            source_keys=["equipment_performance_ko_3201", "production_ko_3201"],
            lineage=[
                ("SOURCE", "Condition History and PI tags", "signal_mapping.csv"),
                ("CANONICAL", "Canonical signal observations", "signal_observations.csv"),
                ("VIEW", "Condition insights", "overview.condition-insights"),
            ],
            preview=self._preview(
                recent,
                ["timestamp", "signal_id", "value", "unit", "quality_status"],
            ),
        )

    def _production_claim(
        self,
        alert: AlertEvent,
        impact: ProductionImpact | None,
    ) -> TraceClaim:
        if impact is None:
            raise TraceabilityNotFoundError("Production impact is unavailable")
        scenario = self._read_csv("data/synthetic/ko_3201/v1/hourly_scenario.csv")
        timestamps = pd.to_datetime(scenario["timestamp"], errors="raise")
        event_rows = scenario.loc[
            timestamps.between(impact.window_start, impact.window_end, inclusive="left")
        ].head(8)
        baseline = impact.baseline
        return self._claim(
            trace_id="production-shortfall",
            title="Estimated production shortfall",
            value=f"{impact.estimated_shortfall_tonnes:,.1f}",
            unit="tonnes",
            provenance="CALCULATED",
            summary="The event shortfall compares actual feed during the offline window with a contextual healthy-feed baseline at comparable pre-trip plant load.",
            as_of=impact.window_end.isoformat(),
            calculation=[
                f"Expected feed: {baseline.expected_feed_tph:.4f} t/h from {baseline.healthy_sample_count:,} comparable healthy hours.",
                f"Expected production: {impact.expected_feed_tonnes:,.3f} tonnes across {impact.offline_hours:g} hours.",
                f"Actual feed: {impact.actual_feed_tonnes:,.3f} tonnes.",
                f"Shortfall: {impact.expected_feed_tonnes:,.3f} − {impact.actual_feed_tonnes:,.3f} = {impact.estimated_shortfall_tonnes:,.3f} tonnes.",
            ],
            source_keys=["production_ko_3201"],
            lineage=[
                ("SOURCE", "Production Data · Sheet2", "production_ko_3201"),
                ("CANONICAL", "Hourly operating context", "hourly_scenario.csv"),
                ("RULE", "Contextual healthy baseline", "ko_3201_production_impact.yaml"),
                ("VIEW", "Production shortfall", "overview.production-shortfall"),
            ],
            preview=self._preview(
                event_rows,
                ["timestamp", "feed_rate_tph", "plant_rate_tph", "run_status"],
            ),
        )

    def _event_claim(self, alert: AlertEvent) -> TraceClaim:
        transitions = self._read_csv(
            "data/alerts/ko_3201/v1/alert_state_transitions.csv"
        )
        transitions = transitions.loc[transitions["alert_id"].eq(alert.alert_id)]
        return self._claim(
            trace_id="event-progression",
            title="Alert event progression",
            value=alert.highest_severity,
            unit="highest severity",
            provenance="CALCULATED",
            summary="Persistent hourly decisions are grouped into one governed alert and retained as an auditable state-transition history.",
            as_of=alert.closed_at or alert.last_evidence_at,
            calculation=[
                "Hourly model scores are evaluated with operating-mode and signal-breadth rules.",
                "Persistence rules promote WATCH, WARNING, HIGH, and CRITICAL states.",
                "Every state change retains its timestamp and decision reason.",
            ],
            source_keys=["production_ko_3201", "equipment_performance_ko_3201"],
            lineage=[
                ("SOURCE", "Hourly equipment context", "production_ko_3201"),
                ("MODEL", "Hourly anomaly scores", "hourly_anomaly_scores.csv"),
                ("RULE", "Alert decision policy", "ko_3201_alert_policy.yaml"),
                ("CANONICAL", "Alert state history", "alert_state_transitions.csv"),
                ("VIEW", "Event progression", "overview.event-progression"),
            ],
            preview=self._preview(
                transitions,
                ["timestamp", "previous_state", "new_state", "reason"],
            ),
        )

    def _rca_claim(self, alert: AlertEvent) -> TraceClaim:
        evidence = self._read_csv("data/normalized/ko_3201/evidence.csv")
        record_path = self.root / "data/rca/ko_3201/v1/rca_record.json"
        if record_path.is_file():
            record = self._read_json("data/rca/ko_3201/v1/rca_record.json")
            leading_title = str(record["generation"]["hypotheses"][0]["title"])
            provenance = "HUMAN_VERIFIED" if record["status"] == "APPROVED" else "AI_SYNTHESIS"
            evidence_as_of = str(record["evidence_as_of"])
        else:
            hypotheses = self._read_csv("data/normalized/ko_3201/hypotheses.csv")
            leading_title = str(hypotheses.sort_values("rank").iloc[0]["statement"])
            provenance = "RECORDED"
            evidence_as_of = alert.last_evidence_at
        return self._claim(
            trace_id="rca-indication",
            title="Leading probable root cause",
            value=leading_title,
            unit=None,
            provenance=provenance,
            summary="The RCA service combines model evidence, source-reported findings, and retrieved incident analogues into ranked hypotheses that require engineering review.",
            as_of=evidence_as_of,
            calculation=[
                "Retrieve similar incidents from the governed incident corpus.",
                "Assemble supporting, contradicting, and missing evidence.",
                "Generate ranked hypotheses without converting missing evidence into facts.",
            ],
            source_keys=[
                "equipment_performance_ko_3201",
                "incident_database",
                "rca_ko_3201",
            ],
            lineage=[
                ("SOURCE", "Equipment, incident, and RCA records", "source_manifest.yaml"),
                ("CANONICAL", "RAG evidence package", "rag_evidence_package.json"),
                ("AI", "Grounded RCA generation", "ko_3201_rca_generation.yaml"),
                ("VIEW", "RCA indication", "rca.leading-hypothesis"),
            ],
            preview=self._preview(
                evidence,
                ["evidence_id", "evidence_type", "title", "verification_status", "source_reference"],
            ),
        )

    def _capa_claim(self, alert: AlertEvent) -> TraceClaim:
        plan_paths = sorted(
            (self.root / "data/actions/ko_3201/v1/plans").glob("*.json")
        )
        if not plan_paths:
            actions = self._read_csv("data/normalized/ko_3201/actions.csv")
            preview_columns = ["action_type", "description", "owner", "priority", "status", "due_date"]
        else:
            plan = json.loads(plan_paths[0].read_text(encoding="utf-8"))
            actions = pd.DataFrame(plan["actions"])
            preview_columns = ["action_type", "title", "owner_role", "priority", "status", "due_date"]
        return self._claim(
            trace_id="capa-plan",
            title="Corrective and preventive action plan",
            value=f"{len(actions)} controlled actions",
            unit=None,
            provenance="HUMAN_VERIFIED",
            summary="Containment, corrective, and preventive work is linked to the approved RCA with owner, due date, completion evidence, and effectiveness criteria.",
            as_of=alert.closed_at or alert.last_evidence_at,
            calculation=[
                "The approved cause selects an applicable action-policy template.",
                "Each action receives an accountable owner and completion criteria.",
                "Completion alone does not close CAPA; effectiveness evidence is required.",
            ],
            source_keys=["rca_ko_3201", "equipment_performance_ko_3201"],
            lineage=[
                ("SOURCE", "Reported RCA actions", "rca_ko_3201"),
                ("RULE", "CA/PA action policy", "ko_3201_action_policy.yaml"),
                ("CANONICAL", "Controlled action records", "actions.csv"),
                ("VIEW", "CA/PA report", "actions.capa-report"),
            ],
            preview=self._preview(
                actions,
                preview_columns,
            ),
        )

    def _claim(
        self,
        *,
        trace_id: str,
        title: str,
        value: str,
        unit: str | None,
        provenance: str,
        summary: str,
        as_of: str,
        calculation: list[str],
        source_keys: list[str],
        lineage: list[tuple[str, str, str]],
        preview: TraceRecordPreview,
    ) -> TraceClaim:
        return TraceClaim.model_validate(
            {
                "trace_id": trace_id,
                "title": title,
                "value": value,
                "unit": unit,
                "provenance": provenance,
                "summary": summary,
                "as_of": as_of,
                "calculation": calculation,
                "lineage": [
                    TraceLineageStep(
                        sequence=index,
                        kind=kind,
                        label=label,
                        reference=reference,
                    )
                    for index, (kind, label, reference) in enumerate(lineage, 1)
                ],
                "sources": [self._trace_source(key) for key in source_keys],
                "quality_issues": self._quality_issues(source_keys),
                "preview": preview,
            }
        )

    def _trace_source(self, source_key: str) -> TraceSource:
        source = self._manifest_source(source_key)
        return TraceSource(
            source_key=source_key,
            title=str(source["title"]),
            location=str(source["local_path"]),
            role=str(source["role"]),
            mappings=self._field_mappings(source_key),
        )

    def _source_summary(self, source: dict[str, Any]) -> DataSourceSummary:
        source_key = str(source["source_key"])
        mappings = self._field_mappings(source_key)
        issues = self._quality_issues([source_key])
        status = "REFERENCE" if not mappings and source_key == "dataset_explanation" else (
            "REVIEW_REQUIRED" if issues else "CONNECTED"
        )
        return DataSourceSummary(
            source_key=source_key,
            title=str(source["title"]),
            domain=self._source_domain(source_key),
            role=str(source["role"]),
            cadence=self._source_cadence(source_key, mappings),
            status=status,
            mapping_count=len(mappings),
            quality_issue_count=len(issues),
            record_count=self._source_record_count(source_key),
            modified_at=str(source["modified_time"]),
            source_url=str(source["drive_url"]),
        )

    def _manifest_sources(self) -> list[dict[str, Any]]:
        path = self.root / "data/catalog/source_manifest.yaml"
        with path.open(encoding="utf-8") as stream:
            payload = yaml.safe_load(stream)
        return list(payload["sources"])

    def _manifest_source(self, source_key: str) -> dict[str, Any]:
        for source in self._manifest_sources():
            if source["source_key"] == source_key:
                return source
        raise TraceabilityNotFoundError(f"Data source not found: {source_key}")

    def _field_mappings(self, source_key: str) -> list[SourceFieldMapping]:
        mappings = self._read_csv("data/catalog/signal_mapping.csv")
        mappings = mappings.loc[mappings["source_key"].eq(source_key)]
        return [
            SourceFieldMapping(
                source_field=f"{row.source_sheet} · {row.source_column}",
                canonical_field=str(row.canonical_name),
                unit=str(row.unit),
                cadence=str(row.cadence),
                status=str(row.quality_status),
            )
            for row in mappings.itertuples()
        ]

    def _quality_issues(self, source_keys: list[str]) -> list[SourceQualityIssue]:
        issues = self._read_csv("data/normalized/ko_3201/quality_issues.csv")
        filenames = {
            Path(str(self._manifest_source(key)["local_path"])).name
            for key in source_keys
        }
        matching = issues.loc[
            issues["source_references"].astype(str).apply(
                lambda references: any(name in references for name in filenames)
            )
        ]
        return [
            SourceQualityIssue(
                issue_id=str(row.issue_id),
                severity=str(row.severity),
                flag=str(row.quality_flag),
                description=str(row.description),
                resolution_status=str(row.resolution_status),
            )
            for row in matching.itertuples()
        ]

    def _source_record_count(self, source_key: str) -> int | None:
        if source_key == "production_ko_3201":
            frame = self._read_csv(
                "data/normalized/ko_3201/production_observations.csv"
            )
            return int(frame["timestamp"].nunique())
        if source_key == "equipment_performance_ko_3201":
            frame = self._read_csv(
                "data/normalized/ko_3201/signal_observations.csv"
            )
            matching = frame.loc[
                frame["source_reference"].astype(str).str.contains(
                    "equipment_performance_ko_3201.xlsx", regex=False
                )
            ]
            return int(matching["timestamp"].nunique())
        paths = {
            "incident_database": "data/normalized/ko_3201/incidents.csv",
            "rca_ko_3201": "data/normalized/ko_3201/evidence.csv",
        }
        relative_path = paths.get(source_key)
        return len(self._read_csv(relative_path)) if relative_path else None

    @staticmethod
    def _source_domain(source_key: str) -> str:
        return {
            "production_ko_3201": "Operations",
            "equipment_performance_ko_3201": "Reliability",
            "incident_database": "Reliability history",
            "rca_ko_3201": "Maintenance and RCA",
            "dataset_explanation": "Data governance",
        }.get(source_key, "Manufacturing")

    @staticmethod
    def _source_cadence(
        source_key: str, mappings: list[SourceFieldMapping]
    ) -> str:
        cadences = sorted({mapping.cadence for mapping in mappings})
        if cadences:
            return " / ".join(cadences)
        return {
            "rca_ko_3201": "Case-based",
            "incident_database": "Event-based",
        }.get(source_key, "Reference")

    def _read_csv(self, relative_path: str) -> pd.DataFrame:
        return pd.read_csv(self.root / relative_path)

    def _read_json(self, relative_path: str) -> dict[str, Any]:
        return json.loads((self.root / relative_path).read_text(encoding="utf-8"))

    @staticmethod
    def _preview(frame: pd.DataFrame, columns: list[str]) -> TraceRecordPreview:
        available = [column for column in columns if column in frame.columns]
        records = frame[available].copy().replace({pd.NA: None}).to_dict("records")
        clean_records = [
            {
                key: None if pd.isna(value) else value.item() if hasattr(value, "item") else value
                for key, value in record.items()
            }
            for record in records
        ]
        return TraceRecordPreview(columns=available, rows=clean_records)
