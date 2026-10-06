import { useState } from 'react';
import type { FlowStep } from '../lib/flowTour';
import type { PageId } from '../components/AppShell';
import { SignalChart } from '../components/SignalChart';
import { ProductionVerificationReport } from '../components/ProductionVerificationReport';
import { TraceButton } from '../components/TraceabilityContext';
import { EmptyState, LoadingState } from '../components/ViewState';
import { api, selectWorkflowSession } from '../lib/api';
import { PRIMARY_ASSET_ID } from '../lib/appConfig';
import { formatDate, formatSignal, humanize } from '../lib/format';
import { buildProductionReview, canRecordProductionDecision, verificationReport, type ProductionReviewDecision } from '../lib/productionReview';
import { useApiResource } from '../lib/useApiResource';
import '../production-review.css';
import '../components/case-packet.css';

const decisions: Array<{ value: ProductionReviewDecision; label: string }> = [
  { value: 'APPROVED', label: 'Approve production evidence' },
  { value: 'CHANGES_REQUESTED', label: 'Request correction' },
  { value: 'UNABLE_TO_VALIDATE', label: 'Unable to validate' },
];

async function loadReview(assetId: string, requestId?: string, personId?: string) {
  if (requestId) {
    const session = await selectWorkflowSession(personId);
    const record = await api.productionReport(requestId);
    if (record.asset.asset_id !== assetId) throw new Error('Report does not belong to the selected equipment');
    return { overview: { asset: record.asset }, report: verificationReport(record), record, session };
  }
  const overview = await api.assetOverview(assetId);
  if (!overview.production_impact) return null;
  const impact = overview.production_impact;
  const start = new Date(new Date(impact.window_start).getTime() - 48 * 3600000).toISOString();
  const end = new Date(new Date(impact.window_end).getTime() + 48 * 3600000).toISOString();
  const telemetry = await api.telemetry(assetId, 1000, start, end);
  const report = buildProductionReview(overview, telemetry.points);
  return report ? { overview, report, record: null, session: null } : null;
}

