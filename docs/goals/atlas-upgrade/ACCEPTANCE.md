> Historical revision-99 release record. The subsequent precinct, historical, reporting and EV-call implementation is documented in [the depth release](../atlas-depth/VERIFICATION.md).

# Election atlas acceptance audit

Reviewed October 21, 2026. This is an independent code, evidence, interface, and recovery audit against the approved colorful 50-state atlas plan. Browser aesthetics, keyboard behavior, and viewport acceptance are recorded in the [separate visual QA pass](../../ATLAS_VERIFICATION.md); this document does not infer those results from a successful build.

**Assessment:** a substantial working local atlas upgrade is implemented. The full research vision still has evidence-dependent modules and some remaining product work. “50 states” describes real nationwide historical/context coverage and source discovery; it does not mean complete current early-voting, every local contest, or verified precinct polygons in every state.

## Implemented and demonstrated

| Requirement | Evidence and practical limits |
|---|---|
| Substantive nationwide foundation | The final verified revision-99 backup contains historical result records and resident context for all 50 states: 1,698,270 stored result versions, 16,205 contests, 48,556 ballot options, and 9,579 context estimates. These counts are records/versions rather than unique voters or complete election inventories. |
| Separate participation, contest returns, and context | Existing participation observations remain separate from new elections/contests/options/results and Census context models. Ballot measures retain response-option identity; contest counts are not turnout. Texas's 38 House contests do not acquire a misleading combined participation total. |
| Canonical and native geography | All 3,112 collected 2024 county/county-equivalent identifiers join the local 2024 Census boundaries. Source IDs and saved legacy selections remain usable. Native Alaska districts and Maine municipalities are not allocated into county polygons. Historical unmatched IDs remain inspectable. |
| Chronology and quality | New Maine parsing withholds request-date reconstruction. Quality revision 68 quarantines 828 retained request-date rows, preserving originals and older pinned views with current quality warnings. Reconstructed and as-reported histories remain distinct. |
| Shared analytical queries | Current/baseline values, individually labeled place trajectories, rankings, contribution changes, concentration, coverage, and evidence references use shared backend services. Date-window tests verify matching headline cutoff, compatible series, place series, and exported observation scope. |
| Visual-system implementation | Code contains the editorial light canvas/navy navigation, complete navy tokens, locally bundled Source Sans 3/Source Serif 4, semantic palettes, quantitative bins/legends, shared map specification, and area-proportional symbols. Browser fidelity and contrast still require their own evidence. |
| Connected state research | Scrollable state overview sections combine participation, geography, history, composition, polls, context, and sources. Specialist workbenches remain available. Historical context is labeled separately when current geographic evidence is absent. |
| All-office discovery and deep loading | The verified inventory exposes original-producer state archives and prospective office families. Actual loaded office names are discovered from source records. Queue jobs retain progress, source errors, and prior validated evidence. State-specific dataset families require the correct state. Guestbook-required sources remain visibly gated. |
| Durable research interfaces | Versioned catalogs, search, results, context, geography versions, denominators, per-place research, contests, ballot options, saved investigations, and exports coexist with `/api/v1`. Deep place history and precinct results are paginated. |
| Reproducible historical exports | An actual Texas 2024 county package at revision 97 was exported and regenerated through the normal CLI using the restored evidence store: 254 places, 11,404,528 candidate votes, `results_agree=true`, and `source_hashes_verified=true`. Historical HTML/PDF now includes vector candidate/option distributions and historical share figures; manifests retain presentation and application/parser/boundary references. CSV formula protection and tamper detection have regression coverage. |
| Named options and complete place-history access | Historical maps support a named candidate/response share with explicit option selection; new nonpartisan investigations use a meaningful volume default. Explicit and pinned layers remain preserved. Place dossiers expose previous/next historical pages rather than presenting the first page as the entire archive. |
| Recovery and migration | The final revision-99 CLI backup/restore verified 338 archive hashes, 388 snapshot paths, SQLite integrity, all-state row counts, and the real saved North Carolina revision-29 view (733,299). The earlier revision-97 backup remains retained. A genuinely empty database migrated to `0002_election_atlas` without seeded observations/results. |
| Local operating boundaries | Loopback serving, locally archived evidence/boundaries/fonts, bounded source collection, durable jobs, source-failure retention, and the two-hour local schedule remain. No public deployment, paid service, or external AI API was introduced. |

## Evidence-dependent limits

These are visible limits of the available evidence, not permission to create substitute numbers:

- At revision 97, **14 states** had at least some reported current-cycle participation observations: AK, AZ, FL, GA, IA, KS, ME, MI, MN, NC, NE, OH, SC, and TX. Definitions, methods, geography, and dates differ. Additional state bridges activate on demand and may still fail or lack usable detail.
- The 2024 county corpus omits all 30 Alaska borough/census-area geometries and Kalawao, Hawaii. Alaska retains statewide/native reporting evidence. Missing areas are not zeros.
- Connecticut has nine planning-region county equivalents in 2024 and eight historical counties in 2020. No invented one-to-one crosswalk is used.
- County/district/precinct swing is withheld without defensible boundary harmonization. Ranked-choice compilation records without tabulation-round provenance do not establish first-choice/final-round comparisons or eventual winners.
- Producer precinct totals and dedicated statewide compilations differ in Texas, North Carolina, Maine, and Connecticut. The application preserves both values and reconciliation warnings rather than rescaling detail. See `docs/ATLAS_VALIDATION.md`.
- Published joint demographics, coherent ballot-status cohorts, dated registration denominators, voting-opportunity calendars, detailed historical snapshots, complete poll crosstabs, and native precinct polygons are source-specific. Separate marginals cannot establish intersections.
- Date-only publication fields do not establish an hour. The implemented conservative rule uses the end of that New York day or an earlier documented same-day first observation; a date alone never establishes a midnight release. Revised bytes require their own publication time or first archive.
- Public source inventories are broader than installed evidence. Office-family metadata is prospective; discovered source rows determine actual offices and years. General-election collections do not establish comprehensive primary, runoff, or local-election coverage.
- The 2020 per-state Dataverse deep archives require a producer guestbook response. That access requirement is not bypassed.
- Live forecasts remain gated pending suitable timestamp-safe historical validation and election-system modeling. Scenario outputs remain explicit assumptions.

