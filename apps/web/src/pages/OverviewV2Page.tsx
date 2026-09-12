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

type SignalField = keyof Pick<TelemetryPoint,
  'radial_vibration_micron' | 'water_in_oil_ppm' | 'lube_oil_pressure_barg' |
  'bearing_metal_temperature_degc' | 'feed_rate_tph' | 'discharge_pressure_barg'>;

const signals: Array<{ field: SignalField; label: string; short: string; unit: string }> = [
  { field: 'water_in_oil_ppm', label: 'Water in oil', short: 'Oil moisture', unit: 'ppm' },
  { field: 'radial_vibration_micron', label: 'Radial vibration', short: 'Vibration', unit: 'µm' },
  { field: 'lube_oil_pressure_barg', label: 'Lube oil pressure', short: 'Oil pressure', unit: 'barg' },
  { field: 'bearing_metal_temperature_degc', label: 'Bearing temperature', short: 'Bearing temp.', unit: '°C' },
  { field: 'feed_rate_tph', label: 'Feed rate', short: 'Feed rate', unit: 'tph' },
  { field: 'discharge_pressure_barg', label: 'Discharge pressure', short: 'Discharge', unit: 'barg' },
];

interface OverviewV2Data {
  overview: AssetOverview;
  telemetry: TelemetrySeries;
  alerts: AlertEvent[];
  detail: AlertDetail | null;
}

async function loadOverviewV2(): Promise<OverviewV2Data> {
  const [overview, telemetry, alerts] = await Promise.all([
    api.assetOverview(ASSET_ID),
    api.telemetry(ASSET_ID, 720),
    api.alerts(ASSET_ID),
  ]);
  const detail = alerts[0] ? await api.alertDetail(alerts[0].alert_id) : null;
  return { overview, telemetry, alerts, detail };
}

