from __future__ import annotations

import copy
import hashlib
import io
import json
import subprocess
import tarfile
import zipfile
from pathlib import Path

import pytest

from scripts import cloud_checkpoint as checkpoints


def public_seed(path: Path, revision: int = 588, *, private_rows: int = 0) -> Path:
    content = b"synthetic aggregate database fixture"
    manifest = {"schema": checkpoints.SEED_SCHEMA, "revision": revision,
        "private_notebook_rows": private_rows, "private_job_rows": 0,
        "entries": [{"file": "observatory.sqlite3", "bytes": len(content),
            "sha256": hashlib.sha256(content).hexdigest()}]}
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("observatory.sqlite3", content)
        archive.writestr("manifest.json", json.dumps(manifest))
    return path


def metadata(seed: Path, run: str = "100-1", revision: int = 588) -> dict:
    return {"schema": checkpoints.SCHEMA, "repository": checkpoints.REPOSITORY,
        "run_id": run, "revision": revision, "as_of": "2026-10-21",
        "created_at": "2026-10-21T20:00:00+00:00", "seed": {"file": checkpoints.SEED_NAME,
            "sha256": checkpoints._digest(seed), "bytes": seed.stat().st_size}}


def site(directory: Path, revision: int = 588) -> Path:
    (directory / "public-data").mkdir(parents=True)
    (directory / "index.html").write_text("<html>Public research</html>")
    (directory / "public-data" / "manifest.json").write_text(json.dumps({
        "dataset_revision": revision, "states": sorted(checkpoints.STATES)}))
    return directory


def release(value: dict, *, published: str = "2026-10-21T20:00:00Z", draft: bool = False) -> dict:
    files = {checkpoints.METADATA_NAME: json.dumps(value).encode()}
    assets = [{"name": checkpoints.SEED_NAME, "size": value["seed"]["bytes"], "state": "uploaded",
        "digest": "sha256:" + value["seed"]["sha256"]},
        {"name": checkpoints.METADATA_NAME, "size": len(files[checkpoints.METADATA_NAME]), "state": "uploaded"}]
    if "site" in value:
        assets.append({"name": checkpoints.SITE_NAME, "size": value["site"]["bytes"], "state": "uploaded",
            "digest": "sha256:" + value["site"]["sha256"]})
    return {"tag_name": checkpoints.PREFIX + value["run_id"], "draft": draft,
        "published_at": None if draft else published, "assets": assets}


class FakeGitHub:
    def __init__(self):
        self.calls = []
        self.releases = []
        self.files = {}
        self.fail_upload = False

    def add(self, value: dict, seed: Path, *, published: str = "2026-10-21T20:00:00Z",
            draft: bool = False, site_archive: Path | None = None):
        record = release(value, published=published, draft=draft)
        record["id"] = len(self.releases) + 1
        self.releases.append(record)
        tag = record["tag_name"]
        self.files[tag] = {checkpoints.METADATA_NAME: json.dumps(value).encode(),
            checkpoints.SEED_NAME: seed.read_bytes()}
        if site_archive is not None:
            self.files[tag][checkpoints.SITE_NAME] = site_archive.read_bytes()
        return record

    def __call__(self, arguments, *, timeout=120):
        self.calls.append(arguments)
        if arguments[:2] == ["api", f"repos/{checkpoints.REPOSITORY}/releases?per_page=100"]:
            return json.dumps([self.releases])
        if arguments[0] == "api":
            identity = arguments[1].rsplit("/", 1)[-1]
            if "/releases/tags/" in arguments[1]:
                record = next(value for value in self.releases if value["tag_name"] == identity)
                if record["draft"]:
                    raise ValueError("Synthetic GitHub 404: draft has no tag yet")
            else:
                record = next(value for value in self.releases if value["id"] == int(identity))
            return json.dumps(record)
        command, tag = arguments[1:3]
        if command == "download":
            name = arguments[arguments.index("--pattern") + 1]
            directory = Path(arguments[arguments.index("--dir") + 1])
            if name not in self.files[tag]:
                raise ValueError("Synthetic missing asset")
            (directory / name).write_bytes(self.files[tag][name])
        elif command == "create":
            if any(value["tag_name"] == tag for value in self.releases):
                raise ValueError("Synthetic existing immutable release")
            self.releases.append({"id": len(self.releases) + 1, "tag_name": tag,
                "draft": True, "published_at": None, "assets": []})
            self.files[tag] = {}
        elif command == "upload":
            if self.fail_upload:
                raise ValueError("Synthetic failed upload")
            record = next(value for value in self.releases if value["tag_name"] == tag)
            for name in arguments[3:arguments.index("--repo")]:
                path = Path(name)
                data = path.read_bytes()
                self.files[tag][path.name] = data
                record["assets"].append({"name": path.name, "state": "uploaded", "size": len(data),
                    "digest": "sha256:" + hashlib.sha256(data).hexdigest()})
        elif command == "edit":
            record = next(value for value in self.releases if value["tag_name"] == tag)
            record.update(draft=False, published_at="2026-10-21T22:00:00Z")
        elif command == "delete":
            self.releases = [value for value in self.releases if value["tag_name"] != tag]
            del self.files[tag]
        else:
            raise AssertionError(arguments)
        return ""


