/** Winner lead and partisan margin are distinct quantities. Keep signed geometry explicit. */
export function signedPartisanMargin(row: {
  rep_share_pct?: number | null;
  dem_share_pct?: number | null;
}): number | null {
  return typeof row.rep_share_pct === "number" &&
    typeof row.dem_share_pct === "number"
    ? row.rep_share_pct - row.dem_share_pct
    : null;
}
export interface OptionInput {
  id?: string;
  name: string;
  party: string;
  votes: number | null;
  share_pct?: number | null;
  partial_suppression?: boolean;
}
export interface DistributionInput {
  contest_id?: string;
  partial_suppression?: boolean;
  options: OptionInput[];
}
export function summarizeOptions(rows: DistributionInput[]) {
  const mixed = new Set(rows.map((r) => r.contest_id).filter(Boolean)).size > 1;
  const complete =
    !mixed &&
    rows.every(
      (r) =>
        !r.partial_suppression &&
        r.options.every(
          (o) =>
            !o.partial_suppression &&
            typeof o.votes === "number" &&
            Number.isFinite(o.votes) &&
            o.share_pct != null,
        ),
    );
  const map = new Map<
    string,
    {
      id: string;
      name: string;
      party: string;
      votes: number;
      observed: boolean;
    }
  >();
  if (!mixed)
    rows.forEach((row) =>
      row.options.forEach((option) => {
        const key = option.id || option.name + "|" + option.party,
          prev = map.get(key) || {
            id: option.id || "",
            name: option.name,
            party: option.party,
            votes: 0,
            observed: false,
          };
        if (typeof option.votes === "number" && Number.isFinite(option.votes)) {
          prev.votes += option.votes;
          prev.observed = true;
        }
        map.set(key, prev);
      }),
    );
  const options = [...map.values()].sort((a, b) => b.votes - a.votes),
    total = options.reduce((sum, o) => sum + o.votes, 0);
  return {
    mixed,
    complete,
    total,
    options: options.map((o) => ({
      ...o,
      share_pct: complete && total > 0 ? (o.votes / total) * 100 : null,
    })),
  };
}
