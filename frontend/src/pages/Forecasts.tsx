import { lazy, memo, Suspense, useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  Bookmark,
  Download,
  FlaskConical,
  Info,
  TrendingUp,
  Vote,
} from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { AppContext } from "../types";
import { api, downloadData } from "../api";
import { earlyVoteCalls, marginCallLabel, type EVCall } from "../earlyVoteApi";
import {
  Badge,
  Empty,
  Loading,
  Notice,
  Panel,
  Segmented,
  Select,
} from "../components/ui";
import { forecastChartRecord } from "../forecastResearchMath";
import { ResearchGuide } from "../components/ResearchGuide";
import { COLORS, fmt, human, partyColor, stateName } from "../utils";
import { focusGeography } from "../interaction";
import { currentLayout, useViewOption } from "../viewState";
import {
  ForecastGeography,
  NationalForecastMap,
} from "../components/forecasts/ForecastGeography";
import {
  ForecastConfidence,
  ForecastSensitivity,
} from "../components/forecasts/ForecastInterpretation";
import { ForecastHistory } from "../components/forecasts/ForecastHistory";
import { ForecastBacktesting } from "../components/forecasts/ForecastBacktesting";
import "../researchCalls.css";
import "../forecastsExpansion.css";
import "../forecastBriefing.css";
import { ForecastBriefing } from "../components/forecasts/ForecastBriefing";
import { ForecastFeatureTests } from "../components/forecasts/ForecastFeatureTests";
import type { ResearchOffice } from "../officeApi";
import "../components/forecasts/officeForecasts.css";
const OfficeForecastDesk = lazy(
  () => import("../components/forecasts/OfficeForecastDesk"),
);
const ValidatedForecast = lazy(() => import("../components/ValidatedForecast"));
const MemoCallEvidence = memo(CallEvidence),
  MemoCallValidation = memo(CallValidation);

const callColor = (value: number | null | undefined) =>
  value == null
    ? "var(--muted)"
    : value > 0
      ? "var(--red)"
      : value < 0
        ? "var(--blue)"
        : "var(--violet)";
const statusLabel = (value: string) =>
  value === "ev_informed"
    ? "Early-vote research call"
    : value === "reference_only"
      ? "History-only reference"
      : "Insufficient evidence";
