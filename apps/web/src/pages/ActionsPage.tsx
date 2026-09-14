import { useEffect, useState } from 'react';

import type { PageId } from '../components/AppShell';
import { EmptyState, ErrorState, LoadingState } from '../components/ViewState';
import { TraceButton } from '../components/TraceabilityContext';
import { api, type ActionItem, type ActionPlan, type ActionStatus, type EffectivenessMetric, type EffectivenessReview } from '../lib/api';
import { actionsForAlert } from '../lib/demoWorkflow';
import { formatDate, humanize } from '../lib/format';
import { useApiResource } from '../lib/useApiResource';
import { actionTransitionLabel, nextActionStatus } from '../lib/workflow';

async function loadActions() {
  const alerts = await api.alerts('asset-ko-3201');
  if (!alerts[0]) return null;
  const [detail, effectiveness] = await Promise.all([
    api.alertDetail(alerts[0].alert_id),
    api.effectiveness(alerts[0].asset_id),
  ]);
  return { detail, effectiveness };
}

export function ActionsPage({ onNavigate }: { onNavigate: (page: PageId) => void }) {
  const [reportOpen, setReportOpen] = useState(false);
  const [busyActionId, setBusyActionId] = useState<string | null>(null);
  const [workflowError, setWorkflowError] = useState<string | null>(null);
  const resource = useApiResource('actions', loadActions);

  useEffect(() => {
    if (!reportOpen) return;
    const closeOnEscape = (event: KeyboardEvent) => event.key === 'Escape' && setReportOpen(false);
    window.addEventListener('keydown', closeOnEscape);
    return () => window.removeEventListener('keydown', closeOnEscape);
  }, [reportOpen]);

  if (resource.loading) return <LoadingState/>;
  if (resource.error) return <ErrorState message={resource.error}/>;

  const plans = resource.data ? actionsForAlert(resource.data.detail.alert.alert_id, resource.data.detail.action_plans, Boolean(resource.data.detail.rca)) : [];
  if (!plans.length) return <EmptyState title="No CAPA report created yet" description="An approved RCA hypothesis unlocks containment, corrective, and preventive work."/>;

  const plan = plans[0];
  const { effectiveness } = resource.data!;
  const caPaActions = plan.actions.filter((action) => action.action_type === 'CORRECTIVE' || action.action_type === 'PREVENTIVE');
  const pendingActions = caPaActions.filter((action) => action.status !== 'CLOSED');
  const nextDueAction = [...pendingActions].sort((left, right) => left.due_date.localeCompare(right.due_date))[0];

  async function advanceAction(actionId: string, status: ActionStatus) {
    const nextStatus = nextActionStatus(status);
    if (!nextStatus) return;
    setBusyActionId(actionId);
    setWorkflowError(null);
    try {
      await api.updateActionStatus(actionId, nextStatus, 'Action Owner', `Action advanced to ${humanize(nextStatus)} from the CAPA report.`);
      resource.reload();
    } catch (error) {
      setWorkflowError(error instanceof Error ? error.message : 'Unable to update action');
    } finally {
      setBusyActionId(null);
    }
  }

  const sourceSummary = resource.data?.detail.rca?.generation.executive_summary ?? 'Approved investigation links the equipment degradation to lubrication contamination.';
  const improvedSignals = effectiveness.metrics.filter((metric) => metric.outcome === 'IMPROVED').length;

  return <div className="decision-workspace action-workspace">
    <header className="decision-workspace-heading">
      <div><span>KO-3201 · Controlled records</span><h1>Corrective and preventive action</h1><p>Track the formal CAPA record created from the approved equipment investigation.</p></div>
      <div><b>{humanize(plan.status)}</b><TraceButton traceId="capa-plan">View supporting sources</TraceButton><button onClick={() => onNavigate('rca')}>Review approved RCA</button></div>
    </header>

    <section className="action-execution-summary">
      <div><span>Approved cause</span><strong>{humanize(plan.selected_cause_category)}</strong></div>
      <div><span>Observed recovery</span><strong>{improvedSignals} of {effectiveness.metrics.length} signals improved</strong></div>
      <div><span>Closure decision</span><strong>{effectiveness.closure_eligible ? 'Eligible for closure' : humanize(effectiveness.approval_status)}</strong></div>
    </section>

    <section className="capa-report-register">
      <header><div><span>CAPA register</span><h2>Formal action records</h2><p>Open the record to review its source, actions, evidence, and approval trail.</p></div><strong>1 record</strong></header>
      <div className="capa-register-columns"><span>Report</span><span>Equipment</span><span>Source</span><span>Target</span><span>Status</span><span/></div>
      <button className="capa-register-row" onClick={() => setReportOpen(true)}>
        <div><span>CAPA report</span><strong>Lubrication contamination on KO-3201</strong><small>{plan.plan_id}</small></div>
        <span>KO-3201</span><span>Approved RCA</span><time>{nextDueAction ? formatDate(nextDueAction.due_date) : 'Completed'}</time><b>{humanize(plan.status)}</b><i>›</i>
      </button>
    </section>

    <section className="capa-closure-note"><div><span>Effectiveness result</span><strong>{humanize(effectiveness.result)}</strong></div><p>{effectiveness.recovery_confirmed ? `All anchor signals improved across ${effectiveness.monitoring_periods} normal post-repair weeks with no recurrence detected. Formal closure remains a separate approval.` : effectiveness.explanation}</p><TraceButton traceId="recovery-effectiveness">View evidence</TraceButton></section>

    {reportOpen && <CapaReportModal plan={plan} effectiveness={effectiveness} sourceSummary={sourceSummary} busyActionId={busyActionId} onAdvance={advanceAction} onClose={() => setReportOpen(false)}/>}
    {workflowError && <p className="workflow-error">{workflowError}</p>}
  </div>;
}

