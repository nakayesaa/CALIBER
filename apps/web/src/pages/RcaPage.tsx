import { EmptyState, ErrorState, LoadingState } from '../components/ViewState';
import { Icon } from '../components/Icon';
import { api } from '../lib/api';
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

  return <div className="product-view">
    <ViewHeader eyebrow="Evidence before conclusion" title="RCA workspace" description="The alert snapshot and retrieved analogues ground the AI draft before human approval."/>
    {!detail ? <EmptyState title="No alert selected" description="A grouped model alert starts the RCA workflow."/> : <div className="rca-layout">
      <section className="evidence-panel panel"><div className="section-heading"><h2>Opening evidence</h2><b className="status-tag warning">{humanize(detail.alert.highest_severity)}</b></div><div className="evidence-grid"><Evidence label="Peak anomaly" value={formatSignal(detail.alert.peak_anomaly_score)}/><Evidence label="Alarm breadth" value={String(detail.opening_snapshot.alarm_breadth)}/><Evidence label="Primary driver" value={humanize(detail.alert.primary_driver)}/><Evidence label="Signals" value={String(detail.alert.breached_signals.length)}/></div></section>
      <section className="analogue-panel panel"><div className="section-heading"><h2>Similar incidents</h2><span>{detail.similar_incidents.length} retrieved</span></div>{detail.similar_incidents.map((incident) => <article className="analogue-row" key={incident.incident_id}><b>#{incident.rank}</b><div><h3>{incident.title}</h3><p>{incident.asset_tag} · {humanize(incident.failure_mechanism)}</p><small>{incident.match_reasons.join(' · ')}</small></div><strong>{Math.round(incident.hybrid_score * 100)}%</strong></article>)}</section>
      <section className="rca-output panel"><div className="section-heading"><h2>Root cause indication</h2><span className="governed-label"><Icon name="spark"/> AI assisted</span></div>{detail.rca ? <><p className="executive-summary">{detail.rca.generation.executive_summary}</p>{detail.rca.generation.hypotheses.map((hypothesis) => <article className="hypothesis" key={hypothesis.hypothesis_id}><b>#{hypothesis.rank}</b><div><h3>{hypothesis.title}</h3><p>{hypothesis.rationale}</p></div><strong>{Math.round(hypothesis.confidence * 100)}%</strong></article>)}</> : <EmptyState title="Evidence package is ready" description="Add the OpenAI key, then generate the grounded RCA draft from this alert and its historical analogues."/>}</section>
    </div>}
  </div>;
}

function Evidence({ label, value }: { label: string; value: string }) { return <div><span>{label}</span><strong>{value}</strong></div>; }
