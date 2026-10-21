# Atlas depth and EV research release — October 21, 2026

This continues the revision-99 atlas release. The installed evidence is pinned to **revision 176**. Senate research is the first forecasting priority; the broader atlas supplies inspectable historical and geographic context. This is a local release, with no public deployment.

## Delivered workflows

- **Precinct research:** verified public source-native acquisition paths for all 50 states; live cached NC 2024, TX/OH/ME/AK 2020 maps. Exact IDs, original CRS, validated geometry, three levels of detail, viewport bounds, source hashes, quantitative legends, keyboard/vector alternatives and selectable original records. Ohio's actual queued download completed with 8,941 matched boundaries. No national precinct download is required on opening.
- **Historical comparisons:** reviewed material county-boundary compatibility for 2018–2024, matched-coverage calculations, synchronized original maps, swipe, eligible difference maps, saved cameras and numeric scales. Alaska native areas and Connecticut changes retain their limitations. Unspecified rounds, incompatible definitions and unproved crosswalks do not become differences.
- **Advanced graphics:** paired-margin dumbbells, transition scatterplots, geographic margin distributions, concentration curves, bivariate income/result maps with a labeled 3×3 legend, individually labeled selected-place trajectories, indexed EV histories, reporting matrices and a working shared date brush. Population context remains separate from measured voters.
- **Senate research calls:** all 35 scheduled contests are represented. At r176/v1.1, 22 have an eligible EV geographic adjustment, 10 are historical references only, and three are withheld. Ohio is R+2.8 and North Carolina R+1.7 under the displayed research assumptions. All winner probabilities are null. Louisiana lacks a defensible party-margin reference; Maine/Alaska lack the necessary electoral-system and option evidence.
- **Report studio:** complete state, EV, historical, resident-context, polling, custom and Senate-call templates; section selection/order, captions, saved configurations, explicit private-note inclusion, exact preview, PDF/HTML/SVG/CSV/JSON/ZIP exports. Historical results, participation and resident context preserve separate scopes. The Senate dossier includes its model manifest and assumptions.
- **Evidence interpretation:** a shared EV guide explains the exact measure, dates, source-native definitions, geographic reconciliation, revisions and unsupported interpretations. Current reported measures now cover 43 states. Original Hawaii and Oregon receipt reports supplement the broader attributed UF research bridge.

## Source and chronology corrections

AZ issued ballots are not requests. TX/DE/DC/UT/WA request proxies are excluded; older affected records are quarantined through source-scoped append-only validation. Tennessee's duplicated in-person family is not an all-method total. Ohio's producer-inferred mode and Iowa's received-versus-accepted distinction remain explicit. KY/MD upload dates cannot establish a dated geographic EV adjustment. Maine's standing-request dates remain withheld.

The EV model requires a positive statewide measure, reconciled geographic totals, sufficient matched evidence, verified underlying report dates and supported historical geography. Its historical Senate reference preserves regular/special identity, final Georgia runoffs including January 2021, and excludes unsupported jungle/independent configurations. Later outcomes cannot enter earlier requested cutoffs.

Reports withhold future final returns, future baselines and baseline-derived swing. They also withhold unreleased ACS context and future precinct bundles. The 2024 ACS five-year release was January 29, 2026; its estimate period alone is not a publication date.

North Carolina 2024's physical-precinct map covers **3,917,853 of 5,697,901 reported candidate votes (68.76%)**. Another **1,780,048 votes** in 254 administrative/unmatched units remain outside those residential shapes. Their counts stay inspectable and are never allocated into neighborhoods. VEST source allocations/estimation are labeled as producer methodology, not observed current EV.

## Evidence and reproduction checks

The database contains 268,628 observation versions, 5,598,143 historical result versions, 17,428 contest records, 9,579 resident-context versions, 19 original polling studies and 617 source snapshots backed by 386 unique archived documents. These are records, not turnout totals. See [current participation coverage](../../COVERAGE.md) and [historical atlas coverage](../../ATLAS_COVERAGE.md).

The actual Ohio report was composed in the browser, its geography chapter moved before change bars, a researcher caption added, and the configuration saved at r176. Exporting its ZIP and regenerating HTML produced byte-identical HTML; source hashes, boundary hashes, selected order and calculations agreed. Files are in `output/atlas-depth/`. The final NC Senate dossier in `output/atlas/ev-senate-nc-final.zip` also reproduced with its 90 source references, geometry and model manifest; its PDF was rendered and visually reviewed.

A complete 1.25 GiB backup was independently restored, verifying every archived document, 37 geometry files, database integrity and migration `0004_result_validation`. The restored app resolved OH/NC native geometry, all 50 states, Ohio's 88-county EV total, the saved report/caption/order, and the older NC revision-29 investigation (733,299). Full evidence: `.local/atlas-depth/restoration-proof-r176.json` and [depth-release recovery documentation](../../ATLAS_DEPTH_RECOVERY.md).

## Verification

The integrated backend suite passed **214 tests**, including offline restoration. The frontend passed **17 tests**, including rendering the real Forecasts component with actual Ohio/Alaska API shapes and compact bootstrap data. TypeScript and production compilation passed; Ruff passed across backend, migrations and scripts.

Rendered verification at actual CSS widths **390, 768, 1440 and 1920** covers both themes, reduced-motion preferences, no page-level horizontal overflow, and real historical swipe/difference/bivariate maps, a source-native NC precinct map, keyboard precinct selection and URL persistence, full-screen exploration, the report composer/save/export flow, date-brush keyboard changes and actual observation playback. A browser-discovered bootstrap-shape crash was fixed, covered by the component regression, and an error boundary now preserves navigation if a renderer fails. The history ledger distinguishes an older zero-valued report from a compatible same-stage observation.

## Qualifications

These conditional EV research calls are **not validated election forecasts**. Their geographic coefficient and wide sensitivity ranges are explicit unvalidated assumptions. There are **zero held-out EV-model cases**. Historical-reference error diagnostics do not validate the EV adjustment or establish as-reported backtesting. Polls do not enter this initial EV model. Candidate rosters remain unverified; point calls are party-margin references rather than named-candidate probabilities.

Missing current EV coverage: AL, LA, MO, NH, NY, WA, WV. Original authority access, daily historical publication evidence, all-year native precinct crosswalks, current residential-precinct EV, complete local-election coverage, individual propensity and published joint composition remain uneven or unavailable. Religion and individual candidate choices are not inferred. Equivalent calendar days do not establish equal voting opportunities. Source outages retain previously validated evidence.

The requested scientific forecasting validation and exhaustive public-data coverage remain research work. No claim of proven predictive accuracy, formal WCAG certification or complete collection of every election is made.

Browser proof images are retained under `frontend/qa/atlas-depth/`. The final Ohio PDF in `output/atlas-depth/ohio-senate-r176.pdf` was rendered and all its pages visually checked; its ZIP regenerated byte-identical HTML with all source/boundary checks passing. The complete restore also rebuilt 382 URL-cache records: original NC PDF, UF CSV and VEST ZIP opened offline with network requests blocked.

Final HTTP spot checks (r176, including JSON transfer/decoding on this Mac) were 30 ms for the cached Ohio participation workspace, 6 ms for its quality guide, 57 ms for NC paired counties, 81 ms for the cached national Senate call response, and 232 ms for a bounded Ohio native-precinct viewport (1,157 features). The full national model is intentionally a slower cold calculation. These are backend spot checks, not universal browser-performance guarantees. Proof: `.local/atlas-depth/final-http-proof.json`.
