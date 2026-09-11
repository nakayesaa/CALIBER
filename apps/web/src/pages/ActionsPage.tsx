import { EmptyState, ErrorState, LoadingState } from '../components/ViewState';
import { Icon } from '../components/Icon';
import { api } from '../lib/api';
import { actionsForAlert } from '../lib/demoWorkflow';
import { formatDate, humanize } from '../lib/format';
import { useApiResource } from '../lib/useApiResource';
import { Metric, ViewHeader } from './ProblemTankPage';

async function loadActions() {
  const alerts = await api.alerts('asset-ko-3201');
  return alerts[0] ? api.alertDetail(alerts[0].alert_id) : null;
}

export function ActionsPage() {
  const resource = useApiResource('actions', loadActions);
  if (resource.loading) return <LoadingState/>;
  if (resource.error) return <ErrorState message={resource.error}/>;
  const plans = resource.data ? actionsForAlert(resource.data.alert.alert_id, resource.data.action_plans) : [];
  const actions = plans.flatMap((plan) => plan.actions);
  return <div className="product-view"><ViewHeader eyebrow="Close the loop" title="CA/PA action tracker" description="Approved root causes become containment, corrective, and preventive work with explicit ownership."/>{plans.length === 0 ? <EmptyState title="No action plan created yet" description="An approved RCA hypothesis unlocks the policy-driven CA/PA plan and its three tracked action types."/> : <>
    <div className="summary-strip"><Metric label="Overall status" value={humanize(plans[0].status)}/><Metric label="Actions closed" value={`${actions.filter((action) => action.status === 'CLOSED').length}/${actions.length}`}/><Metric label="Selected cause" value={humanize(plans[0].selected_cause_category)}/><Metric label="Critical actions" value={String(actions.filter((action) => action.priority === 'CRITICAL').length)}/></div>
    {plans.map((plan) => <section className="action-plan panel" key={plan.plan_id}><div className="section-heading"><div><h2>Response plan</h2><p>Based on approved hypothesis: {humanize(plan.selected_cause_category)}</p></div><b className="status-tag in-progress">{humanize(plan.status)}</b></div><div className="action-cards">{plan.actions.map((action) => <article className="action-card" key={action.action_id}><header><span className={`action-type ${action.action_type.toLowerCase()}`}>{humanize(action.action_type)}</span><b className={`status-tag ${action.status.toLowerCase().replaceAll('_', '-')}`}>{humanize(action.status)}</b></header><h3>{action.title}</h3><p>{action.guidance}</p><div className="action-owner"><span>Owner<strong>{action.owner_role}</strong></span><span>Due<strong>{formatDate(action.due_date)}</strong></span><span>Priority<strong>{humanize(action.priority)}</strong></span></div><details><summary><Icon name="check"/> Definition of done</summary><p><b>Completion:</b> {action.completion_criteria}</p><p><b>Effectiveness:</b> {action.effectiveness_check}</p></details></article>)}</div></section>)}
  </>}</div>;
}
