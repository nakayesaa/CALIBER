"""Application service coordinating artifacts, AI generation, and workflows."""

from __future__ import annotations

import os
import threading
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

from services.api.app.schemas.actions import ActionPlan, ActionStatus
from services.api.app.schemas.alerts import AlertEvent
from services.api.app.schemas.api import (
    AlertDetail,
    AssetOverview,
    AssetSummary,
    ProductionImpact,
    SystemStatus,
    TelemetrySeries,
)
from services.api.app.schemas.rca import RCAGenerationConfig, RCARecord, RCAStatus
from services.api.app.schemas.retrieval import IncidentRetrievalResult
from services.api.app.schemas.traceability import DataSourceDetail, DataSourceSummary, TraceClaim
from services.api.app.services.actions.workflow import (
    build_action_plan,
    load_action_policy,
    transition_action,
    update_plan_status,
)
from services.api.app.services.artifacts import KO3201ArtifactRepository
from services.api.app.services.demo.prepared_rca import PreparedRCAProvider
from services.api.app.services.rca.generation import (
    OpenAIRCAProvider,
    RCAProvider,
    generate_rca_record,
    load_generation_config,
    transition_rca,
)
from services.api.app.services.production_impact import load_production_impact_policy
from services.api.app.services.traceability import TraceabilityService


LOCAL_TIMEZONE = ZoneInfo("Asia/Jakarta")
ProviderFactory = Callable[[RCAGenerationConfig], RCAProvider]


class LLMConfigurationError(RuntimeError):
    pass


class LLMGenerationError(RuntimeError):
    pass


