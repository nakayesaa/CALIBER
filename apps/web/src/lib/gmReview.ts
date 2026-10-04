import type { ActionItem, ActionPlan, AssetSummary, RCARecord } from './apiContracts';
import type { EquipmentReport } from './equipmentReview';
import type { ProductionReport } from './productionReview';

export interface GmReport {
  report_id: string;
  case_id: string;
  version: string;
  revision: number;
  status: 'PENDING_REVIEW' | 'APPROVED' | 'RETURNED';
  created_by: string;
  recipient_id: string;
  recipient_name: string;
  submitted_at: string;
  note: string;
  asset: AssetSummary;
  alert_id: string;
  equipment_report: EquipmentReport;
  production_report: ProductionReport;
  rca: RCARecord | null;
  action_plans: ActionPlan[];
  decision: {
    decision: 'APPROVED' | 'RETURNED';
    note: string;
    actor_id: string;
    at: string;
  } | null;
}

export const gmStatusLabel: Record<GmReport['status'], string> = {
  PENDING_REVIEW: 'Awaiting GM decision',
  APPROVED: 'Approved by GM',
  RETURNED: 'Returned by GM',
};

export function gmActionRows(report: Pick<GmReport, 'report_id' | 'action_plans'>, plans: ActionPlan[]): Array<{ source: ActionItem; action: ActionItem | null }> {
  const current = plans.filter(plan => plan.gm_report_id === report.report_id).flatMap(plan => plan.actions);
  return report.action_plans.flatMap(plan => plan.actions)
    .filter(source => source.action_type !== 'CONTAINMENT')
    .map(source => ({ source, action: current.find(action => action.source_action_id === source.action_id) ?? null }));
}

export function gmReportLink(
  requestId: string,
  assetId: string,
  personId: string,
): string {
  return `#gm-review?${new URLSearchParams({ request: requestId, asset: assetId, person: personId })}`;
}
