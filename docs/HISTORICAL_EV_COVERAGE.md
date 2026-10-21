# Historical early-vote evidence and validation coverage

Updated October 21, 2026. This document describes installed evidence, not a claim of complete historical coverage. The application distinguishes historical source snapshots from final-record event reconstructions and certified candidate results.

## Installed 2020 producer archive

The United States Elections Project's [original producer repository](https://github.com/ElectProject/Early-Vote-2020G) retains historical state reports in versioned HTML. The collector archives the commit inventory and exact commit-addressed HTML, reads only published numeric tables and data-only JSON, and retains native county FIPS identifiers. It never executes R or JavaScript.

The actual acquisition published 150,699 observation versions in local revisions 243–249. Counts below are distinct native report dates, not fabricated daily interpolations. A source can publish several metrics on the same date. “Reconciled dates” means the source's county cells sum exactly to its corresponding statewide headline/table total; it does not independently prove that every county updated simultaneously.

| State | Report dates | Verified report-date range | Exact county/state participation reconciliation |
|---|---:|---|---|
| North Carolina |61|2020-09-01–2020-11-02|18 all-method cast dates;18 in-person dates;52 accepted-mail dates|
| Georgia |38|2020-09-18–2020-11-02|19 all-method cast dates;19 in-person dates;33 accepted-mail dates|
| Michigan |28|2020-09-24–2020-11-02|27 all-absentee accepted dates|
| Florida |63|2020-09-01–2020-11-03|11 all-method cast dates;11 in-person dates;47 received-mail dates|
| Iowa |29|2020-09-21–2020-11-03|25 all-absentee accepted dates|
| Ohio |23|2020-09-25–2020-11-02|None qualify for exact statewide/county reconciliation; retain as research evidence|
| Texas |18|2020-10-13–2020-10-30|Statewide totals only in the reviewed tracker template|

The underlying tracker can update headlines, maps and composition panels asynchronously. The application preserves disagreements and withholds an incompatible geographic forecasting adjustment. It does not fix a mismatch by scaling county values, distributing unallocated records, or changing a source headline. For example, the final Iowa snapshot has a four-ballot difference between the 99 county cells and its statewide headline; those original quantities remain distinct.

### Chronology and source hierarchy

These are tier 3 attributed academic research bridges, with the original authority lineage and producer notes preserved. Repository commit time records source vintage; it does not independently establish when an authority or the public tracker website first published the current bytes. The observations are therefore **reconstructed dated-report snapshots**. They are eligible only for the explicitly retrospective research evaluation, subject to reconciliation, supported definitions and actual cutoff dates. They must not inflate the strictly contemporary as-reported validation count.

For a repeated native report date, the earliest captured source version is retained in the normalized history. Later downloaded versions remain archived. No intermediate snapshot is invented, and missing values remain missing. Explicit published zeroes survive.

Ohio's 2020 tracker specifically combines mail and in-person activity because some counties do not distinguish them, reports a subset of counties, and warns that county source dates can precede the “Last Report” scrape date. Its party-primary history is not party registration; the producer withholds misleading party tables. These limitations remain attached to the observations.

Michigan and Iowa 2020 absentee files can include participation conducted in person. The adapter therefore preserves an all-absentee scope rather than claiming a disjoint mail-only voting method. Accepted, received, requested, rejected and cast are separate metrics. Registration categories are not candidate votes.

## Original authority daily archives already supported

North Carolina's 2018, 2020, 2022 and 2024 dated official reports preserve their printed report dates, S3 object LastModified timestamps, statewide method totals, supported marginal composition, and validated county tables. Later-modified PDF bytes cannot establish contemporary publication on the printed date. The interface therefore exposes reported availability conservatively and reconstructs report-date history separately.

South Carolina's 2022 and 2024 original archived workbooks publish daily early-in-person columns. Their cumulative sums are event-date reconstructions from the retrieved workbook, not proof of what had been published on each historical day. Absentee mail remains separate.

## North Carolina 2016 final-record reconstruction

