import { useState } from 'react';
import { ActionWork } from '../components/CoordinationPanel';
import { LoadingState } from '../components/ViewState';
import { api, selectWorkflowSession } from '../lib/api';
import { useApiResource } from '../lib/useApiResource';
import '../production-review.css';
import '../components/case-packet.css';
import '../gm-review.css';

export function AssignedActionsPage({ personId, assetId }: { personId?: string; assetId?: string }) {
  const resource = useApiResource(`assigned-actions:${personId ?? ''}`, async () => {
    const session = await selectWorkflowSession(personId);
    const plans = await api.assignedActions();
    const reviews = await Promise.all([...new Set(plans.filter(plan => !plan.gm_report_id).map(plan => plan.alert_id))].map(async alertId => [alertId, (await api.caseReview(alertId)).status === 'VERIFIED'] as const));
    return { session, plans, verified: Object.fromEntries(reviews) };
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function run(command: () => Promise<unknown>) {
    if (busy) return;
    setBusy(true); setError(null);
    try { await command(); resource.reload(); }
    catch (failure) { setError(failure instanceof Error ? failure.message : 'Unable to save action progress'); }
    finally { setBusy(false); }
  }
  if (!resource.data) return resource.loading ? <LoadingState/> : <div className="production-review-error"><h1>Assigned actions unavailable</h1><p role="alert">{resource.error}</p><button onClick={resource.reload}>Retry</button></div>;
  const { session, plans, verified } = resource.data;
  return <div className="decision-workspace production-review-page assigned-actions-page">
    <header className="decision-workspace-heading"><div><span>Operator layer · Action owner</span><h1>My assigned actions</h1><p>{session.current.display_name} · Accept the assignment, record execution requirements, then submit completion evidence.</p></div><button disabled={busy || resource.loading} onClick={resource.reload}>Refresh tasks</button></header>
    {(error || resource.error) && <p role="alert">{error ?? resource.error}</p>}
    {!plans.length ? <section className="production-review-card"><h2>No tasks assigned to you</h2><p>The supervisor assigns a named owner after the required case approval.</p></section> : plans.map(plan => <section className="production-review-card coordination-panel assigned-task-group" key={plan.plan_id}>
      <header><div><span>Case-linked follow-up</span><h2>{plan.alert_id.replace(/^alert-asset-/, '').replace(/-\d+$/, '').toUpperCase()}</h2></div></header>
      <p>Authorization: {plan.gm_report_id ?? 'Supervisor-reviewed case'} · {plan.actions.length} assigned {plan.actions.length === 1 ? 'action' : 'actions'}.</p>
      <fieldset disabled={busy || resource.loading}>{plan.actions.map(action => <div key={action.action_id}><p><strong>Supervisor instruction:</strong> {action.assignment?.history.filter(entry => entry.status === 'ASSIGNED').at(-1)?.note ?? action.guidance}</p><ActionWork action={action} session={session} verified={!!plan.gm_report_id || !!verified[plan.alert_id]} run={run} defaultOpen={plan.actions.length === 1}/></div>)}</fieldset>
      {session.can_switch && <a className="scope-return-link" href={`#${plan.gm_report_id ? 'gm-review' : 'actions'}?${new URLSearchParams({ ...(assetId ? { asset: assetId } : {}), ...(plan.gm_report_id ? { request: plan.gm_report_id } : {}), person: plan.actions[0].assignment!.assigned_by })}`}>Return to supervisor follow-up</a>}
    </section>)}
  </div>;
}
