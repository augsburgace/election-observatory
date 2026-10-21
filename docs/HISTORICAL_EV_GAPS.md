# Historical early-vote gap audit — October 21, 2026

## Ohio original-authority expansion

Eight additional source configurations are ready for the ordinary append-only collector in `config/ohio_historical_sources.json`. A standalone acquisition audit uses the same bounded downloader and connector without opening or writing the application database:

```sh
.venv/bin/python scripts/audit_ohio_history.py --source-id oh-official-survey-2016-11-07
```

Every workbook's archived payload matches its independently recorded Internet Archive CDX SHA1. Every native numeric column reconciles exactly between the statewide row and all 88 canonically identified counties. Supporting dated releases are separately archived and SHA256 pinned. Several replay HTML responses differ from the CDX payload digest: those supporting HTML documents are explicitly identified as reviewed replay bytes, not represented as CDX-authenticated raw payloads. The actual workbook payload authentication remains independent.

| Cycle | Release | Observation period | Native measures | Evidence availability |
|---|---|---|---|---|
|2016|November 7|November 7 release; exact survey instant unspecified|Requests, early in-person, mail returns, combined participation|Retrospective; supporting release December 2016, workbook February 2017|
|2020|September 15|September 11 explicitly stated|UOCAVA and non-UOCAVA applications|Retrospective; workbook 2025|
|2020|September 22|September 18 explicitly stated|UOCAVA and non-UOCAVA applications|Retrospective; workbook 2025|
|2020|September 29|September 25 explicitly stated|UOCAVA and non-UOCAVA applications|Retrospective; workbook 2025|
|2020|October 6|October 2 explicitly stated|UOCAVA and non-UOCAVA applications|Retrospective; workbook 2025|
|2020|October 13|Dated release; exact survey instant unspecified|Applications and early in-person|Retrospective; workbook 2025|
|2020|October 27|Dated release; exact survey instant unspecified|Applications, early in-person, mail returns, combined participation|Contemporary capture available November 1, after the October 27 release|
|2020|November 2|Through 2 p.m. November 2 explicitly stated|Applications, early in-person, mail returns, combined participation|Retrospective; workbook captured November 27|

The 2016 November 7 original has 1,798,277 combined ballots, including 661,549 in-person and 1,136,728 mail returns. It retains the native military/overseas components; the 59 military/overseas in-person ballots are included once. The 2020 November 2 original has 3,411,463 combined ballots, including 1,339,764 in-person and 2,071,699 mail returns. These are administrative returned/submitted quantities, not accepted ballots, counted candidate votes or final turnout.

The 2020 schema differs from 2016/2022: application columns identify UOCAVA/non-UOCAVA status, not a defensible request-method split. They remain an all-method native application quantity. No mail-request remainder is fabricated. Four application-only reports do not acquire zero in-person or returned totals. In-person alone on October 13 does not establish a combined turnout count.

Reported availability starts no earlier than **both** supporting release and workbook captures. An October 27 report whose first verified workbook and dating evidence are captured November 1 cannot enter an October 27 as-reported backtest. Sparse reports are not interpolated into daily observations.

Real-source parse proofs: `.local/ev-gap-source/ohio-validated-expansion.json`; acquired payload and CDX inventory proofs remain alongside it. Publication into the live database is a separate coordinated collector operation.

## Ohio 2024 and current record-level gap

