# Free public web application

Open [Battleground Senate Observatory](https://battleground-senate-observatory.pages.dev).

Cloudflare Pages serves the real React application and immutable aggregate research data on its free plan. The GitHub source repository remains private. The existing Mac collects evidence, builds the research publication and deploys updates every two hours while awake, logged in and online. The hosted application remains available with its last successful publication when the Mac is asleep or offline. Fresh source collection resumes with a later successful scheduled run; the schedule does not wake the Mac.

This is one deployment path: Cloudflare Pages **Direct Upload**, driven by `scripts/update_web.py`. There is no GitHub Actions cloud publisher or Git-connected Pages deployment. Pushing a source or generated-data branch alone does not update this website.

## What the web edition contains

The web edition uses the same analytical services as the local application. Every published investigation declares its dataset revision, evidence cutoff, metric, method, comparison cycle and chronology. Its coverage follows collected evidence rather than an assertion that every state publishes every measure.

- All 50 states have reference destinations, source coverage and supported current participation investigations. States without compatible current observations retain historical context and an explicit evidence gap.
- Current participation includes the available uncategorized metric/method combinations and baselines 2022, 2024, 2020 and 2018. Historical participation investigations cover 2016–2024 where the archive supports them. Reported and reconstructed histories remain separate.
- The historical EV workbench includes days-to-election and days-since-opening alignment, with reported versus retrospective policies. Actual source observations and documented voting calendars determine compatibility.
- Historical result workbenches prioritize President, U.S. Senate, U.S. House and governor. The verified catalog also retains local, judicial and legislative contests; additional analytical scopes remain explicitly unpublished in this web edition and available through the full local application.
- Installed, validated precinct maps are published as historical candidate-return context. Other verified precinct sources remain catalog entries. These maps do not claim current residential-precinct early-voting coverage.
- Polling policies include the published response distributions, five recency windows, likely/registered-voter populations, sponsorship inclusion and vote-choice versus winner-expectation questions. Original producer records and secondary summaries have distinct attribution.
- Experimental Senate EV calls include their evidence, historical references, source-quality explanations, turnout assumptions, sensitivity and feature-test results. The battleground watchlist has all eight combinations of the three optional context switches.
- State report packets preserve their exact queries, figures, tables, source appendices and limitations. The browser supports published-section selection, reordering, captions and printable exports. A different analytical query requires a matching published packet or the local edition.

An unavailable revision, cutoff or filter combination never silently receives a statewide or latest-data substitute. The interface explains that the selection has not been published. Browser geography selection can highlight and inspect supported marks; broader recalculation requires a valid published scope or a documented client calculation.

## Interpretation and privacy

The generated explanation uses deterministic local templates and reproducible calculations; no external AI API is required. EV calls are conditional party-margin research estimates. Their historical evaluation has not established dependable predictive improvement, calibrated winner probabilities or statistical confidence intervals. Sensitivity ranges describe changing assumptions.

Polling, market prices and analyst-context switches default off. Enabling them explains supporting or conflicting evidence while preserving the EV estimate. Market contract prices are not vote shares. Registration, demographic and geographic composition do not identify candidate votes. Missing categories and unsupported demographic intersections remain missing.

The website receives aggregate JSON, chart/report primitives, public boundary geometry and source citations. It excludes SQLite databases, original voter files, source archives, private research objects, credentials and local storage paths. Private browser notes and saved investigations remain in that browser's storage. They are not uploaded or synchronized to the Mac; clearing browser storage can remove them.

Public evidence inspectors retain actual source URLs, hashes and reporting/retrieval dates. Native documents and complete private revision/correction details remain in the local edition. UF Election Lab/Michael P. McDonald tracker data has its own attribution, source-cycle links, dates, license reference and transformation caveats, separate from original election authorities. RCP public-browser captures retain their actual capture dates and do not refresh unattended; original producer sources update independently.

## Operate the installed publisher

Run commands from the project directory with its existing Python environment and frontend dependencies:

```sh
# Collect due sources, prepare analysis, build, test and deploy a validated release.
.venv/bin/python scripts/update_web.py

# Publish a newer validated evidence batch without another collection pass.
.venv/bin/python scripts/update_web.py --skip-collect

# Build a newer, unpublished evidence batch; do not change the hosted site.
.venv/bin/python scripts/update_web.py --skip-collect --build-only
```

The updater holds `web-publication.lock` so two publishers cannot overlap. It uses the SQLite backup API to obtain a consistent temporary snapshot, generates the public bundle, runs the static reader's all-state checks, compiles the frontend, verifies object hashes and free-host file limits, then deploys to the approved Pages project. After deployment it verifies the hosted revision and all-state manifest, then runs the actual static reader against the hosted investigations. Hosted-reader failure is inside the rollback-protected publication step.

During state publication, the batch scripts defer automatic cyclic garbage collection and explicitly collect between states. This reduces repeated scans of a large research workspace; ordinary reference counting continues. Automatic collection resumes before results, precinct and forecast processing, and the scripts restore its original setting even after a build failure. The policy changes memory management only; numerical calculations, source selection and evidence revisions are unchanged. Its collection count and time are logged separately from publication progress. Use this policy only in the batch publisher, never in the interactive API process.

The automatic publisher proceeds only when local evidence is newer than both its recorded published revision and the current hosted revision. Equal revisions return `unchanged`; an older local revision returns `waiting_for_new_batch`. This check also precedes `--build-only`. Application-only changes require a new validated evidence batch before automatic republication; use the manual artifact build below to inspect those changes independently. No flag silently rolls a newer hosted investigation back to older evidence.

### Configuration and sign-in

The installed, non-secret configuration is:

`~/Library/Application Support/Battleground Senate Observatory/web-publishing.json`

```json
{
  "account_id": "be41722b274cd61360daa2ee516b47e9",
  "project": "battleground-senate-observatory",
  "url": "https://battleground-senate-observatory.pages.dev"
}
```

The publication helper validates these approved identifiers and HTTPS address before deployment. Tokens do not belong in this file. Credentials use the existing Wrangler sign-in outside Git and public artifacts. Inspect sign-in with:

```sh
pnpm --dir frontend exec wrangler whoami
```

If the existing sign-in expires, the updater retains the hosted release and records a failure. Reauthenticate that same Cloudflare account through Wrangler, then rerun the publisher. Do not paste tokens into source files, command arguments, public logs or this documentation.

### Install, inspect or remove the schedule

After the first deployment has been verified:

```sh
.venv/bin/python scripts/install_schedule.py --publish-web --defer-first-run
launchctl print gui/$(id -u)/local.battleground-senate-observatory.collect
```

This updates the existing collector's launchd job to run `scripts/update_web.py` at two-hour intervals. `--defer-first-run` avoids starting another immediate full publication after the manual first release. Omitting it also runs on installation/login. There is one collector/publisher schedule, and it requires this user to be logged in.

```sh
# Remove the automatic collector/publisher schedule; retain evidence and hosted site.
.venv/bin/python scripts/install_schedule.py --remove
```

Removing the schedule does not delete source data or the existing website. The separate local web server is not managed by this schedule.

### Status and logs

```sh
cat "$HOME/Library/Application Support/Battleground Senate Observatory/web-status.json"
tail -n 60 "$HOME/Library/Application Support/Battleground Senate Observatory/collector.log"
tail -n 60 "$HOME/Library/Application Support/Battleground Senate Observatory/collector-errors.log"
```

`web-status.json` records the last attempt, status, last successful publication, published revision and deployment identity when available. `published` means revision, all-state and hosted-reader checks succeeded. `build_verified` confirms a build-only run. `unchanged` means this revision was already published; `waiting_for_new_batch` retains a newer hosted release. `failed`, `rolled_back` and `rollback_failed` require inspecting the publisher log and the hosted manifest. A running status left by an interrupted process is not proof of publication.

The public manifest is at [the publication manifest](https://battleground-senate-observatory.pages.dev/public-data/manifest.json). Its publication time is separate from source reporting dates. The source-health interface and publication banner make stale observations and missed update windows visible.

## Rollback and recovery

Build, source-validation or pre-deployment failures leave the existing website untouched. If post-deployment verification fails, the updater attempts to restore the exact prior successful production deployment, then verifies its identity and evidence revision. A rollback that cannot be verified is reported as `rollback_failed`; do not describe it as restored until the live checks pass.

For manual rollback, first stop the automatic schedule while investigating. In Cloudflare's **Workers & Pages → battleground-senate-observatory → Deployments**, select the known previous successful production deployment and roll it back. Verify the site's manifest revision, representative investigations and reports before reinstalling the schedule. Correct the application or source issue before publishing again. The publication helper changes only the approved Observatory project.

Evidence backup and restoration remain separate from website rollback. See [local operation and recovery](OPERATIONS.md) for the verified SQLite/source-archive backup process. Restoring an older local backup does not authorize silently replacing a newer hosted evidence revision.

## Rebuild the public artifact manually

The updater automates this sequence. For a separate reviewable build, use a stable aggregate checkpoint and a fresh output directory; do not put the personal database or raw archive in the deployment directory.

```sh
.venv/bin/python scripts/publish_public_data.py \
  --data-dir /absolute/path/to/aggregate-checkpoint \
  --output frontend/public/public-data \
  --as-of 2026-10-21
pnpm --dir frontend typecheck
VITE_PUBLIC_DATA_MODE=true VITE_PUBLIC_BASE=/ \
  pnpm --dir frontend exec vite build --outDir dist-public
.venv/bin/python scripts/prepare_web_site.py \
  --dist frontend/dist-public \
  --output /absolute/new/reviewable-site \
  --provider cloudflare
```

The ordinary `pnpm --dir frontend build` remains the full local backend edition. Public deployment must explicitly enable `VITE_PUBLIC_DATA_MODE=true`. `--replace` applies only when intentionally replacing a generated public-data bundle. The publisher's `--state` and `--skip-*` switches are useful for development; a complete public release must pass the all-50-state verifier.

### Published data contract

`/public-data/manifest.json` declares `schema_version: observatory-public-v1`, publication time, cutoff, revision, source attribution and per-route `request_defaults`. Requests add those declared defaults, retain supplied semantic filters and sort the query keys. The `requests` index resolves the complete scope to an immutable object descriptor; it is not a live FastAPI server.

Objects use `observatory-json-refs-v1` structural sharing. `$public_ref` resolves a hash-verified subtree and `$public_chunks` concatenates complete array chunks. Larger assets use deterministic gzip. The browser verifies SHA-256 over the decompressed canonical JSON before hydration; deduplication never samples or truncates rows.

Final packaging groups small logical objects into hash-verified containers. `object_packs[logicalPath]` is an index into `packs`; the decoded container holds the original object's exact UTF-8 JSON text under `objects[logicalPath]`. Original request descriptors and reference hashes remain unchanged. Containers follow publication insertion order, hold at most 128 members or 256 KiB decoded data, and leave members larger than 64 KiB independently addressable. This reduces physical file count without downloading a large unrelated archive for one investigation. The final `objects` inventory lists physical pack and standalone files; `logical_object_count` records the complete original inventory.

Evidence uses 512-ID buckets: `evidence_buckets[String(Math.floor(observationId / 512))]` identifies a descriptor whose hydrated object maps exact IDs to public inspector responses. Missing IDs remain unavailable. Published reports preserve their exact analytical scopes and source appendices.

The publication command permits up to 100,000 logical fragments before packing and caps the generated data at 900 MB. Final packaging verifies every logical object and reference, then enforces Cloudflare Free's 20,000 physical files and 25 MiB per-file limits, including the manifest and application assets. These bounded free resources and the Mac's availability determine this deployment's operating limits; it does not promise uninterrupted collection.

Official references: [Cloudflare Pages limits](https://developers.cloudflare.com/pages/platform/limits/), [Direct Upload](https://developers.cloudflare.com/pages/get-started/direct-upload/), [Pages rollbacks](https://developers.cloudflare.com/pages/configuration/rollbacks/).
