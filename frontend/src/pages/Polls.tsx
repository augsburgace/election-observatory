import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { queryString, request } from "../api";
import { useViewOption } from "../viewState";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { BarChart3, FileSearch, Filter, Info, Search } from "lucide-react";
import type { AppContext, Poll } from "../types";
import {
  Badge,
  Empty,
  ExternalLink,
  Field,
  Notice,
  Panel,
  Select,
  Segmented,
  Stat,
} from "../components/ui";
import {
  COLORS,
  dateLabel,
  estimateName,
  estimateValue,
  fmt,
  human,
  partyColor,
  pct,
  stateName,
} from "../utils";
interface PollAnalysis {
  status: string;
  producer_count: number;
  averages: Record<string, number>;
  eligible: Poll[];
  excluded: { id?: number; study_id?: string; reason: string }[];
  series: {
    comparison_key: string;
    leave_one_producer_out: {
      excluded_producer: string;
      averages: Record<string, number>;
    }[];
  }[];
  warnings: string[];
}
export default function Polls(ctx: AppContext & { embedded?: boolean }) {
  const { workspace, query, bootstrap, inspect, embedded } = ctx;
  const [windowDays, setWindowDays] = useState(21);
  const [population, setPopulation] = useViewOption<string>(
    "poll_population",
    "LV",
  );
  const [questionType, setQuestionType] = useViewOption<string>(
    "poll_question",
    "vote_choice",
  );
  const [includePartisan, setIncludePartisan] = useState(true);
  const [search, setSearch] = useState("");
  const [view, setView] = useViewOption<"support" | "timeline" | "forest">(
    "poll_view",
    "support",
  );
  const polls = workspace.polls || [];
  const cutoff =
    query.as_of ||
    bootstrap.app?.today ||
    new Date().toISOString().slice(0, 10);
  const canonical = useQuery({
    queryKey: [
      "polling",
      workspace.query,
      windowDays,
      population,
      includePartisan,
      questionType,
    ],
    queryFn: () =>
      request<PollAnalysis>(
        `/polling?${queryString(workspace.query)}&window_days=${windowDays}&population=${population}&include_partisan=${includePartisan}&question_type=${questionType}`,
      ),
  });
  const analysis = {
    included: canonical.data?.eligible || [],
    excluded: (canonical.data?.excluded || []).map((entry) => ({
      poll: polls.find((p) =>
        entry.id ? p.id === entry.id : p.study_id === entry.study_id,
      ),
      reason: entry.reason,
    })),
    averages: Object.entries(canonical.data?.averages || {}).map(
      ([name, value]) => ({
        name,
        value,
        party: polls
          .flatMap((p) => p.estimates)
          .find((e) => estimateName(e) === name)?.party,
      }),
    ),
  };
  const filtered = polls
    .filter((p) =>
      `${p.producer} ${p.sponsor} ${p.question}`
        .toLowerCase()
        .includes(search.toLowerCase()),
    )
    .sort((a, b) => b.field_end.localeCompare(a.field_end));
  const names = [
    ...new Set(polls.flatMap((p) => p.estimates.map(estimateName))),
  ];
  const votePolls = polls.filter(
    (p) =>
      p.question_type === questionType &&
      p.ballot_type === "full_ballot" &&
      (p.population.toUpperCase() === population ||
        p.population
          .toLowerCase()
          .includes(population === "LV" ? "likely" : "registered")),
  );
  const chartPolls = filtered.filter(
    (p) =>
      p.question_type === questionType &&
      p.ballot_type === "full_ballot" &&
      (p.population.toUpperCase() === population ||
        p.population
          .toLowerCase()
          .includes(population === "LV" ? "likely" : "registered")),
  );
  const trajectories = votePolls
    .slice()
    .sort((a, b) => a.field_end.localeCompare(b.field_end))
    .map((p) =>
      Object.fromEntries([
        ["date", p.field_end],
        ["producer", p.producer],
        ...p.estimates.map((e) => [estimateName(e), estimateValue(e)]),
      ]),
    );
  const sensitivity = (
    canonical.data?.series?.length === 1
      ? canonical.data.series[0].leave_one_producer_out
      : []
  ).map((row) => ({
    producer: row.excluded_producer,
    values: Object.entries(row.averages || {}).map(([name, value]) => ({
      name,
      value,
    })),
  }));
  return (
    <>
      {!embedded && (
        <div className="page-intro">
          <div>
            <h2>Polling, with the methodology attached.</h2>
            <p>
              Original studies, complete response distributions, transparent
              inclusion rules, and sensitivity to your assumptions.
            </p>
          </div>
          <Badge tone="violet">
            <BarChart3 size={12} />
            {stateName(query.state)}
          </Badge>
        </div>
      )}
      <div className="poll-control-bar">
        <Field label="Fieldwork midpoint window">
          <Select
            value={windowDays}
            onChange={(v) => setWindowDays(Number(v))}
            label="Polling recency window"
            options={[7, 14, 21, 30, 60].map((d) => ({
              value: d,
              label: `Last ${d} days`,
            }))}
          />
        </Field>
        <Field label="Population">
          <Select
            value={population}
            onChange={setPopulation}
            label="Polling population"
            options={[
              { value: "LV", label: "Likely voters" },
              { value: "RV", label: "Registered voters" },
            ]}
          />
        </Field>
        <Field label="Question">
          <Select
            value={questionType}
            onChange={setQuestionType}
            label="Survey question type"
            options={[
              { value: "vote_choice", label: "Vote choice" },
              { value: "winner_expectation", label: "Winner expectations" },
            ]}
          />
        </Field>
        <label className="checkbox-label">
          <input
            type="checkbox"
            checked={includePartisan}
            onChange={(e) => setIncludePartisan(e.target.checked)}
          />
          Include partisan sponsors
        </label>
        <span className="table-count">Published by {dateLabel(cutoff)}</span>
      </div>
      <div className="stat-grid three">
        <Stat
          label="Original studies"
          value={new Set(polls.map((p) => p.study_id)).size}
          detail={`${polls.length} preserved survey questions / estimates`}
          icon={<FileSearch size={20} />}
          accent="violet"
        />
        <Stat
          label="Eligible independent producers"
          value={canonical.data?.producer_count || 0}
          detail={`Comparable ${population === "all" ? "survey" : population} studies in the selected window`}
          icon={<Filter size={20} />}
          accent="cyan"
        />
        <Stat
          label="Descriptive average"
          value={analysis.averages.length ? "Available" : "Withheld"}
          detail={
            analysis.averages.length
              ? "Simple mean · undecideds remain unallocated"
              : "Requires at least three comparable producers"
          }
          icon={<BarChart3 size={20} />}
          accent="gold"
        />
      </div>
      <div className="poll-main-grid">
        {canonical.isError && (
          <Notice tone="warning">{canonical.error.message}</Notice>
        )}
        <Panel
          title={
            questionType === "vote_choice"
              ? "Vote-choice evidence"
              : "Winner-expectation evidence"
          }
          subtitle={`${stateName(query.state)} · ${population} · ${human(questionType)} · full ballot`}
          actions={
            <Segmented
              value={view}
              onChange={setView}
              label="Polling chart"
              items={[
                { id: "support", label: "Support" },
                { id: "timeline", label: "Timeline" },
                { id: "forest", label: "Estimates" },
              ]}
            />
          }
          exportLabel={`${stateName(query.state)} polls · r${workspace.revision} · cutoff ${cutoff}`}
        >
          {!chartPolls.length ? (
            <Empty title="No verified original polls match these controls">
              Polling is populated from original producer releases and
              methodology documents. Source coverage remains visible while
              collection is incomplete.
            </Empty>
          ) : view === "timeline" ? (
            <div className="chart" style={{ height: 330 }}>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={trajectories}>
                  <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
                  <XAxis
                    dataKey="date"
                    tick={{ fontSize: 10, fill: "var(--muted)" }}
                    tickFormatter={(v) => String(v).slice(5)}
                  />
                  <YAxis
                    domain={[0, 100]}
                    tick={{ fontSize: 10, fill: "var(--muted)" }}
                    tickFormatter={(v) => `${v}%`}
                    width={42}
                  />
                  <Tooltip
                    contentStyle={{
                      background: "var(--popover)",
                      borderColor: "var(--border)",
                    }}
                  />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  {names.map((name, i) => (
                    <Line
                      key={name}
                      dataKey={name}
                      connectNulls={false}
                      stroke={COLORS[i % COLORS.length]}
                      strokeWidth={2}
                      dot={{ r: 4 }}
                      isAnimationActive={false}
                    />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            </div>
          ) : view === "forest" ? (
            <PollForest
              polls={chartPolls.slice(0, 12)}
              onInspect={(poll) =>
                inspect({
                  type: "poll",
                  id: poll.id || poll.study_id,
                  data: poll,
                })
              }
            />
          ) : (
            <div className="poll-support-list">
              {chartPolls.slice(0, 10).map((poll) => (
                <div
                  key={
                    poll.id ||
                    `${poll.study_id}-${poll.population}-${poll.question_type}`
                  }
                  className="poll-support-row"
                >
                  <button
                    className="poll-producer"
                    onClick={() =>
                      inspect({
                        type: "poll",
                        id: poll.id || poll.study_id,
                        data: poll,
                      })
                    }
                  >
                    <b>{poll.producer}</b>
                    <span>
                      {dateLabel(poll.field_end)} · {poll.population} · n=
                      {fmt(poll.sample_size)}
                    </span>
                  </button>
                  <div className="poll-share-stack">
                    {poll.estimates
                      .filter((estimate) =>
                        Number.isFinite(estimateValue(estimate)),
                      )
                      .map((estimate, i) => (
                        <div
                          key={estimateName(estimate)}
                          style={{
                            width: `${estimateValue(estimate)}%`,
                            background: estimate.party
                              ? partyColor(estimate.party)
                              : COLORS[i % COLORS.length],
                          }}
                          title={`${estimateName(estimate)} ${pct(estimateValue(estimate))}`}
                        >
                          {estimateValue(estimate) >= 9 && (
                            <span>
                              {estimateName(estimate).split(" ").at(-1)}{" "}
                              {pct(estimateValue(estimate), 0)}
                            </span>
                          )}
                        </div>
                      ))}
                  </div>
                  <button
                    className="icon-button"
                    onClick={() =>
                      inspect({
                        type: "poll",
                        id: poll.id || poll.study_id,
                        data: poll,
                      })
                    }
                    aria-label={`Inspect ${poll.producer}`}
                  >
                    <FileSearch size={15} />
                  </button>
                </div>
              ))}
            </div>
          )}
        </Panel>
        <Panel
          title={
            questionType === "vote_choice"
              ? "Descriptive vote-choice average"
              : "Descriptive expectation average"
          }
          subtitle="Latest comparable study per producer · simple arithmetic mean."
          className="poll-average-panel"
        >
          {analysis.averages.length ? (
            <>
              <div className="chart" style={{ height: 250 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart
                    data={analysis.averages}
                    layout="vertical"
                    margin={{ right: 30, left: 0 }}
                  >
                    <XAxis
                      type="number"
                      domain={[0, 100]}
                      tickFormatter={(v) => `${v}%`}
                      tick={{ fontSize: 10, fill: "var(--muted)" }}
                    />
                    <YAxis
                      type="category"
                      dataKey="name"
                      width={90}
                      tick={{ fontSize: 11, fill: "var(--muted)" }}
                    />
                    <Tooltip
                      contentStyle={{
                        background: "var(--popover)",
                        borderColor: "var(--border)",
                      }}
                      formatter={(v) => pct(Number(v))}
                    />
                    <Bar dataKey="value" maxBarSize={24} radius={[0, 3, 3, 0]}>
                      {analysis.averages.map((e, i) => (
                        <Cell
                          key={e.name}
                          fill={
                            e.party
                              ? partyColor(e.party)
                              : COLORS[i % COLORS.length]
                          }
                        />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <div className="average-values">
                {analysis.averages.map((a) => (
                  <div key={a.name}>
                    <span>{a.name}</span>
                    <b>{pct(a.value)}</b>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <Empty title="An average would imply too much precision">
              {analysis.included.length} comparable producer
              {analysis.included.length === 1 ? "" : "s"} meet the current
              filters. Three is the minimum display threshold, not a guarantee
              of reliability.
            </Empty>
          )}
          <Notice>
            These estimates describe surveys. Early-ballot registration and
            demographics are never substituted for candidate preferences.
          </Notice>
        </Panel>
      </div>
      <Panel
        title="Original survey inventory"
        subtitle="Open a study to inspect its exact question, methodology, dates, and original release."
      >
        <div className="table-toolbar">
          <div className="search-field">
            <Search size={14} />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search producer, sponsor, question…"
              aria-label="Search polling inventory"
            />
          </div>
          <span className="table-count">
            {filtered.length} questions / estimates
          </span>
        </div>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Producer / publisher</th>
                <th>Fieldwork</th>
                <th>Population</th>
                <th>Sample</th>
                <th>Sponsor</th>
                <th>Question</th>
                <th>Eligibility</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {filtered.map((poll) => {
                const excluded = analysis.excluded.find(
                  (e) =>
                    e.poll?.id === poll.id &&
                    e.poll?.study_id === poll.study_id,
                );
                return (
                  <tr
                    key={
                      poll.id ||
                      `${poll.study_id}-${poll.population}-${poll.question_type}`
                    }
                  >
                    <td>
                      <button
                        className="text-button"
                        onClick={() =>
                          inspect({
                            type: "poll",
                            id: poll.id || poll.study_id,
                            data: poll,
                          })
                        }
                      >
                        {poll.producer}
                      </button>
                      <small>{poll.publisher}</small>
                    </td>
                    <td>
                      {dateLabel(poll.field_start)}
                      <small>to {dateLabel(poll.field_end)}</small>
                    </td>
                    <td>{poll.population}</td>
                    <td>{fmt(poll.sample_size)}</td>
                    <td>
                      {poll.sponsor}
                      {poll.partisan_sponsor && (
                        <small className="amber-text">
                          Partisan sponsorship
                        </small>
                      )}
                    </td>
                    <td>
                      {human(poll.question_type)}
                      <small>{human(poll.ballot_type)}</small>
                    </td>
                    <td>
                      <Badge tone={excluded ? "muted" : "teal"}>
                        {canonical.isPending
                          ? "Checking"
                          : excluded
                            ? "Excluded"
                            : analysis.included.some((p) => p.id === poll.id)
                              ? "Eligible"
                              : "Separate question"}
                      </Badge>
                      {excluded && <small>{excluded.reason}</small>}
                    </td>
                    <td>
                      <ExternalLink href={poll.document_url || poll.source_url}>
                        Original
                      </ExternalLink>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {!filtered.length && (
            <Empty title="No surveys match">
              Change the search or inspect original-source coverage.
            </Empty>
          )}
        </div>
      </Panel>
      <div className="chart-grid">
        <Panel
          title="Leave-one-producer-out sensitivity"
          subtitle="How much does the descriptive average depend on one producer?"
        >
          {sensitivity.length && analysis.averages.length ? (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Omitted producer</th>
                    {analysis.averages.map((a) => (
                      <th key={a.name}>{a.name}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {sensitivity.map((row) => (
                    <tr key={row.producer}>
                      <td>{row.producer}</td>
                      {row.values.map((v) => (
                        <td key={v.name}>{pct(v.value)}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <Empty title="Sensitivity follows sufficient coverage">
              At least three independent comparable producers are needed to form
              the displayed baseline average.
            </Empty>
          )}
        </Panel>
        <Panel
          title="Published subgroup evidence"
          subtitle="Crosstabs retain their published sample limitations."
        >
          {chartPolls.some((p) => p.crosstabs?.length) ? (
            chartPolls
              .filter((p) => p.crosstabs?.length)
              .map((p) => (
                <details
                  key={
                    p.id || `${p.study_id}-${p.population}-${p.question_type}`
                  }
                  className="crosstab-details"
                >
                  <summary>
                    {p.producer} · {dateLabel(p.field_end)}
                  </summary>
                  <pre className="json-view">
                    {JSON.stringify(p.crosstabs, null, 2)}
                  </pre>
                </details>
              ))
          ) : (
            <Empty title="No published crosstabs archived">
              Subgroup estimates appear only when original releases provide
              them. No joint distributions are inferred from separate totals.
            </Empty>
          )}
        </Panel>
      </div>
      <Notice>
        <Info size={12} />
        Reported sampling margins are not a complete measure of polling error.
        Candidate-margin uncertainty is not automatically equal to a poll's
        reported candidate-share margin of error.
      </Notice>
    </>
  );
}
function PollForest({
  polls,
  onInspect,
}: {
  polls: Poll[];
  onInspect: (p: Poll) => void;
}) {
  const height = Math.max(240, polls.length * 70);
  return (
    <div className="forest-wrap">
      <svg
        viewBox={`0 0 800 ${height}`}
        className="poll-forest"
        role="img"
        aria-label="Individual candidate support estimates and disclosed nominal sampling margins"
      >
        {[0, 25, 50, 75, 100].map((v) => (
          <g key={v}>
            <line
              x1={220 + v * 5.1}
              x2={220 + v * 5.1}
              y1={15}
              y2={height - 25}
              stroke="var(--chart-grid)"
              strokeDasharray={v === 50 ? "4 3" : undefined}
            />
            <text x={220 + v * 5.1} y={height - 5} textAnchor="middle">
              {v}%
            </text>
          </g>
        ))}
        {polls.map((poll, i) => (
          <g
            key={
              poll.id ||
              `${poll.study_id}-${poll.population}-${poll.question_type}`
            }
            transform={`translate(0,${35 + i * 70})`}
            onClick={() => onInspect(poll)}
            role="button"
            tabIndex={0}
            aria-label={`Inspect ${poll.producer}`}
            onKeyDown={(e) => e.key === "Enter" && onInspect(poll)}
          >
            <text x={8} y={0} className="forest-producer">
              {poll.producer}
            </text>
            <text x={8} y={16}>
              {poll.field_end} · {poll.population}
            </text>
            {poll.estimates
              .filter((e) => estimateValue(e) > 10)
              .slice(0, 3)
              .map((estimate, j) => {
                const x = 220 + estimateValue(estimate) * 5.1;
                const moe = poll.margin_of_error;
                const color = estimate.party
                  ? partyColor(estimate.party)
                  : COLORS[j];
                return (
                  <g
                    key={estimateName(estimate)}
                    transform={`translate(0,${j * 12 - 6})`}
                  >
                    {moe != null && (
                      <line
                        x1={x - moe * 5.1}
                        x2={x + moe * 5.1}
                        stroke={color}
                        strokeWidth={2}
                      />
                    )}
                    <circle cx={x} r={4.5} fill={color} />
                    <title>
                      {estimateName(estimate)}: {estimateValue(estimate)}%
                      {moe == null ? "" : `; disclosed poll MOE ±${moe} pp`}
                    </title>
                  </g>
                );
              })}
          </g>
        ))}
      </svg>
      <p className="chart-axis-note">
        Points = reported support · Bands = disclosed nominal survey MOE, where
        available
      </p>
    </div>
  );
}
