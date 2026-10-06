import type { EquipmentSignalField } from './conditionSignals';

export interface FlowStep {
  page: 'plant' | 'problems' | 'investigation';
  selector: string; title: string; text: string; next: string;
  tab?: number;
  field?: EquipmentSignalField;
  stage?: 'PROBABLE' | 'CONTAMINATION_SUPPORTED' | 'CAUSE_REPORTED' | 'REPAIR_REPORTED';
}

export const FLOW_STEPS: readonly FlowStep[] = [
  { page: 'plant', selector: '[data-flow="plant-overview"]', title: 'Start with the operating picture', text: 'IRIS brings production, energy, emissions, and equipment performance into one view. Start here to understand the operating context before reviewing an issue.', next: 'Show the Problem Tank' },
  { page: 'plant', selector: '[data-flow="problems-nav"], [data-flow="problems-entry"]', title: 'Find what needs a decision', text: 'The Problem Tank brings prioritized alerts together. Open it to move from the plant-wide picture to the evidence behind a specific equipment issue.', next: 'Open Problem Tank' },
  { page: 'problems', selector: '[data-flow="ko-3201-problem"]', title: 'Review the KO-3201 alert', text: 'This is the cracked-gas compressor case. Its row shows the recorded severity, anomaly peak, and workflow status. A priority is a reason to review evidence—not a confirmed root cause.', next: 'Open investigation' },
  { page: 'investigation', tab: 0, selector: '[data-flow="investigation-heading"]', title: 'Open the KO-3201 investigation', text: 'This case connects the recorded alert to its condition history, model explanation, and investigation findings. We will review each layer before handing evidence to the responsible operators.', next: 'Review detection' },
  { page: 'investigation', tab: 0, selector: '[data-flow="detection-chart"]', title: 'Trace the abnormal pattern', text: 'The anomaly score summarizes unusual behavior. The highlighted window connects the first signal to the warning. A statistical threshold flags a pattern for review; it does not establish a physical failure mechanism.', next: 'Check persistence' },
  { page: 'investigation', tab: 0, selector: '[data-flow="detection-facts"]', title: 'Understand why this alert matters', text: 'Review severity, persistence, and the number of affected variables together. Sustained deviation and converging condition signals give the supervisor a reason to investigate beyond a single unusual reading.', next: 'Inspect oil condition' },
  { page: 'investigation', tab: 1, field: 'water_in_oil_ppm', selector: '[data-flow="variable-chart"]', title: 'Follow water in oil', text: 'IRIS shows the oil-condition trend in ppm within the detection window. Use the source and measurement definition when interpreting the change. The trend supports a contamination hypothesis, not a confirmed water-entry source.', next: 'Inspect vibration' },
  { page: 'investigation', tab: 1, field: 'radial_vibration_micron', selector: '[data-flow="variable-chart"]', title: 'Check the mechanical response', text: 'Radial vibration is shown in micrometres. Compare its progression with oil condition while preserving the original units and sampling frequency. Different measurements must not be treated as interchangeable.', next: 'Inspect temperature' },
  { page: 'investigation', tab: 1, field: 'bearing_metal_temperature_degc', selector: '[data-flow="variable-chart"]', title: 'Check the thermal response', text: 'Bearing temperature adds another condition perspective. Read its trend alongside vibration and lubrication evidence. Multiple related deviations strengthen the need for inspection without proving causality.', next: 'Review the hypothesis' },
  { page: 'investigation', tab: 2, stage: 'PROBABLE', selector: '[data-flow="leading-cause"]', title: 'Start with a probable explanation', text: 'At alert opening, lubrication contamination is suspected. The water-entry source and bearing condition still need laboratory and inspection evidence. IRIS keeps that uncertainty visible.', next: 'Read model contributions' },
  { page: 'investigation', tab: 2, stage: 'PROBABLE', selector: '[data-flow="cause-evidence"]', title: 'Separate model explanation from proof', text: 'Contribution percentages explain the model assessment at this replay time. Historical analogues provide reference cases. Neither a contribution nor incident similarity is a causal probability or a verified diagnosis.', next: 'Replay sample evidence' },
  { page: 'investigation', tab: 2, stage: 'CONTAMINATION_SUPPORTED', selector: '[data-flow="evidence-replay"]', title: 'Update the hypothesis with sample evidence', text: 'The replay advances to the recorded evidence supporting oil contamination. Review the event time, finding, and source. These are recorded RCA event times—not supplied document-ingestion timestamps.', next: 'Review inspection findings' },
  { page: 'investigation', tab: 2, stage: 'CAUSE_REPORTED', selector: '[data-flow="leading-cause"]', title: 'Distinguish reported findings from predictions', text: 'The supplied RCA now reports cooler leakage and bearing distress. IRIS updates the explanation as evidence develops, clearly separating the earlier hypothesis from the later reported mechanism.', next: 'Review recorded repairs' },
  { page: 'investigation', tab: 2, stage: 'REPAIR_REPORTED', selector: '[data-flow="evidence-replay"]', title: 'Connect findings to the repair record', text: 'The repair entry records the response to the reported mechanism. Recorded repairs do not by themselves prove effectiveness: post-restart oil, vibration, and temperature checks still need review.', next: 'Prepare the handoff' },
  { page: 'investigation', tab: 3, stage: 'REPAIR_REPORTED', selector: '[data-flow="scope-handoff"]', title: 'Verify both scopes before accountable action', text: 'The supervisor prepares equipment and production reports for operator verification. The reviewed packet supports the required approval and subsequent CA/PA assignment. This tour has only read evidence: no draft, submission, or assignment was created.', next: 'Finish & explore' },
] as const;

export function flowHash(person: string) {
  return `plant?${new URLSearchParams({ asset: 'asset-ko-3201', person, flow: 'ko-3201' })}`;
}

export function cardPosition(box: { left: number; right: number; top: number; bottom: number }, width: number, height: number, cardWidth: number, cardHeight: number) {
  const left = box.right + cardWidth + 28 <= width ? box.right + 20 : box.left;
  const top = box.bottom + cardHeight + 28 <= height ? box.bottom + 20 : box.top - cardHeight - 20;
  return { left: Math.max(12, Math.min(left, width - cardWidth - 12)), top: Math.max(12, Math.min(top, height - cardHeight - 12)) };
}
