import { useState } from 'react';

import type { PageId } from '../components/AppShell';
import { Icon } from '../components/Icon';
import { SignalChart } from '../components/SignalChart';
import { ErrorState, LoadingState } from '../components/ViewState';
import { api, type AlertDetail, type TelemetryPoint, type TelemetrySeries } from '../lib/api';
import { actionsForAlert, rcaForAlert } from '../lib/demoWorkflow';
import { formatDate, formatDateTime, formatSignal, humanize } from '../lib/format';
import { useApiResource } from '../lib/useApiResource';

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

const storySteps = ['Detection', 'Variables', 'Probable RCA', 'Source trace', 'CA/PA'];

interface InvestigationData {
  detail: AlertDetail;
  telemetry: TelemetrySeries;
  windowStart: string;
  windowEnd: string;
}

async function loadInvestigation(): Promise<InvestigationData> {
  const alerts = await api.alerts();
  const alert = alerts[0];
  if (!alert) throw new Error('No problem is available for investigation');

  const detail = await api.alertDetail(alert.alert_id);
  const start = new Date(alert.first_signal_at);
  start.setHours(start.getHours() - 72);
  const end = new Date(alert.closed_at ?? alert.peak_score_at);
  end.setHours(end.getHours() + 72);
  const telemetry = await api.telemetry(alert.asset_id, 1800, start.toISOString(), end.toISOString());

  return { detail, telemetry, windowStart: start.toISOString(), windowEnd: end.toISOString() };
}

