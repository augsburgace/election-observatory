# EV-led Senate research workspace

The Forecasts page combines a concrete conditional party-margin call with the evidence needed to challenge it. All data remains local, revision-aware and reproducible. A county's historical vote, a registration category or residential demographics do not become current individual candidate choices.

## Reading path

Use the page anchors to move between the call, same-stage/turnout research, confidence, exact geographic inputs, reasoning, sensitivity, held-out tests and nationwide race board.

- **The call** retains a Republican-minus-Democratic point, research status, unvalidated sensitivity band, save/export actions and the sourced report link.
- **Same stage** compares actual reports from 2016–2024, with separate presidential/midterm/off-year selections. The anchor is the latest actual current report; report age stays visible. Election-relative and documented method-opening dates are distinct controls.
- **Confidence** shows source/model checks and a factor-role table. Source completeness or stability across assumptions is not forecast accuracy.
- **Geography** uses exact model county identifiers and values. Current EV uses proportional symbol area; historical R−D context and derived R−D contribution retain separate labels. Select a place to inspect counts, shares, dates and provenance. Missing data is not allocated to smaller places.
- **Reasoning** separates the historical Senate reference, assumed EV conversion and provisional margin. Party/demographic composition remains descriptive unless a documented model actually uses it.
- **Sensitivity** moves only between service-evaluated coefficients. Numeric inputs snap to an evaluated point. Zero and reversal experiments, omitted historical outcomes and contribution stress tests expose dependence on assumptions.
- **Historical tests** compare genuine held-out predictions with final Senate results and an identical-case historical reference. Each case exposes dates, chronology, inputs, training years and outcomes.
- **Nationwide** offers geographic/tile maps and the detailed contest board. Multiple Senate contests in a state are not averaged into one mapped margin.

## Evidence chronology and chart meaning

Recovered historical evidence is explicitly retrospective. The contemporary-only selection requires versions demonstrably available at that historical cutoff. Later-retained records do not become contemporary evidence merely because they contain old dates.

The trajectory chart draws actual observation points. Steps hold the previous report between observations; they do not create daily voting events. Its lower brush changes the display window while preserving the model evidence cutoff. A pace ratio appears only when the analytical service establishes exact stage, compatible definitions, geography and coverage. Opening day is zero calendar days after opening, including weekends; equivalent calendar days are not automatically equivalent voting opportunities.

Method bars show separate native measures with independent dates and definitions. They are not stacked or summed without a service-verified disjoint-category definition. Requests, issuance, returns, acceptance and cast ballots remain distinct.

## Turnout interpretation

Measured current participation, a dated current registration denominator, historical final participation, an empirical analogue and explicit turnout assumptions are different quantities.

The **conditional turnout analogue** divides current same-stage EV by retained earlier same-election-class early/final fractions. Current publication requires at least two compatible prior cycles. Its historical min/max span excludes model error and has no claimed probability coverage. The held-out turnout bench exposes actual percentage/count errors and sparse training; it predicts participation, not candidate margin.

The separate **low/reference/high assumptions** use the service's disclosed 0.9×/1.0×/1.1× prior comparable-election-class final participation. Remaining participation is shown only for a compatible complete statewide all-method ballot quantity and includes later early plus Election Day voting. Candidate support is unspecified. Historical final participation is never used as the current turnout-rate denominator.

## Historical testing

The headline Senate audit stratum is identified explicitly. Filters separate state, cycle, chronology, geographic reference, alignment and checkpoint. The scatterplot compares actual and predicted R−D margin; its diagonal is exact agreement. Cycle bars compare errors using identical held-out cases.

Repeated cutoffs and chronology copies are dependent observations. Filtered error summaries give each independent contest equal total weight; turnout errors give each state-election outcome equal weight. Fixed assumed-coefficient diagnostics remain distinct from trained EV holdouts. Null Brier scores, log loss and interval coverage remain unpublished rather than becoming zero.

## Saved state and verification

Non-sensitive map layers and research controls live in `ui_forecast_*` URL options. Saved calls retain revision, model version, assumptions and layout. Stage/test JSON exports retain exact service objects and manifests.

Frontend tests cover real compact-bootstrap and expanded-response rendering, withheld/no-contest states, actual audit cases, exact map input identity, no multi-contest pooling and contest-balanced repeated-cutoff metrics. Actual r242/r253 fixtures retain original numeric values while shortening repeated provenance payloads. The parent implementation separately verifies rendered controls, maps, chart brushing, mobile/desktop, both themes and console health; SSR/type checking alone do not establish those behaviors.

Opening-relative charts default to observations on or after Day 0. A persisted checkbox reveals original pre-opening records, which always remain in source/export data. The brush retains native pointer/keyboard behavior while an accessibility bridge publishes actual observation coordinates and readable start/end labels instead of pixel values or undefined range names.

## Plain-English briefing and optional context

The top briefing explains the directional call, what was actually reported, which historical reference was used, and why the current evidence changes or fails to change that reference. It is generated deterministically from the revision-pinned analytical response; no external AI service is required. If the reasoning service is unavailable, the page retains an explicitly identified summary of its displayed EV call and does not invent external evidence.

Three keyboard-operable switches add **polling**, **betting-market prices**, and **other separately sourced context** to the explanation. All default off. Their `ui_include_polls`, `ui_include_markets` and `ui_include_context` URL settings are preserved when saving a research layout. Each combination uses a separate query/cache key, and off values are explicitly sent to the service. These switches never alter the EV-call query or silently blend poll/market information into its margin.

When included, surveys retain fieldwork dates, population, available sample size and the original published response shares. Democratic and Republican options use blue and red; unknown or undecided responses remain separate. The page labels secondary summaries and links to original releases where available. Market quotes retain provider, observation time, outcome and published liquidity/volume; a normalized contract price is not presented as an observed vote share or a validated Observatory probability. Missing eligible evidence appears as unavailable even when its switch is on.

The added-factor section asks whether turnout pace, same-stage volume, party composition, method mix and precinct patterns actually improve held-out predictions. It displays source availability, paired errors when testable, earlier-training reasons and explicit promotion decisions. The default table uses the service's headline stratum; a persisted comparison-policy selector opens the other chronology, alignment and reference strata without pooling them. Complete cases and exclusions remain in the JSON export. A null error is displayed as **Not testable yet**, never as zero error or proof a feature is unhelpful.

The Forecasts workspace uses 14px minimum labels, 16px explanatory prose, larger panel headings and a 20px opening summary. The party-margin range has a symmetric, numeric Democratic/Republican axis, while measured early-vote magnitude retains its nonpartisan teal meaning. Geography, historical party context and assumed candidate-margin adjustments remain separately labelled. These font and color changes apply in both themes and do not change stored density or evidence selections.
