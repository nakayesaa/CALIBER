import { useState, type FormEvent } from 'react';
import { GmCaseReport, type GmCaseEvidence } from '../components/GmCaseReport';
import { equipmentDate } from '../components/EquipmentVerificationReport';
import { LoadingState } from '../components/ViewState';
import { GmActionAssignments } from '../components/GmActionAssignments';
import { GmFlowReference } from '../components/GmFlowReference';
import type { FlowStep } from '../lib/flowTour';
import { api, selectWorkflowSession } from '../lib/api';
import { gmReportLink, gmStatusLabel } from '../lib/gmReview';
import { useApiResource } from '../lib/useApiResource';
import '../production-review.css';
import '../components/case-packet.css';
import '../gm-review.css';

export function GmReviewPage({
  requestId,
  personId,
  guidedStep,
}: {
  requestId?: string;
  personId?: string;
  guidedStep?: FlowStep;
}) {
  const guidedDetail = Boolean(guidedStep && !['[data-flow="gm-heading"]', '[data-flow="gm-inbox"]'].includes(guidedStep.selector));
  const resource = useApiResource(
    `gm-review:${requestId ?? 'inbox'}:${personId ?? ''}:${guidedDetail ? 'flow-detail' : 'normal'}`,
    async () => {
      const session = await selectWorkflowSession(personId);
      if (!['MANAGER', 'SUPERVISOR'].includes(session.current.role))
        throw new Error(
          'Management reports are available to the case supervisor and assigned GM.',
        );
      const reports = await api.gmReports();
      let report = null;
      let preview: GmCaseEvidence | null = null;
      if (requestId?.startsWith('gm-')) report = await api.gmReport(requestId);
      else if (requestId?.startsWith('case-')) {
        report = reports.find((item) => item.case_id === requestId) ?? null;
        if (!report) {
          const packet = await api.casePacket(requestId);
          if (!packet.can_escalate) throw new Error(packet.summary);
          const [equipment, production, detail] = await Promise.all([
            api.equipmentReport(packet.equipment_report_id),
            api.productionReport(packet.production_report_id),
            api.alertDetail(packet.alert_id),
          ]);
          preview = {
            case_id: packet.case_id,
            asset: packet.asset,
            alert_id: packet.alert_id,
            equipment_report: equipment,
            production_report: production,
            rca: detail.rca ?? detail.prepared_workflow?.rca ?? null,
            action_plans: detail.action_plans.length
              ? detail.action_plans
              : (detail.prepared_workflow?.action_plans ?? []),
          };
        }
      } else if (requestId)
        throw new Error('Open a case packet or management report.');
      else if (guidedDetail && reports.length) {
        const candidates = [...reports].sort((a, b) => b.submitted_at.localeCompare(a.submitted_at));
        const selected = candidates.find((item) => item.asset.asset_id === 'asset-ko-3201') ?? candidates[0];
        report = await api.gmReport(selected.report_id);
      }
      const executionPlans = report ? await api.gmActionPlans(report.report_id) : [];
      return { session, reports, report, preview, executionPlans, guidedDetail };
    },
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [requestNote, setRequestNote] = useState<string | null>(null);
  if (!resource.data || resource.data.guidedDetail !== guidedDetail)
    return resource.loading || !resource.error ? (
      <LoadingState />
    ) : (
      <div className="production-review-error">
        <h1>Management report unavailable</h1>
        <p role="alert">{resource.error}</p>
        <button onClick={resource.reload}>Retry</button>
      </div>
    );
  const { session, reports, report, preview } = resource.data;
  const evidence = report ?? preview;
  const supervisor = session.current.role === 'SUPERVISOR';
  const previewNote =
    requestNote ??
    `Please review the verified ${preview?.asset.tag ?? 'equipment'} case, its production impact and proposed follow-up actions.`;
  const back =
    supervisor && evidence
      ? `#delegation?${new URLSearchParams({ asset: evidence.asset.asset_id, person: session.current.person_id })}`
      : `#gm-review?person=${encodeURIComponent(session.current.person_id)}`;

  async function send(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || !preview || !supervisor) return;
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setError(null);
    try {
      const saved = await api.submitToGm(preview.case_id, {
        recipient_id: String(form.get('recipient')),
        note: String(form.get('note')).trim(),
      });
      window.location.hash = gmReportLink(
        saved.report_id,
        saved.asset.asset_id,
        session.current.person_id,
      );
    } catch (failure) {
      setError(
        failure instanceof Error
          ? failure.message
          : 'Unable to send report to GM',
      );
    } finally {
      setBusy(false);
    }
  }

  async function decide(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (
      busy ||
      !report ||
      report.status !== 'PENDING_REVIEW' ||
      session.current.person_id !== report.recipient_id ||
      session.current.role !== 'MANAGER'
    )
      return;
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setError(null);
    try {
      await api.decideGmReport(report.report_id, {
        decision: form.get('decision') === 'RETURNED' ? 'RETURNED' : 'APPROVED',
        expected_revision: report.revision,
        note: String(form.get('note')).trim(),
      });
      resource.reload();
    } catch (failure) {
      setError(
        failure instanceof Error
          ? failure.message
          : 'Unable to save management decision',
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="decision-workspace production-review-page gm-review-page">
      <header className="decision-workspace-heading" data-flow="gm-heading">
        <div>
          <span>
            {supervisor ? 'Supervisor' : 'General Manager'} · Case review
          </span>
          <h1>
            {preview
              ? 'Preview management report'
              : report
                ? 'Management case review'
                : 'GM review inbox'}
          </h1>
          <p>
            {preview
              ? 'Review the combined evidence, add your decision request, then send it to the GM.'
              : report
                ? 'Verified scope evidence, RCA indication and proposed follow-up in one report.'
                : 'Review verified cases and record a management decision.'}
          </p>
        </div>
        {evidence && (
          <a className="scope-return-link" href={back}>
            {supervisor ? 'Back to case packet' : 'Back to GM inbox'}
          </a>
        )}
      </header>
      {(error || resource.error) && (
        <div role="alert" className="production-review-error">
          <p>{error ?? resource.error}</p>
          <button onClick={resource.reload} disabled={busy}>
            Reload report
          </button>
        </div>
      )}
      {!evidence ? (
        <section className="production-review-card production-delegation-list" data-flow="gm-inbox">
          <header>
            <h2>Case reports</h2>
            <button onClick={resource.reload} disabled={resource.loading}>
              Refresh inbox
            </button>
          </header>
          {!reports.length ? (
            <p>
              No case reports submitted yet. The supervisor must verify both
              scopes before sending a case.
            </p>
          ) : (
            <ul>
              {reports.map((item) => (
                <li key={item.report_id}>
                  <div>
                    <strong>
                      {item.asset.tag} · {item.asset.plant_id}
                    </strong>
                    <p>
                      {equipmentDate(item.submitted_at)} ·{' '}
                      {item.equipment_report.supervisor}
                    </p>
                    <p>{item.note}</p>
                  </div>
                  <span
                    className={`production-request-status ${item.status.toLowerCase()}`}
                  >
                    {gmStatusLabel[item.status]}
                  </span>
                  <a
                    href={gmReportLink(
                      item.report_id,
                      item.asset.asset_id,
                      session.current.person_id,
                    )}
                  >
                    Open management report
                  </a>
                </li>
              ))}
            </ul>
          )}
        </section>
      ) : (
        <>
          {supervisor && report?.status === 'APPROVED' && <GmActionAssignments report={report} plans={resource.data.executionPlans} session={session} onChange={resource.reload} loading={resource.loading}/>}
          <GmCaseReport
            evidence={evidence}
            fields={[
              ['Report', report?.report_id ?? 'Submission preview'],
              ['Case version', report?.version ?? '01'],
              ['Prepared by', evidence.equipment_report.supervisor],
              [
                'Status',
                report ? gmStatusLabel[report.status] : 'Not submitted',
              ],
              [
                'Issued',
                report
                  ? equipmentDate(report.submitted_at)
                  : 'Snapshot saved when sent',
              ],
              ['Scope verification', 'Equipment and production verified'],
              [
                'Recipient',
                report?.recipient_name ?? 'General Manager selected below',
              ],
            ]}
            note={report?.note ?? previewNote}
            decision={report?.decision ?? null}
          />
          <section
            className="production-review-card gm-decision-panel"
            aria-label="Management handoff"
            data-flow="gm-decision"
          >
            {preview ? (
              <>
                <h2>Send this case to GM</h2>
                <p>
                  The backend rechecks both scope approvals and saves a fixed
                  report snapshot at submission.
                </p>
                <form onSubmit={send}>
                  <fieldset disabled={busy || resource.loading}>
                    <label>
                      General Manager
                      <select name="recipient" aria-label="General Manager recipient" required>
                        {session.participants
                          .filter((person) => person.role === 'MANAGER')
                          .map((person) => (
                            <option
                              value={person.person_id}
                              key={person.person_id}
                            >
                              {person.display_name}
                            </option>
                          ))}
                      </select>
                    </label>
                    <label>
                      Decision request
                      <textarea
                        name="note"
                        required
                        maxLength={2000}
                        rows={3}
                        value={previewNote}
                        onChange={(event) => setRequestNote(event.target.value)}
                      />
                    </label>
                    <button className="production-submit">
                      {busy ? 'Sending…' : 'Send to GM'}
                    </button>
                  </fieldset>
                </form>
              </>
            ) : report?.decision ? (
              <div role="status">
                <h2>{gmStatusLabel[report.status]}</h2>
                <p>{report.decision.note}</p>
                <p>
                  Saved {equipmentDate(report.decision.at)}.{' '}
                  {report.status === 'RETURNED'
                    ? 'The supervisor must address these comments before a revised submission.'
                    : 'The supervisor can use this decision for the next assignment step. No work has been assigned automatically.'}
                </p>
              </div>
            ) : session.current.role === 'MANAGER' &&
              report?.recipient_id === session.current.person_id ? (
              <>
                <h2>Your management decision</h2>
                <p>
                  Approve the proposed approach or return the report with
                  specific changes needed.
                </p>
                <form onSubmit={decide}>
                  <fieldset disabled={busy || resource.loading}>
                    <label>
                      Decision
                      <select name="decision" aria-label="Management decision" required>
                        <option value="APPROVED">Approve</option>
                        <option value="RETURNED">Return for revision</option>
                      </select>
                    </label>
                    <label>
                      Decision note
                      <textarea
                        name="note"
                        required
                        maxLength={2000}
                        rows={3}
                        placeholder="Record your rationale, conditions or required changes."
                      />
                    </label>
                    <button className="production-submit">
                      {busy ? 'Saving…' : 'Save GM decision'}
                    </button>
                  </fieldset>
                </form>
              </>
            ) : (
              <>
                <h2>Sent to GM</h2>
                <p>
                  Waiting for {report?.recipient_name} to review and respond.
                </p>
                <button
                  disabled={busy || resource.loading}
                  onClick={resource.reload}
                >
                  Refresh GM decision
                </button>
              </>
            )}
            {report && session.can_switch && (
              <a
                className="scope-return-link"
                href={
                  supervisor
                    ? gmReportLink(
                        report.report_id,
                        report.asset.asset_id,
                        report.recipient_id,
                      )
                    : `#delegation?${new URLSearchParams({ asset: report.asset.asset_id, person: report.created_by })}`
                }
              >
                {supervisor
                  ? 'Review as GM'
                  : 'Return to supervisor case packet'}
              </a>
            )}
          </section>
          {guidedStep && <section className="production-review-card" data-flow="gm-handoff">
            <h2>Decision to accountable follow-up</h2>
            <p>Approval records the management decision. The supervisor separately assigns an owner, deadline, guidance, and evidence requirements. Returned cases need revision before proceeding; no work is assigned automatically.</p>
          </section>}
        </>
      )}
      {!evidence && guidedDetail && <GmFlowReference />}
    </div>
  );
}
