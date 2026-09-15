import { useState } from 'react';

import type { PageId } from '../components/AppShell';
import { EventProgressionExplorer } from '../components/EventProgressionExplorer';
import { Icon } from '../components/Icon';
import { SignalChart, type ChartTimeWindow, type ChartWindowTone } from '../components/SignalChart';
import { TraceButton } from '../components/TraceabilityContext';
import { ErrorState, LoadingState } from '../components/ViewState';
import { api, type AlertDetail, type AlertEvent, type AssetOverview, type DriverAnalysis, type EffectivenessReview, type TelemetrySeries } from '../lib/api';
import { PRIMARY_ASSET_ID } from '../lib/appConfig';
import { conditionSignals, operatingSignals, type EquipmentSignal, type EquipmentSignalField } from '../lib/conditionSignals';
import { contributionForField, contributionRank } from '../lib/driverAnalysis';
import { formatDate, formatDateTime, formatSignal, humanize } from '../lib/format';
import { alertDetectionWindow, alertProgressionWindows, selectIncidentWindow, timeWindowHours, type AlertTimeWindow, type HealthTimeRange } from '../lib/timeWindow';
import { useApiResource } from '../lib/useApiResource';
import { workflowView } from '../lib/workflowView';

type SignalMode = 'condition' | 'operating';

const healthRanges: Array<{ value: HealthTimeRange; label: string }> = [
  { value: '6M', label: '6M' },
  { value: '3M', label: '3M' },
  { value: '1M', label: '1M' },
  { value: 'DETECTION', label: 'Signal → warning' },
];

interface OverviewData {
  overview: AssetOverview;
  telemetry: TelemetrySeries;
  alerts: AlertEvent[];
  alertDetails: AlertDetail[];
  detail: AlertDetail | null;
  effectiveness: EffectivenessReview;
  driverAnalysis: DriverAnalysis | null;
}

async function loadOverview(): Promise<OverviewData> {
  const [overview, telemetry, alerts, effectiveness] = await Promise.all([
    api.assetOverview(PRIMARY_ASSET_ID),
    api.telemetry(PRIMARY_ASSET_ID, 5000),
    api.alerts(PRIMARY_ASSET_ID),
    api.effectiveness(PRIMARY_ASSET_ID),
  ]);
  const [alertDetails, driverAnalysis] = await Promise.all([
    Promise.all(alerts.map((alert) => api.alertDetail(alert.alert_id))),
    alerts[0] ? api.driverAnalysis(alerts[0].alert_id) : Promise.resolve(null),
  ]);
  return { overview, telemetry, alerts, alertDetails, detail: alertDetails[0] ?? null, effectiveness, driverAnalysis };
}

interface ProgressionSelection {
  detail: AlertDetail;
  milestoneIndex: number | null;
}

