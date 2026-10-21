from __future__ import annotations

import gzip
import hashlib
import json

import pytest

from scripts.prepare_web_site import prepare_site, verify_site
from scripts.public_object_packs import PublicObjectReader, pack_public_objects


def source_dist(tmp_path):
    dist = tmp_path / "dist"
    objects = dist / "public-data" / "objects" / "ab"
    objects.mkdir(parents=True)
    raw = json.dumps({"state": "OH", "revision": 574, "value": 1234}).encode()
    sha = hashlib.sha256(raw).hexdigest()
    name = "objects/ab/" + sha + ".json"
    (dist / "public-data" / name).write_bytes(raw)
    entry = {"path": name, "sha256": sha, "bytes": len(raw)}
    manifest = {"states": [f"S{i}" for i in range(50)], "dataset_revision": 574,
                "requests": {"/api/v1/workspace?state=OH": entry}, "objects": [entry]}
    (dist / "public-data" / "manifest.json").write_text(json.dumps(manifest))
    (dist / "index.html").write_text("<html>Actual application</html>")
    return dist, name, raw


def test_static_gzip_package_preserves_exact_aggregate_integrity(tmp_path):
    dist, name, raw = source_dist(tmp_path)
    output = tmp_path / "site"
    result = prepare_site(dist, output)
    assert result["states"] == 50 and result["objects_verified"] == 1
    manifest = json.loads((output / "public-data" / "manifest.json").read_text())
    assert PublicObjectReader(output / "public-data", manifest).read(name) == raw
    assert name in manifest["object_packs"] and not (output / "public-data" / name).exists()
    config = json.loads((output / "vercel.json").read_text())
    assert any(header["key"] == "Content-Encoding" and header["value"] == "gzip"
               for rule in config["headers"] for header in rule["headers"])


@pytest.mark.parametrize("filename", ["observatory.sqlite3", "evidence.sqlite", "evidence.db", ".env", ".env.production", ".env.local", "private.pem", "private.key"])
def test_static_artifact_rejects_private_runtime_files(tmp_path, filename):
    dist, _, _ = source_dist(tmp_path)
    (dist / filename).write_bytes(b"not public")
    with pytest.raises(ValueError, match="Private source"):
        prepare_site(dist, tmp_path / "site")


def test_tampered_aggregate_fails_before_publication(tmp_path):
    dist, name, _ = source_dist(tmp_path)
    output = tmp_path / "site"
    prepare_site(dist, output)
    manifest = json.loads((output / "public-data" / "manifest.json").read_text())
    descriptor = manifest["packs"][manifest["object_packs"][name]]
    (output / "public-data" / descriptor["path"]).write_bytes(gzip.compress(b'{"value":9999}'))
    with pytest.raises(ValueError, match="integrity"):
        verify_site(output)


def test_owned_partial_publication_directories_are_not_deployed(tmp_path):
    dist, _, _ = source_dist(tmp_path)
    for name in (".public-data-old-stage", "public-data.previous-123"):
        directory = dist / name
        directory.mkdir()
        (directory / "partial.json").write_text('{"partial":true}')
    output = tmp_path / "site"
    prepare_site(dist, output)
    assert not (output / ".public-data-old-stage").exists()
    assert not (output / "public-data.previous-123").exists()
    assert (dist / ".public-data-old-stage" / "partial.json").exists()


def test_github_pages_budget_is_checked_without_changing_evidence(tmp_path, monkeypatch):
    from scripts import prepare_web_site

    dist, name, raw = source_dist(tmp_path)
    output = tmp_path / "github-site"
    proof = prepare_site(dist, output, provider="github")
    assert proof["provider"] == "github" and (output / ".nojekyll").exists()
    manifest = json.loads((output / "public-data" / "manifest.json").read_text())
    assert PublicObjectReader(output / "public-data", manifest).read(name) == raw
    monkeypatch.setattr(prepare_web_site, "GITHUB_PAGES_MAX_BYTES", 1)
    with pytest.raises(ValueError, match="GitHub Pages"):
        verify_site(output, provider="github")


def test_unknown_host_cannot_bypass_publication_limits(tmp_path):
    dist, _, _ = source_dist(tmp_path)
    with pytest.raises(ValueError, match="Unsupported"):
        prepare_site(dist, tmp_path / "site", provider="unknown")


def test_pack_text_preserves_unicode_and_exact_original_bytes(tmp_path):
    dist, original, raw = source_dist(tmp_path)
    root = dist / "public-data"
    manifest = json.loads((root / "manifest.json").read_text())
    for number in range(8):
        value = json.dumps({"number": number, "county": "Doña Ana", "text": "<data> \"quote\"\\ slash"},
                           ensure_ascii=False, separators=(",", ":")).encode()
        sha = hashlib.sha256(value).hexdigest()
        name = f"objects/{sha[:2]}/{sha}.json.gz"
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(gzip.compress(value))
        manifest["objects"].append({"path": name, "sha256": sha, "bytes": path.stat().st_size})
    transport = pack_public_objects(root, manifest, max_objects=3)
    reader = PublicObjectReader(root, manifest)
    assert transport["packed_objects"] == 9 and transport["pack_files"] == 3
    assert reader.read(original) == raw
    assert len(manifest["objects"]) == 3
    assert set(reader.names()) == set(manifest["object_packs"])
    assert all(isinstance(index, int) for index in manifest["object_packs"].values())
    for name in reader.names():
        assert hashlib.sha256(reader.read(name)).hexdigest() == reader.expected_hash(name)


def test_unknown_or_misassigned_pack_members_are_rejected(tmp_path):
    dist, name, _ = source_dist(tmp_path)
    root = dist / "public-data"
    manifest = json.loads((root / "manifest.json").read_text())
    pack_public_objects(root, manifest)
    descriptor = manifest["packs"][0]
    container = {"objects": {name: '{"state":"OH"}', "objects/foreign.json": "{}"}}
    value = json.dumps(container).encode()
    (root / descriptor["path"]).write_bytes(gzip.compress(value))
    descriptor["sha256"] = hashlib.sha256(value).hexdigest()
    with pytest.raises(ValueError, match="undeclared"):
        PublicObjectReader(root, manifest).read(name)


def test_large_members_remain_standalone_and_all_reference_hashes_are_checked(tmp_path):
    dist, name, raw = source_dist(tmp_path)
    root = dist / "public-data"
    manifest = json.loads((root / "manifest.json").read_text())
    transport = pack_public_objects(root, manifest, max_member_bytes=1)
    assert transport["standalone_objects"] == 1 and manifest["object_packs"] == {}
    reader = PublicObjectReader(root, manifest)
    assert reader.read(name) == raw
    reader.verify_references({"$public_ref": name, "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)})
    with pytest.raises(ValueError, match="hash"):
        reader.verify_references({"$public_ref": name, "sha256": "0" * 64, "bytes": len(raw)})
    with pytest.raises(ValueError, match="unpublished"):
        reader.verify_references({"$public_ref": "objects/missing.json", "sha256": "0" * 64, "bytes": 1})
