import { useState } from 'react';

import type { PageId } from '../components/AppShell';
import { Icon } from '../components/Icon';
import { SignalChart } from '../components/SignalChart';
import { TraceButton } from '../components/TraceabilityContext';
import { EmptyState, ErrorState, LoadingState } from '../components/ViewState';
import { api, type AlertDetail, type InvestigationEvidenceProgress, type TelemetryPoint, type TelemetrySeries } from '../lib/api';
import { PRIMARY_ASSET_ID } from '../lib/appConfig';
import { conditionSignals, type ConditionField } from '../lib/conditionSignals';
import { formatDateTime, formatSignal, humanize } from '../lib/format';
import { rcaCheckpoints, type RcaCheckpoint } from '../lib/rcaCheckpoints';
import { alertDetectionWindow, selectTelemetryWindow, type TimeWindow } from '../lib/timeWindow';
import { useApiResource } from '../lib/useApiResource';

interface InvestigationData {
  detail: AlertDetail;
  chronology: InvestigationEvidenceProgress;
  telemetry: TelemetrySeries;
}

const linkSignals: Record<string, { field: ConditionField; interpretation: string }> = {
  cooler_ingress: { field: 'water_in_oil_ppm', interpretation: 'Water-in-oil is a downstream clue. It cannot locate a cooler leak without inspection.' },
  water_contamination: { field: 'water_in_oil_ppm', interpretation: 'The monitored water trend supports contamination; the reported lab sample is a separate source.' },
  bearing_distress: { field: 'bearing_metal_temperature_degc', interpretation: 'Bearing temperature gives thermal context. Physical distress requires the inspection record.' },
  vibration_trip: { field: 'radial_vibration_micron', interpretation: 'Vibration tracks the mechanical response. The trip value is reported in the RCA chronology.' },
};

const initialLink: Record<RcaCheckpoint['kind'], string> = {
  WARNING: 'water_contamination',
  SENSOR: 'vibration_trip',
  LAB: 'water_contamination',
  INSPECTION: 'cooler_ingress',
  ACTION: 'cooler_ingress',
};

async function loadInvestigation(): Promise<InvestigationData | null> {
  const alerts = await api.alerts(PRIMARY_ASSET_ID);
  const alert = alerts[0];
  if (!alert) return null;
  const [detail, chronology, telemetry] = await Promise.all([
    api.alertDetail(alert.alert_id),
    api.investigationEvidence(alert.alert_id),
    api.telemetry(alert.asset_id, 5000),
  ]);
  return { detail, chronology, telemetry };
}

function checkpointWindow(checkpoint: RcaCheckpoint, detail: AlertDetail): TimeWindow {
  if (checkpoint.kind === 'WARNING') return alertDetectionWindow(detail.alert, detail.state_transitions);
  const center = new Date(checkpoint.asOf).getTime();
  const radius = 48 * 60 * 60 * 1000;
  return { start: new Date(center - radius).toISOString(), end: new Date(center + radius).toISOString() };
}

function nearestReading(points: TelemetryPoint[], at: string): TelemetryPoint | null {
  const target = new Date(at).getTime();
  return points.reduce<TelemetryPoint | null>((nearest, point) => {
    if (!nearest) return point;
    return Math.abs(new Date(point.timestamp).getTime() - target) < Math.abs(new Date(nearest.timestamp).getTime() - target) ? point : nearest;
  }, null);
}

