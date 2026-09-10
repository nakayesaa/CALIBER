"""Vectorized feature engineering for hourly equipment signals."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from services.api.app.schemas.features import (
    ConcernDirection,
    FeatureCatalogEntry,
    FeaturePipelineConfig,
    FeatureRole,
)


ELIGIBILITY_COLUMNS = [
    "feature_complete",
    "model_training_eligible",
    "model_scoring_eligible",
]


@dataclass(frozen=True)
class FeatureBuildResult:
    feature_table: pd.DataFrame
    catalog: list[FeatureCatalogEntry]
    model_feature_columns: list[str]
    explanation_feature_columns: list[str]
    lookback_hours: int


def validate_hourly_input(
    frame: pd.DataFrame,
    config: FeaturePipelineConfig,
    expected_rows: int,
) -> pd.DataFrame:
    required = {
        *config.output.metadata_columns,
        *config.output.label_columns,
        *(signal.source_column for signal in config.condition_signals.values()),
        *(signal.source_column for signal in config.process_signals.values()),
    }
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Feature input is missing columns: {sorted(missing)}")
    if len(frame) != expected_rows:
        raise ValueError(f"Feature input has {len(frame)} rows, expected {expected_rows}")

    validated = frame.copy()
    validated["timestamp"] = pd.to_datetime(validated["timestamp"], errors="raise")
    if validated["timestamp"].dt.tz is None:
        raise ValueError("Feature input timestamps must include a timezone")
    if not validated["timestamp"].is_monotonic_increasing:
        raise ValueError("Feature input timestamps must be ordered")
    if validated["timestamp"].duplicated().any():
        raise ValueError("Feature input timestamps must be unique")

    expected_delta = pd.Timedelta(config.expected_frequency)
    deltas = validated["timestamp"].diff().dropna()
    if not (deltas == expected_delta).all():
        raise ValueError("Feature input must have a continuous hourly cadence")
    scenario_ids = set(validated["scenario_id"].dropna().astype(str))
    if scenario_ids != {config.input_scenario_id}:
        raise ValueError(f"Unexpected scenario IDs: {sorted(scenario_ids)}")

    numeric_columns = [
        *(signal.source_column for signal in config.condition_signals.values()),
        *(signal.source_column for signal in config.process_signals.values()),
    ]
    validated[numeric_columns] = validated[numeric_columns].apply(
        pd.to_numeric, errors="raise"
    )
    if not np.isfinite(validated[numeric_columns].to_numpy(dtype=float)).all():
        raise ValueError("Feature input signal values must be finite")
    validated["training_eligible"] = parse_boolean(validated["training_eligible"])
    validated["event_marker"] = validated["event_marker"].fillna("").astype(str)
    return validated


def parse_boolean(series: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(series):
        return series.astype(bool)
    normalized = series.astype(str).str.strip().str.lower()
    allowed = {"true", "false", "1", "0"}
    unexpected = set(normalized) - allowed
    if unexpected:
        raise ValueError(f"Invalid boolean values: {sorted(unexpected)}")
    return normalized.isin({"true", "1"})


def build_features(
    frame: pd.DataFrame,
    config: FeaturePipelineConfig,
) -> FeatureBuildResult:
    feature_values: dict[str, pd.Series] = {}
    catalog: list[FeatureCatalogEntry] = []
    model_columns: list[str] = []
    explanation_columns: list[str] = []
    alarm_ratios: list[pd.Series] = []

    for signal_name, signal in config.condition_signals.items():
        values = frame[signal.source_column].astype(float)
        prefix = f"condition__{signal_name}"
        if signal.include_raw:
            add_feature(
                feature_values,
                catalog,
                model_columns,
                name=f"{prefix}__value",
                values=values,
                role=FeatureRole.MODEL_INPUT,
                group="CONDITION",
                source_column=signal.source_column,
                transformation="IDENTITY",
                unit=signal.unit,
                description=f"Current {signal_name.replace('_', ' ')} value.",
            )
        for period in signal.delta_periods:
            add_feature(
                feature_values,
                catalog,
                model_columns,
                name=f"{prefix}__delta_{period}h",
                values=values.diff(period),
                role=FeatureRole.MODEL_INPUT,
                group="CONDITION_CHANGE",
                source_column=signal.source_column,
                transformation="PAST_DIFFERENCE",
                window_hours=period,
                unit=signal.unit,
                description=f"Change from {period} hour earlier.",
            )
        for window in signal.rolling_windows:
            rolling = values.rolling(window=window, min_periods=window)
            add_feature(
                feature_values,
                catalog,
                model_columns,
                name=f"{prefix}__mean_{window}h",
                values=rolling.mean(),
                role=FeatureRole.MODEL_INPUT,
                group="CONDITION_ROLLING",
                source_column=signal.source_column,
                transformation="TRAILING_MEAN",
                window_hours=window,
                unit=signal.unit,
                description=f"Trailing {window} hour mean including the current hour.",
            )
            add_feature(
                feature_values,
                catalog,
                model_columns,
                name=f"{prefix}__std_{window}h",
                values=rolling.std(ddof=0),
                role=FeatureRole.MODEL_INPUT,
                group="CONDITION_ROLLING",
                source_column=signal.source_column,
                transformation="TRAILING_STANDARD_DEVIATION",
                window_hours=window,
                unit=signal.unit,
                description=f"Trailing {window} hour variability including the current hour.",
            )
        for period in signal.trend_periods:
            add_feature(
                feature_values,
                catalog,
                model_columns,
                name=f"{prefix}__trend_{period}h",
                values=(values - values.shift(period)) / period,
                role=FeatureRole.MODEL_INPUT,
                group="CONDITION_TREND",
                source_column=signal.source_column,
                transformation="PAST_SLOPE",
                window_hours=period,
                unit=f"{signal.unit}/h",
                description=f"Average hourly change across the past {period} hours.",
            )

        alarm_ratio = threshold_ratio(
            values,
            signal.alarm_limit,
            signal.direction_of_concern,
        )
        alarm_ratios.append(alarm_ratio)
        add_feature(
            feature_values,
            catalog,
            explanation_columns,
            name=f"{prefix}__alarm_ratio",
            values=alarm_ratio,
            role=FeatureRole.EXPLANATION_ONLY,
            group="THRESHOLD_CONTEXT",
            source_column=signal.source_column,
            transformation="DIRECTIONAL_ALARM_RATIO",
            unit="ratio",
            description="Directional ratio where one means the alarm limit is reached.",
        )

    for signal_name, signal in config.process_signals.items():
        values = frame[signal.source_column].astype(float)
        prefix = f"process__{signal_name}"
        if signal.include_raw:
            add_feature(
                feature_values,
                catalog,
                model_columns,
                name=f"{prefix}__value",
                values=values,
                role=FeatureRole.MODEL_INPUT,
                group="PROCESS_CONTEXT",
                source_column=signal.source_column,
                transformation="IDENTITY",
                unit=signal.unit,
                description=f"Current {signal_name.replace('_', ' ')} value.",
            )
        for period in signal.delta_periods:
            add_feature(
                feature_values,
                catalog,
                model_columns,
                name=f"{prefix}__delta_{period}h",
                values=values.diff(period),
                role=FeatureRole.MODEL_INPUT,
                group="PROCESS_CHANGE",
                source_column=signal.source_column,
                transformation="PAST_DIFFERENCE",
                window_hours=period,
                unit=signal.unit,
                description=f"Change from {period} hour earlier.",
            )
        for window in signal.rolling_windows:
            add_feature(
                feature_values,
                catalog,
                model_columns,
                name=f"{prefix}__mean_{window}h",
                values=values.rolling(window=window, min_periods=window).mean(),
                role=FeatureRole.MODEL_INPUT,
                group="PROCESS_ROLLING",
                source_column=signal.source_column,
                transformation="TRAILING_MEAN",
                window_hours=window,
                unit=signal.unit,
                description=f"Trailing {window} hour process mean.",
            )

    alarm_frame = pd.concat(alarm_ratios, axis=1)
    add_feature(
        feature_values,
        catalog,
        explanation_columns,
        name="explanation__alarm_breadth",
        values=(alarm_frame >= 1.0).sum(axis=1).astype(float),
        role=FeatureRole.EXPLANATION_ONLY,
        group="MULTIVARIATE_CONTEXT",
        source_column="configured_condition_signals",
        transformation="ALARM_LIMIT_COUNT",
        unit="count",
        description="Number of condition signals currently beyond their alarm limit.",
    )
    add_feature(
        feature_values,
        catalog,
        explanation_columns,
        name="explanation__mean_alarm_ratio",
        values=alarm_frame.mean(axis=1),
        role=FeatureRole.EXPLANATION_ONLY,
        group="MULTIVARIATE_CONTEXT",
        source_column="configured_condition_signals",
        transformation="MEAN_DIRECTIONAL_ALARM_RATIO",
        unit="ratio",
        description="Mean directional alarm ratio across all condition signals.",
    )

    engineered = pd.DataFrame(feature_values, index=frame.index)
    model_values = engineered[model_columns].to_numpy(dtype=float)
    feature_complete = pd.Series(np.isfinite(model_values).all(axis=1), index=frame.index)
    training_mode = frame["operating_mode"].isin(
        config.eligibility.training_operating_modes
    )
    scoring_mode = frame["operating_mode"].isin(
        config.eligibility.scoring_operating_modes
    )
    required_status = frame["run_status"].eq(config.eligibility.required_run_status)
    source_eligible = (
        frame["training_eligible"]
        if config.eligibility.training_requires_source_eligibility
        else pd.Series(True, index=frame.index)
    )
    below_alarm = (
        (alarm_frame < 1.0).all(axis=1)
        if config.eligibility.training_requires_below_alarm
        else pd.Series(True, index=frame.index)
    )
    eligibility = pd.DataFrame(
        {
            "feature_complete": feature_complete,
            "model_training_eligible": feature_complete
            & source_eligible
            & training_mode
            & required_status
            & below_alarm,
            "model_scoring_eligible": feature_complete
            & scoring_mode
            & required_status,
        },
        index=frame.index,
    )
    base_columns = config.output.metadata_columns + config.output.label_columns
    output = pd.concat([frame[base_columns], eligibility, engineered], axis=1)
    lookback = max(
        [
            period
            for signal in config.condition_signals.values()
            for period in [
                *signal.delta_periods,
                *signal.rolling_windows,
                *signal.trend_periods,
            ]
        ]
        + [
            period
            for signal in config.process_signals.values()
            for period in [*signal.delta_periods, *signal.rolling_windows]
        ]
    )
    return FeatureBuildResult(
        feature_table=output,
        catalog=catalog,
        model_feature_columns=model_columns,
        explanation_feature_columns=explanation_columns,
        lookback_hours=lookback,
    )


def threshold_ratio(
    values: pd.Series,
    alarm_limit: float,
    direction: ConcernDirection,
) -> pd.Series:
    if direction == ConcernDirection.HIGH:
        return values / alarm_limit
    if (values <= 0).any():
        raise ValueError("Low-concern threshold ratios require positive signal values")
    return alarm_limit / values


def add_feature(
    values_by_name: dict[str, pd.Series],
    catalog: list[FeatureCatalogEntry],
    ordered_columns: list[str],
    *,
    name: str,
    values: pd.Series,
    role: FeatureRole,
    group: str,
    source_column: str,
    transformation: str,
    unit: str,
    description: str,
    window_hours: int | None = None,
) -> None:
    if name in values_by_name:
        raise ValueError(f"Duplicate feature name: {name}")
    values_by_name[name] = values
    ordered_columns.append(name)
    catalog.append(
        FeatureCatalogEntry(
            feature_name=name,
            feature_role=role,
            feature_group=group,
            source_column=source_column,
            transformation=transformation,
            window_hours=window_hours,
            unit=unit,
            description=description,
        )
    )
