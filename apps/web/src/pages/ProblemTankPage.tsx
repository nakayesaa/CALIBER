import type { PageId } from '../components/AppShell';
import { Icon } from '../components/Icon';
import { EmptyState, ErrorState, LoadingState } from '../components/ViewState';
import { api, type AlertDetail, type AlertEvent } from '../lib/api';
import { actionsForAlert, rcaForAlert } from '../lib/demoWorkflow';
import { formatDateTime, formatSignal, humanize } from '../lib/format';
import { useApiResource } from '../lib/useApiResource';

interface ProblemTankData {
  alerts: AlertEvent[];
  details: AlertDetail[];
}

async function loadProblemTank(): Promise<ProblemTankData> {
  const alerts = await api.alerts();
  const details = await Promise.all(alerts.map((alert) => api.alertDetail(alert.alert_id)));
  return { alerts, details };
}

export function ProblemTankPage({ onNavigate }: { onNavigate: (page: PageId) => void }) {
  const resource = useApiResource('problem-tank', loadProblemTank);
  if (resource.loading) return <LoadingState/>;
  if (resource.error || !resource.data) return <ErrorState message={resource.error ?? 'No alert data returned'}/>;

  const { alerts, details } = resource.data;
  const detail = details[0];
  if (!detail) return <EmptyState title="Problem Tank is clear" description="No governed alert events require review."/>;

  const { alert, opening_snapshot: opening, similar_incidents: incidents } = detail;
  const rca = rcaForAlert(alert.alert_id, detail.rca);
  const plans = actionsForAlert(alert.alert_id, detail.action_plans);
  const actions = plans.flatMap((plan) => plan.actions);
  const closedActions = actions.filter((action) => action.status === 'CLOSED').length;

  return <div className="ramp-problem-page">
    <header className="ramp-problem-heading">
      <div><span className="ramp-eyebrow">Operations review · {alerts.length} governed problem</span><h1>Problem Tank</h1><p>Prioritize the issue, understand the evidence, and move the right decision forward.</p></div>
      <button className="ramp-cta" onClick={() => onNavigate('rca')}>Review RCA <Icon name="arrow"/></button>
    </header>

    <nav className="ramp-tabs" aria-label="Problem views"><button className="active">All problems <span>{alerts.length}</span></button><button>Critical <span>{alerts.filter((item) => item.highest_severity === 'CRITICAL').length}</span></button><button>Action in progress <span>{plans.filter((plan) => plan.status === 'IN_PROGRESS').length}</span></button></nav>

    <section className="ramp-problem-grid">
      <article className="ramp-tile problem-queue-tile">
        <TileHeader eyebrow="Governed queue" title="Prioritized problems" aside="Sorted by consequence"/>
        <div className="problem-column-labels"><span>Problem</span><span>Evidence</span><span>Workflow</span></div>
        <button className="problem-record selected">
          <div className="problem-identity"><span className="problem-rank">01</span><div><b>{alert.alert_id}</b><h3>Multi-signal compressor degradation</h3><p>KO-3201 · {humanize(alert.primary_driver.replaceAll('.', '_'))}</p></div></div>
          <div className="problem-evidence-summary"><strong>{formatSignal(alert.peak_anomaly_score)}</strong><span>peak score</span><p>{alert.breached_signals.length} correlated signals</p></div>
          <div className="problem-workflow"><span className="ramp-badge critical">{humanize(alert.highest_severity)}</span><b>{humanize(plans[0]?.status ?? alert.status)}</b><small>{closedActions}/{actions.length} actions closed</small></div>
        </button>
        <div className="queue-foot"><span>Model alert is closed</span><i/> <span>Operational problem remains in CA/PA execution</span></div>
      </article>

      <article className="ramp-tile ramp-dark problem-brief-tile">
        <TileHeader eyebrow="Selected problem" title="Why it needs attention" aside="Priority 01"/>
        <p className="problem-statement">A persistent oil-condition deviation developed into a four-signal compressor event on a high-criticality Class A asset.</p>
        <div className="dark-metrics"><RampMetric label="Asset" value="KO-3201"/><RampMetric label="Alert window" value={`${formatSignal(alert.duration_hours / 24)} days`}/><RampMetric label="Severity" value={humanize(alert.highest_severity)}/></div>
        <div className="decision-callout"><Icon name="spark"/><div><span>Current decision</span><p>{rca ? 'Root cause approved. Corrective work is in progress.' : 'Evidence is ready for root-cause review.'}</p></div></div>
      </article>

      <article className="ramp-tile evidence-tile">
        <TileHeader eyebrow="At alert opening" title="Evidence package" aside={`${opening.alarm_breadth} initial breach`}/>
        <div className="evidence-sequence">
          {opening.top_drivers.map((driver, index) => <div key={driver.name}><span>{String(index + 1).padStart(2, '0')}</span><div><h3>{humanize(driver.name.replaceAll('.', '_'))}</h3><p>{index === 0 ? 'Opened the persistent warning' : 'Supported the developing pattern'}</p></div><strong>{formatSignal(driver.score)}</strong></div>)}
        </div>
        <div className="evidence-rule"><span>Decision rule</span><p>Score {formatSignal(opening.anomaly_score)} exceeded threshold {formatSignal(opening.anomaly_threshold)} with condition evidence present.</p></div>
      </article>

      <article className="ramp-tile triage-tile">
        <TileHeader eyebrow="Priority logic" title="Triage rationale" aside="Explainable"/>
        <div className="triage-list"><TriageRow label="Consequence" value="Class A equipment" detail="High operational criticality"/><TriageRow label="Persistence" value={`${Math.round(alert.duration_hours).toLocaleString()} hours`} detail="Not a transient excursion"/><TriageRow label="Breadth" value={`${alert.breached_signals.length} signals`} detail="Independent condition parameters"/><TriageRow label="Workflow" value={humanize(plans[0]?.status ?? 'RCA review')} detail={`${closedActions} action already verified`}/></div>
      </article>

      <article className="ramp-tile analogue-tile">
        <TileHeader eyebrow="Historical context" title="Closest incident analogues" aside={`${incidents.length} retrieved`}/>
        <div className="ramp-analogue-list">{incidents.slice(0, 3).map((incident) => <div key={incident.incident_id}><span>#{incident.rank}</span><div><h3>{incident.title}</h3><p>{incident.asset_tag} · {humanize(incident.failure_mechanism)}</p></div><strong>{Math.round(incident.hybrid_score * 100)}%</strong></div>)}</div>
      </article>

      <article className="ramp-tile next-step-tile">
        <TileHeader eyebrow="Ownership and control" title="Next decision" aside={formatDateTime(alert.opened_at)}/>
        <div className="next-step-content"><span className="ramp-badge yellow">CA/PA execution</span><h3>{actions.find((action) => action.status === 'IN_PROGRESS')?.title ?? 'Review probable root cause'}</h3><p>{actions.find((action) => action.status === 'IN_PROGRESS')?.effectiveness_check ?? 'Validate the leading cause against the evidence package.'}</p></div>
        <button className="ramp-text-link" onClick={() => onNavigate('actions')}>Open action tracker <Icon name="arrow"/></button>
      </article>
    </section>
  </div>;
}

function TileHeader({ eyebrow, title, aside }: { eyebrow: string; title: string; aside: string }) {
  return <header className="ramp-tile-head"><div><span>{eyebrow}</span><h2>{title}</h2></div><p>{aside}</p></header>;
}

function RampMetric({ label, value }: { label: string; value: string }) { return <div><span>{label}</span><strong>{value}</strong></div>; }

function TriageRow({ label, value, detail }: { label: string; value: string; detail: string }) {
  return <div><span>{label}</span><strong>{value}</strong><p>{detail}</p></div>;
}

export function ViewHeader({ eyebrow, title, description }: { eyebrow: string; title: string; description: string }) {
  return <header className="view-header"><p>{eyebrow}</p><h1>{title}</h1><span>{description}</span></header>;
}

export function Metric({ label, value }: { label: string; value: string }) {
  return <div><span>{label}</span><strong>{value}</strong></div>;
}
