"""HE reconstruction preserves source anchors, events, and deterministic coverage."""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from scripts.generate_he_3301_scenario import reconstruct, run
from services.api.app.schemas.equipment import EquipmentInvestigation

ROOT = Path(__file__).resolve().parents[3]


def source_bundle():
    path = ROOT / "data/normalized/he_3301/equipment.json"
    if not path.exists():
        pytest.skip("Private HE source bundle is not installed")
    return EquipmentInvestigation.model_validate_json(path.read_text())


def test_he_hourly_anchor_and_operation_integrity(tmp_path):
    bundle = source_bundle()
    config = yaml.safe_load((ROOT / "data/catalog/he_3301_scenario_config.yaml").read_text())
    first, audit = reconstruct(bundle, config)
    second, _ = reconstruct(bundle, config)
    pd.testing.assert_frame_equal(first, second)
    assert len(first) == 4368
    assert first.timestamp.is_unique
    assert first.timestamp.diff().dropna().eq(pd.Timedelta(hours=1)).all()
    assert len(audit) == 104
    assert all(row["source_value"] == row["scenario_value"] for row in audit)
    for point in bundle.operating_states:
        assert (
            first.loc[first.timestamp.eq(pd.Timestamp(point.timestamp)), "run_status"].item()
            == point.state
        )
    assert first.process_source_type.eq("SOURCE_HOURLY").sum() == 720
    manifest = run(ROOT, tmp_path)
    assert manifest["timestamp_count"] == 4368
    assert json.loads((tmp_path / "scenario_quality_report.json").read_text())["status"] == "PASS"
    context = pd.read_csv(tmp_path / "operating_context.csv")
    assert len(context) == 1440
    for signal in bundle.signals:
        if signal.cadence == "HOURLY":
            observed = context.loc[context.signal.eq(signal.key)]
            np.testing.assert_array_equal(observed.value, [point.value for point in signal.points])
    # Explicitly guard pandas timestamp-unit changes, not just source anchor pinning.
    midweek = first.loc[
        first.timestamp.eq(pd.Timestamp("2026-04-26T12:00:00+07:00")), "tube_dp"
    ].item()
    assert 0.70 < midweek < 0.76


def test_he_intervention_is_not_smoothed_and_sensitivity_keeps_anchors():
    bundle = source_bundle()
    config = yaml.safe_load((ROOT / "data/catalog/he_3301_scenario_config.yaml").read_text())
    frame, _ = reconstruct(bundle, config)
    restart = pd.Timestamp(config["restart"])
    before = frame.loc[frame.timestamp.eq(restart - pd.Timedelta(hours=1))].iloc[0]
    after = frame.loc[frame.timestamp.eq(restart)].iloc[0]
    assert before.tube_dp > 0.9 and after.tube_dp < 0.4
    settling = frame.loc[
        (frame.timestamp >= restart) & (frame.timestamp < restart + pd.Timedelta(hours=24))
    ]
    assert len(settling) == 24 and settling.operating_mode.eq("RESTART_SETTLING").all()
    assert not settling.training_eligible.any()
    for scale in [0, 2]:
        variant, audit = reconstruct(bundle, config, scale)
        assert (
            np.isfinite(variant[["tube_dp", "heat_duty", "cold_outlet_temp", "heavy_ends"]])
            .all()
            .all()
        )
        assert all(row["scenario_value"] == row["source_value"] for row in audit)
    with pytest.raises(ValueError, match="scale"):
        reconstruct(bundle, config, -1)
