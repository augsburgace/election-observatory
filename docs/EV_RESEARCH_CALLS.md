# EV-led Senate research calls

## What is published

**Research → Forecasts** contains experimental, deterministic party-margin calls for the 35 scheduled 2026 Senate contests. They are separate from the existing validated-probability gate. A label such as **R+1.7** means a conditional Republican-minus-Democratic margin projection; it does not mean measured early votes, a named candidate prediction, a certified winner or a calibrated win probability.

Every call is labeled:

- **EV informed:** current geographic participation passes the evidence checks and contributes an explicitly assumed adjustment.
- **Historical reference only:** a point is available from prior Senate returns, but no acceptable dated geographic EV adjustment is supported. This is never labeled an EV call.
- **Unavailable:** a defensible party reference or the actual electoral system cannot support the requested call. Alaska and Maine eventual-winner calls are withheld because ranked-choice rounds, independent options and current official candidate configurations are not established.

All official 2026 candidate identities remain unverified in this local dataset. Historical incumbents/candidates are not assumed to be the current nominees.

## Formula and evidence

The projected margin is:

`historical Senate reference + clip(0.35 × geographic EV tilt, -5, +5)`

The coefficient **0.35** and the ±5 percentage-point cap are explicit, **unvalidated research assumptions**. A retrospective historical audit evaluates the frozen formula; it does not validate the coefficient or establish a transferable improvement in forecast accuracy. No learned replacement passes the training-history requirements.

The reference uses up to three most recent Senate-election years in the preceding 12 years, with a six-year recency half-life. Regular and special contests stay separate. Regular context can be an explicitly labeled fallback for a special election without adequate special history. These references still pool different Senate seats, candidates and classes, and are not nominee/incumbency adjusted.

A documented final runoff replaces the preceding general round in its seat family. The Georgia regular and special January 2021 runoffs are retained as distinct final outcomes of their 2020 election families. The 2022 Georgia general runoff replaces the earlier 2022 general round. A jungle ballot with several candidates from a major party, independent-led outcomes, missing major-party options, suppressed returns and unspecified ranked-choice rounds do not become synthetic two-party final outcomes.

The geographic signal compares current county shares with either:

1. Compatible, actually available same-stage early-vote county shares, or
2. Explicitly labeled historical **final candidate-vote shares**.

The second is not an equivalent-day early-voting comparison. County-share differences are weighted by original county R-minus-D margins. Senate county returns are preferred; presidential county context is labeled when Senate county evidence is unavailable. County aggregates do not identify individual early-voter choices, and no votes are allocated into precincts or across changed boundaries.

Only compatible reported cast, accepted or returned ballot measures are eligible. Requests, issued ballots and raw record counts are excluded from the signal. When only a particular method has geographic evidence, that method is labeled; it is not presented as the complete early electorate.

## Evidence gates

A geographic adjustment requires:

- At least two matched counties and 1,000 reported ballots under the explicit minimum-evidence policy.
- At least 90% of known county activity matched to the historical context and 80% of the positive compatible statewide total.
- County/state totals that reconcile. County totals exceeding the statewide total beyond a one-ballot/numerical tolerance withhold the adjustment.
- Synchronous county source reporting dates and evidence no more than seven days old.
- A verified underlying report date. A producer upload date with an unverified authority report date, including the documented Kentucky/Maryland cases, supports a clearly labeled historical-only reference.
- Directly compatible voting definitions and real source identifiers.

Missing is not zero. The interface exposes match coverage, current/source dates, native definitions, input counts, county contributions and source hashes.

Party registration and demographic tables show published marginal composition only. They are not candidate votes and do not enter this initial projection. No unreported joint demographic distributions, religion or propensity scores are inferred. Polling is a secondary research link and does not enter this model.

## Uncertainty and validation

The displayed band is an **unvalidated sensitivity range**. It is at least ±15 percentage points, expands to the historical-reference 95th-percentile absolute error when larger, is wider with sparse historical input, and expands for final-return rather than same-stage EV reference. It has no claimed probability coverage.

