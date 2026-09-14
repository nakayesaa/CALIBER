"""Unit tests for anomaly utilities that do not fit a model."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from services.api.app.schemas.anomaly import ScoreCalibrationConfig
from services.api.app.services.analytics.anomaly_model import (
    calibrate_score_transform,
    chronological_split,
    driver_feature_groups,
    normalize_driver_impacts,
    numeric_matrix,
)


def calibration_config() -> ScoreCalibrationConfig:
    return ScoreCalibrationConfig(
        anomaly_quantile=0.99,
        median_normalized_score=10.0,
        threshold_normalized_score=50.0,
        exponent_clip=60.0,
    )


def test_chronological_split_has_no_overlap() -> None:
    frame = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01", periods=10, freq="1h", tz="UTC"),
            "feature": np.arange(10),
        }
    )
    split = chronological_split(frame, 0.8, minimum_fit_rows=6, minimum_calibration_rows=2)
    assert len(split.fit) == 8
    assert len(split.calibration) == 2
    assert split.fit["timestamp"].max() < split.calibration["timestamp"].min()


def test_chronological_split_rejects_unsorted_rows() -> None:
    frame = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                ["2026-01-01T01:00:00Z", "2026-01-01T00:00:00Z"]
            )
        }
    )
    with pytest.raises(ValueError, match="sorted chronologically"):
        chronological_split(frame, 0.8, minimum_fit_rows=1, minimum_calibration_rows=1)


def test_score_transform_preserves_configured_anchors() -> None:
    raw_scores = np.linspace(0.30, 0.70, 501)
    transform = calibrate_score_transform(raw_scores, calibration_config())
    normalized = transform.normalize(
        np.array([transform.median_raw_score, transform.threshold_raw_score])
    )
    assert normalized[0] == pytest.approx(10.0)
    assert normalized[1] == pytest.approx(50.0)
    assert np.all(np.diff(transform.normalize(raw_scores)) > 0)


def test_driver_groups_follow_feature_contract() -> None:
    columns = [
        "condition__vibration__value",
        "condition__vibration__mean_6h",
        "condition__vibration__delta_1h",
        "process__feed_rate__value",
    ]
    groups = driver_feature_groups(columns, ["__value", "__mean_6h"])
    assert groups == {
        "condition.vibration": [
            "condition__vibration__value",
            "condition__vibration__mean_6h",
        ],
        "process.feed_rate": ["process__feed_rate__value"],
    }


def test_numeric_matrix_rejects_non_finite_values() -> None:
    frame = pd.DataFrame({"a": [1.0, np.nan], "b": [2.0, 3.0]})
    with pytest.raises(ValueError, match="non-finite"):
        numeric_matrix(frame, ["a", "b"])


def test_driver_impact_shares_are_normalized_per_observation() -> None:
    impacts = np.array([[0.19, 0.12, 0.06, 0.04], [0.0, 0.0, 0.0, 0.0]])

    shares = normalize_driver_impacts(impacts)

    assert shares[0].sum() == pytest.approx(100.0)
    assert shares[0, 0] > shares[0, 1] > shares[0, 2] > shares[0, 3]
    assert shares[1].tolist() == [0.0, 0.0, 0.0, 0.0]
