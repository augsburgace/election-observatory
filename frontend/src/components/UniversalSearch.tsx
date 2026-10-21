import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Search, ArrowRight, X } from "lucide-react";
import { atlasApi } from "../atlasApi";
import { STATE_NAMES, stateName } from "../utils";
import type { Page } from "../types";
export default function UniversalSearch({
  onSelect,
}: {
  onSelect: (state: string, page: Page, id?: string) => void;
}) {
  const [text, setText] = useState(""),
    [open, setOpen] = useState(false);
  const q = useQuery({
    queryKey: ["atlas", "search", text],
    queryFn: () => atlasApi.search(text),
    enabled: open && text.trim().length > 1,
  });
  const payload = q.data || {};
  const raw = (
    Array.isArray(payload.items)
      ? payload.items
      : Array.isArray(payload.results)
        ? payload.results
        : []
  ) as Record<string, unknown>[];
  const local = Object.entries(STATE_NAMES)
    .filter(
      ([code, name]) =>
        code !== "DC" &&
        `${code} ${name}`.toLowerCase().includes(text.toLowerCase()),
    )
    .slice(0, 7)
    .map(([code, name]) => ({ id: code, state: code, name, kind: "state" }));
  const items: Record<string, unknown>[] = raw.length ? raw : local;
  return (
    <div className="universal-search">
      <Search size={17} />
      <input
        value={text}
        onChange={(e) => {
          setText(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        aria-label="Search places, elections, candidates, or saved research"
        placeholder="Search a state, county, election or candidate…"
        onKeyDown={(e) => {
          if (e.key === "Escape") setOpen(false);
        }}
      />
      {text && (
        <button
          className="icon-button"
          aria-label="Clear search"
          onClick={() => {
            setText("");
            setOpen(false);
          }}
        >
          <X size={14} />
        </button>
      )}
      {open && text && (
        <div className="universal-results">
          <header>
            <b>Explore the atlas</b>
            <button className="text-button" onClick={() => setOpen(false)}>
              Close
            </button>
          </header>
          {q.isFetching && <small>Searching sourced records…</small>}
          {items.slice(0, 12).map((item, i) => {
            const kind = String(item.kind || item.type || "state"),
              state = String(item.state || item.code || ""),
              id = String(item.geography_id || item.id || "");
            return (
              <button
                key={id + i}
                onClick={() => {
                  onSelect(
                    state || "NC",
                    kind === "state"
                      ? "states"
                      : kind === "place" || kind === "geography"
                        ? "place"
                        : "elections",
                    kind === "state" ? undefined : id,
                  );
                  setOpen(false);
                  setText("");
                }}
              >
                <span>
                  <b>{String(item.name || item.title || item.label || id)}</b>
                  <small>
                    {kind} {state ? `· ${stateName(state)}` : ""}
                  </small>
                </span>
                <ArrowRight size={14} />
              </button>
            );
          })}
          {!items.length && !q.isFetching && (
            <p>No matching verified records. Try a state or county name.</p>
          )}
        </div>
      )}
    </div>
  );
}
