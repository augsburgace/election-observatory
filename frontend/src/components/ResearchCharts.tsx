import { useMemo } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { GeoRow, Observation } from "../types";
import type { PlaceSeries, ResultGeo } from "../atlasApi";
import { COLORS, compact, fmt, partyColor } from "../utils";
import { Empty } from "./ui";
import { openEntity } from "./EntityInspector";
import { signedPartisanMargin, summarizeOptions } from "../chartMath";
const ticks = { fontSize: 11, fill: "var(--muted)" },
  grid = { stroke: "var(--chart-grid)", strokeDasharray: "3 3" };
const tip = {
  background: "var(--popover)",
  border: "1px solid var(--border)",
  color: "var(--text)",
  fontSize: 13,
  borderRadius: 5,
};
export function PlaceTrajectories({
  series,
  observations = [],
  selected = [],
}: {
  series?: PlaceSeries[];
  observations?: Observation[];
  selected?: string[];
}) {
  const rows = useMemo(() => {
    const all = (
      series?.length
        ? series
        : selected.slice(0, 8).map((id) => ({
            id,
            name:
              observations.find((o) => o.geography_id === id)?.geography_name ||
              id,
            points: observations.filter(
              (o) =>
                o.geography_id === id &&
                !o.category_dimension &&
                o.mode === "all",
            ),
          }))
    ).map((p) => ({
      ...p,
      points: p.points || ("series" in p ? p.series : []) || [],
    }));
    const valid = all
      .filter(
        (p) => (!selected.length || selected.includes(p.id)) && p.points.length,
      )
      .slice(0, 8);
    const by = new Map<string, Record<string, string | number>>();
    valid.forEach((p) =>
      p.points.forEach((pt) => {
        const row = by.get(pt.date) || { date: pt.date };
        row[p.id] = pt.value;
        by.set(pt.date, row);
      }),
    );
    return {
      data: [...by.values()].sort((a, b) =>
        String(a.date).localeCompare(String(b.date)),
      ),
      places: valid,
    };
  }, [series, observations, selected]);
  if (!rows.data.length)
    return (
      <Empty
        title={
          selected.length
            ? "No trajectory is published for these places"
            : "Select places to compare"
        }
      >
        Choose reporting areas on the map or in the table. Each place retains
        its own series.
      </Empty>
    );
  return (
    <div className="chart" style={{ height: 285 }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart
          data={rows.data}
          margin={{ left: 0, right: 15, top: 15, bottom: 10 }}
        >
          <CartesianGrid {...grid} vertical={false} />
          <XAxis
            dataKey="date"
            tick={ticks}
            tickFormatter={(v) => String(v).slice(5)}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            tick={ticks}
            tickFormatter={compact}
            width={48}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip contentStyle={tip} formatter={(v) => fmt(v)} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          {rows.places.map((p, i) => (
            <Line
              key={p.id}
              dataKey={p.id}
              name={p.name}
              stroke={COLORS[i % COLORS.length]}
              type="stepAfter"
              strokeWidth={2.5}
              dot={rows.data.length < 3}
              connectNulls={false}
              isAnimationActive={false}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
export function ContributionWaterfall({
  rows,
  onSelect,
}: {
  rows: GeoRow[];
  onSelect?: (id: string) => void;
}) {
  let running = 0;
  const top = [...rows]
    .filter((r) => r.change != null)
    .sort((a, b) => Math.abs(b.change!) - Math.abs(a.change!))
    .slice(0, 12)
    .map((row) => {
      const native = row as GeoRow & { start?: number; end?: number };
      const start = native.start ?? running,
        end = native.end ?? start + row.change!;
      running = end;
      return { ...row, range: [Math.min(start, end), Math.max(start, end)] };
    });
  if (!top.length)
    return (
      <Empty title="A comparable reported change is needed">
        Two compatible observations are required to attribute newly reported
        change to particular places.
      </Empty>
    );
  return (
    <>
      <div className="chart" style={{ height: 330 }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={top} layout="vertical" margin={{ right: 25 }}>
            <CartesianGrid {...grid} horizontal={false} />
            <XAxis type="number" tick={ticks} tickFormatter={compact} />
            <YAxis type="category" dataKey="name" tick={ticks} width={105} />
            <Tooltip
              contentStyle={tip}
              formatter={(_v, _name, item) => [
                fmt((item.payload as { change: number }).change),
                "Contribution to reported change",
              ]}
            />
            <ReferenceLine x={0} stroke="var(--border-strong)" />
            <Bar
              dataKey="range"
              onClick={(r) => onSelect?.(String(r.id))}
              radius={2}
              maxBarSize={17}
            >
              {top.map((r) => (
                <Cell
                  key={r.id}
                  fill={r.change! < 0 ? "var(--orange)" : "var(--teal)"}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <p className="chart-axis-note">
        Largest {top.length} place contributions, accumulated in order. Negative
        changes may be source corrections. This is reported change, not
        voting-day activity.
      </p>
    </>
  );
}
export function ConcentrationChart({ rows }: { rows: GeoRow[] }) {
  const all = [...rows]
      .filter((r) => r.value >= 0)
      .sort((a, b) => b.value - a.value),
    total = all.reduce((n, r) => n + r.value, 0);
  let running = 0;
  const data = [
    { places: 0, share: 0 },
    ...all.map((r, i) => {
      running += r.value;
      return {
        places: ((i + 1) / all.length) * 100,
        share: total ? (running / total) * 100 : 0,
      };
    }),
  ];
  if (!total)
    return (
      <Empty title="Geographic concentration needs reported values">
        Validated source observations are needed for this view.
      </Empty>
    );
  return (
    <div className="chart" style={{ height: 250 }}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart
          data={data}
          margin={{ left: 0, right: 15, top: 15, bottom: 10 }}
        >
          <CartesianGrid {...grid} />
          <XAxis
            dataKey="places"
            type="number"
            domain={[0, 100]}
            tick={ticks}
            tickFormatter={(v) => `${v}%`}
          />
          <YAxis
            domain={[0, 100]}
            tick={ticks}
            tickFormatter={(v) => `${v}%`}
            width={45}
          />
          <Tooltip contentStyle={tip} formatter={(v) => `${fmt(v, 1)}%`} />
          <Area
            dataKey="share"
            name="Cumulative share of reported ballots"
            stroke="var(--violet)"
            fill="var(--violet)"
            fillOpacity={0.17}
            strokeWidth={2}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
export function HistoricalScatter({
  rows,
  onSelect,
}: {
  rows: ResultGeo[];
  onSelect?: (s: string) => void;
}) {
  const data = rows
    .map((r) => ({ ...r, rep_margin_pp: signedPartisanMargin(r) }))
    .filter((r) => r.rep_margin_pp != null);
  if (!data.length)
    return (
      <Empty title="Historical geographic results unavailable">
        Validated source observations are needed for this view.
      </Empty>
    );
  return (
    <div className="chart" style={{ height: 275 }}>
      <ResponsiveContainer width="100%" height="100%">
        <ScatterChart margin={{ left: 5, right: 20, top: 10, bottom: 10 }}>
          <CartesianGrid {...grid} />
          <XAxis
            type="number"
            dataKey="rep_margin_pp"
            name="Republican − Democratic margin"
            unit=" pp"
            tick={ticks}
          />
          <YAxis
            type="number"
            dataKey="total_votes"
            name="Votes cast"
            tick={ticks}
            tickFormatter={compact}
            width={50}
          />
          <Tooltip
            contentStyle={tip}
            formatter={(v, n) => [fmt(v, n === "Partisan margin" ? 1 : 0), n]}
            labelFormatter={() => ""}
          />
          <ReferenceLine x={0} stroke="var(--border-strong)" />
          <Scatter
            data={data}
            name="Reporting areas"
            onClick={(r) =>
              onSelect?.(
                String((r as unknown as { payload: ResultGeo }).payload?.id),
              )
            }
          >
            {data.map((r) => (
              <Cell
                key={r.id}
                fill={r.rep_margin_pp! > 0 ? "#e6254d" : "#165fe0"}
                opacity={0.7}
              />
            ))}
          </Scatter>
        </ScatterChart>
      </ResponsiveContainer>
    </div>
  );
}
export function VoteDistribution({ rows }: { rows: ResultGeo[] }) {
  const distribution = summarizeOptions(rows),
    data = distribution.options;
  if (distribution.mixed)
    return (
      <Empty title="Choose one contest">
        Different districts, rounds, or ballot-measure contests cannot be pooled
        into a candidate-share distribution.
      </Empty>
    );
  if (!data.length)
    return (
      <Empty title="Candidate results are not loaded">
        Validated source observations are needed for this view.
      </Empty>
    );
  return (
    <>
      {distribution.complete && (
        <div className="vote-share-band">
          {data.map((r) => (
            <div
              key={r.id || r.name}
              style={{
                width: `${r.share_pct || 0}%`,
                background: partyColor(r.party),
              }}
              title={`${r.name}: ${fmt(r.votes)} (${fmt(r.share_pct, 1)}%)`}
            />
          ))}
        </div>
      )}
      {!distribution.complete && (
        <p className="chart-axis-note">
          Published counts are incomplete or suppressed. Percentages and the
          share band are withheld; known counts are lower bounds.
        </p>
      )}
      <div className="vote-distribution">
        {data.map((r) => (
          <div key={r.id || r.name}>
            <i style={{ background: partyColor(r.party) }} />
            <span>
              <button
                className="candidate-name-button"
                onClick={() => r.id && openEntity(r.id)}
              >
                {r.name}
              </button>
              <small>{r.party || "Nonpartisan"}</small>
            </span>
            <b>{r.share_pct == null ? "—" : fmt(r.share_pct, 1) + "%"}</b>
            <span>{r.observed ? fmt(r.votes) : "Not published"}</span>
          </div>
        ))}
      </div>
    </>
  );
}
export function ReportingCalendar({
  observations,
}: {
  observations: Observation[];
}) {
  const dates = new Map<string, number>();
  observations
    .filter(
      (o) =>
        o.geography_type === "state" &&
        o.mode === "all" &&
        !o.category_dimension,
    )
    .forEach((o) =>
      dates.set(o.date, Math.max(dates.get(o.date) || 0, o.value)),
    );
  const list = [...dates.entries()].sort(([a], [b]) => a.localeCompare(b));
  if (list.length < 2)
    return (
      <Empty title="Daily source history is not yet established">
        Validated source observations are needed for this view.
      </Empty>
    );
  const max = Math.max(
    ...list.map(([, v], i) => (i ? v - list[i - 1][1] : 0)),
    1,
  );
  return (
    <div className="reporting-calendar">
      {list.map(([date, value], i) => {
        const delta = i ? value - list[i - 1][1] : 0;
        return (
          <div key={date} title={`${date}: ${fmt(delta)} newly reported`}>
            <time>{date.slice(5)}</time>
            <span
              style={{
                background:
                  delta < 0
                    ? "var(--orange)"
                    : `color-mix(in srgb, var(--teal) ${15 + (Math.max(0, delta) / max) * 85}%, var(--panel))`,
              }}
            >
              <b>{i ? compact(delta) : "Start"}</b>
            </span>
          </div>
        );
      })}
    </div>
  );
}
export function EndpointLadder({
  observations,
  cycle,
}: {
  observations: Observation[];
  cycle: number;
}) {
  const map = new Map<number, Observation>();
  observations
    .filter(
      (o) =>
        o.geography_type === "state" &&
        o.mode === "all" &&
        !o.category_dimension,
    )
    .forEach((o) => {
      if (!map.has(o.cycle) || map.get(o.cycle)!.date < o.date)
        map.set(o.cycle, o);
    });
  const data = [...map.values()].sort((a, b) => a.cycle - b.cycle);
  if (data.length < 2)
    return (
      <Empty title="Another cycle is needed for endpoint references">
        Validated source observations are needed for this view.
      </Empty>
    );
  return (
    <div className="endpoint-ladder">
      {data.map((o) => (
        <div key={o.cycle}>
          <b>{o.cycle}</b>
          <span>
            <i
              style={{
                width: `${(o.value / Math.max(...data.map((r) => r.value), 1)) * 100}%`,
                background: o.cycle === cycle ? "var(--cyan)" : "var(--violet)",
              }}
            />
          </span>
          <strong>{compact(o.value)}</strong>
          <small>{o.date}</small>
        </div>
      ))}
    </div>
  );
}
export function HistoricalShareChart({
  history,
}: {
  history: Record<string, unknown>[];
}) {
  const data = history
    .filter((r) => r.dem_share_pct != null || r.rep_share_pct != null)
    .sort((a, b) => Number(a.year) - Number(b.year));
  if (!data.length)
    return (
      <Empty title="Historical series unavailable">
        The source catalog records the years and offices that have been loaded.
      </Empty>
    );
  return (
    <div className="chart" style={{ height: 250 }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart
          data={data}
          margin={{ top: 12, right: 18, left: 0, bottom: 5 }}
        >
          <CartesianGrid {...grid} vertical={false} />
          <XAxis
            dataKey="year"
            tick={ticks}
            minTickGap={25}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            domain={[0, 100]}
            tick={ticks}
            tickFormatter={(v) => `${v}%`}
            width={38}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip contentStyle={tip} formatter={(v) => `${fmt(v, 1)}%`} />
          <Legend
            iconType="circle"
            iconSize={7}
            wrapperStyle={{ fontSize: 11 }}
          />
          <Line
            name="Democratic"
            dataKey="dem_share_pct"
            stroke="#165fe0"
            strokeWidth={2.2}
            dot={{ r: 2.5 }}
            isAnimationActive={false}
          />
          <Line
            name="Republican"
            dataKey="rep_share_pct"
            stroke="#e6254d"
            strokeWidth={2.2}
            dot={{ r: 2.5 }}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
