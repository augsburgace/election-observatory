import { useQuery } from "@tanstack/react-query";
import { Download, FlaskConical } from "lucide-react";
import { downloadData } from "../../api";
import {
  earlyVoteFeatureTests,
  type EVFeatureTests,
  type EVFeatureExperiment,
  type FeatureTestMetrics,
} from "../../earlyVoteApi";
import { fmt, human } from "../../utils";
import { useViewOption } from "../../viewState";
import { Badge, Loading, Notice, Panel, Select, Segmented } from "../ui";
import { ResearchGuide } from "../ResearchGuide";
import { EvidenceLinks } from "./ForecastEvidenceLinks";
export function featureError(metrics?: FeatureTestMetrics) {
  const value = metrics?.margin_mae_pp ?? metrics?.mae_pp;
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}
function stratumKey(experiment: EVFeatureExperiment) {
  return JSON.stringify([
    experiment.chronology,
    experiment.alignment,
    experiment.reference_kind,
  ]);
}
function stratumLabel(experiment: EVFeatureExperiment) {
  return `${experiment.chronology === "strict_contemporary" ? "Reports available at the time" : "Recovered historical reports"} · ${experiment.alignment === "days_since_opening" ? "days after voting opened" : "days until Election Day"} · ${experiment.reference_kind?.startsWith("same_stage") ? "same-stage EV geography" : experiment.reference_kind === "statewide_ev_only" ? "statewide EV" : "final-result geography"}`;
}
export function FeatureTestResults({ data }: { data: EVFeatureTests }) {
  const [inventoryFamily, setInventoryFamily] = useViewOption<string>(
    "forecast_feature_inventory",
    "statewide",
  );
  const inventory =
    inventoryFamily === "geography" && data.geographic_feature_inventory
      ? data.geographic_feature_inventory
      : data.feature_inventory;
  const names = new Map(
    data.feature_inventory.map((feature) => [feature.id, feature.label]),
  );
  const [savedStratum, setStratum] = useViewOption<string>(
    "forecast_feature_stratum",
    "headline",
  );
  const strata = [
    ...new Map(
      data.experiments.map((experiment) => [
        stratumKey(experiment),
        experiment,
      ]),
    ).entries(),
  ];
  const validStratum = strata.some(([key]) => key === savedStratum);
  const experiments = validStratum
    ? data.experiments.filter(
        (experiment) => stratumKey(experiment) === savedStratum,
      )
    : (data.headline_experiments ?? data.experiments);
  return (
    <>
      <div className="forecast-feature-intro">
        <FlaskConical size={26} />
        <div>
          <h3>More data earns its place by improving past predictions.</h3>
          <p>
            For each historical test, the model may learn only from earlier
            elections. Added factors are compared on the same held-out races
            against history alone and the existing geographic model. An
            unavailable result is a data gap, never evidence of zero effect.
            Coverage below refers to the collected Senate test archive.
          </p>
        </div>
      </div>
      <div className="forecast-feature-inventory-controls">
        {data.geographic_feature_inventory && (
          <Segmented
            label="Feature evidence coverage"
            value={inventoryFamily}
            onChange={setInventoryFamily}
            items={[
              { id: "statewide", label: "Statewide early voting" },
              { id: "geography", label: "With county comparisons" },
            ]}
          />
        )}
        {data.coverage_scope && (
          <p>
            {data.coverage_scope.states.length} states reviewed ·{" "}
            {fmt(data.coverage_scope.statewide_cases)} statewide checkpoints ·{" "}
            {fmt(data.coverage_scope.geographic_cases)} geographic checkpoints.
            Supported factors may cover fewer elections.
          </p>
        )}
      </div>
      <div className="forecast-feature-inventory">
        {inventory.map((feature) => (
          <article key={feature.id} data-feature={feature.id}>
            <span className="call-eyebrow">Available historical evidence</span>
            <h4>{feature.label}</h4>
            <strong>
              {fmt(feature.available_state_cycles)}{" "}
              <small>state-election records</small>
            </strong>
            <p>{feature.definition}</p>
            <span className="forecast-caption">
              {fmt(feature.available_cases)} supported checkpoints ·{" "}
              {fmt(feature.missing_cases)} missing
            </span>
            <EvidenceLinks
              refs={feature.source_refs}
              label={`${feature.label} sources`}
            />
          </article>
        ))}
      </div>
      <div className="forecast-feature-policy">
        <Select
          label="Added-factor comparison policy"
          value={validStratum ? savedStratum : "headline"}
          onChange={setStratum}
          options={[
            { value: "headline", label: "Main historical comparison" },
            ...strata.map(([value, experiment]) => ({
              value,
              label: stratumLabel(experiment),
            })),
          ]}
        />
        <p>
          Compare methods within one evidence policy. Contemporary and recovered
          reports, voting stages and reference definitions remain separate.
        </p>
      </div>
      <div className="table-scroll">
        <table className="forecast-feature-table">
          <thead>
            <tr>
              <th>Added evidence</th>
              <th>Historical reference error</th>
              <th>Geography-only error</th>
              <th>With added evidence</th>
              <th>What the test supports</th>
            </tr>
          </thead>
          <tbody>
            {experiments.map((experiment) => {
              const baseline = featureError(experiment.paired?.baseline),
                geography = featureError(experiment.paired?.geography_only),
                augmented = featureError(experiment.paired?.augmented),
                comparison =
                  experiment.comparator === "historical_baseline"
                    ? baseline
                    : geography,
                comparisonLabel =
                  experiment.comparator === "historical_baseline"
                    ? "history"
                    : "geography only",
                difference =
                  comparison != null && augmented != null
                    ? comparison - augmented
                    : null;
              return (
                <tr key={experiment.id}>
                  <td>
                    <b>
                      {experiment.label ||
                        experiment.features
                          .map((id) => names.get(id) || human(id))
                          .join(" + ") ||
                        human(experiment.id)}
                    </b>
                    <small>
                      {/insufficient|not_enough/.test(experiment.status)
                        ? "Needs more earlier-election evidence"
                        : human(experiment.status)}
                    </small>
                  </td>
                  <td>
                    {baseline == null
                      ? "Not testable yet"
                      : `${fmt(baseline, 2)} points`}
                  </td>
                  <td>
                    {experiment.comparator === "historical_baseline"
                      ? "Not part of this test"
                      : geography == null
                        ? "Not testable yet"
                        : `${fmt(geography, 2)} points`}
                  </td>
                  <td>
                    {augmented == null ? (
                      "Not testable yet"
                    ) : (
                      <>
                        <b>{fmt(augmented, 2)} points</b>
                        <small
                          className={
                            difference != null && difference > 0
                              ? "feature-improved"
                              : "feature-worse"
                          }
                        >
                          {difference == null
                            ? ""
                            : difference > 0
                              ? `${fmt(difference, 2)} points less error vs ${comparisonLabel}`
                              : difference < 0
                                ? `${fmt(Math.abs(difference), 2)} points more error vs ${comparisonLabel}`
                                : "No measured error change"}
                        </small>
                      </>
                    )}
                  </td>
                  <td>
                    <Badge
                      tone={experiment.promotion.promoted ? "teal" : "gold"}
                    >
                      {experiment.promotion.promoted
                        ? "Approved by validation"
                        : "Not added to live calls"}
                    </Badge>
                    <p>{experiment.promotion.reason}</p>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="forecast-caption">
        Error is the average absolute difference between predicted and actual
        Republican–Democratic margins, in percentage points; lower is better.
        Repeated dates from one race are not separate independent election
        outcomes.
      </p>
      <details className="forecast-feature-origins">
        <summary>Inspect which elections could actually be tested</summary>
        {experiments.map((experiment) => (
          <article key={experiment.id}>
            <h4>
              {experiment.label ||
                experiment.features
                  .map((id) => names.get(id) || human(id))
                  .join(" + ") ||
                human(experiment.id)}
            </h4>
            {experiment.origins.length ? (
              <ul>
                {experiment.origins.map((origin, index) => (
                  <li key={index}>
                    <b>Earlier training years: </b>
                    {origin.training_years.length
                      ? origin.training_years.join(", ")
                      : "None eligible"}
                    .{" "}
                    {origin.reason ||
                      "Inspect the complete test manifest for counts and fitted values."}
                  </li>
                ))}
              </ul>
            ) : (
              <p>No eligible earlier-election training set is available.</p>
            )}
            <p>
              {experiment.cases.length} held-out case records ·{" "}
              {experiment.exclusions.length} exclusion records.
            </p>
          </article>
        ))}
      </details>
      {!!data.warnings.length && <Notice>{data.warnings.join(" ")}</Notice>}
      <ResearchGuide
        what="Whether turnout, party composition, voting methods and geographic patterns improve predictions beyond the historical and geographic references, using only eligible historical evidence."
        how="Read evidence coverage first, then compare errors only within a row, where methods use the same races. A small improvement on a few races is not reliable nationwide validation. Precinct history alone cannot establish a precinct early-vote signal without dated participation records and compatible boundaries."
        source={`Version ${data.version} · evidence revision ${data.revision} · cutoff ${data.as_of}`}
      />
      <button
        className="button secondary"
        onClick={() =>
          downloadData(data, `ev-added-factor-tests-r${data.revision}.json`)
        }
      >
        <Download size={15} />
        Export factors, test cases & exclusions
      </button>
    </>
  );
}
export function ForecastFeatureTests({
  state,
  cycle,
  revision,
  asOf,
}: {
  state: string;
  cycle: number;
  revision: number;
  asOf?: string;
}) {
  const query = useQuery({
    queryKey: ["forecast-feature-tests", state, cycle, revision, asOf],
    staleTime: Infinity,
    gcTime: 60_000,
    queryFn: ({ signal }) =>
      earlyVoteFeatureTests({ state, cycle, revision, as_of: asOf }, signal),
  });
  return (
    <section id="forecast-feature-tests" className="forecast-anchor">
      <Panel
        title="Does adding turnout, party, method or precinct detail improve the calls?"
        subtitle="Actual historical tests, missing evidence, and the decision about whether a factor is ready for live use."
      >
        {query.isPending ? (
          <Loading label="Checking which added factors can be tested against actual Senate results…" />
        ) : query.isError ? (
          <Notice tone="warning">
            The added-factor test could not be loaded. The existing historical
            test results remain available above. {query.error.message}
          </Notice>
        ) : (
          <FeatureTestResults data={query.data} />
        )}
      </Panel>
    </section>
  );
}
