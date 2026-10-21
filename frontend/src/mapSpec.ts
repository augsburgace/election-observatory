import type { GeoRow } from "./types";
export type MapLayer =
  | "volume"
  | "share"
  | "change"
  | "participation"
  | "coverage"
  | "margin"
  | "swing"
  | "context";
export interface MapSpec {
  layer: MapLayer;
  domain: [number, number];
  colors: string[];
  bins: number[];
  unit: string;
  label: string;
  max: number;
  value: (row: MapMetricRow) => number | null;
  color: (value: number | null) => string;
  radius: (value: number) => number;
}
export type MapMetricRow = Omit<GeoRow, "value"> & { value: number | null };
export const SEQUENTIAL = [
  "#d7f1ef",
  "#91d6d0",
  "#3cb4b0",
  "#138f96",
  "#086776",
];
export const DIVERGING = [
  "#ad491d",
  "#db8752",
  "#f2c29f",
  "#eef0ec",
  "#b2dcd4",
  "#4bb6a8",
  "#087d7b",
];
export const PARTISAN = [
  "#1559be",
  "#377dd7",
  "#96baef",
  "#edeaf0",
  "#f3a1b0",
  "#e64e68",
  "#c41439",
];
export function createMapSpec(
  rows: MapMetricRow[],
  layer: MapLayer,
  scaleMax?: number,
  overrides?: {
    label?: string;
    unit?: string;
    domain?: [number, number];
    bins?: number[];
    colors?: string[];
  },
): MapSpec {
  const value = (r: MapMetricRow): number | null =>
    layer === "share"
      ? r.share == null
        ? null
        : r.share * 100
      : layer === "change" || layer === "margin" || layer === "swing"
        ? r.change
        : layer === "participation"
          ? r.denominator && r.value != null
            ? (r.value / r.denominator) * 100
            : null
          : r.value;
  const vals = rows
    .map(value)
    .filter((v): v is number => v != null && Number.isFinite(v));
  const diverging = ["change", "margin", "swing"].includes(layer);
  const max = Math.max(scaleMax || 0, ...vals.map(Math.abs), 1);
  const domain: [number, number] =
    overrides?.domain || (diverging ? [-max, max] : [0, max]);
  const colors =
    overrides?.colors ||
    (layer === "margin" || layer === "swing"
      ? PARTISAN
      : diverging
        ? DIVERGING
        : SEQUENTIAL);
  const bins =
    overrides?.bins ||
    Array.from(
      { length: colors.length + 1 },
      (_, i) => domain[0] + ((domain[1] - domain[0]) * i) / colors.length,
    );
  const color = (v: number | null) =>
    v == null
      ? "var(--map-missing)"
      : layer === "volume"
        ? "var(--map-land)"
        : layer === "coverage"
          ? "#32a69d"
          : colors[
              Math.min(
                colors.length - 1,
                Math.max(
                  0,
                  bins.slice(1).findIndex((threshold) => v < threshold) < 0
                    ? colors.length - 1
                    : bins.slice(1).findIndex((threshold) => v < threshold),
                ),
              )
            ];
  return {
    layer,
    domain,
    colors,
    bins,
    max,
    unit:
      overrides?.unit ??
      (["share", "participation"].includes(layer)
        ? "%"
        : ["margin", "swing"].includes(layer)
          ? "pp"
          : ""),
    label:
      overrides?.label ??
      {
        volume: "Reported ballots",
        share: "Share of geographic activity",
        change: "Matched historical change",
        participation: "Participation rate",
        coverage: "Observation coverage",
        margin: "Republican − Democratic margin",
        swing: "Change in Republican − Democratic margin",
        context: "Population context estimate",
      }[layer],
    value,
    color,
    radius: (v) => (v > 0 ? 24 * Math.sqrt(v / max) : 0),
  };
}
