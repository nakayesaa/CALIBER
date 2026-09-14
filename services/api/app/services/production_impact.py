"""Explainable production-impact calculation for equipment events."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml
from pydantic import BaseModel, ConfigDict, Field

from services.api.app.schemas.alerts import AlertEvent
from services.api.app.schemas.api import ProductionBaseline, ProductionImpact


class ProductionImpactPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    policy_id: str
    pre_trip_load_window_hours: int = Field(gt=0)
    plant_rate_tolerance_tph: float = Field(gt=0)
    minimum_comparable_samples: int = Field(gt=0)
    high_confidence_samples: int = Field(gt=0)
    source_reference: str


def load_production_impact_policy(path: Path) -> ProductionImpactPolicy:
    with path.open(encoding="utf-8") as stream:
        return ProductionImpactPolicy.model_validate(yaml.safe_load(stream))


def calculate_production_impact(
    scenario: pd.DataFrame,
    decisions: pd.DataFrame,
    alert: AlertEvent,
    policy: ProductionImpactPolicy,
) -> ProductionImpact | None:
    """Estimate event shortfall from a contextual, pre-event healthy baseline."""
    timeline = scenario.copy()
    timeline["timestamp"] = pd.to_datetime(timeline["timestamp"], errors="raise")
    decision_frame = decisions[["timestamp", "decision_state"]].copy()
    decision_frame["timestamp"] = pd.to_datetime(
        decision_frame["timestamp"], errors="raise"
    )
    timeline = timeline.merge(decision_frame, on="timestamp", validate="one_to_one")

    outage = _event_outage(timeline, pd.Timestamp(alert.opened_at))
    if outage.empty:
        return None

    outage_start = outage.iloc[0]["timestamp"]
    interval_hours = _sampling_interval_hours(timeline["timestamp"])
    window_end = outage.iloc[-1]["timestamp"] + pd.Timedelta(hours=interval_hours)
    load_window_start = outage_start - pd.Timedelta(
        hours=policy.pre_trip_load_window_hours
    )
    pre_trip = timeline.loc[
        timeline["timestamp"].between(load_window_start, outage_start, inclusive="left")
        & timeline["run_status"].eq("ON")
        & timeline["operating_mode"].eq("RUNNING_STEADY")
    ]
    if pre_trip.empty:
        return None
    representative_load = float(pre_trip["plant_rate_tph"].median())

    healthy = timeline.loc[
        timeline["timestamp"].lt(pd.Timestamp(alert.first_signal_at))
        & timeline["run_status"].eq("ON")
        & timeline["operating_mode"].eq("RUNNING_STEADY")
        & timeline["decision_state"].eq("NORMAL")
        & timeline["event_marker"].isna()
    ]
    comparable = healthy.loc[
        healthy["plant_rate_tph"].between(
            representative_load - policy.plant_rate_tolerance_tph,
            representative_load + policy.plant_rate_tolerance_tph,
        )
    ]
    if len(comparable) < policy.minimum_comparable_samples:
        comparable = healthy
    if comparable.empty:
        return None

    expected_feed = float(comparable["feed_rate_tph"].median())
    offline_hours = len(outage) * interval_hours
    actual_feed = float(outage["feed_rate_tph"].sum() * interval_hours)
    expected_feed_total = expected_feed * offline_hours
    sample_count = len(comparable)
    confidence = (
        "HIGH"
        if sample_count >= policy.high_confidence_samples
        else "MEDIUM"
        if sample_count >= policy.minimum_comparable_samples
        else "LOW"
    )
    baseline = ProductionBaseline(
        method="CONTEXTUAL_HEALTHY_MEDIAN",
        expected_feed_tph=expected_feed,
        representative_plant_rate_tph=representative_load,
        plant_rate_tolerance_tph=policy.plant_rate_tolerance_tph,
        healthy_sample_count=sample_count,
        reference_start=comparable["timestamp"].min().to_pydatetime(),
        reference_end=comparable["timestamp"].max().to_pydatetime(),
        confidence=confidence,
        source_reference=policy.source_reference,
    )
    return ProductionImpact(
        metric="PRODUCTION_SHORTFALL",
        provenance="CALCULATED",
        window_start=outage_start.to_pydatetime(),
        window_end=window_end.to_pydatetime(),
        offline_hours=offline_hours,
        actual_feed_tonnes=actual_feed,
        expected_feed_tonnes=expected_feed_total,
        estimated_shortfall_tonnes=max(expected_feed_total - actual_feed, 0.0),
        baseline=baseline,
    )


def _event_outage(timeline: pd.DataFrame, after: pd.Timestamp) -> pd.DataFrame:
    candidates = timeline.loc[
        timeline["timestamp"].ge(after) & timeline["run_status"].eq("OFF")
    ]
    if candidates.empty:
        return candidates
    first_position = timeline.index[timeline["timestamp"].eq(candidates.iloc[0]["timestamp"])][0]
    rows = []
    for _, row in timeline.loc[first_position:].iterrows():
        if row["run_status"] != "OFF":
            break
        rows.append(row)
    return pd.DataFrame(rows, columns=timeline.columns)


def _sampling_interval_hours(timestamps: pd.Series) -> float:
    intervals = timestamps.sort_values().diff().dropna().dt.total_seconds() / 3600
    if intervals.empty:
        raise ValueError("At least two telemetry timestamps are required")
    return float(intervals.median())
