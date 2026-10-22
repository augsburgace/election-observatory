import { publicFetch } from "./publicData";
import { params } from "./atlasApi";
export type ResearchOffice = "US SENATE" | "US HOUSE" | "GOVERNOR";
export const officeLabel = (office: string) =>
  office === "US HOUSE"
    ? "U.S. House"
    : office === "GOVERNOR"
      ? "Governor"
      : "U.S. Senate";
export interface OfficeResult {
  year: number;
  margin_pp: number | null;
  total_votes: number;
  contest_id: string;
  contest_name: string;
  district: string;
  boundary_vintage: string;
  geography_level: string;
  geography_id: string;
  round: string;
  election_system: string;
  margin_status: string;
  source_refs: Record<string, unknown>[];
  options: {
    id: string;
    name: string;
    party: string | null;
    votes: number | null;
    share_pct: number | null;
  }[];
}
export interface OfficeRace {
  id: string;
  race_id: string;
  state: string;
  state_name: string;
  office: Exclude<ResearchOffice, "US SENATE">;
  name: string;
  district: number | null;
  at_large: boolean;
  election_system: string;
  election_date: string;
  possible_runoff_date: string | null;
  candidate_verification: string;
  watchlist: boolean;
  history: OfficeResult[];
  history_range: number[];
  latest_result: OfficeResult | null;
  historical_reference: {
    margin_pp: number | null;
    description: string;
    scope: string;
    cycles: (OfficeResult & { weight: number })[];
  };
  call: {
    status: string;
    margin_pp: number | null;
    direction: string | null;
    label: string;
  };
  finding: string;
  warnings: string[];
  validation: {
    ev_model_promoted: boolean;
    ev_backtest_cases: number;
    reason: string;
  };
}
export interface OfficeDesk {
  revision: number;
  as_of: string;
  cycle: number;
  office: OfficeRace["office"];
  model_version: string;
  calls: OfficeRace[];
  coverage: {
    scheduled_races: number;
    states: number;
    races_with_history: number;
    states_with_history: number;
    ev_forecasts: number;
  };
  sources: Record<string, unknown>[];
  registry_sources: { title: string; url: string }[];
  scope_note: string;
  chronology_note: string;
  validation?: {
    metrics: { cases: number; margin_mae_pp: number | null };
    cases: {
      state: string;
      year: number;
      predicted_margin_pp: number;
      actual_margin_pp: number;
      error_pp: number;
    }[];
    methodology: string;
    timestamp_limitations: string;
  } | null;
}
export async function officeDesk(
  query: Record<string, unknown>,
  signal?: AbortSignal,
): Promise<OfficeDesk> {
  const response = await publicFetch(
    "/api/v2/forecasts/offices?" + params(query),
    { signal },
  );
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(
      typeof body.detail === "string"
        ? body.detail
        : "The office evidence desk could not be loaded.",
    );
  }
  return response.json();
}
