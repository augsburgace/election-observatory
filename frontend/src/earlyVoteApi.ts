import { publicFetch } from "./publicData";
import { params } from "./atlasApi";
export interface EVCall {
  race_id: string;
  state: string;
  state_name: string;
  watchlist: boolean;
  office: string;
  special?: boolean;
  election_system?: string;
  call: {
    margin_pp: number | null;
    range_low_pp: number | null;
    range_high_pp: number | null;
    direction: string;
    label: string;
    status: "ev_informed" | "reference_only" | "unavailable";
    candidate_verification?: string;
  };
  evidence: {
    early_vote: {
      total: number | null;
      date: string | null;
      metric_label: string;
      metric: string;
      mode: string;
      source_refs: Record<string, unknown>[];
      coverage: Record<string, unknown>;
      unit?: string;
      report_date_verified?: boolean;
      native_date_caveats?: string[];
    };
    historical_reference: {
      margin_pp: number | null;
      cycles: {
        year: number;
        margin_pp: number;
        weight: number;
        total_votes: number;
        contest_name: string;
        contest_id: string;
        source_refs: Record<string, unknown>[];
      }[];
      description: string;
      source_refs: Record<string, unknown>[];
    };
    geographic_tilt: {
      available: boolean;
      tilt_pp: number | null;
      reference_kind: string;
      same_stage: boolean;
      matched_areas: number;
      coverage_pct: number | null;
      statewide_coverage_pct?: number | null;
      coefficient: number;
      adjustment_pp: number | null;
      description: string;
      reference_office?: string;
      reference_year?: number;
      rows: {
        id: string;
        name: string;
        early_votes: number;
        early_share_pct: number;
        reference_share_pct: number;
        reference_margin_pp: number;
        contribution_pp: number;
        current_source_date: string;
        reference_count?: number;
        source_refs?: Record<string, unknown>[];
      }[];
    };
    same_stage?: SameStageEvidence;
    turnout_projection?: TurnoutProjection;
    composition: {
      dimension: string;
      category: string;
      value: number;
      date: string;
      metric: string;
      mode: string;
      source_ids: string[];
      observation_ids: number[];
    }[];
    polls: { count?: number; [key: string]: unknown };
  };
  confidence?: CallConfidence;
  sensitivity?: CallSensitivity;
  explanation: string[];
  assumptions: string[];
  warnings: string[];
  sources: Record<string, unknown>[];
  manifest: Record<string, unknown>;
}
export interface EarlyVoteCalls {
  revision: number;
  as_of: string;
  model_version: string;
  calls: EVCall[];
  selected: EVCall | null;
  validation: Record<string, unknown>;
  backtesting?: EVBacktesting;
  warnings: string[];
}
export async function earlyVoteCalls(
  query: Record<string, unknown>,
  signal?: AbortSignal,
): Promise<EarlyVoteCalls> {
  const response = await publicFetch(
    "/api/v2/forecasts/early-vote?" + params(query),
    { signal },
  );
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(
      typeof body.detail === "string"
        ? body.detail
        : `Research call service returned ${response.status}`,
    );
  }
  return response.json();
}
export { marginCallLabel } from "./researchCallMath";

