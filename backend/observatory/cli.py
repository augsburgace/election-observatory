"""Local collector, server, backup/recovery, and reproducible analysis commands."""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from .db import Database, Snapshot
from .domain import FetchedDocument, utc_now
from .settings import Settings, get_settings


def _file_hash(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def backup(database: Database, output: Path | None = None) -> Path:
    output = output or database.settings.data_dir / "backups" / f"observatory-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}.zip"
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=database.settings.data_dir / "staging") as stage:
        copied = database.backup(Path(stage) / "observatory.sqlite3")
        # Read the manifest from the copied transaction, so a concurrent collector
        # cannot advance the live revision between the database and archive list.
        with sqlite3.connect(copied) as connection:
            connection.row_factory = sqlite3.Row
            snapshots = [dict(row) for row in connection.execute("SELECT id,sha256,path,url FROM snapshots")]
            revision = connection.execute("SELECT COALESCE(MAX(id),0) FROM revisions").fetchone()[0]
        paths = {s["sha256"]: Path(s["path"]) for s in snapshots}
        geometry_root = database.settings.data_dir / "geometry"
        geometry = []
        if geometry_root.exists():
            for path in sorted(geometry_root.rglob("*")):
                if not path.is_file() or path.is_symlink():
                    continue
                relative = path.relative_to(database.settings.data_dir)
                revisions = [int(part[1:]) for part in relative.parts if part.startswith("r") and part[1:].isdigit()]
                if revisions and max(revisions) > revision:
                    continue
                geometry.append({"file": str(relative), "sha256": _file_hash(path)})
        model_runs = []
        model_root = database.settings.data_dir / "model-runs"
        if model_root.exists():
            for path in sorted(model_root.rglob("r*.json")):
                match = re.match(r"r(\d+)-", path.name)
                if path.is_symlink() or not match or int(match[1]) > revision:
                    continue
                model_runs.append({"file": str(path.relative_to(database.settings.data_dir)), "sha256": _file_hash(path)})
        metadata = {"application": "Battleground Senate Observatory", "created_at": utc_now(), "revision": revision, "database_sha256": _file_hash(copied),
                    "archive_hashes": sorted(paths), "source_snapshots": snapshots, "geometry_files": geometry,
                    "model_run_files": model_runs}
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.write(copied, "observatory.sqlite3")
            archive.writestr("manifest.json", json.dumps(metadata, indent=2))
            for digest, path in paths.items():
                if not path.is_file():
                    raise ValueError(f"Source archive missing: {digest}; backup is incomplete")
                archive.write(path, f"archive/{digest[:2]}/{digest}")
            for item in geometry + model_runs:
                path = database.settings.data_dir / item["file"]
                with path.open("rb") as stream:
                    if hashlib.file_digest(stream, "sha256").hexdigest() != item["sha256"]:
                        raise ValueError("Published geometry/model result changed during backup; retry with immutable evidence")
                archive.write(path, item["file"])
    return output


def restore(backup_path: Path, destination: Path) -> dict:
    destination = destination.expanduser().resolve()
    if destination.exists() and any(destination.iterdir()):
        raise ValueError("Restore destination must be empty; existing application data is never replaced")
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(backup_path) as archive:
        for item in archive.infolist():
            target = (destination / item.filename).resolve()
            if not target.is_relative_to(destination.resolve()):
                raise ValueError("Unsafe path in backup archive")
        manifest = json.loads(archive.read("manifest.json"))
        archive.extractall(destination)
    database_path = destination / "observatory.sqlite3"
    if _file_hash(database_path) != manifest["database_sha256"]:
        raise ValueError("Backup database checksum failed")
    for digest in manifest["archive_hashes"]:
        path = destination / "archive" / digest[:2] / digest
        if _file_hash(path) != digest:
            raise ValueError(f"Archive checksum failed: {digest}")
    for item in manifest.get("geometry_files", []) + manifest.get("model_run_files", []):
        path = destination / item["file"]
        with path.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != item["sha256"]:
                raise ValueError(f"Geometry/model-run checksum failed: {item['file']}")
    with sqlite3.connect(database_path) as connection:
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("Restored SQLite integrity check failed")
        for snapshot_id, digest in connection.execute("SELECT id,sha256 FROM snapshots"):
            connection.execute("UPDATE snapshots SET path=? WHERE id=?", (str(destination / "archive" / digest[:2] / digest), snapshot_id))
        connection.commit()
    cached = rebuild_restored_fetch_cache(destination)
    return {"destination": str(destination), "revision": manifest["revision"], "archives_verified": len(manifest["archive_hashes"]),
        "geometry_files_verified": len(manifest.get("geometry_files", [])), "model_runs_verified": len(manifest.get("model_run_files", [])),
        "fetch_cache_entries": cached, "integrity": "ok"}


