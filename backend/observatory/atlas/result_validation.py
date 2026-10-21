"""Revision-scoped interpretation corrections without modifying source returns."""
from __future__ import annotations

from sqlalchemy import select

from .models import AtlasResultValidation, ElectionResult


def _invalidated_sources(database, revision: int) -> dict[str, set[str]]:
    decisions: dict[str, set[str]] = {}
    with database.session() as session:
        for validation in session.scalars(select(AtlasResultValidation).where(AtlasResultValidation.revision <= revision)):
            for identifier in validation.invalidated_contest_ids:
                decisions.setdefault(identifier, set()).add(validation.dataset_id)
    return decisions


def invalidated_result_contests(database, revision: int) -> set[str]:
    decisions = _invalidated_sources(database, revision)
    if not decisions:
        return set()
    # A bad parser interpretation in one producer cannot hide a compatible
    # independent producer that shares the same semantic contest identity.
    suppliers: dict[str, set[str]] = {}
    with database.session() as session:
        for contest_id, dataset_id in session.execute(select(ElectionResult.contest_id, ElectionResult.dataset_id).where(
                ElectionResult.contest_id.in_(decisions), ElectionResult.revision <= revision).distinct()):
            suppliers.setdefault(contest_id, set()).add(dataset_id)
    return {identifier for identifier, datasets in decisions.items() if not suppliers.get(identifier, set()) - datasets}


def apply_result_validations(database, rows: list[dict], revision: int) -> list[dict]:
    decisions = _invalidated_sources(database, revision)
    return [row for row in rows if row["dataset_id"] not in decisions.get(row["contest_id"], set())]


def result_validation_warnings(database, rows: list[dict], revision: int) -> list[str]:
    dataset_ids = {row["dataset_id"] for row in rows}
    if not dataset_ids:
        return []
    with database.session() as session:
        validations = list(session.scalars(select(AtlasResultValidation).where(
            AtlasResultValidation.dataset_id.in_(dataset_ids))))
    output = []
    for validation in validations:
        if validation.revision > revision and any(row["contest_id"] in validation.invalidated_contest_ids for row in rows):
            output.append(f"Present-day validation revision {validation.revision} corrects this pinned source interpretation: {validation.reason} Original archived values and the older pin remain inspectable; the affected grouped contest must not be treated as one real election.")
        elif validation.revision <= revision:
            output.append(f"Validated contest interpretation revision {validation.revision}: {validation.reason}")
    return output
