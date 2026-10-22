"""Build a complete public release on an ephemeral, free scheduled runner.

The workflow restores a previously sanitized aggregate checkpoint into an empty
runner directory before invoking this script. This script has no deployment or
credential handling: a successful ``ready.json`` is the hand-off for publishing
the verified site and its matching next checkpoint. Failed builds leave the
previous hosted release untouched.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Iterator
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from observatory.db import Database  # noqa: E402
from observatory.domain import utc_now  # noqa: E402
from observatory.historical_comparisons import archive_boundary_review  # noqa: E402
from observatory.public_publish import publish_public_data, readonly_database  # noqa: E402
from observatory.registry import all_states  # noqa: E402
from observatory.settings import Settings, local_today  # noqa: E402

from scripts.cloud_changes import publication_key, publication_reasons, source_receipts  # noqa: E402
from scripts.prepare_web_site import prepare_site  # noqa: E402
from scripts.public_seed import create_seed  # noqa: E402
from scripts.publication_runtime import PublicationRuntime  # noqa: E402


def _event(value: dict) -> None:
    print(json.dumps(value, separators=(",", ":")), flush=True)


def _atomic_json(path: Path, value: dict) -> None:
    pending = path.with_suffix(path.suffix + ".pending")
    pending.write_text(json.dumps(value, indent=2) + "\n")
    pending.replace(path)


def validate_base(value: str) -> str:
    """Only a same-origin root or ordinary Pages project subpath is valid."""
    if not re.fullmatch(r"/(?:[A-Za-z0-9_-]+/)*", value):
        raise ValueError("The public base must be / or a slash-terminated project path")
    return value


def validate_runner_data(settings: Settings, output: Path, previous_revision: int) -> int:
    data_dir = settings.data_dir.resolve()
    private = Path.home() / "Library" / "Application Support" / "Battleground Senate Observatory"
    if data_dir == private.resolve() or data_dir.is_relative_to(private.resolve()):
        raise ValueError("The cloud publisher cannot use the private local application-data directory")
    if not settings.database_path.is_file() or settings.database_path.is_symlink():
        raise ValueError("Restore a public aggregate checkpoint into an ordinary runner directory first")
    if settings.public_mode:
        raise ValueError("The offline publication worker must use local database settings")
    if not isinstance(previous_revision, int) or isinstance(previous_revision, bool) or previous_revision < 0:
        raise ValueError("The previous published revision must be a nonnegative integer")
    if output.exists():
        raise ValueError("Choose a new output directory; previous release artifacts are never overwritten")
    resolved_output = output.resolve()
    if resolved_output.is_relative_to(data_dir) or data_dir.is_relative_to(resolved_output):
        raise ValueError("Release output and ephemeral evidence must use separate directories")
    runner_temp = os.environ.get("RUNNER_TEMP")
    if os.environ.get("GITHUB_ACTIONS") == "true" and (not runner_temp
            or not data_dir.is_relative_to(Path(runner_temp).resolve())):
        raise ValueError("GitHub collection must use an ephemeral RUNNER_TEMP evidence directory")
    uri = "file:" + quote(str(settings.database_path.resolve()), safe="/") + "?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        # A restored public seed contains neither private notebooks nor old jobs.
        for table in ("research", "jobs"):
            if connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]:
                raise ValueError("The cloud worker requires a sanitized public aggregate checkpoint")
        revision = connection.execute("SELECT COALESCE(MAX(id),0) FROM revisions").fetchone()[0]
    if revision < previous_revision:
        raise ValueError("The restored checkpoint predates the published release; restore its matching successor")
    return revision


@contextmanager
def frozen_evidence(path: Path) -> Iterator[int]:
    """Prevent writes without making another multi-gigabyte database copy.

