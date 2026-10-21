import { publicFetch, isPublicMode } from "./publicData";
import type {
  Bootstrap,
  Evidence,
  Job,
  ResearchObject,
  ResearchQuery,
  Source,
  Workspace,
} from "./types";
const BASE = "/api/v1";
export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}
export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await publicFetch(`${BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new ApiError(
      typeof body.detail === "string"
        ? body.detail
        : body.message || `Request failed (${response.status})`,
      response.status,
    );
  }
  if (response.status === 204) return undefined as T;
  return response.json();
}
export function queryString(query: Partial<ResearchQuery>) {
  const params = new URLSearchParams();
  Object.entries(query).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      if (Array.isArray(value)) params.set(key, value.join(","));
      else params.set(key, String(value));
    }
  });
  return params.toString();
}
export const api = {
  bootstrap: () => request<Bootstrap>("/bootstrap"),
  workspace: (query: ResearchQuery, signal?: AbortSignal) =>
    request<Workspace>(`/workspace?${queryString(query)}`, { signal }),
  sources: () =>
    request<Source[] | { sources: Source[]; jobs?: Job[] }>("/sources"),
  evidence: (id: string | number) => request<Evidence>(`/evidence/${id}`),
  research: () =>
    request<ResearchObject[] | { items: ResearchObject[] }>("/research"),
  saveResearch: (data: Partial<ResearchObject>) =>
    request<ResearchObject>("/research", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  updateResearch: (id: number, data: Partial<ResearchObject>) =>
    request<ResearchObject>(`/research/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  deleteResearch: (id: number) =>
    request<void>(`/research/${id}`, { method: "DELETE" }),
  refresh: () =>
    request<Job>("/refresh", { method: "POST", body: JSON.stringify({}) }),
  jobs: () => request<Job[] | { jobs: Job[] }>("/jobs"),
  scenario: (payload: Record<string, unknown>) =>
    request<Record<string, unknown>>("/scenarios", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  forecasts: (query: ResearchQuery) =>
    request<Record<string, unknown>>(`/forecasts?${queryString(query)}`),
};
export function downloadData(
  data: unknown,
  filename: string,
  type = "application/json",
) {
  const body = typeof data === "string" ? data : JSON.stringify(data, null, 2);
  const url = URL.createObjectURL(new Blob([body], { type }));
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
export async function downloadExport(
  query: ResearchQuery,
  format: string,
  extra: Record<string, unknown> = {},
) {
  if (isPublicMode()) {
    if (format === "pdf" || format === "html") { window.print(); return; }
    const data = await api.workspace(query);
    if (format === "json") downloadData(data, `observatory-${query.state}-r${data.revision}.json`);
    else if (format === "csv") downloadData(aggregateCSV(data.geographies || data.observations || []), `observatory-${query.state}-r${data.revision}.csv`, "text/csv");
    else throw new Error("The public edition exports CSV, JSON and browser-print PDF. Full ZIP packages are available through the local research edition.");
    return;
  }
  const params = new URLSearchParams(queryString(query));
  params.set("format", format);
  Object.entries(extra).forEach(([key, value]) =>
    params.set(key, Array.isArray(value) ? value.join(",") : String(value)),
  );
  const custom = Object.keys(extra).length > 0;
  const response = await publicFetch(
    custom ? `${BASE}/exports` : `${BASE}/exports?${params}`,
    custom
      ? {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ query, format, ...extra }),
        }
      : undefined,
  );
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(
      typeof body.detail === "string"
        ? body.detail
        : `Export failed (${response.status})`,
    );
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `observatory-${query.state}-${query.cycle}-r${query.revision ?? "latest"}.${format}`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export async function downloadHistoricalExport(
  query: Record<string, unknown>,
  format: string,
) {
  if (isPublicMode()) {
    if (["pdf", "html"].includes(format)) { window.print(); return; }
    const { atlasApi } = await import("./atlasApi");
    const data = await atlasApi.results(query);
    if (format === "json") downloadData(data, `observatory-${query.state}-${query.year}-historical.json`);
    else if (format === "csv") downloadData(aggregateCSV(data.geographies), `observatory-${query.state}-${query.year}-historical.csv`, "text/csv");
    else throw new Error("This export is available in the local research edition. Choose CSV, JSON or Print / PDF on the public site.");
    return;
  }
  const params = new URLSearchParams();
  Object.entries({ ...query, format }).forEach(([key, value]) => {
    if (value != null && value !== "")
      params.set(key, Array.isArray(value) ? value.join(",") : String(value));
  });
  const response = await publicFetch(`/api/v2/results/exports?${params}`);
  if (!response.ok) {
    const p = await response.json().catch(() => ({}));
    throw new Error(
      typeof p.detail === "string"
        ? p.detail
        : `Historical export failed (${response.status})`,
    );
  }
  const url = URL.createObjectURL(await response.blob());
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `observatory-${query.state}-${query.year}-historical.${format}`;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
export async function downloadContextExport(
  query: Record<string, unknown>,
  format: string,
) {
  if (isPublicMode()) {
    if (["pdf", "html"].includes(format)) { window.print(); return; }
    const { atlasApi } = await import("./atlasApi");
    const data = await atlasApi.context(String(query.state), Number(query.revision) || undefined);
    if (format === "json") downloadData(data, `observatory-${query.state}-population-context.json`);
    else if (format === "csv") downloadData(aggregateCSV(data.rows || data.estimates || []), `observatory-${query.state}-population-context.csv`, "text/csv");
    else throw new Error("Choose CSV, JSON or browser-print PDF for published aggregate context.");
    return;
  }
  const p = new URLSearchParams();
  Object.entries({ ...query, format }).forEach(([key, value]) => {
    if (value != null && value !== "")
      p.set(key, Array.isArray(value) ? value.join(",") : String(value));
  });
  const response = await publicFetch(`/api/v2/context/exports?${p}`);
  if (!response.ok) {
    const b = await response.json().catch(() => ({}));
    throw new Error(
      typeof b.detail === "string"
        ? b.detail
        : `Context export failed (${response.status})`,
    );
  }
  const url = URL.createObjectURL(await response.blob()),
    anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `observatory-${query.state}-${query.metric}-population-context.${format}`;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function aggregateCSV(input: unknown): string {
  const rows = Array.isArray(input) ? input : [];
  const keys = [...new Set(rows.flatMap(row => Object.keys(row)))];
  const cell = (value: unknown) => { let text = String(value == null ? "" : typeof value === "object" ? JSON.stringify(value) : value); if (typeof value === "string" && /^[=+\-@\t\r]/.test(text)) text = "'" + text; return '"' + text.replaceAll('"', '""') + '"'; };
  return [keys.map(cell).join(","), ...rows.map(row => keys.map(key => cell(row[key])).join(","))].join("\r\n");
}
