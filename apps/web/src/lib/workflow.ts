export function nextActionStatus(status: string): string | null {
  return ({
    PROPOSED: 'APPROVED',
    APPROVED: 'IN_PROGRESS',
    IN_PROGRESS: 'EFFECTIVENESS_REVIEW',
    EFFECTIVENESS_REVIEW: 'CLOSED',
  } as Record<string, string>)[status] ?? null;
}

export function actionTransitionLabel(status: string): string {
  return ({
    APPROVED: 'Approve',
    IN_PROGRESS: 'Start work',
    EFFECTIVENESS_REVIEW: 'Review result',
    CLOSED: 'Close action',
  } as Record<string, string>)[status] ?? status;
}
