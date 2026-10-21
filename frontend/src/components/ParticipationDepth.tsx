import { useMemo, useState } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { AppContext, CompositionRow } from "../types";
import { COLORS, CYCLE_COLORS, fmt, human } from "../utils";
import { Panel, Empty, Select } from "./ui";
import { ResearchGuide } from "./ResearchGuide";
import "../atlasDepth.css";
export default function ParticipationDepth({ workspace, query }: AppContext) {
  const indexed = useMemo(() => {
    const cycles = [
      ...new Set(
        (workspace.series || []).map((p) => Number(p.cycle)).filter(Boolean),
      ),
    ];
    const data = new Map<number, Record<string, number>>();
    cycles.forEach((cycle) => {
      const points = (workspace.series || [])
        .filter((p) => p.cycle === cycle && typeof p.value === "number")
        .sort((a, b) => a.date.localeCompare(b.date));
      const first = points.find((p) => p.value! > 0);
      if (!first) return;
      points.forEach((p, index) => {
        const position =
          typeof p.x === "number"
            ? p.x
            : typeof p.days_to_election === "number"
              ? p.days_to_election
              : index;
        const row = data.get(position) || { position };
        row[String(cycle)] = (Number(p.value) / Number(first.value)) * 100;
        data.set(position, row);
      });
    });
    return {
      cycles,
      data: [...data.values()].sort((a, b) => a.position - b.position),
    };
  }, [workspace.series]);
  const observations = workspace.observations || [];
  const observedCycles = [...new Set(observations.map((o) => o.cycle))].sort(
    (a, b) => b - a,
  );
  const modes = [...new Set(observations.map((o) => o.mode))].sort();
  const composition = workspace.composition || [],
    dimensions = [...new Set(composition.map((c) => c.dimension))];
  const [storedDimension, setDimension] = useState("");
  const dimension = dimensions.includes(storedDimension)
    ? storedDimension
    : dimensions[0];
  const groups = composition.filter((c) => c.dimension === dimension);
  const byMode = new Map<string, CompositionRow[]>();
  groups.forEach((row) => {
    const key = row.mode || query.mode;
    byMode.set(key, [...(byMode.get(key) || []), row]);
  });
  return (
    <section
      className="atlas-depth-section"
      aria-label="Participation research detail"
    >
      <div className="participation-depth-grid">
        <Panel
          title="Indexed participation trajectories"
          subtitle="Each cycle starts at 100 on its first positive observation in the selected window."
        >
          {indexed.data.length > 1 ? (
            <div className="chart" style={{ height: 300 }}>
              <ResponsiveContainer>
                <LineChart
                  data={indexed.data}
                  margin={{ left: 4, right: 20, top: 15, bottom: 18 }}
                >
                  <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
                  <XAxis
                    dataKey="position"
                    type="number"
                    tick={{ fontSize: 11, fill: "var(--muted)" }}
                  />
                  <YAxis
                    tickFormatter={(v) => `${fmt(v)}×`.replace("×", " index")}
                    width={65}
                    tick={{ fontSize: 10, fill: "var(--muted)" }}
                  />
                  <ReferenceLine
                    y={100}
                    stroke="var(--muted)"
                    strokeDasharray="3 3"
                  />
                  <Tooltip
                    contentStyle={{
                      background: "var(--popover)",
                      border: "1px solid var(--border)",
                      color: "var(--text)",
                    }}
                    formatter={(v) => `${fmt(v, 1)} index`}
                  />
                  <Legend wrapperStyle={{ fontSize: 12 }} />
                  {indexed.cycles.map((cycle, i) => (
                    <Line
                      key={cycle}
                      dataKey={String(cycle)}
                      name={`${cycle} · first observation = 100`}
                      type="stepAfter"
                      stroke={
                        cycle === query.cycle
                          ? "var(--teal)"
                          : CYCLE_COLORS[cycle] ||
                            COLORS[(i + 1) % COLORS.length]
                      }
                      strokeDasharray={
                        cycle === query.cycle ? undefined : "6 3"
                      }
                      strokeWidth={2.5}
                      dot={false}
                      connectNulls={false}
                      isAnimationActive={false}
                    />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <Empty title="Multiple actual reports are needed">
              One observation cannot establish a trajectory. The source's latest
              value remains visible above.
            </Empty>
          )}
          <ResearchGuide
            what="The growth of reported participation relative to the first positive observation available in each displayed cycle and date window."
            how="100 is the starting observation, not final turnout. Different starting coverage, reporting schedules, or voting rules can produce different curves. An index is not a forecast or a substitute for the compatibility ledger."
            source="Exact source observations in the selected cutoff, chronology, metric, and evidence revision."
          />
        </Panel>
        <Panel
          title="Evidence coverage matrix"
          subtitle="Counts of real report dates, separated by cycle and voting method."
        >
          <div className="coverage-matrix">
            <table>
              <thead>
                <tr>
                  <th>Voting method</th>
                  {observedCycles.map((c) => (
                    <th key={c}>{c}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {modes.map((mode) => (
                  <tr key={mode}>
                    <th>{human(mode)}</th>
                    {observedCycles.map((cycle) => {
                      const points = observations.filter(
                          (o) =>
                            o.cycle === cycle &&
                            o.mode === mode &&
                            !o.category_dimension,
                        ),
                        dates = [...new Set(points.map((o) => o.date))].sort();
                      return (
                        <td
                          key={cycle}
                          className={
                            dates.length ? "has-evidence" : "no-evidence"
                          }
                        >
                          <b>
                            {dates.length
                              ? `${dates.length} report dates`
                              : "Not published"}
                          </b>
                          {dates.length > 0 && (
                            <small>
                              {dates[0]}
                              {dates.length > 1 ? ` → ${dates.at(-1)}` : ""}
                              <br />
                              {
                                new Set(points.map((o) => o.geography_id)).size
                              }{" "}
                              source areas
                            </small>
                          )}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!observations.length && (
            <Empty title="No observations match the current evidence scope">
              Change the metric, cycle, or chronology to a documented source
              selection.
            </Empty>
          )}
          <ResearchGuide
            what="The presence of actual source reports in the current analytical response."
            how="A missing cell is not zero participation. A populated cell is not proof of complete statewide reporting. Report dates can differ across places; inspect the original dates before comparing."
            source="Scoped observation records; date, method, geography, and revision preserved."
          />
        </Panel>
      </div>
      <Panel
        title="Published composition, with unknowns visible"
        subtitle="Separate published dimensions remain separate; demographic intersections require actual joint records."
      >
        {dimensions.length ? (
          <>
            <Select
              label="Composition research dimension"
              value={dimension}
              onChange={setDimension}
              options={dimensions.map((d) => ({ value: d, label: human(d) }))}
            />
            <div className="composition-depth-modes">
              {[...byMode.entries()].map(([mode, values]) => {
                const total = values.reduce((n, r) => n + r.value, 0),
                  unknown = values
                    .filter((r) =>
                      /unknown|unclassified|not.provided|unspecified|other|undesignated/i.test(
                        r.category,
                      ),
                    )
                    .reduce((n, r) => n + r.value, 0),
                  max = Math.max(...values.map((r) => r.value), 1);
                return (
                  <div key={mode}>
                    <h4>
                      {human(mode)} · {human(dimension)}
                    </h4>
                    <div className="composition-depth-summary">
                      <b>{fmt(total)} published category records</b>
                      <span>
                        {fmt(unknown)} unknown / other / unclassified categories
                      </span>
                    </div>
                    {values
                      .sort((a, b) => b.value - a.value)
                      .map((r, i) => (
                        <div
                          key={r.category}
                          className={`composition-depth-row ${/unknown|unclassified|not.provided|unspecified/i.test(r.category) ? "unknown" : ""}`}
                        >
                          <span>{human(r.category)}</span>
                          <div>
                            <i
                              style={{
                                width: `${(r.value / max) * 100}%`,
                                background:
                                  /unknown|unclassified|not.provided|unspecified/i.test(
                                    r.category,
                                  )
                                    ? "var(--muted)"
                                    : COLORS[i % COLORS.length],
                              }}
                            />
                          </div>
                          <b>{fmt(r.value)}</b>
                        </div>
                      ))}
                  </div>
                );
              })}
            </div>
            <ResearchGuide
              what="Directly published counts by one source-supported composition dimension, grouped by voting method."
              how="Unknown and unclassified categories stay visible. These are counts of the source's reported categories; the chart does not infer candidate votes, group turnout rates, or joint demographic intersections. Category totals may have different coverage from the statewide headline."
              source="Published composition observations linked to the active evidence revision."
            />
          </>
        ) : (
          <Empty title="This source does not publish compatible voter composition">
            Population context remains available in Atlas, explicitly labeled as
            residents rather than voters. No demographic or party profile is
            inferred from a place's previous election result.
          </Empty>
        )}
      </Panel>
    </section>
  );
}
