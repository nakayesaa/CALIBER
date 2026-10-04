import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import ts from 'typescript';

const source = readFileSync(new URL('../src/lib/gmReview.ts', import.meta.url), 'utf8');
const js = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext } }).outputText;
const { gmActionRows } = await import(`data:text/javascript,${encodeURIComponent(js)}`);

test('GM execution joins fresh tasks to the approved proposal without reusing historical progress', () => {
  const report = { report_id: 'gm-one', action_plans: [{ actions: [
    { action_id: 'containment', action_type: 'CONTAINMENT', status: 'CLOSED' },
    { action_id: 'corrective', action_type: 'CORRECTIVE', status: 'IN_PROGRESS' },
    { action_id: 'preventive', action_type: 'PREVENTIVE', status: 'APPROVED' },
  ] }] };
  const initial = gmActionRows(report, []);
  assert.deepEqual(initial.map(row => row.source.action_id), ['corrective', 'preventive']);
  assert(initial.every(row => row.action == null));
  const task = { action_id: 'fresh-task', source_action_id: 'corrective', status: 'APPROVED' };
  const rows = gmActionRows(report, [{ gm_report_id: 'gm-one', actions: [task] }, { gm_report_id: 'gm-other', actions: [{ source_action_id: 'preventive' }] }]);
  assert.equal(rows[0].action, task);
  assert.equal(rows[1].action, null);
});
