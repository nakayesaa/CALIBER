"""Acceptance tests for the source-anchored KO-3201 canonical build."""

from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

import pytest

from scripts.ingest_ko_3201 import run
from scripts.seed_database import seed


ROOT = Path(__file__).resolve().parents[3]
RAW_DIRECTORY = ROOT / "data/raw/ko_3201"


@pytest.fixture(scope="module")
def canonical_directory(tmp_path_factory: pytest.TempPathFactory) -> Path:
    if not RAW_DIRECTORY.is_dir():
        pytest.skip("Raw KO-3201 files are not available in this checkout")
    output = tmp_path_factory.mktemp("ko_3201_canonical")
    report = run(ROOT, output)
    assert report["status"] == "PASS_WITH_DOCUMENTED_WARNINGS"
    return output


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_source_counts_and_critical_milestones(canonical_directory: Path) -> None:
    report = json.loads(
        (canonical_directory / "validation_report.json").read_text(encoding="utf-8")
    )
    assert report["profiles"]["production"]["rows"] == 720
    assert report["profiles"]["production"]["off_rows"] == 32
    assert report["profiles"]["weekly_condition"]["rows"] == 26
    assert report["profiles"]["incidents"]["rows"] == 380
    assert all(check["status"] == "PASS" for check in report["checks"])


def test_source_representations_are_not_silently_merged(
    canonical_directory: Path,
) -> None:
    definitions = read_rows(canonical_directory / "signal_definitions.csv")
    vibration = [
        row for row in definitions if row["canonical_name"] == "radial_vibration_de"
    ]
    assert len(vibration) == 2
    assert {row["unit"] for row in vibration} == {"mm/s", "micron"}
    assert {row["quality_status"] for row in vibration} == {
        "UNIT_CONFLICT",
        "THRESHOLD_CONTEXT_REQUIRED",
    }


def test_ko_incident_and_label_are_traceable(canonical_directory: Path) -> None:
    incidents = read_rows(canonical_directory / "incidents.csv")
    ko_incidents = [row for row in incidents if row["asset_tag"] == "KO-3201"]
    assert len(ko_incidents) == 1
    incident = ko_incidents[0]
    assert incident["incident_id"] == "incident-0002"
    assert float(incident["downtime_hours"]) == 32.0
    assert float(incident["actual_loss_kusd"]) == 1584.0
    assert incident["source_reference"].endswith("!R5")

    labels = read_rows(canonical_directory / "incident_labels.csv")
    label = next(row for row in labels if row["incident_id"] == "incident-0002")
    assert label["failure_mechanism"] == "BEARING_DISTRESS"
    assert label["source_reported_root_cause"] == "LEAKING_OIL_COOLER_TUBE"
    assert label["review_status"] == "CURATED_SOURCE_REPORTED_NOT_APP_CONFIRMED"


def test_only_source_and_derived_lineage_exist_before_synthetic_phase(
    canonical_directory: Path,
) -> None:
    observations = read_rows(canonical_directory / "signal_observations.csv")
    assert {row["source_type"] for row in observations} == {"OBSERVED_ANCHOR"}

    effectiveness = read_rows(canonical_directory / "effectiveness_checks.csv")
    assert effectiveness[0]["source_type"] == "DERIVED_FEATURE"
    assert effectiveness[0]["result"] == "INITIAL_EFFECTIVE"


def test_sqlite_seed_matches_validated_outputs(
    canonical_directory: Path,
    tmp_path: Path,
) -> None:
    database = tmp_path / "caliber-test.db"
    counts = seed(canonical_directory, database)
    assert counts["signal_observations"] == 2984
    assert counts["production_observations"] == 1440
    assert counts["incidents"] == 380

    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        row = connection.execute(
            "SELECT downtime_hours, actual_loss_kusd FROM incidents "
            "WHERE incident_id = 'incident-0002'"
        ).fetchone()
    assert row == (32.0, 1584.0)

