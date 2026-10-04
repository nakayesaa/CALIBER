import { VerificationDocument, VerificationReportSection as ReportSection } from './VerificationDocument';
import type { AssetSummary } from '../lib/api';
import { formatDate, formatSignal, humanize } from '../lib/format';
import type { ProductionReviewDecision, ProductionReviewReport } from '../lib/productionReview';

export function ProductionVerificationReport({ report, asset, review }: {
  report: ProductionReviewReport;
  asset: AssetSummary;
  review: { decision: ProductionReviewDecision; note: string; at: string } | null;
}) {
  const { impact } = report;
  const baseline = impact.baseline;
  const fields = [
    ['Report number', report.reportId], ['Revision', report.version],
    ['Plant / equipment', `${asset.plant_id} / ${asset.tag}`], ['Review scope', report.scope],
    ['Prepared by', report.supervisor], ['Issued · WIB', dateTime(report.requestedAt)],
    ['Response due · WIB', dateTime(report.dueAt)], ['Review status', review ? humanize(review.decision) : report.delivery ? humanize(report.delivery.status) : 'Awaiting production verification'],
    ...(report.delivery ? [['Assigned operator', report.delivery.recipient]] : []),
  ];
  const metrics = [
    ['Actual outage feed', `${formatSignal(impact.actual_feed_tonnes)} tonnes`, 'Integrated equipment feed during the sampled outage'],
    ['Expected outage feed', `${formatSignal(impact.expected_feed_tonnes)} tonnes`, 'Reference feed × sampled offline duration'],
    ['Estimated feed shortfall', `${formatSignal(impact.estimated_shortfall_tonnes)} tonnes`, 'max(expected feed − actual feed, 0)'],
    ['Sampled offline duration', `${formatSignal(impact.offline_hours)} hours`, 'Consecutive OFF observations in the operating series'],
  ];
  if (impact.reported_downtime_hours != null) metrics.push(['RCA-reported downtime', `${formatSignal(impact.reported_downtime_hours)} hours`, 'Separate source-report figure; not substituted for sampled duration']);
  if (impact.reported_production_loss_tonnes != null) metrics.push(['RCA-reported production loss', `${formatSignal(impact.reported_production_loss_tonnes)} tonnes`, 'Separate source-report figure; not substituted for the calculated shortfall']);

  return <VerificationDocument title="Production Verification Report" subtitle={`${asset.tag} · Production interruption and impact review`} fields={fields} footer={<><span>{report.reportId} · Revision {report.version} · Production scope</span><span>{report.delivery ? 'Saved evidence snapshot' : 'Simulation request and review record'} · evidence matches the on-screen snapshot</span></>}>
      <ReportSection number="1" title="Purpose and requested verification"><p>{report.response}</p><p>Operating window: {dateTime(impact.window_start)} to {dateTime(impact.window_end)} WIB. Supporting charts include 48 hours before and after this window.</p></ReportSection>
      <ReportSection number="2" title="Production impact summary"><div className="action-report-production"><table><thead><tr><th>Measure</th><th>Report value</th><th>Basis</th></tr></thead><tbody>{metrics.map(([label, value, basis]) => <tr key={label}><td>{label}</td><td>{value}</td><td>{basis}</td></tr>)}</tbody></table></div></ReportSection>
      <ReportSection number="3" title="Reference basis and interpretation"><p>{baseline.method === 'PRE_OUTAGE_OPERATING_MEDIAN' ? 'Pre-outage operating median' : 'Contextual healthy median'}: {formatSignal(baseline.expected_feed_tph, 2)} t/h equipment feed, selected at {formatSignal(baseline.representative_plant_rate_tph)} ± {formatSignal(baseline.plant_rate_tolerance_tph)} t/h plant load.</p><p>Reference: {dateTime(baseline.reference_start)} to {dateTime(baseline.reference_end)} WIB · {baseline.healthy_sample_count.toLocaleString()} observations · {humanize(baseline.confidence)} baseline confidence.</p><p className="production-document-source">Source: {baseline.source_reference}</p><p>Equipment feed and plant rate are separate measures. The calculated shortfall is not a finished-product loss estimate and does not establish which physical mechanism caused the interruption.</p></ReportSection>
      <ReportSection number="4" title="Statement for operator verification"><p className="production-document-statement">{report.statement}</p><p>Confirm the figures, baseline, source records, and operating context. Identify planned load changes, missing records, or discrepancies before accepting the production section.</p></ReportSection>
      <ReportSection number="5" title="Production review record">{review ? <><p>{report.delivery ? 'Recorded outcome' : 'Preview outcome'}: {humanize(review.decision)} · {dateTime(review.at)} WIB.</p><p>Operator note: {review.note}</p></> : <p>Pending operator review. No production attestation has been recorded.</p>}<p>This section validates production evidence only. Other scope approvals and the GM decision remain separate from production verification.</p></ReportSection>
  </VerificationDocument>;
}

function dateTime(value: string): string {
  return formatDate(value, { hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Jakarta' });
}
