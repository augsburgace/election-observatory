"""Archive first, then atomically publish normalized historical election evidence."""
from __future__ import annotations

import csv
import hashlib
import io
import math
import re
import zipfile
from datetime import date, timedelta

from sqlalchemy import insert, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from observatory.archive import Fetcher
from observatory.db import Revision, Snapshot
from observatory.domain import utc_now
from observatory.registry import all_states

from .catalog import expanded_sources
from .models import (
    AtlasResultValidation,
    BallotOption,
    Contest,
    ContextEstimate,
    DatasetState,
    Election,
    ElectionResult,
    GeographyVersion,
    ensure_schema,
)

STATES = {s["code"]: s for s in all_states()}
FIPS_STATES = {s["fips"]: s["code"] for s in all_states()}
STATE_NAMES = {s["name"].upper(): s["code"] for s in all_states()}
NON_OPTIONS = {"UNDERVOTES", "OVERVOTES", "TOTAL", "TOTAL VOTES", "BALLOTS CAST", "REGISTERED VOTERS",
               "UNDERVOTE", "OVERVOTE", "TOTAL BALLOTS CAST", "BALLOTS"}
PARSER_VERSION = "atlas-3"


def stable_id(*parts) -> str:
    return hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()[:24]


def number(value) -> float | None:
    try:
        result = float(str(value).replace(",", "").strip())
        return result if math.isfinite(result) and result >= 0 else None
    except (TypeError, ValueError):
        return None


def normal_office(value: str) -> str:
    value = re.sub(r"\s+", " ", str(value).strip().upper())
    return {"US PRESIDENT": "PRESIDENT", "U.S. PRESIDENT": "PRESIDENT", "PRESIDENT OF THE UNITED STATES": "PRESIDENT",
        "U.S. SENATE": "US SENATE", "SENATE": "US SENATE", "U.S. HOUSE": "US HOUSE", "HOUSE": "US HOUSE"}.get(value, value)


def normal_party(value: str | None) -> str | None:
    value = str(value or "").upper().strip()
    return {"DEMOCRAT": "DEM", "DEMOCRATIC": "DEM", "REPUBLICAN": "REP", "LIBERTARIAN": "LIB",
        "GREEN": "GRN", "INDEPENDENT": "IND", "NA": None, "NAN": None, "": None}.get(value, value)


def election_day(year: int) -> str:
    first = date(year, 11, 1)
    return (first + timedelta(days=(0 - first.weekday()) % 7 + 1)).isoformat()


def _csv_rows(path: str, *, zipped: bool = False):
    if zipped:
        with zipfile.ZipFile(path) as archive:
            for filename in archive.namelist():
                if filename.lower().endswith(('.csv', '.tab')) and not filename.startswith('__MACOSX'):
                    with archive.open(filename) as stream:
                        yield from csv.DictReader(io.TextIOWrapper(stream, encoding="utf-8-sig"),
                            delimiter='\t' if filename.endswith('.tab') else ',')
    else:
        with open(path, "rb") as probe:
            try:
                probe.read().decode("utf-8-sig")
                encoding = "utf-8-sig"
            except UnicodeDecodeError:
                encoding = "latin-1"
        with open(path, encoding=encoding) as stream:
            sample = stream.read(2048)
            stream.seek(0)
            yield from csv.DictReader(stream, delimiter='\t' if sample.count('\t') > sample.count(',') else ',')


