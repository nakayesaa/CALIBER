import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import ts from 'typescript';

test('a stale role selection cannot overwrite the newest API identity', async (context) => {
  const source = readFileSync(new URL('../src/lib/api.ts', import.meta.url), 'utf8')
    .replace('import.meta.env.VITE_API_BASE_URL', 'undefined')
    .replace("export * from './apiContracts';", '');
  const js = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext } }).outputText;
  const { api, selectWorkflowSession } = await import(`data:text/javascript,${encodeURIComponent(js)}`);
  const pending = [];
  const original = globalThis.fetch;
  context.after(() => { globalThis.fetch = original; });
  globalThis.fetch = (url, options) => new Promise((resolve) => pending.push({ url, options, resolve }));
  const reply = (index, person) => pending[index].resolve({ ok: true, json: async () => ({ current: { person_id: person }, can_switch: true }) });
  const older = selectWorkflowSession('demo-equipment-ko');
  const newer = selectWorkflowSession('demo-manager');
  reply(1, 'demo-supervisor');
  await new Promise(setImmediate);
  reply(2, 'demo-manager');
  await newer;
  reply(0, 'demo-supervisor');
  await new Promise(setImmediate);
  if (pending.length > 3) reply(3, 'demo-equipment-ko');
  await older;
  const monitoring = api.equipmentMonitoring();
  const request = pending.at(-1);
  request.resolve({ ok: true, json: async () => [] });
  await monitoring;
  assert.equal(request.options.headers['X-Caliber-Person'], 'demo-manager');
});