export function OverviewV2Page({ onNavigate }: { onNavigate: (page: PageId) => void }) {
  const [selectedField, setSelectedField] = useState<SignalField>('water_in_oil_ppm');
  const resource = useApiResource('overview-v2', loadOverviewV2);
  if (resource.loading) return <LoadingState/>;
  if (resource.error || !resource.data) return <ErrorState message={resource.error ?? 'Overview data unavailable'}/>;

  const { overview, telemetry, alerts, detail } = resource.data;
  const alert = alerts[0];
  const latest = telemetry.points.at(-1);
  const selectedSignal = signals.find((signal) => signal.field === selectedField)!;
  const selectedValues = telemetry.points.map((point) => Number(point[selectedField]));
  const rca = detail ? rcaForAlert(detail.alert.alert_id, detail.rca) : null;
  const plans = detail ? actionsForAlert(detail.alert.alert_id, detail.action_plans, Boolean(detail.rca)) : [];
  const actions = plans.flatMap((plan) => plan.actions);
  const closedActions = actions.filter((action) => action.status === 'CLOSED').length;
  const activeAction = actions.find((action) => action.status === 'IN_PROGRESS') ?? actions.find((action) => action.status !== 'CLOSED');

  return <div className="overview-v2">
    <header className="v2-heading">
      <div><span>Manufacturing intelligence</span><h1>Reliability command center</h1><p>One story from equipment health to the next accountable decision.</p></div>
      <div className="v2-heading-actions"><button onClick={() => onNavigate('overview')}>View original</button><button onClick={() => onNavigate('investigation')}>Investigate KO-3201 <Icon name="arrow"/></button></div>
    </header>

    <section className="v2-kpi-strip" aria-label="Case summary">
      <V2Metric label="Peak anomaly" value={formatSignal(alert?.peak_anomaly_score ?? 0)} detail={humanize(alert?.highest_severity ?? 'normal')} tone="risk"/>
      <V2Metric label="First persistent signal" value={formatDate(alert?.first_signal_at ?? overview.timeline_start)} detail="Early condition evidence"/>
      <V2Metric label="Signals involved" value={String(alert?.breached_signals.length ?? 0)} detail="Correlated condition variables"/>
      <V2Metric label="RCA decision" value={humanize(detail?.rca?.status ?? (rca ? 'Prepared' : 'Pending'))} detail={rca?.generation.hypotheses[0]?.title ?? 'Awaiting evidence review'}/>
      <V2Metric label="Action closure" value={actions.length ? `${closedActions}/${actions.length}` : 'Pending'} detail={humanize(plans[0]?.status ?? 'Not started')} tone="action"/>
    </section>

    <section className="v2-main-grid">
      <article className="v2-trajectory-card">
        <header><div><span className="v2-pill"><i/> Six-month case replay</span><h2>Health trajectory</h2><p>The model surfaced a persistent condition change before multiple signals converged.</p></div><div className="v2-asset-chip"><span>{overview.asset.tag}</span><strong>{overview.asset.equipment_type}</strong></div></header>
        <div className="v2-trajectory-stage">
          <div className="v2-chart-summary"><span>Risk escalated to</span><strong>{formatSignal(alert?.peak_anomaly_score ?? 0)}</strong><p>Decision threshold 50</p></div>
          <div className="v2-main-chart"><SignalChart points={telemetry.points} field="anomaly_score" threshold={50}/></div>
          <div className="v2-chart-dates"><span>{formatDate(overview.timeline_start)}</span><span>{formatDate(alert?.first_signal_at ?? overview.timeline_start)} first signal</span><span>{formatDate(overview.timeline_end)}</span></div>
        </div>
        <div className="v2-storyline">
          <StoryPoint number="01" label="Signal emerged" value="Oil moisture became persistent" date={formatDateTime(alert?.first_signal_at ?? overview.timeline_start)}/>
          <StoryPoint number="02" label="Alert prioritized" value={`${alert?.breached_signals.length ?? 0} signals supported escalation`} date={formatDateTime(alert?.opened_at ?? overview.timeline_start)}/>
          <StoryPoint number="03" label="Decision advanced" value={rca ? 'Probable cause available for review' : 'RCA evidence package ready'} date={humanize(detail?.rca?.status ?? 'Prepared evidence')}/>
        </div>
      </article>

      <aside className="v2-priority-card">
        <header><span>Priority problem</span><strong>01</strong></header>
        <div className="v2-priority-mark"><Icon name="pulse"/><span>{overview.asset.tag}</span></div>
        <h2>Multi-signal compressor degradation</h2>
        <p>Persistent oil-condition deviation developed into a broader bearing-risk pattern on a Class A asset.</p>
        <dl>
          <div><dt>Severity</dt><dd>{humanize(alert?.highest_severity ?? 'normal')}</dd></div>
          <div><dt>Primary driver</dt><dd>{humanize(alert?.primary_driver ?? 'none')}</dd></div>
          <div><dt>Alert window</dt><dd>{formatSignal((alert?.duration_hours ?? 0) / 24)} days</dd></div>
          <div><dt>Workflow</dt><dd>{humanize(plans[0]?.status ?? detail?.rca?.status ?? 'RCA review')}</dd></div>
        </dl>
        <button onClick={() => onNavigate('investigation')}>Open problem story <Icon name="arrow"/></button>
      </aside>
    </section>

    <section className="v2-lower-grid">
      <article className="v2-signal-card">
        <header><div><span>Condition intelligence</span><h2>Variable behavior</h2></div><strong>Hourly</strong></header>
        <div className="v2-signal-layout">
          <nav aria-label="Condition variables">{signals.map((signal) => <button key={signal.field} className={selectedField === signal.field ? 'active' : ''} onClick={() => setSelectedField(signal.field)}><span>{signal.short}</span><strong>{latest ? formatSignal(Number(latest[signal.field])) : '—'} <small>{signal.unit}</small></strong></button>)}</nav>
          <div className="v2-signal-chart"><header><div><span>{selectedSignal.label}</span><strong>{latest ? formatSignal(Number(latest[selectedField])) : '—'} {selectedSignal.unit}</strong></div><div><span>Window peak</span><strong>{selectedValues.length ? formatSignal(Math.max(...selectedValues)) : '—'} {selectedSignal.unit}</strong></div></header><SignalChart points={telemetry.points} field={selectedField}/><footer><span>{formatDate(overview.timeline_start)}</span><span>{formatDate(overview.timeline_end)}</span></footer></div>
        </div>
      </article>

      <article className="v2-decision-card">
        <header><div><span>AI-assisted RCA</span><h2>Leading indication</h2></div><b>{rca ? `${Math.round((rca.generation.hypotheses[0]?.confidence ?? 0) * 100)}%` : '—'}</b></header>
        <h3>{rca?.generation.hypotheses[0]?.title ?? 'Evidence package awaiting RCA generation'}</h3>
        <p>{rca?.generation.hypotheses[0]?.rationale ?? 'The alert snapshot and historical analogues are ready for review.'}</p>
        <div className="v2-evidence-row">{detail?.opening_snapshot.top_drivers.map((driver, index) => <span key={driver.name}><i>{index + 1}</i>{humanize(driver.name.replaceAll('.', '_'))}<strong>{formatSignal(driver.score)}</strong></span>)}</div>
        <button onClick={() => onNavigate('investigation')}>Review evidence and decision <Icon name="arrow"/></button>
      </article>

      <article className="v2-action-card">
        <header><div><span>Operational response</span><h2>Action ownership</h2></div><b>{closedActions}/{actions.length}</b></header>
        {activeAction ? <><div className="v2-next-action"><span>Next accountable move</span><h3>{activeAction.title}</h3><p>{activeAction.owner_role} · due {formatDate(activeAction.due_date)}</p></div><div className="v2-action-progress">{actions.map((action) => <div key={action.action_id}><span><i className={action.status === 'CLOSED' ? 'closed' : action.status === 'IN_PROGRESS' ? 'active' : ''}/>{humanize(action.action_type)}</span><strong>{humanize(action.status)}</strong></div>)}</div></> : <div className="v2-no-action"><Icon name="check"/><p>Approve the probable root cause to create the governed CA/PA plan.</p></div>}
        <button onClick={() => onNavigate('actions')}>Open action tracker <Icon name="arrow"/></button>
      </article>
    </section>
  </div>;
}

function V2Metric({ label, value, detail, tone = '' }: { label: string; value: string; detail: string; tone?: string }) {
  return <div className={tone}><span>{label}</span><strong>{value}</strong><p>{detail}</p></div>;
}

function StoryPoint({ number, label, value, date }: { number: string; label: string; value: string; date: string }) {
  return <div><span>{number}</span><div><b>{label}</b><strong>{value}</strong><p>{date}</p></div></div>;
}
