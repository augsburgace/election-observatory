import { isPublicMode, getPublicManifest } from "./publicData";
import { PublicPublication, PublishedAlternatives } from "./components/PublicPublication";
import "./public.css";
import { Suspense, lazy, useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  CalendarDays as CalendarIcon,
  BarChart3,
  BookOpen,
  Bookmark,
  ChevronRight,
  Clock3,
  Database,
  Download,
  FileChartColumnIncreasing,
  Globe2,
  House,
  Layers3,
  MapPinned,
  Menu,
  Moon,
  RefreshCw,
  Save,
  Settings2,
  SlidersHorizontal,
  Sun,
  Telescope,
  TrendingUp,
  X,
} from "lucide-react";
import {
  api,
  downloadExport,
  downloadHistoricalExport,
  downloadContextExport,
  queryString,
} from "./api";
import type { AppContext, Page, ResearchQuery } from "./types";
import { dateLabel, human, inputDate, stateName } from "./utils";
import { currentLayout, useViewOption } from "./viewState";
import { STATE_NAMES } from "./utils";
import UniversalSearch from "./components/UniversalSearch";
import ResearchBoundary from "./components/ResearchBoundary";
import { atlasApi } from "./atlasApi";
import { initialResultGrain } from "./researchDefaults";
import EntityInspector, { openEntity } from "./components/EntityInspector";
import {
  Badge,
  Empty,
  Field,
  Loading,
  Notice,
  Select,
  Toast,
  useModalFocus,
} from "./components/ui";
import EvidenceDrawer from "./components/EvidenceDrawer";
import type { EvidenceSelection } from "./components/EvidenceDrawer";
const Overview = lazy(() => import("./pages/Overview"));
const StateDossier = lazy(() => import("./pages/StateDossier"));
const Atlas = lazy(() => import("./pages/Atlas"));
const History = lazy(() => import("./pages/History"));
const Polls = lazy(() => import("./pages/Polls"));
const Scenarios = lazy(() => import("./pages/Scenarios"));
const Forecasts = lazy(() => import("./pages/Forecasts"));
const Notebook = lazy(() => import("./pages/Notebook"));
const Reports = lazy(() => import("./pages/Reports"));
const Sources = lazy(() => import("./pages/Sources"));
const Elections = lazy(() => import("./pages/Elections"));
const PlaceDossier = lazy(() => import("./pages/PlaceDossier"));
const NAV: { id: Page; name: string; icon: typeof House; group?: string }[] = [
  { id: "overview", name: "Today", icon: House },
  { id: "atlas", name: "Atlas", icon: MapPinned },
  { id: "states", name: "States", icon: Globe2 },
  { id: "elections", name: "Elections", icon: CalendarIcon },
  { id: "history", name: "History", icon: Clock3, group: "RESEARCH" },
  { id: "polls", name: "Polls", icon: BarChart3 },
  { id: "scenarios", name: "Scenarios", icon: SlidersHorizontal },
  { id: "forecasts", name: "Forecasts", icon: TrendingUp },
  { id: "notebook", name: "Notebook", icon: BookOpen },
  { id: "reports", name: "Reports", icon: FileChartColumnIncreasing },
  { id: "sources", name: "Sources", icon: Database },
];
const defaults: ResearchQuery = {
  state: "NC",
  cycle: 2026,
  baseline: 2022,
  as_of: "",
  time_basis: "reported",
  metric: "ballots_cast",
  mode: "all",
  geography_ids: [],
  alignment: "days_to_election",
};
function sameEvidenceFamily(a: ResearchQuery | undefined, b: ResearchQuery) {
  if (!a) return false;
  return (
    [
      "state",
      "cycle",
      "baseline",
      "metric",
      "mode",
      "time_basis",
      "alignment",
      "category_dimension",
      "category",
    ].every(
      (key) =>
        (a as unknown as Record<string, unknown>)[key] ===
        (b as unknown as Record<string, unknown>)[key],
    ) &&
    a.geography_ids.join(",") === b.geography_ids.join(",") &&
    (a.date_window || []).join(",") === (b.date_window || []).join(",")
  );
}
function readLocation() {
  const p = new URLSearchParams(location.search);
  const q = { ...defaults };
  for (const key of [
    "state",
    "as_of",
    "metric",
    "mode",
    "time_basis",
    "alignment",
    "category_dimension",
    "category",
  ] as const) {
    const value = p.get(key);
    if (value) (q as unknown as Record<string, unknown>)[key] = value;
  }
  for (const key of ["cycle", "baseline", "revision"] as const) {
    const value = p.get(key);
    if (value && !Number.isNaN(Number(value))) q[key] = Number(value);
  }
  q.geography_ids = (p.get("geography_ids") || "").split(",").filter(Boolean);
  q.date_window = (p.get("date_window") || "").split(",").filter(Boolean);
  const page = p.get("page") as Page;
  return {
    query: q,
    page:
      NAV.some((n) => n.id === page) || page === "place"
        ? page
        : ("overview" as Page),
  };
}
export default function App() {
  const cache = useQueryClient();
  const [locationState, setLocationState] = useState(readLocation);
  const { query, page } = locationState;
  const [publicSelectedText, setPublicSelectedText] = useViewOption<string>("selected_geographies", "");
  const selectedGeographyIds = isPublicMode() ? publicSelectedText.split(",").filter(Boolean) : query.geography_ids;
  const initializedPublicScope = useRef(false);
  const publicIndex = useQuery({ queryKey: ["public-publication"], queryFn: () => getPublicManifest(), enabled: isPublicMode() });
  const [theme, setTheme] = useState(
    () => localStorage.getItem("observatory-atlas-theme") || "light",
  );
  const [density, setDensity] = useState(
    () => localStorage.getItem("observatory-density") || "comfortable",
  );
  const [navOpen, setNavOpen] = useState(false);
  const [researchOpen, setResearchOpen] = useState(
    () => !["overview", "atlas", "states", "elections", "place"].includes(page),
  );
  const [researchQuestion, setResearchQuestion] = useViewOption<string>(
    "question",
    new URLSearchParams(location.search).has("metric")
      ? "participation"
      : "historical",
  );
  const [year, setYear] = useViewOption<string>("result_year", "2024");
  const [storedResultGrain, setResultGrain] = useViewOption<string>(
    "result_grain",
    "county",
  );
  const [office, setOffice] = useViewOption<string>(
    "result_office",
    "PRESIDENT",
  );
  const [filterOpen, setFilterOpen] = useState(false);
  const [evidence, setEvidence] = useState<EvidenceSelection | null>(null);
  const [toast, setToast] = useState("");
  const [saving, setSaving] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const explicitResultGrain =
    new URLSearchParams(location.search).get("ui_result_grain") ||
    new URLSearchParams(location.search).get("ui_results_grain");
  const resultGrain = initialResultGrain(
    query.state,
    office,
    explicitResultGrain
      ? new URLSearchParams(location.search).has("ui_result_grain")
        ? storedResultGrain
        : explicitResultGrain
      : null,
  );
  const [saveOpen, setSaveOpen] = useState(false);
  const [saveTitle, setSaveTitle] = useState("");
  const [exportOpen, setExportOpen] = useState(false);
  useModalFocus(saveOpen, ".save-view-modal", () => setSaveOpen(false));
  const [allWarnings, setAllWarnings] = useState(false);
  const bootstrap = useQuery({
    queryKey: ["bootstrap"],
    queryFn: api.bootstrap,
    refetchInterval: 60_000,
  });
  const stateCatalog = useQuery({
    queryKey: ["atlas", "states"],
    queryFn: atlasApi.states,
  });
  const catalogState = stateCatalog.data?.states.find(
    (s) => s.code === query.state,
  );
  const workspace = useQuery({
    queryKey: ["workspace", query],
    queryFn: ({ signal }) => api.workspace(query, signal),
    enabled: !!bootstrap.data,
    placeholderData: (previous, previousQuery) =>
      sameEvidenceFamily(
        previousQuery?.queryKey[1] as ResearchQuery | undefined,
        query,
      )
        ? previous
        : undefined,
  });
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("observatory-theme", theme);
    localStorage.setItem("observatory-atlas-theme", theme);
  }, [theme]);
  useEffect(() => {
    document.documentElement.dataset.density = density;
    localStorage.setItem("observatory-density", density);
  }, [density]);
  useEffect(() => {
    const fn = () => setLocationState(readLocation());
    window.addEventListener("popstate", fn);
    return () => window.removeEventListener("popstate", fn);
  }, []);
  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(""), 6000);
    return () => clearTimeout(timer);
  }, [toast]);
  useEffect(() => {
    if (!isPublicMode() || !publicIndex.data || initializedPublicScope.current) return;
    initializedPublicScope.current = true;
    const params = new URLSearchParams(location.search);
    const explicit = ["cycle", "baseline", "as_of", "revision", "metric", "mode", "time_basis", "alignment", "geography_ids", "category", "category_dimension", "date_window"].some(key => params.has(key));
    if (explicit) return;
    const publication = publicIndex.data;
    const chosen = publication.partitions?.[query.state]?.recommended_query || publication.partitions?.[query.state]?.default_query;
    if (chosen) navigate(chosen as Partial<ResearchQuery>);
    else navigate({ revision: publication.dataset_revision, as_of: publication.data_as_of });
  }, [publicIndex.data]);
  function navigate(patch: Partial<ResearchQuery>, target?: Page) {
    if (isPublicMode() && patch.geography_ids !== undefined && (!patch.state || patch.state === query.state)) {
      setPublicSelectedText(patch.geography_ids.join(","));
      const { geography_ids: _selected, ...remaining } = patch;
      void _selected;
      if (!Object.keys(remaining).length && !target) return;
      patch = remaining;
    }
    if (isPublicMode() && patch.state && patch.state !== query.state) setPublicSelectedText("");
    const nextQuery = { ...query, ...patch };
    if (patch.state && patch.state !== query.state) {
      nextQuery.geography_ids = [];
      delete nextQuery.category;
      delete nextQuery.category_dimension;
    }
    const stateChanged = !!patch.state && patch.state !== query.state;
    const nextPage =
      target || (stateChanged && page === "place" ? "states" : page);
    if (stateChanged)
      window.dispatchEvent(
        new CustomEvent("observatory-entity", { detail: "" }),
      );
    const next = { query: nextQuery, page: nextPage };
    setLocationState(next);
    const params = new URLSearchParams(queryString(nextQuery));
    Object.entries(currentLayout())
      .filter(
        ([key]) =>
          !(
            patch.state &&
            patch.state !== query.state &&
            [
              "ui_map_view",
              "ui_place",
              "ui_entity",
              "ui_result_contest",
              "ui_precinct_contest",
              "ui_precinct_dataset",
              "ui_result_option",
              "ui_result_offset",
              "ui_place_history_offset",
            ].includes(key)
          ),
      )
      .forEach(([key, value]) => params.set(key, value));
    params.set("page", nextPage);
    window.history.pushState(null, "", `?${params}`);
    setNavOpen(false);
    if (nextPage !== page) window.scrollTo({ top: 0, behavior: "instant" });
  }
  async function refresh() {
    setRefreshing(true);
    try {
      if (isPublicMode()) {
        await getPublicManifest(true);
        await cache.invalidateQueries({ queryKey: ["bootstrap"] });
        await cache.invalidateQueries({ queryKey: ["public-publication"] });
        setToast("Checked for a newer published release. Choose Updated data available to move a pinned investigation.");
        setRefreshing(false);
        return;
      }
      const job = await api.refresh();
      setToast(
        `Collection ${job.id ? `job #${job.id} ` : ""}queued. Validated evidence remains available.`,
      );
      cache.invalidateQueries({ queryKey: ["jobs"] });
      setTimeout(() => {
        cache.invalidateQueries({ queryKey: ["bootstrap"] });
        cache.invalidateQueries({ queryKey: ["workspace"] });
        cache.invalidateQueries({ queryKey: ["sources"] });
        setRefreshing(false);
      }, 7000);
    } catch (e) {
      setToast((e as Error).message);
      setRefreshing(false);
    }
  }
  async function saveView() {
    setSaving(true);
    try {
      await api.saveResearch({
        kind: "view",
        title:
          saveTitle.trim() ||
          `${stateName(query.state)} · ${human(page)} · ${dateLabel(query.as_of || bootstrap.data?.app?.today)}`,
        view: {
          query: workspace.data?.query || {
            ...query,
            revision: workspace.data?.revision,
          },
          page,
          density,
          layout: currentLayout(),
          tab: new URLSearchParams(location.search).get("tab"),
        },
      });
      cache.invalidateQueries({ queryKey: ["research"] });
      setSaveOpen(false);
      setToast(`Exact view saved at revision ${workspace.data?.revision}.`);
    } catch (e) {
      setToast((e as Error).message);
    } finally {
      setSaving(false);
    }
  }
  const data = workspace.data;
  const app = bootstrap.data?.app;
  const revision = data?.revision ?? bootstrap.data?.latest_revision ?? 0;
  const latestRevision =
    bootstrap.data?.latest_revision ?? data?.latest_revision ?? revision;
  const updateAvailable = latestRevision > revision;
  const active = NAV.find((n) => n.id === page) || {
    name: "Place profile",
    id: page,
  };
  const ctx: AppContext | undefined =
    bootstrap.data && data
      ? {
          bootstrap: bootstrap.data,
          workspace: data,
          query: workspace.isPlaceholderData
            ? {
                ...query,
                as_of: data.query.as_of || query.as_of,
                revision: data.revision,
              }
            : query,
          selectedGeographyIds,
          selectionScope: isPublicMode() ? "view_local" : undefined,
          setQuery: (patch) => navigate(patch),
          setPage: (p) => navigate({}, p),
          inspect: setEvidence,
          notify: setToast,
          refresh,
          refreshing,
          researchQuestion,
          resultYear: Number(year),
          resultOffice: office,
          setResearchQuestion,
          setResultYear: (value) => setYear(String(value)),
          setResultOffice: setOffice,
        }
      : undefined;
  const currentWorkbench = [
    "history",
    "polls",
    "scenarios",
    "forecasts",
    "notebook",
    "reports",
    "sources",
  ].includes(page);
  const participationScope =
    currentWorkbench || researchQuestion === "participation";
  const activeQuestion =
    page === "polls"
      ? "polls"
      : page === "scenarios"
        ? "scenarios"
        : page === "forecasts"
          ? "forecasts"
          : researchQuestion;
  function chooseElection(value: string) {
    if (participationScope) navigate({ cycle: Number(value) });
    else {
      setYear(value);
      if (
        Number(value) % 4 !== 0 &&
        office === "PRESIDENT" &&
        !new URLSearchParams(location.search).has("ui_result_office") &&
        !query.revision
      )
        setOffice("US SENATE");
    }
  }
  const views = {
    overview: Overview,
    states: StateDossier,
    atlas: Atlas,
    history: History,
    polls: Polls,
    scenarios: Scenarios,
    forecasts: Forecasts,
    notebook: Notebook,
    reports: Reports,
    sources: Sources,
    elections: Elections,
    place: PlaceDossier,
  };
  const CurrentPage = views[page];
  return (
    <>
      <a href="#research-main" className="skip-link">
        Skip to research workspace
      </a>
      <div className="app-shell">
        <aside className={`sidebar ${navOpen ? "is-open" : ""}`}>
          <a
            className="brand"
            href="?page=overview"
            aria-label="Observatory overview"
          >
            <div className="brand-symbol">
              <Telescope size={24} />
            </div>
            <div>
              <strong>OBSERVATORY</strong>
              <span>Election Atlas</span>
            </div>
          </a>
          <div className="nav-label">EXPLORE</div>
          <nav aria-label="Main navigation">
            {NAV.map((item, index) => (
              <div key={item.id}>
                {index === 4 && (
                  <button
                    className={`nav-item research-parent ${researchOpen ? "expanded" : ""}`}
                    onClick={() => setResearchOpen(!researchOpen)}
                    aria-expanded={researchOpen}
                    aria-label="Research"
                    title="Research tools"
                  >
                    <BookOpen size={18} />
                    <span>Research</span>
                    <ChevronRight size={14} />
                  </button>
                )}
                {(index < 4 || researchOpen) && (
                  <button
                    className={`nav-item ${NAV.indexOf(item) >= 4 ? "research-child" : ""} ${page === item.id ? "active" : ""}`}
                    onClick={() => navigate({}, item.id)}
                    aria-current={page === item.id ? "page" : undefined}
                    aria-label={item.name}
                    title={item.name}
                  >
                    <item.icon size={18} />
                    <span>{item.name}</span>
                    {page === item.id && <ChevronRight size={14} />}
                  </button>
                )}
              </div>
            ))}
          </nav>
          <div className="sidebar-bottom">
            <div className="local-status">
              <span className="status-dot" />
              <span>{isPublicMode() ? "PUBLIC RESEARCH" : "LOCAL RESEARCH"}</span>
              <Bookmark size={13} />
            </div>
            <p>
              {isPublicMode() ? "Your notes stay in this browser." : "Evidence stays on this Mac."}
              <br />
              Every number has a source.
            </p>
            <div className="sidebar-tools">
              <button
                className="icon-button"
                onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
                aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
              >
                {theme === "dark" ? <Sun size={17} /> : <Moon size={17} />}
              </button>
              <button
                className="icon-button"
                onClick={() =>
                  setDensity(density === "compact" ? "comfortable" : "compact")
                }
                aria-label={`Use ${density === "compact" ? "comfortable" : "compact"} density`}
                title={`Density: ${density}`}
              >
                <Settings2 size={17} />
              </button>
              <span>v{app?.version || "0.1.0"}</span>
            </div>
          </div>
        </aside>
        {navOpen && (
          <button
            className="nav-scrim"
            aria-label="Close navigation"
            onClick={() => setNavOpen(false)}
          />
        )}
        <div className="app-main">
          <header className="topbar">
            <div className="topbar-title">
              <button
                className="icon-button mobile-menu"
                aria-label="Open navigation"
                onClick={() => setNavOpen(!navOpen)}
              >
                <Menu size={21} />
              </button>
              <div className="mobile-brand">
                OBSERVATORY<small>Election Atlas</small>
              </div>
              <UniversalSearch
                onSelect={(state, target, id) => {
                  navigate({ state }, target);
                  if (id) {
                    if (id.startsWith("option:") || id.startsWith("contest:"))
                      openEntity(id);
                    const p = new URLSearchParams(location.search);
                    p.set("ui_entity", id);
                    history.replaceState(null, "", `?${p}`);
                  }
                }}
              />
            </div>
            <div className="topbar-actions">
              <button
                className="icon-button desktop-only topbar-theme"
                aria-label={
                  theme === "dark" ? "Use light theme" : "Use dark theme"
                }
                onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
              >
                {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
              </button>
              <button
                className={`button secondary refresh-button ${refreshing ? "is-refreshing" : ""}`}
                onClick={refresh}
                disabled={refreshing}
              >
                <RefreshCw size={14} className={refreshing ? "spin" : ""} />
                <span>{isPublicMode() ? "Check publication" : refreshing ? "Collecting" : "Refresh"}</span>
              </button>
              <button
                className="button secondary"
                aria-label="Save view"
                onClick={() => setSaveOpen(true)}
              >
                <Save size={14} />
                <span className="desktop-only">Save view</span>
              </button>
              <div className="dropdown">
                <button
                  className="button primary"
                  aria-label="Export"
                  onClick={() => setExportOpen(!exportOpen)}
                >
                  <Download size={14} />
                  <span>Export</span>
                </button>
                {exportOpen && (
                  <div className="dropdown-menu">
                    {(isPublicMode() ? ["csv", "json", "pdf"] : ["csv", "json", "html", "pdf", "zip"]).map((format) => (
                      <button
                        key={format}
                        onClick={() => {
                          setExportOpen(false);
                          const historical =
                            ["historical", "swing"].includes(
                              researchQuestion,
                            ) && ["atlas", "elections", "place"].includes(page);
                          const params = new URLSearchParams(location.search);
                          (researchQuestion === "context" && page === "atlas"
                            ? downloadContextExport(
                                {
                                  state: query.state,
                                  metric:
                                    params.get("ui_context_metric") ||
                                    "population",
                                  revision: query.revision ?? revision,
                                  view_state: JSON.stringify({
                                    ...currentLayout(),
                                    geography_ids: query.geography_ids,
                                  }),
                                },
                                format,
                              )
                            : historical
                              ? downloadHistoricalExport(
                                  {
                                    state: query.state,
                                    year: Number(year),
                                    office,
                                    baseline: Number(year) - 4,
                                    contest_id:
                                      params.get("ui_result_contest") ||
                                      undefined,
                                    geography_level: initialResultGrain(
                                      query.state,
                                      office,
                                      params.get("ui_result_grain") ||
                                        params.get("ui_results_grain"),
                                    ),
                                    offset: ["precinct", "district"].includes(
                                      initialResultGrain(
                                        query.state,
                                        office,
                                        params.get("ui_result_grain"),
                                      ),
                                    )
                                      ? Number(
                                          params.get("ui_result_offset") || 0,
                                        )
                                      : 0,
                                    limit: ["precinct", "district"].includes(
                                      initialResultGrain(
                                        query.state,
                                        office,
                                        params.get("ui_result_grain"),
                                      ),
                                    )
                                      ? 200
                                      : undefined,
                                    revision: query.revision ?? revision,
                                    view_state: JSON.stringify({
                                      ...currentLayout(),
                                      geography_ids: query.geography_ids,
                                    }),
                                  },
                                  format,
                                )
                              : downloadExport(
                                  data?.query || { ...query, revision },
                                  format,
                                )
                          ).catch((e) => setToast(e.message));
                        }}
                      >
                        <Download size={14} />
                        {format === "zip"
                          ? "Research package"
                          : `${format.toUpperCase()} export`}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </header>
          <section
            className="scopebar simple-scope"
            aria-label="Research scope"
          >
            <div className="primary-scope-fields">
              <Field label="Place">
                <Select
                  label="Research state"
                  value={query.state}
                  onChange={(state) => navigate({ state })}
                  options={Object.entries(STATE_NAMES)
                    .filter(([code]) => code !== "DC")
                    .sort((a, b) => a[1].localeCompare(b[1]))
                    .map(([value, label]) => ({ value, label }))}
                />
              </Field>
              <Field label="Election">
                <Select
                  label="Research election"
                  value={participationScope ? String(query.cycle) : year}
                  onChange={chooseElection}
                  options={(participationScope
                    ? (bootstrap.data?.cycles || [2026, 2024, 2022, 2020, 2018, 2016])
                    : [
                        ...new Set([
                          Number(year),
                          ...(catalogState?.years || [
                            2024, 2022, 2020, 2018, 2016, 2012, 2008, 2004,
                            2000,
                          ]),
                        ]),
                      ].sort((a, b) => b - a)
                  ).map((c) => ({
                    value: String(c),
                    label: `${c} general election`,
                  }))}
                />
              </Field>
              <Field label="Question">
                <Select
                  label="Research question"
                  value={activeQuestion}
                  onChange={(value) => {
                    if (["polls", "scenarios", "forecasts"].includes(value))
                      navigate({}, value as Page);
                    else {
                      setResearchQuestion(value);
                      if (currentWorkbench) navigate({}, "atlas");
                    }
                  }}
                  options={[
                    { value: "historical", label: "How did places vote?" },
                    {
                      value: "participation",
                      label: "How is early voting developing?",
                    },
                    { value: "swing", label: "What changed since last cycle?" },
                    { value: "context", label: "Who lives here?" },
                    { value: "polls", label: "What do current polls show?" },
                    {
                      value: "scenarios",
                      label: "Explore turnout assumptions",
                    },
                    {
                      value: "forecasts",
                      label: "Make an EV-led Senate call",
                    },
                  ]}
                />
              </Field>
            </div>
            <button
              className={`button secondary research-options-toggle ${filterOpen ? "active" : ""}`}
              onClick={() => setFilterOpen(!filterOpen)}
              aria-expanded={filterOpen}
            >
              <SlidersHorizontal size={15} />
              Research options
            </button>
          </section>
          {filterOpen && (
            <section
              className="research-options"
              aria-label="Advanced research options"
            >
              <div className="advanced-mobile-question">
                <Field label="Research question">
                  <Select
                    label="Mobile research question"
                    value={researchQuestion}
                    onChange={setResearchQuestion}
                    options={[
                      { value: "historical", label: "How did places vote?" },
                      {
                        value: "participation",
                        label: "How is early voting developing?",
                      },
                      { value: "swing", label: "What changed historically?" },
                      { value: "context", label: "Who lives here?" },
                    ]}
                  />
                </Field>
              </div>
              <Field label="Historical geographic detail">
                <Select
                  label="Mobile geographic detail"
                  value={resultGrain}
                  onChange={setResultGrain}
                  options={[
                    { value: "state", label: "Statewide" },
                    { value: "county", label: "County / reporting area" },
                    { value: "district", label: "District" },
                    { value: "precinct", label: "Precinct" },
                  ]}
                />
              </Field>
              <Field label="Observation cutoff">
                <input
                  type="date"
                  aria-label="Observation cutoff"
                  value={inputDate(query.as_of)}
                  max={app?.today}
                  onChange={(e) => navigate({ as_of: e.target.value })}
                />
              </Field>
              <Field label="Compare cycle">
                <Select
                  label="Baseline election"
                  value={query.baseline}
                  onChange={(v) => navigate({ baseline: Number(v) })}
                  options={[2024, 2022, 2020, 2018, 2016].map((c) => ({
                    value: c,
                    label: String(c),
                  }))}
                />
              </Field>
              <Field label="Evidence chronology">
                <Select
                  label="Evidence chronology"
                  value={query.time_basis}
                  onChange={(v) =>
                    navigate({ time_basis: v as ResearchQuery["time_basis"] })
                  }
                  options={[
                    { value: "reported", label: "As reported" },
                    { value: "reconstructed", label: "Reconstructed" },
                    { value: "final", label: "Final records" },
                  ]}
                />
              </Field>
              <Field label="Participation metric">
                <Select
                  label="Observation metric"
                  value={query.metric}
                  onChange={(metric) => navigate({ metric })}
                  options={(bootstrap.data?.metrics || []).map((m) => ({
                    value: m.id || m.metric || m.key || "",
                    label: m.label || m.name || human(m.id),
                  }))}
                />
              </Field>
              <Field label="Voting method">
                <Select
                  label="Voting method"
                  value={query.mode}
                  onChange={(mode) => navigate({ mode })}
                  options={[
                    ...new Set([
                      "all",
                      query.mode,
                      ...(data?.coverage?.available_modes || []),
                    ]),
                  ].map((mode) => ({
                    value: mode,
                    label:
                      mode === "all" ? "All reported methods" : human(mode),
                  }))}
                />
              </Field>
              <Field label="Historical office">
                <Select
                  label="Historical office"
                  value={office}
                  onChange={setOffice}
                  options={[
                    ...new Set([
                      "PRESIDENT",
                      "US SENATE",
                      "US HOUSE",
                      "GOVERNOR",
                      "STATE SENATE",
                      "STATE HOUSE",
                      "JUDICIAL",
                      "LOCAL",
                      "BALLOT MEASURE",
                      ...(catalogState?.offices || []),
                    ]),
                  ].map((v) => ({ value: v, label: human(v) }))}
                />
              </Field>
              <div className="scope-revision">
                <Badge tone={query.revision != null ? "violet" : "teal"}>
                  {query.revision != null ? "Pinned evidence" : "Latest data"}
                </Badge>
                <span>Revision {revision}</span>
              </div>
            </section>
          )}
          {updateAvailable && (
            <div className="update-bar">
              <Activity size={15} />
              Validated revision {latestRevision} is available.
              <button
                onClick={() => {
                  navigate({ revision: undefined });
                  cache.invalidateQueries({ queryKey: ["workspace"] });
                }}
              >
                Load updated evidence
              </button>
            </div>
          )}
          <div className="context-strip">
            <span>
              <Globe2 size={13} />
              {stateName(query.state)}
            </span>
            <ChevronRight size={11} />
            <span>{active.name}</span>
            <div className="context-spacer" />
            {query.geography_ids.length > 0 && (
              <button
                className="filter-chip"
                onClick={() => navigate({ geography_ids: [] })}
              >
                {query.geography_ids.length} selected places
                <X size={11} />
              </button>
            )}
            <span className="context-cutoff">
              {query.as_of
                ? `As of ${dateLabel(query.as_of)}`
                : "Latest validated observations"}
            </span>
          </div>
          <PublicPublication />
          {isPublicMode() && selectedGeographyIds.length > 0 && <div className="public-selection-status" role="status"><MapPinned size={16}/><span><strong>Statewide totals; {selectedGeographyIds.length} selected area{selectedGeographyIds.length === 1 ? "" : "s"} highlighted.</strong> Place charts and comparisons identify these areas separately. Statewide calls, totals and polling keep their published scope.</span><button className="text-button" onClick={() => setPublicSelectedText("")}>Clear selection</button></div>}
          <main
            id="research-main"
            className={`research-main ${workspace.isFetching && !workspace.isPending ? "updating" : ""}`}
          >
            {bootstrap.isError ? (
              <Empty
                title={isPublicMode() ? "The published research release is unavailable" : "The local data service is unavailable"}
                action={
                  <button
                    className="button primary"
                    onClick={() => bootstrap.refetch()}
                  >
                    Try again
                  </button>
                }
              >
                {bootstrap.error.message}. {isPublicMode() ? "Please retry. Your browser notes remain private and available on this device." : "Start the backend service, then retry. Your local evidence and notes remain on disk."}
              </Empty>
            ) : bootstrap.isPending || workspace.isPending ? (
              <Loading label="Opening your research desk…" />
            ) : workspace.isError ? (
              <Empty
                title="This investigation could not load"
                action={
                  <button
                    className="button primary"
                    onClick={() => workspace.refetch()}
                  >
                    Retry investigation
                  </button>
                }
              >
                {workspace.error.message}
                <PublishedAlternatives state={query.state} choose={patch => navigate(patch)} />
              </Empty>
            ) : (
              ctx && (
                <>
                  {workspace.isPlaceholderData && (
                    <div className="evidence-updating" role="status">
                      <RefreshCw size={13} className="spin" />
                      <span>
                        Updating the selected cutoff. Displayed evidence remains
                        at {dateLabel(data?.query.as_of)} until validation
                        finishes.
                      </span>
                    </div>
                  )}
                  <ResearchBoundary key={`${page}:${query.state}:${query.cycle}:${revision}`}>
                    <Suspense fallback={<Loading />}>
                      <CurrentPage {...ctx} />
                    </Suspense>
                  </ResearchBoundary>
                  {data && data.warnings.length > 0 && (
                    <div className="workspace-warnings">
                      <button
                        className="text-button"
                        onClick={() => setAllWarnings(!allWarnings)}
                      >
                        {allWarnings ? "Hide" : "Show"} {data.warnings.length}{" "}
                        evidence {data.warnings.length === 1 ? "note" : "notes"}
                      </button>
                      {allWarnings &&
                        data.warnings.map((w, i) => (
                          <Notice key={i} tone="warning">
                            {w}
                          </Notice>
                        ))}
                    </div>
                  )}
                </>
              )
            )}
          </main>
          <footer className="app-footer">
            <div>
              <Layers3 size={13} />
              Measured evidence · Explicit assumptions · Inspectable sources
            </div>
            <span>Local-first · Revision {revision}</span>
          </footer>
        </div>
      </div>
      <nav className="mobile-bottom-nav" aria-label="Mobile main navigation">
        {NAV.slice(0, 4).map((item) => (
          <button
            key={item.id}
            className={page === item.id ? "active" : ""}
            onClick={() => navigate({}, item.id)}
          >
            <item.icon size={21} />
            <span>{item.name}</span>
          </button>
        ))}
        <button
          className={currentWorkbench ? "active" : ""}
          onClick={() => {
            setResearchOpen(true);
            setNavOpen(true);
          }}
        >
          <BookOpen size={21} />
          <span>Research</span>
        </button>
      </nav>
      <EntityInspector revision={query.revision ?? revision} />
      {evidence && (
        <EvidenceDrawer
          key={`${evidence.type}-${evidence.id}`}
          selection={evidence}
          onClose={() => setEvidence(null)}
          notify={setToast}
        />
      )}{" "}
      {toast && <Toast message={toast} onClose={() => setToast("")} />}
      {saveOpen && (
        <div className="modal-backdrop">
          <section
            className="modal save-view-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="save-title"
          >
            <header>
              <h2 id="save-title">Save this research view</h2>
              <button
                className="icon-button"
                aria-label="Close save view"
                onClick={() => setSaveOpen(false)}
              >
                <X size={18} />
              </button>
            </header>
            <p>
              The exact query, selected places, page, and evidence revision will
              be retained in your notebook.
            </p>
            <Field label="View name">
              <input
                autoFocus
                value={saveTitle}
                onChange={(e) => setSaveTitle(e.target.value)}
                placeholder={`${stateName(query.state)} · ${active.name}`}
              />
            </Field>
            <Notice>
              Revision {revision} · {human(query.metric)} ·{" "}
              {human(query.time_basis)} history
            </Notice>
            <footer>
              <button
                className="button secondary"
                onClick={() => setSaveOpen(false)}
              >
                Cancel
              </button>
              <button
                className="button primary"
                onClick={saveView}
                disabled={saving}
              >
                <Save size={14} />
                {saving ? "Saving…" : "Save exact view"}
              </button>
            </footer>
          </section>
        </div>
      )}
    </>
  );
}
