"""Integration evidence workflows using explicitly synthetic public aggregates.

The HTTP transport alone is replaced: the real content-addressed Fetcher,
collector, SQLite store, analytical services, API, exports, and backup code run.
No fixture is installed in the user's application data or live source registry.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import zipfile
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient
from observatory import archive, collector, connectors, service
from observatory.api import create_app
from observatory.cli import backup, restore
from observatory.db import Correction, Revision
from observatory.domain import Observation, ParsedBatch, Poll
from observatory.settings import Settings
from sqlalchemy import select

LOCAL_ORIGIN = {"Origin": "http://127.0.0.1:8776"}
BASE_QUERY = {"state": "NC", "metric": "ballots_cast", "mode": "all", "cycle": 2026, "baseline": 2022}


def aggregate(value=100, *, date="2026-10-20", cycle=2026, name="North Carolina", geo="NC", kind="state", published_at=None):
    return {"state": "NC", "cycle": cycle, "election_date": "2026-11-03" if cycle == 2026 else "2022-11-08",
            "date": date, "metric": "ballots_cast", "value": value, "geography_id": geo,
            "geography_name": name, "geography_type": kind, "published_at": published_at or date + "T12:00:00-04:00"}


def survey(value=48, *, population="LV", question_type="vote_choice"):
    return {"study_id": "explicitly-synthetic-study", "state": "NC", "cycle": 2026,
            "producer": "Synthetic producer for integration testing", "publisher": "Synthetic publisher",
            "field_start": "2026-10-07", "field_end": "2026-10-09", "published_at": "2026-10-10T12:00:00-04:00",
            "population": population, "sample_size": 500, "question_type": question_type,
            "question": "Synthetic vote choice?" if question_type == "vote_choice" else "Synthetic winner expectation?",
            "source_url": "https://fixture.invalid/public-aggregate.json",
            "document_url": "https://fixture.invalid/public-aggregate.json",
            "estimates": [{"candidate": "Example A", "party": "DEM", "value": value},
                          {"candidate": "Example B", "party": "REP", "value": 45}]}


@pytest.fixture
def harness(tmp_path, monkeypatch):
    source = {"id": "synthetic-integration-source", "state": "NC", "name": "Synthetic public aggregate fixture",
              "url": "https://fixture.invalid/public-aggregate.json", "connector": "synthetic_test_only",
              "tier": 1, "enabled": True, "expected_hours": 2}
    state = SimpleNamespace(now="2026-10-20T16:00:00+00:00", payload={"observations": [aggregate()], "polls": []},
                            status=200, calls=[], include_counties=True)
    real_fetcher = archive.Fetcher

    def transport(request):
        assert str(request.url) == source["url"]
        state.calls.append(str(request.url))
        return httpx.Response(state.status, json=state.payload)

    def fetcher(settings, *, offline=False, document_cache=None):
        result = real_fetcher(settings, offline=offline)
        result.client.close()
        result.client = httpx.Client(transport=httpx.MockTransport(transport), follow_redirects=True)
        return result

    def adapter(source, fetcher):
        document = fetcher.fetch(source["url"])
        payload = json.loads(Path(document.path).read_text())
        observations = []
        for row in payload.get("observations", []):
            if not state.include_counties and row.get("geography_type") == "county":
                continue
            observations.append(Observation(**row, metadata={"source_url": document.url,
                "fixture": "Explicitly synthetic test data; never installed in the application",
                "original_cell": str(row["value"]), "retrieved_at": document.retrieved_at}))
        return ParsedBatch(observations=observations, polls=[Poll(**p) for p in payload.get("polls", [])],
                           data_as_of="2026-10-20")

    monkeypatch.setattr(collector, "Fetcher", fetcher)
    monkeypatch.setattr(connectors, "collect", adapter)
    monkeypatch.setattr(collector, "sources", lambda: [source])
    monkeypatch.setattr(service, "sources", lambda: [source])
    monkeypatch.setattr(archive, "utc_now", lambda: state.now)
    monkeypatch.setattr(collector, "utc_now", lambda: state.now)
    settings = Settings(tmp_path / "data")
    app = create_app(settings)
    database = app.state.database

    def collect(*, now=None, offline=False):
        if now:
            state.now = now
        result = collector.collect_sources(database, source_ids=[source["id"]], offline=offline)
        with database.session() as session:
            for revision in session.scalars(select(Revision)):
                if revision.created_at > state.now:
                    revision.created_at = state.now
            session.commit()
        return result

    with TestClient(app) as client:
        yield SimpleNamespace(client=client, database=database, settings=settings, state=state, source=source,
                              collect=collect, monkeypatch=monkeypatch, root=tmp_path)
    database.engine.dispose()


def workspace(harness, **params):
    response = harness.client.get("/api/v1/workspace", params={**BASE_QUERY, **params})
    assert response.status_code == 200, response.text
    return response.json()


def csv_rows(response):
    assert response.status_code == 200, response.text
    return list(csv.DictReader(io.StringIO(response.content.decode("utf-8-sig"))))


def test_collect_archive_inspect_export_save_and_restore_exact_view(harness):
    first = harness.collect()
    assert first["observations_added"] == 1
    view = workspace(harness, revision=first["revision"])
    assert view["summary"]["total"] == 100
    assert view["series"][-1]["value"] == 100
    observation = view["observations"][0]
    evidence = harness.client.get(f"/api/v1/evidence/{observation['id']}").json()
    archived = harness.client.get(f"/api/v1/documents/{observation['snapshot_id']}")
    assert hashlib.sha256(archived.content).hexdigest() == evidence["snapshot"]["sha256"]
    assert json.loads(archived.content)["observations"][0]["value"] == 100
    assert "path" not in evidence["snapshot"]
    assert archived.headers["content-security-policy"] == "sandbox"

    saved = harness.client.post("/api/v1/research", headers=LOCAL_ORIGIN,
        json={"kind": "view", "title": "Exact synthetic evidence", "view": view["query"]}).json()
    assert saved["view"]["revision"] == first["revision"]
    harness.state.payload["observations"][0]["value"] = 140
    second = harness.collect(now="2026-10-21T16:00:00+00:00")
    assert second["revision"] > first["revision"]
    assert workspace(harness, as_of="2026-10-22")["summary"]["total"] == 140
    reopened = workspace(harness, **{k: v for k, v in saved["view"].items() if k not in BASE_QUERY and v is not None})
    assert reopened["summary"]["total"] == 100

    export_params = {**BASE_QUERY, "revision": first["revision"], "format": "csv"}
    rows = csv_rows(harness.client.get("/api/v1/exports", params=export_params))
    assert [float(r["value"]) for r in rows] == [100]
    bundle = harness.client.get("/api/v1/exports", params={**export_params, "format": "zip"})
    with zipfile.ZipFile(io.BytesIO(bundle.content)) as z:
        manifest = json.loads(z.read("manifest.json"))
        packaged = json.loads(z.read("workspace.json"))
        assert manifest["revision"] == first["revision"]
        assert packaged["summary"]["total"] == 100
        assert manifest["source_snapshots"][0]["sha256"] == evidence["snapshot"]["sha256"]
        assert "path" not in manifest["source_snapshots"][0]
        assert set(z.namelist()) == {"observations.csv", "workspace.json", "manifest.json", "report.html", "README.txt"}

    model_dir = harness.settings.data_dir / "model-runs" / "ev-research"
    model_dir.mkdir(parents=True, exist_ok=True)
    model_bytes = b'{"test_fixture":"Explicitly synthetic frozen aggregate manifest"}'
    (model_dir / "r0-fixture.json").write_bytes(model_bytes)
    (model_dir / "r999999-future.json").write_bytes(b'{"future_revision":"not_in_this_backup"}')
    backup_path = backup(harness.database, harness.root / "backup.zip")
    destination = harness.root / "restored"
    restored = restore(backup_path, destination)
    assert restored["integrity"] == "ok" and restored["archives_verified"] == 2
    assert restored["model_runs_verified"] == 1
    assert (destination / "model-runs" / "ev-research" / "r0-fixture.json").read_bytes() == model_bytes
    assert not (destination / "model-runs" / "ev-research" / "r999999-future.json").exists()
    restored_app = create_app(Settings(destination))
    with TestClient(restored_app) as client:
        research = client.get("/api/v1/research", params={"kind": "view"}).json()["items"]
        assert research[0]["view"] == saved["view"]
        result = client.get("/api/v1/workspace", params=export_params).json()
        assert result["summary"]["total"] == 100
        restored_bytes = client.get(f"/api/v1/documents/{observation['snapshot_id']}").content
        assert hashlib.sha256(restored_bytes).hexdigest() == evidence["snapshot"]["sha256"]
    restored_app.state.database.engine.dispose()


def test_cutoff_uses_old_observation_and_poll_revisions(harness):
    harness.state.payload["polls"] = [survey(), survey(50, population="RV"), survey(52, question_type="winner_expectation")]
    harness.collect(now="2026-10-20T16:00:00+00:00")
    harness.state.payload["observations"][0]["value"] = 160
    harness.state.payload["polls"][0]["estimates"][0]["value"] = 49
    harness.collect(now="2026-10-22T16:00:00+00:00")
    old = workspace(harness, as_of="2026-10-20")
    assert old["summary"]["total"] == 100
    assert len(old["polls"]) == 3
    poll = next(p for p in old["polls"] if p["population"] == "LV" and p["question_type"] == "vote_choice")
    assert poll["estimates"][0]["value"] == 48
    newer = workspace(harness, as_of="2026-10-23")
    assert newer["summary"]["total"] == 160
    poll = next(p for p in newer["polls"] if p["population"] == "LV" and p["question_type"] == "vote_choice")
    assert poll["estimates"][0]["value"] == 49


def test_narrative_hypothetical_pairings_survive_generic_labels_and_label_improvements(harness):
    first, second = survey(), survey()
    for record in (first, second):
        record["question"] = "Synthetic narrative Senate preference"
        record["ballot_type"] = "hypothetical"
        record["metadata"] = {"question_wording_exact": False}
    second["estimates"][0]["candidate"] = "Example C"
    harness.state.payload["polls"] = [first, second]
    pinned = harness.collect()
    assert len(harness.database.polls()) == 2
    first["question"] += ": Example A / Example B"
    second["question"] += ": Example C / Example B"
    harness.collect(now="2026-10-22T16:00:00+00:00")
    current = harness.database.polls()
    assert len(current) == 2
    assert {p["estimates"][0]["candidate"] for p in current} == {"Example A", "Example C"}
    assert len(harness.database.polls(revision=pinned["revision"])) == 2


def test_manual_correction_respects_revision_and_creation_timestamp(harness):
    first = harness.collect()
    observation = workspace(harness)["observations"][0]
    response = harness.client.post("/api/v1/corrections", headers=LOCAL_ORIGIN,
        json={"observation_id": observation["id"], "replacement": 120, "reason": "Synthetic audit correction"})
    assert response.status_code == 201
    with harness.database.session() as session:
        correction = session.get(Correction, response.json()["id"])
        correction.created_at = "2026-10-22T16:00:00+00:00"
        session.commit()
    assert workspace(harness, as_of="2026-10-21")["summary"]["total"] == 100
    assert workspace(harness, as_of="2026-10-23")["summary"]["total"] == 120
    assert workspace(harness, as_of="2026-10-23", revision=first["revision"])["summary"]["total"] == 100
    audit = harness.client.get(f"/api/v1/evidence/{observation['id']}").json()
    assert audit["observation"]["value"] == 100
    assert audit["corrections"][0]["original"] == 100
    assert audit["corrections"][0]["replacement"] == 120


def test_baseline_csv_and_bundle_exclude_future_aligned_information(harness):
    harness.state.payload["observations"] += [aggregate(70, cycle=2022, date="2022-10-24"),
                                              aggregate(90, cycle=2022, date="2022-10-26")]
    harness.collect()
    view = workspace(harness, as_of="2026-10-20")
    assert all(p["date"] <= "2022-10-25" for p in view["series"] if p["cycle"] == 2022)
    params = {**BASE_QUERY, "as_of": "2026-10-20", "format": "csv"}
    rows = csv_rows(harness.client.get("/api/v1/exports", params=params))
    assert {r["date"] for r in rows if r["cycle"] == "2022"} == {"2022-10-24"}
    zipped = harness.client.get("/api/v1/exports", params={**params, "format": "zip"})
    with zipfile.ZipFile(io.BytesIO(zipped.content)) as z:
        assert "2022-10-26" not in z.read("observations.csv").decode("utf-8-sig")
        selected = json.loads(z.read("workspace.json"))["observations"]
        assert not any(r["cycle"] == 2022 and r["date"] == "2022-10-26" for r in selected)


def test_unchanged_bytes_reparse_when_connector_signature_changes(harness):
    harness.state.payload["observations"].append(aggregate(100, name="Synthetic County", geo="NC:SYNTHETIC", kind="county"))
    harness.state.include_counties = False
    first = harness.collect()
    unchanged = harness.collect(now="2026-10-21T16:00:00+00:00")
    assert unchanged["sources"][0]["status"] == "unchanged"
    assert unchanged["revision"] == first["revision"]
    harness.state.include_counties = True
    original = Path.read_bytes
    connector_file = Path(connectors.__file__).parent / "common.py"

    def revised_parser_bytes(path):
        data = original(path)
        return data + b"\n# synthetic parser-signature test\n" if path == connector_file else data

    harness.monkeypatch.setattr(Path, "read_bytes", revised_parser_bytes)
    updated = harness.collect(now="2026-10-22T16:00:00+00:00")
    assert updated["revision"] > first["revision"]
    assert updated["observations_added"] == 1
    assert workspace(harness, as_of="2026-10-23")["geographies"][0]["name"] == "Synthetic County"


def test_failed_refresh_retains_evidence_and_offline_replay(harness):
    first = harness.collect()
    before = workspace(harness)["summary"]["total"]
    harness.state.status = 500
    failure = harness.collect(now="2026-10-21T16:00:00+00:00")
    assert failure["sources"][0]["status"] == "failed"
    assert failure["revision"] == first["revision"]
    assert workspace(harness)["summary"]["total"] == before
    assert harness.client.get("/api/v1/sources").json()["sources"][0]["status"] == "failed"
    count = len(harness.state.calls)
    replay = harness.collect(offline=True)
    assert replay["sources"][0]["status"] == "unchanged"
    assert len(harness.state.calls) == count


def test_report_escapes_research_text_and_writes_require_local_origin(harness):
    harness.state.payload["observations"].append(aggregate(100, name="<img src=x onerror=alert(1)>", geo="NC:ESCAPE", kind="county"))
    harness.collect()
    note = {"kind": "note", "title": "<script>alert(1)</script>", "body": "<img src=x onerror=alert(2)>"}
    denied = harness.client.post("/api/v1/research", headers={"Origin": "https://unrelated.invalid"}, json=note)
    assert denied.status_code == 403
    assert harness.client.get("/api/v1/research").json()["items"] == []
    accepted = harness.client.post("/api/v1/research", headers=LOCAL_ORIGIN, json=note)
    assert accepted.status_code == 201
    report = harness.client.get("/api/v1/exports", params={**BASE_QUERY, "format": "html", "include_notes": True})
    assert report.status_code == 200
    assert "<script>alert(1)</script>" not in report.text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in report.text
    assert "<img src=x onerror" not in report.text
    assert "&lt;img src=x onerror" in report.text
    assert report.headers["x-content-type-options"] == "nosniff"


def test_composed_reports_keep_section_order_privacy_and_poll_snapshot_hashes(harness):
    harness.state.payload['polls'] = [survey()]
    harness.collect()
    pinned = workspace(harness)['query']
    body = {'query': pinned, 'format': 'html', 'title': 'A <custom> research report',
            'note': 'Private interpretation must be opt-in', 'sections': ['polls', 'voting'], 'include_notes': False}
    response = harness.client.post('/api/v1/exports', headers=LOCAL_ORIGIN, json=body)
    assert response.status_code == 200, response.text
    assert 'A &lt;custom&gt; research report' in response.text
    assert response.text.index("data-section='polls'") < response.text.index("data-section='voting'")
    assert "data-section='geography'" not in response.text
    assert 'Private interpretation must be opt-in' not in response.text
    assert '<svg ' in response.text and '<polyline ' in response.text
    pdf = harness.client.post('/api/v1/exports', headers=LOCAL_ORIGIN, json={**body, 'format': 'pdf', 'include_notes': True})
    assert pdf.status_code == 200 and pdf.content.startswith(b'%PDF-')
    from pypdf import PdfReader
    text = '\n'.join(page.extract_text() for page in PdfReader(io.BytesIO(pdf.content)).pages)
    assert 'A <custom> research report' in text
    assert 'Private interpretation must be opt-in' in text
    assert 'Geographic observations' not in text
    bundle = harness.client.post('/api/v1/exports', headers=LOCAL_ORIGIN, json={**body, 'format': 'zip'})
    with zipfile.ZipFile(io.BytesIO(bundle.content)) as z:
        manifest = json.loads(z.read('manifest.json'))
        assert manifest['report']['sections'] == ['polls', 'voting']
        assert manifest['report']['private_notes_included'] is False
        assert all(p['snapshot_id'] in {s['id'] for s in manifest['source_snapshots']} for p in json.loads(z.read('workspace.json'))['polls'])


def test_custom_loopback_port_accepts_same_origin_but_rejects_remote_origin(harness):
    body = {'kind':'note', 'title':'Local-port behavior', 'body':'Isolated integration fixture'}
    good = harness.client.post('http://127.0.0.1:8777/api/v1/research', json=body,
                               headers={'Origin':'http://127.0.0.1:8777'})
    assert good.status_code == 201
    bad = harness.client.post('http://127.0.0.1:8777/api/v1/research', json=body,
                              headers={'Origin':'https://untrusted.invalid'})
    assert bad.status_code == 403


def test_report_manifest_regenerates_without_reentering_query(harness):
    from observatory.cli import main
    harness.collect()
    query = workspace(harness)['query']
    exported = harness.client.post('/api/v1/exports', headers=LOCAL_ORIGIN,
        json={'query':query,'format':'zip','title':'Pinned reproducibility check','sections':['voting']})
    package = harness.root/'research.zip'
    package.write_bytes(exported.content)
    output = harness.root/'regenerated.html'
    harness.monkeypatch.setenv('OBSERVATORY_DATA_DIR',str(harness.settings.data_dir))
    main(['reproduce',str(package),'--output',str(output)])
    assert 'Pinned reproducibility check' in output.read_text()
    assert "data-section='voting'" in output.read_text()
    assert "data-section='polls'" not in output.read_text()
    with pytest.raises(ValueError,match='already exists'):
        main(['reproduce',str(package),'--output',str(output)])
