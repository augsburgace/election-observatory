import type {
  ReasoningSignal,
  ReasoningStudy,
  ReasoningMarket,
} from "../../earlyVoteApi";
import { fmt, human, partyColor } from "../../utils";
import { Badge } from "../ui";
import { EvidenceLinks } from "./ForecastEvidenceLinks";
import { fieldworkLabel, populationLabel, easternTimeLabel } from "../../forecastReadingLabels";
function PollingStudy({ study }: { study: ReasoningStudy }) {
  return (
    <article className="briefing-poll-study">
      <div className="briefing-poll-title">
        <h5>{study.producer}</h5>
        <Badge tone={study.secondary_summary ? "gold" : "violet"}>
          {study.secondary_summary ? "Secondary summary" : "Original survey"}
        </Badge>
      </div>
      <p className="briefing-study-meta">
        Interviewed <span title={`${study.field_start || ""} – ${study.field_end || ""}`}>{fieldworkLabel(study.field_start, study.field_end)}</span> · {populationLabel(study.population)}
        {study.sample_size
          ? ` · ${fmt(study.sample_size)} respondents`
          : " · Sample not disclosed"}
      </p>
      {study.question && (
        <p className="briefing-poll-question">{study.question}</p>
      )}
      <div className="briefing-poll-responses">
        {(study.estimates || []).map((estimate, index) => (
          <div key={`${estimate.candidate}-${index}`}>
            <span>
              {estimate.candidate || human(estimate.party || "Other response")}
            </span>
            <i>
              <b
                style={{
                  width:
                    typeof estimate.value === "number" &&
                    Number.isFinite(estimate.value)
                      ? `${Math.min(100, Math.max(0, estimate.value))}%`
                      : "0",
                  background:
                    estimate.party && /^(D|R)/i.test(estimate.party)
                      ? partyColor(estimate.party)
                      : "var(--muted)",
                }}
              />
            </i>
            <strong>
              {typeof estimate.value === "number" &&
              Number.isFinite(estimate.value)
                ? `${fmt(estimate.value, 1)}%`
                : "Not given"}
            </strong>
          </div>
        ))}
      </div>
      <EvidenceLinks
        refs={[
          ...(study.source_refs || []),
          ...(study.source_url
            ? [{ url: study.source_url, title: "Published result" }]
            : []),
          ...(study.document_url
            ? [{ url: study.document_url, title: "Questionnaire / tables" }]
            : []),
        ]}
      />
    </article>
  );
}
function MarketObservation({ market }: { market: ReasoningMarket }) {
  return (
    <article className="briefing-market-observation">
      <div>
        <h5>
          {market.outcome_label || human(market.party || "Market outcome")}
        </h5>
        <p>
          {market.provider || "Market provider"} · archived quote{" "}
          <time dateTime={market.quote_at} title={market.quote_at}>{easternTimeLabel(market.quote_at)}</time>
        </p>
      </div>
      <strong
        style={{
          color:
            market.party && /^(D|R)/i.test(market.party)
              ? partyColor(market.party)
              : "var(--gold)",
        }}
      >
        {market.price_pct == null ? "No quote" : `${fmt(market.price_pct, 1)}%`}
        <small>contract price</small>
      </strong>
      <p className="briefing-market-question">
        {market.question ||
          market.definition ||
          "A contract price is market context, not an observed vote share or a validated model probability."}
      </p>
      {market.provider_updated_at && (
        <p className="briefing-market-question">
          Provider updated: <time dateTime={market.provider_updated_at} title={market.provider_updated_at}>{easternTimeLabel(market.provider_updated_at)}</time>
        </p>
      )}
      {typeof market.best_bid === "number" &&
        typeof market.best_ask === "number" &&
        market.best_bid >= 0 &&
        market.best_ask <= 1 &&
        market.best_bid <= market.best_ask && (
          <p className="briefing-market-question">
            Bid {fmt(market.best_bid * 100, 1)}% · ask{" "}
            {fmt(market.best_ask * 100, 1)}% of the contract payout. The gap is
            the spread.
          </p>
        )}
      {market.settlement_rules && (
        <details className="briefing-market-question">
          <summary>Contract settlement rules</summary>
          <p>{market.settlement_rules}</p>
        </details>
      )}
      {market.liquidity_usd != null && (
        <p className="briefing-market-question">
          Reported liquidity: ${fmt(market.liquidity_usd)}
          {market.volume_usd != null
            ? ` · reported volume: $${fmt(market.volume_usd)}`
            : ""}
        </p>
      )}
      <EvidenceLinks
        refs={[
          ...(market.source_refs || []),
          ...(market.display_url || market.source_url
            ? [
                {
                  url: market.display_url || market.source_url,
                  title: "Original market",
                },
              ]
            : []),
        ]}
      />
    </article>
  );
}
export function ContextSignal({
  title,
  signal,
  kind,
}: {
  title: string;
  signal: ReasoningSignal;
  kind: string;
}) {
  const enabled = !["disabled", "off", "not_requested"].includes(signal.status);
  return (
    <article className={`briefing-signal ${kind}`}>
      <div className="briefing-signal-heading">
        <h4>{title}</h4>
        <Badge
          tone={
            enabled &&
            ["available", "included", "supported"].includes(signal.status)
              ? "teal"
              : "muted"
          }
        >
          {human(signal.status)}
        </Badge>
      </div>
      <p>
        {signal.summary ||
          signal.reason ||
          "No eligible evidence at this cutoff."}
      </p>
      {signal.summary && signal.reason && signal.reason !== signal.summary && (
        <p className="forecast-caption">{signal.reason}</p>
      )}
      {!!signal.studies?.length && (
        <>
          <div className="briefing-poll-studies">
            {signal.studies.slice(0, 4).map((study, index) => (
              <PollingStudy
                key={`${study.producer}-${study.field_end}-${index}`}
                study={study}
              />
            ))}
          </div>
          {signal.studies.length > 4 && (
            <details>
              <summary>
                Show {signal.studies.length - 4} more included studies
              </summary>
              <div className="briefing-poll-studies">
                {signal.studies.slice(4).map((study, index) => (
                  <PollingStudy
                    key={`${study.producer}-${study.field_end}-${index}`}
                    study={study}
                  />
                ))}
              </div>
            </details>
          )}
          <p className="forecast-caption">
            Bars retain the published response shares. Undecided and other
            responses are not redistributed, and different questions are not
            combined.
          </p>
        </>
      )}
      {!!signal.markets?.length && (
        <div className="briefing-market-grid">
          {signal.markets.map((market, index) => (
            <MarketObservation
              key={`${market.outcome_label}-${index}`}
              market={market}
            />
          ))}
        </div>
      )}
      {!!signal.items?.length && (
        <ul className="briefing-context-items">
          {signal.items.map((item, index) => (
            <li key={index}>
              {[
                item.title || item.label,
                item.text || item.description || item.summary || item.value,
              ]
                .filter((value) => typeof value === "string")
                .join(": ") ||
                "Inspect the exported evidence for this context item."}
              {typeof item.date === "string" && (
                <small> · captured <time dateTime={item.date} title={item.date}>{easternTimeLabel(item.date)}</time></small>
              )}
            </li>
          ))}
        </ul>
      )}
      <EvidenceLinks refs={signal.source_refs} label={`${title} sources`} />
    </article>
  );
}
