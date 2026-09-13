import { useEffect, useMemo, useState } from 'react';

import type { AlertEvent, AlertStateTransition, TelemetryPoint } from '../lib/api';
import { conditionSignals } from '../lib/conditionSignals';
import { buildEventMilestones } from '../lib/eventProgression';
import { formatDateTime, formatSignal, humanize } from '../lib/format';

interface EventProgressionExplorerProps {
  assetTag: string;
  alert: AlertEvent;
  transitions: AlertStateTransition[];
  telemetry: TelemetryPoint[];
  initialSelection: number;
  onClose: () => void;
}

export function EventProgressionExplorer({ assetTag, alert, transitions, telemetry, initialSelection, onClose }: EventProgressionExplorerProps) {
  const milestones = useMemo(
    () => buildEventMilestones(alert, transitions, telemetry),
    [alert, transitions, telemetry],
  );
  const [selectedIndex, setSelectedIndex] = useState(() => normalizeIndex(initialSelection, milestones.length));
  const selected = milestones[selectedIndex];

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

  if (!selected) return null;
  const snapshot = selected.snapshot;

  return <aside className="overview-progression-explorer" aria-label={`${assetTag} event progression explorer`}>
    <header>
      <div><span>Event explorer</span><h2>{assetTag} progression</h2><p>Select any milestone to inspect the equipment evidence recorded at that hour.</p></div>
      <button className="overview-modal-close" onClick={onClose} aria-label="Close event progression">×</button>
    </header>
    <div className="overview-explorer-body">
      <nav className="overview-explorer-events" aria-label="Alert milestones">
        <div><span>{milestones.length} milestones</span><b>{formatSignal(alert.duration_hours / 24)} days</b></div>
        {milestones.map((milestone, index) => <button className={selectedIndex === index ? 'active' : ''} key={milestone.id} onClick={() => setSelectedIndex(index)}>
          <i className={milestone.tone}/><span><time>{formatDateTime(milestone.timestamp)}</time><strong>{milestone.title}</strong></span><b className={milestone.tone}>{milestone.label}</b>
        </button>)}
      </nav>
      <section className="overview-explorer-detail" aria-live="polite">
        <header><div><span className={selected.tone}>{selected.label}</span><time>{formatDateTime(selected.timestamp)}</time></div><h3>{selected.title}</h3><p>{selected.description}</p></header>
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
        <section className="overview-event-synthesis">
          <span>Condition synthesis</span><h4>{selected.synthesis.title}</h4><p>{selected.synthesis.detail}</p>
          <footer><span>Source</span><b>Hourly telemetry + alert decision engine</b></footer>
        </section>
      </section>
    </div>
  </aside>;
}

function normalizeIndex(index: number, length: number): number {
  return Math.max(0, Math.min(index, length - 1));
}

function formatReading(value: number | undefined): string {
  return value === undefined ? 'Unavailable' : formatSignal(value);
}
