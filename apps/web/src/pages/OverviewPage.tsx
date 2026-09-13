import { useEffect, useState } from 'react';

import type { PageId } from '../components/AppShell';
import { Icon } from '../components/Icon';
import { SignalChart } from '../components/SignalChart';
import { ErrorState, LoadingState } from '../components/ViewState';
import { api, type AlertDetail, type AlertEvent, type AlertStateTransition, type AssetOverview, type TelemetryPoint, type TelemetrySeries } from '../lib/api';
import { actionsForAlert, rcaForAlert } from '../lib/demoWorkflow';
import { formatDate, formatDateTime, formatSignal, humanize } from '../lib/format';
import { useApiResource } from '../lib/useApiResource';

const ASSET_ID = 'asset-ko-3201';

type ConditionField = keyof Pick<TelemetryPoint,
  'water_in_oil_ppm' | 'radial_vibration_micron' |
  'bearing_metal_temperature_degc' | 'lube_oil_pressure_barg'>;

const conditionSignals: Array<{ field: ConditionField; label: string; unit: string; role: string }> = [
  { field: 'water_in_oil_ppm', label: 'Water in oil', unit: 'ppm', role: 'Primary driver' },
  { field: 'radial_vibration_micron', label: 'Radial vibration', unit: 'µm', role: 'Mechanical response' },
  { field: 'bearing_metal_temperature_degc', label: 'Bearing temperature', unit: '°C', role: 'Thermal response' },
  { field: 'lube_oil_pressure_barg', label: 'Lube oil pressure', unit: 'barg', role: 'Supporting condition' },
];

interface OverviewData {
  overview: AssetOverview;
  telemetry: TelemetrySeries;
  alerts: AlertEvent[];
  detail: AlertDetail | null;
}

async function loadOverview(): Promise<OverviewData> {
  const [overview, telemetry, alerts] = await Promise.all([
    api.assetOverview(ASSET_ID),
    api.telemetry(ASSET_ID, 5000),
    api.alerts(ASSET_ID),
  ]);
  const detail = alerts[0] ? await api.alertDetail(alerts[0].alert_id) : null;
  return { overview, telemetry, alerts, detail };
}

