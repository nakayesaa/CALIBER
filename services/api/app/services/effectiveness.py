"""Translate canonical effectiveness evidence into a product decision view."""

from __future__ import annotations

from dataclasses import dataclass

from services.api.app.schemas.canonical import EffectivenessCheck
from services.api.app.schemas.effectiveness import (
    EffectivenessMetric,
    EffectivenessReview,
)


@dataclass(frozen=True)
class MetricDefinition:
    label: str
    unit: str
    direction_of_concern: str


METRIC_DEFINITIONS = {
    "radial_vibration_micron": MetricDefinition(
        "Radial vibration", "µm", "HIGH"
    ),
    "water_in_oil_ppm": MetricDefinition("Water in oil", "ppm", "HIGH"),
    "lube_oil_pressure_barg": MetricDefinition(
        "Lube-oil pressure", "barg", "LOW"
    ),
    "bearing_metal_temperature_degc": MetricDefinition(
        "Bearing temperature", "°C", "HIGH"
    ),
}


def build_effectiveness_review(check: EffectivenessCheck) -> EffectivenessReview:
    metrics = [
        _build_metric(signal_key, check.comparison_metrics[signal_key])
        for signal_key in METRIC_DEFINITIONS
    ]
    monitoring_periods = int(
        check.comparison_metrics.get("post_repair_normal_weeks", 0)
    )
    recovery_confirmed = (
        bool(metrics)
        and all(metric.outcome == "IMPROVED" for metric in metrics)
        and not check.recurrence_detected
        and check.result in {"INITIAL_EFFECTIVE", "EFFECTIVE"}
    )
    approval_status = (
        "APPROVED" if check.approved_by and check.approved_at else "PENDING_REVIEW"
    )
    return EffectivenessReview(
        effectiveness_check_id=check.effectiveness_check_id,
        rca_case_id=check.rca_case_id,
        incident_id=check.incident_id,
        asset_id=check.asset_id,
        monitoring_start=check.monitoring_start,
        monitoring_end=check.monitoring_end,
        monitoring_periods=monitoring_periods,
        baseline_window=check.baseline_window,
        result=check.result,
        recurrence_detected=check.recurrence_detected,
        recovery_confirmed=recovery_confirmed,
        approval_status=approval_status,
        closure_eligible=check.result == "EFFECTIVE" and approval_status == "APPROVED",
        explanation=check.explanation,
        approved_by=check.approved_by,
        approved_at=check.approved_at,
        source_reference=check.source_reference,
        metrics=metrics,
    )


def _build_metric(signal_key: str, comparison: object) -> EffectivenessMetric:
    definition = METRIC_DEFINITIONS[signal_key]
    if not isinstance(comparison, dict) or not {"before", "after"} <= comparison.keys():
        raise ValueError(f"Invalid effectiveness comparison for {signal_key}")
    before = float(comparison["before"])
    after = float(comparison["after"])
    signed_improvement = (
        before - after
        if definition.direction_of_concern == "HIGH"
        else after - before
    )
    tolerance = max(abs(before), 1.0) * 1e-9
    outcome = (
        "IMPROVED"
        if signed_improvement > tolerance
        else "DETERIORATED"
        if signed_improvement < -tolerance
        else "STABLE"
    )
    improvement_percent = signed_improvement / abs(before) * 100 if before else 0.0
    return EffectivenessMetric(
        signal_key=signal_key,
        label=definition.label,
        unit=definition.unit,
        direction_of_concern=definition.direction_of_concern,
        before=before,
        after=after,
        improvement_percent=round(improvement_percent, 1),
        outcome=outcome,
    )
