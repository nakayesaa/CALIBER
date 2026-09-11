import { EmptyState, ErrorState, LoadingState } from '../components/ViewState';
import { Icon } from '../components/Icon';
import { api } from '../lib/api';
import { rcaForAlert } from '../lib/demoWorkflow';
import { formatSignal, humanize } from '../lib/format';
import { useApiResource } from '../lib/useApiResource';
import { ViewHeader } from './ProblemTankPage';

async function loadRcaWorkspace() {
  const alerts = await api.alerts('asset-ko-3201');
  return alerts[0] ? api.alertDetail(alerts[0].alert_id) : null;
}

export function RcaPage() {
  const resource = useApiResource('rca-workspace', loadRcaWorkspace);
  if (resource.loading) return <LoadingState/>;
  if (resource.error) return <ErrorState message={resource.error}/>;
  const detail = resource.data;
  const rca = detail ? rcaForAlert(detail.alert.alert_id, detail.rca) : null;

  return <div className="product-view">
    <ViewHeader eyebrow="Evidence before conclusion" title="RCA workspace" description="The alert snapshot and retrieved analogues ground the AI draft before human approval."/>
    {!detail ? <EmptyState title="No alert selected" description="A grouped model alert starts the RCA workflow."/> : <div className="rca-layout">
      <section className="evidence-panel panel"><div className="section-heading"><h2>Opening evidence</h2><b className="status-tag warning">{humanize(detail.alert.highest_severity)}</b></div><div className="evidence-grid"><Evidence label="Peak anomaly" value={formatSignal(detail.alert.peak_anomaly_score)}/><Evidence label="Alarm breadth" value={String(detail.opening_snapshot.alarm_breadth)}/><Evidence label="Primary driver" value={humanize(detail.alert.primary_driver)}/><Evidence label="Signals" value={String(detail.alert.breached_signals.length)}/></div></section>
      <section className="analogue-panel panel"><div className="section-heading"><h2>Similar incidents</h2><span>{detail.similar_incidents.length} retrieved</span></div>{detail.similar_incidents.slice(0, 3).map((incident) => <article className="analogue-row" key={incident.incident_id}><b>#{incident.rank}</b><div><h3>{incident.title}</h3><p>{incident.asset_tag} · {humanize(incident.failure_mechanism)}</p><small>{incident.match_reasons.join(' · ')}</small></div><strong>{Math.round(incident.hybrid_score * 100)}%</strong></article>)}</section>
      <section className="rca-output panel"><div className="section-heading"><h2>Root cause indication</h2><div className="section-meta"><b className="status-tag approved">{rca ? humanize(rca.status) : 'Not generated'}</b><span className="governed-label"><Icon name="spark"/> AI assisted</span></div></div>{rca ? <><p className="executive-summary">{rca.generation.executive_summary}</p><div className="hypothesis-list">{rca.generation.hypotheses.map((hypothesis) => <article className={`hypothesis${hypothesis.rank === 1 ? ' selected-hypothesis' : ''}`} key={hypothesis.hypothesis_id}><b>#{hypothesis.rank}</b><div><div className="hypothesis-title"><h3>{hypothesis.title}</h3>{hypothesis.rank === 1 && <span>Selected cause</span>}</div><p>{hypothesis.rationale}</p><details><summary>Evidence and validation boundary</summary><p><strong>Mechanism:</strong> {hypothesis.mechanism}</p><p><strong>Missing evidence:</strong> {hypothesis.missing_evidence.join('; ')}.</p><p><strong>Reject when:</strong> {hypothesis.disconfirming_condition}</p></details></div><strong>{Math.round(hypothesis.confidence * 100)}%</strong></article>)}</div></> : <EmptyState title="Evidence package is ready" description="Generate the grounded RCA draft from this alert and its historical analogues."/>}</section>
      {rca && <section className="investigation-panel panel"><div className="section-heading"><h2>Verification plan</h2><span>{rca.generation.investigation_steps.length} ordered checks</span></div><div className="investigation-list">{rca.generation.investigation_steps.map((step, index) => <article key={step.step_id}><b>{String(index + 1).padStart(2, '0')}</b><div><header><h3>{step.instruction}</h3><span className={`priority-tag ${step.priority.toLowerCase()}`}>{humanize(step.priority)}</span></header><p>{step.rationale}</p><footer><span>Owner: {step.owner_role}</span><span>Evidence: {step.expected_evidence}</span>{step.safety_gate && <strong>Safety gate</strong>}</footer></div></article>)}</div><div className="operating-guidance"><Icon name="alert"/><div><b>Operating guidance</b><p>{rca.generation.operating_guidance}</p></div></div></section>}
    </div>}
  </div>;
}

function Evidence({ label, value }: { label: string; value: string }) { return <div><span>{label}</span><strong>{value}</strong></div>; }