export function OverviewPage({ onNavigate }: { onNavigate: (page: PageId) => void }) {
  const [healthRange, setHealthRange] = useState<HealthTimeRange>('6M');
  const [signalMode, setSignalMode] = useState<SignalMode>('condition');
  const [selectedSignalField, setSelectedSignalField] = useState<EquipmentSignalField>('water_in_oil_ppm');
  const [selectedProgression, setSelectedProgression] = useState<ProgressionSelection | null>(null);
  const resource = useApiResource('overview', loadOverview);
  if (resource.loading) return <LoadingState/>;
  if (resource.error || !resource.data) return <ErrorState message={resource.error ?? 'Overview data unavailable'}/>;

  const { overview, telemetry, alerts, alertDetails, detail, effectiveness, driverAnalysis } = resource.data;
  const productionImpact = overview.production_impact;
  const alert = alerts[0];
  const eventAnchor = productionImpact?.window_start ?? alert?.peak_score_at;
  const detectionWindow = alert && detail ? alertDetectionWindow(alert, detail.state_transitions) : undefined;
  const progressionWindows = alertDetails.flatMap((alertDetail) => alertProgressionWindows(alertDetail.alert, alertDetail.state_transitions));
  const chartWindows = progressionWindows.map(toChartWindow);
  const detectionHours = detectionWindow ? timeWindowHours(detectionWindow) : 0;
  const detectionFocused = healthRange === 'DETECTION' && Boolean(detectionWindow);
  const healthPoints = selectIncidentWindow(telemetry.points, healthRange, eventAnchor, detectionWindow);
  const healthStart = healthPoints[0]?.timestamp ?? overview.timeline_start;
  const healthEnd = healthPoints.at(-1)?.timestamp ?? overview.timeline_end;
  const actionablePoints = healthPoints.filter((point) => !['NORMAL', 'SUPPRESSED'].includes(point.decision_state));
  const visiblePeakScore = Math.max(...actionablePoints.map((point) => point.anomaly_score ?? 0), 0);
  const escalationTransition = detail?.state_transitions.find((transition) => transition.new_state === alert?.highest_severity);
  const escalationIndex = Math.max((detail?.state_transitions.findIndex((transition) => transition === escalationTransition) ?? 0) + 1, 1);
  const latest = telemetry.points.at(-1);
  const visibleEnd = healthPoints.at(-1);
  const contextPoint = detectionFocused ? visibleEnd : latest;
  const { rca, actionPlans: plans } = detail
    ? workflowView(detail)
    : { rca: null, actionPlans: [] };
  const actions = plans.flatMap((plan) => plan.actions);
  const activeAction = actions.find((action) => action.status === 'IN_PROGRESS') ?? actions.find((action) => action.status !== 'CLOSED');
  const correctiveAction = actions.find((action) => action.action_type === 'CORRECTIVE');
  const preventiveAction = actions.find((action) => action.action_type === 'PREVENTIVE');
  const improvedSignals = effectiveness.metrics.filter((metric) => metric.outcome === 'IMPROVED').length;
  const confidence = Math.round((rca?.generation.hypotheses[0]?.confidence ?? 0) * 100);

  const availableSignals: readonly EquipmentSignal[] = signalMode === 'condition' ? conditionSignals : operatingSignals;
  const selectedSignal = availableSignals.find((signal) => signal.field === selectedSignalField) ?? availableSignals[0];
  const selectedContribution = contributionForField(driverAnalysis, selectedSignal.field);
  const selectedValues = healthPoints.map((point) => Number(point[selectedSignal.field]));
  const selectedStart = selectedValues[0] ?? 0;
  const selectedLatest = selectedValues.at(-1) ?? 0;

  function selectSignalMode(mode: SignalMode) {
    setSignalMode(mode);
    setSelectedSignalField((mode === 'condition' ? conditionSignals : operatingSignals)[0].field);
  }

  function openProgressionWindow(windowId: string) {
    const window = progressionWindows.find((candidate) => candidate.id === windowId);
    const alertDetail = window && alertDetails.find((candidate) => candidate.alert.alert_id === window.alertId);
    if (window && alertDetail) setSelectedProgression({ detail: alertDetail, milestoneIndex: window.milestoneIndex });
  }

  return <div className="overview-dashboard">
    <header className="overview-heading">
      <div><span>Manufacturing performance</span><h1>Reliability overview</h1></div>
      <div><button onClick={() => onNavigate('investigation')}>Open investigation <Icon name="arrow"/></button></div>
    </header>

    <section className="overview-main-grid">
      <article className="overview-health-card">
        <header>
          <div><span className="overview-title-icon"><Icon name="pulse"/></span><div><h2>Equipment health trajectory</h2><p>KO-3201 · {detectionFocused ? `${formatSignal(detectionHours)} h detection evidence` : healthRange === '6M' ? 'full monitoring history' : `${healthRange.toLowerCase()} incident-centered window`}</p></div></div>
          <div className="overview-health-controls"><TraceButton traceId="health-trajectory">View sources</TraceButton><span>Anomaly score</span><nav className="overview-range-selector" aria-label="Health trajectory time range">{healthRanges.map((range) => <button className={healthRange === range.value ? 'active' : ''} disabled={range.value === 'DETECTION' && !detectionWindow} key={range.value} onClick={() => setHealthRange(range.value)}>{range.label}</button>)}</nav></div>
        </header>
        <div className="overview-health-body">
          <div className="overview-chart-metric"><span>Actionable peak</span><strong>{formatSignal(visiblePeakScore)}</strong><p>Threshold <b>50</b></p></div>
          <div className="overview-chart"><SignalChart points={healthPoints} field="anomaly_score" threshold={50} highlightWindows={chartWindows} onWindowSelect={openProgressionWindow} yPaddingRatio={0.22}/></div>
          <div className="overview-chart-axis"><span>{formatDate(healthStart)}</span><b>{detectionFocused ? `${formatSignal(detectionHours)} h · first signal to warning` : `${progressionWindows.length} progression windows · click to inspect`}</b><span>{formatDate(healthEnd)}</span></div>
        </div>
        <div className="overview-health-context">
          <div><span>{detectionFocused ? 'At warning · leading condition' : 'Leading condition'}</span><strong>Water in oil</strong><b>{formatSignal(contextPoint?.water_in_oil_ppm ?? 0)} ppm</b></div>
          <div><span>{detectionFocused ? 'At warning · mechanical response' : 'Correlated response'}</span><strong>Radial vibration</strong><b>{formatSignal(contextPoint?.radial_vibration_micron ?? 0)} µm</b></div>
          <div><span>Estimated production shortfall</span><strong>{productionImpact ? `~${Math.round(productionImpact.estimated_shortfall_tonnes).toLocaleString()} tonnes` : 'Unavailable'}</strong><TraceButton traceId="production-shortfall">{productionImpact ? `${formatSignal(productionImpact.offline_hours)} h · View calculation` : 'View calculation'}</TraceButton></div>
        </div>
      </article>

      <article className="overview-timeline-card">
        <header><div><h2>Event progression</h2><p>KO-3201 degradation chronology</p></div><div className="overview-card-actions"><TraceButton traceId="event-progression">Sources</TraceButton><button onClick={() => detail && setSelectedProgression({ detail, milestoneIndex: null })}>View all <Icon name="arrow"/></button></div></header>
        <div className="overview-schedule">
          <div className="overview-time-rule"><span>First signal</span><i/></div>
          <ScheduleEvent title="Oil condition began to deviate" detail="Water-in-oil became persistent before the broader equipment response." date={formatDateTime(alert?.first_signal_at ?? overview.timeline_start)} status="Warning" meta="1 leading signal" tone="warning" onClick={() => detail && setSelectedProgression({ detail, milestoneIndex: 0 })}/>
          <div className="overview-time-rule"><span>Escalation</span><i/></div>
          <ScheduleEvent title="Condition signals converged" detail="Oil, pressure, thermal, and vibration evidence formed a critical pattern." date={formatDateTime(escalationTransition?.timestamp ?? alert?.opened_at ?? overview.timeline_start)} status={humanize(alert?.highest_severity ?? 'critical')} meta={`${alert?.breached_signals.length ?? 0} correlated signals`} tone="critical" onClick={() => detail && setSelectedProgression({ detail, milestoneIndex: escalationIndex })}/>
        </div>
      </article>
    </section>

    <section className="overview-bottom-grid">
      <article className="overview-condition-card">
        <header><div><h2>{signalMode === 'condition' ? 'Condition insights' : 'Operating performance'}</h2><p>{signalMode === 'condition' ? 'Explore how equipment condition contributed to the event' : 'Compare KO-3201 load and delivery against plant operation'}</p></div><div className="overview-card-actions"><TraceButton traceId={signalMode === 'condition' ? 'condition-insights' : 'production-shortfall'}>View sources</TraceButton><nav className="overview-signal-mode" aria-label="Equipment signal group"><button className={signalMode === 'condition' ? 'active' : ''} onClick={() => selectSignalMode('condition')}>Condition</button><button className={signalMode === 'operating' ? 'active' : ''} onClick={() => selectSignalMode('operating')}>Operating</button></nav></div></header>
        <nav className="overview-condition-tabs" aria-label={`${signalMode} variables`}>
          {availableSignals.map((signal) => {
            const contribution = contributionForField(driverAnalysis, signal.field);
            const reading = Number((detectionFocused ? visibleEnd : latest)?.[signal.field] ?? 0);
            return <button className={selectedSignal.field === signal.field ? 'active' : ''} key={signal.field} onClick={() => setSelectedSignalField(signal.field)}><span>{signal.label}</span><strong>{!detectionFocused && signalMode === 'condition' && contribution ? `${formatSignal(contribution.contribution_percent)}% contribution` : `${formatSignal(reading)} ${signal.unit}`}</strong></button>;
          })}
        </nav>
        <div className="overview-condition-visual">
          {detectionFocused
            ? <div className="overview-condition-summary overview-window-summary">
                <span>Reading at warning</span>
                <strong>{formatSignal(selectedLatest)} <small>{selectedSignal.unit}</small></strong>
                <p>From {formatSignal(selectedStart)} {selectedSignal.unit} at first signal</p>
                <dl><div><dt>Window change</dt><dd>{signedSignal(selectedLatest - selectedStart)} {selectedSignal.unit}</dd></div><div><dt>Evidence window</dt><dd>{formatSignal(detectionHours)} h</dd></div></dl>
              </div>
            : signalMode === 'condition'
            ? <div className="overview-condition-summary">
                <span>{selectedContribution && driverAnalysis ? `#${contributionRank(driverAnalysis, selectedContribution)} model contributor` : selectedSignal.role}</span>
                <strong>{selectedContribution ? formatSignal(selectedContribution.contribution_percent) : formatSignal(selectedLatest)} <small>{selectedContribution ? '%' : selectedSignal.unit}</small></strong>
                <p>{selectedContribution ? 'At actionable event peak' : 'Latest reading'}</p>
                <dl><div><dt>Event reading</dt><dd>{selectedContribution ? formatSignal(selectedContribution.value) : formatSignal(selectedLatest)} {selectedSignal.unit}</dd></div><div><dt>Alarm persistence</dt><dd>{selectedContribution ? `${selectedContribution.alarm_persistence_hours.toLocaleString()} h` : '—'}</dd></div></dl>
              </div>
            : <div className="overview-condition-summary overview-production-summary">
                <span>Estimated production shortfall</span>
                <strong>{productionImpact ? Math.round(productionImpact.estimated_shortfall_tonnes).toLocaleString() : '—'} <small>tonnes</small></strong>
                <p>{productionImpact ? `${formatSignal(productionImpact.offline_hours)} h offline · contextual healthy median` : 'No qualifying offline event window'}</p>
                <dl><div><dt>Expected feed</dt><dd>{productionImpact ? `${formatSignal(productionImpact.baseline.expected_feed_tph)} t/h` : '—'}</dd></div><div><dt>Baseline evidence</dt><dd>{productionImpact ? `${productionImpact.baseline.healthy_sample_count.toLocaleString()} h · ${humanize(productionImpact.baseline.confidence)}` : '—'}</dd></div></dl>
              </div>}
          <div className="overview-condition-chart"><SignalChart points={healthPoints} field={selectedSignal.field} highlightTimestamp={detectionFocused ? undefined : signalMode === 'condition' ? driverAnalysis?.as_of : alert?.first_signal_at} highlightWindows={chartWindows} showRunStatus={signalMode === 'operating'}/><div><span>{formatDate(healthStart)}</span><b>{detectionFocused ? 'First signal → warning' : signalMode === 'operating' && productionImpact ? `Healthy median at ${formatSignal(productionImpact.baseline.representative_plant_rate_tph)} ± ${formatSignal(productionImpact.baseline.plant_rate_tolerance_tph)} t/h plant load` : `${formatDate(driverAnalysis?.as_of ?? alert?.peak_score_at ?? overview.timeline_start)} · contribution snapshot`}</b><span>{formatDate(healthEnd)}</span></div></div>
        </div>
      </article>

      <article className="overview-decision-card">
        <section className="overview-decision-half overview-rca-half">
          <header><div><span>Root cause analysis</span><b>{rca ? humanize(rca.status) : 'Pending'}</b></div><div className="overview-card-actions"><TraceButton traceId="rca-indication">Sources</TraceButton><button onClick={() => onNavigate('rca')} aria-label="Open RCA workspace"><Icon name="arrow"/></button></div></header>
          <h3>{rca?.generation.hypotheses[0]?.title ?? 'Evidence package ready for review'}</h3>
          <p>{rca?.generation.hypotheses[0]?.rationale ?? 'Review the signal sequence and historical analogues to establish a probable cause.'}</p>
          <dl><div><dt>Confidence</dt><dd>{confidence}%</dd></div><div><dt>Evidence</dt><dd>{rca?.generation.hypotheses[0]?.supporting_evidence_ids.length ?? 0} items</dd></div><div><dt>Similar cases</dt><dd>{detail?.similar_incidents.length ?? 0}</dd></div></dl>
        </section>
        <section className="overview-decision-half overview-capa-half">
          <header><div><span>CA/PA progress</span><b>{humanize(plans[0]?.status ?? 'Pending')}</b></div><div className="overview-card-actions"><TraceButton traceId="capa-plan">Sources</TraceButton><button onClick={() => onNavigate('actions')} aria-label="Open CA/PA tracker"><Icon name="arrow"/></button></div></header>
          <div className="overview-capa-row"><span>Corrective</span><div><strong>{correctiveAction?.title ?? 'Awaiting approved RCA'}</strong><small>{correctiveAction?.owner_role ?? 'Unassigned'}</small></div><b>{humanize(correctiveAction?.status ?? 'Pending')}</b></div>
          <div className="overview-capa-row"><span>Preventive</span><div><strong>{preventiveAction?.title ?? 'Awaiting approved RCA'}</strong><small>{preventiveAction?.owner_role ?? 'Unassigned'}</small></div><b>{humanize(preventiveAction?.status ?? 'Pending')}</b></div>
          <footer className="overview-recovery-footer"><span>Recovery evidence</span><strong>{effectiveness.recovery_confirmed ? `${improvedSignals}/${effectiveness.metrics.length} signals improved · ${effectiveness.monitoring_periods} normal weeks` : activeAction?.title ?? 'Review post-action evidence'}</strong></footer>
        </section>
      </article>
    </section>

    {selectedProgression ? <EventProgressionExplorer assetTag={overview.asset.tag} alert={selectedProgression.detail.alert} transitions={selectedProgression.detail.state_transitions} telemetry={telemetry.points} initialSelection={selectedProgression.milestoneIndex} onClose={() => setSelectedProgression(null)}/> : null}
  </div>;
}

function ScheduleEvent({ title, detail, date, status, meta, tone, onClick }: { title: string; detail: string; date: string; status: string; meta: string; tone: string; onClick: () => void }) {
  return <article className="overview-schedule-event"><div><h3>{title}</h3><button onClick={onClick} aria-label={`Inspect ${title}`}><Icon name="arrow"/></button></div><p>{detail}</p><footer><span className={tone}>{status}</span><b>{meta}</b><time>{date}</time></footer></article>;
}

function signedSignal(value: number): string {
  return `${value > 0 ? '+' : ''}${formatSignal(value)}`;
}

function toChartWindow(window: AlertTimeWindow): ChartTimeWindow {
  return {
    id: window.id,
    start: window.start,
    end: window.end,
    label: `${humanize(window.fromState)} → ${humanize(window.toState)}`,
    tone: windowTone(window.toState),
  };
}

function windowTone(state: string): ChartWindowTone {
  if (state === 'WARNING' || state === 'HIGH' || state === 'CRITICAL' || state === 'CLOSED') return state.toLowerCase() as ChartWindowTone;
  return 'signal';
}
