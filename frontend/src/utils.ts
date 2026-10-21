import type {
  Observation,
  PollEstimate,
  Race,
  ResearchQuery,
  Source,
} from "./types";
export const STATE_NAMES: Record<string, string> = {
  AL: "Alabama",
  AK: "Alaska",
  AZ: "Arizona",
  AR: "Arkansas",
  CA: "California",
  CO: "Colorado",
  CT: "Connecticut",
  DE: "Delaware",
  FL: "Florida",
  GA: "Georgia",
  HI: "Hawaii",
  ID: "Idaho",
  IL: "Illinois",
  IN: "Indiana",
  IA: "Iowa",
  KS: "Kansas",
  KY: "Kentucky",
  LA: "Louisiana",
  ME: "Maine",
  MD: "Maryland",
  MA: "Massachusetts",
  MI: "Michigan",
  MN: "Minnesota",
  MS: "Mississippi",
  MO: "Missouri",
  MT: "Montana",
  NE: "Nebraska",
  NV: "Nevada",
  NH: "New Hampshire",
  NJ: "New Jersey",
  NM: "New Mexico",
  NY: "New York",
  NC: "North Carolina",
  ND: "North Dakota",
  OH: "Ohio",
  OK: "Oklahoma",
  OR: "Oregon",
  PA: "Pennsylvania",
  RI: "Rhode Island",
  SC: "South Carolina",
  SD: "South Dakota",
  TN: "Tennessee",
  TX: "Texas",
  UT: "Utah",
  VT: "Vermont",
  VA: "Virginia",
  WA: "Washington",
  WV: "West Virginia",
  WI: "Wisconsin",
  WY: "Wyoming",
  DC: "District of Columbia",
};
export const BATTLEGROUNDS = [
  "AK",
  "FL",
  "GA",
  "IA",
  "KS",
  "ME",
  "MI",
  "MN",
  "NE",
  "NH",
  "NC",
  "OH",
  "SC",
  "TX",
];
export const COLORS = [
  "#099f9a",
  "#9365d9",
  "#d39318",
  "#327bd2",
  "#5e9b60",
  "#df7152",
];
export const CYCLE_COLORS: Record<number, string> = {
  2026: COLORS[0],
  2024: COLORS[1],
  2022: COLORS[3],
  2020: COLORS[2],
  2018: COLORS[4],
};

export const MODE_COLORS: Record<string, string> = {
  all: "var(--muted)",
  early_in_person: "var(--cyan)",
  mail: "var(--violet)",
  civilian_mail: "#a26bbb",
  military_mail: "var(--gold)",
  overseas_mail: "#be752d",
  uocava: "#9e7439",
};
export const fmt = (n: unknown, digits = 0) =>
  typeof n === "number" && Number.isFinite(n)
    ? new Intl.NumberFormat("en-US", { maximumFractionDigits: digits }).format(
        n,
      )
    : "—";
export const compact = (n: unknown) =>
  typeof n === "number" && Number.isFinite(n)
    ? new Intl.NumberFormat("en-US", {
        notation: "compact",
        maximumFractionDigits: 1,
      }).format(n)
    : "—";
export const pct = (n: unknown, digits = 1) =>
  typeof n === "number" && Number.isFinite(n) ? `${n.toFixed(digits)}%` : "—";
export function dateLabel(date?: string | null) {
  if (!date) return "Not yet available";
  const parsed = new Date(date.length === 10 ? `${date}T12:00:00` : date);
  return Number.isNaN(parsed.getTime())
    ? date
    : parsed.toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
        year: "numeric",
        timeZone: "America/New_York",
      });
}
export const human = (s?: string | null) =>
  (s || "Unknown")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
export const stateName = (s: string) => STATE_NAMES[s] || s;
export const raceName = (race: Race) =>
  race.name || race.state_name || stateName(race.state);
export const numberValue = (...values: unknown[]) =>
  values.find((v) => typeof v === "number") as number | undefined;
export function latestGeographies(rows: Observation[]) {
  const map = new Map<string, Observation>();
  for (const row of rows) {
    const key = [
      row.geography_id,
      row.mode,
      row.category_dimension || "",
      row.category || "",
    ].join("|");
    if (!map.has(key) || map.get(key)!.date < row.date) map.set(key, row);
  }
  return [...map.values()];
}
export function baseRows(rows: Observation[], query: ResearchQuery) {
  return rows.filter(
    (r) =>
      r.cycle === query.cycle &&
      r.metric === query.metric &&
      r.mode === query.mode &&
      !r.category_dimension &&
      (!query.geography_ids.length ||
        query.geography_ids.includes(r.geography_id)),
  );
}
export function statewideRows(rows: Observation[]) {
  return rows.filter(
    (r) =>
      r.geography_type === "state" && !r.category_dimension && r.mode === "all",
  );
}
export function latestStatewide(rows: Observation[]) {
  return statewideRows(rows).sort((a, b) => b.date.localeCompare(a.date))[0];
}
export function observedGroups(rows: Observation[], cycle: number) {
  return latestGeographies(
    rows.filter(
      (r) =>
        r.cycle === cycle &&
        r.geography_type !== "state" &&
        !r.category_dimension,
    ),
  );
}
export const sourceStatus = (source: Source) =>
  source.status ||
  (source.last_error
    ? "error"
    : source.last_success
      ? "current"
      : "not_collected");
export const estimateValue = (e: PollEstimate) =>
  numberValue(e.value, e.percent, e.support) ?? Number.NaN;
export const estimateName = (e: PollEstimate) =>
  e.candidate || e.name || "Response";
export const partyColor = (party?: string) =>
  party?.toUpperCase().startsWith("D")
    ? "#165fe0"
    : party?.toUpperCase().startsWith("R")
      ? "#e6254d"
      : "#9b66cc";
export function supportedRaces(races: Race[]) {
  const selected = races.filter(
    (r) => r.battleground === true || r.watchlist === true,
  );
  const list = selected.length
    ? selected
    : races.filter((r) => BATTLEGROUNDS.includes(r.state));
  return list.filter(
    (race, index, all) =>
      all.findIndex((other) => other.state === race.state) === index,
  );
}

export function inputDate(value?: string | null) {
  if (!value) return "";
  if (value.length === 10) return value;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "";
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/New_York",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(parsed);
}
