import { EmptyState, ErrorState, LoadingState } from '../components/ViewState';
import { api } from '../lib/api';
import { formatDate, humanize } from '../lib/format';
import { useApiResource } from '../lib/useApiResource';
import { ViewHeader } from './ProblemTankPage';

async function loadActions() {
  const alerts = await api.alerts('asset-ko-3201');
  return alerts[0] ? api.alertDetail(alerts[0].alert_id) : null;
}

export function ActionsPage() {
  const resource = useApiResource('actions', loadActions);
  if (resource.loading) return <LoadingState/>;
  if (resource.error) return <ErrorState message={resource.error}/>;
  const plans = resource.data?.action_plans ?? [];
  return <div className="product-view"><ViewHeader eyebrow="Close the loop" title="CA/PA action tracker" description="Approved root causes become containment, corrective, and preventive work with explicit ownership."/>{plans.length === 0 ? <EmptyState title="No action plan created yet" description="An approved RCA hypothesis unlocks the policy-driven CA/PA plan and its three tracked action types."/> : plans.map((plan) => <section className="table-panel panel" key={plan.plan_id}><div className="section-heading"><h2>{humanize(plan.selected_cause_category)}</h2><b className="status-tag">{humanize(plan.status)}</b></div><div className="data-table actions-table"><div className="table-row table-head"><span>Type</span><span>Action</span><span>Owner</span><span>Due</span><span>Status</span></div>{plan.actions.map((action) => <div className="table-row" key={action.action_id}><b>{humanize(action.action_type)}</b><span>{action.title}</span><span>{action.owner_role}</span><span>{formatDate(action.due_date)}</span><b className="status-tag">{humanize(action.status)}</b></div>)}</div></section>)}</div>;
}
