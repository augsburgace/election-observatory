import { useQuery } from "@tanstack/react-query";
import { Cloud, Clock3, ShieldCheck } from "lucide-react";
import { getPublicManifest, isPublicMode, publicationAge, publicAlternatives } from "../publicData";
import type { ResearchQuery } from "../types";
export function PublicPublication() {
  const query = useQuery({ queryKey: ["public-publication"], queryFn: () => getPublicManifest(), enabled: isPublicMode(), refetchInterval: 60_000 });
  if (!isPublicMode() || !query.data) return null;
  const value = query.data, age = publicationAge(value), published = new Date(value.published_at);
  const sources = new URLSearchParams(location.search); sources.set("page", "sources");
  return <aside className={`public-publication ${age.status}`} aria-label="Public evidence publication status">
    <Cloud size={19}/><div><strong>Public research edition · validated revision {value.dataset_revision}</strong><p><time dateTime={value.published_at}>Published {Number.isNaN(published.valueOf()) ? value.published_at : published.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit", timeZoneName: "short" })}</time> · evidence through {value.data_as_of} · {value.schedule?.description || "Scheduled updates; last validated evidence remains available."}</p>
    {age.status !== "current" && <p className="public-delay"><Clock3 size={13}/>{age.status === "stale" ? "Publication is over 24 hours old. Check source reporting dates before interpreting changes." : "Publication is over 6 hours old; the next scheduled update may be delayed."}</p>}
    <p className="public-privacy"><ShieldCheck size={12}/> Notes and saved investigations stay in this browser. Download your notebook to keep a backup.</p></div><a href={`?${sources}`}>Coverage & sources ↗</a>
  </aside>;
}
export function PublishedAlternatives({ state, choose }: { state: string; choose: (query: Partial<ResearchQuery>) => void }) {
  const manifest = useQuery({ queryKey: ["public-publication"], queryFn: () => getPublicManifest(), enabled: isPublicMode() });
  const options = manifest.data ? publicAlternatives(manifest.data, state) : [];
  if (!isPublicMode() || !options.length) return null;
  return <div className="public-alternatives"><p>Available published investigations for this state:</p>{options.map((row, index) => {
    const clean = Object.fromEntries(Object.entries(row).filter(([key]) => ["state", "cycle", "baseline", "as_of", "revision", "metric", "mode", "time_basis", "alignment"].includes(key)));
    return <button className="button secondary small" key={index} onClick={() => choose({ ...clean, geography_ids: [], date_window: [], category: undefined, category_dimension: undefined } as Partial<ResearchQuery>)}>{String(row.cycle)} · {String(row.metric).replaceAll("_", " ")} · {String(row.mode).replaceAll("_", " ")}</button>;
  })}</div>;
}

export function PublicAttributions() {
  const manifest = useQuery({ queryKey: ["public-publication"], queryFn: () => getPublicManifest(), enabled: isPublicMode() });
  const credits = manifest.data?.attributions || [];
  if (!isPublicMode() || !credits.length) return null;
  return <section id="public-credits" className="public-credits"><h3>Data credits and original producers</h3><p>Official election authorities remain the original owners of reported voting data. These academic compilations fill explicitly labeled coverage gaps.</p>{credits.map(credit => <article key={credit.source_id}><h4><a href={credit.source_url} target="_blank" rel="noreferrer">{credit.title} ↗</a></h4><p><strong>{credit.creator}</strong> · <a href={credit.license_url} target="_blank" rel="noreferrer">{credit.license}</a> · retrieved <time dateTime={credit.retrieved_at}>{new Date(credit.retrieved_at).toLocaleString()}</time></p><details><summary>How this source is used</summary><p>{credit.transformation}</p><p>{credit.interpretation}</p>{credit.about_url && <a href={credit.about_url} target="_blank" rel="noreferrer">Producer’s methodology ↗</a>}</details></article>)}</section>;
}
