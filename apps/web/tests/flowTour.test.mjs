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

test('each supported role has its own read-only Flow and keeps its assigned asset', async () => {
  const source = readFileSync(new URL('../src/lib/flowTour.ts', import.meta.url), 'utf8');
  const js = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext } }).outputText;
  const { flowForPerson, flowHash } = await import(`data:text/javascript,${encodeURIComponent(js)}`);
  for (const [person, page, asset] of [
    ['demo-supervisor', 'plant', 'asset-ko-3201'],
    ['demo-equipment-ko', 'operator-equipment', 'asset-ko-3201'],
    ['demo-equipment-he', 'operator-equipment', 'asset-he-3301'],
    ['demo-production-zcu', 'production-review', 'asset-ko-3201'],
    ['demo-manager', 'gm-review', 'asset-ko-3201'],
  ]) {
    const flow = flowForPerson(person);
    assert.ok(flow.steps.length >= 6);
    assert.equal(flow.steps[0].page, page);
    const [path, query] = flowHash(person).split('?');
    const params = new URLSearchParams(query);
    assert.equal(path, page);
    assert.equal(params.get('asset'), asset);
    assert.equal(params.get('flow'), flow.id);
    assert.equal(params.get('person'), person);
    assert.equal(params.get('flowStep'), '0');
  }
  assert.equal(flowForPerson('demo-maintenance'), null);
  assert.equal(flowForPerson('unknown'), null);
});
