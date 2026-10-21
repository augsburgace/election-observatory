import { publicFetch } from "../publicData";
import { useQuery } from "@tanstack/react-query";
import { BookOpen, Clock3, FileSearch, Layers3 } from "lucide-react";
import type { AppContext, ResearchQuery } from "../types";
import { queryString } from "../api";
import { fmt, human } from "../utils";
import "../participation.css";

type Quality = {
  revision: number; status: string; metric: { label: string; description?: string; unit: string };
  headline: { value: number | null; date: string | null; days_old_at_cutoff: number | null; newly_reported: number | null; previous_report_date: string | null; change_is_correction: boolean };
  coverage: { reporting_areas: number; carried_forward_count: number; oldest_component_date?: string; difference_from_selected_total?: number | null; types: string[] };
  comparison: { available: boolean; reason: string; baseline: number; ratio: number | null };
  sources: { id: string; name: string; authority: string; tier: number; url: string; native_definitions: string[]; flags: string[]; observation_ids: number[]; last_checked: string; collection_status: string }[];
  read_this_first: string[]; warnings: string[];
  recommended_selection?: Partial<ResearchQuery>;
};

export default function EarlyVotingGuide({ query, workspace, inspect, setQuery }: AppContext) {
  const pinned = { ...query, revision: query.revision ?? workspace.revision };
  const quality = useQuery({ queryKey: ["participation-quality", pinned], queryFn: async ({ signal }) => {
    const response = await publicFetch(`/api/v2/participation/quality?${queryString(pinned)}`, { signal });
    if (!response.ok) throw new Error("The interpretation panel could not load; the underlying research remains available.");
    return response.json() as Promise<Quality>;
  }});
  if (quality.isPending) return <div className="ev-guide-status" role="status">Checking definitions, source dates, and comparison coverage…</div>;
  if (!quality.data) return <p className="ev-guide-status">{quality.error?.message}</p>;
  const q = quality.data;
  return <section className="ev-guide" aria-label="Understand this early-voting evidence">
    <div className="ev-guide-heading"><BookOpen size={18}/><div><h3>Read the early-voting evidence correctly.</h3><p>{q.metric.description}</p></div><span className="ev-evidence-tag">Reported evidence · r{q.revision}</span></div>
    <div className="ev-reading-grid">
      <article><span className="ev-reading-label"><Layers3 size={14}/> What is measured</span><strong>{q.headline.value == null ? "Not available" : fmt(q.headline.value)}</strong><span>{q.metric.label} · {human(query.mode)}</span><p>{q.sources.length ? q.sources.map(s=>s.authority).filter((s,i,a)=>a.indexOf(s)===i).join(" + ") : "No compatible source observation at this cutoff."}</p>
        {q.status === "unavailable" && q.recommended_selection && <button className="text-button" onClick={()=>setQuery(q.recommended_selection!)}>Open an available participation measure →</button>}
      </article>
      <article><span className="ev-reading-label"><Clock3 size={14}/> Evidence date</span><strong>{q.headline.date || "Not established"}</strong><span>{q.headline.days_old_at_cutoff == null ? "" : q.headline.days_old_at_cutoff === 0 ? "Report matches the selected day" : `${q.headline.days_old_at_cutoff} day(s) before the cutoff`}</span><p>{q.coverage.carried_forward_count ? `${q.coverage.carried_forward_count} components carried forward; oldest ${q.coverage.oldest_component_date}.` : "The report date and retrieval time are separate. A successful source check does not mean new voting."}</p></article>
      <article><span className="ev-reading-label"><FileSearch size={14}/> Historical meaning</span><strong>{q.comparison.available ? `${fmt((q.comparison.ratio || 0)*100,1)}%` : "Pace unavailable"}</strong><span>{q.comparison.available ? `of compatible ${q.comparison.baseline} participation` : `Compared with ${q.comparison.baseline}`}</span><p>{q.comparison.reason}</p></article>
    </div>
    {q.headline.newly_reported != null && <div className="ev-change-explanation"><b>{q.headline.change_is_correction ? "Reported downward correction" : "Newly reported"}: {fmt(q.headline.newly_reported)}</b><span>Since {q.headline.previous_report_date || "the preceding report"}. This is a change between reports, not a claim about ballots voted on one day.</span></div>}
    {q.coverage.difference_from_selected_total != null && q.coverage.difference_from_selected_total !== 0 && <p className="ev-coverage-alert">Geographic detail differs from the selected total by {fmt(q.coverage.difference_from_selected_total)}. Definitions, reporting coverage, or dates may differ; the map is not silently rescaled.</p>}
    <details><summary>Definitions, original sources, and what this evidence supports</summary>
      <div className="ev-source-grid">{q.sources.map(s=><article key={s.id}><h4>{s.name}</h4><span>{s.authority} · tier {s.tier}</span>{s.native_definitions.map(d=><p key={d}>{d}</p>)}{s.flags.map(f=><p key={f} className="ev-source-note">{f}</p>)}<div className="ev-source-actions"><a href={s.url} target="_blank" rel="noreferrer">Original source ↗</a>{s.observation_ids[0] && <button className="text-button" onClick={()=>inspect({type:"observation",id:s.observation_ids[0]})}>Inspect archived observation</button>}</div><small>Source health checked {s.last_checked?.slice(0,19).replace("T"," ") || "not established"} · {human(s.collection_status)}. Operational health is current; the evidence above remains pinned.</small></article>)}</div>
      <ul className="ev-reading-notes">{q.read_this_first.map(t=><li key={t}>{t}</li>)}</ul>
      {!q.sources.length && <p>No matching source observations exist for this exact metric, method, date, and revision. Missing observations are not zero.</p>}
    </details>
  </section>;
}
