"""Leakage-safe hybrid retrieval for historical manufacturing incidents."""

from __future__ import annotations

import json
import re
from collections import Counter
from typing import Any, Iterable

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer

from services.api.app.schemas.retrieval import (
    IncidentDocument,
    IncidentRetrievalConfig,
    IncidentRetrievalResult,
    RetrievalQuery,
    TfidfConfig,
)


DOCUMENT_COLUMNS = {
    "incident_id",
    "occurred_at",
    "asset_tag",
    "plant_id",
    "title",
    "highest_impact",
    "downtime_hours",
    "total_loss_kusd",
    "source_reference",
}
LABEL_COLUMNS = {
    "incident_id",
    "equipment_family",
    "discipline",
    "component",
    "observed_symptoms",
    "failure_family",
    "failure_mechanism",
    "business_consequences",
}
ASSET_COLUMNS = {
    "asset_id",
    "tag",
    "plant_id",
    "equipment_family",
    "discipline",
}
DECISION_COLUMNS = {
    "timestamp",
    "breached_signals",
    "top_driver_1",
    "top_driver_1_score",
}


def parse_json_list(value: Any, field: str) -> list[str]:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    try:
        decoded = json.loads(str(value))
    except json.JSONDecodeError as error:
        raise ValueError(f"{field} must contain a JSON list") from error
    if not isinstance(decoded, list):
        raise ValueError(f"{field} must contain a JSON list")
    return [str(item) for item in decoded]


def build_incident_documents(
    incidents: pd.DataFrame,
    labels: pd.DataFrame,
) -> list[IncidentDocument]:
    _require_columns(incidents, DOCUMENT_COLUMNS, "incidents")
    _require_columns(labels, LABEL_COLUMNS, "incident labels")
    if incidents["incident_id"].duplicated().any():
        raise ValueError("Incident IDs must be unique")
    if labels["incident_id"].duplicated().any():
        raise ValueError("Incident label IDs must be unique")

    merged = incidents[list(DOCUMENT_COLUMNS)].merge(
        labels[list(LABEL_COLUMNS)],
        on="incident_id",
        how="inner",
        validate="one_to_one",
    )
    if len(merged) != len(incidents) or len(merged) != len(labels):
        raise ValueError("Every incident must have exactly one normalized label")

    documents: list[IncidentDocument] = []
    for record in merged.to_dict("records"):
        symptoms = parse_json_list(record["observed_symptoms"], "observed_symptoms")
        consequences = parse_json_list(
            record["business_consequences"], "business_consequences"
        )
        search_fields = [
            record["title"],
            record["highest_impact"],
            record["equipment_family"],
            record["discipline"],
            record["component"],
            *symptoms,
            record["failure_family"],
            record["failure_mechanism"],
            *consequences,
        ]
        document_data = {
            **record,
            "observed_symptoms": symptoms,
            "business_consequences": consequences,
            "search_text": _search_text(search_fields),
        }
        documents.append(IncidentDocument.model_validate(document_data))
    return documents


def build_alert_open_query(
    alert: dict[str, Any],
    asset: dict[str, Any],
    hourly_decisions: pd.DataFrame,
    config: IncidentRetrievalConfig,
) -> RetrievalQuery:
    _require_keys(alert, {"alert_id", "asset_id", "opened_at", "policy_id"}, "alert")
    _require_keys(asset, ASSET_COLUMNS, "asset")
    _require_columns(hourly_decisions, DECISION_COLUMNS, "hourly alert decisions")
    if str(alert["policy_id"]) != config.input_alert_policy_id:
        raise ValueError("Alert policy does not match retrieval configuration")
    if str(alert["asset_id"]) != str(asset["asset_id"]):
        raise ValueError("Alert and asset IDs do not match")

    decisions = hourly_decisions[list(DECISION_COLUMNS)].copy()
    decisions["timestamp"] = pd.to_datetime(decisions["timestamp"], errors="raise")
    opened_at = pd.Timestamp(alert["opened_at"])
    visible = decisions.loc[decisions["timestamp"].le(opened_at)]
    opening = visible.loc[visible["timestamp"].eq(opened_at)]
    if len(opening) != 1:
        raise ValueError("Exactly one hourly decision must match alert opened_at")

    opening_row = opening.iloc[0]
    breached_signals = _semicolon_values(opening_row["breached_signals"])
    unknown = set(breached_signals) - set(config.signal_mappings)
    if unknown:
        raise ValueError(f"Missing retrieval mappings for signals: {sorted(unknown)}")
    mappings = [config.signal_mappings[signal] for signal in breached_signals]
    components = _unique(mapping.component for mapping in mappings)
    symptoms = _unique(mapping.symptom for mapping in mappings)
    primary_driver = _driver_signal(opening_row["top_driver_1"])
    narrative_parts = [mapping.narrative for mapping in mappings]
    narrative = "; ".join(narrative_parts) or "model anomaly opened for investigation"
    search_fields = [
        asset["equipment_family"],
        asset["discipline"],
        *components,
        *symptoms,
        narrative,
    ]
    return RetrievalQuery(
        query_id=f"query-{alert['alert_id']}-open",
        alert_id=str(alert["alert_id"]),
        as_of=opened_at.to_pydatetime(),
        asset_id=str(asset["asset_id"]),
        asset_tag=str(asset["tag"]),
        plant_id=str(asset["plant_id"]),
        equipment_family=str(asset["equipment_family"]),
        discipline=str(asset["discipline"]),
        components=components,
        observed_symptoms=symptoms,
        breached_signals=breached_signals,
        primary_driver=primary_driver,
        narrative=narrative,
        search_text=_search_text(search_fields),
    )


