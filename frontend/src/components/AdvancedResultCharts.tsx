import { useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Results } from "../atlasApi";
import {
  marginHistogram,
  pairedDifferences,
  type PairedPlace,
} from "../atlasDepthMath";
import { focusGeography, useFocusedGeography } from "../interaction";
import { compact, fmt } from "../utils";
import { ConcentrationChart } from "./ResearchCharts";
import { ResearchGuide } from "./ResearchGuide";
import { Empty, Panel, Select } from "./ui";
const ticks = { fontSize: 11, fill: "var(--muted)" },
  tip = {
    background: "var(--popover)",
    border: "1px solid var(--border)",
    color: "var(--text)",
    fontSize: 12,
  };
export function BivariateScatter({
  rows,
  selected,
  onSelect,
}: {
  rows: {
    id: string;
    name: string;
    margin: number;
    income: number;
    moe: unknown;
  }[];
  selected: string[];
  onSelect: (id: string) => void;
}) {
  const focused = useFocusedGeography();
  return (
    <div className="chart" style={{ height: 320 }}>
      <ResponsiveContainer>
        <ScatterChart margin={{ left: 12, right: 24, top: 15, bottom: 25 }}>
          <CartesianGrid stroke="var(--chart-grid)" />
          <XAxis
            type="number"
            dataKey="margin"
            name="Republican − Democratic margin"
            unit=" pp"
            tick={ticks}
            label={{
              value: "Republican − Democratic margin (pp)",
              position: "bottom",
              fontSize: 12,
              fill: "var(--muted)",
            }}
          />
          <YAxis
            type="number"
            dataKey="income"
            name="Median household income"
            tick={ticks}
            tickFormatter={(v) => "$" + compact(v)}
            width={65}
          />
          <ReferenceLine x={0} stroke="var(--border-strong)" />
          <Tooltip
            contentStyle={tip}
            content={({ active, payload }) => {
              const row = payload?.[0]?.payload as
                (typeof rows)[number] | undefined;
              return active && row ? (
                <div className="depth-chart-tooltip">
                  <b>{row.name}</b>
                  <p>{fmt(row.margin, 1)} pp R−D margin</p>
                  <p>${fmt(row.income)} household income</p>
                  <p>
                    {row.moe == null
                      ? "MOE not supplied"
                      : `±$${fmt(row.moe)} · 90% MOE`}
                  </p>
                  <small>ACS 2020–2024 resident context</small>
                </div>
              ) : null;
            }}
          />
          <Scatter
            data={rows}
            onClick={(d) => onSelect(String(d.payload?.id))}
            onMouseEnter={(d) => focusGeography(String(d.payload?.id))}
            onMouseLeave={() => focusGeography(null)}
          >
            {rows.map((r) => (
              <Cell
                key={r.id}
                fill={r.margin > 0 ? "var(--red)" : "var(--blue)"}
                stroke={
                  selected.includes(r.id) || focused === r.id
                    ? "var(--selection)"
                    : "var(--panel)"
                }
                strokeWidth={
                  selected.includes(r.id) || focused === r.id ? 3 : 1
                }
                opacity={0.8}
              />
            ))}
          </Scatter>
        </ScatterChart>
      </ResponsiveContainer>
    </div>
  );
}
export function PairedResultCharts({
  current,
  rows,
  year,
  baseline,
  selected,
  onSelect,
}: {
  current: Results;
  rows: PairedPlace[];
  year: number;
  baseline: number;
  selected: string[];
  onSelect: (id: string) => void;
}) {
  const [sort, setSort] = useState("change"),
    focused = useFocusedGeography();
  const pairs = pairedDifferences(rows),
    chosen = selected.length
      ? pairs.filter((r) => selected.includes(r.id))
      : pairs;
  const ranked = [...chosen]
    .sort((a, b) =>
      sort === "name"
        ? a.name.localeCompare(b.name)
        : sort === "volume"
          ? (b.current_votes || 0) - (a.current_votes || 0)
          : Math.abs(b.change_pp!) - Math.abs(a.change_pp!),
    )
    .slice(0, 16);
  const hist = marginHistogram(
    current.geographies.map((r) =>
      r.rep_share_pct != null && r.dem_share_pct != null
        ? r.rep_share_pct - r.dem_share_pct
        : null,
    ),
  );
  const chartRows = current.geographies.map((r) => ({
    id: r.id,
    name: r.name,
    type: r.level,
    value: r.total_votes,
    baseline_value: null,
    change: null,
    share: null,
    denominator: null,
    source_ids: [],
    observation_ids: [],
  }));
  return (
    <div className="chart-grid atlas-advanced-charts">
      <Panel
        title="How places moved"
        subtitle={`${baseline} (open circle) → ${year} (solid circle) · matched places only`}
      >
        <div className="depth-chart-controls">
          <Select
            label="Rank historical changes"
            value={sort}
            onChange={setSort}
            options={[
              { value: "change", label: "Largest absolute change" },
              { value: "volume", label: "Most candidate votes" },
              { value: "name", label: "Place name" },
            ]}
          />
          <span>
            {selected.length
              ? `${chosen.length} selected compatible places`
              : `${pairs.length} compatible places`}
          </span>
        </div>
        {ranked.length ? (
          <div className="dumbbell-list">
            <div className="dumbbell-scale">
              <span>D +100</span>
              <span>Even</span>
              <span>R +100</span>
            </div>
            {ranked.map((r) => (
              <button
                key={r.id}
                className={`dumbbell-row ${selected.includes(r.id) ? "selected" : ""}`}
                onClick={() => onSelect(r.id)}
                onFocus={() => focusGeography(r.id)}
                onBlur={() => focusGeography(null)}
                onMouseEnter={() => focusGeography(r.id)}
                onMouseLeave={() => focusGeography(null)}
                aria-label={`${r.name}: ${baseline} ${fmt(r.baseline_margin_pp, 1)} pp; ${year} ${fmt(r.current_margin_pp, 1)} pp; change ${fmt(r.change_pp, 1)} pp`}
              >
                <span>{r.name}</span>
                <svg viewBox="0 0 220 26" role="img" aria-hidden="true">
                  <line
                    x1="10"
                    x2="210"
                    y1="13"
                    y2="13"
                    stroke="var(--chart-grid)"
                  />
                  <line
                    x1="110"
                    x2="110"
                    y1="2"
                    y2="24"
                    stroke="var(--border-strong)"
                  />
                  <line
                    x1={110 + r.baseline_margin_pp!}
                    x2={110 + r.current_margin_pp!}
                    y1="13"
                    y2="13"
                    stroke={r.change_pp! > 0 ? "var(--red)" : "var(--blue)"}
                    strokeWidth="3"
                  />
                  <circle
                    cx={110 + r.baseline_margin_pp!}
                    cy="13"
                    r="4"
                    fill="var(--panel)"
                    stroke="var(--violet)"
                    strokeWidth="2"
                  />
                  <circle
                    cx={110 + r.current_margin_pp!}
                    cy="13"
                    r="5"
                    fill={
                      r.current_margin_pp! > 0 ? "var(--red)" : "var(--blue)"
                    }
                  />
                </svg>
                <b>
                  {r.change_pp! > 0 ? "R" : "D"} +
                  {fmt(Math.abs(r.change_pp!), 1)}
                </b>
              </button>
            ))}
          </div>
        ) : (
          <Empty title="Comparable geographic changes are unavailable">
            A reviewed geographic crosswalk, compatible contest, and specified
            voting round are required. Original election maps remain available.
          </Empty>
        )}
        <ResearchGuide
          what="The change in each matched place's Republican-minus-Democratic vote-share margin."
          how="Follow the open baseline circle to the solid current circle. Rightward movement is toward Republican; leftward movement is toward Democratic. Votes and residents are separate quantities."
          source="Shared results-comparison service, with row-level crosswalk and source eligibility."
        />
      </Panel>
      <Panel
        title="Election-to-election transition"
        subtitle={`${baseline} horizontal · ${year} vertical · matching reporting areas`}
      >
        {pairs.length ? (
          <div className="chart" style={{ height: 340 }}>
            <ResponsiveContainer>
              <ScatterChart
                margin={{ left: 10, right: 20, top: 12, bottom: 25 }}
              >
                <CartesianGrid stroke="var(--chart-grid)" />
                <XAxis
                  type="number"
                  dataKey="baseline_margin_pp"
                  domain={[-100, 100]}
                  name={`${baseline} R−D`}
                  unit=" pp"
                  tick={ticks}
                />
                <YAxis
                  type="number"
                  dataKey="current_margin_pp"
                  domain={[-100, 100]}
                  name={`${year} R−D`}
                  unit=" pp"
                  tick={ticks}
                  width={55}
                />
                <ReferenceLine
                  segment={[
                    { x: -100, y: -100 },
                    { x: 100, y: 100 },
                  ]}
                  stroke="var(--muted)"
                  strokeDasharray="4 4"
                />
                <ReferenceLine x={0} stroke="var(--border-strong)" />
                <ReferenceLine y={0} stroke="var(--border-strong)" />
                <Tooltip
                  contentStyle={tip}
                  content={({ active, payload }) => {
                    const r = payload?.[0]?.payload as PairedPlace | undefined;
                    return active && r ? (
                      <div className="depth-chart-tooltip">
                        <b>{r.name}</b>
                        <p>
                          {baseline}: {fmt(r.baseline_margin_pp, 1)} pp
                        </p>
                        <p>
                          {year}: {fmt(r.current_margin_pp, 1)} pp
                        </p>
                        <p>Change: {fmt(r.change_pp, 1)} pp R−D</p>
                      </div>
                    ) : null;
                  }}
                />
                <Scatter
                  data={pairs}
                  onClick={(d) => onSelect(String(d.payload?.id))}
                >
                  {pairs.map((r) => (
                    <Cell
                      key={r.id}
                      fill={r.change_pp! > 0 ? "var(--red)" : "var(--blue)"}
                      opacity={0.7}
                      stroke={
                        selected.includes(r.id) || focused === r.id
                          ? "var(--selection)"
                          : "transparent"
                      }
                      strokeWidth={3}
                    />
                  ))}
                </Scatter>
              </ScatterChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <Empty title="No eligible paired points">
            Matching identifiers alone do not establish that boundaries and
            contest rounds can be compared.
          </Empty>
        )}
        <ResearchGuide
          what="Each point represents a place measured in two elections using the same signed margin definition."
          how="Points above the dashed diagonal moved toward Republican; points below it moved toward Democratic. This describes places, not individual voters switching sides."
          source="Shared paired historical results and reviewed geography links."
        />
      </Panel>
      <Panel
        title="The distribution of geographic margins"
        subtitle={`${year} · each reporting area counts once, regardless of size`}
      >
        <div className="chart" style={{ height: 285 }}>
          <ResponsiveContainer>
            <BarChart data={hist} margin={{ right: 15, bottom: 25 }}>
              <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
              <XAxis
                dataKey="midpoint"
                tick={ticks}
                tickFormatter={(v) => (v < 0 ? `D+${Math.abs(v)}` : `R+${v}`)}
                interval={3}
              />
              <YAxis allowDecimals={false} tick={ticks} width={42} />
              <Tooltip
                contentStyle={tip}
                formatter={(v) => [fmt(v), "Reporting areas"]}
                labelFormatter={(_v, payload) =>
                  payload[0]?.payload?.label + " pp R−D"
                }
              />
              <Bar
                dataKey="count"
                name="Reporting areas"
                isAnimationActive={false}
              >
                {hist.map((bin) => (
                  <Cell
                    key={bin.start}
                    fill={bin.midpoint < 0 ? "var(--blue)" : "var(--red)"}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
        <ResearchGuide
          what="The number of places in each ten-percentage-point Republican-minus-Democratic margin interval."
          how="This is an unweighted distribution of reporting areas. A large number of small places does not imply a large number of votes. Missing partisan shares are excluded."
          source="All reporting areas loaded in the current result scope."
        />
      </Panel>
      <Panel
        title="Where candidate votes concentrate"
        subtitle="Places ranked by candidate-vote volume, largest first"
      >
        <ConcentrationChart rows={chartRows} />
        <ResearchGuide
          what="The cumulative share of candidate votes represented by the largest reporting areas."
          how="A steeper curve indicates that a small proportion of areas contributes a large proportion of the votes. This is geographic concentration, not turnout or candidate support."
          source="Current result query; disjoint reporting-area candidate totals."
        />
      </Panel>
    </div>
  );
}
