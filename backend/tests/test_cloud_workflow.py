from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import cloud_workflow


@pytest.fixture(autouse=True)
def isolated_runner_environment(monkeypatch):
    # Individual tests opt into Actions explicitly; the host must not change
    # which policy branch an otherwise local unit fixture exercises.
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)


def manifest(revision=588):
    return json.dumps({"dataset_revision": revision, "states": sorted(cloud_workflow.cloud_checkpoint.STATES)}).encode()


def test_rollback_identity_distinguishes_app_releases_at_same_evidence_revision():
    raw = manifest()
    changed = json.dumps({**json.loads(raw), "published_at": "2026-10-21T21:00:00Z"}).encode()
    assert cloud_workflow.manifest_identity(raw)["revision"] == cloud_workflow.manifest_identity(changed)["revision"]
    assert cloud_workflow.manifest_identity(raw) != cloud_workflow.manifest_identity(changed)
    assert cloud_workflow.manifest_identity(raw)["manifest_sha256"] == hashlib.sha256(raw).hexdigest()


def test_frontend_only_release_accepts_presentation_and_operational_changes():
    cloud_workflow.validate_shell_changes(["frontend/src/publicReports.ts", "frontend/pnpm-lock.yaml",
        "scripts/cloud_workflow.py", ".github/workflows/public-cloud.yml", "backend/tests/test_cloud_workflow.py",
        "publication-state.json", "source-check-state.json"])


@pytest.mark.parametrize("path", ["backend/observatory/early_vote.py", "config/sources.yaml",
    "scripts/update_cloud.py", "requirements.lock"])
def test_frontend_only_release_rejects_changes_to_evidence_or_calculations(path):
    with pytest.raises(ValueError, match="analytical or source changes"):
        cloud_workflow.validate_shell_changes(["frontend/src/publicReports.ts", path])


@pytest.mark.parametrize("revision", [True, -1, "588"])
def test_invalid_live_evidence_identity_is_rejected(revision):
    with pytest.raises(ValueError, match="invalid revision"):
        cloud_workflow.manifest_identity(manifest(revision))


def test_live_identity_rejects_duplicate_or_unknown_states():
    with pytest.raises(ValueError):
        cloud_workflow.manifest_identity(json.dumps({"dataset_revision": 588, "states": ["OH"] * 50}).encode())


def test_cloud_directory_cannot_target_personal_data():
    with pytest.raises(ValueError, match="Private local"):
        cloud_workflow.validate_directory(Path.home() / "Library/Application Support/Battleground Senate Observatory")


def test_actions_directories_must_belong_to_ephemeral_runner(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path / "runner"))
    with pytest.raises(ValueError, match="ephemeral"):
        cloud_workflow.validate_directory(tmp_path / "private")


def test_persistence_gate_rejects_oversized_temp_artifacts_before_release_upload(tmp_path, monkeypatch):
    output = tmp_path / "publication"
    (output / "site").mkdir(parents=True)
    (output / "site/index.html").write_text("working application")
    (output / "ready.json").write_text(json.dumps({"status": "verified", "deployment_performed": False}))
    monkeypatch.setattr(cloud_workflow, "MAX_TEMP_ARTIFACT_BYTES", 1)
    monkeypatch.setattr(cloud_workflow.cloud_checkpoint, "publish", lambda *a, **k: pytest.fail("No upload allowed"))
    with pytest.raises(ValueError, match="storage budget"):
        cloud_workflow.persist(tmp_path)


def test_orphan_cleanup_is_limited_to_generated_pages_transfers(monkeypatch):
    calls = []
    monkeypatch.setattr(cloud_workflow.cloud_checkpoint, "_api", lambda path: {"artifacts": [
        {"name": "github-pages", "id": 12}, {"name": "github-pages-rollback", "id": 13},
        {"name": "human-research-package", "id": 14}]})
    monkeypatch.setattr(cloud_workflow.cloud_checkpoint, "_gh", lambda arguments: calls.append(arguments))
    assert cloud_workflow.cleanup_artifacts()["deleted_generated_transfers"] == [12, 13]
    assert len(calls) == 2
    assert all("repos/augsburgace/election-observatory/actions/artifacts/" in args[-1] for args in calls)


def pages_site(directory: Path, *, base: str = cloud_workflow.BASE) -> Path:
    (directory / "assets").mkdir(parents=True)
    (directory / "assets/app.js").write_text("/* built application */")
    (directory / "assets/app.css").write_text("/* built styles */")
    (directory / "index.html").write_text(f'<script type="module" src="{base}assets/app.js"></script>'
        f'<link rel="stylesheet" href="{base}assets/app.css">')
    (directory / "public-data").mkdir()
    (directory / "public-data/manifest.json").write_bytes(manifest())
    return directory


