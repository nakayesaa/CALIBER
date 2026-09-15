"""Acceptance tests for the deterministic KO-3201 six-month scenario."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pandas as pd
import pytest

from scripts.generate_ko_3201_scenario import run as generate_scenario
from scripts.ingest_ko_3201 import run as build_canonical

ROOT = Path(__file__).resolve().parents[3]
RAW_DIRECTORY = ROOT / "data/raw/ko_3201"


@pytest.fixture(scope="module")
def scenario_directory(tmp_path_factory: pytest.TempPathFactory) -> Path:
    if not RAW_DIRECTORY.is_dir():
        pytest.skip("Raw KO-3201 files are not available in this checkout")
    canonical = tmp_path_factory.mktemp("scenario_canonical")
    output = tmp_path_factory.mktemp("ko_3201_scenario")
    build_canonical(ROOT, canonical)
    report = generate_scenario(ROOT, canonical, output)
    assert report["status"] == "PASS"
    return output


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_scenario_has_complete_six_month_hourly_grid(
    scenario_directory: Path,
) -> None:
    rows = read_rows(scenario_directory / "hourly_scenario.csv")
    assert len(rows) == 4368
    timestamps = pd.to_datetime([row["timestamp"] for row in rows], utc=True)
    assert timestamps.is_unique
    assert timestamps[0].isoformat() == "2025-12-09T17:00:00+00:00"
    assert timestamps[-1].isoformat() == "2026-06-09T16:00:00+00:00"
    assert (timestamps.to_series().diff().dropna() == pd.Timedelta(hours=1)).all()


def test_weekly_condition_anchors_are_exact(scenario_directory: Path) -> None:
    anchors = read_rows(scenario_directory / "weekly_anchor_check.csv")
    assert len(anchors) == 104
    assert max(float(row["absolute_error"]) for row in anchors) <= 1e-9
    assert {row["signal_name"] for row in anchors} == {
        "radial_vibration_de",
        "water_in_oil",
        "lube_oil_pressure",
        "bearing_metal_temperature",
    }


def test_april_process_source_is_preserved(scenario_directory: Path) -> None:
    rows = read_rows(scenario_directory / "hourly_scenario.csv")
    april = [row for row in rows if row["process_source_type"] == "OBSERVED_ANCHOR"]
    assert len(april) == 720
    assert sum(row["run_status"] == "OFF" for row in april) == 32
    source = pd.read_excel(
        RAW_DIRECTORY / "production_data_ko_3201.xlsx", sheet_name="Sheet2"
    )
    source_first = source.iloc[0]
    scenario_first = next(
        row for row in april if row["timestamp"] == "2026-04-01T00:00:00+07:00"
    )
    assert float(scenario_first["feed_rate_tph"]) == float(source_first["KO3201_FEED"])
    assert float(scenario_first["pi_vibration_mm_s_as_reported"]) == float(
        source_first["KO3201_VIB"]
    )


def test_labels_support_training_and_evaluation(scenario_directory: Path) -> None:
    rows = read_rows(scenario_directory / "hourly_scenario.csv")
    phases = {row["scenario_phase"] for row in rows}
    assert phases == {
        "HEALTHY_BASELINE",
        "EARLY_DEGRADATION",
        "PERSISTENT_ALARM",
        "ACUTE_ESCALATION",
        "TRIP_AND_SHUTDOWN",
        "REPAIR_INTERVENTION",
        "RESTART",
        "POST_REPAIR_MONITORING",
        "STABLE_RECOVERY",
    }
    eligible = [row for row in rows if row["training_eligible"] == "True"]
    assert len(eligible) == 1505
    assert all(row["scenario_phase"] == "HEALTHY_BASELINE" for row in eligible)
    assert all(not row["event_marker"] for row in eligible)


def test_long_form_and_manifest_match_wide_data(scenario_directory: Path) -> None:
    observations = read_rows(scenario_directory / "signal_observations.csv")
    definitions = read_rows(scenario_directory / "signal_definitions.csv")
    manifest = json.loads(
        (scenario_directory / "scenario_manifest.json").read_text(encoding="utf-8")
    )
    assert len(observations) == 17472
    assert len(definitions) == 4
    assert manifest["timestamp_count"] == 4368
    assert len(manifest["primary_signals"]) == 4


def test_generation_is_reproducible(
    scenario_directory: Path,
    tmp_path: Path,
) -> None:
    output = tmp_path / "rerun"
    canonical = tmp_path / "canonical"
    build_canonical(ROOT, canonical)
    generate_scenario(ROOT, canonical, output)
    first = (scenario_directory / "hourly_scenario.csv").read_bytes()
    second = (output / "hourly_scenario.csv").read_bytes()
    assert first == second
