#!/usr/bin/env python3
"""Reconstruct HE condition hours around dated weekly anchors and source intervention."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_ko_3201_features import write_frame
from services.api.app.schemas.equipment import EquipmentInvestigation
from services.api.app.services.file_io import atomic_write_json, file_sha256


def reconstruct(
    bundle: EquipmentInvestigation, config: dict[str, Any], noise_scale: float = 1.0
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    dates = pd.date_range(config["start"], config["end_exclusive"], freq="h", inclusive="left")
    restart = pd.Timestamp(config["restart"])
    isolation = pd.Timestamp(config["isolation"])
    healthy_end = pd.Timestamp(config["healthy_cutoff"])
    if not 0 <= noise_scale <= 2:
        raise ValueError("Noise sensitivity scale must be between zero and two")
    rng = np.random.default_rng(config["seed"])
    frame = pd.DataFrame({"timestamp": dates})
    audit: list[dict[str, Any]] = []
    timestamps_ns = dates.as_unit("ns").asi8
    x = timestamps_ns.astype(float)
    for signal in bundle.signals:
        if signal.cadence != "WEEKLY":
            continue
        before = [point for point in signal.points if point.timestamp < restart]
        after = [point for point in signal.points if point.timestamp >= restart]
        if not before or not after:
            raise ValueError("Condition reconstruction requires anchors on both sides of repair")
        values = np.empty(len(dates))
        for mask, points in [(dates < restart, before), (dates >= restart, after)]:
            values[mask] = np.interp(
                x[mask],
                np.array([pd.Timestamp(point.timestamp).value for point in points], dtype=float),
                np.array([point.value for point in points]),
            )
        # Noise is independent by variable, bounded, and restarted at intervention.
        noise = np.zeros(len(dates))
        correlation = config["noise_correlation"]
        anchor_times = {pd.Timestamp(point.timestamp) for point in signal.points}
        previous = 0.0
        for index, stamp in enumerate(dates):
            if stamp in anchor_times or stamp == restart:
                previous = 0.0
            else:
                previous = correlation * previous + (1 - correlation) * rng.uniform(-1, 1)
            noise[index] = previous
        amplitude = config["noise_amplitude"][signal.key] * noise_scale
        shifted = values + noise * amplitude
        # Noise must not manufacture an alarm/trip crossing absent from the base path.
        for limit in [signal.alarm_limit, signal.trip_limit]:
            if limit is not None:
                shifted = np.where(
                    values < limit, np.minimum(shifted, np.nextafter(limit, -np.inf)), shifted
                )
                shifted = np.where(
                    values > limit, np.maximum(shifted, np.nextafter(limit, np.inf)), shifted
                )
                shifted = np.where(values == limit, values, shifted)
        frame[signal.key] = shifted
        for point in signal.points:
            mask = dates == pd.Timestamp(point.timestamp)
            if mask.sum() != 1:
                raise ValueError("Every weekly anchor must occur once within the scenario horizon")
            frame.loc[mask, signal.key] = point.value
            audit.append(
                {
                    "signal": signal.key,
                    "timestamp": point.timestamp.isoformat(),
                    "source_value": point.value,
                    "scenario_value": float(frame.loc[mask, signal.key].iloc[0]),
                    "source_reference": point.source_reference,
                    "date_precision": "DATE_ONLY",
                    "anchor_convention": "00:00 Asia/Jakarta dated point, not weekly mean",
                }
            )
        # The map is retrospective reconstruction provenance, never a model feature.
        stamp_values = np.array([pd.Timestamp(point.timestamp).value for point in signal.points])
        previous_indices = np.maximum(
            np.searchsorted(stamp_values, timestamps_ns, side="right") - 1, 0
        )
        following_indices = np.minimum(
            np.searchsorted(stamp_values, timestamps_ns, side="left"), len(stamp_values) - 1
        )
        frame[f"{signal.key}_previous_anchor"] = [
            signal.points[index].source_reference for index in previous_indices
        ]
        frame[f"{signal.key}_following_anchor"] = [
            signal.points[index].source_reference for index in following_indices
        ]
    operating = {pd.Timestamp(point.timestamp): point.state for point in bundle.operating_states}
    frame["run_status"] = [operating.get(stamp, "ON") for stamp in dates]
    frame["operating_mode"] = np.where(frame.run_status.eq("OFF"), "SHUTDOWN", "RUNNING_STEADY")
    settling = (
        (dates >= restart) & (dates < restart + pd.Timedelta(hours=config["warmup_hours"]))
    ) | (dates < dates[0] + pd.Timedelta(hours=config["warmup_hours"]))
    frame.loc[settling, "operating_mode"] = "RESTART_SETTLING"
    frame["scenario_phase"] = np.select(
        [dates < healthy_end, frame.run_status.eq("OFF"), settling, dates < restart],
        ["HEALTHY_BASELINE", "MAINTENANCE", "RESTART_SETTLING", "EARLY_DEGRADATION"],
        default="STABLE_RECOVERY",
    )
    frame["training_eligible"] = (dates < healthy_end) & frame.operating_mode.eq("RUNNING_STEADY")
    frame["scenario_id"] = config["scenario_id"]
    anchors = {
        pd.Timestamp(point.timestamp)
        for signal in bundle.signals
        if signal.cadence == "WEEKLY"
        for point in signal.points
    }
    frame["condition_source_type"] = [
        "WEEKLY_ANCHOR" if stamp in anchors else "ANCHORED_HOURLY_SCENARIO" for stamp in dates
    ]
    frame["process_source_type"] = [
        "SOURCE_HOURLY" if stamp in operating else "NO_OPERATING_OBSERVATION" for stamp in dates
    ]
    frame["health_state"] = "NORMAL"
    for signal in bundle.signals:
        if signal.cadence != "WEEKLY":
            continue
        raw = frame[signal.key]
        alarm = (
            raw >= signal.alarm_limit if signal.direction == "HIGH" else raw <= signal.alarm_limit
        )
        trip = raw >= signal.trip_limit if signal.direction == "HIGH" else raw <= signal.trip_limit
        frame.loc[alarm & frame.health_state.eq("NORMAL"), "health_state"] = "ALARM"
        frame.loc[trip, "health_state"] = "TRIP"
    frame["event_marker"] = ""
    frame.loc[dates == isolation, "event_marker"] = "SOURCE_ISOLATION"
    frame.loc[dates == restart, "event_marker"] = "SOURCE_ON_RESTART"
    return frame, audit


def run(root: Path = ROOT, output: Path | None = None) -> dict[str, Any]:
    source = root / "data/normalized/he_3301/equipment.json"
    config_path = root / "data/catalog/he_3301_scenario_config.yaml"
    config = yaml.safe_load(config_path.read_text())
    source_catalog = yaml.safe_load((root / "data/catalog/he_3301_sources.yaml").read_text())
    for entry in source_catalog["sources"]:
        raw_path = root / entry["local_path"]
        if raw_path.exists() and file_sha256(raw_path) != entry["sha256"]:
            raise ValueError(f"Source checksum mismatch: {entry['source_key']}")
    bundle = EquipmentInvestigation.model_validate_json(source.read_text())
    frame, audit = reconstruct(bundle, config)
    output = output or root / "data/synthetic/he_3301/v1"
    output.mkdir(parents=True, exist_ok=True)
    signals = [signal.key for signal in bundle.signals if signal.cadence == "WEEKLY"]
    checks = {
        "timestamp_count": len(frame) == 4368,
        "anchors_preserved": len(audit) == 104
        and all(row["source_value"] == row["scenario_value"] for row in audit),
        "finite_positive_values": bool(
            np.isfinite(frame[signals]).all().all() and (frame[signals] > 0).all().all()
        ),
        "observed_operation_count": int(frame.process_source_type.eq("SOURCE_HOURLY").sum()) == 720,
    }
    if not all(checks.values()):
        raise ValueError(f"Scenario validation failed: {checks}")
    write_frame(output / "hourly_scenario.csv", frame)
    context = [
        {
            "timestamp": point.timestamp.isoformat(),
            "signal": signal.key,
            "value": point.value,
            "source_reference": point.source_reference,
        }
        for signal in bundle.signals
        if signal.cadence == "HOURLY"
        for point in signal.points
    ]
    write_frame(output / "operating_context.csv", pd.DataFrame(context))
    write_frame(output / "anchor_audit.csv", pd.DataFrame(audit))
    challenges = output / "challenges"
    challenges.mkdir(exist_ok=True)
    brief = frame.copy()
    pulse = (brief.timestamp >= pd.Timestamp("2026-01-14T12:00:00+07:00")) & (
        brief.timestamp < pd.Timestamp("2026-01-14T14:00:00+07:00")
    )
    for key, change in {
        "tube_dp": 0.1,
        "heat_duty": -6,
        "cold_outlet_temp": -4,
        "heavy_ends": 0.2,
    }.items():
        brief.loc[pulse, key] += change
    brief.loc[pulse, "event_marker"] = "CHALLENGE_BRIEF_TRANSIENT"
    write_frame(challenges / "brief_transient.csv", brief)
    for scale in [0.0, 2.0]:
        variant, _ = reconstruct(bundle, config, noise_scale=scale)
        write_frame(challenges / f"noise_{scale:g}.csv", variant)
    write_frame(challenges / "healthy.csv", frame.loc[frame.scenario_phase.eq("HEALTHY_BASELINE")])
    write_frame(
        challenges / "persistent_degradation.csv",
        frame.loc[frame.scenario_phase.eq("EARLY_DEGRADATION")],
    )
    manifest = {
        "scenario_id": config["scenario_id"],
        "timestamp_count": len(frame),
        "phase_count": int(frame.scenario_phase.nunique()),
        "source_sha256": file_sha256(source),
        "config_sha256": file_sha256(config_path),
        "healthy_cutoff": config["healthy_cutoff"],
        "restart": config["restart"],
        "warmup_hours": config["warmup_hours"],
        "method": "Piecewise linear dated anchors; separate repair segments; bounded independent AR noise; terminal anchor hold",
        "healthy_basis": "Pre-Feb26 low-limit envelope before sharp rise; mild February drift retained, not assumed stationary",
        "repair_basis": "Source ON May21 22:00; first later weekly recovery anchor supplies reconstructed post-cleaning level, not an observed restart measurement",
        "tail_basis": "Jun25 anchor held for final interval with bounded variation and no added failure",
        "quality_issues": bundle.quality_issues,
        "noise_amplitude": config["noise_amplitude"],
        "source_checksums": {
            entry["source_key"]: entry["sha256"] for entry in source_catalog["sources"]
        },
        "seed": config["seed"],
    }
    atomic_write_json(output / "scenario_manifest.json", manifest)
    atomic_write_json(output / "scenario_quality_report.json", {"status": "PASS", "checks": checks})
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    print(json.dumps(run(args.root, args.output), indent=2))