export function ProductionReviewPage({ assetId = PRIMARY_ASSET_ID, requestId, personId, onNavigate, guidedStep }: { assetId?: string; requestId?: string; personId?: string; guidedStep?: FlowStep; onNavigate: (page: PageId) => void }) {
  const resource = useApiResource(`production-review:${assetId}:${requestId ?? ''}:${personId ?? ''}`, () => loadReview(assetId, requestId, personId));
  const [signal, setSignal] = useState<'feed_rate_tph' | 'plant_rate_tph'>('feed_rate_tph');
  const [recordPage, setRecordPage] = useState(0);
  const [note, setNote] = useState('');
  const [checked, setChecked] = useState(false);
  const [decision, setDecision] = useState<ProductionReviewDecision>('APPROVED');
  const [previewReceipt, setReceipt] = useState<{ decision: ProductionReviewDecision; note: string; at: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  if (resource.loading) return <LoadingState/>;
  if (resource.error) return <div className="production-review-error"><h1>Production evidence unavailable</h1><p>{resource.error}</p><button onClick={resource.reload}>Retry evidence loading</button></div>;
  if (!resource.data) return <EmptyState title="No production review available" description="This asset has no calculated production-impact window to review."/>;

  const { overview, report, record, session } = resource.data;
  const receipt = record?.review ?? previewReceipt;
  const mayRespond = !record || (record.status === 'SENT' && session?.current.role === 'OPERATOR' && session.current.person_id === record.recipient_id);
  const { impact } = report;
  const baseline = impact.baseline;
  const rows = report.points.slice(recordPage * 12, (recordPage + 1) * 12);
  const totalPages = Math.ceil(report.points.length / 12);
  const window = { start: impact.window_start, end: impact.window_end };
  const validDecision = canRecordProductionDecision(decision, note, checked);

  async function submitDecision() {
    if (!validDecision || busy || !mayRespond) return;
    if (!record) { setReceipt({ decision, note: note.trim(), at: new Date().toISOString() }); return; }
    setBusy(true); setSaveError(null);
    try {
      await api.respondProductionReport(record.report_id, { decision, note: note.trim(), attested: checked, expected_revision: record.revision });
      resource.reload();
    } catch (failure) { setSaveError(failure instanceof Error ? failure.message : 'Unable to save the review'); }
    finally { setBusy(false); }
  }

  return <div className="decision-workspace production-review-page">
    <header data-flow="production-heading" className="decision-workspace-heading">
      <div><span>{session ? humanize(session.current.role) : 'Production operator'} · {report.scope}</span><h1>Production evidence review</h1><p>Review your section of the supervisor's report before it goes to the GM.</p></div>
      <div><b>{record ? humanize(record.status) : 'Simulation preview'}</b>{record && session?.can_switch && session.current.role === 'OPERATOR' ? <a className="scope-return-link" href={`#delegation?${new URLSearchParams({ asset: record.asset.asset_id, person: record.created_by })}`}>Return to case packet</a> : <button onClick={() => onNavigate(record ? 'delegation' : 'overview')}>{record ? 'Back to requests' : 'Exit preview'}</button>}</div>
    </header>

    <div data-flow="production-report"><ProductionVerificationReport report={report} asset={overview.asset} review={receipt}/></div>

    <div className="production-evidence-heading"><h2>Supporting evidence</h2><p>Inspect the records behind report {report.reportId} · v{report.version}, then record your scope decision.</p></div>

    <div className="production-review-grid">
      <div className="production-review-evidence">
        <article data-flow="production-operating" className="production-review-card">
          <header><div><span>01 · Operating evidence</span><h2>Before, during, and after the interruption</h2></div>{!record && <TraceButton traceId="production-shortfall">View sources</TraceButton>}</header>
          <p className="production-context">{overview.asset.tag} equipment feed and {overview.asset.plant_id} plant rate are separate measures. The shaded window marks the sampled equipment outage.</p>
          <nav className="overview-signal-mode" aria-label="Production chart variable"><button className={signal === 'feed_rate_tph' ? 'active' : ''} onClick={() => setSignal('feed_rate_tph')}>Equipment feed</button><button className={signal === 'plant_rate_tph' ? 'active' : ''} onClick={() => setSignal('plant_rate_tph')}>Plant rate</button></nav>
          <div className="production-review-chart"><SignalChart points={report.points} field={signal} threshold={signal === 'feed_rate_tph' ? baseline.expected_feed_tph : undefined} highlightWindow={window} showRunStatus yPaddingRatio={0.12}/></div>
          <footer className="production-chart-legend"><span>{signal === 'feed_rate_tph' ? 'Reference line: expected feed baseline' : 'Plant rate: operating context, not equipment output'}</span><span>{formatDateTime(impact.window_start)} → {formatDateTime(impact.window_end)}</span></footer>
          <div data-flow="production-metrics" className="production-review-metrics">
            <Metric label="Actual outage feed" value={formatSignal(impact.actual_feed_tonnes)} unit="tonnes"/>
            <Metric label="Expected outage feed" value={formatSignal(impact.expected_feed_tonnes)} unit="tonnes"/>
            <Metric label="Estimated shortfall" value={formatSignal(impact.estimated_shortfall_tonnes)} unit="tonnes"/>
            <Metric label="Sampled offline time" value={formatSignal(impact.offline_hours, 0)} unit="hours"/>
          </div>
          {impact.reported_downtime_hours != null && <p className="production-review-qualification">Source RCA reports {formatSignal(impact.reported_downtime_hours)} h downtime{impact.reported_production_loss_tonnes != null ? ` and ${formatSignal(impact.reported_production_loss_tonnes)} tonnes loss` : ''}. These remain separate from the sampled duration and calculated shortfall above.</p>}
        </article>

        <article className="production-review-card">
          <header><div><span>02 · Report section</span><h2>What you are being asked to verify</h2></div><span className="production-version">Report v{report.version}</span></header>
          <blockquote>{report.statement}</blockquote>
          <p className="production-context">{report.response}</p>
          <details open={guidedStep?.expand ? true : undefined} className="production-review-details"><summary>Baseline and calculation</summary><dl>
            <div><dt>Baseline policy</dt><dd>{baseline.method === 'PRE_OUTAGE_OPERATING_MEDIAN' ? 'Pre-outage operating median' : 'Contextual healthy median'}</dd></div>
            <div><dt>Expected feed</dt><dd>{formatSignal(baseline.expected_feed_tph, 2)} t/h</dd></div>
            <div><dt>Comparable plant load</dt><dd>{formatSignal(baseline.representative_plant_rate_tph)} ± {formatSignal(baseline.plant_rate_tolerance_tph)} t/h</dd></div>
            <div><dt>Reference observations</dt><dd>{baseline.healthy_sample_count.toLocaleString()} samples · {humanize(baseline.confidence)} baseline confidence</dd></div>
            <div><dt>Reference period</dt><dd>{formatDateTime(baseline.reference_start)} → {formatDateTime(baseline.reference_end)}</dd></div>
            <div><dt>Calculation</dt><dd>max(expected feed tonnes − actual feed tonnes, 0) over the outage window.</dd></div>
            <div><dt>Source reference</dt><dd>{baseline.source_reference}</dd></div>
          </dl><p>This estimates equipment-feed shortfall against the stated reference, not finished-product loss or proof of a physical cause.</p></details>
        </article>

        <article className="production-review-card">
          <details data-flow="production-records" open={guidedStep?.expand ? true : undefined} className="production-review-details production-records"><summary>03 · Supporting records <span>{report.points.length} observations</span></summary>
            <p>{record ? 'Records frozen when the supervisor prepared this report.' : 'Evidence loaded for this preview.'} Compare run status and readings against the shaded outage window.</p>
            <div className="production-record-table"><table><thead><tr><th>Timestamp · WIB</th><th>Equipment feed · t/h</th><th>Plant rate · t/h</th><th>Run status</th></tr></thead><tbody>{rows.map((point) => <tr key={point.timestamp}><td>{formatDateTime(point.timestamp)}</td><td>{point.feed_rate_tph == null ? 'Unavailable' : formatSignal(point.feed_rate_tph, 2)}</td><td>{point.plant_rate_tph == null ? 'Unavailable' : formatSignal(point.plant_rate_tph, 2)}</td><td><span className={`production-run-status ${point.run_status.toLowerCase()}`}>{point.run_status}</span></td></tr>)}</tbody></table></div>
            <footer className="production-record-pagination"><span>Page {recordPage + 1} of {Math.max(totalPages, 1)}</span><div><button disabled={recordPage === 0} onClick={() => setRecordPage((page) => page - 1)}>Previous</button><button disabled={recordPage + 1 >= totalPages} onClick={() => setRecordPage((page) => page + 1)}>Next</button></div></footer>
            {!record && <TraceButton traceId="production-shortfall">Open calculation and source lineage</TraceButton>}
          </details>
        </article>
      </div>

      <aside className="production-review-sidebar">
        <article data-flow="production-decision" className="production-review-card production-decision-card">
          <header><div><span>Your review</span><h2>Production scope decision</h2></div><span className="production-version">v{report.version}</span></header>
          {saveError && <div role="alert"><p>{saveError}</p><button onClick={resource.reload}>Reload current report</button></div>}
          {receipt ? <div className="production-decision-receipt" role="status"><span>{record ? 'Decision saved' : 'Preview decision recorded'}</span><h3>{decisions.find((item) => item.value === receipt.decision)?.label}</h3><p>{receipt.note}</p><dl><div><dt>Report</dt><dd>{report.reportId} · v{report.version}</dd></div><div><dt>Recorded</dt><dd>{formatDateTime(receipt.at)}</dd></div></dl><p>{record ? 'The supervisor can now read your production verification and note.' : 'Shown to the supervisor in this simulation. No backend approval was changed.'}</p>{record && session?.can_switch && session.current.role === 'OPERATOR' && <a className="scope-return-link" href={`#delegation?${new URLSearchParams({ asset: record.asset.asset_id, person: record.created_by })}`}>Return to case packet</a>}{!record && <button onClick={() => { setReceipt(null); setNote(''); setChecked(false); setDecision('APPROVED'); }}>Reset simulation</button>}</div>
            : !mayRespond ? <p>{record?.status === 'DRAFT' ? 'Draft not yet sent to the operator.' : 'Waiting for the assigned production operator. This report is read-only for your identity.'}</p>
            : <form onSubmit={(event) => { event.preventDefault(); void submitDecision(); }}><fieldset disabled={busy || resource.loading}>
              <p>Check the report against your production records and add any operating context that changes its interpretation.</p>
              <fieldset><legend>Review outcome</legend>{decisions.map((item) => <label className={`production-outcome ${decision === item.value ? 'selected' : ''}`} key={item.value}><input type="radio" name="review-outcome" value={item.value} checked={decision === item.value} onChange={() => setDecision(item.value)}/><span>{item.label}</span></label>)}</fieldset>
              <label className="production-note-label" htmlFor="production-review-note">{decision === 'CHANGES_REQUESTED' ? 'What needs correction?' : decision === 'UNABLE_TO_VALIDATE' ? 'What evidence is missing?' : 'Review note and operational context'}</label>
              <textarea id="production-review-note" required maxLength={2000} rows={5} value={note} onChange={(event) => setNote(event.target.value)} placeholder="Mention the records checked, discrepancies, or planned load changes."/>
              {decision === 'APPROVED' && <label className="production-attestation"><input type="checkbox" checked={checked} onChange={(event) => setChecked(event.target.checked)}/><span>I reviewed the production section of v{report.version}, including its baseline and known limitations.</span></label>}
              <button className="production-submit" type="submit" disabled={!validDecision || busy || resource.loading}>{busy ? 'Saving…' : record ? 'Send verification to supervisor' : 'Record preview decision'}</button>
              <p className="production-decision-boundary">Your decision covers production evidence only. Equipment and planning approvals are separate; GM submission remains the supervisor's responsibility.</p>
            </fieldset></form>}
        </article>
        <div data-flow="production-boundary" className="production-review-snapshot"><span>Evidence snapshot</span><p>{record ? 'The report and evidence are saved as one fixed version. Your verification is retained after reload.' : 'The report stays unchanged while you review it. Decisions on this preview reset when you leave or reload.'}</p></div>
      </aside>
    </div>
  </div>;
}

function Metric({ label, value, unit }: { label: string; value: string; unit: string }) {
  return <div><span>{label}</span><strong>{value}</strong><small>{unit}</small></div>;
}

function formatDateTime(value: string): string {
  return formatDate(value, { hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Jakarta' });
}