def parse_results(source: dict, path: str, *, deep: bool = True) -> tuple[list[dict], dict]:
    """Keep source TOTAL rows separate from disjoint method components.

    All aggregation begins at a native reporting unit/candidate/contest. TOTAL
    supersedes method rows for that exact unit only; absent TOTAL, published
    method categories are summed. Votes for over/undervotes are never candidates.
    """
    provider = source["provider"]
    native = {}
    warnings = []
    suppressed = 0
    input_rows = _csv_rows(path, zipped=provider == "precinct")
    if provider in {'snyder_governor', 'snyder_house'}:
        from .governor_history import governor_rows
        input_rows = governor_rows(input_rows, house=provider == 'snyder_house')
    for row in input_rows:
        state = (row.get("state_po") or STATE_NAMES.get(str(row.get("state_name", "")).upper()) or source.get("state", "")).upper()
        if state not in STATES:
            continue
        year = int(float(row.get("year") or source["years"][0]))
        office = normal_office(row.get("office") or "PRESIDENT")
        if provider == "precinct" and not deep and office != "PRESIDENT":
            continue
        stage = str(row.get("stage") or "GEN").upper()
        special = str(row.get("special", "FALSE")).upper() in {"TRUE", "1"}
        district = str(row.get("district") or "STATEWIDE").strip()
        if district.upper() in {"0", "00", "000", "NA", "NAN"}:
            district = "STATEWIDE"
        # Local contest labels alone are not unique across jurisdictions.
        local = provider == "precinct" and str(row.get("dataverse", "")).upper() == "LOCAL"
        jurisdiction = str(row.get("jurisdiction_name") or row.get("county_name") or "") if local else ""
        candidate = str(row.get("candidate") or "").strip()
        party = normal_party(row.get("party_simplified") or row.get("party") or row.get("party_detailed"))
        if candidate.upper() in NON_OPTIONS or not candidate:
            continue
        is_measure = any(word in office for word in ("PROPOSITION", "REFERENDUM", "AMENDMENT", "BALLOT QUESTION", "MEASURE "))
        option_kind = "response" if is_measure or candidate.upper() in {"YES", "NO", "FOR", "AGAINST"} else "candidate"
        county_fips = str(row.get("county_fips") or row.get("FIPS") or "").split('.')[0].zfill(5)
        county_name = str(row.get("county_name") or row.get("county") or "Unknown reporting area")
        if provider in {"county_legacy", "county_bridge"}:
            if state == "AK" or county_fips in {"000NA", "00000", "00NAN"}:
                continue
            geography_id, level, name = f"county:{county_fips}", "county", county_name
        elif provider == "precinct":
            precinct = str(row.get("precinct") or "UNSPECIFIED")
            parent = row.get("jurisdiction_fips") or row.get("jurisdiction_name") or county_fips
            geography_id = f"precinct:{state}:{year}:{stable_id(parent, precinct)}"
            level, name = "precinct", precinct
        else:
            level = "district" if office == "US HOUSE" else "state"
            geography_id = f"district:{state}:{year}:congress:{district}" if level == "district" else f"state:{state}"
            name = f"{STATES[state]['name']} district {district}" if level == "district" else STATES[state]["name"]
        contest = f"{state}-{year}-{stage}-{'SPECIAL-' if special else ''}{office}-{district}-{jurisdiction}"
        contest_id = "contest:" + stable_id(contest)
        option_id = "option:" + stable_id(contest_id, candidate.upper())
        mode = str(row.get("mode") or "TOTAL").upper().strip()
        mode = "TOTAL" if mode in {"", "NA", "NAN", "ALL"} else mode
        votes = number(row.get("votes", row.get("candidatevotes")))
        if votes is None:
            suppressed += 1
        magnitude = number(row.get("magnitude"))
        info = {"state": state, "year": year, "office": office, "contest_id": contest_id,
            "contest_name": f"{office.title()} · {district}" + (f" · {jurisdiction}" if jurisdiction else ""),
            "district": district, "stage": stage, "special": special,
            "date": row.get("date") or (election_day(year) if stage == "GEN" else ""),
            "magnitude": int(magnitude) if magnitude else 1, "kind": option_kind, "option_id": option_id,
            "candidate": candidate, "party": party, "geography_id": geography_id, "geography_level": level,
            "geography_name": name, "county_fips": county_fips, "county_name": county_name,
            "jurisdiction": str(row.get("jurisdiction_name") or ""), "local": local,
            "jurisdiction_fips":str(row.get("jurisdiction_fips") or ""),
            "round": "first_choice" if state in {"AK", "ME"} and year >= 2018 else "reported",
            "writein": str(row.get("writein", "FALSE")).upper() == "TRUE"}
        key = (contest_id, option_id, geography_id)
        entry = native.setdefault(key, {"info": info, "modes": {}, "parties": set(), "suppressed": False})
        entry["parties"].add(party or "UNCLASSIFIED")
        if party in {"DEM", "REP"}:
            entry["info"]["party"] = party
        entry["suppressed"] |= votes is None
        entry["modes"][mode] = entry["modes"].get(mode, 0) + (votes or 0)
    aggregates = {}
    for entry in native.values():
        info, modes = entry["info"], entry["modes"]
        total = modes["TOTAL"] if "TOTAL" in modes else sum(modes.values())
        if entry["suppressed"] and not total:
            total = None
        targets = [(info["geography_id"], info["geography_level"], info["geography_name"])] if deep or provider != "precinct" else []
        if provider == "precinct":
            # Alaska absentee areas need not be coterminous with boroughs; retain native district geography.
            if info["state"] != "AK" and re.fullmatch(r"\d{5}", info["county_fips"]) and info["county_fips"] != "00000":
                targets.append((f"county:{info['county_fips']}", "county", info["county_name"]))
            if info['state']=='AK' and info['jurisdiction']:
                native_id=info['jurisdiction_fips'] or stable_id(info['jurisdiction'])
                targets.append((f"native:AK:{info['year']}:reporting_area:{native_id}",
                    "district",f"Reporting area {info['jurisdiction']}"))
            if not info["local"] and (info["district"] == "STATEWIDE" or info["office"] in {"PRESIDENT", "US SENATE", "GOVERNOR"}):
                targets.append((f"state:{info['state']}", "state", STATES[info["state"]]["name"]))
            elif not info["local"]:
                targets.append((f"district:{info['state']}:{info['year']}:{info['office']}:{info['district']}",
                    "district", f"{info['office'].title()} district {info['district']}"))
        for geo_id, level, name in set(targets):
            aggregate_key = (info["contest_id"], info["option_id"], geo_id)
            target = aggregates.setdefault(aggregate_key, {**info, "geography_id": geo_id, "geography_level": level,
                "geography_name": name, "votes": 0.0, "mode": "TOTAL", "partial_suppression": False,
                "source_modes": set(), "parties": set(), "known_values": 0})
            if total is not None:
                target["votes"] += total
                target["known_values"] += 1
            target["partial_suppression"] |= entry["suppressed"]
            target["source_modes"].update(modes)
            target["parties"].update(entry["parties"])
    rows = list(aggregates.values())
    for row in rows:
        if not row.pop("known_values"):
            row["votes"] = None
        row["source_modes"] = sorted(row["source_modes"])
        row["parties"] = sorted(row["parties"])
    if suppressed:
        warnings.append(f"{suppressed} suppressed or nonnumeric source rows retained as incomplete, never converted to reported zeroes.")
    if provider == "precinct":
        warnings.append("TOTAL values supersede method components per native reporting unit; source-native method categories are retained in provenance.")
    metadata = {"warnings": warnings, "suppressed_rows": suppressed, "offices": sorted({r['office'] for r in rows})}
    if provider == 'snyder_governor':
        # First local import used the regular GEN stage for these special
        # contests. Preserve its snapshot but withdraw the inferred dates in a
        # new validation revision; special election dates are not supplied.
        metadata['invalidated_contest_ids'] = ['contest:' + stable_id(f'{state}-{year}-GEN-SPECIAL-GOVERNOR-STATEWIDE-')
            for state, year in [('UT', 2010), ('WV', 2011), ('OR', 2016)]]
        metadata['validation_reason'] = 'Academic governor special-election dates were not supplied. Earlier GEN groupings are withheld; separate special stages retain unknown dates.'
    return rows, metadata


