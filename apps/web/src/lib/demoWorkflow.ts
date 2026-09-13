import type { ActionPlan, RCARecord } from './api';

const ALERT_ID = 'alert-asset-ko-3201-0001';

export const demoRca: RCARecord = {
  rca_id: 'rca-ko-3201-demo-001',
  alert_id: ALERT_ID,
  status: 'APPROVED',
  requested_by: 'Reliability Engineer',
  model: 'caliber-rca-demo-v1',
  generation: {
    executive_summary: 'Water-in-oil was the earliest persistent condition driver, followed by reduced lube-oil pressure, rising bearing temperature, and radial vibration. The combined sequence is most consistent with moisture contamination weakening the lubricant film and accelerating bearing distress. Confirm the contamination source and bearing condition before restart.',
    hypotheses: [
      {
        hypothesis_id: 'hyp-lubrication-contamination',
        rank: 1,
        category: 'LUBRICATION_CONTAMINATION',
        title: 'Moisture ingress degraded the bearing oil film',
        mechanism: 'Water contamination reduced lubricant film strength and promoted bearing surface distress. Increasing friction then raised bearing temperature and radial vibration while effective oil pressure deteriorated.',
        confidence: 0.86,
        rationale: 'Water-in-oil opened the warning and remained the primary model driver. The later temperature, pressure, and vibration response forms a physically coherent degradation sequence. Historical compressor bearing incidents strengthen, but do not independently prove, this hypothesis.',
        supporting_evidence_ids: ['signal:water_in_oil', 'signal:lube_oil_pressure', 'signal:bearing_temperature', 'signal:radial_vibration', 'incident:incident-0213'],
        contradicting_evidence_ids: [],
        analogue_incident_ids: ['incident-0213', 'incident-0355'],
        missing_evidence: ['Karl Fischer moisture result', 'Oil particle count and wear debris analysis', 'Inspection of cooler and seal ingress paths'],
        disconfirming_condition: 'Reject if laboratory moisture is within specification and inspection finds no credible ingress path or lubrication distress.',
      },
      {
        hypothesis_id: 'hyp-bearing-degradation',
        rank: 2,
        category: 'BEARING_DEGRADATION',
        title: 'Existing bearing wear drove secondary oil deterioration',
        mechanism: 'Progressive bearing clearance or surface damage increased vibration and temperature, with oil condition degrading as a consequence rather than as the initiating cause.',
        confidence: 0.63,
        rationale: 'The asset shows the vibration and temperature pattern seen in prior compressor bearing failures. It ranks below contamination because water-in-oil appeared first and dominated the opening evidence.',
        supporting_evidence_ids: ['signal:bearing_temperature', 'signal:radial_vibration', 'incident:incident-0213'],
        contradicting_evidence_ids: ['sequence:water_in_oil_precedes_vibration'],
        analogue_incident_ids: ['incident-0213', 'incident-0355'],
        missing_evidence: ['Bearing clearance measurement', 'Vibration spectrum and phase analysis', 'Bearing surface inspection'],
        disconfirming_condition: 'Reject if clearance, spectrum, and surface inspection show no bearing defect.',
      },
      {
        hypothesis_id: 'hyp-instrumentation',
        rank: 3,
        category: 'INSTRUMENTATION_ISSUE',
        title: 'Common instrumentation bias created a false degradation pattern',
        mechanism: 'Sensor drift or a shared acquisition issue could elevate condition indicators without corresponding equipment degradation.',
        confidence: 0.22,
        rationale: 'Instrumentation must be excluded, but independent variables moved in a mechanically consistent sequence and the alert persisted for an extended window.',
        supporting_evidence_ids: [],
        contradicting_evidence_ids: ['multi_signal:four_independent_parameters', 'duration:persistent_alert'],
        analogue_incident_ids: [],
        missing_evidence: ['Portable vibration comparison', 'Pressure gauge cross-check', 'Temperature sensor loop verification'],
        disconfirming_condition: 'Reject if portable measurements agree with the installed sensors within calibration tolerance.',
      },
    ],
    investigation_steps: [
      {
        step_id: 'step-safe-isolation',
        priority: 'IMMEDIATE',
        instruction: 'Maintain KO-3201 in a safe isolated condition and preserve the as-found state before intrusive work.',
        rationale: 'Protects personnel and prevents loss of evidence needed to distinguish contamination from mechanical damage.',
        expected_evidence: 'Approved isolation record, operating log snapshot, and preserved oil sample.',
        owner_role: 'Shift Supervisor',
        safety_gate: true,
      },
      {
        step_id: 'step-oil-analysis',
        priority: 'IMMEDIATE',
        instruction: 'Run Karl Fischer moisture, particle count, viscosity, and wear-debris analysis on the preserved oil sample.',
        rationale: 'Directly tests the leading contamination mechanism and indicates whether bearing wear is already active.',
        expected_evidence: 'Laboratory certificate with moisture ppm, ISO cleanliness code, viscosity, and wear-metal profile.',
        owner_role: 'Lubrication Engineer',
        safety_gate: false,
      },
      {
        step_id: 'step-ingress-path',
        priority: 'HIGH',
        instruction: 'Pressure-test the oil cooler and inspect seals, breathers, reservoirs, and maintenance entry points for water ingress.',
        rationale: 'Finding the physical entry path is required before oil replacement can be an effective corrective action.',
        expected_evidence: 'Photographic inspection record and pass/fail result for every credible ingress path.',
        owner_role: 'Mechanical Maintenance Lead',
        safety_gate: true,
      },
      {
        step_id: 'step-bearing-condition',
        priority: 'HIGH',
        instruction: 'Inspect bearing surfaces and clearances, then compare vibration spectrum and phase against the healthy baseline.',
        rationale: 'Determines whether contamination caused damage that must be repaired before return to service.',
        expected_evidence: 'Bearing inspection report, clearance measurements, spectrum, and phase comparison.',
        owner_role: 'Rotating Equipment Engineer',
        safety_gate: true,
      },
    ],
    operating_guidance: 'Do not return KO-3201 to normal duty until the ingress path is controlled, oil cleanliness is within specification, bearing condition is accepted, and a controlled run confirms stable pressure, temperature, and vibration.',
  },
};

