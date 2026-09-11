const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000/api/v1';

export interface SystemStatus {
  phase: string;
  api_status: string;
  pipeline_artifacts: Record<string, boolean>;
  llm_enabled: boolean;
}

export interface AssetSummary {
  asset_id: string;
  tag: string;
  name: string;
  plant_id: string;
  plant_name: string;
  equipment_family: string;
  equipment_type: string;
  equipment_class: string;
  discipline: string;
  criticality: string;
  monitoring_method: string;
}

export interface AssetOverview {
  asset: AssetSummary;
  timeline_start: string;
  timeline_end: string;
  latest_decision_state: string;
  highest_alert_severity: string | null;
  alert_count: number;
}

export interface TelemetryPoint {
  timestamp: string;
  operating_mode: string;
  run_status: string;
  radial_vibration_micron: number;
  water_in_oil_ppm: number;
  lube_oil_pressure_barg: number;
  bearing_metal_temperature_degc: number;
  feed_rate_tph: number;
  discharge_pressure_barg: number;
  anomaly_score: number | null;
  anomaly_threshold: number;
  is_anomaly: boolean;
  decision_state: string;
  severity_rank: number;
  alarm_breadth: number;
  breached_signals: string[];
}

export interface TelemetrySeries {
  asset_id: string;
  total_points: number;
  returned_points: number;
  points: TelemetryPoint[];
}

export interface AlertEvent {
  alert_id: string;
  asset_id: string;
  first_signal_at: string;
  opened_at: string;
  closed_at: string | null;
  status: string;
  highest_severity: string;
  highest_severity_rank: number;
  peak_anomaly_score: number;
  peak_score_at: string;
  duration_hours: number;
  primary_driver: string;
  breached_signals: string[];
}

export interface SimilarIncident {
  rank: number;
  incident_id: string;
  occurred_at: string;
  asset_tag: string;
  title: string;
  component: string;
  failure_mechanism: string;
  observed_symptoms: string[];
  business_consequences: string[];
  hybrid_score: number;
  match_reasons: string[];
}

export interface RCAHypothesis {
  hypothesis_id: string;
  rank: number;
  category: string;
  title: string;
  mechanism: string;
  confidence: number;
  rationale: string;
  supporting_evidence_ids: string[];
  contradicting_evidence_ids: string[];
  analogue_incident_ids: string[];
  missing_evidence: string[];
  disconfirming_condition: string;
}

export interface RCARecord {
  rca_id: string;
  alert_id: string;
  status: string;
  requested_by: string;
  model: string;
  provider?: string;
  status_history?: Array<{
    previous_status: string;
    new_status: string;
    actor: string;
    occurred_at: string;
    note: string;
  }>;
  generation: {
    executive_summary: string;
    hypotheses: RCAHypothesis[];
    investigation_steps: Array<{
      step_id: string;
      priority: string;
      instruction: string;
      rationale: string;
      expected_evidence: string;
      owner_role: string;
      safety_gate: boolean;
    }>;
    operating_guidance: string;
  };
}

export interface ActionItem {
  action_id: string;
  action_type: string;
  title: string;
  guidance: string;
  owner_role: string;
  priority: string;
  due_date: string;
  status: string;
  completion_criteria: string;
  effectiveness_check: string;
  status_history?: Array<{
    previous_status: string;
    new_status: string;
    actor: string;
    occurred_at: string;
    note: string;
  }>;
}

export interface ActionPlan {
  plan_id: string;
  rca_id: string;
  alert_id: string;
  selected_hypothesis_id: string;
  selected_cause_category: string;
  status: string;
  actions: ActionItem[];
}

export interface AlertDetail {
  alert: AlertEvent;
  opening_snapshot: {
    timestamp: string;
    decision_state: string;
    decision_reason: string;
    anomaly_score: number;
    anomaly_threshold: number;
    alarm_breadth: number;
    breached_signals: string[];
    top_drivers: Array<{ name: string; score: number }>;
  };
  similar_incidents: SimilarIncident[];
  rca: RCARecord | null;
  action_plans: ActionPlan[];
}

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
  telemetry: (assetId: string, maxPoints = 360, start?: string, end?: string) => {
    const query = new URLSearchParams({ max_points: String(maxPoints) });
    if (start) query.set('start', start);
    if (end) query.set('end', end);
    return request<TelemetrySeries>(`/assets/${assetId}/telemetry?${query}`);
  },
  alerts: (assetId?: string) =>
    request<AlertEvent[]>(`/alerts${assetId ? `?asset_id=${assetId}` : ''}`),
  alertDetail: (alertId: string) => request<AlertDetail>(`/alerts/${alertId}`),
  generateRca: (alertId: string, requestedBy: string, mode: 'ai' | 'prepared') =>
    request<RCARecord>(`/alerts/${alertId}/rca`, {
      method: 'POST', body: JSON.stringify({ requested_by: requestedBy, mode }),
    }),
  updateRcaStatus: (rcaId: string, status: 'UNDER_REVIEW' | 'APPROVED' | 'REJECTED', actor: string, note: string) =>
    request<RCARecord>(`/rca/${rcaId}/status`, {
      method: 'PATCH', body: JSON.stringify({ status, actor, note }),
    }),
  createActionPlan: (rcaId: string, hypothesisId: string) =>
    request<ActionPlan>(`/rca/${rcaId}/action-plans`, {
      method: 'POST', body: JSON.stringify({ hypothesis_id: hypothesisId }),
    }),
  updateActionStatus: (actionId: string, status: string, actor: string, note: string) =>
    request<ActionPlan>(`/actions/${actionId}/status`, {
      method: 'PATCH', body: JSON.stringify({ status, actor, note }),
    }),
};
