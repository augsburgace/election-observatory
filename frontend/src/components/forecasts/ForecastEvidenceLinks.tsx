import { ExternalLink } from "lucide-react";
import type { EvidenceReference } from "../../earlyVoteApi";
export function EvidenceLinks({
  refs,
  label = "Sources",
}: {
  refs?: EvidenceReference[];
  label?: string;
}) {
  const links = (refs || [])
    .flatMap((ref) => {
      const url =
        typeof ref.url === "string"
          ? ref.url
          : typeof ref.source_url === "string"
            ? ref.source_url
            : null;
      return url && /^https?:\/\//i.test(url)
        ? [
            {
              url,
              name: String(
                ref.title || ref.name || ref.source_id || "Original evidence",
              ),
            },
          ]
        : [];
    })
    .filter(
      (ref, index, all) =>
        all.findIndex((candidate) => candidate.url === ref.url) === index,
    );
  if (!links.length) return null;
  return (
    <div className="briefing-evidence-links" aria-label={label}>
      {links.slice(0, 8).map((ref) => (
        <a key={ref.url} href={ref.url} target="_blank" rel="noreferrer">
          {ref.name}
          <ExternalLink size={13} />
        </a>
      ))}
    </div>
  );
}
