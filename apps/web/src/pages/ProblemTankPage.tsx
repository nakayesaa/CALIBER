import { useState } from 'react';

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
  const [expandedAlertId, setExpandedAlertId] = useState<string | null>(null);

  if (resource.loading) return <LoadingState/>;
  if (resource.error || !resource.data) return <ErrorState message={resource.error ?? 'No alert data returned'}/>;
  if (!resource.data.details.length) return <EmptyState title="Problem Tank is clear" description="No governed alert events require review."/>;

  const criticalCount = resource.data.alerts.filter((alert) => alert.highest_severity === 'CRITICAL').length;

  return <div className="problem-page">
    <header className="problem-page-heading">
      <div>
        <span className="problem-eyebrow">Operations review</span>
        <h1>Problem Tank</h1>
        <p>Operational issues ranked for review. Select a problem to inspect its evidence, probable cause, and follow-up work.</p>
      </div>
      <div className="problem-counts" aria-label="Problem summary">
        <span><strong>{resource.data.alerts.length}</strong> total</span>
        <span><strong>{criticalCount}</strong> critical</span>
      </div>
    </header>

    <section className="problem-list" aria-label="Prioritized problem list">
      <header className="problem-list-heading">
        <div><span>Priority</span><strong>Problem</strong></div>
        <span>Severity</span>
        <span>Peak score</span>
        <span>Workflow</span>
        <span aria-hidden="true"/>
      </header>

      {resource.data.details.map((detail, index) => {
        const isExpanded = expandedAlertId === detail.alert.alert_id;
        return <ProblemListItem
          key={detail.alert.alert_id}
          detail={detail}
          index={index}
          expanded={isExpanded}
          onToggle={() => setExpandedAlertId(isExpanded ? null : detail.alert.alert_id)}
          onNavigate={onNavigate}
        />;
      })}
    </section>
  </div>;
}

function ProblemListItem({ detail, index, expanded, onToggle, onNavigate }: {
  detail: AlertDetail;
  index: number;
  expanded: boolean;
  onToggle: () => void;
  onNavigate: (page: PageId) => void;
}) {
  const { alert, opening_snapshot: opening, similar_incidents: incidents } = detail;
  const rca = rcaForAlert(alert.alert_id, detail.rca);
  const plans = actionsForAlert(alert.alert_id, detail.action_plans);
  const actions = plans.flatMap((plan) => plan.actions);
  const closedActions = actions.filter((action) => action.status === 'CLOSED').length;
  const activeAction = actions.find((action) => action.status === 'IN_PROGRESS');

  return <article className={`problem-list-item${expanded ? ' expanded' : ''}`}>
    <button className="problem-list-row" onClick={onToggle} aria-expanded={expanded}>
      <div className="problem-list-identity">
        <span className="problem-priority">{String(index + 1).padStart(2, '0')}</span>
        <div><strong>Multi-signal compressor degradation</strong><p>{alert.alert_id} · KO-3201 · {humanize(alert.primary_driver.replaceAll('.', '_'))}</p></div>
      </div>
      <span className={`problem-severity ${alert.highest_severity.toLowerCase()}`}>{humanize(alert.highest_severity)}</span>
      <div className="problem-list-metric"><strong>{formatSignal(alert.peak_anomaly_score)}</strong><span>{alert.breached_signals.length} signals</span></div>
      <div className="problem-list-status"><strong>{humanize(plans[0]?.status ?? alert.status)}</strong><span>{closedActions}/{actions.length} actions closed</span></div>
      <span className={`problem-expand-icon${expanded ? ' open' : ''}`}><Icon name="arrow"/></span>
    </button>

    {expanded && <div className="problem-detail">
      <div className="problem-detail-summary">
        <div>
          <span className="problem-eyebrow">Why it needs attention</span>
          <h2>A persistent oil-condition deviation developed into a {alert.breached_signals.length}-signal compressor event.</h2>
          <p>KO-3201 is a high-criticality Class A asset. The pattern persisted for {Math.round(alert.duration_hours).toLocaleString()} hours, making it more than a transient excursion.</p>
        </div>
        <dl>
          <div><dt>Alert opened</dt><dd>{formatDateTime(alert.opened_at)}</dd></div>
          <div><dt>Current decision</dt><dd>{rca ? 'Root cause approved' : 'RCA review required'}</dd></div>
          <div><dt>Execution</dt><dd>{humanize(plans[0]?.status ?? 'Not started')}</dd></div>
        </dl>
      </div>

      <section className="problem-detail-section">
        <header><div><span className="problem-eyebrow">At alert opening</span><h3>Evidence package</h3></div><p>Score {formatSignal(opening.anomaly_score)} vs {formatSignal(opening.anomaly_threshold)} threshold</p></header>
        <div className="problem-evidence-list">
          {opening.top_drivers.map((driver, driverIndex) => <div key={driver.name}><span>{driverIndex + 1}</span><div><strong>{humanize(driver.name.replaceAll('.', '_'))}</strong><p>{driverIndex === 0 ? 'Opened the persistent warning' : 'Supported the developing pattern'}</p></div><b>{formatSignal(driver.score)}</b></div>)}
        </div>
      </section>

      <div className="problem-detail-columns">
        <section className="problem-detail-section">
          <header><div><span className="problem-eyebrow">Historical context</span><h3>Closest incidents</h3></div></header>
          <div className="problem-incident-list">
            {incidents.slice(0, 3).map((incident) => <div key={incident.incident_id}><div><strong>{incident.title}</strong><p>{incident.asset_tag} · {humanize(incident.failure_mechanism)}</p></div><b>{Math.round(incident.hybrid_score * 100)}% match</b></div>)}
          </div>
        </section>

        <section className="problem-detail-section problem-next-action">
          <header><div><span className="problem-eyebrow">CA/PA execution</span><h3>Next action</h3></div></header>
          <strong>{activeAction?.title ?? 'Review probable root cause'}</strong>
          <p>{activeAction?.effectiveness_check ?? 'Validate the leading cause against the evidence package.'}</p>
          <div className="problem-detail-actions">
            <button onClick={() => onNavigate('rca')}>Review RCA <Icon name="arrow"/></button>
            <button onClick={() => onNavigate('actions')}>Open action tracker</button>
          </div>
        </section>
      </div>
    </div>}
  </article>;
}

export function ViewHeader({ eyebrow, title, description }: { eyebrow: string; title: string; description: string }) {
  return <header className="view-header"><p>{eyebrow}</p><h1>{title}</h1><span>{description}</span></header>;
}

export function Metric({ label, value }: { label: string; value: string }) {
  return <div><span>{label}</span><strong>{value}</strong></div>;
}
