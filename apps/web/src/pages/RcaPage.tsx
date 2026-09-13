import { useState } from 'react';

import type { PageId } from '../components/AppShell';
import { SignalChart } from '../components/SignalChart';
import { EmptyState, ErrorState, LoadingState } from '../components/ViewState';
import { api, type AlertDetail, type TelemetrySeries } from '../lib/api';
import { conditionSignals, type ConditionField } from '../lib/conditionSignals';
import { rcaForAlert } from '../lib/demoWorkflow';
import { formatDate, formatSignal, humanize } from '../lib/format';
import { useApiResource } from '../lib/useApiResource';

interface RcaWorkspaceData {
  detail: AlertDetail;
  telemetry: TelemetrySeries;
}

async function loadRcaWorkspace(): Promise<RcaWorkspaceData | null> {
  const alerts = await api.alerts('asset-ko-3201');
  const alert = alerts[0];
  if (!alert) return null;
  const detail = await api.alertDetail(alert.alert_id);
  const telemetry = await api.telemetry(alert.asset_id, 1800, alert.first_signal_at, alert.closed_at ?? alert.peak_score_at);
  return { detail, telemetry };
}

export function RcaPage({ onNavigate }: { onNavigate: (page: PageId) => void }) {
  const [selectedSignal, setSelectedSignal] = useState<ConditionField>('water_in_oil_ppm');
  const [selectedHypothesisId, setSelectedHypothesisId] = useState<string | null>(null);
  const resource = useApiResource('rca-workspace', loadRcaWorkspace);
  if (resource.loading) return <LoadingState/>;
  if (resource.error) return <ErrorState message={resource.error}/>;
  if (!resource.data) return <EmptyState title="No alert selected" description="A prioritized equipment alert starts the RCA workflow."/>;

  const { detail, telemetry } = resource.data;
  const rca = rcaForAlert(detail.alert.alert_id, detail.rca);
  if (!rca) return <EmptyState title="Evidence package ready" description="Generate a reviewable RCA draft from the alert evidence and historical analogues."/>;

  const leadingHypothesis = rca.generation.hypotheses[0];
  const selectedHypothesis = rca.generation.hypotheses.find((hypothesis) => hypothesis.hypothesis_id === selectedHypothesisId) ?? leadingHypothesis;
  const signal = conditionSignals.find((candidate) => candidate.field === selectedSignal)!;
  const signalValues = telemetry.points.map((point) => Number(point[selectedSignal]));
  return <div className="decision-workspace rca-workspace">
    <header className="decision-workspace-heading">
      <div><span>KO-3201 · {detail.alert.alert_id}</span><h1>Root cause analysis</h1><p>Trace the probable cause from equipment evidence, historical analogues, and explicit validation boundaries.</p></div>
      <div><b>{humanize(rca.status)}</b><button onClick={() => onNavigate('actions')}>Open CA/PA plan</button></div>
    </header>

    <section className="rca-decision-grid">
      <article className="rca-leading-decision">
        <header><span>Leading probable cause</span><strong>{Math.round(leadingHypothesis.confidence * 100)}% confidence</strong></header>
        <h2>{leadingHypothesis.title}</h2>
        <p>{leadingHypothesis.mechanism}</p>
        <dl>
          <div><dt>Supporting evidence</dt><dd>{leadingHypothesis.supporting_evidence_ids.length}</dd></div>
          <div><dt>Contradictions</dt><dd>{leadingHypothesis.contradicting_evidence_ids.length}</dd></div>
          <div><dt>Historical analogues</dt><dd>{leadingHypothesis.analogue_incident_ids.length}</dd></div>
          <div><dt>Decision status</dt><dd>{humanize(rca.status)}</dd></div>
        </dl>
        <p className="rca-leading-rationale">{leadingHypothesis.rationale}</p>
      </article>

      <article className="rca-signal-evidence">
        <header><div><span>Signal evidence</span><h2>{signal.label}</h2></div><div><span>Window peak</span><strong>{signalValues.length ? formatSignal(Math.max(...signalValues)) : '—'} {signal.unit}</strong></div></header>
        <nav aria-label="RCA evidence signals">{conditionSignals.map((candidate) => <button className={candidate.field === selectedSignal ? 'active' : ''} key={candidate.field} onClick={() => setSelectedSignal(candidate.field)}>{candidate.label}</button>)}</nav>
        <div className="rca-evidence-chart"><SignalChart points={telemetry.points} field={selectedSignal} highlightTimestamp={detail.alert.peak_score_at}/></div>
        <footer><span>{formatDate(detail.alert.first_signal_at)} · first signal</span><b>{formatDate(detail.alert.peak_score_at)} · peak risk</b><span>{formatDate(detail.alert.closed_at ?? detail.alert.peak_score_at)} · intervention</span></footer>
      </article>
    </section>

    <section className="rca-hypothesis-workspace">
      <nav aria-label="Root cause hypotheses">
        <header><h2>Ranked hypotheses</h2><span>{rca.generation.hypotheses.length} candidates</span></header>
        {rca.generation.hypotheses.map((hypothesis) => <button className={hypothesis.hypothesis_id === selectedHypothesis.hypothesis_id ? 'active' : ''} key={hypothesis.hypothesis_id} onClick={() => setSelectedHypothesisId(hypothesis.hypothesis_id)}><span>{String(hypothesis.rank).padStart(2, '0')}</span><div><strong>{hypothesis.title}</strong><small>{humanize(hypothesis.category)}</small></div><b>{Math.round(hypothesis.confidence * 100)}%</b></button>)}
      </nav>
      <article className="rca-hypothesis-detail">
        <header><div><span>Hypothesis {String(selectedHypothesis.rank).padStart(2, '0')}</span><h2>{selectedHypothesis.title}</h2></div><strong>{Math.round(selectedHypothesis.confidence * 100)}%</strong></header>
        <p>{selectedHypothesis.rationale}</p>
        <div className="rca-evidence-columns">
          <section><h3>Supporting evidence</h3>{selectedHypothesis.supporting_evidence_ids.length ? selectedHypothesis.supporting_evidence_ids.map((evidence) => <p key={evidence}>{humanize(evidence.replaceAll(':', ' '))}</p>) : <p>No supporting evidence recorded.</p>}</section>
          <section><h3>Contradicting evidence</h3>{selectedHypothesis.contradicting_evidence_ids.length ? selectedHypothesis.contradicting_evidence_ids.map((evidence) => <p key={evidence}>{humanize(evidence.replaceAll(':', ' '))}</p>) : <p>No direct contradiction recorded.</p>}</section>
        </div>
        <div className="rca-validation-boundary"><div><span>Evidence still required</span>{selectedHypothesis.missing_evidence.map((evidence) => <p key={evidence}>{evidence}</p>)}</div><div><span>Reject this hypothesis when</span><p>{selectedHypothesis.disconfirming_condition}</p></div></div>
      </article>
    </section>

    <section className="rca-lower-grid">
      <article className="rca-analogue-list">
        <header><div><span>Historical evidence</span><h2>Similar incidents</h2></div><b>{detail.similar_incidents.length} retrieved</b></header>
        {detail.similar_incidents.slice(0, 4).map((incident) => <div key={incident.incident_id}><span>{String(incident.rank).padStart(2, '0')}</span><div><strong>{incident.title}</strong><p>{incident.asset_tag} · {humanize(incident.failure_mechanism)}</p><small>{incident.match_reasons.slice(0, 2).join(' · ')}</small></div><b>{Math.round(incident.hybrid_score * 100)}%</b></div>)}
      </article>

      <article className="rca-verification-plan">
        <header><div><span>RCA confirmation plan</span><h2>Evidence required to confirm RCA</h2></div><b>{rca.generation.investigation_steps.length} checks</b></header>
        {rca.generation.investigation_steps.map((step, index) => <div className="rca-verification-row" key={step.step_id}>
          <span>{String(index + 1).padStart(2, '0')}</span>
          <div>
            <header><strong>{step.instruction}</strong><b>{humanize(step.priority)}</b></header>
            <p>{step.rationale}</p>
            <dl><div><dt>Owner</dt><dd>{step.owner_role}</dd></div><div><dt>Evidence expected</dt><dd>{step.expected_evidence}</dd></div></dl>
          </div>
          {step.safety_gate && <b className="isolation-required">Shut down first</b>}
        </div>)}
      </article>
    </section>
  </div>;
}
