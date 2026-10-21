from __future__ import annotations

import fcntl
import hashlib
import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

from sqlalchemy import select

from .archive import Fetcher
from .db import (
    Database,
    Job,
    ObservationRecord,
    PollRecord,
    Revision,
    Snapshot,
    SourceState,
    observation_key,
    poll_key,
)
from .domain import ParsedBatch, utc_now
from .registry import source_covers_state, sources

logger = logging.getLogger(__name__)
_host_locks: dict[str, Lock] = {}
_host_locks_guard = Lock()


def semantic_payload(payload: dict) -> dict:
    """Retrieval metadata is evidence provenance, not a change to a published quantity."""
    return {**payload, "metadata": {k: v for k, v in payload.get("metadata", {}).items()
            if k not in {"retrieved_at", "fetched_at", "is_revision", "revision_of", "archive_listing_sha256"}}}


def _collect_one(database: Database, source: dict, offline: bool = False, document_cache: dict | None = None) -> dict:
    from urllib.parse import urlparse

    from .connectors import collect
    host = urlparse(source["url"]).hostname or source["id"]
    with _host_locks_guard:
        host_lock = _host_locks.setdefault(host, Lock())
    fetcher = Fetcher(database.settings, offline=offline, document_cache=document_cache)
    result = {"source_id": source["id"], "status": "failed", "observations": 0, "polls": 0}
    try:
        with host_lock:
            batch = collect(source, fetcher)
        if not isinstance(batch, ParsedBatch):
            batch = ParsedBatch.model_validate(batch)
        if not fetcher.documents:
            raise ValueError("Connector produced no archived source document")
        # A parsed batch must name a source, not merely contain a successful HTTP request.
        document_hash = hashlib.sha256("|".join(sorted(d.sha256 for d in fetcher.documents)).encode()).hexdigest()
        # Parser improvements must publish even when physical source bytes are unchanged.
        from pathlib import Path
        parser_signature = hashlib.sha256(b"".join(path.read_bytes() for path in sorted((Path(__file__).parent / "connectors").glob("*.py")))).hexdigest()
        processed_signature = hashlib.sha256(json.dumps({"documents": document_hash, "parser": parser_signature, "source": source}, sort_keys=True, default=str).encode()).hexdigest()
        with database.lock, database.session() as session:
            state = session.get(SourceState, source["id"])
            if not state:
                state = SourceState(id=source["id"])
                session.add(state)
            unchanged = state.document_hash == processed_signature
            state.last_checked = utc_now()
            state.error = None
            state.warnings = batch.warnings
            state.data_as_of = batch.data_as_of
            if unchanged:
                state.status = "unchanged"
                session.commit()
                return {**result, "status": "unchanged"}
            revision = Revision(reason="Validated public-source collection", source_id=source["id"])
            session.add(revision)
            session.flush()
            snapshots = {}
            for document in fetcher.documents:
                snapshot = Snapshot(source_id=source["id"], url=document.url, sha256=document.sha256,
                    path=document.path, content_type=document.content_type, retrieved_at=document.retrieved_at,
                    byte_count=document.byte_count, revision=revision.id)
                session.add(snapshot)
                session.flush()
                snapshots[document.url] = snapshot.id
            default_snapshot = snapshots[fetcher.documents[-1].url]
            for observation in batch.observations:
                payload = observation.model_dump()
                source_url = payload["metadata"].get("source_url") or batch.metadata.get("primary_document_url")
                snapshot_id = snapshots.get(source_url, default_snapshot)
                key = observation_key(payload, source["id"])
                previous = session.scalar(select(ObservationRecord).where(ObservationRecord.logical_key == key).order_by(ObservationRecord.revision.desc()).limit(1))
                original_comparison = semantic_payload(previous.payload) if previous else None
                if previous and original_comparison == semantic_payload(payload):
                    continue
                if previous:
                    payload["metadata"] = {**payload["metadata"], "is_revision": True, "revision_of": previous.id}
                session.add(ObservationRecord(logical_key=key, source_id=source["id"], snapshot_id=snapshot_id,
                    revision=revision.id, observed_at=utc_now(), state=payload["state"], cycle=payload["cycle"],
                    date=payload["date"], metric=payload["metric"], value=payload["value"], payload=payload))
                result["observations"] += 1
            for poll in batch.polls:
                payload = poll.model_dump()
                snapshot_id = snapshots.get(poll.document_url or poll.source_url, default_snapshot)
                candidates = session.scalars(select(PollRecord).where(PollRecord.source_id == source["id"], PollRecord.study_id == poll.study_id, PollRecord.state == poll.state, PollRecord.cycle == poll.cycle).order_by(PollRecord.revision.desc()))
                previous = next((r for r in candidates if poll_key(r.payload) == poll_key(payload)), None)
                if previous and payload["metadata"].get("publication_date_verified") is False and payload["metadata"].get("source_sha256") and payload["metadata"].get("source_sha256") == previous.payload.get("metadata", {}).get("source_sha256"):
                    # An unchanged release with unknown publication date was known
                    # by its first archived retrieval, not every subsequent check.
                    payload["published_at"] = previous.payload["published_at"]
                    if previous.payload.get("metadata", {}).get("first_archived_at"):
                        payload["metadata"]["first_archived_at"] = previous.payload["metadata"]["first_archived_at"]
                old_payload = semantic_payload(previous.payload) if previous else None
                if previous and old_payload == semantic_payload(payload):
                    continue
                if previous:
                    payload["metadata"] = {**payload["metadata"], "is_revision": True, "revision_of": previous.id}
                session.add(PollRecord(source_id=source["id"], snapshot_id=snapshot_id, revision=revision.id,
                    observed_at=utc_now(), study_id=poll.study_id, state=poll.state, cycle=poll.cycle, payload=payload))
                result["polls"] += 1
            state.document_hash = processed_signature
            state.last_changed = utc_now()
            reference_ready = bool(batch.metadata.get("reference_data"))
            state.status = "ready" if batch.observations or batch.polls or reference_ready else "unavailable"
            if batch.warnings and (batch.observations or batch.polls):
                state.status = "partial"
            result["status"] = state.status
            state.warnings = batch.warnings or ([] if batch.observations or batch.polls or reference_ready else ["Source archived; no compatible aggregate records located."])
            session.commit()
            result["revision"] = revision.id
        return result
    except Exception as exc:
        logger.warning("Source %s: %s", source["id"], exc)
        with database.lock, database.session() as session:
            state = session.get(SourceState, source["id"])
            if not state:
                state = SourceState(id=source["id"])
                session.add(state)
            state.status = "failed"
            state.last_checked = utc_now()
            state.error = str(exc)[:1000]
            session.commit()
        return {**result, "error": str(exc)[:1000]}
    finally:
        fetcher.close()


