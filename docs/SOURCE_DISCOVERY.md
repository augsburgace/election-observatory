# Source discovery, evidence coverage, and connector limits

Verified during implementation on October 20, 2026 (America/New_York). Source availability can change. The Sources screen and archived collection outcomes are the current operational record; this document describes what the adapters actually support.

## Coverage achieved

The registry includes all 14 requested battlegrounds. There are direct original-election-authority adapters for North Carolina, South Carolina, Florida, and Alaska. A conservative local Maine record aggregator and an original Iowa PDF parser are implemented. Iowa's file server currently rejects ordinary requests from this network.

An explicitly attributed **University of Florida Election Lab academic fallback** supplies current aggregate observations for nine additional state feeds. Combined with direct feeds, early-voting information is available for 13 battleground states. New Hampshire remains an explicit statewide-data gap. Academic data never becomes a direct official source merely because the tracker links an election authority.

| State | Direct authority support | Attributed fallback and limitations |
|---|---|---|
| Alaska | HTML statewide issued/received totals and native voting categories; 2026 plus 2018/2020/2022/2024 final references | Historical totals include questioned ballots and some early votes cast on Election Day. Native categories are retained. No county geography fabricated. |
| Florida | Official public TXT downloads for outstanding mail ballots, voted mail, and voted early; county and registration marginals | Blank compilation dates are unreported submissions, not observed zeroes. Combined early totals require both modes on the same geographic reporting date. |
| Georgia | Official dashboard registered; ordinary HTTP requests encounter a challenge | UF statewide total and available marginals. Its county file currently fails reconciliation with statewide totals, so county observations are withheld. Source notes describe same-day county-dashboard adjustments. |
| Iowa | 2026 original source-dated, 100-page county PDF parser implemented; source access currently HTTP 403 | UF statewide and 99-county aggregates. UF explicitly infers mail acceptance from receipt date; these are conservatively exposed as returned ballots. Legacy 2022/2024 PDF layout is not claimed implemented. |
| Kansas | Official Power BI government report discovered; unattended extraction not validated | UF statewide and 105-county aggregates, with available registration, age, and gender marginals. Partial subgroup coverage remains labeled. |
| Maine | Current pipe-delimited public file is aggregated privately into record counts and municipality/registration-code marginals | Direct record counts include duplicate/reissued and rejected records and are **not valid ballots or unique voters**. UF supplies separately attributed turnout aggregates by municipality, although its export filename says `county`. |
| Michigan | Official page currently returns Access Denied to ordinary requests | UF statewide and 83-county aggregate mail participation and available age data. All-zero in-person placeholders are excluded. |
| Minnesota | Official page returns a CAPTCHA challenge; no attempt to bypass it | UF statewide and 87-county aggregates, last updated October 16 in the verified snapshot. The date remains stale rather than being relabeled October 20. |
| Nebraska | Repeatable public statewide daily official aggregate feed not established | UF statewide and 93-county aggregates; tracker identifies a file provided by the Nebraska Secretary of State. |
| New Hampshire | Official election source registered; statewide repeatable daily feed not established | No invented observations. New Hampshire is absent from the verified UF CSV. |
| North Carolina | Original county aggregate CSVs and dated official report archives for 2026, 2024, 2022, 2020, 2018; cast ballots, voting method, and published demographic marginals | Current CSV has no publication date: observations carry retrieval day in New York time with a warning. CSV historical files are final endpoints. Dated PDF report series retain printed dates and object-version chronology separately. |
| Ohio | Official dashboard and advertised public downloads identified; network receives security/maintenance responses | UF statewide and 88-county aggregates. Source notes explicitly say in-person voting is approximated using same-day issuance/receipt. |
| South Carolina | Current early-in-person CSV; 2022 and 2024 archived general-election XLSX daily county reports | General-election workbooks are selected explicitly, excluding primaries/runoffs. Daily columns are reconstructed event-time series; contemporary publication history is not invented. Absentee mail is not silently included in early-in-person totals. |
| Texas | Original current/historical authority index registered; portal export not validated | UF statewide totals. County export is unavailable. **UF substitutes returns for requests in Texas; this adapter omits that synthetic request field.** |

## Original sources and exact extraction paths

### North Carolina