The original [NCSBE absentee data program](https://www.ncsbe.gov/results-data/absentee-and-provisional-data) supplies the [2016 absentee record ZIP](https://s3.amazonaws.com/dl.ncsbe.gov/ENRS/2016_11_08/absentee_20161108.zip) and a separate [county aggregate](https://s3.amazonaws.com/dl.ncsbe.gov/ENRS/2016_11_08/absentee_counts_county_20161108.csv).

The ZIP is 139,602,621 bytes and expands to 1,109,814,169 bytes. Records are streamed and checked with native identifiers in memory. No voter names, addresses or identifiers enter application observations, generated reports or diagnostic proofs. The actual file failed duplicate-identity validation, so no normalized 2016 trajectory was published.

The native final file has 3,147,210 ACCEPTED records: 2,955,609 ONE-STOP and 191,601 MAIL. These independently reconcile to the original published aggregate. A separate aggregate-only identity audit found 18 repeated ACCEPTED identifiers: 17 analytically conflicting records and one identical record. The connector therefore fails closed and preserves the original evidence; it does not silently choose a row, count records as unique voters, or present a deduplicated total that contradicts the published aggregate. The source could support a **retrospective final-accepted cohort** trajectory only after the duplicate identities and date anomalies receive a defensible resolution. Final acceptance and classification may have been established after the recorded return date. This history is descriptive context and is excluded from the dated-report forecast backtest; it is not presented as knowledge available to an analyst at that past cutoff.

The original [October 20, 2016 announcement](https://www.ncsbe.gov/news/press-releases/2016/10/20/sbe-early-voting-begins-north-carolina) verifies the in-person period October 20–November 5. Out-of-calendar in-person dates and other invalid return dates are withheld from the timeline, counted in explicit diagnostics, and never silently corrected. The full final cohort remains archived. The tested parser calculates county counts only from a complete validated cohort; a calculated zero requires complete enumeration and independent final-total reconciliation. This 2016 source is not currently published as such a trajectory.

## Iowa official historical PDFs and independently verified captures

The original [Iowa results inventory](https://sos.iowa.gov/iowans/election-results-statistics) links concatenated dated county/party/receipt-method reports for 2016, 2018, 2020, 2022 and 2024. Indexed original documents contain 198, 325, 1,289 and 937 pages for 2016, 2018, 2022 and 2024 respectively. They contain repeated native report-date footers, not just an election endpoint.

Ordinary direct source retrieval returned HTTP403 on October 21, 2026 for all five reviewed historical PDFs. This direct-URL collection failure remains visible. Public Internet Archive captures supply a separately identified archived-original path: the collector archives the CDX inventory, verifies the exact original URL and capture timestamp, and requires the PDF payload SHA1 to match the independently recorded capture digest. No access challenge is bypassed and no indexed excerpt is substituted for a full original.

The parser requires complete 99-county status-total reconciliation for county detail, preserves blank cells as missing, and keeps registration/receipt-channel intersections distinct. A valid printed statewide Grand Total survives when county detail fails reconciliation. A receipt channel such as Counter/In-Office or Drop Box does not itself prove voting method. The available 2020 producer bridge remains separately attributed.

For contemporaneous captures, the reported observation becomes available at the verified capture timestamp, even when the printed report date is earlier. A later combined historical PDF supports reconstructed report-date history only. This prevents a 2024 archive capture of a 2022 report from entering a strict 2022 forecast cutoff. Where a footer explicitly states data are from the night before the report date, that period-end lag is preserved.

## Installed Iowa archived-original coverage

The actual five-source archived-original collection published 172,426 observation versions in revisions 257–261. The unit is an absentee administrative count: requested, issued or received ballots. Received is not acceptance and does not identify candidate votes. All-method absentee scope is preserved; receipt channels are separately labeled.

| Cycle | Distinct native report dates | Installed range | Contemporary reported dates | Reconstructed dates | Dates with complete 99-county detail |
|---|---:|---|---:|---:|---|
|2016|18|2016-10-17–2016-11-15|0|18|17 reconstructed|
|2018|22|2018-10-09–2018-11-15|0|22|21 reconstructed|
|2020|40|2020-09-18–2020-11-10|5|40|4 reported;28 reconstructed|
|2022|30|2022-10-03–2022-11-16|2|30|1 reported;15 reconstructed|
|2024|16|2024-10-17–2024-11-06|1|16|1 reported;16 reconstructed|

Reported and reconstructed are separate evidence modes; their counts overlap and must never be added as unique days. A contemporary capture may become available days after the native report date. For example, the independently archived 2022-10-21 capture contains the original October 20 report, describing data from the previous night: 173,905 requested, 173,147 issued and 11,206 received. Its availability begins at the capture timestamp, not October 19 or 20.

A full-source digest match authenticates the retrieved archived payload against the capture inventory; it does not validate every value or erase the authority's later corrections. The parser separately checks native footer dates, county identifiers, complete status columns, statewide reconciliation, and marginal categories. Incomplete county rows preserve missing cells. Valid printed statewide totals remain usable while geographic detail is withheld.

Original captures that contain malformed PDF objects or repeated inconsistent report blocks remain archived and are omitted when they fail validation. Later source updates are not inserted into an earlier captured snapshot. Exact hashes, timestamps, values and per-date reconciliation are recorded in `.local/ev-history/iowa-archived-coverage-proof.json`; acquisition outcomes are in `iowa-archived-collection-proof.json`.

## Ohio original dated county surveys

The final acquisition validated five original-authority sources through revision 266. The 2022 sources preserve their existing native definitions and dates. All workbook bytes now match independently recorded public Internet Archive CDX SHA1 digests; source capture times do not come from filenames or retrieval dates.

| Cycle | Observation date | Native date evidence | Early in-person | Mail returns | Combined returned/submitted | Evidence mode |
|---|---|---|---:|---:|---:|---|
|2016|October 28|Original October 31 release explicitly says “as of Friday, October 28,2016”|288,895|766,017|1,054,912|Reconstructed only; post-election captures|
|2018|November 5|Original November 5 release explicitly identifies close of in-person absentee voting|429,521|884,323|1,313,844|Reconstructed only; republished official 2022 county columns|
|2022|October 21|October 25 corrected release explicitly dates Week 2 totals October 21|135,889|Unavailable|Unavailable|Reported and reconstructed; availability begins October 26 capture|
|2022|November 1|Dated original release; exact survey reference instant unavailable|265,062|552,582|817,644|Reconstructed history;2025 capture cannot enter strict 2022 cutoff|
|2022|November 7|Original release explicitly dates survey at 2 p.m.|549,771|842,996|1,392,767|Reconstructed history;2025 capture cannot enter strict 2022 cutoff|

Each row has exactly 88 canonically joined counties, with the native parsed columns independently summing to their statewide totals. In-person counts and derived mail remainders are disjoint; mail returns are not accepted votes or candidate votes. These sparse surveys are observations, not an interpolated daily timeline.

### 2016 date and component proof

The [original October 31 release](https://web.archive.org/web/20161118165952id_/http://www.sos.state.oh.us/sos/mediaCenter/2016/2016-10-31.aspx) explicitly dates its 1,594,220 requests and 1,054,912 cast to October 28. It links the [original county workbook](https://web.archive.org/web/20161225111833id_/http://www.sos.state.oh.us/sos/upload/news/20161031.xlsx). The workbook separates domestic and military/overseas mail requests, mail returns and in-person participation. Every native county component and all eight statewide columns reconcile. In-person includes 30 military/overseas ballots; those cannot also be added to mail returns. Both public captures occurred after Election Day, so this is retrospective dated-report evidence only.

The October 31 filename is not the observation date. The original release also says ordinary absentee voting began October 12 and military/overseas voting September 24; these are calendar facts, not a count of local voting opportunities. The separate November 7 workbook lead remains uncollected because its public capture did not return usable bytes during this audit. Final absentee supplements remain endpoint references and are never turned into pre-election trajectories.

### 2018 republished endpoint proof

The [original November 5 release](https://web.archive.org/web/20181116121832id_/https://www.sos.state.oh.us/media-center/press-releases/2018/2018-11-05a/) explicitly identifies the close-of-in-person endpoint and publishes 1,491,762 combined requests, 429,521 in-person ballots and 1,313,844 combined cast. All three exactly match the 2018 comparison columns of the [official 2022 workbook](https://web.archive.org/web/20250306112939id_/https://www.ohiosos.gov/globalassets/media-center/news/2022/2022-11-07/onedayoutev2022.xlsx). The 88 county cells sum exactly to all three quantities. The original 2018 county-file link has no verified public archive capture in the reviewed inventory, so the application discloses the 2022 republication and 2025 workbook capture rather than claiming contemporary 2018 county availability.

Both the original dating release and later workbook are immutable source snapshots. Each normalized observation carries both original URLs, their archive capture times, the dating release SHA256, the workbook hash/vintage and native column indices. The original release bytes and expected totals must match the reviewed evidence before publication. Any other comparison columns without independently established dates remain withheld.

Acquisition and source proofs are in `.local/ev-history/oh2016-2018-final-collection-proof.json`, `oh2016-release-probe.json`, `oh2016-2018-native-probe.json` and `oh-final-discovery.json`. No primary-party composition or race breakdown is inferred for Ohio from these county surveys.

## Reproduction and operation

List the reviewed program without collecting:

```sh
.venv/bin/python scripts/collect_ev_history.py
```

Collect selected registered sources through the standard run lock, bounded fetcher, immutable archive and append-only publication:

```sh
.venv/bin/python scripts/collect_ev_history.py --collect \
  --source-ids electproject-dated-2020-nc electproject-dated-2020-ga \
  --output .local/ev-history/collection-proof.json
```

Use `--offline` with `--collect` to reparse already archived responses. Exact source lists are in `config/ev_historical_sources.json`; the command defaults to inventory-only. Live verification proofs are in `.local/ev-history/collection-proof.json`, `coverage-proof.json`, `iowa-archived-coverage-proof.json`, `iowa-archived-collection-proof.json`, and `nc2016-collection-proof.json`.

Strict contemporary validation, retrospective dated-report validation, final-cohort descriptive history, and historical-reference-only calls must remain separate in dashboards, model manifests, confidence labels and exported reports. More source observations do not by themselves establish forecast accuracy.
