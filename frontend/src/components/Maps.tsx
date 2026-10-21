import { publicFetch, publicStaticAsset } from "../publicData";
import { useEffect, useMemo, useRef, useState, useId } from "react";
import { useQuery } from "@tanstack/react-query";
import { geoAlbersUsa, geoMercator, geoPath, geoCentroid } from "d3-geo";
import type {
  Feature,
  FeatureCollection,
  Geometry,
  GeoJsonProperties,
} from "geojson";
import { Expand, Layers, Map as MapIcon, RotateCcw } from "lucide-react";
import type { GeoRow, NationalRow } from "../types";
import { STATE_NAMES, compact, fmt, stateName } from "../utils";
import { createMapSpec, type MapLayer, type MapSpec } from "../mapSpec";
import { Empty, Loading, Notice, Segmented } from "./ui";
import "maplibre-gl/dist/maplibre-gl.css";
import { focusGeography, useFocusedGeography } from "../interaction";
export type { MapLayer } from "../mapSpec";
type FC = FeatureCollection<Geometry, GeoJsonProperties>;
type City = {
  state: string;
  name: string;
  longitude: number;
  latitude: number;
  priority: number;
};
async function loadGeo(state: string): Promise<FC> {
  const r = await publicFetch(`/api/v1/geography/${state}`);
  if (!r.ok)
    throw new Error("Official display boundaries are unavailable for this release. The complete source table remains available.");
  return r.json();
}
function stateCode(f: Feature) {
  const p = f.properties || {};
  return String(
    p.code ||
      p.postal ||
      p.STUSPS ||
      p.state ||
      Object.keys(STATE_NAMES).find((c) => STATE_NAMES[c] === p.name) ||
      "",
  );
}
function useMapTheme() {
  const [theme, setTheme] = useState(
    document.documentElement.dataset.theme || "light",
  );
  useEffect(() => {
    const ob = new MutationObserver(() =>
      setTheme(document.documentElement.dataset.theme || "light"),
    );
    ob.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme"],
    });
    return () => ob.disconnect();
  }, []);
  return theme;
}
export function NationalMap({
  rows,
  selected,
  onSelect,
  layer = "coverage",
  tile = false,
  marginContext = "Percentage points · certified historical context",
  missingLabel = "Explore historical results and available evidence",
}: {
  rows: NationalRow[];
  selected: string;
  onSelect: (s: string) => void;
  layer?: string;
  tile?: boolean;
  marginContext?: string;
  missingLabel?: string;
}) {
  const geo = useQuery({
    queryKey: ["boundaries", "US"],
    queryFn: () => loadGeo("US"),
    staleTime: Infinity,
  });
  const [hover, setHover] = useState("");
  const lookup = new Map(rows.map((r) => [r.code, r]));
  const max = Math.max(...rows.map((r) => r.value || 0), 1);
  const projection = useMemo(
    () => geoAlbersUsa().translate([435, 224]).scale(1060),
    [],
  );
  const path = geoPath(projection);
  const id = useId().replaceAll(":", "");
  const current = lookup.get(hover || selected);
  const valueLabel = (value: number | null | undefined) =>
    value == null
      ? missingLabel
      : layer === "margin"
        ? value === 0
          ? "Even margin · 0 pp"
          : `${value > 0 ? "R" : "D"} +${fmt(Math.abs(value), 1)} pp`
        : fmt(value);
  const color = (c: string) => {
    const r = lookup.get(c);
    if (layer === "margin" && r?.value != null) {
      const v = r.value;
      return v < -10
        ? "#235fa8"
        : v < 0
          ? "#91b4e0"
          : v > 10
            ? "#bf354e"
            : "#e29da9";
    }
    return r?.value != null
      ? layer === "coverage"
        ? "#39aca0"
        : "var(--map-land)"
      : "var(--map-missing)";
  };
  if (geo.isPending)
    return <Loading label="Loading local geographic boundaries…" />;
  if (geo.isError)
    return (
      <Empty title="Boundaries unavailable" icon={<MapIcon />}>
        {geo.error.message}
      </Empty>
    );
  return (
    <div className="national-map-wrap">
      {tile ? (
        <div className="state-tiles">
          {Object.keys(STATE_NAMES)
            .filter((c) => c !== "DC")
            .sort((a, b) => stateName(a).localeCompare(stateName(b)))
            .map((c) => (
              <button
                key={c}
                style={{ borderBottom: `4px solid ${color(c)}` }}
                onClick={() => onSelect(c)}
                className={selected === c ? "selected" : ""}
                aria-label={`${stateName(c)}, ${valueLabel(lookup.get(c)?.value)}`}
                aria-pressed={selected === c}
              >
                <b>{c}</b>
                <small>
                  {lookup.get(c)?.value == null
                    ? "Explore"
                    : layer === "margin"
                      ? valueLabel(lookup.get(c)?.value)
                      : compact(lookup.get(c)?.value)}
                </small>
              </button>
            ))}
        </div>
      ) : (
        <svg
          className="map-svg national-map"
          viewBox="0 0 870 475"
          role="group"
          aria-label="Explore all fifty states"
        >
          <defs>
            <pattern id={id} width="6" height="6" patternUnits="userSpaceOnUse">
              <rect width="6" height="6" fill="var(--map-missing)" />
              <path d="M0 6L6 0" stroke="var(--map-stroke)" strokeWidth=".4" />
            </pattern>
          </defs>
          {geo.data?.features.map((f) => {
            const c = stateCode(f),
              r = lookup.get(c),
              center = path.centroid(f),
              active = selected === c;
            return (
              <g key={c} className={`map-state ${active ? "selected" : ""}`}>
                <path
                  d={path(f) || ""}
                  fill={r?.value == null ? `url(#${id})` : color(c)}
                  stroke={active ? "var(--selection)" : "var(--map-stroke)"}
                  strokeWidth={active ? 2.5 : 0.8}
                  onMouseEnter={() => setHover(c)}
                  onMouseLeave={() => setHover("")}
                  onFocus={() => setHover(c)}
                  onClick={() => onSelect(c)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      onSelect(c);
                    }
                  }}
                  tabIndex={0}
                  role="button"
                  aria-label={`${stateName(c)}, ${valueLabel(r?.value)}`}
                  aria-pressed={active}
                >
                  <title>{`${stateName(c)} · ${valueLabel(r?.value)}`}</title>
                </path>
                {layer === "volume" &&
                  r?.value != null &&
                  Number.isFinite(center[0]) && (
                    <circle
                      cx={center[0]}
                      cy={center[1]}
                      r={24 * Math.sqrt(Math.max(0, r.value) / max)}
                      fill="var(--cyan)"
                      fillOpacity=".7"
                      stroke="var(--panel)"
                      strokeWidth="1"
                      pointerEvents="none"
                    />
                  )}
                {Number.isFinite(center[0]) && (
                  <text
                    x={center[0]}
                    y={center[1] + 3}
                    textAnchor="middle"
                    pointerEvents="none"
                  >
                    {c}
                  </text>
                )}
              </g>
            );
          })}
        </svg>
      )}
      <div className="map-readout">
        <span className="status-dot" />
        <b>{stateName(hover || selected)}</b>
        <span>
          {current?.value == null
            ? missingLabel
            : layer === "margin"
              ? valueLabel(current.value)
              : fmt(current.value) + " reported ballots"}
        </span>
      </div>
      <div className="map-legend">
        {layer === "margin" ? (
          <>
            <span>
              <i style={{ background: "#235fa8" }} />
              Democratic margin
            </span>
            <span>
              <i style={{ background: "#bf354e" }} />
              Republican margin
            </span>
            <span>{marginContext}</span>
          </>
        ) : (
          <>
            <span>
              <i style={{ background: "var(--cyan)" }} />
              {layer === "volume"
                ? `Circle area · reference ${compact(max)}`
                : "Matching evidence"}
            </span>
            <span>
              <i className="hatch" />
              No matching observation
            </span>
          </>
        )}
        <span>
          <i className="outline" />
          Selected state
        </span>
      </div>
    </div>
  );
}
function boundsOf(fc: FC): [[number, number], [number, number]] | undefined {
  const ps: number[][] = [];
  const visit = (v: unknown) => {
    if (Array.isArray(v)) {
      if (typeof v[0] === "number" && typeof v[1] === "number")
        ps.push(v as number[]);
      else v.forEach(visit);
    }
  };
  fc.features.forEach((f) => {
    if ("coordinates" in f.geometry) visit(f.geometry.coordinates);
  });
  if (!ps.length) return;
  const usable = ps.filter((p) => p[0] < 0);
  return [
    [
      Math.min(...usable.map((p) => p[0])),
      Math.min(...usable.map((p) => p[1])),
    ],
    [
      Math.max(...usable.map((p) => p[0])),
      Math.max(...usable.map((p) => p[1])),
    ],
  ];
}
function cssColor(name: string) {
  return getComputedStyle(document.documentElement)
    .getPropertyValue(name)
    .trim();
}
/** Apply colors while sources load; isStyleLoaded() also waits for source work. */
function applyMapTheme(map: import("maplibre-gl").Map) {
  const paint = (id: string, property: string, value: string | unknown[]) => {
    if (!map.getLayer(id)) return;
    if (
      JSON.stringify(map.getPaintProperty(id, property)) !==
      JSON.stringify(value)
    )
      map.setPaintProperty(id, property, value);
  };
  paint("background", "background-color", cssColor("--map-background"));
  paint("areas-line", "line-color", [
    "case",
    ["==", ["get", "selected"], 1],
    cssColor("--selection"),
    cssColor("--map-stroke"),
  ]);
  paint("volume-circles", "circle-color", cssColor("--cyan"));
  paint("volume-circles", "circle-stroke-color", cssColor("--panel"));
}

