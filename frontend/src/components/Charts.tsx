import { useMemo } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  Brush,
  CartesianGrid,
  Cell,
  ComposedChart,
  Legend,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type {
  CompositionRow,
  GeoRow,
  Observation,
  SeriesPoint,
} from "../types";
import {
  COLORS,
  CYCLE_COLORS,
  compact,
  dateLabel,
  fmt,
  human,
  pct,
} from "../utils";
import { Empty } from "./ui";
import { focusGeography, useFocusedGeography } from "../interaction";
const grid = { stroke: "var(--chart-grid)", strokeDasharray: "3 3" };
const tooltipStyle = {
  background: "var(--popover)",
  border: "1px solid var(--border-strong)",
  borderRadius: 6,
  color: "var(--text)",
  fontSize: 12,
  boxShadow: "0 12px 30px #0003",
};
function ChartTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: readonly {
    name?: string | number;
    value?: number | string;
    color?: string;
  }[];
  label?: string | number;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="chart-tooltip">
      <strong>
        {typeof label === "number" ? `${label} days to Election Day` : label}
      </strong>
      {payload.map((p, i) => (
        <div key={`${p.name}-${i}`}>
          <span style={{ color: p.color }}>●</span>
          {human(String(p.name))}
          <b>{typeof p.value === "number" ? fmt(p.value) : p.value}</b>
        </div>
      ))}
    </div>
  );
}
export function SeriesChart({
  series,
  observations = [],
  alignment = "days_to_election",
  cutoff,
  onRange,
  height = 245,
  brush = false,
}: {
  series?: SeriesPoint[];
  observations?: Observation[];
  alignment?: string;
  cutoff?: string;
  onRange?: (start: string, end: string) => void;
  height?: number;
  brush?: boolean;
}) {
  const data = useMemo(() => {
    const input = series?.length
      ? series
      : observations
          .filter((o) => o.geography_type === "state" && !o.category_dimension)
          .map((o) => ({
            date: o.date,
            value: o.value,
            cycle: o.cycle,
            days_to_election: Math.round(
              (new Date(o.date).getTime() -
                new Date(o.election_date).getTime()) /
                86400000,
            ),
          }));
    const grouped = new Map<string, Record<string, string | number>>();
    input.forEach((point) => {
      if (typeof point.value !== "number" || !Number.isFinite(point.value))
        return;
      const authoritativeX = "x" in point ? point.x : undefined;
      const coordinate =
        alignment === "days_to_election"
          ? (authoritativeX ?? point.days_to_election)
          : authoritativeX;
      const numericAlignment = alignment !== "calendar";
      if (
        numericAlignment &&
        (typeof coordinate !== "number" || !Number.isFinite(coordinate))
      )
        return;
      const x = numericAlignment ? String(coordinate) : point.date;
      const entry = grouped.get(x) || {
        x,
        sort: numericAlignment
          ? Number(coordinate)
          : new Date(point.date).getTime(),
      };
      entry[String(point.cycle)] = point.value;
      entry[`date_${point.cycle}`] = point.date;
      grouped.set(x, entry);
    });
    return [...grouped.values()].sort(
      (a, b) => Number(a.sort) - Number(b.sort),
    );
  }, [series, observations, alignment]);
  const cycles = useMemo(
    () =>
      [
        ...new Set(
          (series?.length ? series : observations)
            .map((p) => Number(p.cycle))
            .filter(Boolean),
        ),
      ].sort((a, b) => b - a),
    [series, observations],
  );
  if (!data.length)
    return (
      <Empty title="No comparable trajectory yet">
        {alignment !== "days_to_election" && alignment !== "calendar"
          ? "This alignment requires a verified opening calendar or voting-opportunity index for the selected method. A different method's opening date is never substituted."
          : "This view needs validated observations for the selected metric, cutoff, and evidence chronology. Check source coverage or select an available metric."}
      </Empty>
    );
  return (
    <>
      <div
        style={{ height }}
        className="chart"
        role={brush ? "group" : "img"}
        aria-label={`Cumulative observations for ${cycles.join(", ")}`}
      >
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart
            data={data}
            margin={{ top: 12, right: 14, bottom: 0, left: 0 }}
          >
            <CartesianGrid {...grid} vertical={false} />
            <XAxis
              dataKey="x"
              tick={{ fill: "var(--muted)", fontSize: 10 }}
              tickFormatter={(value) =>
                alignment !== "calendar"
                  ? `${value}${alignment === "voting_opportunities" ? "" : "d"}`
                  : String(value).slice(5)
              }
              minTickGap={30}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              tick={{ fill: "var(--muted)", fontSize: 10 }}
              tickFormatter={compact}
              width={48}
              axisLine={false}
              tickLine={false}
            />
            <Tooltip content={<ChartTooltip />} />
            <Legend
              iconType="circle"
              iconSize={7}
              wrapperStyle={{ fontSize: 11, paddingTop: 12 }}
            />
            {cycles.map((cycle, index) => (
              <Line
                key={cycle}
                name={String(cycle)}
                dataKey={String(cycle)}
                type="stepAfter"
                stroke={CYCLE_COLORS[cycle] || COLORS[index % COLORS.length]}
                strokeWidth={index === 0 ? 2.5 : 2}
                dot={{ r: data.length < 3 ? 4 : 0 }}
                activeDot={{ r: 5, stroke: "var(--panel)", strokeWidth: 2 }}
                connectNulls={false}
                isAnimationActive={false}
              />
            ))}
            {cutoff && alignment === "calendar" && (
              <ReferenceLine
                x={cutoff}
                stroke="var(--text)"
                strokeDasharray="4 4"
              />
            )}
            {brush && data.length > 3 && (
              <Brush
                dataKey="x"
                ariaLabel="Reporting-date window handle. Use arrow keys to adjust the selected observations."
                height={22}
                stroke="var(--border-strong)"
                fill="var(--surface)"
                travellerWidth={6}
                onChange={(range) => {
                  if (
                    onRange &&
                    range.startIndex != null &&
                    range.endIndex != null
                  ) {
                    const observed = data
                      .slice(range.startIndex, range.endIndex + 1)
                      .map((point) => point[`date_${cycles[0]}`])
                      .filter(
                        (date): date is string => typeof date === "string",
                      );
                    if (observed.length)
                      onRange(observed[0], observed[observed.length - 1]);
                  }
                }}
              />
            )}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <div className="chart-axis-note">
        {alignment === "days_to_election"
          ? "Days relative to Election Day"
          : alignment === "calendar"
            ? "Source reporting date"
            : alignment === "voting_opportunities"
              ? "Verified voting-opportunity index"
              : "Days since this voting method opened"}{" "}
        · Step lines join actual observations
      </div>
    </>
  );
}
export function GeographyBars({
  rows,
  onSelect,
  selected = [],
}: {
  rows: GeoRow[];
  onSelect?: (id: string) => void;
  selected?: string[];
}) {
  const focused = useFocusedGeography();
  const data = [...rows].sort((a, b) => b.value - a.value).slice(0, 14);
  if (!data.length)
    return (
      <Empty title="Geographic breakdown unavailable">
        No validated reporting-area totals match this selection.
      </Empty>
    );
  return (
    <div style={{ height: Math.max(250, data.length * 27) }} className="chart">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart
          data={data}
          layout="vertical"
          margin={{ left: 4, right: 25, top: 2, bottom: 0 }}
        >
          <CartesianGrid {...grid} horizontal={false} />
          <XAxis
            type="number"
            tickFormatter={compact}
            tick={{ fontSize: 10, fill: "var(--muted)" }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            type="category"
            dataKey="name"
            width={104}
            tick={{ fontSize: 11, fill: "var(--muted)" }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip
            cursor={{ fill: "var(--hover)" }}
            contentStyle={tooltipStyle}
            formatter={(value) => [fmt(value), "Reported ballots"]}
          />
          <Bar
            dataKey="value"
            radius={[0, 3, 3, 0]}
            maxBarSize={14}
            onClick={(entry) => onSelect?.(String(entry.id))}
            onMouseEnter={(entry) => focusGeography(String(entry.id))}
            onMouseLeave={() => focusGeography(null)}
          >
            {data.map((row, index) => (
              <Cell
                key={row.id}
                fill={
                  selected.includes(row.id) || focused === row.id
                    ? "var(--gold)"
                    : COLORS[index % 2]
                }
                opacity={
                  selected.length && !selected.includes(row.id) ? 0.35 : 1
                }
                cursor={onSelect ? "pointer" : "default"}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
export function CompositionChart({
  rows,
  dimension,
  share = false,
}: {
  rows: CompositionRow[];
  dimension?: string;
  share?: boolean;
}) {
  const filtered = rows.filter((r) => !dimension || r.dimension === dimension);
  const sum = filtered.reduce((a, r) => a + r.value, 0);
  const data = filtered.map((row) => ({
    ...row,
    display: share && sum ? (row.value / sum) * 100 : row.value,
  }));
  if (!data.length)
    return (
      <Empty title="No published composition data">
        Demographic or registration detail appears only when directly supported
        by the source.
      </Empty>
    );
  return (
    <div style={{ height: Math.max(210, data.length * 34) }} className="chart">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart
          data={data}
          layout="vertical"
          margin={{ right: 22, left: 0, top: 10, bottom: 5 }}
        >
          <CartesianGrid {...grid} horizontal={false} />
          <XAxis
            type="number"
            tickFormatter={share ? (v) => `${v}%` : compact}
            tick={{ fontSize: 10, fill: "var(--muted)" }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            type="category"
            dataKey="category"
            width={100}
            tick={{ fontSize: 11, fill: "var(--muted)" }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip
            cursor={{ fill: "var(--hover)" }}
            contentStyle={tooltipStyle}
            formatter={(v) => [
              share ? pct(Number(v)) : fmt(v),
              share ? "Share of reported category totals" : "Reported ballots",
            ]}
          />
          <Bar dataKey="display" maxBarSize={20} radius={[0, 3, 3, 0]}>
            {data.map((_, i) => (
              <Cell key={i} fill={COLORS[i % COLORS.length]} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
export function ModeChart({
  observations,
  cycle,
}: {
  observations: Observation[];
  cycle: number;
}) {
  const map = new Map<string, Observation>();
  observations
    .filter(
      (o) =>
        o.cycle === cycle &&
        o.geography_type === "state" &&
        !o.category_dimension &&
        o.mode !== "all",
    )
    .forEach((row) => {
      if (!map.has(row.mode) || map.get(row.mode)!.date < row.date)
        map.set(row.mode, row);
    });
  // Published mail components must not be counted alongside their aggregate.
  const mailComponents = new Set([
    "civilian_mail",
    "military_mail",
    "overseas_mail",
  ]);
  const hasMailAggregate = map.has("mail");
  const omittedMailComponents =
    hasMailAggregate &&
    [...map.keys()].some((mode) => mailComponents.has(mode));
  const data = [...map.values()]
    .filter((o) => !(hasMailAggregate && mailComponents.has(o.mode)))
    .map((o) => ({
      name: human(o.mode),
      value: o.value,
      date: o.date,
    }));
  if (!data.length)
    return (
      <Empty title="Voting-mode detail unavailable">
        The selected metric has no compatible statewide mode breakdown.
      </Empty>
    );
  return (
    <>
      <div className="chart" style={{ height: 220 }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={data}
            margin={{ left: 0, right: 10, top: 10, bottom: 8 }}
          >
            <CartesianGrid {...grid} vertical={false} />
            <XAxis
              dataKey="name"
              tick={{ fontSize: 10, fill: "var(--muted)" }}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              tickFormatter={compact}
              tick={{ fontSize: 10, fill: "var(--muted)" }}
              width={48}
              axisLine={false}
              tickLine={false}
            />
            <Tooltip
              contentStyle={tooltipStyle}
              formatter={(v) => [fmt(v), "Reported ballots"]}
            />
            <Bar dataKey="value" radius={[3, 3, 0, 0]} maxBarSize={55}>
              {data.map((_, i) => (
                <Cell key={i} fill={COLORS[i % COLORS.length]} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      {omittedMailComponents && (
        <p className="chart-axis-note">
          Mail is the published aggregate and includes its civilian, military,
          and overseas components; those components are not added again.
          Component modes remain available in the Voting method selector.
        </p>
      )}
      <p className="chart-axis-note">
        Reported counts, not percentages. Each mode uses its latest available
        source report; report dates may differ.
      </p>
    </>
  );
}
export function ChangeChart({ series }: { series: SeriesPoint[] }) {
  const current = [...series].sort((a, b) => a.date.localeCompare(b.date));
  const data = current.slice(1).map((p, i) => ({
    date: p.date,
    value: (Number(p.value) || 0) - (Number(current[i].value) || 0),
  }));
  if (!data.length)
    return (
      <Empty title="A second observation is needed">
        Newly reported changes require at least two source snapshots. They are
        not assumed to equal votes cast that day.
      </Empty>
    );
  return (
    <div style={{ height: 200 }} className="chart">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data}>
          <CartesianGrid {...grid} vertical={false} />
          <XAxis
            dataKey="date"
            tickFormatter={(v) => dateLabel(v).replace(", 2026", "")}
            tick={{ fontSize: 10, fill: "var(--muted)" }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            tickFormatter={compact}
            width={45}
            tick={{ fontSize: 10, fill: "var(--muted)" }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip
            contentStyle={tooltipStyle}
            formatter={(v) => [fmt(v), "Newly reported change"]}
          />
          <ReferenceLine y={0} stroke="var(--border-strong)" />
          <Bar dataKey="value" radius={[2, 2, 0, 0]}>
            {data.map((p, i) => (
              <Cell
                key={i}
                fill={p.value < 0 ? "var(--orange)" : "var(--cyan)"}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
export function DistributionChart({
  rows,
}: {
  rows: { x: number; density: number }[];
}) {
  return (
    <div style={{ height: 250 }} className="chart">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={rows}>
          <CartesianGrid {...grid} vertical={false} />
          <XAxis dataKey="x" tick={{ fontSize: 10, fill: "var(--muted)" }} />
          <YAxis tick={{ fontSize: 10, fill: "var(--muted)" }} />
          <Tooltip contentStyle={tooltipStyle} />
          <ReferenceLine x={0} stroke="var(--gold)" />
          <Area
            type="monotone"
            dataKey="density"
            fill="var(--violet)"
            fillOpacity={0.25}
            stroke="var(--violet)"
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
