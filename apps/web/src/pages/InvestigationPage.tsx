import { useState } from 'react';

import type { PageId } from '../components/AppShell';
import { Icon } from '../components/Icon';
import { SignalChart } from '../components/SignalChart';
import { TraceButton } from '../components/TraceabilityContext';
import { ErrorState, LoadingState } from '../components/ViewState';
import { api, type ActionStatus, type AlertDetail, type SystemStatus, type TelemetryPoint, type TelemetrySeries } from '../lib/api';
import { actionsForAlert, rcaForAlert } from '../lib/demoWorkflow';
import { formatDate, formatDateTime, formatSignal, humanize } from '../lib/format';
import { useApiResource } from '../lib/useApiResource';
import { actionTransitionLabel, nextActionStatus } from '../lib/workflow';

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
  windowStart: string;
  windowEnd: string;
}

async function loadInvestigation(): Promise<InvestigationData> {
  const [alerts, system] = await Promise.all([api.alerts(), api.status()]);
  const alert = alerts[0];
  if (!alert) throw new Error('No problem is available for investigation');

  const detail = await api.alertDetail(alert.alert_id);
  const start = new Date(alert.first_signal_at);
  start.setHours(start.getHours() - 72);
  const end = new Date(alert.closed_at ?? alert.peak_score_at);
  end.setHours(end.getHours() + 72);
  const telemetry = await api.telemetry(alert.asset_id, 1800, start.toISOString(), end.toISOString());

  return { detail, telemetry, system, windowStart: start.toISOString(), windowEnd: end.toISOString() };
}

