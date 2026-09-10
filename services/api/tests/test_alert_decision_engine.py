"""Unit tests for label-independent alert decisions and event grouping."""

from __future__ import annotations

import pandas as pd
from pandas.testing import assert_frame_equal

from services.api.app.schemas.alerts import AlertPolicyConfig
from services.api.app.services.alerts.decision_engine import build_alert_decisions


def policy(cooldown_hours: int = 0) -> AlertPolicyConfig:
    return AlertPolicyConfig.model_validate(
        {
            "policy_id": "test-policy",
            "policy_version": "1.0.0",
            "asset_id": "asset-test",
            "input_model_id": "model-test",
            "operating_modes": {
                "excluded_modes": ["STARTUP", "OFFLINE_TRIP"],
                "cooldown_hours_after_excluded_mode": cooldown_hours,
            },
            "evidence": {
                "condition_driver_prefix": "condition.",
                "minimum_condition_driver_score": 50.0,
                "maximum_driver_rank": 3,
                "suppress_process_only_anomalies": True,
                "breach_watch_enabled": True,
                "alarm_ratio_columns": {"vibration": "vibration_alarm_ratio"},
            },
            "severity_rules": [
                {
                    "name": "WATCH",
                    "rank": 1,
                    "window_hours": 1,
                    "minimum_candidate_count": 1,
                    "minimum_consecutive_count": 1,
                    "minimum_alarm_breadth": 0,
                    "minimum_score": 50.0,
                },
                {
                    "name": "WARNING",
                    "rank": 2,
                    "window_hours": 3,
                    "minimum_candidate_count": 3,
                    "minimum_consecutive_count": 3,
                    "minimum_alarm_breadth": 0,
                    "minimum_score": 50.0,
                },
            ],
            "events": {
                "open_at_or_above_rank": 2,
                "clear_after_hours": 2,
                "terminal_operating_modes": ["OFFLINE_TRIP"],
            },
            "evaluation": {
                "normal_phases": ["NORMAL"],
                "degradation_phases": ["DEGRADATION"],
                "trip_phase": "TRIP",
                "recovery_phases": ["RECOVERY"],
            },
        }
    )


def input_frames(rows: int = 12) -> tuple[pd.DataFrame, pd.DataFrame]:
    timestamps = pd.date_range("2026-01-01", periods=rows, freq="1h", tz="UTC")
    scores = pd.DataFrame(
        {
            "timestamp": timestamps,
            "model_id": "model-test",
            "operating_mode": "RUNNING_STEADY",
            "run_status": "ON",
            "score_status": "SCORED",
            "anomaly_score": 10.0,
            "anomaly_threshold": 50.0,
            "is_anomaly": False,
            "top_driver_1": "",
            "top_driver_1_score": 0.0,
            "top_driver_2": "",
            "top_driver_2_score": 0.0,
            "top_driver_3": "",
            "top_driver_3_score": 0.0,
            "scenario_phase": "NORMAL",
            "health_state": "NORMAL",
            "event_marker": "",
        }
    )
    features = pd.DataFrame(
        {
            "timestamp": timestamps,
            "vibration_alarm_ratio": 0.8,
            "scenario_phase": "NORMAL",
        }
    )
    return scores, features


def mark_condition_anomaly(scores: pd.DataFrame, positions: list[int]) -> None:
    scores.loc[positions, "anomaly_score"] = 75.0
    scores.loc[positions, "is_anomaly"] = True
    scores.loc[positions, "top_driver_1"] = "condition.vibration"
    scores.loc[positions, "top_driver_1_score"] = 85.0


def test_three_consecutive_condition_anomalies_open_one_event() -> None:
    scores, features = input_frames()
    mark_condition_anomaly(scores, [3, 4, 5])
    result = build_alert_decisions(scores, features, policy())

    states = result.hourly_decisions["decision_state"].tolist()
    assert states[3:6] == ["WATCH", "WATCH", "WARNING"]
    assert len(result.events) == 1
    event = result.events[0]
    assert event.first_signal_at == scores.loc[3, "timestamp"].isoformat()
    assert event.opened_at == scores.loc[5, "timestamp"].isoformat()
    assert event.closed_at == scores.loc[7, "timestamp"].isoformat()
    assert event.highest_severity == "WARNING"
    assert event.primary_driver == "condition.vibration"


def test_process_only_anomaly_is_suppressed() -> None:
    scores, features = input_frames()
    scores.loc[3, "anomaly_score"] = 90.0
    scores.loc[3, "is_anomaly"] = True
    scores.loc[3, "top_driver_1"] = "process.feed_rate"
    scores.loc[3, "top_driver_1_score"] = 99.0
    result = build_alert_decisions(scores, features, policy())

    row = result.hourly_decisions.iloc[3]
    assert row["decision_state"] == "SUPPRESSED"
    assert row["suppression_reason"] == "PROCESS_ONLY_TRANSIENT"
    assert not result.events


def test_operating_mode_cooldown_suppresses_following_hours() -> None:
    scores, features = input_frames()
    scores.loc[2, "operating_mode"] = "STARTUP"
    scores.loc[2, "score_status"] = "EXCLUDED_MODE"
    scores.loc[2, "anomaly_score"] = None
    mark_condition_anomaly(scores, [3, 4])
    result = build_alert_decisions(scores, features, policy(cooldown_hours=2))

    decisions = result.hourly_decisions
    assert decisions.loc[2, "suppression_reason"] == "EXCLUDED_OPERATING_MODE"
    assert decisions.loc[3, "suppression_reason"] == "OPERATING_MODE_COOLDOWN"
    assert decisions.loc[4, "suppression_reason"] == "OPERATING_MODE_COOLDOWN"


def test_scenario_labels_cannot_change_decisions() -> None:
    scores, features = input_frames()
    mark_condition_anomaly(scores, [3, 4, 5])
    baseline = build_alert_decisions(scores, features, policy()).hourly_decisions

    changed_scores = scores.copy()
    changed_features = features.copy()
    changed_scores["scenario_phase"] = "TRIP"
    changed_scores["health_state"] = "CRITICAL"
    changed_scores["event_marker"] = "KNOWN_OUTCOME"
    changed_features["scenario_phase"] = "TRIP"
    changed = build_alert_decisions(
        changed_scores,
        changed_features,
        policy(),
    ).hourly_decisions
    assert_frame_equal(baseline, changed)