export function RcaInvestigationPage({ onNavigate }: { onNavigate: (page: PageId) => void }) {
  const [selectedAsOf, setSelectedAsOf] = useState(() => new URLSearchParams(window.location.hash.split('?')[1] ?? '').get('at'));
  const [selectedLinkId, setSelectedLinkId] = useState<string | null>(null);
  const resource = useApiResource('rca-investigation', loadInvestigation);
  const checkpoints = resource.data ? rcaCheckpoints(resource.data.detail.alert.opened_at, resource.data.chronology.events) : [];
  const selectedIndex = checkpoints.findIndex((item) => item.asOf === selectedAsOf);
  const stepIndex = selectedIndex < 0 ? 0 : selectedIndex;
  const checkpoint = checkpoints[stepIndex] ?? null;
  const alertId = resource.data?.detail.alert.alert_id;
  const evidenceResource = useApiResource<{ requestedAt: string; progress: InvestigationEvidenceProgress } | null>(
    `${alertId ?? ''}:${checkpoint?.asOf ?? ''}`,
    () => alertId && checkpoint
      ? api.investigationEvidence(alertId, checkpoint.asOf).then((progress) => ({ requestedAt: checkpoint.asOf, progress }))
      : Promise.resolve(null),
  );

  if (resource.loading) return <LoadingState/>;
  if (resource.error) return <ErrorState message={resource.error}/>;
  if (!resource.data || !checkpoint) return <EmptyState title="No RCA case" description="An equipment alert starts the causal investigation."/>;

  const { detail, telemetry } = resource.data;
  const progress = evidenceResource.data?.requestedAt === checkpoint.asOf ? evidenceResource.data.progress : null;
  const activeLinkId = selectedLinkId ?? initialLink[checkpoint.kind];
  const link = progress?.causal_path.find((item) => item.link_id === activeLinkId) ?? progress?.causal_path[0];
  const signalContext = link ? linkSignals[link.link_id] : null;
  const signal = signalContext ? conditionSignals.find((item) => item.field === signalContext.field) : null;
  const chartWindow = checkpointWindow(checkpoint, detail);
  const points = selectTelemetryWindow(telemetry.points, chartWindow);
  const reading = nearestReading(points, checkpoint.asOf);

  function selectStep(index: number) {
    setSelectedAsOf(checkpoints[index].asOf);
    setSelectedLinkId(null);
  }

  return <div className="decision-workspace rca-investigation-page">
    <button className="rca-investigation-back" onClick={() => onNavigate('rca')}><Icon name="arrow"/> Back to RCA workspace</button>
    <header className="decision-workspace-heading">
      <div><span>KO-3201 · RCA investigation</span><h1>Follow the evidence</h1><p>Move through the reported chronology, then inspect the monitored trend and source behind each causal link.</p></div>
      <TraceButton traceId="rca-indication">View source lineage</TraceButton>
    </header>

    <nav className="rca-investigation-steps" aria-label="RCA investigation checkpoints">
      {checkpoints.map((item, index) => <button key={item.asOf} className={index === stepIndex ? 'active' : ''} aria-current={index === stepIndex ? 'step' : undefined} onClick={() => selectStep(index)}><small>{String(index + 1).padStart(2, '0')} / {item.label}</small><strong>{item.detail}</strong><time>{formatDateTime(item.asOf)}</time></button>)}
    </nav>

    {evidenceResource.error ? <p className="workflow-error">{evidenceResource.error}</p> : !progress || !link ? <LoadingState/> : <>
      <section className="rca-investigation-decision">
        <div><span>Reconstructed through {formatDateTime(progress.as_of)}</span><h2>{humanize(progress.stage)}</h2><p>{progress.summary}</p></div>
        <div><span>Decision gate</span><p>{progress.decision_gate}</p></div>
      </section>

      <section className="rca-investigation-flow">
        <header><div><span>Causal mechanism</span><h2>Select a link to inspect its evidence</h2></div><p>Report findings and monitored trends are kept distinct.</p></header>
        <div>{progress.causal_path.map((item, index) => <button key={item.link_id} className={item.link_id === link.link_id ? 'active' : ''} aria-pressed={item.link_id === link.link_id} onClick={() => setSelectedLinkId(item.link_id)}><small>{String(index + 1).padStart(2, '0')} · {item.state === 'RCA_REPORTED' ? 'RCA report' : item.state === 'MONITORED_TREND' ? 'Monitored trend' : 'Hypothesis'}</small><strong>{item.label}</strong></button>)}</div>
      </section>

      <section className="rca-investigation-evidence">
        <article className="rca-investigation-chart">
          <header><div><span>Supporting monitored data</span><h2>{signal?.label ?? 'No mapped signal'}</h2></div>{reading && signal && <strong>{formatSignal(Number(reading[signal.field]))} {signal.unit}<small>Nearest hourly reading · {formatDateTime(reading.timestamp)}</small></strong>}</header>
          {signalContext && <div className="rca-investigation-chart-canvas"><SignalChart points={points} field={signalContext.field} highlightTimestamp={reading?.timestamp} yPaddingRatio={0.15}/></div>}
          <p>{signalContext?.interpretation ?? 'This causal step has no direct monitored signal mapped.'}</p>
          <footer>Window: {formatDateTime(chartWindow.start)} to {formatDateTime(chartWindow.end)} · Hourly condition series</footer>
        </article>
        <article className="rca-investigation-source">
          <span>Evidence for selected link</span>
          <h2>{link.label}</h2>
          {link.source_event ? <><strong>{link.source_event.title}</strong><p>{link.source_event.detail}</p><dl><div><dt>Event time</dt><dd>{formatDateTime(link.source_event.occurred_at)}</dd></div><div><dt>Evidence grade</dt><dd>{humanize(link.source_event.source_grade)}</dd></div><div><dt>Source</dt><dd>{link.source_event.source_reference}</dd></div></dl></> : <p>{link.state === 'MONITORED_TREND' ? 'Supported by the opening water-in-oil trend. No independent lab or inspection result had yet occurred in this chronology.' : 'No direct source record for this step at the selected checkpoint. Keep it as a hypothesis.'}</p>}
          <TraceButton traceId="rca-indication">Inspect lineage</TraceButton>
        </article>
      </section>

      <section className="rca-investigation-alternatives">
        <header><h2>Competing explanations</h2><p>Each assessment below is tied to the records visible at this checkpoint.</p></header>
        {progress.explanations.map((item) => <article key={item.explanation_id}><div><strong>{item.title}</strong><span>{humanize(item.state)}</span></div><p>{item.starting_basis}</p><dl><div><dt className="evidence-label support">Supports</dt><dd><EvidenceList events={item.supporting_events} tone="support" empty="No later record yet"/></dd></div><div><dt className="evidence-label challenge">Challenges</dt><dd><EvidenceList events={item.challenging_events} tone="challenge" empty="None recorded"/></dd></div></dl><small>Next check: {item.next_check}</small></article>)}
      </section>

      <p className="rca-investigation-provenance">This is a retrospective reconstruction of event times. The source does not establish when each result reached the team.</p>
      <footer className="rca-investigation-controls"><button disabled={stepIndex === 0} onClick={() => selectStep(stepIndex - 1)}><Icon name="arrow"/> Previous</button><span>{stepIndex + 1} of {checkpoints.length}</span><button disabled={stepIndex === checkpoints.length - 1} onClick={() => selectStep(stepIndex + 1)}>Next checkpoint <Icon name="arrow"/></button></footer>
    </>}
  </div>;
}

function EvidenceList({ events, empty, tone }: { events: InvestigationEvidenceProgress['events']; empty: string; tone: 'support' | 'challenge' }) {
  if (!events.length) return <span>{empty}</span>;
  return <ul>{events.map((event) => <li key={event.event_id}><strong className={`evidence-label ${tone}`}>{event.title}</strong><p>{event.detail}</p><small>{humanize(event.source_grade)} · {event.source_reference}</small></li>)}</ul>;
}
