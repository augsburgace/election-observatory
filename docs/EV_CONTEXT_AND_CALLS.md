# Early-vote calls and optional outside evidence

Open **Research → Forecasts**. The first section explains the selected state’s provisional direction, measured participation, historical starting point, geographic contributors, turnout questions and limits. Its wording is generated locally from the pinned research data with deterministic templates and reproducible arithmetic. No external AI service is required.

## Choose what informs the explanation

All three switches default off in a new investigation:

- **Polling** adds eligible recent likely-voter Senate studies. It retains published response shares, populations, dates and question configurations. Original releases and RCP secondary summaries have separate badges. The latest source per listed producer is selected conservatively; incomplete producer/sample disclosures do not establish independence. Winner-expectation questions, hypothetical ballots and registered-voter questions remain separate. Different studies are not automatically averaged or given an invented pooled margin of error.
- **Betting markets** adds public, timestamped contract quotes, liquidity, bid/ask spreads and settlement rules. Prices are percentages of a contract payout. They are neither candidate vote shares nor calibrated model probabilities. Separate contracts are not forced to sum to 100%. The latest validated event snapshot removes closed, inactive, missing and placeholder options; an older quote cannot survive a documented closure.
- **Other context** adds the separately attributed RCP race assessment where a dated capture exists. It is an analyst classification, not a measurement of voters or a probability.

Enabling a source includes it in the explanation and explicitly identifies agreement or disagreement with the EV direction. **The EV-only point, range and validation record stay unchanged.** There is no validated combined predictor yet, so this interface does not quietly blend survey shares, contract prices and participation counts. A combined model would require its own earlier-trained historical tests.

**Use early votes only** resets all three switches. URL options `ui_include_polls`, `ui_include_markets` and `ui_include_context` preserve the choices alongside the state, cutoff and revision. Saving an investigation retains these settings. **Export this explanation** includes the selected evidence, source references, switches and manifest; the Senate report template continues to identify its EV-only model scope explicitly.

## Source coverage and refresh

The revision-375 batch checked 46 sources successfully and published 8,784 observation versions and 104 polling records. Records include revisions, reported/reconstructed representations and secondary copies; they are not independent elections or unique ballots.

- Eight additional original Ohio surveys cover seven 2020 releases and the November 7, 2016 endpoint. Their county and native method totals reconcile across all 88 counties.
- Thirteen authenticated UF 2024 CSV captures supply 212 state/report dates across 47 states. They are an attributed academic bridge. Statewide observations do not establish county or precinct history, and capture time limits historical availability.
- New original polling includes nine co/efficient state releases and the October Marist Michigan document. Original producer releases can update through the normal collector.
- Public browser captures preserve factual RCP tables for 13 Senate battleground states and their original producer links. Ordinary HTTP retrieval is unavailable on this network. These captures require an explicit browser refresh; a successful reparse of an old capture does not mean new polls were downloaded. Publication availability begins at capture, not at a guessed release day. Summary configurations remain separate from full-questionnaire averages.
- Fourteen Polymarket event feeds use the provider’s public read API. No account, credentials, trading or payment is involved. The existing two-hour collection schedule refreshes activated current sources and warms the research/feature caches.

See `config/external_context_sources.json`, `config/ev_gap_sources.json` and [the detailed historical gap audit](HISTORICAL_EV_GAPS.md). Ohio’s original current and 2024 voter exports remain inaccessible through ordinary public-file retrieval here. Their precinct/method/party intersections have not been manufactured.

## What has actually been tested

[Additional-factor tests](EV_FEATURE_VALIDATION.md) compare turnout pace, volume growth, directly reported method shares, published registration balance and defensible precinct patterns. They use identical-case comparisons, earlier-election training and explicit state/election cluster counts. Native definitions, calendar stages, boundaries and source chronology must be compatible.

At revision 375, the statewide family contains 98 checkpoint observations across 38 state/election clusters in 30 states. The geographic audit contains 40 observations across nine clusters. Added-feature history is still too sparse for valid learned holdout errors. Missing scores remain unavailable, not zero; no feature is promoted into live calls.

The frozen geographic benchmark’s headline MAE is 9.7295 points, versus 9.7815 for its historical reference. The separate sparse turnout benchmark has 22.9135% mean absolute percentage error. These records do not establish reliable EV forecasting skill or justify calibrated winner probabilities.

## Verification

- 341 backend tests and Ruff pass; 29 frontend tests, TypeScript and the production build pass.
- Actual HTTP reasoning requests with all switches off/on preserve the same EV call and hash; Ohio’s expanded view includes five listed pollsters, two contract quotes and a separately dated analyst assessment.
- Cached reasoning requests measured 33–44 ms and the feature-test response 124 ms on the development Mac. Initial nationwide calculation remains a background task.
- Revision-266 report replay still recalculates with agreeing results, sources, boundaries and layout. Existing investigation pins remain unchanged.
- A new local backup preserves revision-375 evidence. Source archives, raw official files and private research stay outside Git and are not sent to the public UI.
