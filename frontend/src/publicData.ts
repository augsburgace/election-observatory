/** Read-only, revision-pinned aggregate publishing. The local API remains unchanged. */
import type { ResearchObject } from "./types";
export interface PublicManifest {
  schema_version: string;
  published_at: string;
  data_as_of: string;
  dataset_revision: number;
  successor_url?: string;
  schedule?: { description?: string; interval_hours?: number };
  requests: Record<string, string | { path: string; sha256?: string; bytes?: number; encoding?: string }>;
  request_defaults?: Record<string, Record<string, unknown>>;
  evidence_buckets?: Record<string, { path: string; sha256?: string; bytes?: number; encoding?: string }>;
  object_packs?: Record<string, number | { path: string; sha256: string; key: string }>;
  packs?: { path: string; sha256: string; bytes?: number; uncompressed_bytes?: number }[];
  available_queries?: Record<string, unknown>[];
  reports?: Record<string, string | { path: string }>;
  partitions?: Record<string, { recommended_query?: Record<string, unknown>; default_query?: Record<string, unknown> }>;
  search_index?: string;
  catalogs?: Record<string, string | { path: string; sha256?: string; bytes?: number; encoding?: string }>;
  limitations?: string[];
  attributions?: { source_id: string; title: string; creator: string; source_url: string; about_url?: string; license: string; license_url: string; retrieved_at: string; transformation?: string; interpretation?: string }[];
}
export const isPublicMode = () =>
  (import.meta as ImportMeta & { env?: Record<string, string> }).env?.VITE_PUBLIC_DATA_MODE === "true" ||
  (typeof window !== "undefined" && (window as Window & { OBSERVATORY_PUBLIC_MODE?: boolean }).OBSERVATORY_PUBLIC_MODE === true);
