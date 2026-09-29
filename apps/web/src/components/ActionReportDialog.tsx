import { useEffect, useRef, type ReactNode } from 'react';
import { createPortal } from 'react-dom';

import type { PlantRateSeries } from '../lib/apiContracts';
import type { selectActionReport } from '../lib/plantOverviewDemoData';

type ActionReport = NonNullable<ReturnType<typeof selectActionReport>>;

function ReportSection({ number, title, children }: { number: number; title: string; children: ReactNode }) {
  return <section className="capa-report-section"><header><span>{number}</span><h3>{title}</h3></header><div>{children}</div></section>;
}

export function ActionReportDialog({ record, production, onClose, onOpenTracking }: { record: ActionReport; production: PlantRateSeries | null; onClose: () => void; onOpenTracking?: () => void }) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const { action, issue } = record;
  const reportId = `CAL-${issue.plant}-${action.id.toUpperCase()}`;

  useEffect(() => {
    const dialog = dialogRef.current!;
    const previousTitle = document.title;
    const previousFocus = document.activeElement;
    document.title = `${reportId} - ${action.title}`;
    dialog.showModal();
    return () => {
      dialog.close();
      document.title = previousTitle;
      if (previousFocus instanceof HTMLElement && previousFocus.isConnected) previousFocus.focus();
    };
  }, [reportId, action.title]);

  const fields = [
    ['Report ID', reportId], ['Handoff status', action.status], ['Plant / equipment', `${issue.plant} / ${issue.tag}`], ['Snapshot', '30 Apr 2026 · 23:00 WIB'],
    ['Prepared by', 'CALIBER operator'], ['Assigned team', action.owner], ['Due date', `${action.due.replace(' ·', ' 2026 ·')} WIB`], ['Issue reference', issue.id],
  ];

  return createPortal(<dialog ref={dialogRef} className="action-report-dialog" aria-labelledby="action-report-title" onCancel={(event) => { event.preventDefault(); onClose(); }} onClick={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <div className="action-report-toolbar"><span>PDF: More settings → turn off Headers and footers.</span><div><button onClick={() => window.print()}>Save as PDF</button><button onClick={onClose} aria-label="Close action report">Close</button></div></div>
    <article className="action-report-paper">
      <header className="action-report-heading"><h1 id="action-report-title">Action handoff report</h1><p>{action.title}</p></header>
      <dl className="capa-document-control">{fields.map(([label, value]) => <div className="capa-document-field" key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>

      <ReportSection number={1} title="Issue and operating context"><div className="capa-report-line"><strong>Issue</strong><p>{issue.title} · {issue.severity} priority</p></div><div className="capa-report-line"><strong>Operating impact</strong><p>{issue.impact}</p></div><div className="capa-report-line"><strong>Working indication</strong><p>{issue.indication}</p></div></ReportSection>
      <ReportSection number={2} title="Assigned scope and execution"><p>{action.report.objective}</p><ol>{action.report.steps.map((step) => <li key={step}>{step}</li>)}</ol></ReportSection>
      <ReportSection number={3} title="Supporting data and source references">
        {action.report.includeProduction && <ProductionEvidence production={production} />}
        <ul>{action.report.sources.map((source) => <li key={source}>{source}</li>)}</ul>
      </ReportSection>
      <ReportSection number={4} title="Required deliverables and verification"><ul>{action.report.deliverables.map((item) => <li key={item}>{item}</li>)}</ul><div className="capa-report-line"><strong>Acceptance criteria</strong><p>{action.report.verification}</p></div></ReportSection>
      <ReportSection number={5} title="Handoff and review record"><div className="capa-report-line"><strong>Receiving team</strong><p>{action.owner}</p></div><div className="capa-report-line"><strong>Review / approval</strong><p>Reviewer name, review date and approval reference are not recorded in this snapshot.</p></div><div className="capa-report-line"><strong>Return to operator</strong><p>Return the assessment and supporting records against action {action.id}. Exporting this report does not complete or approve the action.</p></div><div className="capa-report-line"><strong>Execution and closure</strong><p>{issue.investigationAvailable ? 'The equipment investigation links to a separate CA/PA plan. Track execution there, review recovery evidence, then record effectiveness approval before closure. This handoff status does not override the CA/PA action status.' : 'No linked CA/PA plan is available for this issue. Establish the supporting assessment before creating corrective or preventive work.'}</p>{onOpenTracking && <button className="action-report-tracking-link" onClick={onOpenTracking}>Open linked CA/PA tracking and effectiveness review</button>}</div></ReportSection>
      <footer className="action-report-footnote"><span>{reportId} · Issue {issue.id}</span><span>Action scope: scenario register · production table: observed source where available</span></footer>
    </article>
  </dialog>, document.body);
}

function ProductionEvidence({ production }: { production: PlantRateSeries | null }) {
  const referencePoints = production?.points.slice(0, 7) ?? [];
  const reference = referencePoints.length ? referencePoints.reduce((sum, point) => sum + point.average_rate_tph, 0) / referencePoints.length : null;
  return <div className="action-report-production"><p>Daily means include offline hours. They provide screening context; running-period recovery needs the hourly RUN_STATUS record.</p>
    {production?.points.length ? <><table><caption>ZCU production · recent observed daily means</caption><thead><tr><th scope="col">Date</th><th scope="col">Plant rate (t/h)</th><th scope="col">Hourly readings</th></tr></thead><tbody>{production.points.slice(-3).map((point) => <tr key={point.date}><td>{point.date}</td><td>{point.average_rate_tph.toFixed(2)}</td><td>{point.sample_count}</td></tr>)}</tbody></table><p>Screening reference: {reference?.toFixed(2)} t/h · mean of {referencePoints[0].date} to {referencePoints.at(-1)!.date} daily means.</p><p className="action-report-source">Source: {production.source_reference} · {production.source_rows} hourly readings.</p></> : <p>Observed production data is unavailable. Retrieve the production source before issuing a quantitative recovery assessment.</p>}
  </div>;
}
