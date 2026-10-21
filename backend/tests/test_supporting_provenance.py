"""Historical date evidence travels with the numerical workbook."""
from observatory.analytics.common import source_refs
from observatory.db import Database, Revision, Snapshot
from observatory.provenance import snapshot_references
from observatory.settings import Settings


def test_dating_proof_resolves_only_exact_source_url_digest_and_pinned_revision(tmp_path):
    database = Database(Settings(tmp_path))
    with database.session() as session:
        revision = Revision(reason="Explicit synthetic provenance fixture")
        session.add(revision)
        session.flush()
        bound = revision.id
        row = Snapshot(source_id="synthetic-date-source", url="https://fixture.invalid/dating-release", sha256="1" * 64,
            path="synthetic-test-only", content_type="text/html", retrieved_at="2026-10-21T12:00:00Z",
            byte_count=1, revision=bound)
        session.add(row)
        session.flush()
        proof_id = row.id
        session.commit()
    refs = source_refs([{"source_id": "synthetic-date-source", "snapshot_id": 999,
        "metadata": {"dating_context_url": "https://fixture.invalid/dating-release",
            "dating_context_sha256": "1" * 64}}])
    proof = next(r for r in refs if r.get("role") == "dating_context")
    assert "snapshot_id" not in proof
    actual = snapshot_references(database, refs, bound)
    assert next(r for r in actual if r.get("role") == "dating_context")["snapshot_id"] == proof_id
    assert "snapshot_id" not in snapshot_references(database, [proof], 0)[0]
    assert "snapshot_id" not in snapshot_references(database, [{**proof, "sha256": "2" * 64}], bound)[0]
    assert "snapshot_id" not in snapshot_references(database, [{**proof, "source_id": "different-source"}], bound)[0]
