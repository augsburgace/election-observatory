import type { EVCall, EVBacktestCase } from "./earlyVoteApi";
import type { GeoRow, NationalRow } from "./types";
export type ForecastMapLayer = "volume" | "margin" | "contribution";
/** Render only the exact model input rows; never allocate state evidence to smaller areas. */
export function forecastMapRows(
  call: EVCall,
  layer: ForecastMapLayer,
): GeoRow[] {
  return call.evidence.geographic_tilt.rows.map((row) => ({
    id: row.id,
    canonical_id: row.id,
    name: row.name,
    type: "county",
    value: row.early_votes,
    baseline_value: row.reference_count ?? null,
    change:
      layer === "margin"
        ? row.reference_margin_pp
        : layer === "contribution"
          ? row.contribution_pp
          : null,
    share: row.early_share_pct / 100,
    denominator: null,
    source_ids: [
      ...new Set(
        (row.source_refs || [])
          .map((ref) => String(ref.source_id || ""))
          .filter(Boolean),
      ),
    ],
    observation_ids: (row.source_refs || [])
      .map((ref) => ref.observation_id)
      .filter(
        (id): id is number =>
          typeof id === "number" && Number.isInteger(id) && id > 0,
      ),
  }));
}
/** Multi-contest states are withheld from the margin map unless that exact race is selected. */
export function nationalCallRows(
  calls: EVCall[],
  selectedRace?: string,
): NationalRow[] {
  const states = [...new Set(calls.map((call) => call.state))];
  return states.map((code) => {
    const races = calls.filter((call) => call.state === code);
    const race =
      races.length === 1
        ? races[0]
        : races.find((call) => call.race_id === selectedRace);
    return {
      code,
      name: races[0].state_name,
      fips: "",
      watchlist: races.some((call) => call.watchlist),
      value: race?.call.margin_pp ?? null,
      latest_date: race?.evidence.early_vote.date ?? null,
      source_count: race?.sources.length || 0,
      poll_count: race?.evidence.polls?.count || 0,
      coverage_status: race?.call.status || "multiple_contests",
      metric: "conditional_party_margin",
    };
  });
}
export function uniqueBacktestContests(cases: EVBacktestCase[]) {
  return new Set(
    cases.map((row) => `${row.state}:${row.year}:${row.contest_id}`),
  ).size;
}
export function selectedCaseMetrics(cases: EVBacktestCase[]) {
  if (!cases.length) return null;
  const counts = new Map<string, number>();
  const key = (row: EVBacktestCase) =>
    `${row.state}:${row.year}:${row.contest_id}`;
  cases.forEach((row) => counts.set(key(row), (counts.get(key(row)) || 0) + 1));
  const contests = counts.size;
  const weighted = (fn: (row: EVBacktestCase) => number) =>
    cases.reduce((sum, row) => sum + fn(row) / counts.get(key(row))!, 0) /
    contests;
  return {
    cases: cases.length,
    contests,
    mae: weighted((row) => Math.abs(row.error_pp)),
    referenceMae: weighted((row) => Math.abs(row.baseline_error_pp)),
    bias: weighted((row) => row.error_pp),
  };
}

/** Recharts event records differ by mark family; unwrap only an actual object payload. */
export function forecastChartRecord(
  value: unknown,
): Record<string, unknown> | null {
  if (!value || typeof value !== "object") return null;
  const record = value as Record<string, unknown>;
  return record.payload && typeof record.payload === "object"
    ? (record.payload as Record<string, unknown>)
    : record;
}
