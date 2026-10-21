"""Race/metric registry; counts are never seeded here."""
from __future__ import annotations

import json
from datetime import date

from .settings import PROJECT_ROOT

STATE_ROWS = """AL|Alabama|01
AK|Alaska|02
AZ|Arizona|04
AR|Arkansas|05
CA|California|06
CO|Colorado|08
CT|Connecticut|09
DE|Delaware|10
FL|Florida|12
GA|Georgia|13
HI|Hawaii|15
ID|Idaho|16
IL|Illinois|17
IN|Indiana|18
IA|Iowa|19
KS|Kansas|20
KY|Kentucky|21
LA|Louisiana|22
ME|Maine|23
MD|Maryland|24
MA|Massachusetts|25
MI|Michigan|26
MN|Minnesota|27
MS|Mississippi|28
MO|Missouri|29
MT|Montana|30
NE|Nebraska|31
NV|Nevada|32
NH|New Hampshire|33
NJ|New Jersey|34
NM|New Mexico|35
NY|New York|36
NC|North Carolina|37
ND|North Dakota|38
OH|Ohio|39
OK|Oklahoma|40
OR|Oregon|41
PA|Pennsylvania|42
RI|Rhode Island|44
SC|South Carolina|45
SD|South Dakota|46
TN|Tennessee|47
TX|Texas|48
UT|Utah|49
VT|Vermont|50
VA|Virginia|51
WA|Washington|53
WV|West Virginia|54
WI|Wisconsin|55
WY|Wyoming|56"""
WATCHLIST = set("AK FL GA IA KS ME MI MN NE NH NC OH SC TX".split())
CONTESTED = set("AL AK AR CO DE FL GA ID IL IA KS KY LA ME MA MI MN MS MT NE NH NJ NM NC OH OK OR RI SC SD TN TX VA WV WY".split())
DEMOCRATIC_SEATS = set("CO DE GA IL MA MI MN NH NJ NM OR RI VA".split())
ELECTION_DATES = {year: next(date(year, 11, day).isoformat() for day in range(2, 9)
    if date(year, 11, day).weekday() == 1) for year in range(1976, 2101)}


def all_states() -> list[dict]:
    rows = []
    for row in STATE_ROWS.splitlines():
        code, name, fips = row.split("|")
        rows.append({"code": code, "name": name, "fips": fips, "watchlist": code in WATCHLIST,
                     "contested": code in CONTESTED, "seat_party": "D" if code in DEMOCRATIC_SEATS else ("R" if code in CONTESTED else "not_up"),
                     "election_system": "ranked_choice" if code in {"AK", "ME"} else ("majority_runoff" if code == "GA" else "plurality")})
    return rows


def state_info(code: str) -> dict:
    return next(row for row in all_states() if row["code"] == code.upper())


def source_covers_state(source: dict, state: str) -> bool:
    """National administrative datasets are one source with multiple state rows."""
    return (source.get("state") == state.upper() or state.upper() in source.get("states", [])
            or source.get("scope") == "national")


def races() -> list[dict]:
    return [{"id": f"2026-{s['code']}-SEN" + ("-SPECIAL" if s["code"] in {"FL", "OH"} else ""),
             "state": s["code"], "name": f"{s['name']} U.S. Senate", "cycle": 2026,
             "election_date": ELECTION_DATES[2026], "watchlist": s["watchlist"],
             "election_system": s["election_system"], "seat_party": s["seat_party"],
             "special": s["code"] in {"FL", "OH"}, "candidates": [],
             "candidate_verification": "Official ballot candidate import not yet verified",
             "source_url": "https://www.fec.gov/documents/5910/2026pdates.pdf"}
            for s in all_states() if s["contested"]]


METRICS = [
    {"id": "ballot_records_returned", "label": "Returned absentee records", "unit": "records", "description": "Source rows with a return date. Reissued/duplicate records may exist; this is not an accepted-ballot or unique-voter count."},
    {"id": "ballot_records_requested", "label": "Absentee request records", "unit": "records", "description": "Source request records, potentially including reissues; not ballots cast."},
    {"id": "ballot_records_issued", "label": "Issued absentee records", "unit": "records", "description": "Source issuance records, potentially including reissues; not ballots cast."},
    {"id": "ballots_accepted", "label": "Accepted early ballots", "unit": "ballots", "description": "Early ballots explicitly reported accepted by the authority. Does not identify candidate votes."},
    {"id": "ballots_returned", "label": "Returned ballots", "unit": "ballots", "description": "Ballots reported received or returned; acceptance may still be pending."},
    {"id": "ballots_cast", "label": "Reported early voting", "unit": "ballots", "description": "Participation explicitly reported as voting by the source; consult native categories."},
    {"id": "ballots_requested", "label": "Ballot requests", "unit": "requests", "description": "Requests or applications, not votes cast."},
    {"id": "ballots_issued", "label": "Ballots issued", "unit": "ballots", "description": "Ballots issued/sent, not returned or accepted."},
    {"id": "ballots_outstanding", "label": "Outstanding ballots", "unit": "ballots", "description": "Source-defined issued ballots still outstanding; not returned, accepted, or cast ballots."},
    {"id": "ballots_rejected", "label": "Rejected ballots", "unit": "ballots", "description": "Source-defined rejected ballots; revisions and cure procedures can change totals."},
    {"id": "ballots_invalid", "label": "Reported invalid ballots", "unit": "ballots", "description": "Native authority invalid status; distinct from final rejection and potentially subject to cure/revision."},
    {"id": "registered_voters", "label": "Registered voters", "unit": "voters", "description": "Dated registration denominator; active/all status is source-defined."},
    {"id": "final_turnout", "label": "Final participation", "unit": "ballots", "description": "Historical final participation; a reference, not the current turnout denominator."},
    {"id": "candidate_votes", "label": "Certified candidate votes", "unit": "votes", "description": "Official contest results; not inferred from early-voter characteristics."},
]


def sources() -> list[dict]:
    path = PROJECT_ROOT / "config" / "sources.json"
    if not path.exists():
        return []
    payload = json.loads(path.read_text())
    inventory = payload.get("sources", []) if isinstance(payload, dict) else payload
    # Separate dated archive programs retain their own reviewed inventories.
    for name in ("ev_historical_sources.json", "ohio_historical_sources.json", "turnout_historical_sources.json", "external_context_sources.json", "ev_gap_sources.json"):
        extra = PROJECT_ROOT / "config" / name
        if extra.exists():
            inventory.extend(json.loads(extra.read_text())["sources"])
    if len({row["id"] for row in inventory}) != len(inventory):
        raise ValueError("Source identifiers must be unique across the source inventories")
    existing = {row["state"] for row in inventory if row.get("connector") == "uf_tracker"}
    # This is a source inventory, not a claim of observed participation. Files
    # are validated only when a state is opened; absent/placeholder rows stay absent.
    for state in all_states():
        if state["code"] in existing:
            continue
        inventory.append({"id": f"uf-fallback-{state['code'].lower()}", "state": state["code"],
            "name": f"UF Election Lab {state['name']} attributed academic fallback",
            "url": "https://election.lab.ufl.edu/data-downloads/earlyvote/2026/US.csv",
            "about_url": "https://election.lab.ufl.edu/early-vote/2026-early-voting/",
            "connector": "uf_tracker", "tier": 3, "enabled": False, "on_demand": True,
            "expected_hours": 4, "cycle": 2026,
            "notes": "Availability is unproven until collection; absent or all-zero placeholder rows do not establish zero participation. CC BY-NC-ND 4.0 personal noncommercial research."})
    return inventory
