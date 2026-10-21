"""Anonymous web traffic cannot read private records or change stored evidence."""
from __future__ import annotations

import hashlib
import io
import json
import zipfile
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from observatory.api import create_app
from observatory.db import Correction, Job, ObservationRecord, ResearchObject, Revision, Snapshot, SourceState
from observatory.public_access import MAX_BODY_BYTES, public_payload
from observatory.settings import Settings, get_settings
from pypdf import PdfReader
from sqlalchemy import func, select
from test_evidence_workflows import BASE_QUERY
from test_evidence_workflows import harness as harness

PRIVATE = "PRIVATE_SENTINEL_DO_NOT_PUBLISH_8ee59"
PUBLIC_URL = "https://fixture.invalid/public-aggregate.json"


@pytest.fixture
def public_app(harness):
    harness.collect()
    with harness.database.session() as session:
        note = ResearchObject(kind="note", title=PRIVATE, body=PRIVATE, view={"private": PRIVATE})
        session.add(note)
        observation = session.scalar(select(ObservationRecord))
        revision = Revision(reason="Synthetic correction fixture", created_at="2026-10-20T17:00:00+00:00")
        session.add(revision)
        session.flush()
        session.add(Correction(observation_id=observation.id, revision=revision.id, original=100,
            replacement=101, reason=PRIVATE, created_at="2026-10-20T17:00:00+00:00"))
        raw = PRIVATE.encode()
        path = harness.settings.archive_dir / "aa" / "synthetic-private-voter-file"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        snapshot = Snapshot(source_id="synthetic-private-raw", url="https://fixture.invalid/voters.txt",
            path=str(path), sha256=hashlib.sha256(raw).hexdigest(), content_type="text/plain",
            byte_count=len(raw), revision=revision.id, retrieved_at="2026-10-20T17:00:00+00:00")
        session.add(snapshot)
        state = session.get(SourceState, harness.source["id"])
        state.error = f"{PRIVATE}: failed to read /Users/private/secret.csv"
        state.last_checked = "2026-10-20T17:00:00+00:00"
        session.commit()
        ids = {"observation": observation.id, "snapshot": snapshot.id, "note": note.id}
    settings = Settings(harness.settings.data_dir, public_mode=True,
        allowed_hosts=("testserver", "public.example"), allowed_origins=("https://public.example",))
    app = create_app(settings)
    with TestClient(app) as client:
        yield SimpleNamespace(client=client, database=app.state.database, private=harness, ids=ids, app=app)
    app.state.database.engine.dispose()


def _count(database, model):
    with database.session() as session:
        return session.scalar(select(func.count()).select_from(model))


def _all_export_text(content: bytes, format: str) -> str:
    if format == "pdf":
        return "\n".join(page.extract_text() for page in PdfReader(io.BytesIO(content)).pages)
    if format == "zip":
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            return "\n".join(_all_export_text(archive.read(name), "pdf" if name.endswith(".pdf") else "text")
                for name in archive.namelist())
    return content.decode("utf-8-sig")


def test_private_notebook_archive_and_jobs_are_not_public(public_app):
    client = public_app.client
    for path in ("/api/v1/research", "/api/v1/research?kind=note", "/api/v1/jobs", "/api/v1/jobs/1",
                 f"/api/v1/documents/{public_app.ids['snapshot']}"):
        response = client.get(path)
        assert response.status_code == 403
        assert PRIVATE not in response.text
    search = client.get("/api/v2/search", params={"q": PRIVATE})
    assert search.status_code == 200
    assert search.json()["results"] == []
    # The local notebook is neither deleted nor silently emptied by public mode.
    private = public_app.private.client.get("/api/v1/research").json()
    assert any(item["title"] == PRIVATE for item in private["items"])


@pytest.mark.parametrize("origin", [None, "https://public.example", "https://hostile.invalid"])
def test_anonymous_writes_never_mutate_the_database(public_app, origin):
    models = (ResearchObject, Correction, Job, Revision)
    before = [_count(public_app.database, model) for model in models]
    headers = {"Origin": origin} if origin else {}
    writes = [
        ("POST", "/api/v1/research", {"kind": "note", "title": "anonymous"}),
        ("PUT", f"/api/v1/research/{public_app.ids['note']}", {"kind": "note", "title": "replacement"}),
        ("DELETE", f"/api/v1/research/{public_app.ids['note']}", None),
        ("POST", "/api/v1/corrections", {"observation_id": public_app.ids["observation"], "replacement": 0, "reason": "anonymous"}),
        ("POST", "/api/v1/refresh", {}),
        ("POST", "/api/v1/forecast/backtest", {"cases": [{}]}),
        ("POST", "/api/v2/datasets/national_core/load", {}),
        ("POST", "/api/v2/precincts/vest_2020_OH/load", {}),
    ]
    for method, path, body in writes:
        assert public_app.client.request(method, path, json=body, headers=headers).status_code == 403
    assert [_count(public_app.database, model) for model in models] == before


def test_aggregate_reads_preserve_values_hashes_and_hide_diagnostics(public_app):
    response = public_app.client.get("/api/v1/workspace", params=BASE_QUERY)
    assert response.status_code == 200
    value = response.json()
    assert value["summary"]["total"] == 101
    assert PRIVATE not in response.text and "/Users/private/" not in response.text
    evidence = public_app.client.get(f"/api/v1/evidence/{public_app.ids['observation']}")
    assert evidence.status_code == 200
    assert PRIVATE not in evidence.text
    assert evidence.json()["snapshot"]["url"] == PUBLIC_URL
    assert len(evidence.json()["snapshot"]["sha256"]) == 64
    assert "reason" not in evidence.json()["corrections"][0]
    bootstrap = public_app.client.get("/api/v1/bootstrap").json()
    assert bootstrap["app"]["public_read_only"] is True
    assert bootstrap["capabilities"]["collection"] is False
    assert bootstrap["capabilities"]["report_composition"] is True
    assert public_app.client.get("/api/v1/health").json()["local_only"] is False
    assert public_app.client.get("/api/v1/health", headers={"Host": "unexpected.invalid"}).status_code == 400


