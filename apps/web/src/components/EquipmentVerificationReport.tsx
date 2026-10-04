import { VerificationDocument, VerificationReportSection as Section } from './VerificationDocument';
import { formatDate, formatSignal, humanize } from '../lib/format';
import { equipmentChecks, type EquipmentReport } from '../lib/equipmentReview';
import { conditionSignalsFor } from '../lib/conditionSignals';

export function equipmentDate(value: string): string {
  return `${formatDate(value, { hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Jakarta' })} WIB`;
}

export function EquipmentVerificationReport({ report }: { report: EquipmentReport }) {
  const { evidence, review } = report;
  const labels = conditionSignalsFor(report.asset.asset_id);
  const fields = [
    ['Report number', report.report_id], ['Version', report.version],
    ['Plant / equipment', `${report.asset.plant_id} / ${report.asset.tag}`], ['Scope', 'Equipment performance'],
    ['Prepared by', report.supervisor], ['Assigned operator', report.recipient_name],
    ['Prepared', equipmentDate(report.created_at)], ['Response due', equipmentDate(report.due_at)],
    ['Status', report.status === 'APPROVED' ? 'Verified' : humanize(report.status)], ['Evidence as of', equipmentDate(evidence.as_of)],
  ];
  return <VerificationDocument title="Equipment Verification Report" subtitle={`${report.asset.tag} · Condition evidence and operating-context review`} fields={fields} footer={<><span>{report.report_id} · v{report.version} · Equipment scope</span><span>Fixed evidence snapshot · scope verification only</span></>}>
    <Section number="1" title="Purpose and requested verification"><p>{report.note}</p><p>Recorded window: {equipmentDate(evidence.window_start)} to {equipmentDate(evidence.window_end)}. Alert: {evidence.alert.alert_id}.</p></Section>
    <Section number="2" title="Condition evidence"><p>Contribution readings are evaluated at {equipmentDate(evidence.drivers.as_of)}. Model contribution is an explanation of anomaly detection, not proof of a root cause.</p><div className="action-report-production"><table><thead><tr><th>Parameter</th><th>Reading</th><th>Alarm / trip</th><th>State</th><th>Contribution</th></tr></thead><tbody>{evidence.drivers.contributions.map((signal) => <tr key={signal.signal_key}><td>{labels.find((item) => item.field === signal.source_field)?.label ?? signal.signal_key}</td><td>{formatSignal(signal.value, 2)} {signal.unit}</td><td>{formatSignal(signal.alarm_limit)} / {formatSignal(signal.trip_limit)} {signal.unit}<br/>{signal.direction_of_concern === 'LOW' ? 'Lower values are concerning' : 'Higher values are concerning'}</td><td>{humanize(signal.engineering_state)}</td><td>{formatSignal(signal.contribution_percent)}%</td></tr>)}</tbody></table></div><p>{evidence.points.length.toLocaleString()} condition records retained in this snapshot. {evidence.validation_note}</p></Section>
    <Section number="3" title="Supporting source evidence">{evidence.events.length ? evidence.events.map((event) => <p key={event.event_id}><strong>{event.title}</strong> · {equipmentDate(event.occurred_at)}<br/>{event.detail}<br/>Source: {event.source_reference}</p>) : <p>No lab or inspection finding is attached at this evidence cutoff. Record unavailable evidence explicitly; do not infer a test result.</p>}<p>Model reference: {evidence.drivers.model_id} · {humanize(evidence.drivers.method)}. Engineering limits above are the configured reference for this snapshot and must be cross-checked against the applicable equipment source.</p></Section>
    <Section number="4" title="Operator verification record">{review ? <><p>Outcome: {review.decision === 'APPROVED' ? 'Verified' : humanize(review.decision)} · {equipmentDate(review.at)} · {review.actor_id}</p><p>{review.note}</p><p>Operating context: {review.human_context}</p>{review.checks.map((check) => <p key={check.check}><strong>{equipmentChecks.find((item) => item.id === check.check)?.title}: {humanize(check.result)}</strong><br/>{check.finding}<br/>Reference: {check.reference ?? 'Not available'}</p>)}</> : <p>Pending operator review of data validity, operating context, abnormal behaviour and supporting evidence.</p>}</Section>
    <Section number="5" title="Decision boundary"><p>This review verifies the equipment evidence in this report version. It does not confirm a root cause, authorize operation or approve CA/PA work. Production verification and management authorization remain separate.</p></Section>
  </VerificationDocument>;
}
