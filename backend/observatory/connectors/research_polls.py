"""Original university/research polling documents with fail-closed extraction.

Numerical estimates are always read from the downloaded original document.
Narrative-only releases explicitly retain that limitation instead of inventing
questionnaire wording. Hypothetical candidates and RCV rounds stay distinct.
"""
from __future__ import annotations

import re
from datetime import datetime

from pypdf import PdfReader

from observatory.domain import ParsedBatch, Poll

from .common import soup

MONTHS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
          "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}
DATE_RANGE = re.compile(r"([A-Z][a-z]+)\.?\s+(\d{1,2})(?:st|nd|rd|th)?\s*(?:-|–|—|to|through|and)\s*(?:([A-Z][a-z]+)\.?\s*)?(\d{1,2})(?:st|nd|rd|th)?,?\s+(20\d{2})")


def flat(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def period(text: str) -> tuple[str, str]:
    match = DATE_RANGE.search(text)
    if not match:
        raise ValueError("Original polling document has no supported fieldwork date range")
    month, start, end_month, end, year = match.groups()
    return (datetime(int(year), MONTHS[month[:3].lower()], int(start)).date().isoformat(),
            datetime(int(year), MONTHS[(end_month or month)[:3].lower()], int(end)).date().isoformat())


def estimate(name: str, party: str | None, value: str | float) -> dict:
    party = {"D": "DEM", "R": "REP", "I": "IND"}.get(party, party)
    raw = str(value)
    numeric = None if raw.startswith("<") else float(raw.rstrip("%"))
    if numeric is not None and not 0 <= numeric <= 100:
        raise ValueError("Source percentage outside 0–100")
    return {"candidate": name, "name": name, "party": party, "value": numeric, "reported": raw,
            **({"upper_bound": float(raw[1:].rstrip("%"))} if raw.startswith("<") else {})}


def publication(release, source: dict) -> tuple[str, bool]:
    page = soup(release)
    meta = page.select_one('meta[property="article:published_time"], meta[property="og:article:published_time"]')
    if meta and meta.get("content"):
        return meta["content"][:10], True
    if source.get("published_at"):
        evidence = source.get("publication_evidence")
        if evidence and re.search(evidence, flat(page.get_text(" ", strip=True)), re.I):
            return source["published_at"], True
    # An unidentified release date is not backdated to a guess. The first local
    # archive instant establishes a conservative availability cutoff.
    return release.retrieved_at, False


def make_poll(source, doc, release, *, dates, population, question, estimates, sample=None, moe=None,
              question_type="vote_choice", ballot_type="full_ballot", page=None, exact=True, metadata=None):
    published, verified = publication(release, source)
    producer = source["producer"]
    start, end = dates
    return Poll(study_id=f"{source['study_prefix']}-{start}-{end}", state=source["state"], cycle=2026,
                producer=producer, publisher=source.get("publisher", producer), sponsor=source.get("sponsor", "Not disclosed"),
                field_start=start, field_end=end, published_at=published, population=population,
                sample_size=sample, margin_of_error=moe, methodology=source.get("methodology", "See original methodology"),
                question_type=question_type, ballot_type=ballot_type, question=question, estimates=estimates,
                source_url=release.url, document_url=doc.url, metadata={
                    "source_url": doc.url, "source_sha256": doc.sha256, "page": page, "parser_version": "1.0",
                    "question_wording_exact": exact, "publication_date_verified": verified,
                    "publication_basis": "Original release" if verified else "First local observation; release date not established",
                    "shared_sample_id": f"{source['study_prefix']}-{start}-{end}", **(metadata or {})})


def collect_elon(source, fetcher):
    release = fetcher.fetch(source["release_url"])
    doc = fetcher.fetch(source["url"])
    pages = [p.extract_text() or "" for p in PdfReader(doc.path).pages]
    methods = flat(pages[0])
    dates = period(methods)
    polls = []
    for page_number, question_type in ((4, "vote_choice"), (17, "winner_expectation")):
        text = flat(pages[page_number - 1])
        scope = text[text.index("US SENATE NC" if question_type == "vote_choice" else "US SENATE PREDICT"):]
        qpattern = (r"(If the election for United States Senator.*?someone else\?)" if question_type == "vote_choice"
                    else r"(Regardless of how you personally plan to vote,.*?someone else\?)")
        q = re.search(qpattern, text)
        if not q:
            raise ValueError("Elon original Senate question wording changed")
        n = re.search(r"N=\s*100%\s+(\d+)\s+100%\s+(\d+)\s+100%\s+(\d+)", scope)
        if not n:
            raise ValueError("Elon population-specific sample sizes absent")
        labels = [("MICHAEL WHATLEY, REPUBLICAN", "Michael Whatley", "REP"), ("ROY COOPER, DEMOCRAT", "Roy Cooper", "DEM"),
                  ("SHANNON BRAY, LIBERTARIAN", "Shannon Bray", "LIB"), ("MICHAEL DUBLIN, GREEN", "Michael Dublin", "GRN")]
        labels += ([("SOMEONE ELSE", "Someone else", None), ("UNDECIDED", "Undecided", None), ("DO NOT PLAN TO VOTE", "Do not plan to vote", None)]
                   if question_type == "vote_choice" else [("UNSURE", "Unsure", None)])
        rows = []
        for original, name, party in labels:
            row = re.search(re.escape(original) + r"\s+(\d+)%\s+\d+\s+(\d+)%\s+\d+\s+(\d+)%\s+\d+", scope)
            if not row:
                raise ValueError(f"Elon response row {original} missing")
            rows.append((name, party, row.groups()))
        for col, pop, moe_label in ((0, "LV", "Likely voters"), (1, "RV", "Registered voters"), (2, "A", "All adults")):
            moe = re.search(re.escape(moe_label) + r":\s*\+/-\s*([\d.]+)%", methods)
            polls.append(make_poll(source, doc, release, dates=dates, population=pop, question=q[1],
                estimates=[estimate(name, party, vals[col]) for name, party, vals in rows], sample=int(n[col + 1]),
                moe=float(moe[1]) if moe else None, question_type=question_type, page=page_number,
                metadata={"fieldwork_provider": "YouGov", "n_scope": "Population-specific n parsed from table; not adult n reused as LV n",
                          "undecideds_reallocated": False}))
    return ParsedBatch(polls=polls, data_as_of=dates[1], warnings=[
        "LV, RV, and adults share the same study and are separate populations. Original undecideds remain unallocated.",
        "Elon designed and sponsored the study; YouGov fielded the nonprobability online survey."])


def collect_ut(source, fetcher):
    release = fetcher.fetch(source["release_url"])
    doc = fetcher.fetch(source["url"])
    pages = [p.extract_text() or "" for p in PdfReader(doc.path).pages]
    dates = period(flat(pages[0]))
    page = next((i for i, text in enumerate(pages) if "Q21F." in text and "U.S. senate election" in text), None)
    if page is None:
        raise ValueError("UT/Texas Politics Project Senate question not found")
    text = flat(pages[page])
    q = re.search(r"Q21F\.\s*(.*?)\s*\(n=(\d+), Margin of error \+/- ([\d.]+)%\)", text)
    row = re.search(r"Percent\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+Aug\.", text)
    if not q or not row:
        raise ValueError("UT Senate topline/n/MOE layout changed")
    labels = [("James Talarico", "DEM"), ("Ken Paxton", "REP"), ("Ted Brown", "LIB"), ("Someone else", None), ("Haven't thought enough to have an opinion", None)]
    poll = make_poll(source, doc, release, dates=dates, population="LV", question=q[1],
        estimates=[estimate(name, party, value) for (name, party), value in zip(labels, row.groups())],
        sample=int(q[2]), moe=float(q[3]), page=page + 1, ballot_type="forced_choice_with_leaners",
        metadata={"includes_followup_leaners": True, "comparison_limitation": "Follow-up forced-choice responses are folded into this table; do not pool with unallocated undecided questions"})
    return ParsedBatch(polls=[poll], data_as_of=dates[1], warnings=[
        "Senate table n=861 is parsed separately from the full registered-voter n=1200.",
        "This forced-choice trial ballot folds follow-up choices into results and stays separate from unallocated-undecided polling."])


def collect_asr(source, fetcher):
    doc = fetcher.fetch(source["url"])
    text = flat(soup(doc).get_text(" ", strip=True))
    dates = period(text)
    n, moe = re.search(r"N=([\d,]+)\s+LV", text), re.search(r"MOE=\+/-([\d.]+)%", text)
    question = re.search(r"Q:\s*(Rank the following candidates for US Senate.*?preference\.)", text)
    if not n or not moe or not question:
        raise ValueError("ASR sample/MOE/rank question missing")
    polls = []
    for round_number in (1, 2):
        block = re.search(fr"RCV Round {round_number}:\s*(.*?)(?:\*|RCV Round|NOTE ON)", text)
        if not block:
            raise ValueError("ASR RCV round missing")
        estimates = [estimate(name.strip(), party, val) for name, party, val in
                     re.findall(r"([A-Z][A-Za-z ]+?)\s*\(([DRI])\)\s*([\d.]+)%", block[1])]
        if len(estimates) != (4 if round_number == 1 else 3):
            raise ValueError("ASR RCV response count changed")
        polls.append(make_poll(source, doc, doc, dates=dates, population="LV", question=question[1],
            estimates=estimates, sample=int(n[1].replace(",", "")), moe=float(moe[1]),
            ballot_type="first_choice" if round_number == 1 else "simulated_rcv_round_2", metadata={"rcv_round": round_number,
                "question_note": "Survey simulation is not an election winner probability"}))
    return ParsedBatch(polls=polls, data_as_of=dates[1], warnings=["RCV round 1 and simulated round 2 are distinct outputs of one study; neither is a calibrated forecast."])


def collect_anselm(source, fetcher):
    doc = fetcher.fetch(source["url"])
    pages = [p.extract_text() or "" for p in PdfReader(doc.path).pages]
    methods = flat(pages[2])
    dates = period(methods)
    n = re.search(r"online surveys of ([\d,]+) New Hampshire registered voters", methods)
    moe = re.search(r"margin of sampling error of \+/-\s*([\d.]+)%", methods)
    text = flat(pages[26])
    polls = []
    for surname, name in (("Brown", "Scott Brown"), ("Sununu", "John E. Sununu")):
        # Find the matching candidate block rather than allowing a preceding
        # hypothetical to swallow a later table.
        candidates = re.findall(r"(If the general election for US Senate.*?for whom would you vote\?)\s*Frequency Percent\s*Pappas\s+\d+\s+(\d+)\s*(Brown|Sununu)\s+\d+\s+(\d+)\s*Unsure\s+\d+\s+(\d+)", text)
        selected = next((r for r in candidates if r[2] == surname), None)
        if not selected or not n or not moe:
            raise ValueError("Saint Anselm hypothetical Senate table missing")
        question, dem, _, rep, unsure = selected
        polls.append(make_poll(source, doc, doc, dates=dates, population="RV", question=question,
            estimates=[estimate("Chris Pappas", "DEM", dem), estimate(name, "REP", rep), estimate("Unsure", None, unsure)],
            sample=int(n[1].replace(",", "")), moe=float(moe[1]), ballot_type="hypothetical", page=27,
            metadata={"release_date_unknown": True, "first_archived_at": doc.retrieved_at}))
    return ParsedBatch(polls=polls, data_as_of=dates[1], warnings=["Pre-primary hypothetical pairings, not confirmed final ballot configuration.",
        "Original release day not established by this PDF: availability conservatively begins at first local archive time."])


def collect_narrative(source, fetcher):
    doc = fetcher.fetch(source["url"])
    page = soup(doc)
    text = flat((page.find("article") or page).get_text(" ", strip=True))
    methods = text[text.find("Methodology"):] if "Methodology" in text else text
    if source.get("methods_scope_pattern"):
        selected = re.search(source["methods_scope_pattern"], text, re.I)
        if not selected:
            raise ValueError("Original release's study-specific methodology paragraph missing")
        methods = selected[0]
    dates = period(methods)
    if source.get("expected_fieldwork") and list(dates) != source["expected_fieldwork"]:
        raise ValueError("Mutable original release now describes another study; update source metadata before publication")
    publication_doc = fetcher.fetch(source["publication_url"]) if source.get("publication_url") else doc
    n = re.search(source["sample_pattern"], methods)
    moe = re.search(source["moe_pattern"], methods)
    if not n or not moe:
        raise ValueError("Primary narrative sample size or uncertainty field changed")
    polls = []
    for config in source["questions"]:
        scope = re.search(config["scope_pattern"], text, re.I)
        if not scope:
            raise ValueError("Original release Senate paragraph missing")
        body = scope[0]
        estimates = []
        for response in config["responses"]:
            match = re.search(response["pattern"], body, re.I)
            if not match:
                raise ValueError(f"Original narrative response {response['name']} missing")
            estimates.append(estimate(response["name"], response.get("party"), match[1]))
        candidates = [(row["name"], row["party"]) for row in estimates if row.get("party")]
        label = config["description"] + ": " + " / ".join(name for name, _party in candidates)
        polls.append(make_poll(source, doc, publication_doc, dates=dates, population=source.get("population", "LV"),
            question=label, estimates=estimates, sample=int(n[1].replace(",", "")), moe=float(moe[1]),
            question_type=config.get("question_type", "vote_choice"), ballot_type=config.get("ballot_type", "release_summary"),
            exact=False, metadata={"original_excerpt": body, "uncertainty_type": source.get("uncertainty_type", "Reported margin of error"),
                "candidate_configuration": [{"name": name, "party": party} for name, party in candidates],
                "unreported_responses_not_imputed": True, "question_warning": "This is a descriptive question label. Exact questionnaire wording is not extracted from the narrative release."}))
    return ParsedBatch(polls=polls, data_as_of=dates[1], warnings=[
        "Primary narrative estimates; exact questionnaire wording is not extracted. Descriptive labels are not verbatim questions.",
        "Narrative-only series and pre-primary hypotheticals stay separate from full-questionnaire polling averages.",
        "Response categories absent from the parsed release are not filled in as invented undecideds."])


def collect(source, fetcher):
    return {"elon": collect_elon, "ut": collect_ut, "asr": collect_asr, "anselm": collect_anselm,
            "narrative": collect_narrative}[source["parser"]](source, fetcher)
