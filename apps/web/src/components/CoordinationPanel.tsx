import { useEffect, useState, type FormEvent } from 'react';

import { api, type ActionItem, type AlertDetail, type CaseReview, type ExecutionEvidenceInput, type RequirementCheck, type WorkflowSession } from '../lib/api';
import { formatDate, humanize } from '../lib/format';
import { useApiResource } from '../lib/useApiResource';

type RunCommand = (command: () => Promise<unknown>) => void;
const requirements: RequirementCheck['requirement'][] = ['PROCEDURE', 'AUTHORIZATION', 'CHANGE_CONTROL'];

function formValues(event: FormEvent<HTMLFormElement>) {
  event.preventDefault();
  return new FormData(event.currentTarget);
}

function text(data: FormData, name: string) {
  return String(data.get(name) ?? '').trim();
}

export function CoordinationPanel({ detail, onChange, refreshing = false }: { detail: AlertDetail; onChange: () => void; refreshing?: boolean }) {
  const [personId, setPersonId] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const resource = useApiResource(`coordination-${detail.alert.alert_id}-${personId}`, async () => {
    const [session, review] = await Promise.all([api.workflowSession(), api.caseReview(detail.alert.alert_id)]);
    return { session, review };
  });
  useEffect(() => () => api.setWorkflowPerson(null), []);

  async function run(command: () => Promise<unknown>) {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await command();
      resource.reload();
      onChange();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Unable to save the record');
    } finally {
      setBusy(false);
    }
  }

  if (!resource.data) return <section className="coordination-panel"><p role="status">{resource.error ?? 'Loading coordination record…'}</p></section>;
  const { session, review } = resource.data;
  const supervisor = session.current.role === 'SUPERVISOR';
  return <section className="coordination-panel">
    <header><div><span>{detail.alert.asset_id.replace('asset-', '').toUpperCase()} · Human decision record</span><h2>Validate, delegate, verify</h2><p>Cross-check the issue before authorizing work. Track the named owner and evidence through closure.</p></div>
      {session.can_switch ? <label>Local demo role<select aria-label="Local demo role" disabled={busy || resource.loading || refreshing} value={session.current.person_id} onChange={(event) => { api.setWorkflowPerson(event.target.value); setPersonId(event.target.value); setError(null); }}>
        {session.participants.map((person) => <option value={person.person_id} key={person.person_id}>{person.display_name}</option>)}
      </select></label> : <p>{session.current.display_name} · {humanize(session.current.role)}</p>}
    </header>
    <p className="coordination-sop">Emergency response follows the site SOP immediately. This record tracks review and follow-up; it does not authorize equipment operation.</p>
    {error && <div><p role="alert" className="workflow-error">{error}</p><button disabled={busy || refreshing} onClick={() => { resource.reload(); onChange(); setError(null); }}>Reload current record</button></div>}
    <fieldset disabled={busy || resource.loading || refreshing}>
      <CrossCheckForm review={review} session={session} run={run}/>
      {review.status === 'VERIFIED' && <details className="coordination-record" open={!detail.action_plans.length}>
        <summary><strong>RCA approval and action authorization</strong><span>{detail.rca ? humanize(detail.rca.status) : 'Not created'}</span></summary>
        <p>Approve a specific hypothesis after reviewing its supporting and contradicting evidence in the RCA workspace.</p>
        {detail.rca ? <>
          <p>{detail.rca.generation.executive_summary}</p>
          {supervisor && <form onSubmit={(event) => {
            const values = formValues(event);
            const rca = detail.rca!;
            if (rca.status === 'APPROVED') run(() => api.createActionPlan(rca.rca_id, text(values, 'hypothesis')));
            else run(() => api.updateRcaStatus(rca.rca_id, rca.status === 'UNDER_REVIEW' ? 'APPROVED' : 'UNDER_REVIEW', text(values, 'note')));
          }}>
            {detail.rca.status === 'APPROVED' && !detail.action_plans.length ? <label>Approved hypothesis<select name="hypothesis" required>{detail.rca.generation.hypotheses.map((hypothesis) => <option key={hypothesis.hypothesis_id} value={hypothesis.hypothesis_id}>{hypothesis.title}</option>)}</select></label> : null}
            {['AI_DRAFT', 'UNDER_REVIEW'].includes(detail.rca.status) && <label>Review rationale<textarea name="note" required maxLength={2000}/></label>}
            {detail.rca.status === 'AI_DRAFT' && <button>Start RCA review</button>}
            {detail.rca.status === 'UNDER_REVIEW' && <button>Approve reviewed RCA</button>}
            {detail.rca.status === 'APPROVED' && !detail.action_plans.length && <button>Create action plan</button>}
          </form>}
        </> : <p>{supervisor ? <button onClick={() => run(() => api.generateRca(detail.alert.alert_id, 'prepared'))}>Create working RCA from the prepared evidence</button> : 'A supervisor can create and review the working RCA record.'}</p>}
      </details>}
      {detail.action_plans.flatMap((plan) => plan.actions).map((action) => <ActionWork key={action.action_id} action={action} session={session} verified={review.status === 'VERIFIED'} run={run}/>)}
    </fieldset>
    {busy && <p role="status">Saving controlled record…</p>}
  </section>;
}

