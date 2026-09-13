import type { ActionStatus } from './api';

const nextStatus: Partial<Record<ActionStatus, ActionStatus>> = {
  PROPOSED: 'APPROVED',
  APPROVED: 'IN_PROGRESS',
  IN_PROGRESS: 'EFFECTIVENESS_REVIEW',
  EFFECTIVENESS_REVIEW: 'CLOSED',
};

const transitionLabel: Partial<Record<ActionStatus, string>> = {
  APPROVED: 'Approve',
  IN_PROGRESS: 'Start work',
  EFFECTIVENESS_REVIEW: 'Review result',
  CLOSED: 'Close action',
};

export function nextActionStatus(status: ActionStatus): ActionStatus | null {
  return nextStatus[status] ?? null;
}

export function actionTransitionLabel(status: ActionStatus): string {
  return transitionLabel[status] ?? status;
}
