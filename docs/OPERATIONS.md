# Local operation and recovery

## Daily operation

Run `./scripts/start.sh` and open `http://127.0.0.1:8776`. Select **Sources** to check the last collection, source date, and validation warnings. Use **Check sources** for a queued background collection. Navigation remains usable while the collector runs. The local job table records completed, failed, and interrupted jobs.

The collector allows four HTTP fetches overall, one per host, and a file lock prevents overlapping runs. Original bytes are archived by SHA-256. Unchanged content reuses the archive; parser/configuration changes trigger revalidation. ETag and Last-Modified are used where supported. Retries and ordinary system-TLS/curl fallback are bounded. Authentication challenges are treated as coverage failures, not bypassed.

The installed web application uses the combined two-hour collector/publisher schedule. After configuring and verifying its first release, install it with:

```sh
.venv/bin/python scripts/install_schedule.py --publish-web --defer-first-run
launchctl print gui/$(id -u)/local.battleground-senate-observatory.collect
```

See [free web operation and recovery](FREE_WEB_HOSTING.md) for configuration, hosted verification, status and rollback. Running `install_schedule.py` without `--publish-web` intentionally replaces this with a collection-only schedule and stops automatic website publication.

Individual sources respect their configured `expected_hours`. The schedule runs while this user is logged in and the Mac is available. It does not wake a sleeping Mac. Sources shows elapsed freshness so missed windows remain apparent. Logs are `collector.log` and `collector-errors.log` in the data directory.

The scheduled collector also runs `collect --due --warm-forecasts`. After collection, it prepares the current revision's deterministic aggregate research run outside browser requests. A genuinely new model/data combination can take about 40 seconds and temporarily use about 2.5 GB; validated frozen reuse is much faster. Failed warming is logged separately and retains all validated evidence. Research sessions remain pinned until the user loads updated evidence. For an exact cutoff/revision, run `.venv/bin/python scripts/backtest_ev.py --revision 266 --as-of 2026-10-21 --state NC --output /absolute/path/audit.json`.

Remove just the schedule:

```sh
.venv/bin/python scripts/install_schedule.py --remove
```

This retains all evidence and research objects. It does not stop a separately running web server.

## Backup and restore

```sh
.venv/bin/observatory backup --output /absolute/private/path/observatory-backup.zip
.venv/bin/observatory restore /absolute/private/path/observatory-backup.zip --destination /absolute/new/empty/directory
OBSERVATORY_DATA_DIR=/absolute/new/empty/directory .venv/bin/alembic upgrade head
OBSERVATORY_DATA_DIR=/absolute/new/empty/directory ./scripts/start.sh
```

Backups use the SQLite backup API, include the matching source archives, published source-native geometry, and immutable model-run results, and record checksums. Large files are hashed as streams. Restoration checks archive paths, database SHA-256, every archived file, geometry and model-run hashes, and SQLite integrity; it rebases internal archive paths. Existing nonempty directories are never replaced. Backups contain private notes and may include raw official voter files; aggregate research packages are the appropriate sharing format.

For exact replay, keep the application/configuration version and local Census boundary assets with the backup. The research ZIP records the selected query, revision, parser/application version, source URLs and hashes, metric definitions, coverage warnings, and boundary vintage. A package can be inspected independently; interactive reopening requires its matching local evidence store.

## Source failures

- **HTTP 403, challenge, or unavailable dashboard export:** inspect Sources. The previous validated evidence remains available. A labeled fallback may cover a different metric or date; select the correct measure rather than comparing them as equivalent.
- **Unexpected totals or revisions:** inspect the original snapshot and revision history. Newly reported change does not establish the day ballots were cast. Source corrections are auditable revisions.
- **Schema change:** failed parsing prevents publication. Update the connector, run its tests, and reparse the archived original before refreshing.
- **Offline:** browse validated evidence and local maps. `collect --offline` reparses cached originals and performs no network collection.
- **No matching data:** review the selected metric, mode, cutoff, cycle, and evidence basis. Missing is never presented as zero.
- **Port already used:** select another port with `OBSERVATORY_PORT=8777 ./scripts/start.sh`. The default development proxy remains 8776; change `frontend/vite.config.ts` only for development.
- **Interrupted collection:** the process lock clears when the process exits. Restart; source batches are transactional. Unfinished API jobs are marked interrupted on server restart.

## Extend a connector

Add source metadata to `config/sources.json`, implement a small connector under `backend/observatory/connectors`, and register it in the router. Return validated `Observation`/`Poll` objects with original URL, source geography, metric definition, chronology, and warnings. Archive via the shared `Fetcher`. Do not install invented values in the application database; synthetic fixtures belong only in tests.

Use the original metric owner first. If a fallback fills a gap, preserve its tier, original citation, license, publication limitations, and definition. To add daily historical reports, prove their publication chronology independently of the dates printed inside them. Reconstructed timelines must remain explicitly reconstructed.

## Regenerate a saved report

```sh
.venv/bin/observatory reproduce /absolute/path/research-package.zip --format pdf --output /absolute/new/report.pdf
```

The command restores the package query and revision, verifies snapshot hashes against the matching database, compares the original and recomputed trajectories/totals, and reuses the stored section order, title, and explicit note selection. It refuses to overwrite an existing output or silently accept changed calculations.


### Verified recovery example (October 21, 2026)

The revision-325 backup was restored into a new isolated directory and passed SQLite integrity, 783 source hashes, 37 geometry files and 29 immutable model-run hashes. Both saved investigations retained their original revisions and totals. The revision-266 Senate report recalculated to byte-identical HTML. An older v1.1/r175 report reproduced its verified frozen original after the model upgrade, with the replay mode disclosed. The regenerated 28-page PDF has identical text, page boxes and decoded content streams; PDF creation/modification timestamps and document IDs can change, so binary PDF identity is not the analytical reproducibility criterion.