- Documentation/index: <https://www.ncsbe.gov/results-data/absentee-and-provisional-data>
- 2026 aggregate: <https://s3.amazonaws.com/dl.ncsbe.gov/ENRS/2026_11_03/absentee_counts_county_20261103.csv>
- Previous general-election files use the exact links advertised on that index, with election dates 2024-11-05, 2022-11-08, 2020-11-03, and 2018-11-06.

The authority defines these counts as **absentee ballots cast, including early in-person ballots**. The numeric column is literally named `0`. Each row is a joint county/request-type/party/gender/race cell, with ethnicity present in newer exports. The adapter sums original cells once into total and separate marginal families. It does not sum demographic subtotals into turnout or expose unsupported joint query filters.

`ONE-STOP` and `EARLY VOTING` map to `early_in_person`. The source's civilian/military/overseas categories map to mail, with UOCAVA inclusion documented. Registered party is not candidate choice.

The `nc_reports` connector additionally discovers dated PDFs from the authority's public `Press/<cycle> General/` bucket folders. It validates the printed report date against the filename and preserves the listing's object `LastModified` timestamp. That timestamp is the conservative availability boundary for the current document bytes: a historical filename does not prove that a later replacement was available on the original date. Reconstructed report trajectories retain the original report date and explicitly disclose the later evidence vintage. Current, 2022, and 2018 report series have been collected; 2024 and 2020 are configured and supported rather than represented by invented daily CSV history.

### South Carolina

- Current index: <https://scvotes.gov/elections-statistics/voter-participation/>
- Verified current download: <https://scvotes.gov/wp-content/uploads/2026/10/EV-Totals-10-19-26.csv>
- 2022 archive: <https://scvotes.gov/wp-content/uploads/2022/12/2022-Historical-Absentee-EV-Reports.zip>
- 2024 archive: <https://scvotes.gov/wp-content/uploads/2025/06/2024-Historical-Absentee-EV-Reports-1.zip>

Current downloads are rediscovered from the index rather than freezing October 19 into the adapter. County rows are separated from individual polling-place rows. The current report date and daily event columns have different meanings. For archived workbooks, only `EV Stats (2022 GE - scVOTES).xlsx` and `2024-GE-Early-Voting-Statistics.xlsx` are supported. A small standard-library XLSX reader preserves cell positions, including blank cells and shared strings.

### Florida and Alaska

- Florida index: <https://countyfilesvbm-ev.floridados.gov/VoteByMailEarlyVotingReports/PublicStats>
- Alaska tables: <https://www.elections.alaska.gov/research/statistics/>

Florida download links are rediscovered on every refresh. Published registration components must reconcile to each row's grand total. Same-day all-mode totals preserve component URLs. Alaska's statewide table update date is parsed directly; historical endpoints are labeled final and preserve questioned-ballot caveats.

### University of Florida Election Lab

- Source and license explanation: <https://election.lab.ufl.edu/early-vote/2026-early-voting/>
- State export: <https://election.lab.ufl.edu/data-downloads/earlyvote/2026/US.csv>
- Geographic exports: `https://election.lab.ufl.edu/data-downloads/earlyvote/2026/<ST>_county.csv`
- Source definitions: <https://election.lab.ufl.edu/wp-content/themes/electionlab2023/2026-early-voting.js>
- Age labels and national logic: <https://election.lab.ufl.edu/wp-content/themes/electionlab2023/2026-early-voting-national.js>

Attribution is **University of Florida Election Lab, Dr. Michael McDonald, 2026 Early Voting Tracker**. The source states CC BY-NC-ND 4.0. This is a private noncommercial research integration; the attribution, license, original authority lineage, state notes, and raw column are preserved on every normalized observation. Review redistribution and adaptations against the source's license before public publication.

UF's `voted_all` is mail received plus early in-person participation, not necessarily an accepted-ballot count under every state's legal definition. `accept_all` is conservatively normalized to returned mail ballots with state-specific notes. The source's all-zero demographic families encode absence of data and are excluded. Positive subgroup families can be incomplete; `breakdown_sum` and `breakdown_complete` travel with the rows.

Geographic files inherit the statewide data date only after all available mode totals reconcile with the statewide export. This guards against asynchronous publication. Files are archived even when observations are withheld. Source `turn_2022` is a separately labeled 2022 final participation reference and is not a 2026 turnout denominator.

### Maine private aggregation

The adapter discovers the current text file on <https://www.maine.gov/sos/elections-voting/voter-data>. As of the verified run it contains 203,470 parseable records plus eight incomplete rows excluded with an explicit warning. Its official field-code layout currently cannot be retrieved, so unknown status and duplicate/reissue semantics are not guessed.

