// One aligned operating snapshot. Views consume this contract when an API replaces the fixture.
export const days = ['24 Apr', '25 Apr', '26 Apr', '27 Apr', '28 Apr', '29 Apr', '30 Apr'] as const;
export const trendLabels = days.flatMap((day) => Array.from({ length: 24 }, (_, hour) => `${day} · ${String(hour).padStart(2, '0')}:00`));

export type PlantCode = 'ARP' | 'ZCU' | 'NUP' | 'OPP';
export type PlantId = PlantCode;
export type Severity = 'High' | 'Warning' | 'Watch';

export interface PlantPerformance {
  id: PlantCode;
  assets: number;
  production: readonly number[];
  energy: readonly number[];
  emissions: readonly number[];
  attention: readonly number[];
  downtime: readonly number[];
  trends: Record<'production' | 'energy' | 'emissions', readonly number[]>;
}

export interface OperatingIssue {
  id: string;
  plant: PlantCode;
  tag: string;
  severity: Severity;
  title: string;
  impact: string;
  indication: string;
  evidence: string;
  nextStep: string;
  owner: string;
  investigationAvailable: boolean;
}

export interface FollowUpAction {
  id: string;
  issueId: string;
  title: string;
  owner: string;
  status: 'Open' | 'In progress' | 'Awaiting verification' | 'Verified';
  due: string;
  overdue: boolean;
  report: {
    objective: string;
    steps: readonly string[];
    deliverables: readonly string[];
    verification: string;
    sources: readonly string[];
    includeProduction: boolean;
  };
}

// Hourly variation keeps each daily mean unchanged, so charts and summaries agree.
function hourlyTrend(values: readonly number[], amplitude: number) {
  return values.flatMap((value, day) => Array.from({ length: 24 }, (_, hour) => value + amplitude * (Math.sin(hour * Math.PI / 12) + 0.35 * Math.sin(hour * Math.PI / 3 + day))));
}

export const plantScenarios: readonly PlantPerformance[] = ([
  { id: 'ARP', assets: 1, production: [81, 83, 82, 79, 80, 84, 83], energy: [3.1, 3.08, 3.09, 3.22, 3.18, 3.1, 3.06], emissions: [0.21, 0.21, 0.22, 0.23, 0.22, 0.21, 0.21], attention: [0, 0, 0, 1, 1, 0, 0], downtime: [0, 0, 0, 2, 0, 0, 0] },
  { id: 'ZCU', assets: 2, production: [56, 55, 54, 52, 49, 17, 21], energy: [4.2, 4.22, 4.3, 4.45, 4.7, 5.1, 4.95], emissions: [0.32, 0.32, 0.33, 0.34, 0.36, 0.39, 0.38], attention: [0, 0, 1, 1, 2, 2, 1], downtime: [0, 0, 0, 0, 0, 17, 15] },
  { id: 'NUP', assets: 1, production: [72, 73, 74, 73, 71, 72, 74], energy: [2.8, 2.79, 2.76, 2.8, 2.9, 2.88, 2.83], emissions: [0.19, 0.19, 0.18, 0.19, 0.2, 0.2, 0.19], attention: [0, 0, 0, 0, 1, 0, 0], downtime: [0, 0, 0, 0, 0, 0, 0] },
  { id: 'OPP', assets: 1, production: [96, 95, 94, 93, 95, 97, 96], energy: [3.4, 3.42, 3.48, 3.5, 3.43, 3.4, 3.39], emissions: [0.24, 0.24, 0.25, 0.25, 0.24, 0.24, 0.24], attention: [0, 0, 1, 1, 0, 0, 0], downtime: [0, 0, 1, 0, 0, 0, 0] },
] satisfies Omit<PlantPerformance, 'trends'>[]).map((plant) => ({ ...plant, trends: {
  production: hourlyTrend(plant.production, 0.7),
  energy: hourlyTrend(plant.energy, 0.025),
  emissions: hourlyTrend(plant.emissions, 0.002),
} }));

