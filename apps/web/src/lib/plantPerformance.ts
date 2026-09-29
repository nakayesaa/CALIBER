import type { PlantRateSeries } from './apiContracts';
import type { OperatingIssue, PlantPerformance, FollowUpAction } from './plantOverviewDemoData';

export type OverviewDays = 1 | 3 | 7;
export const snapshotDate = '2026-04-30';
export const mean = (values: readonly number[]) => values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : undefined;
export const deviation = (value: number | undefined, reference: number | undefined) => value !== undefined && reference !== undefined && reference > 0 ? (value - reference) / reference * 100 : undefined;

export function operatingBrief(plant: PlantPerformance, metrics: ReturnType<typeof resourcePerformance>, downtime: readonly number[], issues: readonly OperatingIssue[], actions: readonly FollowUpAction[]) {
  const change = metrics.productionDeviation;
  const hours = downtime.reduce((sum, value) => sum + value, 0);
  const rateText = change === undefined ? 'Production comparison is unavailable.' : Math.abs(change) < 0.1 ? 'Production is in line with its reference.' : `Production is ${Math.abs(change).toFixed(1)}% ${change < 0 ? 'below' : 'above'} reference.`;
  const energyText = metrics.energyDeviation === undefined ? '' : ` Specific energy is ${Math.abs(metrics.energyDeviation).toFixed(1)}% ${metrics.energyDeviation < 0 ? 'below' : 'above'} its scenario reference.`;
  const overdue = actions.filter((action) => action.overdue && action.status !== 'Verified').length;
  const next = issues[0];
  return {
    title: change === undefined ? `${plant.id}: production data needs attention.` : next || hours ? `${plant.id}: check performance and equipment recovery.` : `${plant.id}: continue performance monitoring.`,
    summary: `${rateText}${energyText} ${hours} equipment-hours of downtime in this window; ${overdue} overdue ${overdue === 1 ? 'action' : 'actions'}. These trends indicate exposure, not a confirmed causal link.`,
    next: next ? `${next.severity} priority · ${next.owner}: ${next.nextStep}` : 'Next: monitor trends at comparable load; no current issue assigned.',
  };
}

export function resourcePerformance(plant: PlantPerformance, observed: PlantRateSeries | null, length: OverviewDays, plannedRate?: number) {
  const window = performanceWindow(plant, observed, length);
  const referencePoints = observed?.points.filter((point) => point.date >= '2026-04-01' && point.date <= '2026-04-07') ?? [];
  const referenceRate = plant.id === 'ZCU' ? referencePoints.length === 7 && referencePoints.every((point) => point.sample_count === 24) ? mean(referencePoints.map((point) => point.average_rate_tph)) : undefined : plant.production[0];
  const currentRate = window.complete ? plant.id === 'ZCU' ? window.production.at(-1) : mean(window.production.slice(-24)) : undefined;
  // Mixed-cadence totals use daily means; incomplete source coverage never gets filled.
  const dailyRate = plant.id === 'ZCU' ? window.production : Array.from({ length }, (_, index) => mean(window.production.slice(index * 24, (index + 1) * 24))!);
  const totals = (metric: 'energy' | 'emissions') => window.complete ? dailyRate.reduce((sum, rate, index) => sum + rate * mean(window[metric].slice(index * 24, (index + 1) * 24))! * 24, 0) : undefined;
  const assumedRate = plannedRate ?? currentRate;
  const forecast = assumedRate !== undefined && Number.isFinite(assumedRate) && assumedRate >= 0 && window.complete ? assumedRate * plant.energy[0] * 24 : undefined;
  return {
    referenceRate, currentRate, productionDeviation: deviation(currentRate, referenceRate),
    energyTotal: totals('energy'), emissionsTotal: totals('emissions'),
    energyReference: plant.energy[0], emissionsReference: plant.emissions[0],
    energyDeviation: deviation(mean(window.energy.slice(-24)), plant.energy[0]),
    emissionsDeviation: deviation(mean(window.emissions.slice(-24)), plant.emissions[0]),
    assumedRate, forecast, forecastLow: forecast === undefined ? undefined : forecast * 0.9, forecastHigh: forecast === undefined ? undefined : forecast * 1.1,
  };
}

// Daily source readings stay daily. Scenario trends retain their hourly cadence.
export function performanceWindow(plant: PlantPerformance, observed: PlantRateSeries | null, length: OverviewDays) {
  const start = `2026-04-${String(31 - length).padStart(2, '0')}`;
  const points = observed?.points.filter((point) => point.date >= start && point.date <= snapshotDate) ?? [];
  const production = plant.id === 'ZCU' ? points.map((point) => point.average_rate_tph) : plant.trends.production.slice(-length * 24);
  const productionLabels = plant.id === 'ZCU' ? points.map((point) => point.date) : hourlyLabels(length);
  return {
    start, end: snapshotDate, production, productionLabels,
    productionUnit: plant.id === 'NUP' ? 't/h (equiv.)' : 't/h',
    productionCadence: plant.id === 'ZCU' ? 'daily' : 'hourly',
    productionReadings: plant.id === 'ZCU' ? points.reduce((sum, point) => sum + point.sample_count, 0) : production.length,
    days: Array.from({ length }, (_, index) => `${31 - length + index} Apr`),
    labels: hourlyLabels(length),
    energy: plant.trends.energy.slice(-length * 24),
    emissions: plant.trends.emissions.slice(-length * 24),
    attention: plant.attention.slice(-length), downtime: plant.downtime.slice(-length),
    complete: production.length === (plant.id === 'ZCU' ? length : length * 24) && (plant.id !== 'ZCU' || points.every((point) => point.sample_count === 24)),
  };
}

