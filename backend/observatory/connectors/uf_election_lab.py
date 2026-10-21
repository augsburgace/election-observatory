"""Attributed academic fallback, always separate from original election authorities.

The UF tracker publishes important state-specific inferences in its notes. Those
notes travel with every observation. Texas synthetic request counts are omitted.
"""
from urllib.parse import urljoin

from observatory.domain import ParsedBatch

from .common import iso_date, number, observation, read_csv

BASE = "https://election.lab.ufl.edu"
LICENSE = "https://creativecommons.org/licenses/by-nc-nd/4.0/"
ATTRIBUTION = "University of Florida Election Lab, Dr. Michael McDonald, 2026 Early Voting Tracker"
DIMENSIONS = {
    "registration": [("dem", "DEM"), ("rep", "REP"), ("none", "Other / no party (UF category)")],
    "age": [("age_1", "18–25"), ("age_2", "26–40"), ("age_3", "41–65"), ("age_4", "Over 65")],
    "gender": [("male", "Male"), ("female", "Female"), ("gender_unknown", "Unknown")],
    "race_ethnicity": [("nh_white", "Non-Hispanic White"), ("nh_black", "Non-Hispanic Black"),
                       ("nh_asian", "Non-Hispanic Asian"), ("nh_native_american", "Non-Hispanic Native American"),
                       ("nh_other", "Other non-Hispanic / unknown (UF category)"), ("hispanic", "Hispanic")],
}

# The producer documents these substitutions in the state notes. Retain the
# original fields in the archive; never promote a proxy into a request count.
REQUEST_PROXIES = {"TX", "DE", "DC", "UT", "WA"}


def semantics(state: str, prefix: str) -> tuple[str, str, dict] | None:
    if prefix == "request" and state in REQUEST_PROXIES:
        return None
    metric, mode = {
        "voted": ("ballots_cast", "all"),
        "inperson": ("ballots_cast", "early_in_person"),
        "accept": ("ballots_returned", "mail"),
        "request": ("ballots_requested", "mail"),
    }[prefix]
    metadata = {}
    if state == "AZ" and prefix == "request":
        metric = "ballots_issued"
        metadata["definition_correction"] = "Published request_* columns represent mail ballots issued, not applications."
    if state == "TN" and prefix == "voted":
        mode = "early_in_person"
        metadata["definition_correction"] = "Tennessee's reported total covers early in-person participation only."
    if state in {"KY", "MD"}:
        metadata.update(report_date_semantics="upstream_upload_date", underlying_report_date_unverified=True)
    if state in {"CA", "GA", "NV", "FL"}:
        metadata["upstream_method"] = "Producer combines or selects higher authority/other figures; see original state notes."
    if state == "OH" and prefix == "inperson":
        metadata["mode_classification"] = "Inferred by producer from same-day sent/received dates; not directly observed voting mode."
    if state == "IA" and prefix == "accept":
        metadata["status_classification"] = "Producer infers received mail from RECEIVED_DATE; acceptance status is not established."
    return metric, mode, metadata


def parse_row(row: dict, source: dict, doc, state_row: dict, *, county: bool = False):
    state = source["state"]
    date_ = iso_date(state_row["last_update"])
    name = row["county"].title() if county else state_row["state"]
    kind = "municipality" if county and state == "ME" else "county" if county else "state"
    meta = {"academic_fallback": True, "source_tier": 3, "attribution": ATTRIBUTION,
            "license": LICENSE, "license_note": "Personal noncommercial research; review redistribution and adaptations against source license before publication",
            "upstream_source": state_row.get("data_source"), "source_notes": state_row.get("notes"),
            "statewide_last_update": state_row["last_update"], "county_date_inherited_from_reconciled_state": county,
            "definition_url": BASE + "/wp-content/themes/electionlab2023/2026-early-voting.js"}
    obs = []
    for prefix in ("voted", "inperson", "accept", "request"):
        definition = semantics(state, prefix)
        if definition is None:
            continue
        metric, mode, semantic_metadata = definition
        if state == "TN" and prefix == "inperson" and number(row.get("voted_all") or "0") > 0:
            continue  # Same source family already represented as in-person.
        key = prefix + "_all"
        if key not in row or row[key] in {"", "NA", "N/A"}:
            continue
        value = number(row[key])
        # The tracker uses all-zero families for missing categories. A zero
        # method total without positive source activity is not asserted as data.
        if value == 0:
            continue
        kw = dict(name=name, kind=kind, metric=metric, mode=mode, date_=date_,
                  metadata={**meta, **semantic_metadata, "original_column": key, "original_cell": row[key],
                            "native_definition": {"voted": "Mail ballots received plus early in-person ballots (UF tracker)",
                                                  "accept": "UF accepted/received mail ballots; see state-specific notes",
                                                  "inperson": "UF early in-person; see approximation caveats",
                                                  "request": "Mail ballot requests (UF tracker)"}[prefix]})
        if semantic_metadata.get("definition_correction"):
            kw["metadata"]["native_definition"] = semantic_metadata["definition_correction"]
        obs.append(observation(source, doc, value=value, **kw))
        for dim, categories in DIMENSIONS.items():
            available = [(suffix, label, row.get(prefix + "_" + suffix, "")) for suffix, label in categories]
            numeric = [(suffix, label, number(val)) for suffix, label, val in available if val not in {"", "NA", "N/A"}]
            subtotal = sum(v for _, _, v in numeric)
            if subtotal == 0:
                continue
            for suffix, label, v in numeric:
                item = observation(source, doc, value=v, dimension=dim, category=label, **kw)
                item.metadata.update({"original_column": prefix + "_" + suffix,
                                      "original_cell": row[prefix + "_" + suffix],
                                      "breakdown_sum": subtotal, "breakdown_complete": subtotal == value})
                obs.append(item)
    return obs


