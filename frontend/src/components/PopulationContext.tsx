import { publicFetch } from "../publicData";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  Scatter,
  ScatterChart,
} from "recharts";
import { atlasApi } from "../atlasApi";
import type { AppContext, GeoRow } from "../types";
import { Empty, Loading, Panel, Select } from "./ui";
import { compact, fmt, human, stateName } from "../utils";
import { ResearchGuide } from "./ResearchGuide";
import { StateMap } from "./Maps";
import { useViewOption } from "../viewState";
export default function PopulationContext(ctx: AppContext) {
  const { query } = ctx,
    [search, setSearch] = useState(""),
    [metric, setMetric] = useViewOption<string>("context_metric", "population");
  const q = useQuery({
    queryKey: [
      "atlas",
      "context",
      query.state,
      query.revision ?? ctx.workspace.revision,
    ],
    queryFn: () =>
      atlasApi.context(query.state, query.revision ?? ctx.workspace.revision),
  });
  const geo = useQuery({
    queryKey: ["boundaries", query.state, "detail"],
    queryFn: async () => {
      const r = await publicFetch("/api/v1/geography/" + query.state);
      return r.json() as Promise<{
        features: { properties: Record<string, unknown> }[];
      }>;
    },
    staleTime: Infinity,
  });
  const names = new Map(
    (geo.data?.features || []).map((f) => [
      String(f.properties.canonical_id || "county:" + f.properties.GEOID),
      String(f.properties.name || f.properties.NAME),
    ]),
  );
  const data = q.data || {};
  const all = (Array.isArray(data.estimates) ? data.estimates : []) as Record<
    string,
    unknown
  >[];
  const metrics = [...new Set(all.map((r) => String(r.metric)))],
    state = all.filter((r) => r.geography_id === `state:${query.state}`),
    rows = all.filter((r) => r.metric === metric),
    allCounty = rows.filter((r) => r.geography_id !== `state:${query.state}`),
    county = allCounty
      .filter((r) =>
        `${names.get(String(r.geography_id)) || r.geography_id}`
          .toLowerCase()
          .includes(search.toLowerCase()),
      )
      .sort((a, b) => Number(b.estimate) - Number(a.estimate));
  const mapRows: GeoRow[] = allCounty
    .filter((r) => typeof r.estimate === "number")
    .map((r) => ({
      id: String(r.geography_id),
      canonical_id: String(r.geography_id),
      name: names.get(String(r.geography_id)) || String(r.geography_id),
      type: "county",
      value: Number(r.estimate),
      baseline_value: null,
      change: null,
      share: null,
      denominator: null,
      source_ids: [],
      observation_ids: [],
    }))
    .sort((a, b) => b.value - a.value);
  const pop = new Map(
    all
      .filter(
        (r) => r.metric === "population" && typeof r.estimate === "number",
      )
      .map((r) => [String(r.geography_id), Number(r.estimate)]),
  );
  const scatter = allCounty
    .filter((r) => typeof r.estimate === "number")
    .map((r) => ({
      name: names.get(String(r.geography_id)) || r.geography_id,
      population: pop.get(String(r.geography_id)),
      estimate: Number(r.estimate),
    }))
    .filter((r) => r.population);
  const unit =
    metric === "median_age"
      ? " years"
      : metric === "median_household_income"
        ? " USD"
        : " residents";
  const tips = {
    background: "var(--popover)",
    border: "1px solid var(--border)",
    color: "var(--text)",
    fontSize: 12,
  };
  return (
    <>
      <Panel
        title={`Population context · ${stateName(query.state)}`}
        subtitle="Resident characteristics are separate from observed voter characteristics."
      >
        {q.isPending ? (
          <Loading />
        ) : all.length ? (
          <div className="context-estimate-grid">
            {state.map((r, i) => (
              <div key={i}>
                <span>{human(String(r.metric))}</span>
                <strong>
                  {r.metric === "median_household_income" ? "$" : ""}
                  {fmt(r.estimate, r.metric === "median_age" ? 1 : 0)}
                  {r.metric === "median_age" ? " years" : ""}
                </strong>
                <small>
                  {String(r.period_start || "").slice(0, 4)}–
                  {String(r.period_end || "").slice(0, 4)} estimate{" "}
                  {r.moe != null
                    ? `· ±${fmt(r.moe, r.metric === "median_age" ? 1 : 0)} (90%)`
                    : "· no sampling-error estimate supplied"}
                </small>
              </div>
            ))}
          </div>
        ) : (
          <Empty title="A compatible population dataset has not been loaded">
            Context estimates require a published period, geography, and source.
          </Empty>
        )}
        <ResearchGuide
          what="Census American Community Survey five-year estimates for residents and households."
          how="These include people who may be ineligible or unregistered. They cannot establish the characteristics or choices of early voters. Intervals refer to sampling error, with periods preserved."
          source="U.S. Census Bureau · ACS 2020–2024 five-year estimates"
        />
      </Panel>
      {all.length > 0 && (
        <>
          <div className="context-metric-selector">
            <Select
              label="Population context measure"
              value={metric}
              onChange={setMetric}
              options={metrics.map((m) => ({ value: m, label: human(m) }))}
            />
            <span>2020–2024 estimates · 2024 geographic context</span>
          </div>
          <div className="chart-grid">
            <Panel
              title={`${human(metric)} by reporting area`}
              subtitle="Public population context, with matching Census identifiers."
            >
              <StateMap
                state={query.state}
                rows={mapRows}
                selected={(ctx.selectedGeographyIds ?? query.geography_ids)}
                onSelect={(id) => ctx.setQuery({ geography_ids: [id] })}
                layer={metric === "population" ? "volume" : "context"}
                metricLabel={human(metric)}
                unit={unit}
                height={390}
              />
            </Panel>
            <Panel
              title={`Largest ${human(metric).toLowerCase()} estimates`}
              subtitle="Ranks reported estimates; uncertainty remains available in the table."
            >
              <div className="chart" style={{ height: 360 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart
                    data={mapRows.slice(0, 12)}
                    layout="vertical"
                    margin={{ right: 15 }}
                  >
                    <CartesianGrid
                      stroke="var(--chart-grid)"
                      horizontal={false}
                    />
                    <XAxis
                      type="number"
                      tickFormatter={compact}
                      tick={{ fontSize: 10, fill: "var(--muted)" }}
                    />
                    <YAxis
                      type="category"
                      dataKey="name"
                      width={110}
                      tick={{ fontSize: 11, fill: "var(--muted)" }}
                    />
                    <Tooltip
                      contentStyle={tips}
                      formatter={(v) =>
                        fmt(v, metric === "median_age" ? 1 : 0) + unit
                      }
                    />
                    <Bar
                      dataKey="value"
                      fill="var(--violet)"
                      maxBarSize={18}
                      radius={[0, 3, 3, 0]}
                    />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </Panel>
          </div>
          {metric !== "population" && (
            <Panel
              title={`${human(metric)} and resident population`}
              subtitle="Area-level context; each point represents one reporting area."
            >
              <div className="chart" style={{ height: 300 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <ScatterChart
                    margin={{ left: 8, right: 20, top: 10, bottom: 10 }}
                  >
                    <CartesianGrid stroke="var(--chart-grid)" />
                    <XAxis
                      type="number"
                      dataKey="population"
                      name="Residents"
                      tickFormatter={compact}
                      tick={{ fontSize: 11, fill: "var(--muted)" }}
                    />
                    <YAxis
                      type="number"
                      dataKey="estimate"
                      name={human(metric)}
                      tickFormatter={compact}
                      width={55}
                      tick={{ fontSize: 11, fill: "var(--muted)" }}
                    />
                    <Tooltip
                      contentStyle={tips}
                      formatter={(v, n) => [
                        fmt(
                          v,
                          metric === "median_age" && n !== "Residents" ? 1 : 0,
                        ),
                        n,
                      ]}
                    />
                    <Scatter
                      data={scatter}
                      fill="var(--violet)"
                      opacity={0.65}
                    />
                  </ScatterChart>
                </ResponsiveContainer>
              </div>
              <ResearchGuide
                what="The relationship between the selected population estimate and the number of residents in each area."
                how="Each point is an aggregate place. Associations do not describe individual people, voters, or candidate preferences."
              />
            </Panel>
          )}
          <Panel title="Population estimate evidence">
            <div className="table-toolbar">
              <input
                aria-label="Search population reporting areas"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Find a county or reporting area…"
              />
              <span>
                {county.length} published estimates · {human(metric)}
              </span>
            </div>
            <div className="table-scroll context-table">
              <table>
                <thead>
                  <tr>
                    <th>Place</th>
                    <th>{human(metric)}</th>
                    <th>Margin of error</th>
                    <th>Estimate period</th>
                  </tr>
                </thead>
                <tbody>
                  {county.map((r, i) => (
                    <tr key={i}>
                      <td>
                        {names.get(String(r.geography_id)) ||
                          String(r.geography_id)}
                        <small>{String(r.geography_id)}</small>
                      </td>
                      <td className="numeric">
                        {r.estimate == null
                          ? "Not published / Census annotation"
                          : fmt(r.estimate, metric === "median_age" ? 1 : 0) +
                            unit}
                      </td>
                      <td>
                        {r.moe == null
                          ? "Not applicable / not supplied"
                          : `±${fmt(r.moe, metric === "median_age" ? 1 : 0)} (90%)`}
                      </td>
                      <td>
                        {String(r.period_start || "").slice(0, 4)}–
                        {String(r.period_end || "").slice(0, 4)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
        </>
      )}
    </>
  );
}