function hourlyLabels(length: OverviewDays) {
  return Array.from({ length: length * 24 }, (_, index) => `${31 - length + Math.floor(index / 24)} Apr · ${String(index % 24).padStart(2, '0')}:00`);
}

export interface MetricSource {
  sourceKey?: string;
  fields: Record<string, string>;
}

export function metricSources(plant: PlantPerformance, window: ReturnType<typeof performanceWindow>, observed: PlantRateSeries | null, actionCount: number, plannedRate?: number): Record<'production' | 'energy' | 'emissions' | 'attention' | 'downtime' | 'actions' | 'forecast', MetricSource> {
  const period = `${window.start}–${window.end} · WIB`;
  const fixture = `plantOverviewDemoData.ts · ${plant.id} scenario`;
  const snapshot = 'Snapshot · 30 Apr 2026 · 23:00 WIB';
  const resourceBasis = 'Daily mean rate × daily mean intensity × 24 h; estimate, not metered total.';
  const productionSource = plant.id === 'ZCU' ? observed?.source_reference ?? 'Observed production unavailable' : fixture;
  const intensitySource = `Intensity: ${fixture}. Total estimate also uses production: ${productionSource}.`;
  const forecastSource = `Reference intensity: ${fixture}. Assumed rate: ${plannedRate === undefined ? `latest daily mean from ${productionSource}` : `operator input ${plannedRate} ${window.productionUnit}`}.`;
  return {
    production: { sourceKey: plant.id === 'ZCU' ? observed?.source_key : undefined, fields: {
      Source: plant.id === 'ZCU' ? observed?.source_reference ?? 'Observed workbook unavailable' : fixture,
      Unit: window.productionUnit, Period: period, Cadence: `${window.productionCadence} display${plant.id === 'ZCU' ? ' from hourly observations' : ' scenario'}`,
      Freshness: plant.id === 'ZCU' ? observed?.points.at(-1) ? `${observed.points.at(-1)!.date} · latest source daily mean` : 'Unavailable' : snapshot,
      Coverage: `${window.productionReadings} hourly readings · ${window.complete ? 'complete' : 'incomplete'} window`,
      Formula: plant.id === 'ZCU' ? 'Mean of hourly PLANT_RATE, including offline hours.' : 'Headline and deviation: latest daily mean. Chart: scenario hourly samples.',
      Reference: plant.id === 'ZCU' ? '1–7 Apr observed daily mean; screening comparison, not a production target.' : '24 Apr scenario daily mean.',
    } },
    energy: { fields: { Source: intensitySource, Unit: plant.id === 'NUP' ? 'GJ/t equiv. · GJ total' : 'GJ/t · GJ total', Period: period, Freshness: snapshot, Cadence: 'Hourly scenario intensity', Coverage: `${window.energy.length} intensity points; production coverage ${window.complete ? 'complete' : 'incomplete'}`, Formula: resourceBasis, Reference: '24 Apr scenario intensity at comparable load.' } },
    emissions: { fields: { Source: intensitySource, Unit: plant.id === 'NUP' ? 'tCO₂e/t equiv. · tCO₂e total' : 'tCO₂e/t · tCO₂e total', Period: period, Freshness: snapshot, Cadence: 'Hourly scenario intensity', Coverage: `${window.emissions.length} intensity points; production coverage ${window.complete ? 'complete' : 'incomplete'}`, Formula: resourceBasis, Reference: '24 Apr scenario intensity; no compliance assessment.' } },
    attention: { fields: { Source: fixture, Unit: 'Monitored assets', Period: period, Cadence: 'Daily snapshot', Coverage: `${plant.assets} monitored assets, not the full plant inventory`, Formula: 'Count of scenario attention flags; one asset counted once per day.' } },
    downtime: { fields: { Source: `${fixture}${plant.id === 'ZCU' ? ' · KO-3201 RCA 32-hour anchor event' : ''}`, Unit: 'Equipment-hours', Period: period, Cadence: 'Daily allocation', Coverage: `${window.downtime.length} daily allocations`, Formula: 'Sum of downtime across monitored equipment. Overlapping equipment outages are not merged into plant outage hours.' } },
    actions: { fields: { Source: `${fixture} · issue-linked handoff register`, Unit: 'Assignments by status', Period: snapshot, Cadence: 'Status snapshot, independent of chart window', Coverage: `${actionCount} handoff assignments`, Formula: 'Count by handoff status. Execution, effectiveness approval and formal closure belong to the linked CA/PA plan.' } },
    forecast: { fields: { Source: forecastSource, Unit: 'GJ for next 24 hours', Period: '1 May 2026 · 00:00–23:00 WIB', Cadence: 'Constant-load planning scenario', Coverage: 'Requires a complete production window; assumed load is editable.', Formula: 'Assumed rate × 24 Apr reference energy intensity × 24 h; ±10% planning sensitivity, not a confidence interval.' } },
  };
}