export function StateMap({
  state,
  rows,
  selected = [],
  onSelect,
  layer = "volume",
  height = 380,
  scaleMax,
  metricLabel,
  unit,
}: {
  state: string;
  rows: GeoRow[];
  selected?: string[];
  onSelect: (id: string) => void;
  layer?: MapLayer;
  height?: number;
  scaleMax?: number;
  metricLabel?: string;
  unit?: string;
}) {
  const container = useRef<HTMLDivElement>(null),
    wrap = useRef<HTMLDivElement>(null),
    mapRef = useRef<import("maplibre-gl").Map | null>(null);
  const stateGrain = rows.length > 0 && rows.every((r) => r.type === "state");
  const geo = useQuery({
    queryKey: ["boundaries", state, stateGrain ? "state" : "detail"],
    queryFn: async () => {
      const fc = await loadGeo(stateGrain ? "US" : state);
      return stateGrain
        ? { ...fc, features: fc.features.filter((f) => stateCode(f) === state) }
        : fc;
    },
    staleTime: Infinity,
  });
  const cityData = useQuery({
    queryKey: ["orientation-cities"],
    queryFn: async () => {
      const response = await fetch(publicStaticAsset("/geography/cities.json"));
      return response.json() as Promise<{ labels: City[] }>;
    },
    staleTime: Infinity,
  });
  const cities = useMemo(
    () =>
      (cityData.data?.labels || [])
        .filter((c) => c.state === state)
        .sort((a, b) => a.priority - b.priority)
        .slice(0, 7),
    [cityData.data, state],
  );
  const [renderer, setRenderer] = useState<"map" | "vector">("map");
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const element = wrap.current;
    if (!element) return;
    let frame = 0;
    // Resize and mobile viewport transitions can leave an intersection callback stale.
    // Measure the mounted element itself; intersection observation only schedules a check.
    const measure = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const rect = element.getBoundingClientRect();
        const inView =
          rect.width > 0 &&
          rect.height > 0 &&
          rect.bottom >= -100 &&
          rect.top <= window.innerHeight + 100 &&
          rect.right >= 0 &&
          rect.left <= window.innerWidth;
        setVisible(inView);
        if (inView) mapRef.current?.resize();
      });
    };
    const observer = new IntersectionObserver(measure, { rootMargin: "100px" });
    const sizeObserver = new ResizeObserver(measure);
    observer.observe(element);
    sizeObserver.observe(element);
    window.addEventListener("resize", measure);
    window.addEventListener("scroll", measure, {
      capture: true,
      passive: true,
    });
    window.visualViewport?.addEventListener("resize", measure);
    measure();
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      sizeObserver.disconnect();
      window.removeEventListener("resize", measure);
      window.removeEventListener("scroll", measure, true);
      window.visualViewport?.removeEventListener("resize", measure);
    };
  }, [geo.data, renderer]);
  const [error, setError] = useState("");
  const [hover, setHover] = useState<{
    name: string;
    value: number | null;
  } | null>(null);
  const focusedId = useFocusedGeography();
  const theme = useMapTheme(),
    spec = useMemo(
      () => createMapSpec(rows, layer, scaleMax, { label: metricLabel, unit }),
      [rows, layer, scaleMax, metricLabel, unit],
    );
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;
  const { enriched, unmapped } = useMemo(() => {
    if (!geo.data) return { enriched: null, unmapped: [] as GeoRow[] };
    const lookup = new Map<string, GeoRow>();
    rows.forEach((r) =>
      [r.id, r.canonical_id, r.boundary_id]
        .filter(Boolean)
        .forEach((k) => lookup.set(String(k), r)),
    );
    const mapped = new Set<string>();
    return {
      enriched: {
        ...geo.data,
        features: geo.data.features.map((f) => {
          const p = f.properties || {},
            keys = [
              p.canonical_id,
              p.id,
              p.GEOID ? `county:${p.GEOID}` : null,
              p.GEOID,
            ]
              .filter(Boolean)
              .map(String);
          const r = keys.map((k) => lookup.get(k)).find(Boolean);
          if (r) mapped.add(r.id);
          const value = r ? spec.value(r) : null;
          return {
            ...f,
            properties: {
              ...p,
              id: r?.id || String(p.canonical_id || p.id || p.GEOID),
              name: r?.name || p.name || p.NAME,
              value,
              has_data: value == null ? 0 : 1,
              selected: r && selected.includes(r.id) ? 1 : 0,
              focused:
                r && (focusedId === r.id || focusedId === r.canonical_id)
                  ? 1
                  : 0,
              fill: spec.color(value),
              radius: value == null ? 0 : spec.radius(Math.abs(value)),
            },
          };
        }),
      } as FC,
      unmapped: rows.filter((r) => !mapped.has(r.id)),
    };
  }, [geo.data, rows, selected, spec, focusedId]);
  const latestRender = useRef({ data: enriched, layer });
  latestRender.current = { data: enriched, layer };
  useEffect(() => {
    if (!enriched || !container.current || renderer !== "map" || !visible)
      return;
    let stopped = false;
    let ownedMap: import("maplibre-gl").Map | null = null;
    let removeSync = () => {};
    let removeThemeListeners = () => {};
    import("maplibre-gl").then(({ default: ml }) => {
      if (stopped || !container.current) return;
      try {
        const map = new ml.Map({
          container: container.current,
          style: {
            version: 8,
            sources: {},
            layers: [
              {
                id: "background",
                type: "background",
                paint: { "background-color": cssColor("--map-background") },
              },
            ],
          },
          center: state === "AK" ? [-151, 64] : [-96, 38],
          zoom: 3,
          attributionControl: false,
          cooperativeGestures: true,
          canvasContextAttributes: { preserveDrawingBuffer: true },
        });
        ownedMap = map;
        mapRef.current = map;
        const synchronizeTheme = () => applyMapTheme(map);
        map.on("idle", synchronizeTheme);
        removeThemeListeners = () => map.off("idle", synchronizeTheme);
        map.addControl(
          new ml.NavigationControl({ showCompass: false }),
          "top-right",
        );
        map.addControl(
          new ml.AttributionControl({
            customAttribution: "U.S. Census · 2024 boundaries · local",
            compact: true,
          }),
          "bottom-left",
        );
        map.on("load", () => {
          if (stopped) return;
          map.addSource("areas", {
            type: "geojson",
            data: enriched,
            promoteId: "id",
          });
          map.addLayer({
            id: "areas-fill",
            type: "fill",
            source: "areas",
            paint: { "fill-color": ["get", "fill"], "fill-opacity": 0.95 },
          });
          const pattern = new Uint8Array(8 * 8 * 4);
          for (let y = 0; y < 8; y++)
            for (let x = 0; x < 8; x++) {
              const i = (y * 8 + x) * 4;
              pattern[i] = 130;
              pattern[i + 1] = 150;
              pattern[i + 2] = 170;
              pattern[i + 3] = (x + y) % 8 < 2 ? 100 : 0;
            }
          map.addImage("missing-pattern", {
            width: 8,
            height: 8,
            data: pattern,
          });
          map.addLayer({
            id: "areas-missing",
            type: "fill",
            source: "areas",
            filter: ["==", ["get", "has_data"], 0],
            paint: { "fill-pattern": "missing-pattern" },
          });
          map.addLayer({
            id: "areas-line",
            type: "line",
            source: "areas",
            paint: {
              "line-color": [
                "case",
                ["==", ["get", "selected"], 1],
                cssColor("--selection"),
                cssColor("--map-stroke"),
              ],
              "line-width": ["case", ["==", ["get", "selected"], 1], 2.7, 0.6],
            },
          });
          map.addSource("points", {
            type: "geojson",
            data: { type: "FeatureCollection", features: [] },
          });
          map.addLayer({
            id: "volume-circles",
            type: "circle",
            source: "points",
            paint: {
              "circle-color": cssColor("--cyan"),
              "circle-stroke-color": cssColor("--panel"),
              "circle-stroke-width": 0.8,
              "circle-opacity": 0.72,
              "circle-radius": ["get", "radius"],
            },
          });
          const b = boundsOf(enriched);
          const stored = (
            new URLSearchParams(location.search).get("ui_map_view") || ""
          ).split(",");
          if (stored[0] === state && stored.length === 4)
            map.jumpTo({
              center: [Number(stored[1]), Number(stored[2])],
              zoom: Number(stored[3]),
            });
          else if (b) map.fitBounds(b, { padding: 30, duration: 0 });
          const markers = cities.map((city) => {
            const element = document.createElement("span");
            element.className = "map-city-label";
            element.textContent = city.name;
            element.setAttribute("aria-hidden", "true");
            new ml.Marker({ element, anchor: "left", offset: [5, 0] })
              .setLngLat([city.longitude, city.latitude])
              .addTo(map);
            return { city, element };
          });
          const declutter = () => {
            const occupied: { x: number; y: number }[] = [];
            markers.forEach(({ city, element }) => {
              const p = map.project([city.longitude, city.latitude]);
              const collision = occupied.some(
                (o) => Math.abs(o.x - p.x) < 90 && Math.abs(o.y - p.y) < 24,
              );
              element.style.visibility = collision ? "hidden" : "visible";
              if (!collision) occupied.push(p);
            });
          };
          map.on("move", declutter);
          declutter();
          const origin = crypto.randomUUID();
          const synchronize = (event: Event) => {
            const d = (
              event as CustomEvent<{
                state: string;
                origin: string;
                lng: number;
                lat: number;
                zoom: number;
              }>
            ).detail;
            if (d.state !== state || d.origin === origin) return;
            const c = map.getCenter();
            if (
              Math.abs(c.lng - d.lng) < 0.00001 &&
              Math.abs(c.lat - d.lat) < 0.00001 &&
              Math.abs(map.getZoom() - d.zoom) < 0.00001
            )
              return;
            map.jumpTo({ center: [d.lng, d.lat], zoom: d.zoom });
          };
          window.addEventListener("observatory-map-camera", synchronize);
          removeSync = () =>
            window.removeEventListener("observatory-map-camera", synchronize);
          map.on("moveend", () => {
            const c = map.getCenter(),
              p = new URLSearchParams(location.search);
            p.set(
              "ui_map_view",
              [
                state,
                c.lng.toFixed(5),
                c.lat.toFixed(5),
                map.getZoom().toFixed(3),
              ].join(","),
            );
            history.replaceState(null, "", `?${p}`);
            window.dispatchEvent(
              new CustomEvent("observatory-map-camera", {
                detail: {
                  state,
                  origin,
                  lng: c.lng,
                  lat: c.lat,
                  zoom: map.getZoom(),
                },
              }),
            );
          });
          map.on("click", "areas-fill", (e) => {
            const p = e.features?.[0]?.properties;
            if (p?.has_data) onSelectRef.current(String(p.id));
          });
          map.on("mousemove", "areas-fill", (e) => {
            const p = e.features?.[0]?.properties;
            map.getCanvas().style.cursor = p?.has_data ? "pointer" : "";
            focusGeography(p?.has_data ? String(p.id) : null);
            setHover(
              p
                ? { name: p.name, value: p.has_data ? Number(p.value) : null }
                : null,
            );
          });
          map.on("mouseleave", "areas-fill", () => {
            setHover(null);
            focusGeography(null);
          });
          const current = latestRender.current;
          if (current.data) updateMap(map, current.data, current.layer);
          applyMapTheme(map);
        });
        map.on("error", (e) => {
          if (e.error?.message && !e.error.message.includes("Failed to fetch"))
            setError(e.error.message);
        });
      } catch (e) {
        setError(e instanceof Error ? e.message : "Map unavailable");
        setRenderer("vector");
      }
    });
    return () => {
      stopped = true;
      removeSync();
      removeThemeListeners();
      ownedMap?.remove();
      if (mapRef.current === ownedMap) mapRef.current = null;
    };
  }, [geo.data, renderer, state, visible, cities]);
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    // Paint layers can be updated while GeoJSON source work is pending.
    // The creation load callback applies the latest ref if layers do not exist yet.
    if (enriched && map.getSource("areas")) updateMap(map, enriched, layer);
    applyMapTheme(map);
  }, [enriched, layer, theme]);
  if (geo.isPending)
    return <Loading label={`Loading ${stateName(state)} boundaries…`} />;
  if (geo.isError)
    return (
      <Empty title="Local boundaries unavailable">{geo.error.message}</Empty>
    );
  return (
    <div className="state-map-wrap" ref={wrap}>
      {renderer === "map" ? (
        <div
          ref={container}
          style={{ height }}
          className="state-map"
          aria-label={`${stateName(state)} ${spec.label}. Geographic table provides keyboard selection.`}
        />
      ) : (
        enriched && (
          <VectorStateMap
            geo={enriched}
            onSelect={onSelect}
            height={height}
            spec={spec}
            state={state}
            cities={cities}
          />
        )
      )}
      <div className="map-floating-controls">
        <button
          className="icon-button"
          aria-label="Reset map extent"
          onClick={() => {
            const b = enriched && boundsOf(enriched);
            if (b) mapRef.current?.fitBounds(b, { padding: 30, duration: 0 });
          }}
        >
          <RotateCcw size={15} />
        </button>
        <button
          className="icon-button"
          aria-label="Switch between interactive and vector map"
          onClick={() => setRenderer(renderer === "map" ? "vector" : "map")}
        >
          <Layers size={15} />
        </button>
        <button
          className="icon-button"
          aria-label="Fullscreen map"
          onClick={() => wrap.current?.requestFullscreen()}
        >
          <Expand size={15} />
        </button>
      </div>
      {hover && (
        <div className="state-hover">
          <b>{hover.name}</b>
          <span>
            {hover.value == null
              ? "No matching observation"
              : fmt(hover.value, spec.unit ? 1 : 0) + spec.unit}
          </span>
        </div>
      )}
      <MapLegend spec={spec} />
      {unmapped.length > 0 && (
        <details className="join-details">
          <summary>
            {unmapped.length} reporting areas have no compatible boundary
          </summary>
          <p>
            Their values remain in the table. No estimates are distributed into
            smaller places.
          </p>
          <p>{unmapped.map((r) => r.name).join(", ")}</p>
        </details>
      )}
      {error && (
        <Notice>
          Map renderer: {error}. A matching vector view is available.
        </Notice>
      )}
    </div>
  );
}
function updateMap(map: import("maplibre-gl").Map, data: FC, layer: MapLayer) {
  const resolved: FC = {
    ...data,
    features: data.features.map((f) => ({
      ...f,
      properties: {
        ...f.properties,
        fill: String(f.properties?.fill).startsWith("var(")
          ? cssColor(String(f.properties?.fill).slice(4, -1))
          : f.properties?.fill,
      },
    })),
  };
  (
    map.getSource("areas") as import("maplibre-gl").GeoJSONSource | undefined
  )?.setData(resolved);
  const points: FC = {
    type: "FeatureCollection",
    features: resolved.features
      .filter((f) => f.properties?.has_data === 1)
      .map((f) => ({
        type: "Feature",
        geometry: { type: "Point", coordinates: geoCentroid(f) },
        properties: f.properties,
      })),
  };
  (
    map.getSource("points") as import("maplibre-gl").GeoJSONSource | undefined
  )?.setData(points);
  if (map.getLayer("areas-line"))
    map.setPaintProperty("areas-line", "line-width", [
      "case",
      ["==", ["get", "selected"], 1],
      2.7,
      ["==", ["get", "focused"], 1],
      2,
      0.6,
    ]);
  if (map.getLayer("volume-circles"))
    map.setLayoutProperty(
      "volume-circles",
      "visibility",
      layer === "volume" ? "visible" : "none",
    );
}
function VectorStateMap({
  geo,
  onSelect,
  height,
  spec,
  state,
  cities,
}: {
  cities: City[];
  geo: FC;
  onSelect: (id: string) => void;
  height: number;
  spec: MapSpec;
  state: string;
}) {
  const projection = (
    state === "AK" || state === "HI" ? geoAlbersUsa() : geoMercator()
  ).fitExtent(
    [
      [20, 20],
      [780, height - 20],
    ],
    geo,
  );
  const path = geoPath(projection),
    hatch = useId().replaceAll(":", "");
  return (
    <svg
      className="map-svg vector-state-map"
      viewBox={`0 0 800 ${height}`}
      role="group"
      aria-label="Selectable reporting areas"
    >
      <defs>
        <pattern id={hatch} width="6" height="6" patternUnits="userSpaceOnUse">
          <rect width="6" height="6" fill="var(--map-missing)" />
          <path d="M0 6L6 0" stroke="var(--map-stroke)" strokeWidth=".4" />
        </pattern>
      </defs>
      {geo.features.map((f, i) => {
        const p = f.properties || {},
          center = path.centroid(f);
        return (
          <g key={p.id || i}>
            <path
              d={path(f) || ""}
              fill={p.has_data ? p.fill : `url(#${hatch})`}
              stroke={p.selected ? "var(--selection)" : "var(--map-stroke)"}
              strokeWidth={p.selected ? 2.5 : 0.6}
              tabIndex={p.has_data ? 0 : -1}
              role="button"
              aria-label={`${p.name}: ${p.value == null ? "unavailable" : fmt(p.value, spec.unit ? 1 : 0) + spec.unit}`}
              onFocus={() => focusGeography(p.id)}
              onMouseEnter={() => focusGeography(p.id)}
              onMouseLeave={() => focusGeography(null)}
              onClick={() => p.has_data && onSelect(p.id)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  p.has_data && onSelect(p.id);
                }
              }}
            >
              <title>{`${p.name} · ${p.value == null ? "No observation" : fmt(p.value, spec.unit ? 1 : 0) + spec.unit}`}</title>
            </path>
            {spec.layer === "volume" &&
              p.has_data &&
              Number.isFinite(center[0]) && (
                <circle
                  cx={center[0]}
                  cy={center[1]}
                  r={p.radius}
                  fill="var(--cyan)"
                  fillOpacity=".72"
                  stroke="var(--panel)"
                  strokeWidth=".8"
                  pointerEvents="none"
                />
              )}
          </g>
        );
      })}
      {cities.map((city) => {
        const p = projection([city.longitude, city.latitude]);
        return (
          p && (
            <g
              key={city.name}
              className="vector-city-label"
              pointerEvents="none"
            >
              <circle cx={p[0]} cy={p[1]} r={3.2} />
              <text x={p[0] + 7} y={p[1] + 3}>
                {city.name}
              </text>
            </g>
          )
        );
      })}
    </svg>
  );
}
function MapLegend({ spec }: { spec: MapSpec }) {
  return (
    <div className="quantitative-legend">
      <div className="legend-title">
        <b>{spec.label}</b>
        <span>
          {spec.layer === "volume"
            ? "Circle area represents volume"
            : spec.unit === "pp"
              ? "Percentage points"
              : spec.unit === "%"
                ? "Percent"
                : "Reported count"}
        </span>
      </div>
      {spec.layer === "volume" ? (
        <div className="circle-key">
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
      ) : spec.layer === "coverage" ? (
        <div className="map-legend">
          <span>
            <i style={{ background: "#32a69d" }} />
            Published observation
          </span>
          <span>
            <i className="hatch" />
            Missing / unjoined
          </span>
        </div>
      ) : (
        <>
          <div className="legend-ramp">
            {spec.colors.map((c, i) => (
              <span
                key={c}
                style={{ background: c }}
                title={`${fmt(spec.bins[i], 1)} to ${fmt(spec.bins[i + 1], 1)} ${spec.unit}`}
              />
            ))}
          </div>
          <div className="legend-ticks">
            {[
              spec.bins[0],
              (spec.domain[0] + spec.domain[1]) / 2,
              spec.bins.at(-1)!,
            ].map((n, i) => (
              <span key={i}>
                {fmt(n, spec.unit ? 1 : 0)}
                {spec.unit}
              </span>
            ))}
          </div>
        </>
      )}
      {!["volume", "coverage"].includes(spec.layer) && (
        <details className="legend-bin-details">
          <summary>Exact color thresholds</summary>
          <div>
            {spec.colors.map((color, i) => (
              <span key={i}>
                <i style={{ background: color }} />
                {fmt(spec.bins[i], spec.unit ? 1 : 0)} to{" "}
                {fmt(spec.bins[i + 1], spec.unit ? 1 : 0)}
                {spec.unit}
              </span>
            ))}
          </div>
        </details>
      )}
      <p>
        U.S. Census 2024 display boundaries ·{" "}
        <span className="legend-missing">▧</span> Missing values remain missing
        · Selected places outlined
      </p>
    </div>
  );
}
export function MapLayerControl({
  value,
  onChange,
}: {
  value: MapLayer;
  onChange: (v: MapLayer) => void;
}) {
  return (
    <Segmented
      value={value}
      onChange={onChange}
      label="Map layer"
      items={[
        { id: "volume", label: "Volume" },
        { id: "share", label: "Share" },
        { id: "change", label: "Change" },
        { id: "participation", label: "Rate" },
        { id: "coverage", label: "Coverage" },
      ]}
    />
  );
}
