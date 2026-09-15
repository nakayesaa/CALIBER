"""Decision tests for recovery evidence and formal effectiveness closure."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from services.api.app.schemas.canonical import EffectivenessCheck
from services.api.app.services.effectiveness import build_effectiveness_review

JAKARTA = ZoneInfo("Asia/Jakarta")


def make_check(**updates: object) -> EffectivenessCheck:
    values = {
        "effectiveness_check_id": "effectiveness-test",
        "rca_case_id": "rca-test",
        "incident_id": "incident-test",
        "asset_id": "asset-test",
        "monitoring_start": datetime(2026, 5, 6, tzinfo=JAKARTA),
        "monitoring_end": datetime(2026, 6, 3, tzinfo=JAKARTA),
        "baseline_window": "healthy baseline",
        "comparison_metrics": {
            "radial_vibration_micron": {"before": 76.5, "after": 27.111},
            "water_in_oil_ppm": {"before": 1530.0, "after": 248.268},
            "lube_oil_pressure_barg": {"before": 1.078, "after": 1.718},
            "bearing_metal_temperature_degc": {
                "before": 112.2,
                "after": 76.162,
            },
            "post_repair_normal_weeks": 5,
        },
        "recurrence_detected": False,
        "result": "INITIAL_EFFECTIVE",
        "explanation": "Condition improved during monitoring.",
        "approved_by": None,
        "approved_at": None,
        "source_type": "DERIVED_FEATURE",
        "source_reference": "condition-history",
    }
    values.update(updates)
    return EffectivenessCheck.model_validate(values)


def test_initial_recovery_does_not_authorize_closure() -> None:
    review = build_effectiveness_review(make_check())

    assert review.recovery_confirmed is True
    assert review.approval_status == "PENDING_REVIEW"
    assert review.closure_eligible is False
    assert [metric.outcome for metric in review.metrics] == ["IMPROVED"] * 4


def test_recurrence_blocks_recovery_even_when_individual_metrics_improve() -> None:
    review = build_effectiveness_review(
        make_check(result="RECURRENCE", recurrence_detected=True)
    )

    assert review.recovery_confirmed is False
    assert review.closure_eligible is False


def test_effective_approved_review_is_eligible_for_closure() -> None:
    review = build_effectiveness_review(
        make_check(
            result="EFFECTIVE",
            approved_by="Reliability Manager",
            approved_at=datetime(2026, 6, 4, tzinfo=JAKARTA),
        )
    )

    assert review.recovery_confirmed is True
    assert review.approval_status == "APPROVED"
    assert review.closure_eligible is True
