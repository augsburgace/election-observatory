"""Conservative publication gate and small, non-evidence source-check receipts."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def application_digest(root: Path) -> str:
    """Hash rendering, parsing, configuration and dependency inputs, never Git status.

    Documentation, tests and bot status commits do not change the application.
    Explicit roots keep personal files, generated data and credentials out.
    """
    files = set()
    for directory in ("backend/observatory", "config", "migrations", "frontend/src", "frontend/public", "frontend/scripts"):
        base = root / directory
        if base.is_dir():
            files.update(path for path in base.rglob("*") if path.is_file()
                and "__pycache__" not in path.parts and "public-data" not in path.relative_to(base).parts)
    files.update(path for path in (root / "scripts").glob("*.py") if path.is_file())
    for name in ("pyproject.toml", "requirements.lock", "alembic.ini", "frontend/index.html",
                 "frontend/package.json", "frontend/pnpm-lock.yaml", "frontend/vite.config.ts",
                 "frontend/tsconfig.json", "frontend/pnpm-workspace.yaml"):
        path = root / name
        if path.is_file():
            files.add(path)
    digest = hashlib.sha256()
    for path in sorted(files):
        digest.update(path.relative_to(root).as_posix().encode() + b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def source_receipts(path: Path) -> list[dict]:
    """Only identifiers, hashes, operational status and clocks; never raw errors."""
    with sqlite3.connect(path) as connection:
        return [{"source_id": row[0], "document_hash": row[1], "checked_at": row[2], "status": row[3]}
            for row in connection.execute(
                "SELECT id,document_hash,last_checked,status FROM source_states ORDER BY id")]


def source_health_digest(path: Path) -> str:
    with sqlite3.connect(path) as connection:
        # ready/unchanged are equivalent successes. Check clocks are recorded
        # separately so a successful unchanged fetch does not rebuild the atlas.
        values = [{"id": row[0], "status": "available" if row[1] in {"ready", "partial", "unchanged"} else row[1],
                   "data_as_of": row[2], "warnings": json.loads(row[3] or "[]")}
            for row in connection.execute("SELECT id,status,data_as_of,warnings FROM source_states ORDER BY id")]
    return hashlib.sha256(json.dumps(values, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def publication_key(path: Path, root: Path, *, revision: int, as_of: str, base: str) -> dict:
    return {"schema": "observatory-publication-inputs-v1", "revision": revision,
        "as_of": as_of, "base": base, "application_sha256": application_digest(root),
        "source_health_sha256": source_health_digest(path)}


def publication_reasons(previous: dict, current: dict, *, force: bool = False) -> list[str]:
    reasons = ["Manual rebuild requested"] if force else []
    old = previous.get("publication_inputs") or {}
    for field, reason in (("schema", "Publication gate initialized"), ("revision", "Validated evidence changed"),
            ("as_of", "New research date"), ("base", "Application address changed"),
            ("application_sha256", "Application or source configuration changed"),
            ("source_health_sha256", "Source availability or caveats changed")):
        if old.get(field) != current[field]:
            reasons.append(reason)
    return reasons


def restore_check_clocks(path: Path, receipt: dict, *, checkpoint_sha256: str, revision: int) -> int:
    """Restore only due-check clocks tied to the exact immutable seed and source.

    Receipts can never change an observation, revision, warning or source status.
    Failed checks are retried next run rather than imposing the normal cadence.
    """
    if (receipt.get("schema") != "observatory-source-check-v1"
            or receipt.get("checkpoint_sha256") != checkpoint_sha256 or receipt.get("revision") != revision):
        return 0
    count = 0
    now = datetime.now(timezone.utc)
    with sqlite3.connect(path) as connection:
        for source in receipt.get("source_checks", []):
            if source.get("status") not in {"ready", "partial", "unchanged", "unavailable"}:
                continue
            try:
                checked = datetime.fromisoformat(source["checked_at"])
                if checked.tzinfo is None or checked > now:
                    continue
            except (KeyError, TypeError, ValueError):
                continue
            row = connection.execute("SELECT document_hash,last_checked FROM source_states WHERE id=?",
                (source.get("source_id"),)).fetchone()
            if not row or not row[0] or row[0] != source.get("document_hash"):
                continue
            if row[1] and datetime.fromisoformat(row[1]) >= checked:
                continue
            connection.execute("UPDATE source_states SET last_checked=? WHERE id=?",
                (source["checked_at"], source["source_id"]))
            count += 1
        connection.commit()
    return count
