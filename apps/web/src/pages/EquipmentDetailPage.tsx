import { useEffect, useRef, useState } from 'react';
import type { PageId } from '../components/AppShell';
import { CoordinationPanel } from '../components/CoordinationPanel';
import { EquipmentSeriesChart, type EquipmentChartWindow } from '../components/EquipmentSeriesChart';
import { useTraceability } from '../components/TraceabilityContext';
import { ErrorState, LoadingState } from '../components/ViewState';
import { api } from '../lib/api';
import { equipmentApi, type EquipmentInvestigation, type EquipmentSignal } from '../lib/equipment';
import { formatDate, formatDateTime, formatSignal, humanize } from '../lib/format';
import { rcaCheckpoints } from '../lib/rcaCheckpoints';
import { useApiResource } from '../lib/useApiResource';
import { workflowView } from '../lib/workflowView';

type EquipmentView = 'overview' | 'investigation' | 'rca' | 'rca-investigation' | 'actions';

export function EquipmentDetailPage({ assetId, view, onNavigate }: { assetId: string; view: EquipmentView; onNavigate: (page: PageId) => void }) {
  const resource = useApiResource(`equipment-${assetId}`, async () => {
    const bundle = await equipmentApi.investigation(assetId);
    const [detail, effectiveness] = await Promise.all([api.alertDetail(bundle.alert.alert_id), api.effectiveness(assetId)]);
    return { bundle, detail, effectiveness };
  });
  const [signalKey, setSignalKey] = useState<string | null>(null);
  const [selectedWindow, setSelectedWindow] = useState<EquipmentChartWindow | null>(null);
  const [checkpoint, setCheckpoint] = useState<string | null>(null);
  const [reportId, setReportId] = useState<string | null>(null);
  const report = useRef<HTMLDialogElement>(null);
  const { openSource } = useTraceability();
  useEffect(() => { setSignalKey(null); setSelectedWindow(null); setCheckpoint(null); setReportId(null); }, [assetId]);
  useEffect(() => { if (reportId) report.current?.showModal(); }, [reportId]);
  const loadedBundle = resource.data?.bundle.asset.asset_id === assetId ? resource.data.bundle : null;
  const effectiveCheckpoint = checkpoint ?? loadedBundle?.alert.opened_at;
  const progress = useApiResource(`equipment-evidence-${loadedBundle?.alert.alert_id ?? assetId}-${effectiveCheckpoint ?? 'loading'}`, () =>
    loadedBundle ? api.investigationEvidence(loadedBundle.alert.alert_id, effectiveCheckpoint) : Promise.resolve(null));
  if (resource.loading) return <LoadingState/>;
  if (resource.error || !resource.data) return <ErrorState message={resource.error ?? 'Equipment data unavailable'}/>;
  const { bundle, detail, effectiveness } = resource.data;
  const condition = bundle.signals.filter((signal) => signal.cadence === 'WEEKLY');
  const operating = bundle.signals.filter((signal) => signal.cadence === 'HOURLY');
  const selectedSignal = condition.find((signal) => signal.key === signalKey) ?? condition[0];
  const workflow = workflowView(detail);
  const windows = bundle.transitions.map((transition, index): EquipmentChartWindow => ({
    start: index ? bundle.transitions[index - 1].timestamp : bundle.alert.first_signal_at,
    end: transition.timestamp, state: transition.new_state,
    label: `${index ? humanize(bundle.transitions[index - 1].new_state) : 'First signal'} → ${humanize(transition.new_state)}`,
  })).filter((window) => window.start < window.end && !['NORMAL', 'SUPPRESSED'].includes(window.state));
  const reportAction = bundle.source_actions.find((action) => action.id === reportId);
  const reportTemplate = reportAction && workflow.actionPlans.flatMap((plan) => plan.actions).find((action) => action.title.trim().toLowerCase() === reportAction.title.trim().toLowerCase());
  const checkpoints = rcaCheckpoints(bundle.alert.opened_at, bundle.events);
  const title = view === 'overview' ? 'Equipment performance' : view === 'investigation' ? 'Alert investigation' : view === 'actions' ? 'CA/PA action tracking' : 'Root cause analysis';
  return <div className="overview-dashboard equipment-dashboard">
    <header className="overview-heading"><div><p>{bundle.asset.plant_name} · {bundle.asset.tag}</p><h1>{title}</h1></div><button onClick={() => onNavigate('assets')}>All equipment</button></header>
    <nav className="equipment-page-nav" aria-label="Equipment workflow">{(['overview', 'investigation', 'rca', 'actions'] as const).map((page) => <button key={page} aria-current={view === page ? 'page' : undefined} onClick={() => onNavigate(page)}>{page === 'overview' ? 'Performance' : page === 'actions' ? 'CA/PA' : humanize(page)}</button>)}</nav>
    {view === 'overview' && <>
      <section className="overview-main-grid">
        <article className="equipment-card equipment-health"><header><div><h2>Equipment health trajectory</h2><p>Weekly condition assessment · engineering limits and persistence</p></div><strong>{bundle.assessments.at(-1)?.state}</strong></header>
          <EquipmentSeriesChart label="Weekly condition assessment" unit="condition score" points={bundle.assessments.map((assessment) => ({ timestamp: assessment.timestamp, value: assessment.score, source_reference: assessment.reason }))} windows={windows} onWindowSelect={setSelectedWindow}/>
          <div className="equipment-metric-row"><div><span>Condition readings</span><strong>{bundle.assessments.length} weekly</strong></div><div><span>RCA-reported downtime</span><strong>{bundle.reported_downtime_hours} h</strong></div><div><span>RCA-reported production loss</span><strong>{bundle.reported_production_loss_tonnes} t</strong></div></div>
        </article>
        <article className="equipment-card"><header><h2>Event progression</h2><button onClick={() => onNavigate('investigation')}>Open investigation</button></header><div className="equipment-event-list">{bundle.transitions.map((transition) => <button key={`${transition.timestamp}-${transition.new_state}`} onClick={() => setSelectedWindow(windows.find((window) => window.end === transition.timestamp) ?? { start: transition.timestamp, end: transition.timestamp, state: transition.new_state, label: humanize(transition.new_state) })}><strong>{humanize(transition.new_state)}</strong><time>{formatDate(transition.timestamp)}</time><span>{transition.reason}</span></button>)}</div></article>
      </section>
      {selectedWindow && <><EvidenceWindow bundle={bundle} window={selectedWindow} onClose={() => setSelectedWindow(null)}/><OperatingContext signals={operating} window={selectedWindow} onSource={openSource}/></>}
      <section className="overview-bottom-grid">
        <article className="equipment-card"><header><div><h2>Condition insights</h2><p>Four observed condition variables · weekly cadence</p></div></header><div className="equipment-signal-tabs">{condition.map((signal) => <button key={signal.key} aria-pressed={signal === selectedSignal} onClick={() => setSignalKey(signal.key)}><span>{signal.label}</span><strong>{formatSignal(signal.points.at(-1)?.value ?? 0)} <small>{signal.unit}</small></strong><span>{signal.direction === 'LOW' ? 'Low values increase concern' : 'High values increase concern'}</span></button>)}</div>{selectedSignal && <SignalView signal={selectedSignal} onSource={() => openSource(selectedSignal.source_key)}/>}</article>
        <article className="equipment-card"><header><h2>RCA & action progress</h2></header><h3>{workflow.rca?.generation.hypotheses[0]?.title ?? 'Cause under investigation'}</h3><p>{workflow.rca?.generation.executive_summary ?? 'Review the measured changes and source-reported inspection evidence.'}</p><button onClick={() => onNavigate('rca')}>Open RCA workspace</button><hr/><p>{bundle.source_actions.length} source-reported actions · {workflow.actionPlans.flatMap((plan) => plan.actions).length} workflow actions</p><button onClick={() => onNavigate('actions')}>Open CA/PA tracking</button></article>
      </section>
      {!selectedWindow && <OperatingContext signals={operating} onSource={openSource}/>}
      <details className="equipment-card equipment-source-notes"><summary>Source quality and measurement scope</summary>{bundle.quality_issues.map((issue) => <p key={issue}>{issue}</p>)}</details>
    </>}
    {view === 'investigation' && <>
      <EvidenceWindow bundle={bundle} window={selectedWindow ?? { start: bundle.alert.first_signal_at, end: bundle.alert.peak_score_at, state: bundle.alert.highest_severity, label: 'First signal → peak condition' }}/>
      <OperatingContext signals={operating} window={selectedWindow ?? { start: bundle.alert.first_signal_at, end: bundle.alert.peak_score_at, state: bundle.alert.highest_severity, label: 'Detection window' }} onSource={openSource}/>
      <section className="equipment-card"><header><h2>Dated RCA evidence</h2><button onClick={() => onNavigate('rca-investigation')}>Follow the conclusion</button></header>{bundle.events.map((event) => <details key={event.event_id} className="equipment-evidence-row"><summary><strong>{event.title}</strong><span>{humanize(event.kind)} · {formatDateTime(event.occurred_at)}</span></summary><p>{event.detail}</p><small>{event.source_grade} · {event.source_reference}</small></details>)}</section>
    </>}
    {(view === 'rca' || view === 'rca-investigation') && <>
      <section className="equipment-card"><header><div><h2>How the conclusion changes</h2><p>Select the evidence available at each checkpoint.</p></div></header><nav className="equipment-checkpoints" aria-label="RCA evidence checkpoint">{checkpoints.map((entry) => <button key={entry.asOf} aria-pressed={effectiveCheckpoint === entry.asOf} onClick={() => setCheckpoint(entry.asOf)}><strong>{entry.label}</strong><span>{formatDateTime(entry.asOf)}</span></button>)}</nav>
        {progress.loading ? <p role="status">Loading evidence at this checkpoint…</p> : progress.error ? <p role="alert">{progress.error}</p> : progress.data && <><h3>{humanize(progress.data.stage)}</h3><p>{progress.data.summary}</p><p><strong>Decision gate:</strong> {progress.data.decision_gate}</p><div className="equipment-causal-path">{progress.data.causal_path.map((link) => <details key={link.link_id}><summary><strong>{link.label}</strong><span>{humanize(link.state)}</span></summary>{link.source_event ? <><p>{link.source_event.detail}</p><small>{link.source_event.source_reference}</small></> : <p>Primary evidence still required.</p>}</details>)}</div>{progress.data.explanations.map((explanation) => <details className="equipment-evidence-row" key={explanation.explanation_id}><summary><strong>{explanation.title}</strong><span>{humanize(explanation.state)}</span></summary><p>{explanation.starting_basis}</p>{explanation.supporting_events.map((event) => <p key={event.event_id} className="evidence-support"><strong>Supports:</strong> {event.detail}<small>{event.source_reference}</small></p>)}{explanation.challenging_events.map((event) => <p key={event.event_id} className="evidence-challenge"><strong>Challenges:</strong> {event.detail}<small>{event.source_reference}</small></p>)}<p><strong>Next check:</strong> {explanation.next_check}</p></details>)}</>}
      </section>
      <details className="equipment-card"><summary>Similar incidents · historical context</summary>{detail.similar_incidents.length ? detail.similar_incidents.map((incident) => <article key={incident.incident_id}><h3>{incident.title}</h3><p>{incident.match_reasons.join(' · ')}</p><small>{incident.asset_tag} · {formatDate(incident.occurred_at)} · {incident.source_reference}</small></article>) : <p>No eligible historical analogue was found.</p>}</details>
      <details className="equipment-card"><summary>RCA confirmation plan</summary>{workflow.rca?.generation.hypotheses.map((hypothesis) => <article key={hypothesis.hypothesis_id}><h3>{hypothesis.title}</h3><p>{hypothesis.mechanism}</p><p><strong>Reject when:</strong> {hypothesis.disconfirming_condition}</p>{hypothesis.missing_evidence.map((item) => <p key={item}><strong>Evidence required:</strong> {item}</p>)}</article>) ?? <p>Create a working RCA through the review workflow.</p>}</details>
      <button onClick={() => onNavigate('actions')}>Continue to CA/PA</button>
    </>}
    {view === 'actions' && <>
      <section className="equipment-card"><header><div><h2>Source-reported corrective and preventive plan</h2><p>RCA plan record · click an action to view its handoff report</p></div></header>{bundle.source_actions.map((action) => <button className="equipment-action-row" key={action.id} onClick={() => setReportId(action.id)}><span>{humanize(action.action_type)}</span><strong>{action.title}</strong><span>{action.owner} · {formatDate(action.due_date)}</span><span>{humanize(action.status)} →</span></button>)}</section>
      <CoordinationPanel detail={detail} onChange={resource.reload} refreshing={resource.loading}/>
      <section className="equipment-card"><header><div><h2>Recovery and effectiveness verification</h2><p>{effectiveness.monitoring_periods} observed weekly periods · {formatDate(effectiveness.monitoring_start)} – {formatDate(effectiveness.monitoring_end)}</p></div><strong>{humanize(effectiveness.approval_status)}</strong></header><p>{effectiveness.explanation}</p><div className="equipment-recovery-grid">{effectiveness.metrics.map((metric) => <article key={metric.signal_key}><span>{metric.label}</span><strong>{formatSignal(metric.before)} → {formatSignal(metric.after)} {metric.unit}</strong><span>{humanize(metric.outcome)}</span></article>)}</div><p>Closure: {effectiveness.closure_eligible ? 'Eligible for controlled closure' : 'Pending execution evidence and human effectiveness review'}</p><small>{effectiveness.source_reference}</small></section>
    </>}
    {reportAction && <dialog ref={report} className="equipment-report-dialog" onCancel={() => setReportId(null)} onClose={() => setReportId(null)}><div className="equipment-report-toolbar"><button onClick={() => window.print()}>Print / Save PDF</button><button onClick={() => { report.current?.close(); setReportId(null); }}>Close report</button></div><article className="equipment-action-report"><p>Action handoff report</p><h1>{reportAction.title}</h1><dl><dt>Reference</dt><dd>{reportAction.id}</dd><dt>Asset / plant</dt><dd>{bundle.asset.tag} / {bundle.asset.plant_name}</dd><dt>Action type</dt><dd>{humanize(reportAction.action_type)}</dd><dt>Responsible owner</dt><dd>{reportAction.owner}</dd><dt>Due date</dt><dd>{formatDate(reportAction.due_date)}</dd><dt>Source-reported status</dt><dd>{humanize(reportAction.status)}</dd></dl><h2>Evidence and issue context</h2><p>{workflow.rca?.generation.executive_summary ?? bundle.alert.primary_driver}</p><h2>Action scope</h2><p>{reportTemplate?.guidance ?? reportAction.title}</p><h2>Execution evidence and acceptance</h2><p>{reportTemplate?.completion_criteria ?? 'The source plan does not specify execution acceptance criteria. A reviewed working plan is required before delegation.'}</p><h2>Effectiveness review</h2><p>{reportTemplate?.effectiveness_check ?? effectiveness.explanation}</p><h2>Source record</h2><p>{reportAction.source_reference}</p></article></dialog>}
  </div>;
}

