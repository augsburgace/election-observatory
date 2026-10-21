"""Mocked publication operations never touch the live site, credentials or launchd."""
from __future__ import annotations

import json
import plistlib
import subprocess
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from observatory.registry import all_states
from observatory.settings import Settings

from scripts import cloudflare_publication as cf
from scripts import install_schedule, update_web

PREVIOUS_ID = "11111111-1111-4111-8111-111111111111"
NEW_ID = "22222222-2222-4222-8222-222222222222"
CONFIG = {"account_id": cf.ACCOUNT_ID, "project": cf.PROJECT, "url": f"https://{cf.PUBLIC_HOST}"}
STATES = [state["code"] for state in all_states()]


def test_status_write_atomically_replaces_previous_result(tmp_path, monkeypatch):
    path = tmp_path / "web-status.json"
    update_web.write_status(path, {"status": "published", "published_revision": 574})
    assert not path.with_suffix(".pending").exists()
    original = Path.replace
    def fail_replace(self, target):
        if self.suffix == ".pending":
            raise OSError("Synthetic interrupted status commit")
        return original(self, target)
    monkeypatch.setattr(Path, "replace", fail_replace)
    with pytest.raises(OSError):
        update_web.write_status(path, {"status": "running"})
    assert json.loads(path.read_text())["published_revision"] == 574


def _live_transport(monkeypatch, manifests):
    calls, sleeps = [], []
    def handler(request):
        calls.append(request)
        if request.url.path == "/public-data/manifest.json":
            value = manifests.pop(0) if len(manifests) > 1 else manifests[0]
            return httpx.Response(200, json=value)
        return httpx.Response(200, text="<html>The actual application</html>")
    real_client = httpx.Client
    monkeypatch.setattr(update_web.httpx, "Client", lambda **kwargs: real_client(
        transport=httpx.MockTransport(handler), **kwargs))
    monkeypatch.setattr(update_web.time, "sleep", sleeps.append)
    return calls, sleeps


def test_live_revision_verification_retries_and_checks_all_state_identities(monkeypatch):
    calls, sleeps = _live_transport(monkeypatch, [
        {"dataset_revision": 574, "states": STATES},
        {"dataset_revision": 575, "states": STATES}])
    proof = update_web.verify_live(CONFIG["url"], 575)
    assert proof["revision"] == 575 and proof["states"] == 50
    assert sleeps == [3]
    assert all(request.headers.get("Cache-Control") == "no-cache" for request in calls
        if request.url.path == "/public-data/manifest.json")


@pytest.mark.parametrize("manifest", [
    {"dataset_revision": 575, "states": ["OH"] * 50},
    {"dataset_revision": 575, "states": STATES[:-1]},
    {"dataset_revision": 574, "states": STATES},
    {"dataset_revision": True, "states": STATES},
])
def test_live_check_never_accepts_partial_or_wrong_revision(monkeypatch, manifest):
    _, sleeps = _live_transport(monkeypatch, [manifest])
    with pytest.raises(ValueError, match="revision and all-state"):
        update_web.verify_live(CONFIG["url"], 575)
    assert len(sleeps) == 4


@pytest.mark.parametrize("change", [{"account_id": "other-account"}, {"project": "another-project"},
    {"url": "https://hostile.invalid"}, {"url": CONFIG["url"] + "/private"}])
def test_cloudflare_operations_cannot_target_another_account_or_project(change):
    with pytest.raises(ValueError):
        cf.validate_config({**CONFIG, **change})


def test_capture_and_rollback_use_only_fixed_scope_and_in_memory_authorization(monkeypatch):
    token_marker = "SYNTHETIC_AUTH_ONLY_NEVER_A_REAL_SECRET"
    monkeypatch.setattr(cf, "_existing_token", lambda: token_marker)
    calls = []
    def transport(request):
        calls.append(request)
        assert request.headers["Authorization"] == "Bearer " + token_marker
        assert request.url.host == "api.cloudflare.com"
        assert request.url.path.startswith(f"/client/v4/accounts/{cf.ACCOUNT_ID}/pages/projects/{cf.PROJECT}")
        if request.method == "GET":
            return httpx.Response(200, json={"success": True, "result": {"name": cf.PROJECT,
                "production_branch": "codex/web-publication", "canonical_deployment": {
                    "id": PREVIOUS_ID, "environment": "production", "latest_stage": {"status": "success"}}}})
        return httpx.Response(200, json={"success": True, "result": {"id": PREVIOUS_ID}})
    with cf.CloudflarePublication(CONFIG, transport=httpx.MockTransport(transport)) as pages:
        previous = pages.current_deployment()
        assert previous["id"] == PREVIOUS_ID
        assert token_marker not in json.dumps(previous)
        pages.rollback(previous["id"])
        with pytest.raises(ValueError, match="identifier"):
            pages.rollback("../another-project")
    assert [(call.method, call.url.path.rsplit("/", 1)[-1]) for call in calls] == [("GET", cf.PROJECT), ("POST", "rollback")]


