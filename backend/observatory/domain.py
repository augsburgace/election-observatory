"""Connector contracts. Source categories and chronological meaning remain explicit."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Observation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    state: str
    cycle: int
    election_date: str
    date: str
    metric: str
    value: float = Field(ge=0, allow_inf_nan=False)
    geography_id: str
    geography_name: str
    geography_type: Literal["state", "county", "district", "municipality", "precinct"] = "state"
    mode: str = "all"
    category_dimension: str | None = None
    category: str | None = None
    unit: str = "ballots"
    time_basis: Literal["reported", "reconstructed", "final"] = "reported"
    published_at: str | None = None
    denominator: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Poll(BaseModel):
    model_config = ConfigDict(extra="forbid")
    study_id: str
    state: str
    cycle: int = 2026
    producer: str
    sponsor: str = "Not disclosed"
    publisher: str
    field_start: str
    field_end: str
    published_at: str
    population: str
    sample_size: int | None = None
    methodology: str = "Not disclosed"
    question_type: str = "vote_choice"
    ballot_type: str = "full_ballot"
    question: str
    estimates: list[dict[str, Any]]
    margin_of_error: float | None = None
    partisan_sponsor: bool = False
    source_url: str
    document_url: str | None = None
    crosstabs: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ParsedBatch(BaseModel):
    observations: list[Observation] = Field(default_factory=list)
    polls: list[Poll] = Field(default_factory=list)
    data_as_of: str | None = None
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class FetchedDocument(BaseModel):
    url: str
    sha256: str
    path: str
    content_type: str
    retrieved_at: str
    status_code: int = 200
    byte_count: int
    text: str | None = None
    etag: str | None = None
    last_modified: str | None = None


class ResearchQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    state: str = "NC"
    cycle: int = Field(default=2026, ge=1976, le=2100)
    baseline: int = Field(default=2022, ge=1976, le=2100)
    as_of: str | None = None
    time_basis: Literal["reported", "reconstructed", "final"] = "reported"
    revision: int | None = Field(default=None, ge=0)
    metric: str = "ballots_cast"
    mode: str = "all"
    geography_ids: list[str] = Field(default_factory=list)
    date_window: tuple[str, str] | None = None
    category_dimension: str | None = None
    category: str | None = None
    alignment: Literal["days_to_election", "days_since_open", "days_since_opening", "voting_opportunities", "calendar"] = "days_to_election"

    @field_validator("state")
    @classmethod
    def known_state(cls, value: str) -> str:
        from .registry import all_states
        value = value.upper()
        if value not in {row["code"] for row in all_states()}:
            raise ValueError("Unknown state code")
        return value

    @field_validator("as_of")
    @classmethod
    def iso_cutoff(cls, value: str | None) -> str | None:
        if value:
            datetime.fromisoformat(value)
        return value or None

    @field_validator("date_window")
    @classmethod
    def ordered_window(cls, value: tuple[str, str] | None) -> tuple[str, str] | None:
        if value is not None:
            from datetime import date
            start, end = (date.fromisoformat(part) for part in value)
            if start > end:
                raise ValueError("Date window must run from an earlier to a later date")
        return value
