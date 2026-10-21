# Implementation status

October 21, 2026. The local 50-state election-atlas upgrade is working and backed up at **revision 99**. The full long-term research vision still has evidence-dependent and product-depth work; unavailable evidence is not replaced with invented election numbers.

## Working release

- **Nationwide evidence:** all 50 states have substantive historical election returns and Census resident context. The frozen store contains **1,698,270 historical result versions**, **16,205 contests**, **48,556 ballot options**, **9,579 context estimates**, and **221,838 participation observation versions**. These are stored records/versions, not unique voters or complete election inventories.
- **Research experience:** bright editorial canvas, navy navigation and alternate navy theme, locally bundled fonts, semantic colors, shared legends, geographic and tile maps, dense accessible tables, long state dossiers, original-source inspectors, universal search, and durable place/contest/ballot identities.
- **Detailed analysis:** actual-observation trajectories and playback, historical alignment safeguards, individual-place comparisons, contribution changes, concentration, calendars, method/composition charts, candidate/response distributions, named-option share maps, and resident-context charts with estimate periods and uncertainty.
- **Evidence correctness:** canonical Census joins preserve legacy selections; native reporting areas retain their grain; proportional-symbol area represents volume. Maine request chronology is quarantined through a retained quality revision. Missing values, source corrections, mismatched boundaries, unknown ranked-choice rounds, and cross-source disagreements remain explicit.
- **On-demand depth:** verified state historical archives queue in the background with progress and failure history. Precinct results use bounded pages, and place dossiers expose historical paging. Native precinct data is not painted onto unverified county polygons. Current participation bridges activate by state where usable evidence exists.
- **Persistent workflows:** pinned/latest saved views, notes/bookmarks/scenarios, auditable corrections, deterministic briefs, original polling with population/question/sample separation, scenario sensitivity, and source-health monitoring remain available.
- **Exports and recovery:** CSV/JSON/HTML/PDF/ZIP, chart/map image exports, historical vector figures, presentation/source/build manifests, hash-verified CLI regeneration, and full database/archive restoration work. The original saved North Carolina revision-29 investigation still reopens at **733,299**.

The frozen release passed **138 backend tests**, **8 frontend tests**, and TypeScript/production-build verification. The root browser QA record separately covers the requested viewports and themes. WCAG 2.2 AA is a target, not a formal certification.

## Real remaining gaps

| Area | Remaining work or evidence condition |
|---|---|
| Current voting coverage | Uneven state definitions, dates, geography and source access; additional direct official connectors, original polling-release discovery, registration/calendar onboarding, and official current candidate verification are still needed. All-state historical coverage does not mean all-state daily early-voting coverage. |
| Precinct and historical maps | Verified precinct boundaries, native geographic crosswalks, boundary-harmonized county/precinct swing, and more synchronized historical map comparisons. |
| Full research graphic catalog | Additional bivariate maps, demographic change/dumbbell/cohort graphics, and supported joint distributions. Features requiring absent evidence remain unavailable. |
| Reports and interactions | Fully rearrangeable historical map/chart report composition, more specialized templates, and complete keyboard-linked brushing/focus across every view. Figure-rich historical exports already work. |
| Forecasting | Timestamp-safe historical evaluation inputs, empirically validated live forecasts, specialist RCV/runoff treatment, and complete-universe joint chamber validation. Model/backtest tools and explicit scenarios work; live probabilities remain gated. |
| Election completion | Broader certification tracking, final result reconciliation, and a frozen post-election archive/review workflow. |
| Public release | Hosting, publication rights, and formal public-launch/accessibility review remain a separate future decision. No public deployment was performed. |

See [atlas acceptance](goals/atlas-upgrade/ACCEPTANCE.md), [visual and functional verification](ATLAS_VERIFICATION.md), [geographic/source validation](ATLAS_VALIDATION.md), [final recovery proof](ATLAS_RECOVERY.md), [installed coverage](ATLAS_COVERAGE.md), and [source limitations](ATLAS_SOURCES.md). Coverage documents carry explicit generation revisions; later collection can deepen the installed store.
