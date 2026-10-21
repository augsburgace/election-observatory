from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(os.environ.get("OBSERVATORY_PROJECT_ROOT", str(Path(__file__).resolve().parents[2]))).expanduser().resolve()
LOCAL_HOSTS = ("localhost", "127.0.0.1", "testserver")
LOCAL_ORIGINS = ("http://127.0.0.1:5173", "http://localhost:5173", "http://127.0.0.1:8776", "http://localhost:8776")


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    project_root: Path = PROJECT_ROOT
    host: str = "127.0.0.1"
    port: int = 8776
    public_mode: bool = False
    allowed_hosts: tuple[str, ...] = LOCAL_HOSTS
    allowed_origins: tuple[str, ...] = LOCAL_ORIGINS

    def __post_init__(self) -> None:
        if not self.allowed_hosts or (self.public_mode and any("*" in host for host in self.allowed_hosts)):
            raise ValueError("Public hosting requires an explicit non-wildcard host allowlist")
        if self.public_mode and "*" in self.allowed_origins:
            raise ValueError("Public hosting does not support wildcard origins")

    @property
    def deployment_mode(self) -> str:
        return "public" if self.public_mode else "local"

    @property
    def database_path(self) -> Path:
        return self.data_dir / "observatory.sqlite3"

    @property
    def archive_dir(self) -> Path:
        return self.data_dir / "archive"

    def prepare(self) -> None:
        for path in (self.data_dir, self.archive_dir, self.data_dir / "staging", self.data_dir / "exports", self.data_dir / "backups"):
            path.mkdir(parents=True, exist_ok=True)


def get_settings() -> Settings:
    default = Path.home() / "Library" / "Application Support" / "Battleground Senate Observatory"
    flag = os.environ.get("OBSERVATORY_PUBLIC_MODE", "false").strip().lower()
    if flag not in {"true", "false", "1", "0"}:
        raise ValueError("OBSERVATORY_PUBLIC_MODE must be true or false")
    public_mode = flag in {"true", "1"}
    raw_hosts = os.environ.get("OBSERVATORY_ALLOWED_HOSTS")
    if public_mode and not raw_hosts:
        raise ValueError("Set OBSERVATORY_ALLOWED_HOSTS explicitly before public hosting")
    hosts = tuple(p.strip() for p in raw_hosts.split(",") if p.strip()) if raw_hosts else LOCAL_HOSTS
    raw_origins = os.environ.get("OBSERVATORY_ALLOWED_ORIGINS")
    origins = tuple(p.strip().rstrip("/") for p in raw_origins.split(",") if p.strip()) if raw_origins else (() if public_mode else LOCAL_ORIGINS)
    root = Path(os.environ.get("OBSERVATORY_PROJECT_ROOT", str(PROJECT_ROOT))).expanduser().resolve()
    return Settings(Path(os.environ.get("OBSERVATORY_DATA_DIR", str(default))).expanduser(), project_root=root,
                    public_mode=public_mode, allowed_hosts=hosts, allowed_origins=origins)


def local_today() -> str:
    return datetime.now(ZoneInfo("America/New_York")).date().isoformat()
