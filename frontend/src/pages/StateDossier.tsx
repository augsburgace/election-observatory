import { useEffect, useState } from "react";
import { ArrowRight, Bookmark, FileSearch } from "lucide-react";
import type { AppContext } from "../types";
import {
  ChangeChart,
  CompositionChart,
  ModeChart,
  SeriesChart,
} from "../components/Charts";
import { Badge, Empty, Notice, Panel, Select } from "../components/ui";
import { api } from "../api";
import { dateLabel, fmt, human, stateName } from "../utils";
import StateOverview from "../components/StateOverview";
import EarlyVotingGuide from "../components/EarlyVotingGuide";
import Polls from "./Polls";
import History from "./History";
import Atlas from "./Atlas";
import Scenarios from "./Scenarios";
import Forecasts from "./Forecasts";
import Notebook from "./Notebook";
import Sources from "./Sources";
const tabs = [
  "Overview",
  "Voting",
  "Geography",
  "Composition",
  "History",
  "Polls",
  "Scenarios",
  "Forecast",
  "Notes",
  "Sources",
];
export default function StateDossier(ctx: AppContext) {
  const { workspace, query, inspect, notify } = ctx;
  const [tab, setTab] = useState(
    () => new URLSearchParams(location.search).get("tab") || "Overview",
  );
  useEffect(() => {
    const restore = () =>
      setTab(new URLSearchParams(location.search).get("tab") || "Overview");
    window.addEventListener("popstate", restore);
    return () => window.removeEventListener("popstate", restore);
  }, []);
  const [dimension, setDimension] = useState("");
  const [share, setShare] = useState(false);
  const composition = workspace.composition || [];
  const dimensions = [...new Set(composition.map((r) => r.dimension))];
  const currentSeries = (workspace.series || []).filter(
    (p) => p.cycle === query.cycle,
  );
  const footer = `${stateName(query.state)} · ${query.metric} · r${workspace.revision}`;
  function changeTab(value: string) {
    setTab(value);
    const p = new URLSearchParams(location.search);
    p.set("tab", value);
    history.replaceState(null, "", `?${p}`);
  }
  async function bookmark() {
    try {
      await api.saveResearch({
        kind: "bookmark",
        title: `${stateName(query.state)} state dossier`,
        view: { query: workspace.query, page: "states", tab },
      });
      notify("State dossier bookmarked.");
    } catch (e) {
      notify((e as Error).message);
    }
  }
  return (
    <>
      <div className="page-intro">
        <div>
          <div className="state-title-line">
            <span className="state-title-code">{query.state}</span>
            <h2>{stateName(query.state)}</h2>
            <Badge tone="teal">State dossier</Badge>
          </div>
          <p>
            A complete research trail through participation, geography,
            historical comparisons, and polling.
          </p>
        </div>
        <button className="button secondary" onClick={bookmark}>
          <Bookmark size={14} />
          Bookmark state
        </button>
      </div>
      <div
        className="dossier-tabs"
        role="tablist"
        aria-label="State dossier sections"
      >
        {tabs.map((name) => (
          <button
            key={name}
            role="tab"
            aria-selected={tab === name}
            className={tab === name ? "active" : ""}
            onClick={() => changeTab(name)}
          >
            {name}
          </button>
        ))}
      </div>
      {tab === "Overview" && <StateOverview {...ctx} />}
      {tab === "Voting" && <EarlyVotingGuide {...ctx}/>}
      {tab === "Voting" && (
        <>
          <div className="chart-grid">
            <Panel
              title="Cumulative reported participation"
              subtitle="Step lines represent actual available source observations."
              exportLabel={footer}
            >
              <SeriesChart
                series={workspace.series}
                observations={workspace.observations}
                alignment={query.alignment}
                height={310}
                brush
                onRange={(start, end) =>
                  ctx.setQuery({ date_window: [start, end] })
                }
              />
            </Panel>
            <Panel
              title="Newly reported change"
              subtitle="Reporting batches and revisions may differ from when people voted."
              exportLabel={footer}
            >
              <ChangeChart series={currentSeries} />
            </Panel>
            <Panel title="Voting-method detail" exportLabel={footer}>
              <ModeChart
                observations={workspace.observations}
                cycle={query.cycle}
              />
            </Panel>
            <Panel title="Reported observations">
              <ObservationTable ctx={ctx} />
            </Panel>
          </div>
          <Notice>
            Requested, issued, received, accepted, and cast ballots are
            different measures. Use the metric selector to inspect each
            supported definition.
          </Notice>
        </>
      )}
      {tab === "Geography" && <Atlas {...ctx} embedded />}
      {tab === "Composition" && (
        <>
          <div className="section-toolbar">
            <Select
              value={dimension || dimensions[0] || ""}
              onChange={setDimension}
              label="Composition dimension"
              options={dimensions.map((d) => ({ value: d, label: human(d) }))}
            />
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={share}
                onChange={(e) => setShare(e.target.checked)}
              />
              Show share of reported category totals
            </label>
          </div>
          <div className="chart-grid">
            <Panel
              title="Published composition"
              subtitle="Categories retain the source's terminology."
              exportLabel={footer}
            >
              <CompositionChart
                rows={composition}
                dimension={dimension || dimensions[0]}
                share={share}
              />
            </Panel>
            <Panel title="Category evidence">
              {composition.length ? (
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>Dimension</th>
                        <th>Category</th>
                        <th>Value</th>
                        <th />
                      </tr>
                    </thead>
                    <tbody>
                      {composition
                        .filter(
                          (r) => r.dimension === (dimension || dimensions[0]),
                        )
                        .map((row, i) => (
                          <tr key={i}>
                            <td>{human(row.dimension)}</td>
                            <td>{row.category}</td>
                            <td>{fmt(row.value)}</td>
                            <td>
                              <button
                                className="icon-button"
                                aria-label={`Inspect ${row.category}`}
                                onClick={() =>
                                  row.observation_ids[0] &&
                                  inspect({
                                    type: "observation",
                                    id: row.observation_ids[0],
                                  })
                                }
                              >
                                <FileSearch size={14} />
                              </button>
                            </td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <Empty title="Composition detail is not published">
                  Separate totals will not be combined to invent a demographic
                  intersection.
                </Empty>
              )}
            </Panel>
          </div>
          <Notice>
            Registration and demographic groups describe participation.
            Candidate support remains unobserved.
          </Notice>
        </>
      )}
      {tab === "History" && <History {...ctx} embedded />}
      {tab === "Polls" && <Polls {...ctx} embedded />}
      {tab === "Scenarios" && <Scenarios {...ctx} embedded />}
      {tab === "Forecast" && <Forecasts {...ctx} embedded />}
      {tab === "Notes" && <Notebook {...ctx} embedded />}
      {tab === "Sources" && <Sources {...ctx} embedded />}
    </>
  );
}
export function CoverageFacts({ ctx }: { ctx: AppContext }) {
  const { workspace, setQuery } = ctx;
  const coverage = workspace.coverage;
  return (
    <div className="coverage-facts">
      <div>
        <span>Supported metrics</span>
        <div className="metric-links">
          {coverage?.available_metrics?.length ? (
            coverage.available_metrics.map((m) => (
              <button key={m} onClick={() => setQuery({ metric: m })}>
                {human(m)}
                <ArrowRight size={11} />
              </button>
            ))
          ) : (
            <span>No validated metric yet</span>
          )}
        </div>
      </div>
      <div>
        <span>Voting methods</span>
        <div className="metric-links">
          {coverage?.available_modes?.map((mode) => (
            <button key={mode} onClick={() => setQuery({ mode })}>
              {human(mode)}
              <ArrowRight size={11} />
            </button>
          ))}
        </div>
      </div>
      <div>
        <span>Historical cycles</span>
        <b>{coverage?.available_cycles?.join(", ") || "Not yet available"}</b>
      </div>
      <div>
        <span>As-reported history</span>
        <b>
          {coverage?.as_reported_available ? "Available" : "Not established"}
        </b>
      </div>
      <div>
        <span>Reconstructed history</span>
        <b>
          {coverage?.reconstructed_available ? "Available" : "Not established"}
        </b>
      </div>
    </div>
  );
}
export function ObservationTable({ ctx }: { ctx: AppContext }) {
  const rows = ctx.workspace.observations
    .filter((r) => r.cycle === ctx.query.cycle)
    .slice(0, 100);
  if (!rows.length)
    return (
      <Empty title="No observations match">
        Try one of the available metrics in Research coverage.
      </Empty>
    );
  return (
    <div className="table-scroll observation-table">
      <table>
        <thead>
          <tr>
            <th>Date</th>
            <th>Place</th>
            <th>Metric / mode</th>
            <th>Value</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={row.id || i}>
              <td>{dateLabel(row.date)}</td>
              <td>{row.geography_name}</td>
              <td>
                {human(row.metric)}
                <small>{human(row.mode)}</small>
              </td>
              <td>{fmt(row.value)}</td>
              <td>
                <button
                  className="icon-button"
                  aria-label={`Inspect ${row.geography_name} ${row.date}`}
                  onClick={() =>
                    ctx.inspect({ type: "observation", id: row.id!, data: row })
                  }
                >
                  <FileSearch size={14} />
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {ctx.workspace.observations.length > 100 && (
        <p className="table-footnote">
          Showing 100 observations. Export the filtered dataset for the complete
          series.
        </p>
      )}
    </div>
  );
}