export interface SameStageEvidence {
  alignment: string;
  target_date: string;
  stage: number | string | null;
  comparisons: SameStageComparison[];
  explanation: string;
}
export interface SameStageComparison {
  cycle: number;
  target_date?: string | null;
  report_date?: string | null;
  total?: number | null;
  current_total?: number | null;
  metric: string;
  mode: string;
  ratio?: number | null;
  coverage_pct?: number | null;
  status: string;
  reason?: string;
  chronology?: string;
  source_refs?: Record<string, unknown>[];
}
export interface CallConfidence {
  grade: string;
  label: string;
  reason: string;
  validated_probability: boolean;
  independent_validation_cycles: number;
  checks: { label: string; status: string; detail: string }[];
}
export interface CallSensitivity {
  parameters: {
    id: string;
    label: string;
    default: number;
    min: number;
    max: number;
    unit: string;
    description: string;
  }[];
  points: {
    coefficient: number;
    margin_pp: number | null;
    adjustment_pp: number;
  }[];
  stress_tests: {
    label: string;
    margin_pp: number | null;
    delta_pp: number | null;
    explanation: string;
  }[];
  range_kind: string;
}
export interface EVBacktestCase {
  case_id?: string;
  reference_kind?: string;
  fitted_margin_pp?: number | null;
  fitted_error_pp?: number | null;
  state: string;
  year: number;
  contest_id: string;
  cutoff: string;
  alignment: string;
  stage: number | string | null;
  metric: string;
  mode: string;
  chronology: string;
  baseline_margin_pp: number;
  predicted_margin_pp: number;
  actual_margin_pp: number;
  error_pp: number;
  baseline_error_pp: number;
  feature_tilt_pp?: number | null;
  coefficient?: number | null;
  coefficient_status?: string;
  input_refs?: Record<string, unknown>[];
  training_cycles?: number[];
  training_contests?: number;
  range_low_pp?: number | null;
  range_high_pp?: number | null;
  range_kind?: string;
}
export interface BacktestMetrics {
  cases?: number;
  margin_mae_pp?: number | null;
  margin_rmse_pp?: number | null;
  margin_bias_pp?: number | null;
  winner_accuracy?: number | null;
  direction_accuracy?: number | null;
  interval_80_coverage?: number | null;
  interval_95_coverage?: number | null;
  sensitivity_range_coverage?: number | null;
  [key: string]: unknown;
}
export interface EVBacktesting {
  model_version: string;
  method: string;
  status: string;
  metrics: {
    historical_reference?: BacktestMetrics;
    fixed_ev_assumption?: BacktestMetrics;
    fitted_ev?: BacktestMetrics;
  };
  cases: EVBacktestCase[];
  exclusions: {
    state: string;
    year: number;
    alignment?: string;
    stage?: number | string | null;
    reason: string;
  }[];
  grouped_metrics?: Record<string, unknown> | Record<string, unknown>[];
  turnout?: TurnoutBacktesting;
  independent_cycles: number[];
  independent_contests: number;
  trained_ev_holdout_cases: number;
  strict_contemporary_cases: number;
  probabilities_published: boolean;
  warnings: string[];
  manifest: Record<string, unknown>;
}

