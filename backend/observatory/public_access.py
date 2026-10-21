"""Read-only public boundary for the aggregate research application.

The collector and private notebook remain separate from anonymous web traffic.
Public mode is a presentation boundary, not a substitute for a sanitized seed:
original voter files and the personal research database must not be deployed.
"""
from __future__ import annotations

import asyncio
import json
import re
from collections import defaultdict, deque
from time import monotonic
from urllib.parse import parse_qs

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .settings import Settings

MAX_BODY_BYTES = 256 * 1024
MAX_JSON_BYTES = 64 * 1024 * 1024
PUBLIC_POSTS = frozenset({
    "/api/v1/scenarios", "/api/v1/scenarios/senate", "/api/v1/exports",
    "/api/v2/reports/preview", "/api/v2/reports/exports",
})
PRIVATE_PREFIXES = (
    "/api/v1/research", "/api/v1/documents", "/api/v1/jobs",
    "/api/v1/corrections", "/api/v1/refresh", "/api/v1/forecast/backtest",
)
PRIVATE_KEYS = frozenset({
    "path", "archive_path", "directory", "capture_path", "capture_file", "local_path",
    "raw_path", "staging_path", "traceback", "stack_trace", "exception", "stderr", "api_key", "access_token",
    "authorization", "cookie", "password", "secret", "token",
})
UNAVAILABLE = "Source unavailable; the last validated evidence remains available."
LOCAL_PATH = re.compile(r"(?:file://|(?<![A-Za-z0-9:/])(?:/Users/|/home/|/root/|/tmp/|/private/|[A-Za-z]:\\))[^\s\"'<>]*")


def public_capabilities(settings: Settings) -> dict:
    private = not settings.public_mode
    return {"deployment_mode": settings.deployment_mode, "public_read_only": not private,
            "research_write": private, "collection": private, "raw_documents": private,
            "private_notebook": private, "aggregate_exports": True,
            "scenario_calculation": True, "report_composition": True}


def public_payload(value, *, private_roots: tuple[str, ...] = (), correction: bool = False):
    """Keep aggregate provenance while excluding local storage and private annotations."""
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            normalized = str(key).lower()
            if normalized in PRIVATE_KEYS:
                continue
            if correction and normalized in {"reason", "author", "body", "note", "notes"}:
                continue
            if normalized in {"error", "last_error", "error_message"} and item:
                result[key] = UNAVAILABLE
            else:
                result[key] = public_payload(item, private_roots=private_roots,
                    correction=correction or normalized in {"correction", "corrections"})
        return result
    if isinstance(value, (list, tuple)):
        return [public_payload(item, private_roots=private_roots, correction=correction) for item in value]
    if isinstance(value, str):
        # HTTP source URLs and their hashes are public evidence, not local paths.
        if value.startswith(("https://", "http://")):
            return value
        for root in private_roots:
            if root and root != "/":
                value = value.replace(root, "[private storage]")
        return LOCAL_PATH.sub("[private storage]", value)
    return value


def _bounded_input(value, depth: int = 0) -> bool:
    if depth > 16:
        return False
    if isinstance(value, dict):
        if len(value) > 200:
            return False
        for key, item in value.items():
            if str(key).lower() == "include_notes" and item not in (False, None, 0, "false", "0", ""):
                return False
            if str(key).lower() in {"note", "notes"} and item:
                return False
            if not _bounded_input(item, depth + 1):
                return False
    elif isinstance(value, list):
        return len(value) <= 500 and all(_bounded_input(item, depth + 1) for item in value)
    return True


async def _answer(send: Send, status: int, detail: str, *, retry: bool = False):
    body = json.dumps({"detail": detail}).encode()
    headers = [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode()),
               (b"cache-control", b"no-store")]
    if retry:
        headers.append((b"retry-after", b"60"))
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})


