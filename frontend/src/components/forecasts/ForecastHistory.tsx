import { memo, useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, CalendarDays, Download, Users } from "lucide-react";
import {
  Bar,
  BarChart,
  Cell,
  Brush,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { AppContext } from "../../types";
import {
  earlyVoteHistory,
  type EVCall,
  type EVStageHistory,
} from "../../earlyVoteApi";
import { useViewOption } from "../../viewState";
import { downloadData } from "../../api";
import { CYCLE_COLORS, MODE_COLORS, compact, fmt, human } from "../../utils";
import { Badge, Empty, Loading, Notice, Panel, Select } from "../ui";
import { ResearchGuide } from "../ResearchGuide";
const tooltip = {
  background: "var(--popover)",
  color: "var(--text)",
  border: "1px solid var(--border)",
};
const cycleColor = (cycle: number) =>
  CYCLE_COLORS[cycle] || (cycle === 2016 ? "#c16d94" : "#6c8197");
export function stageChartRows(
  data: EVStageHistory,
  alignment: string,
  includePreOpening = false,
) {
  const points = new Map<number, Record<string, number | string | null>>();
  for (const cycle of [
    { cycle: data.query.cycle, trajectory: data.current.trajectory },
    ...data.cycles,
  ]) {
    for (const point of cycle.trajectory) {
      const x =
        alignment === "days_since_opening"
          ? point.days_since_opening
          : point.days_to_election;
      if (
        x == null ||
        !Number.isFinite(x) ||
        (alignment === "days_since_opening" && x < 0 && !includePreOpening)
      )
        continue;
      const row = points.get(x) || { coordinate: x };
      row[`cycle_${cycle.cycle}`] = point.value;
      row[`date_${cycle.cycle}`] = point.date;
      points.set(x, row);
    }
  }
  return [...points.values()].sort(
    (a, b) => Number(a.coordinate) - Number(b.coordinate),
  );
}
export const ForecastHistory = memo(function ForecastHistory({
  ctx,
  call,
  revision,
  asOf,
}: {
  ctx: AppContext;
  call: EVCall;
  revision: number;
  asOf: string;
}) {
  const [alignment, setAlignment] = useViewOption<string>(
    "forecast_history_alignment",
    "days_to_election",
  );
  const [basis, setBasis] = useViewOption<string>(
    "forecast_history_basis",
    "retrospective",
  );
  const [metric, setMetric] = useViewOption<string>(
    "forecast_history_metric",
    call.evidence.early_vote.metric || "ballots_cast",
  );
  const [mode, setMode] = useViewOption<string>(
    "forecast_history_mode",
    call.evidence.early_vote.mode || "all",
  );
  const [cycleSet, setCycleSet] = useViewOption<string>(
    "forecast_history_cycles",
    "2016,2018,2020,2022,2024",
  );
  const [preOpening, setPreOpening] = useViewOption<string>(
    "forecast_history_preopening",
    "hide",
  );
  const [brushWindow, setBrushWindow] = useState<{
    startIndex: number;
    endIndex: number;
  } | null>(null);
  const chartRef = useRef<HTMLDivElement>(null);
  const [storedSelectedCycle, setSelectedCycle] = useState<number | null>(null);
  const history = useQuery({
    queryKey: [
      "ev-stage-history",
      call.state,
      ctx.query.cycle,
      revision,
      asOf,
      metric,
      mode,
      alignment,
      basis,
      cycleSet,
    ],
    queryFn: ({ signal }) =>
      earlyVoteHistory(
        {
          state: call.state,
          cycle: ctx.query.cycle,
          revision,
          as_of: asOf,
          metric,
          mode,
          alignment,
          history_basis: basis,
          baseline_cycles: cycleSet,
        },
        signal,
      ),
  });
  const data = history.data;
  const chartRows = useMemo(
    () => (data ? stageChartRows(data, alignment, preOpening === "show") : []),
    [data, alignment, preOpening],
  );
  const preOpeningCount = useMemo(
    () =>
      data && alignment === "days_since_opening"
        ? stageChartRows(data, alignment, true).filter(
            (row) => Number(row.coordinate) < 0,
          ).length
        : 0,
    [data, alignment],
  );
  const startIndex = Math.max(
    0,
    Math.min(brushWindow?.startIndex ?? 0, chartRows.length - 1),
  );
  const endIndex = Math.max(
    startIndex,
    Math.min(
      brushWindow?.endIndex ?? chartRows.length - 1,
      chartRows.length - 1,
    ),
  );
  const coordinateLabel = (value: number) =>
    alignment === "days_since_opening"
      ? `Day ${value} after method opened`
      : `${Math.abs(value)} days before Election Day`;
  useEffect(() => setBrushWindow(null), [data, alignment, preOpening]);
  useEffect(() => {
    const element = chartRef.current;
    if (!element || !chartRows.length) return;
    const label = (value: number) =>
      alignment === "days_since_opening"
        ? `Day ${value} after method opened`
        : `${Math.abs(value)} days before Election Day`;
    const apply = () => {
      const handles = element.querySelectorAll<SVGGElement>(
        ".recharts-brush-traveller",
      );
      handles.forEach((handle, index) => {
        const coordinate = Number(
          chartRows[index === 0 ? startIndex : endIndex]?.coordinate,
        );
        const attributes = {
          "aria-label":
            index === 0
              ? "Historical trajectory window start"
              : "Historical trajectory window end",
          "aria-valuemin": String(
            chartRows[index === 0 ? 0 : startIndex]?.coordinate,
          ),
          "aria-valuemax": String(
            chartRows[index === 0 ? endIndex : chartRows.length - 1]
              ?.coordinate,
          ),
          "aria-valuenow": String(coordinate),
          "aria-valuetext": label(coordinate),
          "aria-orientation": "horizontal",
        };
        Object.entries(attributes).forEach(([name, value]) => {
          if (handle.getAttribute(name) !== value)
            handle.setAttribute(name, value);
        });
      });
    };
    // Recharts exposes a readable label but its slider groups otherwise publish
    // pixel-valued now and no min/max. Keep its pointer/keyboard behavior while
    // bridging those attributes to the actual observed-coordinate window.
    const observer = new MutationObserver(apply);
    observer.observe(element, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ["aria-valuenow"],
    });
    apply();
    return () => observer.disconnect();
  }, [chartRows, startIndex, endIndex, alignment]);
  const activeCycles = useMemo(
    () =>
      data
        ? [
            { cycle: data.query.cycle, trajectory: data.current.trajectory },
            ...data.cycles.filter((cycle) => cycle.trajectory.length),
          ]
        : [],
    [data],
  );
  const selectedCycle =
    data?.cycles.find((cycle) => cycle.cycle === storedSelectedCycle) ||
    data?.cycles.find((cycle) => cycle.same_stage) ||
    data?.cycles[0];
  const lastCurrent = data?.current.trajectory.at(-1);
  return (
    <section id="forecast-history" className="forecast-anchor">
      <Panel
        title="Same stage, different elections"
        subtitle="Compare actual reports at equal election-relative coordinates. Presidential, midterm and off-year electorates remain visibly distinct."
      >
        <div className="forecast-history-controls">
          <Select
            label="Historical EV alignment"
            value={alignment}
            onChange={setAlignment}
            options={[
              {
                value: "days_to_election",
                label: "Same days before Election Day",
              },
              {
                value: "days_since_opening",
                label: "Same calendar days after method opened",
              },
            ]}
          />
          <Select
            label="Historical EV evidence vintage"
            value={basis}
            onChange={setBasis}
            options={[
              {
                value: "retrospective",
                label: "Recovered historical evidence · labeled retrospective",
              },
              {
                value: "reported",
                label: "Only evidence available at the historical cutoff",
              },
            ]}
          />
          <Select
            label="Historical EV metric"
            value={metric}
            onChange={setMetric}
            options={[
              { value: "ballots_cast", label: "Reported early ballots cast" },
              {
                value: "ballots_returned",
                label: "Returned / received ballots",
              },
              { value: "ballots_accepted", label: "Accepted ballots" },
              {
                value: "ballots_requested",
                label: "Requests · administration, not turnout",
              },
              {
                value: "ballots_issued",
                label: "Issued ballots · administration, not turnout",
              },
            ]}
          />
          <Select
            label="Historical EV voting method"
            value={mode}
            onChange={setMode}
            options={[
              { value: "all", label: "All methods · source total" },
              { value: "early_in_person", label: "Early in-person" },
              { value: "mail", label: "Mail / absentee" },
            ]}
          />
          <Select
            label="Historical EV cycle set"
            value={cycleSet}
            onChange={setCycleSet}
            options={[
              {
                value: "2016,2018,2020,2022,2024",
                label: "2016–2024 · presidential + midterm",
              },
              { value: "2018,2022", label: "Midterms · 2018 and 2022" },
              {
                value: "2016,2020,2024",
                label: "Presidential cycles · 2016, 2020, 2024",
              },
              {
                value: "2017,2019,2021,2023,2025",
                label: "Off-year cycles · where supported",
              },
            ]}
          />
        </div>
        {history.isPending ? (
          <Loading label="Aligning source reports, voting calendars and historical turnout references…" />
        ) : history.isError ? (
          <Notice tone="warning">
            {history.error.message}. The model’s existing evidence and source
            inspector remain available.
          </Notice>
        ) : data ? (
          <>
            <div className="forecast-stage-summary">
              <div>
                <CalendarDays size={22} />
                <div>
                  <span>Anchor: latest actual report</span>
                  <b>{data.current.date || "No dated current report"}</b>
                  <small>
                    {data.current.age_days == null
                      ? "Age not established"
                      : `${data.current.age_days} days before your evidence cutoff`}
                  </small>
                </div>
              </div>
              <div>
                <span>
                  {alignment === "days_since_opening"
                    ? "Calendar days since method opened"
                    : "Days until Election Day"}
                </span>
                <b>
                  {alignment === "days_since_opening"
                    ? (data.current.days_since_opening ?? "Unverified")
                    : data.current.days_to_election}
                </b>
                <small>
                  {alignment === "days_since_opening"
                    ? "Opening day = 0; weekends included"
                    : "Uses each cycle’s actual election date"}
                </small>
              </div>
              <div>
                <span>Compatible exact-stage cycles</span>
                <b>
                  {data.coverage.same_stage_cycles} /{" "}
                  {data.coverage.requested_cycles}
                </b>
                <small>
                  {data.coverage.available_cycles} cycles have some retained
                  evidence
                </small>
              </div>
            </div>
            {basis === "retrospective" ? (
              <Notice tone="warning">
                Historical data here may have been recovered or reconstructed
                later. It is useful for research, but does not establish what
                was publicly known at that historical moment.
              </Notice>
            ) : (
              <Notice>
                Only historically available evidence versions are eligible. A
                later archive does not become a contemporary report simply
                because it contains an old date.
              </Notice>
            )}
            {alignment === "days_since_opening" && (
              <div className="forecast-preopening-control">
                <label>
                  <input
                    type="checkbox"
                    checked={preOpening === "show"}
                    onChange={(event) =>
                      setPreOpening(event.target.checked ? "show" : "hide")
                    }
                  />
                  Show published observations before the method opened
                </label>
                <p className="forecast-caption">
                  {preOpening === "show"
                    ? "Published pre-opening observations are included in the chart."
                    : `${preOpeningCount} pre-opening observation coordinates are hidden from the default chart window.`}{" "}
                  Original observations remain in the historical source records
                  and JSON export; this display option does not change the model
                  or comparison cutoff.
                </p>
              </div>
            )}
            {!!chartRows.length ? (
              <>
                <div
                  ref={chartRef}
                  className="chart forecast-history-chart"
                  style={{ height: 350 }}
                >
                  <ResponsiveContainer>
                    <LineChart
                      data={chartRows}
                      margin={{ left: 7, right: 20, top: 15, bottom: 22 }}
                    >
                      <CartesianGrid
                        stroke="var(--chart-grid)"
                        vertical={false}
                      />
                      <XAxis
                        dataKey="coordinate"
                        type="number"
                        domain={["dataMin", "dataMax"]}
                        tick={{ fill: "var(--muted)", fontSize: 13 }}
                        tickFormatter={(value) =>
                          alignment === "days_to_election"
                            ? `${Math.abs(value)}d before`
                            : `Day ${value}`
                        }
                        allowDuplicatedCategory={false}
                      />
                      <YAxis
                        width={65}
                        tick={{ fill: "var(--muted)", fontSize: 13 }}
                        tickFormatter={compact}
                      />
                      <Tooltip
                        contentStyle={tooltip}
                        labelFormatter={(value) =>
                          alignment === "days_to_election"
                            ? `${Math.abs(Number(value))} days until Election Day`
                            : `${value} calendar days since opening`
                        }
                        formatter={(value, name) => [fmt(value), String(name)]}
                      />
                      {activeCycles.map((cycle, index) => (
                        <Line
                          key={cycle.cycle}
                          type="stepAfter"
                          dataKey={`cycle_${cycle.cycle}`}
                          name={String(cycle.cycle)}
                          stroke={cycleColor(cycle.cycle)}
                          strokeWidth={
                            cycle.cycle === data.query.cycle ? 3 : 1.8
                          }
                          strokeDasharray={
                            cycle.cycle === data.query.cycle
                              ? undefined
                              : index % 2
                                ? "5 3"
                                : "2 3"
                          }
                          connectNulls
                          dot={{ r: 2 }}
                          isAnimationActive={false}
                        />
                      ))}
                      <Brush
                        dataKey="coordinate"
                        ariaLabel="Historical reported-observation display window; use the arrow keys to adjust each endpoint"
                        startIndex={startIndex}
                        endIndex={endIndex}
                        onChange={(range) => {
                          if (
                            range.startIndex != null &&
                            range.endIndex != null
                          )
                            setBrushWindow({
                              startIndex: range.startIndex,
                              endIndex: range.endIndex,
                            });
                        }}
                        height={22}
                        stroke="var(--violet)"
                        tickFormatter={(value) =>
                          alignment === "days_to_election"
                            ? `${Math.abs(value)}d`
                            : `Day ${value}`
                        }
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
                <p className="forecast-caption" aria-live="polite">
                  Chart window:{" "}
                  {coordinateLabel(Number(chartRows[startIndex]?.coordinate))}{" "}
                  to {coordinateLabel(Number(chartRows[endIndex]?.coordinate))}.
                </p>
                <div className="forecast-map-key">
                  {activeCycles.map((cycle) => (
                    <span key={cycle.cycle}>
                      <i style={{ background: cycleColor(cycle.cycle) }} />
                      {cycle.cycle}
                      {cycle.cycle === data.query.cycle ? " · current" : ""}
                    </span>
                  ))}
                </div>
                <p className="forecast-caption">
                  Dots are actual observations; steps retain the last reported
                  value until another observation. No daily voting events are
                  invented. Drag the chart’s lower handles to inspect a narrower
                  window; this changes the display window and preserves the
                  model’s evidence cutoff.
                </p>
              </>
            ) : (
              <Empty title="No aligned trajectory is available">
                This exact metric, method and chronology has no eligible
                observations. Choose another method or inspect the explicit gaps
                in the cycle ledger.
              </Empty>
            )}
            <div className="forecast-cycle-cards">
              {data.cycles.map((cycle) => (
                <button
                  key={cycle.cycle}
                  className={`${selectedCycle?.cycle === cycle.cycle ? "selected" : ""} ${cycle.same_stage ? "compatible" : "limited"}`}
                  onClick={() => setSelectedCycle(cycle.cycle)}
                >
                  <span className="forecast-cycle-heading">
                    <b style={{ color: cycleColor(cycle.cycle) }}>
                      {cycle.cycle}
                    </b>
                    <small>{human(cycle.election_type)}</small>
                  </span>
                  <strong>
                    {cycle.value == null ? "No evidence" : fmt(cycle.value)}
                  </strong>
                  <span>
                    {cycle.same_stage
                      ? "Exact stage · compatible"
                      : cycle.available
                        ? "Historical context only"
                        : "Unavailable"}
                  </span>
                  <small>{cycle.observed_date || cycle.reason}</small>
                  <em>
                    {cycle.pace_ratio == null
                      ? "Pace ratio withheld"
                      : `${fmt(cycle.pace_ratio, 2)}× current / historical`}
                  </em>
                </button>
              ))}
            </div>
            {selectedCycle && (
              <div className="forecast-cycle-inspector">
                <div>
                  <span className="call-eyebrow">
                    {selectedCycle.cycle} evidence inspector
                  </span>
                  <h4>
                    {selectedCycle.same_stage
                      ? "A supported same-stage comparison"
                      : "The limitation is part of the finding"}
                  </h4>
                  <p>{selectedCycle.reason}</p>
                  <Badge tone={selectedCycle.same_stage ? "teal" : "gold"}>
                    {selectedCycle.chronology.basis === "reported"
                      ? "Contemporary evidence only"
                      : "Retrospective historical evidence"}
                  </Badge>
                </div>
                <dl className="call-facts">
                  <div>
                    <dt>Target historical stage</dt>
                    <dd>
                      {selectedCycle.target_date || "Calendar unavailable"}
                    </dd>
                  </div>
                  <div>
                    <dt>Actual source report</dt>
                    <dd>{selectedCycle.observed_date || "Missing"}</dd>
                  </div>
                  <div>
                    <dt>Report age at target</dt>
                    <dd>
                      {selectedCycle.age_days == null
                        ? "Not established"
                        : `${selectedCycle.age_days} days`}
                    </dd>
                  </div>
                  <div>
                    <dt>Reporting geography</dt>
                    <dd>{human(selectedCycle.grain)}</dd>
                  </div>
                  <div>
                    <dt>Current / historical pace</dt>
                    <dd>
                      {selectedCycle.pace_ratio == null
                        ? "Withheld"
                        : `${fmt(selectedCycle.pace_ratio, 3)}×`}
                    </dd>
                  </div>
                  <div>
                    <dt>Original time basis</dt>
                    <dd>
                      {selectedCycle.chronology.original_time_bases.join(
                        ", ",
                      ) || "Unavailable"}
                    </dd>
                  </div>
                </dl>
                <details>
                  <summary>
                    Matched coverage, original sources, and dates
                  </summary>
                  <p className="forecast-caption">
                    {selectedCycle.chronology.description}
                  </p>
                  <pre className="call-manifest">
                    {JSON.stringify(
                      {
                        matched: selectedCycle.matched,
                        calendar: selectedCycle.calendar,
                        chronology: selectedCycle.chronology,
                        source_refs: selectedCycle.source_refs,
                        warnings: selectedCycle.warnings,
                      },
                      null,
                      2,
                    )}
                  </pre>
                </details>
              </div>
            )}
            <details>
              <summary>Complete historical stage coverage ledger</summary>
              <div className="table-scroll">
                <table className="forecast-history-ledger">
                  <thead>
                    <tr>
                      <th>Cycle</th>
                      <th>Class</th>
                      <th>Target date</th>
                      <th>Observed date</th>
                      <th>Source total</th>
                      <th>Exact-stage eligibility</th>
                      <th>Reason</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.cycles.map((cycle) => (
                      <tr key={cycle.cycle}>
                        <td>{cycle.cycle}</td>
                        <td>{human(cycle.election_type)}</td>
                        <td>{cycle.target_date || "Unavailable"}</td>
                        <td>{cycle.observed_date || "Missing"}</td>
                        <td>{fmt(cycle.value)}</td>
                        <td>{cycle.same_stage ? "Eligible" : "Unavailable"}</td>
                        <td>{cycle.reason}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>
            {lastCurrent && (
              <p className="forecast-caption">
                Latest change:{" "}
                {lastCurrent.newly_reported == null
                  ? "a comparable prior report is unavailable"
                  : `${fmt(lastCurrent.newly_reported)} newly reported ballots`}{" "}
                · {lastCurrent.carried_forward_count || 0} geographic components
                carried forward · oldest component{" "}
                {lastCurrent.oldest_component_date || "not established"}.
              </p>
            )}
            <div className="call-hero-actions">
              <button
                className="button small secondary"
                onClick={() =>
                  downloadData(
                    data,
                    `${call.state}-same-stage-ev-r${data.revision}.json`,
                  )
                }
              >
                <Download size={14} />
                Export exact stage investigation
              </button>
              <button
                className="text-button"
                onClick={() => ctx.setPage("history")}
              >
                Open full historical workbench <ArrowRight size={13} />
              </button>
            </div>
            <ResearchGuide
              what="Reported participation aligned to actual election dates or documented method-opening dates, with exact-stage comparison eligibility."
              how="A current/historical ratio appears only when report stage, metric definitions and matched geographic coverage support it. A ten-day-old report is never silently treated as a report at today's stage. Calendar days are not automatically equal voting opportunities; rule changes and the pandemic can alter interpretation."
              source={`${data.query.metric} · ${data.query.mode} · ${data.units} · evidence r${data.revision}`}
            />
            {!!data.current.mode_values?.length && (
              <div className="forecast-native-methods">
                <h4 className="forecast-chart-title">
                  Voting methods and administrative measures
                </h4>
                <p className="forecast-caption">
                  Each bar is its own native measure with its own date and
                  definition. These rows may overlap and are not stacked or
                  added into a manufactured total.
                </p>
                <div
                  className="chart"
                  style={{
                    height: Math.max(210, data.current.mode_values.length * 43),
                  }}
                >
                  <ResponsiveContainer>
                    <BarChart
                      data={data.current.mode_values.map((row, index) => ({
                        ...row,
                        label: human(row.mode) + " · " + human(row.metric),
                        index,
                      }))}
                      layout="vertical"
                      margin={{ left: 5, right: 20, top: 10, bottom: 10 }}
                    >
                      <CartesianGrid
                        stroke="var(--chart-grid)"
                        horizontal={false}
                      />
                      <XAxis
                        type="number"
                        tickFormatter={compact}
                        tick={{ fill: "var(--muted)", fontSize: 13 }}
                      />
                      <YAxis
                        type="category"
                        dataKey="label"
                        width={155}
                        tick={{ fill: "var(--muted)", fontSize: 13 }}
                      />
                      <Tooltip
                        contentStyle={tooltip}
                        formatter={(value) => [
                          fmt(value),
                          "Native reported measure",
                        ]}
                      />
                      <Bar
                        dataKey="value"
                        maxBarSize={24}
                        isAnimationActive={false}
                      >
                        {data.current.mode_values.map((row) => (
                          <Cell
                            key={`${row.mode}-${row.metric}`}
                            fill={MODE_COLORS[row.mode] || "var(--teal)"}
                          />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
                <details>
                  <summary>
                    Inspect method definitions and source classifications
                  </summary>
                  <div className="table-scroll">
                    <table>
                      <thead>
                        <tr>
                          <th>Method</th>
                          <th>Metric</th>
                          <th>Reported quantity</th>
                          <th>Date</th>
                          <th>Definition / classification</th>
                        </tr>
                      </thead>
                      <tbody>
                        {data.current.mode_values.map((row, index) => (
                          <tr key={index}>
                            <td>{human(row.mode)}</td>
                            <td>{human(row.metric)}</td>
                            <td>{fmt(row.value)}</td>
                            <td>{row.date}</td>
                            <td>
                              {row.definition.join("; ")}
                              <small>{row.classification.join("; ")}</small>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <pre className="call-manifest">
                    {JSON.stringify(data.current.mode_values, null, 2)}
                  </pre>
                </details>
              </div>
            )}
            <ForecastTurnout data={data} call={call} />
            <details>
              <summary>Additional stage and turnout limitations</summary>
              {data.warnings.map((warning, index) => (
                <p key={index} className="body-copy">
                  {warning}
                </p>
              ))}
            </details>
          </>
        ) : null}
      </Panel>
    </section>
  );
});
function ForecastTurnout({
  data,
  call,
}: {
  data: EVStageHistory;
  call: EVCall;
}) {
  const turnout = data.turnout,
    registration = turnout.registration_denominator;
  const scenarios = turnout.scenarios.filter((scenario) => scenario.consistent);
  const canShowRemaining = scenarios.some(
    (scenario) => scenario.remaining_participation != null,
  );
  return (
    <div className="forecast-turnout-section">
      <div className="forecast-turnout-title">
        <Users size={24} />
        <div>
          <span className="call-eyebrow">Turnout is central</span>
          <h3>From early participation to the electorate still to come</h3>
          <p>
            How many people have participated is measured. How many will
            ultimately participate, and which candidates they support, require
            separate explicit assumptions.
          </p>
        </div>
      </div>
      <div className="forecast-turnout-facts">
        <div>
          <span>Measured current quantity</span>
          <b>{fmt(data.current.value)}</b>
          <small>
            {human(data.current.metric)} · {human(data.current.mode)} ·{" "}
            {data.current.date || "date unavailable"}
          </small>
        </div>
        <div>
          <span>Current quantity / registration</span>
          <b>
            {registration
              ? `${fmt(registration.participation_rate_pct, 2)}%`
              : "No valid denominator"}
          </b>
          <small>
            {registration
              ? `${fmt(registration.value)} · ${registration.definition} · ${registration.date}`
              : "A dated, compatible current registration denominator is required."}
          </small>
        </div>
        <div>
          <span>Historical final participation</span>
          <b>
            {turnout.scenario_reference
              ? fmt(turnout.scenario_reference.value)
              : "No comparable reference"}
          </b>
          <small>
            {turnout.scenario_reference
              ? `${turnout.scenario_reference.cycle} ${human(turnout.scenario_reference.election_type)} · context only`
              : "Presidential and midterm turnout histories stay separate."}
          </small>
        </div>
      </div>
      <Notice>
        {turnout.forecast_status} A prior final total is a reference, never the
        denominator for the current turnout rate.
      </Notice>
      {call.evidence.turnout_projection && (
        <div className="forecast-turnout-analogue">
          <span className="call-eyebrow">
            Conditional turnout analogue · model-run scope
          </span>
          <h4>
            {call.evidence.turnout_projection.available
              ? fmt(call.evidence.turnout_projection.projection) +
                " estimated final participants"
              : "A supported turnout analogue is unavailable"}
          </h4>
          <p>{call.evidence.turnout_projection.reason}</p>
          {call.evidence.turnout_projection.available && (
            <>
              <div className="forecast-turnout-analogue-values">
                <div>
                  <span>Analogue span</span>
                  <b>
                    {fmt(call.evidence.turnout_projection.range_low)}–
                    {fmt(call.evidence.turnout_projection.range_high)}
                  </b>
                </div>
                <div>
                  <span>Conditional remaining participation</span>
                  <b>
                    {fmt(
                      call.evidence.turnout_projection.remaining_participation,
                    )}
                  </b>
                </div>
                <div>
                  <span>Independent prior cycles</span>
                  <b>
                    {call.evidence.turnout_projection.prior_cycles.join(", ")}
                  </b>
                </div>
              </div>
              <Notice tone="warning">
                This span reflects the spread of retained historical stage
                fractions. It excludes model error and has no claimed 80% or 95%
                coverage. The historical turnout benchmark below can have
                substantial error.
              </Notice>
            </>
          )}
          <p className="forecast-caption">
            This model-run analogue uses{" "}
            {human(
              call.evidence.turnout_projection.metric ||
                call.evidence.early_vote.metric,
            )}{" "}
            ·{" "}
            {human(
              call.evidence.turnout_projection.mode ||
                call.evidence.early_vote.mode,
            )}{" "}
            · report{" "}
            {call.evidence.turnout_projection.report_date || "unavailable"}.
            Workbench display controls do not silently change the saved
            model-run estimate.
          </p>
          <details>
            <summary>
              Exact prior-cycle fractions and turnout calculation
            </summary>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Prior cycle</th>
                    <th>Same-stage early</th>
                    <th>Final participation</th>
                    <th>Early / final fraction</th>
                    <th>Report date</th>
                  </tr>
                </thead>
                <tbody>
                  {call.evidence.turnout_projection.inputs.map((input) => (
                    <tr key={input.year}>
                      <td>{input.year}</td>
                      <td>{fmt(input.early_total)}</td>
                      <td>{fmt(input.final_total)}</td>
                      <td>{fmt(input.stage_fraction * 100, 2)}%</td>
                      <td>{input.report_date}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <pre className="call-manifest">
              {JSON.stringify(call.evidence.turnout_projection, null, 2)}
            </pre>
          </details>
        </div>
      )}
      <h4 className="forecast-chart-title">
        Explicit low / reference / high turnout assumptions
      </h4>
      <p className="forecast-caption">
        The following assumptions are independent of the historical-stage
        analogue above. They test final turnout at 90%, 100% and 110% of the
        service-selected prior comparable election class.
      </p>
      {turnout.scenarios.some((scenario) => !scenario.consistent) && (
        <Notice tone="warning">
          Excluded inconsistent assumptions:{" "}
          {turnout.scenarios
            .filter((scenario) => !scenario.consistent)
            .map((scenario) => scenario.name)
            .join(", ")}
          . Their assumed final totals fall below already observed compatible
          participation and are not published as valid scenarios.
        </Notice>
      )}
      {registration && registration.participation_rate_pct > 100 && (
        <Notice tone="warning">
          The selected quantity exceeds its published registration denominator.
          Inspect the metric, registration date and source definitions; this
          ratio is not treated as evidence that more than 100% of registered
          people voted.
        </Notice>
      )}
      {scenarios.length ? (
        <>
          <div className="forecast-turnout-scenarios">
            {scenarios.map((scenario) => (
              <div key={scenario.name}>
                <span>{scenario.name}</span>
                <b>{fmt(scenario.assumed_final_participation)}</b>
                <small>
                  Assumed final participation ·{" "}
                  {fmt(scenario.multiplier * 100, 0)}% of{" "}
                  {scenario.reference_cycle}
                </small>
                <dl>
                  <div>
                    <dt>Already reported early</dt>
                    <dd>
                      {scenario.reported_early_participation == null
                        ? "Not comparable"
                        : fmt(scenario.reported_early_participation)}
                    </dd>
                  </div>
                  <div>
                    <dt>Remaining participation</dt>
                    <dd>
                      {scenario.remaining_participation == null
                        ? "Withheld"
                        : fmt(scenario.remaining_participation)}
                    </dd>
                  </div>
                  <div>
                    <dt>Early share of assumed final</dt>
                    <dd>
                      {scenario.early_share_of_assumed_final_pct == null
                        ? "Withheld"
                        : `${fmt(scenario.early_share_of_assumed_final_pct, 1)}%`}
                    </dd>
                  </div>
                </dl>
                <p>{scenario.interpretation}</p>
              </div>
            ))}
          </div>
          {canShowRemaining && (
            <>
              <div className="chart" style={{ height: 230 }}>
                <ResponsiveContainer>
                  <BarChart
                    data={scenarios}
                    layout="vertical"
                    margin={{ left: 8, right: 20, top: 8, bottom: 10 }}
                  >
                    <CartesianGrid
                      stroke="var(--chart-grid)"
                      horizontal={false}
                    />
                    <XAxis
                      type="number"
                      tickFormatter={compact}
                      tick={{ fill: "var(--muted)", fontSize: 13 }}
                    />
                    <YAxis
                      type="category"
                      dataKey="name"
                      width={128}
                      tick={{ fill: "var(--muted)", fontSize: 13 }}
                    />
                    <Tooltip
                      contentStyle={tooltip}
                      formatter={(value, name) => [
                        fmt(value),
                        name === "reported_early_participation"
                          ? "Measured early participation"
                          : "Assumed remaining participation",
                      ]}
                    />
                    <Bar
                      dataKey="reported_early_participation"
                      stackId="turnout"
                      fill="var(--teal)"
                      maxBarSize={28}
                      isAnimationActive={false}
                    />
                    <Bar
                      dataKey="remaining_participation"
                      stackId="turnout"
                      fill="var(--violet)"
                      fillOpacity={0.35}
                      stroke="var(--violet)"
                      strokeDasharray="4 2"
                      maxBarSize={28}
                      isAnimationActive={false}
                    />
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <div className="forecast-map-key">
                <span>
                  <i style={{ background: "var(--teal)" }} />
                  Measured early participation
                </span>
                <span>
                  <i style={{ background: "var(--violet)", opacity: 0.4 }} />
                  Assumed later early + Election Day participation
                </span>
              </div>
            </>
          )}
          {!canShowRemaining && (
            <Notice>
              Remaining participation is withheld because this selection is not
              a complete comparable statewide all-method ballot measure. A
              method-specific count or ballot request is not subtracted from
              final statewide turnout.
            </Notice>
          )}
        </>
      ) : (
        <Empty
          title={
            turnout.scenario_reference
              ? "The turnout assumptions conflict with observed participation"
              : "A conditional final-turnout reference is unavailable"
          }
        >
          {turnout.scenario_reference
            ? "The retained prior-cycle multipliers are below already observed participation. No inconsistent remaining-participation estimate is published."
            : "No compatible prior election-class final participation record is installed. The app does not substitute candidate votes or population as ballot turnout."}
        </Empty>
      )}
      {!!turnout.historical_final_participation.length && (
        <details>
          <summary>
            Historical final-participation sources and definitions
          </summary>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Election</th>
                  <th>Final participation</th>
                  <th>Definition</th>
                  <th>Original evidence</th>
                </tr>
              </thead>
              <tbody>
                {turnout.historical_final_participation.map((reference) => (
                  <tr key={reference.cycle}>
                    <td>
                      {reference.cycle}
                      <small>{human(reference.election_type)}</small>
                    </td>
                    <td>{fmt(reference.value)}</td>
                    <td>{reference.definition}</td>
                    <td>
                      {reference.source_refs.map((ref, index) => (
                        <a
                          key={index}
                          className="text-button"
                          href={String(ref.url || "")}
                          target="_blank"
                          rel="noreferrer"
                        >
                          {String(ref.name || ref.source_id || "Source")}{" "}
                        </a>
                      ))}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <pre className="call-manifest">
            {JSON.stringify(
              {
                registration_denominator: registration,
                historical_final_participation:
                  turnout.historical_final_participation,
              },
              null,
              2,
            )}
          </pre>
        </details>
      )}
      <ResearchGuide
        what="Current measured participation, a dated denominator when available, and three explicitly assumed final-turnout levels relative to a comparable prior election class."
        how="Compare low, reference and high turnout assumptions without treating any as an empirically fitted forecast. Remaining participation includes all later voting. Candidate support is unspecified: this turnout experiment does not manufacture an R/D effect."
        source="Exact historical final-participation observations and the disclosed 0.9× / 1.0× / 1.1× assumptions."
      />
    </div>
  );
}