@pytest.fixture
def github(monkeypatch):
    fake = FakeGitHub()
    monkeypatch.setattr(checkpoints, "_gh", fake)
    return fake


def test_publish_is_draft_until_complete_and_metadata_has_no_local_paths(tmp_path, github):
    seed = public_seed(tmp_path / "private-looking-source.zip")
    result = checkpoints.publish(seed, 588, "100-1", "2026-10-21", site=site(tmp_path / "site"))
    tag = result["release_tag"]
    assert result["metadata"]["repository"] == "augsburgace/election-observatory"
    assert str(tmp_path) not in json.dumps(result)
    assert github.releases[0]["draft"] is False
    assert set(github.files[tag]) == {checkpoints.SEED_NAME, checkpoints.METADATA_NAME, checkpoints.SITE_NAME}
    operations = [call[1] for call in github.calls if call[0] == "release"]
    assert operations == ["create", "upload", "edit"]
    assert "--latest=false" in github.calls[-2]
    assert ["api", f"repos/{checkpoints.REPOSITORY}/releases/1"] in github.calls
    # The fake returns 404 for a draft-by-tag read, matching the real bootstrap
    # failure. Only the post-publication confirmation may use this endpoint.
    tag_reads = [call for call in github.calls if call == ["api", f"repos/{checkpoints.REPOSITORY}/releases/tags/{tag}"]]
    assert len(tag_reads) == 1


def test_failed_upload_never_publishes_a_draft(tmp_path, github):
    github.fail_upload = True
    with pytest.raises(ValueError):
        checkpoints.publish(public_seed(tmp_path / "seed.zip"), 588, "100-1", "2026-10-21")
    assert github.releases[0]["draft"] is True
    assert not any(call[:2] == ["release", "edit"] for call in github.calls)


def test_publish_rejects_private_rows_before_any_github_operation(tmp_path, github):
    with pytest.raises(ValueError, match="sanitized"):
        checkpoints.publish(public_seed(tmp_path / "seed.zip", private_rows=1), 588, "100-1", "2026-10-21")
    assert github.calls == []


def test_seed_revision_and_extra_files_are_rejected(tmp_path):
    seed = public_seed(tmp_path / "seed.zip")
    with pytest.raises(ValueError):
        checkpoints.validate_seed(seed, 589)
    with zipfile.ZipFile(seed, "a") as archive:
        archive.writestr("private-notebook.json", "private")
    with pytest.raises(ValueError):
        checkpoints.validate_seed(seed, 588)


@pytest.mark.parametrize("replacement", [
    {"repository": "other/person"}, {"local_path": "/private/path"}, {"run_id": "../other"},
    {"revision": True}, {"as_of": "20261021"}, {"created_at": "2026-10-21T20:00:00"},
    {"seed": {"file": "../seed.zip", "bytes": 5, "sha256": "a" * 64}},
])
def test_metadata_rejects_other_repositories_paths_or_ambiguous_identity(tmp_path, replacement):
    value = metadata(public_seed(tmp_path / "seed.zip"))
    value.update(replacement)
    with pytest.raises(ValueError):
        checkpoints.validate_metadata(value)


