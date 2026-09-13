import { useEffect, useMemo, useState } from 'react';

import type { AlertEvent, AlertStateTransition, TelemetryPoint } from '../lib/api';
import { conditionSignals } from '../lib/conditionSignals';
import { buildEventMilestones } from '../lib/eventProgression';
import { formatDateTime, formatSignal, humanize } from '../lib/format';
import { SignalChart, type SignalField } from './SignalChart';

interface EventProgressionExplorerProps {
  assetTag: string;
  alert: AlertEvent;
  transitions: AlertStateTransition[];
  telemetry: TelemetryPoint[];
  initialSelection: number | null;
  onClose: () => void;
}

export function EventProgressionExplorer({ assetTag, alert, transitions, telemetry, initialSelection, onClose }: EventProgressionExplorerProps) {
  const milestones = useMemo(
    () => buildEventMilestones(alert, transitions, telemetry),
    [alert, transitions, telemetry],
  );
  const [selectedIndex, setSelectedIndex] = useState<number | null>(() => normalizeIndex(initialSelection, milestones.length));
  const [selectedSignal, setSelectedSignal] = useState<SignalField>('anomaly_score');
  const selected = selectedIndex === null ? undefined : milestones[selectedIndex];
  const chartPoints = useMemo(
    () => selected ? telemetryAround(telemetry, selected.timestamp) : [],
    [selected, telemetry],
  );

  useEffect(() => {
    setSelectedIndex(normalizeIndex(initialSelection, milestones.length));
  }, [initialSelection, milestones.length]);

  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', closeOnEscape);
    return () => window.removeEventListener('keydown', closeOnEscape);
  }, [onClose]);

  const snapshot = selected?.snapshot;
  const expanded = Boolean(selected);

  return <aside className={`overview-progression-explorer${expanded ? ' expanded' : ''}`} aria-label={`${assetTag} event progression explorer`}>
    <header>
      <div><span>Event explorer</span><h2>{assetTag} progression</h2><p>{expanded ? 'Reviewing the evidence available at the selected hour.' : 'Select a milestone to inspect its equipment evidence.'}</p></div>
      <button className="overview-modal-close" onClick={onClose} aria-label="Close event progression">×</button>
    </header>
    <div className={`overview-explorer-body${expanded ? ' expanded' : ''}`}>
      {selected && <section className="overview-explorer-detail" aria-live="polite">
        <header>
          <button onClick={() => setSelectedIndex(null)}>Hide detail</button>
          <div><span className={selected.tone}>{selected.label}</span><time>{formatDateTime(selected.timestamp)}</time></div>
          <h3>{selected.title}</h3>
          <p>{selected.description}</p>
        </header>

        <section className="overview-event-chart">
          <header><div><h4>Evidence around this event</h4><span>Seven days before and after</span></div><strong>{chartLabel(selectedSignal)}</strong></header>
          <nav aria-label="Event chart signal">
            {chartSignals.map((signal) => <button className={selectedSignal === signal.field ? 'active' : ''} key={signal.field} onClick={() => setSelectedSignal(signal.field)}>{signal.label}</button>)}
          </nav>
          <div><SignalChart points={chartPoints} field={selectedSignal} threshold={selectedSignal === 'anomaly_score' ? 50 : undefined} highlightTimestamp={selected.timestamp}/></div>
          <footer><span>{formatDateTime(chartPoints[0]?.timestamp ?? selected.timestamp)}</span><b>Selected event</b><span>{formatDateTime(chartPoints.at(-1)?.timestamp ?? selected.timestamp)}</span></footer>
        </section>

        <section className="overview-snapshot-section">
          <div className="overview-snapshot-heading"><h4>Current condition</h4><span>Hourly snapshot</span></div>
          <div className="overview-snapshot-grid">
            {conditionSignals.map((signal) => <div key={signal.field}><span>{signal.label}</span><strong>{formatReading(snapshot?.[signal.field])} <small>{signal.unit}</small></strong></div>)}
          </div>
        </section>
        <section className="overview-evidence-strip">
          <div><span>Anomaly score</span><strong>{snapshot?.anomaly_score == null ? 'Not scored' : formatSignal(snapshot.anomaly_score)}</strong></div>
          <div><span>Decision state</span><strong>{humanize(snapshot?.decision_state ?? selected.state)}</strong></div>
          <div><span>Signals breached</span><strong>{snapshot?.breached_signals.length ?? 0}</strong></div>
        </section>
        <section className="overview-event-analysis">
          <header><span>Analysis at this point</span><b>Evidence-based indication</b></header>
          <h4>{selected.synthesis.title}</h4>
          <p>{selected.synthesis.detail}</p>
          <footer><span>Derived from</span><b>Hourly telemetry and alert decision state</b></footer>
        </section>
      </section>}

      <nav className="overview-explorer-events" aria-label="Alert milestones">
        <div><span>{milestones.length} milestones</span><b>{formatSignal(alert.duration_hours / 24)} days</b></div>
        {milestones.map((milestone, index) => <button className={selectedIndex === index ? 'active' : ''} key={milestone.id} onClick={() => setSelectedIndex(index)}>
          <i className={milestone.tone}/><span><time>{formatDateTime(milestone.timestamp)}</time><strong>{milestone.title}</strong></span><b className={milestone.tone}>{milestone.label}</b>
        </button>)}
      </nav>
    </div>
  </aside>;
}

const chartSignals: Array<{ field: SignalField; label: string }> = [
  { field: 'anomaly_score', label: 'Risk score' },
  ...conditionSignals.map(({ field, label }) => ({ field, label })),
];

function normalizeIndex(index: number | null, length: number): number | null {
  return index === null ? null : Math.max(0, Math.min(index, length - 1));
}

function formatReading(value: number | undefined): string {
  return value === undefined ? 'Unavailable' : formatSignal(value);
}

function telemetryAround(points: TelemetryPoint[], timestamp: string): TelemetryPoint[] {
  const center = new Date(timestamp).getTime();
  const radius = 7 * 24 * 60 * 60 * 1000;
  return points.filter((point) => Math.abs(new Date(point.timestamp).getTime() - center) <= radius);
}

function chartLabel(field: SignalField): string {
  if (field === 'anomaly_score') return 'Risk score';
  return conditionSignals.find((signal) => signal.field === field)?.label ?? field;
}
