"""Small source-shape fixtures test semantics, not invented election coverage."""
from types import SimpleNamespace

import pytest
from observatory.connectors import (
    calendars,
    north_carolina,
    polling,
    research_polls,
    south_carolina,
    uf_election_lab,
)
from observatory.connectors.iowa import parse_pages as parse_iowa


def doc(tmp_path, text, name="source.csv"):
    path = tmp_path / name
    path.write_text(text)
    return SimpleNamespace(path=str(path), text=text, url="https://example.gov/source", sha256="abc", retrieved_at="2026-10-21T01:00:00+00:00")


class Fetcher:
    def __init__(self, document):
        self.document = document

    def fetch(self, url):
        return self.document


def test_nc_joint_cells_produce_marginals_without_double_counting(tmp_path):
    d = doc(tmp_path, "county_name,abs_request_type,party_cd,gender,race,0\nEXAMPLE,EARLY VOTING,DEM,FEMALE,WHITE,5\nEXAMPLE,CIVILIAN,REP,MALE,WHITE,3\n")
    result = north_carolina.collect({"state": "NC", "url": d.url}, Fetcher(d))
    statewide = [x for x in result.observations if x.geography_type == "state" and x.mode == "all" and x.category is None]
    assert len(statewide) == 1 and statewide[0].value == 8
    assert statewide[0].date == "2026-10-20"  # retrieval day in the user's timezone
    assert statewide[0].published_at is None
    assert {x.metric for x in result.observations} == {"ballots_cast"}


def test_sc_county_totals_exclude_polling_places_and_preserve_reconstructed_dates(tmp_path):
    d = doc(tmp_path, "")
    rows = [["Early Voting Totals: 2022 General Election"], ["County", "44858", "44859", "Total Early Voters"],
            ["Example\u00a0Total", "4", "6", "10"], ["Example Library", "4", "6", "10"], ["Statewide Total", "4", "6", "10"]]
    obs, _ = south_carolina.parse_early_rows(rows, {"state": "SC", "cycle": 2022}, d, historical=True)
    assert len(obs) == 4
    assert [x.value for x in obs if x.geography_type == "county"] == [4, 10]
    assert all(x.time_basis == "reconstructed" and x.published_at is None for x in obs)


def test_poll_bounds_and_suppression_are_not_point_estimates():
    rows = polling.estimates(["Undecided", "No response", "Other"], ["<1%", "*", "0"])
    assert rows[0]["value"] is None and rows[0]["upper_bound"] == 1
    assert rows[1]["value"] is None and rows[1]["suppressed"]
    assert rows[2]["value"] == 0


def test_marist_population_and_question_identity(tmp_path):
    d = doc(tmp_path, "")
    methods = "This Marist Poll survey of 1,176 Ohio registered voters was conducted October 15th through October 18th, 2026. Results for likely voters are statistically significant within ±4.5 percentage points."
    header = "Example Person, the Democrat Other Person, the Republican Another party's candidate Undecided Vol: No response"
    page = f"SNVT26R. Weighted Crosstab\nIn November's election for Senate, are you supporting:\n{header}\nLikely Voters 48% 44% 2% 4% 1%\nParty Identification Democrat 97% 2% <1% 1% <1%"
    result = polling.parse_pages([methods, page], {"state": "OH", "url": d.url, "published_at": "2026-10-20"}, d)
    assert result.polls[0].sample_size is None
    assert result.polls[0].population == "LV"
    assert result.polls[0].margin_of_error == 4.5
    assert result.polls[0].estimates[0]["value"] == 48
    assert result.polls[0].question_type == "vote_choice"


def test_iowa_rejects_mismatched_party_totals(tmp_path):
    d = doc(tmp_path, "")
    page = "Data as of 08:00 on October 20, 2026\nCounty | Page 1\nIowa Statewide\n2026 General Election\nRequested 5 4 1 0 11\n"
    with pytest.raises(ValueError, match="reconcile"):
        parse_iowa([page], {"state": "IA"}, d)


def test_academic_placeholders_and_synthetic_texas_requests_are_excluded(tmp_path):
    d = doc(tmp_path, "")
    row = {"state": "Texas", "state_abbv": "TX", "last_update": "10/20/2026", "voted_all": "10",
           "inperson_all": "8", "accept_all": "2", "request_all": "2", "voted_dem": "0", "voted_rep": "0", "voted_none": "0"}
    result = uf_election_lab.parse_row(row, {"state": "TX"}, d, row)
    assert all(o.category_dimension is None for o in result)
    assert all(o.metric != "ballots_requested" for o in result)
    assert all(o.metadata["academic_fallback"] for o in result)


def test_polling_dates_preserve_cross_month_fieldwork():
    assert research_polls.period("Sept. 29- Oct. 9, 2026") == ("2026-09-29", "2026-10-09")
    assert research_polls.period("August 31 through September 1, 2026") == ("2026-08-31", "2026-09-01")
    with pytest.raises(ValueError, match="fieldwork"):
        research_polls.period("Published October 20, 2026")


