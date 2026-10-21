"""Bounded public-source fetches and content-addressed immutable archives."""
from __future__ import annotations

import hashlib
import os
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import httpx

from .domain import FetchedDocument, utc_now
from .settings import Settings

MAX_BYTES = 150 * 1024 * 1024


class Fetcher:
    def __init__(self, settings: Settings, *, offline: bool = False, document_cache: dict | None = None):
        self.settings = settings
        self.offline = offline
        self.documents: list[FetchedDocument] = []
        self.document_cache = document_cache
        self.settings.prepare()
        self.client = httpx.Client(timeout=httpx.Timeout(50, connect=15), follow_redirects=True,
                                   headers={"User-Agent": "BattlegroundSenateObservatory/0.1 (personal public-data research)", "Accept": "*/*"})

    def fetch(self, url: str) -> FetchedDocument:
        if urlparse(url).scheme not in {"https", "http"}:
            raise ValueError("Only public HTTP(S) source URLs are supported")
        existing = next((doc for doc in self.documents if doc.url == url), None)
        if existing:
            return existing
        if not self.offline and self.document_cache is not None and url in self.document_cache:
            doc = self.document_cache[url]
            self.documents.append(doc)
            return doc
        cache_key = hashlib.sha256(url.encode()).hexdigest()
        cache_path = self.settings.data_dir / "fetch-cache" / f"{cache_key}.json"
        if self.offline:
            if not cache_path.exists():
                raise ValueError(f"No archived response for {url}")
            doc = FetchedDocument.model_validate_json(cache_path.read_text())
            self.documents.append(doc)
            return doc
        cached = FetchedDocument.model_validate_json(cache_path.read_text()) if cache_path.exists() else None
        headers = {}
        if cached and Path(cached.path).is_file():
            if cached.etag:
                headers["If-None-Match"] = cached.etag
            elif cached.last_modified:
                headers["If-Modified-Since"] = cached.last_modified
        etag = last_modified = None
        stage_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile(dir=self.settings.data_dir / "staging", delete=False) as stage:
                stage_name = stage.name
                with self.client.stream("GET", url, headers=headers) as response:
                    if response.status_code == 304 and cached:
                        stage.close()
                        Path(stage_name).unlink(missing_ok=True)
                        doc = cached.model_copy(update={"retrieved_at": utc_now()})
                        cache_path.write_text(doc.model_dump_json())
                        self.documents.append(doc)
                        if self.document_cache is not None:
                            self.document_cache[url] = doc
                        return doc
                    response.raise_for_status()
                    content_type = response.headers.get("content-type", "application/octet-stream")
                    etag, last_modified = response.headers.get("etag"), response.headers.get("last-modified")
                    size = 0
                    for chunk in response.iter_bytes(65536):
                        size += len(chunk)
                        if size > MAX_BYTES:
                            raise ValueError("Source exceeds 150 MB fetch limit")
                        stage.write(chunk)
        except (httpx.HTTPStatusError, httpx.ConnectError) as exc:
            if stage_name and Path(stage_name).exists():
                Path(stage_name).unlink()
            status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else 0
            if status not in {0, 403, 406}:
                raise
            # A normal public-file request through curl can work where a server rejects the Python client.
            # No cookies, credentials, challenge solving, or access-control bypass are involved.
            descriptor, stage_name = tempfile.mkstemp(dir=self.settings.data_dir / "staging")
            os.close(descriptor)
            result = subprocess.run(["curl", "--fail", "--location", "--silent", "--show-error",
                "--max-time", "55", "--max-filesize", str(MAX_BYTES), "--output", stage_name,
                "--write-out", "%{content_type}", url], capture_output=True, text=True, timeout=60)
            if result.returncode:
                Path(stage_name).unlink(missing_ok=True)
                raise ValueError(f"Public source HTTP/TLS {status}; normal file retrieval also failed") from exc
            content_type = result.stdout.strip() or "application/octet-stream"
        except Exception:
            if stage_name:
                Path(stage_name).unlink(missing_ok=True)
            raise
        stage_path = Path(stage_name)
        with stage_path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        destination = self.settings.archive_dir / digest[:2] / digest
        destination.parent.mkdir(parents=True, exist_ok=True)
        byte_count = stage_path.stat().st_size
        if not destination.exists():
            os.replace(stage_path, destination)
        else:
            stage_path.unlink()
        text = None
        if byte_count <= 12 * 1024 * 1024 and any(kind in content_type.lower() for kind in ("text", "json", "csv", "xml")):
            text = destination.read_bytes().decode("utf-8-sig", errors="replace")
        doc = FetchedDocument(url=url, sha256=digest, path=str(destination), content_type=content_type,
                              retrieved_at=utc_now(), byte_count=byte_count, text=text, etag=etag, last_modified=last_modified)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(doc.model_dump_json())
        self.documents.append(doc)
        if self.document_cache is not None and byte_count <= 12 * 1024 * 1024 and sum(d.byte_count for d in self.document_cache.values()) + byte_count <= 64 * 1024 * 1024:
            # This dictionary belongs to one bounded collector run, not a global
            # freshness cache. Per-host collector locks serialize its accesses.
            self.document_cache[url] = doc
        return doc

    def close(self):
        self.client.close()
