"""Bind shared investigation claims to HE evidence rather than compressor records."""

from pathlib import Path

from services.api.app.schemas.alerts import AlertEvent
from services.api.app.schemas.api import ProductionImpact
from services.api.app.schemas.effectiveness import EffectivenessReview
from services.api.app.schemas.traceability import (
    TraceClaim,
    TraceLineageStep,
    TraceRecordPreview,
    TraceSource,
)
from services.api.app.services.equipment_traceability import equipment_source_details
from services.api.app.services.he_repository import HE3301ArtifactRepository
from services.api.app.services.traceability import TraceabilityNotFoundError


def he_traceability_claim(
    root: Path,
    repository: HE3301ArtifactRepository,
    trace_id: str,
    alert: AlertEvent,
    impact: ProductionImpact | None,
    effectiveness: EffectivenessReview,
) -> TraceClaim:
    claims = {
        "health-trajectory": ("Equipment health trajectory", ["he_performance"], "MODEL_OUTPUT"),
        "event-progression": ("Alert event progression", ["he_performance"], "CALCULATED"),
        "condition-insights": ("Equipment condition evidence", ["he_performance"], "STANDARDIZED"),
        "production-shortfall": ("Production shortfall calculation", ["he_production", "he_rca"], "CALCULATED"),
        "rca-indication": ("Root cause evidence", ["he_performance", "he_rca"], "RECORDED"),
        "capa-plan": ("Corrective and preventive action evidence", ["he_rca"], "RECORDED"),
        "recovery-effectiveness": ("Recovery and effectiveness evidence", ["he_performance", "he_rca"], "CALCULATED"),
    }
    if trace_id not in claims:
        raise TraceabilityNotFoundError(f"Traceability claim not found: {trace_id}")
    title, keys, provenance = claims[trace_id]
    bundle = repository.equipment()
    directory = repository._alert_snapshot(alert.alert_id)
    reference = str(directory.relative_to(root)) if directory else "data/normalized/he_3301/equipment.json"
    as_of = alert.peak_score_at
    summary = "HE-3301 weekly condition anchors retain their recorded values and limits."
    value = "26 weekly condition observations"
    calculation = ["Standardize HE source fields without combining assets or changing source cadence."]
    rows = [
        {"signal": signal.key, "value": point.value, "unit": signal.unit,
         "timestamp": point.timestamp.isoformat(), "source_reference": point.source_reference}
        for signal in bundle.signals if signal.cadence == "WEEKLY"
        for point in signal.points[:2]
    ]
    kind = "CANONICAL"
    if trace_id in {"health-trajectory", "event-progression"}:
        kind = "MODEL" if directory else "RULE"
        provenance = "MODEL_OUTPUT" if directory else "CALCULATED"
        value = f"{alert.peak_anomaly_score:.1f} peak score" if trace_id == "health-trajectory" else alert.highest_severity
        series = repository.telemetry(alert.asset_id, None, None, 10)
        summary = series.validation_note or "Weekly engineering-limit assessment; no fitted hourly model is active."
        calculation = [
            "Reconstruct hourly condition between dated weekly source anchors; preserve the source readings." if directory
            else "Preserve the weekly source observations and their engineering limits.",
            "Apply the published model, calibration and persistent engineering alert policy." if directory
            else "Assess weekly observations against the configured HE engineering limits.",
        ]
        rows = [{"timestamp": item.timestamp, "from_state": item.previous_state,
                 "to_state": item.new_state, "reason": item.reason}
                for item in repository.get_alert_transitions(alert.alert_id)]
    elif trace_id == "production-shortfall":
        value = f"{impact.estimated_shortfall_tonnes:.1f} tonnes" if impact else "Unavailable"
        summary = "May operating records support a load-matched pre-outage median; hourly OFF samples and RCA downtime remain separate evidence."
        calculation = [
            "Use pre-outage ON observations within the configured operating-load tolerance.",
            "Sum max(expected feed - observed feed, 0) over the outage intervals.",
            f"RCA reports {bundle.reported_downtime_hours:g} h downtime and {bundle.reported_production_loss_tonnes:g} tonnes loss; these do not override sampled OFF duration.",
        ]
        rows = [] if impact is None else [{
            "expected_feed_tph": impact.baseline.expected_feed_tph,
            "sampled_off_hours": impact.offline_hours,
            "estimated_shortfall_tonnes": impact.estimated_shortfall_tonnes,
            "rca_reported_hours": bundle.reported_downtime_hours,
            "rca_reported_loss_tonnes": bundle.reported_production_loss_tonnes,
        }]
        reference = "data/catalog/he_3301_production_impact.yaml"
        if impact:
            as_of = impact.window_end.isoformat()
        kind = "RULE"
    elif trace_id == "rca-indication":
        value = "Source incident evidence"
        summary = "Dated findings from the HE source RCA support retrospective investigation; they are not observations available at the first warning."
        calculation = ["Keep evidence timestamps and source references visible; distinguish source findings from generated hypotheses."]
        rows = [{"timestamp": event.occurred_at.isoformat(), "title": event.title,
                 "source_reference": event.source_reference} for event in bundle.events]
        if bundle.events:
            as_of = max(event.occurred_at for event in bundle.events).isoformat()
    elif trace_id == "capa-plan":
        value = f"{len(bundle.source_actions)} recorded source actions"
        summary = "Source CAPA entries inform the prepared plan. Current approval, delegation and closure require their own governed records."
        calculation = ["Preserve the source action owner, deadline and recorded status without inventing a current authorization."]
        rows = [{"title": action.title, "owner": action.owner, "due_date": action.due_date.isoformat(),
                 "source_status": action.status, "source_reference": action.source_reference}
                for action in bundle.source_actions]
    elif trace_id == "recovery-effectiveness":
        value = effectiveness.result
        summary = effectiveness.explanation
        calculation = ["Compare pre-intervention and post-repair weekly condition values using each signal's direction of concern.",
                       f"Human review status: {effectiveness.approval_status}; metric improvement is not automatic closure."]
        rows = [{"signal": metric.signal_key, "before": metric.before, "after": metric.after,
                 "unit": metric.unit, "outcome": metric.outcome} for metric in effectiveness.metrics]
        reference = effectiveness.source_reference
        as_of = effectiveness.monitoring_end.isoformat()
    details = equipment_source_details(root)
    sources = [TraceSource(source_key=detail.source.source_key, title=detail.source.title,
                           location=detail.local_path, role=detail.source.role, mappings=detail.mappings)
               for detail in details if detail.source.source_key in keys]
    columns = list(rows[0]) if rows else []
    return TraceClaim(
        trace_id=trace_id, title=f"HE-3301 · {title}", value=value, unit=None,
        provenance=provenance, summary=summary, as_of=as_of,
        calculation=calculation, sources=sources,
        quality_issues=[issue for detail in details
                        if detail.source.source_key == keys[0] for issue in detail.quality_issues],
        lineage=[
            *[TraceLineageStep(sequence=index, kind="SOURCE", label=source.title, reference=source.location)
              for index, source in enumerate(sources, 1)],
            TraceLineageStep(sequence=len(sources) + 1, kind=kind, label=title, reference=reference),
            TraceLineageStep(sequence=len(sources) + 2, kind="VIEW", label="HE investigation workspace", reference=trace_id),
        ],
        preview=TraceRecordPreview(columns=columns, rows=rows[:10]) if rows else None,
    )
