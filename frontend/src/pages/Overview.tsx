import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, ArrowDownUp, Map, Search, Vote } from "lucide-react";
import type { AppContext, NationalRow } from "../types";
import { atlasApi } from "../atlasApi";
import { NationalMap } from "../components/Maps";
import { SeriesChart, ModeChart } from "../components/Charts";
import { ResearchGuide } from "../components/ResearchGuide";
import { Badge, MiniBar, Notice, Panel, Segmented } from "../components/ui";
import {
  compact,
  dateLabel,
  fmt,
  stateName,
  human,
  STATE_NAMES,
} from "../utils";
import { useViewOption } from "../viewState";
import "../participation.css";
export default function Overview(ctx: AppContext) {
  const { workspace, query, setQuery, setPage } = ctx;
  const [layer, setLayer] = useViewOption<"margin" | "volume" | "coverage">(
      "overview_layer",
      "margin",
    ),
    [tile, setTile] = useViewOption<string>("overview_map", "geographic"),
    [search, setSearch] = useState(""),
    [watchOnly, setWatchOnly] = useState(false),
    [sort, setSort] = useState("name");
  const result = useQuery({
    queryKey: [
      "atlas",
      "national-results",
      ctx.resultYear || 2024,
      ctx.resultOffice || "PRESIDENT",
      query.revision ?? workspace.revision,
    ],
    queryFn: () =>
      atlasApi.results({
        year: ctx.resultYear || 2024,
        office: ctx.resultOffice || "PRESIDENT",
        geography_level: "state",
        revision: query.revision ?? workspace.revision,
      }),
  });
  const states = useQuery({
    queryKey: ["atlas", "states"],
    queryFn: atlasApi.states,
  });
  const all = useMemo(
    () =>
      Object.entries(STATE_NAMES)
        .filter(([c]) => c !== "DC")
        .map(([code, name]) => {
          const ev = workspace.national?.find((r) => r.code === code);
          const historic = result.data?.geographies.find(
            (g) => g.id === `state:${code}` || g.id === code,
          );
          return {
            code,
            name,
            fips: ev?.fips || "",
            watchlist: ev?.watchlist || false,
            value: ev?.value ?? null,
            latest_date: ev?.latest_date || null,
            source_count: ev?.source_count || 0,
            poll_count: ev?.poll_count || 0,
            coverage_status: ev?.coverage_status || "not_collected",
            metric: query.metric,
            historical: historic,
          };
        }),
    [workspace.national, result.data, query.metric],
  );
  const rows = all
    .filter(
      (r) =>
        (!watchOnly || r.watchlist) &&
        `${r.name} ${r.code}`.toLowerCase().includes(search.toLowerCase()),
    )
    .sort((a, b) =>
      sort === "volume"
        ? (b.value || 0) - (a.value || 0)
        : a.name.localeCompare(b.name),
    );
  const mapRows: NationalRow[] = all.map((r) => ({
    ...r,
    value:
      layer === "margin"
        ? r.historical?.rep_share_pct != null &&
          r.historical?.dem_share_pct != null
          ? r.historical.rep_share_pct - r.historical.dem_share_pct
          : null
        : r.value,
  }));
  const valid = all.filter((r) => r.value != null),
    total = valid.reduce((n, r) => n + (r.value || 0), 0),
    selected = all.find((r) => r.code === query.state);
  const latest = valid
    .map((r) => r.latest_date || "")
    .sort()
    .at(-1);
  return (
    <>
      <div className="senate-priority-banner">
        <div><strong>2026 Senate research desk</strong><span>Early-voting geography, methods, composition, historical comparisons, and explicit research calls.</span></div>
        <button className="button" onClick={()=>setPage("forecasts")}>Open EV-led Senate calls <ArrowRight size={15}/></button>
      </div>
      <div className="page-intro new-today-intro">
        <div>
          <h2>The election, place by place.</h2>
          <p>
            Follow current participation, compare the historical landscape, and
            open the evidence behind every state.
          </p>
        </div>
        <Badge tone="teal">{dateLabel(ctx.bootstrap.app?.today)}</Badge>
      </div>
      <div className="today-measured-summary">
        <div>
          <strong>{compact(total)}</strong>
          <span>
            {human(query.metric)} · {valid.length} compatible states
          </span>
        </div>
        <div>
          <strong>
            {result.data?.geographies.length ||
              states.data?.states.filter((s) => s.result_count > 0).length ||
              0}
          </strong>
          <span>States with historical reference data</span>
        </div>
        <div>
          <strong>
            {workspace.national?.reduce((n, r) => n + r.poll_count, 0) || 0}
          </strong>
          <span>Original polling studies in current scope</span>
        </div>
        <div>
          <strong>
            {latest ? dateLabel(latest).replace(", 2026", "") : "—"}
          </strong>
          <span>Latest matching participation report</span>
        </div>
      </div>
      <div className="today-national-grid">
        <Panel
          title={
            layer === "margin"
              ? `${ctx.resultYear || 2024} ${human(ctx.resultOffice || "presidential").toLowerCase()} landscape`
              : "Current participation across states"
          }
          subtitle={
            layer === "margin"
              ? "Historical candidate results, separate from current early voting."
              : "Only compatible reported measures appear; missing observations stay missing."
          }
          actions={
            <div className="inline-controls">
              <Segmented
                label="National map layer"
                value={layer}
                onChange={setLayer}
                items={[
                  { id: "margin", label: "Results" },
                  { id: "volume", label: "Early vote" },
                  { id: "coverage", label: "Coverage" },
                ]}
              />
              <button
                className="icon-button"
                aria-label="Toggle geographic and state-tile map"
                onClick={() => setTile(tile === "tile" ? "geographic" : "tile")}
              >
                <Map size={15} />
              </button>
            </div>
          }
        >
          <NationalMap
            rows={mapRows}
            selected={query.state}
            onSelect={(state) => setQuery({ state })}
            layer={layer}
            tile={tile === "tile"}
          />
          <div style={{ padding: "0 16px 12px" }}>
            <ResearchGuide
              what={
                layer === "margin"
                  ? "Historical Republican minus Democratic margin in each state."
                  : "Current early-participation evidence for the selected definition and cutoff."
              }
              how={
                layer === "margin"
                  ? "Blue states show a Democratic advantage; red states show a Republican advantage. Click any state to open its research context."
                  : "Select a state for its current source date, original definition, and detailed dossier."
              }
              source={
                layer === "margin"
                  ? "Original election records and attributed historical research collections"
                  : "Original election authorities; attributed UF Election Lab gap coverage where labeled"
              }
            />
          </div>
        </Panel>
        <Panel
          title={`${stateName(query.state)} · research focus`}
          subtitle="A starting point for a deeper investigation."
          actions={
            <button className="text-button" onClick={() => setPage("states")}>
              State dossier
              <ArrowRight size={13} />
            </button>
          }
        >
          <div className="today-state-list">
            <button
              onClick={() => {
                ctx.setResearchQuestion?.("participation");
                setPage("states");
              }}
            >
              <b>
                <Vote size={20} />
              </b>
              <span>
                <strong>{fmt(selected?.value)}</strong>
                <small>
                  {human(query.metric)} ·{" "}
                  {selected?.latest_date
                    ? dateLabel(selected.latest_date)
                    : "No matching current measure"}
                </small>
              </span>
              <ArrowRight size={14} />
            </button>
            {selected?.historical?.options
              .slice()
              .sort((a, b) => b.votes - a.votes)
              .slice(0, 3)
              .map((o) => (
                <button
                  key={o.id}
                  onClick={() => {
                    ctx.setResearchQuestion?.("historical");
                    setPage("atlas");
                  }}
                >
                  <b>{o.party || "—"}</b>
                  <span>
                    <strong>{o.name}</strong>
                    <small>
                      {fmt(o.votes)} votes · {ctx.resultYear || 2024}
                    </small>
                  </span>
                  <strong>{fmt(o.share_pct, 1)}%</strong>
                </button>
              ))}
            <button onClick={() => setPage("polls")}>
              <b>01</b>
              <span>
                <strong>Original polling</strong>
                <small>
                  {selected?.poll_count || 0} studies in the current scope
                </small>
              </span>
              <ArrowRight size={14} />
            </button>
            <button onClick={() => setPage("sources")}>
              <b>02</b>
              <span>
                <strong>Inspect source coverage</strong>
                <small>{selected?.source_count || 0} registered sources</small>
              </span>
              <ArrowRight size={14} />
            </button>
            <button onClick={() => setPage("elections")}>
              <b>03</b>
              <span>
                <strong>Explore every available contest</strong>
                <small>Federal, state, local and ballot-measure catalog</small>
              </span>
              <ArrowRight size={14} />
            </button>
          </div>
        </Panel>
      </div>
      <Panel
        title="The 50-state research index"
        subtitle="Current voting and historical results appear side by side, with their definitions kept separate."
        className="research-table-panel"
      >
        <div className="table-toolbar">
          <div className="search-field">
            <Search size={15} />
            <input
              placeholder="Find a state…"
              aria-label="Search states"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={watchOnly}
              onChange={(e) => setWatchOnly(e.target.checked)}
            />
            Senate watchlist only
          </label>
          <button
            className="button small secondary"
            onClick={() => setSort(sort === "name" ? "volume" : "name")}
          >
            <ArrowDownUp size={13} />
            {sort === "name" ? "State name" : "Reported volume"}
          </button>
          <span>{rows.length} states</span>
        </div>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>State</th>
                <th>Current reported participation</th>
                <th>Report date</th>
                <th>{ctx.resultYear || 2024} historical margin</th>
                <th>Historical votes</th>
                <th>Sources / polls</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                const margin =
                  r.historical?.rep_share_pct != null &&
                  r.historical?.dem_share_pct != null
                    ? r.historical.rep_share_pct - r.historical.dem_share_pct
                    : null;
                return (
                  <tr
                    key={r.code}
                    className={query.state === r.code ? "selected" : ""}
                  >
                    <td>
                      <button
                        className="state-cell"
                        onClick={() => {
                          setQuery({ state: r.code });
                          setPage("states");
                        }}
                      >
                        <span className="table-state-code">{r.code}</span>
                        <span>
                          <b>{r.name}</b>
                          <small>
                            {r.watchlist
                              ? "Senate watchlist"
                              : "State research atlas"}
                          </small>
                        </span>
                      </button>
                    </td>
                    <td>
                      <MiniBar
                        value={r.value}
                        max={Math.max(...rows.map((x) => x.value || 0), 1)}
                      />
                    </td>
                    <td>
                      {r.latest_date ? (
                        dateLabel(r.latest_date)
                      ) : (
                        <span className="muted">Not available</span>
                      )}
                    </td>
                    <td
                      style={{
                        color:
                          margin == null
                            ? "var(--muted)"
                            : margin > 0
                              ? "var(--red)"
                              : "var(--blue)",
                      }}
                    >
                      {margin == null
                        ? "—"
                        : `${margin > 0 ? "R" : "D"} +${fmt(Math.abs(margin), 1)} pp`}
                    </td>
                    <td className="numeric">
                      {fmt(r.historical?.total_votes)}
                    </td>
                    <td>
                      {r.source_count} / {r.poll_count}
                    </td>
                    <td>
                      <button
                        className="icon-button"
                        aria-label={`Explore ${r.name}`}
                        onClick={() => {
                          setQuery({ state: r.code });
                          setPage("states");
                        }}
                      >
                        <ArrowRight size={14} />
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Panel>
      <div className="chart-grid">
        <Panel
          title={`${stateName(query.state)} · participation over time`}
          subtitle="Current and baseline observations retain their actual reporting chronology."
        >
          <SeriesChart
            series={workspace.series}
            observations={workspace.observations}
            alignment={query.alignment}
          />
        </Panel>
        <Panel
          title="Published voting-method composition"
          subtitle="Requests, returns, acceptance and votes cast remain distinct measures."
        >
          <ModeChart
            observations={workspace.observations}
            cycle={query.cycle}
          />
        </Panel>
      </div>
      <Notice>
        National participation total includes only the {valid.length} states
        reporting the selected compatible measure. Historical results describe
        prior candidate votes; current party registration and early-vote
        geography do not reveal candidate choices.
      </Notice>
    </>
  );
}
