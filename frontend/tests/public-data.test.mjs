import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'vite';
import { fileURLToPath } from 'node:url';

async function moduleFor(t) {
  const server = await createServer({ root: fileURLToPath(new URL('..', import.meta.url)), configFile: false, optimizeDeps: { noDiscovery: true, include: [] }, server: { middlewareMode: true, watch: null, hmr: false, ws: false }, appType: 'custom' });
  t.after(() => server.close());
  return server.ssrLoadModule('/src/publicData.ts');
}
const publication = {
  schema_version: 'observatory-public-v1', dataset_revision: 375, published_at: '2026-10-21T12:00:00Z', data_as_of: '2026-10-21',
  request_defaults: { '/api/v1/workspace': { state: 'NC', revision: 375, cycle: 2026, as_of: '2026-10-21', metric: 'ballots_cast', baseline: 2022, mode: 'all', time_basis: 'reported', alignment: 'days_to_election' } }, requests: {}, available_queries: [{ state: 'OH', cycle: 2026, metric: 'ballots_cast', mode: 'all' }],
};
test('publication-specific manifest URLs avoid stale host caches without changing evidence queries', async t => {
  const { publicManifestURL } = await moduleFor(t);
  assert.equal(publicManifestURL('588-cloud-build'), '/public-data/manifest.json?publication=588-cloud-build');
  assert.equal(publicManifestURL(''), '/public-data/manifest.json');
  assert.match(publicManifestURL('588-cloud-build', true), /publication=588-cloud-build&checked=\d+/);
});
test('canonical publishing defaults preserve explicit dates, revisions, selections and unknown filters', async t => {
  const { canonicalPublicKey, publicAlternatives } = await moduleFor(t);
  const standard = canonicalPublicKey('/api/v1/workspace?state=OH&as_of=&geography_ids=&date_window=', publication);
  assert.equal(standard, '/api/v1/workspace?alignment=days_to_election&as_of=2026-10-21&baseline=2022&cycle=2026&metric=ballots_cast&mode=all&revision=375&state=OH&time_basis=reported');
  assert.notEqual(canonicalPublicKey('/api/v1/workspace?state=OH&revision=176', publication), standard);
  assert.notEqual(canonicalPublicKey('/api/v1/workspace?state=OH&as_of=2024-10-21', publication), standard);
  assert.notEqual(canonicalPublicKey('/api/v1/workspace?state=OH&category=DEM', publication), standard);
  assert.notEqual(canonicalPublicKey('/api/v1/workspace?state=OH&geography_ids=county%3A39049', publication), standard);
  assert.equal(publicAlternatives(publication, 'OH').length, 1);
  assert.equal(publicAlternatives(publication, 'IA').length, 0);
});
test('publication freshness distinguishes six-hour delays from day-old releases', async t => {
  const { publicationAge } = await moduleFor(t);
  const timestamp = Date.parse(publication.published_at);
  assert.equal(publicationAge(publication, timestamp + 5 * 3600000).status, 'current');
  assert.equal(publicationAge(publication, timestamp + 6 * 3600000).status, 'delayed');
  assert.equal(publicationAge(publication, timestamp + 24 * 3600000).status, 'stale');
});
test('public request adapter never substitutes filters and browser notebooks never call the server', async t => {
  const { publicFetch, canonicalPublicKey } = await moduleFor(t);
  const previous = { fetch: globalThis.fetch, window: globalThis.window, localStorage: globalThis.localStorage };
  t.after(() => Object.entries(previous).forEach(([key, value]) => value === undefined ? delete globalThis[key] : globalThis[key] = value));
  const calls = [], storage = new Map();
  globalThis.window = { OBSERVATORY_PUBLIC_MODE: true, dispatchEvent() {} };
  globalThis.localStorage = { getItem: key => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, value) };
  const current = structuredClone(publication);
  current.requests[canonicalPublicKey('/api/v1/workspace?state=OH', current)] = { path: 'objects/oh.json' };
  globalThis.fetch = async input => {
    calls.push(input);
    if (input === '/public-data/manifest.json') return Response.json(current);
    if (input === '/public-data/objects/oh.json') return Response.json({ revision: 375, query: { state: 'OH' }, summary: { total: 123 } });
    throw new Error('Unexpected network access: ' + input);
  };
  const exact = await publicFetch('/api/v1/workspace?state=OH');
  assert.equal(exact.status, 200);
  assert.equal((await exact.json()).summary.total, 123);
  const filtered = await publicFetch('/api/v1/workspace?state=OH&category=DEM');
  assert.equal(filtered.status, 404);
  assert.match((await filtered.json()).detail, /filters were preserved/);
  const pinned = await publicFetch('/api/v1/workspace?state=OH&revision=176');
  assert.equal(pinned.status, 404);
  const before = calls.length;
  const saved = await publicFetch('/api/v1/research', { method: 'POST', body: JSON.stringify({ title: 'Private question', kind: 'note', body: 'Never send me to a server' }) });
  const item = await saved.json();
  assert.equal(item.title, 'Private question');
  assert.equal((await (await publicFetch('/api/v1/research')).json()).length, 1);
  assert.equal((await publicFetch(`/api/v1/research/${item.id}`, { method: 'DELETE' })).status, 204);
  assert.equal(calls.length, before);
  const denied = await publicFetch('/api/v1/refresh', { method: 'POST', body: '{}' });
  assert.equal(denied.status, 405);
  assert.equal(calls.some(url => String(url).startsWith('/api/')), false);
});
test('browser scenario arithmetic matches the constrained two-method calculation and guards observed totals', async t => {
  const { calculatePublicScenario } = await moduleFor(t);
  const assumptions = { final_turnout: 1000, observed_ballots: 100, early_share: .6, early_support: .7, election_day_support: .4, undecided_share: .2, undecided_allocation: .3 };
  const result = calculatePublicScenario(assumptions);
  // Already observed support remains an explicit assumption; undecideds apply to remaining ballots.
  const expected = 100 * .7 + 500 * (.8 * .7 + .2 * .3) + 400 * (.8 * .4 + .2 * .3);
  assert.ok(Math.abs(result.candidate_a_votes - expected) < 1e-9);
  assert.equal(result.candidate_a_votes + result.candidate_b_votes, 1000);
  assert.ok(Math.abs(result.margin - (2 * expected - 1000) / 10) < 1e-9);
  assert.equal(result.grid.length, 25);
  assert.equal(result.sensitivity.length, 4);
  assert.throws(() => calculatePublicScenario({ ...assumptions, observed_ballots: 700 }), /early ballots/);
  assert.throws(() => calculatePublicScenario({ ...assumptions, early_support: 1.2 }), /between/);
  assert.throws(() => calculatePublicScenario({ ...assumptions, final_turnout: NaN }), /finite/);
});
test('content-addressed references and chunks hydrate into the exact aggregate shape and enforce hashes', async t => {
  const { loadPublishedObject, publicAsset } = await moduleFor(t);
  const { createHash } = await import('node:crypto');
  const previous = globalThis.fetch;
  t.after(() => { globalThis.fetch = previous; });
  const blobs = new Map(), counts = new Map();
  const store = (path, body) => { const text = JSON.stringify(body), sha256 = createHash('sha256').update(text).digest('hex'); blobs.set('/public-data/' + path, text); return { $public_ref: path, sha256, bytes: Buffer.byteLength(text) }; };
  const first = store('objects/chunk-a.json', [{ id: 1, value: null }, { id: 2, value: 0 }]);
  const second = store('objects/chunk-b.json', [{ id: 3, value: 100 }]);
  const root = store('objects/root.json', { revision: 375, rows: { $public_chunks: [first, second] }, repeated: first, definition: { unit: 'ballots' } });
  globalThis.fetch = async path => { counts.set(path, (counts.get(path) || 0) + 1); if (!blobs.has(path)) throw new Error('Unexpected data URL'); return new Response(blobs.get(path)); };
  const hydrated = await loadPublishedObject({ path: root.$public_ref, sha256: root.sha256, encoding: 'observatory-json-refs-v1' });
  assert.deepEqual(hydrated, { revision: 375, rows: [{ id: 1, value: null }, { id: 2, value: 0 }, { id: 3, value: 100 }], repeated: [{ id: 1, value: null }, { id: 2, value: 0 }], definition: { unit: 'ballots' } });
  assert.equal(counts.get('/public-data/objects/chunk-a.json'), 1);
  await assert.rejects(loadPublishedObject({ path: root.$public_ref, sha256: 'a'.repeat(64) }), /integrity/);
  assert.throws(() => publicAsset('../private.sqlite'), /Invalid/);
  assert.throws(() => publicAsset('https://private.invalid/data'), /Invalid/);
});
test('a selected historical contest keeps explicit votes, suppression and withheld swing without combining other races', async t => {
  const { projectPublicContest } = await moduleFor(t);
  const contest = { id: 'contest:house:1', year: 2024, office: 'US HOUSE', district: '01', name: 'U.S. House', election_id: 'election:OH:2024:general', payload: { special: false } };
  const previous = { ...contest, id: 'contest:house:old', year: 2020, election_id: 'election:OH:2020:general' };
  const input = { revision: 375, query: { year: 2024, baseline: 2020 }, contests: [contest, previous, { ...contest, id: 'contest:house:2', district: '02' }], geographies: [{ id: 'district:1', contest_id: contest.id, total_votes: 70, swing_pp: null, partial_suppression: true, matched_baseline: false }, { id: 'district:2', contest_id: 'contest:house:2', total_votes: 150 }], baseline_geographies: [{ id: 'district:old', contest_id: previous.id, total_votes: 80 }], coverage: {}, warnings: [], pagination: null };
  const frozen = JSON.stringify(input), result = projectPublicContest(input, contest.id);
  assert.equal(result.summary.total_votes, 70);
  assert.equal(result.summary.contest_count, 1);
  assert.equal(result.geographies.length, 1);
  assert.equal(result.geographies[0].swing_pp, null);
  assert.equal(result.geographies[0].partial_suppression, true);
  assert.equal(result.baseline_geographies.length, 1);
  assert.equal(JSON.stringify(input), frozen);
  assert.throws(() => projectPublicContest(input, 'made-up'), /not completely/);
});
test('raw gzip artifacts and transparently decoded artifacts preserve the same verified JSON payload', async t => {
  const { loadPublishedObject } = await moduleFor(t);
  const { gzipSync } = await import('node:zlib'), { createHash } = await import('node:crypto');
  const previous = globalThis.fetch;
  t.after(() => { globalThis.fetch = previous; });
  const data = { revision: 375, value: 0, missing: null, source: 'Archived aggregate' }, text = JSON.stringify(data), digest = createHash('sha256').update(text).digest('hex');
  globalThis.fetch = async input => new Response(String(input).endsWith('raw.json.gz') ? gzipSync(text) : text);
  assert.deepEqual(await loadPublishedObject({ path: 'objects/raw.json.gz', sha256: digest }), data);
  assert.deepEqual(await loadPublishedObject({ path: 'objects/decoded.json.gz', sha256: digest }), data);
});
test('batched evidence lookup returns only the exact published observation and never a neighboring record', async t => {
  const { publicFetch } = await moduleFor(t);
  const previous = { fetch: globalThis.fetch, window: globalThis.window };
  t.after(() => Object.entries(previous).forEach(([key, value]) => value === undefined ? delete globalThis[key] : globalThis[key] = value));
  globalThis.window = { OBSERVATORY_PUBLIC_MODE: true, dispatchEvent() {} };
  const current = { ...publication, evidence_buckets: { '16': { path: 'objects/evidence-bucket-16.json' } } };
  const fetched = [];
  globalThis.fetch = async input => {
    fetched.push(input);
    if (input === '/public-data/manifest.json') return Response.json(current);
    if (input === '/public-data/objects/evidence-bucket-16.json') return Response.json({ '8437': { observation: { id: 8437, value: 0 }, source: { url: 'https://elections.example/report' }, snapshot: { sha256: 'a'.repeat(64) } } });
    throw new Error('Unexpected network call: ' + input);
  };
  const exact = await publicFetch('/api/v1/evidence/8437');
  assert.equal(exact.status, 200);
  assert.equal((await exact.json()).observation.value, 0);
  assert.equal((await publicFetch('/api/v1/evidence/8438')).status, 404);
  assert.equal((await publicFetch('/api/v1/evidence/999999')).status, 404);
  assert.equal((await publicFetch('/api/v1/evidence/8437?revision=100')).status, 404);
  assert.equal(fetched.filter(url => String(url).includes('bucket-16')).length, 1);
  assert.equal(fetched.some(url => String(url).startsWith('/api/')), false);
});
test('packed objects preserve original hashes, hydrate shared references, and fetch one bounded container', async t => {
  const { publicFetch } = await moduleFor(t);
  const { createHash } = await import('node:crypto'), { gzipSync } = await import('node:zlib');
  const previous = { fetch: globalThis.fetch, window: globalThis.window };
  t.after(() => Object.entries(previous).forEach(([key, value]) => value === undefined ? delete globalThis[key] : globalThis[key] = value));
  globalThis.window = { OBSERVATORY_PUBLIC_MODE: true, dispatchEvent() {} };
  const hash = text => createHash('sha256').update(text).digest('hex');
  const shared = JSON.stringify({ value: 0, missing: null }), root = JSON.stringify({ revision: 375, data: { $public_ref: 'objects/shared.json.gz', sha256: hash(shared), bytes: shared.length } });
  const pack = JSON.stringify({ objects: { 'objects/root.json.gz': root, 'objects/shared.json.gz': shared } }), packHash = hash(pack);
  const current = structuredClone(publication);
  current.requests['/api/v1/bootstrap'] = { path: 'objects/root.json.gz', sha256: hash(root) };
  current.object_packs = Object.fromEntries(['objects/root.json.gz', 'objects/shared.json.gz'].map(key => [key, { path: 'packs/real.json.gz', sha256: packHash, key }]));
  const calls = [];
  globalThis.fetch = async input => { calls.push(input); if (input === '/public-data/manifest.json') return Response.json(current); if (input === '/public-data/packs/real.json.gz') return new Response(gzipSync(pack)); throw new Error('Packed leaf must not be fetched directly: ' + input); };
  const response = await publicFetch('/api/v1/bootstrap');
  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), { revision: 375, data: { value: 0, missing: null } });
  assert.equal(calls.filter(path => path.includes('/packs/')).length, 1);
});
test('a corrupted evidence pack is rejected and a later valid retry succeeds without substituting data', async t => {
  const { publicFetch } = await moduleFor(t);
  const { createHash } = await import('node:crypto');
  const previous = { fetch: globalThis.fetch, window: globalThis.window };
  t.after(() => Object.entries(previous).forEach(([key, value]) => value === undefined ? delete globalThis[key] : globalThis[key] = value));
  globalThis.window = { OBSERVATORY_PUBLIC_MODE: true, dispatchEvent() {} };
  const hash = text => createHash('sha256').update(text).digest('hex'), root = JSON.stringify({ revision: 375, total: 20 }), pack = JSON.stringify({ objects: { 'objects/retry.json': root } });
  const current = structuredClone(publication);
  current.requests['/api/v1/bootstrap'] = { path: 'objects/retry.json', sha256: hash(root) };
  current.object_packs = { 'objects/retry.json': { path: 'packs/retry.json.gz', sha256: hash(pack), key: 'objects/retry.json' } };
  let count = 0;
  globalThis.fetch = async input => { if (input === '/public-data/manifest.json') return Response.json(current); count++; return new Response(count === 1 ? JSON.stringify({ objects: { 'objects/retry.json': '{"total":999}' } }) : pack); };
  const bad = await publicFetch('/api/v1/bootstrap');
  assert.equal(bad.status, 422); assert.match((await bad.json()).detail, /integrity/);
  const good = await publicFetch('/api/v1/bootstrap');
  assert.equal(good.status, 200); assert.equal((await good.json()).total, 20); assert.equal(count, 2);
});
test('packed evidence rejects mismatched keys, absent objects and altered original fragments', async t => {
  const { publicFetch } = await moduleFor(t);
  const { createHash } = await import('node:crypto');
  const previous = { fetch: globalThis.fetch, window: globalThis.window };
  t.after(() => Object.entries(previous).forEach(([key, value]) => value === undefined ? delete globalThis[key] : globalThis[key] = value));
  globalThis.window = { OBSERVATORY_PUBLIC_MODE: true, dispatchEvent() {} };
  const hash = text => createHash('sha256').update(text).digest('hex'), expected = '{"total":20}', altered = '{"total":999}', pack = JSON.stringify({ objects: { 'objects/changed.json': altered } });
  const current = structuredClone(publication); current.object_packs = {};
  for (const name of ['wrong-key', 'absent', 'changed']) {
    const path = `objects/${name}.json`;
    current.requests[`/api/v1/${name}`] = { path, sha256: hash(expected) };
    current.object_packs[path] = { path: 'packs/untrusted.json.gz', sha256: hash(pack), key: name === 'wrong-key' ? 'objects/changed.json' : path };
  }
  globalThis.fetch = async input => input === '/public-data/manifest.json' ? Response.json(current) : new Response(pack);
  const wrong = await publicFetch('/api/v1/wrong-key'); assert.equal(wrong.status, 422); assert.match((await wrong.json()).detail, /exact object/);
  const absent = await publicFetch('/api/v1/absent'); assert.equal(absent.status, 422); assert.match((await absent.json()).detail, /missing/);
  const changed = await publicFetch('/api/v1/changed'); assert.equal(changed.status, 422); assert.match((await changed.json()).detail, /integrity/);
});
test('compact pack index zero resolves the exact object and out-of-range indexes are rejected', async t => {
  const { publicFetch } = await moduleFor(t);
  const { createHash } = await import('node:crypto');
  const previous = { fetch: globalThis.fetch, window: globalThis.window };
  t.after(() => Object.entries(previous).forEach(([key, value]) => value === undefined ? delete globalThis[key] : globalThis[key] = value));
  globalThis.window = { OBSERVATORY_PUBLIC_MODE: true, dispatchEvent() {} };
  const hash = text => createHash('sha256').update(text).digest('hex'), text = '{"revision":375,"zero":0}', pack = JSON.stringify({ objects: { 'objects/compact.json': text } });
  const current = structuredClone(publication);
  current.requests['/api/v1/bootstrap'] = { path: 'objects/compact.json', sha256: hash(text) };
  current.requests['/api/v1/bad-index'] = { path: 'objects/bad-index.json', sha256: hash(text) };
  current.object_packs = { 'objects/compact.json': 0, 'objects/bad-index.json': 99 };
  current.packs = [{ path: 'packs/compact.json.gz', sha256: hash(pack) }];
  globalThis.fetch = async input => input === '/public-data/manifest.json' ? Response.json(current) : new Response(pack);
  const exact = await publicFetch('/api/v1/bootstrap'); assert.equal(exact.status, 200); assert.equal((await exact.json()).zero, 0);
  const bad = await publicFetch('/api/v1/bad-index'); assert.equal(bad.status, 422); assert.match((await bad.json()).detail, /index is invalid/);
});
