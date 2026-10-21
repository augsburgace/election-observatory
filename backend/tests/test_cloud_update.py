"""The cloud build never deploys or reads the owner's private application data."""
from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import subprocess
import traceback
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from observatory.db import Database, ResearchObject, Revision
from observatory.registry import all_states
from observatory.settings import Settings

from scripts import update_cloud

STATES = [state["code"] for state in all_states()]
PRIVATE_DIAGNOSTIC = "PRIVATE_RAW_VOTER_RECORD_MARKER_NEVER_PUBLIC"


@pytest.fixture
def cloud_build(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    settings = Settings(tmp_path / "runner-evidence", project_root=tmp_path / "project")
    database = Database(settings)
    with database.session() as session:
        session.add(Revision(id=588, reason="Restored public evidence"))
        session.commit()
    database.engine.dispose()
    output = tmp_path / "publication"
    commands = []
    state = SimpleNamespace(fail=None, revision=589, seed_error=False, collection=True,
        bad_states=False, published_revision=None, checkpoints=0, prepared=0,
        boundary_calls=0, boundary_error=False, boundary_new_revision=False)

    def run(command, **kwargs):
        commands.append((command, kwargs))
        if "collect" in command:
            assert kwargs["stderr"] == subprocess.STDOUT
            kwargs["stdout"].write(PRIVATE_DIAGNOSTIC + "\n")
            kwargs["stdout"].flush()
            if state.fail == "collect":
                raise subprocess.CalledProcessError(1, command, output=PRIVATE_DIAGNOSTIC,
                    stderr=PRIVATE_DIAGNOSTIC)
            if state.collection:
                with sqlite3.connect(settings.database_path) as connection:
                    connection.execute("INSERT INTO revisions(id,reason,created_at) VALUES(?,?,?)",
                        (state.revision, "Public collection", "2026-10-21T12:00:00Z"))
                    connection.commit()
        elif "vite" in command:
            if state.fail == "build":
                raise subprocess.CalledProcessError(1, command)
            dist = Path(command[command.index("--outDir") + 1])
            (dist / "public-data").mkdir(parents=True)
            (dist / "public-data" / "STALE").write_text("Old Vite-copied bundle must be replaced")
            (dist / "index.html").write_text("<html>Actual application build</html>")
        elif command[0] == "node":
            packed = Path(command[3]).name == "packed-reader-proof.json"
            if state.fail == ("packed-reader" if packed else "reader"):
                raise subprocess.CalledProcessError(1, command)
            Path(command[3]).write_text(json.dumps({"checks": 75, "states": 50}))
        return subprocess.CompletedProcess(command, 0)

    def publish(database, target, **kwargs):
        assert kwargs["max_files"] == 100_000
        assert kwargs["revision"] == database.latest_revision()
        kwargs["progress"]({"stage": "state", "state": "OH"})
        target.mkdir()
        value = {"dataset_revision": kwargs["revision"], "states": STATES if not state.bad_states else ["OH"] * 50,
            "data_as_of": "2026-10-21"}
        state.published_revision = kwargs["revision"]
        return value

    def prepare(dist, target, *, provider):
        state.prepared += 1
        assert provider == "github"
        assert not (dist / "public-data" / "STALE").exists()
        shutil.copytree(dist, target)
        return {"dataset_revision": state.published_revision, "states": 50, "private_runtime_files": 0}

    real_create_seed = update_cloud.create_seed

    def checkpoint(database, target):
        state.checkpoints += 1
        # Exercise the real SQLite backup, sanitization, and vacuum while the
        # source's publication writer lock is held. This catches deadlocks.
        proof = real_create_seed(database, target)
        if state.seed_error:
            proof["private_notebook_rows"] = 1
        return proof

    def boundary_review(database):
        state.boundary_calls += 1
        if state.boundary_error:
            print(PRIVATE_DIAGNOSTIC)
            raise ValueError(PRIVATE_DIAGNOSTIC)
        if state.boundary_new_revision:
            with database.session() as session:
                session.add(Revision(id=590, reason="Archived original Census county-change references"))
                session.commit()
        return {"revision": database.latest_revision()}

    monkeypatch.setattr(update_cloud.subprocess, "run", run)
    monkeypatch.setattr(update_cloud, "publish_public_data", publish)
    monkeypatch.setattr(update_cloud, "prepare_site", prepare)
    monkeypatch.setattr(update_cloud, "create_seed", checkpoint)
    monkeypatch.setattr(update_cloud, "archive_boundary_review", boundary_review)
    return SimpleNamespace(settings=settings, output=output, state=state, commands=commands,
        build=lambda **kwargs: update_cloud.build_cloud_publication(settings, output,
            base="/battleground-senate-observatory/", previous_revision=588, **kwargs))


def test_cloud_build_requires_both_reader_checks_and_matching_sanitized_checkpoint(cloud_build):
    result = cloud_build.build(parent_checkpoint_sha256="a" * 64)
    assert result == json.loads((cloud_build.output / "ready.json").read_text())
    assert result["status"] == "verified" and result["deployment_performed"] is False
    assert result["dataset_revision"] == result["checkpoint"]["revision"] == 589
    assert result["restored_revision"] == result["previous_published_revision"] == 588
    assert result["data_as_of"] == "2026-10-21"
    assert result["parent_checkpoint_sha256"] == "a" * 64
    assert "path" not in result["checkpoint"]
    assert result["checkpoint"]["sha256"] == hashlib.sha256((cloud_build.output / "checkpoint.zip").read_bytes()).hexdigest()
    assert result["checkpoint"]["private_notebook_rows"] == result["checkpoint"]["private_job_rows"] == 0
    manifest = json.loads((cloud_build.output / "site" / "public-data" / "manifest.json").read_text())
    assert manifest["schedule"]["execution"] == "github-actions"
    assert not list(cloud_build.output.glob(".cloud-build-*"))
    assert not list(cloud_build.output.glob("*.pending"))
    assert sum(command[0] == "node" for command, _ in cloud_build.commands) == 2
    assert all("--all-states" in command for command, _ in cloud_build.commands if command[0] == "node")
    assert all("deploy" not in command and "wrangler" not in command[0] for command, _ in cloud_build.commands)


def test_build_uses_explicit_ephemeral_database_and_pages_subpath(cloud_build):
    cloud_build.build()
    collection, config = next((command, config) for command, config in cloud_build.commands if "collect" in command)
    assert "--due" in collection and "--warm-forecasts" in collection
    assert config["env"]["OBSERVATORY_DATA_DIR"] == str(cloud_build.settings.data_dir)
    assert config["env"]["OBSERVATORY_PUBLIC_MODE"] == "false"
    vite = next(config for command, config in cloud_build.commands if "vite" in command)
    assert vite["env"]["VITE_PUBLIC_BASE"] == "/battleground-senate-observatory/"
    assert vite["env"]["VITE_PUBLIC_DATA_MODE"] == "true"


@pytest.mark.parametrize("failure", ["collect", "reader", "build", "packed-reader"])
def test_failure_never_creates_ready_marker_or_successor_checkpoint(cloud_build, failure):
    cloud_build.state.fail = failure
    with pytest.raises(ValueError if failure == "collect" else subprocess.CalledProcessError):
        cloud_build.build()
    assert not (cloud_build.output / "ready.json").exists()
    assert cloud_build.state.checkpoints == 0
    assert not list(cloud_build.output.glob(".cloud-build-*"))


def test_parser_diagnostics_remain_private_on_success_and_never_enter_artifacts(cloud_build, capsys):
    cloud_build.build()
    captured = capsys.readouterr()
    assert PRIVATE_DIAGNOSTIC not in captured.out + captured.err
    private_log = cloud_build.settings.data_dir / "cloud-collection.private.log"
    assert private_log.read_text().strip() == PRIVATE_DIAGNOSTIC
    assert private_log.stat().st_mode & 0o777 == 0o600
    for path in cloud_build.output.rglob("*"):
        if path.is_file() and path.suffix != ".zip":
            assert PRIVATE_DIAGNOSTIC.encode() not in path.read_bytes()
    with zipfile.ZipFile(cloud_build.output / "checkpoint.zip") as checkpoint:
        assert all(PRIVATE_DIAGNOSTIC.encode() not in checkpoint.read(name)
            for name in checkpoint.namelist())


def test_failed_parser_cannot_leak_original_error_output_or_traceback(cloud_build, capsys):
    cloud_build.state.fail = "collect"
    with pytest.raises(ValueError, match="Original diagnostics remain only in ephemeral") as error:
        cloud_build.build()
    rendered = "".join(traceback.format_exception(error.value))
    captured = capsys.readouterr()
    assert PRIVATE_DIAGNOSTIC not in rendered + captured.out + captured.err
    assert "CalledProcessError" not in rendered
    assert not (cloud_build.output / "ready.json").exists()
    assert cloud_build.state.checkpoints == 0


def test_bad_checkpoint_privacy_proof_cannot_publish_ready_marker(cloud_build):
    cloud_build.state.seed_error = True
    with pytest.raises(ValueError, match="privacy"):
        cloud_build.build()
    assert not (cloud_build.output / "ready.json").exists()


def test_same_revision_can_refresh_application_without_inventing_evidence(cloud_build):
    result = cloud_build.build(skip_collect=True)
    assert result["dataset_revision"] == 588
    assert result["checkpoint"]["revision"] == 588
    assert not any("collect" in command for command, _ in cloud_build.commands)
    assert cloud_build.state.boundary_calls == 0


def test_archived_boundary_review_precedes_frozen_publication_and_checkpoint(cloud_build):
    cloud_build.state.boundary_new_revision = True
    ready = cloud_build.build()
    assert cloud_build.state.boundary_calls == 1
    assert ready["dataset_revision"] == ready["checkpoint"]["revision"] == 590


def test_unavailable_census_reference_withholds_review_without_stopping_other_research(cloud_build, capsys):
    cloud_build.state.boundary_error = True
    ready = cloud_build.build()
    captured = capsys.readouterr()
    assert PRIVATE_DIAGNOSTIC not in captured.out + captured.err
    assert '"stage":"boundary-review","status":"unavailable"' in captured.out
    assert ready["status"] == "verified" and ready["dataset_revision"] == 589
    assert PRIVATE_DIAGNOSTIC in (cloud_build.settings.data_dir / "cloud-collection.private.log").read_text()


def test_stale_parent_checkpoint_is_rejected_before_collection(cloud_build):
    with sqlite3.connect(cloud_build.settings.database_path) as connection:
        connection.execute("UPDATE revisions SET id=587 WHERE id=588")
        connection.commit()
    with pytest.raises(ValueError, match="predates"):
        cloud_build.build()
    assert cloud_build.commands == []
    assert not cloud_build.output.exists()


def test_publication_rejects_duplicate_state_labels_even_when_count_is_fifty(cloud_build):
    cloud_build.state.bad_states = True
    with pytest.raises(ValueError, match="all 50 states"):
        cloud_build.build()
    assert cloud_build.state.prepared == cloud_build.state.checkpoints == 0
    assert not (cloud_build.output / "ready.json").exists()


def test_private_notebook_checkpoint_is_rejected_before_collection(cloud_build):
    database = Database(cloud_build.settings)
    with database.session() as session:
        session.add(ResearchObject(kind="note", title="PRIVATE_SENTINEL", body="Private research"))
        session.commit()
    database.engine.dispose()
    with pytest.raises(ValueError, match="sanitized"):
        cloud_build.build()
    assert cloud_build.commands == []


def test_existing_release_output_is_preserved_without_collection(cloud_build):
    cloud_build.output.mkdir()
    sentinel = cloud_build.output / "ready.json"
    sentinel.write_text("KEEP_PREVIOUS_RELEASE")
    with pytest.raises(ValueError, match="never overwritten"):
        cloud_build.build()
    assert sentinel.read_text() == "KEEP_PREVIOUS_RELEASE"
    assert cloud_build.commands == []


@pytest.mark.parametrize("base", ["https://hostile.example/", "//hostile/", "/../", "/project", "/project/?token=bad", "/./"])
def test_pages_base_rejects_external_or_ambiguous_paths(base):
    with pytest.raises(ValueError, match="base"):
        update_cloud.validate_base(base)


def test_private_default_is_never_used_when_cli_omits_data_directory(tmp_path, monkeypatch):
    monkeypatch.delenv("OBSERVATORY_DATA_DIR", raising=False)
    with pytest.raises(SystemExit):
        update_cloud.main(["--output", str(tmp_path / "site"), "--base", "/", "--previous-revision", "588"])
    assert not (tmp_path / "site").exists()


def test_github_runner_requires_ephemeral_data_under_runner_temp(cloud_build, monkeypatch):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("RUNNER_TEMP", str(cloud_build.settings.data_dir.parent / "different-runner-temp"))
    with pytest.raises(ValueError, match="RUNNER_TEMP"):
        cloud_build.build()
    assert cloud_build.commands == []


def test_frozen_evidence_blocks_writes_but_allows_queries_and_releases_lock(tmp_path):
    path = tmp_path / "database.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("CREATE TABLE revisions(id INTEGER PRIMARY KEY)")
        connection.execute("INSERT INTO revisions(id) VALUES(588)")
        connection.commit()
    with update_cloud.frozen_evidence(path) as revision:
        assert revision == 588
        with sqlite3.connect(path, timeout=0.01) as other:
            assert other.execute("SELECT MAX(id) FROM revisions").fetchone()[0] == 588
            with pytest.raises(sqlite3.OperationalError, match="locked"):
                other.execute("INSERT INTO revisions(id) VALUES(589)")
    with sqlite3.connect(path, timeout=0.01) as other:
        other.execute("INSERT INTO revisions(id) VALUES(589)")
        other.commit()
