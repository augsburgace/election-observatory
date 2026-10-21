import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  BarChart3,
  CheckCircle2,
  ClipboardCheck,
  FlaskConical,
  GitBranch,
  LockKeyhole,
  ShieldCheck,
  TrendingUp,
} from "lucide-react";
import type { AppContext } from "../types";
import { api } from "../api";
import {
  Badge,
  Datum,
  Empty,
  Loading,
  Notice,
  Panel,
  Status,
} from "../components/ui";
import { DistributionChart } from "../components/Charts";
import { fmt, human, stateName } from "../utils";
export default function Forecasts(ctx: AppContext & { embedded?: boolean }) {
  const { query, workspace, embedded, setPage } = ctx;
  const forecast = useQuery({
    queryKey: ["forecast", query.state, workspace.revision],
    queryFn: () => api.forecasts({ ...query, revision: workspace.revision }),
  });
  if (forecast.isPending)
    return <Loading label="Checking model validation and availability…" />;
  const data = forecast.data;
  const validated = data?.status === "validated";
  const requirements = Array.isArray(data?.requirements)
    ? (data.requirements as (string | Record<string, unknown>)[])
    : [];
  const runs = Array.isArray(data?.runs)
    ? (data.runs as Record<string, unknown>[])
    : [];
  const validation = data?.validation as Record<string, unknown> | null;
  const distribution = Array.isArray(data?.distribution)
    ? (data.distribution as { x: number; density: number }[])
    : [];
  return (
    <>
      {!embedded && (
        <div className="page-intro">
          <div>
            <h2>Probabilities earn their place here.</h2>
            <p>
              Inspect the model, historical performance, and electoral
              assumptions before trusting a prediction.
            </p>
          </div>
          <Badge tone={validated ? "teal" : "gold"}>
            <ShieldCheck size={12} />
            {validated ? "Validated model" : "Evidence readiness"}
          </Badge>
        </div>
      )}
      {forecast.isError && (
        <Notice tone="warning">{forecast.error.message}</Notice>
      )}
      <div className="forecast-readiness">
        <div className="forecast-symbol">
          {validated ? <TrendingUp size={38} /> : <LockKeyhole size={36} />}
        </div>
        <div>
          <h3>
            {validated
              ? `${stateName(query.state)} forecast`
              : "A live forecast is not yet publishable"}
          </h3>
          <p>
            {String(
              data?.reason ||
                "Cutoff-safe historical inputs and held-out validation are required before calibrated live probabilities can be shown.",
            )}
          </p>
          <Status value={String(data?.status || "unavailable")} />
        </div>
      </div>
      {validated && (
        <div className="chart-grid">
          <Panel
            title="Projected margin distribution"
            subtitle="Model uncertainty, not the distribution of observed votes."
            exportLabel={`${query.state} model · r${workspace.revision}`}
          >
            {distribution.length ? (
              <DistributionChart rows={distribution} />
            ) : (
              <Empty title="No distribution is returned">
                Inspect the model-run records for the supported forecast output.
              </Empty>
            )}
          </Panel>
          <Panel title="Validation results">
            <div className="datum-grid">
              {Object.entries(validation || {})
                .filter(
                  ([, v]) => typeof v === "number" || typeof v === "string",
                )
                .map(([key, value]) => (
                  <Datum
                    key={key}
                    label={human(key)}
                    value={typeof value === "number" ? fmt(value, 3) : value}
                  />
                ))}
            </div>
          </Panel>
        </div>
      )}
      <div className="forecast-method-grid">
        <Panel
          title="Model architecture"
          subtitle="Transparent components, reproducible simulation, calibrated uncertainty."
        >
          <div className="method-flow">
            {[
              {
                icon: BarChart3,
                title: "Polling evidence",
                text: "Comparable producer-level surveys, exact fieldwork dates, and original methodology.",
              },
              {
                icon: GitBranch,
                title: "Fundamentals prior",
                text: "Historical state partisan lean and incumbency, estimated without future information.",
              },
              {
                icon: Activity,
                title: "Correlated uncertainty",
                text: "Shared national and race-specific errors, with Student-t tails and reproducible seeds.",
              },
              {
                icon: ClipboardCheck,
                title: "Held-out validation",
                text: "Rolling-origin comparisons against polling-only and fundamentals-only baselines.",
              },
            ].map((step, i) => (
              <div key={step.title}>
                <span className="method-number">0{i + 1}</span>
                <step.icon size={21} />
                <div>
                  <h3>{step.title}</h3>
                  <p>{step.text}</p>
                </div>
              </div>
            ))}
          </div>
          <Notice>
            {String(
              data?.methodology ||
                "Empirical-Bayes polling-plus-fundamentals baseline. Early-voting predictors remain excluded until they improve held-out performance.",
            )}
          </Notice>
        </Panel>
        <Panel
          title="Publication requirements"
          subtitle="Availability follows evidence, electoral rules, and validation."
        >
          <div className="requirements-list">
            {(requirements.length
              ? requirements
              : [
                  "Original historical polling with verified publication timestamps",
                  "Official certified outcomes for rolling-origin evaluation",
                  "Held-out calibration at 30, 14, 7, and 1 days before Election Day",
                  "Specialist counting-system support where applicable",
                  "Reproducible model version and complete input manifests",
                ]
            ).map((requirement, i) => {
              const title =
                typeof requirement === "string"
                  ? requirement
                  : String(
                      requirement.name ||
                        requirement.requirement ||
                        requirement.description,
                    );
              const complete =
                typeof requirement === "object" &&
                requirement.complete === true;
              return (
                <div key={i}>
                  <CheckCircle2
                    size={17}
                    className={complete ? "cyan-text" : "muted"}
                  />
                  <span>{title}</span>
                  {complete && <Badge tone="teal">Ready</Badge>}
                </div>
              );
            })}
          </div>
          <button
            className="button secondary wide"
            onClick={() => setPage("scenarios")}
          >
            <FlaskConical size={15} />
            Explore explicit scenarios
          </button>
        </Panel>
      </div>
      <div className="chart-grid">
        <Panel
          title="Historical validation scorecard"
          subtitle="2018, 2020, 2022, and 2024 where timestamp-safe evidence exists."
        >
          <div className="validation-scorecard">
            {[
              {
                name: "Margin error",
                description: "Accuracy in percentage points",
              },
              { name: "Brier score", description: "Probability accuracy" },
              { name: "Log loss", description: "Penalty for confident misses" },
              {
                name: "80% / 95% coverage",
                description: "Calibration of uncertainty intervals",
              },
            ].map((metric) => (
              <div key={metric.name}>
                <h3>{metric.name}</h3>
                <b>
                  {validation?.[
                    metric.name.toLowerCase().replaceAll(" ", "_")
                  ] != null
                    ? String(
                        validation[
                          metric.name.toLowerCase().replaceAll(" ", "_")
                        ],
                      )
                    : "Pending evidence"}
                </b>
                <p>{metric.description}</p>
              </div>
            ))}
          </div>
        </Panel>
        <Panel title="Counting rules & Senate control">
          <Notice tone="warning">
            Ranked-choice and runoff elections require specialist treatment. A
            first-choice estimate is not an eventual-winner probability.
          </Notice>
          <p className="body-copy">
            Senate-control probabilities require every contested seat,
            holdovers, explicit independent-caucus assumptions, and correlated
            race simulations. Incomplete coverage supports conditional seat
            scenarios and bounds.
          </p>
          <button className="text-button" onClick={() => setPage("sources")}>
            Inspect source readiness
            <TrendingUp size={13} />
          </button>
        </Panel>
      </div>
      <Panel
        title="Versioned model runs"
        subtitle="Every published run retains its evidence cutoff, parameters, version, and validation record."
      >
        {runs.length ? (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  {Object.keys(runs[0])
                    .filter((k) => typeof runs[0][k] !== "object")
                    .map((key) => (
                      <th key={key}>{human(key)}</th>
                    ))}
                </tr>
              </thead>
              <tbody>
                {runs.map((run, i) => (
                  <tr key={i}>
                    {Object.entries(run)
                      .filter(([, v]) => typeof v !== "object")
                      .map(([key, v]) => (
                        <td key={key}>{String(v)}</td>
                      ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty title="No validated live model runs">
            The platform does not substitute invented probabilities for missing
            historical validation.
          </Empty>
        )}
      </Panel>
      {Array.isArray(data?.warnings) &&
        data.warnings.map((warning, i) => (
          <Notice key={i} tone="warning">
            {String(warning)}
          </Notice>
        ))}
    </>
  );
}
