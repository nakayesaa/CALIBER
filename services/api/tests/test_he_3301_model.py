"""Time-blocked HE training must not leak healthy holdout into calibration."""

import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import joblib
import numpy as np
import pandas as pd
import pytest
import yaml

from scripts import train_he_3301_anomaly as trainer
from scripts.train_he_3301_anomaly import (
    blocked_healthy_split,
    evaluate,
    healthy_split,
    validate_scoring_order,
)
from scripts.train_ko_3201_anomaly import publish_bundle
from services.api.app.schemas.anomaly import AnomalyModelConfig
from services.api.app.services.analytics.anomaly_model import (
    TrainingSplit,
    fit_anomaly_model,
    numeric_matrix,
    score_feature_table,
)


def test_healthy_blocks_have_full_lookback_gaps():
    frame = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01", periods=1400, freq="h", tz="Asia/Jakarta"),
            "model_training_eligible": True,
        }
    )
    split, holdout = healthy_split(frame, pd.Timestamp("2026-02-26", tz="Asia/Jakarta"))
    assert len(split.fit) >= 720
    assert len(split.calibration) >= 168
    assert len(holdout) >= 168
    assert split.calibration.timestamp.min() - split.fit.timestamp.max() > pd.Timedelta(hours=24)
    assert holdout.timestamp.min() - split.calibration.timestamp.max() > pd.Timedelta(hours=24)
    assert holdout.timestamp.max() < pd.Timestamp("2026-02-26", tz="Asia/Jakarta")


def test_retrospective_blocks_are_disjoint_and_have_no_shared_lookback():
    frame = pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=1680, freq="h", tz="Asia/Jakarta"),
        "model_training_eligible": True,
    })
    split, holdout = blocked_healthy_split(frame, pd.Timestamp("2026-02-26", tz="Asia/Jakarta"))
    partitions = [split.fit, split.calibration, holdout]
    assert [len(part) for part in partitions] == [768, 180, 180]
    for index, part in enumerate(partitions):
        assert part.timestamp.is_monotonic_increasing
        for other in partitions[index + 1:]:
            assert set(part.index).isdisjoint(other.index)
            # A full 24-hour gap prevents rolling inputs crossing partition boundaries.
            distances = abs(part.timestamp.dt.as_unit("ns").astype("int64").to_numpy()[:, None] - other.timestamp.dt.as_unit("ns").astype("int64").to_numpy())
            assert distances.min() > pd.Timedelta(hours=24).value
    changed = frame.copy()
    changed.loc[changed.timestamp.ge(pd.Timestamp("2026-02-26", tz="Asia/Jakarta")), "model_training_eligible"] = False
    other_split, other_holdout = blocked_healthy_split(changed, pd.Timestamp("2026-02-26", tz="Asia/Jakarta"))
    assert list(split.fit.index) == list(other_split.fit.index)
    assert list(holdout.index) == list(other_holdout.index)


def test_small_or_unsorted_training_fails():
    frame = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01", periods=600, freq="h", tz="Asia/Jakarta"),
            "model_training_eligible": True,
        }
    )
    with pytest.raises(ValueError, match="Fit partition"):
        healthy_split(frame, pd.Timestamp("2026-02-26", tz="Asia/Jakarta"))
    with pytest.raises(ValueError, match="chronological"):
        healthy_split(frame.iloc[::-1], pd.Timestamp("2026-02-26", tz="Asia/Jakarta"))


def test_model_contract_rejects_reordered_features():
    with pytest.raises(ValueError, match="order"):
        validate_scoring_order(["a", "b"], ["b", "a"])
    validate_scoring_order(["a", "b"], ["a", "b"])


def test_duplicate_timestamps_are_rejected():
    frame = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01", periods=1400, freq="h", tz="Asia/Jakarta"),
            "model_training_eligible": True,
        }
    )
    frame.loc[1, "timestamp"] = frame.loc[0, "timestamp"]
    with pytest.raises(ValueError, match="unique"):
        healthy_split(frame, pd.Timestamp("2026-02-26", tz="Asia/Jakarta"))


