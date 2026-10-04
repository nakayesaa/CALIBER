import { useState, type FormEvent } from 'react';
import { api } from '../lib/api';
import { type CasePacket, type EquipmentReport, type ScopeReport, preferredScopeReports, scopeReportLink } from '../lib/equipmentReview';
import { formatDate, humanize } from '../lib/format';
import { gmReportLink, gmStatusLabel, type GmReport } from '../lib/gmReview';
import './case-packet.css';

export function CasePacketPanel({ packets, reports, gmReports, assetId, personId, loading, canSwitch, onChange }: {
  packets: CasePacket[]; reports: ScopeReport[]; gmReports: GmReport[]; assetId: string; personId: string; loading: boolean; canSwitch: boolean; onChange: () => void;
}) {
  const [selected, setSelected] = useState('');
  const [requestId, setRequestId] = useState(() => crypto.randomUUID());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bound = new Set(packets.flatMap((packet) => [packet.equipment_report_id, packet.production_report_id]));
  const preferred = preferredScopeReports(reports);
  const equipment = preferred.filter((report): report is EquipmentReport => report.scope === 'EQUIPMENT' && report.asset.asset_id === assetId && !bound.has(report.report_id));
  const chosen = equipment.find((report) => report.report_id === selected) ?? equipment[0];
  const production = preferred.filter((report) => report.scope === 'PRODUCTION' && report.asset.asset_id === assetId && report.alert_id === chosen?.evidence.alert.alert_id && !bound.has(report.report_id));
  const visible = packets.filter((packet) => packet.asset.asset_id === assetId);

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || !chosen) return;
    const form = new FormData(event.currentTarget);
    setBusy(true); setError(null);
    try {
      await api.createCasePacket({ request_id: requestId, equipment_report_id: chosen.report_id, production_report_id: String(form.get('production')) });
      setRequestId(crypto.randomUUID()); setSelected(''); onChange();
    } catch (failure) { setError(failure instanceof Error ? failure.message : 'Unable to bind case reports'); }
    finally { setBusy(false); }
  }

  async function sendReport(report: ScopeReport) {
    if (busy) return;
    setBusy(true); setError(null);
    try {
      if (report.scope === 'EQUIPMENT') await api.sendEquipmentReport(report.report_id, report.revision);
      else await api.sendProductionReport(report.report_id, report.revision);
      onChange();
    } catch (failure) { setError(failure instanceof Error ? failure.message : 'Unable to send report'); }
    finally { setBusy(false); }
  }

  return <section className="production-review-card case-packet-section" aria-label="Case packets">
    <header><div><span>Case coordination</span><h2>Case packets</h2></div><button disabled={busy || loading} onClick={onChange}>Refresh case status</button></header>
    <p>Bind equipment and production evidence for the same alert. Each scope keeps its own evidence window and operator decision.</p>
    {error && <p role="alert">{error}</p>}
    {visible.map((packet) => {
      const handoff = gmReports.find((report) => report.case_id === packet.case_id);
      return <article className={`case-packet ${packet.can_escalate ? 'is-ready' : ''}`} key={packet.case_id}>
      <header><div><h3>{packet.asset.tag} Case Packet</h3><p className="case-packet-id">{packet.case_id} · v{packet.version}</p><p>{packet.asset.plant_id} · {formatDate(packet.window_start)} → {formatDate(packet.window_end)}</p></div><span className={`production-request-status ${handoff?.status.toLowerCase() ?? ''}`}>{handoff ? gmStatusLabel[handoff.status] : packet.can_escalate ? 'Ready for GM review' : humanize(packet.state)}</span></header>
      <ul>{packet.scopes.map((scope) => {
        const report = reports.find((item) => item.report_id === scope.report_id);
        return <li key={scope.scope}>
          <div><strong>{scope.scope === 'EQUIPMENT' ? 'Equipment' : 'Production'} verification</strong><p>{scope.recipient_name} · Report v{scope.version}</p>{scope.note && <p className={scope.verified ? 'case-packet-supported' : 'case-packet-challenged'}>{scope.note}</p>}</div>
          <span className={`production-request-status ${scope.status.toLowerCase()}`}>{scope.verified ? 'Verified' : humanize(scope.status)}</span>
          {scope.status !== 'UNAVAILABLE' && <div className="case-packet-actions">
            {scope.status === 'DRAFT' && report && <button disabled={busy || loading} onClick={() => void sendReport(report)}>Send to {scope.scope === 'EQUIPMENT' ? 'equipment' : 'production'} operator</button>}
            {scope.status === 'SENT' && report && canSwitch && <a className="case-packet-review-action" href={scopeReportLink(report, report.recipient_id)}>Review as {scope.scope === 'EQUIPMENT' ? 'equipment' : 'production'} operator</a>}
            <a href={scopeReportLink({ scope: scope.scope, report_id: scope.report_id, asset: packet.asset }, personId)}>View report</a>
          </div>}
        </li>;
      })}</ul>
      <footer><div><strong>{handoff ? gmStatusLabel[handoff.status] : packet.summary}</strong><p>{handoff?.decision ? handoff.decision.note : handoff ? 'Combined report sent. Waiting for the GM to review the evidence and proposed actions.' : 'Equipment and production data must both be verified before submission.'}</p></div>{handoff || packet.can_escalate ? <a className="scope-return-link" href={gmReportLink(handoff?.report_id ?? packet.case_id, packet.asset.asset_id, personId)}>{handoff?.status === 'APPROVED' ? 'Assign CA/PA' : handoff ? 'Open GM report' : 'Preview & send to GM'}</a> : <button disabled>Waiting for scope verification</button>}</footer>
    </article>; })}
    {!visible.length && <p>No case packet for this equipment yet. Prepare its equipment and production reports, then bind them below.</p>}
    <details className="case-packet-create" open={!visible.length}><summary>Bind reports into a case packet</summary><form onSubmit={create}><fieldset disabled={busy || loading}>
      <label>Equipment report<select aria-label="Case equipment report" value={chosen?.report_id ?? ''} onChange={(event) => { setSelected(event.target.value); setRequestId(crypto.randomUUID()); }}>{equipment.map((report) => <option key={report.report_id} value={report.report_id}>{report.status === 'APPROVED' ? 'Verified' : humanize(report.status)} · {formatDate(report.created_at, { hour: '2-digit', minute: '2-digit' })} · {report.report_id.slice(-6)}</option>)}</select></label>
      <label>Production report · same alert<select key={chosen?.report_id} aria-label="Case production report" name="production" required onChange={() => setRequestId(crypto.randomUUID())}>{production.map((report) => <option key={report.report_id} value={report.report_id}>{report.status === 'APPROVED' ? 'Verified' : humanize(report.status)} · {formatDate(report.created_at, { hour: '2-digit', minute: '2-digit' })} · {report.report_id.slice(-6)}</option>)}</select></label>
      {!equipment.length ? <p>Prepare an unbound equipment report first.</p> : !production.length && <p>Prepare an unbound production report for the same equipment and recorded alert.</p>}
      <button className="production-submit" disabled={!chosen || !production.length}>Bind case packet</button>
    </fieldset></form></details>
  </section>;
}
