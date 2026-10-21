"""ReconMR Texas primary tables hosted by Siena; hosting is not poll production."""
import re

from pypdf import PdfReader

from observatory.domain import ParsedBatch, Poll

from .common import iso_date, soup


def collect(source: dict, fetcher) -> ParsedBatch:
    release = fetcher.fetch(source["release_url"])
    text = soup(release).get_text(" ", strip=True)
    if "October 13, 2026" not in text:
        raise ValueError("ReconMR release publication date could not be verified")
    methodology_doc = fetcher.fetch(source["methodology_url"])
    methods = " ".join(p.extract_text() or "" for p in PdfReader(methodology_doc.path).pages)
    if "ReconMR Texas Poll was conducted" not in methods:
        raise ValueError("ReconMR primary methodology is unavailable")
    doc = fetcher.fetch(source["url"])
    pages = [p.extract_text() or "" for p in PdfReader(doc.path).pages]
    match = re.search(r"([A-Z][a-z]+) (\d+)\s*-\s*(\d+), (20\d{2})\s+([\d,]+) Texas Likely Voters\s+MOE \+/- ([\d.]+)%", pages[0])
    if not match:
        raise ValueError("ReconMR date/population/MOE table header changed")
    month, start, end, year, n, moe = match.groups()
    start = iso_date(f"{month} {start}, {year}")
    end = iso_date(f"{month} {end}, {year}")
    polls = []
    groups = ["Total", "DEM", "REP", "IND/OTHER", "18–34", "35–49", "50–64", "65+", "Male", "Female",
              "No Degree", "Bachelors+", "Austin", "DFW", "Houston", "Rural", "San Antonio/South", "White NH", "Black NH", "Hispanic"]
    for page_index, question_type, question in [
        (0, "vote_choice", "If the election for Senator of Texas was held today, who would you vote for if the candidates were:"),
        (2, "winner_expectation", "Regardless of who you are voting for, who do you think will win the election for the Senator of Texas?"),
    ]:
        page = pages[page_index]
        begin = re.search(r"(?m)^The Republican, Ken Paxton\s+", page)
        if not begin:
            raise ValueError("ReconMR Senate response section unavailable")
        block = page[begin.start():].split("\nTotal DEM REP", 1)[0]
        rows = []
        for line in block.splitlines():
            row = re.match(r"(.+?)\s+((?:\d+%\s*)+)\s*$", line)
            if not row:
                continue
            values = [float(x) for x in re.findall(r"(\d+)%", row[2])]
            if len(values) != len(groups):
                raise ValueError("ReconMR subgroup table columns changed")
            raw_name = row[1].strip()
            name = re.sub(r"^The (?:Republican|Democrat), ", "", raw_name)
            rows.append((name, "REP" if raw_name.startswith("The Republican,") else "DEM" if raw_name.startswith("The Democrat,") else None, values))
        if len(rows) != (5 if question_type == "vote_choice" else 3):
            raise ValueError("ReconMR response count changed")
        def estimates(col):
            return [{"candidate": name, "name": name, "party": party, "value": values[col], "reported": f"{values[col]:g}%"}
                    for name, party, values in rows]
        polls.append(Poll(study_id=f"reconmr-tx-{start}-{end}", state="TX", producer="ReconMR",
                          sponsor="Not disclosed", publisher="Siena Research Institute", field_start=start, field_end=end,
                          published_at="2026-10-13", population="LV", sample_size=int(n.replace(",", "")),
                          methodology="Dual-frame landline/cell phone probability sample, including text-to-web; weighted using L2 voter data",
                          question_type=question_type, question=question, estimates=estimates(0), margin_of_error=float(moe),
                          source_url=release.url, document_url=doc.url,
                          crosstabs=[{"label": group, "estimates": estimates(i), "sample_size": None, "margin_of_error": None,
                                      "page": page_index + 1, "warning": "Subgroup n and uncertainty not disclosed in this table"}
                                     for i, group in enumerate(groups) if i > 0],
                          metadata={"source_url": doc.url, "source_sha256": doc.sha256, "page": page_index + 1,
                                    "methodology_url": methodology_doc.url, "publication_source_url": release.url,
                                    "publication_date_precision": "day", "candidate_order_rotated": True,
                                    "producer_verification": "Primary PDF explicitly identifies The ReconMR Texas Poll", "parser_version": "1.0"}))
    return ParsedBatch(polls=polls, data_as_of=end, warnings=[
        "ReconMR produced this poll; Siena Research Institute hosts/publishes the release.",
        "Vote choice and winner expectations are separate questions from the same sample.",
        "Sponsor/funding is not explicitly disclosed in these documents; subgroup MOEs are not the statewide MOE.",
    ])
