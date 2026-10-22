import type { CSSProperties } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  BookOpen,
  Check,
  Download,
  FileText,
  Landmark,
  Radio,
  TrendingUp,
} from "lucide-react";
import { downloadData } from "../../api";
import {
  earlyVoteReasoning,
  marginCallLabel,
  type EVCall,
  type EvidenceReference,
} from "../../earlyVoteApi";
import { fmt, human } from "../../utils";
import { useViewOption } from "../../viewState";
import { Badge, Notice } from "../ui";
import { EvidenceLinks } from "./ForecastEvidenceLinks";
import { ContextSignal } from "./ForecastContextSignals";
import { ForecastModelAudit } from "./ForecastModelAudit";

function partyName(margin: number | null) {
  return margin == null
    ? "No supported party-margin call"
    : margin > 0
      ? "Republicans ahead"
      : margin < 0
        ? "Democrats ahead"
        : "An even race";
}
export function localBriefing(call: EVCall) {
  const early = call.evidence.early_vote,
    geography = call.evidence.geographic_tilt;
  return {
    headline:
      call.call.status === "reference_only"
        ? `${call.state_name}: historical reference only; EV direction not established`
        : `${call.state_name}: ${partyName(call.call.margin_pp).toLowerCase()}${call.call.margin_pp == null || call.call.margin_pp === 0 ? "" : ` by ${fmt(Math.abs(call.call.margin_pp), 1)} points`}`,
    summary:
      call.call.status === "ev_informed"
        ? `The early-vote call starts with prior Senate results and adjusts for where reported early participation is coming from. ${geography.same_stage ? "The geographic comparison uses a compatible stage of a prior early-voting cycle." : "The geographic comparison uses final historical results; a same-stage early-vote reference is unavailable."}`
        : `This is ${call.call.status === "reference_only" ? "a historical reference, because eligible incoming early-vote evidence cannot yet support a geographic adjustment" : "an evidence gap, because the available records or election rules do not support a defensible party-margin call"}.`,
    paragraphs: [
      {
        title: "What we have measured",
        text:
          early.total == null
            ? "No eligible current early-participation total is available for this call."
            : `${fmt(early.total)} ${early.metric_label || "reported early ballots"}, dated ${early.date || "date not established"}. These are participation records. They do not reveal how people voted.`,
      },
      {
        title: "How to use the call",
        text: "Read this as a provisional direction under stated assumptions. More early voting can reflect a change in timing or voting method, rather than higher final turnout. The historical tests and sensitivity range below show how much trust the estimate has earned.",
      },
    ],
  };
}
export function ForecastBriefing({
  call,
  cycle,
  revision,
  asOf,
  enabled = true,
}: {
  call: EVCall;
  cycle: number;
  revision: number;
  asOf?: string;
  enabled?: boolean;
}) {
  const [polls, setPolls] = useViewOption<string>("include_polls", "false"),
    [markets, setMarkets] = useViewOption<string>("include_markets", "false"),
    [context, setContext] = useViewOption<string>("include_context", "false");
  const switches = {
    polls: polls === "true",
    markets: markets === "true",
    context: context === "true",
  };
  const expanded = Object.values(switches).some(Boolean);
  const reasoning = useQuery({
    queryKey: [
      "forecast-reasoning",
      call.state,
      call.race_id,
      cycle,
      revision,
      asOf,
      switches.polls,
      switches.markets,
      switches.context,
    ],
    enabled,
    staleTime: Infinity,
    gcTime: 60_000,
    queryFn: ({ signal }) =>
      earlyVoteReasoning(
        {
          state: call.state,
          race_id: call.race_id,
          cycle,
          revision,
          as_of: asOf,
          include_polls: switches.polls,
          include_markets: switches.markets,
          include_context: switches.context,
        },
        signal,
      ),
  });
  const data = reasoning.data,
    fallback = localBriefing(call),
    color =
      call.call.margin_pp == null
        ? "var(--muted)"
        : call.call.margin_pp > 0
          ? "var(--red)"
          : call.call.margin_pp < 0
            ? "var(--blue)"
            : "var(--violet)";
  const paragraphs: {
    title: string;
    text: string;
    evidence_refs?: EvidenceReference[];
  }[] = data?.paragraphs || fallback.paragraphs;
  return (
    <section
      id="forecast-briefing"
      className="forecast-briefing forecast-anchor"
      aria-labelledby="forecast-briefing-title"
      style={{ "--briefing-direction": color } as CSSProperties}
    >
      <div className="briefing-heading">
        <div>
          <span className="call-eyebrow">
            <BookOpen size={16} /> Your election briefing · {call.state_name}
          </span>
          <h3 id="forecast-briefing-title">
            {data?.headline || fallback.headline}
          </h3>
        </div>
        <Badge tone={expanded ? "violet" : "teal"}>
          {expanded ? "EV + selected context" : "Early-vote evidence only"}
        </Badge>
      </div>
      <p className="briefing-summary">{data?.summary || fallback.summary}</p>
      <div className="briefing-method">
        <FileText size={17} />
        <span>
          Generated from the evidence in this investigation · r{revision} ·{" "}
          {asOf?.slice(0, 10) || "current cutoff"}. Source choices are saved
          with this investigation.
        </span>
      </div>
      <fieldset className="briefing-switches">
        <legend>What should inform the explanation?</legend>
        {[
          {
            id: "polls",
            label: "Polling",
            hint: "Compare with original survey results",
            value: switches.polls,
            update: setPolls,
            icon: <Radio size={19} />,
          },
          {
            id: "markets",
            label: "Betting markets",
            hint: "Review eligible market prices and their limits",
            value: switches.markets,
            update: setMarkets,
            icon: <TrendingUp size={19} />,
          },
          {
            id: "context",
            label: "Other context",
            hint: "Add separately sourced background",
            value: switches.context,
            update: setContext,
            icon: <Landmark size={19} />,
          },
        ].map((item) => (
          <label
            className={`briefing-switch ${item.value ? "on" : ""}`}
            key={item.id}
          >
            <input
              type="checkbox"
              role="switch"
              aria-label={`Include ${item.label.toLowerCase()} in explanation`}
              checked={item.value}
              onChange={(event) =>
                item.update(event.target.checked ? "true" : "false")
              }
            />
            <span className="briefing-switch-icon">{item.icon}</span>
            <span>
              <b>{item.label}</b>
              <small>{item.hint}</small>
            </span>
            <span className="briefing-switch-state" aria-hidden="true">
              {item.value ? (
                <>
                  <Check size={13} /> On
                </>
              ) : (
                "Off"
              )}
            </span>
          </label>
        ))}
      </fieldset>
      <p className="briefing-isolation">
        <b>
          {expanded
            ? "Eligible outside evidence is reviewed below for the sources you selected."
            : "The explanation uses early-vote evidence and its historical context."}
        </b>{" "}
        The EV-only margin stays the same. These switches do not turn betting
        prices into vote shares or create an untested combined forecast.
      </p>
      {expanded && (
        <button
          className="text-button briefing-reset"
          onClick={() => {
            setPolls("false");
            setMarkets("false");
            setContext("false");
          }}
        >
          Use early votes only
        </button>
      )}
      {reasoning.isFetching && (
        <p className="forecast-caption" role="status">
          Updating the sourced explanation for these choices…
        </p>
      )}
      {reasoning.isError && (
        <Notice tone="warning">
          The expanded explanation could not be loaded. The summary below uses
          the displayed EV call; external sources have not been added.{" "}
          {reasoning.error.message}
        </Notice>
      )}
      <ForecastModelAudit
        call={call}
        review={expanded ? data?.comparison_review : undefined}
      />
      <div className="briefing-paragraphs">
        {paragraphs.map((paragraph, index) => (
          <article key={`${paragraph.title}-${index}`}>
            <span className="briefing-step">
              {String(index + 1).padStart(2, "0")}
            </span>
            <div>
              <h4>{paragraph.title}</h4>
              <p>{paragraph.text}</p>
              <EvidenceLinks
                refs={paragraph.evidence_refs}
                label={`${paragraph.title} evidence`}
              />
            </div>
          </article>
        ))}
      </div>
      {!!data?.drivers?.length && (
        <div
          className="briefing-drivers"
          aria-label="What supports the explanation"
        >
          {data.drivers.map((driver, index) => (
            <article
              className={`briefing-driver ${driver.role}`}
              key={`${driver.label}-${index}`}
            >
              <span>{human(driver.role)}</span>
              <h4>{driver.label}</h4>
              {driver.value != null && (
                <strong
                  style={{
                    color:
                      driver.direction === "DEM"
                        ? "var(--blue)"
                        : driver.direction === "REP"
                          ? "var(--red)"
                          : undefined,
                  }}
                >
                  {typeof driver.value === "number"
                    ? driver.role === "measured"
                      ? fmt(driver.value)
                      : driver.role === "assumption" && driver.value === 0
                        ? "No shift"
                        : marginCallLabel(driver.value)
                    : driver.value}
                </strong>
              )}
              <p>{driver.text}</p>
            </article>
          ))}
        </div>
      )}
      {expanded && data?.signals && (
        <div className="briefing-signals">
          {switches.polls && data.signals.polls && (
            <ContextSignal
              title="Polling context"
              signal={data.signals.polls}
              kind="polls"
            />
          )}
          {switches.markets && data.signals.markets && (
            <ContextSignal
              title="Market context"
              signal={data.signals.markets}
              kind="markets"
            />
          )}
          {switches.context && data.signals.context && (
            <ContextSignal
              title="Other context"
              signal={data.signals.context}
              kind="other"
            />
          )}
        </div>
      )}
      {!!data?.warnings?.length && (
        <details className="briefing-caveats">
          <summary>What this explanation cannot establish</summary>
          <ul>
            {data.warnings.map((warning, index) => (
              <li key={index}>{warning}</li>
            ))}
          </ul>
        </details>
      )}
      <div className="briefing-footer">
        <span>
          Participation ≠ candidate votes. Blue and red describe explicit
          parties or historical party context.
        </span>
        {data && (
          <button
            className="text-button"
            onClick={() =>
              downloadData(
                data,
                `${call.state}-${cycle}-explanation-r${revision}.json`,
              )
            }
          >
            <Download size={15} /> Export this explanation
          </button>
        )}
      </div>
    </section>
  );
}
