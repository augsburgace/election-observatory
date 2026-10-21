import { useFocusedGeography, focusGeography } from "../interaction";
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { atlasApi } from "../atlasApi";
import HistoricalExplorer from "../components/HistoricalExplorer";
import PopulationContext from "../components/PopulationContext";
import EarlyVotingGuide from "../components/EarlyVotingGuide";
import {
  PlaceTrajectories,
  ContributionWaterfall,
  ConcentrationChart,
} from "../components/ResearchCharts";
import { ResearchGuide } from "../components/ResearchGuide";
import {
  ArrowRight,
  Bookmark,
  Columns2,
  FileSearch,
  Layers,
  MapPin,
  Search,
  X,
} from "lucide-react";
import type { AppContext, GeoRow } from "../types";
import { StateMap, MapLayerControl } from "../components/Maps";
import type { MapLayer } from "../components/Maps";
import { GeographyBars, SeriesChart } from "../components/Charts";
import { Badge, Empty, Notice, Panel, Segmented } from "../components/ui";
import { api } from "../api";
import { useViewOption } from "../viewState";
import { compact, fmt, stateName } from "../utils";
export default function Atlas(ctx: AppContext & { embedded?: boolean }) {
  const { workspace, query, setQuery, inspect, notify, embedded } = ctx;
  const [layer, setLayer] = useViewOption<MapLayer>("atlas_layer", "volume");
  const [mode, setMode] = useViewOption<
    "single" | "side" | "swipe" | "difference"
  >("atlas_compare", "single");
  const focused = useFocusedGeography();
  const [search, setSearch] = useState("");
  const [swipe, setSwipe] = useState(50);
  const [onlySelected, setOnlySelected] = useState(false);
  const analytics = useQuery({
    queryKey: ["atlas", "analytics", query],
    queryFn: ({ signal }) => atlasApi.analytics(query, signal),
  });
  const rows = workspace.geographies || [];
  const hasBaseline = rows.some((row) => row.baseline_value != null);
  const hasRate = rows.some((row) => row.denominator != null);
  const baseline = useMemo(
    () =>
      rows
        .filter((r) => r.baseline_value != null)
        .map((r) => ({
          ...r,
          value: r.baseline_value!,
          denominator: null,
          share:
            r.baseline_value! /
            rows.reduce((total, row) => total + (row.baseline_value || 0), 0),
        })),
    [rows],
  );
  const filtered = rows
    .filter(
      (row) =>
        (!onlySelected || (ctx.selectedGeographyIds ?? query.geography_ids).includes(row.id)) &&
        row.name.toLowerCase().includes(search.toLowerCase()),
    )
    .sort((a, b) => b.value - a.value);
  const select = (id: string) =>
    setQuery({
      geography_ids: (ctx.selectedGeographyIds ?? query.geography_ids).includes(id)
        ? (ctx.selectedGeographyIds ?? query.geography_ids).filter((v) => v !== id)
        : [...(ctx.selectedGeographyIds ?? query.geography_ids), id],
    });
  async function bookmark(row: GeoRow) {
    try {
      await api.saveResearch({
        kind: "bookmark",
        title: `${row.name} · ${stateName(query.state)}`,
        view: {
          query: {
            ...query,
            geography_ids: [row.id],
            revision: workspace.revision,
          },
          page: "atlas",
          layer,
          mode,
        },
      });
      notify(`${row.name} bookmarked.`);
    } catch (e) {
      notify((e as Error).message);
    }
  }
  const actualLayer = mode === "difference" ? "change" : layer;
  const scaleMax =
    actualLayer === "volume"
      ? Math.max(
          1,
          ...rows.map((r) => r.value),
          ...baseline.map((r) => r.value),
        )
      : actualLayer === "share"
        ? Math.max(
            0.01,
            ...rows.map((r) => r.share || 0),
            ...baseline.map((r) => r.share || 0),
          )
        : undefined;
  const evidenceLabel = `${stateName(query.state)} · ${query.metric} · ${actualLayer} · r${workspace.revision}`;
  if (ctx.researchQuestion === "historical" || ctx.researchQuestion === "swing")
    return <HistoricalExplorer {...ctx} />;
  if (ctx.researchQuestion === "context")
    return (
      <>
        <div className="page-intro">
          <div>
            <h2>People and places.</h2>
            <p>Published population context, with periods and uncertainty.</p>
          </div>
        </div>
        <PopulationContext {...ctx} />
      </>
    );
  return (
    <>
      {!embedded && (
        <div className="page-intro">
          <div>
            <h2>The geographic research atlas.</h2>
            <p>
              Find the places behind the statewide picture. Select, compare, and
              follow each observation back to its source.
            </p>
          </div>
          <Badge tone="teal">
            <MapPin size={12} />
            {stateName(query.state)}
          </Badge>
        </div>
      )}
      {!rows.length && (
        <Notice tone="warning">
          This explicit current-voting investigation has no compatible
          geographic breakdown. Statewide evidence remains available.{" "}
          <button
            className="text-button"
            onClick={() => ctx.setResearchQuestion?.("historical")}
          >
            Explore verified historical results
            <ArrowRight size={13} />
          </button>
        </Notice>
      )}
      {!rows.length && (
        <Panel
          title="Available statewide trajectory"
          subtitle="Current geographic detail is unavailable, while supported statewide evidence remains usable."
        >
          <SeriesChart
            series={workspace.series}
            observations={workspace.observations}
            alignment={query.alignment}
          />
          {workspace.coverage?.available_metrics?.length ? (
            <div className="metric-links">
              {workspace.coverage.available_metrics.map((m) => (
                <button key={m} onClick={() => setQuery({ metric: m })}>
                  {m.replaceAll("_", " ")}
                </button>
              ))}
            </div>
          ) : null}
        </Panel>
      )}
      <EarlyVotingGuide {...ctx}/>
      <div className="atlas-toolbar">
        <MapLayerControl value={layer} onChange={setLayer} />
        <Segmented
          value={mode}
          onChange={setMode}
          label="Map comparison mode"
          items={[
            { id: "single", label: "Single" },
            { id: "side", label: "Side by side", disabled: !hasBaseline },
            { id: "swipe", label: "Swipe", disabled: !hasBaseline },
            { id: "difference", label: "Difference", disabled: !hasBaseline },
          ]}
        />
      </div>
      {actualLayer === "change" && !hasBaseline && (
        <Notice tone="warning">
          No compatible geographic baseline is available. Missing differences
          are not treated as zero.
        </Notice>
      )}
      {layer === "participation" && !hasRate && (
        <Notice tone="warning">
          A dated, compatible registration denominator is not available.
          Participation rates remain unavailable.
        </Notice>
      )}
      <Panel
        title={`${stateName(query.state)} · ${mode === "difference" ? "matched historical change" : layer === "volume" ? "reported ballot volume" : layer === "share" ? "share of geographic activity" : layer === "participation" ? "participation rate" : "source coverage"}`}
        subtitle="Reporting boundaries retain their official geography and vintage. Select a place on the map or in the table."
        exportLabel={evidenceLabel}
        actions={
          (ctx.selectedGeographyIds ?? query.geography_ids).length > 0 ? (
            <button
              className="text-button"
              onClick={() => setQuery({ geography_ids: [] })}
            >
              Clear {(ctx.selectedGeographyIds ?? query.geography_ids).length} selections
              <X size={12} />
            </button>
          ) : undefined
        }
        className="atlas-map-panel"
      >
        {mode === "side" ? (
          <div className="map-comparison">
            <div>
              <div className="map-period-label">
                {query.cycle} · current evidence
              </div>
              <StateMap
                state={query.state}
                rows={rows}
                selected={(ctx.selectedGeographyIds ?? query.geography_ids)}
                onSelect={select}
                layer={actualLayer}
                scaleMax={scaleMax}
                height={390}
              />
            </div>
            <div>
              <div className="map-period-label">
                {query.baseline} · compatible baseline
              </div>
              <StateMap
                state={query.state}
                rows={baseline}
                selected={(ctx.selectedGeographyIds ?? query.geography_ids)}
                onSelect={select}
                layer={actualLayer}
                scaleMax={scaleMax}
                height={390}
              />
            </div>
          </div>
        ) : mode === "swipe" ? (
          <>
            <div className="swipe-map">
              <StateMap
                state={query.state}
                rows={rows}
                selected={(ctx.selectedGeographyIds ?? query.geography_ids)}
                onSelect={select}
                layer={actualLayer}
                scaleMax={scaleMax}
                height={450}
              />
              <div
                className="swipe-overlay"
                style={{ clipPath: `inset(0 ${100 - swipe}% 0 0)` }}
              >
                <StateMap
                  state={query.state}
                  rows={baseline}
                  selected={(ctx.selectedGeographyIds ?? query.geography_ids)}
                  onSelect={select}
                  layer={actualLayer}
                  scaleMax={scaleMax}
                  height={450}
                />
              </div>
              <div className="swipe-line" style={{ left: `${swipe}%` }}>
                <span>
                  <Columns2 size={16} />
                </span>
              </div>
              <div className="swipe-label left">{query.baseline}</div>
              <div className="swipe-label right">{query.cycle}</div>
            </div>
            <label className="swipe-control">
              Historical comparison divider
              <input
                type="range"
                min={5}
                max={95}
                value={swipe}
                onChange={(e) => setSwipe(Number(e.target.value))}
              />
            </label>
          </>
        ) : (
          <StateMap
            state={query.state}
            rows={rows}
            selected={(ctx.selectedGeographyIds ?? query.geography_ids)}
            onSelect={select}
            layer={actualLayer}
            scaleMax={scaleMax}
            height={450}
          />
        )}
      </Panel>
      <div className="atlas-analysis-grid">
        <Panel
          title="Reporting-area contributions"
          subtitle="Reported volume ranks the places included in the current evidence view."
          exportLabel={evidenceLabel}
        >
          <GeographyBars
            rows={rows}
            selected={(ctx.selectedGeographyIds ?? query.geography_ids)}
            onSelect={select}
          />
        </Panel>
        <Panel
          title="Selected geographic trajectory"
          subtitle={
            (ctx.selectedGeographyIds ?? query.geography_ids).length
              ? `${(ctx.selectedGeographyIds ?? query.geography_ids).length} selected reporting areas · individually labeled source trajectories`
              : "Select places to investigate their participation over time."
          }
          exportLabel={evidenceLabel}
        >
          <PlaceTrajectories
            series={analytics.data?.series_by_place}
            observations={workspace.observations}
            selected={(ctx.selectedGeographyIds ?? query.geography_ids)}
          />
          <ResearchGuide
            what="A separate reported trajectory for every selected place."
            how="Select two or more areas to compare their source observations. Missing dates are not invented."
            source="Original observations at the selected evidence revision"
          />
        </Panel>
      </div>
      <div className="chart-grid">
        <Panel
          title="Which places explain the change?"
          subtitle="Signed contributions between actual compatible source observations."
        >
          <ContributionWaterfall
            rows={analytics.data?.geographic_research?.waterfall || []}
            onSelect={select}
          />
        </Panel>
        <Panel
          title="How concentrated is participation?"
          subtitle="Reporting areas ranked from the largest observed volume to the smallest."
        >
          <ConcentrationChart rows={rows} />
          <ResearchGuide
            what="The cumulative share of reported ballots across ranked places."
            how="A steep curve means a small share of places accounts for a large share of voting. Geography size and population also matter."
            source="Selected geographic aggregate observations"
          />
        </Panel>
      </div>
      <Panel
        title="Geographic evidence table"
        subtitle="A keyboard-accessible companion to the map."
      >
        <div className="table-toolbar">
          <div className="search-field">
            <Search size={14} />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Find a reporting area…"
              aria-label="Search reporting areas"
            />
          </div>
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={onlySelected}
              onChange={(e) => setOnlySelected(e.target.checked)}
            />
            Selected places only
          </label>
          <span className="table-count">{filtered.length} places</span>
        </div>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>
                  <span className="sr-only">Selection</span>
                </th>
                <th>Reporting area</th>
                <th>Current</th>
                <th>{query.baseline} baseline</th>
                <th>Change</th>
                <th>Share</th>
                <th>Evidence</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {filtered.map((row) => (
                <tr
                  key={row.id}
                  onMouseEnter={() => focusGeography(row.id)}
                  onMouseLeave={() => focusGeography(null)}
                  className={
                    (ctx.selectedGeographyIds ?? query.geography_ids).includes(row.id)
                      ? "selected"
                      : focused === row.id
                        ? "focused-geography"
                        : ""
                  }
                >
                  <td>
                    <input
                      type="checkbox"
                      checked={(ctx.selectedGeographyIds ?? query.geography_ids).includes(row.id)}
                      onChange={() => select(row.id)}
                      aria-label={`Select ${row.name}`}
                    />
                  </td>
                  <td>
                    <button
                      className="text-button"
                      onClick={() => select(row.id)}
                    >
                      {row.name}
                    </button>
                    <small>
                      {row.type} · {row.id}
                    </small>
                  </td>
                  <td className="numeric">{fmt(row.value)}</td>
                  <td className="numeric">{fmt(row.baseline_value)}</td>
                  <td
                    className={`numeric ${row.change != null && row.change < 0 ? "orange-text" : "cyan-text"}`}
                  >
                    {row.change == null
                      ? "—"
                      : `${row.change > 0 ? "+" : ""}${fmt(row.change)}`}
                  </td>
                  <td>
                    {row.share == null
                      ? "—"
                      : `${(row.share * 100).toFixed(1)}%`}
                  </td>
                  <td>
                    <button
                      className="button small secondary"
                      disabled={!row.observation_ids?.length}
                      onClick={() =>
                        inspect({
                          type: "observation",
                          id: row.observation_ids[0],
                        })
                      }
                    >
                      <FileSearch size={13} />
                      Inspect
                    </button>
                  </td>
                  <td>
                    <button
                      className="icon-button"
                      onClick={() => bookmark(row)}
                      aria-label={`Bookmark ${row.name}`}
                    >
                      <Bookmark size={14} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!filtered.length && (
            <Empty title="No reporting areas match">
              Geographic detail appears when the original source provides it and
              can be joined to defensible boundaries.
            </Empty>
          )}
        </div>
      </Panel>
      <div className="bottom-info-grid">
        <Notice>
          A place’s prior partisan results provide context. They do not identify
          how its early voters chose in this Senate race.
        </Notice>
        <div className="mini-method">
          <Layers size={15} />
          <span>
            {rows.length} reporting areas ·{" "}
            {compact(rows.reduce((sum, row) => sum + row.value, 0))} geographic
            observations
          </span>
          <ArrowRight size={13} />
        </div>
      </div>
    </>
  );
}
