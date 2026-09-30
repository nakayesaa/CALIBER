import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import ts from 'typescript';

function moduleUrl(name) {
  const source = readFileSync(new URL(`../src/lib/${name}.ts`, import.meta.url), 'utf8');
  const js = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext } }).outputText;
  return `data:text/javascript,${encodeURIComponent(js)}`;
}
const signalsUrl = moduleUrl('conditionSignals');
const formatUrl = moduleUrl('format');
const { conditionSignalsFor, operatingSignalsFor } = await import(signalsUrl);
const { formatSignal } = await import(formatUrl);
const eventSource = readFileSync(new URL('../src/lib/eventProgression.ts', import.meta.url), 'utf8');
const eventJs = ts.transpileModule(eventSource, { compilerOptions: { module: ts.ModuleKind.ESNext } }).outputText
  .replace("'./format'", JSON.stringify(formatUrl)).replace("'./conditionSignals'", JSON.stringify(signalsUrl));
const { buildEventMilestones } = await import(`data:text/javascript,${encodeURIComponent(eventJs)}`);

test('HE uses exchanger conditions and only supported operating signals', () => {
  assert.deepEqual(conditionSignalsFor('asset-he-3301').map(({ field }) => field), ['tube_dp', 'heat_duty', 'cold_outlet_temp', 'heavy_ends']);
  assert.deepEqual(operatingSignalsFor('asset-he-3301').map(({ field }) => field), ['feed_rate_tph', 'plant_rate_tph']);
  assert.equal(conditionSignalsFor('asset-ko-3201')[0].field, 'water_in_oil_ppm');
  assert.equal(formatSignal(NaN), 'Unavailable');
});

test('HE milestones retain alert dates without compressor conclusions', () => {
  const timestamp = '2026-03-11T23:00:00+07:00';
  const alert = { asset_id: 'asset-he-3301', first_signal_at: timestamp };
  const transitions = [{ timestamp, new_state: 'WARNING', reason: 'PERSISTENCE' }];
  const milestones = buildEventMilestones(alert, transitions, []);
  assert.equal(milestones[0].timestamp, timestamp);
  assert.match(milestones[0].title, /Exchanger/);
  assert.doesNotMatch(JSON.stringify(milestones), /oil|lubrication|bearing/i);
  assert.match(milestones[1].synthesis.detail, /working hypothesis/);
  const ko = buildEventMilestones({ ...alert, asset_id: 'asset-ko-3201' }, transitions, []);
  assert.match(ko[0].title, /Oil/);
});
