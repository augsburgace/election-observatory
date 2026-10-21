"""Official NC aggregate cast-ballot CSVs. Never interpret registrations as votes."""
from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

from observatory.domain import ParsedBatch

from .common import ELECTION_DATES, observation, read_csv


def collect(source: dict, fetcher) -> ParsedBatch:
    doc = fetcher.fetch(source["url"])
    cycle = source.get("cycle", 2026)
    # Source does not publish a data timestamp inside this CSV. Date is observation
    # time, not an asserted publication time or event date.
    date_ = ELECTION_DATES[cycle] if cycle < 2026 else datetime.fromisoformat(doc.retrieved_at.replace("Z", "+00:00")).astimezone(ZoneInfo("America/New_York")).date().isoformat()
    totals = defaultdict(int)
    dimensions = {"party_cd": "registration", "gender": "gender", "race": "race", "ethnicity": "ethnicity"}
    rows = 0
    for raw in read_csv(doc):
        row = {k.strip(): v.strip() for k, v in raw.items() if k is not None}
        if not {"county_name", "abs_request_type", "0"}.issubset(row):
            raise ValueError("NC aggregate schema changed: missing county_name/abs_request_type/0")
        value = int(row["0"])
        if value < 0:
            raise ValueError("NC published a negative count")
        rows += 1
        county = row["county_name"].title()
        mode = "early_in_person" if row["abs_request_type"] in {"ONE-STOP", "EARLY VOTING"} else "mail"
        # Repeated zero-filled categories are true published zeroes; sum each
        # marginal from the joint cells exactly once, never sum marginals together.
        for geography in (county, "North Carolina"):
            for m in (mode, "all"):
                totals[(geography, m, None, None)] += value
                for col, dim in dimensions.items():
                    if col in row:
                        totals[(geography, m, dim, row[col] or "Unknown")] += value
    if rows == 0:
        raise ValueError("NC file has no data rows")
    obs = [observation(source, doc, name=name, kind="state" if name == "North Carolina" else "county",
                       value=value, metric="ballots_cast", date_=date_, mode=mode,
                       dimension=dim, category=category,
                       metadata={"original_column": "0", "native_definition": "Counts of absentee ballots cast, including in-person early voting",
                                 "observation_date_only": cycle == 2026, "includes_uocava": True,
                                 "dimensions_are_marginals": True})
           for (name, mode, dim, category), value in totals.items()]
    return ParsedBatch(observations=obs, data_as_of=date_, metadata={"input_rows": rows}, warnings=[
        "NC counts are cast ballots, not certified candidate votes or an accepted-ballot measure.",
        "CSV has no publication timestamp. Current date is retrieval date; historical files are final endpoints, not same-day snapshots.",
        "State-native ONE-STOP and EARLY VOTING map to early_in_person; CIVILIAN/MILITARY/OVERSEAS map to mail.",
    ])
