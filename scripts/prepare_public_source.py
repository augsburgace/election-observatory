"""Export reviewed application code without the private repository's history.

The public distribution has its own Git history. Runtime files are never read,
and local verification records containing saved-view metadata are replaced with
public release references. The original checkout and its history stay intact.
"""
from __future__ import annotations

import argparse
import io
import json
import re
import subprocess
import tarfile
from pathlib import Path, PurePosixPath

PRIVATE_VERIFICATION = {
    "docs/VERIFICATION.md", "docs/ATLAS_DEPTH_RECOVERY.md", "docs/ATLAS_RECOVERY.md",
}
PUBLIC_VERIFICATION = """# Verification and recovery

Detailed local recovery records remain in the private development repository.
This public distribution excludes saved-view titles, private report captions,
backup locations, personal notes, and the private repository's Git history.

See [the public release record](FREE_WEB_RELEASE.md),
[cloud operation](CLOUD_UPDATES.md), and [setup](../README.md) for the public
verification results and supported operating procedures.
"""


def prepare_public_source(repository: Path, output: Path, revision: str = "HEAD") -> dict:
    if revision != "HEAD" and not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("Choose HEAD or a complete reviewed commit SHA")
    if output.exists():
        raise ValueError("Public source output must be a new directory")
    commit = subprocess.check_output(["git", "rev-parse", "--verify", revision + "^{commit}"],
                                     cwd=repository, text=True).strip()
    payload = subprocess.check_output(["git", "archive", "--format=tar", commit], cwd=repository)
    output.mkdir(parents=True)
    files = 0
    redacted_files = 0
    owner_home = str(Path.home())
    with tarfile.open(fileobj=io.BytesIO(payload)) as archive:
        for member in archive:
            name = PurePosixPath(member.name)
            if name.is_absolute() or ".." in name.parts or any(part in {".git", ".local", "node_modules", ".venv"} for part in name.parts):
                raise ValueError("Unsafe source archive path")
            target = output.joinpath(*name.parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if (not member.isfile() or target.suffix.lower() in {".zip", ".sqlite", ".sqlite3", ".db", ".pem", ".key"}
                    or name.name.lower().startswith(".env") or name.name.lower() in {"auth.json", "token"}):
                raise ValueError("Runtime, credential or unsupported file in tracked public source")
            source = archive.extractfile(member)
            assert source is not None
            raw = source.read()
            if member.name in PRIVATE_VERIFICATION:
                raw = PUBLIC_VERIFICATION.encode()
                redacted_files += 1
            else:
                try:
                    text = raw.decode("utf-8")
                except UnicodeDecodeError:
                    pass
                else:
                    if owner_home in text:
                        raw = text.replace(owner_home, "/Users/LOCAL_USER").encode()
                        redacted_files += 1
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
            target.chmod(0o755 if member.mode & 0o111 else 0o644)
            files += 1
    proof = {"schema": "observatory-public-source-v1", "source_commit": commit,
             "files": files, "redacted_files": redacted_files, "private_history_included": False}
    (output / ".public-source.json").write_text(json.dumps(proof, indent=2) + "\n")
    return proof


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--revision", default="HEAD")
    parser.add_argument("--repository", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    print(json.dumps(prepare_public_source(args.repository, args.output, args.revision), indent=2))
