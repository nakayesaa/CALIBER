"""Validated file-backed access to pipeline and workflow artifacts."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, TypeVar

import numpy as np
import pandas as pd
from pydantic import BaseModel

from services.api.app.schemas.actions import ActionPlan
from services.api.app.schemas.alerts import AlertEvent, AlertStateTransition
from services.api.app.schemas.api import AssetSummary, TelemetryPoint, TelemetrySeries
from services.api.app.schemas.rca import RCARecord
from services.api.app.schemas.retrieval import (
    IncidentRetrievalResult,
    RAGEvidencePackage,
)


ModelT = TypeVar("ModelT", bound=BaseModel)


class ArtifactNotFoundError(FileNotFoundError):
    pass


class KO3201ArtifactRepository:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self._write_lock = threading.RLock()

    def pipeline_status(self) -> dict[str, bool]:
        return {
            "canonical": self._path("data/normalized/ko_3201/validation_report.json").is_file(),
            "features": self._path("data/features/ko_3201/v1/feature_table.csv").is_file(),
            "model_scores": self._path(
                "data/scored/ko_3201/v1/hourly_anomaly_scores.csv"
            ).is_file(),
            "alerts": self._path("data/alerts/ko_3201/v1/alerts.csv").is_file(),
            "retrieval": self._path(
                "data/retrieval/ko_3201/v1/rag_evidence_package.json"
            ).is_file(),
            "rca": self._rca_path().is_file(),
            "actions": bool(self._action_plan_paths()),
        }

    def list_assets(self) -> list[AssetSummary]:
        frame = self._read_csv("data/normalized/ko_3201/assets.csv")
        fields = list(AssetSummary.model_fields)
        return [AssetSummary.model_validate(record) for record in frame[fields].to_dict("records")]

    def get_asset(self, asset_id: str) -> AssetSummary:
        matches = [asset for asset in self.list_assets() if asset.asset_id == asset_id]
        if len(matches) != 1:
            raise ArtifactNotFoundError(f"Asset not found: {asset_id}")
        return matches[0]

    def list_alerts(self) -> list[AlertEvent]:
        frame = self._read_csv("data/alerts/ko_3201/v1/alerts.csv")
        events = [self._alert_from_record(record) for record in frame.to_dict("records")]
        return sorted(events, key=lambda event: event.opened_at, reverse=True)

    def get_alert(self, alert_id: str) -> AlertEvent:
        matches = [event for event in self.list_alerts() if event.alert_id == alert_id]
        if len(matches) != 1:
            raise ArtifactNotFoundError(f"Alert not found: {alert_id}")
        return matches[0]

    def get_alert_transitions(self, alert_id: str) -> list[AlertStateTransition]:
        frame = self._read_csv(
            "data/alerts/ko_3201/v1/alert_state_transitions.csv"
        )
        matching = frame.loc[frame["alert_id"].astype(str).eq(alert_id)]
        transitions = [
            AlertStateTransition.model_validate(record)
            for record in matching.to_dict("records")
        ]
        return sorted(transitions, key=lambda transition: transition.timestamp)

    def get_opening_snapshot(self, alert: AlertEvent) -> dict[str, object]:
        decisions = self._read_csv(
            "data/alerts/ko_3201/v1/hourly_alert_decisions.csv"
        )
        timestamps = pd.to_datetime(decisions["timestamp"], errors="raise")
        opening = decisions.loc[timestamps.eq(pd.Timestamp(alert.opened_at))]
        if len(opening) != 1:
            raise ArtifactNotFoundError(f"Opening snapshot not found: {alert.alert_id}")
        row = opening.iloc[0]
        return {
            "timestamp": pd.Timestamp(row["timestamp"]).isoformat(),
            "decision_state": str(row["decision_state"]),
            "decision_reason": str(row["decision_reason"]),
            "anomaly_score": float(row["anomaly_score"]),
            "anomaly_threshold": float(row["anomaly_threshold"]),
            "alarm_breadth": int(row["alarm_breadth"]),
            "breached_signals": self._semicolon_list(row["breached_signals"]),
            "top_drivers": [
                {
                    "name": str(row[f"top_driver_{rank}"]),
                    "score": float(row[f"top_driver_{rank}_score"]),
                }
                for rank in range(1, 4)
                if not pd.isna(row[f"top_driver_{rank}"])
            ],
        }

    def get_similar_incidents(self, alert_id: str) -> list[IncidentRetrievalResult]:
        frame = self._read_csv("data/retrieval/ko_3201/v1/retrieval_results.csv")
        query_id = f"query-{alert_id}-open"
        frame = frame.loc[frame["query_id"].astype(str).eq(query_id)]
        results: list[IncidentRetrievalResult] = []
        for record in frame.sort_values("rank").to_dict("records"):
            record["observed_symptoms"] = self._json_list(record["observed_symptoms"])
            record["business_consequences"] = self._json_list(
                record["business_consequences"]
            )
            record["match_reasons"] = self._json_list(record["match_reasons"])
            results.append(IncidentRetrievalResult.model_validate(record))
        return results

    def get_evidence_package(self, alert_id: str) -> RAGEvidencePackage:
        package = self._read_model(
            self._path("data/retrieval/ko_3201/v1/rag_evidence_package.json"),
            RAGEvidencePackage,
        )
        if package.query.alert_id != alert_id:
            raise ArtifactNotFoundError(f"Evidence package not found: {alert_id}")
        return package

    def telemetry(
        self,
        asset_id: str,
        start: str | None,
        end: str | None,
        max_points: int,
    ) -> TelemetrySeries:
        self.get_asset(asset_id)
        scenario = self._read_csv("data/synthetic/ko_3201/v1/hourly_scenario.csv")
        scores = self._read_csv("data/scored/ko_3201/v1/hourly_anomaly_scores.csv")
        decisions = self._read_csv(
            "data/alerts/ko_3201/v1/hourly_alert_decisions.csv"
        )
        scenario_columns = [
            "timestamp",
            "operating_mode",
            "run_status",
            "radial_vibration_micron",
            "water_in_oil_ppm",
            "lube_oil_pressure_barg",
            "bearing_metal_temperature_degc",
            "feed_rate_tph",
            "discharge_pressure_barg",
            "motor_current_a",
            "plant_rate_tph",
        ]
        score_columns = [
            "timestamp",
            "anomaly_score",
            "anomaly_threshold",
            "is_anomaly",
        ]
        decision_columns = [
            "timestamp",
            "decision_state",
            "severity_rank",
            "alarm_breadth",
            "breached_signals",
        ]
        timeline = scenario[scenario_columns].merge(
            scores[score_columns], on="timestamp", validate="one_to_one"
        ).merge(decisions[decision_columns], on="timestamp", validate="one_to_one")
        timeline["timestamp"] = pd.to_datetime(timeline["timestamp"], errors="raise")
        if start:
            timeline = timeline.loc[timeline["timestamp"].ge(pd.Timestamp(start))]
        if end:
            timeline = timeline.loc[timeline["timestamp"].le(pd.Timestamp(end))]
        total = len(timeline)
        if total > max_points:
            positions = np.linspace(0, total - 1, max_points, dtype=int)
            timeline = timeline.iloc[np.unique(positions)]
        points = [self._telemetry_point(record) for record in timeline.to_dict("records")]
        return TelemetrySeries(
            asset_id=asset_id,
            total_points=total,
            returned_points=len(points),
            points=points,
        )

    def timeline_summary(self, asset_id: str) -> tuple[pd.Timestamp, pd.Timestamp, str]:
        self.get_asset(asset_id)
        scenario = self._read_csv("data/synthetic/ko_3201/v1/hourly_scenario.csv")
        decisions = self._read_csv(
            "data/alerts/ko_3201/v1/hourly_alert_decisions.csv"
        )
        timestamps = pd.to_datetime(scenario["timestamp"], errors="raise")
        if timestamps.empty or decisions.empty:
            raise ArtifactNotFoundError("Timeline is empty")
        return timestamps.min(), timestamps.max(), str(decisions.iloc[-1]["decision_state"])

    def get_rca(self, alert_id: str) -> RCARecord | None:
        path = self._rca_path()
        if not path.is_file():
            return None
        record = self._read_model(path, RCARecord)
        return record if record.alert_id == alert_id else None

    def save_rca(self, record: RCARecord) -> None:
        self._write_model(self._rca_path(), record)

    def list_action_plans(self, alert_id: str) -> list[ActionPlan]:
        plans = {
            plan.plan_id: plan
            for plan in (
                self._read_model(path, ActionPlan)
                for path in self._action_plan_paths()
            )
        }
        return [plan for plan in plans.values() if plan.alert_id == alert_id]

    def get_action_plan(self, plan_id: str) -> ActionPlan:
        for path in self._action_plan_paths():
            plan = self._read_model(path, ActionPlan)
            if plan.plan_id == plan_id:
                return plan
        raise ArtifactNotFoundError(f"Action plan not found: {plan_id}")

    def find_action_plan(self, action_id: str) -> ActionPlan:
        for path in self._action_plan_paths():
            plan = self._read_model(path, ActionPlan)
            if any(action.action_id == action_id for action in plan.actions):
                return plan
        raise ArtifactNotFoundError(f"Action not found: {action_id}")

    def save_action_plan(self, plan: ActionPlan) -> None:
        path = self._action_plan_directory() / f"{plan.plan_id}.json"
        self._write_model(path, plan)

    def _alert_from_record(self, record: dict[str, Any]) -> AlertEvent:
        record["breached_signals"] = self._json_list(record["breached_signals"])
        for key in ("closed_at", "closure_reason"):
            if pd.isna(record[key]):
                record[key] = None
        return AlertEvent.model_validate(record)

    def _telemetry_point(self, record: dict[str, Any]) -> TelemetryPoint:
        record["timestamp"] = pd.Timestamp(record["timestamp"]).to_pydatetime()
        record["breached_signals"] = self._semicolon_list(record["breached_signals"])
        if pd.isna(record["anomaly_score"]):
            record["anomaly_score"] = None
        return TelemetryPoint.model_validate(record)

    def _read_csv(self, relative_path: str) -> pd.DataFrame:
        path = self._path(relative_path)
        if not path.is_file():
            raise ArtifactNotFoundError(f"Required artifact not found: {path}")
        return pd.read_csv(path)

    def _read_model(self, path: Path, model_type: type[ModelT]) -> ModelT:
        if not path.is_file():
            raise ArtifactNotFoundError(f"Artifact not found: {path}")
        return model_type.model_validate_json(path.read_text(encoding="utf-8"))

    def _write_model(self, path: Path, model: BaseModel) -> None:
        with self._write_lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(path.suffix + ".tmp")
            temporary.write_text(
                json.dumps(model.model_dump(mode="json"), indent=2, sort_keys=True)
                + "\n",
                encoding="utf-8",
            )
            temporary.replace(path)

    def _rca_path(self) -> Path:
        return self._path("data/rca/ko_3201/v1/rca_record.json")

    def _action_plan_directory(self) -> Path:
        return self._path("data/actions/ko_3201/v1/plans")

    def _action_plan_paths(self) -> list[Path]:
        paths = sorted(self._action_plan_directory().glob("*.json"))
        cli_path = self._path("data/actions/ko_3201/v1/action_plan.json")
        return [cli_path, *paths] if cli_path.is_file() else paths

    def _path(self, relative_path: str) -> Path:
        return self.root / relative_path

    @staticmethod
    def _json_list(value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item) for item in value]
        if value is None or pd.isna(value):
            return []
        decoded = json.loads(str(value))
        if not isinstance(decoded, list):
            raise ValueError("Expected a JSON list")
        return [str(item) for item in decoded]

    @staticmethod
    def _semicolon_list(value: Any) -> list[str]:
        if value is None or pd.isna(value):
            return []
        return [part for part in str(value).split(";") if part]
