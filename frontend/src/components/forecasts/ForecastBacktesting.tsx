import { memo, useMemo, useState } from "react";
import {
  ArrowDownRight,
  ArrowUpRight,
  Download,
  FlaskConical,
} from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { EVBacktestCase, EVBacktesting } from "../../earlyVoteApi";
import {
  forecastChartRecord,
  selectedCaseMetrics,
} from "../../forecastResearchMath";
import { marginCallLabel } from "../../researchCallMath";
import { downloadData } from "../../api";
import { fmt, human, stateName } from "../../utils";
import { useViewOption } from "../../viewState";
import { Badge, Empty, Notice, Panel, Select } from "../ui";
import { ResearchGuide } from "../ResearchGuide";
import { TurnoutValidation } from "./TurnoutValidation";
const tooltip = {
  background: "var(--popover)",
  color: "var(--text)",
  border: "1px solid var(--border)",
};
const pp = (value: unknown) =>
  typeof value === "number" && Number.isFinite(value)
    ? `${fmt(value, 2)} pp`
    : "Not evaluated";
function Chronology({ value }: { value: string }) {
  return (
    <Badge
      tone={
        value === "strict_contemporary"
          ? "teal"
          : value === "reconstructed_event"
            ? "violet"
            : "gold"
      }
    >
      {value === "strict_contemporary"
        ? "Contemporary report"
        : value === "reconstructed_event"
          ? "Later reconstruction"
          : "Retrospective report archive"}
    </Badge>
  );
}
export const ForecastBacktesting = memo(function ForecastBacktesting({
  backtesting,
  state,
}: {
  backtesting?: EVBacktesting;
  state: string;
}) {
  const [scope, setScope] = useViewOption<string>(
    "forecast_test_scope",
    "selected",
  );
  const [year, setYear] = useViewOption<string>("forecast_test_year", "all");
  const [chronology, setChronology] = useViewOption<string>(
    "forecast_test_chronology",
    "retrospective_report",
  );
  const [referenceKind, setReferenceKind] = useViewOption<string>(
    "forecast_test_reference",
    "final_candidate_vote_distribution",
  );
  const [alignment, setAlignment] = useViewOption<string>(
    "forecast_test_alignment",
    "days_to_election",
  );
  const [checkpoint, setCheckpoint] = useViewOption<string>(
    "forecast_test_checkpoint",
    "all",
  );
  const [page, setPage] = useState(0),
    [selectedKey, setSelectedKey] = useState("");
  const rows = useMemo(
    () =>
      (backtesting?.cases || []).filter(
        (row) =>
          (scope !== "selected" || row.state === state) &&
          (year === "all" || row.year === Number(year)) &&
          (chronology === "all" || row.chronology === chronology) &&
          (referenceKind === "all" || row.reference_kind === referenceKind) &&
          (alignment === "all" || row.alignment === alignment) &&
          (checkpoint === "all" ||
            `${row.alignment}:${row.stage}` === checkpoint),
      ),
    [
      backtesting?.cases,
      scope,
      year,
      chronology,
      referenceKind,
      alignment,
      checkpoint,
      state,
    ],
  );
  const summary = useMemo(() => selectedCaseMetrics(rows), [rows]);
  const years = useMemo(
    () =>
      [...new Set((backtesting?.cases || []).map((row) => row.year))].sort(
        (a, b) => b - a,
      ),
    [backtesting?.cases],
  );
  const checkpoints = useMemo(
    () => [
      ...new Set(
        (backtesting?.cases || []).map(
          (row) => `${row.alignment}:${row.stage}`,
        ),
      ),
    ],
    [backtesting?.cases],
  );
  const byYear = useMemo(
    () =>
      years
        .map((year) => {
          const cases = rows.filter((row) => row.year === year),
            metrics = selectedCaseMetrics(cases);
          return {
            year,
            cases: cases.length,
            mae: metrics?.mae,
            referenceMae: metrics?.referenceMae,
          };
        })
        .filter((row) => row.cases),
    [rows, years],
  );
  const key = (row: EVBacktestCase) =>
    row.case_id ||
    `${row.state}:${row.contest_id}:${row.year}:${row.cutoff}:${row.alignment}:${row.stage}:${row.chronology}:${row.reference_kind}`;
  const chosen = rows.find((row) => key(row) === selectedKey);
  const currentPage = Math.min(
    page,
    Math.max(0, Math.ceil(rows.length / 20) - 1),
  );
  const maxMargin = Math.max(
    10,
    ...rows.flatMap((row) => [
      Math.abs(row.actual_margin_pp),
      Math.abs(row.predicted_margin_pp),
    ]),
  );
  const domain = Math.ceil(maxMargin / 10) * 10;
  const update = (fn: (value: string) => void, value: string) => {
    fn(value);
    setPage(0);
    setSelectedKey("");
  };
  return (
    <section id="forecast-validation" className="forecast-anchor">
      <Panel
        title="The historical test bench"
        subtitle="Freeze the inputs before Election Day, make a prediction, then compare it with the actual Senate result."
      >
        {!backtesting ? (
          <Empty title="No EV backtest record is attached to this run">
            The historical-reference diagnostics below remain separately
            available. A missing EV validation record is not treated as zero
            error, high confidence, or a published win probability.
          </Empty>
        ) : (
          <>
            <div className="forecast-validation-status">
              <FlaskConical size={23} />
              <div>
                <b>{human(backtesting.status)}</b>
                <p>{backtesting.method}</p>
              </div>
              <Badge tone="gold">
                {backtesting.probabilities_published
                  ? "Probability publication documented"
                  : "No win probabilities published"}
              </Badge>
            </div>
            <div className="forecast-validation-counts">
              <div>
                <b>{fmt(backtesting.independent_cycles.length)}</b>
                <span>independent election cycles</span>
              </div>
              <div>
                <b>{fmt(backtesting.independent_contests)}</b>
                <span>independent Senate contests</span>
              </div>
              <div>
                <b>{fmt(backtesting.trained_ev_holdout_cases)}</b>
                <span>trained-EV held-out tests</span>
              </div>
              <div>
                <b>{fmt(backtesting.strict_contemporary_cases)}</b>
                <span>contemporary-input tests</span>
              </div>
            </div>
            <div className="forecast-calibration-grid">
              <div>
                <span>Held-out directional accuracy</span>
                <b>
                  {typeof backtesting.metrics.fixed_ev_assumption
                    ?.direction_accuracy === "number"
                    ? fmt(
                        backtesting.metrics.fixed_ev_assumption
                          .direction_accuracy * 100,
                        1,
                      ) + "%"
                    : "Not evaluated"}
                </b>
                <p>
                  Contest-balanced sign agreement on the documented audit
                  sample; this is not the chance this race will win.
                </p>
              </div>
              <div>
                <span>Probability calibration</span>
                <b>
                  {backtesting.probabilities_published
                    ? "See published diagnostics"
                    : "Not established"}
                </b>
                <p>
                  Brier score and log loss require actual probabilities with
                  independent validation. An assumed coefficient does not supply
                  them.
                </p>
              </div>
              <div>
                <span>80% / 95% interval coverage</span>
                <b>
                  {backtesting.metrics.fixed_ev_assumption
                    ?.interval_80_coverage != null
                    ? fmt(
                        Number(
                          backtesting.metrics.fixed_ev_assumption
                            .interval_80_coverage,
                        ) * 100,
                        1,
                      ) +
                      "% / " +
                      fmt(
                        Number(
                          backtesting.metrics.fixed_ev_assumption
                            .interval_95_coverage,
                        ) * 100,
                        1,
                      ) +
                      "%"
                    : "Not calibrated"}
                </b>
                <p>
                  The wide live sensitivity band is not presented as an
                  empirically calibrated prediction interval.
                </p>
              </div>
            </div>
            <Notice>
              Several cutoffs from one race are repeated observations, not
              independent elections. Retrospective archive tests and
              reconstructed event histories do not establish what a researcher
              could actually have known on that date.
            </Notice>
            <div className="table-scroll">
              <table className="forecast-method-comparison">
                <thead>
                  <tr>
                    <th>Model component</th>
                    <th>Test cases</th>
                    <th>Mean absolute error</th>
                    <th>Root mean squared error</th>
                    <th>Average signed error</th>
                  </tr>
                </thead>
                <tbody>
                  {(
                    [
                      ["historical_reference", "Historical Senate reference"],
                      ["fixed_ev_assumption", "Fixed EV assumption"],
                      ["fitted_ev", "Trained EV model"],
                    ] as const
                  ).map(([id, label]) => {
                    const metrics = backtesting.metrics[id];
                    return (
                      <tr key={id}>
                        <td>
                          <b>{label}</b>
                          <small>
                            {id === "fixed_ev_assumption"
                              ? "Explicit coefficient tested against final outcomes"
                              : id === "fitted_ev"
                                ? "Held-out evaluation only; no training-row scores"
                                : "Baseline without an EV adjustment"}
                          </small>
                        </td>
                        <td>
                          {metrics?.cases == null
                            ? "Not evaluated"
                            : fmt(metrics.cases)}
                        </td>
                        <td>{pp(metrics?.margin_mae_pp)}</td>
                        <td>{pp(metrics?.margin_rmse_pp)}</td>
                        <td>{pp(metrics?.margin_bias_pp)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <p className="forecast-caption">
              The headline comparison uses retrospective report archives,
              final-result geographic context and days-until-election
              checkpoints. Filters below let you examine other evidence strata
              separately.
            </p>
            <div className="forecast-test-controls">
              <Select
                label="Backtest geographic scope"
                value={scope}
                onChange={(value) => update(setScope, value)}
                options={[
                  {
                    value: "selected",
                    label: `${stateName(state)} Senate tests`,
                  },
                  { value: "all", label: "All tested Senate contests" },
                ]}
              />
              <Select
                label="Backtest election year"
                value={year}
                onChange={(value) => update(setYear, value)}
                options={[
                  { value: "all", label: "All held-out cycles" },
                  ...years.map((value) => ({ value, label: String(value) })),
                ]}
              />
              <Select
                label="Backtest evidence chronology"
                value={chronology}
                onChange={(value) => update(setChronology, value)}
                options={[
                  { value: "all", label: "All disclosed evidence vintages" },
                  {
                    value: "strict_contemporary",
                    label: "Contemporary reports only",
                  },
                  {
                    value: "retrospective_report",
                    label: "Retrospective report archives",
                  },
                  {
                    value: "reconstructed_event",
                    label: "Later event reconstruction",
                  },
                ]}
              />
              <Select
                label="Backtest geographic reference"
                value={referenceKind}
                onChange={(value) => update(setReferenceKind, value)}
                options={[
                  {
                    value: "final_candidate_vote_distribution",
                    label: "Final-result geographic context",
                  },
                  {
                    value: "same_stage_early_vote",
                    label: "Same-stage EV geographic context",
                  },
                  { value: "all", label: "All geographic references" },
                ]}
              />
              <Select
                label="Backtest stage alignment"
                value={alignment}
                onChange={(value) => update(setAlignment, value)}
                options={[
                  {
                    value: "days_to_election",
                    label: "Days until Election Day",
                  },
                  {
                    value: "days_since_opening",
                    label: "Calendar days since method opened",
                  },
                  { value: "all", label: "All stage alignments" },
                ]}
              />
              <Select
                label="Backtest checkpoint"
                value={checkpoint}
                onChange={(value) => update(setCheckpoint, value)}
                options={[
                  { value: "all", label: "All evaluated checkpoints" },
                  ...checkpoints.map((value) => ({
                    value,
                    label: value.startsWith("days_to_election:")
                      ? value.split(":")[1] + " days before Election Day"
                      : "Opening day " + value.split(":")[1],
                  })),
                ]}
              />
              <button
                className="button small secondary"
                onClick={() =>
                  downloadData(
                    {
                      model_version: backtesting.model_version,
                      scope: {
                        state,
                        scope,
                        year,
                        chronology,
                        referenceKind,
                        alignment,
                        checkpoint,
                      },
                      cases: rows,
                      manifest: backtesting.manifest,
                    },
                    `${state}-held-out-senate-tests.json`,
                  )
                }
              >
                <Download size={14} />
                Export test ledger
              </button>
            </div>
            {summary ? (
              <>
                <div className="forecast-filtered-results">
                  <span>
                    {summary.cases} cutoff tests · {summary.contests}{" "}
                    independent contests in this selection
                  </span>
                  <b>
                    {fmt(summary.mae, 2)} pp contest-balanced mean absolute
                    margin error
                  </b>
                  <span
                    className={
                      summary.mae < summary.referenceMae ? "improved" : "worse"
                    }
                  >
                    {summary.mae < summary.referenceMae ? (
                      <ArrowDownRight size={16} />
                    ) : (
                      <ArrowUpRight size={16} />
                    )}{" "}
                    {fmt(Math.abs(summary.mae - summary.referenceMae), 2)} pp{" "}
                    {summary.mae < summary.referenceMae ? "lower" : "higher"}{" "}
                    error than the same-case historical reference
                  </span>
                </div>
                <div className="chart-grid">
                  <div>
                    <h4 className="forecast-chart-title">
                      Predicted versus actual margin
                    </h4>
                    <div className="chart" style={{ height: 310 }}>
                      <ResponsiveContainer>
                        <ScatterChart
                          margin={{ left: 6, right: 20, top: 10, bottom: 28 }}
                        >
                          <CartesianGrid stroke="var(--chart-grid)" />
                          <XAxis
                            type="number"
                            dataKey="actual_margin_pp"
                            domain={[-domain, domain]}
                            tickFormatter={(value) => marginCallLabel(value, 0)}
                            tick={{ fill: "var(--muted)", fontSize: 13 }}
                            label={{
                              value: "Actual Senate result · R−D pp",
                              position: "insideBottom",
                              offset: -16,
                              fill: "var(--muted)",
                              fontSize: 13,
                            }}
                          />
                          <YAxis
                            type="number"
                            dataKey="predicted_margin_pp"
                            domain={[-domain, domain]}
                            tickFormatter={(value) => marginCallLabel(value, 0)}
                            tick={{ fill: "var(--muted)", fontSize: 13 }}
                            width={60}
                          />
                          <ReferenceLine
                            segment={[
                              { x: -domain, y: -domain },
                              { x: domain, y: domain },
                            ]}
                            stroke="var(--muted)"
                            strokeDasharray="4 4"
                          />
                          <ReferenceLine x={0} stroke="var(--border)" />
                          <ReferenceLine y={0} stroke="var(--border)" />
                          <Tooltip
                            contentStyle={tooltip}
                            cursor={{ stroke: "var(--muted)" }}
                            formatter={(value, name) => [
                              marginCallLabel(Number(value)),
                              name === "actual_margin_pp"
                                ? "Actual margin"
                                : "Predicted margin",
                            ]}
                          />
                          <Scatter
                            name="Held-out tests"
                            data={rows}
                            fill="var(--violet)"
                            onClick={(row) => {
                              const input = forecastChartRecord(row);
                              if (
                                input &&
                                typeof input.state === "string" &&
                                typeof input.contest_id === "string"
                              )
                                setSelectedKey(
                                  key(input as unknown as EVBacktestCase),
                                );
                            }}
                          >
                            {rows.map((row) => (
                              <Cell
                                key={key(row)}
                                fill={
                                  row.error_pp >= 0
                                    ? "var(--orange)"
                                    : "var(--teal)"
                                }
                                fillOpacity={0.7}
                              />
                            ))}
                          </Scatter>
                        </ScatterChart>
                      </ResponsiveContainer>
                    </div>
                    <p className="forecast-caption">
                      The diagonal is perfect agreement. Orange points
                      overpredict the Republican margin; teal points
                      underpredict it. Table selection provides the same details
                      without hover.
                    </p>
                  </div>
                  <div>
                    <h4 className="forecast-chart-title">
                      Does EV improve on the reference?
                    </h4>
                    <div className="chart" style={{ height: 310 }}>
                      <ResponsiveContainer>
                        <BarChart
                          data={byYear}
                          margin={{ left: 5, right: 10, top: 10, bottom: 15 }}
                        >
                          <CartesianGrid
                            stroke="var(--chart-grid)"
                            vertical={false}
                          />
                          <XAxis
                            dataKey="year"
                            tick={{ fill: "var(--muted)", fontSize: 13 }}
                          />
                          <YAxis
                            unit=" pp"
                            tick={{ fill: "var(--muted)", fontSize: 13 }}
                            width={50}
                          />
                          <Tooltip
                            contentStyle={tooltip}
                            formatter={(value, name) => [
                              `${fmt(value, 2)} pp`,
                              name === "mae"
                                ? "EV-model margin MAE"
                                : "Historical-reference margin MAE",
                            ]}
                          />
                          <Bar
                            dataKey="referenceMae"
                            fill="var(--gold)"
                            maxBarSize={32}
                            isAnimationActive={false}
                          />
                          <Bar
                            dataKey="mae"
                            fill="var(--violet)"
                            maxBarSize={32}
                            isAnimationActive={false}
                          />
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                    <div className="forecast-map-key">
                      <span>
                        <i style={{ background: "var(--gold)" }} />
                        Historical reference
                      </span>
                      <span>
                        <i style={{ background: "var(--violet)" }} />
                        EV prediction
                      </span>
                    </div>
                    <p className="forecast-caption">
                      Lower bars indicate smaller absolute margin error. The two
                      bars use identical held-out cases within each cycle,
                      giving each independent contest equal total weight.
                    </p>
                  </div>
                </div>
                {chosen && (
                  <div className="forecast-selected-test">
                    <div>
                      <span className="call-eyebrow">
                        Selected held-out test
                      </span>
                      <h4>
                        {stateName(chosen.state)} · {chosen.year} Senate
                      </h4>
                      <p>
                        Evidence cutoff {chosen.cutoff} ·{" "}
                        {human(chosen.alignment)} · stage{" "}
                        {chosen.stage ?? "unavailable"}
                      </p>
                      <Chronology value={chosen.chronology} />
                    </div>
                    <dl className="call-facts">
                      <div>
                        <dt>Prediction</dt>
                        <dd>{marginCallLabel(chosen.predicted_margin_pp)}</dd>
                      </div>
                      <div>
                        <dt>Actual result</dt>
                        <dd>{marginCallLabel(chosen.actual_margin_pp)}</dd>
                      </div>
                      <div>
                        <dt>Signed error</dt>
                        <dd>{fmt(chosen.error_pp, 2)} pp</dd>
                      </div>
                      <div>
                        <dt>Historical-only prediction</dt>
                        <dd>{marginCallLabel(chosen.baseline_margin_pp)}</dd>
                      </div>
                      <div>
                        <dt>EV coefficient</dt>
                        <dd>
                          {chosen.coefficient == null
                            ? "Not fitted"
                            : fmt(chosen.coefficient, 3)}{" "}
                          · {human(chosen.coefficient_status || "unspecified")}
                        </dd>
                      </div>
                      <div>
                        <dt>Training elections</dt>
                        <dd>
                          {chosen.training_cycles?.join(", ") || "See manifest"}
                        </dd>
                      </div>
                    </dl>
                    <details>
                      <summary>Complete test input and result record</summary>
                      <pre className="call-manifest">
                        {JSON.stringify(chosen, null, 2)}
                      </pre>
                    </details>
                  </div>
                )}
                <div className="table-scroll">
                  <table className="forecast-test-ledger">
                    <thead>
                      <tr>
                        <th>Contest / cutoff</th>
                        <th>Alignment</th>
                        <th>Evidence vintage</th>
                        <th>Historical reference</th>
                        <th>EV prediction</th>
                        <th>Actual result</th>
                        <th>Margin error</th>
                        <th>Inspect</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rows
                        .slice(currentPage * 20, (currentPage + 1) * 20)
                        .map((row) => (
                          <tr
                            key={key(row)}
                            className={
                              chosen && key(chosen) === key(row)
                                ? "selected"
                                : ""
                            }
                          >
                            <td>
                              {stateName(row.state)} · {row.year}
                              <small>{row.cutoff}</small>
                            </td>
                            <td>
                              {human(row.alignment)}
                              <small>
                                Stage {row.stage ?? "not established"} ·{" "}
                                {human(row.mode)}
                              </small>
                            </td>
                            <td>
                              <Chronology value={row.chronology} />
                            </td>
                            <td>{marginCallLabel(row.baseline_margin_pp)}</td>
                            <td>{marginCallLabel(row.predicted_margin_pp)}</td>
                            <td>{marginCallLabel(row.actual_margin_pp)}</td>
                            <td>
                              {fmt(row.error_pp, 2)} pp
                              <small>
                                {Math.abs(row.error_pp) <
                                Math.abs(row.baseline_error_pp)
                                  ? "Improved"
                                  : "Not improved"}{" "}
                                vs reference
                              </small>
                            </td>
                            <td>
                              <button
                                className="text-button"
                                onClick={() => setSelectedKey(key(row))}
                              >
                                Inspect inputs
                              </button>
                            </td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                </div>
                <div className="forecast-pagination">
                  <button
                    className="button small secondary"
                    disabled={currentPage === 0}
                    onClick={() => setPage(currentPage - 1)}
                  >
                    Previous
                  </button>
                  <span>
                    {currentPage * 20 + 1}–
                    {Math.min((currentPage + 1) * 20, rows.length)} of{" "}
                    {rows.length} tests
                  </span>
                  <button
                    className="button small secondary"
                    disabled={(currentPage + 1) * 20 >= rows.length}
                    onClick={() => setPage(currentPage + 1)}
                  >
                    Next
                  </button>
                </div>
              </>
            ) : (
              <Empty title="No held-out tests match this selection">
                Try all tested Senate contests or a broader evidence-vintage
                filter. The state’s source gaps and excluded test cases remain
                visible below.
              </Empty>
            )}
            {!!backtesting.exclusions.length && (
              <details>
                <summary>
                  Why historical tests were excluded (
                  {fmt(backtesting.exclusions.length)})
                </summary>
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>State</th>
                        <th>Cycle</th>
                        <th>Stage</th>
                        <th>Missing evidence or incompatibility</th>
                      </tr>
                    </thead>
                    <tbody>
                      {backtesting.exclusions
                        .filter(
                          (row) => scope !== "selected" || row.state === state,
                        )
                        .slice(0, 120)
                        .map((row, index) => (
                          <tr key={index}>
                            <td>{stateName(row.state)}</td>
                            <td>{row.year}</td>
                            <td>
                              {human(row.alignment || "not established")} ·{" "}
                              {row.stage ?? "—"}
                            </td>
                            <td>{row.reason}</td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                </div>
                <p className="forecast-caption">
                  Up to 120 exclusions are displayed here. The complete
                  versioned record is available in the validation manifest.
                </p>
              </details>
            )}
            {backtesting.warnings.map((warning, index) => (
              <Notice key={index} tone="warning">
                {warning}
              </Notice>
            ))}
            <TurnoutValidation audit={backtesting.turnout} state={state} />
            <details>
              <summary>
                Validation manifest, grouped diagnostics, and reproducibility
              </summary>
              <pre className="call-manifest">
                {JSON.stringify(
                  {
                    model_version: backtesting.model_version,
                    grouped_metrics: backtesting.grouped_metrics,
                    manifest: backtesting.manifest,
                  },
                  null,
                  2,
                )}
              </pre>
            </details>
          </>
        )}
        <ResearchGuide
          what="Out-of-sample Senate party-margin predictions compared with final results, with separate historical-reference and EV model diagnostics."
          how="Compare the EV error with the baseline on identical test cases. Inspect the count of independent contests and cycles, not only cutoff rows. Historical accuracy on a sparse, retrospective sample does not validate live winner probabilities. Errors are predicted R−D margin minus actual R−D margin."
          source="Pinned observation/result records and explicit chronology in each held-out case; no future results enter that case’s training inputs."
        />
      </Panel>
    </section>
  );
});
