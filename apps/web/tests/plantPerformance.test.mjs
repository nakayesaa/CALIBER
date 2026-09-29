import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import ts from 'typescript';

async function load(name) {
  const source = readFileSync(new URL(`../src/lib/${name}.ts`, import.meta.url), 'utf8');
  const js = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext } }).outputText;
  return import(`data:text/javascript,${encodeURIComponent(js)}`);
}
const { performanceWindow, resourcePerformance } = await load('plantPerformance');
const { plantScenarios } = await load('plantOverviewDemoData');
const observed = { points: Array.from({ length: 30 }, (_, index) => ({ date: `2026-04-${String(index + 1).padStart(2, '0')}`, average_rate_tph: 50, sample_count: 24 })) };

test('shared windows preserve cadence, units and observed coverage without fallback', () => {
  for (const length of [1, 3, 7]) {
    for (const plant of plantScenarios) {
      const window = performanceWindow(plant, observed, length);
      assert.equal(window.energy.length, length * 24);
      assert.equal(window.emissions.length, length * 24);
      assert.equal(window.downtime.length, length);
      assert.equal(window.production.length, plant.id === 'ZCU' ? length : length * 24);
      assert.equal(window.productionReadings, length * 24);
      assert.equal(window.complete, true);
      if (plant.id === 'NUP') assert.match(window.productionUnit, /equiv/);
    }
  }
  const zcu = plantScenarios.find((plant) => plant.id === 'ZCU');
  assert.equal(performanceWindow(zcu, null, 7).production.length, 0);
  assert.equal(performanceWindow(zcu, { points: observed.points.slice(0, 29) }, 7).complete, false);
  assert.equal(performanceWindow(zcu, observed, 1).downtime[0], 15);
});

test('resource totals and load-based forecast respect cadence and missing source data', () => {
  const zcu = plantScenarios.find((plant) => plant.id === 'ZCU');
  const metrics = resourcePerformance(zcu, observed, 1);
  assert.ok(Math.abs(metrics.energyTotal - 50 * 4.95 * 24) < 0.0001);
  assert.ok(Math.abs(metrics.emissionsTotal - 50 * 0.38 * 24) < 0.0001);
  assert.equal(metrics.forecast, 50 * 4.2 * 24);
  assert.equal(metrics.forecastLow, metrics.forecast * 0.9);
  const unavailable = resourcePerformance(zcu, null, 1);
  assert.equal(unavailable.energyTotal, undefined);
  assert.equal(unavailable.forecast, undefined);
  const incomplete = resourcePerformance(zcu, { points: observed.points.slice(0, 29) }, 7);
  assert.equal(incomplete.energyTotal, undefined);
});
