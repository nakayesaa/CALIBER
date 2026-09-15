#!/usr/bin/env python3
"""Generate the deterministic six-month KO-3201 hourly scenario dataset.

The weekly condition history defines the long-term equipment trajectory.  The
April production workbook is retained at its original hourly timestamps, while
the surrounding process context is generated from the healthy April operating
profile.  Every output is deterministic for the configured seed and validated
before it is published.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from bisect import bisect_right
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, TypeVar

import numpy as np
import pandas as pd
import yaml
from pydantic import BaseModel
from scipy.interpolate import PchipInterpolator

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from services.api.app.schemas.canonical import (
    DirectionOfConcern,
    HealthState,
    OperatingMode,
    QualityFlag,
    ScenarioManifest,
    ScenarioPhase,
    ScenarioTimelinePoint,
    SignalDefinition,
    SignalObservation,
    SourceType,
)

T = TypeVar("T", bound=BaseModel)
ASSET_ID = "asset-ko-3201"
SOURCE_TIMEZONE = "Asia/Jakarta"
GENERATED_AT = datetime.fromisoformat("2026-09-10T00:00:00+07:00")

CONDITION_COLUMNS = {
    "radial_vibration_de": "radial_vibration_micron",
    "water_in_oil": "water_in_oil_ppm",
    "lube_oil_pressure": "lube_oil_pressure_barg",
    "bearing_metal_temperature": "bearing_metal_temperature_degc",
}

PROCESS_COLUMNS = {
    "KO3201_FEED": "feed_rate_tph",
    "KO3201_DISP": "discharge_pressure_barg",
    "KO3201_VIB": "pi_vibration_mm_s_as_reported",
    "KO3201_TEMP": "pi_bearing_process_temperature_degc",
    "KO3201_AMP": "motor_current_a",
    "PLANT_RATE": "plant_rate_tph",
}

PHASE_HEALTH = {
    ScenarioPhase.HEALTHY_BASELINE: HealthState.NORMAL,
    ScenarioPhase.EARLY_DEGRADATION: HealthState.WATCH,
    ScenarioPhase.PERSISTENT_ALARM: HealthState.ALARM,
    ScenarioPhase.ACUTE_ESCALATION: HealthState.CRITICAL,
    ScenarioPhase.TRIP_AND_SHUTDOWN: HealthState.TRIP,
    ScenarioPhase.REPAIR_INTERVENTION: HealthState.TRIP,
    ScenarioPhase.RESTART: HealthState.RECOVERY_MONITORING,
    ScenarioPhase.POST_REPAIR_MONITORING: HealthState.RECOVERY_MONITORING,
    ScenarioPhase.STABLE_RECOVERY: HealthState.NORMAL,
}


@dataclass(frozen=True)
class Anchor:
    signal_name: str
    observation_id: str
    original_timestamp: pd.Timestamp
    effective_timestamp: pd.Timestamp
    value: float
    source_reference: str
    is_source_anchor: bool


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPOSITORY_ROOT)
    parser.add_argument(
        "--canonical",
        type=Path,
        default=None,
        help="Canonical KO-3201 directory (default: data/normalized/ko_3201)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Scenario output directory (default: data/synthetic/ko_3201/v1)",
    )
    return parser.parse_args()


def model_to_row(model: BaseModel) -> dict[str, Any]:
    row = model.model_dump(mode="json")
    for key, value in row.items():
        if isinstance(value, (list, dict)):
            row[key] = json.dumps(value, separators=(",", ":"), sort_keys=True)
    return row


def write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"Refusing to write an empty CSV: {path}")
    temporary = path.with_suffix(path.suffix + ".tmp")
    path.parent.mkdir(parents=True, exist_ok=True)
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def write_models(path: Path, models: list[T]) -> None:
    write_rows(path, [model_to_row(model) for model in models])


def write_json(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_config(root: Path) -> dict[str, Any]:
    path = root / "data/catalog/ko_3201_scenario_config.yaml"
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    required = {
        "scenario_id",
        "scenario_version",
        "generation_version",
        "random_seed",
        "start_time",
        "end_time_exclusive",
        "primary_signals",
        "phases",
    }
    missing = required - set(config)
    if missing:
        raise ValueError(f"Scenario config missing keys: {sorted(missing)}")
    return config


def require_valid_canonical(canonical: Path) -> None:
    report_path = canonical / "validation_report.json"
    if not report_path.is_file():
        raise FileNotFoundError(
            f"Missing canonical validation report: {report_path}. Run make canonical."
        )
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if not str(report.get("status", "")).startswith("PASS"):
        raise RuntimeError(f"Canonical dataset did not pass validation: {report['status']}")


def timestamp_index(config: dict[str, Any]) -> pd.DatetimeIndex:
    start = pd.Timestamp(config["start_time"])
    end = pd.Timestamp(config["end_time_exclusive"])
    index = pd.date_range(start=start, end=end, freq=config["frequency"], inclusive="left")
    expected = int((end - start) / pd.Timedelta(hours=1))
    if len(index) != expected or expected != 4368:
        raise ValueError(f"Expected 4,368 hourly timestamps, received {len(index)}")
    return index


def phase_for_timestamp(timestamp: pd.Timestamp, config: dict[str, Any]) -> ScenarioPhase:
    matches = [
        phase["phase"]
        for phase in config["phases"]
        if pd.Timestamp(phase["start"]) <= timestamp < pd.Timestamp(phase["end"])
    ]
    if len(matches) != 1:
        raise ValueError(f"Timestamp {timestamp} maps to {len(matches)} scenario phases")
    return ScenarioPhase(matches[0])


def event_for_timestamp(timestamp: pd.Timestamp, config: dict[str, Any]) -> str | None:
    matches = [
        event["event_marker"]
        for event in config.get("minor_events", [])
        if pd.Timestamp(event["start"]) <= timestamp < pd.Timestamp(event["end"])
    ]
    if len(matches) > 1:
        raise ValueError(f"Timestamp {timestamp} maps to overlapping minor events")
    return matches[0] if matches else None


def base_mode(phase: ScenarioPhase, event_marker: str | None) -> OperatingMode:
    if event_marker == "STARTUP_TRANSIENT":
        return OperatingMode.STARTUP
    if phase == ScenarioPhase.TRIP_AND_SHUTDOWN:
        return OperatingMode.OFFLINE_TRIP
    if phase == ScenarioPhase.REPAIR_INTERVENTION:
        return OperatingMode.MAINTENANCE
    if phase == ScenarioPhase.RESTART:
        return OperatingMode.RESTART
    return OperatingMode.RUNNING_STEADY


def condition_source_type(phase: ScenarioPhase) -> SourceType:
    if phase == ScenarioPhase.HEALTHY_BASELINE:
        return SourceType.SYNTHETIC_NORMAL
    if phase in {
        ScenarioPhase.EARLY_DEGRADATION,
        ScenarioPhase.PERSISTENT_ALARM,
        ScenarioPhase.ACUTE_ESCALATION,
        ScenarioPhase.TRIP_AND_SHUTDOWN,
    }:
        return SourceType.SYNTHETIC_ANOMALY
    return SourceType.SYNTHETIC_INTERVENTION


def build_timeline(
    index: pd.DatetimeIndex,
    config: dict[str, Any],
    observed_process_timestamps: set[pd.Timestamp],
    observed_anchor_timestamps: set[pd.Timestamp],
) -> list[ScenarioTimelinePoint]:
    timeline: list[ScenarioTimelinePoint] = []
    for timestamp in index:
        phase = phase_for_timestamp(timestamp, config)
        marker = event_for_timestamp(timestamp, config)
        mode = base_mode(phase, marker)
        condition_type = (
            SourceType.OBSERVED_ANCHOR
            if timestamp in observed_anchor_timestamps
            else condition_source_type(phase)
        )
        process_type = (
            SourceType.OBSERVED_ANCHOR
            if timestamp in observed_process_timestamps
            else condition_source_type(phase)
        )
        training_eligible = (
            phase == ScenarioPhase.HEALTHY_BASELINE
            and mode == OperatingMode.RUNNING_STEADY
            and marker is None
        )
        timeline.append(
            ScenarioTimelinePoint(
                scenario_id=config["scenario_id"],
                timestamp=timestamp.to_pydatetime(),
                scenario_phase=phase,
                operating_mode=mode,
                health_state=PHASE_HEALTH[phase],
                condition_source_type=condition_type,
                process_source_type=process_type,
                training_eligible=training_eligible,
                event_marker=marker,
            )
        )
    return timeline


def load_weekly_anchors(
    canonical: Path,
    config: dict[str, Any],
) -> tuple[dict[str, list[Anchor]], dict[str, dict[str, Any]]]:
    definitions = pd.read_csv(canonical / "signal_definitions.csv")
    observations = pd.read_csv(canonical / "signal_observations.csv")
    weekly_definitions = definitions.loc[definitions["source_cadence"] == "WEEKLY"]
    definition_by_name = weekly_definitions.set_index("canonical_name").to_dict("index")
    weekly_ids = set(weekly_definitions["signal_id"])
    weekly = observations.loc[observations["signal_id"].isin(weekly_ids)].copy()
    weekly["timestamp"] = pd.to_datetime(weekly["timestamp"], utc=True).dt.tz_convert(
        SOURCE_TIMEZONE
    )

    anchors_by_signal: dict[str, list[Anchor]] = {}
    for signal_name in config["primary_signals"]:
        definition = definition_by_name.get(signal_name)
        if definition is None:
            raise ValueError(f"No weekly canonical definition for {signal_name}")
        signal_rows = weekly.loc[weekly["signal_id"] == definition["signal_id"]]
        if len(signal_rows) != 26:
            raise ValueError(f"Expected 26 weekly anchors for {signal_name}")

        anchors: list[Anchor] = []
        for row in signal_rows.to_dict("records"):
            original = pd.Timestamp(row["timestamp"])
            effective = original
            if original == pd.Timestamp("2026-04-29T00:00:00+07:00"):
                effective = original + pd.Timedelta(hours=6)
            anchors.append(
                Anchor(
                    signal_name=signal_name,
                    observation_id=str(row["observation_id"]),
                    original_timestamp=original,
                    effective_timestamp=effective,
                    value=float(row["value"]),
                    source_reference=str(row["source_reference"]),
                    is_source_anchor=True,
                )
            )

        restart_time = pd.Timestamp(config["intervention_anchor"]["timestamp"])
        restart_value = float(config["primary_signals"][signal_name]["restart_value"])
        anchors.append(
            Anchor(
                signal_name=signal_name,
                observation_id=f"scenario-restart-{signal_name}",
                original_timestamp=restart_time,
                effective_timestamp=restart_time,
                value=restart_value,
                source_reference="scenario_config#intervention_anchor",
                is_source_anchor=False,
            )
        )
        terminal_time = pd.Timestamp(config["end_time_exclusive"])
        anchors.append(
            Anchor(
                signal_name=signal_name,
                observation_id=f"scenario-terminal-{signal_name}",
                original_timestamp=terminal_time,
                effective_timestamp=terminal_time,
                value=anchors[-2].value,
                source_reference="scenario_config#end_time_exclusive",
                is_source_anchor=False,
            )
        )
        anchors_by_signal[signal_name] = sorted(
            anchors, key=lambda anchor: anchor.effective_timestamp
        )

    return anchors_by_signal, definition_by_name


def ar1_noise(rng: np.random.Generator, count: int, phi: float = 0.88) -> np.ndarray:
    innovations = rng.normal(0.0, 1.0, count)
    values = np.zeros(count, dtype=float)
    scale = np.sqrt(1.0 - phi**2)
    for index in range(1, count):
        values[index] = phi * values[index - 1] + scale * innovations[index]
    return values


def interpolate_conditions(
    index: pd.DatetimeIndex,
    anchors_by_signal: dict[str, list[Anchor]],
    config: dict[str, Any],
) -> pd.DataFrame:
    rng = np.random.default_rng(int(config["random_seed"]))
    origin = index[0]
    target_hours = ((index - origin) / pd.Timedelta(hours=1)).to_numpy(dtype=float)
    common_noise = ar1_noise(rng, len(index), phi=0.94)
    result = pd.DataFrame(index=index)

    for signal_name, output_column in CONDITION_COLUMNS.items():
        settings = config["primary_signals"][signal_name]
        anchors = anchors_by_signal[signal_name]
        anchor_hours = np.array(
            [
                (anchor.effective_timestamp - origin) / pd.Timedelta(hours=1)
                for anchor in anchors
            ],
            dtype=float,
        )
        anchor_values = np.array([anchor.value for anchor in anchors], dtype=float)
        interpolator = PchipInterpolator(anchor_hours, anchor_values, extrapolate=False)
        values = interpolator(target_hours)

        individual_noise = ar1_noise(rng, len(index), phi=0.84)
        residual = float(settings["noise_standard_deviation"]) * (
            0.55 * common_noise + 0.45 * individual_noise
        )
        daily = float(settings["daily_amplitude"]) * np.sin(
            2.0 * np.pi * (index.hour.to_numpy() - 5.0) / 24.0
        )
        nearest_anchor_distance = np.min(
            np.abs(target_hours[:, None] - anchor_hours[None, :]), axis=1
        )
        damping = np.minimum(nearest_anchor_distance / 12.0, 1.0)
        values = values + (residual + daily) * damping

        values = apply_shutdown_profile(
            index=index,
            values=values,
            signal_name=signal_name,
            trip_value=next(
                anchor.value
                for anchor in anchors
                if anchor.original_timestamp
                == pd.Timestamp("2026-04-29T00:00:00+07:00")
            ),
            restart_value=float(settings["restart_value"]),
        )
        values = apply_minor_condition_events(index, values, signal_name, config)
        values = np.clip(
            values,
            float(settings["hard_min"]),
            float(settings["hard_max"]),
        )

        for anchor in anchors:
            if anchor.effective_timestamp in index:
                position = index.get_loc(anchor.effective_timestamp)
                values[position] = anchor.value
        result[output_column] = np.round(values, 4)
    return result


def apply_shutdown_profile(
    index: pd.DatetimeIndex,
    values: np.ndarray,
    signal_name: str,
    trip_value: float,
    restart_value: float,
) -> np.ndarray:
    start = pd.Timestamp("2026-04-29T07:00:00+07:00")
    restart = pd.Timestamp("2026-04-30T15:00:00+07:00")
    positions = np.flatnonzero((index >= start) & (index < restart))
    if not len(positions):
        return values
    progress = np.linspace(1.0 / len(positions), 1.0, len(positions))
    if signal_name == "radial_vibration_de":
        shutdown_values = 25.0 + (trip_value - 25.0) * np.exp(-7.0 * progress)
    elif signal_name == "water_in_oil":
        shutdown_values = restart_value + (trip_value - restart_value) * (1.0 - progress) ** 1.25
    elif signal_name == "lube_oil_pressure":
        shutdown_values = trip_value + (restart_value - trip_value) * np.sqrt(progress)
    else:
        shutdown_values = 70.0 + (trip_value - 70.0) * np.exp(-3.2 * progress)
    values[positions] = shutdown_values
    return values


def apply_minor_condition_events(
    index: pd.DatetimeIndex,
    values: np.ndarray,
    signal_name: str,
    config: dict[str, Any],
) -> np.ndarray:
    multipliers = {
        "radial_vibration_de": {"STARTUP_TRANSIENT": 1.045, "SHORT_LOAD_TRANSIENT": 1.025},
        "water_in_oil": {"STARTUP_TRANSIENT": 1.004, "SHORT_LOAD_TRANSIENT": 1.006},
        "lube_oil_pressure": {"STARTUP_TRANSIENT": 0.985, "SHORT_LOAD_TRANSIENT": 0.992},
        "bearing_metal_temperature": {"STARTUP_TRANSIENT": 1.018, "SHORT_LOAD_TRANSIENT": 1.012},
    }
    for event in config.get("minor_events", []):
        mask = (index >= pd.Timestamp(event["start"])) & (index < pd.Timestamp(event["end"]))
        values[mask] *= multipliers[signal_name][event["event_marker"]]
    return values


def load_source_process(root: Path) -> pd.DataFrame:
    path = root / "data/raw/ko_3201/production_data_ko_3201.xlsx"
    source = pd.read_excel(path, sheet_name="Sheet2")
    required = {"Timestamp", "RUN_STATUS", *PROCESS_COLUMNS}
    missing = required - set(source.columns)
    if missing:
        raise ValueError(f"Production source missing columns: {sorted(missing)}")
    timestamps = pd.to_datetime(source["Timestamp"], errors="raise")
    source.index = pd.DatetimeIndex(timestamps).tz_localize(SOURCE_TIMEZONE)
    if source.index.duplicated().any():
        raise ValueError("Production source contains duplicate timestamps")
    return source


def generate_process_context(
    index: pd.DatetimeIndex,
    source: pd.DataFrame,
    config: dict[str, Any],
) -> pd.DataFrame:
    rng = np.random.default_rng(int(config["random_seed"]) + 17)
    healthy = source.loc[
        (source.index < pd.Timestamp("2026-04-27T00:00:00+07:00"))
        & (source["RUN_STATUS"].astype(str).str.upper() == "ON")
    ]
    if healthy.empty:
        raise ValueError("No healthy April process profile is available")

    result = pd.DataFrame(index=index)
    common = ar1_noise(rng, len(index), phi=0.92)
    for source_column, output_column in PROCESS_COLUMNS.items():
        hourly_profile = healthy.groupby(healthy.index.hour)[source_column].median()
        base = np.array([hourly_profile.loc[hour] for hour in index.hour], dtype=float)
        standard_deviation = float(healthy[source_column].std())
        independent = ar1_noise(rng, len(index), phi=0.78)
        generated = base + standard_deviation * (0.22 * common + 0.08 * independent)
        lower = float(healthy[source_column].quantile(0.005))
        upper = float(healthy[source_column].quantile(0.995))
        result[output_column] = np.round(np.clip(generated, lower, upper), 4)

    result["run_status"] = "ON"
    apply_process_transients(result, config)

    for timestamp, row in source.iterrows():
        if timestamp not in result.index:
            raise ValueError(f"Source process timestamp outside scenario: {timestamp}")
        for source_column, output_column in PROCESS_COLUMNS.items():
            result.at[timestamp, output_column] = float(row[source_column])
        result.at[timestamp, "run_status"] = str(row["RUN_STATUS"]).strip().upper()
    return result


def apply_process_transients(frame: pd.DataFrame, config: dict[str, Any]) -> None:
    startup_factors = np.array([0.38, 0.60, 0.82, 0.96])
    for event in config.get("minor_events", []):
        mask = (frame.index >= pd.Timestamp(event["start"])) & (
            frame.index < pd.Timestamp(event["end"])
        )
        positions = np.flatnonzero(mask)
        if event["event_marker"] == "STARTUP_TRANSIENT":
            if len(positions) != len(startup_factors):
                raise ValueError("Startup event must span four hourly records")
            for column in ["feed_rate_tph", "motor_current_a", "plant_rate_tph"]:
                frame.iloc[positions, frame.columns.get_loc(column)] *= startup_factors
            frame.iloc[
                positions, frame.columns.get_loc("discharge_pressure_barg")
            ] *= 0.78 + 0.22 * startup_factors
            frame.iloc[
                positions, frame.columns.get_loc("pi_vibration_mm_s_as_reported")
            ] *= 1.04
        elif event["event_marker"] == "SHORT_LOAD_TRANSIENT":
            for column in ["feed_rate_tph", "motor_current_a", "plant_rate_tph"]:
                frame.loc[mask, column] *= 0.94


def surrounding_anchor_ids(
    timestamp: pd.Timestamp,
    anchors: list[Anchor],
) -> tuple[str, str]:
    times = [anchor.effective_timestamp for anchor in anchors]
    insertion = bisect_right(times, timestamp)
    if timestamp in times:
        exact_index = times.index(timestamp)
        return anchors[exact_index].observation_id, anchors[exact_index].observation_id
    before_index = min(max(insertion - 1, 0), len(anchors) - 1)
    after_index = min(max(insertion, 0), len(anchors) - 1)
    return anchors[before_index].observation_id, anchors[after_index].observation_id


def build_synthetic_definitions(
    definition_by_name: dict[str, dict[str, Any]],
    config: dict[str, Any],
) -> list[SignalDefinition]:
    definitions: list[SignalDefinition] = []
    for signal_name, settings in config["primary_signals"].items():
        source = definition_by_name[signal_name]
        definitions.append(
            SignalDefinition(
                signal_id=settings["signal_id"],
                asset_id=ASSET_ID,
                canonical_name=signal_name,
                source_name=CONDITION_COLUMNS[signal_name],
                description=f"Hourly scenario series anchored to {source['source_name']}",
                unit=settings["unit"],
                measurement_type=settings["measurement_type"],
                direction_of_concern=DirectionOfConcern(settings["direction_of_concern"]),
                typical_value=float(source["typical_value"]),
                alarm_limit=float(source["alarm_limit"]),
                trip_limit=float(source["trip_limit"]),
                source_key=config["scenario_id"],
                source_sheet="hourly_scenario",
                source_cadence="HOURLY",
                quality_status="APPROVED_SCENARIO_SERIES",
            )
        )
    return definitions


def build_condition_observations(
    index: pd.DatetimeIndex,
    conditions: pd.DataFrame,
    timeline: list[ScenarioTimelinePoint],
    definitions: list[SignalDefinition],
    anchors_by_signal: dict[str, list[Anchor]],
    config: dict[str, Any],
) -> list[SignalObservation]:
    definition_by_name = {definition.canonical_name: definition for definition in definitions}
    timeline_by_time = {pd.Timestamp(point.timestamp): point for point in timeline}
    records: list[SignalObservation] = []
    for row_number, timestamp in enumerate(index, start=1):
        point = timeline_by_time[timestamp]
        for signal_name, output_column in CONDITION_COLUMNS.items():
            definition = definition_by_name[signal_name]
            anchors = anchors_by_signal[signal_name]
            before_id, after_id = surrounding_anchor_ids(timestamp, anchors)
            exact_anchor = next(
                (anchor for anchor in anchors if anchor.effective_timestamp == timestamp),
                None,
            )
            source_type = point.condition_source_type
            source_reference = (
                exact_anchor.source_reference
                if exact_anchor is not None and exact_anchor.is_source_anchor
                else f"{config['scenario_id']}|anchors:{before_id}:{after_id}"
            )
            records.append(
                SignalObservation(
                    observation_id=(
                        f"scenario-hourly-{row_number:04d}-{definition.signal_id}"
                    ),
                    asset_id=ASSET_ID,
                    signal_id=definition.signal_id,
                    timestamp=timestamp.to_pydatetime(),
                    value=float(conditions.at[timestamp, output_column]),
                    operating_mode=point.operating_mode,
                    health_state=point.health_state,
                    source_type=source_type,
                    source_reference=source_reference,
                    source_cadence="HOURLY",
                    scenario_id=config["scenario_id"],
                    scenario_phase=point.scenario_phase,
                    anchor_before_observation_id=before_id,
                    anchor_after_observation_id=after_id,
                    generation_version=config["generation_version"],
                    quality_flag=QualityFlag.VALID,
                    timezone_assumption=SOURCE_TIMEZONE,
                    ingestion_version=config["generation_version"],
                    ingested_at=GENERATED_AT,
                )
            )
    return records


def build_anchor_audit(
    conditions: pd.DataFrame,
    anchors_by_signal: dict[str, list[Anchor]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for signal_name, anchors in anchors_by_signal.items():
        output_column = CONDITION_COLUMNS[signal_name]
        for anchor in anchors:
            if not anchor.is_source_anchor:
                continue
            generated = float(conditions.at[anchor.effective_timestamp, output_column])
            rows.append(
                {
                    "signal_name": signal_name,
                    "observation_id": anchor.observation_id,
                    "original_timestamp": anchor.original_timestamp.isoformat(),
                    "effective_timestamp": anchor.effective_timestamp.isoformat(),
                    "source_value": anchor.value,
                    "scenario_value": generated,
                    "absolute_error": abs(generated - anchor.value),
                    "source_reference": anchor.source_reference,
                }
            )
    return rows


def build_wide_rows(
    index: pd.DatetimeIndex,
    conditions: pd.DataFrame,
    process: pd.DataFrame,
    timeline: list[ScenarioTimelinePoint],
    anchors_by_signal: dict[str, list[Anchor]],
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    timeline_by_time = {pd.Timestamp(point.timestamp): point for point in timeline}
    source_anchor_ids: dict[pd.Timestamp, list[str]] = {}
    for anchors in anchors_by_signal.values():
        for anchor in anchors:
            if anchor.is_source_anchor:
                source_anchor_ids.setdefault(anchor.effective_timestamp, []).append(
                    anchor.observation_id
                )

    rows: list[dict[str, Any]] = []
    for timestamp in index:
        point = timeline_by_time[timestamp]
        row: dict[str, Any] = {
            "timestamp": timestamp.isoformat(),
            "scenario_id": config["scenario_id"],
            "scenario_phase": point.scenario_phase,
            "operating_mode": point.operating_mode,
            "health_state": point.health_state,
            "condition_source_type": point.condition_source_type,
            "process_source_type": point.process_source_type,
            "training_eligible": point.training_eligible,
            "event_marker": point.event_marker or "",
        }
        row.update(conditions.loc[timestamp].to_dict())
        row.update(process.loc[timestamp].to_dict())
        row["anchor_exact"] = timestamp in source_anchor_ids
        row["anchor_observation_ids"] = ";".join(source_anchor_ids.get(timestamp, []))
        rows.append(row)
    return rows


def build_event_rows(config: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "event_id": "evt-ko-3201-startup-transient",
            "event_type": "OPERATING_TRANSIENT",
            "started_at": "2026-01-05T08:00:00+07:00",
            "ended_at": "2026-01-05T12:00:00+07:00",
            "severity": "INFO",
            "incident_id": "",
            "description": "Short controlled startup signature used for mode-aware filtering.",
        },
        {
            "event_id": "evt-ko-3201-load-transient",
            "event_type": "OPERATING_TRANSIENT",
            "started_at": "2026-01-26T14:00:00+07:00",
            "ended_at": "2026-01-26T17:00:00+07:00",
            "severity": "INFO",
            "incident_id": "",
            "description": "Brief load change within the normal operating envelope.",
        },
        {
            "event_id": "evt-ko-3201-developing-failure",
            "event_type": "DEVELOPING_FAILURE",
            "started_at": "2026-02-11T00:00:00+07:00",
            "ended_at": "2026-04-29T07:00:00+07:00",
            "severity": "HIGH",
            "incident_id": "incident-0002",
            "description": "Correlated vibration, oil-water, pressure, and temperature degradation.",
        },
        {
            "event_id": "evt-ko-3201-trip",
            "event_type": "EQUIPMENT_TRIP",
            "started_at": "2026-04-29T07:00:00+07:00",
            "ended_at": "2026-04-30T15:00:00+07:00",
            "severity": "CRITICAL",
            "incident_id": "incident-0002",
            "description": "KO-3201 trip, shutdown, and corrective intervention window.",
        },
        {
            "event_id": "evt-ko-3201-recovery",
            "event_type": "POST_INTERVENTION_RECOVERY",
            "started_at": "2026-04-30T15:00:00+07:00",
            "ended_at": config["end_time_exclusive"],
            "severity": "INFO",
            "incident_id": "incident-0002",
            "description": "Restart and effectiveness-monitoring period after intervention.",
        },
    ]


def check_process_preservation(source: pd.DataFrame, process: pd.DataFrame) -> float:
    maximum_error = 0.0
    for timestamp, row in source.iterrows():
        for source_column, output_column in PROCESS_COLUMNS.items():
            maximum_error = max(
                maximum_error,
                abs(float(row[source_column]) - float(process.at[timestamp, output_column])),
            )
        if str(row["RUN_STATUS"]).strip().upper() != process.at[timestamp, "run_status"]:
            raise ValueError(f"RUN_STATUS changed at {timestamp}")
    return maximum_error


def build_manifest(config: dict[str, Any], timestamp_count: int) -> ScenarioManifest:
    return ScenarioManifest(
        scenario_id=config["scenario_id"],
        scenario_version=config["scenario_version"],
        generation_version=config["generation_version"],
        anchor_asset_id=ASSET_ID,
        anchor_dataset_version=config["anchor_dataset_version"],
        random_seed=int(config["random_seed"]),
        start_time=config["start_time"],
        end_time_exclusive=config["end_time_exclusive"],
        frequency=config["frequency"],
        timestamp_count=timestamp_count,
        primary_signals=list(config["primary_signals"]),
        process_context_signals=list(PROCESS_COLUMNS.values()) + ["run_status"],
        intended_use=[
            "dashboard_demo",
            "time_series_feature_engineering",
            "normal_baseline_training",
            "anomaly_detection_evaluation",
            "incident_to_rca_workflow_demo",
        ],
        training_policy=(
            "Train the initial normal-behavior model only where training_eligible is true; "
            "use all labeled phases for evaluation and product demonstration."
        ),
        source_type_policy=(
            "Weekly condition points and April process rows retain OBSERVED_ANCHOR lineage; "
            "generated intervals are classified by scenario phase."
        ),
    )


def validate_outputs(
    index: pd.DatetimeIndex,
    conditions: pd.DataFrame,
    process: pd.DataFrame,
    timeline: list[ScenarioTimelinePoint],
    anchor_audit: list[dict[str, Any]],
    source: pd.DataFrame,
    long_observations: list[SignalObservation],
    config: dict[str, Any],
) -> dict[str, Any]:
    process_error = check_process_preservation(source, process)
    checks = [
        ("hourly_timestamp_count", len(index) == 4368, len(index)),
        ("timestamp_uniqueness", index.is_unique, int(index.duplicated().sum())),
        ("condition_signal_completeness", not conditions.isna().any().any(), int(conditions.isna().sum().sum())),
        ("process_context_completeness", not process.isna().any().any(), int(process.isna().sum().sum())),
        ("weekly_anchor_count", len(anchor_audit) == 104, len(anchor_audit)),
        (
            "weekly_anchor_exactness",
            max(row["absolute_error"] for row in anchor_audit) <= 1e-9,
            max(row["absolute_error"] for row in anchor_audit),
        ),
        ("april_source_row_count", len(source) == 720, len(source)),
        ("april_process_exactness", process_error <= 1e-9, process_error),
        (
            "source_offline_hours",
            int((source["RUN_STATUS"].astype(str).str.upper() == "OFF").sum()) == 32,
            int((source["RUN_STATUS"].astype(str).str.upper() == "OFF").sum()),
        ),
        ("timeline_count", len(timeline) == 4368, len(timeline)),
        ("long_observation_count", len(long_observations) == 17472, len(long_observations)),
    ]
    for signal_name, output_column in CONDITION_COLUMNS.items():
        settings = config["primary_signals"][signal_name]
        in_bounds = conditions[output_column].between(
            float(settings["hard_min"]), float(settings["hard_max"]), inclusive="both"
        ).all()
        checks.append((f"{signal_name}_within_configured_bounds", bool(in_bounds), {
            "min": float(conditions[output_column].min()),
            "max": float(conditions[output_column].max()),
        }))

    failed = [name for name, passed, _ in checks if not passed]
    if failed:
        raise RuntimeError("Scenario validation failed: " + ", ".join(failed))
    phase_counts: dict[str, int] = {}
    source_type_counts: dict[str, int] = {}
    for point in timeline:
        phase_counts[str(point.scenario_phase)] = phase_counts.get(str(point.scenario_phase), 0) + 1
        source_type_counts[str(point.condition_source_type)] = (
            source_type_counts.get(str(point.condition_source_type), 0) + 1
        )
    return {
        "status": "PASS",
        "scenario_id": config["scenario_id"],
        "generation_version": config["generation_version"],
        "summary": {
            "hourly_rows": len(index),
            "condition_observations": len(long_observations),
            "source_weekly_anchor_values": len(anchor_audit),
            "source_april_process_rows": len(source),
            "training_eligible_hours": sum(point.training_eligible for point in timeline),
            "phase_counts": phase_counts,
            "condition_source_type_counts": source_type_counts,
        },
        "checks": [
            {"name": name, "status": "PASS" if passed else "FAIL", "actual": actual}
            for name, passed, actual in checks
        ],
    }


def run(root: Path, canonical: Path | None = None, output: Path | None = None) -> dict[str, Any]:
    root = root.resolve()
    canonical = (canonical or root / "data/normalized/ko_3201").resolve()
    output = (output or root / "data/synthetic/ko_3201/v1").resolve()
    require_valid_canonical(canonical)
    config = load_config(root)
    index = timestamp_index(config)
    source_process = load_source_process(root)
    anchors_by_signal, definition_by_name = load_weekly_anchors(canonical, config)
    source_anchor_timestamps = {
        anchor.effective_timestamp
        for anchors in anchors_by_signal.values()
        for anchor in anchors
        if anchor.is_source_anchor
    }
    timeline = build_timeline(
        index,
        config,
        set(source_process.index),
        source_anchor_timestamps,
    )
    conditions = interpolate_conditions(index, anchors_by_signal, config)
    process = generate_process_context(index, source_process, config)
    definitions = build_synthetic_definitions(definition_by_name, config)
    observations = build_condition_observations(
        index,
        conditions,
        timeline,
        definitions,
        anchors_by_signal,
        config,
    )
    anchor_audit = build_anchor_audit(conditions, anchors_by_signal)
    wide_rows = build_wide_rows(
        index, conditions, process, timeline, anchors_by_signal, config
    )
    events = build_event_rows(config)
    manifest = build_manifest(config, len(index))
    report = validate_outputs(
        index,
        conditions,
        process,
        timeline,
        anchor_audit,
        source_process,
        observations,
        config,
    )

    write_rows(output / "hourly_scenario.csv", wide_rows)
    write_models(output / "signal_definitions.csv", definitions)
    write_models(output / "signal_observations.csv", observations)
    write_models(output / "timeline.csv", timeline)
    write_rows(output / "weekly_anchor_check.csv", anchor_audit)
    write_rows(output / "events.csv", events)
    write_json(output / "scenario_manifest.json", manifest.model_dump(mode="json"))
    write_json(output / "generation_report.json", report)

    report["output_files"] = {
        path.name: {"bytes": path.stat().st_size, "sha256": sha256_file(path)}
        for path in sorted(output.iterdir())
        if path.is_file() and path.name != "generation_report.json"
    }
    write_json(output / "generation_report.json", report)
    return report


def main() -> None:
    args = parse_args()
    report = run(args.root, args.canonical, args.output)
    summary = report["summary"]
    print(
        "KO-3201 scenario generated: "
        f"{summary['hourly_rows']:,} hours, "
        f"{summary['condition_observations']:,} condition observations, "
        f"{summary['training_eligible_hours']:,} training-eligible hours."
    )


if __name__ == "__main__":
    main()
