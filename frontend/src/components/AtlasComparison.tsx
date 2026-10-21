import { publicFetch } from "../publicData";
import { useId, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { geoAlbersUsa, geoMercator, geoPath } from "d3-geo";
import type { FeatureCollection, Geometry, GeoJsonProperties } from "geojson";
import {
  ArrowDown,
  ArrowLeft,
  ArrowRight,
  ArrowUp,
  RotateCcw,
} from "lucide-react";
import { atlasApi, type Results } from "../atlasApi";
import type { AppContext, GeoRow } from "../types";
import { createMapSpec } from "../mapSpec";
import {
  BIVARIATE_COLORS,
  quantileBin,
  quantileThresholds,
  sharedMarginMaximum,
} from "../atlasDepthMath";
import { focusGeography, useFocusedGeography } from "../interaction";
import { useViewOption } from "../viewState";
import { fmt, stateName } from "../utils";
import { Empty, Loading, Notice, Panel, Segmented, Select } from "./ui";
import { ResearchGuide } from "./ResearchGuide";
import { PairedResultCharts, BivariateScatter } from "./AdvancedResultCharts";
import ExactMapThresholds from "./ExactMapThresholds";
import "../atlasDepth.css";
type FC = FeatureCollection<Geometry, GeoJsonProperties>;
const row = (id: string, name: string, margin: number | null): GeoRow => ({
  id,
  name,
  type: "county",
  value: 0,
  change: margin,
  baseline_value: null,
  share: null,
  denominator: null,
  source_ids: [],
  observation_ids: [],
});
function geoKey(properties: GeoJsonProperties) {
  return String(
    properties?.canonical_id ||
      properties?.id ||
      (properties?.GEOID ? `county:${properties.GEOID}` : ""),
  );
}
export default function AtlasComparison(
  ctx: AppContext & {
    current: Results;
    year: number;
    office: string;
    grain: string;
    contest?: string;
  },
) {
  const { query, current, year, office, grain } = ctx;
  const revision = query.revision ?? ctx.workspace.revision;
  const defaultBaseline =
    year - (office === "US SENATE" ? 6 : office === "PRESIDENT" ? 4 : 2);
  const [baselineText, setBaseline] = useViewOption(
    "comparison_year",
    String(defaultBaseline),
  );
  const baseline = new URLSearchParams(location.search).has(
    "ui_comparison_year",
  )
    ? Number(baselineText)
    : defaultBaseline;
  const [mode, setMode] = useViewOption<string>("comparison_mode", "side");
  const [swipeText, setSwipeText] = useViewOption<string>(
      "comparison_swipe",
      "50",
    ),
    [zoomText, setZoomText] = useViewOption<string>("comparison_zoom", "1"),
    [cameraText, setCameraText] = useViewOption<string>(
      "comparison_camera",
      "0,0",
    );
  const swipe = Math.max(0, Math.min(100, Number(swipeText) || 0)),
    zoom = Math.max(1, Math.min(5, Number(zoomText) || 1));
  const cameraParts = cameraText.split(",");
  const camera: [number, number] = [
    Number(cameraParts[0]) || 0,
    Number(cameraParts[1]) || 0,
  ];
  const setSwipe = (value: number) => setSwipeText(String(value)),
    setZoom = (value: number) => setZoomText(String(value));
  const setCamera = (
    next: [number, number] | ((current: [number, number]) => [number, number]),
  ) =>
    setCameraText((typeof next === "function" ? next(camera) : next).join(","));
  const focus = useFocusedGeography(),
    clip = useId().replaceAll(":", "");
  const comparison = useQuery({
    queryKey: [
      "atlas",
      "paired-results",
      query.state,
      year,
      baseline,
      office,
      grain,
      ctx.contest,
      revision,
    ],
    queryFn: ({ signal }) =>
      atlasApi.comparisons(
        {
          state: query.state,
          year,
          baseline,
          office,
          geography_level: grain,
          contest_id: ctx.contest || undefined,
          revision,
        },
        signal,
      ),
    enabled: year !== baseline && ["state", "county"].includes(grain),
  });
  const boundaries = useQuery({
    queryKey: [
      "boundaries",
      query.state,
      grain === "state" ? "state" : "detail",
    ],
    queryFn: async () => {
      const response = await publicFetch(
        `/api/v1/geography/${grain === "state" ? "US" : query.state}`,
      );
      if (!response.ok)
        throw new Error("Local Census display boundaries are unavailable.");
      const data = (await response.json()) as FC;
      return grain === "state"
        ? {
            ...data,
            features: data.features.filter(
              (f) =>
                String(f.properties?.code || f.properties?.STUSPS) ===
                query.state,
            ),
          }
        : data;
    },
    staleTime: Infinity,
    enabled: ["state", "county"].includes(grain),
  });
  const context = useQuery({
    queryKey: ["atlas", "context", query.state, revision],
    queryFn: () => atlasApi.context(query.state, revision),
    enabled: grain === "county",
  });
  const paired = comparison.data?.rows || [];
  const currentRows = useMemo(
    () =>
      current.geographies.map((r) =>
        row(
          r.id,
          r.name,
          r.rep_share_pct != null && r.dem_share_pct != null
            ? r.rep_share_pct - r.dem_share_pct
            : null,
        ),
      ),
    [current],
  );
  const baselineRows = useMemo(
    () =>
      (comparison.data?.baseline?.geographies || []).map((r) =>
        row(
          r.id,
          r.name,
          r.rep_share_pct != null && r.dem_share_pct != null
            ? r.rep_share_pct - r.dem_share_pct
            : null,
        ),
      ),
    [comparison.data],
  );
  const baselineLookup = useMemo(
    () => new Map(baselineRows.map((row) => [row.id, row])),
    [baselineRows],
  );
  const maximum = sharedMarginMaximum(
    paired.length
      ? paired
      : currentRows.map((r) => ({
          id: r.id,
          name: r.name,
          current_votes: null,
          baseline_votes: null,
          current_margin_pp: r.change,
          baseline_margin_pp: null,
          change_pp: null,
          eligible: false,
        })),
  );
  const spec = createMapSpec(
    [...currentRows, ...baselineRows],
    "margin",
    maximum,
  );
  const differences = paired
    .filter((r) => r.eligible && r.change_pp != null)
    .map((r) => row(r.id, r.name, r.change_pp));
  const differenceSpec = createMapSpec(differences, "swing");
  const differenceEligible = differences.length > 0;
  const incomes = new Map(
    ((context.data?.estimates || []) as Record<string, unknown>[])
      .filter(
        (r) =>
          r.metric === "median_household_income" &&
          typeof r.estimate === "number",
      )
      .map((r) => [String(r.geography_id), r]),
  );
  const bivariate = currentRows
    .filter((r) => r.change != null && incomes.has(r.id))
    .map((r) => ({
      id: r.id,
      name: r.name,
      margin: r.change!,
      income: Number(incomes.get(r.id)?.estimate),
      moe: incomes.get(r.id)?.moe,
    }));
  const incomeBreaks = quantileThresholds(bivariate.map((r) => r.income)),
    marginBreaks = quantileThresholds(bivariate.map((r) => r.margin));
  const [bivariateCell, setBivariateCell] = useState<string | null>(null);
  const biLookup = new Map(
    bivariate.map((r) => [
      r.id,
      {
        ...r,
        x: quantileBin(r.margin, marginBreaks),
        y: quantileBin(r.income, incomeBreaks),
      },
    ]),
  );
  const select = (id: string) =>
    ctx.setQuery({
      geography_ids: (ctx.selectedGeographyIds ?? query.geography_ids).includes(id)
        ? (ctx.selectedGeographyIds ?? query.geography_ids).filter((x) => x !== id)
        : [...(ctx.selectedGeographyIds ?? query.geography_ids), id].slice(-8),
    });
  const projection = useMemo(
    () =>
      boundaries.data
        ? (query.state === "AK" || query.state === "HI"
            ? geoAlbersUsa()
            : geoMercator()
          ).fitExtent(
            [
              [15, 15],
              [785, 480],
            ],
            boundaries.data,
          )
        : null,
    [boundaries.data, query.state],
  );
  const path = projection ? geoPath(projection) : null;
  const renderMap = (
    kind: "current" | "baseline" | "difference" | "bivariate",
    label: string,
  ) => {
    const source =
      kind === "current"
        ? currentRows
        : kind === "baseline"
          ? baselineRows
          : differences;
    const lookup = new Map(source.map((r) => [r.id, r]));
    const activeSpec = kind === "difference" ? differenceSpec : spec;
    const layers = (which: typeof kind) =>
      boundaries.data?.features.map((feature, index) => {
        const id = geoKey(feature.properties),
          r = (which === "baseline" ? baselineLookup : lookup).get(id),
          b = biLookup.get(id);
        const fill =
          which === "bivariate"
            ? b
              ? BIVARIATE_COLORS[b.y][b.x]
              : `url(#${clip}-missing)`
            : r?.change == null
              ? `url(#${clip}-missing)`
              : activeSpec.color(r.change);
        const dim =
          which === "bivariate" &&
          bivariateCell &&
          b &&
          `${b.x}-${b.y}` !== bivariateCell;
        return (
          <path
            key={`${which}-${id}-${index}`}
            d={path?.(feature) || ""}
            fill={fill}
            fillOpacity={dim ? 0.2 : 1}
            stroke={
              (ctx.selectedGeographyIds ?? query.geography_ids).includes(id) || focus === id
                ? "var(--selection)"
                : "var(--map-stroke)"
            }
            strokeWidth={
              (ctx.selectedGeographyIds ?? query.geography_ids).includes(id) || focus === id
                ? 2.8 / zoom
                : 0.55 / zoom
            }
            tabIndex={r?.change != null || b ? 0 : -1}
            role="button"
            aria-pressed={(ctx.selectedGeographyIds ?? query.geography_ids).includes(id)}
            aria-label={`${String(feature.properties?.name || feature.properties?.NAME || id)}: ${which === "bivariate" && b ? `${fmt(b.margin, 1)} pp margin; $${fmt(b.income)} household income` : r?.change == null ? "No comparable evidence" : `${fmt(r.change, 1)} percentage points`}`}
            onMouseEnter={() => focusGeography(id)}
            onMouseLeave={() => focusGeography(null)}
            onFocus={() => focusGeography(id)}
            onBlur={() => focusGeography(null)}
            onClick={() => select(id)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                select(id);
              }
            }}
          >
            <title>{`${r?.name || feature.properties?.NAME || id}: ${r?.change == null ? "Unavailable" : fmt(r.change, 1) + " pp"}`}</title>
          </path>
        );
      });
    return (
      <div className="depth-map-canvas">
        <div className="depth-map-caption">
          <b>{label}</b>
          <span>
            {kind === "bivariate"
              ? "County-level context"
              : kind === "difference"
                ? `${year} − ${baseline} · percentage points`
                : "Republican − Democratic · percentage points"}
          </span>
        </div>
        <svg viewBox="0 0 800 500" role="group" aria-label={label}>
          <defs>
            <pattern
              id={`${clip}-missing`}
              width="7"
              height="7"
              patternUnits="userSpaceOnUse"
            >
              <rect width="7" height="7" fill="var(--map-missing)" />
              <path d="M0 7L7 0" stroke="var(--map-stroke)" strokeWidth=".55" />
            </pattern>
            <clipPath id={`${clip}-swipe`}>
              <rect width={(800 * swipe) / 100} height="500" />
            </clipPath>
          </defs>
          <g
            transform={`translate(${400 + camera[0]} ${250 + camera[1]}) scale(${zoom}) translate(-400 -250)`}
          >
            {layers(kind)}
          </g>
          {mode === "swipe" && kind === "current" && (
            <g clipPath={`url(#${clip}-swipe)`}>
              <g
                transform={`translate(${400 + camera[0]} ${250 + camera[1]}) scale(${zoom}) translate(-400 -250)`}
              >
                {layers("baseline")}
              </g>
            </g>
          )}
          {mode === "swipe" && kind === "current" && (
            <line
              x1={(800 * swipe) / 100}
              x2={(800 * swipe) / 100}
              y1="0"
              y2="500"
              stroke="var(--selection)"
              strokeWidth="3"
            />
          )}
        </svg>
      </div>
    );
  };
  const years = [
    ...new Set([
      defaultBaseline,
      ...current.history.map((row) => Number(row.year)).filter(Number.isFinite),
      year - 4,
      year - 8,
      2024,
      2020,
      2016,
      2012,
      2008,
      2004,
      2000,
      1996,
      1992,
      1988,
      1984,
      1980,
      1976,
    ]),
  ]
    .filter((y) => y < year && y >= 1976)
    .sort((a, b) => b - a);
  if (!["state", "county"].includes(grain)) return null;
  return (
    <section
      className="atlas-depth-section"
      aria-label="Historical geographic comparison"
    >
      <Panel
        title="Compare elections, place by place"
        subtitle="Two historical elections, one geographic frame, and a visible compatibility ledger."
      >
        <div className="depth-control-row">
          <Select
            label="Compare with election year"
            value={baseline}
            onChange={setBaseline}
            options={years.map((y) => ({ value: String(y), label: String(y) }))}
          />
          <Segmented
            label="Historical map comparison"
            value={mode}
            onChange={setMode}
            items={[
              { id: "side", label: "Side by side" },
              { id: "swipe", label: "Historical swipe" },
              {
                id: "difference",
                label: "Difference",
                disabled: !differenceEligible,
              },
              {
                id: "bivariate",
                label: "Context × result",
                disabled: !bivariate.length,
              },
            ]}
          />
        </div>
        {comparison.isPending && (
          <Loading label="Checking both elections and geographic compatibility…" />
        )}
        {comparison.isError && (
          <Notice tone="warning">
            {comparison.error.message}. The selected election remains usable
            above.
          </Notice>
        )}
        <div className="depth-coverage-ledger">
          <span>
            <b>{currentRows.length}</b> current areas
          </span>
          <span>
            <b>{baselineRows.length}</b> baseline areas
          </span>
          <span>
            <b>{differences.length}</b> defensible changes
          </span>
          <span>
            Evidence revision <b>{revision}</b>
          </span>
        </div>
        {!differenceEligible && comparison.data && (
          <Notice>
            Difference estimates are withheld until the source and geographic
            crosswalk establish comparability. The two original maps remain
            available as historical context.
          </Notice>
        )}
        {boundaries.isPending ? (
          <Loading label="Opening local display boundaries…" />
        ) : boundaries.isError ? (
          <Notice>{boundaries.error.message}</Notice>
        ) : (
          <>
            <div
              className={`depth-map-grid ${mode === "side" ? "two" : "one"}`}
            >
              {mode === "side" ? (
                <>
                  {renderMap(
                    "baseline",
                    `${baseline} ${stateName(query.state)}`,
                  )}
                  {renderMap("current", `${year} ${stateName(query.state)}`)}
                </>
              ) : mode === "difference" ? (
                differenceEligible ? (
                  renderMap("difference", `Matched geographic change`)
                ) : (
                  <Empty title="No defensible difference map">
                    Use side-by-side context while a reviewed crosswalk is
                    unavailable.
                  </Empty>
                )
              ) : mode === "bivariate" ? (
                renderMap("bivariate", `${year} result × household income`)
              ) : (
                renderMap("current", `${baseline} ← swipe → ${year}`)
              )}
            </div>
            <div className="depth-camera-controls">
              <label>
                Shared zoom
                <input
                  type="range"
                  aria-label="Shared comparison map zoom"
                  min="1"
                  max="5"
                  step=".1"
                  value={zoom}
                  onChange={(e) => setZoom(Number(e.target.value))}
                />
              </label>
              {[
                [ArrowLeft, -70, 0, "Pan left"],
                [ArrowRight, 70, 0, "Pan right"],
                [ArrowUp, 0, -70, "Pan up"],
                [ArrowDown, 0, 70, "Pan down"],
              ].map(([Icon, x, y, label]) => {
                const I = Icon as typeof ArrowLeft;
                return (
                  <button
                    key={String(label)}
                    className="icon-button"
                    aria-label={String(label)}
                    onClick={() =>
                      setCamera(([a, b]) => [a + Number(x), b + Number(y)])
                    }
                  >
                    <I size={15} />
                  </button>
                );
              })}
              <button
                className="button small secondary"
                onClick={() => {
                  setZoom(1);
                  setCamera([0, 0]);
                }}
              >
                <RotateCcw size={13} />
                Reset both maps
              </button>
            </div>
            {mode === "swipe" && (
              <label className="depth-swipe">
                Historical swipe position{" "}
                <b>
                  {baseline} left / {year} right
                </b>
                <input
                  type="range"
                  min="0"
                  max="100"
                  value={swipe}
                  onChange={(e) => setSwipe(Number(e.target.value))}
                  aria-label="Historical map swipe position"
                />
              </label>
            )}
            {mode !== "bivariate" && (
              <div className="depth-numeric-legend">
                <div>
                  {(mode === "difference" ? differenceSpec : spec).colors.map(
                    (color, i) => (
                      <span
                        key={color}
                        style={{ background: color }}
                        title={`${fmt((mode === "difference" ? differenceSpec : spec).bins[i], 1)} to ${fmt((mode === "difference" ? differenceSpec : spec).bins[i + 1], 1)} pp`}
                      />
                    ),
                  )}
                </div>
                <p>
                  {fmt(
                    (mode === "difference" ? differenceSpec : spec).domain[0],
                    1,
                  )}{" "}
                  pp{" "}
                  <span>
                    {mode === "difference"
                      ? "Toward Democratic ← 0 → Toward Republican"
                      : "Democratic advantage ← 0 → Republican advantage"}
                  </span>{" "}
                  {fmt(
                    (mode === "difference" ? differenceSpec : spec).domain[1],
                    1,
                  )}{" "}
                  pp
                </p>
                <small>
                  Both original maps share these exact thresholds. ▧ Missing /
                  incompatible; outline = selected place.
                </small>
                <ExactMapThresholds
                  spec={mode === "difference" ? differenceSpec : spec}
                />
              </div>
            )}
          </>
        )}
        {mode === "bivariate" && (
          <div className="bivariate-explainer">
            <div className="bivariate-legend">
              <strong>Household income ↑</strong>
              <div>
                {[2, 1, 0].map((y) =>
                  [0, 1, 2].map((x) => (
                    <button
                      key={`${x}-${y}`}
                      style={{ background: BIVARIATE_COLORS[y][x] }}
                      className={
                        bivariateCell === `${x}-${y}` ? "selected" : ""
                      }
                      aria-label={`Income group ${y + 1}, margin group ${x + 1}; select to highlight`}
                      aria-pressed={bivariateCell === `${x}-${y}`}
                      onClick={() =>
                        setBivariateCell(
                          bivariateCell === `${x}-${y}` ? null : `${x}-${y}`,
                        )
                      }
                    />
                  )),
                )}
              </div>
              <span>Democratic ← margin → Republican</span>
            </div>
            <div>
              <p>
                <b>
                  Three equal-frequency groups, calculated from the displayed
                  places.
                </b>
              </p>
              <p>
                Margin thresholds:{" "}
                {marginBreaks.map((v) => fmt(v, 1) + " pp").join(" / ")}.
              </p>
              <p>
                Income thresholds:{" "}
                {incomeBreaks.map((v) => "$" + fmt(v)).join(" / ")}.
              </p>
              <p>
                ACS 2020–2024 five-year estimates, with published margins of
                error in the context table. Resident income does not measure
                voters' income.
              </p>
            </div>
          </div>
        )}
        <ResearchGuide
          what={
            mode === "bivariate"
              ? "Two area-level measures in one map: historical partisan margin and Census household income."
              : "Original historical Republican-minus-Democratic vote shares, with changes only where source definitions and boundaries can be compared."
          }
          how={
            mode === "swipe"
              ? "Move the divider or use its arrow keys. Both maps use the same projection, zoom, thresholds, and missing-data rules."
              : "Select any area with click or keyboard to coordinate the table and charts. All map zoom and pan controls affect both frames. Darker colors indicate larger margins, not more votes."
          }
          source="Attributed historical returns and Census 2024 display boundaries; comparison eligibility comes from the shared analytical service."
        />
        {!!comparison.data?.warnings.length && (
          <details className="precinct-source-notes">
            <summary>{comparison.data.warnings.length} source and comparison notes</summary>
            <ul>{comparison.data.warnings.map((warning, i) => <li key={i}>{warning}</li>)}</ul>
          </details>
        )}
      </Panel>
      {mode === "bivariate" && bivariate.length > 0 && (
        <Panel
          title="Context and results, linked"
          subtitle="Each point is a place, not a person. Select the map or point to inspect the same area."
        >
          <BivariateScatter
            rows={bivariate}
            selected={(ctx.selectedGeographyIds ?? query.geography_ids)}
            onSelect={select}
          />
        </Panel>
      )}
      {comparison.data && (
        <PairedResultCharts
          current={current}
          rows={paired}
          year={year}
          baseline={baseline}
          selected={(ctx.selectedGeographyIds ?? query.geography_ids)}
          onSelect={select}
        />
      )}
    </section>
  );
}