function CapaReportModal({ plan, effectiveness, sourceSummary, busyActionId, onAdvance, onClose }: { plan: ActionPlan; effectiveness: EffectivenessReview; sourceSummary: string; busyActionId: string | null; onAdvance: (actionId: string, status: ActionStatus) => void; onClose: () => void }) {
  const containment = plan.actions.find((action) => action.action_type === 'CONTAINMENT');
  const plannedActions = plan.actions.filter((action) => action.action_type !== 'CONTAINMENT');
  const issueDate = containment?.due_date ?? plannedActions[0]?.due_date ?? 'Not recorded';

  return <div className="capa-report-overlay" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
    <article className="capa-report-modal" role="dialog" aria-modal="true" aria-labelledby="capa-report-title">
      <header className="capa-document-header">
        <div><span>CALIBER · Manufacturing Reliability</span><h2 id="capa-report-title">Corrective and Preventive Action Report</h2></div>
        <button onClick={onClose} aria-label="Close CAPA report">×</button>
      </header>

      <div className="capa-report-scroll">
        <section className="capa-document-control">
          <DocumentField label="Report number" value={plan.plan_id}/><DocumentField label="Revision" value="01"/><DocumentField label="Status" value={humanize(plan.status)}/><DocumentField label="Issue date" value={formatDate(issueDate)}/>
          <DocumentField label="Equipment" value="KO-3201"/><DocumentField label="Source record" value={plan.rca_id}/><DocumentField label="Record type" value="Equipment problem"/><DocumentField label="Classification" value="Reliability / Process safety"/>
        </section>

        <ReportSection number="1" title="Problem and investigation basis">
          <ReportLine label="Approved root cause" value={humanize(plan.selected_cause_category)}/>
          <ReportLine label="Investigation conclusion" value={sourceSummary}/>
          <ReportLine label="CAPA objective" value="Restore KO-3201 lubrication integrity and prevent recurrence of the confirmed degradation pattern on comparable equipment."/>
        </ReportSection>

        <ReportSection number="2" title="Immediate correction and containment">
          {containment ? <ActionStatement action={containment}/> : <p>No containment action recorded.</p>}
        </ReportSection>

        <ReportSection number="3" title="Corrective and preventive action plan">
          <div className="capa-action-table">
            <div className="capa-action-table-head"><span>Type and action</span><span>Owner</span><span>Target</span><span>Status</span></div>
            {plannedActions.map((action) => <ActionTableRow action={action} busy={busyActionId === action.action_id} key={action.action_id} onAdvance={onAdvance}/>)}
          </div>
        </ReportSection>

        <ReportSection number="4" title="Implementation and change control">
          {plannedActions.map((action) => <div className="capa-control-record" key={action.action_id}><strong>{humanize(action.action_type)}</strong><dl><div><dt>Affected scope</dt><dd>{action.affected_scope ?? 'Affected equipment'}</dd></div><div><dt>Execution route</dt><dd>{action.execution_route ?? 'Managed action plan'}</dd></div><div><dt>Change control</dt><dd>{action.change_control ?? 'Review before execution'}</dd></div></dl></div>)}
        </ReportSection>

        <ReportSection number="5" title="Verification of implementation and effectiveness">
          <EffectivenessEvidence review={effectiveness}/>
          <div className="capa-verification-table"><div className="capa-verification-head"><span>Action</span><span>Implementation evidence</span><span>Effectiveness criteria</span><span>Action status</span></div>{plannedActions.map((action) => <div className="capa-verification-row" key={action.action_id}><strong>{humanize(action.action_type)}</strong><p>{action.completion_criteria}</p><p>{action.effectiveness_check}</p><b>{humanize(action.status)}</b></div>)}</div>
        </ReportSection>

        <ReportSection number="6" title="Approval and closure record">
          <div className="capa-approval-grid"><DocumentField label="RCA disposition" value="Approved"/><DocumentField label="CAPA disposition" value={humanize(plan.status)}/><DocumentField label="Effectiveness review" value={humanize(effectiveness.result)}/><DocumentField label="Closure authorization" value={effectiveness.closure_eligible ? 'Eligible' : 'Pending approval'}/></div>
          <ActionHistory actions={plan.actions}/>
        </ReportSection>
      </div>

      <footer><span>Controlled report · Generated from governed RCA and action records</span><button onClick={onClose}>Close report</button></footer>
    </article>
  </div>;
}

