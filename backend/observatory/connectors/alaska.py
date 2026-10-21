"""Alaska native ballot categories, without manufacturing county geography."""
import re

from observatory.domain import ParsedBatch

from .common import ELECTION_DATES, iso_date, number, observation, soup


def collect(source: dict, fetcher) -> ParsedBatch:
    doc = fetcher.fetch(source["url"])
    page = soup(doc)
    obs, dates = [], []
    for cycle in (2026, 2024, 2022, 2020, 2018):
        heading = next((h for h in page.find_all(re.compile("^h[1-6]$"))
                        if re.match(fr"{cycle} General Election", h.get_text(" ", strip=True))), None)
        if heading is None:
            continue
        table = heading.find_next("table")
        if table is None or "Number Received" not in table.get_text():
            raise ValueError(f"Alaska {cycle} ballot category table unavailable")
        before = []
        for el in heading.next_elements:
            if el is table:
                break
            if isinstance(el, str):
                before.append(el.strip())
        text = " ".join(before)
        updated = re.search(r"Table last updated ([A-Z][a-z]+ \d{1,2}, \d{4})", text)
        if cycle == 2026 and not updated:
            raise ValueError("Alaska current report lacks its update date")
        d = iso_date(updated[1]) if cycle == 2026 else ELECTION_DATES[cycle]
        dates.append(d)
        # Keep the authority's totals. Historical all totals include Questioned
        # ballots and are not comparable with pre-election-only categories.
        for label, metric in (("Issued", "ballots_issued"), ("Received", "ballots_returned")):
            total = re.search(fr"Total Ballots {label}:\s*([\d,]+)", text)
            if total:
                obs.append(observation(source, doc, name="Alaska", kind="state", value=number(total[1]),
                                       metric=metric, date_=d, cycle=cycle,
                                       metadata={"native_definition": f"Total Ballots {label}",
                                                 "historical_total_includes_questioned": cycle < 2026,
                                                 "original_cell": total[0]}))
        for row in table.select("tr"):
            cells = [c.get_text(" ", strip=True) for c in row.select("td")]
            if len(cells) != 3:
                continue
            mode = {"Early Vote": "early_in_person", "By Mail": "mail", "In-Person (Absentee)": "absentee_in_person",
                    "Online Delivery": "online_delivery", "By Fax": "fax", "Federal Write-In (Absentee)": "federal_write_in",
                    "Questioned": "questioned", "Special Needs": "special_needs"}.get(cells[0])
            if not mode:
                continue
            for i, metric in ((1, "ballots_issued"), (2, "ballots_returned")):
                if not cells[i]:
                    continue
                obs.append(observation(source, doc, name="Alaska", kind="state", value=number(cells[i]),
                                       metric=metric, date_=d, mode=mode, cycle=cycle,
                                       metadata={"native_definition": cells[0], "original_cell": cells[i],
                                                 "original_column": "Number Issued" if i == 1 else "Number Received"}))
    if not obs:
        raise ValueError("Alaska general-election tables could not be identified")
    return ParsedBatch(observations=obs, data_as_of=max(dates), warnings=[
        "Alaska preserves Early Vote, In-Person (Absentee), mail, and other native categories separately.",
        "Historical final totals include questioned ballots and early votes through Election Day; they are not pre-election-only totals.",
    ])