export interface EVStagePoint {
  date: string;
  value: number;
  days_to_election: number | null;
  days_since_opening: number | null;
  newly_reported?: number | null;
  carried_forward_count?: number;
  geography_count?: number;
  oldest_component_date?: string;
  sources?: Record<string, unknown>[];
}
export interface EVStageCycle {
  cycle: number;
  election_type: string;
  target_date: string | null;
  observed_date: string | null;
  age_days: number | null;
  value: number | null;
  available: boolean;
  alignment_available: boolean;
  same_stage: boolean;
  reason: string;
  pace_ratio: number | null;
  grain: string;
  trajectory: EVStagePoint[];
  calendar?: Record<string, unknown> | null;
  chronology: {
    basis: string;
    description: string;
    original_time_bases: string[];
    reconstruction_types: string[];
    latest_known_at: string | null;
  };
  matched?: {
    coverage?: Record<string, unknown>;
    ratio?: number | null;
    [key: string]: unknown;
  } | null;
  source_refs: Record<string, unknown>[];
  warnings: string[];
}
export interface HistoricalFinalParticipation {
  cycle: number;
  value: number;
  date: string;
  election_type: string;
  definition: string;
  source_refs: Record<string, unknown>[];
  alternate_source_values?: { value: number; source_id: string }[];
}
export interface TurnoutScenario {
  name: string;
  reference_cycle: number;
  multiplier: number;
  assumed_final_participation: number;
  consistent: boolean;
  reported_early_participation: number | null;
  remaining_participation: number | null;
  early_share_of_assumed_final_pct: number | null;
  interpretation: string;
}
export interface EVStageHistory {
  schema: string;
  revision: number;
  query: {
    state: string;
    cycle: number;
    as_of: string;
    metric: string;
    mode: string;
    alignment: string;
    history_basis: string;
    baseline_cycles: number[];
  };
  metric_definition: {
    id: string;
    unit: string;
    description?: string;
    name?: string;
  };
  units: string;
  current: {
    available: boolean;
    date: string | null;
    cutoff: string;
    value: number | null;
    metric: string;
    mode: string;
    grain: string;
    days_to_election: number;
    days_since_opening: number | null;
    age_days: number | null;
    calendar: Record<string, unknown> | null;
    trajectory: EVStagePoint[];
    mode_values?: EVModeValue[];
    source_refs: Record<string, unknown>[];
  };
  cycles: EVStageCycle[];
  coverage: {
    requested_cycles: number;
    available_cycles: number;
    same_stage_cycles: number;
  };
  turnout: {
    registration_denominator: {
      value: number;
      date: string;
      definition: string;
      participation_rate_pct: number;
      source_refs: Record<string, unknown>[];
    } | null;
    historical_final_participation: HistoricalFinalParticipation[];
    scenarios: TurnoutScenario[];
    scenario_reference: HistoricalFinalParticipation | null;
    forecast_status: string;
    warnings: string[];
  };
  warnings: string[];
}
export async function earlyVoteHistory(
  query: Record<string, unknown>,
  signal?: AbortSignal,
): Promise<EVStageHistory> {
  const response = await publicFetch("/api/v2/early-vote/history?" + params(query), {
    signal,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(
      typeof body.detail === "string"
        ? body.detail
        : `Historical EV service returned ${response.status}`,
    );
  }
  return response.json();
}

export interface EVModeValue {
  mode: string;
  metric: string;
  value: number;
  date: string;
  grain: string;
  definition: string[];
  classification: string[];
  source_refs: Record<string, unknown>[];
  aggregation_policy: string;
}
export interface TurnoutProjection {
  available: boolean;
  projection: number | null;
  remaining_participation: number | null;
  current_total?: number;
  prior_cycles: number[];
  inputs: {
    year: number;
    early_total: number;
    final_total: number;
    stage_fraction: number;
    report_date: string;
    source_refs: Record<string, unknown>[];
  }[];
  range_low: number | null;
  range_high: number | null;
  range_kind: string;
  validated_forecast: boolean;
  range_includes_model_error: boolean;
  reason: string;
  metric?: string;
  mode?: string;
  alignment?: string;
  stage?: number;
  report_date?: string;
  method?: string;
}
export interface TurnoutBacktesting {
  status: string;
  cases: {
    case_id: string;
    state: string;
    year: number;
    alignment: string;
    stage: number;
    cutoff: string;
    chronology: string;
    predicted_turnout: number;
    actual_turnout: number;
    error_ballots: number;
    percentage_error: number;
    prior_cycles: number[];
    [key: string]: unknown;
  }[];
  exclusions: Record<string, unknown>[];
  metrics: {
    cases: number;
    independent_state_cycles: number;
    independent_cycles: number;
    mean_absolute_percentage_error: number | null;
    mean_absolute_error_ballots: number | null;
    rmse_ballots: number | null;
  };
  grouped_metrics: Record<string, unknown>[];
  warnings: string[];
}

export interface EvidenceReference {
  url?: string;
  source_url?: string;
  title?: string;
  name?: string;
  source_id?: string;
  snapshot_id?: number;
  [key: string]: unknown;
}
export interface ReasoningStudy {
  producer: string;
  field_start?: string;
  field_end?: string;
  population?: string;
  sample_size?: number | null;
  question?: string;
  ballot_type?: string;
  estimates?: { candidate?: string; party?: string; value?: number | null }[];
  source_url?: string;
  document_url?: string;
  source_refs?: EvidenceReference[];
  secondary_summary?: boolean;
}
export interface ReasoningMarket {
  party?: string;
  outcome_label?: string;
  price_pct?: number | null;
  quote_at?: string;
  provider_updated_at?: string;
  best_bid?: number | null;
  best_ask?: number | null;
  settlement_rules?: string;
  provider?: string;
  question?: string;
  liquidity_usd?: number | null;
  volume_usd?: number | null;
  source_url?: string;
  display_url?: string;
  source_refs?: EvidenceReference[];
  definition?: string;
}
export interface ReasoningSignal {
  status: string;
  reason?: string;
  summary?: string;
  studies?: ReasoningStudy[];
  markets?: ReasoningMarket[];
  items?: Record<string, unknown>[];
  source_refs?: EvidenceReference[];
}
export interface EVReasoning {
  revision: number;
  as_of: string;
  state: string;
  mode: "ev_only" | "expanded";
  switches: { polls: boolean; markets: boolean; context: boolean };
  headline: string;
  summary: string;
  paragraphs: {
    title: string;
    text: string;
    evidence_refs?: EvidenceReference[];
  }[];
  drivers: {
    label: string;
    role: "measured" | "historical" | "assumption" | "external";
    value?: string | number | null;
    text: string;
    direction?: "DEM" | "REP" | "neutral" | null;
  }[];
  signals: {
    polls?: ReasoningSignal;
    markets?: ReasoningSignal;
    context?: ReasoningSignal;
  };
  ev_call: EVCall;
  warnings: string[];
  source_refs: EvidenceReference[];
  method: Record<string, unknown>;
  manifest: Record<string, unknown>;
}
export interface FeatureTestMetrics {
  margin_mae_pp?: number | null;
  mae_pp?: number | null;
  cases?: number;
  independent_contests?: number;
  [key: string]: unknown;
}
export interface EVFeatureExperiment {
  id: string;
  chronology?: string;
  alignment?: string;
  reference_kind?: string;
  comparator?: "historical_baseline" | "geography_only";
  label?: string;
  features: string[];
  status: string;
  paired: {
    baseline?: FeatureTestMetrics;
    geography_only?: FeatureTestMetrics;
    augmented?: FeatureTestMetrics;
  };
  origins: {
    training_years: number[];
    reason?: string;
    [key: string]: unknown;
  }[];
  cases: Record<string, unknown>[];
  exclusions: unknown[];
  promotion: { promoted: boolean; reason: string };
}
export interface EVFeatureTests {
  version: string;
  revision: number;
  as_of: string;
  status: string;
  feature_inventory: {
    id: string;
    label: string;
    definition: string;
    available_cases: number;
    available_state_cycles: number;
    missing_cases: number;
    source_refs: EvidenceReference[];
  }[];
  experiments: EVFeatureExperiment[];
  headline_experiments?: EVFeatureExperiment[];
  geographic_feature_inventory?: EVFeatureTests["feature_inventory"];
  coverage_scope?: {
    states: string[];
    statewide_cases: number;
    geographic_cases: number;
    inventory_family: string;
  };
  warnings: string[];
  manifest: Record<string, unknown>;
}
async function forecastService<T>(
  path: string,
  query: Record<string, unknown>,
  signal?: AbortSignal,
): Promise<T> {
  const response = await publicFetch(path + "?" + params(query), { signal });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(
      typeof body.detail === "string"
        ? body.detail
        : `Forecast research service returned ${response.status}`,
    );
  }
  return response.json();
}
export function earlyVoteReasoning(
  query: Record<string, unknown>,
  signal?: AbortSignal,
) {
  return forecastService<EVReasoning>(
    "/api/v2/forecasts/reasoning",
    query,
    signal,
  );
}
export function earlyVoteFeatureTests(
  query: Record<string, unknown>,
  signal?: AbortSignal,
) {
  return forecastService<EVFeatureTests>(
    "/api/v2/forecasts/feature-tests",
    query,
    signal,
  );
}
