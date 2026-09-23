import { useEffect, useState } from 'react';

import type { PageId } from '../components/AppShell';
import { Icon } from '../components/Icon';
import { SignalChart } from '../components/SignalChart';
import { TraceButton } from '../components/TraceabilityContext';
import { ErrorState, LoadingState } from '../components/ViewState';
import { api, type ActionStatus, type AlertDetail, type DriverAnalysis, type InvestigationEvidenceProgress, type SystemStatus, type TelemetryPoint, type TelemetrySeries } from '../lib/api';
import { contributionForField } from '../lib/driverAnalysis';
import { formatDate, formatDateTime, formatSignal, humanize } from '../lib/format';
import { alertDetectionWindow, selectTelemetryWindow, timeWindowHours } from '../lib/timeWindow';
import { useApiResource } from '../lib/useApiResource';
import { actionTransitionLabel, nextActionStatus } from '../lib/workflow';
import { workflowView } from '../lib/workflowView';

type SignalField = keyof Pick<TelemetryPoint,
  'radial_vibration_micron' | 'water_in_oil_ppm' | 'lube_oil_pressure_barg' |
  'bearing_metal_temperature_degc' | 'feed_rate_tph' | 'discharge_pressure_barg'>;

const signalDefinitions: Array<{ field: SignalField; label: string; unit: string; source: string }> = [
  { field: 'water_in_oil_ppm', label: 'Water in oil', unit: 'ppm', source: 'Equipment Performance · Condition History' },
  { field: 'radial_vibration_micron', label: 'Radial vibration', unit: 'µm', source: 'Equipment Performance · Condition History' },
  { field: 'lube_oil_pressure_barg', label: 'Lube oil pressure', unit: 'barg', source: 'Equipment Performance · Condition History' },
  { field: 'bearing_metal_temperature_degc', label: 'Bearing temperature', unit: '°C', source: 'Equipment Performance · Condition History' },
  { field: 'feed_rate_tph', label: 'Feed rate', unit: 'tph', source: 'Production Data · Sheet2' },
  { field: 'discharge_pressure_barg', label: 'Discharge pressure', unit: 'barg', source: 'Production Data · Sheet2' },
];

const storySteps = ['Detection', 'Variables', 'Probable RCA', 'CA/PA'];

interface InvestigationData {
  detail: AlertDetail;
  telemetry: TelemetrySeries;
  system: SystemStatus;
  driverAnalysis: DriverAnalysis;
}

async function loadInvestigation(): Promise<InvestigationData> {
  const [alerts, system] = await Promise.all([api.alerts(), api.status()]);
  const alert = alerts[0];
  if (!alert) throw new Error('No problem is available for investigation');

  const [detail, driverAnalysis] = await Promise.all([
    api.alertDetail(alert.alert_id),
    api.driverAnalysis(alert.alert_id, alert.opened_at),
  ]);
  const start = new Date(alert.first_signal_at);
  start.setHours(start.getHours() - 72);
  const end = new Date(alert.closed_at ?? alert.peak_score_at);
  end.setHours(end.getHours() + 72);
  const telemetry = await api.telemetry(alert.asset_id, 1800, start.toISOString(), end.toISOString());

  return { detail, telemetry, system, driverAnalysis };
}

