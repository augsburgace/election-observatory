# Do extra early-vote factors improve predictions?

This laboratory measures a narrower question than “is the data interesting?” It tests whether an extra historical input improves Senate **party-margin** predictions on later elections, compared with a model using the same geographic input. It does not automatically change the live research call.

There are two test families. **With geography** asks whether an added factor beats the county-based model. **Statewide** asks whether a factor beats the historical Senate reference where county evidence is absent or unnecessary. Statewide measurements do not acquire invented county values.

The experiments are deliberately strict: an unavailable input remains unavailable. A current voter’s party registration is not a recorded candidate vote, an absentee receipt channel is not necessarily a voting method, and a precinct result map is not a dated precinct early-voting report.

## What is tested

| Factor | Calculation | Evidence needed |
|---|---|---|
| Where early voters live | Existing county-mix historical party-margin tilt | Reconciled county EV and earlier electoral context |
| Growth in early voting | Log of this cycle’s EV total divided by the previous comparable cycle’s total at the same stage | Same election type, metric, method definition, date alignment, and report age |
| Early participation relative to earlier turnout | Difference between current and prior stage EV, each divided by a final administrative turnout total **from an earlier cycle** | Two earlier same-type participation endpoints; returned receipts do not become counted voters |
| Change in in-person share | Change in directly reported in-person EV divided by all-method EV | Same source, status metric, date, and a directly reported, compatible method classification |
| Change in registration balance | Change in Republican registration share minus Democratic registration share | A complete published registration partition at both stages; all other and unknown categories remain in the denominator |
| Change in precinct participation | Total variation distance between complete precinct-share distributions | Real dated precinct EV, reviewed stable IDs, matching boundary vintage, and statewide reconciliation |

Presidential, midterm, and off-year histories stay separate when constructing same-stage comparisons. The current audit’s admitted origins are the general-election years 2016, 2018, 2020, 2022, and 2024 where evidence exists; no off-year EV holdouts have yet been admitted. A one-day-old report is compared with another one-day-old report at the equivalent coordinate. The stage audit allows at most three days of report age. Missing observations are not interpolated. Native metric definitions must match when an explicit normalized metric definition is absent; a generic “ballots cast” label does not override a changed source meaning. A source that explicitly declines to establish a disjoint method partition cannot supply a direct method-share feature.

The turnout feature never uses the held-out election’s final turnout or final registration. Explicitly identified highest-office-vote proxies are excluded from this feature. Other administrative endpoint measurement caveats travel with the feature’s denominator records.

Precinct comparison currently accepts only an explicitly reviewed identical-boundary partition. A changed-boundary crosswalk must first become a verified common-boundary dataset; native precinct names alone are insufficient.

## How the test avoids misleading improvements

For every additional feature set:

1. Select complete historical cases for that set. Missing measurements are not filled with zero.
2. Hold out an entire later election year. Training labels and feature scales use only earlier election years, including the actual outcome year of a later runoff.
3. In the geographic family, fit the geographic comparator and augmented model on **exactly the same training cases**. In the statewide family, compare the earlier-trained extra-factor model to the same case’s prior-only historical reference; the geographic comparator is explicitly unavailable.
4. Compare both models and the historical reference on **exactly the same held-out cases**.
5. Give each state/election year one total unit of weight. Extra dates, regular/special contests, alternate alignments, and chronology copies do not become extra independent elections.
6. Keep contemporary-publication, retrospective-report, days-to-election, opening-day, and reference-definition strata separate.

The fitted models use a fixed Huber loss (10-point threshold), ridge penalty 8, training-only weighted RMS scaling, no explicit intercept, standardized coefficients bounded at ±10, and a ±5-point cap on the predicted adjustment. Scaling is not fitted on the held-out year. Hyperparameters are fixed in code rather than selected against these outcomes.

A learned model needs at least **three earlier election years** and at least **eight earlier state-election clusters**. Larger feature sets require at least four earlier clusters per input, so the four-input combination needs sixteen. A fit that does not converge is withheld.

A candidate improvement needs at least four held-out election years, thirty held-out state-election clusters, at least a 0.25-point paired MAE reduction, no RMSE deterioration, and improvement in at least three held-out years. Passing these error checks triggers independent review; it does not automatically publish a production model, uncertainty interval, or winner probability.

The existing frozen 0.35 geographic conversion is shown separately. It was not historically preregistered or learned from prior-only holdouts. Its retrospective error is not evidence that any newly added factor generalizes.

## Reproducible run

From the project directory, reuse a pinned stage-audit or complete forecast response:

```sh
.venv/bin/python scripts/test_ev_features.py \
  --backtest-input .local/ev-validation/followup-forecasts-r375.json \
  --output .local/ev-feature-validation/r375.json
```