def parse_bridge(source: dict, path: str) -> tuple[list[dict], dict]:
    rows = []
    for row in _csv_rows(path):
        state = STATE_NAMES.get(str(row.get("state_name", "")).upper())
        if not state or state == "AK":
            continue
        year = source["years"][0]
        fips = str(row["county_fips"]).zfill(5)
        total, dem, rep = (number(row.get(k)) for k in ("total_votes", "votes_dem", "votes_gop"))
        if None in {total, dem, rep} or total < dem + rep:
            continue
        contest = "contest:" + stable_id(f"{state}-{year}-GEN-PRESIDENT-STATEWIDE-")
        for candidate, party, votes in [("Joe Biden" if year == 2020 else "Kamala Harris", "DEM", dem),
                                        ("Donald Trump", "REP", rep), ("Other candidates", "OTHER", total-dem-rep)]:
            rows.append({"state": state, "year": year, "office": "PRESIDENT", "contest_id": contest,
                "contest_name": "President · STATEWIDE", "district": "STATEWIDE", "stage": "GEN", "special": False,
                "date": election_day(year), "magnitude": 1, "kind": "candidate", "candidate": candidate,
                "party": party, "option_id": "option:" + stable_id(contest, candidate.upper()),
                "geography_id": f"county:{fips}", "geography_level": "county", "geography_name": row["county_name"],
                "votes": votes, "mode": "TOTAL", "round": "reported", "source_modes": ["TOTAL"], "parties": [party],
                "partial_suppression": False, "writein": False})
    return rows, {"offices": ["PRESIDENT"], "warnings": source.get("warnings", [])}