def test_reload_preserves_scores_and_all_four_contribution_groups(tmp_path):
    payload = yaml.safe_load(
        (Path(__file__).parents[3] / "data/catalog/he_3301_anomaly_model.yaml").read_text()
    )
    payload.pop("validation")
    payload.pop("feature_projection", None)
    payload["expected_feature_count"] = 12
    payload["estimator"].update(n_estimators=50, n_jobs=1, max_samples=200)
    config = AnomalyModelConfig.model_validate(payload)
    columns = [
        f"condition__{signal}__{suffix}"
        for signal in ["tube_dp", "heat_duty", "cold_outlet_temp", "heavy_ends"]
        for suffix in ["value", "mean_6h", "mean_24h"]
    ]
    frame = pd.DataFrame(np.random.default_rng(3301).normal(size=(300, 12)), columns=columns)
    frame["feature_complete"] = True
    frame["model_scoring_eligible"] = True
    bundle, _ = fit_anomaly_model(
        TrainingSplit(frame.iloc[:200], frame.iloc[200:]),
        columns,
        config,
        datetime.now(ZoneInfo("Asia/Jakarta")),
    )
    _, difference = publish_bundle(
        tmp_path / "model.joblib", bundle, numeric_matrix(frame, columns)
    )
    expected = score_feature_table(frame, bundle, 4)
    actual = score_feature_table(frame, joblib.load(tmp_path / "model.joblib"), 4)
    assert difference == 0
    np.testing.assert_allclose(expected.anomaly_score, actual.anomaly_score)
    shares = [name for name in actual if name.startswith("contribution_pct__")]
    assert len(shares) == 4
    sums = actual[shares].sum(axis=1)
    assert ((np.isclose(sums, 100)) | (sums == 0)).all()


def test_evaluation_rejects_false_positive_holdout():
    frame = pd.DataFrame(
        {"timestamp": pd.date_range("2026-02-20", periods=2400, freq="h", tz="Asia/Jakarta")}
    )
    scores = pd.DataFrame(
        {"score_status": "SCORED", "anomaly_score": 80.0, "anomaly_threshold": 50.0},
        index=frame.index,
    )
    scores.loc[frame.timestamp.ge(pd.Timestamp("2026-05-22T22:00:00+07:00")), "anomaly_score"] = (
        10.0
    )
    validation = {
        "healthy_end_exclusive": "2026-02-26T00:00:00+07:00",
        "isolation_at": "2026-05-21T09:00:00+07:00",
        "recovery_start": "2026-05-22T22:00:00+07:00",
        "sustained_hours": 6,
        "maximum_healthy_exceedance": 0.05,
    }
    report = evaluate(frame, scores, frame.iloc[:100], validation)
    assert report["status"] == "FAIL"
    assert report["checks"]["healthy_holdout_exceedance"] is False


def test_rejected_candidate_preserves_existing_model_and_scores(tmp_path, monkeypatch):
    artifacts = tmp_path / "models"
    scores = tmp_path / "scores"
    artifacts.mkdir()
    scores.mkdir()
    (artifacts / "model.joblib").write_bytes(b"existing-approved-model")
    (scores / "hourly_anomaly_scores.csv").write_text("existing-approved-scores")
    frame = pd.DataFrame({"model_scoring_eligible": [True]})
    config = SimpleNamespace(model_id="he-test", drivers=SimpleNamespace(maximum_drivers=4))
    split = TrainingSplit(frame, frame)
    monkeypatch.setattr(
        trainer,
        "prepare_inputs",
        lambda *_: (config, {}, frame, ["x"], split, frame, {"feature_table_sha256": "test-hash"}),
    )
    monkeypatch.setattr(
        trainer, "fit_anomaly_model", lambda *_: (SimpleNamespace(feature_columns=("x",)), None)
    )
    monkeypatch.setattr(trainer, "score_feature_table", lambda *_: frame)
    monkeypatch.setattr(
        trainer,
        "evaluate",
        lambda *_: {"status": "FAIL", "checks": {"healthy_holdout_exceedance": False}},
    )
    with pytest.raises(ValueError, match="promotion rejected"):
        trainer.train(tmp_path, tmp_path, artifacts, scores)
    assert (artifacts / "model.joblib").read_bytes() == b"existing-approved-model"
    assert (scores / "hourly_anomaly_scores.csv").read_text() == "existing-approved-scores"
    report = json.loads((artifacts / "rejection_report.json").read_text())
    assert report["status"] == "FAIL"
    assert report["feature_table_sha256"] == "test-hash"
