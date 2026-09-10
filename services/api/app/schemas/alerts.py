"""Validated contracts for transparent alert decisions and event grouping."""

from __future__ import annotations

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class AlertConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SeverityRule(AlertConfigModel):
    name: str
    rank: int = Field(ge=1)
    window_hours: int = Field(ge=1)
    minimum_candidate_count: int = Field(ge=1)
    minimum_consecutive_count: int = Field(ge=0)
    minimum_alarm_breadth: int = Field(ge=0)
    minimum_score: float = Field(ge=0, le=100)

    @model_validator(mode="after")
    def validate_counts(self) -> "SeverityRule":
        if self.minimum_candidate_count > self.window_hours:
            raise ValueError("Candidate count cannot exceed the rule window")
        if self.minimum_consecutive_count > self.window_hours:
            raise ValueError("Consecutive count cannot exceed the rule window")
        return self


class OperatingModePolicy(AlertConfigModel):
    excluded_modes: list[str] = Field(min_length=1)
    cooldown_hours_after_excluded_mode: int = Field(ge=0)


class EvidencePolicy(AlertConfigModel):
    condition_driver_prefix: str
    minimum_condition_driver_score: float = Field(ge=0, le=100)
    maximum_driver_rank: int = Field(ge=1, le=5)
    suppress_process_only_anomalies: bool
    alarm_ratio_columns: dict[str, str]
    breach_watch_enabled: bool


class EventPolicy(AlertConfigModel):
    open_at_or_above_rank: int = Field(ge=1)
    clear_after_hours: int = Field(ge=1)
    terminal_operating_modes: list[str] = Field(min_length=1)


class AlertEvaluationConfig(AlertConfigModel):
    normal_phases: list[str] = Field(min_length=1)
    degradation_phases: list[str] = Field(min_length=1)
    trip_phase: str
    recovery_phases: list[str] = Field(min_length=1)


class AlertPolicyConfig(AlertConfigModel):
    policy_id: str
    policy_version: str
    asset_id: str
    input_model_id: str
    operating_modes: OperatingModePolicy
    evidence: EvidencePolicy
    severity_rules: list[SeverityRule] = Field(min_length=1)
    events: EventPolicy
    evaluation: AlertEvaluationConfig

    @model_validator(mode="after")
    def validate_policy(self) -> "AlertPolicyConfig":
        ranks = [rule.rank for rule in self.severity_rules]
        names = [rule.name for rule in self.severity_rules]
        if len(ranks) != len(set(ranks)):
            raise ValueError("Severity rule ranks must be unique")
        if len(names) != len(set(names)):
            raise ValueError("Severity rule names must be unique")
        if ranks != sorted(ranks):
            raise ValueError("Severity rules must be ordered by ascending rank")
        if self.events.open_at_or_above_rank not in ranks:
            raise ValueError("Event opening rank must match a severity rule")
        if not self.evidence.alarm_ratio_columns:
            raise ValueError("At least one alarm ratio column is required")
        return self


class AlertEvent(AlertConfigModel):
    alert_id: str
    asset_id: str
    model_id: str
    policy_id: str
    first_signal_at: str
    opened_at: str
    closed_at: str | None
    status: str
    closure_reason: str | None
    highest_severity: str
    highest_severity_rank: int
    peak_anomaly_score: float
    peak_score_at: str
    last_evidence_at: str
    duration_hours: float
    primary_driver: str
    breached_signals: list[str]


class AlertStateTransition(AlertConfigModel):
    alert_id: str
    timestamp: str
    previous_state: str
    new_state: str
    reason: str


class AlertEngineManifest(AlertConfigModel):
    policy_id: str
    policy_version: str
    input_model_id: str
    generated_at: AwareDatetime
    scored_timeline_sha256: str
    feature_table_sha256: str
    policy_sha256: str
    hourly_decision_rows: int
    alert_event_count: int
    state_transition_count: int
    decision_input_columns: list[str]
    evaluation_only_columns: list[str]


class AlertValidationCheck(AlertConfigModel):
    name: str
    status: str
    actual: int | float | str | bool


class AlertValidationReport(AlertConfigModel):
    status: str
    policy_id: str
    checks: list[AlertValidationCheck]
