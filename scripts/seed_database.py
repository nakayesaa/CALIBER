#!/usr/bin/env python3
"""Seed a deterministic SQLite database from validated canonical CSV outputs."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

import pandas as pd

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = REPOSITORY_ROOT / "data/normalized/ko_3201"
DEFAULT_DATABASE = REPOSITORY_ROOT / "data/caliber.db"

TABLE_FILES = {
    "assets": "assets.csv",
    "signal_definitions": "signal_definitions.csv",
    "signal_observations": "signal_observations.csv",
    "production_observations": "production_observations.csv",
    "operating_periods": "operating_periods.csv",
    "incidents": "incidents.csv",
    "incident_labels": "incident_labels.csv",
    "rca_cases": "rca_cases.csv",
    "evidence": "evidence.csv",
    "hypotheses": "hypotheses.csv",
    "actions": "actions.csv",
    "effectiveness_checks": "effectiveness_checks.csv",
    "quality_issues": "quality_issues.csv",
}

INDEXES = [
    "CREATE UNIQUE INDEX idx_assets_tag ON assets(tag)",
    "CREATE UNIQUE INDEX idx_signal_definitions_id ON signal_definitions(signal_id)",
    "CREATE UNIQUE INDEX idx_signal_observations_id ON signal_observations(observation_id)",
    "CREATE INDEX idx_signal_observations_asset_time ON signal_observations(asset_id, timestamp)",
    "CREATE INDEX idx_signal_observations_signal_time ON signal_observations(signal_id, timestamp)",
    "CREATE UNIQUE INDEX idx_production_observations_id ON production_observations(observation_id)",
    "CREATE INDEX idx_production_observations_asset_time ON production_observations(asset_id, timestamp)",
    "CREATE UNIQUE INDEX idx_incidents_id ON incidents(incident_id)",
    "CREATE INDEX idx_incidents_asset ON incidents(asset_tag)",
    "CREATE INDEX idx_incidents_workflow ON incidents(workflow_status)",
    "CREATE UNIQUE INDEX idx_incident_labels_incident ON incident_labels(incident_id)",
    "CREATE UNIQUE INDEX idx_rca_cases_id ON rca_cases(rca_case_id)",
    "CREATE INDEX idx_evidence_case ON evidence(rca_case_id)",
    "CREATE INDEX idx_hypotheses_case ON hypotheses(rca_case_id)",
    "CREATE INDEX idx_actions_case ON actions(rca_case_id)",
    "CREATE INDEX idx_quality_entity ON quality_issues(entity_type, entity_id)",
]

TABLE_COUNT_QUERY = """
SELECT 'assets', COUNT(*) FROM assets
UNION ALL SELECT 'signal_definitions', COUNT(*) FROM signal_definitions
UNION ALL SELECT 'signal_observations', COUNT(*) FROM signal_observations
UNION ALL SELECT 'production_observations', COUNT(*) FROM production_observations
UNION ALL SELECT 'operating_periods', COUNT(*) FROM operating_periods
UNION ALL SELECT 'incidents', COUNT(*) FROM incidents
UNION ALL SELECT 'incident_labels', COUNT(*) FROM incident_labels
UNION ALL SELECT 'rca_cases', COUNT(*) FROM rca_cases
UNION ALL SELECT 'evidence', COUNT(*) FROM evidence
UNION ALL SELECT 'hypotheses', COUNT(*) FROM hypotheses
UNION ALL SELECT 'actions', COUNT(*) FROM actions
UNION ALL SELECT 'effectiveness_checks', COUNT(*) FROM effectiveness_checks
UNION ALL SELECT 'quality_issues', COUNT(*) FROM quality_issues
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    return parser.parse_args()


def load_validation(input_directory: Path) -> dict:
    path = input_directory / "validation_report.json"
    if not path.is_file():
        raise FileNotFoundError(f"Missing canonical validation report: {path}")
    report = json.loads(path.read_text(encoding="utf-8"))
    if report["status"] not in {"PASS", "PASS_WITH_DOCUMENTED_WARNINGS"}:
        raise RuntimeError(f"Refusing to seed unvalidated data: {report['status']}")
    return report


def seed(input_directory: Path, database: Path) -> dict[str, int]:
    input_directory = input_directory.resolve()
    database = database.resolve()
    validation = load_validation(input_directory)
    missing = [
        filename
        for filename in TABLE_FILES.values()
        if not (input_directory / filename).is_file()
    ]
    if missing:
        raise FileNotFoundError(f"Missing canonical tables: {missing}")

    database.parent.mkdir(parents=True, exist_ok=True)
    temporary = database.with_suffix(database.suffix + ".tmp")
    if temporary.exists():
        temporary.unlink()

    counts: dict[str, int] = {}
    try:
        with sqlite3.connect(temporary) as connection:
            connection.execute("PRAGMA journal_mode=DELETE")
            connection.execute("PRAGMA synchronous=FULL")
            for table, filename in TABLE_FILES.items():
                frame = pd.read_csv(input_directory / filename, keep_default_na=False)
                frame.to_sql(table, connection, if_exists="fail", index=False)
                counts[table] = len(frame)

            connection.execute(
                "CREATE TABLE dataset_registry (dataset TEXT PRIMARY KEY, "
                "dataset_version TEXT NOT NULL, ingestion_version TEXT NOT NULL, "
                "validation_status TEXT NOT NULL, generated_at TEXT NOT NULL)"
            )
            connection.execute(
                "INSERT INTO dataset_registry VALUES (?, ?, ?, ?, ?)",
                (
                    validation["dataset"],
                    validation["dataset_version"],
                    validation["ingestion_version"],
                    validation["status"],
                    validation["generated_at"],
                ),
            )
            for statement in INDEXES:
                connection.execute(statement)
            connection.commit()

            actual_counts = dict(connection.execute(TABLE_COUNT_QUERY).fetchall())
            for table, expected in counts.items():
                actual = actual_counts[table]
                if actual != expected:
                    raise RuntimeError(
                        f"SQLite row-count mismatch for {table}: {actual} != {expected}"
                    )
            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
            if integrity != "ok":
                raise RuntimeError(f"SQLite integrity check failed: {integrity}")
    except Exception:
        if temporary.exists():
            temporary.unlink()
        raise

    temporary.replace(database)
    return counts


def main() -> None:
    args = parse_args()
    counts = seed(args.input, args.database)
    print(
        json.dumps(
            {
                "database": str(args.database.resolve()),
                "status": "PASS",
                "tables": counts,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
