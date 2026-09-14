import type { DriverAnalysis, SignalContribution } from './api';

export function contributionForField(
  analysis: DriverAnalysis | null,
  sourceField: string,
): SignalContribution | undefined {
  return analysis?.contributions.find(
    (contribution) => contribution.source_field === sourceField,
  );
}

export function contributionRank(
  analysis: DriverAnalysis,
  contribution: SignalContribution,
): number {
  return analysis.contributions.findIndex(
    (candidate) => candidate.signal_key === contribution.signal_key,
  ) + 1;
}
