# Observatory election atlas interface

A local React/TypeScript atlas connected to the FastAPI research service. Every displayed number comes from collected evidence or explicitly labeled scenario assumptions. No external AI service is required.

## Run and verify

Use Node 22+ and pnpm. From this directory:

```sh
pnpm install --frozen-lockfile
pnpm dev
pnpm typecheck
pnpm test
pnpm build
```

The development interface is at `http://127.0.0.1:5173`; `/api` proxies to the local service on port 8776. The backend serves the production build. The lockfile pins dependencies. Generate OpenAPI types with the root project script rather than editing `src/generated/api.ts`.

## Research destinations

- **Today:** a fifty-state national map, tile alternative, current participation totals with explicit inclusion scope, historical results, state comparison table, and current study coverage.
- **Atlas:** historical candidate/option results, named-option shares, available swing, current participation, and Census population context. Quantitative maps have numeric legends and exact color intervals. Maps, geographic tables, and comparisons share selections.
- **States:** substantial scrollable dossiers covering participation trajectories, actual reporting changes, method mix, reporting calendars, geographic contributions, per-place series, published composition, historical context, polls, Census context, and source evidence.
- **Elections:** searchable verified dataset and contest catalogs. Offices and years come from actual catalog availability; local, judicial, legislative and ballot-measure records appear where collected. Candidate and ballot-option names open contest-specific identity inspectors.
- **Research:** historical playback, original polling and sensitivity, explicit scenarios, gated forecasts, notebooks, sourced reports, and collection health.

Existing `/api/v1` URLs and saved investigations remain supported. Small visualization choices are stored as `ui_*` URL values; private notes stay in local research objects. Pinned views retain revision and chronology. Secondary evidence reads use the current workspace revision, and a background download offers an updated revision instead of silently replacing an active investigation.

## Cartography and interaction

`mapSpec.ts` is the shared rendering contract: value, unit, domain, thresholds, colors, missing-data treatment, and square-root symbol radius. MapLibre and SVG use the same specification. Blue/red is reserved for explicit Democratic/Republican quantities; ordinary activity uses teal, historical cycles use persistent categorical colors, and nonpartisan change uses teal/orange.

Canonical IDs join observations to boundaries; source names are preserved in evidence records. Unmatched or incompatible geographies remain inspectable. Native precinct/district results do not get painted onto county boundaries. Offscreen MapLibre instances are removed; synchronized maps share camera changes. City orientation labels come from the locally archived Census Gazetteer. Required map assets and Source Sans 3/Source Serif 4 fonts are served locally; font licenses are in `public/licenses`.

The editorial light theme is the redesigned default, with a complete navy theme and comfortable/compact density settings. Mobile has a navy brand header, compact scope controls, advanced-options drawer, and persistent five-destination navigation. Charts have tables and plain-language reading guides. Dialogs support Escape, focus trapping, and focus restoration. Reduced-motion preferences are honored.

## Data limitations

Available capabilities depend on evidence. Unsupported party/demographic intersections, geographic harmonizations, denominators, candidate probabilities, or election-system treatments are explained instead of fabricated. Historical candidate/option votes are distinct from ballots and people. Population context includes nonvoters. County source totals may differ from the separate statewide compilation; reconciliation warnings appear prominently.

See `qa/atlas/FIDELITY.md` for the design comparison. Backend tests own analytical/source correctness; `pnpm test` exercises critical renderer-independent map semantics.
