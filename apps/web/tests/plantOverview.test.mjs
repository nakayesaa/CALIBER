import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import ts from 'typescript';

const source = readFileSync(new URL('../src/lib/plantOverviewDemoData.ts', import.meta.url), 'utf8');
const javascript = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext } }).outputText;
const { selectPlantOverview, selectActionReport, plantScenarios, days, trendLabels, performanceInsight } = await import(`data:text/javascript,${encodeURIComponent(javascript)}`);

test('each action has a specific handoff report joined to its own issue', () => {
  const { actions } = selectPlantOverview('ZCU');
  const objectives = new Set();
  for (const action of actions) {
    const report = selectActionReport('ZCU', action.id);
    assert.equal(report.issue.id, action.issueId);
    assert.equal(report.action.owner, action.owner);
    assert.ok(report.action.report.steps.length > 0);
    assert.ok(report.action.report.deliverables.length > 0);
    assert.ok(report.action.report.verification.length > 0);
    objectives.add(report.action.report.objective);
  }
  assert.equal(objectives.size, actions.length);
  assert.equal(selectActionReport('ARP', actions[0].id), undefined);
  assert.equal(selectActionReport('ZCU', 'missing'), undefined);
});

test('hourly demo trends retain daily means and unique timestamps', () => {
  assert.equal(trendLabels.length, 168);
  assert.equal(new Set(trendLabels).size, 168);
  for (const plant of plantScenarios) {
    for (const metric of ['production', 'energy', 'emissions']) {
      assert.equal(plant.trends[metric].length, 168);
      for (const index of days.keys()) {
        const mean = plant.trends[metric].slice(index * 24, (index + 1) * 24).reduce((sum, value) => sum + value, 0) / 24;
        assert.ok(Math.abs(mean - plant[metric][index]) < 0.00001);
      }
    }
  }
});

test('emissions scenario stays positive and differs from energy while retaining disruption and recovery', () => {
  const plant = plantScenarios.find(plant => plant.id === 'ZCU');
  assert.ok(plant.trends.emissions.every(value => value > 0));
  assert.ok(plant.energy[4] > plant.energy[3]);
  assert.ok(plant.emissions[4] < plant.emissions[3]);
  assert.ok(plant.emissions[5] > plant.emissions[4]);
  assert.ok(plant.emissions[6] < plant.emissions[5]);
  assert.notEqual(plant.trends.energy[0] - plant.energy[0], plant.trends.emissions[0] - plant.emissions[0]);
});

test('performance insight states direction without inventing a root cause', () => {
  assert.match(performanceInsight('ZCU', 25, 50), /50.0% below/);
  assert.match(performanceInsight('ARP', 55, 50), /10.0% above/);
  assert.match(performanceInsight('ARP', 50, 50), /in line/);
  assert.match(performanceInsight('ZCU', undefined, 50), /unavailable/i);
});

test('source coverage follows plant selection and observed data availability', () => {
  for (const plant of ['ARP', 'NUP', 'OPP']) {
    const { sources } = selectPlantOverview(plant, 'ready');
    const production = sources.find((source) => source.name === 'Production');
    const equipment = sources.find((source) => source.name === 'Equipment');
    assert.ok(!production.basis.includes('ZCU'));
    assert.match(production.freshness, /Demo snapshot/);
    assert.match(equipment.basis, /1 monitored asset\./);
  }
  const unavailable = selectPlantOverview('ZCU').sources.find((source) => source.name === 'Production');
  assert.match(unavailable.basis, /unavailable/);
  assert.ok(!unavailable.freshness.includes('through'));
  const observed = selectPlantOverview('ZCU', 'ready').sources.find((source) => source.name === 'Production');
  assert.match(observed.basis, /720 hourly readings/);
  assert.match(observed.freshness, /through 30 Apr/);
});

test('plant selection scopes issues, actions and daily equipment counts together', () => {
  const overview = selectPlantOverview('ZCU');
  assert.equal(overview.plants.length, 1);
  assert.ok(overview.issues.every((issue) => issue.plant === 'ZCU'));
  assert.ok(overview.actions.every((action) => overview.issues.some((issue) => issue.id === action.issueId)));
  assert.ok(overview.attention.every((count) => count <= overview.assetCount));
  assert.equal(overview.downtime.reduce((sum, hours) => sum + hours, 0), 32);
});

test('one selected plant ranks severity first and keeps daily counts scoped', () => {
  const overview = selectPlantOverview('ZCU');
  assert.equal(overview.assetCount, 2);
  assert.equal(overview.issues[0].severity, 'High');
  assert.ok(overview.issues.every((issue) => issue.priorityReason.length > 0));
  assert.equal(overview.plants.length, 1);
  assert.ok(!('production' in overview));
  for (const plant of plantScenarios) {
    for (const key of ['production', 'attention', 'downtime', 'energy', 'emissions']) {
      assert.equal(plant[key].length, days.length);
    }
    assert.ok(plant.attention.every((count) => count >= 0 && count <= plant.assets));
  }
  for (const index of days.keys()) {
    assert.equal(overview.attention[index], plantScenarios.find((plant) => plant.id === 'ZCU').attention[index]);
  }
});
