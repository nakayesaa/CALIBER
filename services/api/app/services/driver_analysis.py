"""Build an interpretable condition-signal decomposition for an alert."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from services.api.app.schemas.alerts import AlertEvent
from services.api.app.schemas.driver_analysis import DriverAnalysis, SignalContribution
from services.api.app.schemas.features import (
    ConditionSignalConfig,
    ConcernDirection,
    FeaturePipelineConfig,
)


class DriverAnalysisService:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def for_alert(
        self,
        alert: AlertEvent,
        requested_at: datetime | None = None,
    ) -> DriverAnalysis:
        scenario = self._read_csv("data/synthetic/ko_3201/v1/hourly_scenario.csv")
        scores = self._read_csv("data/scored/ko_3201/v1/hourly_anomaly_scores.csv")
        config = self._load_config()
        scenario["timestamp"] = pd.to_datetime(scenario["timestamp"], errors="raise")
        scores["timestamp"] = pd.to_datetime(scores["timestamp"], errors="raise")
        requested_time = pd.Timestamp(requested_at or alert.peak_score_at)
        if requested_time.tzinfo is None:
            raise ValueError("Driver analysis timestamp must include a timezone")
        eligible_scores = scores.loc[
            scores["timestamp"].le(requested_time)
            & scores["score_status"].eq("SCORED")
        ]
        if eligible_scores.empty:
            raise ValueError(
                f"No scored evidence is available by {requested_time.isoformat()}"
            )
        evidence_time = pd.Timestamp(eligible_scores.iloc[-1]["timestamp"])
        evidence_scenario = self._single_row(scenario, evidence_time, "scenario")
        evidence_score = eligible_scores.iloc[-1]
        baseline_rows = scenario.loc[
            scenario["scenario_phase"].eq("HEALTHY_BASELINE")
            & scenario["operating_mode"].eq("RUNNING_STEADY")
            & scenario["run_status"].eq("ON")
        ]
        if baseline_rows.empty:
            raise ValueError("Driver analysis requires a healthy operating baseline")

        alert_window = scenario.loc[
            scenario["timestamp"].between(
                pd.Timestamp(alert.first_signal_at), evidence_time, inclusive="both"
            )
        ]
        first_alarms = {
            signal_key: self._first_alarm(alert_window, signal)
            for signal_key, signal in config.condition_signals.items()
        }
        chronology = {
            signal_key: rank
            for rank, (signal_key, timestamp) in enumerate(
                sorted(
                    (
                        (signal_key, timestamp)
                        for signal_key, timestamp in first_alarms.items()
                        if timestamp is not None
                    ),
                    key=lambda item: item[1],
                ),
                start=1,
            )
        }

        contributions = [
            self._signal_contribution(
                signal_key,
                signal,
                evidence_scenario,
                evidence_score,
                baseline_rows,
                alert_window,
                first_alarms[signal_key],
                chronology.get(signal_key),
            )
            for signal_key, signal in config.condition_signals.items()
        ]
        contributions.sort(key=lambda item: item.contribution_percent, reverse=True)
        return DriverAnalysis(
            alert_id=alert.alert_id,
            asset_id=alert.asset_id,
            model_id=alert.model_id,
            as_of=evidence_time.to_pydatetime(),
            anomaly_score=float(evidence_score["anomaly_score"]),
            method="GROUPED_COUNTERFACTUAL_BASELINE_REPLACEMENT",
            interpretation=(
                "Contribution estimates how much the raw model anomaly decreases "
                "when one signal group is restored to its healthy baseline. It "
                "explains the model decision and does not establish physical causality."
            ),
            contributions=contributions,
        )

    def _signal_contribution(
        self,
        signal_key: str,
        signal: ConditionSignalConfig,
        evidence_scenario: pd.Series,
        evidence_score: pd.Series,
        baseline_rows: pd.DataFrame,
        alert_window: pd.DataFrame,
        first_alarm: pd.Timestamp | None,
        chronology_rank: int | None,
    ) -> SignalContribution:
        source_field = signal.source_column
        value = float(evidence_scenario[source_field])
        contribution_column = f"contribution_pct__condition__{signal_key}"
        impact_column = f"model_impact__condition__{signal_key}"
        missing = {
            column
            for column in (contribution_column, impact_column)
            if column not in evidence_score.index
        }
        if missing:
            raise ValueError(
                "Model scores do not contain counterfactual contributions. "
                "Run make train. Missing: " + ", ".join(sorted(missing))
            )
        recent = alert_window.tail(24)[source_field].astype(float)
        return SignalContribution(
            driver_name=f"condition.{signal_key}",
            signal_key=signal_key,
            source_field=source_field,
            unit=signal.unit,
            direction_of_concern=signal.direction_of_concern,
            value=value,
            healthy_baseline=float(baseline_rows[source_field].median()),
            alarm_limit=signal.alarm_limit,
            trip_limit=signal.trip_limit,
            engineering_state=self._engineering_state(value, signal),
            trend=self._trend(recent),
            first_alarm_at=first_alarm.to_pydatetime() if first_alarm is not None else None,
            alarm_persistence_hours=self._persistence(alert_window[source_field], signal),
            chronology_rank=chronology_rank,
            raw_model_impact=float(evidence_score[impact_column]),
            contribution_percent=float(evidence_score[contribution_column]),
        )

    @staticmethod
    def _concern_mask(
        values: pd.Series,
        signal: ConditionSignalConfig,
    ) -> pd.Series:
        numeric = values.astype(float)
        if signal.direction_of_concern == ConcernDirection.HIGH:
            return numeric.ge(signal.alarm_limit)
        return numeric.le(signal.alarm_limit)

    def _first_alarm(
        self,
        frame: pd.DataFrame,
        signal: ConditionSignalConfig,
    ) -> pd.Timestamp | None:
        breached = frame.loc[self._concern_mask(frame[signal.source_column], signal)]
        return None if breached.empty else pd.Timestamp(breached.iloc[0]["timestamp"])

    def _persistence(
        self,
        values: pd.Series,
        signal: ConditionSignalConfig,
    ) -> int:
        breached = self._concern_mask(values, signal).to_numpy(dtype=bool)
        if not len(breached) or not breached[-1]:
            return 0
        return int(np.argmax(~breached[::-1])) if (~breached[::-1]).any() else len(breached)

    @staticmethod
    def _engineering_state(
        value: float,
        signal: ConditionSignalConfig,
    ) -> str:
        if signal.direction_of_concern == ConcernDirection.HIGH:
            return "TRIP" if value >= signal.trip_limit else "ALARM" if value >= signal.alarm_limit else "NORMAL"
        return "TRIP" if value <= signal.trip_limit else "ALARM" if value <= signal.alarm_limit else "NORMAL"

    @staticmethod
    def _trend(values: pd.Series) -> str:
        if len(values) < 2:
            return "STABLE"
        numeric = values.to_numpy(dtype=float)
        slope = float(np.polyfit(np.arange(len(numeric)), numeric, 1)[0])
        tolerance = max(float(np.median(np.abs(numeric))), 1.0) * 1e-6
        return "RISING" if slope > tolerance else "FALLING" if slope < -tolerance else "STABLE"

    def _load_config(self) -> FeaturePipelineConfig:
        path = self.root / "data/catalog/ko_3201_feature_config.yaml"
        return FeaturePipelineConfig.model_validate(
            yaml.safe_load(path.read_text(encoding="utf-8"))
        )

    def _read_csv(self, relative_path: str) -> pd.DataFrame:
        path = self.root / relative_path
        if not path.is_file():
            raise FileNotFoundError(f"Required artifact not found: {path}")
        return pd.read_csv(path)

    @staticmethod
    def _single_row(frame: pd.DataFrame, timestamp: pd.Timestamp, label: str) -> pd.Series:
        matching = frame.loc[frame["timestamp"].eq(timestamp)]
        if len(matching) != 1:
            raise ValueError(f"Expected one {label} row at {timestamp.isoformat()}")
        return matching.iloc[0]