def parse_context(source: dict, path: str, state: str | None = None) -> list[dict]:
    output = []
    with open(path, encoding="utf-8-sig") as stream:
        for row in csv.DictReader(stream, delimiter="|"):
            geo = row.get("GEO_ID", "")
            if geo.startswith("0400000US") and len(geo) == 11:
                code, geo_id = FIPS_STATES.get(geo[-2:]), f"state:{FIPS_STATES.get(geo[-2:])}"
            elif geo.startswith("0500000US") and len(geo) == 14:
                code, geo_id = FIPS_STATES.get(geo[-5:-3]), f"county:{geo[-5:]}"
            else:
                continue
            if code is None or (state and code != state):
                continue
            estimate_raw, moe_raw = row.get(f"{source['table']}_E001"), row.get(f"{source['table']}_M001")
            output.append({"state": code, "geography_id": geo_id, "metric": source["metric"],
                "estimate": number(estimate_raw), "moe": number(moe_raw), "unit": source["unit"],
                "period_start": "2020-01-01", "period_end": "2024-12-31",
                "payload": {"table": source["table"], "variable": f"{source['table']}_001", "confidence_level": 0.90,
                    "estimate_raw": estimate_raw, "moe_raw": moe_raw, "population": "resident population",
                    "is_voter_characteristic": False, "geography_vintage": "2024"}})
    return output


