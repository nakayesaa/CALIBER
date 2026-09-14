"""Reusable training, scoring, driver, and evaluation logic."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd
from scipy.special import expit
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import RobustScaler

from services.api.app.schemas.anomaly import (
    AnomalyModelConfig,
    ScoreCalibrationConfig,
)


@dataclass(frozen=True)
class TrainingSplit:
    fit: pd.DataFrame
    calibration: pd.DataFrame


@dataclass(frozen=True)
class LogisticScoreTransform:
    median_raw_score: float
    threshold_raw_score: float
    slope: float
    intercept: float
    median_normalized_score: float
    threshold_normalized_score: float
    exponent_clip: float

    def normalize(self, raw_scores: np.ndarray) -> np.ndarray:
        logits = np.clip(
            self.slope * raw_scores + self.intercept,
            -self.exponent_clip,
            self.exponent_clip,
        )
        return 100.0 * expit(logits)

    def as_dict(self) -> dict[str, float]:
        return {
            "median_raw_score": self.median_raw_score,
            "threshold_raw_score": self.threshold_raw_score,
            "slope": self.slope,
            "intercept": self.intercept,
            "median_normalized_score": self.median_normalized_score,
            "threshold_normalized_score": self.threshold_normalized_score,
            "exponent_clip": self.exponent_clip,
        }


@dataclass(frozen=True)
class DriverProfile:
    driver_name: str
    feature_columns: tuple[str, ...]
    score_transform: LogisticScoreTransform

    def as_dict(self) -> dict[str, Any]:
        return {
            "driver_name": self.driver_name,
            "feature_columns": list(self.feature_columns),
            "score_transform": self.score_transform.as_dict(),
        }


@dataclass(frozen=True)
class AnomalyModelBundle:
    model_id: str
    model_version: str
    feature_pipeline_id: str
    feature_columns: tuple[str, ...]
    scaler: RobustScaler
    estimator: IsolationForest
    score_transform: LogisticScoreTransform
    driver_profiles: tuple[DriverProfile, ...]
    trained_at: datetime


@dataclass(frozen=True)
class TrainingDiagnostics:
    fit_rows: int
    calibration_rows: int
    raw_fit_score_min: float
    raw_fit_score_max: float
    raw_calibration_score_min: float
    raw_calibration_score_max: float

    def as_dict(self) -> dict[str, int | float]:
        return {
            "fit_rows": self.fit_rows,
            "calibration_rows": self.calibration_rows,
            "raw_fit_score_min": self.raw_fit_score_min,
            "raw_fit_score_max": self.raw_fit_score_max,
            "raw_calibration_score_min": self.raw_calibration_score_min,
            "raw_calibration_score_max": self.raw_calibration_score_max,
        }


def chronological_split(
    training_rows: pd.DataFrame,
    fit_fraction: float,
    minimum_fit_rows: int,
    minimum_calibration_rows: int,
) -> TrainingSplit:
    if training_rows.empty:
        raise ValueError("Training rows cannot be empty")
    if not training_rows["timestamp"].is_monotonic_increasing:
        raise ValueError("Training rows must be sorted chronologically")
    split_at = int(np.floor(len(training_rows) * fit_fraction))
    fit = training_rows.iloc[:split_at].copy()
    calibration = training_rows.iloc[split_at:].copy()
    if len(fit) < minimum_fit_rows:
        raise ValueError(f"Fit partition has {len(fit)} rows, requires {minimum_fit_rows}")
    if len(calibration) < minimum_calibration_rows:
        raise ValueError(
            f"Calibration partition has {len(calibration)} rows, "
            f"requires {minimum_calibration_rows}"
        )
    if fit["timestamp"].max() >= calibration["timestamp"].min():
        raise ValueError("Fit and calibration partitions overlap")
    return TrainingSplit(fit=fit, calibration=calibration)


def validate_feature_contract(
    feature_table: pd.DataFrame,
    feature_manifest: dict[str, Any],
    config: AnomalyModelConfig,
) -> list[str]:
    if feature_manifest["pipeline_id"] != config.input_pipeline_id:
        raise ValueError("Model config and feature manifest pipeline IDs do not match")
    feature_columns = list(feature_manifest["model_feature_columns"])
    if len(feature_columns) != config.expected_feature_count:
        raise ValueError(
            f"Expected {config.expected_feature_count} features, found {len(feature_columns)}"
        )
    if len(feature_columns) != len(set(feature_columns)):
        raise ValueError("Model feature names must be unique")
    missing = set(feature_columns) - set(feature_table.columns)
    if missing:
        raise ValueError(f"Feature table is missing model columns: {sorted(missing)}")

    forbidden = {
        *feature_manifest["metadata_columns"],
        *feature_manifest["label_columns"],
        *feature_manifest["eligibility_columns"],
    }
    leaked = forbidden.intersection(feature_columns)
    if leaked:
        raise ValueError(f"Labels or metadata leaked into model features: {sorted(leaked)}")
    return feature_columns


def prepare_training_split(
    feature_table: pd.DataFrame,
    config: AnomalyModelConfig,
) -> TrainingSplit:
    required = {"timestamp", "model_training_eligible"}
    missing = required - set(feature_table.columns)
    if missing:
        raise ValueError(f"Feature table is missing training fields: {sorted(missing)}")
    training_rows = feature_table.loc[feature_table["model_training_eligible"]].copy()
    return chronological_split(
        training_rows,
        fit_fraction=config.split.fit_fraction,
        minimum_fit_rows=config.split.minimum_fit_rows,
        minimum_calibration_rows=config.split.minimum_calibration_rows,
    )


def fit_anomaly_model(
    split: TrainingSplit,
    feature_columns: list[str],
    config: AnomalyModelConfig,
    trained_at: datetime,
) -> tuple[AnomalyModelBundle, TrainingDiagnostics]:
    fit_matrix = numeric_matrix(split.fit, feature_columns)
    calibration_matrix = numeric_matrix(split.calibration, feature_columns)
    scaler = RobustScaler(
        with_centering=config.scaler.with_centering,
        with_scaling=config.scaler.with_scaling,
        quantile_range=config.scaler.quantile_range,
        unit_variance=config.scaler.unit_variance,
    )
    scaled_fit = scaler.fit_transform(fit_matrix)
    scaled_calibration = scaler.transform(calibration_matrix)
    estimator = IsolationForest(
        n_estimators=config.estimator.n_estimators,
        max_samples=config.estimator.max_samples,
        contamination="auto",
        max_features=config.estimator.max_features,
        bootstrap=config.estimator.bootstrap,
        n_jobs=config.estimator.n_jobs,
        random_state=config.random_seed,
    )
    estimator.fit(scaled_fit)
    raw_fit_scores = raw_anomaly_scores(estimator, scaled_fit)
    raw_calibration_scores = raw_anomaly_scores(estimator, scaled_calibration)
    score_transform = calibrate_score_transform(
        raw_calibration_scores,
        config.calibration,
    )
    driver_profiles = build_driver_profiles(
        scaled_calibration,
        feature_columns,
        config,
    )
    bundle = AnomalyModelBundle(
        model_id=config.model_id,
        model_version=config.model_version,
        feature_pipeline_id=config.input_pipeline_id,
        feature_columns=tuple(feature_columns),
        scaler=scaler,
        estimator=estimator,
        score_transform=score_transform,
        driver_profiles=tuple(driver_profiles),
        trained_at=trained_at,
    )
    diagnostics = TrainingDiagnostics(
        fit_rows=len(split.fit),
        calibration_rows=len(split.calibration),
        raw_fit_score_min=float(raw_fit_scores.min()),
        raw_fit_score_max=float(raw_fit_scores.max()),
        raw_calibration_score_min=float(raw_calibration_scores.min()),
        raw_calibration_score_max=float(raw_calibration_scores.max()),
    )
    return bundle, diagnostics


def numeric_matrix(frame: pd.DataFrame, feature_columns: list[str]) -> np.ndarray:
    matrix = frame[feature_columns].to_numpy(dtype=float)
    if matrix.ndim != 2 or matrix.shape[1] != len(feature_columns):
        raise ValueError("Feature matrix shape does not match the feature contract")
    if not np.isfinite(matrix).all():
        raise ValueError("Feature matrix contains missing or non-finite values")
    return matrix


def raw_anomaly_scores(
    estimator: IsolationForest,
    scaled_matrix: np.ndarray,
) -> np.ndarray:
    return -estimator.score_samples(scaled_matrix)


def calibrate_score_transform(
    raw_calibration_scores: np.ndarray,
    config: ScoreCalibrationConfig,
) -> LogisticScoreTransform:
    scores = np.asarray(raw_calibration_scores, dtype=float)
    if scores.ndim != 1 or not len(scores):
        raise ValueError("Calibration scores must be a non-empty one-dimensional array")
    if not np.isfinite(scores).all():
        raise ValueError("Calibration scores must be finite")
    median = float(np.median(scores))
    threshold = float(np.quantile(scores, config.anomaly_quantile))
    if threshold <= median:
        raise ValueError("Calibration threshold must exceed the median score")
    median_logit = logit_percent(config.median_normalized_score)
    threshold_logit = logit_percent(config.threshold_normalized_score)
    slope = (threshold_logit - median_logit) / (threshold - median)
    intercept = threshold_logit - slope * threshold
    return LogisticScoreTransform(
        median_raw_score=median,
        threshold_raw_score=threshold,
        slope=slope,
        intercept=intercept,
        median_normalized_score=config.median_normalized_score,
        threshold_normalized_score=config.threshold_normalized_score,
        exponent_clip=config.exponent_clip,
    )


def logit_percent(value: float) -> float:
    proportion = value / 100.0
    if not 0 < proportion < 1:
        raise ValueError("Normalized score anchors must be between zero and one hundred")
    return float(np.log(proportion / (1.0 - proportion)))


def build_driver_profiles(
    scaled_calibration: np.ndarray,
    feature_columns: list[str],
    config: AnomalyModelConfig,
) -> list[DriverProfile]:
    groups = driver_feature_groups(feature_columns, config.drivers.included_feature_suffixes)
    profiles: list[DriverProfile] = []
    calibration_config = config.calibration.model_copy(
        update={"anomaly_quantile": 0.95}
    )
    column_positions = {name: index for index, name in enumerate(feature_columns)}
    for driver_name, columns in groups.items():
        positions = [column_positions[column] for column in columns]
        magnitude = np.max(np.abs(scaled_calibration[:, positions]), axis=1)
        transform = calibrate_score_transform(magnitude, calibration_config)
        profiles.append(
            DriverProfile(
                driver_name=driver_name,
                feature_columns=tuple(columns),
                score_transform=transform,
            )
        )
    return profiles


def driver_feature_groups(
    feature_columns: list[str],
    included_suffixes: list[str],
) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {}
    for column in feature_columns:
        parts = column.split("__")
        if len(parts) != 3:
            raise ValueError(f"Feature name does not follow the expected contract: {column}")
        if not any(column.endswith(suffix) for suffix in included_suffixes):
            continue
        driver_name = f"{parts[0]}.{parts[1]}"
        groups.setdefault(driver_name, []).append(column)
    if not groups:
        raise ValueError("Driver configuration selected no model features")
    return groups


def score_feature_table(
    feature_table: pd.DataFrame,
    bundle: AnomalyModelBundle,
    maximum_drivers: int,
) -> pd.DataFrame:
    required = {
        "feature_complete",
        "model_scoring_eligible",
        *bundle.feature_columns,
    }
    missing = required - set(feature_table.columns)
    if missing:
        raise ValueError(f"Scoring input is missing columns: {sorted(missing)}")

    output = pd.DataFrame(index=feature_table.index)
    output["score_status"] = np.where(
        ~feature_table["feature_complete"],
        "WARMUP",
        np.where(feature_table["model_scoring_eligible"], "SCORED", "EXCLUDED_MODE"),
    )
    output["raw_anomaly_score"] = np.nan
    output["anomaly_score"] = np.nan
    output["anomaly_threshold"] = bundle.score_transform.threshold_normalized_score
    output["is_anomaly"] = False
    for rank in range(1, maximum_drivers + 1):
        output[f"top_driver_{rank}"] = ""
        output[f"top_driver_{rank}_score"] = np.nan
    contribution_columns = counterfactual_column_names(bundle, "condition.")
    for column in contribution_columns:
        output[column] = np.nan

    eligible = feature_table["model_scoring_eligible"].astype(bool)
    matrix = numeric_matrix(feature_table.loc[eligible], list(bundle.feature_columns))
    scaled = bundle.scaler.transform(matrix)
    raw_scores = raw_anomaly_scores(bundle.estimator, scaled)
    normalized = bundle.score_transform.normalize(raw_scores)
    output.loc[eligible, "raw_anomaly_score"] = raw_scores
    output.loc[eligible, "anomaly_score"] = normalized
    output.loc[eligible, "is_anomaly"] = (
        raw_scores >= bundle.score_transform.threshold_raw_score
    )
    contributions = counterfactual_driver_contributions(
        scaled,
        bundle,
        driver_prefix="condition.",
        full_raw_scores=raw_scores,
    )
    for column, values in contributions.items():
        output.loc[eligible, column] = values
    driver_ranking = rank_drivers(scaled, bundle, maximum_drivers)
    for column in driver_ranking:
        output.loc[eligible, column] = driver_ranking[column].to_numpy()
    return output


def counterfactual_column_names(
    bundle: AnomalyModelBundle,
    driver_prefix: str,
) -> list[str]:
    names = [
        profile.driver_name
        for profile in bundle.driver_profiles
        if profile.driver_name.startswith(driver_prefix)
    ]
    return [
        column
        for name in names
        for column in (
            f"model_impact__{name.replace('.', '__')}",
            f"contribution_pct__{name.replace('.', '__')}",
        )
    ]


def counterfactual_driver_contributions(
    scaled_matrix: np.ndarray,
    bundle: AnomalyModelBundle,
    driver_prefix: str,
    full_raw_scores: np.ndarray | None = None,
) -> dict[str, np.ndarray]:
    """Estimate driver impact by restoring one feature group to baseline.

    Zero is the fitted RobustScaler center, so each counterfactual replaces a
    signal's model inputs with its healthy calibration median. The result is a
    local model explanation, not a claim of physical causality.
    """

    full_scores = (
        raw_anomaly_scores(bundle.estimator, scaled_matrix)
        if full_raw_scores is None
        else np.asarray(full_raw_scores, dtype=float)
    )
    if full_scores.shape != (len(scaled_matrix),):
        raise ValueError("Full raw scores do not match the scoring matrix")
    positions = {name: index for index, name in enumerate(bundle.feature_columns)}
    selected_profiles = [
        profile
        for profile in bundle.driver_profiles
        if profile.driver_name.startswith(driver_prefix)
    ]
    if not selected_profiles:
        raise ValueError(f"No model drivers match prefix: {driver_prefix}")

    impacts: list[np.ndarray] = []
    for profile in selected_profiles:
        domain, signal = profile.driver_name.split(".", maxsplit=1)
        feature_prefix = f"{domain}__{signal}__"
        group_positions = [
            position
            for name, position in positions.items()
            if name.startswith(feature_prefix)
        ]
        if not group_positions:
            raise ValueError(f"No model features found for {profile.driver_name}")
        counterfactual = scaled_matrix.copy()
        counterfactual[:, group_positions] = 0.0
        without_driver = raw_anomaly_scores(bundle.estimator, counterfactual)
        impacts.append(np.maximum(full_scores - without_driver, 0.0))

    impact_matrix = np.column_stack(impacts)
    shares = normalize_driver_impacts(impact_matrix)
    result: dict[str, np.ndarray] = {}
    for index, profile in enumerate(selected_profiles):
        suffix = profile.driver_name.replace(".", "__")
        result[f"model_impact__{suffix}"] = impact_matrix[:, index]
        result[f"contribution_pct__{suffix}"] = shares[:, index]
    return result


def normalize_driver_impacts(impacts: np.ndarray) -> np.ndarray:
    values = np.asarray(impacts, dtype=float)
    if values.ndim != 2 or values.shape[1] == 0:
        raise ValueError("Driver impacts must be a non-empty two-dimensional matrix")
    if not np.isfinite(values).all() or (values < 0).any():
        raise ValueError("Driver impacts must be finite and non-negative")
    totals = values.sum(axis=1, keepdims=True)
    return np.divide(
        values * 100.0,
        totals,
        out=np.zeros_like(values),
        where=totals > np.finfo(float).eps,
    )


def rank_drivers(
    scaled_matrix: np.ndarray,
    bundle: AnomalyModelBundle,
    maximum_drivers: int,
) -> pd.DataFrame:
    positions = {name: index for index, name in enumerate(bundle.feature_columns)}
    names: list[str] = []
    scores: list[np.ndarray] = []
    for profile in bundle.driver_profiles:
        selected = [positions[column] for column in profile.feature_columns]
        magnitude = np.max(np.abs(scaled_matrix[:, selected]), axis=1)
        names.append(profile.driver_name)
        scores.append(profile.score_transform.normalize(magnitude))
    score_matrix = np.column_stack(scores)
    order = np.argsort(-score_matrix, axis=1, kind="stable")
    result: dict[str, Any] = {}
    limit = min(maximum_drivers, len(names))
    name_array = np.asarray(names, dtype=object)
    for rank in range(limit):
        indices = order[:, rank]
        result[f"top_driver_{rank + 1}"] = name_array[indices]
        result[f"top_driver_{rank + 1}_score"] = score_matrix[
            np.arange(len(score_matrix)), indices
        ]
    return pd.DataFrame(result)


def evaluate_scored_timeline(
    scored_timeline: pd.DataFrame,
    config: AnomalyModelConfig,
) -> dict[str, Any]:
    scored = scored_timeline.loc[scored_timeline["score_status"] == "SCORED"].copy()
    if scored.empty:
        raise ValueError("Evaluation requires at least one scored row")
    phase_metrics: dict[str, dict[str, int | float]] = {}
    for phase, group in scored.groupby("scenario_phase", sort=False):
        phase_metrics[str(phase)] = summarize_scores(group)

    degradation = scored.loc[
        scored["scenario_phase"].isin(config.evaluation.degradation_phases)
        & scored["is_anomaly"]
    ]
    trip_rows = scored_timeline.loc[
        scored_timeline["scenario_phase"] == config.evaluation.trip_phase
    ]
    first_warning = degradation["timestamp"].min() if not degradation.empty else None
    trip_time = trip_rows["timestamp"].min() if not trip_rows.empty else None
    lead_time_hours: float | None = None
    if first_warning is not None and trip_time is not None:
        lead_time_hours = float(
            (pd.Timestamp(trip_time) - pd.Timestamp(first_warning)) / pd.Timedelta(hours=1)
        )

    normal = scored.loc[scored["scenario_phase"].isin(config.evaluation.normal_phases)]
    recovery = scored.loc[
        scored["scenario_phase"].isin(config.evaluation.recovery_phases)
    ]
    return {
        "model_id": config.model_id,
        "scored_rows": len(scored),
        "first_degradation_anomaly_at": timestamp_or_none(first_warning),
        "trip_at": timestamp_or_none(trip_time),
        "warning_lead_time_hours": lead_time_hours,
        "normal_false_positive_rate": anomaly_rate(normal),
        "recovery_anomaly_rate": anomaly_rate(recovery),
        "phase_metrics": phase_metrics,
    }


def summarize_scores(frame: pd.DataFrame) -> dict[str, int | float]:
    scores = frame["anomaly_score"].astype(float)
    return {
        "scored_rows": len(frame),
        "anomaly_count": int(frame["is_anomaly"].sum()),
        "anomaly_rate": anomaly_rate(frame),
        "mean_score": float(scores.mean()),
        "median_score": float(scores.median()),
        "p95_score": float(scores.quantile(0.95)),
        "maximum_score": float(scores.max()),
    }


def anomaly_rate(frame: pd.DataFrame) -> float:
    if frame.empty:
        return 0.0
    return float(frame["is_anomaly"].mean())


def timestamp_or_none(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    return pd.Timestamp(value).isoformat()
