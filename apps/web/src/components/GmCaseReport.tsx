import {
  VerificationDocument,
  VerificationReportSection as Section,
} from './VerificationDocument';
import { equipmentDate } from './EquipmentVerificationReport';
import { conditionSignalsFor } from '../lib/conditionSignals';
import { formatSignal, humanize } from '../lib/format';
import type { GmReport } from '../lib/gmReview';

export type GmCaseEvidence = Pick<
  GmReport,
  | 'case_id'
  | 'asset'
  | 'alert_id'
  | 'equipment_report'
  | 'production_report'
  | 'rca'
  | 'action_plans'
>;

export function GmCaseReport({
  evidence,
  fields,
  note,
  decision,
}: {
  evidence: GmCaseEvidence;
  fields: string[][];
  note: string;
  decision: GmReport['decision'];
}) {
  const {
    equipment_report: equipment,
    production_report: production,
    rca,
  } = evidence;
  const impact = production.impact;
  const labels = conditionSignalsFor(evidence.asset.asset_id);
  const actions = evidence.action_plans.flatMap((plan) => plan.actions);
  return (
    <VerificationDocument
      title="Management Decision Report"
      subtitle={`${evidence.asset.plant_id} / ${evidence.asset.tag} · Verified equipment and production evidence`}
      fields={fields}
      footer={
        <>
          <span>
            Case {evidence.case_id} · Alert {evidence.alert_id}
          </span>
          <span>
            GM decision is separate from work assignment and execution.
          </span>
        </>
      }
    >
      <Section number="1" title="Issue and decision requested">
        <p>{note}</p>
        <p>
          Recorded equipment alert:{' '}
          <strong>{humanize(equipment.evidence.alert.highest_severity)}</strong>
          . Evidence window: {equipmentDate(equipment.evidence.window_start)} to{' '}
          {equipmentDate(equipment.evidence.window_end)}.
        </p>
        <p>
          {rca?.generation.executive_summary ??
            'No RCA assessment is attached. Further investigation is required before a cause can be confirmed.'}
        </p>
      </Section>
      <Section number="2" title="Verified evidence and operational impact">
        <div className="action-report-production">
          <table>
            <thead>
              <tr>
                <th>Equipment parameter</th>
                <th>Reading</th>
                <th>Condition</th>
              </tr>
            </thead>
            <tbody>
              {equipment.evidence.drivers.contributions.map((signal) => (
                <tr key={signal.signal_key}>
                  <td>
                    {labels.find((item) => item.field === signal.source_field)
                      ?.label ?? signal.signal_key}
                  </td>
                  <td>
                    {formatSignal(signal.value, 2)} {signal.unit}
                  </td>
                  <td>{humanize(signal.engineering_state)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p>
          Condition readings at{' '}
          {equipmentDate(equipment.evidence.drivers.as_of)}. Production window:{' '}
          {equipmentDate(impact.window_start)} to{' '}
          {equipmentDate(impact.window_end)}.
        </p>
        <div className="action-report-production">
          <table>
            <thead>
              <tr>
                <th>Production measure</th>
                <th>Value</th>
                <th>Basis</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>Sampled equipment downtime</td>
                <td>{formatSignal(impact.offline_hours)} h</td>
                <td>OFF observations in the equipment series</td>
              </tr>
              <tr>
                <td>Expected / actual equipment feed</td>
                <td>
                  {formatSignal(impact.expected_feed_tonnes)} /{' '}
                  {formatSignal(impact.actual_feed_tonnes)} t
                </td>
                <td>Configured baseline compared with integrated feed</td>
              </tr>
              <tr>
                <td>Estimated equipment feed shortfall</td>
                <td>{formatSignal(impact.estimated_shortfall_tonnes)} t</td>
                <td>
                  max(expected − actual feed, 0); not plant-wide product loss
                </td>
              </tr>
              {impact.reported_downtime_hours != null && (
                <tr>
                  <td>Source-reported equipment downtime</td>
                  <td>{formatSignal(impact.reported_downtime_hours)} h</td>
                  <td>Linked RCA report; separate from sampled duration</td>
                </tr>
              )}
              {impact.reported_production_loss_tonnes != null && (
                <tr>
                  <td>Source-reported production loss</td>
                  <td>{formatSignal(impact.reported_production_loss_tonnes)} t</td>
                  <td>Linked RCA report; separate from calculated feed shortfall</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        <p>
          Feed reference: {formatSignal(impact.baseline.expected_feed_tph, 2)}{' '}
          t/h · {humanize(impact.baseline.method)} ·{' '}
          {impact.baseline.healthy_sample_count} observations.
          <br />
          Source: {impact.baseline.source_reference}
        </p>
      </Section>
      <Section number="3" title="RCA indication and remaining questions">
        {rca?.generation.hypotheses.length ? (
          rca.generation.hypotheses.map((hypothesis) => (
            <div className="gm-hypothesis" key={hypothesis.hypothesis_id}>
              <h4>
                {hypothesis.rank}. {hypothesis.title}
              </h4>
              <p>{hypothesis.rationale}</p>
              <details>
                <summary>Mechanism, evidence and uncertainty</summary>
                <p>{hypothesis.mechanism}</p>
                <p>
                  Supporting evidence:{' '}
                  {hypothesis.supporting_evidence_ids.join(', ') ||
                    'None attached'}
                  .
                </p>
                <p>
                  Contradicting evidence:{' '}
                  {hypothesis.contradicting_evidence_ids.join(', ') ||
                    'None recorded'}
                  .
                </p>
                <p>
                  Still needed:{' '}
                  {hypothesis.missing_evidence.join('; ') ||
                    'No additional requirement listed'}
                  .
                </p>
                <p>
                  Reconsider this hypothesis if:{' '}
                  {hypothesis.disconfirming_condition}
                </p>
              </details>
            </div>
          ))
        ) : (
          <p>No probable cause has been recorded.</p>
        )}
        <p>
          Data verification confirms the scope records. It does not establish
          that an RCA hypothesis is proven.
        </p>
      </Section>
      <Section number="4" title="Proposed follow-up actions">
        {actions.length ? (
          <div className="action-report-production">
            <table>
              <thead>
                <tr>
                  <th>Action</th>
                  <th>Owner role / priority</th>
                  <th>Completion evidence</th>
                </tr>
              </thead>
              <tbody>
                {actions.map((action) => (
                  <tr key={action.action_id}>
                    <td>
                      <strong>{action.title}</strong>
                      <br />
                      {humanize(action.action_type)}
                      <br />
                      {action.guidance}
                    </td>
                    <td>
                      {action.owner_role}
                      <br />
                      {humanize(action.priority)}
                    </td>
                    <td>{action.completion_criteria}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p>
            No action plan is attached. The supervisor must prepare a plan
            before work assignment.
          </p>
        )}
        <p>
          This report requests a management decision on the case and proposed
          approach. Named assignment, work authorization and execution remain
          separate steps.
        </p>
      </Section>
      <Section number="5" title="Scope verification and source records">
        {[equipment, production].map((report) => (
          <div key={report.report_id}>
            <h4>
              {humanize(report.scope)} · {report.recipient_name}
            </h4>
            <p>
              {report.review?.note}
              <br />
              Verified{' '}
              {report.review
                ? equipmentDate(report.review.at)
                : 'not recorded'}{' '}
              · {report.report_id} · v{report.version} · revision{' '}
              {report.revision}
            </p>
          </div>
        ))}
        <details>
          <summary>Equipment checks and supporting sources</summary>
          <p>Operating context: {equipment.review?.human_context}</p>
          {equipment.review?.checks.map((check) => (
            <p key={check.check}>
              <strong>{humanize(check.check)}</strong>: {check.finding}
              <br />
              Reference: {check.reference ?? 'Not available'}
            </p>
          ))}
          {equipment.evidence.events.map((event) => (
            <p key={event.event_id}>
              <strong>{event.title}</strong> ·{' '}
              {equipmentDate(event.occurred_at)}
              <br />
              {event.detail}
              <br />
              Source: {event.source_reference}
            </p>
          ))}
        </details>
      </Section>
      <Section number="6" title="Management decision">
        {decision ? (
          <>
            <p>
              <strong>
                {decision.decision === 'APPROVED'
                  ? 'Approved'
                  : 'Returned for revision'}
              </strong>{' '}
              · {equipmentDate(decision.at)} · {decision.actor_id}
            </p>
            <p>{decision.note}</p>
          </>
        ) : (
          <p>No management decision recorded.</p>
        )}
      </Section>
    </VerificationDocument>
  );
}
