import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, FileSearch, CalendarDays } from "lucide-react";
import type { AppContext } from "../types";
import { atlasApi } from "../atlasApi";
import { StateMap } from "./Maps";
import {
  SeriesChart,
  ChangeChart,
  CompositionChart,
  ModeChart,
  GeographyBars,
} from "./Charts";
import {
  PlaceTrajectories,
  ConcentrationChart,
  ContributionWaterfall,
  ReportingCalendar,
  EndpointLadder,
} from "./ResearchCharts";
import HistoricalExplorer from "./HistoricalExplorer";
import PopulationContext from "./PopulationContext";
import { DatasetDownload } from "./DownloadStatus";
import { ResearchGuide } from "./ResearchGuide";
import { Empty, Notice, Panel, Select, Status } from "./ui";
import { dateLabel, fmt, human, compact } from "../utils";
import Polls from "../pages/Polls";
import EarlyVotingGuide from "./EarlyVotingGuide";
export default function StateOverview(ctx: AppContext) {
  const { workspace, query, setQuery, inspect } = ctx;
  const rows = workspace.geographies || [],
    composition = workspace.composition || [],
    dims = [...new Set(composition.map((r) => r.dimension))],
    [dim, setDim] = useState("");
  const datasets = useQuery({
    queryKey: ["atlas", "datasets", query.state],
    queryFn: () => atlasApi.datasets(query.state),
  });
  const analytics = useQuery({
    queryKey: ["atlas", "analytics", query],
    queryFn: ({ signal }) => atlasApi.analytics(query, signal),
  });
  const sections = Array.isArray(workspace.brief)
    ? workspace.brief
    : workspace.brief?.sections || [];
  const select = (id: string) =>
    setQuery({
      geography_ids: (ctx.selectedGeographyIds ?? query.geography_ids).includes(id)
        ? (ctx.selectedGeographyIds ?? query.geography_ids).filter((x) => x !== id)
        : [...(ctx.selectedGeographyIds ?? query.geography_ids), id].slice(-8),
    });
  const current = (workspace.series || []).filter(
    (p) => p.cycle === query.cycle,
  );
  const hasCurrent = workspace.summary?.total != null;
  const loadable = (datasets.data?.datasets || []).filter(
    (d) => d.on_demand && !d.loaded_states?.includes(query.state),
  );
  return (
    <>
      {!hasCurrent &&
        (workspace.coverage?.available_metrics?.length || 0) > 0 && (
          <Notice tone="warning">
            This selected participation definition is not published for the
            current scope. Available measures:{" "}
            <span className="metric-links">
              {workspace.coverage?.available_metrics.map((m) => (
                <button key={m} onClick={() => setQuery({ metric: m })}>
                  {human(m)}
                  <ArrowRight size={12} />
                </button>
              ))}
            </span>
          </Notice>
        )}
      <nav className="section-anchors" aria-label="State overview sections">
        {[
          "Landscape",
          "Participation",
          "Geography",
          "Composition",
          "History",
          "Polls",
          "Context",
          "Evidence",
        ].map((s) => (
          <a key={s} href={`#state-${s.toLowerCase()}`}>
            {s}
          </a>
        ))}
      </nav>
      <section id="state-landscape" className="dossier-section">
        {rows.length && hasCurrent ? (
          <>
            <div className="editorial-totals state-overview-totals">
              <div>
                <strong>{compact(workspace.summary?.total)}</strong>
                <span>{human(query.metric)}</span>
              </div>
              <div>
                <strong>{fmt(workspace.summary?.newly_reported)}</strong>
                <span>Newly reported since prior observation</span>
              </div>
              <div>
                <strong>{rows.length}</strong>
                <span>Reporting areas in this scope</span>
              </div>
              <div>
                <strong>
                  {workspace.summary?.pace_ratio != null
                    ? fmt(Number(workspace.summary.pace_ratio) * 100, 1) + "%"
                    : "—"}
                </strong>
                <span>of compatible {query.baseline} comparison</span>
              </div>
            </div>
            <div className="dossier-main-grid">
              <Panel
                title="Where participation is being reported"
                subtitle={`${dateLabel(String(workspace.summary?.latest_date || ""))} · ${human(query.metric)}`}
              >
                <StateMap
                  state={query.state}
                  rows={rows}
                  selected={(ctx.selectedGeographyIds ?? query.geography_ids)}
                  onSelect={select}
                  height={410}
                />
              </Panel>
              <Panel
                title="Participation across cycles"
                subtitle="Actual observations, with the selected historical alignment."
              >
                <SeriesChart
                  series={workspace.series}
                  observations={workspace.observations}
                  alignment={query.alignment}
                  height={350}
                  brush
                  onRange={(start, end) =>
                    setQuery({ date_window: [start, end] })
                  }
                />
                <ResearchGuide
                  what="Reported participation in the current and comparison cycle."
                  how="Step lines join actual source observations. Historical pace is withheld when definitions, timing, or coverage do not match."
                  source="Original source snapshots at the selected revision"
                />
              </Panel>
            </div>
          </>
        ) : (
          <>
            <Notice>
              {hasCurrent
                ? `${fmt(workspace.summary?.total)} ${human(query.metric).toLowerCase()} are reported statewide. A compatible current geographic breakdown is unavailable.`
                : "No current observation matches this participation measure."}{" "}
              The map below is explicitly labeled historical context.{" "}
              <button
                className="text-button"
                onClick={() => ctx.setPage("atlas")}
              >
                Open current-voting investigation
                <ArrowRight size={13} />
              </button>
            </Notice>
            <HistoricalExplorer
              {...ctx}
              researchQuestion="historical"
              embedded
              preview
            />
          </>
        )}
        {loadable
          .filter(
            (d) =>
              String(
                (d as unknown as Record<string, unknown>).provider || d.id,
              ).includes("participation") || d.id.startsWith("uf-"),
          )
          .slice(0, 1)
          .map((d) => (
            <DatasetDownload
              key={d.id}
              dataset={d}
              state={query.state}
              automatic={
                query.revision == null &&
                !hasCurrent &&
                !workspace.coverage?.available_metrics?.length
              }
            />
          ))}
      </section>
      <section id="state-participation" className="dossier-section">
        <h2 className="dossier-section-title">Participation, over time.</h2>
        <EarlyVotingGuide {...ctx}/>
        <div className="chart-grid">
          <Panel
            title="Latest reported changes"
            subtitle="Reporting batches do not necessarily show when voting occurred."
          >
            <ChangeChart series={current} />
          </Panel>
          <Panel
            title="Voting-method composition"
            subtitle="Compatible published categories retain their actual definitions."
          >
            <ModeChart
              observations={workspace.observations}
              cycle={query.cycle}
            />
          </Panel>
          <Panel
            title="Reporting calendar"
            subtitle="Each cell is an actual observation, with change since the preceding report."
          >
            <ReportingCalendar
              observations={workspace.observations.filter(
                (o) => o.cycle === query.cycle,
              )}
            />
          </Panel>
          <Panel
            title="Historical endpoint references"
            subtitle="Latest available observations are references, not current turnout denominators."
          >
            <EndpointLadder
              observations={workspace.observations}
              cycle={query.cycle}
            />
          </Panel>
        </div>
      </section>
      <section id="state-geography" className="dossier-section">
        <h2 className="dossier-section-title">The places behind the total.</h2>
        <div className="chart-grid">
          <Panel
            title="Largest geographic contributors"
            subtitle="Select a place to coordinate its evidence across this investigation."
          >
            <GeographyBars
              rows={rows}
              selected={(ctx.selectedGeographyIds ?? query.geography_ids)}
              onSelect={select}
            />
          </Panel>
          <Panel
            title="Compare selected place trajectories"
            subtitle="Each place retains its own observed series."
          >
            <PlaceTrajectories
              series={analytics.data?.series_by_place}
              observations={workspace.observations}
              selected={(ctx.selectedGeographyIds ?? query.geography_ids)}
            />
          </Panel>
          <Panel title="Contributions to newly reported change">
            <ContributionWaterfall
              rows={analytics.data?.geographic_research?.waterfall || []}
              onSelect={select}
            />
          </Panel>
          <Panel title="Geographic concentration">
            <ConcentrationChart rows={rows} />
            <ResearchGuide
              what="Cumulative reported ballots as the largest places are added."
              how="Read the horizontal axis as the share of reporting areas, and the vertical axis as their share of ballots. Population and geographic scale help explain concentration."
            />
          </Panel>
        </div>
        <button
          className="button secondary"
          onClick={() => {
            ctx.setResearchQuestion?.("participation");
            ctx.setPage("atlas");
          }}
        >
          Open geographic evidence table
          <ArrowRight size={14} />
        </button>
      </section>
      <section id="state-composition" className="dossier-section">
        <h2 className="dossier-section-title">Who is participating?</h2>
        <div className="chart-grid">
          <Panel
            title="Published voter composition"
            subtitle="Only directly supported categories appear."
            actions={
              dims.length ? (
                <Select
                  label="Composition dimension"
                  value={dim || dims[0]}
                  onChange={setDim}
                  options={dims.map((d) => ({ value: d, label: human(d) }))}
                />
              ) : undefined
            }
          >
            <CompositionChart rows={composition} dimension={dim || dims[0]} />
            <ResearchGuide
              what="The source's reported categories among current participants."
              how="These categories describe participation, not candidate choice. Separate demographic totals cannot establish joint demographic combinations."
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
                      <th>Reported</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {composition
                      .filter((r) => r.dimension === (dim || dims[0]))
                      .map((r, i) => (
                        <tr key={i}>
                          <td>{human(r.dimension)}</td>
                          <td>{r.category}</td>
                          <td className="numeric">{fmt(r.value)}</td>
                          <td>
                            <button
                              className="icon-button"
                              aria-label={`Inspect ${r.category}`}
                              onClick={() =>
                                r.observation_ids[0] &&
                                inspect({
                                  type: "observation",
                                  id: r.observation_ids[0],
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
              <Empty title="No compatible voter-composition records">
                Population context below remains separate from the identity of
                actual voters.
              </Empty>
            )}
          </Panel>
        </div>
      </section>
      <section id="state-history" className="dossier-section">
        <h2 className="dossier-section-title">
          Election history and geographic trends.
        </h2>
        <HistoricalExplorer {...ctx} embedded researchQuestion="historical" />
      </section>
      <section id="state-polls" className="dossier-section">
        <h2 className="dossier-section-title">What the polls actually show.</h2>
        <Polls {...ctx} embedded />
      </section>
      <section id="state-context" className="dossier-section">
        <h2 className="dossier-section-title">
          People, calendars, and election rules.
        </h2>
        <PopulationContext {...ctx} />
        <Panel title="Election calendar and source context">
          <div className="calendar-context">
            {workspace.calendar?.map((e, i) => (
              <div key={i}>
                <CalendarDays size={18} />
                <span>
                  <b>{e.label}</b>
                  <small>{dateLabel(e.date)}</small>
                </span>
                <a href={e.source_url} target="_blank" rel="noreferrer">
                  Original authority
                  <ArrowRight size={13} />
                </a>
              </div>
            ))}
          </div>
          <Notice>
            Native reporting geographies and counting systems are preserved. A
            prior place's partisan margin does not identify how its early voters
            voted.
          </Notice>
        </Panel>
      </section>
      <section id="state-evidence" className="dossier-section">
        <h2 className="dossier-section-title">Findings you can inspect.</h2>
        <div className="dossier-detail-grid">
          <Panel
            title="State research brief"
            subtitle="Deterministic findings from the current filters and evidence revision."
          >
            {sections.map((s, i) => (
              <section key={i} className="brief-section">
                <h3>{s.title}</h3>
                <p>
                  {s.text ||
                    s.body ||
                    s.sentences?.map((x) => x.text).join(" ")}
                </p>
                {Array.isArray(s.observation_ids) &&
                  s.observation_ids.length > 0 && (
                    <button
                      className="text-button"
                      onClick={() =>
                        inspect({
                          type: "observation",
                          id: Number((s.observation_ids as number[])[0]),
                        })
                      }
                    >
                      <FileSearch size={13} />
                      Inspect evidence
                    </button>
                  )}
              </section>
            ))}
          </Panel>
          <div>
            <Panel title="Original evidence and collection health">
              <div className="source-mini-list">
                {workspace.sources?.map((s) => (
                  <button
                    key={s.id}
                    className="source-mini-row"
                    onClick={() =>
                      inspect({ type: "source", id: s.id, data: s })
                    }
                  >
                    <span>
                      {s.name}
                      <small>
                        {s.data_as_of
                          ? dateLabel(s.data_as_of)
                          : "Source inventory"}
                      </small>
                    </span>
                    <Status value={s.status || "not_collected"} />
                  </button>
                ))}
              </div>
            </Panel>
            <Panel title="More detail, on demand">
              {loadable.length ? (
                loadable.map((d) => (
                  <DatasetDownload key={d.id} dataset={d} state={query.state} />
                ))
              ) : (
                <p className="muted">
                  All currently supported datasets for this state are already
                  available locally. The dataset catalog records additional
                  source limitations.
                </p>
              )}
            </Panel>
          </div>
        </div>
      </section>
    </>
  );
}