const operatingIssues: readonly OperatingIssue[] = [
  { id: 'ko-oil', plant: 'ZCU', tag: 'KO-3201', severity: 'High', title: 'Compressor recovery needs confirmation', impact: 'Plant rate remains below its earlier operating level after the compressor outage.', indication: 'Oil contamination is a probable contributor to bearing distress, pending confirmation.', evidence: 'Review water content, oil-pressure decline and inspection records together. A plant-rate decline alone does not establish the cause.', nextStep: 'Confirm oil condition and bearing inspection before closing the recovery action.', owner: 'ZCU Maintenance', investigationAvailable: true },
  { id: 'he-duty', plant: 'ZCU', tag: 'HE-3301', severity: 'Watch', title: 'Exchanger duty needs a trend review', impact: 'Reduced heat transfer could increase utility demand.', indication: 'Fouling is a candidate, not a confirmed diagnosis.', evidence: 'Compare inlet and outlet temperatures, flow and differential pressure at comparable load.', nextStep: 'Check duty against matched-load reference conditions.', owner: 'ZCU Process Engineering', investigationAvailable: false },
];

const followUpActions: readonly FollowUpAction[] = [
  { id: 'oil-review', issueId: 'ko-oil', title: 'Review oil sample and contamination path', owner: 'ZCU Maintenance', status: 'In progress', due: '30 Apr · 16:00', overdue: true, report: {
    objective: 'Determine whether oil contamination remains present and document the evidence for its likely entry path.',
    steps: ['Match the oil sample ID and collection time to the degradation and maintenance timeline.', 'Review water-content results alongside the lube-pressure trend and available cooler inspection records.', 'Record supported findings, alternative explanations and any further inspection required.'],
    deliverables: ['Oil sample result with sample ID and timestamp.', 'Contamination-path assessment linked to inspection evidence.'],
    verification: 'Maintenance reviewer confirms that each finding has a traceable result or inspection record. An unsupported entry path stays unconfirmed.',
    sources: ['KO-3201 water-content and lube-pressure monitoring records.', 'Oil laboratory results and cooler inspection records: required attachments, not supplied in this action snapshot.'], includeProduction: false,
  } },
  { id: 'recovery-check', issueId: 'ko-oil', title: 'Review production recovery after restart', owner: 'ZCU Production', status: 'Awaiting verification', due: '1 May · 10:00', overdue: false, report: {
    objective: 'Assess whether production has returned to a comparable operating level after the KO-3201 outage.',
    steps: ['Review the 29–30 Apr plant-rate trend and separate offline periods from running operation.', 'Compare running-period rates against a matched-load reference; use the 1–7 Apr daily mean only as screening context.', 'Record planned rate changes or other constraints before attributing a production gap to the compressor.'],
    deliverables: ['Production recovery assessment with selected dates, run-status evidence and reference basis.', 'List of remaining constraints and the next monitoring period.'],
    verification: 'Production owner confirms comparable operating conditions and a stable running-period trend. A daily mean that includes offline hours cannot by itself demonstrate failed recovery.',
    sources: ['production_data_ko_3201.xlsx · PLANT_RATE · observed daily means from the production API.', 'RUN_STATUS hourly records: retrieve for running-period verification.'], includeProduction: true,
  } },
  { id: 'bearing-check', issueId: 'ko-oil', title: 'Complete bearing inspection record', owner: 'ZCU Reliability', status: 'Verified', due: '30 Apr · 14:00', overdue: false, report: {
    objective: 'Document bearing condition and check whether inspection findings support the working lubrication-related explanation.',
    steps: ['Identify the inspected bearing, inspection date and work-order reference.', 'Attach condition photographs and measured findings; distinguish observations from interpretation.', 'Compare findings with the recorded vibration, bearing-temperature and lubrication trends.'],
    deliverables: ['Bearing inspection record and photographs.', 'Reliability assessment linking findings to the investigation.'],
    verification: 'Reliability reviewer checks inspection completeness and consistency with monitoring evidence. The scenario register marks this action verified; the inspection attachments still need to accompany the issued report.',
    sources: ['KO-3201 vibration and bearing-temperature monitoring records.', 'Bearing inspection / work-order attachments: not included in this action snapshot.'], includeProduction: false,
  } },
  { id: 'duty-review', issueId: 'he-duty', title: 'Establish matched-load exchanger reference', owner: 'ZCU Process Engineering', status: 'Open', due: '1 May · 10:00', overdue: false, report: {
    objective: 'Establish whether HE-3301 duty has deviated after accounting for flow and inlet operating conditions.',
    steps: ['Select comparable periods with documented flow and inlet conditions.', 'Review inlet / outlet temperatures and differential pressure, then calculate duty only when the required inputs are available.', 'Compare the matched-load result and record whether fouling remains a supported candidate.'],
    deliverables: ['Matched-load comparison with units, calculation basis and selected periods.', 'Duty assessment and recommendation for further checks.'],
    verification: 'Process Engineering confirms comparable conditions and complete calculation inputs. Missing flow or temperature records prevent a quantitative duty conclusion.',
    sources: ['HE-3301 temperature, flow and differential-pressure records: required for the comparison.', 'Scenario issue register: exchanger duty review; no measured duty dataset attached.'], includeProduction: false,
  } },
];

