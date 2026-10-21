from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.prepare_public_source import prepare_public_source


def commit_source(root: Path) -> None:
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                    "commit", "-qm", "Test source"], cwd=root, check=True)


def test_public_distribution_has_no_private_history_or_saved_metadata(tmp_path):
    repo = tmp_path / "private"
    (repo / "docs").mkdir(parents=True)
    (repo / "docs/VERIFICATION.md").write_text("PRIVATE_SAVED_VIEW_TITLE")
    (repo / "README.md").write_text(f"Example path: {Path.home()}/private-backup.zip")
    commit_source(repo)
    (repo / "untracked-private.txt").write_text("PRIVATE_NOTE")
    out = tmp_path / "public"
    proof = prepare_public_source(repo, out)
    assert not (out / ".git").exists() and not (out / "untracked-private.txt").exists()
    assert "PRIVATE_SAVED_VIEW_TITLE" not in (out / "docs/VERIFICATION.md").read_text()
    assert str(Path.home()) not in (out / "README.md").read_text()
    assert proof["private_history_included"] is False
    assert (repo / "docs/VERIFICATION.md").read_text() == "PRIVATE_SAVED_VIEW_TITLE"


def test_tracked_runtime_files_cannot_enter_public_source(tmp_path):
    repo = tmp_path / "private"
    repo.mkdir()
    (repo / "private.sqlite3").write_bytes(b"private")
    commit_source(repo)
    with pytest.raises(ValueError, match="Runtime"):
        prepare_public_source(repo, tmp_path / "public")


def test_export_never_replaces_an_existing_tree(tmp_path):
    out = tmp_path / "existing"
    out.mkdir()
    with pytest.raises(ValueError, match="new directory"):
        prepare_public_source(tmp_path, out)
