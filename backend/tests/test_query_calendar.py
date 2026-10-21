"""Historical queries and calendar alignment include presidential and off years."""
from datetime import date, timedelta

import pytest
from observatory.domain import ResearchQuery
from observatory.registry import ELECTION_DATES
from pydantic import ValidationError


def test_2016_is_a_supported_investigation_and_baseline():
    current = ResearchQuery(state="nc", cycle=2016, baseline=2012, as_of="2016-10-20")
    assert current.state == "NC"
    assert current.cycle == 2016
    baseline = ResearchQuery(state="NC", cycle=2026, baseline=2016)
    assert baseline.baseline == 2016
    assert ResearchQuery.model_validate_json(current.model_dump_json()) == current


@pytest.mark.parametrize(("year", "expected"), [
    (1976, "1976-11-02"),
    (1977, "1977-11-08"),
    (2016, "2016-11-08"),
    (2017, "2017-11-07"),
    (2018, "2018-11-06"),
    (2019, "2019-11-05"),
    (2020, "2020-11-03"),
    (2021, "2021-11-02"),
    (2022, "2022-11-08"),
    (2023, "2023-11-07"),
    (2024, "2024-11-05"),
    (2025, "2025-11-04"),
    (2026, "2026-11-03"),
])
def test_registry_general_election_dates_include_off_years(year, expected):
    assert ELECTION_DATES[year] == expected
    assert ResearchQuery(state="VA", cycle=year).cycle == year


def test_every_supported_year_uses_tuesday_after_first_november_monday():
    for year in range(1976, 2101):
        first = date(year, 11, 1)
        monday = first + timedelta(days=(7 - first.weekday()) % 7)
        expected = monday + timedelta(days=1)
        assert ELECTION_DATES[year] == expected.isoformat()
        assert expected.weekday() == 1 and 2 <= expected.day <= 8


def test_general_date_registry_does_not_replace_actual_special_or_runoff_dates():
    # This registry is the annual general-election alignment anchor. Source
    # election records retain their own stage/date, including January runoffs.
    assert ELECTION_DATES[2021] != "2021-01-05"
    assert ELECTION_DATES[2022] != "2022-12-06"


@pytest.mark.parametrize("field", ["cycle", "baseline"])
@pytest.mark.parametrize("year", [1975, 2101])
def test_queries_reject_years_outside_the_supported_calendar(field, year):
    with pytest.raises(ValidationError):
        ResearchQuery(**{field: year})