function CrossCheckForm({ review, session, run }: { review: CaseReview; session: WorkflowSession; run: RunCommand }) {
  const submit = session.current.role === 'OPERATOR' && ['DRAFT', 'CHANGES_REQUESTED'].includes(review.status);
  const verify = session.current.role === 'SUPERVISOR' && review.status === 'PENDING_REVIEW';
  return <details className="coordination-record" open={review.status !== 'VERIFIED'}>
    <summary><strong>Issue cross-check</strong><span>{humanize(review.status)}</span></summary>
    {review.note && <p>{review.note}</p>}
    {review.references.length > 0 && <ul>{review.references.map((reference) => <li key={reference}>{reference}</li>)}</ul>}
    {review.human_context && <p><strong>Reported field context:</strong> {review.human_context}</p>}
    {submit && <form onSubmit={(event) => {
      const values = formValues(event);
      run(() => api.submitCrossCheck(review.alert_id, { note: text(values, 'note'), references: text(values, 'references').split('\n').map((value) => value.trim()).filter(Boolean), human_context: text(values, 'context'), expected_revision: review.revision }));
    }}>
      <label>What did you cross-check?<textarea name="note" required maxLength={2000} defaultValue={review.note}/></label>
      <label>Source or record references, one per line<textarea name="references" required defaultValue={review.references.join('\n')} placeholder="Sample ID, source record, inspection report or shift log"/></label>
      <label>Reported field context (optional)<textarea name="context" maxLength={2000} defaultValue={review.human_context} placeholder="Observed conditions only, not inferred human fault"/></label>
      <button>Submit for supervisor review</button>
    </form>}
    {verify && <form onSubmit={(event) => {
      const values = formValues(event);
      run(() => api.reviewCrossCheck(review.alert_id, { decision: text(values, 'decision') as 'VERIFIED' | 'CHANGES_REQUESTED', note: text(values, 'note'), expected_revision: review.revision }));
    }}>
      <label>Review decision<select name="decision"><option value="VERIFIED">Verify cross-check</option><option value="CHANGES_REQUESTED">Return to operator for clarification</option></select></label>
      <label>Review rationale<textarea name="note" required maxLength={2000}/></label><button>Record review</button>
    </form>}
    {review.history.length > 0 && <details><summary>Review trail</summary><ol>{review.history.map((entry, index) => <li key={index}><strong>{humanize(entry.status)} · {entry.actor_id}</strong><p>{entry.note}</p><time>{formatDate(entry.occurred_at)}</time></li>)}</ol></details>}
  </details>;
}