def _publish(database, source: dict, document, rows: list[dict], metadata: dict, *, context=False, deep=True) -> dict:
    now = utc_now()
    with database.lock, database.session() as session, session.begin():
        revision = Revision(reason=f"Atlas {'context' if context else 'election results'}: {source['title']}", source_id=source["id"])
        session.add(revision)
        session.flush()
        snapshot = Snapshot(source_id=source["id"], url=document.url, sha256=document.sha256, path=document.path,
            content_type=document.content_type, retrieved_at=document.retrieved_at, byte_count=document.byte_count, revision=revision.id)
        session.add(snapshot)
        session.flush()
        count = 0
        if context:
            existing = {r.logical_key: r for r in session.scalars(select(ContextEstimate).where(ContextEstimate.dataset_id == source['id']).order_by(ContextEstimate.id))}
            records = []
            for row in rows:
                key = stable_id(source['id'], row['geography_id'], row['metric'], row['period_end'])
                old = existing.get(key)
                if old and old.estimate == row['estimate'] and old.moe == row['moe']:
                    continue
                records.append({**row, "logical_key": key, "dataset_id": source['id'], "snapshot_id": snapshot.id, "revision": revision.id})
            if records:
                session.execute(insert(ContextEstimate), records)
            count = len(records)
        else:
            elections, contests, options, geographies = {}, {}, {}, {}
            records = []
            existing = {r.logical_key: r.votes for r in session.scalars(select(ElectionResult).where(ElectionResult.dataset_id == source['id']).order_by(ElectionResult.id))}
            for row in rows:
                election_id = f"election:{row['state']}:{row['year']}:{row['stage']}"
                elections[election_id] = {"id": election_id, "state": row['state'], "year": row['year'], "date": row['date'], "stage": row['stage'], "payload": {"historical_final": True, "date_precision":"day" if row['date'] else "unknown"}}
                contests[row['contest_id']] = {"id": row['contest_id'], "election_id": election_id, "state": row['state'], "year": row['year'], "office": row['office'], "name": row['contest_name'], "district": row['district'], "magnitude": row['magnitude'], "kind": row['kind'], "payload": {"special": row['special'], "source_id": source['id']}}
                options[row['option_id']] = {"id": row['option_id'], "contest_id": row['contest_id'], "name": row['candidate'], "party": row['party'], "kind": row['kind'], "payload": {"writein": row['writein'], "ballot_parties": row['parties']}}
                geo_version = f"{row['geography_id']}:{row['year']}"
                geographies[geo_version] = {"id": geo_version, "geography_id": row['geography_id'], "state": row['state'], "name": row['geography_name'], "level": row['geography_level'], "vintage": str(row['year']), "parent_id": f"state:{row['state']}" if row['geography_level'] != 'state' else None, "payload": {"source_id": source['id'], "boundary_match": "requires_vintage_check"}}
                key = stable_id(source['id'], row['contest_id'], row['option_id'], row['geography_id'], row['mode'], row['round'])
                if key in existing and existing[key] == row['votes']:
                    continue
                records.append({"logical_key": key, "dataset_id": source['id'], "source_id": source['id'], "snapshot_id": snapshot.id, "revision": revision.id, **{k: row[k] for k in ('state','year','office','contest_id','option_id','geography_id','geography_level','geography_name','votes','mode','round')}, "payload": {"source_tier": source['tier'], "source_modes": row['source_modes'], "partial_suppression": row['partial_suppression'], "historical_final": True, "candidate_vote_denominator": True, "geography_vintage": str(row['year'])}})
            for model, objects in [(Election,elections),(Contest,contests),(BallotOption,options),(GeographyVersion,geographies)]:
                values = list(objects.values())
                for offset in range(0,len(values),2000):
                    if model is Election:
                        statement=sqlite_insert(Election)
                        statement=statement.on_conflict_do_update(index_elements=['id'],set_={'date':statement.excluded.date,'payload':statement.excluded.payload})
                        session.execute(statement,values[offset:offset+2000])
                    else:
                        session.execute(insert(model).prefix_with("OR IGNORE"), values[offset:offset+2000])
            for offset in range(0,len(records),3000):
                session.execute(insert(ElectionResult), records[offset:offset+3000])
            count = len(records)
        stored = session.get(DatasetState, source['id'])
        if metadata.get('invalidated_contest_ids'):
            session.add(AtlasResultValidation(dataset_id=source['id'], revision=revision.id,
                invalidated_contest_ids=metadata['invalidated_contest_ids'],
                reason=metadata.get('validation_reason', 'Separate judicial seats or other repeated office codes use distinct documented candidate option sets; the earlier mixed-office grouping is withheld.'),
                payload={'parser_version':metadata.get('precinct_parser_version'), 'source_sha256':document.sha256}))
        if not stored:
            stored = DatasetState(id=source['id'],dataset_id=source['id'],state=source.get('state'),status="loaded")
            session.add(stored)
        stored.status, stored.checked_at, stored.error, stored.revision = "loaded", now, None, revision.id
        stored.record_count = (stored.record_count or 0) + count
        stored.payload = {**metadata, "sha256": document.sha256, "parser_version": PARSER_VERSION, "depth": "full" if deep else "presidential_core",
            "loaded_states": sorted({r['state'] for r in rows}), "snapshot_id": snapshot.id}
        return {"status": "loaded", "dataset_id": source['id'], "state": source.get('state'), "revision": revision.id,
            "records": count, "record_count": stored.record_count, "warnings": metadata.get('warnings', []), "snapshot_id": snapshot.id}


