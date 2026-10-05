const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000/api/v1';
import type { ProductionReport, ProductionReviewDecision } from './productionReview';
import type { EquipmentCheck, EquipmentEvidence, EquipmentMonitoringAsset, EquipmentReport } from './equipmentReview';
import type { CasePacket } from './equipmentReview';
import type { GmReport } from './gmReview';

import type {
  ActionPlan,
  ActionAssignmentInput,
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
let workflowSelection = 0;

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
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

export async function selectWorkflowSession(personId?: string): Promise<WorkflowSession> {
  const selection = ++workflowSelection;
  const session = await request<WorkflowSession>('/workflow/session');
  if (selection !== workflowSelection || !session.can_switch || !personId || personId === session.current.person_id) return session;
  const previous = workflowPerson;
  workflowPerson = personId;
  try { return await request<WorkflowSession>('/workflow/session'); }
  catch (error) { if (selection === workflowSelection) workflowPerson = previous; throw error; }
}

export const api = {
  assignedActions: () => request<ActionPlan[]>('/workflow/assigned-actions'),
  gmActionPlans: (reportId: string) => request<ActionPlan[]>(`/workflow/gm-reports/${encodeURIComponent(reportId)}/actions`),
  assignGmAction: (reportId: string, sourceActionId: string, data: ActionAssignmentInput) =>
    request<ActionPlan>(`/workflow/gm-reports/${encodeURIComponent(reportId)}/actions/${encodeURIComponent(sourceActionId)}/assignment`, { method: 'POST', body: JSON.stringify(data) }),
  casePacket: (caseId: string) => request<CasePacket>(`/workflow/case-packets/${encodeURIComponent(caseId)}`),
  gmReports: () => request<GmReport[]>('/workflow/gm-reports'),
  gmReport: (reportId: string) => request<GmReport>(`/workflow/gm-reports/${encodeURIComponent(reportId)}`),
  submitToGm: (caseId: string, data: { recipient_id: string; note: string }) =>
    request<GmReport>(`/workflow/case-packets/${encodeURIComponent(caseId)}/submit-to-gm`, { method: 'POST', body: JSON.stringify(data) }),
  decideGmReport: (reportId: string, data: { decision: 'APPROVED' | 'RETURNED'; expected_revision: number; note: string }) =>
    request<GmReport>(`/workflow/gm-reports/${encodeURIComponent(reportId)}/decision`, { method: 'POST', body: JSON.stringify(data) }),
  casePackets: () => request<CasePacket[]>('/workflow/case-packets'),
  createCasePacket: (data: { request_id: string; equipment_report_id: string; production_report_id: string }) =>
    request<CasePacket>('/workflow/case-packets', { method: 'POST', body: JSON.stringify(data) }),
  equipmentMonitoring: () => request<EquipmentMonitoringAsset[]>('/workflow/equipment-monitoring'),
  operatorEquipmentEvidence: (assetId: string) => request<EquipmentEvidence>(`/workflow/equipment-monitoring/${encodeURIComponent(assetId)}`),
  equipmentReports: () => request<EquipmentReport[]>('/workflow/equipment-reports'),
  equipmentReport: (reportId: string) => request<EquipmentReport>(`/workflow/equipment-reports/${encodeURIComponent(reportId)}`),
  createEquipmentReport: (data: { request_id: string; asset_id: string; alert_id: string; recipient_id: string; due_at: string; note: string }) =>
    request<EquipmentReport>('/workflow/equipment-reports', { method: 'POST', body: JSON.stringify(data) }),
  sendEquipmentReport: (reportId: string, revision: number) =>
    request<EquipmentReport>(`/workflow/equipment-reports/${encodeURIComponent(reportId)}/send`, { method: 'POST', body: JSON.stringify({ expected_revision: revision }) }),
  respondEquipmentReport: (reportId: string, data: { decision: ProductionReviewDecision; note: string; attested: boolean; expected_revision: number; checks: EquipmentCheck[]; human_context: string }) =>
    request<EquipmentReport>(`/workflow/equipment-reports/${encodeURIComponent(reportId)}/response`, { method: 'POST', body: JSON.stringify(data) }),
  productionReports: () => request<ProductionReport[]>('/workflow/production-reports'),
  productionReport: (reportId: string) => request<ProductionReport>(`/workflow/production-reports/${encodeURIComponent(reportId)}`),
  createProductionReport: (data: { request_id: string; asset_id: string; recipient_id: string; due_at: string; note: string; alert_id?: string }) =>
    request<ProductionReport>('/workflow/production-reports', { method: 'POST', body: JSON.stringify(data) }),
  sendProductionReport: (reportId: string, revision: number) =>
    request<ProductionReport>(`/workflow/production-reports/${encodeURIComponent(reportId)}/send`, { method: 'POST', body: JSON.stringify({ expected_revision: revision }) }),
  respondProductionReport: (reportId: string, data: { decision: ProductionReviewDecision; note: string; attested: boolean; expected_revision: number }) =>
    request<ProductionReport>(`/workflow/production-reports/${encodeURIComponent(reportId)}/response`, { method: 'POST', body: JSON.stringify(data) }),
  workflowSession: () => request<WorkflowSession>('/workflow/session'),
  caseReview: (alertId: string) => request<CaseReview>(`/alerts/${alertId}/cross-check`),
  submitCrossCheck: (alertId: string, data: { note: string; references: string[]; human_context: string; expected_revision: number }) =>
    request<CaseReview>(`/alerts/${alertId}/cross-check`, { method: 'POST', body: JSON.stringify(data) }),
  reviewCrossCheck: (alertId: string, data: { decision: 'VERIFIED' | 'CHANGES_REQUESTED'; note: string; expected_revision: number }) =>
    request<CaseReview>(`/alerts/${alertId}/cross-check/review`, { method: 'POST', body: JSON.stringify(data) }),
  assignAction: (actionId: string, data: ActionAssignmentInput) =>
    request<ActionPlan>(`/actions/${actionId}/assignment`, { method: 'POST', body: JSON.stringify(data) }),
  respondToAssignment: (actionId: string, data: { decision: 'ACCEPT' | 'BLOCK'; note: string; expected_revision: number }) =>
    request<ActionPlan>(`/actions/${actionId}/assignment/response`, { method: 'POST', body: JSON.stringify(data) }),
  status: () => request<SystemStatus>('/status'),
  assets: () => request<AssetSummary[]>('/assets'),
  assetOverview: (assetId: string) => request<AssetOverview>(`/assets/${assetId}/overview`),
  effectiveness: (assetId: string) => request<EffectivenessReview>(`/assets/${assetId}/effectiveness`),
  dataSources: () => request<DataSourceSummary[]>('/data-sources'),
  dataSource: (sourceKey: string) => request<DataSourceDetail>(`/data-sources/${sourceKey}`),
  traceClaim: (traceId: string, assetId?: string) => request<TraceClaim>(`/traceability/claims/${traceId}${assetId ? `?asset_id=${encodeURIComponent(assetId)}` : ''}`),
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
