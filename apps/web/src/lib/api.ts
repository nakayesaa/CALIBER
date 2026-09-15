const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000/api/v1';

import type {
  ActionPlan,
  ActionStatus,
  AlertDetail,
  AlertEvent,
  AssetOverview,
  AssetSummary,
  DataSourceDetail,
  DataSourceSummary,
  DriverAnalysis,
  EffectivenessReview,
  RCARecord,
  SystemStatus,
  TelemetrySeries,
  TraceClaim,
} from './apiContracts';

export * from './apiContracts';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: init?.body ? { 'Content-Type': 'application/json', ...init.headers } : init?.headers,
  });
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(payload?.detail ?? `Request failed with status ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  status: () => request<SystemStatus>('/status'),
  assets: () => request<AssetSummary[]>('/assets'),
  assetOverview: (assetId: string) => request<AssetOverview>(`/assets/${assetId}/overview`),
  effectiveness: (assetId: string) => request<EffectivenessReview>(`/assets/${assetId}/effectiveness`),
  dataSources: () => request<DataSourceSummary[]>('/data-sources'),
  dataSource: (sourceKey: string) => request<DataSourceDetail>(`/data-sources/${sourceKey}`),
  traceClaim: (traceId: string) => request<TraceClaim>(`/traceability/claims/${traceId}`),
  telemetry: (assetId: string, maxPoints = 360, start?: string, end?: string) => {
    const query = new URLSearchParams({ max_points: String(maxPoints) });
    if (start) query.set('start', start);
    if (end) query.set('end', end);
    return request<TelemetrySeries>(`/assets/${assetId}/telemetry?${query}`);
  },
  alerts: (assetId?: string) =>
    request<AlertEvent[]>(`/alerts${assetId ? `?asset_id=${assetId}` : ''}`),
  alertDetail: (alertId: string) => request<AlertDetail>(`/alerts/${alertId}`),
  driverAnalysis: (alertId: string, timestamp?: string) => {
    const query = timestamp ? `?${new URLSearchParams({ timestamp })}` : '';
    return request<DriverAnalysis>(`/alerts/${alertId}/driver-analysis${query}`);
  },
  generateRca: (alertId: string, mode: 'ai' | 'prepared') =>
    request<RCARecord>(`/alerts/${alertId}/rca`, {
      method: 'POST', body: JSON.stringify({ mode }),
    }),
  updateRcaStatus: (rcaId: string, status: 'UNDER_REVIEW' | 'APPROVED' | 'REJECTED', note: string) =>
    request<RCARecord>(`/rca/${rcaId}/status`, {
      method: 'PATCH', body: JSON.stringify({ status, note }),
    }),
  createActionPlan: (rcaId: string, hypothesisId: string) =>
    request<ActionPlan>(`/rca/${rcaId}/action-plans`, {
      method: 'POST', body: JSON.stringify({ hypothesis_id: hypothesisId }),
    }),
  updateActionStatus: (actionId: string, status: ActionStatus, note: string) =>
    request<ActionPlan>(`/actions/${actionId}/status`, {
      method: 'PATCH', body: JSON.stringify({ status, note }),
    }),
};
