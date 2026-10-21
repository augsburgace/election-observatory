import { isPublicMode } from "../publicData";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight,
  Bookmark,
  BookOpen,
  Check,
  Clock3,
  Copy,
  FileText,
  FolderOpen,
  Plus,
  Save,
  Search,
  Trash2,
  X,
} from "lucide-react";
import type { AppContext, ResearchObject, ResearchQuery } from "../types";
import { api, downloadData, queryString } from "../api";
import {
  Badge,
  Empty,
  Field,
  Loading,
  Notice,
  Panel,
  Select,
  useModalFocus,
} from "../components/ui";
import { dateLabel, human, stateName } from "../utils";
const ICONS: Record<string, typeof BookOpen> = {
  note: FileText,
  view: FolderOpen,
  bookmark: Bookmark,
  scenario: Copy,
  report: FileText,
  correction: Check,
};
export default function Notebook(ctx: AppContext & { embedded?: boolean }) {
  const { workspace, query, notify, embedded } = ctx;
  const cache = useQueryClient();
  const research = useQuery({ queryKey: ["research"], queryFn: api.research });
  const [filter, setFilter] = useState("all");
  const [search, setSearch] = useState("");
  const [scope, setScope] = useState(embedded ? "state" : "all");
  const [editing, setEditing] = useState<number | "new" | null>(null);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [kind, setKind] = useState("note");
  const [saving, setSaving] = useState(false);
  const [deleteId, setDeleteId] = useState<number | null>(null);
  useModalFocus(editing !== null, ".note-modal", () => setEditing(null));
  const items = research.data
    ? Array.isArray(research.data)
      ? research.data
      : research.data.items
    : [];
  const filtered = items.filter(
    (item) =>
      (filter === "all" || item.kind === filter) &&
      `${item.title} ${item.body}`
        .toLowerCase()
        .includes(search.toLowerCase()) &&
      (scope === "all" || itemState(item) === query.state),
  );
  function startEdit(item?: ResearchObject) {
    setEditing(item?.id || "new");
    setTitle(item?.title || "");
    setBody(item?.body || "");
    setKind(item?.kind || "note");
  }
  async function save() {
    if (!title.trim()) {
      notify("Give this research note a title.");
      return;
    }
    setSaving(true);
    try {
      const old = items.find((i) => i.id === editing);
      const record = {
        kind,
        title: title.trim(),
        body,
        view: old?.view || {
          query: workspace.query,
          page: "states",
          state: query.state,
        },
      };
      if (typeof editing === "number")
        await api.updateResearch(editing, record);
      else await api.saveResearch(record);
      setEditing(null);
      cache.invalidateQueries({ queryKey: ["research"] });
      notify("Research note saved locally.");
    } catch (e) {
      notify((e as Error).message);
    } finally {
      setSaving(false);
    }
  }
  async function remove(id: number) {
    try {
      await api.deleteResearch(id);
      setDeleteId(null);
      cache.invalidateQueries({ queryKey: ["research"] });
      notify("Research item deleted.");
    } catch (e) {
      notify((e as Error).message);
    }
  }
  function href(item: ResearchObject, latest = false) {
    const saved = item.view || item.payload || {};
    const q = { ...query, ...(saved.query as Partial<ResearchQuery>) };
    if (latest) {
      delete q.revision;
      q.as_of = "";
    }
    const p = new URLSearchParams(queryString(q));
    p.set("page", String(saved.page || "states"));
    if (item.kind === "report" || item.kind === "scenario")
      p.set("research_id", String(item.id));
    if (saved.layout && typeof saved.layout === "object")
      Object.entries(saved.layout as Record<string, string>).forEach(
        ([key, value]) => p.set(key, value),
      );
    if (saved.tab) p.set("tab", String(saved.tab));
    return `?${p}`;
  }
  return (
    <>
      {!embedded && (
        <div className="page-intro">
          <div>
            <h2>Your research, with a memory.</h2>
            <p>
              Keep exact evidence views, questions, source bookmarks, scenarios,
              and personal interpretations together.
            </p>
          </div>
          <button className="button primary" onClick={() => startEdit()}>
            <Plus size={15} />
            New research note
          </button>
        </div>
      )}
      <div className="notebook-summary">
        <div className="notebook-symbol">
          <BookOpen size={30} />
        </div>
        <div>
          <h3>Private local notebook</h3>
          <p>
            Notes describe your interpretation. Saved views preserve the
            evidence revision that supported it.
          </p>
        </div>
        <div className="notebook-count">
          <b>{items.length}</b>
          <span>saved research items</span>
        </div>
        {embedded && (
          <button className="button primary" onClick={() => startEdit()}>
            <Plus size={14} />
            Add note
          </button>
        )}
      </div>
      {isPublicMode() && <Notice>Private to this browser and device. Export your collection regularly; clearing browser storage removes these notes and saved views. Nothing is sent to a shared server.</Notice>}
      <Panel
        title="Research collection"
        subtitle="Open exact evidence or deliberately apply a saved configuration to the latest data."
      >
        <div className="table-toolbar">
          <div className="search-field">
            <Search size={14} />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search your research…"
              aria-label="Search research collection"
            />
          </div>
          <Select
            value={filter}
            onChange={setFilter}
            label="Research item type"
            options={[
              { value: "all", label: "All research types" },
              ...[
                "note",
                "view",
                "bookmark",
                "scenario",
                "report",
                "correction",
              ].map((k) => ({ value: k, label: human(k) })),
            ]}
          />
          <Select
            value={scope}
            onChange={setScope}
            label="Research state scope"
            options={[
              { value: "all", label: "Every state" },
              { value: "state", label: stateName(query.state) },
            ]}
          />
          <button
            className="button small secondary"
            onClick={() => downloadData(filtered, "observatory-notebook.json")}
          >
            Export collection
          </button>
        </div>
        {research.isPending ? (
          <Loading />
        ) : research.isError ? (
          <Notice tone="warning">{research.error.message}</Notice>
        ) : !filtered.length ? (
          <Empty
            title="Start an investigation worth returning to"
            icon={<BookOpen size={28} />}
            action={
              <button className="button primary" onClick={() => startEdit()}>
                <Plus size={14} />
                Write a research note
              </button>
            }
          >
            Use “Save view” anywhere in the application to retain an exact
            evidence revision, or add a note with a research question.
          </Empty>
        ) : (
          <div className="research-collection">
            {filtered.map((item) => {
              const Icon = ICONS[item.kind] || FileText;
              const state = itemState(item);
              const revision = (
                item.view?.query as Partial<ResearchQuery> | undefined
              )?.revision;
              return (
                <article className="research-item" key={item.id}>
                  <div className={`research-item-icon ${item.kind}`}>
                    <Icon size={21} />
                  </div>
                  <div className="research-item-main">
                    <div className="research-item-meta">
                      <Badge
                        tone={
                          item.kind === "view"
                            ? "cyan"
                            : item.kind === "scenario"
                              ? "gold"
                              : "violet"
                        }
                      >
                        {human(item.kind)}
                      </Badge>
                      {state && <span>{stateName(state)}</span>}
                      {revision != null && <span>r{revision}</span>}
                      <span>
                        <Clock3 size={11} />
                        {dateLabel(item.updated_at || item.created_at)}
                      </span>
                    </div>
                    <h3>{item.title}</h3>
                    {item.body && <p className="research-body">{item.body}</p>}
                    <div className="research-item-actions">
                      <a className="button small secondary" href={href(item)}>
                        Open exact view
                        <ArrowRight size={12} />
                      </a>
                      <a className="text-button" href={href(item, true)}>
                        Apply to latest data
                      </a>
                      <button
                        className="text-button"
                        onClick={() => startEdit(item)}
                      >
                        Edit
                      </button>
                      <button
                        className="icon-button delete-button"
                        aria-label={`Delete ${item.title}`}
                        onClick={() => setDeleteId(item.id)}
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                    {deleteId === item.id && (
                      <div className="delete-confirm">
                        <span>Delete this research item?</span>
                        <button
                          className="button small danger"
                          onClick={() => remove(item.id)}
                        >
                          Delete item
                        </button>
                        <button
                          className="button small secondary"
                          onClick={() => setDeleteId(null)}
                        >
                          Keep it
                        </button>
                      </div>
                    )}
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </Panel>
      <Notice>
        Exact views retain an evidence revision. “Apply to latest data” clears
        the pinned revision and cutoff so that newer evidence is an explicit
        choice.
      </Notice>
      {editing !== null && (
        <div className="modal-backdrop">
          <section
            className="modal note-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="note-modal-title"
          >
            <header>
              <h2 id="note-modal-title">
                {editing === "new" ? "New research note" : "Edit research item"}
              </h2>
              <button
                className="icon-button"
                onClick={() => setEditing(null)}
                aria-label="Close note editor"
              >
                <X size={18} />
              </button>
            </header>
            <Field label="Title">
              <input
                autoFocus
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="What are you investigating?"
              />
            </Field>
            <Field label="Type">
              <Select
                value={kind}
                onChange={setKind}
                label="Research note type"
                options={[
                  { value: "note", label: "Research note" },
                  { value: "bookmark", label: "Evidence bookmark" },
                ]}
              />
            </Field>
            <Field label="Your notes">
              <textarea
                rows={9}
                value={body}
                onChange={(e) => setBody(e.target.value)}
                placeholder="Record your question, interpretation, limitations, and next steps."
              />
            </Field>
            <Notice>
              Attached to {stateName(query.state)} · revision{" "}
              {workspace.revision}. Personal interpretation remains distinct
              from the source evidence.
            </Notice>
            <footer>
              <button
                className="button secondary"
                onClick={() => setEditing(null)}
              >
                Cancel
              </button>
              <button
                className="button primary"
                disabled={saving}
                onClick={save}
              >
                <Save size={14} />
                {saving ? "Saving…" : "Save locally"}
              </button>
            </footer>
          </section>
        </div>
      )}
    </>
  );
}
function itemState(item: ResearchObject) {
  const view = item.view || item.payload || {};
  return String(
    view.state ||
      (view.query as Record<string, unknown> | undefined)?.state ||
      "",
  );
}