export function OverviewPage({ onNavigate }: { onNavigate: (page: PageId) => void }) {
  const [selectedCondition, setSelectedCondition] = useState<ConditionField>('water_in_oil_ppm');
  const [selectedProgression, setSelectedProgression] = useState<number | null>(null);
  const resource = useApiResource('overview', loadOverview);
  if (resource.loading) return <LoadingState/>;
  if (resource.error || !resource.data) return <ErrorState message={resource.error ?? 'Overview data unavailable'}/>;

  const { overview, telemetry, alerts, detail } = resource.data;
  const alert = alerts[0];
  const escalationTransition = detail?.state_transitions.find((transition) => transition.new_state === alert?.highest_severity);
  const escalationIndex = Math.max((detail?.state_transitions.findIndex((transition) => transition === escalationTransition) ?? 0) + 1, 1);
  const latest = telemetry.points.at(-1);
  const rca = detail ? rcaForAlert(detail.alert.alert_id, detail.rca) : null;
  const plans = detail ? actionsForAlert(detail.alert.alert_id, detail.action_plans, Boolean(detail.rca)) : [];
  const actions = plans.flatMap((plan) => plan.actions);
  const closedActions = actions.filter((action) => action.status === 'CLOSED').length;
  const activeAction = actions.find((action) => action.status === 'IN_PROGRESS') ?? actions.find((action) => action.status !== 'CLOSED');
  const confidence = Math.round((rca?.generation.hypotheses[0]?.confidence ?? 0) * 100);

  const selectedSignal = conditionSignals.find((signal) => signal.field === selectedCondition)!;
  const selectedValues = telemetry.points.map((point) => Number(point[selectedCondition]));
  const selectedLatest = selectedValues.at(-1) ?? 0;
  const selectedFirst = selectedValues[0] ?? 0;
  const selectedPeak = selectedValues.length ? Math.max(...selectedValues) : 0;
  const selectedDelta = selectedLatest - selectedFirst;

  return <div className="overview-dashboard">
    <header className="overview-heading">
      <div><span>Manufacturing performance</span><h1>Reliability overview</h1></div>
      <div><button onClick={() => onNavigate('investigation')}>Open investigation <Icon name="arrow"/></button></div>
    </header>

    <section className="overview-main-grid">
      <article className="overview-health-card">
        <header>
          <div><span className="overview-title-icon"><Icon name="pulse"/></span><div><h2>Equipment health trajectory</h2><p>KO-3201 · six-month monitoring window</p></div></div>
          <span className="overview-select">Anomaly score <Icon name="arrow"/></span>
        </header>
        <div className="overview-health-body">
          <div className="overview-chart-metric"><span>Peak risk score</span><strong>{formatSignal(alert?.peak_anomaly_score ?? 0)}</strong><p>Threshold <b>50</b></p></div>
          <div className="overview-chart"><SignalChart points={telemetry.points} field="anomaly_score" threshold={50}/></div>
          <div className="overview-chart-axis"><span>{formatDate(overview.timeline_start)}</span><b>{formatDate(alert?.first_signal_at ?? overview.timeline_start)} · first signal</b><span>{formatDate(overview.timeline_end)}</span></div>
        </div>
        <div className="overview-health-context">
          <div><span>Leading condition</span><strong>Water in oil</strong><b>{formatSignal(latest?.water_in_oil_ppm ?? 0)} ppm</b></div>
          <div><span>Correlated response</span><strong>Radial vibration</strong><b>{formatSignal(latest?.radial_vibration_micron ?? 0)} µm</b></div>
          <div><span>Incident window</span><strong>{formatSignal((alert?.duration_hours ?? 0) / 24)} days</strong><b>{alert?.breached_signals.length ?? 0} signals</b></div>
        </div>
      </article>

      <article className="overview-timeline-card">
        <header><div><h2>Event progression</h2><p>KO-3201 degradation chronology</p></div><button onClick={() => setSelectedProgression(0)}>View all <Icon name="arrow"/></button></header>
        <div className="overview-schedule">
          <div className="overview-time-rule"><span>First signal</span><i/></div>
          <ScheduleEvent title="Oil condition began to deviate" detail="Water-in-oil became persistent before the broader equipment response." date={formatDateTime(alert?.first_signal_at ?? overview.timeline_start)} status="Warning" meta="1 leading signal" tone="warning" onClick={() => setSelectedProgression(0)}/>
          <div className="overview-time-rule"><span>Escalation</span><i/></div>
          <ScheduleEvent title="Condition signals converged" detail="Oil, pressure, thermal, and vibration evidence formed a critical pattern." date={formatDateTime(escalationTransition?.timestamp ?? alert?.opened_at ?? overview.timeline_start)} status={humanize(alert?.highest_severity ?? 'critical')} meta={`${alert?.breached_signals.length ?? 0} correlated signals`} tone="critical" onClick={() => setSelectedProgression(escalationIndex)}/>
        </div>
      </article>
    </section>

    <section className="overview-bottom-grid">
      <article className="overview-condition-card">
        <header><div><h2>Condition insights</h2><p>Explore how each variable contributed to the event</p></div><button onClick={() => onNavigate('assets')}>All equipment data <Icon name="arrow"/></button></header>
        <nav className="overview-condition-tabs" aria-label="Condition variables">
          {conditionSignals.map((signal) => <button className={selectedCondition === signal.field ? 'active' : ''} key={signal.field} onClick={() => setSelectedCondition(signal.field)}><span>{signal.label}</span><strong>{formatSignal(Number(latest?.[signal.field] ?? 0))} {signal.unit}</strong></button>)}
        </nav>
        <div className="overview-condition-visual">
          <div className="overview-condition-summary">
            <span>{selectedSignal.role}</span>
            <strong>{formatSignal(selectedLatest)} <small>{selectedSignal.unit}</small></strong>
            <p>Latest reading</p>
            <dl><div><dt>Window peak</dt><dd>{formatSignal(selectedPeak)} {selectedSignal.unit}</dd></div><div><dt>Net movement</dt><dd>{selectedDelta >= 0 ? '+' : ''}{formatSignal(selectedDelta)} {selectedSignal.unit}</dd></div></dl>
          </div>
          <div className="overview-condition-chart"><SignalChart points={telemetry.points} field={selectedCondition}/><div><span>{formatDate(overview.timeline_start)}</span><b>{formatDate(alert?.first_signal_at ?? overview.timeline_start)} · event onset</b><span>{formatDate(overview.timeline_end)}</span></div></div>
        </div>
      </article>

      <article className="overview-decision-card">
        <header><h2>RCA &amp; action progress</h2><button onClick={() => onNavigate('investigation')}><Icon name="arrow"/></button></header>
        <section className="overview-rca-summary">
          <div><span>01</span><h3>{rca?.generation.hypotheses[0]?.title ?? 'Evidence package ready'}</h3><b>{confidence}%</b></div>
          <p>Supported by signal sequence and similar incident evidence.</p>
        </section>
        <section className="overview-goal-tracking">
          <div className="overview-goal-cards"><GoalCard label="Closed" value={closedActions} tone="green"/><GoalCard label="In progress" value={actions.filter((action) => action.status === 'IN_PROGRESS').length} tone="blue"/><GoalCard label="Pending" value={actions.filter((action) => !['CLOSED', 'IN_PROGRESS'].includes(action.status)).length} tone="orange"/></div>
          <div className="overview-action-target"><header><span>CA/PA completion</span><b>{actions.length ? `${closedActions}/${actions.length}` : '0/0'}</b></header><div><i style={{ width: `${actions.length ? closedActions / actions.length * 100 : 0}%` }}/></div></div>
          <div className="overview-action-target"><header><span>{activeAction?.title ?? 'Approve RCA to create actions'}</span><b>{activeAction ? humanize(activeAction.status) : 'Pending'}</b></header><p>{activeAction?.owner_role ?? 'Reliability Engineer'}</p></div>
        </section>
        <footer><button onClick={() => onNavigate('actions')}>Open action tracker <Icon name="arrow"/></button></footer>
      </article>
    </section>

    {selectedProgression !== null && alert && detail ? <EventProgressionExplorer alert={alert} transitions={detail.state_transitions} telemetry={telemetry.points} initialSelection={selectedProgression} onClose={() => setSelectedProgression(null)}/> : null}
  </div>;
}

