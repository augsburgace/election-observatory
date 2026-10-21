# Battleground Senate Observatory implementation contract

**Intent:** Implement the expanded user-approved election research plan with a navy research-desk interface, local storage, real source collection, linked maps/charts, historical comparisons, polling, scenarios, saved research, reports, and honest forecast availability.
**Starting point:** Empty Git repository. Current implementation and evidence are recorded in `docs/IMPLEMENTATION_STATUS.md`, `docs/COVERAGE.md`, and `docs/VERIFICATION.md`.
**Truth owner:** Original source snapshots; validated normalized observations retain source-native definitions and chronology. Sources have a metric-specific hierarchy.
**Boundary:** Typed connector batches -> immutable source archive + revisioned SQLite observations -> shared analytical queries -> API, UI, briefs, and exports.
**Cutover:** New application; no existing data or implementation is displaced.
**Acceptance evidence:** Real source -> persisted snapshot -> linked UI -> source inspector -> saved view -> reproducible export; desktop/mobile/light QA, chronology and aggregation tests, backup restoration.
**Kill criteria:** No duplicate truth/query/filter/export system; no generated election facts, fabricated history, or unsupported demographic or winner inference.
**Forbidden moves:** External transmission of private notes, automatic paid services, public deployment, raw voter records in Git/UI/exports, bypassing access gates, claims of calibrated forecasts without validation.

## Work board

1. Shared Python contracts, revisioned database, registry, archive, source collection CLI. Root integrates; connector work parallel after contracts are fixed.
2. Frontend design system and complete navigation; frontend agent owns frontend only. API contract is coordinated below.
3. Real-source connectors and archived data; source agent owns connectors and source discovery artifacts only.
4. Analytical/scenario/forecast primitives and important tests; analysis agent owns these modules and tests only.
5. Root integrates API, persistence, research objects, exports, source worker, operations scripts and documentation.
6. Collect feasible source data, verify against original records, fix defects. All 14 watchlist states stay visible with honest coverage.
7. Run unit/API/export/recovery checks and browser functional + visual QA. Fix important review findings.

## Scope and source standards

Registry: all 35 scheduled 2026 Senate elections; initial detailed states AK FL GA IA KS ME MI MN NE NH NC OH SC TX. Candidates require official ballot or original poll attribution. Default historical context 2022/2018, with 2024/2020 separately labeled.

Preserve requested/issued/received/accepted/rejected/counted distinctions, source geography and boundaries, unknown versus zero, registered denominator dates, and publication/observation/event dates. Reconstructed final-file histories never become as-reported histories.

## Shared implementation interfaces

`domain.py` owns Observation, Poll, ParsedBatch, FetchedDocument, ResearchQuery. Connectors implement `collect(source: dict, fetcher) -> ParsedBatch`; fetcher provides `fetch(url) -> FetchedDocument`, `documents`, and immutable local files. Exceptions are captured as source failures without replacing valid data.

Frontend API: `/api/v1/bootstrap`, `/api/v1/workspace` (query parameters), `/api/v1/geography/{state}`, `/api/v1/sources`, `/api/v1/evidence/{observation_id}`, `/api/v1/research` CRUD, `/api/v1/scenarios`, `/api/v1/forecasts`, `/api/v1/jobs`, `/api/v1/refresh`, `/api/v1/exports`. Full contract tracked in `docs/API.md` as implemented. Every analytical envelope contains revision, query, coverage, warnings, and provenance.

## Completion tracking

Forecast release and conditional modules depend on real evidence. Record source accessibility and empirical validation gaps in the coverage report, while delivering functioning tools and model/backtest interfaces. Do not label unavailable capabilities complete.