function SignalView({ signal, onSource }: { signal: EquipmentSignal; onSource: () => void }) {
  return <><div className="equipment-signal-heading"><p>{signal.label} · {humanize(signal.cadence)} · {signal.alarm_limit == null ? 'Operating context' : `Alarm ${signal.alarm_limit} / trip ${signal.trip_limit} ${signal.unit}`}</p><button onClick={onSource}>View source</button></div><EquipmentSeriesChart label={signal.label} unit={signal.unit} points={signal.points} threshold={signal.alarm_limit}/></>;
}

function OperatingContext({ signals, window, onSource }: { signals: EquipmentSignal[]; window?: EquipmentChartWindow; onSource: (key: string) => void }) {
  const start = window ? Date.parse(window.start) : -Infinity;
  const end = window ? Date.parse(window.end) : Infinity;
  return <section className="equipment-card"><header><div><h2>Operating performance</h2><p>May hourly readings · feed and source-specific plant rate{window ? ' · selected condition window' : ''}</p></div></header><div className="equipment-operating-grid">{signals.map((signal) => <article key={signal.key}><h3>{signal.label}</h3><SignalView signal={{ ...signal, points: signal.points.filter((point) => Date.parse(point.timestamp) >= start && Date.parse(point.timestamp) <= end) }} onSource={() => onSource(signal.source_key)}/></article>)}</div></section>;
}

