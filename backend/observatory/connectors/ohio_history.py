"""Archived original Ohio county surveys with native report chronology.

Comparison columns require a separately archived dated original-authority release
and exact statewide reconciliation. Returned/submitted ballots are not counted votes.
"""
from __future__ import annotations

import base64
import hashlib
from pathlib import Path

from observatory.domain import ParsedBatch
from observatory.geography import county_match

from .common import number, observation, xlsx_rows


def parse(source, document):
    rows = xlsx_rows(Path(document.path).read_bytes())
    if source.get("native_schema") == "2020_native":
        return _parse_2020(source, document, rows)
    if source.get("native_schema") == "2016_detailed":
        if len(rows) != 91 or rows[2][0].strip() != "Statewide":
            raise ValueError("Ohio 2016 survey must contain its native header, blank row, total and 88 counties")
        header = " ".join(rows[0]).lower()
        if not all(label in header for label in ("total ballots cast", "military & overseas ballots requested", "domestic ballots requested")):
            raise ValueError("Ohio 2016 native detailed schema changed")
        native = []
        for row in rows[2:]:
            values = [number(cell) for cell in row[2:10]]
            if len(values) != 8 or values[0] != sum(values[i] for i in (2, 4, 5, 7)) or values[1] != sum(values[i] for i in (3, 4, 6, 7)):
                raise ValueError("Ohio 2016 native military/domestic and method components do not reconcile")
            native.append((row[0], values))
        if [sum(v[i] for _, v in native[1:]) for i in range(8)] != native[0][1]:
            raise ValueError("Ohio 2016 native county components do not reconcile with statewide totals")
        if native[0][1][:2] != source.get("expected_totals"):
            raise ValueError("Ohio 2016 workbook disagrees with the dated original-release totals")
        rows = [["County", "Total Ballots Requested", "Ballots Cast Early In Person", "Ballots Returned and Submitted for Counting"]]
        rows += [["TOTAL" if index == 0 else name, str(v[0]), str(v[4] + v[7]), str(v[1])] for index, (name, v) in enumerate(native)]
    if len(rows) != 90:
        raise ValueError("Ohio survey must contain a header, one total and exactly 88 counties")
    header = " ".join(rows[0]).lower()
    if "early voting" not in header and "early in person" not in header:
        raise ValueError("Ohio early-voting survey schema changed")
    has_returns = "returned and submitted" in header
    count = 3 if has_returns else 2
    column_start = source.get("column_start", 1)
    republished = bool(source.get("republished_historical_columns"))
    if column_start != 1 and not republished:
        raise ValueError("Historical comparison columns require verified dated primary context")
    if republished and (column_start != 5 or source.get("cycle") != 2018 or not source.get("context_verified")):
        raise ValueError("Republished Ohio 2018 columns require the validated original dated release")
    totals = [number(cell) for cell in rows[1][column_start:column_start + count]]
    if republished and totals != source.get("expected_totals"):
        raise ValueError("Republished Ohio columns disagree with all three dated original-release totals")
    if rows[1][0].strip().upper() != "TOTAL":
        raise ValueError("Ohio statewide total row missing")
    counties = [(r[0].strip(), [number(cell) for cell in r[column_start:column_start + count]]) for r in rows[2:]]
    if len({name.lower() for name, _ in counties}) != 88:
        raise ValueError("Duplicate or missing Ohio county")
    if any(county_match("OH", name=name) is None for name, _ in counties):
        raise ValueError("Ohio survey has a county without a validated canonical join")
    if [sum(v[i] for _, v in counties) for i in range(count)] != totals:
        raise ValueError("Ohio counties do not reconcile with the native statewide totals")
    observations = []
    for name, values, kind in [("Ohio", totals, "state"), *[(n, v, "county") for n, v in counties]]:
        requested, in_person = values[:2]
        if requested < in_person or (has_returns and values[2] < in_person):
            raise ValueError("Ohio combined categories cannot yield a nonnegative native remainder")
        measures = [("ballots_cast", "early_in_person", in_person,
                     "Ballots cast early in person in the original Ohio county survey"),
                    ("ballots_requested", "mail", requested - in_person,
                     "Combined early-voting/request total less in-person ballots; native mail absentee requests, not votes")]
        if has_returns:
            measures += [("ballots_cast", "all", values[2], "Ballots returned and submitted for counting, including in-person early ballots; unofficial participation, not counted votes"),
                         ("ballots_returned", "mail", values[2] - in_person,
                          "Returned/submitted total less early-in-person ballots; derived mail returns, not accepted or counted votes")]
        for metric, mode, value, definition in measures:
            for basis in (("reconstructed",) if republished or source.get("retrospective_only") else ("reconstructed", "reported")):
                observations.append(observation(source, document, name=name, value=value, metric=metric,
                    date_=source["data_date"], kind=kind, mode=mode, basis=basis,
                    published_at=max(source["archive_captured_at"], source.get("context_captured_at", "")), metadata={
                        "parser_version": "ohio-survey-archive-1.1", "original_url": source["original_url"],
                        "archive_captured_at": source["archive_captured_at"],
                        "report_date": source["report_date"], "period_end": source.get("period_end"),
                        "report_date_semantics": source["date_semantics"],
                        "native_definition": definition, "reconstruction_basis": "dated original-authority report snapshots, not individual ballot-event dates",
                        "contemporary_publication_verified": source["archive_captured_at"][:4] == str(source["cycle"]),
                        "publication_evidence": "Earliest verified public Internet Archive capture of these workbook bytes; printed report date does not prove earlier availability",
                        "geographic_reconciliation": "All 88 native county totals equal statewide figures for every parsed column",
                        "prior_cycle_columns_withheld": not republished,
                        "republished_historical_columns": republished,
                        "workbook_vintage": source.get("workbook_vintage", source["cycle"]),
                        "native_column_indices": (list(range(2, 10)) if source.get("native_schema") == "2016_detailed" else list(range(column_start, column_start + count))),
                        "native_schema": source.get("native_schema", "2022_combined"),
                        "dating_context_url": source.get("context_url"),
                        "dating_context_sha256": source.get("context_sha256"),
                        "dating_context_original_url": source.get("context_original_url"),
                        "dating_context_capture": source.get("context_captured_at"),
                        "includes_uocava": True, "derived": mode == "mail"}))
    return ParsedBatch(observations=observations, data_as_of=source["data_date"],
        warnings=["Original Ohio unofficial county survey preserved through the Internet Archive. Returns can later be rejected or revised.",
            "Historical report dates and archive availability are distinct; later captures are retrospective evidence.",
            ("2018 endpoint is republished in a 2022 workbook. Its date is established by the original 2018 release and three exact statewide totals; this is retrospective evidence only." if republished else
             "Prior-cycle comparison columns remain in the original workbook and are not assigned invented dates.")],
        metadata={"county_count": 88, "reconciles": True, "report_date": source["report_date"], "archive_url": document.url})


