# Atlas verification — October 21, 2026

The production frontend and local FastAPI server were verified against dataset revision **99**. This records observed behavior and practical limits; it is not a claim that every proposed research feature or every public election dataset is complete.

## Evidence and functional checks

- All 50 states return positive 2024 statewide presidential evidence, attributed source references, historical cycle records, and Census resident context. Deep all-office archives are installed for TX/NC/ME/AK in 2024, TX/NC in 2022, and AK in 2018. Other verified state archives are available on demand.
- The final store contains 1,698,270 result versions, 16,205 contests, 48,556 ballot options, 9,579 resident-context estimates, and 221,838 participation versions. These are database records, not a count of unique voters or complete elections.
- Current reported participation is available to some degree in 14 states. Every state has substantive historical/context research; the application does not substitute historical candidate returns for current voting.
- All 3,112 collected 2024 county identifiers join the local 2024 Census boundaries. Missing and historically incompatible geography remains inspectable. Alaska native reporting districts and Maine municipalities remain distinct from county polygons.
- Shared services enforce date windows, cutoffs, revision pins, voting definitions, individually labeled place trajectories, and compatible historical comparisons. Maine request-date reconstruction remains quarantined under a new validation revision, with originals retained.
- Actual Arizona participation loading completed through a durable background job. Job progress, failures, cached evidence, and producer-access restrictions remain explicit.
- Texas's 38 collected 2024 House contests were opened through the catalog. District 014 expands into election/office/district metadata and its contest-specific HART/DEM and WEBER/REP identities. Names are not automatically merged across unrelated elections.
- Candidate and place inspectors, saved investigations, source records, map selections, and the actual historical tables were exercised. New Alaska historical investigations default to valid statewide evidence; an explicit county request retains its unavailable-coverage explanation.
- CSV, JSON, HTML, PDF, and ZIP result/context exports returned successfully. Research ZIPs regenerated from their query, revision, source hashes, and presentation descriptors; matching results and hashes were verified. A missing Census income estimate remains unavailable rather than becoming $0.

Machine-readable local proofs are retained in `.local/atlas/all-50-state-proof.json`, `final-api-proof.json`, `final-export-proof.json`, and `final-r99-restore-proof.json`.

## Visual and interaction checks

The running application was inspected in the Codex in-app browser at actual CSS viewport widths **390, 768, 1440, and 1920 pixels**. Existing browser zoom was preserved; emulation dimensions were adjusted to obtain the intended CSS widths.

| View | Observed result | Screenshot |
|---|---|---|
| Mobile 390 × 844 | Compact place/election controls, navy identity header, visible figures and reconciliation note, map near the top, bottom navigation, no page-width overflow | `frontend/qa/atlas/mobile-390.png` |
| Tablet 768 × 1024 | National map and research controls remain readable; collapsed navigation has accessible names; no page-width overflow | `frontend/qa/atlas/tablet-768.png` |
| Desktop 1440 × 1000 | Map and selected-place detail sit together; exact totals, coverage, semantic result colors, source warnings, and research controls remain visible | `frontend/qa/atlas/desktop-1440.png` |
| Navy theme 1440 × 1000 | Panels, map canvas, borders, text, controls, and quantitative legends follow the navy theme | `frontend/qa/atlas/dark-1440.png` |
| Wide 1920 × 1080 | Research canvas expands, retaining useful map/detail proportions and historical chart context | `frontend/qa/atlas/wide-1920.png` |

Map gestures were checked on mobile: ordinary page scrolling over the cooperative map did not change the camera or trap scrolling. Explicit saved cameras remain preserved; reset fits the selected geography. Quantitative legends expose their numeric thresholds, units, and boundary/source context. The SVG and MapLibre renderers consume the same map specification; circle area is proportional to volume.

The final pass found and corrected responsive visibility and pending-theme map lifecycle issues. Visibility now rechecks actual element bounds on viewport changes, and theme changes update existing paints even while source work is pending. The rebuilt app retained one live map and all seven local city labels through the desktop → navy → light → mobile sequence without a reload; the light map background was visually confirmed. Scrolling beyond the map released its WebGL context (zero canvases), and returning to the top restored it (one canvas).

Keyboard focus was visible on the research controls. Reduced-motion emulation yielded static main-panel animation (`0s`) and retained keyboard use. The final browser pass recorded no console errors. These checks do not establish formal WCAG 2.2 AA conformance or exhaustive assistive-technology coverage; cross-chart keyboard highlighting remains a documented area for further work.

The desktop/mobile planning references were compared with the real application. Intentional differences and source-driven restrictions are recorded in `frontend/qa/atlas/FIDELITY.md`.

## Export appearance

The actual Texas result report (11 pages) and Census context report (3 pages) were rendered with Poppler. First-page images were visually inspected for clipping, overlap, legibility, and glyph problems. Result figures are vector candidate/option bars and historical share charts, with source appendices and revision/page footers. Context retains estimate periods, units, missing values, and published uncertainty. A fully rearrangeable historical figure composer remains additional product work.

QA exports are in `output/atlas/`; they are aggregate research outputs. Private notebook text and raw personal records are not automatically packaged.

## Automated verification

- **138 backend tests passed.** Coverage includes revision chronology, source corrections, geographic aliases/vintages, missing and suppressed values, result reconciliation, ranked-choice/multi-seat limits, method overlap, dated denominators, source outages, polling eligibility, scenarios, export tampering, and reproduction.
- **8 frontend regression tests passed**, plus TypeScript checking and the production Vite build.
- Ruff passed for backend, scripts, and migrations.
- An empty database migrated to `0002_election_atlas` without invented seed observations or results. Frontend contracts were generated from OpenAPI.

The backend test run emits one nonblocking Starlette/httpx deprecation warning. No failed check is hidden behind these totals.

## Performance spot checks

Actual local HTTP responses on this Mac, with installed source evidence and no commercial map service:

| Query | First read | Repeated read | Compressed response |
|---|---:|---:|---:|
| All-state catalog | 123 ms | 3 ms | 8.6 KB |
| National statewide 2024 presidential results | 86 ms | 79 ms | 71 KB |
| Texas 254-county results | 98 ms | 76 ms | 105 KB |
| North Carolina detailed participation analytics | 2,612 ms | 182 ms | 283 KB |
| Texas result analysis | 50 ms | 48 ms | 41 KB |

A Texas precinct request returned its bounded first 200 areas in 173 ms, with 9,712 total areas disclosed through pagination. The previously slow pinned geography route returned in 207 ms after the query fix. These are service measurements, not a promise that every browser interaction finishes within 500 ms. Cached ordinary requests meet the target in the tested cases; initial deep downloads and cold detailed analyses have visible loading states. No national precinct geometry is loaded on startup.

## Backup and recovery

The final revision-99 backup was restored into a separate directory and independently checked: **338 unique archive hashes, 388 snapshot paths, SQLite integrity, migration head, and all-state result/context counts passed**. The original North Carolina revision-29 saved investigation still returns **733,299**, including its original source hash. Earlier revision-97 recovery artifacts remain retained. Exact paths and checksums are in `docs/ATLAS_RECOVERY.md`.

## Release qualifications

This is a useful working local atlas upgrade. Source-dependent precinct cartography, boundary harmonization, exhaustive local/primary/runoff coverage, every proposed visualization, a fully flexible historical figure composer, and published validated forecasts are not all complete. See `docs/goals/atlas-upgrade/ACCEPTANCE.md` for the explicit remaining work. No public deployment was performed.
