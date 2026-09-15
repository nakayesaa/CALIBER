import type { ActionPlan, AlertDetail, RCARecord } from './api';

export interface WorkflowView {
  rca: RCARecord | null;
  actionPlans: ActionPlan[];
  isPrepared: boolean;
}

export function workflowView(detail: AlertDetail): WorkflowView {
  if (detail.rca) {
    return { rca: detail.rca, actionPlans: detail.action_plans, isPrepared: false };
  }
  return {
    rca: detail.prepared_workflow?.rca ?? null,
    actionPlans: detail.prepared_workflow?.action_plans ?? [],
    isPrepared: Boolean(detail.prepared_workflow),
  };
}