class BackendService:
    def __init__(
        self,
        root: Path,
        repository: KO3201ArtifactRepository | None = None,
        provider_factory: ProviderFactory | None = None,
    ) -> None:
        self.root = root.resolve()
        self.repository = repository or KO3201ArtifactRepository(self.root)
        self.provider_factory = provider_factory or OpenAIRCAProvider
        self.traceability = TraceabilityService(self.root)
        self._mutation_lock = threading.RLock()
        load_dotenv(self.root / ".env", override=False)

    def status(self) -> SystemStatus:
        artifacts = self.repository.pipeline_status()
        required = ["canonical", "features", "model_scores", "alerts", "retrieval"]
        return SystemStatus(
            phase="ko_3201_vertical_slice",
            api_status="ready" if all(artifacts[name] for name in required) else "partial",
            pipeline_artifacts=artifacts,
            llm_enabled=self._llm_ready(),
        )

    def list_assets(self) -> list[AssetSummary]:
        return self.repository.list_assets()

    def asset_overview(self, asset_id: str) -> AssetOverview:
        asset = self.repository.get_asset(asset_id)
        start, end, latest_state = self.repository.timeline_summary(asset_id)
        alerts = [alert for alert in self.repository.list_alerts() if alert.asset_id == asset_id]
        highest = max(alerts, key=lambda alert: alert.highest_severity_rank, default=None)
        production_impact = self._production_impact(asset_id, highest)
        return AssetOverview(
            asset=asset,
            timeline_start=start.to_pydatetime(),
            timeline_end=end.to_pydatetime(),
            latest_decision_state=latest_state,
            highest_alert_severity=highest.highest_severity if highest else None,
            alert_count=len(alerts),
            production_impact=production_impact,
        )

    def list_data_sources(self) -> list[DataSourceSummary]:
        return self.traceability.list_sources()

    def data_source_detail(self, source_key: str) -> DataSourceDetail:
        return self.traceability.source_detail(source_key)

    def traceability_claim(self, trace_id: str) -> TraceClaim:
        alert = max(
            self.repository.list_alerts(),
            key=lambda candidate: candidate.highest_severity_rank,
        )
        impact = self._production_impact(alert.asset_id, alert)
        return self.traceability.claim(trace_id, alert, impact)

    def telemetry(
        self,
        asset_id: str,
        start: str | None,
        end: str | None,
        max_points: int,
    ) -> TelemetrySeries:
        return self.repository.telemetry(asset_id, start, end, max_points)

    def list_alerts(self, asset_id: str | None = None) -> list[AlertEvent]:
        alerts = self.repository.list_alerts()
        return [alert for alert in alerts if alert.asset_id == asset_id] if asset_id else alerts

    def alert_detail(self, alert_id: str) -> AlertDetail:
        alert = self.repository.get_alert(alert_id)
        return AlertDetail(
            alert=alert,
            state_transitions=self.repository.get_alert_transitions(alert_id),
            opening_snapshot=self.repository.get_opening_snapshot(alert),
            similar_incidents=self.repository.get_similar_incidents(alert_id),
            rca=self.repository.get_rca(alert_id),
            action_plans=self.repository.list_action_plans(alert_id),
        )

    def similar_incidents(self, alert_id: str) -> list[IncidentRetrievalResult]:
        self.repository.get_alert(alert_id)
        return self.repository.get_similar_incidents(alert_id)

    def get_rca(self, alert_id: str) -> RCARecord | None:
        self.repository.get_alert(alert_id)
        return self.repository.get_rca(alert_id)

    def generate_rca(
        self,
        alert_id: str,
        requested_by: str,
        mode: Literal["ai", "prepared"] = "ai",
    ) -> RCARecord:
        with self._mutation_lock:
            self.repository.get_alert(alert_id)
            existing = self.repository.get_rca(alert_id)
            if existing is not None:
                return existing
            if mode == "ai" and not self._llm_ready():
                raise LLMConfigurationError(
                    "OpenAI RCA generation requires CALIBER_LLM_ENABLED=true "
                    "and OPENAI_API_KEY"
                )
            config = load_generation_config(
                self.root / "data/catalog/ko_3201_rca_generation.yaml"
            )
            package = self.repository.get_evidence_package(alert_id)
            try:
                provider = (
                    self.provider_factory(config)
                    if mode == "ai"
                    else PreparedRCAProvider()
                )
                record = generate_rca_record(package, provider, config, requested_by)
            except Exception as error:
                raise LLMGenerationError("RCA generation failed") from error
            self.repository.save_rca(record)
            return record

    def transition_rca(
        self,
        rca_id: str,
        status: RCAStatus,
        actor: str,
        note: str,
        occurred_at: datetime | None,
    ) -> RCARecord:
        with self._mutation_lock:
            record = self._require_rca_id(rca_id)
            changed = transition_rca(
                record,
                status,
                actor,
                note,
                self._aware_time(occurred_at),
            )
            self.repository.save_rca(changed)
            return changed

    def create_action_plan(
        self,
        rca_id: str,
        hypothesis_id: str,
    ) -> ActionPlan:
        with self._mutation_lock:
            rca = self._require_rca_id(rca_id)
            if rca.status != RCAStatus.APPROVED:
                raise ValueError("Action plans require an approved RCA")
            policy = load_action_policy(
                self.root / "data/catalog/ko_3201_action_policy.yaml"
            )
            plan = build_action_plan(
                rca,
                hypothesis_id,
                policy,
                rca.evidence_as_of.date(),
            )
            try:
                return self.repository.get_action_plan(plan.plan_id)
            except FileNotFoundError:
                self.repository.save_action_plan(plan)
                return plan

    def get_action_plan(self, plan_id: str) -> ActionPlan:
        return self.repository.get_action_plan(plan_id)

    def transition_action(
        self,
        action_id: str,
        status: ActionStatus,
        actor: str,
        note: str,
        occurred_at: datetime | None,
    ) -> ActionPlan:
        with self._mutation_lock:
            plan = self.repository.find_action_plan(action_id)
            rca = self._require_rca_id(plan.rca_id)
            policy = load_action_policy(
                self.root / "data/catalog/ko_3201_action_policy.yaml"
            )
            actions = []
            for action in plan.actions:
                if action.action_id == action_id:
                    action = transition_action(
                        action,
                        status,
                        policy,
                        rca.status,
                        actor,
                        note,
                        self._aware_time(occurred_at),
                    )
                actions.append(action)
            changed = update_plan_status(plan.model_copy(update={"actions": actions}))
            self.repository.save_action_plan(changed)
            return changed

    def _require_rca_id(self, rca_id: str) -> RCARecord:
        alerts = self.repository.list_alerts()
        for alert in alerts:
            record = self.repository.get_rca(alert.alert_id)
            if record is not None and record.rca_id == rca_id:
                return record
        raise FileNotFoundError(f"RCA not found: {rca_id}")

    def _production_impact(
        self, asset_id: str, alert: AlertEvent | None
    ) -> ProductionImpact | None:
        if alert is None:
            return None
        policy = load_production_impact_policy(
            self.root / "data/catalog/ko_3201_production_impact.yaml"
        )
        return self.repository.production_impact(asset_id, alert, policy)

    @staticmethod
    def _aware_time(value: datetime | None) -> datetime:
        resolved = value or datetime.now(LOCAL_TIMEZONE)
        if resolved.tzinfo is None or resolved.utcoffset() is None:
            raise ValueError("Workflow timestamps must include a timezone")
        return resolved

    @staticmethod
    def _llm_ready() -> bool:
        enabled = os.getenv("CALIBER_LLM_ENABLED", "false").strip().lower() == "true"
        return enabled and bool(os.getenv("OPENAI_API_KEY"))