export function InvestigationPage({ onNavigate }: { onNavigate: (page: PageId) => void }) {
  const [selectedField, setSelectedField] = useState<SignalField>('water_in_oil_ppm');
  const [activeStep, setActiveStep] = useState(0);
  const [workflowBusy, setWorkflowBusy] = useState(false);
  const [workflowError, setWorkflowError] = useState<string | null>(null);
  const resource = useApiResource('problem-investigation', loadInvestigation);
  if (resource.loading) return <LoadingState/>;
  if (resource.error || !resource.data) return <ErrorState message={resource.error ?? 'Investigation data unavailable'}/>;

  const { detail, telemetry, system, windowStart, windowEnd } = resource.data;
  const { alert, opening_snapshot: opening, similar_incidents: incidents } = detail;
  const rca = rcaForAlert(alert.alert_id, detail.rca);
  const plans = actionsForAlert(alert.alert_id, detail.action_plans, Boolean(detail.rca));
  const actions = plans.flatMap((plan) => plan.actions);
  const hypothesis = rca?.generation.hypotheses[0];
  const selectedSignal = signalDefinitions.find((signal) => signal.field === selectedField)!;
  const selectedValues = telemetry.points.map((point) => Number(point[selectedField]));
  const latestPoint = telemetry.points.at(-1);

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
      'Reliability Engineer',
      system.llm_enabled ? 'ai' : 'prepared',
    ));
  }

  function startReview() {
    if (!detail.rca) return;
    return runWorkflow(() => api.updateRcaStatus(
      detail.rca!.rca_id,
      'UNDER_REVIEW',
      'Reliability Engineer',
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
        'Reliability Engineer',
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
      'Action Owner',
      `Action advanced to ${humanize(nextStatus)} from the investigation workspace.`,
    ));
  }

  return <div className="investigation-page">
    <button className="investigation-back" onClick={() => onNavigate('problems')}><Icon name="arrow"/> Back to Problem Tank</button>

    <header className="investigation-heading">
      <div>
        <span className="investigation-case-id">Priority 01 · {alert.alert_id}</span>
        <h1>KO-3201 compressor degradation</h1>
        <p>One governed view from abnormal signal detection to root-cause decision and follow-up execution.</p>
      </div>
      <div className="investigation-state"><span>Current workflow</span><strong>{humanize(detail.action_plans[0]?.status ?? detail.rca?.status ?? 'RCA not started')}</strong><p>{detail.action_plans.length ? `${actions.filter((action) => action.status === 'CLOSED').length} of ${actions.length} actions closed` : 'No action plan created'}</p></div>
    </header>

    <nav className="storyline-nav" aria-label="Investigation storyline">
      {storySteps.map((step, index) => <button key={step} className={`${index === activeStep ? 'active' : ''}${index < activeStep ? ' complete' : ''}`} onClick={() => setActiveStep(index)}><span>{String(index + 1).padStart(2, '0')}</span>{step}</button>)}
    </nav>

    <section className="investigation-section" hidden={activeStep !== 0}>
      <div className="investigation-hero-grid">
        <article className="degradation-chart panel">
          <header><div><span>Anomaly trajectory</span><h3>From first deviation to intervention</h3></div><div><span>Peak score</span><strong>{formatSignal(alert.peak_anomaly_score)}</strong><TraceButton traceId="health-trajectory">View sources</TraceButton></div></header>
          <div className="degradation-chart-canvas"><SignalChart points={telemetry.points} field="anomaly_score" threshold={opening.anomaly_threshold}/></div>
          <div className="degradation-dates"><span>{formatDate(windowStart)} · context</span><span>{formatDate(alert.first_signal_at)} · first signal</span><span>{formatDate(windowEnd)} · response</span></div>
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
          {signalDefinitions.map((signal) => <button key={signal.field} className={selectedField === signal.field ? 'active' : ''} onClick={() => setSelectedField(signal.field)}><span>{signal.label}</span><strong>{latestPoint ? formatSignal(Number(latestPoint[signal.field])) : '—'} <small>{signal.unit}</small></strong><i>{signal.source}</i></button>)}
        </nav>
        <div className="investigation-signal-chart">
          <header><div><span>{selectedSignal.label}</span><h3>Degradation-window trend</h3></div><div><span>Window peak</span><strong>{selectedValues.length ? formatSignal(Math.max(...selectedValues)) : '—'} {selectedSignal.unit}</strong></div></header>
          <SignalChart points={telemetry.points} field={selectedField}/>
          <div className="investigation-trace-footer"><p>Source: {selectedSignal.source}</p><TraceButton traceId="condition-insights">Inspect lineage</TraceButton></div>
        </div>
      </article>
    </section>

    <section className="investigation-section" hidden={activeStep !== 2}>
      <div className="rca-story-grid">
        <article className="leading-cause panel">
          <header className="investigation-trace-heading"><span>Leading hypothesis · {hypothesis ? Math.round(hypothesis.confidence * 100) : 0}% confidence</span><TraceButton traceId="rca-indication">View evidence sources</TraceButton></header>
          <h3>{hypothesis?.title ?? 'RCA awaiting review'}</h3>
          <p>{hypothesis?.mechanism ?? 'No root-cause hypothesis is available.'}</p>
          <div><strong>Why this ranks first</strong><p>{hypothesis?.rationale}</p></div>
          <WorkflowControls
            rcaStatus={detail.rca?.status ?? null}
            hasPlan={detail.action_plans.length > 0}
            busy={workflowBusy}
            error={workflowError}
            draftMode={system.llm_enabled ? 'AI-generated' : 'Prepared-case'}
            onCreateDraft={createDraft}
            onStartReview={startReview}
            onApprove={approveAndCreatePlan}
            onReject={() => detail.rca && runWorkflow(() => api.updateRcaStatus(detail.rca!.rca_id, 'REJECTED', 'Reliability Engineer', 'Draft rejected for further investigation.'))}
            onCreatePlan={createPlan}
          />
        </article>
        <article className="cause-evidence panel">
          <header><span>Evidence chain</span><strong>{opening.top_drivers.length} model drivers</strong></header>
          {opening.top_drivers.map((driver, index) => <div key={driver.name}><span>{String(index + 1).padStart(2, '0')}</span><p>{humanize(driver.name.replaceAll('.', '_'))}</p><strong>{formatSignal(driver.score)}</strong></div>)}
          <footer>{incidents.length} historical analogues retrieved · best match {incidents[0] ? `${Math.round(incidents[0].hybrid_score * 100)}%` : '—'}</footer>
        </article>
      </div>
    </section>

    <section className="investigation-section" hidden={activeStep !== 3}>
      <div className="investigation-section-trace"><TraceButton traceId="capa-plan">View CA/PA sources and lineage</TraceButton></div>
      <div className="investigation-action-list panel">
        <header><span>Priority and action</span><span>Owner</span><span>Status</span><span>Due date</span></header>
        {actions.map((action) => {
          const nextStatus = detail.action_plans.length ? nextActionStatus(action.status) : null;
          return <div key={action.action_id}><div><span>{humanize(action.priority)}</span><strong>{action.title}</strong><p>{action.effectiveness_check}</p></div><strong>{action.owner_role}</strong><div className="action-workflow-state"><span className={`action-state ${action.status.toLowerCase()}`}>{humanize(action.status)}</span>{nextStatus && <button disabled={workflowBusy} onClick={() => updateAction(action.action_id, action.status)}>{actionTransitionLabel(nextStatus)}</button>}</div><time>{formatDate(action.due_date)}</time></div>;
        })}
      </div>
      {workflowError && <p className="workflow-error">{workflowError}</p>}
    </section>

    <footer className="story-controls">
      <button className="story-previous" disabled={activeStep === 0} onClick={() => setActiveStep((step) => Math.max(0, step - 1))}><Icon name="arrow"/> Previous</button>
      {activeStep < storySteps.length - 1
        ? <button className="story-next" onClick={() => setActiveStep((step) => Math.min(storySteps.length - 1, step + 1))}>Next: {storySteps[activeStep + 1]} <Icon name="arrow"/></button>
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
