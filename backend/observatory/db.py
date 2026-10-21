"""Revisioned aggregate evidence store with immutable original values."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from threading import RLock
from typing import Any

from sqlalchemy import JSON, Float, ForeignKey, Integer, String, Text, create_engine, event, func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from .analytics.common import available_at, day, instant, is_generic_poll_response
from .domain import utc_now
from .settings import Settings


class Base(DeclarativeBase):
    pass


class Revision(Base):
    __tablename__ = "revisions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[str] = mapped_column(String, default=utc_now)
    reason: Mapped[str] = mapped_column(String)
    source_id: Mapped[str | None] = mapped_column(String)


class SourceState(Base):
    __tablename__ = "source_states"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    status: Mapped[str] = mapped_column(String, default="not_collected")
    last_checked: Mapped[str | None] = mapped_column(String)
    last_changed: Mapped[str | None] = mapped_column(String)
    data_as_of: Mapped[str | None] = mapped_column(String)
    error: Mapped[str | None] = mapped_column(Text)
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    document_hash: Mapped[str | None] = mapped_column(String)


class Snapshot(Base):
    __tablename__ = "snapshots"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[str] = mapped_column(String, index=True)
    url: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String, index=True)
    path: Mapped[str] = mapped_column(Text)
    content_type: Mapped[str] = mapped_column(String)
    retrieved_at: Mapped[str] = mapped_column(String)
    byte_count: Mapped[int] = mapped_column(Integer)
    revision: Mapped[int] = mapped_column(ForeignKey("revisions.id"), index=True)


class ObservationRecord(Base):
    __tablename__ = "observations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    logical_key: Mapped[str] = mapped_column(String, index=True)
    source_id: Mapped[str] = mapped_column(String, index=True)
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("snapshots.id"))
    revision: Mapped[int] = mapped_column(ForeignKey("revisions.id"), index=True)
    observed_at: Mapped[str] = mapped_column(String)
    state: Mapped[str] = mapped_column(String, index=True)
    cycle: Mapped[int] = mapped_column(Integer, index=True)
    date: Mapped[str] = mapped_column(String, index=True)
    metric: Mapped[str] = mapped_column(String, index=True)
    value: Mapped[float] = mapped_column(Float)
    payload: Mapped[dict] = mapped_column(JSON)


class PollRecord(Base):
    __tablename__ = "polls"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[str] = mapped_column(String, index=True)
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("snapshots.id"))
    revision: Mapped[int] = mapped_column(ForeignKey("revisions.id"), index=True)
    observed_at: Mapped[str] = mapped_column(String)
    study_id: Mapped[str] = mapped_column(String, index=True)
    state: Mapped[str] = mapped_column(String, index=True)
    cycle: Mapped[int] = mapped_column(Integer, index=True)
    payload: Mapped[dict] = mapped_column(JSON)


class ResearchObject(Base):
    __tablename__ = "research"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String)
    title: Mapped[str] = mapped_column(String)
    body: Mapped[str] = mapped_column(Text, default="")
    view: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[str] = mapped_column(String, default=utc_now)
    updated_at: Mapped[str] = mapped_column(String, default=utc_now)


class Correction(Base):
    __tablename__ = "corrections"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    observation_id: Mapped[int] = mapped_column(ForeignKey("observations.id"), index=True)
    revision: Mapped[int] = mapped_column(ForeignKey("revisions.id"))
    original: Mapped[float] = mapped_column(Float)
    replacement: Mapped[float] = mapped_column(Float)
    reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String, default=utc_now)


class QualityValidation(Base):
    """Append-only quality decisions; source payloads and old revisions survive."""
    __tablename__ = "quality_validations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String, unique=True)
    revision: Mapped[int] = mapped_column(ForeignKey("revisions.id"), index=True)
    state: Mapped[str] = mapped_column(String, index=True)
    source_id: Mapped[str | None] = mapped_column(String, nullable=True)
    metric: Mapped[str] = mapped_column(String)
    time_basis: Mapped[str] = mapped_column(String)
    action: Mapped[str] = mapped_column(String, default="quarantine")
    reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String, default=utc_now)


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="queued")
    created_at: Mapped[str] = mapped_column(String, default=utc_now)
    started_at: Mapped[str | None] = mapped_column(String)
    finished_at: Mapped[str | None] = mapped_column(String)
    progress: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)


def record_dict(record: Any) -> dict:
    return {column.name: getattr(record, column.name) for column in record.__table__.columns}


def observation_key(payload: dict, source_id: str) -> str:
    keys = ("state", "cycle", "date", "metric", "geography_id", "geography_type", "mode", "category_dimension", "category", "time_basis")
    value = {key: payload.get(key) for key in keys}
    value["source_id"] = source_id
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def poll_key(payload: dict) -> tuple:
    """Study questions retain their actual candidate configuration.

    Some original releases disclose a table but omit verbatim question wording.
    A connector's descriptive label is then not part of survey identity.
    """
    candidates = []
    for estimate in payload.get("estimates", []):
        name = str(estimate.get("candidate") or estimate.get("name") or estimate.get("label") or "").strip()
        if not name or is_generic_poll_response(name):
            continue
        candidates.append((" ".join(name.casefold().split()), str(estimate.get("party") or "").upper().strip()))
    metadata = payload.get("metadata") or {}
    question = None if metadata.get("question_wording_exact") is False else payload.get("question")
    return (payload.get("state"), payload.get("cycle"), payload.get("study_id"),
            str(payload.get("producer", "")).casefold().strip(), payload.get("population"),
            payload.get("question_type"), payload.get("ballot_type"), question, tuple(sorted(candidates)))


class Database:
    def __init__(self, settings: Settings):
        self.settings = settings
        settings.prepare()
        self.lock = RLock()
        self.engine = create_engine(f"sqlite:///{settings.database_path}", connect_args={"check_same_thread": False, "timeout": 30})
        @event.listens_for(self.engine, "connect")
        def configure(connection, _):
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA busy_timeout=30000")
        self.session = sessionmaker(self.engine, expire_on_commit=False)
        Base.metadata.create_all(self.engine)
        # Additive indexes also cover existing local databases. JSON scope fields
        # keep the source payload immutable while avoiding full-state JSON reads.
        with self.engine.begin() as connection:
            connection.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_observation_research_scope ON observations "
                "(state,cycle,metric,json_extract(payload,'$.time_basis'),json_extract(payload,'$.mode'),revision,date)")
            connection.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_observation_national_scope ON observations "
                "(cycle,metric,json_extract(payload,'$.time_basis'),json_extract(payload,'$.mode'),"
                "json_extract(payload,'$.geography_type'),revision)")

    def latest_revision(self) -> int:
        with self.session() as session:
            return session.scalar(select(Revision.id).order_by(Revision.id.desc()).limit(1)) or 0

    def observations(self, *, revision: int | None = None, state: str | None = None, cycle: int | None = None,
                     cutoff: str | None = None, all_versions: bool = False, metric: str | None = None,
                     mode: str | None = None, time_basis: str | None = None, uncategorized: bool = False,
                     geography_type: str | None = None, states: list[str] | None = None) -> list[dict]:
        bound_revision = revision if revision is not None else self.latest_revision()
        statement = select(ObservationRecord.id, ObservationRecord.logical_key, ObservationRecord.source_id,
            ObservationRecord.snapshot_id, ObservationRecord.revision, ObservationRecord.observed_at,
            ObservationRecord.payload).where(ObservationRecord.revision <= bound_revision)
        if state:
            statement = statement.where(ObservationRecord.state == state)
        if cycle:
            statement = statement.where(ObservationRecord.cycle == cycle)
        if states is not None:
            statement = statement.where(ObservationRecord.state.in_(states))
        if metric:
            statement = statement.where(ObservationRecord.metric == metric)
        if mode:
            statement = statement.where(ObservationRecord.payload["mode"].as_string() == mode)
        if time_basis:
            statement = statement.where(ObservationRecord.payload["time_basis"].as_string() == time_basis)
        if uncategorized:
            statement = statement.where(ObservationRecord.payload["category_dimension"].as_string().is_(None))
        if geography_type:
            statement = statement.where(ObservationRecord.payload["geography_type"].as_string() == geography_type)
        deadline = instant(cutoff, end_of_day=True) if cutoff else None
        if deadline:
            statement = statement.where(ObservationRecord.date <= day(deadline).isoformat())
        statement = statement.order_by(ObservationRecord.revision, ObservationRecord.id)
        with self.session() as session:
            latest = {}
            versions = []
            for record in session.execute(statement):
                payload = record.payload
                # Publication evidence is required for old as-reported views. A report date by itself is insufficient.
                availability = available_at({**payload, "observed_at": record.observed_at})
                if deadline and payload["time_basis"] != "reconstructed" and availability > deadline:
                    continue
                row = {**payload, "id": record.id, "source_id": record.source_id,
                    "snapshot_id": record.snapshot_id, "observed_at": record.observed_at, "revision": record.revision}
                latest[record.logical_key] = row
                versions.append(row)
            rows = versions if all_versions else list(latest.values())
            ids = {row["id"]: row for row in rows}
            corrections = session.scalars(select(Correction).where(Correction.revision <= bound_revision).order_by(Correction.id))
            for correction in corrections:
                if correction.observation_id in ids and (not deadline or instant(correction.created_at) <= deadline):
                    row = ids[correction.observation_id]
                    row["original_value"] = correction.original
                    row["value"] = correction.replacement
                    row["correction"] = record_dict(correction)
            decisions = list(session.scalars(select(QualityValidation).order_by(QualityValidation.id)))
            for row in rows:
                for decision in decisions:
                    if row.get("state") == decision.state and row.get("metric") == decision.metric and row.get("time_basis") == decision.time_basis and (not decision.source_id or row.get("source_id") == decision.source_id):
                        active = decision.revision <= bound_revision and (not deadline or instant(decision.created_at) <= deadline)
                        row["validation"] = {"status": "quarantined" if active and decision.action == "quarantine" else "historical_warning",
                            "reason": decision.reason, "validation_id": decision.id, "effective_revision": decision.revision,
                            "validated_at": decision.created_at, "original_retained": True}
            from .geography import canonicalize_observation
            return [canonicalize_observation(row) for row in rows]

    def validation_for(self, observation: dict, *, revision: int | None = None, cutoff: str | None = None) -> dict | None:
        """Quality annotation for an evidence inspector, independent of payload."""
        bound_revision = self.latest_revision() if revision is None else revision
        deadline = instant(cutoff, end_of_day=True) if cutoff else None
        with self.session() as session:
            decisions = session.scalars(select(QualityValidation).where(
                QualityValidation.state == observation.get("state"),
                QualityValidation.metric == observation.get("metric"),
                QualityValidation.time_basis == observation.get("time_basis")).order_by(QualityValidation.id.desc()))
            decision = next((d for d in decisions if not d.source_id or d.source_id == observation.get("source_id")), None)
            if decision is None:
                return None
            active = decision.revision <= bound_revision and (not deadline or instant(decision.created_at) <= deadline)
            return {"status": "quarantined" if active and decision.action == "quarantine" else "historical_warning",
                    "reason": decision.reason, "validation_id": decision.id, "effective_revision": decision.revision,
                    "validated_at": decision.created_at, "original_retained": True}

    def apply_quality_validations(self) -> dict:
        """Install reviewed policy once, after the caller's pre-migration backup.

        A policy applies to retained and future source records, so reparsing cannot
        silently resurrect a disallowed trajectory. Pinned older revisions retain
        original values and receive a separately identified present-day warning.
        """
        key = "maine-standing-request-chronology-v1"
        reason = ("Maine request-date trajectory is withheld: standing absentee requests and anomalous dates "
                  "do not establish current-election voting events. Original source records remain archived.")
        with self.lock, self.session() as session:
            existing = session.scalar(select(QualityValidation).where(QualityValidation.key == key))
            if existing:
                return record_dict(existing)
            revision = Revision(reason="Quality validation: quarantine Maine request-date reconstruction", source_id="me-absentee-records")
            session.add(revision)
            session.flush()
            finding = QualityValidation(key=key, revision=revision.id, state="ME", metric="ballot_records_requested",
                                        time_basis="reconstructed", reason=reason)
            session.add(finding)
            session.commit()
            return record_dict(finding)

    def observation_catalog(self, *, revision: int, state: str, cutoff: str) -> list[dict]:
        """Availability dimensions without decoding thousands of full source payloads.

        Earliest first-observation time suffices for an availability catalogue;
        actual numerical reads still retain every eligible version separately.
        """
        model = ObservationRecord
        expressions = [model.source_id.label("source_id"), model.cycle.label("cycle"), model.metric.label("metric"), model.date.label("date"),
            model.payload["mode"].as_string().label("mode"),
            model.payload["time_basis"].as_string().label("time_basis"),
            model.payload["category_dimension"].as_string().label("category_dimension"),
            model.payload["category"].as_string().label("category"),
            model.payload["published_at"].as_string().label("published_at"),
            model.payload["metadata"]["is_revision"].as_boolean().label("is_revision"),
            model.payload["metadata"]["revision_of"].as_string().label("revision_of"),
            model.payload["metadata"]["revision_published_at"].as_string().label("revision_published_at")]
        deadline = instant(cutoff, end_of_day=True)
        catalog_cache = self.__dict__.setdefault("_catalog_entry_cache", {})
        cache_guard = self.__dict__.setdefault("_catalog_entry_cache_lock", RLock())
        cache_key = (revision, state)
        with cache_guard:
            entries = catalog_cache.get(cache_key)
        if entries is None:
            statement = select(*expressions, func.min(model.observed_at).label("observed_at")).where(
                model.revision <= revision, model.state == state).group_by(*expressions)
            with self.session() as session:
                entries = [dict(record) for record in session.execute(statement).mappings()]
            if len(entries) <= 25000:
                with cache_guard:
                    catalog_cache[cache_key] = entries
                    while len(catalog_cache) > 16 or sum(len(item) for item in catalog_cache.values()) > 50000:
                        del catalog_cache[next(iter(catalog_cache))]
        with self.session() as session:
            quarantines = list(session.scalars(select(QualityValidation).where(QualityValidation.state == state,
                QualityValidation.revision <= revision, QualityValidation.action == "quarantine")))
        found = {}
        cutoff_date = day(deadline).isoformat()
        for row in entries:
            if any(item.metric == row["metric"] and item.time_basis == row["time_basis"] and (not item.source_id or item.source_id == row["source_id"])
                   and instant(item.created_at) <= deadline for item in quarantines):
                continue
            if row["date"] > cutoff_date:
                continue
            known = available_at({**row, "metadata": {"is_revision": row["is_revision"], "revision_of": row["revision_of"],
                                                      "revision_published_at": row["revision_published_at"]}})
            if row["time_basis"] != "reconstructed" and (known is None or known > deadline):
                continue
            entry = {key: row[key] for key in ("source_id", "cycle", "metric", "mode", "time_basis", "category_dimension", "category")}
            found[tuple(entry.values())] = entry
        return list(found.values())

    def polls(self, *, revision: int | None = None, state: str | None = None, cutoff: str | None = None) -> list[dict]:
        statement = select(PollRecord).where(PollRecord.revision <= (revision if revision is not None else self.latest_revision())).order_by(PollRecord.revision, PollRecord.id)
        if state:
            statement = statement.where(PollRecord.state == state)
        latest = {}
        with self.session() as session:
            for record in session.scalars(statement):
                if cutoff and available_at({**record.payload, "observed_at": record.observed_at}) > instant(cutoff, end_of_day=True):
                    continue
                key = poll_key(record.payload)
                latest[key] = {**record.payload, "id": record.id, "source_id": record.source_id,
                    "snapshot_id": record.snapshot_id, "observed_at": record.observed_at, "revision": record.revision}
        return list(latest.values())

    def backup(self, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.settings.database_path) as original, sqlite3.connect(destination) as target:
            original.backup(target)
        return destination
