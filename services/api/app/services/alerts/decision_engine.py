"""Configuration-driven alert decisions and deterministic event grouping."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from services.api.app.schemas.alerts import (
    AlertEvent,
    AlertPolicyConfig,
    AlertStateTransition,
    SeverityRule,
)


SCORE_INPUT_COLUMNS = [
    "timestamp",
    "model_id",
    "operating_mode",
    "run_status",
    "score_status",
    "anomaly_score",
    "anomaly_threshold",
    "is_anomaly",
    "top_driver_1",
    "top_driver_1_score",
    "top_driver_2",
    "top_driver_2_score",
    "top_driver_3",
    "top_driver_3_score",
]


@dataclass(frozen=True)
class AlertDecisionResult:
    hourly_decisions: pd.DataFrame
    events: list[AlertEvent]
    transitions: list[AlertStateTransition]


def build_alert_decisions(
    scored_timeline: pd.DataFrame,
    feature_table: pd.DataFrame,
    policy: AlertPolicyConfig,
) -> AlertDecisionResult:
    inputs = prepare_decision_inputs(scored_timeline, feature_table, policy)
    decisions = apply_alert_policy(inputs, policy)
    events, transitions = group_alert_events(decisions, policy)
    return AlertDecisionResult(
        hourly_decisions=decisions,
        events=events,
        transitions=transitions,
    )


def prepare_decision_inputs(
    scored_timeline: pd.DataFrame,
    feature_table: pd.DataFrame,
    policy: AlertPolicyConfig,
) -> pd.DataFrame:
    score_missing = set(SCORE_INPUT_COLUMNS) - set(scored_timeline.columns)
    ratio_columns = list(policy.evidence.alarm_ratio_columns.values())
    feature_missing = {"timestamp", *ratio_columns} - set(feature_table.columns)
    if score_missing:
        raise ValueError(f"Scored timeline is missing columns: {sorted(score_missing)}")
    if feature_missing:
        raise ValueError(f"Feature table is missing columns: {sorted(feature_missing)}")

    scores = scored_timeline[SCORE_INPUT_COLUMNS].copy()
    features = feature_table[["timestamp", *ratio_columns]].copy()
    scores["timestamp"] = pd.to_datetime(scores["timestamp"], errors="raise")
    features["timestamp"] = pd.to_datetime(features["timestamp"], errors="raise")
    for frame, name in [(scores, "scored timeline"), (features, "feature table")]:
        if not frame["timestamp"].is_monotonic_increasing:
            raise ValueError(f"{name} must be sorted chronologically")
        if frame["timestamp"].duplicated().any():
            raise ValueError(f"{name} timestamps must be unique")
    if len(scores) != len(features):
        raise ValueError("Scored timeline and feature table row counts differ")

    model_ids = set(scores["model_id"].dropna().astype(str))
    if model_ids != {policy.input_model_id}:
        raise ValueError(f"Unexpected model IDs: {sorted(model_ids)}")
    scores["is_anomaly"] = parse_boolean(scores["is_anomaly"], "is_anomaly")
    for column in ratio_columns:
        features[column] = pd.to_numeric(features[column], errors="raise")
    ratios = features[ratio_columns].to_numpy(dtype=float)
    if not np.isfinite(ratios).all() or (ratios < 0).any():
        raise ValueError("Alarm ratios must be finite and non-negative")

    merged = scores.merge(features, on="timestamp", how="inner", validate="one_to_one")
    if len(merged) != len(scores):
        raise ValueError("Scored timeline and feature timestamps do not match")
    deltas = merged["timestamp"].diff().dropna()
    if not (deltas == pd.Timedelta(hours=1)).all():
        raise ValueError("Alert decisions require a continuous hourly cadence")
    return merged


def parse_boolean(series: pd.Series, column: str) -> pd.Series:
    if pd.api.types.is_bool_dtype(series):
        return series.astype(bool)
    normalized = series.astype(str).str.strip().str.lower()
    allowed = {"true", "false", "1", "0"}
    unexpected = set(normalized) - allowed
    if unexpected:
        raise ValueError(f"Invalid boolean values in {column}: {sorted(unexpected)}")
    return normalized.isin({"true", "1"})


def apply_alert_policy(
    inputs: pd.DataFrame,
    policy: AlertPolicyConfig,
) -> pd.DataFrame:
    decisions = inputs.copy()
    ratio_by_signal = policy.evidence.alarm_ratio_columns
    ratio_columns = list(ratio_by_signal.values())
    ratios = decisions[ratio_columns]
    decisions["alarm_breadth"] = (ratios >= 1.0).sum(axis=1).astype(int)
    decisions["breached_signals"] = [
        ";".join(
            signal
            for signal, column in ratio_by_signal.items()
            if float(row[column]) >= 1.0
        )
        for _, row in decisions.iterrows()
    ]
    decisions["has_condition_driver"] = condition_driver_evidence(decisions, policy)
    excluded_mode = decisions["operating_mode"].isin(
        policy.operating_modes.excluded_modes
    )
    decisions["cooldown_active"] = cooldown_mask(
        decisions["timestamp"],
        excluded_mode,
        policy.operating_modes.cooldown_hours_after_excluded_mode,
    )
    decisions["suppression_reason"] = suppression_reasons(
        decisions,
        excluded_mode,
        policy,
    )
    suppressed = decisions["suppression_reason"].ne("")
    decisions["candidate_anomaly"] = (
        decisions["score_status"].eq("SCORED")
        & decisions["is_anomaly"]
        & ~suppressed
        & (decisions["has_condition_driver"] | decisions["alarm_breadth"].gt(0))
    )
    decisions["attention_signal"] = decisions["candidate_anomaly"]
    if policy.evidence.breach_watch_enabled:
        decisions["attention_signal"] |= decisions["alarm_breadth"].gt(0) & ~suppressed

    decisions["consecutive_candidate_count"] = consecutive_true_count(
        decisions["candidate_anomaly"]
    )
    decisions["decision_state"] = "NORMAL"
    decisions["severity_rank"] = 0
    decisions["decision_reason"] = "NO_ACTIONABLE_EVIDENCE"
    decisions.loc[suppressed, "decision_state"] = "SUPPRESSED"
    decisions.loc[suppressed, "decision_reason"] = decisions.loc[
        suppressed, "suppression_reason"
    ]

    breach_watch = decisions["attention_signal"] & ~decisions["candidate_anomaly"]
    decisions.loc[breach_watch, "decision_state"] = "WATCH"
    decisions.loc[breach_watch, "severity_rank"] = 1
    decisions.loc[breach_watch, "decision_reason"] = "ENGINEERING_LIMIT_BREACH"

    for rule in policy.severity_rules:
        apply_severity_rule(decisions, rule, suppressed)
    ordered_columns = [
        "timestamp",
        "model_id",
        "score_status",
        "operating_mode",
        "run_status",
        "anomaly_score",
        "anomaly_threshold",
        "is_anomaly",
        "candidate_anomaly",
        "attention_signal",
        "has_condition_driver",
        "alarm_breadth",
        "breached_signals",
        "consecutive_candidate_count",
        "cooldown_active",
        "suppression_reason",
        "decision_state",
        "severity_rank",
        "decision_reason",
        "top_driver_1",
        "top_driver_1_score",
        "top_driver_2",
        "top_driver_2_score",
        "top_driver_3",
        "top_driver_3_score",
        *ratio_columns,
    ]
    rolling_columns = [
        column
        for column in decisions.columns
        if column.startswith("candidate_count_") or column.startswith("peak_score_")
    ]
    return decisions[[*ordered_columns, *rolling_columns]]


def condition_driver_evidence(
    frame: pd.DataFrame,
    policy: AlertPolicyConfig,
) -> pd.Series:
    evidence = pd.Series(False, index=frame.index)
    prefix = policy.evidence.condition_driver_prefix
    minimum_score = policy.evidence.minimum_condition_driver_score
    for rank in range(1, 4):
        driver = frame[f"top_driver_{rank}"].fillna("").astype(str)
        score = pd.to_numeric(frame[f"top_driver_{rank}_score"], errors="coerce")
        evidence |= driver.str.startswith(prefix) & score.ge(minimum_score)
    return evidence


def cooldown_mask(
    timestamps: pd.Series,
    excluded_mode: pd.Series,
    cooldown_hours: int,
) -> pd.Series:
    if cooldown_hours == 0:
        return pd.Series(False, index=timestamps.index)
    last_excluded = timestamps.where(excluded_mode).ffill()
    hours_since = (timestamps - last_excluded) / pd.Timedelta(hours=1)
    return ~excluded_mode & hours_since.gt(0) & hours_since.le(cooldown_hours)


def suppression_reasons(
    frame: pd.DataFrame,
    excluded_mode: pd.Series,
    policy: AlertPolicyConfig,
) -> pd.Series:
    reasons = pd.Series("", index=frame.index, dtype=object)
    reasons.loc[frame["score_status"].eq("WARMUP")] = "MODEL_WARMUP"
    reasons.loc[excluded_mode] = "EXCLUDED_OPERATING_MODE"
    reasons.loc[frame["cooldown_active"]] = "OPERATING_MODE_COOLDOWN"
    process_only = (
        frame["score_status"].eq("SCORED")
        & frame["is_anomaly"]
        & ~frame["has_condition_driver"]
        & frame["alarm_breadth"].eq(0)
    )
    if policy.evidence.suppress_process_only_anomalies:
        reasons.loc[process_only & reasons.eq("")] = "PROCESS_ONLY_TRANSIENT"
    return reasons


def consecutive_true_count(values: pd.Series) -> pd.Series:
    groups = (~values.astype(bool)).cumsum()
    return values.astype(int).groupby(groups).cumsum().astype(int)


def apply_severity_rule(
    decisions: pd.DataFrame,
    rule: SeverityRule,
    suppressed: pd.Series,
) -> None:
    count_column = f"candidate_count_{rule.window_hours}h"
    peak_column = f"peak_score_{rule.window_hours}h"
    if count_column not in decisions:
        decisions[count_column] = (
            decisions["candidate_anomaly"]
            .astype(int)
            .rolling(rule.window_hours, min_periods=1)
            .sum()
            .astype(int)
        )
    if peak_column not in decisions:
        decisions[peak_column] = (
            decisions["anomaly_score"]
            .fillna(0.0)
            .rolling(rule.window_hours, min_periods=1)
            .max()
        )
    matched = (
        ~suppressed
        & decisions[count_column].ge(rule.minimum_candidate_count)
        & decisions["consecutive_candidate_count"].ge(
            rule.minimum_consecutive_count
        )
        & decisions["alarm_breadth"].ge(rule.minimum_alarm_breadth)
        & decisions[peak_column].ge(rule.minimum_score)
    )
    decisions.loc[matched, "decision_state"] = rule.name
    decisions.loc[matched, "severity_rank"] = rule.rank
    decisions.loc[matched, "decision_reason"] = f"POLICY_{rule.name}"


def group_alert_events(
    decisions: pd.DataFrame,
    policy: AlertPolicyConfig,
) -> tuple[list[AlertEvent], list[AlertStateTransition]]:
    events: list[AlertEvent] = []
    transitions: list[AlertStateTransition] = []
    active: dict[str, Any] | None = None
    pending_signal_at: pd.Timestamp | None = None
    clear_count = 0

    for row in decisions.itertuples(index=False):
        timestamp = pd.Timestamp(row.timestamp)
        if row.attention_signal:
            pending_signal_at = pending_signal_at or timestamp
        elif active is None:
            pending_signal_at = None

        if active is None and row.severity_rank >= policy.events.open_at_or_above_rank:
            sequence = len(events) + 1
            alert_id = f"alert-{policy.asset_id}-{sequence:04d}"
            active = new_active_event(
                alert_id,
                timestamp,
                pending_signal_at or timestamp,
                row,
            )
            transitions.append(
                AlertStateTransition(
                    alert_id=alert_id,
                    timestamp=timestamp.isoformat(),
                    previous_state="NO_EVENT",
                    new_state=row.decision_state,
                    reason=row.decision_reason,
                )
            )

        if active is None:
            continue
        update_active_event(active, timestamp, row, transitions)
        terminal = row.operating_mode in policy.events.terminal_operating_modes
        clear_count = 0 if row.attention_signal else clear_count + 1
        if terminal:
            events.append(
                close_active_event(
                    active,
                    timestamp,
                    "OPERATING_MODE_TERMINATION",
                    policy,
                )
            )
            transitions.append(
                AlertStateTransition(
                    alert_id=active["alert_id"],
                    timestamp=timestamp.isoformat(),
                    previous_state=active["highest_severity"],
                    new_state="CLOSED",
                    reason="OPERATING_MODE_TERMINATION",
                )
            )
            active = None
            pending_signal_at = None
            clear_count = 0
        elif clear_count >= policy.events.clear_after_hours:
            events.append(
                close_active_event(active, timestamp, "SUSTAINED_CLEAR", policy)
            )
            transitions.append(
                AlertStateTransition(
                    alert_id=active["alert_id"],
                    timestamp=timestamp.isoformat(),
                    previous_state=active["highest_severity"],
                    new_state="CLOSED",
                    reason="SUSTAINED_CLEAR",
                )
            )
            active = None
            pending_signal_at = None
            clear_count = 0

    if active is not None:
        final_timestamp = pd.Timestamp(decisions["timestamp"].iloc[-1])
        events.append(open_active_event(active, final_timestamp, policy))
    return events, transitions


def new_active_event(
    alert_id: str,
    timestamp: pd.Timestamp,
    first_signal_at: pd.Timestamp,
    row: Any,
) -> dict[str, Any]:
    score = float(row.anomaly_score) if pd.notna(row.anomaly_score) else 0.0
    return {
        "alert_id": alert_id,
        "first_signal_at": first_signal_at,
        "opened_at": timestamp,
        "highest_severity": row.decision_state,
        "highest_rank": int(row.severity_rank),
        "peak_score": score,
        "peak_score_at": timestamp,
        "last_evidence_at": timestamp,
        "driver_counts": Counter(),
        "breached_signals": set(),
    }


def update_active_event(
    active: dict[str, Any],
    timestamp: pd.Timestamp,
    row: Any,
    transitions: list[AlertStateTransition],
) -> None:
    if row.attention_signal:
        active["last_evidence_at"] = timestamp
        active["breached_signals"].update(
            signal for signal in str(row.breached_signals).split(";") if signal
        )
        if str(row.top_driver_1).startswith("condition."):
            active["driver_counts"][row.top_driver_1] += 1
    if pd.notna(row.anomaly_score) and float(row.anomaly_score) > active["peak_score"]:
        active["peak_score"] = float(row.anomaly_score)
        active["peak_score_at"] = timestamp
    if int(row.severity_rank) > active["highest_rank"]:
        previous = active["highest_severity"]
        active["highest_rank"] = int(row.severity_rank)
        active["highest_severity"] = row.decision_state
        transitions.append(
            AlertStateTransition(
                alert_id=active["alert_id"],
                timestamp=timestamp.isoformat(),
                previous_state=previous,
                new_state=row.decision_state,
                reason=row.decision_reason,
            )
        )


def close_active_event(
    active: dict[str, Any],
    closed_at: pd.Timestamp,
    reason: str,
    policy: AlertPolicyConfig,
) -> AlertEvent:
    return materialize_event(active, closed_at, "CLOSED", reason, policy)


def open_active_event(
    active: dict[str, Any],
    final_timestamp: pd.Timestamp,
    policy: AlertPolicyConfig,
) -> AlertEvent:
    return materialize_event(active, final_timestamp, "OPEN", None, policy)


def materialize_event(
    active: dict[str, Any],
    end_at: pd.Timestamp,
    status: str,
    closure_reason: str | None,
    policy: AlertPolicyConfig,
) -> AlertEvent:
    driver_counts: Counter[str] = active["driver_counts"]
    primary_driver = driver_counts.most_common(1)[0][0] if driver_counts else ""
    duration = float((end_at - active["opened_at"]) / pd.Timedelta(hours=1))
    return AlertEvent(
        alert_id=active["alert_id"],
        asset_id=policy.asset_id,
        model_id=policy.input_model_id,
        policy_id=policy.policy_id,
        first_signal_at=active["first_signal_at"].isoformat(),
        opened_at=active["opened_at"].isoformat(),
        closed_at=end_at.isoformat() if status == "CLOSED" else None,
        status=status,
        closure_reason=closure_reason,
        highest_severity=active["highest_severity"],
        highest_severity_rank=active["highest_rank"],
        peak_anomaly_score=round(active["peak_score"], 6),
        peak_score_at=active["peak_score_at"].isoformat(),
        last_evidence_at=active["last_evidence_at"].isoformat(),
        duration_hours=duration,
        primary_driver=primary_driver,
        breached_signals=sorted(active["breached_signals"]),
    )
