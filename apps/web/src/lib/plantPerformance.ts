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
  const referenceRate = plant.id === 'ZCU' ? mean(observed?.points.filter((point) => point.date >= '2026-04-01' && point.date <= '2026-04-07').map((point) => point.average_rate_tph) ?? []) : plant.production[0];
  const currentRate = plant.id === 'ZCU' ? window.production.at(-1) : mean(window.production.slice(-24));
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
    complete: production.length === (plant.id === 'ZCU' ? length : length * 24),
  };
}

function hourlyLabels(length: OverviewDays) {
  return Array.from({ length: length * 24 }, (_, index) => `${31 - length + Math.floor(index / 24)} Apr · ${String(index % 24).padStart(2, '0')}:00`);
}
