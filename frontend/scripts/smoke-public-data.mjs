/** Exercise the real static reader against a real published bundle, without a backend. */
import { createServer } from 'vite';
import assert from 'node:assert/strict';
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const root = fileURLToPath(new URL('..', import.meta.url));
const nativeFetch = globalThis.fetch.bind(globalThis);
const input = process.argv[2] || '../.local/free-web-ohio-final';
const remote = /^https?:\/\//.test(input) ? new URL(input.replace(/\/?$/, '/')) : null;
const directory = remote ? remote.href : path.resolve(input);
const proofPath = process.argv[3] && path.resolve(process.argv[3]);
let manifest;
if (remote) {
  const manifestURL = new URL('manifest.json', remote);
  if (process.env.OBSERVATORY_MANIFEST_ID) manifestURL.searchParams.set('publication', process.env.OBSERVATORY_MANIFEST_ID);
  const response = await nativeFetch(manifestURL, { cache: 'no-cache' });
  assert.ok(response.ok, `Remote publication manifest returned ${response.status}`);
  manifest = await response.json();
} else manifest = JSON.parse(await readFile(path.join(directory, 'manifest.json'), 'utf8'));
const state = manifest.states.includes('OH') ? 'OH' : manifest.states[0], revision = manifest.dataset_revision;
const requestedFiles = new Map(), storage = new Map();
globalThis.window = { OBSERVATORY_PUBLIC_MODE: true, dispatchEvent() {} };
globalThis.localStorage = { getItem: key => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, value) };
globalThis.fetch = async (input) => {
  const url = new URL(String(input), 'https://observatory.invalid');
  assert.ok(url.pathname.startsWith('/public-data/'), 'A published reader must not call a backend: ' + input);
  const relative = url.pathname.slice('/public-data/'.length);
  assert.ok(!relative.includes('..'));
  requestedFiles.set(relative, (requestedFiles.get(relative) || 0) + 1);
  if (remote) {
    if (relative === 'manifest.json') return Response.json(manifest);
    const response = await nativeFetch(new URL(relative, remote));
    assert.ok(response.ok, `Remote aggregate ${relative} returned ${response.status}`);
    return new Response(await response.arrayBuffer(), { headers: response.headers });
  }
  const bytes = await readFile(path.join(directory, relative));
  return new Response(bytes, { headers: { 'Content-Type': relative.endsWith('.gz') ? 'application/gzip' : 'application/json' } });
};
const server = await createServer({ root, configFile: false, optimizeDeps: { noDiscovery: true, include: [] }, server: { middlewareMode: true, watch: null, hmr: false, ws: false }, appType: 'custom' });
const checks = [], started = performance.now();
try {
  const { publicFetch, canonicalPublicKey, loadPublishedObject } = await server.ssrLoadModule('/src/publicData.ts');
  const q = manifest.partitions[state].default_query;
  const params = values => { const result = new URLSearchParams(); Object.entries(values).forEach(([key, value]) => { if (value != null && value !== '') result.set(key, Array.isArray(value) ? value.join(',') : String(value)); }); return result; };
  async function check(label, url, validate, expected = 200) {
    const start = performance.now(), response = await publicFetch(url), data = await response.json();
    assert.equal(response.status, expected, label + ': ' + JSON.stringify(data).slice(0, 500));
    if (validate) validate(data);
    checks.push({ label, status: response.status, ms: Math.round(performance.now() - start), url });
    return data;
  }
  await check('bootstrap', '/api/v1/bootstrap', data => assert.ok(data.latest_revision >= revision));
  const workspace = await check('default statewide workspace', '/api/v1/workspace?' + params(q), data => { assert.equal(data.revision, revision); assert.equal(data.query.state, state); assert.ok(Array.isArray(data.geographies)); });
  await check('source inventory', '/api/v1/sources', data => assert.ok(Array.isArray(data.sources || data)));
  await check('external job status', '/api/v1/jobs', data => assert.ok(Array.isArray(data.jobs || data)));
  await check('state catalog', '/api/v2/catalog/states', data => assert.ok(data.states.length >= manifest.states.length));
  await check('dataset inventory', '/api/v2/catalog/datasets?state=' + state, data => assert.ok(Array.isArray(data.datasets)));
  await check('state boundaries', '/api/v1/geography/' + state, data => assert.ok(Array.isArray(data.features)));
  await check('national boundaries', '/api/v1/geography/US', data => assert.ok(data.features.length >= 50));
  await check('national historical map', '/api/v2/results?' + params({ year: 2024, office: 'PRESIDENT', geography_level: 'state', revision }), data => assert.ok(data.geographies.length >= 50));
  await check('county history', '/api/v2/results?' + params({ state, year: 2024, office: 'PRESIDENT', geography_level: state === 'AK' ? 'state' : 'county', baseline: 2020, revision, offset: 0 }), data => assert.ok(data.geographies.length > 0));
  await check('coordinated analytics', '/api/v2/analytics?' + params(q), data => assert.equal(data.revision, revision));
  await check('polling lab policy', '/api/v1/polling?' + params({ ...q, window_days: 21, population: 'LV', include_partisan: true, question_type: 'vote_choice' }), data => assert.equal(data.revision, revision));
  await check('EV interpretation', '/api/v2/participation/quality?' + params(q), data => assert.equal(data.revision, revision));
  await check('historical EV stages', '/api/v2/early-vote/history?' + params({ state, cycle: 2026, revision, as_of: manifest.data_as_of, metric: q.metric, mode: q.mode, alignment: 'days_to_election', history_basis: 'retrospective', baseline_cycles: '2016,2018,2020,2022,2024' }), data => assert.equal(data.revision, revision));
  if (workspace.observations.length) {
    const id = workspace.observations[0].id;
    await check('exact evidence inspector', '/api/v1/evidence/' + id, data => { assert.equal(data.observation.id, id); assert.ok(data.source?.url); assert.ok(data.snapshot?.sha256); });
  }
  const forecastQuery = { state, cycle: 2026, revision, as_of: manifest.data_as_of };
  for (const [office, count] of [['US HOUSE', 435], ['GOVERNOR', 36]]) {
    const url = '/api/v2/forecasts/offices?' + params({ office, cycle: 2026, revision, as_of: manifest.data_as_of });
    if (manifest.requests[canonicalPublicKey(url, manifest)]) await check('office-specific evidence ' + office, url, data => {
      assert.equal(data.revision, revision); assert.equal(data.office, office); assert.equal(data.calls.length, count);
      assert.equal(data.coverage.scheduled_races, count);
      assert.ok(data.calls.every(r => r.office === office && r.call.eventual_winner_probability == null));
      assert.ok(data.calls.every(r => r.history.every(h => h.year < Number(manifest.data_as_of.slice(0, 4)))));
      if (office === 'US HOUSE') assert.ok(data.calls.every(r => r.call.margin_pp == null && r.call.ev_adjustment_pp == null));
      else assert.equal(data.validation.office, office);
    });
  }
  if (manifest.requests[canonicalPublicKey('/api/v2/forecasts/early-vote?' + params(forecastQuery), manifest)]) {
    const calls = await check('experimental EV calls', '/api/v2/forecasts/early-vote?' + params(forecastQuery), data => assert.equal(data.revision, revision));
    if (calls.selected) {
      const reasoningQuery = { ...forecastQuery, race_id: calls.selected.race_id, include_polls: false, include_markets: false, include_context: false };
      const evOnly = await check('EV-only sourced explanation', '/api/v2/forecasts/reasoning?' + params(reasoningQuery), data => { assert.equal(data.mode, 'ev_only'); assert.equal(data.ev_call.call.margin_pp, calls.selected.call.margin_pp); });
      const all = { ...reasoningQuery, include_polls: true, include_markets: true, include_context: true };
      if (manifest.requests[canonicalPublicKey('/api/v2/forecasts/reasoning?' + params(all), manifest)]) await check('optional context keeps exact EV estimate', '/api/v2/forecasts/reasoning?' + params(all), data => { assert.equal(data.ev_call.call.margin_pp, evOnly.ev_call.call.margin_pp); assert.equal(data.manifest.ev_call_sha256, evOnly.manifest.ev_call_sha256); });
    }
    await check('factor validation research', '/api/v2/forecasts/feature-tests?' + params(forecastQuery), data => assert.equal(data.revision, revision));
  }
  if (manifest.reports?.[state]) {
    const packet = await loadPublishedObject(manifest.reports[state]);
    assert.equal(packet.revision, revision); assert.equal(packet.request.query.state, state); assert.ok(packet.html.includes('<svg')); assert.ok(packet.sections.length > 5);
    checks.push({ label: 'published report packet includes real figures and exact scope', status: 200, sections: packet.sections.length, sourceCount: packet.sources.length });
  }
  if (process.argv.includes('--all-states')) for (const code of manifest.states) {
    if (code === state) continue;
    const query = manifest.partitions[code].default_query;
    await check('state investigation ' + code, '/api/v1/workspace?' + params(query), data => { assert.equal(data.query.state, code); assert.equal(data.revision, revision); });
  }
  await check('catalog filtering', '/api/v2/catalog/contests?' + params({ state, year: 2024, office: 'PRESIDENT', revision, q: '', limit: 50, offset: 0 }), data => assert.ok(data.contests.length > 0));
  await check('search published records', '/api/v2/search?q=' + encodeURIComponent(state), data => assert.ok(Array.isArray(data.items)));
  await check('unsupported revision remains unsupported', '/api/v1/workspace?' + params({ ...q, revision: revision - 1 }), data => assert.match(data.detail, /filters were preserved/), 404);
  await check('evidence filter never becomes statewide', '/api/v1/workspace?' + params({ ...q, geography_ids: ['county:39049'] }), data => assert.match(data.detail, /filters were preserved/), 404);
  const denied = await publicFetch('/api/v1/refresh', { method: 'POST', body: '{}' }); assert.equal(denied.status, 405);
  const saved = await publicFetch('/api/v1/research', { method: 'POST', body: JSON.stringify({ kind: 'note', title: 'Private smoke-test note', body: 'Never uploaded' }) }); assert.equal(saved.status, 200);
  const report = { schema: 'observatory-public-reader-smoke-v1', directory, revision, state, passed: checks.length + 2, checks, uniqueFiles: requestedFiles.size, duplicateFetches: [...requestedFiles.values()].reduce((sum, n) => sum + Math.max(0, n - 1), 0), seconds: (performance.now() - started) / 1000 };
  if (proofPath) { await mkdir(path.dirname(proofPath), { recursive: true }); await writeFile(proofPath, JSON.stringify(report, null, 2)); }
  console.log(JSON.stringify(report, null, 2));
} finally { await server.close(); }
