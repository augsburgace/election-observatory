import { publicFetch, isPublicMode } from "../publicData";
import { useEffect, useMemo, useRef, useState, useId } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { geoAlbersUsa, geoMercator, geoPath, geoCentroid } from "d3-geo";
import {
  Download,
  Layers,
  Maximize2,
  Minus,
  Plus,
  RotateCcw,
} from "lucide-react";
import type { AppContext, Job } from "../types";
import { atlasApi, type PrecinctMapData } from "../atlasApi";
import { request } from "../api";
import { createMapSpec, type MapLayer, type MapMetricRow } from "../mapSpec";
import { focusGeography } from "../interaction";
import { useViewOption } from "../viewState";
import { compact, fmt, human, stateName } from "../utils";
import { Empty, Loading, Notice, Panel, Segmented, Select } from "./ui";
import { ResearchGuide } from "./ResearchGuide";
import ExactMapThresholds from "./ExactMapThresholds";
import "../atlasDepth.css";

function precinctRow(properties: Record<string, unknown>): MapMetricRow {
  const repMargin =
    typeof properties.rep_margin_pp === "number"
      ? properties.rep_margin_pp
      : typeof properties.dem_margin_pp === "number"
        ? -properties.dem_margin_pp
        : null;
  const baseName = String(
      properties.official_name || properties.name || properties.id,
    ),
    countyLabel = String(
      properties.county_name ||
        properties.COUNTYNAME ||
        properties.county_id ||
        "",
    );
  return {
    id: String(properties.id),
    name:
      countyLabel && !baseName.toLowerCase().includes(countyLabel.toLowerCase())
        ? `${baseName} · ${countyLabel}`
        : baseName,
    type: "precinct",
    value:
      typeof properties.total_votes === "number"
        ? properties.total_votes
        : null,
    change: repMargin,
    baseline_value: null,
    share: null,
    denominator: null,
    source_ids: [],
    observation_ids: [],
  };
}
function nativeBounds(
  data: PrecinctMapData,
): [[number, number], [number, number]] | undefined {
  let minX = Infinity,
    minY = Infinity,
    maxX = -Infinity,
    maxY = -Infinity;
  const visit = (v: unknown) => {
    if (Array.isArray(v)) {
      if (typeof v[0] === "number" && typeof v[1] === "number") {
        const x = v[0] > 0 && data.query.state === "AK" ? v[0] - 360 : v[0],
          y = v[1];
        minX = Math.min(minX, x);
        minY = Math.min(minY, y);
        maxX = Math.max(maxX, x);
        maxY = Math.max(maxY, y);
      } else v.forEach(visit);
    }
  };
  data.features.forEach((f) => {
    "coordinates" in f.geometry && visit(f.geometry.coordinates);
  });
  if (!Number.isFinite(minX)) return undefined;
  // Alaska's western Aleutians use positive longitudes; unwrap them for a compact camera.
  return [
    [minX, minY],
    [maxX, maxY],
  ];
}
export default function PrecinctExplorer(
  ctx: AppContext & { year: number; office: string },
) {
  const { query, year, office } = ctx,
    revision = query.revision ?? ctx.workspace.revision;
  const sectionRef = useRef<HTMLElement>(null);
  const [activated, setActivated] = useState(false);
  useEffect(() => {
    const element = sectionRef.current;
    if (!element) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setActivated(true);
          observer.disconnect();
        }
      },
      { rootMargin: "600px" },
    );
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  const [yearText, setYear] = useViewOption("precinct_year", String(year)),
    precinctYear = new URLSearchParams(location.search).has("ui_precinct_year")
      ? Number(yearText)
      : year;
  const [layer, setLayer] = useViewOption<"margin" | "volume">(
    "precinct_layer",
    "margin",
  );
  const [lod, setLod] = useViewOption<string>("precinct_lod", "overview");
  const [contestId, setContestId] = useViewOption<string>(
    "precinct_contest",
    "",
  );
  const [datasetId, setDatasetId] = useViewOption<string>(
    "precinct_dataset",
    "",
  );
  const [jobId, setJobId] = useState<number | null>(null),
    [loading, setLoading] = useState(false),
    [loadError, setLoadError] = useState("");
  const [search, setSearch] = useState(""),
    [page, setPage] = useState(0),
    cache = useQueryClient();
  const catalog = useQuery({
    queryKey: ["atlas", "precinct-catalog", query.state, revision],
    queryFn: () => atlasApi.precinctCatalog(query.state, revision),
  });
  const candidates = catalog.data?.datasets || [],
    yearDatasets = candidates.filter((d) => d.year === precinctYear),
    dataset =
      yearDatasets.find((d) => d.id === datasetId) ||
      yearDatasets.find((d) => d.loaded) ||
      yearDatasets[0];
  const years = [...new Set([year, ...candidates.map((d) => d.year)])].sort(
    (a, b) => b - a,
  );
  const map = useQuery({
    queryKey: [
      "atlas",
      "precinct-map",
      query.state,
      precinctYear,
      office,
      revision,
      lod,
      dataset?.id,
      contestId,
    ],
    queryFn: ({ signal }) =>
      atlasApi.precinctMap(
        {
          state: query.state,
          year: precinctYear,
          office,
          revision,
          lod,
          dataset_id: dataset?.id,
          contest_id: contestId || undefined,
        },
        signal,
      ),
    enabled: !!dataset?.loaded && activated,
  });
  const countyContext = useQuery({
    queryKey: ["boundaries", query.state, "detail"],
    queryFn: async () => {
      const response = await publicFetch(`/api/v1/geography/${query.state}`);
      if (!response.ok) throw new Error("County labels unavailable");
      return response.json() as Promise<{
        features: { properties: Record<string, unknown> }[];
      }>;
    },
    enabled: activated,
    staleTime: Infinity,
  });
  const countyNames = useMemo(
    () =>
      new Map(
        (countyContext.data?.features || []).map((feature) => [
          String(
            feature.properties.canonical_id ||
              feature.properties.id ||
              (feature.properties.GEOID
                ? `county:${feature.properties.GEOID}`
                : ""),
          ),
          String(feature.properties.name || feature.properties.NAME || ""),
        ]),
      ),
    [countyContext.data],
  );
  const displayMap = useMemo(
    () =>
      map.data
        ? {
            ...map.data,
            features: map.data.features.map((feature) => ({
              ...feature,
              properties: {
                ...feature.properties,
                county_name:
                  feature.properties?.county_name ||
                  countyNames.get(String(feature.properties?.county_id)) ||
                  "",
              },
            })),
          }
        : undefined,
    [map.data, countyNames],
  );
  const job = useQuery({
    queryKey: ["job", jobId],
    queryFn: () => request<Job>(`/jobs/${jobId}`),
    enabled: jobId != null,
    refetchInterval: (q) =>
      ["completed", "failed", "unavailable"].includes(
        q.state.data?.status || "",
      )
        ? false
        : 1500,
  });
  useEffect(() => {
    if (job.data?.status === "completed") {
      cache.invalidateQueries({ queryKey: ["atlas", "precinct-catalog"] });
      cache.invalidateQueries({ queryKey: ["atlas", "precinct-map"] });
      ctx.refresh();
    }
  }, [job.data?.status]);
  async function download() {
    if (!dataset) return;
    setLoading(true);
    setLoadError("");
    try {
      const work = await atlasApi.loadPrecincts(dataset.id);
      setJobId(work.id);
    } catch (error) {
      setLoadError(
        error instanceof Error
          ? error.message
          : "The source could not be queued.",
      );
    } finally {
      setLoading(false);
    }
  }
  const rows = (displayMap?.features || []).map((f) =>
    precinctRow(f.properties || {}),
  );
  const visible = rows
    .filter((r) => r.name.toLowerCase().includes(search.toLowerCase()))
    .sort((a, b) => (b.value ?? -1) - (a.value ?? -1));
  const selected = rows.filter((r) => (ctx.selectedGeographyIds ?? query.geography_ids).includes(r.id));
  const select = (id: string) =>
    ctx.setQuery({
      geography_ids: (ctx.selectedGeographyIds ?? query.geography_ids).includes(id)
        ? (ctx.selectedGeographyIds ?? query.geography_ids).filter((x) => x !== id)
        : [...(ctx.selectedGeographyIds ?? query.geography_ids), id].slice(-8),
    });
  const activeJob =
    job.data &&
    !["completed", "failed", "unavailable"].includes(job.data.status);
  return (
    <section
      className="atlas-depth-section"
      aria-label="Native precinct evidence"
      ref={sectionRef}
    >
      <Panel
        title={`${stateName(query.state)} · precinct research`}
        subtitle="Real source-native precinct boundaries and matching results, downloaded by state and election."
      >
        <div className="depth-control-row">
          <Select
            label="Precinct evidence year"
            value={precinctYear}
            onChange={(value) => {
              setYear(value);
              setContestId("");
              setPage(0);
            }}
            options={years.map((y) => ({
              value: String(y),
              label: `${y} historical results`,
            }))}
          />
          {yearDatasets.length > 1 && (
            <Select
              label="Precinct source bundle"
              value={dataset?.id || ""}
              onChange={(value) => {
                setDatasetId(value);
                setContestId("");
              }}
              options={yearDatasets.map((d) => ({
                value: d.id,
                label: d.title,
              }))}
            />
          )}
          <Segmented
            label="Precinct map measure"
            value={layer}
            onChange={setLayer}
            items={[
              { id: "margin", label: "Partisan margin" },
              { id: "volume", label: "Candidate votes" },
            ]}
          />
          <Select
            label="Precinct boundary detail"
            value={lod}
            onChange={setLod}
            options={[
              { value: "overview", label: "Fast overview geometry" },
              { value: "detail", label: "Detailed geometry" },
            ]}
          />
        </div>
        <p className="precinct-context-line">
          {precinctYear} historical {human(office).toLowerCase()} results are
          separate from {query.cycle} early-voting participation. Precincts are
          the election producer's reporting units, with their original boundary
          vintage.
        </p>
        {catalog.isPending ? (
          <Loading label="Checking this state's verified precinct inventory…" />
        ) : catalog.isError ? (
          <Notice tone="warning">{catalog.error.message}</Notice>
        ) : !dataset ? (
          <Empty
            title={`Verified ${precinctYear} precinct geometry is not available for this selection`}
          >
            Choose a documented year above. A different election year is never
            substituted silently.{" "}
            {candidates.length
              ? `${candidates.map((d) => d.year).join(", ")} source bundles are available.`
              : "The source inventory has no repeatable public precinct bundle for this selection."}
          </Empty>
        ) : (
          <>
            <div className="precinct-source-card">
              <div>
                <b>{dataset.title}</b>
                <span>
                  {dataset.provider} · {dataset.year} ·{" "}
                  {dataset.loaded
                    ? "Cached for offline research"
                    : human(dataset.status)}
                </span>
              </div>
              <a href={dataset.source_url} target="_blank" rel="noreferrer">
                Original dataset ↗
              </a>
              {!dataset.loaded && !isPublicMode() && (
                <button
                  className="button"
                  disabled={query.revision != null || loading || !!activeJob}
                  onClick={download}
                >
                  <Download size={15} />
                  {query.revision != null
                    ? "Pinned evidence: collection disabled"
                    : activeJob
                      ? "Downloading and validating…"
                      : "Download matching precinct evidence"}
                </button>
              )}
            </div>
            {!dataset.loaded && isPublicMode() && <Notice>This precinct bundle is catalogued but not included in this public release. Open the original dataset above, or use county results. The local research edition can download and validate the full bundle.</Notice>}
            {dataset.provider === "vest" && (
              <p className="precinct-context-line">
                Producer-harmonized results: VEST may allocate or estimate
                non-geographic absentee/provisional returns. These are historical
                context, not independently observed resident-precinct voting.
                Details are retained in the source methodology below.
              </p>
            )}
            {activeJob && (
              <div className="precinct-job" role="status">
                <b>
                  {human(
                    job.data?.progress?.stage || job.data?.status || "queued",
                  )}
                </b>
                <p>
                  {job.data?.progress?.message ||
                    "The original bundle is being downloaded, archived, and validated."}
                </p>
                <progress
                  max={Number(job.data?.progress?.total) || 100}
                  value={Number(job.data?.progress?.completed) || undefined}
                />
              </div>
            )}
            {(loadError || job.data?.status === "failed") && (
              <Notice tone="warning">
                {loadError ||
                  job.data?.error ||
                  "Source validation failed. Existing validated evidence remains available."}
              </Notice>
            )}
            {dataset.loaded &&
              (map.isPending ? (
                <Loading label="Opening matching precinct geometry and results…" />
              ) : map.isError ? (
                <Notice tone="warning">{map.error.message}</Notice>
              ) : map.data?.features.length ? (
                <>
                  <div className="depth-coverage-ledger">
                    <span>
                      <b>{fmt(rows.length)}</b> mapped source areas
                    </span>
                    <span>
                      <b>
                        {compact(rows.reduce((n, r) => n + (r.value ?? 0), 0))}
                      </b>{" "}
                      mapped candidate votes
                    </span>
                    <span>
                      <b>{selected.length}</b> selected
                    </span>
                    <span>
                      Evidence revision <b>{map.data.revision}</b>
                    </span>
                  </div>
                  {map.data.warnings
                    .filter((warning) =>
                      /exceeds the geometry limit|multiple distinct contests|ambiguous|unsupported/i.test(
                        warning,
                      ),
                    )
                    .map((warning, i) => (
                      <Notice
                        key={i}
                        tone={
                          /unallocat|administrative|missing|partial/i.test(
                            warning,
                          )
                            ? "warning"
                            : "info"
                        }
                      >
                        {warning}
                      </Notice>
                    ))}
                  {Number(map.data.coverage.unmapped_candidate_votes) > 0 && (
                    <Notice tone="warning">
                      <b>
                        {fmt(map.data.coverage.unmapped_candidate_votes)}{" "}
                        candidate votes remain outside these resident precinct
                        shapes.
                      </b>{" "}
                      {fmt(
                        100 - Number(map.data.coverage.mapped_votes_pct || 0),
                        1,
                      )}
                      % of the reported source votes are not geographically
                      allocated here. Administrative early-vote, absentee,
                      provisional, and central-count units are listed below
                      rather than assigned to home precincts.
                    </Notice>
                  )}
                  <NativePrecinctMap
                    data={displayMap || map.data}
                    state={query.state}
                    layer={layer}
                    selected={(ctx.selectedGeographyIds ?? query.geography_ids)}
                    onSelect={select}
                  />
                  {((map.data.contests?.length || 0) > 1 || !!contestId) && (
                    <Select
                      label="Native precinct contest"
                      value={contestId}
                      onChange={setContestId}
                      options={[
                        {
                          value: "",
                          label: "Source areas with one unambiguous contest",
                        },
                        ...(map.data.contests || []).map((contest) => ({
                          value: contest.id,
                          label: contest.name || contest.title || contest.id,
                        })),
                      ]}
                    />
                  )}
                  <details
                    className="precinct-coverage-details"
                    open={Object.keys(map.data.coverage).some((k) =>
                      /unmapped|administrative|unallocated/.test(k),
                    )}
                  >
                    <summary>Precinct join coverage and exclusions</summary>
                    <dl>
                      {Object.entries(map.data.coverage).map(([key, value]) => (
                        <div key={key}>
                          <dt>{human(key)}</dt>
                          <dd>
                            {typeof value === "number"
                              ? fmt(value)
                              : typeof value === "object"
                                ? JSON.stringify(value)
                                : String(value)}
                          </dd>
                        </div>
                      ))}
                    </dl>
                  </details>
                  {!!map.data.unmapped_results?.length && (
                    <details className="precinct-coverage-details">
                      <summary>
                        {fmt(map.data.unmapped_results.length)} unallocated /
                        unmatched source units — inspect original rows
                      </summary>
                      <div className="table-scroll">
                        <table>
                          <thead>
                            <tr>
                              <th>Source reporting unit</th>
                              <th>Candidate votes</th>
                              <th>Original record identifiers</th>
                            </tr>
                          </thead>
                          <tbody>
                            {map.data.unmapped_results.map((row) => (
                              <tr key={row.id}>
                                <td>
                                  {row.name}
                                  <small>{row.id}</small>
                                </td>
                                <td className="numeric">
                                  {fmt(row.total_votes)}
                                </td>
                                <td>
                                  {row.source_refs.map((ref, i) => (
                                    <span key={i}>
                                      {Object.entries(ref)
                                        .map(
                                          ([k, v]) =>
                                            `${human(k)}: ${String(v)}`,
                                        )
                                        .join(" · ")}
                                      <br />
                                    </span>
                                  ))}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </details>
                  )}
                  <ResearchGuide
                    what={`${precinctYear} source-native precinct returns joined to the matching published geometry. Administrative absentee, early-vote, provisional, or central-count rows remain outside resident precinct shapes when the source does not allocate them.`}
                    how="Use explicit map zoom controls; scrolling continues to move the page. Click or keyboard-select precincts in the map or table. Circle area represents vote volume; the partisan layer uses Republican-minus-Democratic percentage points."
                    source={dataset.source_url}
                  />
                  <details className="research-guide">
                    <summary>
                      Source methodology, boundary vintage, and join notes
                    </summary>
                    <div>
                      {[
                        ...new Set([
                          ...(dataset.warnings || []),
                          ...map.data.warnings,
                        ]),
                      ].map((warning, i) => (
                        <p key={i}>{warning}</p>
                      ))}
                      <p>
                        County orientation labels use published Census
                        identifiers when a matching label is available; no vote
                        values are allocated or changed.
                      </p>
                    </div>
                  </details>
                  <div className="table-toolbar">
                    <input
                      aria-label="Search source precincts"
                      value={search}
                      onChange={(e) => {
                        setSearch(e.target.value);
                        setPage(0);
                      }}
                      placeholder="Find a source precinct…"
                    />
                    <span>{fmt(visible.length)} matching source areas</span>
                  </div>
                  <div className="table-scroll">
                    <table>
                      <thead>
                        <tr>
                          <th>Source precinct</th>
                          <th>Candidate votes</th>
                          <th>R − D margin</th>
                          <th>Identity</th>
                        </tr>
                      </thead>
                      <tbody>
                        {visible.slice(page * 50, (page + 1) * 50).map((r) => (
                          <tr
                            key={r.id}
                            className={
                              (ctx.selectedGeographyIds ?? query.geography_ids).includes(r.id)
                                ? "selected"
                                : ""
                            }
                            onMouseEnter={() => focusGeography(r.id)}
                            onMouseLeave={() => focusGeography(null)}
                          >
                            <td>
                              <button
                                className="text-button"
                                onClick={() => select(r.id)}
                                aria-pressed={(ctx.selectedGeographyIds ?? query.geography_ids).includes(
                                  r.id,
                                )}
                              >
                                {r.name}
                              </button>
                            </td>
                            <td className="numeric">
                              {r.value == null
                                ? "Not published / choose contest"
                                : fmt(r.value)}
                            </td>
                            <td>
                              {r.change == null
                                ? "Unavailable"
                                : `${r.change >= 0 ? "R" : "D"} +${fmt(Math.abs(r.change), 1)} pp`}
                            </td>
                            <td>
                              <small>{r.id}</small>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <div className="table-pagination">
                    <button
                      className="button small secondary"
                      disabled={!page}
                      onClick={() => setPage(page - 1)}
                    >
                      Previous 50
                    </button>
                    <span>
                      {page * 50 + 1}–
                      {Math.min((page + 1) * 50, visible.length)} of{" "}
                      {fmt(visible.length)}
                    </span>
                    <button
                      className="button small secondary"
                      disabled={(page + 1) * 50 >= visible.length}
                      onClick={() => setPage(page + 1)}
                    >
                      Next 50
                    </button>
                  </div>
                </>
              ) : (
                <Empty title="No compatible precinct layer is attached">
                  {String(
                    map.data?.availability?.reason ||
                      "This office or evidence revision has no validated matching precinct values. Other source offices remain listed in the catalog.",
                  )}
                </Empty>
              ))}
          </>
        )}
      </Panel>
    </section>
  );
}

function NativePrecinctMap({
  data,
  state,
  layer,
  selected,
  onSelect,
}: {
  data: PrecinctMapData;
  state: string;
  layer: MapLayer;
  selected: string[];
  onSelect: (id: string) => void;
}) {
  const [renderer, setRenderer] = useState<"map" | "vector">("map"),
    [fullscreen, setFullscreen] = useState(false),
    [error, setError] = useState(""),
    [hover, setHover] = useState<string>(""),
    [theme, setTheme] = useState(
      document.documentElement.dataset.theme || "light",
    );
  const container = useRef<HTMLDivElement>(null),
    wrap = useRef<HTMLDivElement>(null),
    mapRef = useRef<import("maplibre-gl").Map | null>(null),
    selectRef = useRef(onSelect);
  selectRef.current = onSelect;
  useEffect(() => {
    const changed = () => {
      setFullscreen(document.fullscreenElement === wrap.current);
      requestAnimationFrame(() => mapRef.current?.resize());
    };
    document.addEventListener("fullscreenchange", changed);
    return () => document.removeEventListener("fullscreenchange", changed);
  }, []);
  const id = useId().replaceAll(":", "");
  const rows = useMemo(
      () => data.features.map((f) => precinctRow(f.properties || {})),
      [data],
    ),
    spec = useMemo(
      () =>
        createMapSpec(rows, layer, undefined, {
          label:
            layer === "volume"
              ? "Mapped candidate votes"
              : "Republican − Democratic margin",
          ...(layer === "margin" &&
          Array.isArray(data.legend.bins) &&
          Array.isArray(data.legend.colors) &&
          Array.isArray(data.legend.domain)
            ? {
                bins: data.legend.bins as number[],
                colors: data.legend.colors as string[],
                domain: data.legend.domain as [number, number],
              }
            : {}),
        }),
      [rows, layer, data.legend],
    );
  const volumeSpec = useMemo(() => createMapSpec(rows, "volume"), [rows]);
  const enriched = useMemo(
    () => ({
      type: "FeatureCollection" as const,
      features: data.features.map((feature, i) => ({
        ...feature,
        properties: {
          id: rows[i].id,
          name: rows[i].name,
          total_votes: rows[i].value,
          rep_margin_pp: rows[i].change,
          fill:
            spec.value(rows[i]) == null
              ? "#b8c4ce"
              : layer === "volume"
                ? getComputedStyle(document.documentElement)
                    .getPropertyValue("--map-land")
                    .trim()
                : spec.color(spec.value(rows[i])),
          selected: selected.includes(rows[i].id) ? 1 : 0,
          radius: volumeSpec.radius(rows[i].value ?? 0),
        },
      })),
    }),
    [data, layer, selected.join("|"), theme],
  );
  const latest = useRef(enriched);
  latest.current = enriched;
  useEffect(() => {
    if (renderer !== "map" || !container.current) return;
    let disposed = false,
      owned: import("maplibre-gl").Map | undefined;
    import("maplibre-gl")
      .then((ml) => {
        if (disposed || !container.current) return;
        const css = (name: string) =>
          getComputedStyle(document.documentElement)
            .getPropertyValue(name)
            .trim();
        const map = new ml.Map({
          container: container.current,
          style: {
            version: 8,
            sources: {},
            layers: [
              {
                id: "background",
                type: "background",
                paint: { "background-color": css("--map-background") },
              },
            ],
          },
          center: [-98, 38],
          zoom: 3,
          attributionControl: false,
          cooperativeGestures: true,
        });
        owned = map;
        mapRef.current = map;
        map.addControl(
          new ml.AttributionControl({
            compact: true,
            customAttribution: "Source-native election precinct geometry",
          }),
        );
        map.on("load", () => {
          map.addSource("precincts", { type: "geojson", data: latest.current });
          map.addLayer({
            id: "precinct-fill",
            type: "fill",
            source: "precincts",
            paint: { "fill-color": ["get", "fill"], "fill-opacity": 0.9 },
          });
          map.addSource("precinct-points", {
            type: "geojson",
            data: {
              type: "FeatureCollection",
              features: latest.current.features.map((f) => ({
                type: "Feature",
                geometry: { type: "Point", coordinates: geoCentroid(f) },
                properties: f.properties,
              })),
            },
          });
          map.addLayer({
            id: "precinct-volume",
            type: "circle",
            source: "precinct-points",
            paint: {
              "circle-radius": ["get", "radius"],
              "circle-color": css("--teal"),
              "circle-opacity": 0.72,
              "circle-stroke-color": css("--panel"),
              "circle-stroke-width": 0.7,
            },
            layout: { visibility: layer === "volume" ? "visible" : "none" },
          });
          map.addLayer({
            id: "precinct-line",
            type: "line",
            source: "precincts",
            paint: {
              "line-color": [
                "case",
                ["==", ["get", "selected"], 1],
                css("--selection"),
                css("--map-stroke"),
              ],
              "line-width": ["case", ["==", ["get", "selected"], 1], 2.5, 0.5],
            },
          });
          const bounds = nativeBounds(data);
          if (bounds) map.fitBounds(bounds, { padding: 25, duration: 0 });
          map.on("click", "precinct-fill", (event) => {
            const p = event.features?.[0]?.properties;
            p && selectRef.current(String(p.id));
          });
          map.on("mousemove", "precinct-fill", (event) => {
            const p = event.features?.[0]?.properties;
            setHover(
              p
                ? `${p.name} · ${fmt(p.total_votes)} candidate votes · ${p.rep_margin_pp == null ? "margin unavailable" : fmt(p.rep_margin_pp, 1) + " pp R−D"}`
                : "",
            );
            map.getCanvas().style.cursor = "pointer";
          });
          map.on("mouseleave", "precinct-fill", () => setHover(""));
        });
        map.on("error", (event) =>
          setError(
            event.error?.message || "The interactive renderer could not load.",
          ),
        );
      })
      .catch((error) => {
        setError(String(error));
        setRenderer("vector");
      });
    return () => {
      disposed = true;
      owned?.remove();
      if (mapRef.current === owned) mapRef.current = null;
    };
  }, [data, state, renderer]);
  useEffect(() => {
    const map = mapRef.current,
      source = map?.getSource("precincts") as
        import("maplibre-gl").GeoJSONSource | undefined;
    source?.setData(enriched);
    const pointSource = map?.getSource("precinct-points") as
      import("maplibre-gl").GeoJSONSource | undefined;
    pointSource?.setData({
      type: "FeatureCollection",
      features: enriched.features.map((f) => ({
        type: "Feature",
        geometry: { type: "Point", coordinates: geoCentroid(f) },
        properties: f.properties,
      })),
    });
    if (map?.getLayer("precinct-volume"))
      map.setLayoutProperty(
        "precinct-volume",
        "visibility",
        layer === "volume" ? "visible" : "none",
      );
  }, [enriched, layer]);
  useEffect(() => {
    const apply = () => {
      setTheme(document.documentElement.dataset.theme || "light");
      const map = mapRef.current;
      if (!map?.getLayer("background")) return;
      const css = (n: string) =>
        getComputedStyle(document.documentElement).getPropertyValue(n).trim();
      map.setPaintProperty(
        "background",
        "background-color",
        css("--map-background"),
      );
      map.setPaintProperty("precinct-line", "line-color", [
        "case",
        ["==", ["get", "selected"], 1],
        css("--selection"),
        css("--map-stroke"),
      ]);
    };
    const observer = new MutationObserver(apply);
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme"],
    });
    return () => observer.disconnect();
  }, []);
  const projection = useMemo(
      () =>
        renderer !== "vector"
          ? null
          : (state === "AK" || state === "HI"
              ? geoAlbersUsa()
              : geoMercator()
            ).fitExtent(
              [
                [20, 20],
                [980, 570],
              ],
              data,
            ),
      [data, state, renderer],
    ),
    path = projection ? geoPath(projection) : null;
  return (
    <div className="native-precinct-map" ref={wrap}>
      <div className="precinct-map-toolbar">
        <button
          className="button small secondary"
          onClick={() => setRenderer(renderer === "map" ? "vector" : "map")}
        >
          <Layers size={14} />
          {renderer === "map" ? "Keyboard / vector map" : "Interactive map"}
        </button>
        <button
          className="icon-button"
          aria-label="Zoom precinct map in"
          onClick={() => mapRef.current?.zoomIn()}
        >
          <Plus size={16} />
        </button>
        <button
          className="icon-button"
          aria-label="Zoom precinct map out"
          onClick={() => mapRef.current?.zoomOut()}
        >
          <Minus size={16} />
        </button>
        <button
          className="icon-button"
          aria-label="Reset precinct map"
          onClick={() => {
            const b = nativeBounds(data);
            if (b) mapRef.current?.fitBounds(b, { padding: 25, duration: 0 });
          }}
        >
          <RotateCcw size={16} />
        </button>
        <button
          className="icon-button"
          aria-label={fullscreen ? "Exit full-screen precinct map" : "Full-screen precinct map"}
          onClick={async () => {
            try {
              if (document.fullscreenElement === wrap.current) await document.exitFullscreen();
              else await wrap.current?.requestFullscreen();
            } catch {
              setError("Full-screen mode is unavailable in this browser. The embedded map remains usable.");
            }
          }}
        >
          <Maximize2 size={16} />
        </button>
      </div>
      {renderer === "map" ? (
        <div
          ref={container}
          className="native-precinct-canvas"
          aria-label="Interactive source-native precinct map. The table below provides keyboard selection."
        />
      ) : (
        <svg
          viewBox="0 0 1000 590"
          className="native-precinct-vector"
          role="group"
          aria-label="Source-native precinct map"
        >
          <defs>
            <pattern id={id} width="6" height="6" patternUnits="userSpaceOnUse">
              <rect width="6" height="6" fill="var(--map-missing)" />
              <path d="M0 6L6 0" stroke="var(--map-stroke)" strokeWidth=".5" />
            </pattern>
          </defs>
          {enriched.features.map((f, i) => {
            const p = f.properties,
              r = rows[i];
            const center = path?.centroid(f) || [NaN, NaN];
            return (
              <g key={r.id}>
                <path
                  d={path?.(f) || ""}
                  fill={
                    layer !== "volume" && r.change == null
                      ? `url(#${id})`
                      : p.fill
                  }
                  stroke={p.selected ? "var(--selection)" : "var(--map-stroke)"}
                  strokeWidth={p.selected ? 2.5 : 0.45}
                  role="button"
                  tabIndex={0}
                  aria-label={`${r.name}, ${fmt(r.value)} candidate votes, ${r.change == null ? "margin unavailable" : fmt(r.change, 1) + " pp R−D"}`}
                  aria-pressed={!!p.selected}
                  onClick={() => onSelect(r.id)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      onSelect(r.id);
                    }
                  }}
                >
                  <title>
                    {r.name} · {fmt(r.value)} candidate votes
                  </title>
                </path>
                {layer === "volume" && Number.isFinite(center[0]) && (
                  <circle
                    cx={center[0]}
                    cy={center[1]}
                    r={p.radius}
                    fill="var(--teal)"
                    fillOpacity=".72"
                    stroke="var(--panel)"
                    strokeWidth=".7"
                    pointerEvents="none"
                  />
                )}
              </g>
            );
          })}
        </svg>
      )}
      {hover && (
        <p className="precinct-hover" role="status">
          {hover}
        </p>
      )}
      <div className="depth-numeric-legend">
        {layer === "volume" ? (
          <div className="precinct-volume-key">
            {[0.0625, 0.25, 1].map((f) => (
              <span key={f}>
                <i
                  style={{
                    width: spec.radius(spec.max * f) * 2,
                    height: spec.radius(spec.max * f) * 2,
                  }}
                />
                {compact(spec.max * f)}
              </span>
            ))}
          </div>
        ) : (
          <>
            <b>{spec.label} · percentage points</b>
            <div>
              {spec.colors.map((color, i) => (
                <span
                  key={color}
                  style={{ background: color }}
                  title={`${fmt(spec.bins[i], 1)} to ${fmt(spec.bins[i + 1], 1)} ${spec.unit}`}
                />
              ))}
            </div>
            <p>
              {fmt(spec.domain[0], 1)}
              {spec.unit}
              <span>
                {layer === "margin"
                  ? "Democratic advantage ← 0 → Republican advantage"
                  : "Values describe the included source precinct returns"}
              </span>
              {fmt(spec.domain[1], 1)}
              {spec.unit}
            </p>
          </>
        )}
        <small>
          {layer === "volume"
            ? "Circle area represents candidate-vote volume; reference sizes above share the map scale."
            : "▧ Missing partisan evidence · outline = selected precinct"}
        </small>
        {layer !== "volume" && <ExactMapThresholds spec={spec} />}
        <small>
          Election day {String(data.legend.date || data.query.year)} · boundary
          vintage {String(data.boundary_vintage || "source-published")} ·
          revision {data.revision}
        </small>
      </div>
      {error && (
        <Notice>
          The interactive map reported: {error}. The vector map and evidence
          table remain available.
        </Notice>
      )}
    </div>
  );
}
