import type { PageId } from '../components/AppShell';
import { Icon } from '../components/Icon';
import { EmptyState, ErrorState, LoadingState } from '../components/ViewState';
import { api, type AlertDetail, type AlertEvent } from '../lib/api';
import { actionsForAlert } from '../lib/demoWorkflow';
import { formatSignal, humanize } from '../lib/format';
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
  if (!resource.data.details.length) return <EmptyState title="Problem Tank is clear" description="No governed alert events require review."/>;

  const criticalCount = resource.data.alerts.filter((alert) => alert.highest_severity === 'CRITICAL').length;

  return <div className="problem-page">
    <header className="problem-page-heading">
      <div>
        <span className="problem-eyebrow">Operations review</span>
        <h1>Problem Tank</h1>
        <p>Operational issues ranked by consequence, anomaly severity, and workflow urgency. Open a problem to investigate the complete case.</p>
      </div>
      <div className="problem-counts" aria-label="Problem summary">
        <span><strong>{resource.data.alerts.length}</strong> total</span>
        <span><strong>{criticalCount}</strong> critical</span>
      </div>
    </header>

    <section className="problem-list" aria-label="Prioritized problem list">
      <header className="problem-list-heading">
        <div><span>Priority</span><strong>Problem</strong></div>
        <span>Severity</span><span>Peak score</span><span>Workflow</span><span/>
      </header>
      {resource.data.details.map((detail, index) => {
        const { alert } = detail;
        const plans = actionsForAlert(alert.alert_id, detail.action_plans, Boolean(detail.rca));
        const actions = plans.flatMap((plan) => plan.actions);
        const closedActions = actions.filter((action) => action.status === 'CLOSED').length;
        return <button key={alert.alert_id} className="problem-list-row" onClick={() => onNavigate('investigation')}>
          <div className="problem-list-identity">
            <span className="problem-priority">{String(index + 1).padStart(2, '0')}</span>
            <div><strong>Multi-signal compressor degradation</strong><p>{alert.alert_id} · KO-3201 · {humanize(alert.primary_driver.replaceAll('.', '_'))}</p></div>
          </div>
          <span className={`problem-severity ${alert.highest_severity.toLowerCase()}`}>{humanize(alert.highest_severity)}</span>
          <div className="problem-list-metric"><strong>{formatSignal(alert.peak_anomaly_score)}</strong><span>{alert.breached_signals.length} signals</span></div>
          <div className="problem-list-status"><strong>{humanize(plans[0]?.status ?? detail.rca?.status ?? alert.status)}</strong><span>{actions.length ? `${closedActions}/${actions.length} actions closed` : 'RCA review'}</span></div>
          <span className="problem-row-arrow"><Icon name="arrow"/></span>
        </button>;
      })}
    </section>
  </div>;
}

export function ViewHeader({ eyebrow, title, description }: { eyebrow: string; title: string; description: string }) {
  return <header className="view-header"><p>{eyebrow}</p><h1>{title}</h1><span>{description}</span></header>;
}

export function Metric({ label, value }: { label: string; value: string }) {
  return <div><span>{label}</span><strong>{value}</strong></div>;
}
