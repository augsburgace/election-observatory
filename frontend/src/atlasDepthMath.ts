/** Shared, deterministic chart transforms. Missing evidence never becomes zero. */
export interface PairedPlace {
  id: string;
  name: string;
  current_votes: number | null;
  baseline_votes: number | null;
  current_margin_pp: number | null;
  baseline_margin_pp: number | null;
  change_pp: number | null;
  eligible: boolean;
  reason?: string | null;
}
export function quantileThresholds(values: number[]): [number, number] {
  const sorted = values.filter(Number.isFinite).sort((a, b) => a - b);
  if (!sorted.length) return [0, 0];
  const quantile = (p: number) => {
    const i = (sorted.length - 1) * p,
      lo = Math.floor(i),
      hi = Math.ceil(i);
    return sorted[lo] + (sorted[hi] - sorted[lo]) * (i - lo);
  };
  return [quantile(1 / 3), quantile(2 / 3)];
}
export function quantileBin(value: number, thresholds: [number, number]) {
  return value <= thresholds[0] ? 0 : value <= thresholds[1] ? 1 : 2;
}
export const BIVARIATE_COLORS = [
  ["#e8e8e8", "#ace4e4", "#5ac8c8"],
  ["#dfb0d6", "#a5add3", "#5698b9"],
  ["#be64ac", "#8c62aa", "#3b4994"],
];
export function pairedDifferences(rows: PairedPlace[]) {
  return rows.filter(
    (r) =>
      r.eligible &&
      r.current_margin_pp != null &&
      r.baseline_margin_pp != null &&
      r.change_pp != null,
  );
}
export function marginHistogram(values: (number | null)[], width = 10) {
  const data = Array.from({ length: Math.ceil(200 / width) }, (_, i) => ({
    start: -100 + i * width,
    end: Math.min(100, -100 + (i + 1) * width),
    count: 0,
  }));
  values.forEach((value) => {
    if (value == null || !Number.isFinite(value) || value < -100 || value > 100)
      return;
    data[Math.min(data.length - 1, Math.floor((value + 100) / width))].count++;
  });
  return data.map((row) => ({
    ...row,
    label: `${row.start} to ${row.end}`,
    midpoint: (row.start + row.end) / 2,
  }));
}
export function sharedMarginMaximum(rows: PairedPlace[]) {
  return Math.max(
    1,
    ...rows
      .flatMap((row) => [row.current_margin_pp, row.baseline_margin_pp])
      .filter((v): v is number => v != null && Number.isFinite(v))
      .map(Math.abs),
  );
}
