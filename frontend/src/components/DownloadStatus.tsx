import { isPublicMode } from "../publicData";
import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CloudDownload, RefreshCw, Check, AlertTriangle } from "lucide-react";
import { atlasApi, type Dataset } from "../atlasApi";
import { api } from "../api";
import type { Job } from "../types";
export function DatasetDownload({
  dataset,
  state,
  automatic = false,
}: {
  dataset: Dataset;
  state: string;
  automatic?: boolean;
}) {
  const cache = useQueryClient(),
    attempted = useRef(new Set<string>()),
    [job, setJob] = useState<Job | null>(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const loaded =
    dataset.loaded_states?.includes(state) || dataset.status === "loaded";
  const jobs = useQuery({
    queryKey: ["jobs", "datasets"],
    queryFn: api.jobs,
    enabled: !!job && ["queued", "running", "pending"].includes(job.status),
    refetchInterval: 1800,
  });
  useEffect(() => {
    const j = jobs.data;
    const list = Array.isArray(j) ? j : j?.jobs || [];
    const fresh = list.find((r) => r.id === job?.id);
    if (fresh) {
      setJob(fresh);
      if (["failed", "error", "interrupted"].includes(fresh.status))
        setError(
          fresh.error ||
            "Collection did not complete. Previously validated evidence remains available.",
        );
      if (
        ["complete", "completed", "success", "succeeded"].includes(fresh.status)
      ) {
        cache.invalidateQueries({ queryKey: ["atlas"] });
        cache.invalidateQueries({ queryKey: ["bootstrap"] });
      }
    }
  }, [jobs.data]);
  const start = async () => {
    setBusy(true);
    setError("");
    try {
      setJob(await atlasApi.load(dataset.id, state));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  useEffect(() => {
    const key = dataset.id + ":" + state;
    if (
      !isPublicMode() &&
      automatic &&
      !attempted.current.has(key) &&
      !loaded &&
      dataset.on_demand &&
      dataset.status !== "guestbook_required"
    ) {
      attempted.current.add(key);
      void start();
    }
  }, [automatic, loaded, dataset.id, state]);
  const active =
    busy || (job && ["queued", "running", "pending"].includes(job.status));
  return (
    <div className={`dataset-download ${loaded ? "loaded" : ""}`}>
      <div>
        {loaded ? (
          <Check size={17} />
        ) : active ? (
          <RefreshCw className="spin" size={17} />
        ) : error ? (
          <AlertTriangle size={17} />
        ) : (
          <CloudDownload size={17} />
        )}
        <span>
          <b>{dataset.title}</b>
          <small>
            {dataset.producer} ·{" "}
            {loaded
              ? isPublicMode() ? "Included in this published release" : "Available locally"
              : active
                ? `${job?.progress?.message || job?.progress?.stage || job?.status || "Starting"}${job?.progress?.total ? ` (${job.progress.completed || 0}/${job.progress.total})` : ""} · evidence remains usable`
                : dataset.on_demand
                  ? isPublicMode() ? "Additional source evidence is available in the local edition" : "Download detailed public evidence"
                  : dataset.status}{" "}
            · {dataset.record_count?.toLocaleString() || "No"} records
          </small>
          {error && <small className="orange-text">{error}</small>}
        </span>
      </div>
      {!loaded && !isPublicMode() && (
        <button
          className="button secondary small"
          disabled={
            !!active ||
            !dataset.on_demand ||
            dataset.status === "guestbook_required"
          }
          onClick={start}
        >
          {dataset.status === "guestbook_required"
            ? "Producer access required"
            : active
              ? "Loading…"
              : error
                ? "Retry"
                : "Load data"}
        </button>
      )}
      {job?.result && (
        <details>
          <summary>Collection details</summary>
          <pre>{JSON.stringify(job.result, null, 2)}</pre>
        </details>
      )}
    </div>
  );
}
