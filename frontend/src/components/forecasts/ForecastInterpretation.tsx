import { memo, useMemo, useState } from "react";
import {
  CheckCircle2,
  CircleDashed,
  ShieldCheck,
  SlidersHorizontal,
  AlertTriangle,
} from "lucide-react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceDot,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { EVCall } from "../../earlyVoteApi";
import { marginCallLabel } from "../../researchCallMath";
import { Badge, Empty, Notice, Panel } from "../ui";
import { ResearchGuide } from "../ResearchGuide";
import { fmt, human } from "../../utils";
const tooltip = {
  background: "var(--popover)",
  color: "var(--text)",
  border: "1px solid var(--border)",
};
const directionColor = (value: number | null) =>
  value == null
    ? "var(--muted)"
    : value > 0
      ? "var(--red)"
      : value < 0
        ? "var(--blue)"
        : "var(--violet)";
export const ForecastConfidence = memo(function ForecastConfidence({
  call,
}: {
  call: EVCall;
}) {
  const confidence = call.confidence;
  const checks = confidence?.checks || [
    {
      label: "Current EV date",
      status:
        call.evidence.early_vote.report_date_verified === false
          ? "unverified"
          : call.evidence.early_vote.date
            ? "available"
            : "unavailable",
      detail: call.evidence.early_vote.date || "No dated current observation.",
    },
    {
      label: "Geographic adjustment",
      status: call.evidence.geographic_tilt.available
        ? "available"
        : "unavailable",
      detail: call.evidence.geographic_tilt.description,
    },
    {
      label: "Same-stage geographic reference",
      status: call.evidence.geographic_tilt.same_stage
        ? "available"
        : "unavailable",
      detail: call.evidence.geographic_tilt.same_stage
        ? "Compatible historical EV geography supports the reference."
        : "A final-result geographic reference is not a historical EV-stage comparison.",
    },
    {
      label: "Calibrated win probability",
      status: "unavailable",
      detail:
        "No probability is published by this experimental research model.",
    },
  ];
  return (
    <section id="forecast-confidence" className="forecast-anchor">
      <Panel
        title="How much confidence should this call earn?"
        subtitle="Evidence quality, historical testing, and a winner probability answer different questions."
      >
        <div className="forecast-confidence-summary">
          <ShieldCheck size={25} />
          <div>
            <span className="call-eyebrow">Publication status</span>
            <h4>{confidence?.label || "Conditional research estimate"}</h4>
            <p>
              {confidence?.reason ||
                "The point call is explicit, while its accuracy remains subject to held-out historical evaluation. No calibrated probability follows from a complete source file or a narrow sensitivity test."}
            </p>
          </div>
          <Badge tone={confidence?.validated_probability ? "teal" : "gold"}>
            {confidence?.validated_probability
              ? "Probability validation documented"
              : "No validated win probability"}
          </Badge>
        </div>
        <div className="forecast-check-grid">
          {checks.map((check, index) => {
            const pass =
              /^(available|passed|pass|supported|verified|complete|eligible|yes)$/.test(
                check.status,
              );
            return (
              <div
                key={`${check.label}-${index}`}
                className={pass ? "pass" : "review"}
              >
                {pass ? <CheckCircle2 size={17} /> : <CircleDashed size={17} />}
                <div>
                  <b>{check.label}</b>
                  <span>{human(check.status)}</span>
                  <p>{check.detail}</p>
                </div>
              </div>
            );
          })}
        </div>
        <details className="forecast-factor-roles">
          <summary>
            Which evidence enters the call, and which remains context?
          </summary>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Factor</th>
                  <th>Published evidence</th>
                  <th>Role in this research call</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>Early participation volume and location</td>
                  <td>
                    {call.evidence.early_vote.total == null
                      ? "Unavailable"
                      : fmt(call.evidence.early_vote.total) +
                        " reported ballots"}
                  </td>
                  <td>
                    {call.evidence.geographic_tilt.available
                      ? "Geographic composition contributes through the disclosed conversion assumption."
                      : "Does not create a geographic adjustment without eligible reconciled inputs."}
                  </td>
                </tr>
                <tr>
                  <td>Historical Senate results</td>
                  <td>
                    {call.evidence.historical_reference.cycles.length} reference
                    contests
                  </td>
                  <td>
                    Recency-weighted party-margin reference; candidates and
                    Senate seats may differ.
                  </td>
                </tr>
                <tr>
                  <td>Voting-method and turnout comparisons</td>
                  <td>Inspect the same-stage and turnout workbench.</td>
                  <td>
                    Measured participation context and explicit conditional
                    turnout scenarios; no automatic conversion from more early
                    ballots to a candidate advantage.
                  </td>
                </tr>
                <tr>
                  <td>Party registration / primary history</td>
                  <td>
                    {call.evidence.composition.some((row) =>
                      /party|registration|primary/i.test(row.dimension),
                    )
                      ? "Published composition is available."
                      : "No compatible published composition in this call."}
                  </td>
                  <td>
                    Descriptive context. Registration or past primary
                    participation is not observed candidate choice.
                  </td>
                </tr>
                <tr>
                  <td>Race, ethnicity, age and other voter characteristics</td>
                  <td>
                    {call.evidence.composition.some((row) =>
                      /race|ethnic|age|sex|gender/i.test(row.dimension),
                    )
                      ? "Inspect the original published marginal categories below."
                      : "No compatible directly published voter categories in this call."}
                  </td>
                  <td>
                    Published groups remain separate; population traits do not
                    identify who voted or support joint demographic filters.
                  </td>
                </tr>
                <tr>
                  <td>Individual voting propensity and religion</td>
                  <td>
                    No observed individual propensity or religion evidence in
                    this model.
                  </td>
                  <td>
                    No inferred belief, individual turnout score, or demographic
                    candidate-choice estimate is manufactured.
                  </td>
                </tr>
                <tr>
                  <td>Polls and betting markets</td>
                  <td>
                    {call.evidence.polls?.count || 0} polling studies for
                    separate review.
                  </td>
                  <td>
                    Polling is secondary context; polling and market odds do not
                    enter this EV research calculation.
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </details>
        <details className="forecast-interpretation">
          <summary>Read a margin call correctly</summary>
          <div className="forecast-reading-grid">
            <div>
              <b>1 · Read the point</b>
              <p>
                R +3 means the configured model puts the Republican party margin
                three percentage points ahead of the Democratic party. It does
                not mean a 3% win probability.
              </p>
            </div>
            <div>
              <b>2 · Read what moves it</b>
              <p>
                The historical Senate reference and the assumed EV adjustment
                are shown separately. Registration, race, method and geography
                describe participation only where actually published.
              </p>
            </div>
            <div>
              <b>3 · Read the uncertainty</b>
              <p>
                An assumption sensitivity range describes changes under a
                disclosed set of assumptions. It acquires an empirical coverage
                interpretation only when independently tested and documented.
              </p>
            </div>
            <div>
              <b>4 · Challenge the call</b>
              <p>
                Inspect same-stage comparisons, source dates, reconciliation and
                held-out cases. A confident directional label cannot resolve
                missing historical evidence or identify individual vote choice.
              </p>
            </div>
          </div>
        </details>
      </Panel>
    </section>
  );
});
export const ForecastSensitivity = memo(function ForecastSensitivity({
  call,
}: {
  call: EVCall;
}) {
  const sensitivity = call.sensitivity;
  const points = useMemo(
    () =>
      [...(sensitivity?.points || [])]
        .filter(
          (point): point is typeof point & { margin_pp: number } =>
            Number.isFinite(point.coefficient) &&
            typeof point.margin_pp === "number" &&
            Number.isFinite(point.margin_pp),
        )
        .sort((a, b) => a.coefficient - b.coefficient),
    [sensitivity?.points],
  );
  const defaultCoefficient =
    sensitivity?.parameters.find((parameter) =>
      /coefficient|ev_weight|conversion/.test(parameter.id),
    )?.default ?? call.evidence.geographic_tilt.coefficient;
  const defaultIndex = Math.max(
    0,
    points.findIndex(
      (point) => Math.abs(point.coefficient - defaultCoefficient) < 1e-8,
    ),
  );
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);
  const index =
    selectedIndex == null || selectedIndex >= points.length
      ? defaultIndex
      : selectedIndex;
  const selected = points[index];
  const signs = new Set(points.map((point) => Math.sign(point.margin_pp)));
  return (
    <section id="forecast-sensitivity" className="forecast-anchor">
      <Panel
        title="Put the call under pressure"
        subtitle="Change an explicit assumption and see which part of the conclusion survives. These are conditional experiments, not alternate measurements."
      >
        {points.length ? (
          <>
            <div className="forecast-sensitivity-grid">
              <div className="forecast-sensitivity-controls">
                <span className="call-eyebrow">
                  <SlidersHorizontal size={13} /> Assumption experiment
                </span>
                <label htmlFor={`ev-coefficient-${call.race_id}`}>
                  How strongly should the geographic pattern affect the call?
                </label>
                <div className="forecast-numeric-control">
                  <input
                    id={`ev-coefficient-${call.race_id}`}
                    type="range"
                    min={0}
                    max={points.length - 1}
                    step={1}
                    value={index}
                    onChange={(event) =>
                      setSelectedIndex(Number(event.target.value))
                    }
                  />
                  <input
                    type="number"
                    aria-label="EV conversion coefficient numeric value"
                    min={points[0].coefficient}
                    max={points.at(-1)!.coefficient}
                    step="any"
                    value={selected.coefficient}
                    onChange={(event) => {
                      const value = Number(event.target.value);
                      if (!Number.isFinite(value)) return;
                      setSelectedIndex(
                        points.reduce(
                          (best, point, i) =>
                            Math.abs(point.coefficient - value) <
                            Math.abs(points[best].coefficient - value)
                              ? i
                              : best,
                          0,
                        ),
                      );
                    }}
                  />
                </div>
                <p className="forecast-caption">
                  This is the model’s geographic conversion factor. Zero removes
                  the early-vote adjustment; larger values give it more weight.
                  Choose an evaluated value; the underlying evidence stays
                  fixed.
                </p>
                <button
                  className="text-button"
                  onClick={() => setSelectedIndex(null)}
                >
                  Reset to model default ({fmt(defaultCoefficient, 2)})
                </button>
                <div className="forecast-sensitivity-result">
                  <span>Conditional party margin</span>
                  <strong style={{ color: directionColor(selected.margin_pp) }}>
                    {marginCallLabel(selected.margin_pp)}
                  </strong>
                  <p>
                    {selected.adjustment_pp > 0 ? "+" : ""}
                    {fmt(selected.adjustment_pp, 2)} pp EV adjustment; the
                    historical reference stays fixed.
                  </p>
                </div>
                <Notice tone={signs.size > 1 ? "warning" : "info"}>
                  {signs.size > 1
                    ? "Changing the assumed weight can change which party leads. Treat this call as sensitive to the assumption."
                    : "The same party leads at every tested weight. That shows stability under these assumptions; historical tests are still needed to establish accuracy."}
                </Notice>
              </div>
              <div>
                <div className="chart" style={{ height: 300 }}>
                  <ResponsiveContainer>
                    <LineChart
                      data={points}
                      margin={{ left: 8, right: 20, top: 15, bottom: 20 }}
                    >
                      <CartesianGrid stroke="var(--chart-grid)" />
                      <XAxis
                        dataKey="coefficient"
                        type="number"
                        domain={["dataMin", "dataMax"]}
                        tick={{ fill: "var(--muted)", fontSize: 13 }}
                        label={{
                          value: "Weight given to the EV geographic pattern",
                          position: "insideBottom",
                          offset: -12,
                          fill: "var(--muted)",
                          fontSize: 13,
                        }}
                      />
                      <YAxis
                        tickFormatter={(value) => marginCallLabel(value)}
                        width={65}
                        tick={{ fill: "var(--muted)", fontSize: 13 }}
                      />
                      <ReferenceLine
                        y={0}
                        stroke="var(--border-strong)"
                        strokeDasharray="4 4"
                      />
                      <ReferenceLine
                        x={defaultCoefficient}
                        stroke="var(--muted)"
                        strokeDasharray="3 3"
                      />
                      <Tooltip
                        contentStyle={tooltip}
                        labelFormatter={(value) =>
                          `Coefficient ${fmt(value, 2)}`
                        }
                        formatter={(value) => [
                          marginCallLabel(Number(value)),
                          "Conditional margin",
                        ]}
                      />
                      <Line
                        dataKey="margin_pp"
                        stroke="var(--violet)"
                        strokeWidth={2.5}
                        dot={{ r: 3 }}
                        isAnimationActive={false}
                      />
                      <ReferenceDot
                        x={selected.coefficient}
                        y={selected.margin_pp}
                        r={6}
                        fill={directionColor(selected.margin_pp)}
                        stroke="var(--panel)"
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
                <p className="forecast-caption">
                  D/R labels show the sign and magnitude of the party margin.
                  Dashed zero is an even two-party margin. The vertical line
                  marks the model’s published default.
                </p>
              </div>
            </div>
            {!!sensitivity?.stress_tests?.length && (
              <div className="forecast-stress-grid">
                {sensitivity.stress_tests.map((stress, index) => (
                  <div key={`${stress.label}-${index}`}>
                    <span>{stress.label}</span>
                    <b style={{ color: directionColor(stress.margin_pp) }}>
                      {marginCallLabel(stress.margin_pp)}
                    </b>
                    <small>
                      {stress.delta_pp != null && stress.delta_pp > 0
                        ? "+"
                        : ""}
                      {fmt(stress.delta_pp, 2)} pp from configured point
                    </small>
                    <p>{stress.explanation}</p>
                  </div>
                ))}
              </div>
            )}
            <details>
              <summary>Every evaluated assumption and output</summary>
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Coefficient</th>
                      <th>EV adjustment</th>
                      <th>Conditional margin</th>
                    </tr>
                  </thead>
                  <tbody>
                    {points.map((point) => (
                      <tr
                        key={point.coefficient}
                        className={
                          point.coefficient === selected.coefficient
                            ? "selected"
                            : ""
                        }
                      >
                        <td>{fmt(point.coefficient, 3)}</td>
                        <td>{fmt(point.adjustment_pp, 3)} pp</td>
                        <td>{marginCallLabel(point.margin_pp, 3)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {sensitivity?.parameters.map((parameter) => (
                <p className="body-copy" key={parameter.id}>
                  <b>{parameter.label}.</b> {parameter.description} Range{" "}
                  {parameter.min}–{parameter.max} {parameter.unit}.
                </p>
              ))}
            </details>
          </>
        ) : (
          <Empty title="No supported EV assumption experiment is available">
            The source/model run has not supplied an evaluated sensitivity grid
            for this race. Historical-reference-only calls are not made to look
            EV-informed by adding a slider.
          </Empty>
        )}
        <ResearchGuide
          what="Service-evaluated model points across an explicit EV conversion assumption, with optional stress tests."
          how="Move the coefficient control to an evaluated point. Observe whether the sign changes and how far the point shifts. Stability across a limited assumption set does not test unmeasured candidate effects, late voters, turnout composition, or historical calibration."
          source={
            sensitivity?.range_kind
              ? human(sensitivity.range_kind)
              : "Exact versioned model response; no client-generated forecast outputs."
          }
        />
        <p className="forecast-caption">
          <AlertTriangle size={13} /> No polling or betting odds are used to
          make this sensitivity curve look more certain.
        </p>
      </Panel>
    </section>
  );
});