def _parse_2020(source, document, rows):
    """Preserve the native 2020 columns; never infer a missing mail-return count."""
    expected_headers = ["County", "UOCAVA Applications", "Non-UOCAVA Applications"]
    if len(rows) != 90 or rows[0][:3] != expected_headers or rows[1][0] != "TOTAL":
        raise ValueError("Ohio 2020 survey requires its native header, total and 88 counties")
    width = len(rows[0])
    if width not in (3, 4, 6):
        raise ValueError("Ohio 2020 native survey columns changed")
    if width >= 4 and "Early In Person Ballots Cast" not in rows[0][3]:
        raise ValueError("Ohio 2020 native in-person header changed")
    if width == 6 and rows[0][4:] != ["Ballots Returned and Submitted for Counting", "Total Ballots Returned and Submitted for Counting"]:
        raise ValueError("Ohio 2020 native return/combined headers changed")
    native = [(row[0].strip(), [number(cell) for cell in row[1:width]]) for row in rows[1:]]
    counties = native[1:]
    if len({name.lower() for name, _ in counties}) != 88 or any(county_match("OH", name=name) is None for name, _ in counties):
        raise ValueError("Ohio 2020 survey county identities are incomplete or unverified")
    if [sum(v[i] for _, v in counties) for i in range(width - 1)] != native[0][1]:
        raise ValueError("Ohio 2020 native county columns do not reconcile")
    if native[0][1] != source.get("expected_native_totals"):
        raise ValueError("Ohio 2020 native totals disagree with reviewed original evidence")
    observations = []
    for index, (name, values) in enumerate(native):
        if width == 6 and values[2] + values[3] != values[4]:
            raise ValueError("Ohio 2020 mail returns plus in-person ballots do not equal combined participation")
        measures = [("ballots_requested", "all", values[0] + values[1],
                     "Native UOCAVA plus non-UOCAVA absentee applications; request method is not separately established by these columns")]
        if width >= 4:
            measures.append(("ballots_cast", "early_in_person", values[2], "Native early-in-person ballots cast"))
        if width == 6:
            measures.extend([("ballots_returned", "mail", values[3], "Native mail ballots returned and submitted for counting; not accepted or counted candidate votes"),
                             ("ballots_cast", "all", values[4], "Native total ballots returned and submitted for counting, including early-in-person; unofficial participation, not counted votes")])
        for metric, mode, value, definition in measures:
            bases = ("reconstructed",) if source.get("retrospective_only") else ("reconstructed", "reported")
            for basis in bases:
                observations.append(observation(source, document, name="Ohio" if index == 0 else name,
                    value=value, metric=metric, date_=source["data_date"], kind="state" if index == 0 else "county",
                    mode=mode, basis=basis, published_at=max(source["archive_captured_at"], source.get("context_captured_at", "")),
                    metadata={"parser_version": "ohio-survey-archive-1.2", "native_schema": "2020_native",
                        "original_url": source["original_url"], "archive_captured_at": source["archive_captured_at"],
                        "report_date": source["report_date"], "period_end": source.get("period_end"),
                        "report_date_semantics": source["date_semantics"], "native_definition": definition,
                        "reconstruction_basis": "dated original-authority report snapshots, not individual ballot-event dates",
                        "contemporary_publication_verified": not source.get("retrospective_only", True),
                        "publication_evidence": "Availability begins no earlier than both archived workbook and supporting release captures",
                        "geographic_reconciliation": "All 88 county totals equal every native statewide column",
                        "native_column_indices": list(range(1, width)), "includes_uocava": True,
                        "dating_context_url": source.get("context_url"), "dating_context_sha256": source.get("context_sha256"),
                        "dating_context_original_url": source.get("context_original_url"), "dating_context_capture": source.get("context_captured_at"),
                        "party_classification": "Not supplied; Ohio primary participation is not party registration",
                        "requests_method_available": False}))
    return ParsedBatch(observations=observations, data_as_of=source["data_date"], metadata={"county_count": 88, "reconciles": True},
        warnings=["Original Ohio 2020 county survey: requests, mail receipts and in-person ballots remain distinct.",
                  "Applications do not establish voter choice or a mail-versus-in-person request split.",
                  "The observation uses an explicitly dated source period when supplied; otherwise the dated release is not an individual voting-event date."])


def _verify_digest(document, expected):
    if expected:
        digest = base64.b32encode(hashlib.sha1(Path(document.path).read_bytes()).digest()).decode()
        if digest != expected:
            raise ValueError("Ohio archive bytes disagree with the configured CDX capture digest")


def collect(source, fetcher):
    if source.get("context_url"):
        # Both originals become immutable source snapshots in this collection.
        context = fetcher.fetch(source["context_url"])
        _verify_digest(context, source.get("context_digest"))
        if context.sha256 != source["context_sha256"]:
            raise ValueError("Dated Ohio original-release evidence changed; manual review required")
        from .common import soup
        text = " ".join(soup(context).stripped_strings)
        if not all(token in text for token in source["context_required_tokens"]):
            raise ValueError("Original Ohio release no longer establishes the specified date and totals")
        source = {**source, "context_verified": True}
    document = fetcher.fetch(source["url"])
    _verify_digest(document, source.get("archive_digest"))
    return parse(source, document)
