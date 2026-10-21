# Atlas evidence and geography validation

Audit date: October 21, 2026 (America/New_York). Historical-result checks below are pinned to dataset revision **88**; later collections may add evidence. This audit uses the actual local SQLite evidence and the locally archived Census boundary files, rather than demonstration values.

## 2024 geographic joins

- **3,112 distinct 2024 county/county-equivalent identifiers** are present in collected historical results.
- **3,112 match the archived 2024 Census GEOIDs; 0 are unmatched.** Different capitalization or producer labels do not create additional places.
- The local boundary set contains **3,143** county/county-equivalent geometries. A successful join does not establish complete result coverage or compatible historical boundaries.
- **31 boundary areas have no collected 2024 county result:** all 30 Alaska borough/census-area geometries, plus **Kalawao, Hawaii (`county:15005`)**. Absence is not a reported zero.
- Alaska's collected 2024 evidence includes statewide, native district, and precinct records. It is not allocated into borough totals.
- Connecticut's 2024 evidence uses **nine planning regions**, which are Census county equivalents: Capitol (`09110`), Greater Bridgeport (`09120`), Lower Connecticut River Valley (`09130`), Naugatuck Valley (`09140`), Northeastern Connecticut (`09150`), Northwest Hills (`09160`), South Central Connecticut (`09170`), Southeastern Connecticut (`09180`), and Western Connecticut (`09190`). The 2020 evidence instead has eight historical counties. These do not acquire an invented one-to-one comparison.

The application keeps original geography IDs and adds canonical IDs. Legacy aliases such as North Carolina's New Hanover and Iowa's O’Brien, Cerro Gordo, Buena Vista, Palo Alto, and Van Buren resolve within their verified state/county scope. Virginia's identically named counties and independent cities remain ambiguous without a GEOID or distinguishing Census label. An explicit foreign or unknown GEOID cannot be overridden by a familiar place name.

## Historical-vintage exceptions

The following source identifiers have no geometry in the **2024** boundary set. They remain evidence records; a current map must not distribute or silently rename them.

| Result years | Unmatched identifiers | Count per year |
|---|---|---:|
| 2000, 2004, 2008, 2012, 2016 | Connecticut `09001` Fairfield, `09003` Hartford, `09005` Litchfield, `09007` Middlesex, `09009` New Haven, `09011` New London, `09013` Tolland, `09015` Windham; Missouri `36000` Kansas City source reporting row; South Dakota `46113` Oglala Lakota source label; Virginia `51515` Bedford | 11 |
| 2020 | The eight historical Connecticut county identifiers above | 8 |
| 2024 | None among the 3,112 collected county identifiers | 0 |

The Missouri source row's `36000` identifier is not a valid Missouri Census county identifier. It is not mapped onto a different county. No equivalence or population-weighted crosswalk is implied for these exceptions.

Current election maps use archived Census **2024** geometry. Historical result records preserve their source election vintage. Matching IDs alone do not prove unchanged boundaries: county/district/precinct swing is withheld until a defensible crosswalk exists. Original margins remain inspectable. State comparisons use stable state boundaries where supported.

## Actual source reconciliation

The collected 2024 producer precinct compilation and the dedicated statewide compilation do **not** always sum to the same number. These are candidate-vote totals, not early ballots or turnout denominators.

| State | Detailed geographic sum | State reference | Detail minus state | Relative difference |
|---|---:|---:|---:|---:|
| Texas | 11,404,528 | 11,388,674 | +15,854 | +0.1392% |
| North Carolina | 5,697,901 | 5,699,141 | −1,240 | −0.0218% |
| Maine | 824,806 | 831,375 | −6,569 | −0.7901% |
| Connecticut | 1,758,429 | 1,759,010 | −581 | −0.0330% |

Texas, North Carolina, and Maine detail comes from the MEDSL 2024 state precinct datasets; Connecticut currently uses the explicitly labeled secondary county compilation. The state references come from the MEDSL statewide presidential collection. The application exposes the producer IDs, snapshot hashes, and reconciliation warnings. These differences are not automatically attributed to one particular cause, and the detail is not labeled reconciled certification. Source vintages, treatment of write-ins, election rounds, or completeness require additional producer-specific review.

## Election and chronology safeguards

- Texas 2024 U.S. House district view contains **38 separate contests**. Its combined participation total is **unavailable**, rather than a misleading sum across contests.
- **153 multi-seat contests** were present in the revision-88 catalog. A leading option is not presented as the unique elected winner of a multi-seat contest.
- Alaska and Maine compilations without documented tabulation rounds are labeled `reported_round_unspecified`; they are not presumed first-choice or final-round. Eventual winners and round-compatible swing are withheld until that provenance is established. Ties and partially suppressed results do not produce a definitive winner.
- Requests, issuance, returns, acceptance, candidate votes, and resident population remain separate measures. Resident context is not a measured voter demographic.
- Quality revision **68**, published October 21, 2026, quarantines **828 retained Maine request-date reconstruction rows**. Standing requests and anomalous dates do not establish current-election voting events. Original records and archives remain intact; older pinned revisions retain their original values with a separately identified present-day quality warning.
- The revised Maine parser produces no request-date trajectory. It preserves snapshot presence counts with record-count caveats and excludes malformed, future, or outside-cycle dates from issued/returned event timelines.
- Date-only publication metadata establishes availability by the end of its New York calendar day, or an earlier documented same-day first observation. It does not establish a midnight release. Revised bytes require their own publication evidence or first archive time.
- A chart date window constrains the evidence cutoff, compatible chart series, individually labeled place trajectories, and selected export rows together. Historical dates align to the election-relative window rather than acquiring synthetic observations.

## Reproducibility and test coverage

The audit selects distinct `(state, geography_id)` pairs from `atlas_results` for year 2024 at revision ≤88 and compares each county GEOID against the locally archived Census GeoJSON index. The unmatched historical table uses the same method for each available year. It examines the shared `result_query` responses for totals, winner restrictions, explicit round-provenance limits, source reconciliation, and incompatible multi-contest aggregates.

Regression tests cover county aliases, ambiguous city/county names, canonical versus legacy selections, unassigned native reporting areas, non-finite observations/denominators, anomalous dates, Maine quality-revision replay, date-window agreement, per-place series, paginated observations, dataset/state validation, pinned place history, and spreadsheet-safe CSV exports. Core tests use explicitly synthetic fixtures and never install those values into the user's dataset.

Performance spot check on this Mac: North Carolina's compact research response was approximately **2.44 MB** before HTTP compression, **2.67 seconds** on a cold analytical read and **12 milliseconds** on an immediate cached read. This is a limited spot check, not a guarantee for every state or a complete browser-performance benchmark.
