import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import ts from 'typescript';

const source = readFileSync(new URL('../src/lib/equipmentReview.ts', import.meta.url), 'utf8');
const js = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext } }).outputText;
const { canVerifyEquipment, orderedEquipmentRequests, preferredScopeReports, scopeReportLink } = await import(`data:text/javascript,${encodeURIComponent(js)}`);
const checks = ['DATA_VALIDITY', 'OPERATING_CONTEXT', 'ABNORMAL_BEHAVIOUR', 'SUPPORTING_EVIDENCE'].map((check) => ({ check, result: 'VERIFIED', finding: 'Compared with source', reference: 'shift:123' }));

test('equipment verification requires four unique checked areas and referenced findings', () => {
  assert.equal(canVerifyEquipment('APPROVED', checks, 'Reviewed', 'Steady operation', true), true);
  assert.equal(canVerifyEquipment('APPROVED', checks, 'Reviewed', 'Steady operation', false), false);
  assert.equal(canVerifyEquipment('APPROVED', checks.slice(1), 'Reviewed', 'Steady operation', true), false);
  assert.equal(canVerifyEquipment('APPROVED', [checks[0], ...checks.slice(0, 3)], 'Reviewed', 'Steady operation', true), false);
  assert.equal(canVerifyEquipment('APPROVED', checks.map((item) => ({ ...item, reference: '' })), 'Reviewed', 'Steady operation', true), false);
  assert.equal(canVerifyEquipment('APPROVED', checks, 'Reviewed', '', true), false);
});

test('correction and inability to verify require the corresponding evidence finding', () => {
  assert.equal(canVerifyEquipment('CHANGES_REQUESTED', checks, 'Reviewed', 'Checked context', false), false);
  assert.equal(canVerifyEquipment('UNABLE_TO_VALIDATE', checks, 'Reviewed', 'Checked context', false), false);
  const missing = checks.map((item, index) => index === 3 ? { ...item, result: 'MISSING', reference: null } : item);
  assert.equal(canVerifyEquipment('UNABLE_TO_VALIDATE', missing, 'Lab result unavailable', 'Checked context', false), true);
  assert.equal(canVerifyEquipment('APPROVED', missing, 'Reviewed', 'Checked context', true), false);
  const correction = checks.map((item, index) => index === 0 ? { ...item, result: 'ISSUE' } : item);
  assert.equal(canVerifyEquipment('CHANGES_REQUESTED', correction, 'Unit mismatch', 'Checked context', false), true);
});

test('equipment inbox ranks pending requests before responses and severity before deadline', () => {
  const report = (status, rank, due) => ({ status, evidence: { alert: { highest_severity_rank: rank } }, due_at: due });
  const saved = report('APPROVED', 3, '2026-10-01');
  const high = report('SENT', 2, '2026-10-01');
  const critical = report('SENT', 3, '2026-10-02');
  assert.deepEqual(orderedEquipmentRequests([saved, high, critical]), [critical, high, saved]);
  const link = scopeReportLink({ scope: 'EQUIPMENT', report_id: 'equipment-123', asset: { asset_id: 'asset-ko-3201' } }, 'demo-equipment-ko');
  assert.match(link, /^#equipment-review\?/);
  assert.match(link, /person=demo-equipment-ko/);
});

test('case binding prefers verified reports over newer drafts', () => {
  const draft = { status: 'DRAFT' };
  const verified = { status: 'APPROVED' };
  const sent = { status: 'SENT' };
  assert.deepEqual(preferredScopeReports([draft, verified, sent]), [verified, sent, draft]);
});
