"""Fixed-project production checkpoint and rollback using existing Wrangler auth.

Only this Observatory project can be read or changed. Credentials stay in memory
and are never written to deployment artifacts, command arguments or status files.
API reference: developers.cloudflare.com/api/resources/pages/subresources/projects/
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path
from urllib.parse import urlsplit

import httpx

ACCOUNT_ID = "be41722b274cd61360daa2ee516b47e9"
PROJECT = "battleground-senate-observatory"
PUBLIC_HOST = f"{PROJECT}.pages.dev"
API_ROOT = "https://api.cloudflare.com/client/v4"
DEPLOYMENT_ID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def validate_config(value: dict) -> dict:
    if not isinstance(value, dict) or value.get("project") != PROJECT or value.get("account_id") != ACCOUNT_ID:
        raise ValueError("Web publishing must name the approved Observatory account and Pages project")
    parsed = urlsplit(str(value.get("url", "")))
    if (parsed.scheme != "https" or parsed.hostname != PUBLIC_HOST or parsed.username or parsed.password
            or parsed.port not in (None, 443) or parsed.path not in ("", "/") or parsed.query or parsed.fragment):
        raise ValueError("Web publishing requires the approved HTTPS Observatory Pages address")
    return {**value, "url": f"https://{PUBLIC_HOST}"}


def refresh_credentials(wrangler: Path, project_root: Path) -> None:
    try:
        subprocess.run([str(wrangler), "whoami"], cwd=project_root, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=90)
    except (OSError, subprocess.SubprocessError):
        raise ValueError("Existing Cloudflare sign-in could not be refreshed; the hosted release was retained") from None


def _existing_token() -> str:
    token = os.environ.get("CLOUDFLARE_API_TOKEN")
    if token:
        return token
    legacy = Path.home() / ".wrangler"
    if legacy.is_dir():
        root = legacy
    else:
        default = Path.home() / "Library" / "Preferences" if sys.platform == "darwin" else Path.home() / ".config"
        root = Path(os.environ.get("XDG_CONFIG_HOME", str(default))) / ".wrangler"
    try:
        value = tomllib.loads((root / "config" / "default.toml").read_text())
        token = value.get("oauth_token")
        if not isinstance(token, str) or not token.strip():
            raise ValueError
        return token
    except (OSError, ValueError):
        raise ValueError("Existing default Wrangler sign-in is unavailable; no publication was attempted") from None


class CloudflarePublication:
    def __init__(self, config: dict, *, transport: httpx.BaseTransport | None = None):
        self.config = validate_config(config)
        self._client = httpx.Client(base_url=API_ROOT, timeout=60, follow_redirects=False,
            headers={"Authorization": "Bearer " + _existing_token()}, transport=transport)
        self._project_path = f"/accounts/{ACCOUNT_ID}/pages/projects/{PROJECT}"

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self._client.close()

    def _request(self, method: str, path: str) -> dict:
        try:
            response = self._client.request(method, path)
            response.raise_for_status()
            value = response.json()
            if not isinstance(value, dict) or value.get("success") is not True or not isinstance(value.get("result"), dict):
                raise ValueError
            return value["result"]
        except (httpx.HTTPError, ValueError):
            raise ValueError("The approved Cloudflare Pages operation did not return a successful result") from None

    def current_deployment(self) -> dict:
        project = self._request("GET", self._project_path)
        if project.get("name") != PROJECT:
            raise ValueError("Cloudflare returned a different Pages project; publication stopped")
        deployment = project.get("canonical_deployment") or {}
        deployment_id, branch = deployment.get("id", ""), project.get("production_branch", "")
        if (not isinstance(deployment_id, str) or not DEPLOYMENT_ID.fullmatch(deployment_id)
                or deployment.get("environment") != "production"
                or deployment.get("latest_stage", {}).get("status") != "success"
                or not isinstance(branch, str) or not branch or len(branch) > 200):
            raise ValueError("A verified successful production deployment is required before automatic publication")
        return {"id": deployment_id, "production_branch": branch}

    def rollback(self, deployment_id: str) -> None:
        if not isinstance(deployment_id, str) or not DEPLOYMENT_ID.fullmatch(deployment_id):
            raise ValueError("Rollback requires the exact previously captured deployment identifier")
        result = self._request("POST", f"{self._project_path}/deployments/{deployment_id}/rollback")
        if result.get("id") != deployment_id:
            raise ValueError("Cloudflare did not confirm the requested previous deployment")
