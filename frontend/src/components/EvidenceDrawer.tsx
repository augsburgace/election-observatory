import { isPublicMode, originalDocumentHref } from "../publicData";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowUpRight,
  Clipboard,
  ExternalLink as LinkIcon,
  FileText,
  ShieldCheck,
  X,
} from "lucide-react";
import { api, request } from "../api";
import type { Observation, Poll, Source } from "../types";
import { dateLabel, fmt, human } from "../utils";
import {
  Datum,
  ExternalLink,
  Field,
  Loading,
  Notice,
  Status,
  useModalFocus,
} from "./ui";
export type EvidenceSelection = {
  type: "source" | "observation" | "poll";
  id: string | number;
  data?: unknown;
};
export default function EvidenceDrawer({
  selection,
  onClose,
  notify,
}: {
  selection: EvidenceSelection;
  onClose: () => void;
  notify: (m: string) => void;
}) {
  const cache = useQueryClient();
  useModalFocus(true, ".evidence-drawer", onClose);
  const evidence = useQuery({
    queryKey: ["evidence", selection.id],
    queryFn: () => api.evidence(selection.id),
    enabled: selection.type === "observation",
  });
  const [correction, setCorrection] = useState(false);
  const [replacement, setReplacement] = useState("");
  const [reason, setReason] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const source =
    selection.type === "source"
      ? (selection.data as Source)
      : evidence.data?.source;
  const observation = (
    selection.type === "observation"
      ? evidence.data?.observation || selection.data
      : null
  ) as Observation | undefined;
  const poll = selection.type === "poll" ? (selection.data as Poll) : undefined;
  const snapshot = evidence.data?.snapshot;
  async function saveCorrection() {
    if (!reason.trim() || replacement === "" || Number(replacement) < 0) {
      setError("Enter a nonnegative replacement and an explanation.");
      return;
    }
    setSaving(true);
    try {
      await request("/corrections", {
        method: "POST",
        body: JSON.stringify({
          observation_id: selection.id,
          replacement: Number(replacement),
          reason: reason.trim(),
        }),
      });
      notify("Correction recorded with the original evidence preserved.");
      setCorrection(false);
      cache.invalidateQueries({ queryKey: ["workspace"] });
      cache.invalidateQueries({ queryKey: ["bootstrap"] });
      cache.invalidateQueries({ queryKey: ["evidence"] });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }
  return (
    <div className="drawer-backdrop" onClick={onClose}>
      <aside
        className="evidence-drawer"
        aria-label="Evidence inspector"
        role="dialog"
        aria-modal="true"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="drawer-head">
          <div className="drawer-title">
            <ShieldCheck size={20} />
            <div>
              <h2>Evidence inspector</h2>
              <span>Definitions, chronology & provenance</span>
            </div>
          </div>
          <button
            className="icon-button"
            onClick={onClose}
            aria-label="Close evidence inspector"
          >
            <X />
          </button>
        </header>
        <div className="drawer-content">
          {evidence.isLoading && <Loading />}
          {evidence.isError && (
            <Notice tone="warning">{evidence.error.message}</Notice>
          )}
          {observation && (
            <>
              <BadgeRow text="Reported observation" />
              <h3>{human(observation.metric)}</h3>
              <div className="evidence-large">
                {fmt(observation.value)}
                <small>{observation.unit}</small>
              </div>
              <div className="datum-grid">
                <Datum label="Place" value={observation.geography_name} />
                <Datum label="Cycle" value={String(observation.cycle)} />
                <Datum
                  label="Source report date"
                  value={dateLabel(observation.date)}
                />
                <Datum
                  label="Chronology"
                  value={human(observation.time_basis)}
                />
                <Datum label="Voting mode" value={human(observation.mode)} />
                <Datum
                  label="Reported category"
                  value={observation.category || "Aggregate"}
                />
              </div>
              {evidence.data?.calculation && (
                <section>
                  <h4>Calculation</h4>
                  <p>{String(evidence.data.calculation)}</p>
                </section>
              )}
              <Notice>
                Reporting date and retrieval date have different meanings. Newly
                discovered evidence does not establish when it was originally
                published.
              </Notice>
            </>
          )}
          {poll && (
            <>
              <BadgeRow text="Original survey evidence" />
              <h3>{poll.producer}</h3>
              <p className="quote">{poll.question}</p>
              <div className="datum-grid">
                <Datum
                  label="Fieldwork"
                  value={`${dateLabel(poll.field_start)} – ${dateLabel(poll.field_end)}`}
                />
                <Datum label="Population" value={poll.population} />
                <Datum label="Sample size" value={poll.sample_size} />
                <Datum label="Sponsor" value={poll.sponsor} />
                <Datum label="Published" value={dateLabel(poll.published_at)} />
                <Datum
                  label="Reported MOE"
                  value={
                    poll.margin_of_error == null
                      ? "Not disclosed"
                      : `±${poll.margin_of_error} pp`
                  }
                />
              </div>
              <section>
                <h4>Methodology</h4>
                <p>{poll.methodology}</p>
              </section>
              <section>
                <h4>Question classification</h4>
                <p>
                  {human(poll.question_type)} · {human(poll.ballot_type)}
                </p>
              </section>
              <ExternalLink href={poll.document_url || poll.source_url}>
                Read original survey
              </ExternalLink>
            </>
          )}
          {source && (
            <section className="source-detail">
              <BadgeRow text="Source record" />
              <h3>{source.name}</h3>
              <Status value={String(source.status || "not_collected")} />
              <p>
                {source.description ||
                  source.notes ||
                  "Original public source registered for local collection and validation."}
              </p>
              <ExternalLink href={source.url}>
                Open original source
              </ExternalLink>
              <div className="datum-grid">
                <Datum
                  label="Last checked"
                  value={dateLabel(source.last_checked)}
                />
                <Datum
                  label="Last changed"
                  value={dateLabel(source.last_changed)}
                />
                <Datum
                  label="Data as of"
                  value={dateLabel(source.data_as_of)}
                />
                <Datum label="Connector" value={human(source.connector)} />
                <Datum label="Observations" value={source.observation_count} />
                <Datum label="Source ID" value={source.id} />
              </div>
              {Boolean(source.last_error || source.error) && (
                <Notice tone="warning">
                  {String(source.last_error || source.error)}
                </Notice>
              )}
              {source.warnings?.map((w, i) => (
                <Notice key={i} tone="warning">
                  {w}
                </Notice>
              ))}
            </section>
          )}
          {snapshot && (
            <section>
              <h4>Archived source snapshot</h4>
              <div className="datum-grid">
                <Datum
                  label="Retrieved"
                  value={dateLabel(snapshot.retrieved_at)}
                />
                <Datum
                  label="Size"
                  value={
                    snapshot.byte_count == null
                      ? "—"
                      : `${fmt(snapshot.byte_count)} bytes`
                  }
                />
              </div>
              <p className="hash-label">SHA-256</p>
              <code className="hash">{snapshot.sha256}</code>
              <div className="button-row">
                <a
                  className="button secondary"
                  href={originalDocumentHref(snapshot, source?.url)}
                  target="_blank"
                  rel="noreferrer"
                >
                  <FileText size={15} />
                  {isPublicMode() ? "Original source document" : "Archived document"}
                  <ArrowUpRight size={13} />
                </a>
                <button
                  className="button secondary"
                  onClick={() => {
                    navigator.clipboard.writeText(snapshot.sha256);
                    notify("Snapshot hash copied.");
                  }}
                >
                  <Clipboard size={14} />
                  Copy hash
                </button>
              </div>
            </section>
          )}
          {evidence.data?.revisions && (
            <section>
              <h4>Revision history</h4>
              {evidence.data.revisions.length ? (
                <pre className="json-view">
                  {JSON.stringify(evidence.data.revisions, null, 2)}
                </pre>
              ) : (
                <p>No prior revisions are recorded for this observation.</p>
              )}
            </section>
          )}
          {observation?.metadata &&
            Object.keys(observation.metadata).length > 0 && (
              <section>
                <h4>Source methodology & limitations</h4>
                <pre className="json-view">
                  {JSON.stringify(observation.metadata, null, 2)}
                </pre>
              </section>
            )}
          {evidence.data?.warnings?.map((warning, i) => (
            <Notice key={i} tone="warning">
              {warning}
            </Notice>
          ))}
          {observation && !isPublicMode() && (
            <section className="correction">
              <button
                className="text-button"
                onClick={() => setCorrection(!correction)}
              >
                {correction
                  ? "Close correction form"
                  : "Record a reviewed correction"}
              </button>
              {correction && (
                <>
                  <Notice>
                    A correction creates an auditable overlay. The original
                    source value remains in the archive.
                  </Notice>
                  <Field label="Replacement value">
                    <input
                      type="number"
                      min="0"
                      value={replacement}
                      onChange={(e) => setReplacement(e.target.value)}
                    />
                  </Field>
                  <Field label="Reason">
                    <textarea
                      value={reason}
                      onChange={(e) => setReason(e.target.value)}
                      rows={3}
                    />
                  </Field>
                  {error && <p className="error-text">{error}</p>}
                  <button
                    className="button primary"
                    disabled={saving}
                    onClick={saveCorrection}
                  >
                    {saving ? "Recording…" : "Record correction"}
                  </button>
                </>
              )}
            </section>
          )}
        </div>
        <footer className="drawer-footer">
          <LinkIcon size={14} />
          {isPublicMode() ? "Published aggregate evidence · original source links" : "Local archive · original evidence retained"}
        </footer>
      </aside>
    </div>
  );
}
function BadgeRow({ text }: { text: string }) {
  return (
    <div className="evidence-kind">
      <ShieldCheck size={13} />
      {text}
    </div>
  );
}
