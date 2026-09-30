import { useState } from 'react';

import type { PageId } from '../components/AppShell';
import { Icon } from '../components/Icon';
import { SignalChart } from '../components/SignalChart';
import { TraceButton } from '../components/TraceabilityContext';
import { EmptyState, ErrorState, LoadingState } from '../components/ViewState';
import { api, type AlertDetail, type DriverAnalysis, type InvestigationEvidenceProgress, type TelemetrySeries } from '../lib/api';
import { PRIMARY_ASSET_ID } from '../lib/appConfig';
import { conditionSignalsFor, equipmentPresentation, type ConditionField } from '../lib/conditionSignals';
import { contributionForField } from '../lib/driverAnalysis';
import { formatDate, formatDateTime, formatSignal, humanize } from '../lib/format';
import { rcaCheckpoints } from '../lib/rcaCheckpoints';
import { alertDetectionWindow, timeWindowHours } from '../lib/timeWindow';
import { useApiResource } from '../lib/useApiResource';
import { workflowView } from '../lib/workflowView';

interface RcaWorkspaceData {
  detail: AlertDetail;
  telemetry: TelemetrySeries;
  driverAnalysis: DriverAnalysis;
  caseProgress: InvestigationEvidenceProgress;
}

async function loadRcaWorkspace(assetId: string): Promise<RcaWorkspaceData | null> {
  const alerts = await api.alerts(assetId);
  const alert = alerts[0];
  if (!alert) return null;
  const [detail, telemetry, driverAnalysis, caseProgress] = await Promise.all([
    api.alertDetail(alert.alert_id),
    api.telemetry(alert.asset_id, 1800, alert.first_signal_at, alert.closed_at ?? alert.peak_score_at),
    api.driverAnalysis(alert.alert_id),
    api.investigationEvidence(alert.alert_id),
  ]);
  return { detail, telemetry, driverAnalysis, caseProgress };
}