def rebuild_restored_fetch_cache(destination: Path) -> int:
    """Recover offline URL lookups from the verified, rebased snapshot store.

    Cache keys retain the original requested URL (including query strings), not
    an invented redirect target. Snapshot metadata cannot recover ETags or
    Last-Modified headers, so those are learned again on a future online check.
    """
    destination = destination.expanduser().resolve()
    with sqlite3.connect(destination / "observatory.sqlite3") as connection:
        connection.row_factory = sqlite3.Row
        snapshots = [dict(row) for row in connection.execute(
            "SELECT id,revision,url,sha256,path,content_type,retrieved_at,byte_count FROM snapshots")]
    latest = {}
    def rank(row):
        try:
            observed = datetime.fromisoformat(row["retrieved_at"].replace("Z", "+00:00"))
            observed = observed.replace(tzinfo=timezone.utc) if observed.tzinfo is None else observed.astimezone(timezone.utc)
        except (AttributeError, TypeError, ValueError):
            observed = datetime.min.replace(tzinfo=timezone.utc)
        return observed, row["revision"], row["id"]
    for snapshot in snapshots:
        original_url = snapshot["url"]
        if original_url not in latest or rank(snapshot) > rank(latest[original_url]):
            latest[original_url] = snapshot
    cache_dir = destination / "fetch-cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    for original_url, snapshot in latest.items():
        archived = destination / "archive" / snapshot["sha256"][:2] / snapshot["sha256"]
        if not archived.is_file():
            raise ValueError("Cannot rebuild offline URL cache without its verified archive")
        document = FetchedDocument(url=original_url, sha256=snapshot["sha256"], path=str(archived),
            content_type=snapshot["content_type"], retrieved_at=snapshot["retrieved_at"],
            byte_count=snapshot["byte_count"], text=None, etag=None, last_modified=None)
        key = hashlib.sha256(original_url.encode()).hexdigest()
        pending = cache_dir / (key + ".json.pending")
        pending.write_text(document.model_dump_json())
        pending.replace(cache_dir / (key + ".json"))
    return len(latest)


def _warm_forecasts(database: Database) -> None:
    """A slow first calculation belongs to the local worker, not browsing."""
    from time import monotonic

    from .ev_forecast import early_vote_forecasts

    started = monotonic()
    try:
        result = early_vote_forecasts(database, state="NC")
        print(json.dumps({"forecast_cache": "ready", "revision": result["revision"],
            "as_of": result["as_of"], "model_version": result["model_version"],
            "seconds": round(monotonic() - started, 3)}), flush=True)
        from .ev_feature_validation import build_feature_validation
        features = build_feature_validation(database, result["revision"], result["as_of"], backtesting=result["backtesting"])
        print(json.dumps({"feature_cache": "ready", "revision": features["revision"], "as_of": features["as_of"]}), flush=True)
    except Exception as exc:
        # Collection is still successful; a failed analytical warmup must never
        # discard source evidence or advertise a ready model cache.
        logging.exception("Forecast prewarming failed; validated source evidence is retained")
        print(json.dumps({"forecast_cache": "failed", "error": str(exc)}), file=sys.stderr, flush=True)


