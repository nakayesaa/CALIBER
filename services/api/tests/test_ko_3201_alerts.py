"""Acceptance tests for the trained KO-3201 alert decision outputs."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from scripts.build_ko_3201_alerts import run


ROOT = Path(__file__).resolve().parents[3]
SCORE_DIRECTORY = ROOT / "data/scored/ko_3201/v1"
FEATURE_DIRECTORY = ROOT / "data/features/ko_3201/v1"


@pytest.fixture(scope="module")
def alert_directory(tmp_path_factory: pytest.TempPathFactory) -> Path:
    required = [
        SCORE_DIRECTORY / "hourly_anomaly_scores.csv",
        FEATURE_DIRECTORY / "feature_table.csv",
        ROOT / "artifacts/models/ko_3201/v1/technical_validation.json",
    ]
    if not all(path.is_file() for path in required):
        pytest.skip("Trained KO-3201 outputs are not available in this checkout")
    output = tmp_path_factory.mktemp("ko_3201_alerts")
    report = run(ROOT, SCORE_DIRECTORY, FEATURE_DIRECTORY, output)
    assert report["status"] == "PASS"
    return output


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_alert_policy_groups_the_degradation_into_one_event(
    alert_directory: Path,
) -> None:
    events = read_rows(alert_directory / "alerts.csv")
    assert len(events) == 1
    event = events[0]
    assert event["highest_severity"] == "CRITICAL"
    assert event["status"] == "CLOSED"
    assert event["closure_reason"] == "OPERATING_MODE_TERMINATION"
    assert event["primary_driver"] == "condition.water_in_oil"


def test_alert_transitions_are_ordered(alert_directory: Path) -> None:
    transitions = read_rows(alert_directory / "alert_state_transitions.csv")
    assert [row["new_state"] for row in transitions] == [
        "WARNING",
        "HIGH",
        "CRITICAL",
        "CLOSED",
    ]


def test_decisions_exclude_evaluation_labels(alert_directory: Path) -> None:
    decisions = read_rows(alert_directory / "hourly_alert_decisions.csv")
    assert len(decisions) == 4368
    assert not {"scenario_phase", "health_state", "event_marker"}.intersection(
        decisions[0]
    )


def test_policy_suppresses_user_alerts_in_normal_and_recovery(
    alert_directory: Path,
) -> None:
    evaluation = json.loads(
        (alert_directory / "alert_evaluation.json").read_text(encoding="utf-8")
    )
    assert evaluation["normal_user_alert_hours"] == 0
    assert evaluation["recovery_user_alert_hours"] == 0
    assert evaluation["first_detection_by_state"] == {
        "WATCH": "2026-02-11T00:00:00+07:00",
        "WARNING": "2026-02-23T19:00:00+07:00",
        "HIGH": "2026-02-23T22:00:00+07:00",
        "CRITICAL": "2026-04-01T15:00:00+07:00",
    }
