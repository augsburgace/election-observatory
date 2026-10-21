"""Collect and publish the private-code, zero-hosting-cost web edition.

The website remains on Cloudflare Pages when this Mac is offline. Verified local
artifacts precede deployment; failed hosted verification attempts an exact,
verified rollback rather than claiming that a deployment never happened.
A published revision is never reused. Application-only updates therefore wait
for a new validated evidence batch rather than replacing an existing revision.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402
from observatory.db import Database  # noqa: E402
from observatory.domain import utc_now  # noqa: E402
from observatory.public_publish import publish_public_data, readonly_database  # noqa: E402
from observatory.settings import get_settings  # noqa: E402

from scripts.cloudflare_publication import CloudflarePublication, refresh_credentials, validate_config  # noqa: E402
from scripts.prepare_web_site import prepare_site  # noqa: E402
from scripts.publication_runtime import PublicationRuntime  # noqa: E402


def write_status(path: Path, value: dict) -> None:
    temporary = path.with_suffix(".pending")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


def verify_live(url: str, revision: int | None) -> dict:
    from observatory.registry import all_states
    states = {state["code"] for state in all_states()}
    with httpx.Client(timeout=60, follow_redirects=True) as client:
        for attempt in range(5):
            try:
                page = client.get(url)
                page.raise_for_status()
                response = client.get(url.rstrip("/") + "/public-data/manifest.json", headers={"Cache-Control": "no-cache"})
                response.raise_for_status()
                manifest = response.json()
                found_revision = manifest["dataset_revision"]
                if (isinstance(found_revision, int) and not isinstance(found_revision, bool)
                        and found_revision >= 0 and (revision is None or found_revision == revision)
                        and len(manifest["states"]) == 50 and set(manifest["states"]) == states):
                    return {"url": url, "revision": found_revision, "states": 50, "verified_at": utc_now()}
            except (httpx.HTTPError, ValueError, KeyError, TypeError):
                pass
            if attempt < 4:
                time.sleep(3)
    raise ValueError("The hosted release did not pass its revision and all-state availability check")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-collect", action="store_true", help="Use the current validated evidence")
    parser.add_argument("--build-only", action="store_true", help="Verify without changing the hosted site")
    args = parser.parse_args()
    settings = get_settings()
    settings.prepare()
    config_path = settings.data_dir / "web-publishing.json"
    if not config_path.exists():
        raise SystemExit("Configure web-publishing.json after the first verified Pages deployment")
    config = validate_config(json.loads(config_path.read_text()))
    status_path = settings.data_dir / "web-status.json"
    old = json.loads(status_path.read_text()) if status_path.exists() else {}
    status = {**old, "last_attempt_at": utc_now(), "status": "running", "interval_hours": 2,
              "execution": "This Mac; the hosted site retains its last validated release while offline"}
    with (settings.data_dir / "web-publication.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print(json.dumps({"status": "skipped", "reason": "Another publication is already running"}))
            return
        write_status(status_path, status)
        try:
            if not args.skip_collect:
                subprocess.run([sys.executable, "-m", "observatory.cli", "collect", "--due", "--warm-forecasts"],
                    cwd=settings.project_root, check=True)
            database = Database(settings)
            revision = database.latest_revision()
            if revision <= old.get("published_revision", 0):
                same = revision == old.get("published_revision", 0)
                write_status(status_path, {**status, "status": "unchanged" if same else "waiting_for_new_batch",
                    "detail": "This evidence revision is already published. A new validated batch is required before republishing application changes."
                    if same else "The existing hosted evidence is newer; it was retained without a revision rollback"})
                return
            with tempfile.TemporaryDirectory(prefix="web-publication-", dir=settings.data_dir / "staging") as temporary:
                stage = Path(temporary)
                snapshot = stage / "evidence"
                snapshot.mkdir()
                database.backup(snapshot / "observatory.sqlite3")
                for name in ("geometry", "model-runs"):
                    original = settings.data_dir / name
                    original.mkdir(exist_ok=True)
                    (snapshot / name).symlink_to(original, target_is_directory=True)
                readonly = readonly_database(type(settings)(snapshot, project_root=settings.project_root))
                try:
                    bundle = stage / "public-data"
                    with PublicationRuntime(lambda value: print(json.dumps(value), flush=True)) as runtime:
                        manifest = publish_public_data(readonly, bundle, max_files=100_000,
                            progress=runtime.progress)
                    print(json.dumps({"publication_runtime": runtime.summary()}), flush=True)
                finally:
                    readonly.engine.dispose()
                manifest["schedule"] = {"interval_hours": 2, "execution": "local-mac",
                    "description": "Collection and publication run every two hours while the owner's Mac is awake and online. The hosted site keeps this validated release when the updater is offline."}
                (bundle / "manifest.json").write_text(json.dumps(manifest, separators=(",", ":")))
                smoke = settings.project_root / "frontend" / "scripts" / "smoke-public-data.mjs"
                subprocess.run(["node", str(smoke), str(bundle), str(stage / "reader-proof.json"), "--all-states"], check=True)
                dist = stage / "dist"
                environment = {**os.environ, "VITE_PUBLIC_DATA_MODE": "true", "VITE_PUBLIC_BASE": "/"}
                subprocess.run(["pnpm", "--dir", str(settings.project_root / "frontend"), "exec", "vite", "build", "--outDir", str(dist)],
                    env=environment, cwd=settings.project_root, check=True)
                stale = dist / "public-data"
                if stale.exists():
                    shutil.rmtree(stale)  # Only this process's temporary build output.
                shutil.copytree(bundle, stale)
                proof = prepare_site(dist, stage / "site", provider="cloudflare")
                if args.build_only:
                    write_status(status_path, {**status, "status": "build_verified", "verification": proof})
                    print(json.dumps(proof))
                    return
                wrangler = settings.project_root / "frontend" / "node_modules" / ".bin" / "wrangler"
                refresh_credentials(wrangler, settings.project_root)
                with CloudflarePublication(config) as pages:
                    previous = pages.current_deployment()
                    prior_live = verify_live(config["url"], None)
                    if manifest["dataset_revision"] <= prior_live["revision"]:
                        same = manifest["dataset_revision"] == prior_live["revision"]
                        write_status(status_path, {**status, "status": "unchanged" if same else "waiting_for_new_batch",
                            "published_revision": prior_live["revision"],
                            "detail": "This evidence revision is already hosted and was retained. Application-only changes require a new validated evidence batch."
                            if same else "The current hosted evidence is newer and was retained without a revision rollback"})
                        return
                    try:
                        subprocess.run([str(wrangler), "pages", "deploy", str(stage / "site"), "--project-name", config["project"],
                            "--branch", previous["production_branch"], "--commit-dirty=true"], cwd=settings.project_root, check=True,
                            env={**os.environ, "CLOUDFLARE_ACCOUNT_ID": config["account_id"]})
                        live = verify_live(config["url"], manifest["dataset_revision"])
                        subprocess.run(["node", str(smoke), config["url"].rstrip("/") + "/public-data/",
                            str(stage / "hosted-reader-proof.json"), "--all-states"], check=True, timeout=600)
                        live["hosted_reader_verified"] = True
                        deployed = pages.current_deployment()
                        if deployed["id"] == previous["id"]:
                            raise ValueError("The production deployment did not advance; hosted publication was not confirmed")
                        live["deployment_id"] = deployed["id"]
                    except Exception:
                        try:
                            try:
                                current = pages.current_deployment()
                            except Exception:
                                current = None
                            if current is None or current["id"] != previous["id"]:
                                pages.rollback(previous["id"])
                            rolled_back = verify_live(config["url"], prior_live["revision"])
                            if pages.current_deployment()["id"] != previous["id"]:
                                raise ValueError("The previous deployment identity was not restored")
                            status = {**status, "status": "rolled_back", "published_revision": rolled_back["revision"],
                                "rollback_deployment_id": previous["id"], "rollback_verified_at": rolled_back["verified_at"],
                                "detail": "Publication verification failed; the previous hosted deployment and evidence revision were restored and verified."}
                        except Exception:
                            status = {**status, "status": "rollback_failed", "rollback_deployment_id": previous["id"],
                                "detail": "Publication verification failed and automatic restoration could not be verified. Inspect the hosted release and the private publisher log."}
                        write_status(status_path, status)
                        raise
                write_status(status_path, {**status, "status": "published", "published_revision": live["revision"],
                    "last_success_at": live["verified_at"], "url": live["url"],
                    "deployment_id": live["deployment_id"], "hosted_reader_verified": live["hosted_reader_verified"],
                    "verification": proof})
                print(json.dumps(live), flush=True)
        except Exception:
            if status.get("status") not in {"rolled_back", "rollback_failed"}:
                write_status(status_path, {**status, "status": "failed",
                    "detail": "Publication stopped before a hosted change; the previous release was retained. See the private publisher log."})
            logging.exception("Web publication failed")
            raise


if __name__ == "__main__":
    main()
