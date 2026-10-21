"""Additive atlas schema. Existing evidence and pinned research remain untouched."""
from __future__ import annotations

from sqlalchemy import JSON, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from observatory.db import Base


class Election(Base):
    __tablename__ = "atlas_elections"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    state: Mapped[str] = mapped_column(String, index=True)
    year: Mapped[int] = mapped_column(Integer, index=True)
    date: Mapped[str] = mapped_column(String)
    stage: Mapped[str] = mapped_column(String, default="general")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)


class Contest(Base):
    __tablename__ = "atlas_contests"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    election_id: Mapped[str] = mapped_column(ForeignKey("atlas_elections.id"), index=True)
    state: Mapped[str] = mapped_column(String, index=True)
    year: Mapped[int] = mapped_column(Integer, index=True)
    office: Mapped[str] = mapped_column(String, index=True)
    name: Mapped[str] = mapped_column(String)
    district: Mapped[str] = mapped_column(String, default="STATEWIDE")
    magnitude: Mapped[int | None] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String, default="candidate")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)


class BallotOption(Base):
    __tablename__ = "atlas_options"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    contest_id: Mapped[str] = mapped_column(ForeignKey("atlas_contests.id"), index=True)
    name: Mapped[str] = mapped_column(String)
    party: Mapped[str | None] = mapped_column(String)
    kind: Mapped[str] = mapped_column(String, default="candidate")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)


class ElectionResult(Base):
    __tablename__ = "atlas_results"
    __table_args__ = (Index("ix_atlas_result_scope", "state", "year", "office", "geography_level", "revision"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    logical_key: Mapped[str] = mapped_column(String, index=True)
    dataset_id: Mapped[str] = mapped_column(String, index=True)
    source_id: Mapped[str] = mapped_column(String, index=True)
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("snapshots.id"))
    revision: Mapped[int] = mapped_column(ForeignKey("revisions.id"), index=True)
    state: Mapped[str] = mapped_column(String, index=True)
    year: Mapped[int] = mapped_column(Integer, index=True)
    office: Mapped[str] = mapped_column(String, index=True)
    contest_id: Mapped[str] = mapped_column(ForeignKey("atlas_contests.id"), index=True)
    option_id: Mapped[str] = mapped_column(ForeignKey("atlas_options.id"), index=True)
    geography_id: Mapped[str] = mapped_column(String, index=True)
    geography_level: Mapped[str] = mapped_column(String, index=True)
    geography_name: Mapped[str] = mapped_column(String)
    votes: Mapped[float | None] = mapped_column(Float)
    mode: Mapped[str] = mapped_column(String, default="TOTAL")
    round: Mapped[str] = mapped_column(String, default="reported")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)


class GeographyVersion(Base):
    __tablename__ = "atlas_geography_versions"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    geography_id: Mapped[str] = mapped_column(String, index=True)
    state: Mapped[str] = mapped_column(String, index=True)
    name: Mapped[str] = mapped_column(String)
    level: Mapped[str] = mapped_column(String)
    vintage: Mapped[str] = mapped_column(String)
    parent_id: Mapped[str | None] = mapped_column(String)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)


class GeographicCrosswalk(Base):
    __tablename__ = "atlas_geographic_crosswalks"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    source_id: Mapped[str] = mapped_column(String, index=True)
    source_geography_id: Mapped[str] = mapped_column(String)
    target_geography_id: Mapped[str] = mapped_column(String, index=True)
    status: Mapped[str] = mapped_column(String)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)


class ContextEstimate(Base):
    __tablename__ = "atlas_context_estimates"
    __table_args__ = (Index("ix_atlas_context_scope", "state", "geography_id", "metric", "revision"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    logical_key: Mapped[str] = mapped_column(String, index=True)
    revision: Mapped[int] = mapped_column(ForeignKey("revisions.id"), index=True)
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("snapshots.id"))
    dataset_id: Mapped[str] = mapped_column(String)
    state: Mapped[str] = mapped_column(String, index=True)
    geography_id: Mapped[str] = mapped_column(String, index=True)
    metric: Mapped[str] = mapped_column(String, index=True)
    estimate: Mapped[float | None] = mapped_column(Float)
    moe: Mapped[float | None] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String)
    period_start: Mapped[str] = mapped_column(String)
    period_end: Mapped[str] = mapped_column(String)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)


class DenominatorEvidence(Base):
    __tablename__ = "atlas_denominators"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    geography_id: Mapped[str] = mapped_column(String, index=True)
    metric: Mapped[str] = mapped_column(String)
    value: Mapped[float] = mapped_column(Float)
    date: Mapped[str] = mapped_column(String)
    definition: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)


class DatasetState(Base):
    __tablename__ = "atlas_dataset_states"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    dataset_id: Mapped[str] = mapped_column(String, index=True)
    state: Mapped[str | None] = mapped_column(String, index=True)
    status: Mapped[str] = mapped_column(String)
    revision: Mapped[int | None] = mapped_column(Integer)
    record_count: Mapped[int] = mapped_column(Integer, default=0)
    checked_at: Mapped[str | None] = mapped_column(String)
    error: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)


class AtlasResultValidation(Base):
    """Append-only structural corrections to parsed contest interpretation."""
    __tablename__ = "atlas_result_validations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dataset_id: Mapped[str] = mapped_column(String, index=True)
    revision: Mapped[int] = mapped_column(ForeignKey("revisions.id"), index=True)
    invalidated_contest_ids: Mapped[list] = mapped_column(JSON, default=list)
    reason: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)


ATLAS_TABLES = [m.__table__ for m in (Election, Contest, BallotOption, ElectionResult, GeographyVersion,
    GeographicCrosswalk, ContextEstimate, DenominatorEvidence, DatasetState, AtlasResultValidation)]


def ensure_schema(database) -> None:
    Base.metadata.create_all(database.engine, tables=ATLAS_TABLES, checkfirst=True)
