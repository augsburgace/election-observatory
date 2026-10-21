import { PublicAttributions } from "../components/PublicPublication";
import { isPublicMode } from "../publicData";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  AlertTriangle,
  ArrowUpRight,
  CheckCircle2,
  Database,
  FileSearch,
  RefreshCw,
  Search,
  ShieldCheck,
} from "lucide-react";
import type { AppContext, Job, Source } from "../types";
import { api, request } from "../api";
import {
  Empty,
  Loading,
  Notice,
  Panel,
  Select,
  Stat,
  Status,
} from "../components/ui";
import { dateLabel, fmt, human, stateName } from "../utils";
export default function Sources(ctx: AppContext & { embedded?: boolean }) {
  const { workspace, query, inspect, notify, refresh, refreshing, embedded } =
    ctx;
  const cache = useQueryClient();
  const [scope, setScope] = useState(embedded ? "state" : "all");
  const [status, setStatus] = useState("all");
  const [search, setSearch] = useState("");
  const [collecting, setCollecting] = useState("");
  const [expandedJob, setExpandedJob] = useState<number | null>(null);
  const sourcesQuery = useQuery({
    queryKey: ["sources"],
    queryFn: api.sources,
    refetchInterval: 30_000,
  });
  const jobsQuery = useQuery({
    queryKey: ["jobs"],
    queryFn: api.jobs,
    refetchInterval: (query) => {
      const data = query.state.data;
      const jobs = data ? (Array.isArray(data) ? data : data.jobs) : [];
      return jobs.some((j) => ["queued", "running"].includes(j.status))
        ? 3000
        : 15_000;
    },
  });
  const all = sourcesQuery.data
    ? Array.isArray(sourcesQuery.data)
      ? sourcesQuery.data
      : sourcesQuery.data.sources
    : workspace.sources || [];
  const sources = all.filter(
    (source) =>
      (scope === "all" || source.state === query.state || source.scope === "national") &&
      (status === "all" || source.status === status) &&
      `${source.name} ${source.state} ${source.url} ${source.connector}`
        .toLowerCase()
        .includes(search.toLowerCase()),
  );
  const jobs = jobsQuery.data
    ? Array.isArray(jobsQuery.data)
      ? jobsQuery.data
      : jobsQuery.data.jobs
    : [];
  const ready = all.filter((s) =>
    ["ready", "unchanged", "partial", "current"].includes(String(s.status)),
  );
  const failed = all.filter((s) =>
    ["failed", "error"].includes(String(s.status)),
  );
  const uncollected = all.filter(
    (s) =>
      !s.status || ["not_collected", "unavailable"].includes(String(s.status)),
  );
  async function collect(source: Source) {
    setCollecting(source.id);
    try {
      const result = await request<Job>("/refresh", {
        method: "POST",
        body: JSON.stringify({ source_ids: [source.id] }),
      });
      notify(`Collection job #${result.id} queued for ${source.name}.`);
      cache.invalidateQueries({ queryKey: ["jobs"] });
    } catch (e) {
      notify((e as Error).message);
    } finally {
      setCollecting("");
    }
  }
  return (
    <>
      {!embedded && (
        <div className="page-intro">
          <div>
            <h2>The evidence behind the interface.</h2>
            <p>
              Inspect original sources, collection chronology, validation
              results, and gaps. A successful request is only the first step.
            </p>
          </div>
          {isPublicMode() ? <span className="status-badge">Scheduled publisher · read-only evidence</span> : <button
            className="button primary"
            disabled={refreshing}
            onClick={refresh}
          >
            <RefreshCw size={14} className={refreshing ? "spin" : ""} />
            {isPublicMode() ? "Scheduled publication" : refreshing ? "Collection queued" : "Check all sources"}
          </button>}
        </div>
      )}
      <div className="stat-grid">
        <Stat
          label="Registered sources"
          value={all.length}
          detail="Sources retain ownership and authority by metric"
          icon={<Database size={21} />}
          accent="cyan"
        />
        <Stat
          label="Collected evidence"
          value={ready.length}
          detail="Ready, unchanged, or explicitly partial"
          icon={<CheckCircle2 size={21} />}
          accent="teal"
        />
        <Stat
          label="Sources needing attention"
          value={failed.length}
          detail="Last validated evidence is preserved"
          icon={<AlertTriangle size={21} />}
          accent="gold"
        />
        <Stat
          label="Coverage to establish"
          value={uncollected.length}
          detail="Unavailable or awaiting first collection"
          icon={<FileSearch size={21} />}
          accent="violet"
        />
      </div>
      <PublicAttributions />
      <Panel
        title="Source inventory & coverage"
        subtitle="Every source keeps its native definitions, publication context, and immutable local snapshots."
      >
        <div className="table-toolbar">
          <div className="search-field">
            <Search size={14} />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              aria-label="Search source inventory"
              placeholder="Search sources, states, connectors…"
            />
          </div>
          <Select
            value={scope}
            onChange={setScope}
            label="Source geography"
            options={[
              { value: "all", label: "All battleground sources" },
              { value: "state", label: stateName(query.state) },
            ]}
          />
          <Select
            value={status}
            onChange={setStatus}
            label="Source collection status"
            options={[
              { value: "all", label: "Every status" },
              ...[
                "ready",
                "unchanged",
                "partial",
                "failed",
                "not_collected",
                "unavailable",
              ].map((s) => ({ value: s, label: human(s) })),
            ]}
          />
          <span className="table-count">{sources.length} sources</span>
        </div>
        {sourcesQuery.isPending && !all.length ? (
          <Loading />
        ) : (
          <div className="table-scroll">
            <table className="sources-table">
              <thead>
                <tr>
                  <th>Source / authority</th>
                  <th>State</th>
                  <th>Validation status</th>
                  <th>Last checked</th>
                  <th>Data as of</th>
                  <th>Observations</th>
                  <th>Collection</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {sources.map((source) => (
                  <tr key={source.id}>
                    <td>
                      <button
                        className="text-button source-name"
                        onClick={() =>
                          inspect({
                            type: "source",
                            id: source.id,
                            data: source,
                          })
                        }
                      >
                        {source.name}
                      </button>
                      <small>
                        {human(source.connector)} · Tier{" "}
                        {String(source.tier || "1")}
                      </small>
                      {(source.error || source.last_error) && (
                        <small className="error-text source-error">
                          {String(source.error || source.last_error)}
                        </small>
                      )}
                    </td>
                    <td>
                      <span className="table-state-code">{source.state}</span>
                    </td>
                    <td>
                      <Status
                        value={String(source.status || "not_collected")}
                      />
                      {source.warnings?.length ? (
                        <small>{source.warnings.length} validation notes</small>
                      ) : null}
                    </td>
                    <td>{dateLabel(source.last_checked)}</td>
                    <td>{dateLabel(source.data_as_of)}</td>
                    <td>{fmt(source.observation_count)}</td>
                    <td>
                      {isPublicMode() ? <small>Scheduled publisher</small> : <button
                        className="button small secondary"
                        disabled={
                          collecting === source.id || source.enabled === false
                        }
                        onClick={() => collect(source)}
                      >
                        <RefreshCw
                          size={12}
                          className={collecting === source.id ? "spin" : ""}
                        />
                        {collecting === source.id ? "Queuing" : "Check"}
                      </button>}
                    </td>
                    <td>
                      <a
                        className="icon-button"
                        href={source.url}
                        target="_blank"
                        rel="noreferrer"
                        aria-label={`Open ${source.name}`}
                      >
                        <ArrowUpRight size={15} />
                      </a>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!sources.length && (
              <Empty title="No source records match">
                Change the state scope, search, or status filter.
              </Empty>
            )}
          </div>
        )}
      </Panel>
      <div className="source-bottom-grid">
        <Panel
          title="Collection history"
          subtitle="Actual queued and completed local work; no simulated live status."
        >
          {jobsQuery.isError ? (
            <Notice tone="warning">{jobsQuery.error.message}</Notice>
          ) : jobs.length ? (
            <div className="job-list">
              {jobs.slice(0, 20).map((job) => (
                <article key={job.id} className="job-row">
                  <button
                    onClick={() =>
                      setExpandedJob(expandedJob === job.id ? null : job.id)
                    }
                  >
                    <span className="job-icon">
                      <Activity size={16} />
                    </span>
                    <div>
                      <b>
                        {human(job.kind)} · #{job.id}
                      </b>
                      <small>{dateLabel(job.created_at)}</small>
                    </div>
                    <Status value={job.status} />
                  </button>
                  {expandedJob === job.id && (
                    <div className="job-detail">
                      {job.error && <Notice tone="warning">{job.error}</Notice>}
                      <div className="datum-grid">
                        <div>
                          <small>Started</small>
                          <p>{job.started_at || "Not started"}</p>
                        </div>
                        <div>
                          <small>Finished</small>
                          <p>{job.finished_at || "Not finished"}</p>
                        </div>
                      </div>
                      {job.result && (
                        <pre className="json-view">
                          {JSON.stringify(job.result, null, 2)}
                        </pre>
                      )}
                    </div>
                  )}
                </article>
              ))}
            </div>
          ) : (
            <Empty title="No collection jobs recorded">
              The collector and manual refresh will add actual run histories
              here.
            </Empty>
          )}
        </Panel>
        <Panel title="How collection is interpreted">
          <div className="collection-stages">
            {[
              {
                name: "Checked",
                text: "The original resource was requested; the response and retrieval time were recorded.",
              },
              {
                name: "Changed",
                text: "A content hash differs from the archived version; unchanged files are deduplicated.",
              },
              {
                name: "Validated",
                text: "A parser produced records that passed structural and domain checks.",
              },
              {
                name: "Published",
                text: "Validated observations became an atomic, versioned research dataset.",
              },
            ].map((stage, i) => (
              <div key={stage.name}>
                <span>0{i + 1}</span>
                <div>
                  <h3>{stage.name}</h3>
                  <p>{stage.text}</p>
                </div>
              </div>
            ))}
          </div>
          <Notice>
            {isPublicMode() ? "The publication banner shows the update schedule and last validated release. A source outage or failed publishing job keeps the previous release available. Individual source reporting dates can be older than the publication date." : "The default schedule checks every two hours while this Mac is awake and online. An offline or sleeping Mac can miss publication windows."}
          </Notice>
          <div className="provenance-footer">
            <ShieldCheck size={17} />
            <span>
              Raw snapshots are private local evidence. Research exports contain
              aggregate data and source manifests.
            </span>
          </div>
        </Panel>
      </div>
    </>
  );
}
