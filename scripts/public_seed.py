"""Sanitized aggregate checkpoint for the free scheduled publication worker.

This is deliberately not a full Observatory backup: original voter documents,
personal notebooks, job history and credentials never enter the release asset.
The private backup/recovery commands remain unchanged.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from observatory.db import Database  # noqa: E402
from observatory.domain import utc_now  # noqa: E402
from observatory.public_access import public_payload  # noqa: E402
from observatory.settings import Settings, get_settings  # noqa: E402

SCHEMA = "observatory-public-collector-seed-v1"
MAX_EXPANDED_BYTES = 12 * 1024**3
MAX_CONTEXT_BYTES = 2_000_000


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _sanitize_database(path: Path) -> dict:
    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=DELETE")
        # DELETE alone leaves notebook text recoverable in SQLite free pages.
        # Scrub deleted/replaced cells before making a public release asset.
        connection.execute("PRAGMA secure_delete=ON")
        tables = {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for table in ("research", "jobs"):
            if table in tables:
                connection.execute(f'DELETE FROM "{table}"')
        if "corrections" in tables:
            connection.execute("UPDATE corrections SET reason='Private annotation withheld from public checkpoint'")
        for row in connection.execute("SELECT id,sha256 FROM snapshots").fetchall():
            connection.execute("UPDATE snapshots SET path=? WHERE id=?", (f"archive/{row['sha256'][:2]}/{row['sha256']}", row["id"]))
        for row in connection.execute("SELECT id,error,warnings FROM source_states").fetchall():
            warnings = public_payload(json.loads(row["warnings"] or "[]"))
            connection.execute("UPDATE source_states SET error=?,warnings=? WHERE id=?", (
                "Source unavailable; prior validated evidence retained" if row["error"] else None,
                json.dumps(warnings), row["id"]))
        # Parse every payload: guessing which path spelling or nested secret key
        # might be present is not a trustworthy public-data boundary.
        for table in tables:
            columns = {r["name"] for r in connection.execute(f'PRAGMA table_info("{table}")')}
            if "error" in columns:
                connection.execute(f'UPDATE "{table}" SET error=? WHERE error IS NOT NULL',
                    ("Source unavailable; prior validated evidence retained",))
            if "payload" not in columns or "id" not in columns:
                continue
            cursor = connection.execute(f'SELECT id,payload FROM "{table}"')
            while rows := cursor.fetchmany(2000):
                changed = []
                for row in rows:
                    original = json.loads(row["payload"])
                    clean = public_payload(original)
                    if clean != original:
                        changed.append((json.dumps(clean), row["id"]))
                if changed:
                    connection.executemany(f'UPDATE "{table}" SET payload=? WHERE id=?', changed)
        revision = connection.execute("SELECT COALESCE(MAX(id),0) FROM revisions").fetchone()[0]
        connection.commit()
        # Rebuild into clean pages. secure_delete cannot erase private content
        # that was deleted before this export and survives on old free pages.
        connection.execute("VACUUM")
        if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise ValueError("Public checkpoint failed SQLite consistency check")
        return {"revision": revision, "private_notebook_rows": connection.execute("SELECT COUNT(*) FROM research").fetchone()[0],
                "private_job_rows": connection.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]}


def create_seed(database: Database, output: Path) -> dict:
    if output.exists():
        raise ValueError("Choose a new output file; existing checkpoints are never overwritten")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=database.settings.data_dir / "staging") as stage_name:
        stage = Path(stage_name)
        copied = database.backup(stage / "observatory.sqlite3")
        proof = _sanitize_database(copied)
        entries = [{"file": "observatory.sqlite3", "sha256": digest(copied), "bytes": copied.stat().st_size}]
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, compresslevel=3) as archive:
            archive.write(copied, "observatory.sqlite3")
            geometry = database.settings.data_dir / "geometry"
            if geometry.exists():
                for source in sorted(geometry.rglob("*")):
                    if not source.is_file() or source.is_symlink() or source.suffix not in {".json", ".geojson"}:
                        continue
                    relative = str(source.relative_to(database.settings.data_dir))
                    clean = None
                    if source.suffix == ".json":
                        # Review records can contain local archive references
                        # even when their filename is not manifest.json.
                        # Retain exact source bytes when no redaction is needed.
                        original = json.loads(source.read_bytes())
                        sanitized = public_payload(original)
                        if sanitized != original:
                            clean = json.dumps(sanitized, separators=(",", ":")).encode()
                    if clean is not None:
                        archive.writestr(relative, clean)
                        entries.append({"file": relative, "sha256": hashlib.sha256(clean).hexdigest(), "bytes": len(clean)})
                    else:
                        archive.write(source, relative)
                        entries.append({"file": relative, "sha256": digest(source), "bytes": source.stat().st_size})
            # RCP captures contain factual public tables only. Whitelist the
            # exact capture schema; all other original archives stay local.
            with sqlite3.connect(copied) as connection:
                documents = connection.execute("SELECT DISTINCT sha256 FROM snapshots WHERE content_type='application/vnd.observatory.browser-table+json'").fetchall()
            for (sha,) in documents:
                source = database.settings.archive_dir / sha[:2] / sha
                if not source.is_file() or source.stat().st_size > MAX_CONTEXT_BYTES:
                    continue
                raw = source.read_bytes()
                payload = json.loads(raw)
                if payload.get("schema") != "rcp-browser-tables-v1" or public_payload(payload) != payload:
                    continue
                if hashlib.sha256(raw).hexdigest() != sha:
                    raise ValueError("Public capture checksum mismatch")
                name = f"archive/{sha[:2]}/{sha}"
                archive.writestr(name, raw)
                entries.append({"file": name, "sha256": sha, "bytes": len(raw)})
            manifest = {"schema": SCHEMA, "created_at": utc_now(), **proof, "entries": entries,
                "scope": "Normalized aggregate observations/results, boundary geometry, and factual browser polling tables only",
                "excluded": ["private notebook and saved investigations", "job history", "original voter-file archives", "full source archives", "credentials", "private correction reasons", "server caches", "backups"]}
            archive.writestr("manifest.json", json.dumps(manifest, separators=(",", ":")))
    return {**proof, "path": str(output), "sha256": digest(output), "bytes": output.stat().st_size, "entries": len(entries)}


def restore_seed(source: Path, destination: Path) -> dict:
    if destination.exists() and any(destination.iterdir()):
        raise ValueError("Public seed destination must be empty")
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(source) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        if manifest.get("schema") != SCHEMA:
            raise ValueError("Unsupported public checkpoint schema")
        files = {item["file"]: item for item in manifest["entries"]}
        if sum(item["bytes"] for item in files.values()) > MAX_EXPANDED_BYTES:
            raise ValueError("Public checkpoint exceeds worker storage allowance")
        if set(archive.namelist()) != set(files) | {"manifest.json"}:
            raise ValueError("Unexpected file in public checkpoint")
        for name, item in files.items():
            target = (destination / name).resolve()
            if not target.is_relative_to(destination.resolve()) or target == destination.resolve():
                raise ValueError("Unsafe checkpoint path")
            allowed = name == "observatory.sqlite3" or name.startswith(("geometry/", "archive/"))
            if not allowed or archive.getinfo(name).file_size != item["bytes"]:
                raise ValueError("Unexpected checkpoint member")
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(name) as incoming, target.open("wb") as outgoing:
                shutil.copyfileobj(incoming, outgoing, length=1024 * 1024)
            if digest(target) != item["sha256"]:
                raise ValueError("Checkpoint checksum failed")
    with sqlite3.connect(destination / "observatory.sqlite3") as connection:
        for snapshot_id, sha in connection.execute("SELECT id,sha256 FROM snapshots").fetchall():
            connection.execute("UPDATE snapshots SET path=? WHERE id=?", (str(destination / "archive" / sha[:2] / sha), snapshot_id))
        connection.commit()
    settings = Settings(destination)
    settings.prepare()
    # Rebuild only whitelisted existing captures. A missing original archive
    # is never represented as a successful retrieval.
    from observatory.domain import FetchedDocument
    with sqlite3.connect(settings.database_path) as connection:
        connection.row_factory = sqlite3.Row
        for row in connection.execute("SELECT * FROM snapshots ORDER BY revision,id"):
            if not Path(row["path"]).is_file():
                continue
            doc = FetchedDocument(url=row["url"], sha256=row["sha256"], path=row["path"], content_type=row["content_type"], retrieved_at=row["retrieved_at"], byte_count=row["byte_count"])
            cache = destination / "fetch-cache" / (hashlib.sha256(row["url"].encode()).hexdigest() + ".json")
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(doc.model_dump_json())
    return {"revision": manifest["revision"], "entries_verified": len(files), "private_notebook_rows": 0, "destination": str(destination)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    make = sub.add_parser("create")
    make.add_argument("--output", type=Path, required=True)
    load = sub.add_parser("restore")
    load.add_argument("source", type=Path)
    load.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    result = create_seed(Database(get_settings()), args.output) if args.command == "create" else restore_seed(args.source, args.destination)
    print(json.dumps(result, indent=2))
