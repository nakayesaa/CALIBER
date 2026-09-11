"""Acceptance tests for KO-3201 historical incident retrieval outputs."""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

import pytest

from scripts.build_ko_3201_retrieval import run


ROOT = Path(__file__).resolve().parents[3]
NORMALIZED_DIRECTORY = ROOT / "data/normalized/ko_3201"
ALERT_DIRECTORY = ROOT / "data/alerts/ko_3201/v1"


@pytest.fixture(scope="module")
def retrieval_directory(tmp_path_factory: pytest.TempPathFactory) -> Path:
    required = [
        NORMALIZED_DIRECTORY / "incidents.csv",
        NORMALIZED_DIRECTORY / "incident_labels.csv",
        NORMALIZED_DIRECTORY / "validation_report.json",
        ALERT_DIRECTORY / "alerts.csv",
        ALERT_DIRECTORY / "hourly_alert_decisions.csv",
        ALERT_DIRECTORY / "technical_validation.json",
    ]
    if not all(path.is_file() for path in required):
        pytest.skip("KO-3201 canonical and alert outputs are not available")
    output = tmp_path_factory.mktemp("ko_3201_retrieval")
    report = run(ROOT, NORMALIZED_DIRECTORY, ALERT_DIRECTORY, output)
    assert report["status"] == "PASS"
    return output


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_query_represents_only_information_visible_at_warning(
    retrieval_directory: Path,
) -> None:
    query = json.loads(
        (retrieval_directory / "retrieval_query.json").read_text(encoding="utf-8")
    )
    assert query["as_of"] == "2026-02-23T19:00:00+07:00"
    assert query["breached_signals"] == ["water_in_oil"]
    assert query["supporting_signals"] == [
        "bearing_temperature",
        "radial_vibration",
    ]
    assert "lube_oil_pressure" not in query["breached_signals"]


def test_eligible_corpus_excludes_current_case_and_future_rows(
    retrieval_directory: Path,
) -> None:
    rows = read_rows(retrieval_directory / "eligible_incident_documents.csv")
    assert len(rows) == 314
    assert "incident-0002" not in {row["incident_id"] for row in rows}
    assert all(row["occurred_at"] < "2026-02-23T19:00:00+07:00" for row in rows)
    assert "source_reported_root_cause" not in rows[0]


def test_ranked_analogues_are_diverse_and_relevant(
    retrieval_directory: Path,
) -> None:
    rows = read_rows(retrieval_directory / "retrieval_results.csv")
    mechanisms = Counter(row["failure_mechanism"] for row in rows)
    assert len(rows) == 8
    assert max(mechanisms.values()) <= 2
    assert rows[0]["title"] == "KO-8443C Bearing Worn Out"
    assert {row["failure_mechanism"] for row in rows[:5]} >= {
        "WORN_OUT",
        "HIGH_VIBRATION",
        "LEAKAGE",
    }


def test_rag_package_preserves_evidence_boundaries(
    retrieval_directory: Path,
) -> None:
    package = json.loads(
        (retrieval_directory / "rag_evidence_package.json").read_text(
            encoding="utf-8"
        )
    )
    serialized = json.dumps(package)
    assert package["created_for_stage"] == "EARLY_WARNING_RCA"
    assert len(package["historical_analogues"]) == 8
    assert "source_reported_root_cause" not in serialized
    assert "LEAKING_OIL_COOLER_TUBE" not in serialized