def test_pages_shell_accepts_existing_subpath_assets(tmp_path):
    cloud_workflow.validate_pages_asset_base(pages_site(tmp_path / "site"))


def test_frontend_only_build_retains_exact_evidence_and_seed(tmp_path, monkeypatch):
    project = tmp_path / "project"
    (project / "scripts").mkdir(parents=True)
    (project / cloud_workflow.STATE_PATH).write_text(json.dumps({"source_commit": "d" * 40}))
    monkeypatch.setattr(cloud_workflow, "__file__", str(project / "scripts/cloud_workflow.py"))
    directory = tmp_path / "runner"
    original = pages_site(directory / "rollback/site")
    bundle = original / "public-data"
    raw = json.dumps({**json.loads(manifest()), "data_as_of": "2026-10-21"}).encode()
    (bundle / "manifest.json").write_bytes(raw)
    (bundle / "aggregate.json").write_bytes(b'{"verified_original_value":123}')
    seed = directory / "checkpoint/collector-seed.zip"
    seed.parent.mkdir()
    seed.write_bytes(b"isolated validated seed fixture")
    cloud_workflow.save(directory / "prepared.json", {"previous": cloud_workflow.manifest_identity(raw),
        "retained_seed": "checkpoint/collector-seed.zip", "restored_revision": 588,
        "checkpoint_sha256": hashlib.sha256(seed.read_bytes()).hexdigest()})

    def run(arguments, **kwargs):
        if arguments[0] == "git":
            return SimpleNamespace(stdout="frontend/src/publicReports.ts\n", returncode=0)
        if arguments[0] == "pnpm":
            dist = Path(arguments[-1])
            (dist / "assets").mkdir(parents=True)
            (dist / "assets/new.js").write_text("new presentation")
            (dist / "index.html").write_text('<script type="module" src="/election-observatory/assets/new.js"></script>')
            (dist / "public-data").mkdir()
            (dist / "public-data/aggregate.json").write_text("stale development data must not replace evidence")
        return SimpleNamespace(stdout="", returncode=0)

    monkeypatch.setattr(cloud_workflow.subprocess, "run", run)
    monkeypatch.setattr(cloud_workflow, "verify_site", lambda *a, **k: {"dataset_revision": 588})
    monkeypatch.setattr(cloud_workflow, "source_receipts", lambda *a: [])
    monkeypatch.setenv("GITHUB_SHA", "e" * 40)
    result = cloud_workflow.build_shell(directory)
    site = directory / "publication/site"
    assert result["dataset_revision"] == 588 and result["frontend_only"]
    assert (site / "public-data/aggregate.json").read_bytes() == (bundle / "aggregate.json").read_bytes()
    assert (directory / "publication/checkpoint.zip").read_bytes() == seed.read_bytes()
    assert (bundle / "manifest.json").read_bytes() == raw
    assert cloud_workflow.load(site / "public-data/manifest.json")["frontend_release"]["analytical_source_commit"] == "d" * 40
    assert (site / "404.html").read_bytes() == (site / "index.html").read_bytes()
    assert cloud_workflow.load(directory / "publication/check.json")["checked_sources"] == 0


@pytest.mark.parametrize("base", ["/", "https://other.invalid/election-observatory/", "/another-repository/"])
def test_pages_shell_rejects_root_or_foreign_build_even_with_matching_data_manifest(tmp_path, base):
    source = pages_site(tmp_path / "site", base=base)
    assert cloud_workflow.manifest_identity((source / "public-data/manifest.json").read_bytes())["revision"] == 588
    with pytest.raises(ValueError, match="browser shell"):
        cloud_workflow.validate_pages_asset_base(source)


def test_pages_shell_rejects_missing_script_asset(tmp_path):
    source = pages_site(tmp_path / "site")
    (source / "assets/app.js").unlink()
    with pytest.raises(ValueError, match="browser shell"):
        cloud_workflow.validate_pages_asset_base(source)