def main(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(description="Local source-backed Senate research observatory")
    parser.add_argument("--data-dir", type=Path, help="Override the local application-data directory")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init", help="Initialize SQLite without creating election observations")
    collect = commands.add_parser("collect", help="Fetch and validate configured public sources")
    collect.add_argument("--state")
    collect.add_argument("--source", action="append", dest="source_ids")
    collect.add_argument("--include-historical", action="store_true")
    collect.add_argument("--offline", action="store_true", help="Reparse locally archived source responses")
    collect.add_argument("--due", action="store_true", help="Check only sources due according to their publication cadence")
    collect.add_argument("--warm-forecasts", action="store_true", help="Prepare the current EV research run after collection, outside web requests")
    serve = commands.add_parser("serve", help="Serve the API and production frontend on loopback")
    serve.add_argument("--port", type=int, default=8776)
    commands.add_parser("geography", help="Download official local Census boundary assets")
    commands.add_parser("coverage", help="Print source coverage and collection diagnostics")
    atlas = commands.add_parser("atlas", help="Install real nationwide reference data or deeper state evidence")
    atlas.add_argument("--core", action="store_true", help="Install nationwide reference data; precinct archives remain on demand")
    atlas.add_argument("--dataset", help="Verified dataset ID from /api/v2/catalog/datasets")
    atlas.add_argument("--state", help="State code for a per-state dataset family")
    atlas.add_argument("--offline", action="store_true", help="Use locally archived source documents")
    save = commands.add_parser("backup", help="Consistent SQLite and source-archive backup")
    save.add_argument("--output", type=Path)
    recover = commands.add_parser("restore", help="Verify and restore into a new empty directory")
    recover.add_argument("backup", type=Path)
    recover.add_argument("--destination", type=Path, required=True)
    backtest = commands.add_parser("backtest", help="Evaluate documented historical forecasting inputs")
    backtest.add_argument("input", type=Path)
    backtest.add_argument("--output", type=Path)
    backtest.add_argument("--simulations", type=int, default=20000)
    reproduce = commands.add_parser("reproduce", help="Regenerate a report from its pinned research-package manifest")
    reproduce.add_argument("package", type=Path)
    reproduce.add_argument("--format", choices=["html", "pdf", "csv", "json"], default="html")
    reproduce.add_argument("--output", type=Path)
    arguments = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    settings = Settings(arguments.data_dir.expanduser()) if arguments.data_dir else get_settings()
    if arguments.data_dir:
        os.environ["OBSERVATORY_DATA_DIR"] = str(settings.data_dir)
    database = Database(settings)
    if arguments.command == "init":
        from .atlas.models import ensure_schema
        ensure_schema(database)
        print(json.dumps({"database": str(settings.database_path), "revision": database.latest_revision()}))
    elif arguments.command == "serve":
        import uvicorn
        uvicorn.run("observatory.api:app", host="127.0.0.1", port=arguments.port)
    elif arguments.command == "collect":
        from .collector import collect_sources
        source_ids = arguments.source_ids
        if arguments.due and not source_ids:
            from .service import source_inventory
            source_ids = []
            for source in source_inventory(database):
                if not source.get("enabled", True) and not source.get("last_changed"):
                    continue
                if source.get("historical") and not arguments.include_historical:
                    continue
                last = source.get("last_checked")
                if not last or (datetime.now(timezone.utc) - datetime.fromisoformat(last)).total_seconds() >= float(source.get("expected_hours", 24)) * 3600:
                    source_ids.append(source["id"])
            if not source_ids:
                print(json.dumps({"checked": 0, "reason": "No sources are due", "revision": database.latest_revision()}))
                if arguments.warm_forecasts:
                    _warm_forecasts(database)
                return
        result = collect_sources(database, state=arguments.state, source_ids=source_ids, include_historical=arguments.include_historical, offline=arguments.offline)
        print(json.dumps(result, indent=2))
        if arguments.warm_forecasts:
            _warm_forecasts(database)
    elif arguments.command == "geography":
        subprocess.run([sys.executable, str(settings.project_root / "scripts" / "fetch_geography.py")], check=True)
    elif arguments.command == "coverage":
        from .service import bootstrap, source_inventory
        print(json.dumps({"summary": bootstrap(database)["coverage"], "sources": source_inventory(database)}, indent=2))
    elif arguments.command == "atlas":
        from .atlas import core_install, load_dataset
        if arguments.core:
            result = core_install(database, progress=lambda update: print(json.dumps(update), flush=True))
        elif arguments.dataset:
            result = load_dataset(database, arguments.dataset, state=arguments.state, offline=arguments.offline,
                                  progress=lambda update: print(json.dumps(update), flush=True))
        else:
            parser.error("atlas requires --core or --dataset ID")
        print(json.dumps(result, indent=2))
    elif arguments.command == "backup":
        print(backup(database, arguments.output))
    elif arguments.command == "restore":
        print(json.dumps(restore(arguments.backup, arguments.destination), indent=2))
    elif arguments.command == "backtest":
        from .analytics import backtest_forecasts
        payload = json.loads(arguments.input.read_text())
        result = backtest_forecasts(payload.get("cases", payload) if isinstance(payload, dict) else payload, simulations=arguments.simulations)
        output = arguments.output or settings.data_dir / "exports" / f"backtest-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2))
        print(json.dumps({"output": str(output), "gate": result.get("gate"), "metrics": result.get("metrics")}, indent=2))
    elif arguments.command == "reproduce":
        from .domain import ResearchQuery
        from .exports import csv_data, html_report, pdf_report
        from .service import workspace
        with zipfile.ZipFile(arguments.package) as package:
            evidence_manifest = json.loads(package.read("manifest.json"))
            if evidence_manifest.get("schema") in {"observatory-atlas-research-v1", "observatory-context-research-v1", "observatory-composed-report-v1"}:
                from .atlas_reproduce import reproduce_atlas
                print(json.dumps(reproduce_atlas(database, arguments.package, arguments.format, arguments.output)))
                return
            original = json.loads(package.read("workspace.json"))
        query = ResearchQuery.model_validate(evidence_manifest["query"])
        view = workspace(database, query)
        with database.session() as session:
            for expected in evidence_manifest.get("source_snapshots", []):
                snapshot = session.get(Snapshot, expected["id"])
                if snapshot is None or snapshot.sha256 != expected["sha256"]:
                    raise ValueError("This package requires its matching evidence database/archive backup")
        def signature(data):
            return [(p["cycle"], p["date"], p["value"]) for p in data["series"]]
        if view["summary"]["total"] != original["summary"]["total"] or signature(view) != signature(original):
            raise ValueError("Analytical output differs from the package; retain the original application version for exact reproduction")
        configuration = evidence_manifest.get("report", {})
        options = {"sections": configuration.get("sections"), "title": configuration.get("title"),
                   "notes": evidence_manifest.get("selected_notes") if configuration.get("private_notes_included") else None}
        if arguments.format == "html":
            content = html_report(view, **options)
        elif arguments.format == "pdf":
            content = pdf_report(view, **options)
        elif arguments.format == "csv":
            content = csv_data(view)
        else:
            content = json.dumps(view, indent=2).encode()
        output = arguments.output or settings.data_dir / "exports" / f"reproduced-{query.state}-r{view['revision']}-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}.{arguments.format}"
        output.parent.mkdir(parents=True, exist_ok=True)
        if output.exists():
            raise ValueError("The output already exists; choose a new filename")
        output.write_bytes(content)
        print(json.dumps({"output": str(output), "revision": view["revision"], "observations_agree": True}))


if __name__ == "__main__":
    main()