def test_download_falls_back_after_corrupt_latest_and_ignores_drafts(tmp_path, github):
    seed = public_seed(tmp_path / "seed.zip")
    good = metadata(seed, "100-1")
    github.add(good, seed, published="2026-10-21T19:00:00Z")
    corrupt = metadata(seed, "101-1")
    github.add(corrupt, seed)
    github.files[checkpoints.PREFIX + "101-1"][checkpoints.SEED_NAME] = b"corrupt"
    github.add(metadata(seed, "102-1"), seed, draft=True)
    result = checkpoints.download(tmp_path / "download")
    assert result["release_tag"] == checkpoints.PREFIX + "100-1"
    assert result["seed"] == checkpoints.SEED_NAME
    assert (tmp_path / "download" / result["seed"]).read_bytes() == seed.read_bytes()
    assert all("102-1" not in str(call) for call in github.calls if call[0] != "api")


def test_download_verifies_matching_site_and_returns_relative_paths(tmp_path, github):
    seed = public_seed(tmp_path / "seed.zip")
    value = metadata(seed)
    packed = tmp_path / checkpoints.SITE_NAME
    value["site"] = checkpoints._pack_site(site(tmp_path / "source-site"), packed, 588)
    github.add(value, seed, site_archive=packed)
    result = checkpoints.download(tmp_path / "download", with_site=True)
    assert result["site"] == "site"
    assert (tmp_path / "download" / "site" / "index.html").is_file()
    assert str(tmp_path) not in json.dumps(result)


def test_with_site_refuses_seed_only_checkpoint(tmp_path, github):
    seed = public_seed(tmp_path / "seed.zip")
    github.add(metadata(seed), seed)
    with pytest.raises(ValueError, match="No completed"):
        checkpoints.download(tmp_path / "download", with_site=True)
    assert list((tmp_path / "download").iterdir()) == []


def test_exact_revision_download_finds_live_site_when_newer_checkpoint_was_not_deployed(tmp_path, github):
    older_seed = public_seed(tmp_path / "older.zip", revision=588)
    newer_seed = public_seed(tmp_path / "newer.zip", revision=590)
    github.add(metadata(older_seed, "older", 588), older_seed, published="2026-10-21T19:00:00Z")
    github.add(metadata(newer_seed, "newer", 590), newer_seed)
    result = checkpoints.download(tmp_path / "rollback", revision=588)
    assert result["revision"] == 588
    assert result["release_tag"] == checkpoints.PREFIX + "older"
    with pytest.raises(ValueError, match="No completed"):
        checkpoints.download(tmp_path / "missing", revision=589)


def test_exact_manifest_selects_live_site_among_same_revision_candidates(tmp_path, github):
    seed = public_seed(tmp_path / "seed.zip")
    older = metadata(seed, "older")
    newer = metadata(seed, "newer")
    original_site = site(tmp_path / "live-site")
    changed_site = site(tmp_path / "failed-candidate")
    manifest_path = changed_site / "public-data" / "manifest.json"
    manifest_path.write_text(json.dumps({**json.loads(manifest_path.read_text()), "published_at": "later"}))
    older_archive, newer_archive = tmp_path / "older.tar.gz", tmp_path / "newer.tar.gz"
    older["site"] = checkpoints._pack_site(original_site, older_archive, 588)
    newer["site"] = checkpoints._pack_site(changed_site, newer_archive, 588)
    github.add(older, seed, published="2026-10-21T19:00:00Z", site_archive=older_archive)
    github.add(newer, seed, site_archive=newer_archive)
    result = checkpoints.download(tmp_path / "rollback", with_site=True, revision=588,
        site_manifest_sha256=older["site"]["manifest_sha256"])
    assert result["release_tag"] == checkpoints.PREFIX + "older"
    assert checkpoints._digest(tmp_path / "rollback" / "site" / "public-data" / "manifest.json") == older["site"]["manifest_sha256"]
    with pytest.raises(ValueError, match="No completed"):
        checkpoints.download(tmp_path / "missing", with_site=True, site_manifest_sha256="f" * 64)


def test_manifest_selector_requires_site_and_valid_digest_before_network(tmp_path, github):
    with pytest.raises(ValueError, match="requires --with-site"):
        checkpoints.download(tmp_path / "no-site", site_manifest_sha256="a" * 64)
    with pytest.raises(ValueError, match="SHA-256"):
        checkpoints.download(tmp_path / "bad", with_site=True, site_manifest_sha256="wrong")
    assert github.calls == []