const progressionCopy: Record<string, { title: string; detail: string; tone: string }> = {
  WARNING: {
    title: 'Persistent condition warning opened',
    detail: 'The leading condition remained abnormal long enough to satisfy the alert policy.',
    tone: 'warning',
  },
  HIGH: {
    title: 'Alert escalated to high priority',
    detail: 'Additional evidence increased confidence that the deviation required engineering review.',
    tone: 'high',
  },
  CRITICAL: {
    title: 'Multi-signal degradation became critical',
    detail: 'Oil, pressure, thermal, and vibration evidence converged into a critical equipment condition.',
    tone: 'critical',
  },
  CLOSED: {
    title: 'Alert monitoring window closed',
    detail: 'The operating-state transition ended this alert window and preserved it for investigation.',
    tone: 'closed',
  },
};

function EventProgressionExplorer({ alert, transitions, telemetry, initialSelection, onClose }: { alert: AlertEvent; transitions: AlertStateTransition[]; telemetry: TelemetryPoint[]; initialSelection: number; onClose: () => void }) {
  const milestones = [
    { timestamp: alert.first_signal_at, state: 'FIRST_SIGNAL', reason: 'MODEL_CONDITION_DEVIATION' },
    ...transitions.map((transition) => ({ timestamp: transition.timestamp, state: transition.new_state, reason: transition.reason })),
  ];
  const [selectedIndex, setSelectedIndex] = useState(Math.min(initialSelection, milestones.length - 1));
  const selected = milestones[selectedIndex];
  const snapshot = nearestTelemetryPoint(telemetry, selected.timestamp);
  const copy = selected.state === 'FIRST_SIGNAL'
    ? { title: 'Oil condition began to deviate', detail: 'Water-in-oil became the earliest persistent signal before the wider equipment response.', tone: 'signal' }
    : progressionCopy[selected.state] ?? { title: `${humanize(selected.state)} state recorded`, detail: humanize(selected.reason), tone: 'signal' };
  const synthesis = conditionSynthesis(selected.state, snapshot);

  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', closeOnEscape);
    return () => window.removeEventListener('keydown', closeOnEscape);
  }, [onClose]);

  useEffect(() => setSelectedIndex(Math.min(initialSelection, milestones.length - 1)), [initialSelection, milestones.length]);

  return <aside className="overview-progression-explorer" aria-label="KO-3201 event progression explorer">
      <header>
        <div><span>Event explorer</span><h2>KO-3201 progression</h2><p>Select any milestone to inspect the equipment evidence recorded at that hour.</p></div>
        <button className="overview-modal-close" onClick={onClose} aria-label="Close event progression">×</button>
      </header>
      <div className="overview-explorer-body">
        <nav className="overview-explorer-events" aria-label="Alert milestones">
          <div><span>{milestones.length} milestones</span><b>{formatSignal(alert.duration_hours / 24)} days</b></div>
          {milestones.map((milestone, index) => {
            const itemCopy = milestone.state === 'FIRST_SIGNAL'
              ? { title: 'First condition signal', tone: 'signal' }
              : progressionCopy[milestone.state] ?? { title: humanize(milestone.state), tone: 'signal' };
            return <button className={selectedIndex === index ? 'active' : ''} key={`${milestone.timestamp}-${milestone.state}`} onClick={() => setSelectedIndex(index)}>
              <i className={itemCopy.tone}/><span><time>{formatDateTime(milestone.timestamp)}</time><strong>{itemCopy.title}</strong></span><b className={itemCopy.tone}>{humanize(milestone.state)}</b>
            </button>;
          })}
        </nav>
        <section className="overview-explorer-detail" aria-live="polite">
          <header><div><span className={copy.tone}>{humanize(selected.state)}</span><time>{formatDateTime(selected.timestamp)}</time></div><h3>{copy.title}</h3><p>{copy.detail}</p></header>
          <section className="overview-snapshot-section">
            <div className="overview-snapshot-heading"><h4>Current condition</h4><span>Hourly snapshot</span></div>
            <div className="overview-snapshot-grid">
              {conditionSignals.map((signal) => <div key={signal.field}><span>{signal.label}</span><strong>{formatSignal(Number(snapshot?.[signal.field] ?? 0))} <small>{signal.unit}</small></strong></div>)}
            </div>
          </section>
          <section className="overview-evidence-strip">
            <div><span>Anomaly score</span><strong>{snapshot?.anomaly_score == null ? 'Not scored' : formatSignal(snapshot.anomaly_score)}</strong></div>
            <div><span>Decision state</span><strong>{humanize(snapshot?.decision_state ?? selected.state)}</strong></div>
            <div><span>Signals breached</span><strong>{snapshot?.breached_signals.length ?? 0}</strong></div>
          </section>
          <section className="overview-event-synthesis">
            <span>Condition synthesis</span><h4>{synthesis.title}</h4><p>{synthesis.detail}</p>
            <footer><span>Source</span><b>Hourly telemetry + alert decision engine</b></footer>
          </section>
        </section>
      </div>
    </aside>;
}

