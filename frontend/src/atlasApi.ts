import { publicFetch } from "./publicData";
import type { ResearchQuery, Job, GeoRow } from "./types";
import type { FeatureCollection, Geometry, GeoJsonProperties } from "geojson";
import type { PairedPlace } from "./atlasDepthMath";
export interface ResultsComparison {
  current: Results;
  baseline: Results;
  rows: PairedPlace[];
  eligible: boolean;
  coverage: Record<string, unknown>;
  warnings: string[];
  sources: Record<string, unknown>[];
  revision: number;
}
export interface PrecinctDataset {
  id: string;
  title: string;
  state: string;
  year: number;
  status: string;
  loaded: boolean;
  source_url: string;
  provider: string;
  offices: string[];
  coverage: Record<string, unknown>;
  warnings: string[];
}
export interface PrecinctMapData extends FeatureCollection<
  Geometry,
  GeoJsonProperties
> {
  revision: number;
  coverage: Record<string, unknown>;
  legend: Record<string, unknown>;
  sources: Record<string, unknown>[];
  warnings: string[];
  query: Record<string, unknown>;
  availability: Record<string, unknown>;
  unmapped_results?: {
    id: string;
    name: string;
    total_votes: number;
    contest_id?: string;
    source_refs: Record<string, unknown>[];
  }[];
  contests?: Contest[];
  boundary_vintage?: string;
}
export interface AtlasOption {
  kind?: string;
  partial_suppression?: boolean;
  id: string;
  name: string;
  party: string;
  votes: number;
  share_pct: number;
}
export interface ResultGeo {
  contest_id?: string;
  partial_suppression?: boolean;
  id: string;
  name: string;
  level: string;
  total_votes: number;
  options: AtlasOption[];
  winner: string | AtlasOption | null;
  margin_pp: number | null;
  dem_share_pct: number | null;
  rep_share_pct: number | null;
  baseline_margin_pp: number | null;
  swing_pp: number | null;
  source_refs: Record<string, unknown>[];
}
export interface Contest {
  id: string;
  name?: string;
  title?: string;
  state?: string;
  year?: number;
  office?: string;
  election_type?: string;
  district?: string;
  date?: string;
  options?: AtlasOption[];
  [key: string]: unknown;
}
export interface Results {
  pagination?: {
    total_geographies: number;
    has_more: boolean;
    offset?: number;
    limit?: number;
  };
  revision: number;
  query: Record<string, unknown>;
  contests: Contest[];
  summary: Record<string, unknown>;
  geographies: ResultGeo[];
  history: Record<string, unknown>[];
  warnings: string[];
  coverage: Record<string, unknown>;
  sources: Record<string, unknown>[];
}
export interface Dataset {
  id: string;
  title: string;
  producer: string;
  tier: number;
  url: string;
  license: string;
  years: number[];
  states: string[];
  offices: string[];
  geography_levels: string[];
  status: string;
  loaded_states: string[];
  record_count: number;
  warnings: string[];
  on_demand: boolean;
}
export interface CatalogState {
  code: string;
  name: string;
  fips: string;
  watchlist: boolean;
  years: number[];
  offices: string[];
  geography_levels: string[];
  result_count: number;
  latest_results: Record<string, unknown> | null;
  coverage: Record<string, unknown>;
}
export interface PlaceSeries {
  id: string;
  name: string;
  points?: {
    date: string;
    value: number;
    cycle?: number;
    [key: string]: unknown;
  }[];
  series?: {
    date: string;
    value: number;
    cycle?: number;
    [key: string]: unknown;
  }[];
}
export interface Analytics {
  geographic_research?: {
    waterfall: GeoRow[];
    concentration: Record<string, unknown>[];
  };
  revision: number;
  query: Record<string, unknown>;
  series_by_place: PlaceSeries[];
  rankings: Record<string, unknown>[];
  waterfall: Record<string, unknown>[];
  concentration: Record<string, unknown>[];
  endpoints: Record<string, unknown>[];
  coverage_matrix: Record<string, unknown>[];
  summary: Record<string, unknown>;
  warnings: string[];
  sources: Record<string, unknown>[];
}
async function v2<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await publicFetch("/api/v2" + path, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!r.ok) {
    const p = await r.json().catch(() => ({}));
    throw new Error(
      typeof p.detail === "string"
        ? p.detail
        : `Research service returned ${r.status}`,
    );
  }
  return r.json();
}
export function params(o: Record<string, unknown>) {
  const p = new URLSearchParams();
  Object.entries(o).forEach(([k, v]) => {
    if (v != null && v !== "")
      p.set(k, Array.isArray(v) ? v.join(",") : String(v));
  });
  return p.toString();
}
export const atlasApi = {
  comparisons: (q: Record<string, unknown>, signal?: AbortSignal) =>
    v2<ResultsComparison>("/comparisons/results?" + params(q), { signal }),
  precinctCatalog: (state: string, revision?: number) =>
    v2<{ datasets: PrecinctDataset[]; revision: number }>(
      "/precincts/catalog?" + params({ state, revision }),
    ),
  precinctMap: (q: Record<string, unknown>, signal?: AbortSignal) =>
    v2<PrecinctMapData>("/precincts/map?" + params(q), { signal }),
  loadPrecincts: (id: string) =>
    v2<Job>("/precincts/" + encodeURIComponent(id) + "/load", {
      method: "POST",
      body: JSON.stringify({}),
    }),
  contests: (query: Record<string, unknown>) =>
    v2<{
      revision: number;
      total: number;
      contests: Contest[];
      offset: number;
      limit: number;
    }>("/catalog/contests?" + params(query)),
  states: () =>
    v2<{ revision: number; states: CatalogState[] }>("/catalog/states"),
  datasets: (state?: string) =>
    v2<{ revision: number; datasets: Dataset[] }>(
      "/catalog/datasets" + (state ? "?state=" + state : ""),
    ),
  results: (q: Record<string, unknown>, signal?: AbortSignal) =>
    v2<Results>("/results?" + params(q), { signal }),
  context: (state: string, revision?: number) =>
    v2<Record<string, unknown>>(
      "/context?state=" +
        state +
        (revision != null ? "&revision=" + revision : ""),
    ),
  search: (q: string) =>
    v2<Record<string, unknown>>("/search?q=" + encodeURIComponent(q)),
  place: (
    id: string,
    state: string,
    revision?: number,
    year?: number,
    office?: string,
    participation?: ResearchQuery,
    historyOffset = 0,
  ) =>
    v2<Record<string, unknown>>(
      "/places/" +
        encodeURIComponent(id) +
        "?" +
        params({
          ...participation,
          state,
          revision,
          year,
          office,
          history_offset: historyOffset,
        }),
    ),
  analytics: (q: ResearchQuery, signal?: AbortSignal) =>
    v2<Analytics>(
      "/analytics?" + params(q as unknown as Record<string, unknown>),
      { signal },
    ),
  load: (id: string, state?: string) =>
    v2<Job>("/datasets/" + encodeURIComponent(id) + "/load", {
      method: "POST",
      body: JSON.stringify({ state }),
    }),
};
