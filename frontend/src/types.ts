export type Page =
  | "overview"
  | "states"
  | "atlas"
  | "history"
  | "polls"
  | "scenarios"
  | "forecasts"
  | "notebook"
  | "reports"
  | "sources"
  | "elections"
  | "place";
export type TimeBasis = "reported" | "reconstructed" | "final";
export interface ResearchQuery {
  state: string;
  cycle: number;
  baseline: number;
  as_of: string;
  time_basis: TimeBasis;
  revision?: number;
  metric: string;
  mode: string;
  geography_ids: string[];
  alignment: string;
  category_dimension?: string;
  category?: string;
  date_window?: string[];
}
export interface Metric {
  id?: string;
  key?: string;
  metric?: string;
  name?: string;
  label?: string;
  definition?: string;
  unit?: string;
  description?: string;
  supported_dimensions?: string[];
  valid_aggregation?: string;
  warnings?: string[];
}
export interface Race {
  id?: string;
  state: string;
  name?: string;
  state_name?: string;
  cycle?: number;
  race_id?: string;
  special?: boolean;
  battleground?: boolean;
  watchlist?: boolean;
  election_system?: string;
  election_date?: string;
  electoral_system?: string;
  candidates?: { name: string; party: string; verified?: boolean }[];
  notes?: string;
  [key: string]: unknown;
}
export interface Observation {
  id?: number;
  state: string;
  cycle: number;
  election_date: string;
  date: string;
  metric: string;
  value: number;
  geography_id: string;
  geography_name: string;
  geography_type: string;
  mode: string;
  category_dimension?: string | null;
  category?: string | null;
  unit: string;
  time_basis: TimeBasis;
  published_at?: string | null;
  denominator?: number | null;
  snapshot_id?: number;
  source_id?: string;
  metadata?: Record<string, unknown>;
}
export interface Source {
  id: string;
  state: string;
  name: string;
  url: string;
  kind?: string;
  source_type?: string;
  status?: string;
  connector?: string;
  enabled?: boolean;
  last_checked?: string | null;
  last_changed?: string | null;
  last_success?: string | null;
  data_as_of?: string | null;
  observation_count?: number;
  notes?: string;
  description?: string;
  warnings?: string[];
  last_error?: string | null;
  latest_snapshot_id?: number;
  [key: string]: unknown;
}
export interface PollEstimate {
  candidate?: string;
  name?: string;
  party?: string;
  value?: number;
  percent?: number;
  support?: number;
  [key: string]: unknown;
}
export interface Poll {
  id?: number;
  study_id: string;
  state: string;
  cycle: number;
  producer: string;
  sponsor: string;
  publisher: string;
  field_start: string;
  field_end: string;
  published_at: string;
  population: string;
  sample_size?: number | null;
  methodology: string;
  question_type: string;
  ballot_type: string;
  question: string;
  estimates: PollEstimate[];
  margin_of_error?: number | null;
  partisan_sponsor: boolean;
  source_url: string;
  document_url?: string | null;
  crosstabs?: Record<string, unknown>[];
  snapshot_id?: number;
  metadata?: Record<string, unknown>;
}
export interface OverviewState {
  state: string;
  name?: string;
  value?: number | null;
  latest_value?: number | null;
  total?: number | null;
  data_as_of?: string | null;
  date?: string | null;
  source_count?: number;
  observation_count?: number;
  poll_count?: number;
  status?: string;
  warnings?: string[];
  [key: string]: unknown;
}
export interface Bootstrap {
  cycles?: number[];
  app?: { name: string; version: string; election_date: string; today: string };
  revision?: number;
  latest_revision?: number;
  races: Race[];
  sources?: Source[];
  metrics: Metric[];
  states?: {
    code: string;
    name: string;
    fips: string;
    watchlist: boolean;
    seat_party: string;
    election_system: string;
  }[];
  coverage?: unknown;
  app_version?: string;
  election_date?: string;
  [key: string]: unknown;
}
export interface SeriesPoint {
  [key: string]: string | number | null | undefined;
  date: string;
  value?: number;
  cycle?: number;
  days_to_election?: number;
}
export interface BriefSection {
  title: string;
  text?: string;
  body?: string;
  sentences?: {
    text: string;
    observation_ids?: number[];
    source_ids?: string[];
  }[];
  source_ids?: string[];
  [key: string]: unknown;
}
export interface GeoRow {
  id: string;
  canonical_id?: string;
  boundary_id?: string;
  name: string;
  type: string;
  value: number;
  baseline_value: number | null;
  change: number | null;
  share: number | null;
  denominator: number | null;
  source_ids: string[];
  observation_ids: number[];
}
export interface CompositionRow {
  dimension: string;
  category: string;
  value: number;
  metric: string;
  mode: string;
  source_ids: string[];
  observation_ids: number[];
}
export interface NationalRow {
  code: string;
  name: string;
  fips: string;
  watchlist: boolean;
  value: number | null;
  latest_date: string | null;
  source_count: number;
  poll_count: number;
  coverage_status: string;
  metric: string;
}
export interface Workspace {
  revision: number;
  latest_revision?: number;
  series?: SeriesPoint[];
  national?: NationalRow[];
  state?: {
    code: string;
    name: string;
    fips: string;
    watchlist: boolean;
    seat_party: string;
    election_system: string;
  };
  calendar?: { date: string; label: string; source_url: string }[];
  coverage?: {
    status: string;
    available_metrics: string[];
    available_modes: string[];
    available_dimensions: string[];
    available_cycles: number[];
    geographic_count: number;
    as_reported_available: boolean;
    reconstructed_available: boolean;
  };
  composition?: CompositionRow[];
  query: ResearchQuery;
  observations: Observation[];
  historical?: Observation[];
  history?: Observation[];
  polls?: Poll[];
  sources?: Source[];
  summary?: Record<string, unknown>;
  comparison?: Record<string, unknown>;
  brief?:
    | { title?: string; sections: BriefSection[]; [key: string]: unknown }
    | BriefSection[];
  geographies?: GeoRow[];
  warnings: string[];
  availability?: Record<string, unknown>;
  polling?: Record<string, unknown>;
  forecasts?: Record<string, unknown>;
  [key: string]: unknown;
}
export interface ResearchObject {
  id: number;
  kind: string;
  title: string;
  body?: string;
  payload?: Record<string, unknown>;
  view?: Record<string, unknown>;
  created_at?: string;
  updated_at?: string;
}
export interface SourceSnapshot {
  id: number;
  source_id: string;
  url: string;
  sha256: string;
  retrieved_at: string;
  published_at?: string;
  data_as_of?: string;
  status?: string;
  byte_count?: number;
  [key: string]: unknown;
}
export interface Evidence {
  source?: Source;
  snapshot?: SourceSnapshot;
  observation?: Observation;
  observations?: Observation[];
  revisions?: unknown[];
  warnings?: string[];
  [key: string]: unknown;
}
export interface Job {
  id: number;
  kind: string;
  status: string;
  created_at?: string;
  started_at?: string;
  finished_at?: string;
  error?: string;
  result?: Record<string, unknown>;
  progress?: {
    stage?: string;
    message?: string;
    completed?: number;
    total?: number;
    [key: string]: unknown;
  };
  [key: string]: unknown;
}
export interface AppContext {
  bootstrap: Bootstrap;
  workspace: Workspace;
  query: ResearchQuery;
  selectedGeographyIds?: string[];
  selectionScope?: "view_local";
  setQuery: (patch: Partial<ResearchQuery>) => void;
  setPage: (page: Page) => void;
  inspect: (item: {
    type: "source" | "observation" | "poll";
    id: string | number;
    data?: unknown;
  }) => void;
  notify: (message: string) => void;
  refresh: () => void;
  refreshing: boolean;
  researchQuestion?: string;
  resultYear?: number;
  resultOffice?: string;
  setResearchQuestion?: (value: string) => void;
  setResultYear?: (value: number) => void;
  setResultOffice?: (value: string) => void;
}
