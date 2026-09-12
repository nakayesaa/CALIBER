import type { PageId } from '../components/AppShell';
import { Icon } from '../components/Icon';
import { SignalChart } from '../components/SignalChart';
import { ErrorState, LoadingState } from '../components/ViewState';
import { api, type AlertDetail, type AlertEvent, type AssetOverview, type TelemetrySeries } from '../lib/api';
import { actionsForAlert, rcaForAlert } from '../lib/demoWorkflow';
import { formatDate, formatDateTime, formatSignal, humanize } from '../lib/format';
import { useApiResource } from '../lib/useApiResource';

const ASSET_ID = 'asset-ko-3201';

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
  const resource = useApiResource('overview-v2', loadOverviewV2);
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

  const signalRows = [
    { label: 'Water in oil', value: `${formatSignal(latest?.water_in_oil_ppm ?? 0)} ppm`, role: 'Earliest persistent driver', state: 'Primary' },
    { label: 'Radial vibration', value: `${formatSignal(latest?.radial_vibration_micron ?? 0)} µm`, role: 'Mechanical response', state: 'Correlated' },
    { label: 'Bearing temperature', value: `${formatSignal(latest?.bearing_metal_temperature_degc ?? 0)} °C`, role: 'Thermal response', state: 'Correlated' },
    { label: 'Lube oil pressure', value: `${formatSignal(latest?.lube_oil_pressure_barg ?? 0)} barg`, role: 'Lubrication condition', state: 'Supporting' },
  ];

  return <div className="fusion-overview">
    <header className="fusion-heading">
      <div><span>Manufacturing performance</span><h1>Reliability overview</h1></div>
      <div><button onClick={() => onNavigate('overview')}>Original view</button><button onClick={() => onNavigate('investigation')}>Open investigation <Icon name="arrow"/></button></div>
    </header>

    <section className="fusion-kpis">
      <FusionMetric label="Peak anomaly" value={formatSignal(alert?.peak_anomaly_score ?? 0)} change={humanize(alert?.highest_severity ?? 'normal')} tone="critical"/>
      <FusionMetric label="Alert duration" value={`${formatSignal((alert?.duration_hours ?? 0) / 24)} days`} change="Persistent event"/>
      <FusionMetric label="Signals correlated" value={String(alert?.breached_signals.length ?? 0)} change="Condition evidence"/>
      <FusionMetric label="RCA confidence" value={rca ? `${confidence}%` : 'Pending'} change={humanize(detail?.rca?.status ?? 'Prepared evidence')}/>
      <FusionMetric label="Actions closed" value={actions.length ? `${closedActions}/${actions.length}` : 'Pending'} change={humanize(plans[0]?.status ?? 'Not started')} tone="positive"/>
    </section>

    <section className="fusion-main-grid">
      <article className="fusion-health-card">
        <header>
          <div><span className="fusion-title-icon"><Icon name="pulse"/></span><div><h2>Equipment health trajectory</h2><p>KO-3201 · six-month monitoring window</p></div></div>
          <span className="fusion-select">Anomaly score <Icon name="arrow"/></span>
        </header>
        <div className="fusion-health-body">
          <div className="fusion-chart-metric"><span>Peak risk score</span><strong>{formatSignal(alert?.peak_anomaly_score ?? 0)}</strong><p>Threshold <b>50</b></p></div>
          <div className="fusion-chart"><SignalChart points={telemetry.points} field="anomaly_score" threshold={50}/></div>
          <div className="fusion-chart-axis"><span>{formatDate(overview.timeline_start)}</span><b>{formatDate(alert?.first_signal_at ?? overview.timeline_start)} · first signal</b><span>{formatDate(overview.timeline_end)}</span></div>
        </div>
        <footer><div><span>Primary driver</span><strong>{humanize(alert?.primary_driver ?? 'None')}</strong></div><div><span>Equipment class</span><strong>{overview.asset.criticality}</strong></div><div><span>Current workflow</span><strong>{humanize(plans[0]?.status ?? detail?.rca?.status ?? 'RCA review')}</strong></div></footer>
      </article>

      <article className="fusion-timeline-card">
        <header><div><h2>Event progression</h2><p>From signal to accountable response</p></div><button onClick={() => onNavigate('investigation')}><Icon name="arrow"/></button></header>
        <div className="fusion-timeline">
          <TimelineItem time={formatDateTime(alert?.first_signal_at ?? overview.timeline_start)} label="Signal detected" title="Oil condition changed" detail="Water-in-oil became persistent." tone="blue"/>
          <TimelineItem time={formatDateTime(alert?.opened_at ?? overview.timeline_start)} label="Alert opened" title="Risk crossed decision threshold" detail={`${detail?.opening_snapshot.alarm_breadth ?? 0} initial signal breach.`} tone="orange"/>
          <TimelineItem time={formatDateTime(alert?.peak_score_at ?? overview.timeline_end)} label="Critical pattern" title="Condition signals converged" detail={`${alert?.breached_signals.length ?? 0} variables supported escalation.`} tone="red"/>
          <TimelineItem time={humanize(detail?.rca?.status ?? 'Prepared')} label="Decision status" title={rca ? 'Probable cause identified' : 'Evidence ready for RCA'} detail={rca?.generation.hypotheses[0]?.title ?? 'Review required.'} tone="green"/>
        </div>
      </article>
    </section>

    <section className="fusion-bottom-grid">
      <article className="fusion-signal-table">
        <header><div><h2>Condition insights</h2><p>Variables supporting the current problem</p></div><button onClick={() => onNavigate('assets')}>View all <Icon name="arrow"/></button></header>
        <div className="fusion-table-head"><span>Variable</span><span>Latest value</span><span>Role in event</span><span>Evidence</span></div>
        {signalRows.map((signal, index) => <div className="fusion-signal-row" key={signal.label}><div><span>{String(index + 1).padStart(2, '0')}</span><strong>{signal.label}</strong></div><b>{signal.value}</b><p>{signal.role}</p><span className={index === 0 ? 'primary' : ''}>{signal.state}</span></div>)}
        <div className="fusion-insight-note"><Icon name="spark"/><p><strong>Insight:</strong> Moisture appeared first, followed by a mechanically consistent bearing response.</p></div>
      </article>

      <div className="fusion-side-stack">
        <article className="fusion-accent-card">
          <header><span>RCA indication</span><b>{confidence}%</b></header>
          <h2>{rca?.generation.hypotheses[0]?.title ?? 'Evidence package ready'}</h2>
          <p>{rca ? 'Leading hypothesis based on signal sequence and historical analogues.' : 'Open the investigation to generate and review a probable cause.'}</p>
          <button onClick={() => onNavigate('investigation')}>Review RCA <Icon name="arrow"/></button>
        </article>

        <article className="fusion-action-card">
          <header><div><h2>Action tracking</h2><p>CA/PA execution by status</p></div><b>{closedActions}/{actions.length}</b></header>
          <div className="fusion-action-states"><StatusBox label="Closed" value={closedActions} tone="green"/><StatusBox label="In progress" value={actions.filter((action) => action.status === 'IN_PROGRESS').length} tone="blue"/><StatusBox label="Pending" value={actions.filter((action) => !['CLOSED', 'IN_PROGRESS'].includes(action.status)).length} tone="orange"/></div>
          <div className="fusion-next-action"><span>Next accountable move</span><strong>{activeAction?.title ?? 'Approve RCA to create actions'}</strong><p>{activeAction ? `${activeAction.owner_role} · ${humanize(activeAction.status)}` : 'Reliability Engineer'}</p></div>
          <button onClick={() => onNavigate('actions')}>Open action tracker <Icon name="arrow"/></button>
        </article>
      </div>
    </section>
  </div>;
}

function FusionMetric({ label, value, change, tone = '' }: { label: string; value: string; change: string; tone?: string }) {
  return <div><span>{label}</span><strong>{value}</strong><p className={tone}>{change}</p></div>;
}

function TimelineItem({ time, label, title, detail, tone }: { time: string; label: string; title: string; detail: string; tone: string }) {
  return <div className="fusion-event"><time>{time}</time><i className={tone}/><article><span>{label}</span><h3>{title}</h3><p>{detail}</p></article></div>;
}

function StatusBox({ label, value, tone }: { label: string; value: number; tone: string }) {
  return <div className={tone}><span>{label}</span><strong>{value}</strong></div>;
}
