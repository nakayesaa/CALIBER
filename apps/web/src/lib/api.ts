const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000/api/v1';

import type {
  ActionPlan,
  ActionStatus,
  CaseReview,
  ExecutionEvidenceInput,
  AlertDetail,
  AlertEvent,
  AssetOverview,
  AssetSummary,
  DataSourceDetail,
  DataSourceSummary,
  DriverAnalysis,
  EffectivenessReview,
  InvestigationEvidenceProgress,
  PlantRateSeries,
  RCARecord,
  SystemStatus,
  TelemetrySeries,
  TraceClaim,
  WorkflowSession,
} from './apiContracts';

export * from './apiContracts';

let workflowPerson: string | null = null;

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      ...(init?.body ? { 'Content-Type': 'application/json' } : {}),
      ...(workflowPerson ? { 'X-Caliber-Person': workflowPerson } : {}),
      ...init?.headers,
    },
  });
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(payload?.detail ?? `Request failed with status ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  setWorkflowPerson: (personId: string | null) => { workflowPerson = personId; },
  workflowSession: () => request<WorkflowSession>('/workflow/session'),
  caseReview: (alertId: string) => request<CaseReview>(`/alerts/${alertId}/cross-check`),
  submitCrossCheck: (alertId: string, data: { note: string; references: string[]; human_context: string; expected_revision: number }) =>
    request<CaseReview>(`/alerts/${alertId}/cross-check`, { method: 'POST', body: JSON.stringify(data) }),
  reviewCrossCheck: (alertId: string, data: { decision: 'VERIFIED' | 'CHANGES_REQUESTED'; note: string; expected_revision: number }) =>
    request<CaseReview>(`/alerts/${alertId}/cross-check/review`, { method: 'POST', body: JSON.stringify(data) }),
  assignAction: (actionId: string, data: { person_id: string; due_date: string; expected_status: ActionStatus; expected_assigned_to: string | null; expected_revision: number; note: string }) =>
    request<ActionPlan>(`/actions/${actionId}/assignment`, { method: 'POST', body: JSON.stringify(data) }),
  respondToAssignment: (actionId: string, data: { decision: 'ACCEPT' | 'BLOCK'; note: string; expected_revision: number }) =>
    request<ActionPlan>(`/actions/${actionId}/assignment/response`, { method: 'POST', body: JSON.stringify(data) }),
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
  plantRate: (assetId: string) => request<PlantRateSeries>(`/assets/${assetId}/production-rate`),
  alerts: (assetId?: string) =>
    request<AlertEvent[]>(`/alerts${assetId ? `?asset_id=${assetId}` : ''}`),
  alertDetail: (alertId: string) => request<AlertDetail>(`/alerts/${alertId}`),
  investigationEvidence: (alertId: string, asOf?: string) =>
    request<InvestigationEvidenceProgress>(`/alerts/${alertId}/investigation-evidence${asOf ? `?${new URLSearchParams({ as_of: asOf })}` : ''}`),
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
  updateActionStatus: (actionId: string, status: ActionStatus, note: string, evidence?: ExecutionEvidenceInput, expectedRevision = 0) =>
    request<ActionPlan>(`/actions/${actionId}/status`, {
      method: 'PATCH', body: JSON.stringify({ status, note, evidence, expected_revision: expectedRevision }),
    }),
};
