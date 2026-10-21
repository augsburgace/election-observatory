from __future__ import annotations

import hashlib
import json
import sqlite3
import zipfile

import pytest
from observatory.db import Database, ObservationRecord, ResearchObject, Revision, Snapshot, SourceState
from observatory.settings import Settings

from scripts.public_seed import SCHEMA, create_seed, restore_seed


def test_public_checkpoint_excludes_private_rows_raw_archives_and_deleted_cells(tmp_path):
    database = Database(Settings(tmp_path / "private"))
    raw_marker = b"PRIVATE_VOTER_RECORD_SENTINEL"
    raw_hash = hashlib.sha256(raw_marker).hexdigest()
    raw_path = database.settings.archive_dir / raw_hash[:2] / raw_hash
    raw_path.parent.mkdir(parents=True)
    raw_path.write_bytes(raw_marker)
    with database.session() as session:
        rev = Revision(reason="Source collection")
        session.add(rev)
        session.flush()
        session.add(Snapshot(source_id="voter-file", url="https://example.org/voters.csv", sha256=raw_hash,
            path=str(raw_path), content_type="text/csv", retrieved_at="2026-10-21T12:00:00Z", byte_count=len(raw_marker), revision=rev.id))
        session.add(ResearchObject(kind="note", title="PRIVATE_NOTE_TITLE", body="PRIVATE_NOTE_BODY_SENTINEL"))
        session.add(SourceState(id="voter-file", error="PRIVATE_ERROR_SENTINEL /Users/private/file"))
        session.commit()
    output = tmp_path / "public.zip"
    result = create_seed(database, output)
    assert result["revision"] == 1
    with zipfile.ZipFile(output) as archive:
        assert set(archive.namelist()) == {"observatory.sqlite3", "manifest.json"}
        db_bytes = archive.read("observatory.sqlite3")
        assert b"PRIVATE_NOTE_BODY_SENTINEL" not in db_bytes
        assert b"PRIVATE_NOTE_TITLE" not in db_bytes
        assert b"PRIVATE_ERROR_SENTINEL" not in db_bytes
        assert raw_marker not in db_bytes
        assert json.loads(archive.read("manifest.json"))["schema"] == SCHEMA
    target = tmp_path / "restored"
    proof = restore_seed(output, target)
    assert proof["entries_verified"] == 1
    with sqlite3.connect(target / "observatory.sqlite3") as connection:
        assert connection.execute("SELECT COUNT(*) FROM research").fetchone()[0] == 0
        assert connection.execute("SELECT path FROM snapshots").fetchone()[0].startswith(str(target))
    with database.session() as session:
        assert session.query(ResearchObject).count() == 1
    assert raw_path.read_bytes() == raw_marker


def test_checkpoint_refuses_overwrite_and_nonempty_restore(tmp_path):
    database = Database(Settings(tmp_path / "private"))
    output = tmp_path / "public.zip"
    create_seed(database, output)
    with pytest.raises(ValueError, match="never overwritten"):
        create_seed(database, output)
    target = tmp_path / "nonempty"
    target.mkdir()
    (target / "keep.txt").write_text("keep")
    with pytest.raises(ValueError, match="must be empty"):
        restore_seed(output, target)


def test_all_geometry_metadata_is_sanitized_and_unchanged_bytes_are_preserved(tmp_path):
    database = Database(Settings(tmp_path / "private"))
    geometry = database.settings.data_dir / "geometry"
    geometry.mkdir()
    review = {"sources": [{"url": "https://example.org/county-boundaries.zip",
                           "archive_path": "/Users/private/original-boundaries.zip",
                           "description": "Verified against /Users/private/review.csv",
                           "nested": {"access_token": "PRIVATE_TOKEN_MARKER"}}]}
    original_review = json.dumps(review, indent=2).encode()
    (geometry / "county-boundary-review.json").write_bytes(original_review)
    unchanged = b'{\n  "source": "https://example.org/public", "vintage": "2024"\n}\n'
    (geometry / "manifest.json").write_bytes(unchanged)
    shape = b'{ "type": "FeatureCollection", "features": [] }\n'
    (geometry / "county.geojson").write_bytes(shape)
    output = tmp_path / "public.zip"
    create_seed(database, output)
    with zipfile.ZipFile(output) as archive:
        clean = archive.read("geometry/county-boundary-review.json")
        payload = json.loads(clean)
        assert "archive_path" not in payload["sources"][0]
        assert "access_token" not in payload["sources"][0]["nested"]
        assert b"/Users/private" not in clean and b"PRIVATE_TOKEN_MARKER" not in clean
        assert payload["sources"][0]["url"] == review["sources"][0]["url"]
        assert archive.read("geometry/manifest.json") == unchanged
        assert archive.read("geometry/county.geojson") == shape
        entries = json.loads(archive.read("manifest.json"))["entries"]
        for entry in entries:
            content = archive.read(entry["file"])
            assert hashlib.sha256(content).hexdigest() == entry["sha256"]
            assert len(content) == entry["bytes"]
    assert (geometry / "county-boundary-review.json").read_bytes() == original_review


def test_public_checkpoint_rejects_path_traversal(tmp_path):
    output = tmp_path / "bad.zip"
    payload = b"bad"
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("../escape", payload)
        archive.writestr("manifest.json", json.dumps({"schema": SCHEMA, "revision": 0,
            "entries": [{"file": "../escape", "sha256": hashlib.sha256(payload).hexdigest(), "bytes": 3}]}))
    with pytest.raises(ValueError, match="Unsafe"):
        restore_seed(output, tmp_path / "restore")
    assert not (tmp_path / "escape").exists()


def test_prior_deleted_notes_and_nested_secrets_cannot_survive_checkpoint(tmp_path):
    database = Database(Settings(tmp_path / "private"))
    deleted_marker = "OLD_DELETED_PRIVATE_NOTE_MARKER_bc134"
    with database.session() as session:
        rev = Revision(reason="Source collection")
        session.add(rev)
        session.flush()
        snapshot = Snapshot(source_id="aggregate", url="https://example.org/counts", sha256="a" * 64,
            path="/data/private/raw", content_type="text/csv", retrieved_at="2026-10-21T00:00:00Z", byte_count=0, revision=rev.id)
        session.add(snapshot)
        session.flush()
        session.add(ObservationRecord(logical_key="test", source_id="aggregate", snapshot_id=snapshot.id,
            revision=rev.id, observed_at="2026-10-21T00:00:00Z", state="OH", cycle=2026, date="2026-10-21",
            metric="ballots_cast", value=12, payload={"value": 12, "metadata": {
                "directory": "/data/PRIVATE_STORAGE_MARKER", "api_key": "PRIVATE_TOKEN_MARKER",
                "nested": {"corrections": [{"reason": "PRIVATE_CORRECTION_MARKER", "original": 11, "replacement": 12}]}}}))
        session.commit()
    with sqlite3.connect(database.settings.database_path) as connection:
        connection.execute("PRAGMA secure_delete=OFF")
        connection.execute("INSERT INTO research(kind,title,body,view,created_at,updated_at) VALUES('note','old',?,'{}','old','old')", (deleted_marker * 10000,))
        connection.commit()
        connection.execute("DELETE FROM research")
        connection.commit()
    output = tmp_path / "public.zip"
    create_seed(database, output)
    with zipfile.ZipFile(output) as archive:
        data = archive.read("observatory.sqlite3")
        for marker in (deleted_marker, "PRIVATE_STORAGE_MARKER", "PRIVATE_TOKEN_MARKER", "PRIVATE_CORRECTION_MARKER"):
            assert marker.encode() not in data
