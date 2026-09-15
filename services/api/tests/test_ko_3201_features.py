"""Acceptance tests for the KO-3201 feature pipeline."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from scripts.build_ko_3201_features import load_config
from scripts.build_ko_3201_features import run as build_feature_outputs
from scripts.generate_ko_3201_scenario import run as build_scenario
from scripts.ingest_ko_3201 import run as build_canonical
from services.api.app.services.analytics.feature_pipeline import (
    build_features,
    validate_hourly_input,
)

ROOT = Path(__file__).resolve().parents[3]
RAW_DIRECTORY = ROOT / "data/raw/ko_3201"


@dataclass(frozen=True)
class FeatureFixture:
    scenario_csv: Path
    output_directory: Path


@pytest.fixture(scope="module")
def feature_fixture(tmp_path_factory: pytest.TempPathFactory) -> FeatureFixture:
    if not RAW_DIRECTORY.is_dir():
        pytest.skip("Raw KO-3201 files are not available in this checkout")
    base = tmp_path_factory.mktemp("ko_3201_features")
    canonical = base / "canonical"
    scenario = base / "scenario"
    output = base / "features"
    build_canonical(ROOT, canonical)
    build_scenario(ROOT, canonical, scenario)
    report = build_feature_outputs(ROOT, scenario / "hourly_scenario.csv", output)
    assert report["status"] == "PASS"
    return FeatureFixture(scenario / "hourly_scenario.csv", output)


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_output_contract_and_eligibility_counts(
    feature_fixture: FeatureFixture,
) -> None:
    manifest = json.loads(
        (feature_fixture.output_directory / "feature_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["row_count"] == 4368
    assert manifest["complete_row_count"] == 4345
    assert manifest["training_row_count"] == 1479
    assert manifest["scoring_row_count"] == 4308
    assert manifest["lookback_hours"] == 24
    assert len(manifest["model_feature_columns"]) == 40
    assert len(manifest["explanation_feature_columns"]) == 6


def test_catalog_separates_model_and_explanation_features(
    feature_fixture: FeatureFixture,
) -> None:
    catalog = read_rows(feature_fixture.output_directory / "feature_catalog.csv")
    roles = pd.Series(row["feature_role"] for row in catalog).value_counts().to_dict()
    assert roles == {"MODEL_INPUT": 40, "EXPLANATION_ONLY": 6}

    manifest = json.loads(
        (feature_fixture.output_directory / "feature_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    forbidden = {
        *manifest["label_columns"],
        *manifest["metadata_columns"],
        *manifest["eligibility_columns"],
    }
    assert not forbidden.intersection(manifest["model_feature_columns"])


def test_trailing_features_match_source_calculation(
    feature_fixture: FeatureFixture,
) -> None:
    source = pd.read_csv(feature_fixture.scenario_csv)
    features = pd.read_csv(feature_fixture.output_directory / "feature_table.csv")
    row = 100
    expected_mean = source.loc[row - 5 : row, "water_in_oil_ppm"].mean()
    expected_delta = (
        source.loc[row, "lube_oil_pressure_barg"]
        - source.loc[row - 1, "lube_oil_pressure_barg"]
    )
    assert features.loc[row, "condition__water_in_oil__mean_6h"] == pytest.approx(
        expected_mean
    )
    assert features.loc[
        row, "condition__lube_oil_pressure__delta_1h"
    ] == pytest.approx(expected_delta)
    assert features.loc[
        row, "condition__lube_oil_pressure__alarm_ratio"
    ] == pytest.approx(1.4 / source.loc[row, "lube_oil_pressure_barg"])


def test_future_changes_cannot_modify_past_features(
    feature_fixture: FeatureFixture,
) -> None:
    config = load_config(ROOT)
    source = pd.read_csv(feature_fixture.scenario_csv)
    validated = validate_hourly_input(source, config, expected_rows=4368)
    baseline = build_features(validated, config)

    changed = validated.copy()
    change_at = 2000
    changed.loc[change_at, "radial_vibration_micron"] *= 1.5
    changed.loc[change_at, "feed_rate_tph"] *= 0.5
    rebuilt = build_features(changed, config)
    columns = baseline.model_feature_columns + baseline.explanation_feature_columns
    assert_frame_equal(
        baseline.feature_table.loc[: change_at - 1, columns],
        rebuilt.feature_table.loc[: change_at - 1, columns],
    )


def test_training_matrix_is_complete_and_threshold_safe(
    feature_fixture: FeatureFixture,
) -> None:
    table = pd.read_csv(feature_fixture.output_directory / "feature_table.csv")
    training = table.loc[table["model_training_eligible"]]
    assert len(training) == 1479
    assert training["feature_complete"].all()
    assert training["training_eligible"].all()
    assert training["operating_mode"].eq("RUNNING_STEADY").all()
    assert training["run_status"].eq("ON").all()
    assert training["explanation__alarm_breadth"].eq(0).all()

    matrix = pd.read_csv(feature_fixture.output_directory / "training_matrix.csv")
    assert len(matrix) == 1479
    assert np.isfinite(matrix.drop(columns="timestamp").to_numpy(dtype=float)).all()


def test_broken_hourly_cadence_is_rejected(feature_fixture: FeatureFixture) -> None:
    config = load_config(ROOT)
    source = pd.read_csv(feature_fixture.scenario_csv).drop(index=100).reset_index(drop=True)
    with pytest.raises(ValueError, match="rows, expected"):
        validate_hourly_input(source, config, expected_rows=4368)