def collect_sources(database: Database, *, source_ids: list[str] | None = None, state: str | None = None,
                    include_historical: bool = False, job_id: int | None = None, offline: bool = False) -> dict:
    lock_path = database.settings.data_dir / "collector.lock"
    with lock_path.open("w") as lock_file:
        try:
            fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("Another source collection is already running") from exc
        inventory = sources()
        with database.session() as session:
            activated = {s.id for s in session.scalars(select(SourceState)) if s.last_changed}
        unknown = set(source_ids or []) - {source["id"] for source in inventory}
        if unknown:
            raise ValueError("Unknown source IDs: " + ", ".join(sorted(unknown)))
        state = state.upper() if state else None
        selected = [s for s in inventory if (s.get("enabled", True) or
                    (s.get("on_demand") and (s["id"] in (source_ids or []) or s["id"] in activated)))
                    and (not source_ids or s["id"] in source_ids)
                    and (not state or source_covers_state(s, state))
                    and (include_historical or source_ids or not s.get("historical", int(s.get("cycle", 2026)) < 2026))]
        outcomes = []
        document_cache = {}
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {pool.submit(_collect_one, database, source, offline, document_cache): source for source in selected}
            for future in as_completed(futures):
                outcome = future.result()
                outcomes.append(outcome)
                if job_id:
                    with database.lock, database.session() as session:
                        job = session.get(Job, job_id)
                        job.progress = {**job.progress, "completed": len(outcomes), "total": len(selected), "last": outcome}
                        session.commit()
        return {"sources": outcomes, "checked": len(outcomes), "successful": sum(s["status"] in {"ready", "partial", "unchanged"} for s in outcomes),
                "observations_added": sum(s["observations"] for s in outcomes), "polls_added": sum(s["polls"] for s in outcomes),
                "revision": database.latest_revision()}
