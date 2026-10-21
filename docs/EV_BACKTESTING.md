# Senate early-voting and turnout audit

The forecasting workspace now evaluates actual historical Senate outcomes against the conditional EV geography model. It also audits a separate total-participation extrapolation. These are distinct questions: knowing how many people participated does not identify their candidate choices.

## What is evaluated

The default party-margin model is the recency-weighted prior Senate reference plus `clip(0.35 × geographic tilt, −5, +5)` percentage points, Republican minus Democratic. The 0.35 conversion remains an explicit research assumption. Historical county margins are context, not observed early candidate votes.

The stage audit evaluates the frozen formula at 30, 14, 7 and 1 days before Election Day. When a verified method-opening calendar and matching observations exist, it also requests calendar days 1, 5, 10 and 15 after opening, with opening day counted as day 1. These calendar days are not a count of actual open sites or voting opportunities.

For each historical contest:

1. Build the reference using only Senate outcomes from earlier years. Keep regular/special seat families separate; respect documented final runoffs and unsupported ranked-choice cases. A later runoff final margin is excluded from general-election-stage tests unless that round has its own verified calendar and EV observations; November ballots are not substituted for January runoff participation.
2. Obtain county election context only from years before the held-out election. Final returns for the held-out race are validation labels, never geographic feature weights.
3. Select an actual dated, same-source, same-method statewide/county report available at or before the cutoff. The last report can be at most three days old; its age is explicit. There is no interpolation.
4. Require exact reconciliation of same-date county totals with the same-source statewide total, canonical county joins, sufficient matched coverage and a positive reported quantity.
5. Compare the historical-only reference with the frozen EV adjustment against actual final Senate returns. A compatible prior EV distribution supports an additional same-stage feature; otherwise the feature is explicitly final-result geography.
6. Keep a complete exclusion ledger, including absent sources, incomplete county coverage, missing calendars and unsupported definitions.

The headline paired metrics use retrospective report snapshots, days-to-election alignment and final-result geography. The API also supplies separate groups by chronology, alignment, feature definition and checkpoint. It never pools those duplicated representations as independent elections.

## Chronology strata

- **Strict contemporary feature chronology:** original report observations have documented publication or first-observation evidence no later than the historical cutoff. Later versions cannot erase eligible earlier versions. Later manual corrections do not alter these feature values.
- **Retrospective dated-report study:** a document has an actual printed historical report date, but its current bytes were recovered or modified later. This can support a retrospective algorithm audit; it does not establish what a forecaster could have downloaded that day.
- **Final-cohort event reconstruction:** later voter-history or final-accepted-ballot records are descriptive historical context. They are excluded from report-snapshot forecasting tests when later acceptance/status determines membership, because that selection was not known at the historical return date.

Even the first stratum is not a fully restored historical production system. Final-return archives were collected retrospectively, and present-day quality decisions clean the evaluation universe. Those timestamp and vintage limitations accompany every audit.

## Independent evidence and fitting

Four checkpoints from one state/election are four dependent snapshots of one outcome. Each state/election receives equal total weight in aggregate errors and fitting; same-day regular and special contests share that cluster weight. The legacy `independent_contests` field counts distinct contests, while `independent_state_cycles` reports these shared clusters. The response reports snapshots, independent contests and independent election cycles separately.

A learned EV conversion uses state-election-balanced Huber loss with fixed delta 10 percentage points, ridge penalty 8, one coefficient bounded −2 to +2 and no intercept. Its training set contains only earlier cycles with actual outcome years before the target origin. Different chronology and feature-definition strata are fitted separately. Hyperparameters are not tuned on the held-out outcome.

A fit requires at least three independent earlier cycles and eight earlier state/election clusters. Production promotion additionally requires convincing held-out improvement across states and cycles. Sparse evidence does not trigger a fitted replacement. A retrospective evaluation of a formula chosen after the historical elections is not a preregistered prospective forecast.

MAE, RMSE, bias and direction accuracy are supplied where there are actual cases. Brier score and log loss remain null because no calibrated probabilities are issued. EV 80%/95% interval coverage remains null until adequate earlier independent calibration errors exist. Historical-reference interval diagnostics remain separate from the current unvalidated sensitivity range.

## Turnout, separately

Original EAC EAVS Section F and NCSBE turnout summaries provide final participation endpoints. They are not calculated by adding candidate votes. EAVS's native F1a measure can itself be based on poll books, counted ballots, vote history or highest-office vote totals; source methods and vintage caveats remain visible. Missing survey codes are never converted to zero, and incomplete statewide category aggregates are withheld.

The conditional turnout analogue divides current same-stage EV by the median earlier same-election-type EV/final-participation fraction. Presidential, midterm and off-year cycles remain separate. Methods, metric definitions and report age must match. Only earlier final turnout enters this predictor; the target final turnout is used solely as the eventual validation label. Final-election registration and eligibility figures do not enter pre-election predictors.

Current participation extrapolations require two earlier compatible cycles. A one-cycle analogue is allowed only as an explicitly sparse historical benchmark. Its range is the span of historical analogues, not a confidence interval. A projected final total and its lower sensitivity endpoint can never fall below already observed participation.

## Original turnout sources

