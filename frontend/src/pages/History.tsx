import { useEffect, useRef, useState } from "react";
import {
  CalendarDays,
  ChevronLeft,
  ChevronRight,
  Clock3,
  Pause,
  Play,
  RotateCcw,
} from "lucide-react";
import type { AppContext } from "../types";
import { ChangeChart, SeriesChart } from "../components/Charts";
import {
  Badge,
  Datum,
  Empty,
  Field,
  Notice,
  Panel,
  Select,
} from "../components/ui";
import { dateLabel, fmt, human, stateName } from "../utils";
import ParticipationDepth from "../components/ParticipationDepth";
export default function History(ctx: AppContext & { embedded?: boolean }) {
  const { workspace, query, setQuery, embedded } = ctx;
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState("1500");
  const fullDates = useRef<string[]>([]);
  const familyRef = useRef("");
  const family = [
    query.state,
    query.cycle,
    query.metric,
    query.mode,
    query.time_basis,
    query.geography_ids.join(","),
  ].join("|");
  const current = (workspace.series || []).filter(
    (p) => p.cycle === query.cycle,
  );
  const received = [...new Set(current.map((p) => p.date))].sort();
  if (
    familyRef.current !== family ||
    received.length > fullDates.current.length ||
    fullDates.current.some((d) => d.slice(0, 4) !== String(query.cycle))
  )
    fullDates.current = received;
  familyRef.current = family;
  const dates = fullDates.current;
  const index = query.as_of
    ? Math.max(
        0,
        dates.reduce((found, d, i) => (d <= query.as_of ? i : found), -1),
      )
    : Math.max(0, dates.length - 1);
  const indexRef = useRef(index);
  indexRef.current = index;
  useEffect(() => {
    if (!playing) return;
    const timer = setInterval(() => {
      const next = indexRef.current + 1;
      if (next >= dates.length) {
        setPlaying(false);
        return;
      }
      setQuery({ as_of: dates[next] });
    }, Number(speed));
    return () => clearInterval(timer);
  }, [playing, speed, dates.join("|"), setQuery]);
  useEffect(() => setPlaying(false), [query.state, query.cycle]);
  function move(i: number) {
    setPlaying(false);
    if (dates[i]) setQuery({ as_of: dates[i] });
  }
  const baseline = workspace.summary?.baseline_total;
  const currentTotal = workspace.summary?.total;
  const pace = workspace.summary?.pace_ratio;
  const comparison = workspace.comparison ?? {};
  const asynchronous = comparison.asynchronous === true;
  const matchedCount = typeof comparison.matched_count === "number" ? comparison.matched_count : null;
  const comparisonReason = typeof comparison.reason === "string" ? comparison.reason : "";
  const baselineDates = Array.isArray(comparison.geographies)
    ? [...new Set(comparison.geographies.map((row) => row.baseline_date).filter((date): date is string => typeof date === "string"))].sort()
    : [];
  const exportLabel = `${stateName(query.state)} · ${query.cycle} vs ${query.baseline} · ${query.alignment} · r${workspace.revision}`;
  const historical = (workspace.observations || []).filter(
    (o) => o.cycle !== query.cycle,
  );
  return (
    <>
      {!embedded && (
        <div className="page-intro">
          <div>
            <h2>History, on the same terms.</h2>
            <p>
              Align cycles, replay actual observations, and inspect where
              differences in the evidence matter.
            </p>
          </div>
          <Badge tone="violet">
            <Clock3 size={12} />
            Historical workbench
          </Badge>
        </div>
      )}
      <div className="history-control-grid">
        <Field label="Alignment">
          <Select
            label="Historical alignment"
            value={query.alignment}
            onChange={(alignment) => setQuery({ alignment })}
            options={[
              { value: "days_to_election", label: "Days until Election Day" },
              { value: "calendar", label: "Source calendar date" },
              {
                value: "days_since_opening",
                label: "Days since voting opened",
              },
              {
                value: "voting_opportunities",
                label: "Equivalent documented voting opportunities",
              },
            ]}
          />
        </Field>
        <Field label="Evidence chronology">
          <Select
            value={query.time_basis}
            onChange={(v) =>
              setQuery({
                time_basis: v as "reported" | "reconstructed" | "final",
              })
            }
            label="Historical chronology"
            options={[
              { value: "reported", label: "As reported at the cutoff" },
              { value: "reconstructed", label: "Reconstructed after the fact" },
              { value: "final", label: "Final official totals" },
            ]}
          />
        </Field>
        <div className="history-current">
          <span>Current comparison</span>
          <b>
            {query.cycle}
            <span>↔</span>
            {query.baseline}
          </b>
          <small>
            {query.baseline === 2020 || query.baseline === 2024
              ? "Presidential-cycle context"
              : "Midterm-cycle comparison"}
          </small>
        </div>
      </div>
      <Notice>
        {query.time_basis === "reported"
          ? "As-reported history includes only information demonstrably available by the cutoff. Reports first discovered later cannot be silently backdated."
          : query.time_basis === "reconstructed"
            ? "Reconstructed history can group later records by event date. It does not establish what election officials had reported at that time."
            : "Final records describe completed official reporting. They are endpoint references rather than daily evidence."}
      </Notice>
      <Panel
        title={`${stateName(query.state)} · participation over time`}
        subtitle="A shared date cursor coordinates the selected evidence cutoff."
        exportLabel={exportLabel}
      >
        <SeriesChart
          series={workspace.series}
          observations={workspace.observations}
          alignment={query.alignment}
          cutoff={query.as_of}
          height={360}
          brush
          onRange={(start, end) => setQuery({ date_window: [start, end] })}
        />
        {!!query.date_window?.length && (
          <div className="history-advanced-toggle">
            <span>
              Shared reporting window: {query.date_window.join(" → ")}
            </span>
            <button
              className="button small secondary"
              onClick={() => setQuery({ date_window: [] })}
            >
              Show the full reporting window
            </button>
          </div>
        )}
        <div className="playback-controls">
          <div className="playback-buttons">
            <button
              className="icon-button"
              aria-label="Previous observation"
              disabled={index <= 0}
              onClick={() => move(index - 1)}
            >
              <ChevronLeft size={19} />
            </button>
            <button
              className="play-button"
              aria-label={
                playing
                  ? "Pause historical playback"
                  : "Play historical observations"
              }
              disabled={dates.length < 2}
              onClick={() => {
                if (!playing && index >= dates.length - 1)
                  setQuery({ as_of: dates[0] });
                setPlaying(!playing);
              }}
            >
              {playing ? <Pause size={19} /> : <Play size={19} />}
            </button>
            <button
              className="icon-button"
              aria-label="Next observation"
              disabled={index >= dates.length - 1}
              onClick={() => move(index + 1)}
            >
              <ChevronRight size={19} />
            </button>
          </div>
          <div className="playback-scrub">
            <div>
              <span>Observation cutoff</span>
              <b>
                {dates[index] ? dateLabel(dates[index]) : "No observations"}
              </b>
            </div>
            <input
              type="range"
              min={0}
              max={Math.max(0, dates.length - 1)}
              value={Math.min(index, Math.max(0, dates.length - 1))}
              disabled={dates.length < 2}
              aria-label="Historical observation"
              onChange={(e) => move(Number(e.target.value))}
            />
            <div className="range-labels">
              <span>{dateLabel(dates[0])}</span>
              <span>{dates.length} actual observations</span>
              <span>{dateLabel(dates.at(-1))}</span>
            </div>
          </div>
          <Select
            value={speed}
            onChange={setSpeed}
            label="Playback speed"
            options={[
              { value: "2500", label: "0.5×" },
              { value: "1500", label: "1×" },
              { value: "750", label: "2×" },
            ]}
          />
          <button
            className="button small secondary"
            onClick={() => {
              setPlaying(false);
              setQuery({ as_of: "" });
            }}
          >
            <RotateCcw size={12} />
            Latest
          </button>
        </div>
      </Panel>
      <div className="chart-grid">
        <Panel
          title="Comparison ledger"
          subtitle="Only compatible observations contribute to this comparison."
        >
          <div className="datum-grid three">
            <Datum label={`${query.cycle} observed`} value={currentTotal} />
            <Datum label={`${query.baseline} ${asynchronous ? "last eligible report" : "baseline"}`} value={baseline} />
            <Datum
              label="Historical pace"
              value={
                typeof pace === "number"
                  ? `${(pace * 100).toFixed(1)}%`
                  : "Unavailable"
              }
            />
          </div>
          {asynchronous ? (
            <Notice tone="warning">
              The source reports do not align at the selected voting stage, so historical pace is withheld.
              {baselineDates.length > 0 && ` Eligible baseline report dates: ${dateLabel(baselineDates[0])}${baselineDates.length > 1 ? `–${dateLabel(baselineDates.at(-1))}` : ""}.`}
              {" "}A zero in an older report does not establish zero participation at the equivalent current stage.
            </Notice>
          ) : baseline == null ? (
            <Empty title="Historical compatibility is not yet established">
              A prior endpoint alone cannot manufacture a same-day historical
              series. Compatible source records are needed before a pace
              comparison is shown.
            </Empty>
          ) : (
            <Notice>
              {comparisonReason || "Interpret this comparison using the matched definitions, reporting geography, and source chronology shown in the evidence records."}
            </Notice>
          )}
          <div className="compatibility-list">
            {[
              { name: "Metric", value: human(query.metric) },
              { name: "Chronology", value: human(query.time_basis) },
              {
                name: "Geographic coverage",
                value: matchedCount == null ? "Match coverage not established" : `${matchedCount} matched ${String(comparison.geography_type ?? "reporting")} areas`,
              },
              { name: "Alignment", value: human(query.alignment) },
              {
                name: "Historical records",
                value: `${historical.length} observations in this response`,
              },
            ].map((item) => (
              <div key={item.name}>
                <span>{item.name}</span>
                <b>{item.value}</b>
              </div>
            ))}
          </div>
        </Panel>
        <Panel
          title="Reporting activity"
          subtitle="Source-to-source changes, including explicit negative revisions."
          exportLabel={exportLabel}
        >
          <ChangeChart series={current} />
        </Panel>
      </div>
      <Panel
        title="Observation calendar"
        subtitle="Each colored cell is a real report date; gaps remain unfilled."
      >
        {current.length ? (
          <div className="observation-calendar">
            {current.map((point, i) => {
              const delta = i
                ? Number(point.value) - Number(current[i - 1].value)
                : null;
              return (
                <button
                  key={`${point.date}-${i}`}
                  className={`calendar-cell ${query.as_of === point.date ? "active" : ""}`}
                  onClick={() => setQuery({ as_of: point.date })}
                >
                  <CalendarDays size={16} />
                  <time>{dateLabel(point.date)}</time>
                  <b>{fmt(point.value)}</b>
                  <small>
                    {delta == null
                      ? "First observation"
                      : `${delta >= 0 ? "+" : ""}${fmt(delta)} newly reported`}
                  </small>
                </button>
              );
            })}
          </div>
        ) : (
          <Empty title="No observation dates match">
            Choose an available cycle and metric to explore its actual reporting
            history.
          </Empty>
        )}
      </Panel>
      <ParticipationDepth {...ctx} />
    </>
  );
}
