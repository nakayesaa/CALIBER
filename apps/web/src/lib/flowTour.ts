import type { EquipmentSignalField } from './conditionSignals';

export interface FlowStep {
  page: 'plant' | 'problems' | 'investigation' | 'operator-equipment' | 'production-review' | 'gm-review';
  selector: string; title: string; text: string; next: string;
  tab?: number;
  panel?: string;
  expand?: boolean;
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

const EQUIPMENT_STEPS: readonly FlowStep[] = [
  { page: 'operator-equipment', panel: 'monitoring', selector: '[data-flow="operator-heading"]', title: 'Start in your equipment workspace', text: 'IRIS brings your assigned condition monitoring and verification requests into one workspace. This tour reads the equipment evidence; it does not submit a verification or authorize maintenance.', next: 'Check your scope' },
  { page: 'operator-equipment', panel: 'monitoring', selector: '[data-flow="operator-scope"]', title: 'Stay within the assigned scope', text: 'Check which equipment is assigned to you and whether requests are awaiting review. Your verification covers equipment evidence only. Production verification and management authorization remain separate decisions.', next: 'Review the recorded trajectory' },
  { page: 'operator-equipment', panel: 'monitoring', selector: '[data-flow="operator-trajectory"]', title: 'Read the historical alert window', text: 'Trace the anomaly and recorded state transitions from first signal to peak. The dates describe a historical event window, not live plant conditions. Persistence helps distinguish an isolated deviation from sustained deterioration.', next: 'Inspect condition signals' },
  { page: 'operator-equipment', panel: 'monitoring', selector: '[data-flow="operator-signals"]', title: 'Compare readings with engineering limits', text: 'Each condition card preserves its unit, alarm and trip limits, and model contribution. Interpret limit direction and persistence together. Model contributions explain the assessment; they do not confirm a physical cause.', next: 'Inspect supporting findings' },
  { page: 'operator-equipment', panel: 'monitoring', expand: true, selector: '[data-flow="operator-findings"]', title: 'Challenge the interpretation with records', text: 'Review laboratory and inspection references alongside supporting and contradicting findings. Missing records are not confirmation. Keep the source and cutoff visible when deciding whether the evidence can be verified.', next: 'Open your verification inbox' },
  { page: 'operator-equipment', panel: 'requests', selector: '[data-flow="operator-inbox"]', title: 'Verify the version sent by the supervisor', text: 'Your inbox lists assigned report versions and deadlines. Open a report outside this tour to record verified findings, request correction, or state which evidence is missing. An empty inbox means no report has been assigned—not that a case is verified.', next: 'Finish & explore' },
];

const PRODUCTION_STEPS: readonly FlowStep[] = [
  { page: 'production-review', selector: '[data-flow="production-heading"]', title: 'Start with your production scope', text: 'Review production evidence independently from equipment condition. A saved request is a fixed report version; a simulation preview is not a submitted verification request. This tour does not save a decision.', next: 'Read operating evidence' },
  { page: 'production-review', selector: '[data-flow="production-operating"]', title: 'Read the interruption in context', text: 'Compare equipment feed before, during, and after the sampled outage. Plant rate and equipment feed are separate measures. The reference baseline supports the shortfall estimate, not a claim about total plant loss.', next: 'Check the impact measures' },
  { page: 'production-review', selector: '[data-flow="production-metrics"]', title: 'Keep sampled and reported impact separate', text: 'Read sampled downtime and calculated feed shortfall with their baseline. Source-reported RCA downtime and loss retain their own definitions. A count of hourly observations is not an exact event duration.', next: 'Review the report basis' },
  { page: 'production-review', expand: true, selector: '[data-flow="production-report"]', title: 'Understand what you are verifying', text: 'Review the report response, version, calculation method, and known limitations. Verify whether its production interpretation agrees with operating records before approving the scope.', next: 'Inspect original observations' },
  { page: 'production-review', expand: true, selector: '[data-flow="production-records"]', title: 'Check timestamped supporting records', text: 'Use the observation table to inspect feed, plant rate, and run status with their original timestamps. Missing observations remain unavailable rather than being silently filled in.', next: 'Review the decision controls' },
  { page: 'production-review', selector: '[data-flow="production-decision"]', title: 'Record a justified scope outcome', text: 'Outside Flow, choose verified, correction required, or unable to verify. Give the operational context and required evidence; verification requires the displayed attestation. This spotlight does not select an outcome or send your response.', next: 'Understand the handoff boundary' },
  { page: 'production-review', selector: '[data-flow="production-boundary"]', title: 'Return evidence, not management approval', text: 'Your production decision goes back to the supervisor. Equipment checks, case-packet consolidation, and any required GM authorization remain separate. A production verification does not assign CA/PA work.', next: 'Finish & explore' },
];

const GM_STEPS: readonly FlowStep[] = [
  { page: 'gm-review', panel: 'heading', selector: '[data-flow="gm-heading"]', title: 'Start with management case review', text: 'IRIS brings verified scope evidence, probable RCA, and proposed follow-up into management review. Your decision authorizes the approach or requests revision; this tour does not approve a case.', next: 'Review the inbox' },
  { page: 'gm-review', panel: 'inbox', selector: '[data-flow="gm-inbox"]', title: 'Review submitted cases, not raw alerts', text: 'The inbox contains case packets sent for your review. If no packet is submitted, Flow explains the required review using clearly labelled reference guidance. It will not create a packet or invent an approval.', next: 'Review equipment verification' },
  { page: 'gm-review', panel: 'report', selector: '[data-flow="gm-equipment"]', title: 'Check the equipment verification', text: 'Review who verified the equipment scope, which report version they reviewed, and any condition-evidence limitations. Scope verification checks records; it is not automatically a confirmed root cause.', next: 'Review production impact' },
  { page: 'gm-review', panel: 'report', selector: '[data-flow="gm-production"]', title: 'Review qualified production impact', text: 'Check production verification, the operating window, and the calculation basis. Keep calculated feed shortfall separate from source-reported downtime and loss before using impact to justify the response.', next: 'Review the RCA basis' },
  { page: 'gm-review', panel: 'report', selector: '[data-flow="gm-rca"]', title: 'Separate probable causes from findings', text: 'Review the RCA indication and the evidence still needed. Model explanation, historical similarity, and reported inspection findings have different evidentiary roles. Record conditions or request revision where support is insufficient.', next: 'Review proposed actions' },
  { page: 'gm-review', panel: 'report', selector: '[data-flow="gm-actions"]', title: 'Check the proposed response', text: 'Review how each corrective or preventive action addresses the supported mechanism and how effectiveness will be checked. Proposed owner roles are not execution assignments; assignment remains a separate supervisor step.', next: 'Review your decision' },
  { page: 'gm-review', panel: 'report', selector: '[data-flow="gm-decision"]', title: 'Make the management decision explicit', text: 'Outside Flow, approve the proposed approach or return the report with specific changes. Record the rationale and conditions. A recorded decision remains attached to its report version; nothing is saved by this tour.', next: 'Understand the handoff' },
  { page: 'gm-review', panel: 'report', selector: '[data-flow="gm-handoff"]', title: 'Approval does not execute the work', text: 'After approval, the supervisor assigns qualified owners, deadlines, guidance, and evidence requirements. Assignees execute the work, then completion and effectiveness are reviewed. GM approval alone does not assign or close an action.', next: 'Finish & explore' },
];

export interface FlowDefinition { id: string; label: string; assetId: string; steps: readonly FlowStep[] }

export function flowForPerson(person: string): FlowDefinition | null {
  switch (person) {
    case 'demo-supervisor': return { id: 'ko-3201', label: 'KO-3201', assetId: 'asset-ko-3201', steps: FLOW_STEPS };
    case 'demo-equipment-ko': return { id: 'equipment-ko', label: 'Equipment · KO-3201', assetId: 'asset-ko-3201', steps: EQUIPMENT_STEPS };
    case 'demo-equipment-he': return { id: 'equipment-he', label: 'Equipment · HE-3301', assetId: 'asset-he-3301', steps: EQUIPMENT_STEPS };
    case 'demo-production-zcu': return { id: 'production', label: 'Production · KO-3201', assetId: 'asset-ko-3201', steps: PRODUCTION_STEPS };
    case 'demo-manager': return { id: 'gm', label: 'GM case review', assetId: 'asset-ko-3201', steps: GM_STEPS };
    default: return null;
  }
}

export function flowHash(person: string) {
  const flow = flowForPerson(person);
  if (!flow) throw new Error('No guided Flow is available for this role');
  return `${flow.steps[0].page}?${new URLSearchParams({ asset: flow.assetId, person, flow: flow.id, flowStep: '0' })}`;
}

export function cardPosition(box: { left: number; right: number; top: number; bottom: number }, width: number, height: number, cardWidth: number, cardHeight: number) {
  const left = box.right + cardWidth + 28 <= width ? box.right + 20 : box.left;
  const top = box.bottom + cardHeight + 28 <= height ? box.bottom + 20 : box.top - cardHeight - 20;
  return { left: Math.max(12, Math.min(left, width - cardWidth - 12)), top: Math.max(12, Math.min(top, height - cardHeight - 12)) };
}