def test_narrative_polling_scopes_current_study_and_does_not_invent_question_or_responses(tmp_path):
    document = doc(tmp_path, '<meta property="article:published_time" content="2026-10-16T08:00:00Z">'
        '<article>Current study: poll of 1,000 likely voters September 29-October 9, 2026, '
        'margin of error +/- 3.95 percentage points. Senate: Example Democrat 48%, Example Republican 42%. '
        'Methodology Statement for an older study: poll of 1,200 registered voters August 1-3, 2026, '
        'margin of error +/- 4.1 percentage points.</article>', 'release.html')
    source = {"state": "OH", "url": document.url, "producer": "Example University", "study_prefix": "fixture",
        "population": "LV", "methods_scope_pattern": r"Current study:.*?percentage points\.",
        "sample_pattern": r"poll of ([\d,]+)", "moe_pattern": r"error \+/- ([\d.]+)",
        "questions": [{"scope_pattern": r"Senate:.*?\.", "description": "Descriptive label",
            "responses": [{"name": "Example Democrat", "party": "DEM", "pattern": r"Democrat (\d+)%"},
                          {"name": "Example Republican", "party": "REP", "pattern": r"Republican (\d+)%"}]}]}
    result = research_polls.collect_narrative(source, Fetcher(document))
    poll = result.polls[0]
    assert (poll.field_start, poll.field_end, poll.sample_size, poll.margin_of_error) == ("2026-09-29", "2026-10-09", 1000, 3.95)
    assert poll.published_at == "2026-10-16" and poll.metadata["publication_date_verified"]
    assert poll.ballot_type == "release_summary" and not poll.metadata["question_wording_exact"]
    assert len(poll.estimates) == 2  # missing response mass is not manufactured as undecided
    source["expected_fieldwork"] = ["2026-08-01", "2026-08-03"]
    with pytest.raises(ValueError, match="another study"):
        research_polls.collect_narrative(source, Fetcher(document))
    source.pop("expected_fieldwork")
    source["questions"][0]["responses"][1]["pattern"] = r"Absent candidate (\d+)%"
    with pytest.raises(ValueError, match="response"):
        research_polls.collect_narrative(source, Fetcher(document))


def test_ranked_choice_poll_rounds_share_sample_without_becoming_forecast(tmp_path):
    document = doc(tmp_path, '<p>Updated April 23, 2026. Survey April 16-19, 2026. N=1,946 LV MOE=+/-2.5%. '
        'Q: Rank the following candidates for US Senate in order of preference. '
        'RCV Round 1: Example A (D) 49.1% Example B (R) 42.5% Example C (I) 5.2% Example D (I) 3.2% * '
        'RCV Round 2: Example A (D) 50.2% Example B (R) 43.6% Example C (I) 6.2% * NOTE ON</p>', 'rank.html')
    source = {"state": "AK", "url": document.url, "producer": "Example Research", "study_prefix": "fixture",
              "published_at": "2026-04-23", "publication_evidence": "Updated April 23, 2026"}
    result = research_polls.collect_asr(source, Fetcher(document))
    first, later = result.polls
    assert first.study_id == later.study_id
    assert first.ballot_type == "first_choice" and later.ballot_type == "simulated_rcv_round_2"
    assert (len(first.estimates), len(later.estimates)) == (4, 3)
    assert first.sample_size == later.sample_size == 1946
    assert all("not an election winner probability" in p.metadata["question_note"] for p in result.polls)


def test_unverified_poll_publication_is_not_retrodated(tmp_path):
    document = doc(tmp_path, "<p>Survey fieldwork March 16-18, 2026.</p>", "undated.html")
    published, verified = research_polls.publication(document, {"published_at": "2026-03-19"})
    assert published == document.retrieved_at and not verified


def test_verified_calendars_are_method_specific_and_2018_has_distinct_span():
    refs = calendars.load_calendars()
    assert {row["cycle"] for row in refs} == {2016, 2018, 2020, 2022, 2024, 2026}
    assert calendars.calendar_reference("NC", 2016, "early_in_person")["voting_open_date"] == "2016-10-20"
    assert calendars.calendar_reference("NC", 2018, "early_in_person")["calendar_span_days"] == 18
    assert calendars.calendar_reference("NC", 2026, "early_in_person")["voting_open_date"] == "2026-10-15"
    assert calendars.calendar_reference("NC", 2026, "mail") is None
    assert calendars.calendar_reference("NC", 2026, "all") is None
    assert calendars.calendar_reference("IA", 2026, "early_in_person")["voting_open_date"] == "2026-10-14"
    assert all("opportunity_index" not in row for row in refs)


def test_calendar_reference_archives_confirmed_dates_without_vote_observations(tmp_path):
    reference = calendars.calendar_reference("NC", 2026, "early_in_person")
    document = doc(tmp_path, "<article>2026 general election early voting begins Thursday, Oct. 15, "
        "2026, and ends Saturday, Oct. 31, 2026.</article>", "calendar.html")
    source = {"state": "NC", "cycle": 2026, "url": reference["source_url"]}
    result = calendars.collect(source, Fetcher(document))
    assert result.observations == [] and result.polls == []
    assert result.metadata["reference_data"] == "calendar"
    assert result.metadata["calendar"]["source_sha256"] == document.sha256
    assert result.metadata["calendar"]["retrieved_at"] == document.retrieved_at
    document.text = "<article>2026 early voting from October 16 through October 31.</article>"
    with pytest.raises(ValueError, match="opening/closing"):
        calendars.collect(source, Fetcher(document))