Collection has already exited. A reserved SQLite writer lock permits all query
connections to keep reading, while excluding commits throughout publication and
the sanitized checkpoint backup. Each view therefore reads the same revision.
    """
    with sqlite3.connect(path, timeout=60) as connection:
        result = connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        if result and result[0]:
            raise ValueError("The evidence WAL is busy; refusing a mixed-revision publication")
        connection.execute("BEGIN IMMEDIATE")
        try:
            yield connection.execute("SELECT COALESCE(MAX(id),0) FROM revisions").fetchone()[0]
        finally:
            connection.rollback()


def build_cloud_publication(settings: Settings, output: Path, *, base: str,
                            previous_revision: int, skip_collect: bool = False,
                            parent_checkpoint_sha256: str | None = None,
                            previous_manifest: dict | None = None, force: bool = False) -> dict:
    """Verify site and matching sanitized checkpoint; never contact a deploy API."""
    base = validate_base(base)
    if parent_checkpoint_sha256 is not None and not re.fullmatch(r"[0-9a-f]{64}", parent_checkpoint_sha256):
        raise ValueError("The parent checkpoint digest must be a lowercase SHA-256")
    previous_seed_revision = validate_runner_data(settings, output, previous_revision)
    settings.prepare()
    output.mkdir(parents=True)
    environment = {**os.environ, "OBSERVATORY_DATA_DIR": str(settings.data_dir.resolve()),
        "OBSERVATORY_PROJECT_ROOT": str(settings.project_root), "OBSERVATORY_PUBLIC_MODE": "false"}
    started_at = utc_now()
    before_checks = {row["source_id"]: row["checked_at"] for row in source_receipts(settings.database_path)}
    with (settings.data_dir / "cloud-publication.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError("Another cloud publication is already using this evidence directory") from error
        if not skip_collect:
            # Parser tracebacks can quote an individual source record. Never
            # stream those diagnostics into public Actions logs; this ordinary
            # worker file is excluded from both the seed and the published site.
            diagnostics = settings.data_dir / "cloud-collection.private.log"
            try:
                with diagnostics.open("w") as log:
                    diagnostics.chmod(0o600)
                    # Small immutable reference source. The atlas loader skips
                    # an already validated parser version, so this adds no
                    # repeated download to ordinary two-hour source checks.
                    for dataset in ('snyder_governor_2006_2024', 'snyder_house_2006_2024'):
                        subprocess.run([sys.executable, "-m", "observatory.cli", "atlas", "--dataset", dataset],
                            cwd=settings.project_root, env=environment, check=True,
                            stdout=log, stderr=subprocess.STDOUT)
                    # Restored public checkpoints deliberately omit runtime
                    # model caches. Warming here would rebuild every forecast
                    # even when the change gate below will retain the site.
                    # The publisher computes forecasts once, after that gate,
                    # against the final frozen evidence revision.
                    subprocess.run([sys.executable, "-m", "observatory.cli", "collect", "--due"],
                        cwd=settings.project_root, env=environment, check=True,
                        stdout=log, stderr=subprocess.STDOUT)
            except (OSError, subprocess.SubprocessError):
                raise ValueError("Public source collection failed; the prior hosted release is retained. Original diagnostics remain only in ephemeral worker storage.") from None
            # Restore the two fixed official Census references before the
            # read-only publication freeze. A failed reference fetch withholds
            # county differences, while retaining both original result sets.
            boundary_database = Database(settings)
            try:
                try:
                    with diagnostics.open("a") as log, redirect_stdout(log), redirect_stderr(log):
                        boundary_review = archive_boundary_review(boundary_database)
                except Exception:
                    boundary_review = None
                _event({"stage": "boundary-review", "status": "verified" if boundary_review else "unavailable",
                    "revision": boundary_review["revision"] if boundary_review else None,
                    "detail": "Archived original Census evidence verified" if boundary_review else
                        "County differences remain withheld where original Census continuity evidence cannot be verified"})
            finally:
                boundary_database.engine.dispose()
        with frozen_evidence(settings.database_path) as revision:
            if revision < max(previous_seed_revision, previous_revision):
                raise ValueError("Collection moved evidence backwards; the prior hosted release must be retained")
            if not skip_collect:
                _event({"stage": "collection", "status": "completed", "revision": revision,
                    "diagnostics": "Original parser diagnostics are withheld from public logs and artifacts"})
            database = readonly_database(settings)
            try:
                # Freeze the research day as well as evidence: a long build
                # crossing midnight must not mix two calendar cutoffs.
                as_of = local_today()
                inputs = publication_key(settings.database_path, settings.project_root,
                    revision=revision, as_of=as_of, base=base)
                reasons = publication_reasons(previous_manifest or {}, inputs, force=force or skip_collect)
                receipts = source_receipts(settings.database_path)
                check = {"schema": "observatory-source-check-v1", "checked_at": utc_now(),
                    "revision": revision, "publication_required": bool(reasons), "reasons": reasons,
                    "checked_sources": sum(row["checked_at"] != before_checks.get(row["source_id"]) for row in receipts),
                    "failed_sources": [row["source_id"] for row in receipts if row["status"] == "failed"],
                    "source_checks": receipts}
                _atomic_json(output / "check.json", check)
                _event({key: value for key, value in check.items() if key != "source_checks"})
                if not reasons:
                    # Keep the exact hosted site and seed, avoiding all fifty
                    # state recalculations, ZIP/VACUUM and deployment transfers.
                    result = {"status": "unchanged", "dataset_revision": revision,
                        "checked_at": check["checked_at"], "deployment_performed": False}
                    _atomic_json(output / "unchanged.json", result)
                    return result
                with tempfile.TemporaryDirectory(prefix=".cloud-build-", dir=output) as temporary:
                    stage = Path(temporary)
                    bundle = stage / "public-data"
                    with PublicationRuntime(_event) as runtime:
                        manifest = publish_public_data(database, bundle, revision=revision, as_of=as_of,
                            max_files=100_000, progress=runtime.progress)
                    _event({"publication_runtime": runtime.summary()})
                    expected_states = {state["code"] for state in all_states()}
                    if (manifest.get("dataset_revision") != revision
                            or len(manifest.get("states", [])) != 50
                            or set(manifest.get("states", [])) != expected_states):
                        raise ValueError("The release does not contain the exact evidence revision and all 50 states")
                    manifest["published_at"] = utc_now()
                    manifest["publication_inputs"] = inputs
                    manifest["schedule"] = {"interval_hours": 2, "execution": "github-actions",
                        "description": "Public cloud collection and publication are scheduled every two hours. Free hosted jobs may be delayed or missed; the last validated release remains available."}
                    (bundle / "manifest.json").write_text(json.dumps(manifest, separators=(",", ":")))
                    smoke = settings.project_root / "frontend" / "scripts" / "smoke-public-data.mjs"
                    subprocess.run(["node", str(smoke), str(bundle), str(output / "reader-proof.json"),
                        "--all-states"], cwd=settings.project_root, env=environment, check=True)
                    dist = stage / "dist"
                    subprocess.run(["pnpm", "--dir", str(settings.project_root / "frontend"), "exec", "vite",
                        "build", "--outDir", str(dist)], cwd=settings.project_root, check=True,
                        env={**environment, "VITE_PUBLIC_DATA_MODE": "true", "VITE_PUBLIC_BASE": base,
                             "VITE_PUBLICATION_ID": f"{revision}-{started_at}"})
                    stale = dist / "public-data"
                    if stale.exists():
                        shutil.rmtree(stale)  # Only this process's temporary Vite output.
                    shutil.copytree(bundle, stale)
                    proof = prepare_site(dist, output / "site", provider="github")
                    subprocess.run(["node", str(smoke), str(output / "site" / "public-data"),
                        str(output / "packed-reader-proof.json"), "--all-states"],
                        cwd=settings.project_root, env=environment, check=True)
                # Drop the raw bundle and intermediate dist before copying and
                # vacuuming the sanitized checkpoint, to bound runner disk use.
                checkpoint = create_seed(database, output / "checkpoint.zip")
                if (checkpoint.get("revision") != revision or checkpoint.get("private_notebook_rows") != 0
                        or checkpoint.get("private_job_rows") != 0):
                    raise ValueError("The successor checkpoint failed revision or privacy verification")
            finally:
                database.engine.dispose()
    # The publication can take longer than collection. The visible release
    # clock describes this completed build, rather than its initial start time.
    packed_manifest = output / "site" / "public-data" / "manifest.json"
    release_manifest = json.loads(packed_manifest.read_text())
    release_manifest["published_at"] = utc_now()
    _atomic_json(packed_manifest, release_manifest)
    ready = {"schema": "observatory-cloud-publication-v1", "status": "verified", "started_at": started_at,
        "verified_at": utc_now(), "dataset_revision": revision, "data_as_of": manifest["data_as_of"],
        "previous_published_revision": previous_revision,
        "restored_revision": previous_seed_revision, "base": base, "execution": "github-actions",
        "interval_hours": 2, "site": "site", "verification": proof,
        "checkpoint": {key: value for key, value in checkpoint.items() if key != "path"},
        "parent_checkpoint_sha256": parent_checkpoint_sha256,
        "deployment_performed": False}
    _atomic_json(output / "ready.json", ready)
    _event(ready)
    return ready


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=os.environ.get("OBSERVATORY_DATA_DIR"),
        help="Explicit ephemeral directory restored from a sanitized public checkpoint")
    parser.add_argument("--output", type=Path, required=True, help="New verified release artifact directory")
    parser.add_argument("--base", required=True, help="/ for root hosting, or /repository-name/ for GitHub Pages")
    parser.add_argument("--previous-revision", type=int, required=True)
    parser.add_argument("--parent-checkpoint-sha256")
    parser.add_argument("--skip-collect", action="store_true", help="Verify and publish the restored evidence unchanged")
    args = parser.parse_args(argv)
    if args.data_dir is None:
        parser.error("An explicit --data-dir or OBSERVATORY_DATA_DIR is required; private local storage is never a default")
    settings = Settings(Path(args.data_dir).expanduser().resolve())
    build_cloud_publication(settings, args.output.expanduser().resolve(), base=args.base,
        previous_revision=args.previous_revision, skip_collect=args.skip_collect,
        parent_checkpoint_sha256=args.parent_checkpoint_sha256)


if __name__ == "__main__":
    main()
