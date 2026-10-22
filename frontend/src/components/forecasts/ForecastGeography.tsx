import { memo, useMemo } from "react";
import { MapPin, ArrowRight } from "lucide-react";
import type { AppContext } from "../../types";
import type { EVCall } from "../../earlyVoteApi";
import {
  forecastMapRows,
  nationalCallRows,
  type ForecastMapLayer,
} from "../../forecastResearchMath";
import { marginCallLabel } from "../../researchCallMath";
import { NationalMap, StateMap } from "../Maps";
import { Empty, Notice, Panel, Segmented } from "../ui";
import { ResearchGuide } from "../ResearchGuide";
import { useViewOption } from "../../viewState";
import { focusGeography } from "../../interaction";
import { fmt } from "../../utils";
const color = (value: number) => (value >= 0 ? "var(--red)" : "var(--blue)");
export const NationalForecastMap = memo(function NationalForecastMap({
  calls,
  selected,
  onSelect,
}: {
  calls: EVCall[];
  selected?: EVCall | null;
  onSelect: (state: string) => void;
}) {
  const [view, setView] = useViewOption<string>(
    "forecast_national_map",
    "geographic",
  );
  const [scope, setScope] = useViewOption<string>(
    "forecast_national_scope",
    "ev_supported",
  );
  const rows = useMemo(
    () =>
      nationalCallRows(calls, selected?.race_id).map((row) =>
        scope === "ev_supported" && row.coverage_status !== "ev_informed"
          ? { ...row, value: null }
          : row,
      ),
    [calls, selected?.race_id, scope],
  );
  return (
    <Panel
      title="The Senate map, with the evidence attached"
      subtitle={
        scope === "ev_supported"
          ? "Only points with an eligible same-stage EV adjustment are colored. Unavailable EV evidence is never replaced by a historical party-colored call."
          : "Historical and conditional Republican − Democratic reference points. These colors are research context, not validated winner predictions."
      }
    >
      <div className="forecast-map-toolbar">
        <Segmented
          label="Senate map evidence scope"
          value={scope}
          onChange={setScope}
          items={[
            { id: "ev_supported", label: "Eligible EV comparisons" },
            { id: "all_context", label: "Include historical references" },
          ]}
        />
        <Segmented
          label="Senate call map view"
          value={view}
          onChange={setView}
          items={[
            { id: "geographic", label: "Geographic map" },
            { id: "tiles", label: "State tiles" },
          ]}
        />
        <span>
          Open a state to inspect its assumptions <ArrowRight size={13} />
        </span>
      </div>
      {typeof window !== "undefined" ? (
        <NationalMap
          rows={rows}
          selected={selected?.state || ""}
          onSelect={onSelect}
          layer="margin"
          marginContext={
            scope === "ev_supported"
              ? "Eligible same-stage EV research point · R−D percentage points"
              : "Historical / conditional research margin · R−D percentage points"
          }
          missingLabel="No published conditional margin; open available research"
          tile={view === "tiles"}
        />
      ) : (
        <p className="body-copy">
          Interactive geographic and state-tile maps load in the browser; the
          complete race table remains available below.
        </p>
      )}
      <div
        className="forecast-map-key"
        aria-label="Conditional margin map legend"
      >
        <span>
          <i style={{ background: "#235fa8" }} />D more than 10 pp
        </span>
        <span>
          <i style={{ background: "#91b4e0" }} />D 0–10 pp
        </span>
        <span>
          <i style={{ background: "#e29da9" }} />R 0–10 pp
        </span>
        <span>
          <i style={{ background: "#bf354e" }} />R more than 10 pp
        </span>
        <span>
          <i className="missing" />
          No published point / no contest / multiple races / EV unsupported in
          this view
        </span>
      </div>
      <ResearchGuide
        what="Each state’s conditional party-margin point from this exact model run. No seat-win probability or chamber-control probability is encoded."
        how="Blue and red identify explicit Democratic and Republican party margins. Patterned states lack a usable selected point. A state with two Senate contests is not pooled: select its exact contest in the race board. Sensitivity ranges and evidence quality are essential context."
        source="The same versioned research call objects used by the race table, state explanation, JSON export, and report."
      />
    </Panel>
  );
});
export const ForecastGeography = memo(function ForecastGeography({
  ctx,
  call,
}: {
  ctx: AppContext;
  call: EVCall;
}) {
  const [storedLayer, setLayer] = useViewOption<string>(
    "forecast_geo_layer",
    "volume",
  );
  const layer: ForecastMapLayer = ["volume", "margin", "contribution"].includes(
    storedLayer,
  )
    ? (storedLayer as ForecastMapLayer)
    : "volume";
  const rows = useMemo(() => forecastMapRows(call, layer), [call, layer]);
  const tilt = call.evidence.geographic_tilt;
  const selected = tilt.rows.find((row) =>
    (ctx.selectedGeographyIds ?? ctx.query.geography_ids).includes(row.id),
  );
  const ranked = useMemo(
    () =>
      [...tilt.rows].sort(
        (a, b) => Math.abs(b.contribution_pp) - Math.abs(a.contribution_pp),
      ),
    [tilt.rows],
  );
  const label =
    layer === "volume"
      ? "Measured reported early participation"
      : layer === "margin"
        ? `${tilt.reference_year || "Historical"} ${tilt.reference_office || "election"} R−D margin`
        : "Contribution to geographic-context tilt";
  return (
    <section id="forecast-geography" className="forecast-anchor">
      <Panel
        title="Where the early-vote signal comes from"
        subtitle="Start with the actual ballot totals. Then see how the locations compare with past elections, and which places move the call."
      >
        <Segmented
          label="Forecast geographic evidence layer"
          value={layer}
          onChange={setLayer}
          items={[
            { id: "volume", label: "Measured EV volume" },
            { id: "margin", label: "Historical party context" },
            { id: "contribution", label: "Geographic contribution" },
          ]}
        />
        {rows.length ? (
          <>
            {!tilt.available && (
              <Notice tone="warning">
                These geographic inputs are diagnostic only and do not adjust
                the call. {tilt.description}
              </Notice>
            )}
            <div className="forecast-geography-grid">
              <div>
                {typeof window !== "undefined" ? (
                  <StateMap
                    state={call.state}
                    rows={rows}
                    selected={
                      ctx.selectedGeographyIds ?? ctx.query.geography_ids
                    }
                    onSelect={(id) => ctx.setQuery({ geography_ids: [id] })}
                    layer={layer === "contribution" ? "swing" : layer}
                    metricLabel={label}
                    unit={layer === "volume" ? "ballots" : "pp"}
                    height={430}
                  />
                ) : (
                  <p>
                    {rows.length} exact geographic model inputs; interactive map
                    loads in the browser.
                  </p>
                )}
                <p className="forecast-caption">
                  {layer === "volume"
                    ? "Circle area represents reported ballots. Unreported areas remain missing."
                    : layer === "margin"
                      ? "Historical candidate results provide geographic context. They do not identify current early-voter choices."
                      : "Shows which places move the historical party context: red toward Republicans, blue toward Democrats. It combines the change in a county’s share of participation with its past party margin; the weight applied to the call is an assumption."}
                </p>
              </div>
              <aside className="forecast-place-card">
                <span className="call-eyebrow">
                  <MapPin size={13} />{" "}
                  {selected ? "Selected model input" : "Choose a place"}
                </span>
                <h4>{selected?.name || "Follow the geography"}</h4>
                {selected ? (
                  <>
                    <strong className="forecast-place-total">
                      {fmt(selected.early_votes)}
                    </strong>
                    <p>reported ballots · {selected.current_source_date}</p>
                    <dl className="call-facts">
                      <div>
                        <dt>Share of matched EV</dt>
                        <dd>{fmt(selected.early_share_pct, 2)}%</dd>
                      </div>
                      <div>
                        <dt>Reference geographic share</dt>
                        <dd>{fmt(selected.reference_share_pct, 2)}%</dd>
                      </div>
                      <div>
                        <dt>Historical party margin</dt>
                        <dd
                          style={{ color: color(selected.reference_margin_pp) }}
                        >
                          {marginCallLabel(selected.reference_margin_pp)}
                        </dd>
                      </div>
                      <div>
                        <dt>Context contribution</dt>
                        <dd style={{ color: color(selected.contribution_pp) }}>
                          {fmt(selected.contribution_pp, 3)} points
                        </dd>
                      </div>
                    </dl>
                    <p className="forecast-caption">
                      {tilt.same_stage
                        ? "Reference shares use compatible same-stage EV."
                        : "Reference shares use final historical candidate-vote distribution; they are not same-stage EV."}
                    </p>
                    <button
                      className="text-button"
                      onClick={() => ctx.setPage("place")}
                    >
                      Open place dossier <ArrowRight size={13} />
                    </button>
                    {selected.source_refs?.length ? (
                      <details>
                        <summary>Inspect the original source records</summary>
                        <pre className="call-manifest">
                          {JSON.stringify(selected.source_refs, null, 2)}
                        </pre>
                      </details>
                    ) : null}
                  </>
                ) : (
                  <p>
                    Select a county on the map or in the ranked list. The same
                    identifier highlights the map, contribution chart, input
                    table, and dossier selection.
                  </p>
                )}
                <div className="forecast-place-rank">
                  {ranked.slice(0, 8).map((row) => (
                    <button
                      key={row.id}
                      className={selected?.id === row.id ? "selected" : ""}
                      onMouseEnter={() => focusGeography(row.id)}
                      onMouseLeave={() => focusGeography(null)}
                      onFocus={() => focusGeography(row.id)}
                      onBlur={() => focusGeography(null)}
                      onClick={() => ctx.setQuery({ geography_ids: [row.id] })}
                    >
                      <span>{row.name}</span>
                      <b style={{ color: color(row.contribution_pp) }}>
                        {row.contribution_pp > 0 ? "+" : ""}
                        {fmt(row.contribution_pp, 2)} pp
                      </b>
                    </button>
                  ))}
                </div>
              </aside>
            </div>
            <ResearchGuide
              what="Exact county inputs included in, or explicitly excluded from, the model's geographic calculation."
              how="Start with measured volume, then compare historical context and contributions. Current EV composition and final election partisanship are different measurements. The contribution map shows a reproducible calculation, not an inferred map of candidate votes. Missing data is never filled using neighbors."
              source={`${call.state_name} · ${call.evidence.early_vote.date || "date unavailable"} · ${tilt.description}`}
            />
          </>
        ) : (
          <Empty title="No compatible geographic model inputs">
            The current call uses its disclosed statewide or historical
            reference evidence. State totals are not distributed into counties
            or precincts. Use the Atlas for separately labeled historical
            precinct context.
          </Empty>
        )}
      </Panel>
    </section>
  );
});