@pytest.fixture
def prepared_checkpoint(tmp_path, monkeypatch):
    control = SimpleNamespace(previous=None, base="/", restored=False)
    monkeypatch.setattr(cloud_workflow.shutil, "disk_usage", lambda path: SimpleNamespace(free=30_000_000_000))
    monkeypatch.setattr(cloud_workflow, "live_identity", lambda **kwargs: control.previous)

    def download(destination, **kwargs):
        destination.mkdir(parents=True)
        pages_site(destination / "site", base=control.base)
        (destination / "seed.zip").write_bytes(b"synthetic public checkpoint")
        return {"seed": "seed.zip", "site": "site", "metadata": {"revision": 588,
            "site": {"manifest_sha256": hashlib.sha256(manifest()).hexdigest()},
            "seed": {"sha256": "a" * 64}}}

    def restore(source, destination):
        control.restored = True
        destination.mkdir()
        return {"revision": 588}

    monkeypatch.setattr(cloud_workflow.cloud_checkpoint, "download", download)
    monkeypatch.setattr(cloud_workflow, "restore_seed", restore)
    return SimpleNamespace(directory=tmp_path / "workflow", control=control)


def test_bootstrap_evidence_is_never_claimed_as_a_previous_pages_site(prepared_checkpoint, monkeypatch, tmp_path):
    prepared = cloud_workflow.prepare(prepared_checkpoint.directory, bootstrap=True)
    assert prepared["previous_site_existed"] is False
    assert prepared_checkpoint.control.restored
    output = tmp_path / "step-output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    cloud_workflow.write_prepare_outputs(prepared)
    assert output.read_text() == "has_previous_site=false\n"
    with pytest.raises(ValueError, match="No previous Pages website"):
        cloud_workflow.verify(prepared_checkpoint.directory, rollback=True)


def test_actual_previous_pages_site_requires_a_subpath_browser_shell(prepared_checkpoint):
    prepared_checkpoint.control.previous = cloud_workflow.manifest_identity(manifest())
    with pytest.raises(ValueError, match="browser shell"):
        cloud_workflow.prepare(prepared_checkpoint.directory)
    assert not prepared_checkpoint.control.restored
    assert not (prepared_checkpoint.directory / "prepared.json").exists()


def test_verified_previous_pages_site_enables_rollback_output(prepared_checkpoint, monkeypatch, tmp_path):
    prepared_checkpoint.control.previous = cloud_workflow.manifest_identity(manifest())
    prepared_checkpoint.control.base = cloud_workflow.BASE
    prepared = cloud_workflow.prepare(prepared_checkpoint.directory)
    assert prepared["previous_site_existed"] is True
    output = tmp_path / "step-output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    cloud_workflow.write_prepare_outputs(prepared)
    assert output.read_text() == "has_previous_site=true\n"


def test_workflow_rollback_upload_requires_actual_previous_site():
    workflow = Path(__file__).resolve().parents[2] / ".github/workflows/public-cloud.yml"
    text = workflow.read_text()
    rollback = text.split("id: rollback_upload", 1)[1].split("uses:", 1)[0]
    assert "steps.prepare.outputs.has_previous_site == 'true'" in rollback


def test_unchanged_check_records_cadence_without_claiming_new_publication(tmp_path, monkeypatch):
    publication = tmp_path / "publication"
    publication.mkdir()
    previous = cloud_workflow.manifest_identity(manifest())
    cloud_workflow.save(tmp_path / "prepared.json", {"previous": previous, "checkpoint_sha256": "a" * 64})
    cloud_workflow.save(publication / "check.json", {"schema": "observatory-source-check-v1",
        "revision": 588, "publication_required": False, "checked_sources": 2, "failed_sources": [],
        "source_checks": [{"source_id": "ohio", "status": "unchanged", "document_hash": "b" * 64}]})
    cloud_workflow.save(publication / "unchanged.json", {"status": "unchanged"})
    monkeypatch.setattr(cloud_workflow, "live_identity", lambda: previous)
    writes = []
    monkeypatch.setattr(cloud_workflow, "write_status", lambda *args: writes.append(args))
    result = cloud_workflow.record_check(tmp_path)
    assert result["status"] == "unchanged" and result["revision"] == 588
    assert len(writes) == 1 and writes[0][0] == cloud_workflow.CHECK_PATH
    assert "source_checks" in writes[0][1] and "source_checks" not in result
    monkeypatch.setattr(cloud_workflow, "live_identity", lambda: {**previous, "revision": 589})
    with pytest.raises(ValueError, match="live website changed"):
        cloud_workflow.record_check(tmp_path)
    assert len(writes) == 1
    check = cloud_workflow.load(publication / "check.json")
    cloud_workflow.save(publication / "check.json", {**check, "revision": 589})
    with pytest.raises(ValueError, match="conceal newer evidence"):
        cloud_workflow.record_check(tmp_path)


def test_cloud_status_writer_cannot_commit_runtime_files():
    with pytest.raises(ValueError, match="fixed public"):
        cloud_workflow.write_status("config/sources.json", {}, "Unexpected change")
