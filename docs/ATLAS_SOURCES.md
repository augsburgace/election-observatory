# Nationwide election atlas evidence

The atlas stores historical candidate or ballot-option votes separately from early-voting participation. It does not add contests together to create a turnout measure. All source bytes are content-addressed outside Git, with SHA-256, URL, retrieval time, snapshot ID, parser version, and a global dataset revision.

## Installed nationwide reference core

| Evidence | Verified producer and original location | Coverage | Status |
|---|---|---|---|
| State presidential results | MIT Election Data and Science Lab, [Dataverse](https://doi.org/10.7910/DVN/42MVDX) | 1976–2024, all 50 states | Original-producer public CSV, CC0 |
| State Senate results | MEDSL, [Dataverse](https://doi.org/10.7910/DVN/PEJ5QU) | 1976–2024; stages and special contests retained | Original-producer public tabular file, CC0 |
| House district results | MEDSL, [constituency returns](https://github.com/MEDSL/constituency-returns) | 1976–2018 | Original-producer archived release; district vintages differ |
| County presidential results | MEDSL, [county returns](https://github.com/MEDSL/county-returns) | 2000–2016 | Archived original-producer release; current complete Dataverse file requires a guestbook |
| County presidential results | Tony McGovern, [US County Level Election Results](https://github.com/tonmcg/US_County_Level_Election_Results_08-24) | 2020 and 2024 | Explicit secondary gap bridge, MIT license; replaced by more authoritative data where loaded |
| Resident population | Census Bureau, [ACS summary file](https://www.census.gov/programs-surveys/acs/data/summary-file.2024.html) | 2020–2024 ACS 5-year, states and counties | Published estimate and 90% margin of error, public domain |

The national catalog covers 50 states. It excludes Washington, D.C. from national sums and does not claim that these sums are the complete United States total. Alaska borough/county presidential estimates are not manufactured; Alaska retains state and native reporting-unit evidence.

The county bridge has Democratic and Republican votes plus an explicitly aggregated residual for other candidates. It does not invent individual minor-candidate returns. Names, votes, and current candidate-ballot status must not be inferred from this residual.

## Deep data on demand

Public, original-producer MEDSL ZIPs are verified for every state's [2024](https://github.com/MEDSL/2024-elections-official), [2022](https://github.com/MEDSL/2022-elections-official), and [2018](https://github.com/MEDSL/2018-elections-official) general elections. Initial deep installations cover Texas, North Carolina, Maine, and Alaska in 2024, and Texas in 2022. Other ZIPs download only when requested. Dataset loading archives the source, parses and validates it, and publishes one atomic revision. Source failures retain the previous usable data.

These files contain a variable inventory of presidential, congressional, statewide, legislative, judicial, local, and ballot-measure contests. The catalog distinguishes prospective office families from the actual verified office names discovered after parsing. It does not claim complete local coverage. Multi-seat magnitudes are producer estimates and require caution.

The [2020 per-state Dataverse inventory](https://doi.org/10.7910/DVN/NT66Z3) has verified exact file identifiers but requires a guestbook response. Its catalog entries are `guestbook_required`. The application neither bypasses that gate nor fabricates the user's personal information. Existing state and county reference data remain available.

Precinct identifiers preserve state, source year, and native jurisdiction. They do not establish a match to Census voting-district geometry. Precinct maps require a separately verified crosswalk. Alaska's absentee reporting areas are not treated as borough boundaries.

### Vote-method reconciliation

At each native reporting-unit/contest/ballot-option scope, a source `TOTAL` supersedes its component method rows. Without a `TOTAL`, published method components are summed. No total is added to its own components. The original method labels remain in provenance. Overvotes, undervotes, registration statistics, and ballot totals are excluded from candidate options.

Suppressed or nonnumeric values remain missing; their aggregate is flagged incomplete. Exact candidate percentages and winner labels are withheld when suppression makes them unsupported. Write-ins and published ballot responses remain distinct. Tied contests, multi-seat contests, and ranked-choice records without round provenance expose a leading option without claiming an eventual winner.

### Cross-source differences

Actual source vintages do not always reconcile. For example, the 2024 MEDSL Texas precinct file sums to 11,404,528 presidential candidate votes, while its dedicated statewide compilation sums to 11,388,674. North Carolina and Maine also have differences between the two releases. These are differences in the original source records, not an instruction to rescale counties. Responses report the independent statewide reference, difference, and `source_vintage_or_coverage_difference` status. Maps and exports preserve the original values and warning.

Margins are explicit: `dem_margin_pp = DEM − REP`; `rep_margin_pp = REP − DEM`; `margin_pp` is the positive lead of the largest option over the second largest. `winner_margin_pp` is available only when the source and contest support a winner label. Cross-cycle swing is withheld for counties, districts, and precincts until a defensible geographic crosswalk exists. Stable state boundaries allow state comparisons from 1960 onward.

## Population context

Census API requests currently return a missing-key page, so the keyless bulk [2024 ACS table-based summary files](https://www2.census.gov/programs-surveys/acs/summary_file/2024/table-based-SF/data/5YRData/) supply B01003 total population, B01002 median age, and B19013 median household income. The provider streams these files and retains only state and county records. Estimates, original 90% margins of error, period, and raw special-value annotations are preserved. Negative Census sentinel codes become a missing analytical value with the original code retained.

These describe resident population or households, **not voters**. They are not a current registration denominator. The five-year period is January 2020–December 2024; income uses 2024 inflation-adjusted dollars. No demographic intersection is inferred.

## Operating commands

```sh
.venv/bin/python scripts/atlas_data.py --core
.venv/bin/python scripts/atlas_data.py --catalog --state TX
.venv/bin/python scripts/atlas_data.py --dataset medsl_2024 --state TX
.venv/bin/python scripts/atlas_data.py --dataset acs2024_median_age
.venv/bin/python -m pytest backend/tests/test_atlas_data.py
```

`--offline` reparses an already archived source. Public Python interfaces are exported from `observatory.atlas`: `state_catalog`, `dataset_catalog`, `availability`, `search`, `result_query`, `context_query`, `load_dataset`, and `core_install`. Every numerical query accepts a dataset revision. Existing early-vote records and pinned saved views remain untouched by the additive atlas schema.

Ranked-choice applicability is office- and year-specific: Maine congressional general elections from 2018 and presidential general elections from 2020; Alaska specified state/federal offices from 2022. Local and judicial-retention races are not automatically classified as ranked-choice. Compilation files without an explicit tabulation round are labeled `reported_round_unspecified`, never presumed first-choice or final-round. See [Maine SOS](https://www.maine.gov/sos/sites/maine.gov.sos/files/content/assets/rcv-faq.pdf) and [Alaska Division of Elections](https://www.elections.alaska.gov/election-information/).
