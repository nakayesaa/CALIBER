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

from services.api.app.schemas.actions import ActionItem, ActionPlan, ActionStatus
from services.api.app.schemas.alerts import AlertEvent
from services.api.app.schemas.api import (
    AlertDetail,
    AssetOverview,
    AssetSummary,
    InvestigationEvidenceProgress,
    PlantRateSeries,
    PreparedWorkflow,
    ProductionImpact,
    SystemStatus,
    TelemetrySeries,
)
from services.api.app.schemas.coordination import (
    AssignmentInput,
    AssignmentResponse,
    CaseReview,
    CrossCheckInput,
    ExecutionEvidenceInput,
    Participant,
    ReviewInput,
)
from services.api.app.schemas.driver_analysis import DriverAnalysis
from services.api.app.schemas.effectiveness import EffectivenessReview
from services.api.app.schemas.equipment import EquipmentInvestigation
from services.api.app.schemas.rca import RCAGenerationConfig, RCARecord, RCAStatus
from services.api.app.schemas.retrieval import IncidentRetrievalResult
from services.api.app.schemas.traceability import (
    DataSourceDetail,
    DataSourceSummary,
    TraceClaim,
)
from services.api.app.services.actions.workflow import (
    build_action_plan,
    load_action_policy,
    transition_action,
    update_plan_status,
)
from services.api.app.services.artifacts import ArtifactNotFoundError, KO3201ArtifactRepository
from services.api.app.services.coordination import (
    assign_action,
    record_execution_evidence,
    require_role,
    require_verified,
    respond_to_assignment,
    review_case,
    submit_case,
)
from services.api.app.services.data.he_3301 import load_he_3301
from services.api.app.services.demo.prepared_he_rca import PreparedHERCAProvider
from services.api.app.services.demo.prepared_rca import PreparedRCAProvider
from services.api.app.services.demo.prepared_workflow import build_prepared_workflow
from services.api.app.services.driver_analysis import DriverAnalysisService
from services.api.app.services.effectiveness import build_effectiveness_review
from services.api.app.services.equipment_traceability import equipment_source_details
from services.api.app.services.he_repository import HE3301ArtifactRepository
from services.api.app.services.production_impact import load_production_impact_policy
from services.api.app.services.rca.case_assessment import assess_case, load_case_policy
from services.api.app.services.rca.generation import (
    OpenAIRCAProvider,
    RCAProvider,
    generate_rca_record,
    load_generation_config,
    transition_rca,
)
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
        self.he_repository = HE3301ArtifactRepository(self.root)
        self.provider_factory = provider_factory or OpenAIRCAProvider
        self.traceability = TraceabilityService(self.root)
        self.driver_analysis_service = DriverAnalysisService(self.root)
        self._mutation_lock = threading.RLock()
        load_dotenv(self.root / ".env", override=False)

    def status(self) -> SystemStatus:
        artifacts = self.repository.pipeline_status()
        required = ["canonical", "features", "model_scores", "alerts", "retrieval"]
        return SystemStatus(
            phase="equipment_verticals",
            api_status="ready" if all(artifacts[name] for name in required) else "partial",
            pipeline_artifacts=artifacts,
            llm_enabled=self._llm_ready(),
        )

    def list_assets(self) -> list[AssetSummary]:
        return [asset for repository in self._repositories() for asset in repository.list_assets()]

    def asset_overview(self, asset_id: str) -> AssetOverview:
        repository = self._repository_for_asset(asset_id)
        asset = repository.get_asset(asset_id)
        start, end, latest_state = repository.timeline_summary(asset_id)
        alerts = [alert for alert in repository.list_alerts() if alert.asset_id == asset_id]
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
        return [
            *self.traceability.list_sources(),
            *[detail.source for detail in equipment_source_details(self.root)],
        ]

    def data_source_detail(self, source_key: str) -> DataSourceDetail:
        for detail in equipment_source_details(self.root):
            if detail.source.source_key == source_key:
                return detail
        return self.traceability.source_detail(source_key)

    def equipment_investigation(self, asset_id: str) -> EquipmentInvestigation:
        if self._repository_for_asset(asset_id) is not self.he_repository:
            raise ArtifactNotFoundError(f"Source-series investigation unavailable for {asset_id}")
        bundle = load_he_3301(self.root)
        from services.api.app.services.he_analytics import hourly_analytics

        return bundle.model_copy(update={"analytics": hourly_analytics(self.root, bundle)})

    def traceability_claim(self, trace_id: str) -> TraceClaim:
        alert = max(
            self.repository.list_alerts(),
            key=lambda candidate: candidate.highest_severity_rank,
        )
        impact = self._production_impact(alert.asset_id, alert)
        effectiveness = self.effectiveness_review(alert.asset_id)
        return self.traceability.claim(trace_id, alert, impact, effectiveness)

    def effectiveness_review(self, asset_id: str) -> EffectivenessReview | None:
        if self._repository_for_asset(asset_id) is self.he_repository:
            return self.he_repository.effectiveness_review()
        check = self.repository.effectiveness_check(asset_id)
        return build_effectiveness_review(check) if check else None

    def driver_analysis(
        self,
        alert_id: str,
        requested_at: datetime | None = None,
    ) -> DriverAnalysis:
        repository = self._repository_for_alert(alert_id)
        if repository is self.he_repository:
            from services.api.app.services.he_analytics import active_snapshot

            active_snapshot(self.root)
            directory = repository._alert_snapshot(alert_id)
            if directory is None:
                raise ValueError(
                    "HE model attribution unavailable; run make he-train and make he-alerts"
                )
            alert = repository.get_alert(alert_id)
            return DriverAnalysisService(self.root, "he_3301", directory).for_alert(
                alert, requested_at
            )
        alert = repository.get_alert(alert_id)
        return self.driver_analysis_service.for_alert(alert, requested_at)

    def telemetry(
        self,
        asset_id: str,
        start: str | None,
        end: str | None,
        max_points: int,
    ) -> TelemetrySeries:
        return self._repository_for_asset(asset_id).telemetry(asset_id, start, end, max_points)

    def plant_rate_daily(self, asset_id: str) -> PlantRateSeries:
        return self._repository_for_asset(asset_id).plant_rate_daily(asset_id)

    def list_alerts(self, asset_id: str | None = None) -> list[AlertEvent]:
        repositories = [self._repository_for_asset(asset_id)] if asset_id else self._repositories()
        alerts = [alert for repository in repositories for alert in repository.list_alerts()]
        return [alert for alert in alerts if alert.asset_id == asset_id] if asset_id else alerts

    def alert_detail(self, alert_id: str) -> AlertDetail:
        repository = self._repository_for_alert(alert_id)
        alert = repository.get_alert(alert_id)
        rca = repository.get_rca(alert_id)
        action_plans = repository.list_action_plans(alert_id)
        return AlertDetail(
            alert=alert,
            state_transitions=repository.get_alert_transitions(alert_id),
            opening_snapshot=repository.get_opening_snapshot(alert),
            similar_incidents=repository.get_similar_incidents(alert_id),
            rca=rca,
            action_plans=action_plans,
            prepared_workflow=(self._prepared_workflow(alert_id) if rca is None else None),
        )

    def investigation_evidence(
        self, alert_id: str, as_of: datetime | None = None
    ) -> InvestigationEvidenceProgress:
        repository = self._repository_for_alert(alert_id)
        alert = repository.get_alert(alert_id)
        current_time = self._aware_time(as_of)
        if current_time < datetime.fromisoformat(alert.opened_at):
            raise ValueError("Evidence replay cannot precede the alert opening")
        events = repository.investigation_events(alert)
        policy = load_case_policy(self._policy_path(repository, "rca_case"))
        opening = repository.get_opening_snapshot(alert)
        return assess_case(alert_id, current_time, events, set(opening["breached_signals"]), policy)

    def similar_incidents(self, alert_id: str) -> list[IncidentRetrievalResult]:
        return self._repository_for_alert(alert_id).get_similar_incidents(alert_id)

    def get_rca(self, alert_id: str) -> RCARecord | None:
        return self._repository_for_alert(alert_id).get_rca(alert_id)

    def generate_rca(
        self,
        alert_id: str,
        requested_by: str,
        mode: Literal["ai", "prepared"] = "ai",
    ) -> RCARecord:
        with self._mutation_lock:
            repository = self._repository_for_alert(alert_id)
            existing = repository.get_rca(alert_id)
            if existing is not None:
                return existing
            if mode == "ai" and not self._llm_ready():
                raise LLMConfigurationError(
                    "OpenAI RCA generation requires CALIBER_LLM_ENABLED=true and OPENAI_API_KEY"
                )
            config = load_generation_config(self.root / "data/catalog/ko_3201_rca_generation.yaml")
            package = repository.get_evidence_package(alert_id)
            try:
                provider = (
                    self.provider_factory(config)
                    if mode == "ai"
                    else self._prepared_provider(repository)
                )
                record = generate_rca_record(package, provider, config, requested_by)
            except Exception as error:
                raise LLMGenerationError("RCA generation failed") from error
            repository.save_rca(record)
            return record

    def transition_rca(
        self,
        rca_id: str,
        status: RCAStatus,
        person: Participant,
        note: str,
        occurred_at: datetime | None,
    ) -> RCARecord:
        with self._mutation_lock:
            record = self._require_rca_id(rca_id)
            require_role(person, "SUPERVISOR")
            if status == RCAStatus.APPROVED:
                require_verified(self.case_review(record.alert_id))
            changed = transition_rca(
                record,
                status,
                person.display_name,
                note,
                self._aware_time(occurred_at),
            )
            self._repository_for_alert(record.alert_id).save_rca(changed)
            return changed

    def create_action_plan(
        self,
        rca_id: str,
        hypothesis_id: str,
        person: Participant,
    ) -> ActionPlan:
        with self._mutation_lock:
            rca = self._require_rca_id(rca_id)
            require_role(person, "SUPERVISOR")
            if rca.status != RCAStatus.APPROVED:
                raise ValueError("Action plans require an approved RCA")
            require_verified(self.case_review(rca.alert_id))
            repository = self._repository_for_alert(rca.alert_id)
            policy = load_action_policy(self._policy_path(repository, "action_policy"))
            plan = build_action_plan(
                rca,
                hypothesis_id,
                policy,
                rca.evidence_as_of.date(),
            )
            try:
                return repository.get_action_plan(plan.plan_id)
            except FileNotFoundError:
                repository.save_action_plan(plan)
                return plan

    def get_action_plan(self, plan_id: str) -> ActionPlan:
        for repository in self._repositories():
            try:
                return repository.get_action_plan(plan_id)
            except ArtifactNotFoundError:
                continue
        raise ArtifactNotFoundError(f"Action plan not found: {plan_id}")

    def case_review(self, alert_id: str) -> CaseReview:
        return self._repository_for_alert(alert_id).case_review(alert_id)

    def submit_cross_check(
        self, alert_id: str, data: CrossCheckInput, person: Participant
    ) -> CaseReview:
        with self._mutation_lock:
            changed = submit_case(self.case_review(alert_id), data, person, self._aware_time(None))
            self._repository_for_alert(alert_id).save_case_review(changed)
            return changed

    def review_cross_check(
        self, alert_id: str, data: ReviewInput, person: Participant
    ) -> CaseReview:
        with self._mutation_lock:
            changed = review_case(self.case_review(alert_id), data, person, self._aware_time(None))
            self._repository_for_alert(alert_id).save_case_review(changed)
            return changed

    def transition_action(
        self,
        action_id: str,
        status: ActionStatus,
        person: Participant,
        note: str,
        occurred_at: datetime | None,
        evidence: ExecutionEvidenceInput | None = None,
        expected_revision: int = 0,
    ) -> ActionPlan:
        def change(action: ActionItem, plan: ActionPlan) -> ActionItem:
            if action.revision != expected_revision:
                raise ValueError("Action changed; reload before recording a decision")
            rca = self._require_rca_id(plan.rca_id)
            require_verified(self.case_review(plan.alert_id))
            if status in {ActionStatus.APPROVED, ActionStatus.REJECTED}:
                require_role(person, "SUPERVISOR")
            action = record_execution_evidence(
                action, status, evidence, person, self._aware_time(None)
            )
            policy = load_action_policy(
                self._policy_path(self._repository_for_alert(plan.alert_id), "action_policy")
            )
            return transition_action(
                action,
                status,
                policy,
                rca.status,
                person.display_name,
                note,
                self._aware_time(occurred_at),
            )

        return self._change_action(action_id, change)

    def delegate_action(
        self, action_id: str, data: AssignmentInput, person: Participant
    ) -> ActionPlan:
        return self._change_action(
            action_id,
            lambda action, plan: assign_action(
                action, data, person, self.case_review(plan.alert_id), self._aware_time(None)
            ),
        )

    def respond_to_action(
        self, action_id: str, data: AssignmentResponse, person: Participant
    ) -> ActionPlan:
        return self._change_action(
            action_id,
            lambda action, _plan: respond_to_assignment(
                action, data, person, self._aware_time(None)
            ),
        )

    def _change_action(
        self, action_id: str, change: Callable[[ActionItem, ActionPlan], ActionItem]
    ) -> ActionPlan:
        with self._mutation_lock:
            plan = self._action_plan_for_item(action_id)
            actions = [
                change(action, plan).model_copy(update={"revision": action.revision + 1})
                if action.action_id == action_id
                else action
                for action in plan.actions
            ]
            changed = update_plan_status(plan.model_copy(update={"actions": actions}))
            self._repository_for_alert(plan.alert_id).save_action_plan(changed)
            return changed

    def _action_plan_for_item(self, action_id: str) -> ActionPlan:
        for repository in self._repositories():
            try:
                return repository.find_action_plan(action_id)
            except ArtifactNotFoundError:
                continue
        raise ArtifactNotFoundError(f"Action not found: {action_id}")

    def _require_rca_id(self, rca_id: str) -> RCARecord:
        alerts = self.list_alerts()
        for alert in alerts:
            record = self._repository_for_alert(alert.alert_id).get_rca(alert.alert_id)
            if record is not None and record.rca_id == rca_id:
                return record
        paths = [
            self.root / "data/rca/he_3301/v1/rca_record.json",
            *sorted((self.root / "data/rca/he_3301/v1/records").glob("*.json")),
        ]
        for path in paths:
            if path.is_file():
                record = RCARecord.model_validate_json(path.read_text())
                if record.rca_id == rca_id:
                    return record
        raise FileNotFoundError(f"RCA not found: {rca_id}")

    def _production_impact(
        self, asset_id: str, alert: AlertEvent | None
    ) -> ProductionImpact | None:
        if alert is None:
            return None
        if self._repository_for_asset(asset_id) is self.he_repository:
            return None
        policy = load_production_impact_policy(
            self.root / "data/catalog/ko_3201_production_impact.yaml"
        )
        return self.repository.production_impact(asset_id, alert, policy)

    def _prepared_workflow(self, alert_id: str) -> PreparedWorkflow:
        generation_config = load_generation_config(
            self.root / "data/catalog/ko_3201_rca_generation.yaml"
        )
        repository = self._repository_for_alert(alert_id)
        action_policy = load_action_policy(self._policy_path(repository, "action_policy"))
        rca, plan = build_prepared_workflow(
            repository.get_evidence_package(alert_id),
            generation_config,
            action_policy,
            self._prepared_provider(repository),
        )
        return PreparedWorkflow(rca=rca, action_plans=[plan])

    def _repositories(self) -> list[KO3201ArtifactRepository]:
        return (
            [self.repository, self.he_repository]
            if (self.root / "data/normalized/he_3301/equipment.json").is_file()
            else [self.repository]
        )

    def _repository_for_asset(self, asset_id: str) -> KO3201ArtifactRepository:
        for repository in self._repositories():
            if any(asset.asset_id == asset_id for asset in repository.list_assets()):
                return repository
        raise ArtifactNotFoundError(f"Asset not found: {asset_id}")

    def _repository_for_alert(self, alert_id: str) -> KO3201ArtifactRepository:
        for repository in self._repositories():
            try:
                repository.get_alert(alert_id)
                return repository
            except ArtifactNotFoundError:
                continue
        raise ArtifactNotFoundError(f"Alert not found: {alert_id}")

    def _policy_path(self, repository: KO3201ArtifactRepository, policy: str) -> Path:
        return self.root / "data/catalog" / f"{repository.asset_key}_{policy}.yaml"

    @staticmethod
    def _prepared_provider(repository: KO3201ArtifactRepository) -> RCAProvider:
        return (
            PreparedHERCAProvider() if repository.asset_key == "he_3301" else PreparedRCAProvider()
        )

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