function EvidenceWindow({ bundle, window, onClose }: { bundle: EquipmentInvestigation; window: EquipmentChartWindow; onClose?: () => void }) {
  const start = Date.parse(window.start), end = Date.parse(window.end);
  const assessments = bundle.assessments.filter((assessment) => Date.parse(assessment.timestamp) >= start && Date.parse(assessment.timestamp) <= end);
  return <section className="equipment-card equipment-window-evidence"><header><div><h2>{window.label}</h2><p>{formatDate(window.start)} – {formatDate(window.end)} · weekly supporting evidence</p></div>{onClose && <button onClick={onClose}>Close window</button>}</header><div className="equipment-operating-grid">{bundle.signals.filter((signal) => signal.cadence === 'WEEKLY').map((signal) => <article key={signal.key}><h3>{signal.label}</h3><EquipmentSeriesChart label={signal.label} unit={signal.unit} threshold={signal.alarm_limit} points={signal.points.filter((point) => Date.parse(point.timestamp) >= start && Date.parse(point.timestamp) <= end)}/></article>)}</div><div className="equipment-table-wrap"><table><thead><tr><th>Weekly date</th>{bundle.signals.filter((signal) => signal.cadence === 'WEEKLY').map((signal) => <th key={signal.key}>{signal.label} ({signal.unit})</th>)}<th>Calculated state</th><th>Source status</th></tr></thead><tbody>{assessments.map((assessment) => <tr key={assessment.timestamp}><td>{formatDate(assessment.timestamp)}</td>{bundle.signals.filter((signal) => signal.cadence === 'WEEKLY').map((signal) => { const point = signal.points.find((reading) => reading.timestamp === assessment.timestamp); return <td key={signal.key} title={point?.source_reference}>{point ? formatSignal(point.value) : '—'}</td>; })}<td>{assessment.state}</td><td>{assessment.source_status}</td></tr>)}</tbody></table></div>{!assessments.length && <p>No weekly condition row falls inside this timestamped interval. Inspect the adjacent weekly readings and the separately dated RCA event.</p>}{assessments.map((assessment) => <p key={assessment.timestamp}><strong>{formatDate(assessment.timestamp)}:</strong> {assessment.reason}</p>)}</section>;
}
