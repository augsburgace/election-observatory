from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts import cloud_workflow


def manifest(revision=588):
    return json.dumps({"dataset_revision": revision, "states": sorted(cloud_workflow.cloud_checkpoint.STATES)}).encode()


def test_rollback_identity_distinguishes_app_releases_at_same_evidence_revision():
    raw = manifest()
    changed = json.dumps({**json.loads(raw), "published_at": "2026-10-21T21:00:00Z"}).encode()
    assert cloud_workflow.manifest_identity(raw)["revision"] == cloud_workflow.manifest_identity(changed)["revision"]
    assert cloud_workflow.manifest_identity(raw) != cloud_workflow.manifest_identity(changed)
    assert cloud_workflow.manifest_identity(raw)["manifest_sha256"] == hashlib.sha256(raw).hexdigest()


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