def test_rollback_extraction_checks_exact_manifest_not_only_revision(tmp_path):
    archive = tmp_path / "site.tar.gz"
    value = checkpoints._pack_site(site(tmp_path / "source"), archive, 588)
    value["manifest_sha256"] = "f" * 64
    with pytest.raises(ValueError, match="revision validation"):
        checkpoints._extract_site(archive, tmp_path / "extracted", 588, value)
    assert not (tmp_path / "extracted").exists()


@pytest.mark.parametrize("kind", ["traversal", "symlink", "hardlink", "duplicate", "oversized"])
def test_site_archive_rejects_unsafe_or_inconsistent_members(tmp_path, kind):
    archive_path = tmp_path / "unsafe.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        info = tarfile.TarInfo("../escape" if kind == "traversal" else "index.html")
        info.size = 1
        if kind in {"symlink", "hardlink"}:
            info.type = tarfile.SYMTYPE if kind == "symlink" else tarfile.LNKTYPE
            info.linkname = "../escape"
            info.size = 0
            archive.addfile(info)
        else:
            archive.addfile(info, io.BytesIO(b"x"))
            if kind == "duplicate":
                archive.addfile(info, io.BytesIO(b"x"))
    expected = {"files": 1, "expanded_bytes": 0 if kind == "oversized" else 1}
    with pytest.raises(ValueError, match="safe extraction"):
        checkpoints._extract_site(archive_path, tmp_path / "extracted", 588, expected)
    assert not (tmp_path / "escape").exists()
    assert not (tmp_path / "extracted").exists()


def test_pack_site_rejects_revision_mismatch_or_links(tmp_path):
    directory = site(tmp_path / "site")
    with pytest.raises(ValueError, match="matching"):
        checkpoints._pack_site(directory, tmp_path / "site.tar.gz", 589)
    (directory / "external").symlink_to(tmp_path / "something")
    with pytest.raises(ValueError, match="links"):
        checkpoints._pack_site(directory, tmp_path / "site.tar.gz", 588)


def test_prune_only_owned_verified_old_releases_and_protects_bootstrap(tmp_path, github):
    seed = public_seed(tmp_path / "seed.zip")
    for number in range(5):
        github.add(metadata(seed, f"{number}-1"), seed, published=f"2026-10-21T1{number}:00:00Z")
    bootstrap = github.add(metadata(seed, "bootstrap-588"), seed)
    unverified = github.add(metadata(seed, "unverified"), seed)
    del unverified["assets"][0]["digest"]
    unrelated = copy.deepcopy(bootstrap)
    unrelated["tag_name"] = "application-v1"
    github.releases.append(unrelated)
    result = checkpoints.prune(3)
    assert result["deleted"] == [checkpoints.PREFIX + "1-1", checkpoints.PREFIX + "0-1"]
    assert result["protected"] == [checkpoints.PREFIX + "bootstrap-588"]
    assert result["unverified_retained"] == [checkpoints.PREFIX + "unverified"]
    assert any(value["tag_name"] == "application-v1" for value in github.releases)
    assert all("--cleanup-tag" in call for call in github.calls if call[:2] == ["release", "delete"])


def test_prune_refuses_unsafe_retention_without_a_network_call(github):
    with pytest.raises(ValueError):
        checkpoints.prune(2)
    assert github.calls == []


def test_gh_uses_structured_arguments_and_never_repeats_auth_errors(monkeypatch):
    def fail(arguments, **options):
        assert arguments == ["gh", "api", f"repos/{checkpoints.REPOSITORY}/releases"]
        assert options["capture_output"] is True
        assert "shell" not in options and "env" not in options
        raise subprocess.CalledProcessError(1, arguments, stderr="TOKEN_PRIVATE_SENTINEL")

    monkeypatch.setattr(subprocess, "run", fail)
    with pytest.raises(ValueError) as caught:
        checkpoints._gh(["api", f"repos/{checkpoints.REPOSITORY}/releases"])
    assert "TOKEN_PRIVATE_SENTINEL" not in str(caught.value)
