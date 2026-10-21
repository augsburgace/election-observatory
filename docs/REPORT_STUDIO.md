# Report studio

The **Research → Reports** workspace assembles an exact, sourced document rather than an illustration of the current screen. The HTML preview, downloadable HTML, vector PDF, individual SVG figures and research ZIP share one document model and the same figure coordinates, quantitative legends, tables and definitions.

## A complete workflow

1. Open a state or place investigation and choose its metric, chronology, cutoff and selected areas.
2. Open **Reports**. The investigation's evidence revision is copied into the draft. New data does not replace it underneath your work.
3. Choose a state dossier, daily early-voting brief, historical comparison, Census-context packet, polling review or custom template.
4. Check the sections to include. Use their up/down controls to change reading order; add captions to explain your findings. Captions are explicitly labeled as researcher writing.
5. Open **Evidence and comparison settings** to choose the historical election, baseline, office, reporting grain and map measure. Historical contest returns and population context remain separate from current participation.
6. Select **Update preview**. The preview is the HTML produced by the same service that exports the report. It includes complete tables, source hashes and limitations.
7. **Save report configuration** stores the title, order, captions, exact queries, revision and personal notes locally. Reopening a saved report restores its original evidence selection. Old participation-only report layouts remain readable through a compatibility adapter.
8. Export **PDF**, **HTML**, **Tables CSV** or **Research ZIP**. A ZIP includes the printable PDF, HTML, editable layout JSON, original aggregate observations/results, complete tables, each vector figure, source hashes and boundary-file hashes.

Personal notes stay local and are excluded from preview/exports unless **Explicitly include my private notes** is selected. The saved local notebook object can retain a private note even when the exported research packet omits it. Raw personal voter records are never packaged.

## Available sections

- Research findings with units, dates and scope.
- Step trajectories built from actual reports and aligned historical observations.
- Newly reported changes, retaining negative corrections and coverage limitations.
- County/state participation maps with circle **area** proportional to count.
- Ranked geographic contributors and separately labeled place trajectories.
- Directly published composition groups, preserving unknown values and avoiding unsupported intersections.
- Historical margin or volume maps, candidate/ballot-option distributions, statewide presidential history and compatibility-qualified comparisons.
- ACS population, median age and household-income maps and rankings, with estimate periods and published 90% margins of error.
- Original polling questions, fieldwork, populations, samples and complete response distributions.
- Original source URLs, archive SHA-256 values, definitions and evidence limitations.

The historical core and Census context support all 50 states. Early-voting sections depend on that state's actual source coverage. An unavailable section says so; an absent count is never rendered as zero.

The Senate EV chapter includes the exact conditional call, county inputs, paired EV/reference audit metrics, eligible-case ledger and the separate prior-only turnout analogue. Source appendices include validation and turnout references as well as the selected state's observations. If a later model version changes the calculation, `reproduce` can render the checksum-verified frozen original result after verifying sources and boundaries. Its output explicitly says `verified_frozen_model_result` and `analytical_recomputed: false`; it never silently substitutes a newer forecast. Same-version analytical disagreements still fail verification.

County/state maps use locally served Census polygons. Precinct maps use the separately validated, source-native boundary bundle only when its exact identifiers match the requested result page and pinned revision. Unmapped administrative records stay in the table. VEST allocations, source joins, native geography, unspecified ranked-choice rounds and boundary-crosswalk limitations remain visible. A report never substitutes county polygons for precincts.

Precinct result packets are bounded to a page of at most 200 complete reporting areas. Their counts describe that page, not statewide turnout. The evidence appendix identifies the source boundary and its vintage. Unsupported historical differences remain withheld while the two elections' original values stay available.

## Regenerating a research ZIP

Use the matching local SQLite/archive backup and the preserved boundary cache:

```sh
.venv/bin/observatory reproduce /absolute/path/research.zip --format html --output /absolute/path/regenerated.html
.venv/bin/observatory reproduce /absolute/path/research.zip --format pdf --output /absolute/path/regenerated.pdf
```

The command verifies the packaged evidence and report-layout checksums, checks the original archived source bytes and map boundary files, reruns the pinned queries, compares the resulting complete document fingerprint and then regenerates the requested format. Existing output files are not overwritten. A mismatch is an error, not permission to silently regenerate using later or different evidence.

## Interfaces

- `POST /api/v2/reports/preview` accepts a `ReportRequest` and returns the normalized pinned request, section/figure inventory, source references, HTML and document fingerprint.
- `POST /api/v2/reports/exports?format=pdf|html|zip|json|csv` accepts the same request and exports the same document.
- Saved layouts use the existing local research-object APIs with `kind: report` and `view.report_request`.

The export schema is `observatory-composed-report-v1`. The document records participation query, historical-result query, context measure, evidence revision, enabled section order, captions, note policy, source snapshots and boundary descriptors independently.

## Senate EV-led forecast dossier

The **Senate EV-led forecast dossier** template adds the exact experimental Senate research call, wide unvalidated sensitivity band, actual EV measure, historical reference, county contributions, assumptions and historical-only validation diagnostics. It executes the model only when its section is enabled. The source appendix and ZIP include its model manifest and original snapshot hashes; the model cutoff is pinned even when the originating draft used “latest.” See [EV research methodology](EV_RESEARCH_CALLS.md).

A saved earlier cutoff cannot silently acquire a later final election. Final returns from the cutoff calendar year or later are conservatively withheld because the archive does not establish contemporary final-publication timing. Original earlier historical context remains available. Pale slate on a selected/place-page map means outside that scope or unavailable, separate from zero.
