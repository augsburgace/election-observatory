import { Info, ExternalLink } from "lucide-react";
export function ResearchGuide({
  what,
  how,
  source,
}: {
  what: string;
  how: string;
  source?: string;
}) {
  return (
    <details className="research-guide">
      <summary>
        <Info size={14} />
        How to read this
      </summary>
      <div>
        <p>
          <b>What this shows.</b> {what}
        </p>
        <p>
          <b>How to read it.</b> {how}
        </p>
        {source && (
          <p>
            <b>Source.</b>{" "}
            {source.startsWith("http") ? (
              <a href={source} target="_blank" rel="noreferrer">
                Original publication <ExternalLink size={12} />
              </a>
            ) : (
              source
            )}
          </p>
        )}
      </div>
    </details>
  );
}
