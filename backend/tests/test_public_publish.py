"""Publication tests use isolated synthetic aggregates; no live evidence is changed."""
from __future__ import annotations

import gzip
import hashlib
import json

import pytest
from observatory.atlas.models import ensure_schema
from observatory.db import Database, ObservationRecord, ResearchObject, Revision, Snapshot, observation_key
from observatory.domain import Observation
from observatory.public_publish import (
    Publication,
    _evidence,
    canonical_request,
    publish_public_data,
    readonly_database,
)
from observatory.settings import Settings
from sqlalchemy import text


def read_object(path):
    content = path.read_bytes()
    return gzip.decompress(content) if path.name.endswith(".gz") else content


def synthetic_database(tmp_path):
    database = Database(Settings(tmp_path / "private"))
    ensure_schema(database)
    with database.session() as session:
        revision = Revision(reason="Synthetic publication test", created_at="2026-10-20T12:00:00+00:00")
        session.add(revision)
        session.flush()
        snapshot = Snapshot(source_id="synthetic-publication", url="https://fixture.invalid/aggregate.csv",
            sha256="0" * 64, path=str(tmp_path / "private" / "raw-voters.txt"), content_type="text/csv",
            retrieved_at="2026-10-20T12:00:00+00:00", byte_count=1, revision=revision.id)
        session.add(snapshot)
        session.flush()
        value = Observation(state="NH", cycle=2026, election_date="2026-11-03", date="2026-10-20",
            value=100, metric="ballots_cast", geography_id="NH", geography_name="New Hampshire",
            geography_type="state", published_at="2026-10-20T12:00:00+00:00").model_dump()
        session.add(ObservationRecord(logical_key=observation_key(value, "synthetic-publication"),
            source_id="synthetic-publication", snapshot_id=snapshot.id, revision=revision.id,
            observed_at="2026-10-20T12:00:00+00:00", state="NH", cycle=2026,
            date=value["date"], metric=value["metric"], value=value["value"], payload=value))
        session.add(ResearchObject(kind="note", title="PERSONAL SECRET SENTINEL", body="Never publish this"))
        session.commit()
    return database


def test_canonical_keys_preserve_scope_and_encoded_values():
    defaults = {"revision": 7, "mode": "all", "include_polls": False}
    key = canonical_request("/api/v2/results", {"state": "OH", "office": "US SENATE", "geography_ids": []}, defaults)
    assert key == "/api/v2/results?include_polls=false&mode=all&office=US+SENATE&revision=7&state=OH"
    assert canonical_request("/x?state=OH&revision=2", {}, {"revision": 7}) == "/x?revision=2&state=OH"
    assert canonical_request("/x", {"unsupported_filter": "yes"}) != "/x"


def test_content_addressing_deduplicates_and_scrubs_private_values(tmp_path):
    stage = tmp_path / "publication"
    stage.mkdir()
    publication = Publication(stage, revision=1, as_of="2026-10-21", settings=Settings(tmp_path / "private"), states=["OH"])
    payload = {"total": 25, "source": {"url": "https://official.example/results", "sha256": "abc"},
        "path": "/Users/name/secret", "error": "/Users/name/private-file.csv failed"}
    first = publication.response("/api/v1/example", {}, payload)
    second = publication.response("/api/v1/other", {}, payload)
    assert first == second
    assert len(publication.files) == 1
    content = read_object(stage / first["path"])
    assert hashlib.sha256(content).hexdigest() == first["sha256"]
    assert b"/Users" not in content and b"private-file" not in content
    assert json.loads(content)["source"]["url"] == "https://official.example/results"


