from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest
from observatory.db import Database, SourceState
from observatory.settings import Settings

from scripts.cloud_changes import (
    application_digest,
    publication_key,
    publication_reasons,
    restore_check_clocks,
    source_health_digest,
    source_receipts,
)


@pytest.fixture
def evidence(tmp_path):
    settings = Settings(tmp_path / "evidence")
    database = Database(settings)
    with database.session() as session:
        session.add(SourceState(id="ohio", status="ready", document_hash="a" * 64,
            last_checked="2026-01-01T12:00:00+00:00", data_as_of="2026-01-01"))
        session.commit()
    database.engine.dispose()
    return settings.database_path


def test_bot_status_and_docs_do_not_trigger_builds_but_code_and_config_do(tmp_path):
    (tmp_path / "backend/observatory").mkdir(parents=True)
    code = tmp_path / "backend/observatory/service.py"
    code.write_text("VERSION = 1\n")
    original = application_digest(tmp_path)
    (tmp_path / "publication-state.json").write_text('{"revision": 593}')
    (tmp_path / "source-check-state.json").write_text('{"checked_at": "later"}')
    (tmp_path / "README.md").write_text("Operational notes")
    assert application_digest(tmp_path) == original
    code.write_text("VERSION = 2\n")
    assert application_digest(tmp_path) != original
    second = application_digest(tmp_path)
    (tmp_path / "config").mkdir()
    (tmp_path / "config/sources.json").write_text('{"source": "new"}')
    assert application_digest(tmp_path) != second


def test_unchanged_check_clock_does_not_change_health_but_failure_and_warning_do(evidence):
    original = source_health_digest(evidence)
    with sqlite3.connect(evidence) as connection:
        connection.execute("UPDATE source_states SET status='unchanged',last_checked='2026-01-02T12:00:00+00:00'")
    assert source_health_digest(evidence) == original
    with sqlite3.connect(evidence) as connection:
        connection.execute("UPDATE source_states SET status='failed',error='PRIVATE_RECORD_MARKER'")
    assert source_health_digest(evidence) != original
    assert "PRIVATE_RECORD_MARKER" not in json.dumps(source_receipts(evidence))
    with sqlite3.connect(evidence) as connection:
        connection.execute("UPDATE source_states SET status='partial',warnings='[\"Partial coverage\"]'")
    assert source_health_digest(evidence) != original


@pytest.mark.parametrize("field,value", [("revision", 594), ("as_of", "2026-10-22"),
    ("base", "/new-path/"), ("application_sha256", "new code"), ("source_health_sha256", "failure")])
def test_every_material_publication_input_prevents_false_unchanged_result(evidence, tmp_path, field, value):
    key = publication_key(evidence, tmp_path, revision=593, as_of="2026-10-21", base="/atlas/")
    previous = {"publication_inputs": key}
    assert not publication_reasons(previous, key)
    assert publication_reasons(previous, {**key, field: value})
    assert publication_reasons(previous, key, force=True)
    assert publication_reasons({}, key)


def test_receipts_restore_only_successful_clocks_for_exact_checkpoint_and_document(evidence):
    checked = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    receipt = {"schema": "observatory-source-check-v1", "revision": 593,
        "checkpoint_sha256": "b" * 64, "source_checks": [
            {"source_id": "ohio", "document_hash": "a" * 64, "checked_at": checked, "status": "unchanged"}]}
    assert restore_check_clocks(evidence, receipt, checkpoint_sha256="c" * 64, revision=593) == 0
    assert restore_check_clocks(evidence, receipt, checkpoint_sha256="b" * 64, revision=594) == 0
    source = receipt["source_checks"][0]
    for changes in ({"document_hash": "d" * 64}, {"status": "failed"}, {"checked_at": "bad date"},
                    {"checked_at": "2099-01-01T00:00:00+00:00"}, {"checked_at": "2026-01-01T00:00:00"}):
        invalid = {**receipt, "source_checks": [{**source, **changes}]}
        assert restore_check_clocks(evidence, invalid, checkpoint_sha256="b" * 64, revision=593) == 0
    assert restore_check_clocks(evidence, receipt, checkpoint_sha256="b" * 64, revision=593) == 1
    with sqlite3.connect(evidence) as connection:
        assert connection.execute("SELECT last_checked,status,data_as_of FROM source_states").fetchone() == (
            checked, "ready", "2026-01-01")
    assert restore_check_clocks(evidence, receipt, checkpoint_sha256="b" * 64, revision=593) == 0
