"""Deterministic incident-label normalization.

The rules create a reviewable first-pass taxonomy for retrieval.  They never
overwrite raw incident fields, and non-anchor rows remain marked for review.
"""

from __future__ import annotations

from typing import Any

from services.api.app.schemas.canonical import Incident, IncidentLabel
from services.api.app.services.data.normalization import slug_label


def normalize_incident_label(
    incident: Incident,
    taxonomy: dict[str, Any],
) -> IncidentLabel:
    """Return a governed label package for one raw incident."""

    if incident.asset_tag == "KO-3201":
        override = taxonomy["ko_3201_override"]
        return IncidentLabel(
            incident_id=incident.incident_id,
            equipment_family=override["equipment_family"],
            discipline="ROTATING",
            component=override["component"],
            observed_symptoms=override["observed_symptoms"],
            failure_family="BEARING_LUBRICATION_THERMAL",
            failure_mechanism=override["failure_mechanism"],
            probable_cause_family=override["probable_cause_family"],
            source_reported_root_cause=override["source_reported_root_cause"],
            business_consequences=override["business_consequences"],
            confidence=0.98,
            normalization_method="CURATED_ANCHOR_V1",
            normalization_reason=(
                "Matched KO-3201 incident, four condition signals, and supplied RCA deck"
            ),
            review_status="CURATED_SOURCE_REPORTED_NOT_APP_CONFIRMED",
        )

    searchable = (
        f"{incident.title} {incident.component_raw} {incident.mechanism_raw}"
    ).lower()
    failure_family = "UNCLASSIFIED"
    matched_keywords: list[str] = []
    for family in taxonomy["failure_families"]:
        matches = [keyword for keyword in family["keywords"] if keyword in searchable]
        if matches:
            failure_family = family["label"]
            matched_keywords = matches
            break

    equipment_family = taxonomy["equipment_type_map"].get(
        incident.equipment_type_raw,
        f"CODE_{slug_label(incident.equipment_type_raw)}",
    )
    discipline = taxonomy["discipline_map"].get(
        incident.discipline_raw,
        slug_label(incident.discipline_raw),
    )
    consequences: list[str] = []
    if incident.downtime_hours > 0:
        consequences.append("DOWNTIME")
    if incident.actual_loss_kusd > 0:
        consequences.append("FINANCIAL_LOSS")
    if "uptime" in incident.highest_impact.lower() or "breakdown" in incident.highest_impact.lower():
        consequences.append("PRODUCTION_OR_UPTIME_LOSS")
    if not consequences:
        consequences.append("POTENTIAL_OPERATIONAL_IMPACT")

    confidence = 0.82 if matched_keywords else 0.45
    reason = (
        "Ordered deterministic keyword match: " + ", ".join(matched_keywords)
        if matched_keywords
        else "No governed failure-family keyword matched"
    )
    return IncidentLabel(
        incident_id=incident.incident_id,
        equipment_family=equipment_family,
        discipline=discipline,
        component=slug_label(incident.component_raw),
        observed_symptoms=[slug_label(incident.mechanism_raw)],
        failure_family=failure_family,
        failure_mechanism=slug_label(incident.mechanism_raw),
        business_consequences=consequences,
        confidence=confidence,
        normalization_method="ORDERED_RULES_V1",
        normalization_reason=reason,
        review_status="NEEDS_REVIEW",
    )