const overviewSources = [
  { name: 'Production', system: 'Hourly production workbook', metric: 'Plant rate · t/h', basis: 'ZCU: observed API, 720 readings. Other plants: scenario fixture.', freshness: 'ZCU through 30 Apr · 23:00' },
  { name: 'Energy', system: 'Utility / energy dashboard', metric: 'Specific energy · GJ/t', basis: 'Scenario: utility energy divided by production for the same period.', freshness: 'Demo snapshot · 30 Apr · 23:00' },
  { name: 'Emissions', system: 'HSE / emissions dashboard', metric: 'Emissions intensity · tCO₂e/t', basis: 'Scenario: assigned emissions divided by production; not a compliance reading.', freshness: 'Demo snapshot · 30 Apr · 23:00' },
  { name: 'Equipment', system: 'Condition monitoring & downtime log', metric: 'Attention count · equipment-hours', basis: 'Scenario across 5 monitored assets. ZCU downtime is anchored to the 32-hour equipment event.', freshness: 'Demo snapshot · 30 Apr · 23:00' },
  { name: 'Follow-up', system: 'RCA / maintenance action register', metric: 'Owner · status · due date', basis: 'Scenario issue and action records joined by issue ID.', freshness: 'Demo snapshot · 30 Apr · 23:00' },
] as const;

const severityOrder: Record<Severity, number> = { High: 0, Warning: 1, Watch: 2 };

export function performanceInsight(plant: PlantId, current: number | undefined, reference: number | undefined) {
  if (current === undefined || reference === undefined || reference <= 0) return `${plant} production comparison is unavailable until the rate data loads.`;
  const change = (current - reference) / reference * 100;
  return `${plant} daily mean production is ${Math.abs(change) < 0.1 ? 'in line with' : `${Math.abs(change).toFixed(1)}% ${change < 0 ? 'below' : 'above'}`} its reference (${current.toFixed(2)} vs ${reference.toFixed(2)} t/h).`;
}

export function selectPlantOverview(plantId: PlantId, productionStatus: 'ready' | 'loading' | 'unavailable' = 'unavailable') {
  const plants = plantScenarios.filter((plant) => plant.id === plantId);
  const issues = operatingIssues.filter((issue) => issue.plant === plantId)
    .sort((left, right) => severityOrder[left.severity] - severityOrder[right.severity]);
  const issueIds = new Set(issues.map((issue) => issue.id));
  const assetCount = plants.reduce((sum, plant) => sum + plant.assets, 0);
  const includesZcu = plants.some((plant) => plant.id === 'ZCU');
  const sources = overviewSources.map((source) => {
    if (source.name === 'Production') {
      const observedBasis = productionStatus === 'ready' ? 'ZCU: observed API, 720 hourly readings.' : `ZCU observed API: ${productionStatus}. No scenario fallback.`;
      return { ...source,
        basis: includesZcu ? observedBasis : `${plantId}: aligned scenario production fixture.`,
        freshness: includesZcu ? productionStatus === 'ready' ? 'ZCU through 30 Apr · 23:00' : 'ZCU freshness unavailable until data loads' : 'Demo snapshot · 30 Apr · 23:00',
      };
    }
    if (source.name === 'Equipment') {
      return { ...source, basis: `Scenario across ${assetCount} monitored ${assetCount === 1 ? 'asset' : 'assets'}.${includesZcu ? ' ZCU downtime is anchored to the 32-hour equipment event.' : ''}` };
    }
    return source;
  });
  return {
    plants,
    issues,
    actions: followUpActions.filter((action) => issueIds.has(action.issueId)),
    assetCount,
    sources,
    attention: days.map((_, index) => plants.reduce((sum, plant) => sum + plant.attention[index], 0)),
    downtime: days.map((_, index) => plants.reduce((sum, plant) => sum + plant.downtime[index], 0)),
  };
}

export function selectActionReport(plantId: PlantId, actionId: string) {
  const { actions, issues } = selectPlantOverview(plantId);
  const action = actions.find((item) => item.id === actionId);
  const issue = issues.find((item) => item.id === action?.issueId);
  return action && issue ? { action, issue } : undefined;
}