def test_cloudflare_error_bodies_and_auth_refresh_output_are_not_exposed(monkeypatch, tmp_path):
    marker = "SYNTHETIC_PRIVATE_AUTH_ERROR"
    monkeypatch.setattr(cf, "_existing_token", lambda: "unit-only")
    with cf.CloudflarePublication(CONFIG, transport=httpx.MockTransport(lambda request:
            httpx.Response(403, text=marker))) as pages:
        with pytest.raises(ValueError) as error:
            pages.current_deployment()
        assert marker not in str(error.value)
    calls = []
    monkeypatch.setattr(cf.subprocess, "run", lambda *args, **kwargs: calls.append((args, kwargs)))
    cf.refresh_credentials(tmp_path / "wrangler", tmp_path)
    assert calls[0][1]["stdout"] == subprocess.DEVNULL
    assert calls[0][1]["stderr"] == subprocess.DEVNULL


@pytest.fixture
def operation(tmp_path, monkeypatch):
    settings = Settings(tmp_path / "data", project_root=tmp_path / "project")
    settings.prepare()
    (settings.data_dir / "web-publishing.json").write_text(json.dumps(CONFIG))
    update_web.write_status(settings.data_dir / "web-status.json", {"status": "published", "published_revision": 574,
        "last_success_at": "2026-10-21T00:00:00Z", "url": CONFIG["url"]})
    monkeypatch.setattr(update_web, "get_settings", lambda: settings)
    commands = []
    control = SimpleNamespace(current=PREVIOUS_ID, rollback_error=False, verification_error=False,
        collection_error=False, hosted_smoke_error=False, revision=575, rollbacks=[], auth_refreshes=0)
    class Database:
        def __init__(self, settings):
            pass
        def latest_revision(self):
            return control.revision
        def backup(self, path):
            path.write_bytes(b"Synthetic private snapshot; never a public artifact")
    monkeypatch.setattr(update_web, "Database", Database)
    monkeypatch.setattr(update_web, "readonly_database", lambda settings:
        SimpleNamespace(engine=SimpleNamespace(dispose=lambda: None)))
    def publish(database, bundle, **kwargs):
        bundle.mkdir()
        return {"dataset_revision": control.revision, "states": STATES}
    monkeypatch.setattr(update_web, "publish_public_data", publish)
    monkeypatch.setattr(update_web, "prepare_site", lambda *args, **kwargs: {"states": 50, "private_runtime_files": 0})
    def run(command, **kwargs):
        commands.append((command, kwargs))
        if "collect" in command and control.collection_error:
            raise subprocess.CalledProcessError(1, command)
        if command[0] == "node" and any(str(arg).startswith("https://") for arg in command) and control.hosted_smoke_error:
            raise subprocess.CalledProcessError(1, command)
        if "pages" in command and "deploy" in command:
            control.current = NEW_ID
        return subprocess.CompletedProcess(command, 0)
    monkeypatch.setattr(update_web.subprocess, "run", run)
    def refresh(*args):
        control.auth_refreshes += 1
    monkeypatch.setattr(update_web, "refresh_credentials", refresh)
    class Pages:
        def __init__(self, config):
            cf.validate_config(config)
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def current_deployment(self):
            return {"id": control.current, "production_branch": "codex/web-publication"}
        def rollback(self, deployment_id):
            control.rollbacks.append(deployment_id)
            if control.rollback_error:
                raise ValueError("Synthetic Cloudflare rollback failure")
            control.current = deployment_id
    monkeypatch.setattr(update_web, "CloudflarePublication", Pages)
    def verify(url, revision):
        if revision == 575 and control.verification_error:
            raise ValueError("Synthetic hosted revision mismatch")
        return {"url": url, "revision": revision if revision is not None else 574, "states": 50,
                "verified_at": "2026-10-21T12:00:00Z"}
    monkeypatch.setattr(update_web, "verify_live", verify)
    return SimpleNamespace(settings=settings, control=control, commands=commands,
        status=lambda: json.loads((settings.data_dir / "web-status.json").read_text()))