function ActionWork({ action, session, verified, run }: { action: ActionItem; session: WorkflowSession; verified: boolean; run: RunCommand }) {
  const supervisor = session.current.role === 'SUPERVISOR';
  const own = action.assignment?.person_id === session.current.person_id;
  const ready = own && action.assignment?.accepted_at && !action.assignment.blocked_reason;
  const canAssign = supervisor && (action.status === 'APPROVED' || (action.status === 'IN_PROGRESS' && !action.assignment));
  const assignees = session.participants.filter((person) => person.owner_roles.includes(action.owner_role));
  const reviewer = supervisor && !own && action.status === 'EFFECTIVENESS_REVIEW';
  const execution = ready && ['APPROVED', 'IN_PROGRESS'].includes(action.status);
  const owner = session.participants.find((person) => person.person_id === action.assignment?.person_id);
  return <details className="coordination-record">
    <summary><strong>{humanize(action.action_type)} · {action.title}</strong><span>{humanize(action.status)}</span></summary>
    <p>{action.guidance}</p><p><strong>{owner?.display_name ?? `Unassigned · ${action.owner_role}`}</strong> · Due {formatDate(action.due_date)}</p>
    {action.assignment && <p>{action.assignment.blocked_reason ? `Blocked: ${action.assignment.blocked_reason}` : action.assignment.accepted_at ? 'Assignment accepted' : 'Awaiting PIC acceptance'}</p>}
    {action.completion && <p><strong>Completion evidence:</strong> {action.completion.reference} · {action.completion.finding}</p>}
    {action.verification && <p><strong>{humanize(action.verification.outcome)}:</strong> {action.verification.reference} · {action.verification.finding}</p>}
    {!verified ? <p>Supervisor verification of the issue cross-check is required before authorization.</p> : <>
      {supervisor && action.status === 'PROPOSED' && <form onSubmit={(event) => { const values = formValues(event); run(() => api.updateActionStatus(action.action_id, 'APPROVED', text(values, 'note'), undefined, action.revision ?? 0)); }}><label>Authorization rationale<textarea name="note" required maxLength={2000}/></label><button>Authorize action</button></form>}
      {canAssign && <form onSubmit={(event) => {
        const values = formValues(event);
        run(() => api.assignAction(action.action_id, { person_id: text(values, 'person'), due_date: text(values, 'due'), expected_status: action.status, expected_assigned_to: action.assignment?.person_id ?? null, expected_revision: action.assignment?.revision ?? 0, note: text(values, 'note') }));
      }}>
        <label>Named PIC<select name="person" defaultValue={action.assignment?.person_id} required>{assignees.map((person) => <option key={person.person_id} value={person.person_id}>{person.display_name}</option>)}</select></label>
        <label>Target date<input name="due" type="date" defaultValue={action.due_date.slice(0, 10)} required/></label><label>Assignment instruction<textarea name="note" required maxLength={2000}/></label><button>{action.assignment ? 'Update delegation' : 'Delegate to PIC'}</button>
      </form>}
      {own && ['APPROVED', 'IN_PROGRESS'].includes(action.status) && <form onSubmit={(event) => {
        const values = formValues(event);
        run(() => api.respondToAssignment(action.action_id, { decision: text(values, 'decision') as 'ACCEPT' | 'BLOCK', note: text(values, 'note'), expected_revision: action.assignment!.revision }));
      }}><label>Assignment response<select name="decision"><option value="ACCEPT">Accept / resolve blocker</option><option value="BLOCK">Record a blocker</option></select></label><label>Response and context<textarea name="note" required maxLength={2000}/></label><button>Record PIC response</button></form>}
      {(execution || reviewer) && <form onSubmit={(event) => {
        const values = formValues(event);
        const evidence: ExecutionEvidenceInput = { reference: text(values, 'reference') || undefined, finding: text(values, 'finding') || undefined };
        if (!action.requirements?.length) evidence.requirements = requirements.map((requirement) => ({ requirement, disposition: text(values, `${requirement}-disposition`) as RequirementCheck['disposition'], reference: text(values, `${requirement}-reference`), note: text(values, `${requirement}-note`) }));
        const target = reviewer ? text(values, 'decision') as 'CLOSED' | 'IN_PROGRESS' : action.status === 'APPROVED' ? 'IN_PROGRESS' : 'EFFECTIVENESS_REVIEW';
        run(() => api.updateActionStatus(action.action_id, target, text(values, 'note'), evidence, action.revision ?? 0));
      }}>
        {!action.requirements?.length && <div className="coordination-checks"><h3>Execution requirements</h3><p>Reference the applicable site documents. A not-applicable decision also needs a recorded justification.</p>{requirements.map((requirement) => <div key={requirement}><strong>{humanize(requirement)}</strong><label>Disposition<select name={`${requirement}-disposition`}><option value="CONFIRMED">Confirmed against document</option><option value="NOT_APPLICABLE">Not applicable with justification</option></select></label><label>Document reference<input name={`${requirement}-reference`} required maxLength={2000}/></label><label>Confirmation or justification<textarea name={`${requirement}-note`} required maxLength={2000}/></label></div>)}</div>}
        {reviewer && <label>Effectiveness decision<select name="decision"><option value="CLOSED">Effective: close after independent verification</option><option value="IN_PROGRESS">Not effective: return for rework</option></select></label>}
        {(action.status !== 'APPROVED' || reviewer) && <><p>{reviewer ? action.effectiveness_check : action.completion_criteria}</p><label>{reviewer ? 'Verification record reference' : 'Completion evidence reference'}<input name="reference" required maxLength={2000}/></label><label>Evidence finding<textarea name="finding" required maxLength={2000}/></label></>}
        <label>Decision rationale<textarea name="note" required maxLength={2000}/></label><button>{reviewer ? 'Record independent verification' : action.status === 'APPROVED' ? 'Start approved work' : 'Submit completion for review'}</button>
      </form>}
    </>}
    {!!action.requirements?.length && <details><summary>Documented requirements</summary><ul>{action.requirements.map((check) => <li key={check.requirement}><strong>{humanize(check.requirement)} · {humanize(check.disposition)}</strong><p>{check.reference} · {check.note}</p></li>)}</ul></details>}
    {!!action.evidence_history?.length && <details><summary>Completion and verification evidence</summary><ol>{action.evidence_history.map((entry, index) => <li key={index}><strong>{humanize(entry.outcome)} · {entry.actor_id}</strong><p>{entry.reference} · {entry.finding}</p><time>{formatDate(entry.occurred_at)}</time></li>)}</ol></details>}
    {(action.assignment?.history.length || action.status_history?.length) ? <details><summary>Accountability trail</summary><ol>{[...(action.assignment?.history ?? []), ...(action.status_history ?? []).map((entry) => ({ status: entry.new_status, actor_id: entry.actor, occurred_at: entry.occurred_at, note: entry.note, recipient_id: null, due_date: null }))].sort((a, b) => a.occurred_at.localeCompare(b.occurred_at)).map((entry, index) => <li key={index}><strong>{humanize(entry.status)} · {entry.actor_id}</strong>{entry.recipient_id && <p>Assigned to {entry.recipient_id} · Due {formatDate(entry.due_date ?? '')}</p>}<p>{entry.note}</p><time>{formatDate(entry.occurred_at)}</time></li>)}</ol></details> : null}
  </details>;
}
