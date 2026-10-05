import { useState } from 'react';
import type { PageId } from '../components/AppShell';
import { EquipmentOperatorEvidence } from '../components/EquipmentOperatorEvidence';
import { EquipmentVerificationReport, equipmentDate } from '../components/EquipmentVerificationReport';
import { LoadingState } from '../components/ViewState';
import { api, selectWorkflowSession } from '../lib/api';
import { canVerifyEquipment, equipmentChecks, type EquipmentCheck } from '../lib/equipmentReview';
import { humanize } from '../lib/format';
import type { ProductionReviewDecision } from '../lib/productionReview';
import { useApiResource } from '../lib/useApiResource';
import '../production-review.css';
import '../equipment-operator.css';
import '../components/case-packet.css';

const outcomes: Array<{ value: ProductionReviewDecision; label: string }> = [
  { value: 'APPROVED', label: 'Verified' }, { value: 'CHANGES_REQUESTED', label: 'Correction required' }, { value: 'UNABLE_TO_VALIDATE', label: 'Unable to verify' },
];

export function EquipmentReviewPage({ assetId, requestId, personId, onNavigate }: { assetId?: string; requestId?: string; personId?: string; onNavigate: (page: PageId) => void }) {
  const resource = useApiResource(`equipment-review:${requestId ?? ''}:${personId ?? ''}`, async () => {
    const session = await selectWorkflowSession(personId);
    if (!requestId) throw new Error('Open an equipment verification request from your inbox');
    const report = await api.equipmentReport(requestId);
    if (assetId && report.asset.asset_id !== assetId) throw new Error('Report does not belong to the selected equipment');
    return { session, report };
  });
  const [checks, setChecks] = useState<EquipmentCheck[]>(equipmentChecks.map((item) => ({ check: item.id, result: 'MISSING', finding: '', reference: '' })));
  const [decision, setDecision] = useState<ProductionReviewDecision>('APPROVED');
  const [note, setNote] = useState('');
  const [context, setContext] = useState('');
  const [attested, setAttested] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (!resource.data) return resource.loading ? <LoadingState/> : <div className="production-review-error"><h1>Equipment report unavailable</h1><p role="alert">{resource.error}</p><button onClick={resource.reload}>Retry</button></div>;
  const { report, session } = resource.data;
  const supervisor = session.current.role === 'SUPERVISOR';
  const returnToCase = `#delegation?${new URLSearchParams({ asset: report.asset.asset_id, person: report.created_by })}`;
  const mayRespond = report.status === 'SENT' && session.current.person_id === report.recipient_id && session.current.role === 'OPERATOR';
  const valid = canVerifyEquipment(decision, checks, note, context, attested);
  function updateCheck(index: number, change: Partial<EquipmentCheck>) { setChecks((current) => current.map((item, position) => position === index ? { ...item, ...change } : item)); }
  async function respond() {
    if (busy || !valid || !mayRespond) return;
    setBusy(true); setError(null);
    try {
      await api.respondEquipmentReport(report.report_id, { decision, note: note.trim(), human_context: context.trim(), attested, expected_revision: report.revision, checks: checks.map((item) => ({ ...item, finding: item.finding.trim(), reference: item.reference?.trim() || null })) });
      resource.reload();
    } catch (failure) { setError(failure instanceof Error ? failure.message : 'Unable to save equipment verification'); }
    finally { setBusy(false); }
  }
  return <div className="decision-workspace production-review-page equipment-review-page">
    <header className="decision-workspace-heading"><div><span>{humanize(session.current.role)} · {report.asset.plant_id} / Equipment</span><h1>Equipment evidence review</h1><p>Check this report version against equipment records. Scope verification is not root-cause confirmation.</p></div>{session.can_switch && !supervisor ? <a className="scope-return-link" href={returnToCase}>Return to case packet</a> : <button onClick={() => onNavigate(supervisor ? 'delegation' : 'operator-equipment')}>Back to {supervisor ? 'requests' : 'equipment workspace'}</button>}</header>
    <EquipmentVerificationReport report={report}/>
    <div className="production-evidence-heading"><h2>Supporting evidence</h2><p>Fixed snapshot for {report.asset.tag} · v{report.version} · {equipmentDate(report.evidence.as_of)}.</p></div>
    <div className="operator-review-content"><EquipmentOperatorEvidence evidence={report.evidence}/>
      <section className="production-review-card operator-verification-form"><header><div><span>Equipment scope only</span><h2>{report.review ? 'Verification recorded' : 'Your evidence checks'}</h2></div></header>
        {error && <div role="alert"><p>{error}</p><button onClick={resource.reload}>Reload report</button></div>}
        {report.review ? <div className="production-decision-receipt" role="status"><h3>{outcomes.find((item) => item.value === report.review?.decision)?.label}</h3><p>{report.review.note}</p><p>{report.review.human_context}</p><p>{equipmentDate(report.review.at)} · {report.review.actor_id}</p><p>Saved and available to the supervisor. This does not approve RCA or authorize equipment operation.</p>{session.can_switch && !supervisor && <a className="scope-return-link" href={returnToCase}>Return to case packet</a>}</div> : !mayRespond ? <p>{report.status === 'DRAFT' ? 'This draft has not been sent to the operator.' : 'Read-only: the assigned equipment operator must complete this verification.'}</p> : <form onSubmit={(event) => { event.preventDefault(); void respond(); }}><fieldset disabled={busy || resource.loading}>
          <p>Each finding needs the record you checked. Use Missing when evidence is unavailable; do not treat an unavailable inspection as a normal result.</p>
          <div className="operator-check-grid">{equipmentChecks.map((item, index) => <section className="operator-check" key={item.id}><h3>{index + 1}. {item.title}</h3><p>{item.prompt}</p><label>Check result<select aria-label={`${item.title} result`} value={checks[index].result} onChange={(event) => updateCheck(index, { result: event.target.value as EquipmentCheck['result'] })}><option value="MISSING">Missing evidence</option><option value="VERIFIED">Verified against source</option><option value="ISSUE">Discrepancy found</option></select></label><label>Finding<textarea aria-label={`${item.title} finding`} required rows={3} maxLength={2000} value={checks[index].finding} onChange={(event) => updateCheck(index, { finding: event.target.value })}/></label><label>Source record reference<input aria-label={`${item.title} reference`} required={checks[index].result !== 'MISSING'} maxLength={2000} value={checks[index].reference ?? ''} placeholder="Logbook entry, instrument record or lab reference" onChange={(event) => updateCheck(index, { reference: event.target.value })}/></label></section>)}</div>
          <label>Operating context<textarea aria-label="Operating context note" required rows={3} maxLength={2000} value={context} placeholder="Actual operating mode, load changes and relevant field observations." onChange={(event) => setContext(event.target.value)}/></label>
          <fieldset className="operator-decision-options"><legend>Scope verification outcome</legend>{outcomes.map((item) => <label key={item.value} className={`production-outcome ${decision === item.value ? 'selected' : ''}`}><input type="radio" name="equipment-outcome" checked={decision === item.value} onChange={() => setDecision(item.value)}/>{item.label}</label>)}</fieldset>
          <label>Response to supervisor<textarea aria-label="Response to supervisor" required rows={3} maxLength={2000} value={note} onChange={(event) => setNote(event.target.value)}/></label>
          {decision === 'APPROVED' && <label className="production-attestation"><input type="checkbox" checked={attested} onChange={(event) => setAttested(event.target.checked)}/>I checked all four areas for this report version against the stated equipment references.</label>}
          <p className="operator-submit-guidance">{decision === 'APPROVED' ? 'Verified requires four verified checks, source references and your attestation.' : decision === 'CHANGES_REQUESTED' ? 'Correction requires at least one discrepancy finding.' : 'Unable to verify requires at least one missing-evidence finding.'}</p>
          <button className="production-submit" disabled={!valid || busy || resource.loading}>{busy ? 'Saving…' : 'Send verification to supervisor'}</button>
        </fieldset></form>}
      </section>
    </div>
  </div>;
}