def test_build_only_performs_no_hosted_operations(operation, monkeypatch):
    monkeypatch.setattr(update_web.sys, "argv", ["update_web", "--skip-collect", "--build-only"])
    update_web.main()
    assert operation.status()["status"] == "build_verified"
    assert operation.control.auth_refreshes == 0
    assert not any("deploy" in command for command, _ in operation.commands)


def test_published_status_requires_new_production_identity_and_correct_account(operation, monkeypatch):
    monkeypatch.setattr(update_web.sys, "argv", ["update_web", "--skip-collect"])
    update_web.main()
    assert operation.status()["status"] == "published"
    assert operation.status()["published_revision"] == 575
    assert operation.status()["deployment_id"] == NEW_ID
    assert operation.status()["hosted_reader_verified"] is True
    deploy = next((command, kwargs) for command, kwargs in operation.commands if "deploy" in command)
    assert deploy[1]["env"]["CLOUDFLARE_ACCOUNT_ID"] == cf.ACCOUNT_ID
    assert deploy[0][deploy[0].index("--project-name") + 1] == cf.PROJECT
    hosted_smoke = next(command for command, _ in operation.commands if command[0] == "node"
        and CONFIG["url"] + "/public-data/" in command)
    assert "--all-states" in hosted_smoke


def test_postdeploy_verification_failure_restores_exact_previous_release(operation, monkeypatch):
    monkeypatch.setattr(update_web.sys, "argv", ["update_web", "--skip-collect"])
    operation.control.verification_error = True
    with pytest.raises(ValueError, match="hosted revision"):
        update_web.main()
    status = operation.status()
    assert operation.control.rollbacks == [PREVIOUS_ID]
    assert operation.control.current == PREVIOUS_ID
    assert status["status"] == "rolled_back" and status["published_revision"] == 574
    assert status["rollback_deployment_id"] == PREVIOUS_ID
    assert "restored and verified" in status["detail"]


def test_failed_rollback_does_not_claim_the_old_site_was_retained(operation, monkeypatch):
    monkeypatch.setattr(update_web.sys, "argv", ["update_web", "--skip-collect"])
    operation.control.verification_error = operation.control.rollback_error = True
    with pytest.raises(ValueError):
        update_web.main()
    status = operation.status()
    assert status["status"] == "rollback_failed"
    assert operation.control.current == NEW_ID
    assert "could not be verified" in status["detail"]
    assert "retained" not in status["detail"] and "restored" not in status["detail"]


def test_hosted_object_reader_failure_rolls_back_even_when_manifest_passes(operation, monkeypatch):
    monkeypatch.setattr(update_web.sys, "argv", ["update_web", "--skip-collect"])
    operation.control.hosted_smoke_error = True
    with pytest.raises(subprocess.CalledProcessError):
        update_web.main()
    assert operation.control.rollbacks == [PREVIOUS_ID]
    assert operation.control.current == PREVIOUS_ID
    assert operation.status()["status"] == "rolled_back"
    assert operation.status()["published_revision"] == 574


def test_collection_failure_keeps_published_revision_and_never_deploys(operation, monkeypatch):
    monkeypatch.setattr(update_web.sys, "argv", ["update_web"])
    operation.control.collection_error = True
    with pytest.raises(subprocess.CalledProcessError):
        update_web.main()
    assert operation.status()["status"] == "failed"
    assert operation.status()["published_revision"] == 574
    assert not any("deploy" in command for command, _ in operation.commands)


def test_newer_hosted_evidence_is_never_replaced_by_older_local_data(operation, monkeypatch):
    monkeypatch.setattr(update_web.sys, "argv", ["update_web", "--skip-collect"])
    def newer(url, revision):
        assert revision is None
        return {"url": url, "revision": 577, "states": 50, "verified_at": "2026-10-21T12:00:00Z"}
    monkeypatch.setattr(update_web, "verify_live", newer)
    update_web.main()
    assert operation.status()["status"] == "waiting_for_new_batch"
    assert operation.status()["published_revision"] == 577
    assert not any("deploy" in command for command, _ in operation.commands)


