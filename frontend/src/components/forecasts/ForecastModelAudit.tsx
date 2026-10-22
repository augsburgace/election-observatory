import { CheckCircle2, CircleAlert, Microscope, MoveRight } from "lucide-react";
import type { ComparisonReview, EVCall } from "../../earlyVoteApi";
import { marginCallLabel } from "../../earlyVoteApi";
import { fmt, human } from "../../utils";
import "../../forecastAudit.css";

const color = (value: number) =>
  value > 0 ? "var(--red)" : value < 0 ? "var(--blue)" : "var(--muted)";

/** Signed bars have one common zero and scale; labels also carry the party. */
export function AuditMarginRows({
  rows,
}: {
  rows: { label: string; margin: number; detail?: string }[];
}) {
  const extent = Math.max(
    5,
    Math.ceil(Math.max(...rows.map((row) => Math.abs(row.margin))) / 5) * 5,
  );
  return (
    <div className="audit-margins">
      <div className="audit-axis">
        <span>Democratic advantage</span>
        <span>Even</span>
        <span>Republican advantage</span>
      </div>
      {rows.map((row, i) => (
        <div className="audit-margin-row" key={`${row.label}-${i}`}>
          <div>
            <b>{row.label}</b>
            <strong style={{ color: color(row.margin) }}>
              {marginCallLabel(row.margin)}
            </strong>
          </div>
          <div
            className="audit-margin-track"
            role="img"
            aria-label={`${row.label}: ${marginCallLabel(row.margin)}; common scale ${extent} points in either direction`}
          >
            <i className="audit-zero" />
            <span
              style={{
                left: `${50 + (Math.min(0, row.margin) / extent) * 50}%`,
                width: `${(Math.abs(row.margin) / extent) * 50}%`,
                background: color(row.margin),
              }}
            />
          </div>
          {row.detail && <small>{row.detail}</small>}
        </div>
      ))}
      <div className="audit-axis">
        <span>D+{extent}</span>
        <span>0</span>
        <span>R+{extent}</span>
      </div>
    </div>
  );
}