def load_dataset(database, dataset_id: str, state: str | None = None, *, deep: bool = True, offline: bool = False,
                 progress=None, force: bool = False) -> dict:
    ensure_schema(database)
    if state and dataset_id in {"medsl_2024", "medsl_2022", "medsl_2020", "medsl_2018"}:
        dataset_id = f"{dataset_id}_{state.upper()}"
    source = next((s for s in expanded_sources(database) if s['id'] == dataset_id), None)
    if source is None:
        raise ValueError("Unknown verified atlas dataset")
    if source.get('acquisition') == 'guestbook_required':
        raise ValueError('This original-producer file requires a guestbook response; unattended retrieval is unavailable and no access gate is bypassed.')
    with database.session() as session:
        stored = session.get(DatasetState,dataset_id)
        if not force and stored and stored.status == 'loaded' and stored.payload.get('parser_version') == PARSER_VERSION and (not deep or stored.payload.get('depth') == 'full'):
            return {"status":"unchanged","dataset_id":dataset_id,"revision":stored.revision,"records":0,"record_count":stored.record_count,"warnings":stored.payload.get('warnings',[])}
    fetcher = Fetcher(database.settings, offline=offline)
    try:
        if progress:
            progress({"stage":"download","message":f"Archiving {source['title']}"})
        doc = fetcher.fetch(source['url'])
        if progress:
            progress({"stage":"parse","message":"Validating source rows and preserving geographic and vote-method scope"})
        if source['provider'] == 'acs':
            rows, metadata = parse_context(source,doc.path), {"warnings":source.get('warnings',[])}
            if progress:
                progress({"stage":"publish","total":len(rows),"message":"Publishing population context with original margins of error"})
            result = _publish(database,source,doc,rows,metadata,context=True)
        else:
            rows, metadata = parse_bridge(source,doc.path) if source['provider'] == 'county_bridge' else parse_results(source,doc.path,deep=deep)
            if not rows:
                raise ValueError("Source download contained no valid supported election results")
            if progress:
                progress({"stage":"publish","total":len(rows),"message":"Atomically publishing validated results"})
            result = _publish(database,source,doc,rows,metadata,deep=deep)
        if progress:
            progress({"stage":"complete","completed":result['record_count'],"total":result['record_count'],"message":"Validated evidence ready"})
        return result
    except Exception as exc:
        with database.lock, database.session() as session, session.begin():
            stored = session.get(DatasetState,dataset_id)
            if not stored:
                stored=DatasetState(id=dataset_id,dataset_id=dataset_id,state=source.get('state'),status='error',record_count=0,payload={})
                session.add(stored)
            stored.error, stored.checked_at = str(exc)[:1000], utc_now()
            stored.status = 'loaded_with_error' if stored.record_count else 'error'
        raise
    finally:
        fetcher.client.close()


def core_install(database, *, progress=None) -> dict:
    """Small nationwide reference datasets; large precinct files remain on demand."""
    ensure_schema(database)
    ids = ['medsl_state_president','medsl_state_senate','medsl_house_1976_2018','snyder_governor_2006_2024','snyder_house_2006_2024','medsl_county_2000_2016',
        'county_president_2020_bridge','county_president_2024_bridge','acs2024_population']
    results = []
    for index,dataset_id in enumerate(ids):
        if progress:
            progress({"dataset_id":dataset_id,"completed":index,"total":len(ids)})
        try:
            results.append(load_dataset(database,dataset_id))
        except Exception as exc:
            results.append({"dataset_id":dataset_id,"status":"error","error":str(exc)})
    return {"revision":database.latest_revision(),"datasets":results,"records":sum(r.get('records',0) for r in results)}
