import { api } from '../lib/api';
import { PRIMARY_ASSET_ID } from '../lib/appConfig';
import { useApiResource } from '../lib/useApiResource';

// Reuse the governed retriever; history is reference evidence, not today's alert queue.
async function loadHistory() {
  const alerts = await api.alerts(PRIMARY_ASSET_ID);
  const alert = alerts.filter((item) => Date.parse(item.opened_at) <= Date.parse('2026-04-30T23:00:00+07:00')).sort((a, b) => Date.parse(b.opened_at) - Date.parse(a.opened_at))[0];
  if (!alert) return [];
  return (await api.alertDetail(alert.alert_id)).similar_incidents;
}

export function SimilarIncidentPreview() {
  const resource = useApiResource('plant-ko-history', loadHistory);
  return <details className="portfolio-history"><summary>Similar historical incidents <span aria-hidden="true">+</span></summary>
    <p>Retrieved for the KO-3201 alert. Previous cases inform hypotheses; they do not confirm the current cause.</p>
    {resource.loading ? <p>Loading incident history…</p> : resource.error ? <p role="status">History unavailable: {resource.error} <button onClick={resource.reload}>Retry</button></p> : !resource.data?.length ? <p>No eligible similar incidents were retrieved.</p> : resource.data.slice(0, 3).map((incident) => <article key={incident.incident_id}><strong>{incident.asset_tag} · {incident.title}</strong><p>{incident.occurred_at.slice(0, 10)} · {incident.failure_mechanism}</p><ul>{incident.match_reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul><small>{incident.incident_id} · {incident.source_reference}</small></article>)}
  </details>;
}