export function RcaPage({ onNavigate, assetId = PRIMARY_ASSET_ID }: { onNavigate: (page: PageId) => void; assetId?: string }) {
  const equipment = equipmentPresentation(assetId);
  const conditionSignals = conditionSignalsFor(assetId);
  const [selectedSignal, setSelectedSignal] = useState<ConditionField>(conditionSignals[0].field);
  const [selectedHypothesisId, setSelectedHypothesisId] = useState<string | null>(null);
  const [selectedAsOf, setSelectedAsOf] = useState<string | null>(null);
  const resource = useApiResource(`rca-workspace:${assetId}`, () => loadRcaWorkspace(assetId));
  const alertId = resource.data?.detail.alert.alert_id;
  const activeAsOf = selectedAsOf ?? resource.data?.detail.alert.opened_at ?? null;
  const checkpointResource = useApiResource<{ requestedAt: string; progress: InvestigationEvidenceProgress } | null>(
    `${alertId ?? ''}:${activeAsOf ?? ''}`,
    () => alertId && activeAsOf
      ? api.investigationEvidence(alertId, activeAsOf).then((progress) => ({ requestedAt: activeAsOf, progress }))
      : Promise.resolve(null),
  );
  if (resource.loading) return <LoadingState/>;
  if (resource.error) return <ErrorState message={resource.error}/>;
  if (!resource.data) return <EmptyState title="No alert selected" description="A prioritized equipment alert starts the RCA workflow."/>;

  const { detail, telemetry, driverAnalysis, caseProgress } = resource.data;
  const { rca } = workflowView(detail);
  if (!rca) return <EmptyState title="Evidence package ready" description="Generate a reviewable RCA draft from the alert evidence and historical analogues."/>;

  const leadingHypothesis = rca.generation.hypotheses[0];
  const selectedHypothesis = rca.generation.hypotheses.find((hypothesis) => hypothesis.hypothesis_id === selectedHypothesisId) ?? leadingHypothesis;
  const signal = conditionSignals.find((candidate) => candidate.field === selectedSignal) ?? conditionSignals[0];
  const contribution = contributionForField(driverAnalysis, signal.field);
  const detectionWindow = alertDetectionWindow(detail.alert, detail.state_transitions);
  const checkpoints = rcaCheckpoints(detail.alert.opened_at, caseProgress.events);
  const progress = checkpointResource.data?.requestedAt === activeAsOf ? checkpointResource.data.progress : null;
  return <div className="decision-workspace rca-workspace">
    <header className="decision-workspace-heading">
      <div><span>{equipment.tag} · {detail.alert.alert_id}</span><h1>Root cause analysis</h1><p>Trace the probable cause from equipment evidence, historical analogues, and explicit validation boundaries.</p></div>
      <div><b>{humanize(rca.status)}</b><TraceButton traceId="rca-indication">View supporting sources</TraceButton><button onClick={() => onNavigate('actions')}>Open CA/PA plan</button></div>
    </header>

    <section className="rca-decision-grid">
      <article className="rca-leading-decision">
        <header><span>Early-warning hypothesis</span><strong>Ranked 01 · review basis</strong></header>
        <h2>{leadingHypothesis.title}</h2>
        <p>{leadingHypothesis.mechanism}</p>
        <dl>
          <div><dt className="evidence-label support">Supporting evidence</dt><dd>{leadingHypothesis.supporting_evidence_ids.length}</dd></div>
          <div><dt className="evidence-label challenge">Contradictions</dt><dd>{leadingHypothesis.contradicting_evidence_ids.length}</dd></div>
          <div><dt>Historical analogues</dt><dd>{leadingHypothesis.analogue_incident_ids.length}</dd></div>
          <div><dt>Decision status</dt><dd>{humanize(rca.status)}</dd></div>
        </dl>
        <p className="rca-leading-rationale">{leadingHypothesis.rationale}</p>
      </article>

      <article className="rca-signal-evidence">
        <header><div><span>Signal evidence</span><h2>{signal.label}</h2></div><div><span>Peak-risk model contribution</span><strong>{contribution ? `${formatSignal(contribution.contribution_percent)}%` : 'Unavailable'}</strong></div></header>
        <nav aria-label="RCA evidence signals">{conditionSignals.map((candidate) => { const item = contributionForField(driverAnalysis, candidate.field); return <button className={candidate.field === selectedSignal ? 'active' : ''} key={candidate.field} onClick={() => setSelectedSignal(candidate.field)}>{candidate.label}<small>{item ? `${formatSignal(item.contribution_percent)}%` : '—'}</small></button>; })}</nav>
        <div className="rca-evidence-chart"><SignalChart points={telemetry.points} field={signal.field} highlightTimestamp={detail.alert.peak_score_at} highlightWindow={detectionWindow}/></div>
        <dl className="rca-driver-context"><div><dt>Event reading</dt><dd>{contribution ? `${formatSignal(contribution.value)} ${signal.unit}` : 'Unavailable'}</dd></div><div><dt>Healthy median</dt><dd>{contribution ? `${formatSignal(contribution.healthy_baseline)} ${signal.unit}` : 'Unavailable'}</dd></div><div><dt>Engineering state</dt><dd>{contribution ? humanize(contribution.engineering_state) : 'Unavailable'}</dd></div><div><dt>Alarm persistence</dt><dd>{contribution ? `${contribution.alarm_persistence_hours.toLocaleString()} h` : 'Unavailable'}</dd></div></dl>
        <footer><span>{formatDate(detectionWindow.start)} · first signal</span><b>{formatSignal(timeWindowHours(detectionWindow))} h to warning</b><span>{formatDate(detail.alert.peak_score_at)} · peak risk</span></footer>
      </article>
    </section>

    <section className="rca-hypothesis-workspace">
      <nav aria-label="Root cause hypotheses">
        <header><h2>At-warning hypotheses</h2><span>{rca.generation.hypotheses.length} candidates</span></header>
        {rca.generation.hypotheses.map((hypothesis) => <button className={hypothesis.hypothesis_id === selectedHypothesis.hypothesis_id ? 'active' : ''} key={hypothesis.hypothesis_id} onClick={() => setSelectedHypothesisId(hypothesis.hypothesis_id)}><span>{String(hypothesis.rank).padStart(2, '0')}</span><div><strong>{hypothesis.title}</strong><small>{humanize(hypothesis.category)}</small></div></button>)}
      </nav>
      <article className="rca-hypothesis-detail">
        <header><div><span>Hypothesis {String(selectedHypothesis.rank).padStart(2, '0')}</span><h2>{selectedHypothesis.title}</h2></div><strong>At warning</strong></header>
        <p>{selectedHypothesis.rationale}</p>
        <div className="rca-evidence-columns">
          <section><h3 className="evidence-label support">Supporting evidence</h3>{selectedHypothesis.supporting_evidence_ids.length ? selectedHypothesis.supporting_evidence_ids.map((evidence) => <p key={evidence}><span className="evidence-label support">{humanize(evidence.replaceAll(':', ' '))}</span></p>) : <p>No supporting evidence recorded.</p>}</section>
          <section><h3 className="evidence-label challenge">Contradicting evidence</h3>{selectedHypothesis.contradicting_evidence_ids.length ? selectedHypothesis.contradicting_evidence_ids.map((evidence) => <p key={evidence}><span className="evidence-label challenge">{humanize(evidence.replaceAll(':', ' '))}</span></p>) : <p>No direct contradiction recorded.</p>}</section>
        </div>
        <div className="rca-validation-boundary"><div><span>Evidence requested at warning</span>{selectedHypothesis.missing_evidence.map((evidence) => <p key={evidence}>{evidence}</p>)}</div><div><span className="evidence-label challenge">Reject this hypothesis when</span><p>{selectedHypothesis.disconfirming_condition}</p></div></div>
      </article>
    </section>

    <section className="rca-caseboard">
      <header><div><span>Evidence-led case reconstruction</span><h2>How the conclusion changes</h2><p>Follow the case from first warning to repair, one checkpoint at a time.</p></div><div className="rca-caseboard-actions"><strong>{progress ? humanize(progress.stage) : 'Loading checkpoint'}</strong><button onClick={() => { window.location.hash = `rca-investigation?asset=${encodeURIComponent(assetId)}&at=${encodeURIComponent(activeAsOf ?? detail.alert.opened_at)}`; }}>Investigate flow <Icon name="arrow"/></button></div></header>
      <nav aria-label="RCA evidence checkpoints">
        {checkpoints.map((checkpoint, index) => <button key={checkpoint.asOf} className={activeAsOf === checkpoint.asOf ? 'active' : ''} aria-current={activeAsOf === checkpoint.asOf ? 'step' : undefined} onClick={() => setSelectedAsOf(checkpoint.asOf)}><span>{String(index + 1).padStart(2, '0')} · {checkpoint.label}</span><small>{checkpoint.detail}</small><time>{formatDateTime(checkpoint.asOf)}</time></button>)}
      </nav>
      {checkpointResource.error ? <p className="workflow-error">{checkpointResource.error}</p> : progress ? <>
        <div className="rca-case-summary"><div><span>Reconstructed through {formatDateTime(progress.as_of)}</span><p>{progress.summary}</p></div><div><span>Decision gate</span><p>{progress.decision_gate}</p></div></div>
        <details key={progress.as_of} className="rca-case-detail">
          <summary><span><strong>Supporting detail</strong><small>{progress.events.length} dated records · {progress.explanations.length} explanations</small></span><span className="rca-case-chevron" aria-hidden="true"/></summary>
          <div className="rca-case-path"><header><h3>Working causal path</h3><p>Arrows show the proposed mechanism; each step carries its own evidence state.</p></header><div>{progress.causal_path.map((link) => <article key={link.link_id}><span>{link.state === 'RCA_REPORTED' ? 'RCA report' : link.state === 'MONITORED_TREND' ? 'Monitored trend' : 'Hypothesis'}</span><strong>{link.label}</strong><small>{link.source_event ? `${humanize(link.source_event.source_grade)} · ${link.source_event.source_reference}` : link.state === 'MONITORED_TREND' ? 'Opening alert · monitored condition trend' : 'Not yet verified'}</small></article>)}</div></div>
          <div className="rca-case-columns">
            <section><header><h3>Evidence on record</h3><span>{progress.events.length} dated items</span></header>{progress.events.length ? progress.events.map((event) => <article key={event.event_id}><time>{formatDateTime(event.occurred_at)}</time><div><strong>{event.title}</strong><p>{event.detail}</p><small>{humanize(event.source_grade)} · {event.source_reference}</small></div></article>) : <p className="rca-case-empty">No post-alert lab or inspection findings yet. The monitored trend remains the initial clue.</p>}</section>
            <section><header><h3>Competing explanations</h3><span>Evidence for and against</span></header>{progress.explanations.map((item) => <article key={item.explanation_id}><div><strong>{item.title}</strong><b>{humanize(item.state)}</b></div><p>{item.starting_basis}</p><dl><div><dt className="evidence-label support">Supports</dt><dd>{item.supporting_events.length ? item.supporting_events.map((event) => <span className="evidence-label support" key={event.event_id}>{event.title}</span>) : 'No later finding yet'}</dd></div><div><dt className="evidence-label challenge">Challenges</dt><dd>{item.challenging_events.length ? item.challenging_events.map((event) => <span className="evidence-label challenge" key={event.event_id}>{event.title}</span>) : 'None recorded yet'}</dd></div></dl><small>Next check: {item.next_check}</small></article>)}</section>
          </div>
          <p className="rca-case-source-note">Retrospective chronology: the source does not establish when each result became available to the team.</p>
        </details>
      </> : <p className="rca-case-empty">Loading evidence at this checkpoint…</p>}
    </section>

    <section className="rca-lower-grid">
      <details className="rca-analogue-list">
        <summary><span><small>Historical evidence</small><strong>Similar incidents</strong></span><span>{detail.similar_incidents.length} retrieved</span><span className="rca-case-chevron" aria-hidden="true"/></summary>
        {detail.similar_incidents.map((incident) => <div key={incident.incident_id}><span>{String(incident.rank).padStart(2, '0')}</span><div><strong>{incident.title}</strong><p>{incident.asset_tag} · {humanize(incident.failure_mechanism)}</p><small>{incident.match_reasons.slice(0, 2).join(' · ')}</small></div><b>{Math.round(incident.hybrid_score * 100)}% match</b></div>)}
      </details>

      <details className="rca-verification-plan">
        <summary><span><small>RCA confirmation plan</small><strong>Evidence required to confirm RCA</strong></span><span>{rca.generation.investigation_steps.length} checks</span><span className="rca-case-chevron" aria-hidden="true"/></summary>
        {rca.generation.investigation_steps.map((step, index) => <div className="rca-verification-row" key={step.step_id}>
          <span>{String(index + 1).padStart(2, '0')}</span>
          <div>
            <header><strong>{step.instruction}</strong><b>{humanize(step.priority)}</b></header>
            <p>{step.rationale}</p>
            <dl><div><dt>Owner</dt><dd>{step.owner_role}</dd></div><div><dt>Evidence expected</dt><dd>{step.expected_evidence}</dd></div></dl>
          </div>
          {step.safety_gate && <b className="isolation-required">Shut down first</b>}
        </div>)}
      </details>
    </section>
  </div>;
}
