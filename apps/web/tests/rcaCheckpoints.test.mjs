import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import ts from 'typescript';

const source = readFileSync(new URL('../src/lib/rcaCheckpoints.ts', import.meta.url), 'utf8');
const javascript = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext } }).outputText;
const { rcaCheckpoints } = await import(`data:text/javascript,${encodeURIComponent(javascript)}`);

test('RCA checkpoints group records from the same event time', () => {
  const occurredAt = '2026-04-29T18:00:00+07:00';
  const events = [
    { occurred_at: occurredAt, kind: 'INSPECTION', title: 'Bearing distress reference' },
    { occurred_at: occurredAt, kind: 'INSPECTION', title: 'Cooler leak reference' },
  ];
  const checkpoints = rcaCheckpoints('2026-02-23T19:00:00+07:00', events);

  assert.equal(checkpoints.length, 2);
  assert.deepEqual(checkpoints.map(({ label }) => label), ['Warning', 'Inspection']);
  assert.equal(checkpoints[1].detail, 'Bearing distress');
});
