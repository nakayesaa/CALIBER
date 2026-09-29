"""HE decisions preserve source cadence, direction and independent source claims."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import yaml

from scripts.ingest_he_3301 import assess, ingest
from services.api.app.schemas.equipment import EquipmentPoint, EquipmentSignal
from services.api.app.services.data.he_3301 import load_he_3301

ROOT = Path(__file__).resolve().parents[3]


def standalone_signal(direction="HIGH"):
    start = datetime(2026, 1, 1, tzinfo=UTC)
    return EquipmentSignal(
        key="pressure",
        label="Pressure",
        unit="bar",
        direction=direction,
        alarm_limit=0.6 if direction == "HIGH" else 0.2,
        trip_limit=0.9 if direction == "HIGH" else 0.1,
        cadence="WEEKLY",
        source_key="test_source",
        points=[
            EquipmentPoint(
                timestamp=start + timedelta(weeks=i),
                value=0.3,
                source_reference=f"test:row:{i}",
                source_status="NORMAL",
            )
            for i in range(4)
        ],
    )


@pytest.mark.skipif(
    not all(
        (ROOT / path).is_file()
        for path in [
            "data/raw/he_3301/performance.xlsx",
            "data/raw/he_3301/production.xlsx",
            "data/raw/he_3301/rca.pptx",
            "data/normalized/he_3301/equipment.json",
        ]
    ),
    reason="HE source integration requires downloaded immutable sources and make ingest-he artifact",
)
def test_he_source_anchors_and_weekly_assessment():
    result = ingest(ROOT)
    assert result == load_he_3301(ROOT)
    signals = {signal.key: signal for signal in result.signals}
    assert len(signals["tube_dp"].points) == 26
    assert len(signals["feed_rate"].points) == 720
    for signal in signals.values():
        interval = 604800 if signal.cadence == "WEEKLY" else 3600
        assert all(
            (right.timestamp - left.timestamp).total_seconds() == interval
            for left, right in zip(signal.points, signal.points[1:], strict=False)
        )
    assert signals["tube_dp"].points[20].value == 0.918
    assert signals["heat_duty"].points[20].value == 68.6
    assert signals["cold_outlet_temp"].direction == "LOW"
    assert signals["heavy_ends"].direction == "HIGH"
    assert all(a.state == "NORMAL" for a in result.assessments[:8])
    assert result.assessments[10].source_status == "ALARM"
    assert result.assessments[10].state == "WATCH"
    assert result.assessments[20].state == "CRITICAL"
    assert len(result.assessments[20].breached_signals) == 4
    assert all(a.state == "NORMAL" for a in result.assessments[21:])
    assert result.alert.closed_at is None
    assert result.reported_downtime_hours == 12
    assert sum(state.state == "OFF" for state in result.operating_states) == 13
    assert result.reported_production_loss_tonnes == 216
    assert len(result.source_actions) == 6
    assert result.source_actions[0].owner == "STA-02"
    assert "cleaning" in result.source_actions[0].title
    assert result.events[2].occurred_at.hour == 11
    assert set(signals) == {
        "tube_dp",
        "heat_duty",
        "cold_outlet_temp",
        "heavy_ends",
        "feed_rate",
        "plant_rate",
    }


def test_one_week_alarm_does_not_become_persistent_warning():
    policy = yaml.safe_load((ROOT / "data/catalog/he_3301_detection.yaml").read_text())
    signals = [standalone_signal()]
    signals[0].points[2].value = 0.61
    decisions = assess(signals, policy)
    assert [d.state for d in decisions] == ["NORMAL", "NORMAL", "WATCH", "NORMAL"]
    signals[0].points[3].value = 0.62
    assert assess(signals, policy)[3].state == "WARNING"


def test_duplicate_timestamp_rejected():
    signal = standalone_signal().model_dump()
    signal["points"][1]["timestamp"] = signal["points"][0]["timestamp"]
    with pytest.raises(ValueError, match="unique ascending"):
        EquipmentSignal.model_validate(signal)


def test_low_direction_and_invalid_limit_order():
    policy = yaml.safe_load((ROOT / "data/catalog/he_3301_detection.yaml").read_text())
    signal = standalone_signal("LOW")
    signal.points[1].value = 0.19
    signal.points[2].value = 0.18
    signal.points[3].value = 0.1
    assert [d.state for d in assess([signal], policy)] == ["NORMAL", "WATCH", "WARNING", "CRITICAL"]
    invalid = signal.model_dump()
    invalid["trip_limit"] = 0.4
    with pytest.raises(ValueError, match="more severe"):
        EquipmentSignal.model_validate(invalid)
