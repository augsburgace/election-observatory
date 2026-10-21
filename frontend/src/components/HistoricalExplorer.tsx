import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, FileSearch, Search } from "lucide-react";
import { atlasApi, type Results, type ResultGeo } from "../atlasApi";
import type { AppContext, GeoRow } from "../types";
import { StateMap } from "./Maps";
import { initialResultGrain } from "../researchDefaults";
import { signedPartisanMargin, summarizeOptions } from "../chartMath";
import {
  HistoricalScatter,
  VoteDistribution,
  HistoricalShareChart,
} from "./ResearchCharts";
import { ResearchGuide } from "./ResearchGuide";
import { DatasetDownload } from "./DownloadStatus";
import { Empty, Loading, Notice, Panel, Segmented, Select } from "./ui";
import { fmt, human, stateName, partyColor } from "../utils";
import { useFocusedGeography, focusGeography } from "../interaction";
import { useViewOption } from "../viewState";
import AtlasComparison from "./AtlasComparison";
import PrecinctExplorer from "./PrecinctExplorer";
export function signedMargin(row: ResultGeo) {
  return signedPartisanMargin(row);
}
export function resultRows(result?: Results, layer = "margin"): GeoRow[] {
  return (result?.geographies || []).map((r) => ({
    id: r.id,
    canonical_id: r.id,
    name: r.name,
    type: r.level,
    value: r.total_votes,
    baseline_value: null,
    change:
      layer === "swing"
        ? r.swing_pp == null
          ? null
          : -r.swing_pp
        : signedMargin(r),
    share: null,
    denominator: null,
    source_ids: [],
    observation_ids: [],
  }));
}
export default function HistoricalExplorer(
  ctx: AppContext & { embedded?: boolean; preview?: boolean },
) {
  const {
    query,
    setQuery,
    setPage,
    resultYear = 2024,
    resultOffice = "PRESIDENT",
    researchQuestion = "historical",
  } = ctx;
  const [layer, setLayer] = useViewOption<
    "margin" | "swing" | "volume" | "option"
  >("results_layer", researchQuestion === "swing" ? "swing" : "margin");
  const focused = useFocusedGeography();
  const [optionId, setOptionId] = useViewOption<string>("result_option", "");
  const boundRevision = query.revision ?? ctx.workspace.revision;
  const [offsetText, setOffsetText] = useViewOption<string>(
    "result_offset",
    "0",
  );
  const offset = Math.max(0, Number(offsetText) || 0);
  const setOffset = (value: number) => setOffsetText(String(value));
  const [search, setSearch] = useState(""),
    [sort, setSort] = useViewOption<string>("results_sort", "volume");
  const [contest, setContest] = useViewOption<string>("result_contest", "");
  const [storedGrain, setGrain] = useViewOption<string>(
    "result_grain",
    initialResultGrain(query.state, resultOffice),
  );
  const explicitGrain =
    new URLSearchParams(location.search).get("ui_result_grain") ||
    new URLSearchParams(location.search).get("ui_results_grain");
  const grain = initialResultGrain(
    query.state,
    resultOffice,
    explicitGrain
      ? new URLSearchParams(location.search).has("ui_result_grain")
        ? storedGrain
        : explicitGrain
      : null,
  );
  const catalog = useQuery({
    queryKey: [
      "atlas",
      "contest-list",
      query.state,
      resultYear,
      resultOffice,
      boundRevision,
    ],
    queryFn: () =>
      atlasApi.contests({
        state: query.state,
        year: resultYear,
        office: resultOffice,
        revision: boundRevision,
        limit: 500,
      }),
  });
  const contests = (catalog.data?.contests || []).filter(
    (c) => c.year === resultYear,
  );
  const activeContest =
    contest && contests.some((c) => c.id === contest)
      ? contest
      : contests.length > 1
        ? contests[0].id
        : "";
  useEffect(() => {
    if (!contest && contests.length > 1) setContest(contests[0].id);
  }, [contest, contests.map((c) => c.id).join(",")]);
  const scopeKey = [query.state, resultYear, resultOffice, grain, search].join(
    "|",
  );
  const previousScope = useRef(scopeKey);
  useEffect(() => {
    if (previousScope.current !== scopeKey) {
      previousScope.current = scopeKey;
      setOffset(0);
    }
  }, [scopeKey]);
  const localPaging = grain === "county" || grain === "state";
  const result = useQuery({
    queryKey: [
      "atlas",
      "results",
      query.state,
      resultYear,
      resultOffice,
      boundRevision,
      activeContest,
      grain,
      localPaging ? 0 : offset,
    ],
    queryFn: ({ signal }) =>
      atlasApi.results(
        {
          state: query.state,
          year: resultYear,
          office: resultOffice,
          baseline: resultYear - 4,
          geography_level: grain,
          contest_id: activeContest || undefined,
          limit: localPaging ? undefined : 200,
          offset: localPaging ? 0 : offset,
          revision: boundRevision,
        },
        signal,
      ),
  });
  const datasets = useQuery({
    queryKey: ["atlas", "datasets", query.state],
    queryFn: () => atlasApi.datasets(query.state),
  });
  const selected = (result.data?.geographies || []).filter((r) =>
    (ctx.selectedGeographyIds ?? query.geography_ids).includes(r.id),
  );
  const focus =
    selected[0] ||
    result.data?.geographies.reduce<ResultGeo | undefined>(
      (top, r) => (!top || r.total_votes > top.total_votes ? r : top),
      undefined,
    );
  const hasPartisan = (result.data?.geographies || []).some(
    (r) => r.dem_share_pct != null && r.rep_share_pct != null,
  );
  const explicitLayer = new URLSearchParams(location.search).has(
    "ui_results_layer",
  );
  const actualLayer =
    researchQuestion === "swing"
      ? "swing"
      : !hasPartisan &&
          !explicitLayer &&
          query.revision == null &&
          layer === "margin"
        ? "volume"
        : layer;
  const optionOptions = Array.from(
    new Map(
      (result.data?.geographies || [])
        .flatMap((r) => r.options)
        .map((o) => [o.id, o]),
    ).values(),
  );
  const chosenOption =
    optionOptions.find((o) => o.id === optionId) || optionOptions[0];
  const rows = useMemo(
    () =>
      resultRows(result.data, actualLayer).map((row, index) =>
        actualLayer === "option"
          ? {
              ...row,
              share:
                result.data?.geographies[index].options.find(
                  (o) => o.id === chosenOption?.id,
                )?.share_pct == null
                  ? null
                  : result.data.geographies[index].options.find(
                      (o) => o.id === chosenOption?.id,
                    )!.share_pct / 100,
            }
          : row,
      ),
    [result.data, actualLayer, chosenOption?.id],
  );
  const ordered = [...(result.data?.geographies || [])]
    .filter((r) => r.name.toLowerCase().includes(search.toLowerCase()))
    .sort((a, b) =>
      sort === "name"
        ? a.name.localeCompare(b.name)
        : sort === "margin"
          ? Math.abs(signedMargin(b) || 0) - Math.abs(signedMargin(a) || 0)
          : b.total_votes - a.total_votes,
    );
  const pageSize = localPaging ? 50 : 200;
  const visibleRows = localPaging
    ? ordered.slice(offset, offset + pageSize)
    : ordered;
  const totalAreas =
    result.data?.pagination?.total_geographies ?? ordered.length;
  const select = (id: string) =>
    setQuery({
      geography_ids: (ctx.selectedGeographyIds ?? query.geography_ids).includes(id)
        ? (ctx.selectedGeographyIds ?? query.geography_ids).filter((x) => x !== id)
        : [id, ...(ctx.selectedGeographyIds ?? query.geography_ids)].slice(0, 8),
    });
  const total =
    typeof result.data?.summary.total_votes === "number"
      ? result.data.summary.total_votes
      : 0;
  const completeShares = summarizeOptions(
    result.data?.geographies || [],
  ).complete;
  const stateVotes =
    total > 0
      ? Array.from(
          (result.data?.geographies || [])
            .reduce((map, r) => {
              r.options.forEach((o) => {
                const prev = map.get(o.name) || { ...o, votes: 0 };
                prev.votes += o.votes;
                map.set(o.name, prev);
              });
              return map;
            }, new Map<string, ResultGeo["options"][number]>())
            .values(),
        ).sort((a, b) => b.votes - a.votes)
      : [];
  if (result.isPending)
    return (
      <Loading label={`Opening ${stateName(query.state)} election history…`} />
    );
  return (
    <div className="historical-explorer">
      {!ctx.embedded && (
        <div className="editorial-state-heading">
          <div>
            <h2>
              {stateName(query.state)} <span>Election atlas</span>
            </h2>
            <p>
              {resultYear} {human(resultOffice).toLowerCase()} · verified
              historical results
            </p>
          </div>
          <div className="editorial-totals">
            <div>
              <strong>{rows.length ? fmt(total) : "—"}</strong>
              <span>Candidate / option votes</span>
            </div>
            {stateVotes.slice(0, 2).map((o) => (
              <div key={o.name}>
                <strong style={{ color: partyColor(o.party) }}>
                  {total && completeShares
                    ? fmt((o.votes / total) * 100, 1) + "%"
                    : "—"}
                </strong>
                <span>
                  {o.name} ({o.party})
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
      <div className="historical-coverage-strip">
        <span>{rows.length} loaded reporting areas</span>
        <span>Revision {result.data?.revision}</span>
        <span>Historical published returns</span>
        <span>
          {result.data?.sources.length || 0} attributed source snapshots
        </span>
      </div>
      {result.data?.warnings
        .filter((w) =>
          /differ from|not been reconciled|suppression|incomplete/i.test(w),
        )
        .map((warning, i) => (
          <Notice key={i} tone="warning">
            {warning}
          </Notice>
        ))}
      <div className="result-evidence-controls primary-result-grain">
        {contests.length > 1 && (
          <Select
            label="Historical contest"
            value={activeContest}
            onChange={(value) => {
              setContest(value);
              setOffset(0);
            }}
            options={contests.map((c) => ({
              value: c.id,
              label: c.name || c.title || c.id,
            }))}
          />
        )}
        <Select
          label="Historical geographic detail"
          value={grain}
          onChange={setGrain}
          options={[
            { value: "state", label: "Statewide results" },
            { value: "county", label: "County / reporting-area results" },
            { value: "district", label: "District results" },
            { value: "precinct", label: "Precinct results" },
          ]}
        />
      </div>
      {!ctx.preview && !rows.length && grain === "precinct" && (
        <PrecinctExplorer {...ctx} year={resultYear} office={resultOffice} />
      )}
      {result.isError ? (
        <Notice tone="warning">
          {result.error.message}. Historical records already loaded remain on
          disk.
        </Notice>
      ) : !rows.length ? (
        <>
          <Empty title="This selection has no compatible results">
            {query.state === "AK" && grain === "county"
              ? "Alaska's loaded election records use statewide or native reporting geographies. A compatible county or borough breakdown is not attached to this selection. Open verified statewide results below."
              : `${resultYear} ${human(resultOffice).toLowerCase()} results are unavailable at the selected ${grain} level and evidence revision. The catalog may contain other years, offices, or geographic levels; this does not mean the state's entire dataset is missing.`}
          </Empty>
          <button
            className="button secondary"
            onClick={() => setGrain("state")}
          >
            Open verified statewide results
            <ArrowRight size={14} />
          </button>
          {datasets.data?.datasets
            .filter(
              (d) =>
                d.on_demand &&
                d.offices.includes(resultOffice) &&
                d.years.includes(resultYear) &&
                !d.id.startsWith("uf-"),
            )
            .slice(0, 2)
            .map((d) => (
              <DatasetDownload
                key={d.id}
                dataset={d}
                state={query.state}
                automatic={query.revision == null}
              />
            ))}
        </>
      ) : (
        <>
          <div className="results-toolbar">
            <div className="result-tabs">
              <button className="active">Historical results</button>
              <button
                onClick={() => ctx.setResearchQuestion?.("participation")}
              >
                Participation
              </button>
              <button onClick={() => ctx.setResearchQuestion?.("context")}>
                Population context
              </button>
            </div>
            <Segmented
              label="Historical result layer"
              value={actualLayer}
              onChange={(v) => {
                setLayer(v);
                if (researchQuestion === "swing" && v !== "swing")
                  ctx.setResearchQuestion?.("historical");
              }}
              items={[
                { id: "margin", label: "Margin", disabled: !hasPartisan },
                { id: "swing", label: "Swing", disabled: !hasPartisan },
                { id: "volume", label: "Votes" },
                { id: "option", label: "Option share" },
              ]}
            />
          </div>
          {actualLayer === "swing" && !rows.some((r) => r.change != null) && (
            <Notice tone="warning">
              A defensible geographic crosswalk is required before showing
              change between these boundary vintages. Current results remain
              available; missing changes are not zero.
            </Notice>
          )}
          {actualLayer === "option" && (
            <div className="result-evidence-controls">
              <Select
                label="Candidate or ballot-option share"
                value={chosenOption?.id || ""}
                onChange={setOptionId}
                options={optionOptions.map((o) => ({
                  value: o.id,
                  label: `${o.name} (${o.party || o.kind || "Ballot option"})`,
                }))}
              />
            </div>
          )}
          {!hasPartisan && ["margin", "swing"].includes(actualLayer) && (
            <Notice tone="warning">
              This contest has no published Democratic-versus-Republican
              quantities. Use candidate / option votes or a named option's
              share.{" "}
              <button
                className="text-button"
                onClick={() => setLayer("volume")}
              >
                Show valid vote totals
              </button>
            </Notice>
          )}
          <div className="results-main-grid">
            <Panel
              title={`${stateName(query.state)} · ${actualLayer === "swing" ? "change from " + (resultYear - 4) : actualLayer === "volume" ? "candidate / option votes" : "partisan margin"}`}
              subtitle={`${resultYear} ${human(resultOffice).toLowerCase()} · select a reporting area`}
              className="results-map-panel"
              exportLabel={`${query.state} · ${resultYear} · ${resultOffice} · ${actualLayer} · revision ${result.data?.revision}`}
            >
              {grain === "precinct" || grain === "district" ? (
                <Notice tone="warning">
                  These native {grain} returns retain their source identities.
                  The precinct workspace below opens a matching, verified
                  boundary bundle when available. Values are never painted onto
                  county boundaries.
                </Notice>
              ) : (
                <StateMap
                  state={query.state}
                  rows={rows}
                  selected={(ctx.selectedGeographyIds ?? query.geography_ids)}
                  onSelect={select}
                  layer={actualLayer === "option" ? "share" : actualLayer}
                  height={510}
                  metricLabel={
                    actualLayer === "volume"
                      ? "Candidate / option votes"
                      : actualLayer === "option"
                        ? `${chosenOption?.name || "Ballot option"} share of candidate / option votes`
                        : undefined
                  }
                />
              )}
              <ResearchGuide
                what={
                  actualLayer === "volume"
                    ? "The number of candidate or ballot-option votes recorded in this contest."
                    : actualLayer === "option"
                      ? `The published share of candidate / option votes for ${chosenOption?.name || "the selected option"}.`
                      : "Historical Republican minus Democratic vote share by reporting area."
                }
                how={
                  actualLayer === "volume"
                    ? "Circle area represents the number of candidate / option votes."
                    : actualLayer === "option"
                      ? "Stronger teal indicates a larger published share. Missing option estimates remain missing, rather than being assumed to be zero."
                      : "Blue means a Democratic advantage; red means a Republican advantage. Stronger colors mean larger margins. Select places to inspect complete distributions."
                }
                source={String(
                  result.data?.sources[0]?.url ||
                    "Attributed original records and documented research datasets",
                )}
              />
            </Panel>
            <aside className="results-place-inspector">
              {focus && (
                <>
                  <Panel
                    title={focus.name}
                    subtitle={`${stateName(query.state)} · ${focus.level} · ${resultYear}`}
                    actions={
                      <button
                        className="text-button"
                        onClick={() => {
                          const p = new URLSearchParams(location.search);
                          p.set("ui_place", focus.id);
                          history.replaceState(null, "", `?${p}`);
                          setPage("place");
                        }}
                      >
                        Place profile
                        <ArrowRight size={13} />
                      </button>
                    }
                  >
                    <div className="selected-place-volume">
                      <b>{fmt(focus.total_votes)}</b>
                      <span>
                        candidate / option votes ·{" "}
                        {total
                          ? fmt((focus.total_votes / total) * 100, 1)
                          : "—"}
                        % of loaded geographic votes
                      </span>
                    </div>
                    <VoteDistribution rows={[focus]} />
                    <div className="place-metric-pair">
                      <div>
                        <span>Partisan margin</span>
                        <strong
                          style={{
                            color:
                              (signedMargin(focus) || 0) > 0
                                ? "var(--red)"
                                : "var(--blue)",
                          }}
                        >
                          {signedMargin(focus) == null
                            ? "—"
                            : `${signedMargin(focus)! > 0 ? "R" : "D"} +${fmt(Math.abs(signedMargin(focus)!), 1)} pp`}
                        </strong>
                      </div>
                      <div>
                        <span>Change since {resultYear - 4}</span>
                        <strong>
                          {focus.swing_pp == null
                            ? "—"
                            : `${focus.swing_pp > 0 ? "D" : "R"} +${fmt(Math.abs(focus.swing_pp), 1)} pp`}
                        </strong>
                      </div>
                    </div>
                    <ResearchGuide
                      what="Complete published response totals for this historical contest."
                      how="Shares use all included ballot options. Third parties and write-ins retain separate identities where the source publishes them."
                      source="The source appendix below preserves producer and lineage."
                    />
                  </Panel>
                  <Panel
                    title="Historical candidate share"
                    subtitle={`${stateName(query.state)} statewide historical context · published returns`}
                  >
                    <HistoricalShareChart
                      history={result.data?.history || []}
                    />
                    <ResearchGuide
                      what="Statewide Democratic and Republican candidate shares across loaded elections."
                      how="These are published historical election results, not a same-boundary estimate of the selected county's change."
                      source="Original records and documented research datasets"
                    />
                  </Panel>
                </>
              )}
            </aside>
          </div>
          {!ctx.preview && (
            <>
              <AtlasComparison
                {...ctx}
                current={result.data!}
                year={resultYear}
                office={resultOffice}
                grain={grain}
                contest={activeContest}
              />
              <PrecinctExplorer
                {...ctx}
                year={resultYear}
                office={resultOffice}
              />
              <Panel
                title={`Reporting areas in ${stateName(query.state)}`}
                subtitle={`${ordered.length} areas · ${resultYear} ${human(resultOffice).toLowerCase()}`}
                className="results-table-panel"
              >
                <div className="table-toolbar">
                  <div className="search-field">
                    <Search size={14} />
                    <input
                      aria-label="Search historical reporting areas"
                      placeholder="Search counties or reporting areas…"
                      value={search}
                      onChange={(e) => setSearch(e.target.value)}
                    />
                  </div>
                  <select
                    aria-label="Sort historical places"
                    value={sort}
                    onChange={(e) => setSort(e.target.value)}
                  >
                    <option value="volume">Sort by vote total</option>
                    <option value="margin">Sort by margin</option>
                    <option value="name">Sort by name</option>
                  </select>
                  <span>
                    {selected.length
                      ? selected.length + " places selected"
                      : "Select places to compare"}
                  </span>
                </div>
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>#</th>
                        <th>Reporting area</th>
                        <th>Partisan margin</th>
                        <th>Democratic share</th>
                        <th>Republican share</th>
                        <th>Candidate / option votes</th>
                        <th>Change vs {resultYear - 4}</th>
                        <th />
                      </tr>
                    </thead>
                    <tbody>
                      {visibleRows.map((r, i) => {
                        const margin = signedMargin(r);
                        return (
                          <tr
                            key={r.id}
                            onMouseEnter={() => focusGeography(r.id)}
                            onMouseLeave={() => focusGeography(null)}
                            className={
                              (ctx.selectedGeographyIds ?? query.geography_ids).includes(r.id)
                                ? "selected"
                                : focused === r.id
                                  ? "focused-geography"
                                  : ""
                            }
                          >
                            <td>{offset + i + 1}</td>
                            <td>
                              <button
                                className="text-button"
                                onClick={() => select(r.id)}
                              >
                                {r.name}
                              </button>
                              <small>
                                {r.level} · {r.id}
                              </small>
                            </td>
                            <td>
                              <div className="margin-cell">
                                <b
                                  style={{
                                    color:
                                      margin != null && margin > 0
                                        ? "var(--red)"
                                        : "var(--blue)",
                                  }}
                                >
                                  {margin == null
                                    ? "—"
                                    : `${margin > 0 ? "R" : "D"} +${fmt(Math.abs(margin), 1)}`}
                                </b>
                                <i
                                  style={{
                                    width: `${Math.abs(margin || 0)}%`,
                                    background:
                                      margin != null && margin > 0
                                        ? "var(--red)"
                                        : "var(--blue)",
                                  }}
                                />
                              </div>
                            </td>
                            <td className="dem-value">
                              {r.dem_share_pct == null
                                ? "—"
                                : fmt(r.dem_share_pct, 1) + "%"}
                            </td>
                            <td className="rep-value">
                              {r.rep_share_pct == null
                                ? "—"
                                : fmt(r.rep_share_pct, 1) + "%"}
                            </td>
                            <td className="numeric">{fmt(r.total_votes)}</td>
                            <td
                              style={{
                                color:
                                  r.swing_pp != null && r.swing_pp > 0
                                    ? "var(--blue)"
                                    : "var(--red)",
                              }}
                            >
                              {r.swing_pp == null
                                ? "—"
                                : `${r.swing_pp > 0 ? "D" : "R"} +${fmt(Math.abs(r.swing_pp), 1)}`}
                            </td>
                            <td>
                              <button
                                className="icon-button"
                                aria-label={`Open ${r.name} profile`}
                                onClick={() => {
                                  const p = new URLSearchParams(
                                    location.search,
                                  );
                                  p.set("ui_place", r.id);
                                  history.replaceState(null, "", `?${p}`);
                                  setPage("place");
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
                {totalAreas > pageSize && (
                  <div className="table-pagination">
                    <button
                      className="button small secondary"
                      disabled={offset === 0}
                      onClick={() => setOffset(Math.max(0, offset - pageSize))}
                    >
                      Previous areas
                    </button>
                    <span>
                      {offset + 1}–{Math.min(offset + pageSize, totalAreas)} of{" "}
                      {totalAreas} reporting areas
                    </span>
                    <button
                      className="button small secondary"
                      disabled={offset + pageSize >= totalAreas}
                      onClick={() => setOffset(offset + pageSize)}
                    >
                      Next areas
                    </button>
                  </div>
                )}
              </Panel>
              <div className="chart-grid">
                <Panel
                  title="Geographic volume and partisan context"
                  subtitle="Every dot is a reporting area; votes are candidate / option votes."
                >
                  <HistoricalScatter
                    rows={result.data?.geographies || []}
                    onSelect={select}
                  />
                </Panel>
                <Panel
                  title="Complete contest distribution"
                  subtitle="Aggregate of disjoint reporting areas in the current view."
                >
                  <VoteDistribution rows={result.data?.geographies || []} />
                </Panel>
                <Panel title="Historical evidence and sources">
                  <div className="source-list">
                    {result.data?.sources.map((source, i) => (
                      <a
                        href={String(source.url || "")}
                        target="_blank"
                        rel="noreferrer"
                        key={i}
                      >
                        <FileSearch size={16} />
                        <span>
                          <b>
                            {String(
                              source.name ||
                                source.title ||
                                source.producer ||
                                "Source record",
                            )}
                          </b>
                          <small>
                            {String(source.license || source.url || "")}
                          </small>
                        </span>
                        <ArrowRight size={14} />
                      </a>
                    ))}
                  </div>
                  {result.data?.warnings.map((w, i) => (
                    <Notice key={i}>{w}</Notice>
                  ))}
                </Panel>
              </div>
            </>
          )}
        </>
      )}
    </div>
  );
}