export const demoActionPlan: ActionPlan = {
  plan_id: 'plan-ko-3201-demo-001',
  rca_id: demoRca.rca_id,
  alert_id: ALERT_ID,
  selected_hypothesis_id: 'hyp-lubrication-contamination',
  selected_cause_category: 'LUBRICATION_CONTAMINATION',
  status: 'IN_PROGRESS',
  actions: [
    {
      action_id: 'action-containment-001',
      action_type: 'CONTAINMENT',
      title: 'Isolate the contaminated lubrication circuit',
      guidance: 'Keep the compressor isolated, preserve representative oil samples, drain affected oil, and quarantine replacement stock until cleanliness is verified.',
      owner_role: 'Shift Supervisor',
      priority: 'CRITICAL',
      due_date: '2026-04-29',
      status: 'CLOSED',
      completion_criteria: 'Isolation approved, samples logged with chain of custody, contaminated oil removed, and replacement oil certificate verified.',
      effectiveness_check: 'No contaminated oil is circulated during inspection or controlled restart preparation.',
    },
    {
      action_id: 'action-corrective-001',
      action_type: 'CORRECTIVE',
      title: 'Eliminate moisture ingress and restore bearing integrity',
      guidance: 'Repair the confirmed cooler, seal, or breather ingress path. Replace damaged bearing components where inspection exceeds acceptance limits, then flush and refill the system.',
      owner_role: 'Mechanical Maintenance Lead',
      priority: 'CRITICAL',
      due_date: '2026-05-03',
      status: 'IN_PROGRESS',
      completion_criteria: 'Ingress pressure test passes, bearing clearances meet specification, and oil moisture and cleanliness meet the approved limits.',
      effectiveness_check: 'During a 24-hour controlled run, lube-oil pressure remains stable and vibration and bearing temperature remain within baseline control bands.',
      affected_scope: 'KO-3201 lubrication circuit',
      execution_route: 'Corrective maintenance',
      change_control: 'MOC screening before execution',
    },
    {
      action_id: 'action-preventive-001',
      action_type: 'PREVENTIVE',
      title: 'Add early moisture controls to the lubrication program',
      guidance: 'Introduce weekly water-in-oil trending, cooler integrity checks after relevant maintenance, and an escalation rule that links moisture rise with pressure, temperature, and vibration.',
      owner_role: 'Reliability Engineer',
      priority: 'HIGH',
      due_date: '2026-05-20',
      status: 'APPROVED',
      completion_criteria: 'Monitoring task, alarm limit, owner, route frequency, and response procedure are active in the reliability workflow.',
      effectiveness_check: 'For 90 operating days, moisture stays below the alert limit with no recurring multi-signal degradation event.',
      affected_scope: 'Comparable critical compressors',
      execution_route: 'Reliability program update',
      change_control: 'Procedure and alarm review',
    },
  ],
};

export function rcaForAlert(alertId: string, liveRca: RCARecord | null): RCARecord | null {
  if (liveRca) return liveRca;
  return alertId === ALERT_ID ? demoRca : null;
}

export function actionsForAlert(alertId: string, livePlans: ActionPlan[], hasLiveRca = false): ActionPlan[] {
  if (livePlans.length) return livePlans;
  if (hasLiveRca) return [];
  return alertId === ALERT_ID ? [demoActionPlan] : [];
}
