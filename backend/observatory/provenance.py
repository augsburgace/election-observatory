"""Resolve supporting documentary evidence without guessing snapshot identity."""
from __future__ import annotations

from sqlalchemy import select, tuple_

from .db import Snapshot


def snapshot_references(database, evidence, revision):
    """Collect exact references, including proof documents with URL/hash refs.

    Some historical dates are established by a separate official release. Its
    bytes must appear beside the numeric workbook in an export's source list.
    """
    stack, refs, seen = [evidence], [], set()
    while stack:
        value = stack.pop()
        if isinstance(value, list):
            stack.extend(value)
        elif isinstance(value, dict):
            stack.extend(v for v in value.values() if isinstance(v, (dict, list)))
            snapshot_id = value.get("snapshot_id")
            url = value.get("source_url") or value.get("url")
            digest = value.get("sha256") or value.get("source_sha256")
            if not isinstance(snapshot_id, int) and not (value.get("source_id") and url and digest):
                continue
            key = (snapshot_id, value.get("source_id"), url, digest)
            if key not in seen:
                seen.add(key)
                refs.append(dict(value))
    unresolved = {(r["source_id"], r.get("source_url") or r.get("url"), r.get("sha256") or r.get("source_sha256"))
        for r in refs if not isinstance(r.get("snapshot_id"), int)}
    with database.session() as session:
        rows = session.scalars(select(Snapshot).where(Snapshot.revision <= revision,
            tuple_(Snapshot.source_id, Snapshot.url, Snapshot.sha256).in_(unresolved)).order_by(Snapshot.revision.desc())) if unresolved else []
        matches = {}
        for row in rows:
            matches.setdefault((row.source_id, row.url, row.sha256), row.id)
    for ref in refs:
        if not isinstance(ref.get("snapshot_id"), int):
            key = (ref["source_id"], ref.get("source_url") or ref.get("url"), ref.get("sha256") or ref.get("source_sha256"))
            if key in matches:
                ref["snapshot_id"] = matches[key]
    return refs