def retrieve_incidents(
    documents: list[IncidentDocument],
    query: RetrievalQuery,
    config: IncidentRetrievalConfig,
) -> list[IncidentRetrievalResult]:
    excluded = set(config.eligibility.exclude_incident_ids)
    eligible = [document for document in documents if document.incident_id not in excluded]
    if config.eligibility.require_occurred_before_alert_open:
        eligible = [document for document in eligible if document.occurred_at < query.as_of]
    if not eligible:
        return []

    corpus = [document.search_text for document in eligible]
    word_scores = _tfidf_scores(corpus, query.search_text, config.word_vectorizer)
    character_scores = _tfidf_scores(
        corpus, query.search_text, config.character_vectorizer
    )
    weighted: list[tuple[IncidentRetrievalResult, pd.Timestamp]] = []
    query_components = set(query.components)
    query_symptoms = set(query.observed_symptoms)
    weights = config.weights

    for index, document in enumerate(eligible):
        equipment_score = float(document.equipment_family == query.equipment_family)
        discipline_score = float(document.discipline == query.discipline)
        component_score = _set_overlap(query_components, {document.component})
        symptom_score = _set_overlap(query_symptoms, set(document.observed_symptoms))
        plant_score = float(document.plant_id == query.plant_id)
        hybrid_score = (
            weights.word_similarity * word_scores[index]
            + weights.character_similarity * character_scores[index]
            + weights.equipment_family * equipment_score
            + weights.discipline * discipline_score
            + weights.component_overlap * component_score
            + weights.symptom_overlap * symptom_score
            + weights.plant * plant_score
        )
        if hybrid_score < config.minimum_hybrid_score:
            continue
        result = IncidentRetrievalResult(
            query_id=query.query_id,
            rank=1,
            incident_id=document.incident_id,
            occurred_at=document.occurred_at,
            asset_tag=document.asset_tag,
            title=document.title,
            equipment_family=document.equipment_family,
            discipline=document.discipline,
            component=document.component,
            failure_mechanism=document.failure_mechanism,
            observed_symptoms=document.observed_symptoms,
            business_consequences=document.business_consequences,
            hybrid_score=_bounded(hybrid_score),
            word_similarity=_bounded(word_scores[index]),
            character_similarity=_bounded(character_scores[index]),
            equipment_family_score=equipment_score,
            discipline_score=discipline_score,
            component_overlap_score=component_score,
            symptom_overlap_score=symptom_score,
            plant_score=plant_score,
            match_reasons=_match_reasons(
                document,
                equipment_score,
                discipline_score,
                component_score,
                symptom_score,
                plant_score,
            ),
            source_reference=document.source_reference,
        )
        weighted.append((result, pd.Timestamp(document.occurred_at)))

    weighted.sort(
        key=lambda item: (
            -item[0].hybrid_score,
            -item[1].value,
            item[0].incident_id,
        )
    )
    selected: list[IncidentRetrievalResult] = []
    mechanism_counts: Counter[str] = Counter()
    for result, _ in weighted:
        if mechanism_counts[result.failure_mechanism] >= (
            config.diversity.maximum_per_failure_mechanism
        ):
            continue
        selected.append(result.model_copy(update={"rank": len(selected) + 1}))
        mechanism_counts[result.failure_mechanism] += 1
        if len(selected) == config.top_k:
            break
    return selected


def _tfidf_scores(
    corpus: list[str],
    query: str,
    config: TfidfConfig,
) -> np.ndarray:
    vectorizer = TfidfVectorizer(
        analyzer=config.analyzer,
        ngram_range=config.ngram_range,
        sublinear_tf=config.sublinear_tf,
        lowercase=True,
        strip_accents="unicode",
    )
    document_matrix = vectorizer.fit_transform(corpus)
    query_vector = vectorizer.transform([query])
    return (document_matrix @ query_vector.T).toarray().ravel()


def _set_overlap(query_values: set[str], document_values: set[str]) -> float:
    if not query_values or not document_values:
        return 0.0
    return len(query_values & document_values) / len(query_values | document_values)


def _match_reasons(
    document: IncidentDocument,
    equipment_score: float,
    discipline_score: float,
    component_score: float,
    symptom_score: float,
    plant_score: float,
) -> list[str]:
    candidates = [
        (equipment_score, f"same equipment family: {document.equipment_family}"),
        (discipline_score, f"same discipline: {document.discipline}"),
        (component_score, f"component overlap: {document.component}"),
        (symptom_score, "observed symptom overlap"),
        (plant_score, f"same plant: {document.plant_id}"),
    ]
    return [reason for score, reason in candidates if score > 0]


def _require_columns(frame: pd.DataFrame, required: set[str], name: str) -> None:
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"{name} is missing columns: {sorted(missing)}")


def _require_keys(record: dict[str, Any], required: set[str], name: str) -> None:
    missing = required - set(record)
    if missing:
        raise ValueError(f"{name} is missing fields: {sorted(missing)}")


def _search_text(values: Iterable[Any]) -> str:
    tokens: list[str] = []
    for value in values:
        if value is None or (isinstance(value, float) and np.isnan(value)):
            continue
        tokens.append(re.sub(r"[_\W]+", " ", str(value)).strip().lower())
    return " ".join(token for token in tokens if token)


def _semicolon_values(value: Any) -> list[str]:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return []
    return _unique(part.strip() for part in str(value).split(";") if part.strip())


def _driver_signal(value: Any) -> str:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return ""
    return str(value).removeprefix("condition.")


def _unique(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _bounded(value: float) -> float:
    return round(float(np.clip(value, 0.0, 1.0)), 8)
