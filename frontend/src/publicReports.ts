import type { ReportPreview, ReportRequest } from "./reportTypes";
import { canonicalPublicKey, getPublicManifest, loadPublishedObject } from "./publicData";
function sameScope(a: Record<string, unknown>, b: Record<string, unknown>) {
  return [...new Set([...Object.keys(a), ...Object.keys(b)])].every(key => {
    const left = a[key], right = b[key];
    if ((left == null || left === "" || Array.isArray(left) && !left.length) && (right == null || right === "" || Array.isArray(right) && !right.length)) return true;
    return JSON.stringify(left) === JSON.stringify(right);
  });
}
export async function previewPublicReport(request: ReportRequest, signal?: AbortSignal): Promise<ReportPreview> {
  const publication = await getPublicManifest(), entry = publication.reports?.[request.query.state];
  if (!entry) throw new Error("A report packet for this state is not published yet. You can export the displayed aggregate data and print the current research page.");
  const base = await loadPublishedObject(entry, signal) as ReportPreview;
  const key = (query: ReportRequest["query"]) => {
    const p = new URLSearchParams();
    Object.entries(query).forEach(([k, v]) => { if (v != null && v !== "") p.set(k, Array.isArray(v) ? v.join(",") : String(v)); });
    return canonicalPublicKey("/api/v1/workspace?" + p, publication);
  };
  if (key(request.query) !== key(base.request.query)) throw new Error("This report packet covers a different evidence selection. The public composer preserves your filters; use the published statewide scope or print/export your current investigation instead.");
  const selected = request.sections.filter(section => section.enabled), resultsSelected = selected.some(section => ["results_map", "results_distribution", "historical_trend", "comparison"].includes(section.id)), contextSelected = selected.some(section => section.id.startsWith("context_"));
  if (resultsSelected && (!sameScope(request.results as unknown as Record<string, unknown>, base.request.results as unknown as Record<string, unknown>) || request.map_metric !== base.request.map_metric)) throw new Error("The public report's historical result scope differs from these settings. Choose the published year, office and geography; no different election is substituted.");
  if (contextSelected && request.context_metric !== base.request.context_metric) throw new Error("The public report does not include that resident-context metric. Choose the published metric or remove that section.");
  const document = new DOMParser().parseFromString(base.html, "text/html"), main = document.querySelector("main");
  if (!main) throw new Error("The published report layout is invalid.");
  const available = new Map(base.sections.map(section => [section.id, section]));
  if (selected.some(section => !available.has(section.id))) throw new Error("A selected report section is not present in this public evidence packet.");
  const nodes = new Map([...document.querySelectorAll<HTMLElement>('section[id^="section-"]')].map(node => [node.id.slice(8), node]));
  nodes.forEach(node => node.remove());
  const footer = document.querySelector("footer");
  for (const section of selected) {
    const node = nodes.get(section.id);
    if (!node) throw new Error(`The ${section.id} figure layout is unavailable in this release.`);
    node.querySelectorAll(".caption").forEach(caption => caption.remove());
    if (section.caption.trim()) { const caption = document.createElement("p"); caption.className = "caption"; caption.textContent = "Researcher caption: " + section.caption; node.append(caption); }
    main.insertBefore(node, footer);
  }
  document.querySelectorAll(".notes").forEach(node => node.remove());
  if (request.include_notes && request.notes.trim()) {
    const notes = document.createElement("section"), heading = document.createElement("h2"), text = document.createElement("p");
    notes.className = "notes"; heading.textContent = "Personal research notes"; text.textContent = request.notes;
    notes.append(heading, text); main.insertBefore(notes, footer);
  }
  document.title = request.title;
  const title = document.querySelector("h1"); if (title) title.textContent = request.title;
  const notice = document.createElement("p"); notice.className = "warning"; notice.textContent = "Composed privately in this browser from published aggregate evidence. Personal notes are included only when explicitly selected. The original source revision remains pinned.";
  document.querySelector("header")?.append(notice);
  const bytes = new TextEncoder().encode(JSON.stringify({ schema: "observatory-browser-report-v1", source_content_sha256: base.content_sha256, revision: base.revision, request: { ...request, notes: request.include_notes ? request.notes : "" } }));
  const hash = Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", bytes))).map(v => v.toString(16).padStart(2, "0")).join("");
  if (footer) footer.textContent = `Published aggregate evidence · revision ${base.revision} · browser composition SHA-256 ${hash}. Source hashes and original evidence links are retained below.`;
  return { ...base, title: request.title, request, html: "<!doctype html>" + document.documentElement.outerHTML, content_sha256: hash, sections: selected.map(choice => available.get(choice.id)!), limitations: [...base.limitations, "Browser composition; PDF uses your browser's print renderer. Server-generated ZIP and arbitrary data queries require the local research edition."] };
}
export function publicReportCSV(report: ReportPreview) {
  const escape = (value: unknown) => { let text = String(value == null ? "" : typeof value === "object" ? JSON.stringify(value) : value); if (typeof value === "string" && /^[=+\-@\t\r]/.test(text)) text = "'" + text; return '"' + text.replaceAll('"', '""') + '"'; };
  return report.sections.flatMap(section => section.tables.flatMap((table, index) => {
    const detail = table as { title?: string; columns?: unknown[]; rows: unknown[] };
    return [[section.title, detail.title || `Table ${index + 1}`].map(escape).join(","), ...(detail.columns ? [detail.columns.map(escape).join(",")] : []), ...detail.rows.map(row => (Array.isArray(row) ? row : Object.values(row as object)).map(escape).join(",")), ""];
  })).join("\r\n");
}
