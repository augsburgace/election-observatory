"""Package the real aggregate edition for free static hosting, without a backend."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import shutil
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.public_object_packs import (
    PublicObjectReader,
    decoded_bytes,
    pack_public_objects,
    safe_public_path,
)

GITHUB_PAGES_MAX_BYTES = 950_000_000  # Headroom below the published 1 GB site limit.
PROVIDERS = {"cloudflare", "vercel", "github"}


def _owned_generated_stages(directory: str, names: list[str]) -> list[str]:
    """Vite copies public/ directories; temporary publication stages are not assets."""
    return [name for name in names if (name.startswith(".public-data-") or name.startswith("public-data.previous-"))
            and (Path(directory) / name).is_dir()]


def prepare_site(dist: Path, output: Path, *, provider: str = "cloudflare") -> dict:
    if provider not in PROVIDERS:
        raise ValueError("Unsupported static hosting provider")
    if output.exists():
        raise ValueError("Choose a new site directory so an existing release is preserved")
    source_manifest = dist / "public-data" / "manifest.json"
    manifest = json.loads(source_manifest.read_text())
    if len(manifest.get("states", [])) != 50:
        raise ValueError("A public release must represent all 50 states")
    if not (dist / "index.html").is_file():
        raise ValueError("Build the real React application first")
    shutil.copytree(dist, output, ignore=_owned_generated_stages)
    transport = pack_public_objects(output / "public-data", manifest)
    files = transport["logical_objects"]
    total_before = transport["original_bytes"]
    for path in (output / "public-data" / "objects").rglob("*"):
        if not path.is_file() or not (path.name.endswith(".json") or path.name.endswith(".json.gz")):
            continue
        stored = path.read_bytes()
        raw = gzip.decompress(stored) if stored.startswith(b"\x1f\x8b") else stored
        packed = gzip.compress(raw, compresslevel=7, mtime=0)
        path.write_bytes(packed)
    total_after = sum(path.stat().st_size for name in ("objects", "packs")
        for path in (output / "public-data" / name).rglob("*") if path.is_file())
    manifest["transport"].update({"encoding": "gzip", "scope": "object packs and standalone objects",
                                 "stored_bytes": total_after})
    (output / "public-data" / "manifest.json").write_text(json.dumps(manifest, separators=(",", ":")))
    config = {"$schema": "https://openapi.vercel.sh/vercel.json", "framework": None,
        "buildCommand": "", "installCommand": "", "outputDirectory": ".",
        "headers": [
            {"source": "/public-data/objects/(.*)", "headers": [
                {"key": "Content-Encoding", "value": "gzip"},
                {"key": "Content-Type", "value": "application/json; charset=utf-8"},
                {"key": "Cache-Control", "value": "public, max-age=31536000, immutable"}]},
            {"source": "/public-data/packs/(.*)", "headers": [
                {"key": "Content-Encoding", "value": "gzip"},
                {"key": "Content-Type", "value": "application/json; charset=utf-8"},
                {"key": "Cache-Control", "value": "public, max-age=31536000, immutable"}]},
            {"source": "/public-data/manifest.json", "headers": [
                {"key": "Cache-Control", "value": "public, max-age=0, must-revalidate"}]},
            {"source": "/(.*)", "headers": [
                {"key": "X-Content-Type-Options", "value": "nosniff"},
                {"key": "Referrer-Policy", "value": "strict-origin-when-cross-origin"},
                {"key": "Permissions-Policy", "value": "camera=(), microphone=(), geolocation=()"}]}],
        "rewrites": [{"source": "/", "destination": "/index.html"}]}
    (output / "vercel.json").write_text(json.dumps(config, indent=2))
    (output / ".nojekyll").touch()
    # Cloudflare serves these as ordinary files. The reader detects gzip and
    # validates decoded bytes, independently of automatic HTTP compression.
    (output / "_headers").write_text("/public-data/manifest.json\n  Cache-Control: public, max-age=0, must-revalidate\n/public-data/objects/*\n  Cache-Control: public, max-age=31536000, immutable\n/public-data/packs/*\n  Cache-Control: public, max-age=31536000, immutable\n/*\n  X-Content-Type-Options: nosniff\n  Referrer-Policy: strict-origin-when-cross-origin\n  Permissions-Policy: camera=(), microphone=(), geolocation=()\n")
    proof = verify_site(output, provider=provider)
    return {**proof, "objects": files, "uncompressed_object_bytes": total_before,
            "compressed_object_bytes": total_after}


def verify_site(site: Path, *, provider: str = "cloudflare") -> dict:
    if provider not in PROVIDERS:
        raise ValueError("Unsupported static hosting provider")
    manifest = json.loads((site / "public-data" / "manifest.json").read_text())
    if len(manifest.get("states", [])) != 50:
        raise ValueError("Missing state coverage")
    reader = PublicObjectReader(site / "public-data", manifest)
    verified = 0
    for name in reader.names():
        raw = reader.read(name)
        reader.verify_references(json.loads(raw))
        verified += 1
    for name in manifest["requests"].values():
        path = name if isinstance(name, str) else name["path"]
        expected = reader.expected_hash(path)
        if isinstance(name, dict) and name.get("sha256") != expected:
            raise ValueError("An API request names an incorrect aggregate hash")
    for group in ("reports", "catalogs", "evidence_buckets"):
        for descriptor in manifest.get(group, {}).values():
            path = descriptor if isinstance(descriptor, str) else descriptor["path"]
            expected = reader.expected_hash(path)
            if isinstance(descriptor, dict) and descriptor.get("sha256") != expected:
                raise ValueError("A research descriptor names an incorrect aggregate hash")
    allowed = set(reader.physical)
    for directory in ("objects", "packs"):
        for path in (site / "public-data" / directory).rglob("*"):
            if path.is_file() and str(path.relative_to(site / "public-data")) not in allowed:
                raise ValueError("An unlisted aggregate file remains in the public artifact")
    for descriptor in reader.physical.values():
        path = safe_public_path(site / "public-data", descriptor["path"])
        if hashlib.sha256(decoded_bytes(path)).hexdigest() != descriptor["sha256"]:
            raise ValueError("Physical public aggregate integrity mismatch")
    unsafe = [str(p.relative_to(site)) for p in site.rglob("*") if p.is_file() and
        (p.suffix.lower() in {".sqlite3", ".sqlite", ".db", ".zip", ".env", ".py", ".pem", ".key"}
         or p.name.lower().startswith(".env") or p.name.lower() in {"auth.json", "token"}
         or any(part in {"archive", "backups", "source-captures", ".git", "fetch-cache"} for part in p.relative_to(site).parts))]
    if unsafe:
        raise ValueError("Private source, archive or runtime file found in public artifact")
    total = sum(p.stat().st_size for p in site.rglob("*") if p.is_file())
    physical_files = [p for p in site.rglob("*") if p.is_file()]
    if provider == "cloudflare" and (len(physical_files) > 20_000 or any(p.stat().st_size > 25 * 1024**2 for p in physical_files)):
        raise ValueError("Cloudflare Free allows at most 20,000 files and 25 MiB per file")
    if provider == "vercel" and total > 95_000_000:
        raise ValueError(f"Static artifact is {total:,} bytes; reduce publication scope to remain below the free deployment allowance")
    if provider == "github" and total > GITHUB_PAGES_MAX_BYTES:
        raise ValueError("GitHub Pages publication exceeds the bounded free site allowance")
    return {"dataset_revision": manifest["dataset_revision"], "states": len(manifest["states"]),
            "requests": len(manifest["requests"]), "objects_verified": verified, "site_bytes": total,
            "private_runtime_files": 0, "physical_files": len(physical_files), "provider": provider}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist", type=Path, default=Path("frontend/dist"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--provider", choices=sorted(PROVIDERS), default="cloudflare")
    args = parser.parse_args()
    print(json.dumps(prepare_site(args.dist, args.output, provider=args.provider), indent=2))
