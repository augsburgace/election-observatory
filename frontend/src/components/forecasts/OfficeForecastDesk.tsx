import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  Bookmark,
  Download,
  FileText,
  Search,
  Vote,
} from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  ReferenceLine,
} from "recharts";
import type { AppContext, NationalRow } from "../../types";
import type { EVCall } from "../../earlyVoteApi";
import { marginCallLabel } from "../../earlyVoteApi";
import { api, downloadData } from "../../api";
import {
  officeDesk,
  officeLabel,
  type OfficeRace,
  type ResearchOffice,
} from "../../officeApi";
import { useViewOption, currentLayout } from "../../viewState";
import { Badge, Empty, Loading, Notice, Panel, Select } from "../ui";
import { NationalMap } from "../Maps";
import { ForecastHistory } from "./ForecastHistory";
import { fmt, human, partyColor, stateName } from "../../utils";
import "./officeForecasts.css";

const signedColor = (value: number | null) =>
  value == null
    ? "var(--muted)"
    : value > 0
      ? "var(--red)"
      : value < 0
        ? "var(--blue)"
        : "var(--violet)";
export function OfficeResultHistory({ race }: { race: OfficeRace }) {
  return (
    <Panel
      title="What happened in this office?"
      subtitle={
        race.office === "US HOUSE"
          ? "Each bar is an actual result in that year’s district boundaries. Matching numbers do not establish matching geography."
          : "Actual governor candidate-vote margins. Presidential and midterm environments are identified separately."
      }
    >
      {race.history.length ? (
        <>
          <div
            className="office-result-chart"
            role="img"
            aria-label="Historical Republican minus Democratic margins; blue favors Democrats and red favors Republicans"
          >
            <ResponsiveContainer width="100%" height={250}>
              <BarChart
                data={race.history}
                margin={{ left: 4, right: 18, top: 15, bottom: 8 }}
              >
                <CartesianGrid vertical={false} stroke="var(--border)" />
                <XAxis dataKey="year" tick={{ fill: "var(--muted)" }} />
                <YAxis unit=" pp" tick={{ fill: "var(--muted)" }} />
                <ReferenceLine y={0} stroke="var(--text)" />
                <Tooltip
                  formatter={(v) => marginCallLabel(Number(v))}
                  contentStyle={{
                    background: "var(--popover)",
                    color: "var(--text)",
                    border: "1px solid var(--border)",
                  }}
                />
                <Bar
                  dataKey="margin_pp"
                  name="Actual R−D margin"
                  radius={[4, 4, 0, 0]}
                >
                  {race.history.map((r) => (
                    <Cell key={r.contest_id} fill={signedColor(r.margin_pp)} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Election</th>
                  <th>Environment</th>
                  <th>Actual R−D margin</th>
                  <th>Candidate votes</th>
                  <th>Geography / round</th>
                </tr>
              </thead>
              <tbody>
                {race.history
                  .slice()
                  .reverse()
                  .map((r) => (
                    <tr key={r.contest_id}>
                      <th>{r.year}</th>
                      <td>
                        {r.year % 4 === 0
                          ? "Presidential"
                          : r.year % 2 === 0
                            ? "Midterm"
                            : "Off-year"}
                      </td>
                      <td
                        style={{
                          color: signedColor(r.margin_pp),
                          fontWeight: 750,
                        }}
                      >
                        {r.margin_pp == null
                          ? "Comparison unavailable"
                          : marginCallLabel(r.margin_pp)}
                      </td>
                      <td>{fmt(r.total_votes)}</td>
                      <td>
                        {r.boundary_vintage} · {human(r.round)}
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
          <p className="office-help">
            What this shows: actual candidate votes, including third-party
            options in the denominator. A missing bar can mean an uncontested
            race, independent winner, suppressed values or an unresolved
            ranked-choice round. It does not mean a tie. R +3 means a Republican
            lead of 3 percentage points.
          </p>
        </>
      ) : (
        <Empty title="Historical returns are not loaded for this race">
          Open Sources to inspect coverage. Current participation remains
          available below where supported.
        </Empty>
      )}
    </Panel>
  );
}
export default function OfficeForecastDesk(
  ctx: AppContext & { office: Exclude<ResearchOffice, "US SENATE"> },
) {
  const { query, workspace, office } = ctx,
    revision = query.revision ?? workspace.revision;
  const [active, setActive] = useViewOption<string>("forecast_race", "");
  const [scope, setScope] = useState("state"),
    [search, setSearch] = useState("");
  const [includePolls, setPolls] = useViewOption<string>(
      "include_polls",
      "false",
    ),
    [includeMarkets, setMarkets] = useViewOption<string>(
      "include_markets",
      "false",
    );
  const result = useQuery({
    queryKey: ["office-desk", office, query.cycle, revision, query.as_of],
    queryFn: ({ signal }) =>
      officeDesk(
        {
          office,
          cycle: query.cycle,
          revision,
          as_of: query.as_of || undefined,
        },
        signal,
      ),
    staleTime: Infinity,
  });
  const data = result.data,
    stateRaces = data?.calls.filter((r) => r.state === query.state) || [],
    selected = stateRaces.find((r) => r.id === active) || stateRaces[0];
  const rows = useMemo(
    () =>
      (data?.calls || []).filter(
        (r) =>
          (scope !== "state" || r.state === query.state) &&
          `${r.name} ${r.state} ${r.id}`
            .toLowerCase()
            .includes(search.toLowerCase()),
      ),
    [data, scope, query.state, search],
  );
  const mapRows: NationalRow[] = useMemo(
    () =>
      Object.entries(
        Object.fromEntries(
          (data?.calls || []).map((r) => [r.state, r.state_name]),
        ),
      ).map(([state, name]) => {
        const races = data!.calls.filter((r) => r.state === state),
          count = races.filter((r) => r.latest_result).length;
        return {
          code: state,
          name,
          fips: "",
          watchlist: races.some((r) => r.watchlist),
          value: count || null,
          latest_date: null,
          source_count: count,
          poll_count: 0,
          coverage_status: count
            ? "Historical returns loaded"
            : "No loaded returns",
          metric: "Races with archived results",
        };
      }),
    [data],
  );
  const participation = {
    state: query.state,
    evidence: {
      early_vote: {
        metric: query.metric,
        mode: query.mode,
      } as EVCall["evidence"]["early_vote"],
    },
  };
  function openRace(r: OfficeRace) {
    setActive(r.id);
    if (query.state !== r.state)
      ctx.setQuery({ state: r.state, geography_ids: [] });
  }
  function historicalHref(r: OfficeRace) {
    const p = new URLSearchParams(location.search);
    p.set("page", "atlas");
    p.set("ui_result_office", office);
    p.set("ui_question", "historical");
    if (r.latest_result) {
      p.set("ui_result_year", String(r.latest_result.year));
      p.set("ui_result_contest", r.latest_result.contest_id);
      p.set("ui_result_grain", r.latest_result.geography_level);
    }
    return "?" + p;
  }
  function reportHref() {
    const p = new URLSearchParams(location.search);
    p.set("page", "reports");
    p.set("ui_report_template", "office");
    p.set("ui_result_office", office);
    p.set("revision", String(data?.revision ?? revision));
    if (selected) p.set("ui_forecast_race", selected.id);
    return "?" + p;
  }
  async function save() {
    if (!selected || !data) return;
    try {
      await api.saveResearch({
        kind: "view",
        title: `${selected.name} · office evidence r${revision}`,
        view: {
          page: "forecasts",
          layout: currentLayout(),
          query: { ...query, revision },
          office,
          race_id: selected.id,
          office_evidence: selected,
        },
      });
      ctx.notify(
        "Office investigation saved with its revision and exact race.",
      );
    } catch (error) {
      ctx.notify((error as Error).message);
    }
  }
  if (result.isPending)
    return (
      <Loading
        label={`Opening ${officeLabel(office)} races and their original result history…`}
      />
    );
  if (result.isError)
    return <Notice tone="warning">{result.error.message}</Notice>;
  return (
    <div className="office-desk">
      <div className="page-intro">
        <div>
          <span className="call-eyebrow">
            {query.cycle} · {officeLabel(office)} · evidence first
          </span>
          <h2>
            {office === "US HOUSE"
              ? "Every district. Its own story."
              : "Governor races, state by state."}
          </h2>
          <p>
            Follow the race, inspect its history, and understand what the
            incoming early vote can support.
          </p>
        </div>
        <Badge tone="violet">Evidence r{data!.revision}</Badge>
      </div>
      <div className="office-scope-strip">
        <span>
          <Vote size={18} />
          <b>{data!.coverage.scheduled_races}</b> scheduled races
        </span>
        <span>
          <b>{data!.coverage.states}</b> states
        </span>
        <span>
          <b>{data!.coverage.races_with_history}</b> with archived returns
        </span>
        <span>
          Cutoff <b>{data!.as_of.slice(0, 10)}</b>
        </span>
      </div>
      {stateRaces.length > 0 && (
        <div className="office-place-picker">
          <label htmlFor="office-race">
            Choose a {office === "US HOUSE" ? "district" : "race"} in{" "}
            {stateName(query.state)}
          </label>
          <Select
            label="Current office race"
            value={selected?.id || ""}
            onChange={(id) => setActive(id)}
            options={stateRaces.map((r) => ({ value: r.id, label: r.name }))}
          />
        </div>
      )}
      {selected ? (
        <>
          <section className="office-story">
            <span className="call-eyebrow">
              THE RACE · {human(selected.election_system)}
            </span>
            <h3>{selected.name}</h3>
            <p>{selected.finding}</p>
            <div className="office-conclusion">
              <strong>EV direction not established</strong>
              <span>
                Current participation is measured separately. This office has
                not passed a same-stage EV forecast backtest.
              </span>
            </div>
            {selected.possible_runoff_date && (
              <p>
                November 3 is the open primary. A final runoff may be required
                on {selected.possible_runoff_date}.
              </p>
            )}
            <div className="office-actions">
              <button className="button secondary small" onClick={save}>
                <Bookmark size={15} /> Save investigation
              </button>
              <a className="button secondary small" href={reportHref()}>
                <FileText size={15} /> Build this race report
              </a>
              <button
                className="button secondary small"
                onClick={() =>
                  downloadData(
                    {
                      revision,
                      as_of: data!.as_of,
                      office,
                      race: selected,
                      sources: data!.sources,
                      registry_sources: data!.registry_sources,
                    },
                    `${selected.id}-r${revision}.json`,
                  )
                }
              >
                <Download size={15} /> Export race evidence
              </button>
            </div>
          </section>
          <div className="office-main-grid">
            <OfficeResultHistory race={selected} />
            <Panel
              title={
                selected.latest_result
                  ? `${selected.latest_result.year} · actual candidate shares`
                  : "Candidate results"
              }
              subtitle="Historical candidates are labeled by election year. They are not assumed to be today’s nominees."
            >
              {selected.latest_result ? (
                <>
                  <div className="office-option-bars">
                    {selected.latest_result.options.map((o) => (
                      <div key={o.id}>
                        <div>
                          <b>{o.name}</b>
                          <span>
                            {o.party || "Unclassified"} ·{" "}
                            {o.share_pct == null
                              ? "Not reported"
                              : o.share_pct.toFixed(1) + "%"}
                          </span>
                        </div>
                        <div className="office-option-track">
                          <i
                            style={{
                              width: `${o.share_pct ?? 0}%`,
                              background: partyColor(o.party || ""),
                            }}
                          />
                        </div>
                        <small>{fmt(o.votes)} candidate votes</small>
                      </div>
                    ))}
                  </div>
                  <a className="text-button" href={historicalHref(selected)}>
                    Explore original contest and geography{" "}
                    <ArrowRight size={14} />
                  </a>
                </>
              ) : (
                <p>No candidate return is loaded at this pinned revision.</p>
              )}
              <p className="office-help">
                Source: archived final returns listed in the evidence appendix.
                Shares use all published candidate votes. These values are not
                an early-voter preference estimate.
              </p>
            </Panel>
          </div>
          <Panel
            title="How to interpret the current early vote"
            subtitle={`${stateName(query.state)} participation · ${workspace.summary?.metric_label || human(query.metric)} · ${human(query.mode)}`}
          >
            <div className="office-ev-context">
              <strong>{fmt(workspace.summary?.total)}</strong>
              <div>
                <b>
                  {query.geography_ids.length
                    ? "Selected participation areas"
                    : "State participation evidence"}
                </b>
                <span>
                  Source date{" "}
                  {String(workspace.summary?.latest_date || "unavailable")} ·{" "}
                  {query.time_basis} chronology
                </span>
              </div>
            </div>
            <p>
              {office === "US HOUSE"
                ? "This participation measure is not a district count. Counties can overlap several districts; totals are not divided among seats. A House forecast needs verified district-level EV or precinct assignments, matching historical boundaries and held-out tests."
                : "Governor and Senate voters can split their tickets. The same statewide turnout can accompany different office results; a Senate margin or coefficient cannot stand in for a governor model."}
            </p>
            <div className="office-validation-grid">
              <div>
                <b>1 · Match the electorate</b>
                <span>
                  {office === "US HOUSE"
                    ? "Verify the actual district map and precinct assignments."
                    : "Use governor results, not a different office’s returns."}
                </span>
              </div>
              <div>
                <b>2 · Match the voting stage</b>
                <span>
                  Compare midterms with midterms, the same method and reporting
                  status, and equivalent voting opportunities.
                </span>
              </div>
              <div>
                <b>3 · Test before making a call</b>
                <span>
                  Validate on earlier elections. Current party registration and
                  geographic mix do not reveal candidate votes.
                </span>
              </div>
            </div>
          </Panel>
          <ForecastHistory
            key={query.state + office}
            ctx={ctx}
            call={participation}
            revision={revision}
            asOf={data!.as_of}
          />
          {data!.validation && (
            <Panel
              title="How well does governor history predict the next result?"
              subtitle="A separate governor-only baseline test. These scores do not validate an early-vote forecast."
            >
              <div className="office-ev-context">
                <strong>
                  {fmt(data!.validation.metrics.margin_mae_pp, 1)} pp
                </strong>
                <div>
                  <b>Average absolute historical-reference error</b>
                  <span>
                    {data!.validation.metrics.cases} retrospective tests across
                    2018, 2020, 2022 and 2024 where earlier inputs exist
                  </span>
                </div>
              </div>
              <p>{data!.validation.methodology}</p>
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>{stateName(query.state)} test</th>
                      <th>Historical baseline R−D</th>
                      <th>Actual result R−D</th>
                      <th>Error</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data!.validation.cases
                      .filter((r) => r.state === query.state)
                      .map((r, i) => (
                        <tr key={i}>
                          <th>{r.year}</th>
                          <td>{marginCallLabel(r.predicted_margin_pp)}</td>
                          <td
                            style={{ color: signedColor(r.actual_margin_pp) }}
                          >
                            {marginCallLabel(r.actual_margin_pp)}
                          </td>
                          <td>{Math.abs(r.error_pp).toFixed(1)} pp</td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
              <p className="office-help">
                Lower error is better. A 10-point error can change which party
                leads. {data!.validation.timestamp_limitations} Candidate
                changes, split tickets and state conditions remain unmodeled.
              </p>
            </Panel>
          )}
          <Panel
            title="Outside evidence · optional cross-checks"
            subtitle="An office and district must match before a survey or market can inform this investigation."
          >
            <div className="office-toggles">
              <label>
                <input
                  type="checkbox"
                  checked={includePolls === "true"}
                  onChange={(e) => setPolls(String(e.target.checked))}
                />{" "}
                Include office-matched polling
              </label>
              <label>
                <input
                  type="checkbox"
                  checked={includeMarkets === "true"}
                  onChange={(e) => setMarkets(String(e.target.checked))}
                />{" "}
                Include office-matched betting markets
              </label>
            </div>
            <p>
              {includePolls === "true" || includeMarkets === "true"
                ? "No verified office-matched outside-evidence connector is installed for this race. Senate polls and market contracts are excluded. These switches do not create or alter a race call."
                : "EV-only research is selected. Outside surveys and market prices are excluded from the explanation."}
            </p>
            <Notice>
              The reference remains historical context.{" "}
              {selected.validation.reason}
            </Notice>
          </Panel>
          <Panel title="Evidence and the remaining checks">
            <details>
              <summary>Read the scope and limitations</summary>
              <ul>
                {selected.warnings.map((w) => (
                  <li key={w}>{w}</li>
                ))}
              </ul>
            </details>
            <p>{data!.chronology_note}</p>
            <p>{data!.scope_note}</p>
            <details>
              <summary>Original source records and registry references</summary>
              <ul>
                {data!.sources
                  .filter((s) =>
                    selected.history.some((h) =>
                      h.source_refs.some(
                        (ref) => ref.snapshot_id === s.snapshot_id,
                      ),
                    ),
                  )
                  .map((s, i) => (
                    <li key={i}>
                      <a
                        href={String(s.url || s.source_url)}
                        target="_blank"
                        rel="noreferrer"
                      >
                        {String(s.source_id || "Archived results")}
                      </a>{" "}
                      · snapshot {String(s.snapshot_id)} · SHA-256{" "}
                      {String(s.sha256 || s.source_sha256 || "see archive")}
                    </li>
                  ))}
                {data!.registry_sources.map((s) => (
                  <li key={s.url}>
                    <a href={s.url} target="_blank" rel="noreferrer">
                      {s.title}
                    </a>
                  </li>
                ))}
              </ul>
            </details>
          </Panel>
        </>
      ) : (
        <Empty
          title={`No scheduled ${officeLabel(office)} race in ${stateName(query.state)} in this registry`}
        >
          Choose a race on the nationwide desk below. Your state and pinned
          evidence selection are preserved.
        </Empty>
      )}
      <Panel
        title={`The nationwide ${officeLabel(office)} research desk`}
        subtitle="Map colors show archived-data coverage. Blue/red result labels in the table describe the stated historical election year; they are not forecasts."
      >
        {typeof window !== "undefined" && (
          <NationalMap
            rows={mapRows}
            selected={query.state}
            onSelect={(state) => ctx.setQuery({ state, geography_ids: [] })}
            layer="coverage"
            missingLabel="No archived result for a scheduled race"
          />
        )}
        <div className="office-board-toolbar">
          <Select
            label="Race table scope"
            value={scope}
            onChange={setScope}
            options={[
              { value: "state", label: `${stateName(query.state)} races` },
              { value: "all", label: "All scheduled races" },
            ]}
          />
          <label>
            <Search size={16} />
            <input
              aria-label="Search House or governor races"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Find a state or district…"
            />
          </label>
          <span>{rows.length} races</span>
        </div>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Race</th>
                <th>Latest archived result</th>
                <th>Actual R−D margin</th>
                <th>Historical range</th>
                <th>EV forecast</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr
                  key={r.id}
                  className={r.id === selected?.id ? "selected" : ""}
                >
                  <th>
                    <button className="text-button" onClick={() => openRace(r)}>
                      {r.name}
                      <ArrowRight size={13} />
                    </button>
                  </th>
                  <td>{r.latest_result?.year ?? "Not loaded"}</td>
                  <td
                    style={{
                      color: signedColor(r.latest_result?.margin_pp ?? null),
                      fontWeight: 750,
                    }}
                  >
                    {r.latest_result?.margin_pp == null
                      ? "Unavailable"
                      : marginCallLabel(r.latest_result.margin_pp)}
                  </td>
                  <td>{r.history_range.join("–") || "Not loaded"}</td>
                  <td>Not validated</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  );
}
