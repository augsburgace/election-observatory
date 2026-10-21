"""Verified dataset inventory and lightweight all-state discovery."""
from __future__ import annotations

import json
from collections import defaultdict

from sqlalchemy import func, select

from observatory.db import ResearchObject
from observatory.registry import all_states

from .models import BallotOption, Contest, DatasetState, ElectionResult, GeographyVersion, ensure_schema
from .result_validation import invalidated_result_contests


def source_definitions(database) -> list[dict]:
    return json.loads((database.settings.project_root / "config" / "atlas_sources.json").read_text())


def expanded_sources(database) -> list[dict]:
    rows = []
    for source in source_definitions(database):
        if source.get("per_state"):
            for state in all_states():
                file=source.get('per_state_files',{}).get(state['code'])
                if source.get('per_state_files') and not file:
                    continue
                rows.append({**source, "id": f"{source['id']}_{state['code']}", "family": source["id"],
                    "state": state["code"], "states": [state["code"]],
                    "title": f"{state['name']}: {source['title']}",
                    "file":file,
                    "url": source["url"].format(lower=state["code"].lower(), state=state["code"],file_id=file['id'] if file else '')})
        else:
            rows.append({**source, "states": [s["code"] for s in all_states()]})
    return rows


def dataset_catalog(database, state: str | None = None) -> dict:
    ensure_schema(database)
    with database.session() as session:
        statuses = {r.id: r for r in session.scalars(select(DatasetState))}
    output = []
    for source in expanded_sources(database):
        if state and state.upper() not in source["states"]:
            continue
        stored = statuses.get(source["id"])
        payload = stored.payload if stored else {}
        output.append({**source, "status": stored.status if stored else source.get('acquisition',"available"),
            "record_count": stored.record_count if stored else 0, "revision": stored.revision if stored else None,
            "loaded_states": payload.get("loaded_states", [stored.state] if stored and stored.state else []),
            "depth": payload.get("depth"), "checked_at": stored.checked_at if stored else None,
            "error": stored.error if stored else None, "verified_offices": payload.get("offices", []),
            "warnings": list(dict.fromkeys(source.get("warnings", []) + payload.get("warnings", [])))})
    return {"revision": database.latest_revision(), "datasets": output}


def state_catalog(database) -> dict:
    ensure_schema(database)
    revision=database.latest_revision()
    cached=getattr(database,'_atlas_state_catalog_cache',None)
    if cached and cached['revision']==revision:
        return cached
    invalidated = invalidated_result_contests(database, revision)
    with database.session() as session:
        grouped = session.execute(select(ElectionResult.state, ElectionResult.year, ElectionResult.office,
            ElectionResult.geography_level, func.count()).where(~ElectionResult.contest_id.in_(invalidated)).group_by(ElectionResult.state, ElectionResult.year,
            ElectionResult.office, ElectionResult.geography_level)).all()
    by_state = defaultdict(list)
    for state, year, office, level, count in grouped:
        by_state[state].append((year, office, level, count))
    states = []
    for row in all_states():
        data = by_state[row["code"]]
        states.append({**row, "years": sorted({r[0] for r in data}), "offices": sorted({r[1] for r in data}),
            "geography_levels": sorted({r[2] for r in data}), "result_count": sum(r[3] for r in data),
            "latest_results": max((r[0] for r in data), default=None),
            "coverage": "loaded" if data else "available_on_demand"})
    result={"revision":revision,"states":states}
    database._atlas_state_catalog_cache=result
    return result


def availability(database, state: str) -> dict:
    row = next((s for s in state_catalog(database)["states"] if s["code"] == state.upper()), None)
    if row is None:
        raise ValueError("Unknown state")
    return {**row, "datasets": dataset_catalog(database, state)["datasets"],
        "limitations": ["Each office and geography is available only within its verified source coverage.",
            "Historical final results do not represent what was publicly known during voting."]}


def search(database, text: str, state: str | None = None, limit: int = 30, revision: int | None = None,
           *, include_research: bool = True) -> dict:
    ensure_schema(database)
    text = text.strip()[:100]
    if not text:
        return {"query": text, "results": []}
    term = f"%{text}%"
    bound = database.latest_revision() if revision is None else revision
    invalidated = invalidated_result_contests(database, bound)
    found = [{"type": "state", "id": f"state:{s['code']}", "name": s["name"], "state": s["code"]}
        for s in all_states() if text.casefold() in s["name"].casefold() or text.upper() == s["code"]]
    with database.session() as session:
        for model, field, kind in [(GeographyVersion, GeographyVersion.name, "place"),
                                   (Contest, Contest.name, "contest"), (BallotOption, BallotOption.name, "candidate")]:
            statement = select(model).where(field.ilike(term))
            if model is Contest:
                statement = statement.where(~Contest.id.in_(invalidated), select(ElectionResult.id).where(
                    ElectionResult.contest_id == Contest.id, ElectionResult.revision <= bound).exists())
            elif model is BallotOption:
                statement = statement.where(~BallotOption.contest_id.in_(invalidated), select(ElectionResult.id).where(
                    ElectionResult.option_id == BallotOption.id, ElectionResult.revision <= bound).exists())
                if state:
                    statement = statement.join(Contest, BallotOption.contest_id == Contest.id).where(Contest.state == state.upper())
            elif model is GeographyVersion:
                statement = statement.where(select(ElectionResult.id).where(ElectionResult.geography_id == GeographyVersion.geography_id,
                    ElectionResult.revision <= bound, ~ElectionResult.contest_id.in_(invalidated)).exists())
            if state and hasattr(model, "state"):
                statement = statement.where(model.state == state.upper())
            for record in session.scalars(statement.limit(limit)):
                item = {"type": kind, "id": record.id, "name": record.name}
                for attr in ("state", "year", "office", "geography_id", "level", "party", "contest_id"):
                    if hasattr(record, attr):
                        item[attr] = getattr(record, attr)
                if model is BallotOption:
                    contest = session.get(Contest, record.contest_id)
                    if contest:
                        item.update({"state": contest.state, "year": contest.year, "office": contest.office})
                found.append(item)
        if include_research:
            for record in session.scalars(select(ResearchObject).where(ResearchObject.title.ilike(term)).limit(limit)):
                found.append({"type": "research", "id": record.id, "name": record.title, "kind": record.kind})
    # Different vintages may have the same place. Keep one discovery entry.
    unique = {(r["type"], r.get("geography_id", r["id"])): r for r in found}
    return {"query": text, "results": list(unique.values())[:max(1, min(limit, 100))]}