export function InvestigationPage({ onNavigate }: { onNavigate: (page: PageId) => void }) {
  const [selectedField, setSelectedField] = useState<SignalField>('water_in_oil_ppm');
  const [activeStep, setActiveStep] = useState(0);
  const resource = useApiResource('problem-investigation', loadInvestigation);
  if (resource.loading) return <LoadingState/>;
  if (resource.error || !resource.data) return <ErrorState message={resource.error ?? 'Investigation data unavailable'}/>;

  const { detail, telemetry, windowStart, windowEnd } = resource.data;
  const { alert, opening_snapshot: opening, similar_incidents: incidents } = detail;
  const rca = rcaForAlert(alert.alert_id, detail.rca);
  const plans = actionsForAlert(alert.alert_id, detail.action_plans);
  const actions = plans.flatMap((plan) => plan.actions);
  const hypothesis = rca?.generation.hypotheses[0];
  const selectedSignal = signalDefinitions.find((signal) => signal.field === selectedField)!;
  const selectedValues = telemetry.points.map((point) => Number(point[selectedField]));
  const latestPoint = telemetry.points.at(-1);

  return <div className="investigation-page">
    <button className="investigation-back" onClick={() => onNavigate('problems')}><Icon name="arrow"/> Back to Problem Tank</button>

    <header className="investigation-heading">
      <div>
        <span className="investigation-case-id">Priority 01 · {alert.alert_id}</span>
        <h1>KO-3201 compressor degradation</h1>
        <p>One governed view from abnormal signal detection to root-cause decision and follow-up execution.</p>
      </div>
      <div className="investigation-state"><span>Current workflow</span><strong>{humanize(plans[0]?.status ?? alert.status)}</strong><p>{actions.filter((action) => action.status === 'CLOSED').length} of {actions.length} actions closed</p></div>
    </header>

    <nav className="storyline-nav" aria-label="Investigation storyline">
      {storySteps.map((step, index) => <button key={step} className={`${index === activeStep ? 'active' : ''}${index < activeStep ? ' complete' : ''}`} onClick={() => setActiveStep(index)}><span>{String(index + 1).padStart(2, '0')}</span>{step}</button>)}
    </nav>

    <section className="investigation-section" hidden={activeStep !== 0}>
      <StoryHeader number="01" eyebrow="Issue detection" title="The degradation window" description="The chart begins 72 hours before the first persistent signal and ends after the alert closes, keeping the investigation focused on the event."/>
      <div className="investigation-hero-grid">
        <article className="degradation-chart panel">
          <header><div><span>Anomaly trajectory</span><h3>From first deviation to intervention</h3></div><div><span>Peak score</span><strong>{formatSignal(alert.peak_anomaly_score)}</strong></div></header>
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
      <StoryHeader number="02" eyebrow="Condition evidence" title="Which variables changed" description="Select any condition or operating variable to inspect its behavior during the same degradation window."/>
      <article className="investigation-signal-panel panel">
        <nav aria-label="Investigated variables">
          {signalDefinitions.map((signal) => <button key={signal.field} className={selectedField === signal.field ? 'active' : ''} onClick={() => setSelectedField(signal.field)}><span>{signal.label}</span><strong>{latestPoint ? formatSignal(Number(latestPoint[signal.field])) : '—'} <small>{signal.unit}</small></strong><i>{signal.source}</i></button>)}
        </nav>
        <div className="investigation-signal-chart">
          <header><div><span>{selectedSignal.label}</span><h3>Degradation-window trend</h3></div><div><span>Window peak</span><strong>{selectedValues.length ? formatSignal(Math.max(...selectedValues)) : '—'} {selectedSignal.unit}</strong></div></header>
          <SignalChart points={telemetry.points} field={selectedField}/>
          <p>Source: {selectedSignal.source}</p>
        </div>
      </article>
    </section>

    <section className="investigation-section" hidden={activeStep !== 2}>
      <StoryHeader number="03" eyebrow="Root cause indication" title="What most likely happened" description="The leading explanation combines signal sequence, physical mechanism, and similar historical incidents. It remains traceable to supporting evidence."/>
      <div className="rca-story-grid">
        <article className="leading-cause panel">
          <span>Leading hypothesis · {hypothesis ? Math.round(hypothesis.confidence * 100) : 0}% confidence</span>
          <h3>{hypothesis?.title ?? 'RCA awaiting review'}</h3>
          <p>{hypothesis?.mechanism ?? 'No root-cause hypothesis is available.'}</p>
          <div><strong>Why this ranks first</strong><p>{hypothesis?.rationale}</p></div>
        </article>
        <article className="cause-evidence panel">
          <header><span>Evidence chain</span><strong>{opening.top_drivers.length} model drivers</strong></header>
          {opening.top_drivers.map((driver, index) => <div key={driver.name}><span>{String(index + 1).padStart(2, '0')}</span><p>{humanize(driver.name.replaceAll('.', '_'))}</p><strong>{formatSignal(driver.score)}</strong></div>)}
          <footer>{incidents.length} historical analogues retrieved · best match {incidents[0] ? `${Math.round(incidents[0].hybrid_score * 100)}%` : '—'}</footer>
        </article>
      </div>
    </section>

    <section className="investigation-section" hidden={activeStep !== 3}>
      <StoryHeader number="04" eyebrow="Governed evidence" title="Where every insight came from" description="Each analytical statement links back to its operational source, transformation, and role in the decision."/>
      <div className="source-trace-list panel">
        <SourceRow label="Hourly operating context" source="Production Data - RCA2 KO-3201.xlsx" detail="Feed rate, discharge pressure, operating status, shutdown and restart context" use="Detection and operating context" href="https://drive.google.com/file/d/1xHVQZcSJZg0-Tknd2PjZ8mJVByQsFDMr"/>
        <SourceRow label="Equipment condition" source="Equipment Performance - RCA2 KO-3201.xlsx" detail="Vibration, oil water content, oil pressure, bearing temperature and engineering limits" use="Variable evidence and thresholds" href="https://drive.google.com/file/d/1JbDwEz1q3NRxW4OVrJR9q9M7ec2Nn0Ch"/>
        <SourceRow label="Anomaly decision" source="KO-3201 Isolation Forest v1" detail="Canonical hourly features scored against a calibrated decision threshold" use="Detection, severity and drivers"/>
        <SourceRow label="Historical context" source="Incident Database.xlsx" detail="Governed corpus of 380 historical manufacturing incidents" use="Similar-incident retrieval" href="https://drive.google.com/file/d/12zoQhytgMpmOlR-cKeF-WPmw-Tn5fk6Z"/>
        <SourceRow label="Reported RCA history" source="RCA2 - KO-3201 High Radial Vibration Trip.pptx" detail="Reported chronology, root-cause statements, actions and impact" use="RCA grounding and validation" href="https://drive.google.com/file/d/1Fwbx5RIeBsHEftLaVNbYgFUDSEcvB9iX"/>
      </div>
    </section>

    <section className="investigation-section" hidden={activeStep !== 4}>
      <StoryHeader number="05" eyebrow="Follow-up execution" title="Who needs to do what next" description="Recommended actions are prioritized, assigned to accountable roles, and tracked through completion and effectiveness checks."/>
      <div className="investigation-action-list panel">
        <header><span>Priority and action</span><span>Owner</span><span>Status</span><span>Due date</span></header>
        {actions.map((action) => <div key={action.action_id}><div><span>{humanize(action.priority)}</span><strong>{action.title}</strong><p>{action.effectiveness_check}</p></div><strong>{action.owner_role}</strong><span className={`action-state ${action.status.toLowerCase()}`}>{humanize(action.status)}</span><time>{formatDate(action.due_date)}</time></div>)}
      </div>
    </section>

    <footer className="story-controls">
      <button className="story-previous" disabled={activeStep === 0} onClick={() => setActiveStep((step) => Math.max(0, step - 1))}><Icon name="arrow"/> Previous</button>
      <p><span>Step {activeStep + 1} of {storySteps.length}</span><strong>{storySteps[activeStep]}</strong></p>
      {activeStep < storySteps.length - 1
        ? <button className="story-next" onClick={() => setActiveStep((step) => Math.min(storySteps.length - 1, step + 1))}>Next: {storySteps[activeStep + 1]} <Icon name="arrow"/></button>
        : <button className="story-next" onClick={() => onNavigate('actions')}>Open action tracker <Icon name="arrow"/></button>}
    </footer>
  </div>;
}

function StoryHeader({ number, eyebrow, title, description }: { number: string; eyebrow: string; title: string; description: string }) {
  return <header className="story-header"><span>{number}</span><div><p>{eyebrow}</p><h2>{title}</h2><strong>{description}</strong></div></header>;
}

function SourceRow({ label, source, detail, use, href }: { label: string; source: string; detail: string; use: string; href?: string }) {
  const name = href ? <a href={href} target="_blank" rel="noreferrer">{source} <Icon name="arrow"/></a> : <strong>{source}</strong>;
  return <div><span>{label}</span><div>{name}<p>{detail}</p></div><b>{use}</b></div>;
}
