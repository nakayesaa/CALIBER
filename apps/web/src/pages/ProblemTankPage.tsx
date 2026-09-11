import { ErrorState, LoadingState } from '../components/ViewState';
import { Icon } from '../components/Icon';
import { api } from '../lib/api';
import { formatDateTime, formatSignal, humanize } from '../lib/format';
import { useApiResource } from '../lib/useApiResource';

export function ProblemTankPage() {
  const resource = useApiResource('problem-tank', () => api.alerts());
  if (resource.loading) return <LoadingState/>;
  if (resource.error || !resource.data) return <ErrorState message={resource.error ?? 'No alert data returned'}/>;

  return (
    <div className="product-view">
      <ViewHeader eyebrow="Prioritized operations" title="Problem tank" description="One governed queue for model alerts, severity, evidence, and workflow status."/>
      <div className="summary-strip">
        <Metric label="Total alerts" value={String(resource.data.length)}/>
        <Metric label="Critical" value={String(resource.data.filter((alert) => alert.highest_severity === 'CRITICAL').length)}/>
        <Metric label="Assets affected" value={String(new Set(resource.data.map((alert) => alert.asset_id)).size)}/>
      </div>
      <section className="table-panel panel">
        <div className="section-heading"><h2>Prioritized alerts</h2><span className="governed-label"><Icon name="check"/> Governed evidence</span></div>
        <div className="data-table" role="table">
          <div className="table-row table-head" role="row"><span>Alert</span><span>Opened</span><span>Driver</span><span>Peak score</span><span>Severity</span></div>
          {resource.data.map((alert) => <div className="table-row" role="row" key={alert.alert_id}><strong>{alert.alert_id}</strong><span>{formatDateTime(alert.opened_at)}</span><span>{humanize(alert.primary_driver)}</span><span>{formatSignal(alert.peak_anomaly_score)}</span><b className={`status-tag ${alert.highest_severity.toLowerCase()}`}>{humanize(alert.highest_severity)}</b></div>)}
        </div>
      </section>
    </div>
  );
}

export function ViewHeader({ eyebrow, title, description }: { eyebrow: string; title: string; description: string }) {
  return <header className="view-header"><p>{eyebrow}</p><h1>{title}</h1><span>{description}</span></header>;
}

export function Metric({ label, value }: { label: string; value: string }) {
  return <div><span>{label}</span><strong>{value}</strong></div>;
}