def test_repeated_exact_geometry_is_compressed_once_without_changing_public_bytes(tmp_path, monkeypatch):
    from observatory import public_publish
    publication = Publication(tmp_path, revision=1, as_of="2026-10-21", settings=Settings(tmp_path), states=["NC"])
    geometry = {"type": "Polygon", "coordinates": [[[index / 10000, (index % 9) / 10000]
        for index in range(2500)]]}
    encoded = json.dumps(geometry, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()
    digest = hashlib.sha256(encoded).hexdigest()
    compress = gzip.compress
    expected_bytes = compress(encoded, compresslevel=6, mtime=0)
    assert len(expected_bytes) < len(encoded) * .95
    calls = []

    def counted(value, **kwargs):
        calls.append(hashlib.sha256(value).hexdigest())
        return compress(value, **kwargs)

    monkeypatch.setattr(public_publish.gzip, "compress", counted)
    first = publication._store(geometry)
    bytes_before = publication.bytes
    for _ in range(4):
        # A separately decoded object has identical evidence bytes; object
        # identity and mutable reference caching cannot satisfy this check.
        assert publication._store(json.loads(encoded)) == first
    assert calls == [digest]
    assert publication.bytes == bytes_before == len(expected_bytes)
    assert len(publication.files) == 1
    assert first == {"path": f"objects/{digest[:2]}/{digest}.json.gz", "sha256": digest,
        "bytes": len(expected_bytes), "uncompressed_bytes": len(encoded), "compression": "gzip"}
    assert (tmp_path / first["path"]).read_bytes() == expected_bytes


def test_shared_geometry_across_contest_overlays_skips_duplicate_compression(tmp_path, monkeypatch):
    from observatory import public_publish
    publication = Publication(tmp_path, revision=1, as_of="2026-10-21", settings=Settings(tmp_path), states=["NC"])
    coordinates = [[[index / 10000, (index % 9) / 10000] for index in range(2500)]]
    encoded = json.dumps(coordinates, separators=(",", ":"), ensure_ascii=False).encode()
    encoded_ring = json.dumps(coordinates[0], separators=(",", ":"), ensure_ascii=False).encode()
    compress = gzip.compress
    coordinate_compressions = 0

    def counted(value, **kwargs):
        nonlocal coordinate_compressions
        if value == encoded_ring:
            coordinate_compressions += 1
        return compress(value, **kwargs)

    monkeypatch.setattr(public_publish.gzip, "compress", counted)
    first = publication.object({"type": "Feature", "properties": {"contest": "A", "votes": 123},
        "geometry": {"type": "Polygon", "coordinates": coordinates}})
    second = publication.object({"type": "Feature", "properties": {"contest": "B", "votes": 456},
        "geometry": {"type": "Polygon", "coordinates": json.loads(encoded)}})
    assert first != second
    assert coordinate_compressions == 1


def test_publication_budget_failure_keeps_previous_bundle(tmp_path):
    database = synthetic_database(tmp_path)
    output = tmp_path / "public-data"
    output.mkdir()
    (output / "manifest.json").write_text('{"previous":true}')
    with pytest.raises(ValueError, match="limit|budget"):
        publish_public_data(database, output, states=["NH"], as_of="2026-10-21", replace=True,
            include_forecasts=False, include_results=False, include_reports=False,
            include_precincts=False, max_bytes=20, max_file_bytes=20)
    assert json.loads((output / "manifest.json").read_text()) == {"previous": True}
    assert not list(tmp_path.glob(".public-data-*"))


def test_exact_query_manifest_and_no_private_research(tmp_path):
    database = synthetic_database(tmp_path)
    output = tmp_path / "public-data"
    manifest = publish_public_data(database, output, states=["NH"], as_of="2026-10-21",
        include_forecasts=False, include_results=False, include_reports=False, include_precincts=False)
    defaults = manifest["request_defaults"]["/api/v1/workspace"]
    key = canonical_request("/api/v1/workspace", {"state": "NH"}, defaults)
    value = json.loads(read_object(output / manifest["requests"][key]["path"]))
    assert value["summary"]["total"] == 100
    assert value["query"]["revision"] == manifest["dataset_revision"] == 1
    different_cutoff = canonical_request("/api/v1/workspace", {"state": "NH", "as_of": "2026-10-19"}, defaults)
    assert different_cutoff not in manifest["requests"]
    geographic_filter = canonical_request("/api/v1/workspace", {"state": "NH", "geography_ids": ["county:33001"]}, defaults)
    assert geographic_filter not in manifest["requests"]
    assert manifest["states"] == ["NH"] and manifest["available_queries"]
    assert not any("research" in path for path in manifest["requests"])
    for descriptor in manifest["objects"]:
        content = read_object(output / descriptor["path"])
        assert b"PERSONAL SECRET SENTINEL" not in content and b"raw-voters.txt" not in content
        assert hashlib.sha256(content).hexdigest() == descriptor["sha256"]
    assert not any(key.startswith("/api/v1/evidence/") for key in manifest["requests"])
    assert manifest["evidence_bucket_size"] == 512
    descriptor = manifest["evidence_buckets"]["0"]
    bucket = json.loads(read_object(output / descriptor["path"]))
    assert set(bucket) == {"1"}
    detail = bucket["1"]
    assert detail["snapshot"]["url"] == "https://fixture.invalid/aggregate.csv"
    assert detail["snapshot"]["sha256"] == "0" * 64
    assert "path" not in detail["snapshot"]
    assert detail["history_available"] is False


def test_readonly_database_refuses_mutation(tmp_path):
    database = synthetic_database(tmp_path)
    read_only = readonly_database(database.settings)
    try:
        assert read_only.latest_revision() == 1
        with pytest.raises(Exception, match="readonly"):
            with read_only.engine.begin() as connection:
                connection.execute(text("DELETE FROM research"))
    finally:
        read_only.engine.dispose()


def test_conflicting_exact_request_is_rejected(tmp_path):
    publication = Publication(tmp_path, revision=1, as_of="2026-10-21", settings=Settings(tmp_path), states=["OH"])
    publication.response("/api/v1/workspace", {"state": "OH"}, {"total": 1})
    with pytest.raises(ValueError, match="Conflicting"):
        publication.response("/api/v1/workspace", {"state": "OH"}, {"total": 2})


def test_structural_sharing_roundtrips_without_losing_rows(tmp_path):
    publication = Publication(tmp_path, revision=1, as_of="2026-10-21", settings=Settings(tmp_path), states=["OH"])
    rows = [{"id": index, "votes": index * 5, "source": "https://example.invalid/" + "x" * 200}
            for index in range(300)]
    first = publication.object({"query": {"baseline": 2020}, "rows": rows, "source_context": rows})
    first_bytes = publication.bytes
    second = publication.object({"query": {"baseline": 2022}, "rows": rows, "source_context": rows})
    assert publication.bytes - first_bytes < 2000

    def resolve(value):
        if isinstance(value, dict) and "$public_ref" in value:
            content = read_object(tmp_path / value["$public_ref"])
            assert hashlib.sha256(content).hexdigest() == value["sha256"]
            return resolve(json.loads(content))
        if isinstance(value, dict) and "$public_chunks" in value:
            return [row for chunk in value["$public_chunks"] for row in resolve(chunk)]
        if isinstance(value, dict):
            return {key: resolve(item) for key, item in value.items()}
        if isinstance(value, list):
            return [resolve(item) for item in value]
        return value

    assert resolve(json.loads(read_object(tmp_path / first["path"])))["rows"] == rows
    assert resolve(json.loads(read_object(tmp_path / second["path"]))) == {
        "query": {"baseline": 2022}, "rows": rows, "source_context": rows}
    assert any(descriptor.get("compression") == "gzip" for descriptor in publication.files.values())


def test_file_count_budget_reuses_existing_objects_but_refuses_new_ones(tmp_path):
    publication = Publication(tmp_path, revision=1, as_of="2026-10-21", settings=Settings(tmp_path),
        states=["OH"], max_files=1)
    first = publication.object({"value": 1})
    assert publication.object({"value": 1}) == first
    with pytest.raises(ValueError, match="file-count"):
        publication.object({"value": 2})


def test_evidence_bucket_boundaries_never_substitute_a_neighbor(tmp_path):
    database = synthetic_database(tmp_path)
    publication = Publication(tmp_path / "objects", revision=1, as_of="2026-10-21",
        settings=database.settings, states=["NH"])
    original = database.observations(state="NH")[0]
    rows = {number: {**original, "id": number, "value": number} for number in (511, 512)}
    _evidence(database, publication, rows, [])
    assert set(publication.manifest["evidence_buckets"]) == {"0", "1"}
    for number, key in ((511, "0"), (512, "1")):
        descriptor = publication.manifest["evidence_buckets"][key]
        bucket = json.loads(read_object(publication.directory / descriptor["path"]))
        assert set(bucket) == {str(number)}
        assert bucket[str(number)]["observation"]["value"] == number
        assert str(number + 1) not in bucket