@pytest.mark.parametrize("revision,expected_status", [(574, "unchanged"), (573, "waiting_for_new_batch")])
def test_published_revision_is_never_reused_before_build_or_upload(operation, monkeypatch, revision, expected_status):
    monkeypatch.setattr(update_web.sys, "argv", ["update_web", "--skip-collect"])
    operation.control.revision = revision
    update_web.main()
    assert operation.status()["status"] == expected_status
    assert operation.status()["published_revision"] == 574
    assert operation.commands == []
    assert operation.control.auth_refreshes == 0
    assert operation.control.current == PREVIOUS_ID
    if revision == 574:
        assert "new validated batch" in operation.status()["detail"]


def test_live_equal_revision_is_retained_even_when_local_success_status_is_older(operation, monkeypatch):
    monkeypatch.setattr(update_web.sys, "argv", ["update_web", "--skip-collect"])
    def already_hosted(url, revision):
        assert revision is None
        return {"url": url, "revision": 575, "states": 50, "verified_at": "2026-10-21T12:00:00Z"}
    monkeypatch.setattr(update_web, "verify_live", already_hosted)
    update_web.main()
    assert operation.status()["status"] == "unchanged"
    assert operation.status()["published_revision"] == 575
    assert operation.control.current == PREVIOUS_ID
    assert operation.control.rollbacks == []
    assert not any("deploy" in command for command, _ in operation.commands)
    assert "Application-only changes require a new validated evidence batch" in operation.status()["detail"]


def test_invalid_publication_config_stops_before_collection_or_hosted_changes(operation, monkeypatch):
    monkeypatch.setattr(update_web.sys, "argv", ["update_web"])
    (operation.settings.data_dir / "web-publishing.json").write_text(json.dumps({**CONFIG, "project": "another-project"}))
    with pytest.raises(ValueError, match="approved Observatory"):
        update_web.main()
    assert operation.commands == []
    assert operation.control.auth_refreshes == 0


def test_default_auth_read_does_not_disclose_file_contents_on_parse_failure(tmp_path, monkeypatch):
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
    monkeypatch.setattr(cf.Path, "home", lambda: tmp_path)
    config = tmp_path / ".wrangler" / "config"
    config.mkdir(parents=True)
    (config / "default.toml").write_text('oauth_token = "SYNTHETIC_PRIVATE_TOKEN"\nmalformed = [')
    with pytest.raises(ValueError) as error:
        cf._existing_token()
    assert "SYNTHETIC_PRIVATE_TOKEN" not in str(error.value)
    assert str(tmp_path) not in str(error.value)


def test_existing_schedule_is_replaced_with_one_reversible_two_hour_publisher(tmp_path, monkeypatch):
    settings = Settings(tmp_path / "data", project_root=tmp_path / "project")
    settings.prepare()
    (settings.data_dir / "web-publishing.json").write_text(json.dumps(CONFIG))
    monkeypatch.setattr(install_schedule, "get_settings", lambda: settings)
    monkeypatch.setattr(install_schedule.Path, "home", lambda: tmp_path / "home")
    monkeypatch.setattr(install_schedule.shutil, "which", lambda name: f"/runtime/bin/{name}")
    monkeypatch.setattr(install_schedule.sys if hasattr(install_schedule, "sys") else update_web.sys,
                        "argv", ["install_schedule", "--publish-web", "--defer-first-run"])
    calls = []
    monkeypatch.setattr(install_schedule.subprocess, "run", lambda *args, **kwargs: calls.append(args[0]))
    install_schedule.main()
    target = tmp_path / "home" / "Library" / "LaunchAgents" / f"{install_schedule.LABEL}.plist"
    value = plistlib.loads(target.read_bytes())
    assert value["StartInterval"] == 7200 and value["RunAtLoad"] is False
    assert value["ProgramArguments"][-1] == str(settings.project_root / "scripts" / "update_web.py")
    assert set(value["EnvironmentVariables"]) == {"OBSERVATORY_DATA_DIR", "PATH"}
    assert calls[-1][:2] == ["launchctl", "bootstrap"]
