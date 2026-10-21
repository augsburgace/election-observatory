import { memo } from "react";
import {
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { TurnoutBacktesting } from "../../earlyVoteApi";
import { compact, fmt, human, stateName } from "../../utils";
import { Empty, Notice } from "../ui";
import { ResearchGuide } from "../ResearchGuide";
export const TurnoutValidation = memo(function TurnoutValidation({
  audit,
  state,
}: {
  audit?: TurnoutBacktesting;
  state: string;
}) {
  if (!audit) return null;
  const rows = audit.cases.filter(
    (row) =>
      row.state === state &&
      row.chronology === "retrospective_report" &&
      row.alignment === "days_to_election",
  );
  const maximum = Math.max(
    1,
    ...rows.flatMap((row) => [row.actual_turnout, row.predicted_turnout]),
  );
  return (
    <div className="forecast-turnout-audit">
      <h3>Does the turnout analogue survive historical testing?</h3>
      <p className="forecast-caption">
        This is a separate participation benchmark. Candidate margin, final
        turnout and individual candidate choice are different prediction
        targets.
      </p>
      <div className="forecast-validation-counts">
        <div>
          <b>{fmt(audit.metrics.cases)}</b>
          <span>headline turnout cutoff tests</span>
        </div>
        <div>
          <b>{fmt(audit.metrics.independent_state_cycles)}</b>
          <span>independent state-election outcomes</span>
        </div>
        <div>
          <b>
            {audit.metrics.mean_absolute_percentage_error == null
              ? "Not evaluated"
              : fmt(audit.metrics.mean_absolute_percentage_error, 1) + "%"}
          </b>
          <span>mean absolute turnout percentage error</span>
        </div>
        <div>
          <b>{fmt(audit.metrics.mean_absolute_error_ballots)}</b>
          <span>mean absolute participation error</span>
        </div>
      </div>
      <Notice tone="warning">
        The historical benchmark may use only one earlier analogue for an
        explicit sparse-data diagnostic. Current projections require at least
        two compatible prior cycles. These errors do not calibrate a winner
        probability or the min/max analogue span.
      </Notice>
      {rows.length ? (
        <>
          <div className="chart" style={{ height: 280 }}>
            <ResponsiveContainer>
              <ScatterChart
                margin={{ left: 10, right: 20, top: 10, bottom: 28 }}
              >
                <CartesianGrid stroke="var(--chart-grid)" />
                <XAxis
                  type="number"
                  dataKey="actual_turnout"
                  domain={[0, maximum]}
                  tickFormatter={compact}
                  tick={{ fill: "var(--muted)", fontSize: 13 }}
                  label={{
                    value: "Actual final participation",
                    position: "insideBottom",
                    offset: -15,
                    fill: "var(--muted)",
                    fontSize: 13,
                  }}
                />
                <YAxis
                  type="number"
                  dataKey="predicted_turnout"
                  domain={[0, maximum]}
                  tickFormatter={compact}
                  tick={{ fill: "var(--muted)", fontSize: 13 }}
                  width={65}
                />
                <ReferenceLine
                  segment={[
                    { x: 0, y: 0 },
                    { x: maximum, y: maximum },
                  ]}
                  stroke="var(--muted)"
                  strokeDasharray="4 4"
                />
                <Tooltip
                  contentStyle={{
                    background: "var(--popover)",
                    border: "1px solid var(--border)",
                    color: "var(--text)",
                  }}
                  formatter={(value, name) => [
                    fmt(value),
                    name === "actual_turnout"
                      ? "Actual final participation"
                      : "Prior-only turnout prediction",
                  ]}
                />
                <Scatter data={rows} fill="var(--teal)" />
              </ScatterChart>
            </ResponsiveContainer>
          </div>
          <p className="forecast-caption">
            {stateName(state)} retrospective report tests at election-relative
            checkpoints. Above the diagonal overpredicts turnout; below it
            underpredicts. Each plotted point has its original cutoff and
            training years in the ledger.
          </p>
          <details>
            <summary>
              Inspect {stateName(state)} turnout predictions and actual outcomes
              ({rows.length})
            </summary>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Cycle / cutoff</th>
                    <th>Stage</th>
                    <th>Prior cycles</th>
                    <th>Predicted final</th>
                    <th>Actual final</th>
                    <th>Error</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.slice(0, 80).map((row) => (
                    <tr key={row.case_id}>
                      <td>
                        {row.year}
                        <small>{row.cutoff}</small>
                      </td>
                      <td>{row.stage} days before Election Day</td>
                      <td>{row.prior_cycles.join(", ")}</td>
                      <td>{fmt(row.predicted_turnout)}</td>
                      <td>{fmt(row.actual_turnout)}</td>
                      <td>
                        {fmt(row.percentage_error, 1)}%
                        <small>{fmt(row.error_ballots)} participants</small>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        </>
      ) : (
        <Empty
          title={`No eligible ${stateName(state)} turnout holdouts in this stratum`}
        >
          The headline metrics summarize the actually tested state-election
          outcomes. This state's gap is not treated as validation.
        </Empty>
      )}
      <details>
        <summary>
          Turnout validation chronology, exclusions, and original evidence
        </summary>
        <pre className="call-manifest">
          {JSON.stringify(
            {
              status: audit.status,
              grouped_metrics: audit.grouped_metrics,
              state_cases: audit.cases.filter((row) => row.state === state),
              state_exclusions: audit.exclusions.filter(
                (row) => row.state === state,
              ),
              warnings: audit.warnings,
            },
            null,
            2,
          )}
        </pre>
      </details>
      <ResearchGuide
        what="A prior-only historical stage-fraction turnout analogue evaluated against actual administrative final-participation records."
        how="Compare total-participation errors with the much narrower historical-analogue span. The span excludes model error and cannot become a confidence interval. Repeated cutoff rows receive one state-election total weight. Different election classes and chronology strata are not interchangeable."
        source={human(audit.status)}
      />
    </div>
  );
});