def collect(source: dict, fetcher) -> ParsedBatch:
    index = fetcher.fetch(source.get("about_url", BASE + "/early-vote/2026-early-voting/"))
    doc = fetcher.fetch(source["url"])
    rows = list(read_csv(doc))
    row = next((r for r in rows if r.get("state_abbv") == source["state"]), None)
    if not row:
        raise ValueError("State absent from UF public 2026 tracker; no fabricated missing-state values")
    if not row.get("last_update"):
        raise ValueError("UF state row has no last-update date")
    observations = parse_row(row, source, doc, row)
    if row.get("turn_2022") not in {None, "", "NA", "N/A", "0"}:
        observations.append(observation(source, doc, name=row["state"], kind="state", metric="final_turnout",
            value=number(row["turn_2022"]), date_="2022-11-08", cycle=2022, basis="final",
            metadata={"academic_fallback": True, "source_tier": 3, "attribution": ATTRIBUTION,
                      "license": LICENSE, "original_column": "turn_2022", "original_cell": row["turn_2022"],
                      "native_definition": "UF tracker historical 2022 total turnout reference; not current turnout denominator"}))
    warnings = ["Academic fallback, not direct official collection. " + ATTRIBUTION,
                "Source-specific definitions and inferences are preserved in every observation.",
                "All-zero demographic families mean unavailable and are excluded. Categories are marginal, not joint filters.",
                "Source license CC BY-NC-ND 4.0; private noncommercial research. Publication requires license review."]
    notes = row.get("notes", "")
    if notes and notes != "NA":
        warnings.append(notes)
    if source["state"] in REQUEST_PROXIES:
        warnings.append("Request fields omitted: the producer substitutes returns or registration for unavailable actual requests.")
    if source["state"] == "AZ":
        warnings.append("The producer's request_* fields are issued ballots; normalized as ballots issued, never requests.")
    if source["state"] == "TN":
        warnings.append("Only early in-person participation is reported; no complete all-method total is asserted.")
    if source["state"] != "TX":
        county_url = urljoin(BASE, f"/data-downloads/earlyvote/2026/{source['state']}_county.csv")
        try:
            county_doc = fetcher.fetch(county_url)
        except Exception as exc:
            # Several producers expose only statewide data. Retain the archived
            # state evidence while reporting the separate geographic gap.
            warnings.append(f"County export unavailable; only statewide aggregates validated: {str(exc)[:180]}")
            return ParsedBatch(observations=observations, data_as_of=iso_date(row["last_update"]), warnings=warnings,
                metadata={"primary_document_url": doc.url, "license": LICENSE, "attribution": ATTRIBUTION,
                          "about_snapshot_url": index.url})
        counties = list(read_csv(county_doc))
        if not counties or "county" not in counties[0]:
            raise ValueError("UF county/municipality export schema changed")
        # Fail closed on asynchronous files. County data cannot inherit a
        # statewide reporting date unless all published total modes reconcile.
        columns = [key for key in ("voted_all", "accept_all", "inperson_all", "request_all") if key in counties[0]]
        matches = all(sum(number(r.get(key, "0") or "0") for r in counties) == number(row[key]) for key in columns)
        if matches:
            for county in counties:
                observations.extend(parse_row(county, source, county_doc, row, county=True))
        else:
            warnings.append("County and statewide files do not reconcile at this collection; county observations withheld to avoid mixed vintages.")
    return ParsedBatch(observations=observations, data_as_of=iso_date(row["last_update"]), warnings=warnings,
                       metadata={"primary_document_url": doc.url, "license": LICENSE, "attribution": ATTRIBUTION,
                                 "about_snapshot_url": index.url})