export function InvestigationPage({ onNavigate }: { onNavigate: (page: PageId) => void }) {
  const [selectedField, setSelectedField] = useState<SignalField>('water_in_oil_ppm');
  const [activeStep, setActiveStep] = useState(0);
  const [workflowBusy, setWorkflowBusy] = useState(false);
  const [workflowError, setWorkflowError] = useState<string | null>(null);
  const [replayAt, setReplayAt] = useState<string | null>(null);
  const [replayPlaying, setReplayPlaying] = useState(false);
  const resource = useApiResource('problem-investigation', loadInvestigation);
  const alertId = resource.data?.detail.alert.alert_id;
  const evidenceResource = useApiResource<InvestigationEvidenceProgress | null>(
    `${alertId ?? ''}:${replayAt ?? ''}`,
    () => alertId && replayAt ? api.investigationEvidence(alertId, replayAt) : Promise.resolve(null),
  );
  const replayDriverResource = useApiResource<{ requestedAt: string; analysis: DriverAnalysis } | null>(
    `driver:${alertId ?? ''}:${replayAt ?? ''}`,
    () => alertId && replayAt
      ? api.driverAnalysis(alertId, replayAt).then((analysis) => ({ requestedAt: replayAt, analysis }))
      : Promise.resolve(null),
  );
  const progress = evidenceResource.data?.as_of === replayAt ? evidenceResource.data : null;

  useEffect(() => {
    if (resource.data && replayAt === null) setReplayAt(resource.data.detail.alert.opened_at);
  }, [resource.data, replayAt]);

  useEffect(() => {
    if (!replayPlaying || activeStep !== 2 || !progress?.next_event_at) return;
    const timer = window.setTimeout(() => setReplayAt(progress.next_event_at), 2200);
    return () => window.clearTimeout(timer);
  }, [replayPlaying, activeStep, progress]);

  if (resource.loading) return <LoadingState/>;
  if (resource.error || !resource.data) return <ErrorState message={resource.error ?? 'Investigation data unavailable'}/>;

  const { detail, telemetry, system, driverAnalysis } = resource.data;
  const { alert, opening_snapshot: opening, similar_incidents: incidents } = detail;
  const detectionWindow = alertDetectionWindow(alert, detail.state_transitions);
  const detectionPoints = selectTelemetryWindow(telemetry.points, detectionWindow);
  const { rca, actionPlans: plans } = workflowView(detail);
  const actions = plans.flatMap((plan) => plan.actions);
  const hypothesis = rca?.generation.hypotheses[0];
  const replayDriver = replayDriverResource.data?.requestedAt === replayAt
    ? replayDriverResource.data.analysis : null;
  const causeReported = progress?.stage === 'CAUSE_REPORTED' || progress?.stage === 'REPAIR_REPORTED';
  const repairReported = progress?.stage === 'REPAIR_REPORTED';
  const causeTitle = causeReported
    ? 'Cooler leak and bearing distress reported'
    : progress?.stage === 'CONTAMINATION_SUPPORTED'
      ? 'Oil contamination supported by sample'
      : 'Lubrication contamination suspected';
  const selectedSignal = signalDefinitions.find((signal) => signal.field === selectedField)!;
  const selectedValues = detectionPoints.map((point) => Number(point[selectedField]));
  const latestPoint = detectionPoints.at(-1);

  async function runWorkflow(operation: () => Promise<unknown>, nextStep?: number) {
    setWorkflowBusy(true);
    setWorkflowError(null);
    try {
      await operation();
      if (nextStep !== undefined) setActiveStep(nextStep);
    } catch (error) {
      setWorkflowError(error instanceof Error ? error.message : 'Workflow update failed');
    } finally {
      setWorkflowBusy(false);
      resource.reload();
    }
  }

  function createDraft() {
    return runWorkflow(() => api.generateRca(
      alert.alert_id,
      system.llm_enabled ? 'ai' : 'prepared',
    ));
  }

  function startReview() {
    if (!detail.rca) return;
    return runWorkflow(() => api.updateRcaStatus(
      detail.rca!.rca_id,
      'UNDER_REVIEW',
      'Evidence review started from the investigation workspace.',
    ));
  }

  function approveAndCreatePlan() {
    if (!detail.rca) return;
    const selectedHypothesis = detail.rca.generation.hypotheses[0];
    return runWorkflow(async () => {
      const approved = await api.updateRcaStatus(
        detail.rca!.rca_id,
        'APPROVED',
        'Leading cause accepted against the available evidence.',
      );
      await api.createActionPlan(approved.rca_id, selectedHypothesis.hypothesis_id);
    }, 3);
  }

  function createPlan() {
    if (!detail.rca) return;
    return runWorkflow(() => api.createActionPlan(
      detail.rca!.rca_id,
      detail.rca!.generation.hypotheses[0].hypothesis_id,
    ), 3);
  }

  function updateAction(actionId: string, currentStatus: ActionStatus) {
    const nextStatus = nextActionStatus(currentStatus);
    if (!nextStatus) return;
    return runWorkflow(() => api.updateActionStatus(
      actionId,
      nextStatus,
      `Action advanced to ${humanize(nextStatus)} from the investigation workspace.`,
    ));
  }

  function openStep(step: number) {
    setActiveStep(step);
    setReplayPlaying(step === 2 && (replayAt === alert.opened_at || Boolean(progress?.next_event_at)));
  }

  return <div className="investigation-page">
    <button className="investigation-back" onClick={() => onNavigate('problems')}><Icon name="arrow"/> Back to Problem Tank</button>

    <header className="investigation-heading">
      <div>
        <span className="investigation-case-id">Priority 01 · {alert.alert_id}</span>
        <h1>KO-3201 compressor degradation</h1>
        <p>One governed view from abnormal signal detection to root-cause decision and follow-up execution.</p>
      </div>
      <div className="investigation-state"><span>{activeStep === 2 ? 'Evidence state' : 'Current workflow'}</span><strong>{activeStep === 2 ? humanize(progress?.stage ?? 'Probable') : humanize(plans[0]?.status ?? rca?.status ?? 'RCA not started')}</strong><p>{activeStep === 2 ? formatDateTime(replayAt ?? alert.opened_at) : plans.length ? `${actions.filter((action) => action.status === 'CLOSED').length} of ${actions.length} actions closed` : 'No action plan created'}</p></div>
    </header>

    <nav className="storyline-nav" aria-label="Investigation storyline">
      {storySteps.map((step, index) => <button key={step} className={`${index === activeStep ? 'active' : ''}${index < activeStep ? ' complete' : ''}`} onClick={() => openStep(index)}><span>{String(index + 1).padStart(2, '0')}</span>{step}</button>)}
    </nav>

    <section className="investigation-section" hidden={activeStep !== 0}>
      <div className="investigation-hero-grid">
        <article className="degradation-chart panel">
          <header><div><span>Anomaly trajectory</span><h3>From first signal to warning</h3></div><div><span>Alert peak</span><strong>{formatSignal(alert.peak_anomaly_score)}</strong><TraceButton traceId="health-trajectory">View sources</TraceButton></div></header>
          <div className="degradation-chart-canvas"><SignalChart points={telemetry.points} field="anomaly_score" threshold={opening.anomaly_threshold} highlightWindow={detectionWindow}/></div>
          <div className="degradation-dates"><span>{formatDateTime(detectionWindow.start)} · first signal</span><span>{formatSignal(timeWindowHours(detectionWindow))} h · evidence window</span><span>{formatDateTime(detectionWindow.end)} · warning</span></div>
        </article>
        <article className="investigation-facts panel">
          <div><span>Severity</span><strong>{humanize(alert.highest_severity)}</strong></div>
          <div><span>Alert opened</span><strong>{formatDateTime(alert.opened_at)}</strong></div>
          <div><span>Persistence</span><strong>{Math.round(alert.duration_hours).toLocaleString()} hours</strong></div>
          <div><span>Correlated signals</span><strong>{alert.breached_signals.length} variables</strong></div>
          <p>The model escalated this case because the anomaly persisted and independent condition parameters converged.</p>
        </article>
      </div>
    </section>

    <section className="investigation-section" hidden={activeStep !== 1}>
      <article className="investigation-signal-panel panel">
        <nav aria-label="Investigated variables">
          {signalDefinitions.map((signal) => { const contribution = contributionForField(driverAnalysis, signal.field); return <button key={signal.field} className={selectedField === signal.field ? 'active' : ''} onClick={() => setSelectedField(signal.field)}><span>{signal.label}</span><strong>{contribution ? `${formatSignal(contribution.contribution_percent)}%` : latestPoint ? formatSignal(Number(latestPoint[signal.field])) : '—'} <small>{contribution ? 'contribution' : signal.unit}</small></strong><i>{signal.source}</i></button>; })}
        </nav>
        <div className="investigation-signal-chart">
          <header><div><span>{selectedSignal.label}</span><h3>Degradation-window trend</h3></div><div><span>Window peak</span><strong>{selectedValues.length ? formatSignal(Math.max(...selectedValues)) : '—'} {selectedSignal.unit}</strong></div></header>
          <SignalChart points={detectionPoints} field={selectedField} highlightWindow={detectionWindow}/>
          <div className="investigation-trace-footer"><p>Source: {selectedSignal.source}</p><TraceButton traceId="condition-insights">Inspect lineage</TraceButton></div>
        </div>
      </article>
    </section>

    <section className="investigation-section" hidden={activeStep !== 2}>
      <div className="evidence-replay panel">
        <div className="evidence-replay-heading">
          <div><span>Evidence replay · {formatDateTime(replayAt ?? alert.opened_at)}</span><strong>{humanize(progress?.stage ?? 'Probable')}</strong></div>
          <div className="evidence-replay-controls">
            <button onClick={() => { setReplayAt(alert.opened_at); setReplayPlaying(true); }}>Restart</button>
            {progress?.next_event_at && <button onClick={() => setReplayPlaying((playing) => !playing)}>{replayPlaying ? 'Pause' : 'Play'}</button>}
          </div>
        </div>
        <p>{progress?.summary ?? 'Loading evidence at this point in time…'}</p>
        {evidenceResource.error && <p className="workflow-error">{evidenceResource.error}</p>}
        <div className="evidence-replay-events">
          {progress?.events.length ? progress.events.map((event) => <div key={event.event_id}>
            <time>{formatDateTime(event.occurred_at)}</time>
            <div><strong>{event.title}</strong><p>{event.detail}</p><small>{humanize(event.kind)} · {event.source_reference} · {humanize(event.source_grade)}</small></div>
          </div>) : <span>No post-alert lab or inspection evidence available yet.</span>}
        </div>
        <small className="evidence-replay-note">Times are recorded event times from the RCA; document ingestion times were not supplied.</small>
      </div>
      <div className="rca-story-grid">
        <article className="leading-cause panel">
          <header className="investigation-trace-heading"><span>{causeReported ? 'RCA-reported cause' : 'Leading hypothesis'}</span>{causeReported && <TraceButton traceId="rca-indication">View evidence sources</TraceButton>}</header>
          <h3>{causeTitle}</h3>
          <p>{progress?.summary ?? 'Reviewing the condition evidence available at this time.'}</p>
          <div><strong>{causeReported ? 'Case interpretation' : 'What remains unverified'}</strong><p>{causeReported ? hypothesis?.rationale : 'The source of water entry and bearing condition require lab and inspection evidence. The current signal pattern alone cannot prove the physical cause.'}</p></div>
          {causeReported && <WorkflowControls
            rcaStatus={detail.rca?.status ?? null}
            hasPlan={detail.action_plans.length > 0}
            busy={workflowBusy}
            error={workflowError}
            draftMode={system.llm_enabled ? 'AI-generated' : 'Prepared-case'}
            onCreateDraft={createDraft}
            onStartReview={startReview}
            onApprove={approveAndCreatePlan}
            onReject={() => detail.rca && runWorkflow(() => api.updateRcaStatus(detail.rca!.rca_id, 'REJECTED', 'Draft rejected for further investigation.'))}
            onCreatePlan={createPlan}
          />}
        </article>
        <article className="cause-evidence panel">
          <header><span>Model contribution at replay time</span><strong>{replayDriver?.contributions.length ?? '—'} condition drivers</strong></header>
          {replayDriver?.contributions.map((driver, index) => <div key={driver.driver_name}><span>{String(index + 1).padStart(2, '0')}</span><p>{humanize(driver.signal_key)}</p><strong>{formatSignal(driver.contribution_percent)}%</strong></div>)}
          {replayDriverResource.error && <p className="workflow-error">{replayDriverResource.error}</p>}
          <footer>Counterfactual model explanation · {incidents.length} historical analogues retrieved</footer>
        </article>
      </div>
    </section>

    <section className="investigation-section" hidden={activeStep !== 3}>
      {!repairReported && <p className="evidence-replay-notice panel">Follow-up record is available once the evidence replay reaches the repair entry. Return to Probable RCA to continue the replay.</p>}
      {repairReported && <>
      <div className="investigation-section-trace"><TraceButton traceId="capa-plan">View CA/PA sources and lineage</TraceButton></div>
      <div className="investigation-action-list panel">
        <header><span>Priority and action</span><span>Owner</span><span>Status</span><span>Due date</span></header>
        {actions.map((action) => {
          const nextStatus = detail.action_plans.length ? nextActionStatus(action.status) : null;
          return <div key={action.action_id}><div><span>{humanize(action.priority)}</span><strong>{action.title}</strong><p>{action.effectiveness_check}</p></div><strong>{action.owner_role}</strong><div className="action-workflow-state"><span className={`action-state ${action.status.toLowerCase()}`}>{humanize(action.status)}</span>{nextStatus && <button disabled={workflowBusy} onClick={() => updateAction(action.action_id, action.status)}>{actionTransitionLabel(nextStatus)}</button>}</div><time>{formatDate(action.due_date)}</time></div>;
        })}
      </div>
      {workflowError && <p className="workflow-error">{workflowError}</p>}
      </>}
    </section>

    <footer className="story-controls">
      <button className="story-previous" disabled={activeStep === 0} onClick={() => openStep(Math.max(0, activeStep - 1))}><Icon name="arrow"/> Previous</button>
      {activeStep < storySteps.length - 1
        ? <button className="story-next" onClick={() => openStep(Math.min(storySteps.length - 1, activeStep + 1))}>Next: {storySteps[activeStep + 1]} <Icon name="arrow"/></button>
        : <button className="story-next" onClick={() => onNavigate('actions')}>Open action tracker <Icon name="arrow"/></button>}
    </footer>
  </div>;
}