class PublicAccessMiddleware:
    """Deny anonymous administration and scrub JSON before compression/rendering."""

    def __init__(self, app: ASGIApp, settings: Settings):
        self.app, self.settings = app, settings
        self.recent: dict[str, deque] = defaultdict(deque)
        self.reports = asyncio.Semaphore(2)
        self.private_roots = (str(settings.data_dir.resolve()), str(settings.project_root.resolve()))

    def _rate_allowed(self, key: str) -> bool:
        now = monotonic()
        if len(self.recent) > 4096:
            self.recent = defaultdict(deque, {k: v for k, v in self.recent.items() if v and v[-1] > now - 60})
            if len(self.recent) > 4096 and key not in self.recent:
                return False
        queue = self.recent[key]
        while queue and queue[0] <= now - 60:
            queue.popleft()
        if len(queue) >= 180:
            return False
        queue.append(now)
        return True

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if not self.settings.public_mode or scope["type"] != "http":
            return await self.app(scope, receive, send)
        path, method = scope["path"].rstrip("/"), scope["method"]
        if not path.startswith("/api/"):
            return await self.app(scope, receive, send)
        if any(path == prefix or path.startswith(prefix + "/") for prefix in PRIVATE_PREFIXES):
            return await _answer(send, 403, "This private research or administration feature is available only in the local application.")
        if method not in {"GET", "HEAD", "OPTIONS"} and (method != "POST" or path not in PUBLIC_POSTS):
            return await _answer(send, 403, "The public application does not accept changes to stored evidence.")
        params = parse_qs(scope.get("query_string", b"").decode("utf-8", errors="replace"))
        if any(v.lower() not in {"false", "0", ""} for v in params.get("include_notes", [])):
            return await _answer(send, 403, "Private notebook content cannot be included in public exports.")
        peer = str((scope.get("client") or ("anonymous", 0))[0])
        if not self._rate_allowed(peer):
            return await _answer(send, 429, "Too many requests. Please wait a minute and try again.", retry=True)

        if method == "POST":
            body = bytearray()
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                body.extend(message.get("body", b""))
                if len(body) > MAX_BODY_BYTES:
                    return await _answer(send, 413, "Public calculations accept at most 256 KB per request.")
                if not message.get("more_body", False):
                    break
            try:
                payload = json.loads(body or b"{}")
            except (ValueError, RecursionError):
                return await _answer(send, 422, "Supply a bounded JSON object for this calculation.")
            if not isinstance(payload, dict) or not _bounded_input(payload):
                return await _answer(send, 422, "Use a bounded aggregate calculation without private notes.")
            sent = False
            original_receive = receive

            async def replay():
                nonlocal sent
                if not sent:
                    sent = True
                    return {"type": "http.request", "body": bytes(body), "more_body": False}
                return await original_receive()

            receive = replay

        start: Message | None = None
        chunks: list[bytes] = []
        size = 0
        sanitize = False

        async def safe_send(message: Message):
            nonlocal start, sanitize, size
            if message["type"] == "http.response.start":
                headers = dict(message.get("headers", []))
                sanitize = b"json" in headers.get(b"content-type", b"")
                if sanitize:
                    start = message
                else:
                    await send(message)
            elif message["type"] == "http.response.body" and sanitize:
                size += len(message.get("body", b""))
                if size <= MAX_JSON_BYTES:
                    chunks.append(message.get("body", b""))
                if not message.get("more_body", False):
                    if size > MAX_JSON_BYTES:
                        return await _answer(send, 413, "This evidence selection is too large. Choose a smaller area or date range.")
                    try:
                        value = json.loads(b"".join(chunks))
                        if start["status"] >= 400:
                            value = {"detail": "This request could not be completed. Check the selected election, place and filters."}
                        else:
                            value = public_payload(value, private_roots=self.private_roots)
                        raw = json.dumps(value, ensure_ascii=False, allow_nan=False).encode()
                    except (TypeError, ValueError, RecursionError):
                        return await _answer(send, 503, "The selected evidence is temporarily unavailable.")
                    headers = [(k, v) for k, v in start.get("headers", []) if k.lower() not in {b"content-length", b"etag"}]
                    headers.append((b"content-length", str(len(raw)).encode()))
                    await send({**start, "headers": headers})
                    await send({"type": "http.response.body", "body": raw})
            else:
                await send(message)

        limited_report = path in {"/api/v2/reports/preview", "/api/v2/reports/exports", "/api/v1/exports",
                                  "/api/v2/results/exports", "/api/v2/context/exports"}
        if limited_report:
            if self.reports.locked():
                return await _answer(send, 429, "Two reports are already being prepared. Please try again shortly.", retry=True)
            async with self.reports:
                return await self.app(scope, receive, safe_send)
        return await self.app(scope, receive, safe_send)


def public_report_document(database, request):
    """Sanitize the common document before *any* HTML/PDF/ZIP renderer sees it."""
    from .report_composer import _digest, _document
    if request.include_notes or request.notes:
        raise ValueError("Private notes are available only in the local report builder")
    document = public_payload(_document(database, request), private_roots=(str(database.settings.data_dir),
                                                                         str(database.settings.project_root)))
    document["content_sha256"] = _digest({key: document[key] for key in
        ("title", "state", "revision", "query", "request", "sections", "sources", "boundary_files", "notes")})
    return document