The original [Ohio dashboard](https://data.ohiosos.gov/portal/election-dashboards/absentee) states that a reconstructed November 2024 voter-level requests/returns file is available, and that demographic reporting before November 2024 was incomplete. The current publicly linked export is [Absentee_Request_Report.txt](https://publicfiles.ohiosos.gov/free/absentee_public_export/Absentee_Request_Report.txt). Ordinary direct HTTP requests to both currently return a 403 maintenance page in this environment. That HTML is never parsed as voting data. No access challenge was solved or bypassed.

The public November 2024 archived dashboard page verifies its original PowerBI report but supplies no record download link. The reviewed public CDX inventory has no capture of the current public-file path or new dashboard route. A record-level 2024 reconstruction therefore remains uncollected. It must not be described as as-reported history; primary-history labels and precinct mappings require their own dated classification and geography checks. Same-day issuance and return does not itself establish an observed in-person voting method.

No Ohio party registration, race, religion or candidate-choice breakdown is inferred from the county surveys. The separate original public export may eventually support labeled primary-participation categories; it does not establish party registration or how an individual voted.

## Original-producer 2024 bridge discovery

The University of Florida Election Lab's original public tracker JavaScript identifies [US.csv](https://election.lab.ufl.edu/data-downloads/earlyvote/2024/US.csv). Ordinary retrieval succeeds. The independently archived public CDX inventory contains 13 distinct payload captures, including October 2, October 8 and November 3–5. Ohio's final preserved row identifies November 4 and reports 995,482 mail returns plus 1,536,778 in-person ballots, equaling 2,532,260 combined early ballots. The published source is the Ohio dashboard. This is attributed academic compilation, with its original metric notes and archive availability retained; it is not a newly recovered Ohio original record file.

The producer's public GitHub account exposes its 2020 and 2026-primary repositories, but no equivalent 2024 daily-history repository was found. Public CSV capture inventories should be used rather than invented repository URLs or authenticated/subscription archive access.

### Installed bridge adapter and actual acquisition audit

`backend/observatory/connectors/uf_history.py` and `config/ev_gap_sources.json` implement the reviewed 2024 bridge. The standalone standard-fetcher audit succeeded with 14 archived documents (the capture inventory plus all 13 digest-verified CSV payloads), producing 6,792 normalized observation versions across 212 distinct state/report-date pairs in 47 states. Reported and reconstructed versions are separate analytical modes and must not be added together. There are 46 states with a positive combined-participation measure and a separate native in-person-only state; absence of Alabama, Montana and New Hampshire is a documented source gap. This is statewide evidence, with no county geometry or precinct observations.

```sh
.venv/bin/python scripts/audit_ohio_history.py \
  --config config/ev_gap_sources.json \
  --work-dir .local/ev-gap-source/uf-audit
```

The proof is `.local/ev-gap-source/uf-audit/proof.json`. All database publication remains a separate coordinated operation. The audit withheld 34 wrong-cycle template, future-date or unsupported-jurisdiction rows. For example, the July 2024 template still contained 2022 North Carolina counts. Zero placeholders never become measured zero participation or invented voting modes. Texas request proxies are omitted; Iowa and Michigan native absentee receipts retain all-absentee scope rather than being relabeled mail only.

The earliest positive validated producer snapshot for each state/report date is normalized. Another 183 later same-date source versions remain archived and listed for review; they are not silently substituted into earlier availability. The Florida November 5 combined total failed its separate method reconciliation, so that combined measure is withheld while independently published method totals remain available with the discrepancy recorded.

For Ohio, the earliest original-producer snapshot has:

| Native report date | Combined | In-person | Mail returns | First verified capture |
|---|---:|---:|---:|---|
|November 2, 2024|2,353,487|1,403,075|950,412|November 3 at 05:51:04 UTC|
|November 4, 2024|2,532,260|1,536,778|995,482|November 5 at 21:24:34 UTC|

The second row cannot enter a November 4 as-reported forecast simply because its native date says November 4. No public capture within the reviewed inventory fills the October 9–November 2 gap. Uncollected daily Ohio original records and county/precinct party/method histories remain explicit gaps.

## Optional external-evidence ingestion safeguards

`backend/tests/test_external_context.py` exercises original co/efficient response completeness and publication chronology, RCP public browser-table capture identity and chronology, duplicated studies, and prediction-market identity and units. These unit fixtures are explicitly artificial and are never installed as election data.

RCP table order does not establish fieldwork order: rows are dated independently within the named contest cycle, and future fieldwork is withheld rather than moved into an invented prior year. Exact duplicate studies are counted once; conflicting duplicates fail closed. The secondary summary keeps the displayed candidate shares, without fabricating undecideds or relabeling incomplete metadata as an original questionnaire.

Only active, open, named Senate contracts survive market parsing. Inactive/null-price placeholders, generic Person/Candidate letters, and “Other” contracts are omitted. Both Yes and No prices must be finite and within zero to one. Yes is located by its outcome label, not array position. A quoted price of 0.6 is stored as 60 percent of a one-dollar contract payout; it is not stored as a vote share or a calibrated probability. Named contracts whose party is not explicit retain an unknown party, including Alaska names without explicit party labels. Duplicate contract identities are counted once, and conflicting identities fail closed.
