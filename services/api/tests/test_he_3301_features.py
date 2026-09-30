"""The shared feature pipeline supports HE without process imputation or future leakage."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from scripts.build_ko_3201_features import load_config, run
from scripts.generate_he_3301_scenario import reconstruct
from services.api.app.services.analytics.feature_pipeline import build_features
from services.api.tests.test_he_3301_scenario import source_bundle

ROOT = Path(__file__).resolve().parents[3]


def test_condition_only_config_and_directional_limits():
    config = load_config(ROOT, ROOT / "data/catalog/he_3301_feature_config.yaml")
    assert config.process_signals == {}
    assert config.condition_signals["heat_duty"].direction_of_concern == "LOW"
    assert config.condition_signals["tube_dp"].direction_of_concern == "HIGH"
    assert len(load_config(ROOT).process_signals) == 4
    invalid = config.model_dump()
    invalid["condition_signals"]["heat_duty"]["source_column"] = "tube_dp"
    with pytest.raises(ValueError, match="unique"):
        type(config).model_validate(invalid)


def test_he_feature_causality_warmup_and_roles(tmp_path):
    bundle = source_bundle()
    scenario_config = yaml.safe_load(
        (ROOT / "data/catalog/he_3301_scenario_config.yaml").read_text()
    )
    frame, _ = reconstruct(bundle, scenario_config)
    config_path = ROOT / "data/catalog/he_3301_feature_config.yaml"
    config = load_config(ROOT, config_path)
    result = build_features(frame, config)
    assert len(result.model_feature_columns) == 28
    assert not any("process" in name for name in result.model_feature_columns)
    assert not set(config.output.metadata_columns + config.output.label_columns) & set(
        result.model_feature_columns
    )
    complete = result.feature_table.loc[
        result.feature_table.model_scoring_eligible, result.model_feature_columns
    ]
    assert np.isfinite(complete.to_numpy()).all()
    assert not result.feature_table.iloc[:24].model_scoring_eligible.any()
    restart = pd.Timestamp(scenario_config["restart"])
    excluded = (frame.timestamp >= restart) & (frame.timestamp < restart + pd.Timedelta(hours=24))
    assert not result.feature_table.loc[excluded, "model_scoring_eligible"].any()
    outside_may = frame.process_source_type.eq("NO_OPERATING_OBSERVATION")
    assert result.feature_table.loc[outside_may, "model_scoring_eligible"].sum() > 3000
    changed = frame.copy()
    changed.loc[changed.index >= 600, "tube_dp"] *= 5
    mutated = build_features(changed, config)
    pd.testing.assert_frame_equal(result.feature_table.iloc[:600], mutated.feature_table.iloc[:600])
    frame.to_csv(tmp_path / "hourly_scenario.csv", index=False)
    (tmp_path / "scenario_manifest.json").write_text(
        '{"scenario_id":"he-3301-six-month-v1","timestamp_count":4368,"phase_count":5}'
    )
    report = run(ROOT, tmp_path / "hourly_scenario.csv", tmp_path / "features", config_path)
    assert report["status"] == "PASS" and report["model_feature_count"] == 28
