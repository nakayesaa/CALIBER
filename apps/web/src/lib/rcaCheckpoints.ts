import type { InvestigationEvidenceEvent } from './apiContracts';

export interface RcaCheckpoint {
  asOf: string;
  label: string;
  detail: string;
  kind: 'WARNING' | InvestigationEvidenceEvent['kind'];
}

export function rcaCheckpoints(openedAt: string, events: InvestigationEvidenceEvent[]): RcaCheckpoint[] {
  const checkpoints: RcaCheckpoint[] = [{ asOf: openedAt, label: 'Warning', detail: 'Alert opened', kind: 'WARNING' }];
  const seen = new Set([openedAt]);
  for (const event of events) {
    if (seen.has(event.occurred_at)) continue;
    seen.add(event.occurred_at);
    checkpoints.push({
      asOf: event.occurred_at,
      label: event.kind === 'ACTION' ? 'Repair' : event.kind.charAt(0) + event.kind.slice(1).toLowerCase(),
      detail: event.title.replace(/ reference$/i, ''),
      kind: event.kind,
    });
  }
  return checkpoints;
}
