"""Florida Division of Elections downloadable tab-separated public statistics."""
from urllib.parse import urljoin

from observatory.domain import ParsedBatch

from .common import iso_date, number, observation, read_csv, soup


def collect(source: dict, fetcher) -> ParsedBatch:
    index = fetcher.fetch(source["url"])
    links = [urljoin(index.url, a["href"]) for a in soup(index).select("a[href]")
             if "Stats_" in a["href"] and a["href"].lower().endswith(".txt")]
    if len(links) < 3:
        raise ValueError("Florida public statistics no longer advertises three downloadable statistics files")
    obs, dates = [], []
    for url in dict.fromkeys(links):
        doc = fetcher.fetch(url)
        for row in read_csv(doc, "\t"):
            if not {"StatType", "GrandTotal", "ElectionDate", "CountyName", "CompileDate"}.issubset(row):
                raise ValueError("Florida public statistics schema changed")
            election = iso_date(row["ElectionDate"])
            if election != "2026-11-03":
                continue
            stat = row["StatType"].strip()
            metric, mode = (("ballots_outstanding", "mail") if "Not Yet" in stat or "Provided" in stat
                            else ("ballots_cast", "early_in_person" if "Early" in stat else "mail"))
            raw_date = row["CompileDate"].strip()
            # Blank compilation dates are no submission, even when cells contain
            # zero. Do not turn the portal's placeholder zeros into observations.
            if not raw_date:
                continue
            date_ = iso_date(raw_date.split()[0])
            dates.append(date_)
            name = "Florida" if row["CountyName"] == "State Totals" else row["CountyName"]
            kw = dict(name=name, kind="state" if name == "Florida" else "county", date_=date_, mode=mode,
                      metric=metric, metadata={"native_definition": stat, "compile_date": raw_date,
                      "election_number": row.get("ElectionNumber"), "original_column": "GrandTotal"})
            total = number(row["GrandTotal"])
            parts = [("TotalRep", "REP"), ("TotalDem", "DEM"), ("TotalOth", "Other"), ("TotalNpa", "NPA")]
            if sum(number(row[col]) for col, _ in parts) != total:
                raise ValueError(f"Florida categories fail reconciliation in {name}")
            obs.append(observation(source, doc, value=total, **kw))
            for col, label in parts:
                obs.append(observation(source, doc, value=number(row[col]), dimension="registration", category=label, **kw))
    if not obs:
        raise ValueError("No dated 2026 general-election Florida observations")
    # Derive all early-voting modes only where BOTH files report the same
    # geography/date/category. A missing county submission is never a zero.
    from collections import defaultdict
    pairs = defaultdict(dict)
    for item in obs:
        if item.metric == "ballots_cast":
            pairs[(item.geography_id, item.date, item.category_dimension, item.category)][item.mode] = item
    for pair in pairs.values():
        if set(pair) == {"mail", "early_in_person"}:
            mail, early = pair["mail"], pair["early_in_person"]
            obs.append(mail.model_copy(update={"mode": "all", "value": mail.value + early.value,
                "metadata": {**mail.metadata, "derived": "Sum of same-day voted-by-mail and voted-early categories",
                             "component_source_urls": [mail.metadata["source_url"], early.metadata["source_url"]]}}))
    return ParsedBatch(observations=obs, data_as_of=max(dates), warnings=[
        "Florida county compilation dates vary; blank-date placeholder zeroes are excluded.",
        "Registered party is not candidate choice. Provided-but-unreturned ballots are outstanding, not votes.",
    ])