function EffectivenessEvidence({ review }: { review: EffectivenessReview }) {
  return <div className="capa-effectiveness-evidence">
    <header><div><span>Post-repair monitoring</span><strong>{humanize(review.result)}</strong></div><p>{review.monitoring_periods} normal weekly observations · {review.recurrence_detected ? 'Recurrence detected' : 'No recurrence detected'}</p><TraceButton traceId="recovery-effectiveness">Source evidence</TraceButton></header>
    <div className="capa-recovery-grid">{review.metrics.map((metric) => <RecoveryMetric metric={metric} key={metric.signal_key}/>)}</div>
    <footer><span>Monitoring window</span><strong>{formatDate(review.monitoring_start)} – {formatDate(review.monitoring_end)}</strong><p>{review.explanation}</p></footer>
  </div>;
}

function RecoveryMetric({ metric }: { metric: EffectivenessMetric }) {
  const scale = Math.max(Math.abs(metric.before), Math.abs(metric.after), 1);
  return <article className="capa-recovery-metric">
    <header><strong>{metric.label}</strong><b>{humanize(metric.outcome)}</b></header>
    <div><span>Before</span><i><b style={{ width: `${Math.abs(metric.before) / scale * 100}%` }}/></i><strong>{metric.before.toLocaleString()} {metric.unit}</strong></div>
    <div><span>After</span><i><b style={{ width: `${Math.abs(metric.after) / scale * 100}%` }}/></i><strong>{metric.after.toLocaleString()} {metric.unit}</strong></div>
  </article>;
}

function ActionStatement({ action }: { action: ActionItem }) {
  return <div className="capa-action-statement"><p>{action.guidance}</p><dl><div><dt>Responsible owner</dt><dd>{action.owner_role}</dd></div><div><dt>Due date</dt><dd>{formatDate(action.due_date)}</dd></div><div><dt>Status</dt><dd>{humanize(action.status)}</dd></div></dl><ReportLine label="Evidence required" value={action.completion_criteria}/></div>;
}

function ActionTableRow({ action, busy, onAdvance }: { action: ActionItem; busy: boolean; onAdvance: (actionId: string, status: ActionStatus) => void }) {
  const nextStatus = nextActionStatus(action.status);
  return <div className="capa-action-table-row"><div><span>{humanize(action.action_type)}</span><strong>{action.title}</strong><p>{action.guidance}</p></div><span>{action.owner_role}</span><time>{formatDate(action.due_date)}</time><div><b>{humanize(action.status)}</b>{nextStatus && <button disabled={busy} onClick={() => onAdvance(action.action_id, action.status)}>{busy ? 'Updating…' : actionTransitionLabel(nextStatus)}</button>}</div></div>;
}

function ActionHistory({ actions }: { actions: ActionItem[] }) {
  const history = actions.flatMap((action) => (action.status_history ?? []).map((entry) => ({ ...entry, actionType: action.action_type })));
  return <div className="capa-report-history"><h4>Record history</h4>{history.length ? history.map((entry, index) => <div key={`${entry.occurred_at}-${index}`}><time>{formatDate(entry.occurred_at)}</time><p><strong>{humanize(entry.actionType)} · {entry.actor}</strong>{entry.note}</p><b>{humanize(entry.new_status)}</b></div>) : <p>No recorded transition yet.</p>}</div>;
}

function DocumentField({ label, value }: { label: string; value: string }) {
  return <div className="capa-document-field"><span>{label}</span><strong>{value}</strong></div>;
}

function ReportLine({ label, value }: { label: string; value: string }) {
  return <div className="capa-report-line"><strong>{label}</strong><p>{value}</p></div>;
}

function ReportSection({ number, title, children }: { number: string; title: string; children: React.ReactNode }) {
  return <section className="capa-report-section"><header><span>{number}</span><h3>{title}</h3></header><div>{children}</div></section>;
}