let manifestPromise: Promise<PublicManifest> | undefined;
let manifest: PublicManifest | undefined;
let checked = 0;
export function publicManifestURL(publicationId = (import.meta as ImportMeta & { env?: Record<string, string> }).env?.VITE_PUBLICATION_ID || "", force = false) {
  const values = new URLSearchParams();
  if (publicationId) values.set("publication", publicationId);
  if (force) values.set("checked", String(Date.now()));
  return publicAsset("manifest.json") + (values.size ? "?" + values.toString() : "");
}
export function canonicalPublicKey(input: string, publication: PublicManifest): string {
  const url = new URL(input, "https://observatory.invalid");
  const values = new URLSearchParams();
  Object.entries(publication.request_defaults?.[url.pathname] || {}).forEach(([key, value]) => {
    if (value != null && value !== "") values.set(key, Array.isArray(value) ? value.join(",") : String(value));
  });
  url.searchParams.forEach((value, key) => { if (value !== "") values.set(key, value); });
  values.sort();
  return url.pathname + (values.size ? "?" + values.toString() : "");
}
export async function getPublicManifest(force = false): Promise<PublicManifest> {
  if (!manifestPromise || force || Date.now() - checked > 60_000) {
    checked = Date.now();
    manifestPromise = fetch(publicManifestURL(undefined, force), { cache: "no-cache" }).then(async response => {
      if (!response.ok) throw new Error("The published research index is unavailable. Please retry; the local research edition remains available.");
      const next = await response.json() as PublicManifest;
      if (next.schema_version !== "observatory-public-v1" || !next.requests || typeof next.requests !== "object" || Array.isArray(next.requests) || !Number.isInteger(next.dataset_revision) || next.dataset_revision < 0 || !Number.isFinite(Date.parse(next.published_at)) || !/^\d{4}-\d{2}-\d{2}$/.test(next.data_as_of)) throw new Error("The publication manifest is invalid; no unverified data were substituted.");
      manifest = next;
      if (typeof window !== "undefined") window.dispatchEvent(new CustomEvent("observatory-publication", { detail: next }));
      return next;
    }).catch(error => { manifestPromise = undefined; if (manifest) return manifest; throw error; });
  }
  return manifestPromise;
}
export function publicationAge(publication: PublicManifest, now = Date.now()) {
  const hours = Math.max(0, (now - Date.parse(publication.published_at)) / 3_600_000);
  return { hours, status: hours >= 24 ? "stale" : hours >= 6 ? "delayed" : "current" };
}
const jsonResponse = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
export function publicAlternatives(publication: PublicManifest, state: string) {
  return (publication.available_queries || []).map(row => row.query && typeof row.query === "object" ? row.query as Record<string, unknown> : row).filter(row => row.state === state).sort((a, b) => Number(b.cycle) - Number(a.cycle)).slice(0, 5);
}
function researchItems(): ResearchObject[] {
  const text = localStorage.getItem("observatory-public-research-v1");
  if (!text) return [];
  const parsed: unknown = JSON.parse(text);
  if (!Array.isArray(parsed)) throw new Error("Browser notebook storage is invalid. Export or restore your browser data before replacing it.");
  return parsed as ResearchObject[];
}
function localResearch(path: string, method: string, init?: RequestInit): Response {
  const items = researchItems();
  if (method === "GET") return jsonResponse(items);
  const id = Number(path.split("/").at(-1));
  const index = items.findIndex(item => item.id === id);
  if (method === "DELETE") {
    if (index < 0) return jsonResponse({ detail: "This browser notebook item no longer exists." }, 404);
    items.splice(index, 1);
    localStorage.setItem("observatory-public-research-v1", JSON.stringify(items));
    return new Response(null, { status: 204 });
  }
  const data = JSON.parse(String(init?.body || "{}"));
  if (method === "PUT" && index < 0) return jsonResponse({ detail: "This browser notebook item no longer exists." }, 404);
  const saved = { ...(index >= 0 ? items[index] : {}), ...data, id: method === "PUT" ? id : Math.max(Date.now(), ...items.map(item => item.id + 1)), updated_at: new Date().toISOString() } as ResearchObject;
  if (method === "PUT") items[index] = saved; else items.push(saved);
  localStorage.setItem("observatory-public-research-v1", JSON.stringify(items));
  return jsonResponse(saved);
}
export async function publicFetch(input: string, init?: RequestInit): Promise<Response> {
  if (!isPublicMode() || !input.startsWith("/api/")) return fetch(input, init);
  const url = new URL(input, "https://observatory.invalid"), method = init?.method || "GET";
  try {
    if (/^\/api\/v1\/research(?:\/\d+)?$/.test(url.pathname)) return localResearch(url.pathname, method, init);
    if (url.pathname === "/api/v1/scenarios" && method === "POST") return jsonResponse(calculatePublicScenario(JSON.parse(String(init?.body || "{}"))));
    const publication = await getPublicManifest();
    const evidenceId = /^\/api\/v1\/evidence\/(\d+)$/.exec(url.pathname)?.[1];
    if (method === "GET" && evidenceId && publication.evidence_buckets) {
      if (url.searchParams.size || !Number.isSafeInteger(Number(evidenceId))) return jsonResponse({ detail: "This exact evidence request is not included in the public release." }, 404);
      const bucket = publication.evidence_buckets[String(Math.floor(Number(evidenceId) / 512))];
      if (!bucket) return jsonResponse({ detail: "This observation is not included in the published evidence scope." }, 404);
      const payload = await loadPublishedObject(bucket, init?.signal) as Record<string, unknown>;
      // Both original wrapped buckets and current compact direct-ID maps are supported.
      const items = Object.hasOwn(payload, "items") ? payload.items as Record<string, unknown> : payload;
      if (Object.hasOwn(payload, "items") && payload.revision !== publication.dataset_revision || !items || typeof items !== "object" || Array.isArray(items) || !Object.hasOwn(items, evidenceId)) return jsonResponse({ detail: "This observation is not included in the published evidence scope." }, 404);
      return jsonResponse(items[evidenceId]);
    }
    if (method !== "GET") return jsonResponse({ detail: "This public edition publishes validated aggregate evidence. Server collection, corrections and download jobs are managed by its scheduled publisher. Your notes and scenarios are private to this browser." }, 405);
    if (url.pathname === "/api/v2/search" && publication.search_index) {
      const data = await loadPublishedObject(publication.search_index, init?.signal) as { items?: unknown[] };
      const rows = Array.isArray(data) ? data : data.items || [];
      const words = (url.searchParams.get("q") || "").toLowerCase().split(/\s+/).filter(Boolean);
      return jsonResponse({ revision: publication.dataset_revision, items: rows.filter((row: unknown) => words.every(word => JSON.stringify(row).toLowerCase().includes(word))).slice(0, 30) });
    }
    if (publication.catalogs && ["/api/v2/catalog/contests", "/api/v2/search"].includes(url.pathname)) {
      const requestedRevision = url.searchParams.get("revision");
      if (requestedRevision && Number(requestedRevision) !== publication.dataset_revision) return jsonResponse({ detail: "That catalog revision is not included in this published release. Your pinned selection was preserved." }, 404);
      const kinds = url.pathname.endsWith("/search") ? ["contests", "candidates", "places", "elections"] : ["contests"];
      const groups = await Promise.all(kinds.map(async kind => {
        const entry = publication.catalogs?.[kind];
        if (!entry) return [];
        const body = await loadPublishedObject(entry, init?.signal) as { items?: Record<string, unknown>[] };
        return (body.items || []) as Record<string, unknown>[];
      }));
      const words = (url.searchParams.get("q") || "").toLowerCase().split(/\s+/).filter(Boolean);
      if (url.pathname.endsWith("/search")) {
        const contestStates = new Map(groups[0].map(row => [row.id, row.state]));
        groups[1] = (groups[1] || []).map(row => ({ ...row, state: row.state || contestStates.get(row.contest_id) }));
        return jsonResponse({ revision: publication.dataset_revision, items: groups.flatMap((rows, index) => rows.map(row => ({ ...row, kind: kinds[index] === "places" ? "place" : kinds[index] === "candidates" ? "candidate" : "contest" }))).filter(row => words.every(word => JSON.stringify(row).toLowerCase().includes(word))).slice(0, 30), scope: "Published verified records; private browser notes are excluded." });
      }
      const allowed = new Set(["state", "year", "office", "revision", "q", "limit", "offset"]);
      if ([...url.searchParams.keys()].some(key => !allowed.has(key))) return jsonResponse({ detail: "This catalog filter is not supported in the public release." }, 404);
      const rows = groups[0].filter(row => ["state", "year", "office"].every(key => !url.searchParams.has(key) || String(row[key]).toLowerCase() === url.searchParams.get(key)!.toLowerCase()) && words.every(word => JSON.stringify(row).toLowerCase().includes(word)));
      const limit = Math.max(1, Math.min(200, Number(url.searchParams.get("limit") || 50))), offset = Math.max(0, Number(url.searchParams.get("offset") || 0));
      if (!Number.isFinite(limit) || !Number.isFinite(offset)) return jsonResponse({ detail: "Catalog pagination must be finite." }, 422);
      return jsonResponse({ revision: publication.dataset_revision, total: rows.length, contests: rows.slice(offset, offset + limit), offset, limit });
    }
    const key = canonicalPublicKey(input, publication), entry = publication.requests[key];
    if (!entry && url.pathname === "/api/v2/results" && url.searchParams.get("contest_id")) {
      const contestId = url.searchParams.get("contest_id")!;
      url.searchParams.delete("contest_id");
      const baseKey = canonicalPublicKey(url.pathname + "?" + url.searchParams, publication);
      if (publication.requests[baseKey]) {
        const response = await publicFetch(url.pathname + "?" + url.searchParams, init);
        if (!response.ok) return response;
        return jsonResponse(projectPublicContest(await response.json(), contestId));
      }
    }
    if (!entry) return jsonResponse({ detail: "This exact combination is not in the current public release. Your filters were preserved. Open a published selection below, or use Sources to inspect coverage. Detailed downloads and arbitrary historical cutoffs remain available in the local research edition.", published: publicAlternatives(publication, url.searchParams.get("state") || "") }, 404);
    return jsonResponse(await loadPublishedObject(entry, init?.signal));
  } catch (error) { return jsonResponse({ detail: (error as Error).message }, 422); }
}
export function publicAsset(path: string) {
  const base = ((import.meta as ImportMeta & { env?: Record<string, string> }).env?.BASE_URL || "/").replace(/\/?$/, "/");
  if (path.includes("..") || /^[a-z]+:/i.test(path)) throw new Error("Invalid public artifact path");
  if (path.startsWith(base + "public-data/")) return path;
  return base + "public-data/" + path.replace(/^\/?public-data\//, "").replace(/^\/+/, "");
}
export function originalDocumentHref(snapshot: { url?: unknown; source_url?: unknown; id?: unknown }, fallback?: string) {
  return isPublicMode() ? String(snapshot.url || snapshot.source_url || fallback || "?page=sources") : `/api/v1/documents/${snapshot.id}`;
}
/** Same disjoint two-method arithmetic as scenario_service.py; never an election forecast. */
export function calculatePublicScenario(body: Record<string, unknown>) {
  const n = (key: string, fallback?: number) => { const value = Number(body[key] ?? fallback); if (!Number.isFinite(value)) throw new Error(`${key} must be a finite number`); return value; };
  const observed = n("observed_ballots", 0), total = n("final_turnout");
  const shares = { early_share: n("early_share", .5), early_support: n("early_support", .5), election_day_support: n("election_day_support", .5), undecided_share: n("undecided_share", 0), undecided_allocation: n("undecided_allocation", .5) };
  if (observed < 0 || total <= 0 || total < observed || Object.values(shares).some(value => value < 0 || value > 1)) throw new Error("Turnout must cover observed ballots and all support assumptions must be between 0% and 100%.");
  const run = (turnout: number, values = shares) => {
    const early = turnout * values.early_share;
    if (early + 1e-6 < observed) throw new Error("Assumed final early ballots cannot be below the reported starting count.");
    const adjusted = (support: number) => (1 - values.undecided_share) * support + values.undecided_share * values.undecided_allocation;
    const a = observed * values.early_support + Math.max(0, early - observed) * adjusted(values.early_support) + turnout * (1 - values.early_share) * adjusted(values.election_day_support);
    return { candidate_a_votes: a, candidate_b_votes: turnout - a, candidate_a_share: 100 * a / turnout, candidate_b_share: 100 * (turnout - a) / turnout, margin: 100 * (2 * a - turnout) / turnout };
  };
  const result = run(total), grid: Record<string, number>[] = [];
  for (const factor of [.8, .9, 1, 1.1, 1.2]) for (const offset of [-.1, -.05, 0, .05, .1]) {
    const turnout = total * factor, support = Math.max(0, Math.min(1, shares.election_day_support + offset));
    if (turnout * shares.early_share >= observed) grid.push({ turnout, election_day_support: support * 100, ...run(turnout, { ...shares, election_day_support: support }) });
  }
  const sensitivity = ([['early_share', .1], ['early_support', .05], ['election_day_support', .05], ['undecided_allocation', .1]] as const).map(([parameter, amount]) => {
    const low = Math.max(parameter === "early_share" ? observed / total : 0, shares[parameter] - amount), high = Math.min(1, shares[parameter] + amount);
    return { parameter, low, high, low_margin: run(total, { ...shares, [parameter]: low }).margin, high_margin: run(total, { ...shares, [parameter]: high }).margin };
  });
  return { status: "scenario", label: "Browser-calculated turnout and support scenario", ...result, state: body.state, revision: body.revision, query: body.query, parameters: shares, total_turnout: total, observed_ballots: observed, observed_total: observed, remaining_ballots: total - observed, early_ballots: total * shares.early_share, election_day_ballots: total * (1 - shares.early_share), projected_votes: { candidate_a: result.candidate_a_votes, candidate_b: result.candidate_b_votes, other: 0 }, components: [{ name: "Early participation", ballots: total * shares.early_share, assumed_A_support_pct: shares.early_support * 100 }, { name: "Election Day participation", ballots: total * (1 - shares.early_share), assumed_A_support_pct: shares.election_day_support * 100 }], sensitivity, grid, assumptions: shares, warnings: ["Conditional arithmetic, not a forecast. Candidate support is assumed, including support among ballots already observed.", "This scenario runs privately in your browser against the selected published evidence."] };
}

export function publicStaticAsset(path: string) {
  if (!isPublicMode()) return path;
  const base = (import.meta as ImportMeta & { env?: Record<string, string> }).env?.BASE_URL || "/";
  return base.replace(/\/?$/, "/") + path.replace(/^\/+/, "");
}

/** Select one published contest without reallocating votes or inventing a boundary comparison. */
export function projectPublicContest(input: Record<string, unknown>, contestId: string) {
  const source = structuredClone(input), query = source.query as Record<string, unknown>;
  const contests = source.contests as Record<string, unknown>[];
  const selected = contests.find(row => row.id === contestId && row.year === query.year);
  if (!selected || (source.pagination as { has_more?: boolean } | null)?.has_more) throw new Error("This contest is not completely represented in the published result scope.");
  const identity = (row: Record<string, unknown>) => JSON.stringify([row.office, String(row.district || "").toUpperCase(), (row.payload as Record<string, unknown> | undefined)?.special || false, String(row.name || "").toUpperCase(), String(row.election_id || "").split(":").at(-1)]);
  const current = (source.geographies as Record<string, unknown>[]).filter(row => row.contest_id === contestId);
  if (!current.length) throw new Error("No complete current result rows were published for this contest.");
  const related = contests.filter(row => row.id === contestId || row.year === query.baseline && identity(row) === identity(selected));
  const previousIds = new Set(related.filter(row => row.year === query.baseline).map(row => row.id));
  const earlier = ((source.baseline_geographies || []) as Record<string, unknown>[]).filter(row => previousIds.has(row.contest_id));
  const total = current.reduce((sum, row) => sum + (typeof row.total_votes === "number" ? row.total_votes : 0), 0);
  current.forEach(row => row.share_of_selected_votes_pct = total ? 100 * Number(row.total_votes) / total : null);
  const summary: Record<string, unknown> = { total_votes: total, geography_count: current.length, contest_count: 1, matched_baseline_count: current.filter(row => row.matched_baseline === true).length, unit: "candidate votes" };
  if (current.length === 1) for (const key of ["options", "winner", "leading_option", "winner_status", "margin_pp", "winner_margin_pp", "dem_share_pct", "rep_share_pct", "dem_margin_pp", "rep_margin_pp", "swing_pp"]) if (key in current[0]) summary[key] = current[0][key];
  return { ...source, query: { ...query, contest_id: contestId }, contests: related, geographies: current, baseline_geographies: earlier, summary, pagination: null, coverage: { ...(source.coverage as object), current_geographies: current.length, baseline_geographies: earlier.length, matched_geographies: summary.matched_baseline_count }, warnings: [...(source.warnings as string[]).filter(text => text !== "Several contests are present; their candidate vote totals are not added together."), "This browser view selects an explicitly identified contest from complete published aggregate returns. Existing source suppression, round and boundary-comparison restrictions remain in force. Provenance may include the parent packet's additional sources."] };
}

const objectCache = new Map<string, Promise<unknown>>();
const packCache = new Map<string, Record<string, string>>();
const pendingPacks = new Map<string, Promise<Record<string, string>>>();
let activePacks = 0;
const packQueue: (() => void)[] = [];
async function decodedBytes(path: string, signal?: AbortSignal | null) {
  const response = await fetch(path, { signal });
  if (!response.ok) throw new Error("This release's aggregate file could not load. Retry the same investigation; no different evidence was substituted.");
  let bytes = await response.arrayBuffer();
  const magic = new Uint8Array(bytes);
  // Hosts may return raw .gz objects or transparently decode Content-Encoding.
  if (magic[0] === 0x1f && magic[1] === 0x8b) {
    if (typeof DecompressionStream === "undefined") throw new Error("This browser cannot unpack published evidence. Update your browser or download the aggregate package.");
    bytes = await new Response(new Blob([bytes]).stream().pipeThrough(new DecompressionStream("gzip"))).arrayBuffer();
  }
  return bytes;
}
async function verifyObjectHash(bytes: ArrayBuffer, hash?: string) {
  if (!hash) return;
  if (!/^[a-f0-9]{64}$/.test(hash) || typeof crypto === "undefined" || !crypto.subtle) throw new Error("The published evidence integrity check is unavailable or invalid.");
  const actual = Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", bytes))).map(value => value.toString(16).padStart(2, "0")).join("");
  if (actual !== hash) throw new Error("The published evidence failed its integrity check. Retry after the current deployment completes.");
}
async function loadObjectPack(marker: { path: string; sha256: string; key: string }, signal?: AbortSignal | null) {
  const path = publicAsset(marker.path), key = path + ":" + marker.sha256;
  const cached = packCache.get(key);
  if (cached) { packCache.delete(key); packCache.set(key, cached); return cached; }
  if (pendingPacks.has(key)) return pendingPacks.get(key)!;
  if (!/^[a-f0-9]{64}$/.test(marker.sha256)) throw new Error("The published evidence pack hash is invalid.");
  const pending = (async () => {
    if (activePacks >= 4) await new Promise<void>(resolve => packQueue.push(resolve));
    else activePacks++;
    try {
      const bytes = await decodedBytes(path, signal);
      if (bytes.byteLength > 16 * 1024 * 1024) throw new Error("The published evidence pack exceeds the reader size limit.");
      await verifyObjectHash(bytes, marker.sha256);
      const payload = JSON.parse(new TextDecoder().decode(bytes)) as { objects?: unknown };
      if (!payload.objects || typeof payload.objects !== "object" || Array.isArray(payload.objects) || Object.values(payload.objects).some(value => typeof value !== "string")) throw new Error("The published evidence pack is invalid.");
      const objects = payload.objects as Record<string, string>;
      packCache.set(key, objects);
      while (packCache.size > 8) packCache.delete(packCache.keys().next().value!);
      return objects;
    } finally { const next = packQueue.shift(); if (next) next(); else activePacks--; }
  })();
  pendingPacks.set(key, pending);
  try { return await pending; } finally { pendingPacks.delete(key); }
}
export async function loadPublishedObject(entry: string | { path: string; sha256?: string; encoding?: string }, signal?: AbortSignal | null, depth = 0): Promise<unknown> {
  if (depth > 40) throw new Error("The published evidence reference depth is invalid.");
  const path = publicAsset(typeof entry === "string" ? entry : entry.path), hash = typeof entry === "string" ? undefined : entry.sha256, key = path + ":" + (hash || "");
  if (objectCache.has(key)) return objectCache.get(key)!;
  const pending = (async () => {
    const originalPath = path.slice(publicAsset("").length), packedEntry = manifest?.object_packs?.[originalPath];
    let packed: { path: string; sha256: string; key: string } | undefined;
    if (typeof packedEntry === "number") {
      if (!Number.isSafeInteger(packedEntry) || packedEntry < 0 || !manifest?.packs?.[packedEntry]) throw new Error("The published evidence pack index is invalid.");
      packed = { ...manifest.packs[packedEntry], key: originalPath };
    } else packed = packedEntry;
    let bytes: ArrayBuffer;
    if (packed) {
      if (packed.key !== originalPath || publicAsset(packed.path) === path || !hash) throw new Error("The published evidence pack does not identify this exact object.");
      const objects = await loadObjectPack(packed, signal);
      if (!Object.hasOwn(objects, originalPath)) throw new Error("This exact aggregate object is missing from its published evidence pack.");
      bytes = new TextEncoder().encode(objects[originalPath]).buffer;
    } else bytes = await decodedBytes(path, signal);
    await verifyObjectHash(bytes, hash);
    return hydratePublishedJSON(JSON.parse(new TextDecoder().decode(bytes)), signal, depth + 1);
  })();
  objectCache.set(key, pending);
  if (objectCache.size > 384) objectCache.delete(objectCache.keys().next().value!);
  try { return await pending; } catch (error) { objectCache.delete(key); throw error; }
}
export async function hydratePublishedJSON(value: unknown, signal?: AbortSignal | null, depth = 0): Promise<unknown> {
  if (depth > 40) throw new Error("The published evidence reference depth is invalid.");
  if (Array.isArray(value)) return Promise.all(value.map(item => hydratePublishedJSON(item, signal, depth + 1)));
  if (!value || typeof value !== "object") return value;
  const object = value as Record<string, unknown>;
  if (typeof object.$public_ref === "string" && Object.keys(object).every(key => ["$public_ref", "sha256", "bytes"].includes(key))) return loadPublishedObject({ path: object.$public_ref, sha256: typeof object.sha256 === "string" ? object.sha256 : undefined }, signal, depth + 1);
  if (Array.isArray(object.$public_chunks) && Object.keys(object).every(key => key === "$public_chunks")) {
    const arrays = await Promise.all(object.$public_chunks.map(chunk => hydratePublishedJSON(chunk, signal, depth + 1)));
    if (arrays.some(array => !Array.isArray(array))) throw new Error("A published evidence array chunk is invalid.");
    return arrays.flatMap(array => array as unknown[]);
  }
  const entries = await Promise.all(Object.entries(object).map(async ([key, child]) => [key, await hydratePublishedJSON(child, signal, depth + 1)] as const));
  return Object.fromEntries(entries);
}
