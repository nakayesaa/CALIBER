import type { AlertEvent, AlertStateTransition, AssetSummary, DriverAnalysis, InvestigationEvidenceEvent, InvestigationEvidenceProgress, TelemetryPoint } from './apiContracts';
import type { ProductionReport, ProductionReviewDecision } from './productionReview';

export interface EquipmentEvidence {
  alert: Pick<AlertEvent, 'alert_id' | 'asset_id' | 'first_signal_at' | 'opened_at' | 'highest_severity' | 'highest_severity_rank'>;
  as_of: string;
  window_start: string;
  window_end: string;
  points: Array<Pick<TelemetryPoint, 'timestamp' | 'operating_mode' | 'run_status' | 'anomaly_score' | 'decision_state'> & Partial<TelemetryPoint>>;
  transitions: AlertStateTransition[];
  drivers: DriverAnalysis;
  events: InvestigationEvidenceEvent[];
  explanations: InvestigationEvidenceProgress['explanations'];
  validation_note: string | null;
}

export interface EquipmentMonitoringAsset {
  asset: AssetSummary;
  timeline_start: string;
  timeline_end: string;
  latest_decision_state: string;
  highest_alert_severity: string | null;
  alert_count: number;
}

export const equipmentChecks = [
  { id: 'DATA_VALIDITY', title: 'Data validity', prompt: 'Compare timestamps, units, readings and instrument status with the equipment source.' },
  { id: 'OPERATING_CONTEXT', title: 'Operating context', prompt: 'Check whether the equipment was steady, starting, stopping or changing load.' },
  { id: 'ABNORMAL_BEHAVIOUR', title: 'Abnormal behaviour', prompt: 'Compare recorded alarms and persistence with the trend. Identify transient behaviour.' },
  { id: 'SUPPORTING_EVIDENCE', title: 'Supporting evidence', prompt: 'Check available lab, inspection and maintenance records. Record missing evidence explicitly.' },
] as const;

export interface EquipmentCheck {
  check: typeof equipmentChecks[number]['id'];
  result: 'VERIFIED' | 'ISSUE' | 'MISSING';
  finding: string;
  reference: string | null;
}

export interface EquipmentReport extends Omit<ProductionReport, 'scope' | 'impact' | 'points' | 'review'> {
  scope: 'EQUIPMENT';
  evidence: EquipmentEvidence;
  review: (NonNullable<ProductionReport['review']> & { checks: EquipmentCheck[]; human_context: string }) | null;
}

export type ScopeReport = ProductionReport | EquipmentReport;

export function preferredScopeReports(reports: ScopeReport[]): ScopeReport[] {
  const priority = { APPROVED: 0, SENT: 1, DRAFT: 2, CHANGES_REQUESTED: 3, UNABLE_TO_VALIDATE: 4 };
  return [...reports].sort((a, b) => priority[a.status] - priority[b.status]);
}

export interface CasePacket {
  case_id: string;
  version: string;
  asset: AssetSummary;
  alert_id: string;
  created_at: string;
  window_start: string;
  window_end: string;
  equipment_report_id: string;
  production_report_id: string;
  verified_scopes: number;
  required_scopes: number;
  can_escalate: boolean;
  state: 'AWAITING_VERIFICATION' | 'NEEDS_CORRECTION' | 'EVIDENCE_REQUIRED' | 'UNAVAILABLE' | 'READY_FOR_GM';
  summary: string;
  scopes: Array<{ scope: 'EQUIPMENT' | 'PRODUCTION'; report_id: string; version: string; recipient_name: string; status: string; verified: boolean; note: string | null }>;
}

export function canVerifyEquipment(decision: ProductionReviewDecision, checks: EquipmentCheck[], note: string, context: string, attested: boolean): boolean {
  if (!note.trim() || !context.trim() || checks.length !== 4 || new Set(checks.map((item) => item.check)).size !== 4) return false;
  if (checks.some((item) => !item.finding.trim() || (item.result !== 'MISSING' && !item.reference?.trim()))) return false;
  if (decision === 'APPROVED') return attested && checks.every((item) => item.result === 'VERIFIED');
  return checks.some((item) => item.result === (decision === 'CHANGES_REQUESTED' ? 'ISSUE' : 'MISSING'));
}

export function scopeReportLink(report: Pick<ScopeReport, 'scope' | 'report_id' | 'asset'>, personId: string): string {
  return `#${report.scope === 'EQUIPMENT' ? 'equipment-review' : 'production-review'}?${new URLSearchParams({ asset: report.asset.asset_id, request: report.report_id, person: personId })}`;
}

export function orderedEquipmentRequests(reports: EquipmentReport[]): EquipmentReport[] {
  return [...reports].sort((a, b) => Number(b.status === 'SENT') - Number(a.status === 'SENT') || b.evidence.alert.highest_severity_rank - a.evidence.alert.highest_severity_rank || Date.parse(a.due_at) - Date.parse(b.due_at));
}