## Corrections found during this acceptance pass

The following were reported and corrected in current source code before final review:

- Pinned revision propagation in national history, place profiles, contest lookup requests, and cache keys.
- An old correlated geography lookup that timed out after 60 seconds. The replacement materializes known `(geography_id, year)` pairs once, also preventing later geography-vintage metadata from appearing in an older pin. Direct corrected-route checks were 175 ms for NC revision 29 (zero known atlas versions) and 316 ms for revision 97.
- Automatic historical downloads now check the selected year as well as office; a 2024 investigation does not automatically request an unrelated 2022 archive.
- Precinct queries are bounded to at most 200 areas, with pagination metadata; precinct/district values are not painted onto county boundaries.
- A Census missing-income annotation (`NM county:35011`, raw `-666666666`) was correctly stored as missing but initially coerced to zero by the frontend. Current map/scatter conversion filters missing estimates rather than displaying $0.
- README now specifies Node **22.12+**, consistent with the installed Vite engine requirement.

The root integration now threads the complete active participation query—including cutoff, method, metric, time basis, and date window—through place dossiers, rather than only their revision. Exact place-query propagation remains part of the final interface/browser regression pass. Seven added chronology regressions cover intraday original records, poll releases, corrections, timezone boundaries, catalog agreement, and daily/pinned replay.

## Executable checks and performance

This pass initially ran 23 focused integrity/API/reproduction regression cases successfully. The subsequent chronology change passed 44 targeted cases covering the new availability rule together with analytical, evidence-workflow, and service-scope regressions. The frozen release passed 138 backend tests and 8 frontend tests, plus the TypeScript/production build checks reported by the root release pass. Browser checks remain separately recorded; they are not replaced by these test counts.

Actual revision-97 backend timing, including JSON serialization on this Mac:

| Query | Repeated read | JSON size | Coverage |
|---|---:|---:|---|
| Texas 2024 presidential statewide | 4 ms | 35 KB | One statewide contest result |
| Texas 2024 presidential county | 45 ms | 1.50 MB | All 254 collected counties |
| Texas 2024 presidential precinct | 135 ms | 662 KB | First page of 200; total source areas remain in pagination metadata |

Peak process resident memory during this bounded benchmark was approximately 108 MB. These are backend spot checks rather than a browser-interaction guarantee. Root HTTP proofs additionally record compressed response sizes and cached participation response times. No national precinct geometry is loaded initially.

Artifacts:

- `.local/atlas/acceptance-performance.json`
- `.local/atlas/final-api-proof.json`
- `.local/atlas/performance.json`
- `.local/atlas/acceptance-TX-2024-r97.zip`
- `.local/atlas/acceptance-TX-2024-r97-reproduced.html`
- `.local/atlas/post-upgrade-restore-proof.json`
- `.local/atlas/final-r99-restore-proof.json`
- `docs/ATLAS_RECOVERY.md`

## Remaining product work and release qualifications

Named-option share maps, nonpartisan defaults, place-history pagination controls, and figure-rich historical HTML/PDF exports were completed during final integration. They are no longer listed as missing features. The following distinctions remain:

1. **Precinct cartography:** source-native precinct result tables are useful now; verified native boundaries, crosswalks, and geographic levels of detail still need onboarding. Precinct values alone do not supply polygons.
2. **Historical harmonization:** county and smaller-area crosswalks, robust matched-boundary differences, and synchronized historical map comparisons require additional source-backed work. Current original margins remain available.
3. **Full chart-catalog depth:** the upgrade adds trajectories, change bars, calendars, mode/composition charts, endpoint references, ranked geography, concentration, waterfalls, candidate distributions, and contextual scatterplots. It does not establish complete implementation of every proposed dumbbell, cohort small-multiple, bivariate, distribution, or composition-change graphic in every state.
4. **Historical report composition:** historical exports now include sourced vector figures and reproducibility/presentation manifests. A fully rearrangeable historical report composer with arbitrary combined maps/charts, specialized templates, and complete saved figure layouts remains additional product work. Existing participation report composition remains available.
5. **Complete interaction coverage:** map/ranking focus and selections, individually labeled place trajectories, and date brushes are implemented. Universal keyboard-linked highlighting across every chart/table/category and every comparison layout should be tested and expanded explicitly.
6. **Accessibility qualification:** the root browser pass covers the requested 390, 768, 1440, and wide-desktop viewports, both themes, keyboard/reduced-motion and readability checks in its separate record. WCAG 2.2 AA remains the target; this is not a formal accessibility certification, and a screenshot or build alone does not establish conformance.

The final full backup and independent restoration are pinned to revision 99, preserving the earlier revision-97 recovery artifacts. See `docs/ATLAS_RECOVERY.md` for the exact final counts and checksums.

This upgrade can be released as a useful local research atlas with the above qualifications. It should not be represented as complete nationwide real-time voting coverage or completion of every expansive research feature.
