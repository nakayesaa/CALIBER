import { useState, type FormEvent } from 'react';
import { ActionWork } from './CoordinationPanel';
import { api, type ActionPlan, type WorkflowSession } from '../lib/api';
import { gmActionRows, type GmReport } from '../lib/gmReview';
import { humanize } from '../lib/format';

export function GmActionAssignments({ report, plans, session, onChange, loading }: {
  report: GmReport; plans: ActionPlan[]; session: WorkflowSession; onChange: () => void; loading: boolean;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const rows = gmActionRows(report, plans);
  async function run(command: () => Promise<unknown>) {
    if (busy) return;
    setBusy(true); setError(null);
    try { await command(); onChange(); }
    catch (failure) { setError(failure instanceof Error ? failure.message : 'Unable to save assignment'); }
    finally { setBusy(false); }
  }
  function assign(event: FormEvent<HTMLFormElement>, sourceId: string) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const action = rows.find(row => row.source.action_id === sourceId)?.action;
    void run(() => api.assignGmAction(report.report_id, sourceId, {
      person_id: String(form.get('person')), due_date: String(form.get('due')),
      expected_status: action?.status ?? 'PROPOSED', expected_assigned_to: action?.assignment?.person_id ?? null,
      expected_revision: action?.assignment?.revision ?? 0, note: String(form.get('note')).trim(),
    }));
  }
  const minimumDate = new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Jakarta' }).format(new Date());
  return <section className="production-review-card coordination-panel gm-assignment-panel" aria-label="Assign approved follow-up">
    <header><div><span>Next step · Supervisor</span><h2>Assign corrective and preventive work</h2></div><span className="production-request-status approved">GM approved</span></header>
    <p>Select a qualified owner, target date and instruction. These are new execution tasks; historical progress in the proposal is not carried forward.</p>
    {error && <p role="alert">{error}</p>}
    {!rows.length && <p>No corrective or preventive proposal is attached to this report. Prepare the action proposal before assignment.</p>}
    <fieldset disabled={busy || loading} className="gm-task-list">
      {rows.map(({ source, action }) => {
        const owners = session.participants.filter(person => person.owner_roles.includes(source.owner_role));
        return <article className="gm-task" key={source.action_id}>
          {action?.assignment ? <><ActionWork action={action} session={session} verified run={run}/>{session.can_switch && <a className="scope-return-link" href={`#assigned-actions?${new URLSearchParams({ asset: report.asset.asset_id, person: action.assignment.person_id })}`}>Open assigned owner workspace</a>}</> : <>
            <header><div><span>{humanize(source.action_type)} · {humanize(source.priority)}</span><h3>{source.title}</h3></div><span className="production-request-status">Not assigned</span></header>
            <p>{source.guidance}</p><p><strong>Completion evidence:</strong> {source.completion_criteria}</p>
            <form onSubmit={event => assign(event, source.action_id)} className="gm-task-form">
              <label>Responsible owner<select name="person" aria-label={`${source.action_type} responsible owner`} required>{owners.map(owner => <option key={owner.person_id} value={owner.person_id}>{owner.display_name} · {source.owner_role}</option>)}</select></label>
              <label>Target date<input name="due" aria-label={`${source.action_type} target date`} type="date" min={minimumDate} defaultValue={minimumDate} required/></label>
              <label className="gm-task-instruction">Assignment instruction<textarea name="note" aria-label={`${source.action_type} assignment instruction`} required rows={2} maxLength={2000} defaultValue={source.guidance}/></label>
              {!owners.length && <p>No participant is configured with the required responsibility: {source.owner_role}.</p>}
              <button className="production-submit" disabled={!owners.length}>Assign {humanize(source.action_type).toLowerCase()} action</button>
            </form>
          </>}
        </article>;
      })}
    </fieldset>
  </section>;
}
