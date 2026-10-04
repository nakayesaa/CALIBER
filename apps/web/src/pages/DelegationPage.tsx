import { useState, type FormEvent } from 'react';
import type { PageId } from '../components/AppShell';
import { ProductionVerificationReport } from '../components/ProductionVerificationReport';
import { EquipmentVerificationReport } from '../components/EquipmentVerificationReport';
import { CasePacketPanel } from '../components/CasePacketPanel';
import { LoadingState } from '../components/ViewState';
import { api, selectWorkflowSession } from '../lib/api';
import { PRIMARY_ASSET_ID } from '../lib/appConfig';
import { formatDate, humanize } from '../lib/format';
import { verificationReport } from '../lib/productionReview';
import { scopeReportLink, type ScopeReport } from '../lib/equipmentReview';
import { useApiResource } from '../lib/useApiResource';
import '../production-review.css';

export function DelegationPage({ assetId = PRIMARY_ASSET_ID, alertId, personId, onNavigate }: {
  assetId?: string; alertId?: string; personId?: string; onNavigate: (page: PageId) => void;
}) {
  const resource = useApiResource(`delegation:${personId ?? 'supervisor'}`, async () => {
    const session = await selectWorkflowSession(personId ?? 'demo-supervisor');
    const [production, equipment, assets, packets, gmReports] = await Promise.all([api.productionReports(), api.equipmentReports(), api.assets(), session.current.role === 'SUPERVISOR' ? api.casePackets() : Promise.resolve([]), session.current.role === 'SUPERVISOR' ? api.gmReports() : Promise.resolve([])]);
    return { session, reports: [...equipment, ...production].sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at)), assets, packets, gmReports };
  });
  const [selectedAsset, setSelectedAsset] = useState(assetId);
  const [scope, setScope] = useState<'EQUIPMENT' | 'PRODUCTION'>('EQUIPMENT');
  const [draft, setDraft] = useState<ScopeReport | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [requestId, setRequestId] = useState(() => crypto.randomUUID());
  const alerts = useApiResource(`delegation-alerts:${selectedAsset}`, () => api.alerts(selectedAsset));
  if (resource.loading && !resource.data) return <LoadingState/>;
  if (!resource.data) return <div className="production-review-error"><h1>Verification requests unavailable</h1><p role="alert">{resource.error}</p><button onClick={resource.reload}>Retry</button></div>;
  const { session, reports, assets } = resource.data;
  const supervisor = session.current.role === 'SUPERVISOR';
  const asset = assets.find((item) => item.asset_id === selectedAsset);
  const operators = session.participants.filter((person) => person.role === 'OPERATOR' && person.scopes.includes(scope) && person.plant_ids.includes(asset?.plant_id ?? '') && (scope !== 'EQUIPMENT' || person.asset_ids.includes(selectedAsset)));

  async function prepare(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const form = new FormData(event.currentTarget);
    setBusy(true); setError(null);
    try {
      const payload = {
        request_id: requestId, asset_id: selectedAsset,
        recipient_id: String(form.get('recipient')),
        due_at: new Date(`${form.get('deadline')}:00+07:00`).toISOString(),
        note: String(form.get('instruction')).trim(),
        alert_id: String(form.get('alert')),
      };
      const report = scope === 'EQUIPMENT' ? await api.createEquipmentReport(payload) : await api.createProductionReport(payload);
      setDraft(report); setRequestId(crypto.randomUUID()); resource.reload();
    } catch (failure) { setError(failure instanceof Error ? failure.message : 'Unable to prepare report'); }
    finally { setBusy(false); }
  }

  async function send() {
    if (!draft || busy) return;
    setBusy(true); setError(null);
    try { setDraft(await (draft.scope === 'EQUIPMENT' ? api.sendEquipmentReport(draft.report_id, draft.revision) : api.sendProductionReport(draft.report_id, draft.revision))); resource.reload(); }
    catch (failure) { setError(failure instanceof Error ? failure.message : 'Unable to send report'); }
    finally { setBusy(false); }
  }

  return <div className="decision-workspace production-review-page production-delegation-page">
    <header className="decision-workspace-heading"><div><span>{supervisor ? 'Supervisor' : humanize(session.current.role)} · Data verification</span><h1>{supervisor ? 'Delegate a scope review' : 'Production review inbox'}</h1><p>{supervisor ? 'Isolate each scope, preview its report, then send it to the responsible operator.' : 'Review the reports assigned to your production scope.'}</p></div>
      <span>{session.current.display_name}</span>
    </header>
    {(error || resource.error) && <div className="production-review-error" role="alert"><p>{error ?? resource.error}</p><button disabled={busy} onClick={resource.reload}>Refresh requests</button></div>}

    {supervisor && <CasePacketPanel packets={resource.data.packets} reports={reports} gmReports={resource.data.gmReports} assetId={selectedAsset} personId={session.current.person_id} loading={resource.loading || busy} canSwitch={session.can_switch} onChange={resource.reload}/>}

    {supervisor && <section className="production-review-card production-delegation-controls">
      <header><div><span>01 · Prepare a scope report</span><h2>Evidence and recipient</h2></div><span className="production-version">{humanize(scope)} only</span></header>
      <p>{scope === 'EQUIPMENT' ? 'The equipment report preserves first-signal-to-peak condition records, engineering limits, model contributions and evidence available at the peak cutoff. Production figures are excluded.' : 'The production report covers the calculated interruption window with 48 hours of supporting records on either side. Condition sensors and RCA hypotheses are excluded.'}</p>
      <form onSubmit={prepare} onChange={() => { setDraft(null); setRequestId(crypto.randomUUID()); }}><fieldset disabled={busy || resource.loading} className="production-delegation-fields">
        <label>Equipment<select aria-label="Equipment for verification" value={selectedAsset} onChange={(event) => { setSelectedAsset(event.target.value); setRequestId(crypto.randomUUID()); }}>{assets.map((item) => <option key={item.asset_id} value={item.asset_id}>{item.plant_id} · {item.tag}</option>)}</select></label>
        <label>Review scope<select aria-label="Review scope" value={scope} onChange={(event) => setScope(event.target.value as typeof scope)}><option value="EQUIPMENT">Equipment performance</option><option value="PRODUCTION">Production</option></select></label>
        <label>Assigned operator<select key={`${selectedAsset}:${scope}`} name="recipient" required aria-label="Assigned operator">{operators.map((person) => <option key={person.person_id} value={person.person_id}>{person.display_name}</option>)}</select></label>
        <label>Recorded alert<select key={`${selectedAsset}:${alerts.loading}`} name="alert" defaultValue={selectedAsset === assetId ? alertId : undefined} required aria-label="Recorded alert" disabled={alerts.loading}>{alerts.data?.map((alert) => <option key={alert.alert_id} value={alert.alert_id}>{alert.highest_severity} · {formatDate(alert.opened_at)}</option>)}</select></label>
        <label>Response deadline · WIB<input type="datetime-local" name="deadline" required defaultValue={new Date(Date.now() + (24 + 7) * 3600000).toISOString().slice(0, 16)}/></label>
        <label className="production-delegation-instruction">Verification instruction<textarea key={scope} name="instruction" required maxLength={2000} rows={3} defaultValue={scope === 'EQUIPMENT' ? 'Cross-check condition readings, engineering limits, operating mode and persistent alarms with equipment records. State discrepancies and unavailable lab or inspection evidence.' : 'Compare equipment feed, offline interval, plant load and baseline with production records. Explain discrepancies or planned load changes.'}/></label>
        {alerts.error && <p role="alert">{alerts.error}</p>}
        <button className="production-submit" type="submit" disabled={!operators.length || alerts.loading || !alerts.data?.length}>{busy ? 'Preparing…' : 'Prepare report preview'}</button>
      </fieldset></form>
    </section>}

    {draft && supervisor && <>
      <div className="production-delegation-preview"><div><h2>{draft.status === 'DRAFT' ? 'Review before sending' : 'Report sent'}</h2><p>{draft.recipient_name} · Due {formatDate(draft.due_at, { hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Jakarta' })} WIB</p></div>{draft.status === 'DRAFT' ? <button className="production-submit" disabled={busy || resource.loading} onClick={send}>{busy ? 'Sending…' : `Send to ${draft.scope === 'EQUIPMENT' ? 'equipment' : 'production'} operator`}</button> : <a href={`#${draft.scope === 'EQUIPMENT' ? 'operator-equipment' : 'delegation'}?${new URLSearchParams({ asset: draft.asset.asset_id, person: draft.recipient_id })}`}>View operator inbox</a>}</div>
      {draft.scope === 'EQUIPMENT' ? <EquipmentVerificationReport report={draft}/> : <ProductionVerificationReport report={verificationReport(draft)} asset={draft.asset} review={draft.review}/>}
    </>}

    <section className="production-review-card production-delegation-list"><header><div><span>{supervisor ? '02 · Sent and draft reports' : 'Assigned to you'}</span><h2>{supervisor ? 'Verification requests' : 'Your production reports'}</h2></div><button disabled={busy || resource.loading} onClick={resource.reload}>Refresh</button></header>
      {!reports.length ? <p>No {supervisor ? 'verification requests prepared' : 'reports assigned'} yet.</p> : <ul>{reports.map((report) => <li key={report.report_id}><div><strong>{report.asset.tag} · {humanize(report.scope)} verification</strong><p>{report.recipient_name} · v{report.version} · Due {formatDate(report.due_at, { timeZone: 'Asia/Jakarta' })}</p>{report.review && <p>Operator response: {report.review.note}</p>}</div><span className={`production-request-status ${report.status.toLowerCase()}`}>{report.scope === 'EQUIPMENT' && report.status === 'APPROVED' ? 'Verified' : humanize(report.status)}</span>{supervisor && report.status === 'DRAFT' ? <button disabled={busy} onClick={() => { setDraft(report); setError(null); }}>Preview draft</button> : <a href={scopeReportLink(report, session.current.person_id)}>Open report</a>}</li>)}</ul>}
    </section>
    <p className="production-delegation-boundary">Scope verification requests are separate from CA/PA work assignment and GM authorization.</p>
    <button className="production-delegation-back" onClick={() => onNavigate('investigation')}>Back to investigation</button>
  </div>;
}