function nearestTelemetryPoint(points: TelemetryPoint[], timestamp: string): TelemetryPoint | undefined {
  if (!points.length) return undefined;
  const target = new Date(timestamp).getTime();
  let low = 0;
  let high = points.length - 1;
  while (low < high) {
    const middle = Math.floor((low + high) / 2);
    if (new Date(points[middle].timestamp).getTime() < target) low = middle + 1;
    else high = middle;
  }
  if (low === 0) return points[0];
  const before = points[low - 1];
  const after = points[low];
  return target - new Date(before.timestamp).getTime() <= new Date(after.timestamp).getTime() - target ? before : after;
}

function conditionSynthesis(state: string, snapshot?: TelemetryPoint): { title: string; detail: string } {
  const score = snapshot?.anomaly_score == null ? 'not yet available' : formatSignal(snapshot.anomaly_score);
  const breadth = snapshot?.breached_signals.length ?? 0;
  if (state === 'FIRST_SIGNAL') return {
    title: 'An isolated lubrication signal is emerging',
    detail: `Water-in-oil moved first while broader mechanical evidence had not yet converged. The anomaly score was ${score}, so the appropriate response at this point was observation and verification rather than a confirmed RCA.`,
  };
  if (state === 'WARNING') return {
    title: 'Lubrication contamination is the earliest working hypothesis',
    detail: `The persistent oil-condition deviation satisfied the warning policy with ${breadth} breached signal. Evidence was still narrow, so an oil sample and sensor verification were needed before escalation.`,
  };
  if (state === 'HIGH') return {
    title: 'Persistent oil-condition evidence raises the priority',
    detail: `The model reached ${score} with ${breadth} breached ${breadth === 1 ? 'signal' : 'signals'}. Persistence and risk intensity drove this escalation before broad signal convergence, making impaired lubrication a stronger but still unconfirmed hypothesis.`,
  };
  if (state === 'CRITICAL') return {
    title: 'Multi-signal convergence supports bearing oil-film degradation',
    detail: `Oil condition, pressure, temperature, and vibration now form a mechanically coherent pattern. Moisture ingress degrading the lubricant film is the leading probable cause and immediate equipment inspection is justified.`,
  };
  return {
    title: 'The alert window ended, but the cause remains actionable',
    detail: `Closure records the operating-state termination rather than proof that the equipment recovered. The accumulated evidence remains available for RCA, corrective action, and effectiveness verification.`,
  };
}

function ScheduleEvent({ title, detail, date, status, meta, tone, onClick }: { title: string; detail: string; date: string; status: string; meta: string; tone: string; onClick: () => void }) {
  return <article className="overview-schedule-event"><div><h3>{title}</h3><button onClick={onClick} aria-label={`Inspect ${title}`}><Icon name="arrow"/></button></div><p>{detail}</p><footer><span className={tone}>{status}</span><b>{meta}</b><time>{date}</time></footer></article>;
}

function GoalCard({ label, value, tone }: { label: string; value: number; tone: string }) {
  return <div className={tone}><span>{label}</span><strong>{value}</strong></div>;
}