Only aggregates leave the ingestion layer. The analytical API contains no voter IDs or individual records. Metrics `ballot_records_requested`, `ballot_records_issued`, and `ballot_records_returned` use **records** as their unit and must never be combined with cast/accepted ballot metrics. Reconstructed dated records do not establish historical publication dates.

## Polling coverage

The original-document parser supports Marist's published Senate vote-choice and winner-expectation crosstab pages for:

- Ohio, October 20 release, October 15–18 fieldwork.
- Iowa, October 15 release, October 8–11 fieldwork.
- Texas, October 14 release, October 8–11 fieldwork.
- Maine, October 6 release, October 1–4 fieldwork.
- Michigan, September 30 release, September 24–27 fieldwork.

These five studies yield 16 distinct population/question records. Original PDF URLs and release URLs are in `config/sources.json`; every value is extracted from PDF rows. Registered-voter sample sizes are not relabeled likely-voter sample sizes. Likely-voter n remains unavailable where the source discloses only RV n. `<1%` remains an upper bound, suppressed `*` remains unavailable, and subgroup uncertainty is never copied from statewide MOE.

ReconMR supplies a second original producer in Texas:

- Original publisher release: <https://sri.siena.edu/2026/10/13/talarico-maintains-small-lead-over-paxton/>
- Original tables: <https://sri.siena.edu/wp-content/uploads/2026/10/TXP004-Crosstabs.pdf>
- Original methodology: <https://sri.siena.edu/wp-content/uploads/2026/10/TXP004-October-Press-Release.pdf>

The poll producer is **ReconMR**, while Siena Research Institute hosts/publishes the documents. October 5–8 fieldwork, 617 likely voters, and 4.4-point reported statewide MOE are parsed from the original table header. Vote-choice and winner-expectation questions remain separate. Funding is recorded as not disclosed.

### Expanded original-producer research inventory

Thirteen additional source releases were fetched and parsed successfully, adding 24 distinct population/question records. Together with Marist and ReconMR, this represents **19 independent studies across 10 battleground states**, rather than 42 independent polls. Multiple populations, candidate pairings, or question types from one sample share a study identifier.

| Original producer | State and fieldwork | Parsed evidence and limitations |
|---|---|---|
| Elon University Poll / YouGov fieldwork | NC, September 29–October 8, 2026 | Original 47-page questionnaire. Vote choice and winner expectation each retain LV, RV, and adult populations. Sample sizes 561 / 691 / 800 and reported MOEs are population-specific. Undecideds are not reassigned. |
| University of Texas / Texas Politics Project | TX, September 25–October 5, 2026 | Original topline, Senate question Q21F, n=861 and MOE 3.34. The full RV n=1200 is not reused. Follow-up leaners are folded into the published Senate table, so it remains a distinct forced-choice ballot type. |
| Alaska Survey Research | AK, April 16–19, 2026 | Original ranking question, n=1946 LV. First choices and simulated RCV round 2 are separate records from one study, not eventual-winner probabilities. Older fieldwork remains visible. |
| Saint Anselm College Survey Center | NH, March 16–18, 2026 | Original questionnaire, n=1491 RV. Two pre-primary hypothetical pairings. PDF release date is not established; availability conservatively begins at first local retrieval, not a guessed March publication day. |
| Emerson College Polling | IA, October 5–6; August 31–September 1; August 2–4, 2026 | Three original narrative releases. Current October release is n=650 LV. Original response percentages and producer uncertainty are preserved; absent responses are not manufactured. |
| Emerson College Polling | GA, February 28–March 2, 2026 | Three pre-primary hypothetical Ossoff pairings from one study. Overall n=1000; population is labeled as the source's overall voters sample rather than guessing LV or RV. |
| Emerson College Polling | MN, February 6–8, 2026 | Two pre-primary hypothetical Democratic nominees versus Tafoya; one n=1000 LV study. |
| Emerson College Polling | ME, March 21–23, 2026 | Two pre-primary hypothetical Democratic nominees versus Collins; one n=1075 LV study. |
| Emerson College Polling | OH, August 18–19 and December 6–8, **2025** | Two studies for the 2026 race. Original 2025 fieldwork dates are retained and remain outside the current averaging window. |
| Bowling Green State University / YouGov fieldwork | OH, September 29–October 9, 2026 | Original university narrative, n=1000 LV, reported MOE 3.95. Original repository establishes October 16 availability. Mutable landing-page parser rejects another fieldwork period instead of reusing the old release date. |

