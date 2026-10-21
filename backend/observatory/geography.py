"""Canonical, evidence-preserving joins to the locally archived Census boundaries.

Name normalization only chooses a unique county *within its reported state and
county grain*. It never assigns a municipality or an Alaska election district to
a county. Original observation/feature identifiers remain unchanged for old URLs.
"""
from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote

from .settings import PROJECT_ROOT

BOUNDARY_VINTAGE = "2024"
BOUNDARY_ROOT = PROJECT_ROOT / "frontend" / "public" / "geography"
# Reviewed spelling variations, not fuzzy matches or geographic crosswalks.
COUNTY_ALIASES = {("IA", "OBRIEN"): "O'Brien", ("NC", "NEWHANOVER"): "New Hanover",
                  ("IA", "BUENAVISTA"): "Buena Vista", ("IA", "CERROGORDO"): "Cerro Gordo",
                  ("IA", "PALOALTO"): "Palo Alto", ("IA", "VANBUREN"): "Van Buren"}


def normalized_name(value: str) -> str:
    value = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Z0-9]", "", value.upper())


@lru_cache(maxsize=50)
def county_index(state: str, boundary_root: str | None = None) -> dict:
    path = Path(boundary_root or BOUNDARY_ROOT) / f"{state.upper()}.geojson"
    if not path.exists():
        return {"by_geoid": {}, "by_name": {}, "by_legacy": {}}
    data = json.loads(path.read_text())
    result = {"by_geoid": {}, "by_name": {}, "by_legacy": {}}
    for feature in data.get("features", []):
        p = feature.get("properties") or {}
        geoid = str(p.get("GEOID", ""))
        if not re.fullmatch(r"\d{5}", geoid) or p.get("STUSPS", p.get("postal")) != state.upper():
            continue
        record = {"canonical_id": f"county:{geoid}", "name": p.get("NAME", p.get("name")),
                  "geoid": geoid, "boundary_vintage": str(p.get("vintage", BOUNDARY_VINTAGE)),
                  "legacy_id": str(p.get("id", feature.get("id", "")))}
        result["by_geoid"][geoid] = record
        # Virginia independent cities can share a name and legacy generated ID
        # with a county. A collision is deliberately unresolved until a GEOID or
        # the complete Census label distinguishes the two.
        if record["legacy_id"] not in result["by_legacy"]:
            result["by_legacy"][record["legacy_id"]] = record
        elif result["by_legacy"][record["legacy_id"]] != record:
            result["by_legacy"][record["legacy_id"]] = None
        for name in {record["name"], p.get("NAMELSAD", "")}:
            if name:
                result["by_name"].setdefault(normalized_name(name), []).append(record)
    return result


def county_match(state: str, identifier: str = "", name: str = "", *, boundary_root: str | None = None) -> dict | None:
    index = county_index(state.upper(), boundary_root)
    raw = str(identifier)
    geoid = raw.removeprefix("county:")
    if geoid in index["by_geoid"]:
        return {**index["by_geoid"][geoid], "method": "census_geoid"}
    if re.fullmatch(r"\d{5}", geoid):
        return None  # An explicit foreign/unknown GEOID cannot be overridden by a familiar name.
    if index["by_legacy"].get(raw):
        return {**index["by_legacy"][raw], "method": "archived_boundary_identifier"}
    for candidate in (name, raw.split(":", 1)[-1] if ":" in raw else raw):
        if not candidate:
            continue
        alias = COUNTY_ALIASES.get((state.upper(), normalized_name(candidate)))
        matches = index["by_name"].get(normalized_name(alias or candidate), [])
        unique = {match["geoid"]: match for match in matches}
        if len(unique) == 1:
            return {**next(iter(unique.values())), "method": "reviewed_alias" if alias else "unique_state_county_name"}
    return None


def canonicalize_observation(row: dict, *, boundary_root: str | None = None) -> dict:
    state = str(row.get("state", "")).upper()
    grain = row.get("geography_type", row.get("type", "state"))
    original = str(row.get("geography_id", row.get("id", "")))
    metadata = row.get("metadata") or {}
    if grain == "state":
        canonical, join = f"state:{state}", {"status": "matched", "method": "state_postal_code", "boundary_vintage": BOUNDARY_VINTAGE}
    elif grain == "county":
        match = county_match(state, str(metadata.get("geoid") or metadata.get("GEOID") or original),
                             str(row.get("geography_name", row.get("name", ""))), boundary_root=boundary_root)
        canonical = match["canonical_id"] if match else None
        join = {"status": "matched" if match else "unmatched", "method": match["method"] if match else "no_unique_verified_county",
                "boundary_vintage": match["boundary_vintage"] if match else BOUNDARY_VINTAGE,
                "boundary_geoid": match["geoid"] if match else None}
    else:
        source = str(row.get("source_id") or metadata.get("source_id") or "unattributed")
        vintage = str(metadata.get("boundary_vintage") or metadata.get("reporting_geography_vintage") or row.get("cycle") or "undated")
        native_id = str(metadata.get("native_geography_id") or original)
        canonical = ":".join(("native", quote(source, safe=""), str(grain), quote(vintage, safe=""), quote(native_id, safe="")))
        join = {"status": "native_geography", "method": "source_native_identifier", "boundary_vintage": metadata.get("boundary_vintage"),
                "warning": "Native reporting geography has no asserted county-boundary correspondence."}
    return {**row, "canonical_id": canonical, "geography_join": join}


def normalize_selections(state: str, identifiers: list[str]) -> list[str]:
    """Return canonical selections where verified, preserving unresolved IDs."""
    result = []
    for identifier in identifiers:
        if identifier in {state, f"state:{state}"}:
            value = f"state:{state}"
        else:
            match = county_match(state, identifier)
            value = match["canonical_id"] if match else identifier
        if value not in result:
            result.append(value)
    return result


def enrich_geojson(data: dict, state: str | None = None) -> dict:
    features = []
    for feature in data.get("features", []):
        p = feature.get("properties") or {}
        code = p.get("STUSPS", p.get("postal", state))
        geoid = str(p.get("GEOID", ""))
        canonical = f"county:{geoid}" if len(geoid) == 5 else f"state:{code}"
        features.append({**feature, "properties": {**p, "canonical_id": canonical,
                         "boundary_vintage": str(p.get("vintage", BOUNDARY_VINTAGE))}})
    return {**data, "features": features}
