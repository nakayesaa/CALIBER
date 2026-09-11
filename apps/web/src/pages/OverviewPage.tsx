import type { PageId } from '../components/AppShell';
import { Icon } from '../components/Icon';
import { SignalChart } from '../components/SignalChart';
import { ErrorState, LoadingState } from '../components/ViewState';
import { api, type AlertDetail, type AlertEvent, type AssetOverview, type TelemetrySeries } from '../lib/api';
import { actionsForAlert, rcaForAlert } from '../lib/demoWorkflow';
import { formatDate, formatDateTime, formatSignal, humanize } from '../lib/format';
import { useApiResource } from '../lib/useApiResource';

const ASSET_ID = 'asset-ko-3201';

interface OverviewData {
  overview: AssetOverview;
  telemetry: TelemetrySeries;
  alerts: AlertEvent[];
  detail: AlertDetail | null;
}

async function loadOverview(): Promise<OverviewData> {
  const [overview, telemetry, alerts] = await Promise.all([
    api.assetOverview(ASSET_ID),
    api.telemetry(ASSET_ID, 720),
    api.alerts(ASSET_ID),
  ]);
  const detail = alerts[0] ? await api.alertDetail(alerts[0].alert_id) : null;
  return { overview, telemetry, alerts, detail };
}

export function OverviewPage({ onNavigate }: { onNavigate: (page: PageId) => void }) {
  const resource = useApiResource('overview', loadOverview);
  if (resource.loading) return <LoadingState/>;
  if (resource.error || !resource.data) return <ErrorState message={resource.error ?? 'No overview data returned'}/>;

  const { overview, telemetry, alerts, detail } = resource.data;
  const alert = alerts[0];
  const rca = detail && rcaForAlert(detail.alert.alert_id, detail.rca);
  const plans = detail ? actionsForAlert(detail.alert.alert_id, detail.action_plans) : [];
  const actions = plans.flatMap((plan) => plan.actions);
  const latest = telemetry.points.at(-1);
  const alertDays = alert ? alert.duration_hours / 24 : 0;
  const detectionDays = alert ? hoursBetween(alert.first_signal_at, alert.opened_at) / 24 : 0;
  const selectedCause = rca?.generation.hypotheses.find((hypothesis) => hypothesis.hypothesis_id === plans[0]?.selected_hypothesis_id)
    ?? rca?.generation.hypotheses[0];

  return (
    <div className="product-view overview-page">
      <header className="overview-heading">
        <div><p>KO-3201 reliability case</p><h1>Operational overview</h1><span>From condition change to corrective action in one decision view.</span></div>
        <button className="asset-context" onClick={() => onNavigate('assets')}><span>{overview.asset.tag}</span><strong>{overview.asset.name}</strong><Icon name="arrow"/></button>
      </header>

      <section className="overview-kpis" aria-label="Case summary">
        <OverviewMetric label="Current condition" value={humanize(overview.latest_decision_state)} note="Recovered after event" tone="normal"/>
        <OverviewMetric label="Highest severity" value={humanize(alert?.highest_severity ?? 'none')} note="Historical case maximum" tone="critical"/>
        <OverviewMetric label="Actionable window" value={`${formatSignal(alertDays)} days`} note="Alert open to termination"/>
        <OverviewMetric label="Correlated signals" value={String(alert?.breached_signals.length ?? 0)} note="Condition evidence"/>
      </section>

      <section className="overview-main-grid">
        <article className="trajectory-card panel">
          <div className="overview-card-head"><div><p>Model decision signal</p><h2>Health trajectory</h2></div><span className="status-tag">6-month case window</span></div>
          <div className="trajectory-summary"><div><strong>{formatSignal(alert?.peak_anomaly_score ?? 0)}</strong><span>Peak anomaly score</span></div><p>The score crossed the decision threshold after water-in-oil became persistent, then escalated as temperature, pressure, and vibration joined the pattern.</p></div>
          <div className="trajectory-plot"><div className="chart-axis"><span>100</span><span>50</span><span>0</span></div><div><SignalChart points={telemetry.points} field="anomaly_score" threshold={50}/><div className="chart-dates"><span>{formatDate(overview.timeline_start)}</span><span>Alert threshold: 50</span><span>{formatDate(overview.timeline_end)}</span></div></div></div>
          <div className="trajectory-legend"><span><i className="model-line"/> Model anomaly score</span><span><i className="threshold-legend"/> Decision threshold</span><b>{telemetry.total_points.toLocaleString()} hourly decisions</b></div>
        </article>

        <article className="case-insight-card panel">
          <div className="overview-card-head"><div><p>Decision interpretation</p><h2>What the data says</h2></div><Icon name="spark"/></div>
          <div className="insight-list">
            <Insight number="01" title="Earliest persistent driver" value={humanize(alert?.primary_driver ?? 'none')} detail={`Detected ${formatSignal(detectionDays)} days before the grouped alert opened.`}/>
            <Insight number="02" title="Pattern progression" value="Contamination to bearing distress" detail="Oil condition led; pressure, temperature, and vibration later converged."/>
            <Insight number="03" title="Probable cause" value={selectedCause?.title ?? 'RCA pending'} detail={selectedCause ? `${Math.round(selectedCause.confidence * 100)}% ranked confidence, approved for action planning.` : 'Review the grounded evidence package.'}/>
          </div>
          <button className="primary-link" onClick={() => onNavigate('rca')}>Review evidence and RCA <Icon name="arrow"/></button>
        </article>
      </section>

      <section className="overview-bottom-grid">
        <article className="case-timeline-card panel">
          <div className="overview-card-head"><div><p>How the case developed</p><h2>Event progression</h2></div><button onClick={() => onNavigate('problems')}>Open problem <Icon name="arrow"/></button></div>
          {alert ? <div className="case-stages">
            <CaseStage state="Signal" date={formatDateTime(alert.first_signal_at)} title="Condition change detected" detail="Water-in-oil became the earliest persistent driver."/>
            <CaseStage state="Warning" date={formatDateTime(alert.opened_at)} title="Operational alert opened" detail={`Anomaly score reached ${formatSignal(detail?.opening_snapshot.anomaly_score ?? 0)} against a threshold of ${formatSignal(detail?.opening_snapshot.anomaly_threshold ?? 50)}.`}/>
            <CaseStage state="Peak" date={formatDateTime(alert.peak_score_at)} title="Multi-signal degradation" detail={`${alert.breached_signals.length} condition signals contributed to a ${humanize(alert.highest_severity)} event.`}/>
            <CaseStage state="Closed" date={formatDateTime(alert.closed_at ?? alert.peak_score_at)} title="Case moved to investigation" detail="Alert ended at the operating-mode termination; RCA and response work continued."/>
          </div> : <p>No alert event is available.</p>}
        </article>

        <article className="workflow-card panel">
          <div className="overview-card-head"><div><p>Response status</p><h2>Decision workflow</h2></div><button onClick={() => onNavigate('actions')}>View actions <Icon name="arrow"/></button></div>
          <div className="workflow-steps">
            <WorkflowStep title="Detect and prioritize" detail={`${alerts.length} grouped critical event`} status="Complete" complete/>
            <WorkflowStep title="Review probable cause" detail={rca ? humanize(rca.status) : 'Awaiting RCA'} status={rca ? 'Complete' : 'Pending'} complete={Boolean(rca)}/>
            <WorkflowStep title="Execute CA/PA" detail={`${actions.filter((action) => action.status === 'CLOSED').length} of ${actions.length} actions closed`} status={humanize(plans[0]?.status ?? 'pending')} complete={actions.length > 0 && actions.every((action) => action.status === 'CLOSED')}/>
          </div>
          {latest && <div className="current-state-note"><span className="state-dot"/><p><b>Current monitor:</b> {humanize(latest.decision_state)} at {formatDateTime(latest.timestamp)}</p></div>}
        </article>
      </section>
    </div>
  );
}

function OverviewMetric({ label, value, note, tone }: { label: string; value: string; note: string; tone?: string }) {
  return <article><div><span>{label}</span>{tone && <i className={tone}/>}</div><strong>{value}</strong><p>{note}</p></article>;
}

function Insight({ number, title, value, detail }: { number: string; title: string; value: string; detail: string }) {
  return <div className="insight"><b>{number}</b><div><span>{title}</span><h3>{value}</h3><p>{detail}</p></div></div>;
}

function CaseStage({ state, date, title, detail }: { state: string; date: string; title: string; detail: string }) {
  return <div className="case-stage"><div><b>{state}</b><span>{date}</span></div><h3>{title}</h3><p>{detail}</p></div>;
}

function WorkflowStep({ title, detail, status, complete }: { title: string; detail: string; status: string; complete: boolean }) {
  return <div className="workflow-step"><span className={complete ? 'complete' : ''}>{complete ? <Icon name="check"/> : null}</span><div><h3>{title}</h3><p>{detail}</p></div><b>{status}</b></div>;
}

function hoursBetween(start: string, end: string): number {
  return Math.max(0, (new Date(end).getTime() - new Date(start).getTime()) / 3_600_000);
}
