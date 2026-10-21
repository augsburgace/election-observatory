"""Rotate sanitized public collector checkpoints using GitHub's ephemeral token.

Only this Observatory repository and machine-owned release prefix are supported.
Credentials come from gh's environment; they never enter arguments or metadata.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path, PurePosixPath

REPOSITORY = "augsburgace/election-observatory"
PREFIX = "collector-checkpoint-"
SCHEMA = "observatory-cloud-checkpoint-v1"
SEED_SCHEMA = "observatory-public-collector-seed-v1"
SEED_NAME = "collector-seed.zip"
METADATA_NAME = "checkpoint.json"
SITE_NAME = "publication-site.tar.gz"
MAX_ASSET_BYTES = 2 * 1024**3 - 1
MAX_EXPANDED_BYTES = 12 * 1024**3
MAX_SITE_BYTES = 1024**3
MAX_SITE_FILES = 20_000
MAX_METADATA_BYTES = 16_384
RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}")
SHA256 = re.compile(r"[0-9a-f]{64}")
STATES = frozenset("AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY".split())


def _gh(arguments: list[str], *, timeout: int = 120) -> str:
    try:
        completed = subprocess.run(["gh", *arguments], check=True, capture_output=True,
                                   text=True, timeout=timeout)
        return completed.stdout
    except (OSError, subprocess.SubprocessError):
        # gh errors may include server responses, local paths or auth diagnostics.
        raise ValueError("The approved GitHub checkpoint operation failed") from None


def _api(path: str) -> dict | list:
    return json.loads(_gh(["api", f"repos/{REPOSITORY}/{path}"]))


def _digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _revision(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError("A nonnegative integer evidence revision is required")
    return value


def _tag(run_id: str) -> str:
    if not isinstance(run_id, str) or not RUN_ID.fullmatch(run_id):
        raise ValueError("Checkpoint run identity must contain only letters, numbers, underscores or hyphens")
    return PREFIX + run_id


def validate_metadata(value: object, *, tag: str | None = None) -> dict:
    expected = {"schema", "repository", "run_id", "revision", "as_of", "created_at", "seed"}
    if (not isinstance(value, dict) or set(value) not in (expected, expected | {"site"}) or value.get("schema") != SCHEMA
            or value.get("repository") != REPOSITORY):
        raise ValueError("Unsupported public checkpoint metadata")
    actual_tag = _tag(value["run_id"])
    if tag is not None and actual_tag != tag:
        raise ValueError("Checkpoint release identity does not match its metadata")
    _revision(value["revision"])
    try:
        if date.fromisoformat(value["as_of"]).isoformat() != value["as_of"]:
            raise ValueError
        timestamp = datetime.fromisoformat(value["created_at"].replace("Z", "+00:00"))
        if timestamp.utcoffset() is None:
            raise ValueError
    except (TypeError, ValueError, AttributeError):
        raise ValueError("Checkpoint chronology must use an ISO date and timezone-aware timestamp") from None
    seed = value["seed"]
    if (not isinstance(seed, dict) or set(seed) != {"file", "sha256", "bytes"}
            or seed.get("file") != SEED_NAME or not isinstance(seed.get("sha256"), str)
            or not SHA256.fullmatch(seed["sha256"]) or not isinstance(seed.get("bytes"), int)
            or isinstance(seed["bytes"], bool) or not 0 < seed["bytes"] <= MAX_ASSET_BYTES):
        raise ValueError("Checkpoint asset identity, checksum or free release size limit is invalid")
    if "site" in value:
        site = value["site"]
        if (not isinstance(site, dict) or set(site) != {"file", "sha256", "manifest_sha256", "bytes", "expanded_bytes", "files"}
                or site.get("file") != SITE_NAME or not isinstance(site.get("sha256"), str)
                or not SHA256.fullmatch(site["sha256"])
                or not isinstance(site.get("manifest_sha256"), str)
                or not SHA256.fullmatch(site["manifest_sha256"])
                or any(not isinstance(site.get(key), int) or isinstance(site[key], bool)
                       for key in ("bytes", "expanded_bytes", "files"))
                or not 0 < site["bytes"] <= MAX_ASSET_BYTES
                or not 0 < site["expanded_bytes"] <= MAX_SITE_BYTES
                or not 0 < site["files"] <= MAX_SITE_FILES):
            raise ValueError("Checkpoint rollback site metadata exceeds its bounded public scope")
    return value


def _validate_site(directory: Path, revision: int, expected_manifest_sha256: str | None = None) -> str:
    try:
        manifest_path = directory / "public-data" / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        if (not (directory / "index.html").is_file() or manifest.get("dataset_revision") != revision
                or not isinstance(manifest.get("states"), list) or len(manifest["states"]) != 50
                or set(manifest["states"]) != STATES):
            raise ValueError
        manifest_sha256 = _digest(manifest_path)
        if expected_manifest_sha256 is not None and manifest_sha256 != expected_manifest_sha256:
            raise ValueError
        return manifest_sha256
    except (OSError, ValueError, KeyError, TypeError):
        raise ValueError("Rollback site must contain the matching verified 50-state publication") from None


def _pack_site(directory: Path, target: Path, revision: int) -> dict:
    manifest_sha256 = _validate_site(directory, revision)
    files = []
    expanded = 0
    for source in sorted(directory.rglob("*")):
        if source.is_symlink() or not (source.is_file() or source.is_dir()):
            raise ValueError("Rollback sites cannot contain links or special files")
        if not source.is_file():
            continue
        files.append(source)
        expanded += source.stat().st_size
    if not files or len(files) > MAX_SITE_FILES or not 0 < expanded <= MAX_SITE_BYTES:
        raise ValueError("Rollback publication exceeds its free site size or file-count limit")
    with tarfile.open(target, "w:gz", compresslevel=1) as archive:
        for source in files:
            info = archive.gettarinfo(str(source), arcname=source.relative_to(directory).as_posix())
            info.uid, info.gid, info.uname, info.gname, info.mtime, info.mode = 0, 0, "", "", 0, 0o644
            with source.open("rb") as incoming:
                archive.addfile(info, incoming)
    if target.stat().st_size > MAX_ASSET_BYTES:
        raise ValueError("Rollback publication exceeds GitHub's 2 GiB asset limit")
    return {"file": SITE_NAME, "sha256": _digest(target), "bytes": target.stat().st_size,
        "manifest_sha256": manifest_sha256, "expanded_bytes": expanded, "files": len(files)}


def _extract_site(source: Path, destination: Path, revision: int, expected: dict) -> None:
    destination.mkdir()
    files, expanded, names = 0, 0, set()
    try:
        with tarfile.open(source, "r|gz") as archive:
            for member in archive:
                name = member.name
                relative = PurePosixPath(name)
                if (not member.isfile() or relative.is_absolute() or ".." in relative.parts
                        or "\\" in name or str(relative) != name or name in names
                        or member.size < 0):
                    raise ValueError("Unsafe rollback publication archive member")
                names.add(name)
                files += 1
                expanded += member.size
                if files > expected["files"] or expanded > expected["expanded_bytes"]:
                    raise ValueError("Rollback publication exceeds its declared size")
                target = destination / name
                target.parent.mkdir(parents=True, exist_ok=True)
                incoming = archive.extractfile(member)
                if incoming is None:
                    raise ValueError("Rollback publication member has no content")
                with incoming, target.open("xb") as outgoing:
                    shutil.copyfileobj(incoming, outgoing, length=1024 * 1024)
        if files != expected["files"] or expanded != expected["expanded_bytes"]:
            raise ValueError("Rollback publication does not match its complete archive manifest")
        _validate_site(destination, revision, expected["manifest_sha256"])
    except (OSError, tarfile.TarError, ValueError):
        shutil.rmtree(destination)
        raise ValueError("Rollback publication failed safe extraction or revision validation") from None


def validate_seed(path: Path, revision: int) -> None:
    """Check the public export envelope; restore_seed verifies each expanded file."""
    _revision(revision)
    if not path.is_file() or not 0 < path.stat().st_size <= MAX_ASSET_BYTES:
        raise ValueError("Checkpoint ZIP must be smaller than GitHub's 2 GiB asset limit")
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)) or archive.getinfo("manifest.json").file_size > 4_000_000:
                raise ValueError
            manifest = json.loads(archive.read("manifest.json"))
            if (manifest.get("schema") != SEED_SCHEMA or manifest.get("revision") != revision
                    or manifest.get("private_notebook_rows") != 0 or manifest.get("private_job_rows") != 0):
                raise ValueError
            entries = manifest["entries"]
            if not isinstance(entries, list) or not entries:
                raise ValueError
            files = {item["file"]: item for item in entries}
            if (len(files) != len(entries) or set(names) != set(files) | {"manifest.json"}
                    or "observatory.sqlite3" not in files):
                raise ValueError
            total = 0
            for name, item in files.items():
                parts = PurePosixPath(name)
                allowed = (name == "observatory.sqlite3"
                    or (name.startswith("geometry/") and parts.suffix in {".json", ".geojson"})
                    or bool(re.fullmatch(r"archive/[0-9a-f]{2}/[0-9a-f]{64}", name)))
                if (not allowed or parts.is_absolute() or ".." in parts.parts or "\\" in name
                        or not isinstance(item["bytes"], int) or isinstance(item["bytes"], bool)
                        or item["bytes"] < 0 or archive.getinfo(name).file_size != item["bytes"]
                        or not SHA256.fullmatch(item["sha256"])):
                    raise ValueError
                total += item["bytes"]
            if total > MAX_EXPANDED_BYTES:
                raise ValueError
    except (OSError, zipfile.BadZipFile, KeyError, TypeError, ValueError):
        raise ValueError("Checkpoint is not a verified sanitized aggregate export") from None


def _all_releases() -> list[dict]:
    pages = json.loads(_gh(["api", f"repos/{REPOSITORY}/releases?per_page=100", "--paginate", "--slurp"]))
    return [value for page in pages for value in page if isinstance(value, dict)]


def _releases() -> list[dict]:
    values = _all_releases()
    selected = [value for value in values if isinstance(value, dict)
        and isinstance(value.get("tag_name"), str) and value["tag_name"].startswith(PREFIX)
        and not value.get("draft") and value.get("published_at")]
    return sorted(selected, key=lambda value: value["published_at"], reverse=True)


def _assets(release: dict, metadata: dict, *, require_digest: bool = False) -> None:
    assets = release.get("assets", [])
    indexed = {asset.get("name"): asset for asset in assets}
    expected = {SEED_NAME, METADATA_NAME} | ({SITE_NAME} if "site" in metadata else set())
    if len(indexed) != len(assets) or set(indexed) != expected:
        raise ValueError("Checkpoint release does not contain exactly its completed assets")
    seed = indexed[SEED_NAME]
    actual_digest = seed.get("digest")
    if (seed.get("state") != "uploaded" or seed.get("size") != metadata["seed"]["bytes"]
            or indexed[METADATA_NAME].get("state") != "uploaded"
            or not 0 < indexed[METADATA_NAME].get("size", 0) <= MAX_METADATA_BYTES
            or (actual_digest is not None and actual_digest != "sha256:" + metadata["seed"]["sha256"])
            or (require_digest and actual_digest is None)):
        raise ValueError("Checkpoint release asset metadata does not agree with its manifest")
    if "site" in metadata:
        site = indexed[SITE_NAME]
        site_digest = site.get("digest")
        if (site.get("state") != "uploaded" or site.get("size") != metadata["site"]["bytes"]
                or (site_digest is not None and site_digest != "sha256:" + metadata["site"]["sha256"])
                or (require_digest and site_digest is None)):
            raise ValueError("Rollback site asset does not agree with its checksum manifest")


def _download_metadata(release: dict, directory: Path) -> dict:
    _gh(["release", "download", release["tag_name"], "--repo", REPOSITORY,
         "--pattern", METADATA_NAME, "--dir", str(directory)], timeout=120)
    path = directory / METADATA_NAME
    if not path.is_file() or path.stat().st_size > MAX_METADATA_BYTES:
        raise ValueError("Checkpoint metadata is absent or oversized")
    metadata = validate_metadata(json.loads(path.read_text()), tag=release["tag_name"])
    _assets(release, metadata)
    return metadata


def download(destination: Path, *, with_site: bool = False, revision: int | None = None,
             site_manifest_sha256: str | None = None) -> dict:
    if revision is not None:
        _revision(revision)
    if site_manifest_sha256 is not None:
        if not with_site or not isinstance(site_manifest_sha256, str) or not SHA256.fullmatch(site_manifest_sha256):
            raise ValueError("Exact rollback manifest selection requires --with-site and a SHA-256 digest")
    if destination.exists() and any(destination.iterdir()):
        raise ValueError("Choose an empty checkpoint download directory")
    destination.mkdir(parents=True, exist_ok=True)
    for release in _releases():
        try:
            with tempfile.TemporaryDirectory(prefix="checkpoint-", dir=destination) as temporary:
                stage = Path(temporary)
                metadata = _download_metadata(release, stage)
                if revision is not None and metadata["revision"] != revision:
                    continue
                if (site_manifest_sha256 is not None
                        and metadata.get("site", {}).get("manifest_sha256") != site_manifest_sha256):
                    continue
                if with_site and "site" not in metadata:
                    raise ValueError("Checkpoint does not preserve its matching rollback site")
                _gh(["release", "download", release["tag_name"], "--repo", REPOSITORY,
                     "--pattern", SEED_NAME, "--dir", str(stage)], timeout=1800)
                seed = stage / SEED_NAME
                if (not seed.is_file() or seed.stat().st_size != metadata["seed"]["bytes"]
                        or _digest(seed) != metadata["seed"]["sha256"]):
                    raise ValueError("Checkpoint download checksum failed")
                validate_seed(seed, metadata["revision"])
                if with_site:
                    _gh(["release", "download", release["tag_name"], "--repo", REPOSITORY,
                         "--pattern", SITE_NAME, "--dir", str(stage)], timeout=1800)
                    site = stage / SITE_NAME
                    if (not site.is_file() or site.stat().st_size != metadata["site"]["bytes"]
                            or _digest(site) != metadata["site"]["sha256"]):
                        raise ValueError("Rollback publication download checksum failed")
                    _extract_site(site, stage / "site", metadata["revision"], metadata["site"])
                    (stage / "site").replace(destination / "site")
                seed.replace(destination / SEED_NAME)
                (stage / METADATA_NAME).replace(destination / METADATA_NAME)
                return {"seed": SEED_NAME, "checkpoint": METADATA_NAME, "revision": metadata["revision"],
                    "release_tag": release["tag_name"], "metadata": metadata,
                    **({"site": "site"} if with_site else {})}
        except (OSError, ValueError, TypeError, KeyError):
            # A partial/corrupt newest checkpoint cannot destroy a valid older one.
            # The publication runtime separately refuses any revision older than live.
            continue
    raise ValueError("No completed, checksum-verified public checkpoint is available")


def publish(seed: Path, revision: int, run_id: str, as_of: str, *, site: Path | None = None) -> dict:
    tag = _tag(run_id)
    validate_seed(seed, revision)
    metadata = validate_metadata({"schema": SCHEMA, "repository": REPOSITORY, "run_id": run_id,
        "revision": revision, "as_of": as_of, "created_at": datetime.now(timezone.utc).isoformat(),
        "seed": {"file": SEED_NAME, "sha256": _digest(seed), "bytes": seed.stat().st_size}}, tag=tag)
    with tempfile.TemporaryDirectory(prefix="public-checkpoint-") as temporary:
        stage = Path(temporary)
        upload = stage / SEED_NAME
        try:
            os.link(seed, upload)
        except OSError:
            shutil.copyfile(seed, upload)
        context = stage / METADATA_NAME
        if site is not None:
            metadata["site"] = _pack_site(site, stage / SITE_NAME, revision)
            validate_metadata(metadata, tag=tag)
        context.write_text(json.dumps(metadata, indent=2) + "\n")
        _gh(["release", "create", tag, "--repo", REPOSITORY, "--draft", "--title",
             f"Collector checkpoint: evidence revision {revision}", "--notes",
             "Machine-generated sanitized aggregate collector state. Private notebooks, original voter records and credentials are excluded."])
        uploads = [str(upload), str(context)] + ([str(stage / SITE_NAME)] if site is not None else [])
        _gh(["release", "upload", tag, *uploads, "--repo", REPOSITORY], timeout=1800)
        # Draft releases may not have a Git tag yet, so the by-tag endpoint can
        # return 404 even to their authenticated creator. Locate the draft in
        # the authenticated release inventory, then verify it by numeric ID.
        matches = [value for value in _all_releases()
            if value.get("tag_name") == tag and value.get("draft") is True]
        if (len(matches) != 1 or not isinstance(matches[0].get("id"), int)
                or isinstance(matches[0]["id"], bool) or matches[0]["id"] <= 0):
            raise ValueError("GitHub did not identify the unique uploaded draft checkpoint")
        release = _api(f"releases/{matches[0]['id']}")
        if not isinstance(release, dict) or release.get("tag_name") != tag or release.get("draft") is not True:
            raise ValueError("New checkpoint must remain a draft until both assets are verified")
        _assets(release, metadata)
        _gh(["release", "edit", tag, "--repo", REPOSITORY, "--draft=false", "--latest=false"])
        completed = _api(f"releases/tags/{tag}")
        if (not isinstance(completed, dict) or completed.get("tag_name") != tag
                or completed.get("draft") or not completed.get("published_at")):
            raise ValueError("GitHub did not confirm a completed public checkpoint")
        _assets(completed, metadata)
    return {"release_tag": tag, "revision": revision, "metadata": metadata}


def prune(keep: int = 3) -> dict:
    """Explicit managed-cache rotation; preserve bootstrap and three verified states."""
    if not isinstance(keep, int) or isinstance(keep, bool) or not 3 <= keep <= 100:
        raise ValueError("Retain between three and 100 completed collector checkpoints")
    verified, protected, skipped, deleted = [], [], [], []
    for release in _releases():
        tag = release["tag_name"]
        if tag == PREFIX + "bootstrap" or tag.startswith(PREFIX + "bootstrap-"):
            protected.append(tag)
            continue
        try:
            with tempfile.TemporaryDirectory(prefix="checkpoint-retention-") as temporary:
                metadata = _download_metadata(release, Path(temporary))
                # Without GitHub's independent uploaded-byte digest, retain safely.
                _assets(release, metadata, require_digest=True)
            verified.append(release)
        except (OSError, ValueError, TypeError, KeyError):
            skipped.append(tag)
    for release in verified[keep:]:
        tag = release["tag_name"]
        _gh(["release", "delete", tag, "--repo", REPOSITORY, "--yes", "--cleanup-tag"])
        deleted.append(tag)
    return {"deleted": deleted, "retained": [value["tag_name"] for value in verified[:keep]],
        "protected": protected, "unverified_retained": skipped}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    fetch = commands.add_parser("download")
    fetch.add_argument("--destination", type=Path, required=True)
    fetch.add_argument("--with-site", action="store_true")
    fetch.add_argument("--revision", type=int, help="Require the exact live evidence revision for rollback")
    fetch.add_argument("--site-manifest-sha256", help="Require the exact live publication manifest for rollback")
    save = commands.add_parser("publish")
    save.add_argument("--seed", type=Path, required=True)
    save.add_argument("--revision", type=int, required=True)
    save.add_argument("--run-id", required=True)
    save.add_argument("--as-of", required=True)
    save.add_argument("--site", type=Path)
    rotate = commands.add_parser("prune")
    rotate.add_argument("--keep", type=int, default=3)
    arguments = parser.parse_args()
    if arguments.command == "download":
        result = download(arguments.destination, with_site=arguments.with_site, revision=arguments.revision,
                          site_manifest_sha256=arguments.site_manifest_sha256)
    elif arguments.command == "publish":
        result = publish(arguments.seed, arguments.revision, arguments.run_id, arguments.as_of, site=arguments.site)
    else:
        result = prune(arguments.keep)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
