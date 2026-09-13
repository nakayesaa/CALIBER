import { useState } from 'react';

import type { PageId } from '../components/AppShell';
import { Icon } from '../components/Icon';
import { SignalChart } from '../components/SignalChart';
import { ErrorState, LoadingState } from '../components/ViewState';
import { api, type AlertDetail, type AlertEvent, type AssetOverview, type TelemetryPoint, type TelemetrySeries } from '../lib/api';
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
  const resource = useApiResource('overview', loadOverview);
  if (resource.loading) return <LoadingState/>;
  if (resource.error || !resource.data) return <ErrorState message={resource.error ?? 'Overview data unavailable'}/>;

  const { overview, telemetry, alerts, detail } = resource.data;
  const alert = alerts[0];
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

  return <div className="overview-overview">
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
        <header><div><h2>Event progression</h2><p>KO-3201 degradation chronology</p></div><button onClick={() => onNavigate('investigation')}>View all <Icon name="arrow"/></button></header>
        <div className="overview-schedule">
          <div className="overview-time-rule"><span>First signal</span><i/></div>
          <ScheduleEvent title="Oil condition began to deviate" detail="Water-in-oil became persistent before the broader equipment response." date={formatDateTime(alert?.first_signal_at ?? overview.timeline_start)} status="Warning" meta="1 leading signal" tone="warning"/>
          <div className="overview-time-rule"><span>Escalation</span><i/></div>
          <ScheduleEvent title="Condition signals converged" detail="The anomaly score crossed the decision threshold and required review." date={formatDateTime(alert?.opened_at ?? overview.timeline_start)} status={humanize(alert?.highest_severity ?? 'critical')} meta={`${alert?.breached_signals.length ?? 0} correlated signals`} tone="critical"/>
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
  </div>;
}

function ScheduleEvent({ title, detail, date, status, meta, tone }: { title: string; detail: string; date: string; status: string; meta: string; tone: string }) {
  return <article className="overview-schedule-event"><div><h3>{title}</h3><button><Icon name="arrow"/></button></div><p>{detail}</p><footer><span className={tone}>{status}</span><b>{meta}</b><time>{date}</time></footer></article>;
}

function GoalCard({ label, value, tone }: { label: string; value: number; tone: string }) {
  return <div className={tone}><span>{label}</span><strong>{value}</strong></div>;
}
