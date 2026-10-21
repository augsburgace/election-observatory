"""Coordinate the fixed public GitHub Pages workflow without persistent secrets."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from observatory.domain import utc_now  # noqa: E402
from observatory.settings import Settings  # noqa: E402

from scripts import cloud_checkpoint  # noqa: E402
from scripts.public_seed import restore_seed  # noqa: E402
from scripts.update_cloud import build_cloud_publication  # noqa: E402

REPOSITORY = "augsburgace/election-observatory"
PUBLIC_URL = "https://augsburgace.github.io/election-observatory/"
BASE = "/election-observatory/"
STATE_PATH = "publication-state.json"
MIN_FREE_BYTES = 25_000_000_000
MAX_TEMP_ARTIFACT_BYTES = 400_000_000


def load(path: Path) -> dict:
    return json.loads(path.read_text())


def save(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n")


def manifest_identity(raw: bytes) -> dict:
    value = json.loads(raw)
    revision = value.get("dataset_revision")
    if (not isinstance(revision, int) or isinstance(revision, bool) or revision < 0
            or not isinstance(value.get("states"), list)
            or len(value["states"]) != 50 or set(value["states"]) != cloud_checkpoint.STATES):
        raise ValueError("Published website has an invalid revision or state catalog")
    return {"revision": revision, "manifest_sha256": hashlib.sha256(raw).hexdigest()}


def live_identity(*, bootstrap: bool = False) -> dict | None:
    with httpx.Client(timeout=60, follow_redirects=False) as client:
        response = client.get(PUBLIC_URL + "public-data/manifest.json",
            params={"observatory-check": str(time.time_ns())}, headers={"Cache-Control": "no-cache"})
    if response.status_code == 404 and bootstrap:
        return None
    response.raise_for_status()
    return manifest_identity(response.content)


def validate_directory(directory: Path) -> Path:
    directory = directory.resolve()
    runner = os.environ.get("RUNNER_TEMP")
    if os.environ.get("GITHUB_ACTIONS") == "true" and (
            not runner or not directory.is_relative_to(Path(runner).resolve())):
        raise ValueError("Cloud workflow must use its ephemeral RUNNER_TEMP directory")
    private = Path.home() / "Library/Application Support/Battleground Senate Observatory"
    if directory == private or directory.is_relative_to(private):
        raise ValueError("Private local data cannot be a cloud workflow directory")
    return directory


def prepare(directory: Path, *, bootstrap: bool = False) -> dict:
    directory = validate_directory(directory)
    if directory.exists():
        raise ValueError("Choose a new cloud workflow directory")
    directory.mkdir(parents=True)
    if shutil.disk_usage(directory).free < MIN_FREE_BYTES:
        raise ValueError("The free runner needs at least 25 GB available before restoring the checkpoint")
    previous = live_identity(bootstrap=bootstrap)
    downloaded = cloud_checkpoint.download(directory / "checkpoint", with_site=True)
    metadata = downloaded["metadata"]
    if previous and metadata["revision"] < previous["revision"]:
        raise ValueError("The latest public checkpoint is older than the live website")
    rollback_source = directory / "checkpoint/site"
    if previous and metadata["site"]["manifest_sha256"] != previous["manifest_sha256"]:
        rollback = cloud_checkpoint.download(directory / "rollback-checkpoint", with_site=True,
            revision=previous["revision"], site_manifest_sha256=previous["manifest_sha256"])
        rollback_source = directory / "rollback-checkpoint" / rollback["site"]
        (directory / "rollback-checkpoint" / rollback["seed"]).unlink()
    (directory / "rollback").mkdir()
    rollback_source.replace(directory / "rollback/site")
    rollback_identity = manifest_identity((directory / "rollback/site/public-data/manifest.json").read_bytes())
    if previous and rollback_identity != previous:
        raise ValueError("Rollback artifact does not match the exact live publication")
    source = directory / "checkpoint" / downloaded["seed"]
    restored = restore_seed(source, directory / "data")
    source.unlink()  # Verified release asset remains recoverable on GitHub.
    prepared = {"schema": "observatory-cloud-workflow-v1", "restored_revision": restored["revision"],
        "previous": previous or rollback_identity, "previous_site_existed": previous is not None,
        "checkpoint_sha256": metadata["seed"]["sha256"], "prepared_at": utc_now()}
    save(directory / "prepared.json", prepared)
    return prepared


def build(directory: Path, *, skip_collect: bool = False) -> dict:
    directory = validate_directory(directory)
    prepared = load(directory / "prepared.json")
    return build_cloud_publication(Settings(directory / "data"), directory / "publication", base=BASE,
        previous_revision=prepared["previous"]["revision"], skip_collect=skip_collect,
        parent_checkpoint_sha256=prepared["checkpoint_sha256"])


def persist(directory: Path) -> dict:
    directory = validate_directory(directory)
    ready = load(directory / "publication/ready.json")
    if ready.get("status") != "verified" or ready.get("deployment_performed") is not False:
        raise ValueError("Only a completely verified build can be persisted")
    site = directory / "publication/site"
    files = [p for p in site.rglob("*") if p.is_file()]
    # One short-lived artifact at a time; no caches or retained build artifacts.
    estimated_tar = sum(p.stat().st_size for p in files) + len(files) * 1024 + 1_000_000
    if estimated_tar > MAX_TEMP_ARTIFACT_BYTES:
        raise ValueError("The temporary Pages artifact exceeds its bounded free storage budget")
    run = os.environ.get("GITHUB_RUN_ID")
    attempt = os.environ.get("GITHUB_RUN_ATTEMPT", "1")
    if not run or not run.isdigit() or not attempt.isdigit():
        raise ValueError("A GitHub workflow run identity is required")
    cleanup_artifacts()
    result = cloud_checkpoint.publish(directory / "publication/checkpoint.zip", ready["dataset_revision"],
        f"{run}-{attempt}", ready["data_as_of"], site=site)
    save(directory / "persisted.json", result)
    return result


def cleanup_artifacts() -> dict:
    """Remove only generated Pages transfers; durable release checkpoints remain."""
    value = cloud_checkpoint._api("actions/artifacts?per_page=100")
    if not isinstance(value, dict) or not isinstance(value.get("artifacts"), list):
        raise ValueError("Could not verify bounded temporary deployment storage")
    deleted = []
    for artifact in value["artifacts"]:
        if artifact.get("name") not in {"github-pages", "github-pages-rollback"}:
            continue
        identity = artifact.get("id")
        if not isinstance(identity, int) or isinstance(identity, bool) or identity <= 0:
            raise ValueError("Invalid generated Pages artifact identity")
        cloud_checkpoint._gh(["api", "--method", "DELETE", f"repos/{REPOSITORY}/actions/artifacts/{identity}"])
        deleted.append(identity)
    return {"deleted_generated_transfers": deleted}


def verify(directory: Path, *, rollback: bool = False) -> dict:
    directory = validate_directory(directory)
    expected = load(directory / "prepared.json")["previous"] if rollback else manifest_identity(
        (directory / "publication/site/public-data/manifest.json").read_bytes())
    matched = False
    for attempt in range(12):
        try:
            matched = live_identity() == expected
        except (httpx.HTTPError, ValueError, KeyError):
            matched = False
        if matched:
            break
        print(json.dumps({"stage": "waiting-for-pages", "attempt": attempt + 1}), flush=True)
        time.sleep(5)
    if not matched:
        raise ValueError("The hosted website did not match the exact verified publication")
    proof_file = directory / ("rollback-reader-proof.json" if rollback else "hosted-reader-proof.json")
    smoke = Path(__file__).resolve().parents[1] / "frontend/scripts/smoke-public-data.mjs"
    subprocess.run(["node", str(smoke), PUBLIC_URL + "public-data/", str(proof_file), "--all-states"],
                   check=True, timeout=600,
                   env={**os.environ, "OBSERVATORY_MANIFEST_ID": expected["manifest_sha256"]})
    reader = load(proof_file)
    if reader.get("revision") != expected["revision"] or reader.get("passed", 0) < 75:
        raise ValueError("Hosted research reader did not verify the expected evidence")
    result = {"url": PUBLIC_URL, **expected, "reader_checks": reader["passed"], "verified_at": utc_now()}
    save(directory / ("rollback-verified.json" if rollback else "hosted-verified.json"), result)
    return result


def record(directory: Path) -> dict:
    directory = validate_directory(directory)
    verified = load(directory / "hosted-verified.json")
    persisted = load(directory / "persisted.json")
    state = {"schema": "observatory-publication-status-v1", "status": "published", **verified,
        "checkpoint": persisted["release_tag"], "workflow_run": os.environ.get("GITHUB_RUN_ID"),
        "source_commit": os.environ.get("GITHUB_SHA"), "interval_hours": 2, "execution": "github-actions"}
    # Actual publication status is committed for a durable, public operations trail.
    # Runtime code changes and private local history are never pushed by this job.
    path = f"repos/{REPOSITORY}/contents/{STATE_PATH}"
    current = subprocess.run(["gh", "api", path], capture_output=True, text=True)
    payload = {"message": f"Record verified publication r{verified['revision']}", "branch": "main",
        "content": base64.b64encode((json.dumps(state, indent=2) + "\n").encode()).decode()}
    if current.returncode == 0:
        payload["sha"] = json.loads(current.stdout)["sha"]
    elif "404" not in current.stderr:
        raise ValueError("Could not read the previous public publication status")
    result = subprocess.run(["gh", "api", "--method", "PUT", path, "--input", "-"],
        input=json.dumps(payload), capture_output=True, text=True)
    if result.returncode:
        raise ValueError("Could not record the verified public publication status")
    return state


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "build", "persist", "verify", "record"))
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--bootstrap", action="store_true")
    parser.add_argument("--skip-collect", action="store_true")
    parser.add_argument("--rollback", action="store_true")
    args = parser.parse_args()
    if args.command == "prepare":
        result = prepare(args.directory, bootstrap=args.bootstrap)
    elif args.command == "build":
        result = build(args.directory, skip_collect=args.skip_collect)
    elif args.command == "persist":
        result = persist(args.directory)
    elif args.command == "verify":
        result = verify(args.directory, rollback=args.rollback)
    else:
        result = record(args.directory)
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
