import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import ts from 'typescript';

const source = readFileSync(new URL('../src/lib/productionReview.ts', import.meta.url), 'utf8');
const js = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext } }).outputText;
const { buildProductionReview, canRecordProductionDecision, verificationReport } = await import(`data:text/javascript,${encodeURIComponent(js)}`);

test('production review uses supplied impact without inventing missing observations', () => {
  const impact = { window_end: '2026-04-30T15:00:00+07:00', offline_hours: 32, estimated_shortfall_tonnes: 1762.803, baseline: { expected_feed_tph: 55.1075 } };
  const overview = { asset: { tag: 'KO-3201', plant_id: 'ZCU' }, production_impact: impact };
  const points = [{ timestamp: impact.window_end, feed_rate_tph: null, plant_rate_tph: null }];
  const report = buildProductionReview(overview, points);
  assert.equal(report.impact, impact);
  assert.equal(report.points[0].feed_rate_tph, null);
  assert.match(report.statement, /1762\.8 tonnes/);
  assert.match(report.statement, /55\.11 t\/h/);
  assert.equal(report.scope, 'ZCU / Production');
  assert.equal(buildProductionReview({ ...overview, production_impact: null }, []), null);
});

test('approval requires a note and attestation; corrections and missing evidence require a reason', () => {
  assert.equal(canRecordProductionDecision('APPROVED', '', true), false);
  assert.equal(canRecordProductionDecision('APPROVED', 'Reviewed source records', false), false);
  assert.equal(canRecordProductionDecision('APPROVED', 'Reviewed source records', true), true);
  assert.equal(canRecordProductionDecision('CHANGES_REQUESTED', '   ', false), false);
  assert.equal(canRecordProductionDecision('CHANGES_REQUESTED', 'Wrong baseline window', false), true);
  assert.equal(canRecordProductionDecision('UNABLE_TO_VALIDATE', 'Run-status records missing', false), true);
});

test('sent report retains its saved snapshot, recipient, version and instruction', () => {
  const impact = { estimated_shortfall_tonnes: 216, offline_hours: 13, baseline: { expected_feed_tph: 18 } };
  const saved = { report_id: 'production-abc', version: '01', status: 'SENT', asset: { plant_id: 'ZCU' }, supervisor: 'Supervisor', recipient_name: 'ZCU production operator', created_at: '2026-10-01T00:00:00Z', due_at: '2026-10-02T00:00:00Z', impact, points: [], note: 'Check against shift records' };
  const report = verificationReport(saved);
  assert.equal(report.impact, impact);
  assert.equal(report.points, saved.points);
  assert.equal(report.version, '01');
  assert.equal(report.response, saved.note);
  assert.equal(report.delivery.recipient, saved.recipient_name);
  assert.equal(report.delivery.status, 'SENT');
});
