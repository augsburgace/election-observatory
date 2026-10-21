"""Hawaii's native electronic/mail/early receipt table, with arithmetic checks."""
import re

from observatory.domain import ParsedBatch

from .common import iso_date, number, observation, soup


def collect(source, fetcher):
    doc = fetcher.fetch(source["url"])
    page = soup(doc)
    text = page.get_text(" ", strip=True)
    stamp = re.search(r"Last Updated on ([A-Za-z]+ \d{1,2}, \d{4})", text)
    if not stamp:
        raise ValueError("Hawaii report date unavailable")
    date = iso_date(stamp[1])
    if not date.startswith(str(source.get("cycle", 2026))):
        raise ValueError("Hawaii report belongs to another election cycle")
    table = next((t for t in page.find_all("table") if "ELECT Sent" in t.get_text()), None)
    if table is None:
        raise ValueError("Hawaii voting table schema unavailable")
    parsed = []
    for row in table.find_all("tr")[1:]:
        cells = [c.get_text(" ", strip=True) for c in row.find_all(["td", "th"])]
        if len(cells) != 10:
            raise ValueError("Hawaii voting table width changed")
        values = [number(v) for v in cells[1:]]
        a, b, c, d, e, f, g, voted, total = values
        if voted != b + d + f or total != a + d + e:
            raise ValueError("Hawaii published row arithmetic does not reconcile")
        parsed.append((cells[0], values))
    counties = [(n, v) for n, v in parsed if n]
    totals = [v for n, v in parsed if not n]
    if len(counties) != 4 or len(totals) != 1 or any(sum(v[i] for _, v in counties) != totals[0][i] for i in range(9)):
        raise ValueError("Hawaii county/state reconciliation failed")
    observations = []
    fields = [(0, "ballots_issued", "electronic"), (1, "ballots_returned", "electronic"),
        (2, "ballots_invalid", "electronic"), (3, "ballots_returned", "early_in_person"),
        (4, "ballots_issued", "mail"), (5, "ballots_returned", "mail"),
        (6, "ballots_invalid", "mail"), (7, "ballots_returned", "all")]
    for name, values in parsed:
        for index, metric, mode in fields:
            observations.append(observation(source, doc, name=name or "Hawaii", kind="county" if name else "state",
                value=values[index], metric=metric, mode=mode, date_=date, published_at=date,
                metadata={"native_definition": "Official VOTED means received electronic + early + mail envelopes, not counted candidate votes.",
                    "original_column_index": index + 1, "explicit_reported_zero": values[index] == 0,
                    "coverage_note": "Four administrative county reports; no separate Kalawao figure is supplied.",
                    "acceptance_not_established": True, "coherent_status_cohort": False}))
    return ParsedBatch(observations=observations, data_as_of=date, metadata={"primary_document_url": doc.url},
        warnings=["Native VOTED means received ballots/envelopes; acceptance and candidate choice are not established.",
            "Four county reports reconcile to the published statewide receipt total. Kalawao is not separately reported.",
            "Sent, received and invalid counts are separate administrative measures, not a coherent ballot-status funnel."])
