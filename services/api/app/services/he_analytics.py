"""Read a checksum-bound HE analytics snapshot, never mixed candidate artifacts."""

import json
from pathlib import Path

import numpy as np
import pandas as pd

from services.api.app.schemas.alerts import AlertEvent, AlertStateTransition
from services.api.app.schemas.equipment import (
    EquipmentHourlyAnalytics,
    EquipmentHourlyAssessment,
    EquipmentInvestigation,
    EquipmentModelRecovery,
    EquipmentPoint,
)
from services.api.app.services.file_io import file_sha256


def active_snapshot(root: Path) -> Path | None:
    pointer = root / "data/alerts/he_3301/active.json"
    if not pointer.is_file():
        return None
    active = json.loads(pointer.read_text())
    bundles = (root / "data/alerts/he_3301/bundles").resolve()
    directory = (bundles / active["version"]).resolve()
    if directory.parent != bundles:
        raise ValueError("Invalid HE analytics version")
    if file_sha256(directory / "manifest.json") != active["manifest_sha256"]:
        raise ValueError("HE analytics manifest changed; rebuild with make he-alerts")
    manifest = validate_snapshot(directory)
    if file_sha256(root / "data/normalized/he_3301/equipment.json") != manifest["canonical_sha256"]:
        raise ValueError("HE analytics source changed; rebuild with make he-train")
    return directory


def validate_snapshot(directory: Path) -> dict:
    manifest = json.loads((directory / "manifest.json").read_text())
    for name, checksum in manifest["files"].items():
        path = directory / name
        if Path(name).name != name or path.resolve().parent != directory.resolve() or file_sha256(path) != checksum:
            raise ValueError(f"HE analytics artifact changed: {name}")
    return manifest


def snapshot_alerts(directory: Path) -> list[AlertEvent]:
    validate_snapshot(directory)
    payload = json.loads((directory / "events.json").read_text())
    return [AlertEvent.model_validate(item) for item in payload["events"]]


def hourly_analytics(root: Path, bundle: EquipmentInvestigation) -> EquipmentHourlyAnalytics | None:
    directory = active_snapshot(root)
    if directory is None:
        return None
    manifest = json.loads((directory / "manifest.json").read_text())
    evaluation = json.loads((directory / "evaluation_report.json").read_text())
    scenario = pd.read_csv(directory / "hourly_scenario.csv")
    scores = pd.read_csv(directory / "hourly_anomaly_scores.csv")
    decisions = pd.read_csv(directory / "hourly_alert_decisions.csv")
    for table in [scenario, scores, decisions]:
        table["timestamp"] = pd.to_datetime(table.timestamp, errors="raise")
    thresholds = scores.anomaly_threshold.dropna().unique()
    if len(thresholds) != 1:
        raise ValueError("HE scoring threshold must be consistent within a model version")
    timeline = scenario.merge(
        scores[["timestamp", "anomaly_score"]], on="timestamp", validate="one_to_one"
    )
    timeline = timeline.merge(
        decisions[["timestamp", "decision_state", "decision_reason", "breached_signals"]],
        on="timestamp",
        validate="one_to_one",
    )
    if len(timeline) != manifest["row_count"]:
        raise ValueError("Incomplete HE analytics timeline")
    signals = []
    for signal in bundle.signals:
        if signal.direction is None:
            continue
        hourly = signal.model_copy(
            update={
                "cadence": "HOURLY",
                "points": [
                    EquipmentPoint(
                        timestamp=row.timestamp,
                        value=getattr(row, signal.key),
                        source_reference=(
                            f"Reconstructed hour · {getattr(row, f'{signal.key}_previous_anchor', 'weekly anchor')} → "
                            f"{getattr(row, f'{signal.key}_following_anchor', 'weekly anchor')} · snapshot {manifest['version']}"
                        ),
                    )
                    for row in scenario.itertuples(index=False)
                ],
            }
        )
        signals.append(hourly)
    assessments = [
        EquipmentHourlyAssessment(
            timestamp=row.timestamp,
            state=row.decision_state,
            score=float(row.anomaly_score) if np.isfinite(row.anomaly_score) else None,
            breached_signals=[]
            if pd.isna(row.breached_signals)
            else str(row.breached_signals).split(";"),
            reason=row.decision_reason,
            source_status="SCENARIO_MODEL",
        )
        for row in timeline.itertuples(index=False)
    ]
    transitions = [
        AlertStateTransition.model_validate(item)
        for item in json.loads((directory / "events.json").read_text())["transitions"]
    ]
    alerts = snapshot_alerts(directory)
    if not alerts:
        raise ValueError("Promoted HE analytics has no investigation event")
    alert = max(alerts, key=lambda item: (item.highest_severity_rank, item.peak_anomaly_score))
    transitions = [item for item in transitions if item.alert_id == alert.alert_id]
    recovery_rows = timeline.loc[
        timeline.scenario_phase.isin(["POST_REPAIR_MONITORING", "STABLE_RECOVERY"])
    ]
    eligible = recovery_rows.anomaly_score.notna()
    anomalous = eligible & recovery_rows.anomaly_score.ge(float(thresholds[0]))
    return EquipmentHourlyAnalytics(
        version=manifest["version"],
        model_id=manifest["model_id"],
        signals=signals,
        assessments=assessments,
        transitions=transitions,
        alert=alert,
        recovery=EquipmentModelRecovery(
            eligible_hours=int(eligible.sum()),
            anomalous_hours=int(anomalous.sum()),
            anomaly_rate=float(anomalous.sum() / max(eligible.sum(), 1)),
        ),
        validation_note=(
            f"Retrospective replay · healthy holdout {evaluation['healthy_exceedance']:.1%}; "
            f"terminal normal block {evaluation['terminal_healthy_exceedance']:.1%}. "
            "WATCH novelty alone cannot open an investigation. "
            f"Forward-only reference: {evaluation.get('forward_reference', {}).get('status', 'not recorded')}."
        ),
    )
