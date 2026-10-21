"""Parse original Marist methodology and Senate crosstab pages; no seeded results."""
import re

from pypdf import PdfReader

from observatory.domain import ParsedBatch, Poll

from .common import iso_date

PERCENT = r"(?:<\s*1%|\d+%|0|\*)"


def estimates(labels: list[str], values: list[str]) -> list[dict]:
    result = []
    for label, raw in zip(labels, values):
        bounded = raw.startswith("<")
        value = None if raw == "*" or bounded else float(raw.rstrip("%"))
        party = "DEM" if ", the Democrat" in label else "REP" if ", the Republican" in label else None
        name = re.sub(r", the (?:Democrat|Republican)$", "", label)
        result.append({"candidate": name, "name": name, "party": party, "value": value, "reported": raw,
                       **({"upper_bound": 1.0} if bounded else {}), "suppressed": raw == "*"})
    return result


def parse_pages(pages: list[str], source: dict, doc) -> ParsedBatch:
    methods = re.sub(r"\s+", " ", pages[0])
    field = re.search(r"conducted ([A-Z][a-z]+) (\d+)(?:st|nd|rd|th)? through (?:([A-Z][a-z]+) )?(\d+)(?:st|nd|rd|th)?, (20\d{2})", methods)
    if not field:
        raise ValueError("Marist methodology fieldwork dates not found")
    month, start, end_month, end, year = field.groups()
    field_start = iso_date(f"{month} {start}, {year}")
    field_end = iso_date(f"{end_month or month} {end}, {year}")
    n = re.search(r"survey of ([\d,]+).*?registered voters", methods, re.I)
    study = f"marist-{source['state'].lower()}-{field_start}-{field_end}"
    polls = []
    for i, text in enumerate(pages):
        if "Weighted Crosstab" not in text or "Senate" not in text:
            continue
        if "In November's election for Senate, are you supporting:" in text:
            question = "In November's election for Senate, are you supporting:"
            question_type = "vote_choice"
        elif "Regardless of who you support, who do you think will actually win the election for Senate?" in text:
            question = "Regardless of who you support, who do you think will actually win the election for Senate?"
            question_type = "winner_expectation"
        else:
            continue
        flat = re.sub(r"\s+", " ", text)
        row = re.search(fr"\b(Likely Voters|Registered Voters)\s+((?:{PERCENT}\s*){{4,5}})", flat)
        if not row:
            raise ValueError(f"Marist Senate page {i + 1} has an unrecognized topline")
        header = flat[flat.index(question) + len(question):row.start()].strip()
        candidates = re.match(r"(.+?, the Democrat)\s+(.+?, the Republican)\s+Another party's candidate", header)
        if not candidates:
            raise ValueError(f"Marist Senate page {i + 1} candidate header changed")
        labels = [candidates[1], candidates[2], "Another party's candidate",
                  "Undecided" if question_type == "vote_choice" else "Unsure", "No response"]
        values = re.findall(PERCENT, row[2])
        if len(values) not in {4, 5}:
            raise ValueError("Marist Senate topline must have four or five response categories")
        labels = labels[:len(values)]
        population = "LV" if row[1] == "Likely Voters" else "RV"
        population_words = "likely voters" if population == "LV" else "registered voters"
        moe = re.search(fr"Results for {population_words} are statistically significant within ±\s*([\d.]+)", methods, re.I)
        crosstabs = []
        # Preserve source row labels and suppression/bounded values. Do not claim
        # subgroups have the statewide MOE or fabricate unweighted subgroup n.
        after_topline = False
        for line in text.splitlines():
            if re.match(r"\s*(?:Likely|Registered) Voters\s+\d+%", line):
                after_topline = True
                continue
            match = re.match(fr"\s*(.*?)\s+((?:{PERCENT}\s*){{4,5}})\s*$", line)
            if after_topline and match and match[1] and not match[1].startswith("Marist Poll"):
                vals = re.findall(PERCENT, match[2])
                crosstabs.append({"label": match[1].strip(), "estimates": estimates(labels, vals), "page": i + 1,
                                  "sample_size": None, "margin_of_error": None,
                                  "warning": "Subgroup uncertainty is not the statewide MOE; source red-text small-n styling may be lost in extraction."})
        polls.append(Poll(study_id=study, state=source["state"], cycle=int(year), producer="Marist Poll",
                          sponsor="Marist University", publisher="Marist Poll", field_start=field_start,
                          field_end=field_end, published_at=source["published_at"], population=population,
                          sample_size=int(n[1].replace(",", "")) if n and population == "RV" else None,
                          methodology="Multi-mode: live-interviewer phone, text, online; weighted using voter parameters",
                          question_type=question_type,
                          ballot_type="first_choice" if source["state"] in {"AK", "ME"} else "full_ballot",
                          question=question, estimates=estimates(labels, values),
                          margin_of_error=float(moe[1]) if moe else None, source_url=source.get("release_url", source["url"]),
                          document_url=doc.url, crosstabs=crosstabs,
                          metadata={"source_url": doc.url, "source_sha256": doc.sha256, "page": i + 1,
                                    "methodology_page": 1, "sample_size_note": "The reported n describes RV; LV n not disclosed" if population == "LV" else "Reported registered voter sample",
                                    "publication_date_source": source.get("release_url"), "publication_date_precision": "day",
                                    "publication_verified_during_discovery": True, "parser_version": "1.0"}))
    if not polls:
        raise ValueError("No supported Marist Senate vote-choice or expectation crosstab")
    return ParsedBatch(polls=polls, data_as_of=field_end, warnings=[
        "One producer does not qualify for the three-producer descriptive average.",
        "LV and RV share a study sample and must not be treated as independent surveys.",
        "Less-than-one-percent responses remain bounds; suppressed subgroup cells remain unavailable.",
    ])


def collect(source: dict, fetcher) -> ParsedBatch:
    doc = fetcher.fetch(source["url"])
    return parse_pages([p.extract_text() or "" for p in PdfReader(doc.path).pages], source, doc)