Without `--backtest-input`, the script rebuilds the source-backed historical case audit from the local database. This can take more time and memory. It does not fetch new documents or publish new observations. A supplied audit must match the requested dataset revision and research cutoff.

The result is cached as immutable aggregate JSON under `model-runs/ev-features/`. Cache identity covers revision, cutoff, input audit, model version, every backend and configuration file, local geography, Python/NumPy, and SciPy. Bounded reads, envelope and payload hashes, finite JSON checks, atomic writes, and a process lock prevent stale, partial, or overlapping builds. A two-result memory cache returns independent copies. Background warming avoids rebuilding the nationwide feature inventory on a reasoning toggle.

The JSON contains:

- Feature definitions, units, availability, missing reasons, and original source references.
- Every eligible historical case, its actual result and input/outcome references.
- Per-origin training case IDs, years, independent counts, coefficients, and scales.
- Paired MAE, RMSE, bias, direction accuracy, and separate prediction records where training is adequate.
- Every missing-feature and insufficient-training exclusion, plus the upstream case-admission exclusions.
- Separate chronology/alignment/reference strata and a default retrospective days-to-election headline.
- Dataset revision, cutoff, code digest, input-audit digest, feature digest, fixed hyperparameters, and source manifests.

No Brier score, log loss, or interval coverage is published because these experiments do not produce calibrated probabilities or intervals. Repeated checkpoint metrics are cluster balanced, but uncertainty about generalization still depends on independent elections and national environments.

## Recorded coverage: revision 375, October 21, 2026

This is a real local run, not invented demonstration data. All 50 states are reviewed against the Senate result history. The separate statewide family admits **98 checkpoint records across 38 state-election clusters in 30 states**. A checkpoint is a dated, scoped research observation; it is not an independent election.

The geographic stage audit admits **40 records across nine state-election clusters**. Its default retrospective days-to-election stratum has 26 records across those nine clusters. The extra original Ohio 2016 endpoint adds a genuinely new state-election cluster rather than an invented daily path.

The default feature inventory uses the deduplicated statewide family. Repeated chronology/alignment records still share their state-election weighting:

| Feature | Available checkpoint records | State-election clusters | Election years |
|---|---:|---:|---|
| County geographic tilt | 33 | 9 | 2016, 2018, 2020, 2022 |
| Same-stage EV volume growth | 13 | 4 | 2020, 2022 |
| Turnout pace with earlier denominators | 6 | 1 | 2022 |
| Direct in-person share change | 4 | 2 | 2022 |
| Published registration balance change | 4 | 2 | 2020, 2022 |
| Verified precinct distribution shift | 0 | 0 | None |

**No added-feature experiment yet has adequate earlier training for a genuine holdout score.** Its MAE and RMSE therefore remain unavailable, not zero. The evidence cannot establish that these extra factors improve accuracy, and no feature has been promoted into live calls.

New 2024 statewide reports expand descriptive coverage, but they do not by themselves establish compatible earlier reports, method partitions, or native definitions. Uncertain source crosswalks are withheld rather than matched solely on a generic metric name.

For context, the separate frozen 0.35 geographic conversion has a 9.7295-point mean absolute margin error on the default nine-cluster stratum, compared with 9.7815 for the historical reference. That roughly 0.052-point difference does not establish a transferable improvement. The separate turnout analogue benchmark has eleven records across six state-election clusters and a 22.9135% mean absolute percentage error. These broader-coverage results replace the earlier eight-cluster headline; expanding the sample can worsen absolute error.

The most valuable next collection is multi-cycle, date-specific official EV with state and county totals, directly reported voting modes, and published registration partitions. Dated precinct EV with verified boundaries would unlock the precinct experiment. Historical precinct results alone do not close that gap.

The experiment is exploratory and the historical source inventory was assembled later. Contemporary feature timestamps do not reconstruct every historical production decision or contemporaneous final-result vintage. Complete availability and exclusion records make those limits inspectable.

## Verified cache behavior

At revision 375, the full uncached forecast/audit build took 44.43 seconds and the first feature build took 3.80 seconds. The combined process peaked at approximately 2.52 GB; scheduled warming keeps that work outside ordinary cached navigation.

A fresh process then read the frozen forecast in 63.5 milliseconds and the feature result in 38.5 milliseconds, with approximately 206 MB peak resident memory. The verification disabled the expensive rebuild functions, proving that those results came from the validated disk caches. Repeated in-process feature access took 14.5 milliseconds and returned an independent copy.

These are measured service-computation timings, not browser rendering or network timings. The local proofs are `.local/ev-feature-validation/performance-r375.json` and `.local/ev-feature-validation/disk-cache-r375.json`. Their dependency digest matches the frozen full call response and feature package.