The historical-reference-only rolling-origin diagnostic uses 2018, 2020, 2022 and 2024 outcomes; the separate EV stage audit below has its own observed origins and exclusions. Every fit uses earlier-year Senate results; interval calibration uses residuals from earlier origins. A 2021 final runoff can be the held-out outcome for its 2020 election family but cannot enter a prediction made before that election. Later final returns are excluded from earlier requested cutoffs, conservatively withholding same-calendar-year final results until the next year.

At revision **175**, model **ev-geography-research-1.1**, the historical-reference-only diagnostic has **123 held-out contests**, **7.69 percentage-point MAE** and **10.21 percentage-point RMSE**. Rolling historical-only 80%/95% interval coverage is also exposed. These are retrospective results from the collected final-return archive; original publication timestamps and later revisions are incompletely documented. They do not establish an as-reported historical backtest.

At that initial v1.1 release there were no EV-enhanced audit cases. **Version 1.2, retained revision 266**, contains **39 eligible checkpoint observations across eight distinct historical Senate contests**, with origins in 2016, 2018, 2020 and 2022. The headline retrospective days-to-election group contains **25 observations**. The frozen EV assumption's state/election-balanced MAE is **8.434477243 percentage points**, versus **8.486268853** for the historical baseline. This tiny difference in a small, selectively available sample establishes no reliable improvement. Contemporary and later-retained dated reports remain separate strata; repeated stages are dependent. **Zero earlier-trained EV holdouts** meet the minimum prior-history requirements. Brier score, log loss, calibrated EV interval coverage and winner probabilities remain unpublished. See [the complete empirical audit](EV_BACKTESTING.md). Current calls can use compatible prior same-election-class EV geography already known at the current cutoff, with the prior report's chronology disclosed. The audit permits a report age of at most three days, while current calls permit up to seven; the Ohio October 28, 2016 report is four days old at the seven-days-before-election checkpoint, so it remains sourced context rather than an added standard audit case.

Illustrative actual revision-175 output, rather than manually authored values:

| State | Research point | Basis |
|---|---:|---|
| North Carolina | R+1.7 | EV informed, 100 matched counties; Senate county context |
| Ohio | R+2.8 | EV informed, 88 matched counties; Senate county context |
| Texas | R+7.4 | Historical reference only; compatible current county EV is unavailable |
| Georgia | R+1.2 | Historical reference only; documented final Senate runoffs retained |
| Kentucky | R+20.2 | Historical reference only; underlying report date is unverified |
| Alaska / Maine | Withheld | Eventual-winner electoral-system/option evidence insufficient |

These points change with validated evidence revisions and should always be read with their wide ranges, assumptions and exact pinned inputs.

## Reproducibility and reporting

Runs are cached independently of the selected state, so opening another race reuses the same national computation. The verified revision-266 cold run took approximately 38 seconds; a fresh process loaded its validated frozen aggregate artifact in 0.051 seconds, and a subsequent state change took 0.0009 seconds. These are measured service timings on the development Mac, not full-page load guarantees. Background source publication creates a new revision; pinned runs remain unchanged. See [the performance record](EV_BACKTESTING.md).

Aggregate run manifests are stored locally under `model-runs/ev-research/` inside the application data directory. Each call records its model/build fingerprints, query, evidence revision, source URLs and SHA-256 hashes, deterministic formula, coefficient policy and explicit absence of a simulation seed/probabilities.

The **Senate EV-led forecast dossier** report template renders the exact selected model run, point, range, county inputs, assumptions and validation limits. Its research ZIP preserves the model manifest, source hashes and report order. `observatory reproduce` verifies the package and matching evidence before regenerating it. Personal notes remain excluded unless explicitly selected.

The API is `GET /api/v2/forecasts/early-vote?state=NC&revision=266&as_of=2026-10-21`. A source failure does not delete the last validated evidence; stale or incomparable EV inputs withhold only the adjustment.
