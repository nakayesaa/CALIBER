"""Unit tests for temporal and outcome-safe incident retrieval."""

from __future__ import annotations

import pandas as pd

from services.api.app.schemas.retrieval import IncidentRetrievalConfig
from services.api.app.schemas.retrieval import IncidentDocument
from services.api.app.services.rca.incident_retrieval import (
    build_alert_open_query,
    build_incident_documents,
    retrieve_incidents,
)


def retrieval_config() -> IncidentRetrievalConfig:
    return IncidentRetrievalConfig.model_validate(
        {
            "retriever_id": "test-retriever",
            "retriever_version": "1.0.0",
            "input_alert_policy_id": "test-policy",
            "top_k": 3,
            "minimum_hybrid_score": 0,
            "word_vectorizer": {
                "analyzer": "word",
                "ngram_range": [1, 2],
                "sublinear_tf": True,
            },
            "character_vectorizer": {
                "analyzer": "char_wb",
                "ngram_range": [3, 5],
                "sublinear_tf": True,
            },
            "weights": {
                "word_similarity": 0.35,
                "character_similarity": 0.15,
                "equipment_family": 0.20,
                "discipline": 0.05,
                "component_overlap": 0.10,
                "symptom_overlap": 0.10,
                "plant": 0.05,
            },
            "eligibility": {
                "exclude_incident_ids": ["current"],
                "require_occurred_before_alert_open": True,
            },
            "diversity": {"maximum_per_failure_mechanism": 1},
            "signal_mappings": {
                "water_in_oil": {
                    "symptom": "HIGH_WATER_IN_OIL",
                    "component": "LUBE_OIL_SYSTEM",
                    "narrative": "water in lube oil exceeded alarm limit",
                },
                "radial_vibration": {
                    "symptom": "HIGH_RADIAL_VIBRATION",
                    "component": "BEARING",
                    "narrative": "radial vibration exceeded alarm limit",
                },
            },
        }
    )


def alert_and_asset() -> tuple[dict[str, str], dict[str, str]]:
    alert = {
        "alert_id": "alert-1",
        "asset_id": "asset-1",
        "opened_at": "2026-02-01T02:00:00+07:00",
        "policy_id": "test-policy",
    }
    asset = {
        "asset_id": "asset-1",
        "tag": "KO-1",
        "plant_id": "ZCU",
        "equipment_family": "COMPRESSOR",
        "discipline": "ROTATING",
    }
    return alert, asset


def decisions() -> pd.DataFrame:
    timestamps = pd.date_range(
        "2026-02-01T00:00:00+07:00", periods=5, freq="1h"
    )
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "breached_signals": ["", "", "water_in_oil", "radial_vibration", ""],
            "top_driver_1": ["", "", "condition.water_in_oil", "condition.radial_vibration", ""],
            "top_driver_1_score": [0, 0, 82, 91, 0],
        }
    )


def incident_frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    incidents = pd.DataFrame(
        [
            ["old-a", "2025-01-01T00:00:00+07:00", "KO-A", "ZCU", "Oil leak", "Downtime", 2, 10, "source-a"],
            ["old-b", "2025-02-01T00:00:00+07:00", "KO-B", "ARP", "Bearing vibration", "Downtime", 3, 20, "source-b"],
            ["old-c", "2025-03-01T00:00:00+07:00", "KO-C", "ARP", "Second oil leak", "Downtime", 1, 5, "source-c"],
            ["current", "2026-01-01T00:00:00+07:00", "KO-1", "ZCU", "Known outcome", "Breakdown", 20, 100, "source-current"],
            ["future", "2026-03-01T00:00:00+07:00", "KO-F", "ZCU", "Future match", "Breakdown", 30, 200, "source-future"],
        ],
        columns=[
            "incident_id", "occurred_at", "asset_tag", "plant_id", "title",
            "highest_impact", "downtime_hours", "total_loss_kusd", "source_reference",
        ],
    )
    labels = pd.DataFrame(
        [
            ["old-a", "COMPRESSOR", "ROTATING", "OIL_SEAL", '["LEAKAGE"]', "LEAKAGE", "LEAKAGE", '["DOWNTIME"]', "seal wear"],
            ["old-b", "COMPRESSOR", "ROTATING", "BEARING", '["HIGH_RADIAL_VIBRATION"]', "VIBRATION", "HIGH_VIBRATION", '["DOWNTIME"]', "misalignment"],
            ["old-c", "COMPRESSOR", "ROTATING", "SEAL", '["LEAKAGE"]', "LEAKAGE", "LEAKAGE", '["DOWNTIME"]', "seal damage"],
            ["current", "COMPRESSOR", "ROTATING", "LUBE_OIL_SYSTEM", '["HIGH_WATER_IN_OIL"]', "BEARING", "BEARING_DISTRESS", '["BREAKDOWN"]', "known secret cause"],
            ["future", "COMPRESSOR", "ROTATING", "LUBE_OIL_SYSTEM", '["HIGH_WATER_IN_OIL"]', "BEARING", "BEARING_DISTRESS", '["BREAKDOWN"]', "future secret cause"],
        ],
        columns=[
            "incident_id", "equipment_family", "discipline", "component",
            "observed_symptoms", "failure_family", "failure_mechanism",
            "business_consequences", "source_reported_root_cause",
        ],
    )
    return incidents, labels


def test_query_uses_only_the_alert_opening_snapshot() -> None:
    alert, asset = alert_and_asset()
    baseline_decisions = decisions()
    baseline = build_alert_open_query(
        alert, asset, baseline_decisions, retrieval_config()
    )

    changed_future = baseline_decisions.copy()
    changed_future.loc[3:, "breached_signals"] = "radial_vibration;water_in_oil"
    changed_future.loc[3:, "top_driver_1"] = "condition.radial_vibration"
    changed = build_alert_open_query(alert, asset, changed_future, retrieval_config())

    assert baseline == changed
    assert baseline.breached_signals == ["water_in_oil"]
    assert baseline.observed_symptoms == ["HIGH_WATER_IN_OIL"]


def test_documents_do_not_expose_reported_root_cause() -> None:
    incidents, labels = incident_frames()
    documents = build_incident_documents(incidents, labels)

    assert "source_reported_root_cause" not in IncidentDocument.model_fields
    assert all("secret cause" not in document.search_text for document in documents)


def test_retrieval_excludes_current_future_and_limits_mechanism_duplicates() -> None:
    incidents, labels = incident_frames()
    documents = build_incident_documents(incidents, labels)
    alert, asset = alert_and_asset()
    query = build_alert_open_query(alert, asset, decisions(), retrieval_config())

    first = retrieve_incidents(documents, query, retrieval_config())
    second = retrieve_incidents(documents, query, retrieval_config())
    ids = [result.incident_id for result in first]

    assert "current" not in ids
    assert "future" not in ids
    assert len([result for result in first if result.failure_mechanism == "LEAKAGE"]) == 1
    assert [result.model_dump() for result in first] == [
        result.model_dump() for result in second
    ]
    assert [result.rank for result in first] == list(range(1, len(first) + 1))