Representative original releases and documents:

- [Elon release](https://www.elon.edu/u/news/2026/10/20/final-elon-university-poll-before-election-day-cooper-has-double-digit-lead-over-whatley-in-nc-us-senate-race/), [Elon original questionnaire](https://eloncdn.blob.core.windows.net/eu3/sites/819/2026/10/Elon-University-Poll-topline-methodology-10_20_26.pdf).
- [UT / Texas Politics Project release](https://texaspolitics.utexas.edu/blog/latest-ut-texas-politics-poll-finds-historic-levels-of-competition-in-texas-midterm-elections), [original topline](https://texaspolitics.utexas.edu/files/202610_POLL_TOPLINE-76f91287.pdf).
- [Alaska Survey Research original release](https://alaskasurveyresearch.com/peltola-vs-sullivan-april-2026/).
- [Saint Anselm original questionnaire](https://www.anselm.edu/sites/default/files/2026-03/March%202026%20NHRV%20Final_0.pdf).
- [Emerson Iowa October release](https://emersoncollegepolling.com/iowa-2026-poll-u-s-senate-race-tightens-sand-maintains-edge-for-governor/), [Georgia original release](https://emersoncollegepolling.com/georgia-2026-poll-senator-ossoff-starts-re-election-near-50-and-outpaces-gop-field/), [Minnesota original release](https://emersoncollegepolling.com/minnesota-2026-poll-democrats-lead-gop-as-voters-cite-threats-to-democracy/). Every other release URL is preserved in the source registry.
- [BGSU original findings](https://www.bgsu.edu/arts-and-sciences/democracy-and-public-policy-research-network/bgsu-poll.html), [dated original repository record](https://scholarworks.bgsu.edu/depo/31/).

Narrative-only estimates explicitly set `question_wording_exact=false`. The displayed question is a descriptive label, and the original paragraph is retained as evidence. These records use `release_summary` or `hypothetical` ballot types and do not silently enter the full-questionnaire descriptive average. Source-reported credibility intervals remain labeled as such rather than being described as probability-sample design-based MOEs.

There are still not three eligible comparable independent producers in any implemented state's current window. The application must therefore withhold the initial descriptive average. Texas has three producers overall, but UT's forced-choice treatment differs from Marist and ReconMR. Two populations, two questions, or two publishers from one study do not count as independent producers.

**Polling gaps:** Florida, Kansas, Nebraska, and South Carolina have no successfully ingested original Senate poll in this inventory. Coverage in Alaska, Georgia, Minnesota, and New Hampshire is older or hypothetical, not a claim of current general-election coverage. The NYT/Siena October 3 original producer release is discoverable, but linked New York Times questionnaires return access challenges on this network; no values were seeded from aggregator headlines. UNH September questionnaire and CNN/SSRS Ohio/Iowa original files are likewise unresolved public-document access gaps. BGSU's downloadable PDF returns an access challenge, so only its accessible original narrative is claimed. No credentials or paid subscriptions are required.

## Validation and operating checks

```sh
.venv/bin/python scripts/source_probe.py nc-counts-2026
.venv/bin/python scripts/source_probe.py sc-early-2022
.venv/bin/python scripts/source_probe.py uf-fallback-oh
.venv/bin/python scripts/source_probe.py marist-oh-2026-10-20
.venv/bin/python scripts/source_probe.py reconmr-tx-2026-10-13
.venv/bin/python scripts/source_probe.py elon-nc-2026-10-20
.venv/bin/python scripts/source_probe.py bgsu-oh-2026-10 --offline
.venv/bin/python scripts/source_probe.py uf-fallback-oh --offline
.venv/bin/python -m pytest backend/tests/test_connectors.py -q
```

`source_probe` archives responses and validates parsing without changing normalized database records. The normal collector publishes validated batches and records source failures. A valid HTTP status alone is not election-data success: discovery-only sources remain explicitly partial, while security pages and unsupported schemas fail without invented observations.

Important remaining work includes primary dashboard exports for blocked states; a verified New Hampshire early-voting feed; legacy Iowa daily PDF parsing; direct Maine status/reissue code verification; current full-questionnaire polling across all 14 states; official candidate ballot imports; and historical publication-vintage datasets suitable for forecast validation. No forecast is validated merely by having collected contemporary early-voting totals.