@pytest.mark.parametrize("format", ["csv", "json", "html", "pdf", "zip"])
def test_aggregate_exports_do_not_include_private_notebook_or_correction_notes(public_app, format):
    response = public_app.client.get("/api/v1/exports", params={**BASE_QUERY, "format": format})
    assert response.status_code == 200, response.text[:1000]
    text = _all_export_text(response.content, format)
    assert PRIVATE not in text and "/Users/private/" not in text
    assert public_app.client.get("/api/v1/exports", params={**BASE_QUERY, "format": format,
        "include_notes": "true"}).status_code == 403


@pytest.mark.parametrize("format", ["csv", "json", "html", "pdf", "zip"])
def test_public_report_builder_uses_sanitized_document(public_app, format):
    body = {"title": "Public aggregate report", "query": BASE_QUERY,
            "sections": [{"id": "summary"}, {"id": "ev_trajectory"}, {"id": "evidence"}]}
    response = public_app.client.post("/api/v2/reports/exports", params={"format": format}, json=body)
    assert response.status_code == 200, response.text[:1000]
    text = _all_export_text(response.content, format)
    assert PRIVATE not in text and "/Users/private/" not in text
    assert public_app.client.post("/api/v2/reports/preview", json={**body,
        "include_notes": True, "notes": PRIVATE}).status_code == 422


def test_pure_scenarios_and_bounded_reports_still_work(public_app):
    before = _count(public_app.database, ResearchObject)
    response = public_app.client.post("/api/v1/scenarios/senate", json={"holdovers": {"D": 45, "R": 49},
        "races": [{"race_id": "synthetic-senate", "winner_caucus": "D"}]})
    assert response.status_code == 200
    assert response.json()["assigned_seats"] == {"D": 46, "R": 49, "other": 0}
    too_large = public_app.client.post("/api/v2/reports/preview", content=b"x" * (MAX_BODY_BYTES + 1),
        headers={"Content-Type": "application/json"})
    assert too_large.status_code == 413
    nested_notes = public_app.client.post("/api/v1/exports", json={"query": BASE_QUERY,
        "include_notes": True, "note": PRIVATE})
    assert nested_notes.status_code == 422
    assert _count(public_app.database, ResearchObject) == before


def test_public_errors_and_recursive_sources_do_not_expose_private_storage(public_app, monkeypatch):
    import observatory.api as api
    def failure(*args, **kwargs):
        raise ValueError(f"{PRIVATE}: /Users/private/raw.csv")
    monkeypatch.setattr(api, "workspace", failure)
    response = public_app.client.get("/api/v1/workspace", params=BASE_QUERY)
    assert response.status_code == 422
    assert PRIVATE not in response.text and "/Users/" not in response.text
    sanitized = public_payload({"sources": [{"source_url": PUBLIC_URL, "sha256": "a" * 64,
        "archive_path": "/Users/private/raw", "nested": {"directory": "/tmp/private"}}],
        "correction": {"original": 1, "replacement": 2, "reason": PRIVATE}, "error": PRIVATE})
    assert sanitized["sources"][0]["source_url"] == PUBLIC_URL
    assert sanitized["sources"][0]["sha256"] == "a" * 64
    assert PRIVATE not in json.dumps(sanitized)
    assert "archive_path" not in json.dumps(sanitized)
    assert sanitized["correction"] == {"original": 1, "replacement": 2}


def test_json_sanitization_precedes_gzip(public_app, monkeypatch):
    import observatory.api as api
    monkeypatch.setattr(api, "source_inventory", lambda database: [{"id": "aggregate-fixture",
        "url": PUBLIC_URL, "error": PRIVATE, "description": "Public coverage information. " * 200,
        "lineage": [{"archive_path": "/Users/private/marker.csv", "sha256": "b" * 64}]}])
    response = public_app.client.get("/api/v1/sources", headers={"Accept-Encoding": "gzip"})
    assert response.status_code == 200
    assert response.headers["content-encoding"] == "gzip"
    assert PRIVATE not in response.text and "/Users/private/" not in response.text
    assert response.json()["sources"][0]["lineage"] == [{"sha256": "b" * 64}]


def test_public_configuration_is_explicit_and_local_defaults_survive(monkeypatch, tmp_path):
    for name in ("OBSERVATORY_PUBLIC_MODE", "OBSERVATORY_ALLOWED_HOSTS", "OBSERVATORY_ALLOWED_ORIGINS"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("OBSERVATORY_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("OBSERVATORY_PROJECT_ROOT", str(tmp_path / "portable-project"))
    assert get_settings().public_mode is False
    assert get_settings().project_root == tmp_path / "portable-project"
    monkeypatch.setenv("OBSERVATORY_PUBLIC_MODE", "true")
    with pytest.raises(ValueError, match="ALLOWED_HOSTS"):
        get_settings()
    monkeypatch.setenv("OBSERVATORY_ALLOWED_HOSTS", "public.example,localhost")
    settings = get_settings()
    assert settings.public_mode and settings.allowed_hosts == ("public.example", "localhost")
    assert settings.allowed_origins == ()
    monkeypatch.setenv("OBSERVATORY_ALLOWED_HOSTS", "*")
    with pytest.raises(ValueError, match="host allowlist"):
        get_settings()
