# Advanced research workflows

The atlas separates observed participation, historical election returns, population context, conditional research calls, and validated forecasts. The current election and evidence revision remain visible throughout an investigation.

## Compare two historical elections

Open **Atlas → Historical results**, choose an office and year, and scroll to **Compare elections, place by place**.

- **Side by side** uses the same projection, camera, color domain, and missing-data treatment for both original maps.
- **Historical swipe** moves an accessible divider over the two maps. Arrow keys operate its range control.
- **Difference** activates only for pairs approved by the comparison service. An identifier match alone does not establish a valid boundary or contest comparison.
- **Context × result** compares a place's historical partisan margin with its published ACS household-income estimate. The 3×3 legend contains numeric thresholds and selectable cells; the linked scatterplot identifies the same places. These are geographic associations, not characteristics of individual voters.

The default comparison is six years earlier for Senate results, four years earlier for presidential results, and two years earlier for other offices. Explicitly saved comparison years remain unchanged. Source availability and contest compatibility still determine whether a particular pair is meaningful.

The camera, divider, comparison mode, baseline year, and place selections survive in URL/saved-view state. Exact color thresholds can be opened without hovering. Selected places coordinate map outlines, table rows, paired-margin graphics, and transition plots.

The companion charts show matched-place margin changes, election-to-election transitions, the unweighted distribution of geographic margins, and concentration of candidate-vote volume. Their explanatory sections distinguish margins from vote counts and places from people.

## Open actual precinct evidence

The **Precinct research** section lists source-paired boundary/results bundles for the selected state. Choose the historical year explicitly. A different year is never silently substituted for an unavailable election.

Download a documented bundle to start a visible background job. Collection archives the original source, validates its geometry and identifiers, and publishes a new evidence revision. Pinned investigations do not initiate collection. Downloaded evidence remains available locally.

When more than one bundle exists for a year, the source selector retains its identity. Multi-contest offices expose a native-contest selector rather than adding unrelated district or judicial-seat returns together. Unknown or ambiguous quantities remain missing, including when their polygons are present.

Use the interactive map or switch to the keyboard/vector map. Candidate-vote volume uses proportional circle **area**. Partisan margins use the service's exact numeric bins, domain, and palette in both renderers. The evidence table supplies keyboard selection, search, and bounded pages.

Official administrative early-vote, absentee, provisional, and central-count rows are never distributed into resident precincts without source allocation. Their unallocated counts/share and original identifiers remain inspectable. A map can therefore show useful physical-precinct returns while covering only part of the reported election total.

For example, the archived North Carolina 2024 presidential bundle maps 2,654 uniquely matched physical precincts and leaves 254 administrative/unmatched source units outside those polygons. Its coverage ledger, rather than polygon density, establishes how much of the reported candidate-vote total is represented.

## Investigate current early voting

Open **Research → History** with a supported participation measure. Brushing the trajectory updates the shared reporting-date window; **Show the full reporting window** removes that restriction. Playback advances only through actual source observations.

The indexed trajectory begins at 100 on each cycle's first positive observation in the selected window. It is not a final-turnout denominator or forecast. The evidence matrix identifies actual reporting dates by cycle and method; a populated cell does not establish complete statewide reporting. Published composition retains unknown and unclassified categories. Missing composition never triggers demographic inference from population or prior results.

## Read a Senate research call

Open **Research → Forecasts**. The research-call desk displays conditional Republican-minus-Democratic point margins and wide **unvalidated sensitivity ranges**. Filters distinguish battleground races, all scheduled Senate contests, EV-informed calls, and historical-reference-only calls.

Each state shows:

1. The historical Senate reference and its input-election weights.
2. Current observed participation, its exact metric, date, method, and geographic coverage.
3. A geographic-context tilt and the explicitly assumed coefficient converting it into a provisional adjustment.
4. Matched same-stage EV comparison when supported, or a prominently labeled final-election geographic reference.
5. Geographic contributors, actual published composition, assumptions, source snapshots, and the reproducibility manifest.

Party registration, race, county partisanship, religion, and voting propensity are never treated as observed candidate votes. Religion and individual propensity are unavailable unless a future appropriate source directly supports them. Polls remain secondary context in this EV-led research model.

The validation section evaluates the **historical-only reference**. Its rolling-origin errors and historical interval coverage do not validate the EV coefficient or the displayed current sensitivity range. Winner probabilities remain subject to the separately expandable calibrated-model publication gate. Unsupported ranked-choice/independent configurations withhold D/R calls rather than invent an eventual-winner estimate.

Save a call to retain its pinned research view, exact output, assumptions, and input manifest. Export its JSON evidence packet for independent inspection. The backend also retains deterministic run manifests locally.

## Verification boundaries

Frontend regression tests cover signed margins, source-provided uneven map bins, missing precinct counts, proportional symbol area, geographic comparison eligibility, and missing/nonfinite research-call estimates. Type checking and production compilation verify the integrated contracts. Rendered desktop/mobile, theme, interaction, and console checks are recorded by the main implementation verification run; they are not replaced by these mathematical tests.