- [EAC historical resources](https://www.eac.gov/research-and-data/eavs-retrospective): Section F time-series workbook, normalized for 2016–2022.
- [EAC studies and reports](https://www.eac.gov/research-and-data/studies-and-reports): original 2024 version 2.0 CSV and codebook.
- [EAC 2024 survey instrument](https://www.eac.gov/sites/default/files/2024-04/2024_EAVS_FINAL_508c.pdf): F1/F2 definitions and measurement sources.
- [NCSBE turnout summary](https://www.ncsbe.gov/results-data/voter-turnout): general-election main summary, 1976–2024. Its current 2024 total differs from a separate official detail page; the main-summary source vintage remains explicit.

`config/turnout_historical_sources.json` contains two national downloads and one North Carolina source. National collection emits complete state endpoints with an explicit state/year coverage manifest, rather than downloading the same national workbook fifty times. Original documents and hashes are archived by the normal collector.

## Running and reproducing

From the repository root:

```sh
.venv/bin/python scripts/backtest_ev.py --revision 266 --as-of 2026-10-21 --state NC --output .local/atlas-depth/ev-backtesting-r266-final.json
.venv/bin/pytest -q backend/tests/test_ev_forecast.py backend/tests/test_ev_backtesting.py backend/tests/test_turnout_historical.py
```

The script reads retained local evidence and writes aggregate JSON; it performs no collection. Each response contains the revision, cutoff, actual case/exclusion ledgers, original source references, input/code hashes and deterministic model manifests. Immutable run artifacts are also retained under the local data directory's `model-runs/ev-backtesting` and `model-runs/ev-research` folders.

The API remains backward compatible and adds `backtesting`, per-call `confidence`/`sensitivity`, and selected evidence's `same_stage` and `turnout_projection`. Evidence strength is separate from forecasting confidence. A concrete conditional margin is not a statement that its direction is certain.

## Verified October 21, 2026 run

At retained revision **266**, the audit contains **39 stage/chronology/feature observations for eight distinct Senate contests** in 2016, 2018, 2020 and 2022. The headline retrospective days-to-election group has 25 observations for those eight state/election clusters. The actual cases include Iowa, Michigan, North Carolina and Ohio; missing historical EV data remains an explicit exclusion elsewhere. Georgia's later runoffs are excluded from November-stage margin evaluation.

The frozen EV adjustment's state/election-balanced MAE is **8.434 percentage points**, compared with **8.486** for the historical reference. RMSE is **10.933**, compared with **11.069**. This slight change does not establish a meaningful, transferable accuracy improvement. A correct direction in this small, selectively available sample does not establish reliable future predictions. No earlier-trained EV holdout passes the training-history requirements, and no calibrated winner probabilities are published.

The separate sparse turnout analogue has eight headline observations for three North Carolina/Ohio state-election cycles, with approximately **17.9% mean absolute percentage error**. That poor, limited record is displayed as a warning, not hidden by a tight historical-analogue span. That span excludes model error and is not a confidence interval.

The current North Carolina conditional margin at this revision is **R+2.2**. Its EV distribution genuinely compares the current reported stage with the compatible October 26, 2022 county report, rather than using a final-vote distribution as an unlabeled substitute. The historical document's retrospective chronology remains explicit. Ohio is **R+2.8** and retains the comparison/definition limitations displayed in its evidence inspector. Both are experimental research calls.

The complete response is retained locally as `.local/atlas-depth/ev-backtesting-r266-final.json`; `.local/atlas-depth/ev-cache-performance-r266.json` records the performance verification. A fresh process loaded the validated 9.29 MB frozen aggregate run in **0.051 seconds**, with refitting deliberately disabled to prove reuse. A subsequent state change took **0.0009 seconds**. Fresh-process peak resident memory was approximately **129 MB**. The initial computation took approximately **38 seconds** and peaked at **2.46 GB**, so it remains a background/prewarming concern for a genuinely new evidence revision.

Frozen-run cache keys include the evidence revision, cutoff, cycle, model version and a fingerprint of backend Python, source/calendar configuration, canonical county geometry, Python and NumPy. The envelope's payload hash, schema and request key are checked before reuse; reads are bounded, invalid/tampered files are recomputed, and new writes replace atomically. Every state's selected diagnostics are preserved in the same run, so restarting or selecting a different state does not reload the large historical inputs. Source/input caches are released after the cold calculation. Any analysis/configuration change correctly requires a new cold run.

The current-call freshness policy permits up to seven days of source age; the default historical audit conservatively requires a report within three days of its requested checkpoint. Thus the Ohio October 28, 2016 snapshot remains useful sourced context but does not enter the default seven-days-before-election audit (it is four days old at that checkpoint). This coverage restriction is visible in the exclusion ledger and is not evidence that the original report is absent. Exact-stage pace comparisons retain stricter date/definition requirements.


## Expanded evidence at revision 375

The October 21 follow-up adds eight original Ohio surveys, authenticated UF 2024 statewide archive captures, and optional external-context sources. The retained geographic audit now has 40 checkpoint observations across nine state/election clusters; its headline retrospective election-relative stratum has 26 observations. Its frozen geographic EV assumption has MAE **9.7295 pp**, versus **9.7815 pp** for the identical-case historical reference. The added Ohio 2016 endpoint increases both absolute errors. The difference does not establish a reliable improvement.

The separate turnout benchmark has 11 observations across six state/election clusters in three election years, with **22.9135% MAPE**. This replaces neither the retained revision-266 record nor its explicit scope; the larger current record must not be presented using the earlier, smaller errors.

Additional-factor testing includes a separate statewide family with 98 checkpoint observations across 38 state/election clusters in 30 states, without inventing missing county geography. Valid prior-only training remains too sparse for learned holdout scores. No turnout, method, registration or precinct factor has been promoted into live calls. See [the feature-testing methodology and evidence](EV_FEATURE_VALIDATION.md).
