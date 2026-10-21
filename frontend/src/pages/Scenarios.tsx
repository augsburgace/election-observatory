import { useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  Copy,
  FlaskConical,
  RotateCcw,
  Save,
  SlidersHorizontal,
  Vote,
} from "lucide-react";
import type { AppContext, ResearchObject } from "../types";
import { api, downloadData } from "../api";
import {
  Badge,
  Datum,
  Empty,
  Field,
  Loading,
  Notice,
  Panel,
  Stat,
} from "../components/ui";
import { compact, fmt, pct, stateName } from "../utils";
type Params = {
  final_turnout: number;
  early_share: number;
  early_support: number;
  election_day_support: number;
  undecided_share: number;
  undecided_allocation: number;
};
function asPercent(value: unknown) {
  return typeof value === "number" ? value : undefined;
}
export default function Scenarios(ctx: AppContext & { embedded?: boolean }) {
  const { workspace, query, bootstrap, notify, embedded } = ctx;
  const cache = useQueryClient();
  const observed =
    ["ballots_cast", "ballots_accepted"].includes(query.metric) &&
    workspace.summary?.unit === "ballots" &&
    typeof workspace.summary?.total === "number"
      ? workspace.summary.total
      : 0;
  const defaults: Params = {
    final_turnout: Math.max(
      1_000_000,
      Math.ceil((observed * 3) / 10000) * 10000,
    ),
    early_share: 0.6,
    early_support: 0.5,
    election_day_support: 0.5,
    undecided_share: 0,
    undecided_allocation: 0.5,
  };
  const [params, setParams] = useState<Params>(defaults);
  const [debounced, setDebounced] = useState(params);
  const [title, setTitle] = useState("");
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    setParams(defaults);
    setTitle("");
  }, [query.state]);
  useEffect(() => {
    const timeout = setTimeout(() => setDebounced(params), 400);
    return () => clearTimeout(timeout);
  }, [params]);
  const requested = {
    state: query.state,
    revision: workspace.revision,
    query: workspace.query,
    observed_ballots: observed,
    ...debounced,
  };
  const result = useQuery({
    queryKey: ["scenario", requested],
    queryFn: () => api.scenario(requested),
    retry: false,
  });
  const research = useQuery({ queryKey: ["research"], queryFn: api.research });
  const items = research.data
    ? Array.isArray(research.data)
      ? research.data
      : research.data.items
    : [];
  const saved = items.filter(
    (item) =>
      item.kind === "scenario" &&
      (item.view?.state === query.state ||
        (item.view?.query &&
          (item.view.query as Record<string, unknown>).state === query.state)),
  );
  useEffect(() => {
    const id = Number(new URLSearchParams(location.search).get("research_id"));
    const item = items.find((row) => row.id === id && row.kind === "scenario");
    if (item?.view?.parameters) {
      setParams(item.view.parameters as Params);
      setTitle(item.title);
    }
  }, [research.data]);
  const output = result.data;
  const candidateAVotes =
    output?.candidate_a_votes ??
    (output?.projected_votes as Record<string, unknown> | undefined)
      ?.candidate_a;
  const candidateBVotes =
    output?.candidate_b_votes ??
    (output?.projected_votes as Record<string, unknown> | undefined)
      ?.candidate_b;
  const share = asPercent(output?.candidate_a_share);
  const margin = typeof output?.margin === "number" ? output.margin : undefined;
  const components = Array.isArray(output?.components)
    ? (output.components as Record<string, unknown>[])
    : [];
  const grid = Array.isArray(output?.grid)
    ? (output.grid as Record<string, unknown>[])
    : [];
  const race = bootstrap.races.find((r) => r.state === query.state);
  const candidates = race?.candidates || [];
  const candidateA = candidates[0]?.name || "Candidate A";
  const candidateB = candidates[1]?.name || "Candidate B";
  const earlyExpected = params.final_turnout * params.early_share;
  const invalid = earlyExpected < observed || params.final_turnout < observed;
  function set(key: keyof Params, value: number) {
    setParams((current) => ({ ...current, [key]: value }));
  }
  async function saveScenario() {
    setSaving(true);
    try {
      await api.saveResearch({
        kind: "scenario",
        title:
          title.trim() ||
          `${stateName(query.state)} · ${compact(params.final_turnout)} turnout scenario`,
        body: "Explicit hypothetical assumptions; this is not a forecast.",
        view: {
          state: query.state,
          query: workspace.query,
          page: "scenarios",
          parameters: params,
          result: output,
        },
      });
      cache.invalidateQueries({ queryKey: ["research"] });
      notify("Scenario and evidence revision saved.");
    } catch (e) {
      notify((e as Error).message);
    } finally {
      setSaving(false);
    }
  }
  function loadSaved(item: ResearchObject) {
    const p = item.view?.parameters as Params | undefined;
    if (p) {
      setParams(p);
      setTitle(`${item.title} · copy`);
      notify(
        "Saved assumptions loaded. Calculating against this evidence view.",
      );
    }
  }
  const outcomeBars = useMemo(
    () => [
      { name: candidateA, value: Number(candidateAVotes) },
      { name: candidateB, value: Number(candidateBVotes) },
    ],
    [candidateAVotes, candidateBVotes, candidateA, candidateB],
  );
  return (
    <>
      {!embedded && (
        <div className="page-intro">
          <div>
            <h2>Explore what would have to be true.</h2>
            <p>
              Adjust explicit turnout and support assumptions. Every result is
              conditional, and every assumption remains visible.
            </p>
          </div>
          <Badge tone="gold">
            <FlaskConical size={12} />
            Scenario laboratory
          </Badge>
        </div>
      )}
      <Notice tone="warning">
        Scenario outputs are hypothetical. Early ballots do not reveal candidate
        choice. Support levels below are your assumptions for all early voters,
        including ballots already observed.
      </Notice>
      <div className="scenario-layout">
        <Panel
          title="Your assumptions"
          subtitle={`${stateName(query.state)} · evidence revision ${workspace.revision}`}
          actions={
            <button
              className="icon-button"
              aria-label="Reset scenario assumptions"
              onClick={() => setParams(defaults)}
            >
              <RotateCcw size={15} />
            </button>
          }
          className="scenario-controls"
        >
          <div className="observed-context">
            <Vote size={18} />
            <div>
              <span>Observed cast / accepted ballots</span>
              <b>{fmt(observed)}</b>
            </div>
          </div>
          <SliderField
            label="Final turnout"
            value={params.final_turnout}
            min={Math.max(1, observed)}
            max={Math.max(5_000_000, params.final_turnout * 1.2, observed * 5)}
            step={1000}
            onChange={(v) => set("final_turnout", v)}
            explanation="Hypothetical final participation across all voting methods."
          />
          <SliderField
            label="Early share of final turnout"
            value={params.early_share}
            min={0}
            max={1}
            step={0.01}
            onChange={(v) => set("early_share", v)}
            percent
            explanation="Includes already observed ballots and additional expected early participation."
          />
          <SliderField
            label={`${candidateA} · early-vote support`}
            value={params.early_support}
            min={0}
            max={1}
            step={0.005}
            onChange={(v) => set("early_support", v)}
            percent
            explanation="Assumed support among all early voters; not inferred from registration."
          />
          <SliderField
            label={`${candidateA} · Election Day support`}
            value={params.election_day_support}
            min={0}
            max={1}
            step={0.005}
            onChange={(v) => set("election_day_support", v)}
            percent
            explanation="Assumed support among voters participating on Election Day."
          />
          <SliderField
            label="Undecided share"
            value={params.undecided_share}
            min={0}
            max={0.5}
            step={0.005}
            onChange={(v) => set("undecided_share", v)}
            percent
            explanation="Explicit undecided component of the hypothetical electorate."
          />
          <SliderField
            label="Undecideds allocated to candidate A"
            value={params.undecided_allocation}
            min={0}
            max={1}
            step={0.01}
            onChange={(v) => set("undecided_allocation", v)}
            percent
            explanation="Allocation assumption; changing it is a scenario, not measured movement."
          />
          {invalid && (
            <Notice tone="warning">
              Expected early participation cannot be lower than the observed
              ballot count. Increase turnout or the early-vote share.
            </Notice>
          )}
        </Panel>
        <div className="scenario-results">
          {result.isPending ? (
            <Loading label="Calculating conditional outcomes…" />
          ) : result.isError ? (
            <Notice tone="warning">{result.error.message}</Notice>
          ) : (
            <>
              <div className="stat-grid three">
                <Stat
                  label={`${candidateA} share`}
                  value={pct(share)}
                  detail="Conditional on your assumptions"
                  icon={<SlidersHorizontal size={20} />}
                  accent="cyan"
                />
                <Stat
                  label="Scenario margin"
                  value={
                    margin == null
                      ? "—"
                      : `${margin > 0 ? "+" : ""}${fmt(margin, 2)} pp`
                  }
                  detail="Candidate A minus candidate B"
                  icon={<FlaskConical size={20} />}
                  accent="violet"
                />
                <Stat
                  label="Remaining participation"
                  value={compact(output?.remaining_ballots)}
                  detail="Hypothetical ballots beyond observed totals"
                  icon={<Vote size={20} />}
                  accent="gold"
                />
              </div>
              <Panel
                title="Conditional vote allocation"
                subtitle="Two-candidate hypothetical allocation; counting rules require separate assumptions."
                exportLabel={`Scenario · ${query.state} · r${workspace.revision} · assumptions attached`}
              >
                <div className="chart" style={{ height: 245 }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart
                      data={outcomeBars}
                      layout="vertical"
                      margin={{ left: 0, right: 25 }}
                    >
                      <CartesianGrid
                        stroke="var(--chart-grid)"
                        horizontal={false}
                      />
                      <XAxis
                        type="number"
                        tickFormatter={compact}
                        tick={{ fill: "var(--muted)", fontSize: 10 }}
                      />
                      <YAxis
                        type="category"
                        dataKey="name"
                        width={110}
                        tick={{ fill: "var(--muted)", fontSize: 11 }}
                      />
                      <Tooltip
                        contentStyle={{
                          background: "var(--popover)",
                          borderColor: "var(--border)",
                        }}
                        formatter={(v) => fmt(v)}
                      />
                      <Bar
                        dataKey="value"
                        maxBarSize={35}
                        radius={[0, 4, 4, 0]}
                      >
                        <Cell fill="var(--cyan)" />
                        <Cell fill="var(--violet)" />
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
                <div className="datum-grid three">
                  <Datum
                    label="Assumed early ballots"
                    value={output?.early_ballots ?? earlyExpected}
                  />
                  <Datum
                    label="Assumed Election Day ballots"
                    value={
                      output?.election_day_ballots ??
                      params.final_turnout - earlyExpected
                    }
                  />
                  <Datum
                    label="Final turnout assumption"
                    value={params.final_turnout}
                  />
                </div>
              </Panel>
              <Panel
                title="Outcome sensitivity surface"
                subtitle="Explore combinations of turnout and remaining-voter support; each cell is a scenario."
              >
                {grid.length ? (
                  <ScenarioGrid grid={grid} />
                ) : (
                  <Empty title="Sensitivity grid is unavailable">
                    The calculation engine has not returned compatible parameter
                    combinations.
                  </Empty>
                )}
              </Panel>
              {Array.isArray(output?.sensitivity) &&
                output.sensitivity.length > 0 && (
                  <Panel
                    title="Which assumptions move the result?"
                    subtitle="One-at-a-time changes around this scenario; values are conditional margins."
                    exportLabel={`Scenario sensitivity · ${query.state} · r${workspace.revision}`}
                  >
                    <SensitivityChart
                      rows={output.sensitivity as Record<string, unknown>[]}
                      margin={margin || 0}
                    />
                  </Panel>
                )}
              {components.length > 0 && (
                <Panel title="Contribution by voting component">
                  <div className="table-scroll">
                    <table>
                      <thead>
                        <tr>
                          {Object.keys(components[0]).map((key) => (
                            <th key={key}>{key.replaceAll("_", " ")}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {components.map((row, i) => (
                          <tr key={i}>
                            {Object.values(row).map((v, j) => (
                              <td key={j}>
                                {typeof v === "number" ? fmt(v, 2) : String(v)}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </Panel>
              )}
              {Array.isArray(output?.warnings) &&
                output.warnings.map((w, i) => (
                  <Notice key={i} tone="warning">
                    {String(w)}
                  </Notice>
                ))}
            </>
          )}
        </div>
      </div>
      <Panel
        title="Save and compare assumptions"
        subtitle="Scenarios remain separate from observed evidence and calibrated forecasts."
      >
        <div className="scenario-save-row">
          <Field label="Scenario name">
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder={`${stateName(query.state)} turnout hypothesis`}
            />
          </Field>
          <button
            className="button primary"
            disabled={saving || !output || invalid}
            onClick={saveScenario}
          >
            <Save size={14} />
            {saving ? "Saving…" : "Save scenario"}
          </button>
          <button
            className="button secondary"
            disabled={!output}
            onClick={() =>
              downloadData(
                { query, parameters: params, result: output },
                `scenario-${query.state}-r${workspace.revision}.json`,
              )
            }
          >
            Export assumptions & result
          </button>
        </div>
        {saved.length > 0 && (
          <div className="saved-scenarios">
            {saved.map((item) => (
              <button key={item.id} onClick={() => loadSaved(item)}>
                <Copy size={16} />
                <div>
                  <b>{item.title}</b>
                  <span>
                    {item.created_at?.slice(0, 10)} · Load as a new comparison
                  </span>
                </div>
              </button>
            ))}
          </div>
        )}
        {saved.length > 1 && <ScenarioComparison items={saved} />}
      </Panel>
    </>
  );
}
function SliderField({
  label,
  value,
  min,
  max,
  step,
  onChange,
  explanation,
  percent = false,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (v: number) => void;
  explanation: string;
  percent?: boolean;
}) {
  return (
    <div className="slider-field">
      <div className="slider-label">
        <label>{label}</label>
        <div>
          <input
            aria-label={`${label} numeric value`}
            type="number"
            min={percent ? min * 100 : min}
            max={percent ? max * 100 : max}
            step={percent ? step * 100 : 1}
            value={percent ? Number((value * 100).toFixed(2)) : value}
            onChange={(e) => {
              const next = Number(e.target.value) / (percent ? 100 : 1);
              if (Number.isFinite(next)) onChange(next);
            }}
          />
          {percent && <span>%</span>}
        </div>
      </div>
      <input
        aria-label={label}
        type="range"
        min={min}
        max={max}
        step={percent ? step : 1}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
      />
      <small>{explanation}</small>
    </div>
  );
}
function ScenarioGrid({ grid }: { grid: Record<string, unknown>[] }) {
  const xs = [
    ...new Set(
      grid.map((r) =>
        Number(
          r.remaining_candidate_share ?? r.election_day_support ?? r.support,
        ),
      ),
    ),
  ].sort((a, b) => a - b);
  const ys = [
    ...new Set(grid.map((r) => Number(r.turnout ?? r.final_turnout))),
  ].sort((a, b) => a - b);
  const max = Math.max(...grid.map((r) => Math.abs(Number(r.margin))), 1);
  return (
    <div className="scenario-grid-wrap">
      <table className="scenario-heatmap">
        <thead>
          <tr>
            <th>Turnout / support</th>
            {xs.map((x) => (
              <th key={x}>{pct(x <= 1 ? x * 100 : x, 0)}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {ys.map((y) => (
            <tr key={y}>
              <th>{compact(y)}</th>
              {xs.map((x) => {
                const row = grid.find(
                  (r) =>
                    Number(r.turnout ?? r.final_turnout) === y &&
                    Number(
                      r.remaining_candidate_share ??
                        r.election_day_support ??
                        r.support,
                    ) === x,
                );
                const margin = Number(row?.margin);
                return (
                  <td
                    key={x}
                    title={`Turnout ${fmt(y)}, support ${x}, margin ${fmt(margin, 2)} pp`}
                    style={
                      row
                        ? {
                            background:
                              margin >= 0
                                ? `rgba(37,207,212,${0.12 + (Math.abs(margin) / max) * 0.5})`
                                : `rgba(170,123,250,${0.12 + (Math.abs(margin) / max) * 0.5})`,
                          }
                        : {}
                    }
                  >
                    {row ? `${margin > 0 ? "+" : ""}${fmt(margin, 1)}` : "—"}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <div className="chart-axis-note">
        Margin in percentage points · Colors indicate conditional advantage, not
        probabilities
      </div>
    </div>
  );
}

function SensitivityChart({
  rows,
  margin,
}: {
  rows: Record<string, unknown>[];
  margin: number;
}) {
  const max = Math.max(
    1,
    ...rows.flatMap((row) => [
      Math.abs(Number(row.low_margin) - margin),
      Math.abs(Number(row.high_margin) - margin),
    ]),
  );
  const width = 700;
  const center = 430;
  const plot = 220;
  return (
    <svg
      className="poll-forest"
      viewBox={`0 0 ${width} ${rows.length * 58 + 40}`}
      role="img"
      aria-label="Conditional scenario sensitivity by assumption"
    >
      <line
        x1={center}
        x2={center}
        y1={8}
        y2={rows.length * 58 + 5}
        stroke="var(--border-strong)"
        strokeDasharray="4 3"
      />
      {rows.map((row, i) => {
        const low = Number(row.low_margin),
          high = Number(row.high_margin);
        const a = center + ((low - margin) / max) * plot,
          b = center + ((high - margin) / max) * plot;
        return (
          <g
            key={String(row.parameter)}
            transform={`translate(0,${i * 58 + 28})`}
          >
            <text x={0} y={0}>
              {String(row.parameter).replaceAll("_", " ")}
            </text>
            <text x={0} y={17}>
              {(Number(row.low) * 100).toFixed(1)}% →{" "}
              {(Number(row.high) * 100).toFixed(1)}%
            </text>
            <line
              x1={Math.min(a, b)}
              x2={Math.max(a, b)}
              stroke="var(--violet)"
              strokeWidth={14}
              strokeLinecap="round"
            />
            <circle cx={a} r={4} fill="var(--cyan)" />
            <circle cx={b} r={4} fill="var(--gold)" />
            <text x={width - 10} y={4} textAnchor="end">
              {fmt(low, 1)} to {fmt(high, 1)} pp
            </text>
          </g>
        );
      })}
      <text x={center} y={rows.length * 58 + 30} textAnchor="middle">
        Current margin {fmt(margin, 1)} pp
      </text>
    </svg>
  );
}
function ScenarioComparison({ items }: { items: ResearchObject[] }) {
  return (
    <div className="table-scroll scenario-comparison">
      <table>
        <thead>
          <tr>
            <th>Saved scenario</th>
            <th>Turnout</th>
            <th>Early share</th>
            <th>Early A support</th>
            <th>Election Day A support</th>
            <th>A share</th>
            <th>Margin</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => {
            const params = item.view?.parameters as Params | undefined;
            const result = item.view?.result as
              Record<string, unknown> | undefined;
            return (
              <tr key={item.id}>
                <td>{item.title}</td>
                <td>{compact(params?.final_turnout)}</td>
                <td>{params ? pct(params.early_share * 100) : "—"}</td>
                <td>{params ? pct(params.early_support * 100) : "—"}</td>
                <td>{params ? pct(params.election_day_support * 100) : "—"}</td>
                <td>{pct(result?.candidate_a_share)}</td>
                <td>{fmt(result?.margin, 1)} pp</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