export function ForecastModelAudit({
  call,
  review,
}: {
  call: EVCall;
  review?: ComparisonReview;
}) {
  const audit = call.audit;
  if (!audit) return null;
  const reference = call.evidence.historical_reference;
  const validation = audit.validation;
  const outcomeCount = Number(
    validation.ev_assumption.independent_state_cycles || 0,
  );
  const rows = reference.cycles.map((row) => ({
    label: `${row.year} Senate result`,
    margin: row.margin_pp,
    detail: `${fmt(row.weight * 100, 1)}% of this historical reference · ${fmt(row.total_votes)} contest votes`,
  }));
  const components = audit.components.filter((row) => row.margin_pp != null);
  const turnout = call.evidence.turnout_projection;
  const remainder =
    turnout?.available && turnout.mode === "all"
      ? turnout.remaining_participation
      : null;
  const observed = call.evidence.early_vote.total;
  const projected = turnout?.projection;
  const currentShare =
    projected && observed != null && remainder != null
      ? Math.min(100, (observed / projected) * 100)
      : null;
  return (
    <section
      className="forecast-model-audit"
      id="forecast-model-audit"
      aria-labelledby="audit-title"
    >
      <div className="audit-heading">
        <div>
          <span className="audit-kicker">
            <Microscope size={18} /> Check the reasoning
          </span>
          <h4 id="audit-title">What earns this call?</h4>
        </div>
        <span
          className={`audit-role ${call.call.status === "ev_informed" ? "conditional" : "context"}`}
        >
          {audit.point_role}
        </span>
      </div>
      <p className="audit-conclusion">{audit.conclusion}</p>
      <div className="audit-components" aria-label="Point calculation">
        {components.map((row, i) => (
          <div key={row.label}>
            <span>{row.label}</span>
            <strong style={{ color: color(row.margin_pp!) }}>
              {row.label === "Eligible EV adjustment"
                ? `${row.margin_pp! > 0 ? "+" : ""}${fmt(row.margin_pp!, 2)} pp`
                : marginCallLabel(row.margin_pp)}
            </strong>
            <small>{human(row.role)}</small>
            {i < components.length - 1 && <MoveRight size={19} />}
          </div>
        ))}
      </div>
      <div className="audit-two-column">
        <article>
          <h5>The elections behind the reference</h5>
          <p>
            Only {human(audit.election_type)} Senate elections enter this point.
            Each bar shows an actual earlier result, not today’s voters.
          </p>
          {rows.length ? (
            <AuditMarginRows rows={rows} />
          ) : (
            <p>No eligible earlier same-type Senate outcome is retained.</p>
          )}
          {!!reference.excluded_context?.length && (
            <details>
              <summary>
                {reference.excluded_context.length} different-type outcomes
                excluded from the point
              </summary>
              <ul>
                {reference.excluded_context.map((row, i) => (
                  <li key={`${row.year}-${i}`}>
                    {row.year} · {human(row.election_type)} ·{" "}
                    {marginCallLabel(row.margin_pp)}
                  </li>
                ))}
              </ul>
            </details>
          )}
        </article>
        <article>
          <h5>Comparable evidence checklist</h5>
          <div className="audit-checks">
            {audit.checks.map((check) => (
              <div
                key={check.label}
                className={check.passed ? "supported" : "limited"}
              >
                {check.passed ? (
                  <CheckCircle2 size={18} />
                ) : (
                  <CircleAlert size={18} />
                )}
                <div>
                  <b>{check.label}</b>
                  <p>{check.detail}</p>
                </div>
              </div>
            ))}
          </div>
        </article>
      </div>
      <div className="audit-validation">
        <div>
          <span>Matching historical state/election outcomes</span>
          <strong>{outcomeCount}</strong>
          <small>
            {validation.independent_cycles.join(", ") ||
              "No matching held-out cycles"}
          </small>
        </div>
        <div>
          <span>Average absolute margin error</span>
          <strong>
            {validation.ev_assumption.margin_mae_pp == null
              ? "Not established"
              : `${fmt(validation.ev_assumption.margin_mae_pp, 1)} pp`}
          </strong>
          <small>
            {validation.historical_reference.margin_mae_pp == null
              ? "Insufficient comparable history"
              : `History-only error: ${fmt(validation.historical_reference.margin_mae_pp, 1)} pp`}
          </small>
        </div>
        <p>
          {validation.scope} No validated winner probability follows from these
          figures.
        </p>
      </div>
      <article className="audit-turnout">
        <h5>Votes earlier, or more voters overall?</h5>
        <p>{audit.state_note}</p>
        {currentShare != null && projected != null && remainder != null ? (
          <>
            <div className="audit-turnout-labels">
              <span>
                <b>{fmt(observed)}</b> observed early participation
              </span>
              <span>
                <b>{fmt(remainder)}</b> later participation under the analogue
              </span>
            </div>
            <div
              className="audit-turnout-track"
              role="img"
              aria-label={`${fmt(currentShare, 1)} percent of an assumed ${fmt(projected)} final participants have reported early participation; the remainder is conditional, not measured`}
            >
              <span style={{ width: `${currentShare}%` }} />
            </div>
            <p className="audit-caption">
              Assumed final participation: {fmt(projected)}. This is a
              historical turnout analogue, not a count of remaining candidate
              votes or a calibrated interval.
            </p>
          </>
        ) : (
          <p className="audit-caption">
            {turnout?.reason ||
              "A compatible final-turnout analogue is not established."}{" "}
            A source total alone cannot tell us how many votes remain or which
            party will receive them.
          </p>
        )}
      </article>
      {review && (review.studies.length > 0 || review.markets.length > 0) && (
        <article
          className={`audit-disagreement ${review.status === "review_required" ? "flagged" : ""}`}
        >
          <h5>
            {review.status === "review_required"
              ? "Outside evidence challenges this point"
              : "Compare the outside evidence"}
          </h5>
          <p>{review.interpretation}</p>
          {!!review.studies.length && (
            <AuditMarginRows
              rows={[
                { label: audit.point_role, margin: call.call.margin_pp || 0 },
                ...review.studies.map((row) => ({
                  label: row.producer,
                  margin: row.poll_margin_pp,
                  detail: `${row.field_end || "Fieldwork date not established"} · gap from research point: ${fmt(Math.abs(row.gap_pp), 1)} pp${row.large_gap || row.opposite_direction ? " · review flagged" : ""}`,
                })),
              ]}
            />
          )}
          {!!review.markets.length && (
            <div className="audit-market-quotes">
              {review.markets.map((row, i) => (
                <div key={`${row.label}-${i}`}>
                  <b>{row.label}</b>
                  <strong
                    style={{
                      color: row.party === "REP" ? "var(--red)" : "var(--blue)",
                    }}
                  >
                    {fmt(row.price_pct, 1)}%
                  </strong>
                  <span>
                    contract price ·{" "}
                    {row.challenges_direction
                      ? "challenges the direction"
                      : "separate market context"}
                  </span>
                </div>
              ))}
            </div>
          )}
          <details open={review.status === "review_required"}>
            <summary>Checks before trusting the disagreement</summary>
            <ol>
              {review.review_steps.map((step) => (
                <li key={step}>{step}</li>
              ))}
            </ol>
          </details>
        </article>
      )}
      <details className="audit-reading">
        <summary>How to read early votes without overreading them</summary>
        <ul>
          {audit.interpretation.map((text) => (
            <li key={text}>{text}</li>
          ))}
        </ul>
        <div>
          {audit.references.map((ref) => (
            <p key={ref.url}>
              <a href={ref.url} target="_blank" rel="noreferrer">
                {ref.title} ↗
              </a>
              <br />
              {ref.lesson}
            </p>
          ))}
          {audit.state_reference && (
            <a
              href={audit.state_reference.url}
              target="_blank"
              rel="noreferrer"
            >
              {audit.state_reference.title} ↗
            </a>
          )}
        </div>
      </details>
    </section>
  );
}