function WorkflowControls({ rcaStatus, hasPlan, busy, error, draftMode, onCreateDraft, onStartReview, onApprove, onReject, onCreatePlan }: {
  rcaStatus: string | null;
  hasPlan: boolean;
  busy: boolean;
  error: string | null;
  draftMode: string;
  onCreateDraft: () => void;
  onStartReview: () => void;
  onApprove: () => void;
  onReject: () => void;
  onCreatePlan: () => void;
}) {
  return <div className="rca-workflow-controls">
    <div><span>Decision workflow</span><strong>{rcaStatus ? humanize(rcaStatus) : `${draftMode} draft preview`}</strong></div>
    <div>
      {!rcaStatus && <button className="workflow-primary" disabled={busy} onClick={onCreateDraft}>{busy ? 'Creating…' : 'Create reviewable draft'}</button>}
      {rcaStatus === 'AI_DRAFT' && <button className="workflow-primary" disabled={busy} onClick={onStartReview}>{busy ? 'Updating…' : 'Start human review'}</button>}
      {rcaStatus === 'UNDER_REVIEW' && <><button className="workflow-secondary" disabled={busy} onClick={onReject}>Reject draft</button><button className="workflow-primary" disabled={busy} onClick={onApprove}>{busy ? 'Creating plan…' : 'Approve and create CA/PA'}</button></>}
      {rcaStatus === 'APPROVED' && !hasPlan && <button className="workflow-primary" disabled={busy} onClick={onCreatePlan}>{busy ? 'Creating…' : 'Create CA/PA plan'}</button>}
      {rcaStatus === 'APPROVED' && hasPlan && <span className="workflow-complete"><Icon name="check"/> Approved · CA/PA created</span>}
      {rcaStatus === 'REJECTED' && <span className="workflow-rejected">Rejected · further evidence required</span>}
    </div>
    {error && <p>{error}</p>}
  </div>;
}
