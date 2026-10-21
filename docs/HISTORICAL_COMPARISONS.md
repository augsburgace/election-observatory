# Defensible historical comparisons

Historical candidate returns and current early-voting participation answer different questions. Candidate vote shares and margins cannot reveal the choices of current early voters. This workbench keeps historical results, participation snapshots, and assumptions separate.

## Matched result comparisons

The shared result service powers maps, charts, tables, briefs, and exports. `/api/v2/comparisons/results` adds two explicitly reported election views, per-place comparisons, matched coverage, signed margin changes, original sources, and reasons for withheld differences.

The comparison convention is **Republican minus Democratic share of all reported candidate/option votes**, measured in percentage points. Positive change means movement toward the Republican margin. The legacy `swing_pp` result field remains Democratic-minus-Republican for URL/API compatibility and is labeled accordingly. Never compare differently signed fields without conversion.

A difference requires:

1. A matching reported geographic unit and supported boundary-continuity review.
2. The same office and semantic contest, including district, special-election status, stage, and ballot configuration.
3. Comparable source-established counting rounds. An unspecified ranked-choice round is insufficient.
4. No suppressed/incomplete denominator.
5. Explicit Democratic and Republican options for a partisan swing calculation.

Different contests for an office are not summed. A stable county does not establish that its intersection with a redrawn legislative/congressional/local contest district stayed the same.

## County continuity standard

The current reviewed priority window is **2018–2024**. The app archives the actual [Census county-change inventory for the 2020s](https://www.census.gov/programs-surveys/geography/technical-documentation/county-changes.html) and [2010s](https://www.census.gov/programs-surveys/geography/technical-documentation/county-changes.2010.html), checks the retained hashes, and records a validation revision.

The standard is **the same canonical reported Census county identifier with no Census-listed substantial boundary or county-equivalent change during the interval**. It is a material reporting-unit comparison, not a claim of pixel-identical cartography. Census defines substantial changes using population/area thresholds; minor boundary adjustments and map generalization are not certified identical. The app does not redistribute any votes.

Withheld cases include:

- Connecticut's replacement of eight historic counties with nine planning regions until an appropriate source-specific crosswalk exists.
- Alaska native election reporting districts, which are not borough/census-area totals.
- Deleted or mismatched Bedford, Virginia; Shannon/Oglala Lakota, South Dakota; and changed Alaska source identifiers.
- Unmatched/noncanonical county IDs.
- Comparisons outside the reviewed window, until their boundary history is reviewed.
- Numbered contest districts without their own boundary-continuity review.

A pinned investigation cannot acquire a later county-review validation. Original values stay visible while a difference remains withheld. Old pins affected by a later structural parsing correction receive a present-day warning, preserving their original values and evidence chronology.

## Denominators and reconciliation

Coverage reports current-only, baseline-only, matched, and analytically eligible places. Matched sums use the same eligible set on both sides. Original full-coverage totals remain beside them so missing reporting areas cannot create a misleading statewide trend.

County producer sums can differ from dedicated statewide compilations because of reporting coverage, write-ins, source vintages, or revisions. These discrepancies remain visible. A difference map does not certify that two producers reconcile perfectly with the official statewide result.

Current early-voting history continues to use actual source observations and its established chronology/definition/calendar gates. A later reconstructed event-date file cannot establish what officials had reported at an earlier cutoff. Missing snapshots remain missing; no intermediate votes are manufactured.
