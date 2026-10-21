# Observatory · Election Atlas

A local 50-state election research atlas, retaining the 2026 Senate watchlist and expanding into verified federal, state, judicial, local, and ballot-measure records. Real archived evidence drives maps, charts, historical comparisons, original polling, deterministic briefs, scenarios, notebooks, and reproducible exports. Bright editorial and navy themes, compact density, mobile navigation, and accessible table alternatives are included. Available offices and years follow each source's actual coverage.

**Web application:** [Battleground Senate Observatory](https://battleground-senate-observatory.pages.dev). Cloudflare Pages hosts the public aggregate edition on its free plan; the source repository remains private. The existing Mac checks sources and publishes validated updates every two hours while awake and online. The website keeps its last successful release when the Mac is asleep or offline.

**Cloud update migration:** [the public source distribution](https://github.com/augsburgace/election-observatory) adds free GitHub-hosted collection and [GitHub Pages](https://augsburgace.github.io/election-observatory/). Its first complete cloud run must pass before the existing Mac publisher is retired. The private development repository and its old history stay private; only the reviewed source snapshot and sanitized aggregate checkpoints are public. See [cloud updates and recovery](docs/CLOUD_UPDATES.md).

**Full local application:** [http://127.0.0.1:8776](http://127.0.0.1:8776), while the server is running. The local edition retains arbitrary evidence queries, source collection, original archives and private research. The web edition serves explicitly published investigations, browser-local notes, maps, polling research and editable reports. It never substitutes a different cutoff or filter for an unavailable query. See [web operation, publication and rollback](docs/FREE_WEB_HOSTING.md).

## Install and run

Requirements: Python 3.11 or newer, Node.js 22.12 or newer, and pnpm 10 or newer. On this Mac Python 3.14 and Node 24 were verified.

```sh
./scripts/setup.sh
./scripts/collect.sh
./scripts/start.sh
```

Setup installs the Python package in `.venv`, uses the committed frontend lockfile, builds the frontend, initializes SQLite, downloads local official Census boundary files, and installs the nationwide historical reference core. Current participation collection remains separate. A failed source retains already validated evidence and does not prevent startup. First collection can take several minutes. Accessing original sources requires internet; already collected evidence and locally served boundaries remain usable offline.

```sh
# Include historical source archives (longer first run).
.venv/bin/observatory collect --include-historical

# Collect one state or connector.
.venv/bin/observatory collect --state NC
.venv/bin/observatory collect --source nc-counts-2026

# Reparse original bytes already stored locally, without a network request.
.venv/bin/observatory collect --offline --include-historical

# Inspect attribution, failures, and data dates.
.venv/bin/observatory coverage
```

Participation source IDs are listed in `config/sources.json` and the runtime source inventory; use that inventory when selecting an individual source. Set `OBSERVATORY_DATA_DIR` to choose a different local storage directory. Set `OBSERVATORY_PORT` before running `start.sh` if port 8776 is occupied. The local launcher binds loopback.

### Update the public website

The cloud distribution uses **Actions → Public cloud updates** in `augsburgace/election-observatory`. Standard public runners collect sources and publish independently of the Mac. The workflow preserves exact rollback artifacts, checks the actual hosted research reader, and uses short-lived GitHub credentials. No Cloudflare login is copied into GitHub. See [cloud operating instructions](docs/CLOUD_UPDATES.md).

The following commands describe the existing Mac publisher retained during the migration:

The installed publisher uses the existing Cloudflare sign-in and the approved Observatory Pages project. No paid host, public source repository or external AI API is required.

```sh
# Collect due sources, build and verify all-state public data, then publish.
.venv/bin/python scripts/update_web.py

# Build an unpublished evidence batch without changing the hosted website.
.venv/bin/python scripts/update_web.py --skip-collect --build-only

# Install the combined two-hour collector/publisher after a verified first release.
.venv/bin/python scripts/install_schedule.py --publish-web --defer-first-run
```

Publication configuration and status remain outside Git in the application-data directory as `web-publishing.json` and `web-status.json`. The updater snapshots SQLite, validates the static reader across all 50 states, enforces free-host limits and verifies the deployed revision and hosted research workflows. Failed builds retain the previous release; failed post-deployment verification triggers a checked rollback. An already-published revision returns `unchanged`; application-only changes need a new validated evidence batch before this automatic publisher republishes them. Source collection and publication share one existing launchd schedule rather than duplicate timers. [Operating commands and recovery](docs/FREE_WEB_HOSTING.md#operate-the-installed-publisher) explain status, logs, sign-in and rollback.


Install or expand historical evidence from the command line:

```sh
.venv/bin/observatory atlas --core
.venv/bin/observatory atlas --dataset medsl_2024 --state TX
.venv/bin/observatory atlas --dataset medsl_2022 --state NC
.venv/bin/observatory atlas --dataset acs2024_median_age

# Verify and regenerate a pinned results package.
.venv/bin/observatory reproduce atlas-TX-2024-r87.zip --format html
```

The interface also queues these downloads and shows durable job progress. State and local archives stay cached after download; raw precinct geometry is never fetched nationally at startup. Sources that require a guestbook remain visibly gated. Configured current-participation sources are checked on their own cadences and retain their original authority lineage and source-license caveats.

## Use the research desk

1. Start on **Today**. Explore the 50-state map, historical results, state comparison table and current voting developments. Choose **Place → Election → Question**; move chronology, metrics and denominators into **Research options** when needed.
2. Open **States** for a long research dossier: map, current participation, trajectories, methods, composition, historical contest context, polling, calendars and original evidence. Historical final results remain labeled separately from early voting.
3. In **Atlas**, explore color-coded historical candidate returns or current participation. Select reporting areas, open place profiles and compare individually labeled trajectories. Circle area represents counts; rates require suitable denominators. Every renderer shares values, palette and bins. Use **Elections** to search actual collected contests and ballot identities, and download deeper state evidence in the background.
4. Under **Research → History**, step or play through actual observations. Reported and reconstructed histories are distinct. Unsupported voting-opportunity alignments, incompatible geography, or unavailable historical snapshots remain visibly unavailable.
5. In **Polls**, review original questions, producer, fieldwork, population, sample disclosures, and complete response shares. Window, population, and sponsorship controls use the canonical backend eligibility rules. A descriptive average requires three independent eligible producers.
6. In **Scenarios**, set turnout, method composition, support, and undecided assumptions. Values are conditional calculations, not predictions. Save named alternatives and inspect the sensitivity plots.
7. Use **Notebook** to save a pinned view, bookmark evidence, and attach notes. Reopen the original revision or apply its configuration to latest evidence. Background changes offer an update rather than moving an active investigation.
8. In **Forecasts**, inspect an EV-led Senate research call, its county contributors, published composition, historical reference and sensitivity range. EV-informed calls and historical-only references are labeled separately. Use **Build this Senate report** to capture the exact inputs. These experimental calls have no established EV-model predictive accuracy.
9. Use **Reports** to choose and reorder sections, add captions, save exact layouts, and export PDF, HTML, SVG figures, tables, or a research ZIP. Private notes are opt-in. Reproduction verifies the query, revision, data, geometry and source hashes.
10. In **Sources**, review successful checks, unchanged documents, validated updates, failures, archive hashes, and revisions. A source outage retains the previous validated data.

## What is implemented and what depends on evidence

The original 35-contest 2026 Senate registry and 14-state watchlist remain available. All 50 states now have substantive historical research content. The nationwide reference core includes state presidential and Senate history from 1976, House district history through 2018, county presidential returns from 2000, and Census ACS resident context. All-office detail comes from attributed state archives downloaded on demand; available offices and years are explicit rather than a claim that every local election has been collected. Available primary and explicitly labeled academic fallback sources are enabled, with collection diagnostics and archival provenance. See [nationwide atlas coverage](docs/ATLAS_COVERAGE.md), [source definitions](docs/ATLAS_SOURCES.md), [geographic validation](docs/ATLAS_VALIDATION.md), and [current voting coverage](docs/COVERAGE.md) for exact installed depth and limitations.

The current depth release adds source-native precinct acquisition for all 50 states, installed NC/TX/OH/ME/AK maps, synchronized side-by-side/swipe/difference maps, reviewed 2018–2024 county comparisons, bivariate/distribution/concentration graphics, and a complete saved report composer. At revision 176, current validated reported participation is installed for 43 states. Precinct maps are historical candidate-return context, with source-native administrative and unmapped votes preserved separately; they are not current residential-precinct EV maps.

Experimental **EV-led Senate party-margin research calls** cover the 35-contest registry with explicit EV-informed, historical-only and withheld statuses. Forecasts now includes national/county maps, same-stage cycle overlays, method evidence, turnout analogues and assumptions, reasoning, confidence checks, coefficient sensitivity and source-backed Senate/turnout test benches. Polls do not enter this initial EV model. At retained revision **266**, the empirical audit contains **39 eligible checkpoint observations across eight distinct historical Senate contests** in 2016, 2018, 2020 and 2022; contemporary and retrospective evidence remain separate. The headline retrospective days-to-election group contains 25 dependent checkpoint observations. Its frozen EV MAE is **8.434 percentage points**, versus **8.486** for the historical baseline. This tiny selected-sample difference establishes no reliable improvement. Zero earlier-trained EV holdouts meet the training requirements; no calibrated winner probabilities or EV confidence intervals are published. See [backtesting and performance](docs/EV_BACKTESTING.md), [historical EV coverage](docs/HISTORICAL_EV_COVERAGE.md), [forecast workspace guide](docs/FORECAST_RESEARCH_WORKSPACE.md), [EV research methodology](docs/EV_RESEARCH_CALLS.md), [precinct cartography](docs/PRECINCT_CARTOGRAPHY.md), and [report studio](docs/REPORT_STUDIO.md).

Some requested research depth remains conditional on reliable public evidence: precinct observations, joint demographic distributions, coherent ballot-status cohorts, complete historical daily reports, official candidate verification, and complete-universe chamber forecasts. The app explains missing evidence instead of generating substitute figures. Current source coverage is not a claim to have collected every public poll or all historical records.

## Architecture

```text
backend/observatory/
  connectors/       Source-specific extraction and validation
  analytics/        Historical alignment, polling, briefs, scenarios, forecasting
  atlas/            Revisioned elections, contests, options, results, context and on-demand loaders
  atlas_api.py      Nationwide catalog, results, place dossiers and background-download APIs
  geography.py      Reviewed geographic aliases and canonical boundary identifiers
  archive.py        Content-addressed original response archive
  collector.py      Bounded fetches, run lock, atomic source publication
  db.py             Revisioned SQLAlchemy aggregate evidence and research objects
  service.py        Shared analytical read path for UI and exports
  public_publish.py Exact-scope, sanitized aggregate responses for the hosted edition
  scenario_service.py  Assumption validation against pinned measured evidence
  api.py            Versioned FastAPI interfaces and local frontend serving
  exports.py        CSV, JSON, vector HTML/PDF, research-package ZIP
  cli.py            Collection, serving, backup, restoration, backtesting
frontend/src/
  components/       Shared chart, map, table, inspector, and scope primitives
  pages/            Today, States, Atlas, Elections, place dossiers and Research workbenches
  api.ts            Typed API access and pinned exports
  publicData.ts     Hash-verified static data, browser notes and supported client research
config/sources.json Source hierarchy, connectors, cadence, and coverage metadata
config/atlas_sources.json Verified national and per-state historical/context source inventory
migrations/         Alembic schema history
scripts/            Setup, launch, geography, schedule, public packaging and deployment helpers
```

FastAPI and SQLite serve the React/TypeScript/Vite frontend. Recharts renders analytical charts, MapLibre renders interactive reporting-area maps, and D3 geographic projection renders the national map. TanStack Query coordinates requests. Boundary files, fonts, map style, and application assets are served locally. No external AI API, paid data subscription, or commercial tile service is required.

[API contracts](docs/API.md) · [Source discovery](docs/SOURCE_DISCOVERY.md) · [Forecast method](docs/FORECAST_METHOD.md) · [Operations and recovery](docs/OPERATIONS.md) · [Atlas verification](docs/ATLAS_VERIFICATION.md) · [Current verification and remaining research](docs/goals/atlas-depth/VERIFICATION.md)

## Develop and verify

```sh
.venv/bin/python -m pytest -q
.venv/bin/ruff check backend scripts migrations
pnpm --dir frontend typecheck
pnpm --dir frontend build

# Development, in two terminals:
.venv/bin/python -m uvicorn observatory.api:app --host 127.0.0.1 --port 8776 --reload --reload-dir backend
pnpm --dir frontend dev

# Apply schema migrations after a backup.
.venv/bin/python -m alembic upgrade head
```

The development frontend proxies the API to 8776. Production `start.sh` serves its built frontend and API together. OpenAPI documentation is available at `/docs`; `/api/v1/health` reports the validated dataset revision. `requirements.lock` records the verified Python dependency versions; `pyproject.toml` declares supported ranges. Frontend dependencies are fixed by `frontend/pnpm-lock.yaml`.

## Data safeguards and interpretation

Source archives and SQLite live outside Git in `~/Library/Application Support/Battleground Senate Observatory`. Some official input files contain individual voter records; parsers aggregate them for application use. Aggregate exports do not include those raw records. Full backups include the original archive and should remain private.

Requests, issuance, returns, acceptance, rejection, and cast ballots are separate metrics. Missing, unknown, and zero remain distinct. Party registration and demographic/geographic context are not candidate votes. Historical snapshots preserve publication, report, retrieval, and revision chronology where evidence exists. Shared polling samples are not independent studies. The public edition includes source attribution and license references, including the University of Florida tracker. Original voter files, SQLite, archives, personal research objects and credentials are excluded from deployment. Web notes and saved views stay in that browser; they are not uploaded to the publisher.


October 21 follow-up at revision 375: Forecasts now leads with a sourced plain-English explanation, larger type and explicit party colours. Polling, market prices and analyst context have separate default-off switches; they change the written context while preserving the EV-only point and its source manifest. Eight more original Ohio reports and UF 2024 snapshots extend the history; 104 additional polling records preserve original versus secondary provenance. See [context controls and operating limits](docs/EV_CONTEXT_AND_CALLS.md), [historical gaps](docs/HISTORICAL_EV_GAPS.md) and [additional-factor tests](docs/EV_FEATURE_VALIDATION.md).
