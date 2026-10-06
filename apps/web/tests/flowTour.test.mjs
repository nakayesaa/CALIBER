import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import ts from 'typescript';

test('KO-3201 Flow follows monitoring, prioritized alert, then investigation without writes', async () => {
  const source = readFileSync(new URL('../src/lib/flowTour.ts', import.meta.url), 'utf8');
  const js = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext } }).outputText;
  const { FLOW_STEPS, flowHash, cardPosition } = await import(`data:text/javascript,${encodeURIComponent(js)}`);
  assert.ok(FLOW_STEPS.length >= 12, 'Detailed investigation must continue beyond the entry screen');
  assert.deepEqual([...new Set(FLOW_STEPS.filter(step => step.page === 'investigation').map(step => step.tab))], [0, 1, 2, 3]);
  assert.equal(FLOW_STEPS[2].selector, '[data-flow="ko-3201-problem"]');
  const route = new URLSearchParams(flowHash('demo-supervisor').split('?')[1]);
  assert.equal(route.get('person'), 'demo-supervisor');
  assert.equal(route.get('asset'), 'asset-ko-3201');
  assert.equal(route.get('flow'), 'ko-3201');
  for (const width of [375, 1440]) {
    const box = cardPosition({ left: 310, right: 370, top: 20, bottom: 70 }, width, 800, 300, 240);
    assert.ok(box.left >= 12 && box.left + 300 <= width - 12);
    assert.ok(box.top >= 12 && box.top + 240 <= 788);
  }
});
