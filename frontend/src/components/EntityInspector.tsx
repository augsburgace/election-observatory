import { publicFetch, originalDocumentHref } from "../publicData";
import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, FileSearch, X } from "lucide-react";
import { Loading, Notice, useModalFocus } from "./ui";
import { fmt, human } from "../utils";
export function openEntity(id: string) {
  const p = new URLSearchParams(location.search);
  p.set("ui_entity", id);
  history.replaceState(null, "", `?${p}`);
  window.dispatchEvent(new CustomEvent("observatory-entity", { detail: id }));
}
export default function EntityInspector({ revision }: { revision?: number }) {
  const [id, setId] = useState(
    () => new URLSearchParams(location.search).get("ui_entity") || "",
  );
  useEffect(() => {
    const open = (e: Event) => setId((e as CustomEvent<string>).detail);
    const pop = () =>
      setId(new URLSearchParams(location.search).get("ui_entity") || "");
    window.addEventListener("observatory-entity", open);
    window.addEventListener("popstate", pop);
    return () => {
      window.removeEventListener("observatory-entity", open);
      window.removeEventListener("popstate", pop);
    };
  }, []);
  const candidate = id.startsWith("option:") || id.startsWith("candidate:");
  const enabled = candidate || id.startsWith("contest:");
  const q = useQuery({
    queryKey: ["atlas", "entity", id, revision],
    queryFn: async () => {
      const r = await publicFetch(
        `/api/v2/${candidate ? "candidates" : "contests"}/${encodeURIComponent(id)}${revision != null ? "?revision=" + revision : ""}`,
      );
      if (!r.ok)
        throw new Error(
          "This verified identity record is unavailable at the selected revision.",
        );
      return r.json() as Promise<Record<string, unknown>>;
    },
    enabled,
  });
  const close = () => {
    setId("");
    const p = new URLSearchParams(location.search);
    p.delete("ui_entity");
    history.replaceState(null, "", `?${p}`);
  };
  useModalFocus(enabled, ".entity-inspector", close);
  if (!enabled) return null;
  const data = q.data || {},
    option = (data.option || {}) as Record<string, unknown>,
    contest = (data.contest || {}) as Record<string, unknown>,
    refs = (option.source_refs || data.sources || []) as Record<
      string,
      unknown
    >[],
    resultRecords = (data.results || []) as Record<string, unknown>[],
    options = (data.options || []) as Record<string, unknown>[];
  return (
    <div className="modal-backdrop">
      <section
        className="modal entity-inspector"
        role="dialog"
        aria-modal="true"
        aria-label={candidate ? "Candidate dossier" : "Contest dossier"}
      >
        <header>
          <div>
            <small>
              {candidate ? "Candidate / ballot identity" : "Election contest"}
            </small>
            <h2>
              {String(option.name || contest.name || "Original evidence")}
            </h2>
          </div>
          <button
            className="icon-button"
            aria-label="Close identity dossier"
            onClick={close}
          >
            <X size={19} />
          </button>
        </header>
        {q.isPending ? (
          <Loading />
        ) : q.isError ? (
          <Notice tone="warning">{q.error.message}</Notice>
        ) : (
          <>
            <dl className="identity-facts">
              {Object.entries(
                candidate
                  ? {
                      party: option.party,
                      kind: option.kind,
                      contest: contest.name,
                      state: contest.state,
                      year: contest.year,
                      office: contest.office,
                      district: contest.district,
                    }
                  : {
                      state: contest.state,
                      year: contest.year,
                      office: contest.office,
                      district: contest.district,
                      election_type: contest.election_type,
                      kind: contest.kind,
                    },
              )
                .filter(([, v]) => v != null)
                .map(([k, v]) => (
                  <div key={k}>
                    <dt>{human(k)}</dt>
                    <dd>{String(v)}</dd>
                  </div>
                ))}
            </dl>
            {options.length > 0 && (
              <div className="candidate-list">
                <h3>Published ballot options</h3>
                {options.map((o, i) => (
                  <button
                    key={i}
                    className="source-mini-row"
                    onClick={() => openEntity(String(o.id))}
                  >
                    <b>{String(o.name)}</b>
                    <span>{String(o.party || o.kind || "")}</span>
                    <ArrowRight size={13} />
                  </button>
                ))}
              </div>
            )}
            {resultRecords.length > 0 && (
              <div className="table-scroll identity-results">
                <table>
                  <thead>
                    <tr>
                      <th>Published geography</th>
                      <th>Candidate / option votes</th>
                      <th>Share</th>
                      <th>Round</th>
                    </tr>
                  </thead>
                  <tbody>
                    {resultRecords.slice(0, 30).map((r, i) => {
                      const value = (r.result || {}) as Record<string, unknown>;
                      return (
                        <tr key={i}>
                          <td>{String(r.name || r.geography_id)}</td>
                          <td className="numeric">{fmt(value.votes)}</td>
                          <td>
                            {value.share_pct == null
                              ? "—"
                              : fmt(value.share_pct, 1) + "%"}
                          </td>
                          <td>{String(r.round || "Reported")}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
                {resultRecords.length > 30 && (
                  <p className="table-footnote">
                    Showing the first 30 geographic records; the contest results
                    explorer provides the complete paginated evidence.
                  </p>
                )}
              </div>
            )}
            <Notice>
              {String(
                data.identity_scope ||
                  "This identity belongs to the recorded contest and ballot context. Similar names in other elections are not automatically merged.",
              )}
            </Notice>
            {refs.length > 0 && (
              <div className="source-list">
                {refs.map((r, i) => (
                  <a
                    key={i}
                    href={originalDocumentHref({ ...r, id: r.snapshot_id || r.id })}
                    target="_blank"
                    rel="noreferrer"
                  >
                    <FileSearch size={15} />
                    <span>
                      <b>{String(r.source_id || "Original result record")}</b>
                      <small>
                        Snapshot {String(r.snapshot_id || r.id)} · revision{" "}
                        {String(r.revision || revision || "")}
                      </small>
                    </span>
                  </a>
                ))}
              </div>
            )}
          </>
        )}
      </section>
    </div>
  );
}