function MarginRange({
  call,
  large = false,
}: {
  call: EVCall["call"];
  large?: boolean;
}) {
  if (call.margin_pp == null)
    return (
      <p className="call-range-explanation">
        No D/R point or sensitivity range is published for this electoral
        configuration and evidence coverage.
      </p>
    );
  const extent = Math.min(
    100,
    Math.max(
      10,
      Math.ceil(
        Math.max(
          Math.abs(call.margin_pp),
          Math.abs(call.range_low_pp ?? 0),
          Math.abs(call.range_high_pp ?? 0),
        ) / 5,
      ) * 5,
    ),
  );
  const position = (n: number) =>
    Math.max(0, Math.min(100, ((n + extent) / (2 * extent)) * 100));
  return (
    <div className={`call-range ${large ? "large" : ""}`}>
      {large && (
        <div className="call-range-axis">
          <span>Democratic advantage · {extent} points</span>
          <span>Even</span>
          <span>Republican advantage · {extent} points</span>
        </div>
      )}
      <div
        className="call-range-track"
        role="img"
        aria-label={`${marginCallLabel(call.margin_pp)}; assumption range ${marginCallLabel(call.range_low_pp)} to ${marginCallLabel(call.range_high_pp)}`}
      >
        <i className="call-range-zero" />
        {call.range_low_pp != null && call.range_high_pp != null && (
          <span
            className="call-range-interval"
            style={{
              left: `${position(call.range_low_pp)}%`,
              width: `${Math.max(0.5, position(call.range_high_pp) - position(call.range_low_pp))}%`,
              background: callColor(call.margin_pp),
            }}
          />
        )}
        {call.margin_pp != null && (
          <b
            style={{
              left: `${position(call.margin_pp)}%`,
              background: callColor(call.margin_pp),
            }}
          />
        )}
      </div>
      <div className="call-range-labels">
        <span>
          {call.range_low_pp == null
            ? "Unavailable"
            : marginCallLabel(call.range_low_pp)}
        </span>
        <span>Unvalidated sensitivity range</span>
        <span>
          {call.range_high_pp == null
            ? "Unavailable"
            : marginCallLabel(call.range_high_pp)}
        </span>
      </div>
    </div>
  );
}
export default function Forecasts(ctx: AppContext & { embedded?: boolean }) {
  const [storedOffice, setOffice] = useViewOption<string>(
    "forecast_office",
    "US SENATE",
  );
  const office: ResearchOffice =
    storedOffice === "US HOUSE" || storedOffice === "GOVERNOR"
      ? storedOffice
      : "US SENATE";
  return (
    <>
      <div className="forecast-office-picker">
        <span>Research an office</span>
        <Segmented
          label="Forecast office"
          value={office}
          onChange={setOffice}
          items={[
            { id: "US SENATE", label: "U.S. Senate" },
            { id: "US HOUSE", label: "U.S. House" },
            { id: "GOVERNOR", label: "Governor" },
          ]}
        />
      </div>
      {office === "US SENATE" ? (
        <SenateForecasts {...ctx} />
      ) : (
        <Suspense fallback={<Loading label="Opening office research…" />}>
          <OfficeForecastDesk {...ctx} office={office} />
        </Suspense>
      )}
    </>
  );
}
function SenateForecasts(ctx: AppContext & { embedded?: boolean }) {
  const { query, workspace, embedded } = ctx,
    revision = query.revision ?? workspace.revision;
  const calls = useQuery({
    staleTime: Infinity,
    gcTime: 60_000,
    queryKey: [
      "early-vote-calls",
      query.state,
      query.cycle,
      revision,
      query.as_of,
    ],
    queryFn: ({ signal }) =>
      earlyVoteCalls(
        {
          state: query.state,
          cycle: query.cycle,
          revision,
          as_of: query.as_of || undefined,
        },
        signal,
      ),
  });
  const [filter, setFilter] = useState("watchlist"),
    [search, setSearch] = useState(""),
    [sort, setSort] = useState("competitiveness"),
    [saved, setSaved] = useState(false);
  const [validationOpen, setValidationOpen] = useState(false);
  const [activeRace, setActiveRace] = useViewOption<string>(
    "forecast_race",
    "",
  );
  const data = calls.data,
    selected =
      data?.calls.find(
        (call) => call.race_id === activeRace && call.state === query.state,
      ) || data?.selected;
  useEffect(() => setSaved(false), [selected?.race_id, data?.revision]);
  const reportHref = () => {
    const params = new URLSearchParams(location.search);
    params.set("page", "reports");
    params.set("ui_report_template", "ev_senate");
    params.set("ui_question", "forecasts");
    params.set("revision", String(data?.revision ?? revision));
    if (data?.as_of) params.set("as_of", data.as_of);
    params.delete("research_id");
    return `?${params}`;
  };
  const rows = useMemo(
    () =>
      (data?.calls || [])
        .filter(
          (row) =>
            (filter !== "watchlist" || row.watchlist) &&
            (filter !== "ev_informed" || row.call.status === "ev_informed") &&
            (filter !== "reference_only" ||
              row.call.status === "reference_only") &&
            `${row.state_name} ${row.state} ${row.race_id}`
              .toLowerCase()
              .includes(search.toLowerCase()),
        )
        .sort((a, b) =>
          sort === "state"
            ? a.state_name.localeCompare(b.state_name)
            : sort === "margin"
              ? (b.call.margin_pp ?? -200) - (a.call.margin_pp ?? -200)
              : Math.abs(a.call.margin_pp ?? 200) -
                Math.abs(b.call.margin_pp ?? 200),
        ),
    [data, filter, search, sort],
  );
  async function saveCall() {
    if (!selected || !data) return;
    try {
      await api.saveResearch({
        kind: "view",
        title: `${selected.state_name} ${query.cycle} · ${marginCallLabel(selected.call.margin_pp)} · r${data.revision}`,
        view: {
          page: "forecasts",
          layout: currentLayout(),
          query: { ...query, revision: data.revision },
          model_version: data.model_version,
          as_of: data.as_of,
          research_call: selected,
        },
      });
      setSaved(true);
      ctx.notify(
        "Research call saved with its evidence revision, assumptions, and input manifest.",
      );
    } catch (error) {
      ctx.notify(
        error instanceof Error ? error.message : "The call could not be saved.",
      );
    }
  }
  return (
    <div className="early-vote-research-calls">
      {!embedded && (
        <div className="page-intro">
          <div>
            <span className="call-eyebrow">
              {query.cycle} U.S. Senate · evidence first
            </span>
            <h2>Early voting, interpreted.</h2>
            <p>
              A clear call, the voting patterns behind it, and the evidence that
              could change our view.
            </p>
          </div>
          <Badge tone="violet">
            <FlaskConical size={13} />
            Research estimates
          </Badge>
        </div>
      )}
      {query.time_basis !== "reported" && (
        <Notice>
          Model evidence is <b>as reported</b>. This research model uses its own
          disclosed reported-evidence scope; your{" "}
          {human(query.time_basis).toLowerCase()} chronology remains selected
          for other research views.
        </Notice>
      )}
      {selected &&
        (query.metric !== selected.evidence.early_vote.metric ||
          query.mode !== selected.evidence.early_vote.mode) && (
          <Notice>
            <b>
              Forecast input scope:{" "}
              {selected.evidence.early_vote.metric_label ||
                human(selected.evidence.early_vote.metric)}{" "}
              · {human(selected.evidence.early_vote.mode)} · as reported.
            </b>{" "}
            Your saved research filter remains {human(query.metric)} ·{" "}
            {human(query.mode)}. This versioned model selects its disclosed
            eligible source/metric; the same-stage workbench below has separate
            visible metric and method controls.
          </Notice>
        )}
      {calls.isPending ? (
        <Loading label="Reading early-vote evidence and building reproducible Senate research calls…" />
      ) : calls.isError ? (
        <Notice tone="warning">
          {calls.error.message}. Historical research and source evidence remain
          available elsewhere in the atlas.
        </Notice>
      ) : (
        <>
          <nav
            className="forecast-section-nav"
            aria-label="Forecast research sections"
          >
            <a href="#forecast-briefing">The story</a>
            <a href="#forecast-call">The call</a>
            <a href="#forecast-reasoning">Why this direction</a>
            <a href="#forecast-confidence">Confidence</a>
            <a href="#forecast-model-audit">Call audit</a>
            <a href="#forecast-history">Same-stage & turnout</a>
            <a href="#forecast-geography">Geographic signal</a>
            <a href="#forecast-sensitivity">Sensitivity</a>
            <a href="#forecast-validation">Historical tests</a>
            <a href="#forecast-feature-tests">Do more inputs help?</a>
            <a href="#forecast-nationwide">All Senate races</a>
          </nav>
          {selected ? (
            <>
              <ForecastBriefing
                call={selected}
                cycle={query.cycle}
                revision={data?.revision ?? revision}
                asOf={data?.as_of || query.as_of}
              />
              <section
                id="forecast-call"
                className="call-state-hero forecast-anchor"
                style={{ borderTopColor: callColor(selected.call.margin_pp) }}
              >
                <div className="call-state-title">
                  <div>
                    <span className="call-eyebrow">
                      {selected.state_name} · {selected.office || "U.S. Senate"}
                    </span>
                    <h3>{statusLabel(selected.call.status)}</h3>
                    <p>
                      {selected.call.margin_pp == null
                        ? "The counting rules or available inputs do not support a defensible D/R margin."
                        : `${selected.call.direction} direction under this configuration`}
                    </p>
                  </div>
                  <strong
                    className={`call-point-estimate ${selected.call.margin_pp == null ? "unavailable" : ""}`}
                    style={{ color: callColor(selected.call.margin_pp) }}
                  >
                    {marginCallLabel(selected.call.margin_pp)}
                  </strong>
                </div>
                <MarginRange call={selected.call} large />
                {selected.call.margin_pp != null && (
                  <p className="call-range-explanation">
                    R +3 means Republicans ahead by 3 percentage points; D +3
                    means Democrats ahead by 3 points. The shaded range shows
                    how much the estimate changes under different assumptions.
                    It does not have a verified 80% or 95% chance of containing
                    the eventual result.
                  </p>
                )}
                {selected.call.candidate_verification && (
                  <p className="call-range-explanation">
                    {selected.call.candidate_verification}. These are
                    party-level research estimates, without verified current
                    candidate adjustments.
                  </p>
                )}
                <div className="call-hero-actions">
                  <button className="button small secondary" onClick={saveCall}>
                    <Bookmark size={14} />
                    {saved ? "Call saved" : "Save this research call"}
                  </button>
                  {selected.race_id === data?.selected?.race_id ? (
                    <a
                      className="button small secondary"
                      href={reportHref()}
                      onClick={(event) => {
                        event.currentTarget.href = reportHref();
                      }}
                    >
                      Build this Senate report
                      <ArrowRight size={13} />
                    </a>
                  ) : (
                    <span className="forecast-caption">
                      Export this exact contest’s evidence; the state-report
                      template currently selects the default Senate contest.
                    </span>
                  )}
                  <button
                    className="button small secondary"
                    onClick={() =>
                      downloadData(
                        {
                          revision: data?.revision,
                          as_of: data?.as_of,
                          model_version: data?.model_version,
                          call: selected,
                        },
                        `${selected.state}-${query.cycle}-research-call-r${data?.revision}.json`,
                      )
                    }
                  >
                    <Download size={14} />
                    Export evidence & assumptions
                  </button>
                  <button
                    className="text-button"
                    onClick={() => ctx.setPage("scenarios")}
                  >
                    Test different assumptions
                    <ArrowRight size={13} />
                  </button>
                </div>
              </section>
              <ForecastHistory
                key={selected.state}
                ctx={ctx}
                call={selected}
                revision={data?.revision ?? revision}
                asOf={data?.as_of || query.as_of}
              />
              <ForecastConfidence call={selected} />
              <ForecastGeography ctx={ctx} call={selected} />
              <section id="forecast-reasoning" className="forecast-anchor">
                <MemoCallEvidence {...ctx} call={selected} />
              </section>
              <ForecastSensitivity
                key={selected.race_id + ":" + data?.model_version}
                call={selected}
              />
            </>
          ) : (
            <Empty
              title={`${stateName(query.state)} has no selected Senate contest in this cycle`}
            >
              Use the nationwide race board below to open a scheduled contest.
              All 50 states retain historical, geographic, and
              population-context research in the atlas.
            </Empty>
          )}
          <ForecastBacktesting
            backtesting={data?.backtesting}
            state={query.state}
          />
          <ForecastFeatureTests
            state={query.state}
            cycle={query.cycle}
            revision={data?.revision ?? revision}
            asOf={data?.as_of || query.as_of}
          />
          <section id="forecast-nationwide" className="forecast-anchor">
            <div className="call-national-strip">
              <span>
                <Vote size={15} />
                <b>{data?.calls.length || 0}</b> scheduled Senate contests
              </span>
              <span>
                <b>{data?.calls.filter((c) => c.watchlist).length || 0}</b>{" "}
                watchlist races
              </span>
              <span>
                <b>
                  {data?.calls.filter((c) => c.call.status === "ev_informed")
                    .length || 0}
                </b>{" "}
                EV-informed calls
              </span>
              <span>
                Evidence r<b>{data?.revision}</b> ·{" "}
                {String(data?.as_of || "").slice(0, 10)}
              </span>
            </div>
            <NationalForecastMap
              calls={data?.calls || []}
              selected={selected}
              onSelect={(state) => ctx.setQuery({ state, geography_ids: [] })}
            />
            <Panel
              title="The nationwide Senate research desk"
              subtitle="Compare concrete calls and distinguish races whose current EV geography supports an adjustment from historical-reference-only races."
            >
              <div className="call-board-toolbar">
                <Segmented
                  label="Senate research call coverage"
                  value={filter}
                  onChange={setFilter}
                  items={[
                    { id: "watchlist", label: "Battleground watchlist" },
                    { id: "all", label: "All Senate contests" },
                    { id: "ev_informed", label: "EV-informed" },
                    { id: "reference_only", label: "Reference only" },
                  ]}
                />
                <input
                  aria-label="Search Senate research calls"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Find a state or contest…"
                />
                <Select
                  label="Sort research calls"
                  value={sort}
                  onChange={setSort}
                  options={[
                    {
                      value: "competitiveness",
                      label: "Closest provisional margin",
                    },
                    { value: "state", label: "State name" },
                    { value: "margin", label: "Republican → Democratic" },
                  ]}
                />
              </div>
              <div className="table-scroll">
                <table className="research-call-table">
                  <thead>
                    <tr>
                      <th>State / contest</th>
                      <th>Research call</th>
                      <th>What supports it</th>
                      <th>Observed participation</th>
                      <th>Evidence date</th>
                      <th>Sensitivity range</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((call) => (
                      <tr
                        key={call.race_id}
                        className={
                          call.race_id === selected?.race_id ? "selected" : ""
                        }
                      >
                        <td>
                          <button
                            className="text-button"
                            onClick={() => {
                              setActiveRace(call.race_id);
                              ctx.setQuery({
                                state: call.state,
                                geography_ids: [],
                              });
                              setSaved(false);
                            }}
                          >
                            {call.state_name}
                          </button>
                          <small>
                            {human(call.race_id)}
                            {call.watchlist ? " · watchlist" : ""}
                          </small>
                        </td>
                        <td>
                          <strong
                            className="table-margin-call"
                            style={{ color: callColor(call.call.margin_pp) }}
                          >
                            {marginCallLabel(call.call.margin_pp)}
                          </strong>
                        </td>
                        <td>
                          <Badge
                            tone={
                              call.call.status === "ev_informed"
                                ? "teal"
                                : call.call.status === "reference_only"
                                  ? "gold"
                                  : "muted"
                            }
                          >
                            {statusLabel(call.call.status)}
                          </Badge>
                          <small>
                            {call.evidence.geographic_tilt.available &&
                            call.evidence.geographic_tilt.same_stage
                              ? "Matched same-stage EV reference"
                              : call.evidence.geographic_tilt.available
                                ? "Final-result geographic reference"
                                : "No compatible EV geographic adjustment"}
                          </small>
                        </td>
                        <td>
                          {call.evidence.early_vote.total == null
                            ? "Not available"
                            : fmt(call.evidence.early_vote.total)}
                          <small>
                            {call.evidence.early_vote.metric_label ||
                              "No compatible current metric"}
                          </small>
                        </td>
                        <td>
                          {call.evidence.early_vote.date || "—"}
                          {call.evidence.early_vote.report_date_verified ===
                            false && (
                            <small>
                              Upload/source date; authority report date
                              unverified
                            </small>
                          )}
                        </td>
                        <td>
                          <MarginRange call={call.call} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {!rows.length && (
                <Empty title="No races match these filters">
                  Try all Senate contests or clear the state search.
                </Empty>
              )}
              <ResearchGuide
                what="A conditional research margin for each scheduled Senate race, with its EV evidence status and sensitivity range."
                how="A historical-reference-only call has no supported current EV adjustment. EV-informed means geographic participation contributes to an explicitly assumed adjustment; it does not establish observed candidate support. Open a state to see every component."
                source={`Local evidence revision ${data?.revision} · ${data?.model_version}`}
              />
            </Panel>
          </section>
          <MemoCallValidation validation={data?.validation || {}} />
          {data?.warnings.map((warning, i) => (
            <Notice key={i}>{warning}</Notice>
          ))}
        </>
      )}
      <details
        className="validated-model-disclosure"
        onToggle={(event) => setValidationOpen(event.currentTarget.open)}
      >
        <summary>
          <TrendingUp size={17} />
          <span>
            <b>Validated forecasts and probability publication gate</b>
            <small>
              Separate calibrated-model requirements, historical evaluation,
              electoral systems, and versioned model runs.
            </small>
          </span>
        </summary>
        {validationOpen && (
          <Suspense
            fallback={
              <Loading label="Opening calibrated-model publication requirements…" />
            }
          >
            <ValidatedForecast {...ctx} embedded />
          </Suspense>
        )}
      </details>
    </div>
  );
}

function CallEvidence(ctx: AppContext & { call: EVCall }) {
  const { call } = ctx,
    evidence = call.evidence,
    tilt = evidence.geographic_tilt,
    historical = evidence.historical_reference,
    early = evidence.early_vote;
  const contributions = useMemo(
    () =>
      [...(tilt.rows || [])]
        .sort(
          (a, b) => Math.abs(b.contribution_pp) - Math.abs(a.contribution_pp),
        )
        .slice(0, 14),
    [tilt.rows],
  );
  const sourceNames = useMemo(
    () =>
      new Map(
        (ctx.bootstrap.sources || []).map((source) => [source.id, source.name]),
      ),
    [ctx.bootstrap.sources],
  );
  const dimensions = [
    ...new Set((evidence.composition || []).map((r) => r.dimension)),
  ];
  const [storedDimension, setDimension] = useState("");
  const dimension = dimensions.includes(storedDimension)
    ? storedDimension
    : dimensions.find((value) => /party|registration|primary/i.test(value)) ||
      dimensions[0];
  const composition = (evidence.composition || []).filter(
      (r) => r.dimension === dimension,
    ),
    maxCategory = Math.max(...composition.map((r) => r.value), 1);
  return (
    <>
      <div className="call-evidence-grid">
        <Panel
          title="How we get from the evidence to this call"
          subtitle="See the historical starting point, the early-vote adjustment, and the resulting direction."
        >
          <div className="call-component-flow">
            <div>
              <span>Historical Senate reference</span>
              <b style={{ color: callColor(historical.margin_pp) }}>
                {marginCallLabel(historical.margin_pp)}
              </b>
              <small>{historical.description}</small>
            </div>
            <ArrowRight size={19} />
            <div>
              <span>Assumed EV adjustment</span>
              <b style={{ color: callColor(tilt.adjustment_pp) }}>
                {tilt.adjustment_pp == null
                  ? "Not available"
                  : tilt.adjustment_pp === 0
                    ? "No change"
                    : `${fmt(Math.abs(tilt.adjustment_pp), 1)} points toward ${tilt.adjustment_pp > 0 ? "Republicans" : "Democrats"}`}
              </b>
              <small>
                {tilt.available
                  ? `${fmt(tilt.coefficient * 100, 0)}% of the measured geographic shift is applied. This weight is an assumption.`
                  : "No supported geographic EV adjustment"}
              </small>
            </div>
            <ArrowRight size={19} />
            <div>
              <span>Provisional call</span>
              <b style={{ color: callColor(call.call.margin_pp) }}>
                {marginCallLabel(call.call.margin_pp)}
              </b>
              <small>{statusLabel(call.call.status)}</small>
            </div>
          </div>
          {call.explanation.map((text, i) => (
            <p className="call-explanation" key={i}>
              <Info size={15} />
              <span>{text}</span>
            </p>
          ))}
        </Panel>
        <Panel
          title="Current early-vote evidence"
          subtitle="The precise metric, date, method, and geographic scope behind this investigation."
        >
          <div className="call-ev-total">
            <b>{early.total == null ? "Unavailable" : fmt(early.total)}</b>
            <span>
              {early.metric_label ||
                "No compatible current participation record"}
            </span>
            <small>
              {early.metric ? human(early.metric) : "No observed metric"} ·{" "}
              {early.unit ? `unit: ${human(early.unit)}` : "unit unavailable"}
            </small>
          </div>
          <dl className="call-facts">
            <div>
              <dt>
                {early.report_date_verified === false
                  ? "Source / upload date"
                  : "Report date"}
              </dt>
              <dd>{early.date || "Unavailable"}</dd>
            </div>
            <div>
              <dt>Voting method</dt>
              <dd>{human(early.mode || "unavailable")}</dd>
            </div>
            <div>
              <dt>Comparable areas</dt>
              <dd>{tilt.matched_areas || 0}</dd>
            </div>
            <div>
              <dt>Matched share of reported county activity</dt>
              <dd>
                {tilt.coverage_pct == null
                  ? "Not established"
                  : `${fmt(tilt.coverage_pct, 1)}%`}
              </dd>
            </div>
            <div>
              <dt>Matched share of statewide quantity</dt>
              <dd>
                {tilt.statewide_coverage_pct == null
                  ? "Not established"
                  : `${fmt(tilt.statewide_coverage_pct, 1)}%`}
              </dd>
            </div>
            <div>
              <dt>Geographic reference</dt>
              <dd>
                {tilt.same_stage
                  ? "Matched same-stage early voting"
                  : tilt.reference_kind === "final_candidate_vote_distribution"
                    ? `${tilt.reference_year || "Prior"} final candidate-vote distribution`
                    : "Unavailable"}
              </dd>
            </div>
            <div>
              <dt>Polling role</dt>
              <dd>
                Available for optional context · {evidence.polls?.count || 0}{" "}
                studies; excluded from the EV-only margin
              </dd>
            </div>
          </dl>
          {early.report_date_verified === false && (
            <Notice tone="warning">
              The election authority's underlying report date is unverified. The
              displayed source/upload date cannot establish the reporting stage,
              so this evidence does not adjust the point call.
            </Notice>
          )}
          {!!early.native_date_caveats?.length && (
            <details>
              <summary>Source date semantics</summary>
              {early.native_date_caveats.map((caveat, i) => (
                <p className="body-copy" key={i}>
                  {caveat}
                </p>
              ))}
            </details>
          )}
          {!tilt.same_stage && tilt.available && (
            <Notice tone="warning">
              This uses an explicitly labeled final-election geographic
              reference. It is not a same-day early-vote pace comparison.
            </Notice>
          )}
          <button className="text-button" onClick={() => ctx.setPage("states")}>
            Open full voting dossier
            <ArrowRight size={13} />
          </button>
        </Panel>
      </div>
      <div className="chart-grid">
        <Panel
          title="Which places explain the EV geographic signal?"
          subtitle="Which counties pull the geographic comparison toward Republicans or Democrats, using their historical results."
        >
          {!!contributions.length && !tilt.available && (
            <Notice tone="warning">
              Diagnostic context only: these geographic quantities are excluded
              from the point call. {tilt.description}
            </Notice>
          )}
          {contributions.length ? (
            <div className="chart" style={{ height: 420 }}>
              <ResponsiveContainer>
                <BarChart
                  data={contributions}
                  layout="vertical"
                  margin={{ right: 22, left: 8 }}
                >
                  <CartesianGrid
                    stroke="var(--chart-grid)"
                    horizontal={false}
                  />
                  <XAxis
                    type="number"
                    tick={{ fontSize: 13, fill: "var(--muted)" }}
                    tickFormatter={(v) => `${fmt(v, 1)} pp`}
                  />
                  <YAxis
                    type="category"
                    dataKey="name"
                    width={125}
                    tick={{ fontSize: 13, fill: "var(--muted)" }}
                  />
                  <ReferenceLine x={0} stroke="var(--border-strong)" />
                  <Tooltip
                    contentStyle={{
                      background: "var(--popover)",
                      border: "1px solid var(--border)",
                      color: "var(--text)",
                    }}
                    formatter={(v) => [
                      fmt(v, 3) + " pp",
                      "Geographic-context contribution",
                    ]}
                  />
                  <Bar
                    dataKey="contribution_pp"
                    maxBarSize={20}
                    onClick={(row) => {
                      const input = forecastChartRecord(row);
                      if (input && typeof input.id === "string")
                        ctx.setQuery({ geography_ids: [input.id] });
                    }}
                  >
                    {contributions.map((row) => (
                      <Cell
                        key={row.id}
                        stroke={
                          (
                            ctx.selectedGeographyIds ?? ctx.query.geography_ids
                          ).includes(row.id)
                            ? "var(--selection)"
                            : "transparent"
                        }
                        strokeWidth={2}
                        fill={
                          row.contribution_pp > 0 ? "var(--red)" : "var(--blue)"
                        }
                      />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <Empty title="A defensible geographic signal is not available">
              Compatible current geographic observations and a documented
              reference distribution are required. A statewide total or party
              registration alone does not reveal candidate votes.
            </Empty>
          )}
          <ResearchGuide
            what="Each area's contribution to the change in the geographic mix of reported participation, weighted by that area's historical election context."
            how="Positive values increase Republican geographic context; negative values increase Democratic context. These are aggregate contextual contributions, not estimates of the ballots' actual candidate choices. The coefficient converting this signal to the research call is an assumption."
            source={tilt.description}
          />
        </Panel>
        <Panel
          title="Who is participating, where directly reported?"
          subtitle="Published voter composition; resident demographics and inferred beliefs remain separate."
        >
          {composition.length ? (
            <>
              <Select
                label="Research call composition dimension"
                value={dimension}
                onChange={setDimension}
                options={dimensions.map((d) => ({ value: d, label: human(d) }))}
              />
              {/party|registration|primary/i.test(dimension) && (
                <p className="forecast-caption">
                  <b style={{ color: "var(--blue)" }}>Blue: Democratic</b> ·{" "}
                  <b style={{ color: "var(--red)" }}>Red: Republican</b>. These
                  are the source’s registration or primary-history categories,
                  not candidate votes.
                </p>
              )}
              <div className="call-composition">
                {composition
                  .sort((a, b) => b.value - a.value)
                  .map((row, i) => (
                    <div key={`${row.category}-${row.mode}`}>
                      <span>
                        {human(row.category)}
                        <small>
                          {human(row.mode)} · {row.date}
                        </small>
                      </span>
                      <i>
                        <b
                          style={{
                            width: `${(row.value / maxCategory) * 100}%`,
                            background: /unknown|other|unclassified/i.test(
                              row.category,
                            )
                              ? "var(--muted)"
                              : /party|registration|primary/i.test(dimension)
                                ? partyColor(row.category)
                                : COLORS[i % COLORS.length],
                          }}
                        />
                      </i>
                      <strong>{fmt(row.value)}</strong>
                    </div>
                  ))}
              </div>
            </>
          ) : (
            <Empty title="Compatible published composition is unavailable">
              The platform does not infer age, race, party, religion, or voting
              propensity from county results or residential population.
            </Empty>
          )}
          <Notice>
            Religion and individual voting propensity are not observed in these
            election records. Separate published marginal groups cannot
            establish joint demographic intersections or candidate support.
          </Notice>
        </Panel>
      </div>
      {!!tilt.rows?.length && (
        <Panel
          title="Geographic evidence ledger"
          subtitle="Actual place totals, reference shares, context margins, and source dates agree with the chart."
        >
          <details>
            <summary>
              Inspect all {tilt.rows.length} geographic model inputs
            </summary>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Place</th>
                    <th>Current reported quantity</th>
                    <th>Current geographic share</th>
                    <th>Reference geographic share</th>
                    <th>Historical party margin (R−D)</th>
                    <th>Context contribution</th>
                    <th>Source date</th>
                  </tr>
                </thead>
                <tbody>
                  {tilt.rows.map((row) => (
                    <tr
                      key={row.id}
                      className={
                        (
                          ctx.selectedGeographyIds ?? ctx.query.geography_ids
                        ).includes(row.id)
                          ? "selected"
                          : ""
                      }
                      onMouseEnter={() => focusGeography(row.id)}
                      onMouseLeave={() => focusGeography(null)}
                    >
                      <td>
                        <button
                          className="text-button"
                          onFocus={() => focusGeography(row.id)}
                          onBlur={() => focusGeography(null)}
                          onClick={() =>
                            ctx.setQuery({ geography_ids: [row.id] })
                          }
                        >
                          {row.name}
                        </button>
                      </td>
                      <td className="numeric">{fmt(row.early_votes)}</td>
                      <td>{fmt(row.early_share_pct, 2)}%</td>
                      <td>{fmt(row.reference_share_pct, 2)}%</td>
                      <td>{marginCallLabel(row.reference_margin_pp)}</td>
                      <td style={{ color: callColor(row.contribution_pp) }}>
                        {fmt(row.contribution_pp, 3)} pp
                      </td>
                      <td>{row.current_source_date}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        </Panel>
      )}
      <div className="chart-grid">
        <Panel
          title="Historical reference ledger"
          subtitle="Past Senate results contribute to the reference with explicitly retained weights."
        >
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Election</th>
                  <th>R−D margin</th>
                  <th>Reference weight</th>
                  <th>Candidate votes</th>
                </tr>
              </thead>
              <tbody>
                {historical.cycles.map((row) => (
                  <tr key={row.contest_id}>
                    <td>
                      {row.year}
                      <small>{row.contest_name}</small>
                    </td>
                    <td style={{ color: callColor(row.margin_pp) }}>
                      {marginCallLabel(row.margin_pp)}
                    </td>
                    <td>{fmt(row.weight, 3)}</td>
                    <td>{fmt(row.total_votes)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
        <Panel title="Assumptions, limits, and evidence lineage">
          <ul className="call-assumptions">
            {call.assumptions.map((text, i) => (
              <li key={i}>{text}</li>
            ))}
          </ul>
          {call.warnings.map((text, i) => (
            <Notice key={i} tone="warning">
              {text}
            </Notice>
          ))}
          <details>
            <summary>Complete reproducibility manifest</summary>
            <pre className="call-manifest">
              {JSON.stringify(call.manifest, null, 2)}
            </pre>
          </details>
          <div className="call-source-links">
            {call.sources.map((source, i) => (
              <a
                key={i}
                href={String(source.url || "")}
                target="_blank"
                rel="noreferrer"
              >
                {String(
                  source.name ||
                    source.title ||
                    source.producer ||
                    sourceNames.get(String(source.source_id)) ||
                    source.source_id ||
                    "Original source",
                )}{" "}
                {source.id != null ? `· snapshot ${source.id}` : ""}
              </a>
            ))}
          </div>
        </Panel>
      </div>
    </>
  );
}
function CallValidation({
  validation,
}: {
  validation: Record<string, unknown>;
}) {
  const metrics =
    validation.metrics && typeof validation.metrics === "object"
      ? (validation.metrics as Record<string, unknown>)
      : validation;
  const numbers = Object.entries(metrics).filter(
      ([, value]) => typeof value === "number",
    ),
    description = String(
      validation.description ||
        validation.methodology ||
        validation.note ||
        (validation.status ? human(String(validation.status)) : null) ||
        "Historical-reference evaluation is separate from validation of an early-vote adjustment.",
    );
  const origins = Array.isArray(validation.origins)
    ? (validation.origins as Record<string, unknown>[])
    : [];
  const metricLabels: Record<string, string> = {
    cases: "Historical test cases",
    margin_mae_pp: "Mean absolute margin error",
    margin_rmse_pp: "Root mean squared margin error",
    margin_bias_pp: "Average signed margin error",
    interval_80_coverage: "80% historical interval coverage",
    interval_95_coverage: "95% historical interval coverage",
  };
  return (
    <Panel
      title="What has actually been evaluated?"
      subtitle="Reference-only evaluation stays distinct from the EV test bench and its timestamp limitations."
    >
      <Notice tone="warning">
        <b>These diagnostics evaluate the historical reference component.</b>{" "}
        The EV test bench above separately documents early-vote adjustment
        tests, independent election coverage, and the probability publication
        gate.
      </Notice>
      <p className="body-copy">{description}</p>
      {!!numbers.length && (
        <div className="call-validation-metrics">
          {numbers.map(([key, value]) => (
            <div key={key}>
              <span>{metricLabels[key] || human(key)}</span>
              <b>
                {/coverage/.test(key)
                  ? fmt(Number(value) * 100, 1) + "%"
                  : fmt(value, /cases/.test(key) ? 0 : 2) +
                    (/_pp$/.test(key) ? " pp" : "")}
              </b>
            </div>
          ))}
        </div>
      )}
      {origins.length > 0 && (
        <>
          <div className="chart" style={{ height: 240 }}>
            <ResponsiveContainer>
              <BarChart
                data={origins}
                margin={{ left: 5, right: 18, top: 10, bottom: 12 }}
              >
                <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
                <XAxis
                  dataKey="year"
                  tick={{ fontSize: 13, fill: "var(--muted)" }}
                />
                <YAxis
                  tick={{ fontSize: 13, fill: "var(--muted)" }}
                  width={45}
                  unit=" pp"
                />
                <Tooltip
                  contentStyle={{
                    background: "var(--popover)",
                    border: "1px solid var(--border)",
                    color: "var(--text)",
                  }}
                  formatter={(value) => [
                    fmt(value, 2) + " pp",
                    "Historical-only margin MAE",
                  ]}
                />
                <Bar
                  dataKey="margin_mae_pp"
                  fill="var(--violet)"
                  maxBarSize={45}
                  radius={[4, 4, 0, 0]}
                  isAnimationActive={false}
                />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <p className="call-range-explanation">
            Rolling historical Senate reference errors by evaluation election.
            This tests the historical reference component; the early-vote
            adjustment has {String(validation.ev_backtest_cases ?? 0)} held-out
            backtest cases.
          </p>
        </>
      )}
      {validation.timestamp_limitations != null && (
        <Notice>{String(validation.timestamp_limitations)}</Notice>
      )}
      <details>
        <summary>Full validation record and coverage limitations</summary>
        <pre className="call-manifest">
          {JSON.stringify(validation, null, 2)}
        </pre>
      </details>
    </Panel>
  );
}
