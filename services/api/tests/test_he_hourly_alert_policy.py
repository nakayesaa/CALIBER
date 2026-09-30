"""Hourly HE rules require raw persistence and preserve engineering trip indications."""

import pandas as pd

from services.api.app.schemas.alerts import AlertPolicyConfig
from services.api.app.services.alerts.decision_engine import apply_alert_policy


def policy():
    return AlertPolicyConfig.model_validate(
        {
            "policy_id": "he-test",
            "policy_version": "1",
            "asset_id": "asset-he-3301",
            "input_model_id": "he-model",
            "operating_modes": {
                "excluded_modes": ["MAINTENANCE"],
                "cooldown_hours_after_excluded_mode": 0,
            },
            "evidence": {
                "condition_driver_prefix": "condition.",
                "minimum_condition_driver_score": 50,
                "maximum_driver_rank": 1,
                "suppress_process_only_anomalies": False,
                "alarm_ratio_columns": {"tube_dp": "ratio"},
                "breach_watch_enabled": True,
                "trip_ratio_limits": {"tube_dp": 1.5},
            },
            "severity_rules": [
                {
                    "name": "WATCH",
                    "rank": 1,
                    "window_hours": 1,
                    "minimum_candidate_count": 1,
                    "minimum_consecutive_count": 1,
                    "minimum_alarm_breadth": 0,
                    "minimum_score": 50,
                },
                {
                    "name": "WARNING",
                    "rank": 2,
                    "window_hours": 8,
                    "minimum_candidate_count": 6,
                    "minimum_consecutive_count": 0,
                    "minimum_alarm_breadth": 0,
                    "minimum_score": 50,
                    "minimum_raw_breach_count": 6,
                },
                {
                    "name": "CRITICAL",
                    "rank": 4,
                    "window_hours": 1,
                    "minimum_candidate_count": 1,
                    "minimum_consecutive_count": 0,
                    "minimum_alarm_breadth": 1,
                    "minimum_score": 50,
                },
            ],
            "events": {
                "open_at_or_above_rank": 2,
                "clear_after_hours": 24,
                "terminal_operating_modes": ["MAINTENANCE"],
            },
            "evaluation": {
                "normal_phases": ["HEALTHY_BASELINE"],
                "degradation_phases": ["DEGRADATION"],
                "trip_phase": "TRIP",
                "recovery_phases": ["RECOVERY"],
            },
        }
    )


def inputs(ratios, score=90):
    return pd.DataFrame(
        {
            "timestamp": pd.date_range(
                "2026-01-01", periods=len(ratios), freq="h", tz="Asia/Jakarta"
            ),
            "model_id": "he-model",
            "score_status": "SCORED",
            "operating_mode": "RUNNING_STEADY",
            "run_status": "ON",
            "anomaly_score": score,
            "anomaly_threshold": 50,
            "is_anomaly": score >= 50,
            "top_driver_1": "condition.tube_dp",
            "top_driver_1_score": score,
            "ratio": ratios,
        }
    )


def test_rolling_model_memory_does_not_escalate_a_two_hour_raw_spike():
    result = apply_alert_policy(inputs([1.1, 1.1] + [0.5] * 22), policy())
    assert "WARNING" not in set(result.decision_state)
    sustained = apply_alert_policy(inputs([1.1] * 24), policy())
    assert "WARNING" in set(sustained.decision_state)


def test_trip_override_does_not_require_anomalous_model_score():
    result = apply_alert_policy(inputs([1.6], score=10), policy())
    assert result.iloc[0].decision_state == "CRITICAL"
    assert result.iloc[0].decision_reason == "ENGINEERING_TRIP_LIMIT"
    offline = inputs([1.6], score=10)
    offline["operating_mode"] = "MAINTENANCE"
    assert apply_alert_policy(offline, policy()).iloc[0].decision_state == "SUPPRESSED"
