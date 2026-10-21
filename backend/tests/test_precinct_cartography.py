from __future__ import annotations

import csv
import hashlib
import io
import json
import zipfile

import pytest
import shapefile
from observatory.atlas.ingest import _publish, stable_id
from observatory.atlas.models import ensure_schema
from observatory.db import Database
from observatory.domain import FetchedDocument
from observatory.historical_comparisons import boundary_eligibility, compare_results
from observatory.precincts import (
    _geometry_file,
    _nc_native_index,
    _numeric_padding,
    _shape_records,
    _vest_bundle,
    parse_bbox,
    precinct_catalog,
    precinct_map,
    precinct_sources,
)
from observatory.settings import PROJECT_ROOT, Settings
from pyproj import CRS


@pytest.fixture
def database(tmp_path):
    value = Database(Settings(tmp_path, project_root=PROJECT_ROOT))
    ensure_schema(value)
    return value


def archive_shape(tmp_path, records):
    shp, shx, dbf = io.BytesIO(), io.BytesIO(), io.BytesIO()
    writer = shapefile.Writer(shp=shp, shx=shx, dbf=dbf, shapeType=shapefile.POLYGON)
    writer.field("NAME", "C")
    writer.field("G20PREDBID", "N", 12, 0)
    writer.field("G20PRERTRU", "N", 12, 0)
    writer.field("G20PRELJOR", "N", 12, 0)
    for i, values in enumerate(records):
        x = -70 + i
        writer.poly([[[x, 44], [x, 45], [x + 0.1, 45], [x + 0.1, 44], [x, 44]]])
        writer.record(*values)
    writer.close()
    path = tmp_path / "fixture.zip"
    with zipfile.ZipFile(path, "w") as output:
        for suffix, data in (("shp", shp), ("shx", shx), ("dbf", dbf)):
            output.writestr(f"fixture.{suffix}", data.getvalue())
        output.writestr("fixture.prj", CRS.from_epsg(4326).to_wkt())
    return path


def doc(path):
    return FetchedDocument(url="https://example.org/precincts.zip", path=str(path),
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(), content_type="application/zip",
        retrieved_at="2026-10-21T12:00:00Z", byte_count=path.stat().st_size)


DOCUMENTATION = """Maine
-----
Boundaries and vote columns are paired by the original producer.
G20PREDBID - Joseph Biden (Democratic Party)
G20PRERTRU - Donald Trump (Republican Party)
G20PRELJOR - Jo Jorgensen (Libertarian Party)
"""


def test_all_50_original_producer_files_are_verified_public_inventory(database):
    sources = [row for row in precinct_sources() if row["provider"] == "vest"]
    assert len(sources) == 50
    assert len({row["state"] for row in sources}) == 50
    assert all(row["file_id"] and row["publisher_checksum"] and not row["restricted"] for row in sources)
    catalog = precinct_catalog(database, state="TX")
    assert catalog["datasets"][0]["status"] == "not_loaded"
    assert not catalog["datasets"][0]["loaded"]


def test_pairing_is_with_the_archived_record_not_a_guessed_vtd(tmp_path):
    path = archive_shape(tmp_path, [("A", 100, 80, 20), ("B", 0, 25, 5)])
    document = doc(path)
    source = next(row for row in precinct_sources() if row["id"] == "vest_2020_ME")
    features, rows, metadata = _vest_bundle(source, document, DOCUMENTATION)
    assert len(features) == 2
    assert all(f["properties"]["join_status"] == "publisher_paired_record" for f in features)
    assert document.sha256[:12] in features[0]["id"]
    assert {r["geography_id"] for r in rows} == {f["id"] for f in features}
    assert sum(r["votes"] for r in rows) == 230
    assert metadata["offices"] == ["PRESIDENT"]
    assert any("allocated" in warning for warning in metadata["warnings"])


def test_true_zero_and_missing_remain_distinct_in_paired_returns(tmp_path):
    path = archive_shape(tmp_path, [("A", 0, None, 5)])
    source = next(row for row in precinct_sources() if row["id"] == "vest_2020_ME")
    _, rows, _ = _vest_bundle(source, doc(path), DOCUMENTATION)
    by_party = {r["party"]: r for r in rows}
    assert by_party["DEM"]["votes"] == 0
    assert by_party["REP"]["votes"] is None
    assert by_party["REP"]["partial_suppression"]


def test_repeated_judicial_office_codes_preserve_distinct_option_sets():
    from observatory.precincts import _vest_fields
    fields = _vest_fields("""G20SSCRAAA - Judge A (Republican Party)
G20SSCDBBB - Judge B (Democratic Party)

G20SSCRCCC - Judge C (Republican Party)
G20SSCDDDD - Judge D (Democratic Party)

G20PREDBID - Joseph Biden (Democratic Party)
G20PRERTRU - Donald Trump (Republican Party)

C20PREDBID - Joseph Biden (Democratic Party)
C20PRERTRU - Donald Trump (Republican Party)
""")
    assert fields["G20SSCRAAA"]["documented_option_set"] == fields["G20SSCDBBB"]["documented_option_set"]
    assert fields["G20SSCRAAA"]["documented_option_set"] != fields["G20SSCRCCC"]["documented_option_set"]
    assert fields["C20PREDBID"]["stage"] == "RECOUNT"
    assert fields["G20PREDBID"]["stage"] == "GEN"


def test_missing_crs_is_a_failure_not_assumed_wgs84(tmp_path):
    path = archive_shape(tmp_path, [("A", 10, 20, 0)])
    with zipfile.ZipFile(path) as archive:
        data = {n: archive.read(n) for n in archive.namelist() if not n.endswith(".prj")}
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in data.items():
            archive.writestr(name, content)
    with pytest.raises(KeyError):
        list(_shape_records(str(path)))


def test_cached_geometry_hash_is_verified(tmp_path):
    path = tmp_path / "test.geojson"
    path.write_text('{"type":"FeatureCollection","features":[]}')
    with pytest.raises(ValueError, match="checksum"):
        _geometry_file(str(path), "incorrect")


@pytest.mark.parametrize("value", ["0,0,nan,1", "-181,0,1,1", "0,20,1,10", "1,2,3", "0,0,inf,1"])
def test_invalid_viewports_fail(value):
    with pytest.raises(ValueError):
        parse_bbox(value)


def test_dateline_viewport_is_retained():
    assert parse_bbox("170,40,-170,70") == (170, 40, -170, 70)


def test_unloaded_and_pinned_precinct_maps_are_explicit(database):
    value = precinct_map(database, state="TX", year=2020)
    assert value["features"] == []
    assert value["availability"]["status"] == "not_loaded"
    with pytest.raises(ValueError, match="does not belong"):
        precinct_map(database, state="TX", year=2020, dataset_id="vest_2020_NC")


def test_native_zero_padding_never_changes_punctuation_or_letters():
    assert _numeric_padding("0003") == "3"
    assert _numeric_padding("001A") == "001A"
    assert _numeric_padding("01-01") == "01-01"


def test_nc_native_index_preserves_ambiguous_codes_and_administrative_rows(tmp_path):
    content = io.StringIO()
    writer = csv.DictWriter(content, fieldnames=["jurisdiction_fips", "county_fips", "county_name", "precinct"])
    writer.writeheader()
    writer.writerows([{"jurisdiction_fips": "37027", "county_fips": "37027", "county_name": "CALDWELL", "precinct": p} for p in ["1", "01", "ABSENTEE"]])
    path = tmp_path / "nc.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("nc.csv", content.getvalue())
    index = _nc_native_index(str(path), 2024)
    assert len(index[("county:37027", "1")]) == 2
    assert len(index[("county:37027", "ABSENTEE")]) == 1
    assert f"precinct:NC:2024:{stable_id('37027', '1')}" in index[("county:37027", "1")]


@pytest.mark.parametrize(("state", "identifier", "level", "reason"), [
    ("CT", "county:09001", "county", "county_equivalents_changed"),
    ("AK", "county:02020", "county", "native_reporting_areas_not_counties"),
    ("VA", "county:51515", "county", "changed_or_noncanonical_identifier"),
    ("SD", "county:46113", "county", "changed_or_noncanonical_identifier"),
    ("TX", "precinct:TX:1", "precinct", "reviewed_crosswalk_required"),
])
def test_changed_or_native_geographies_are_not_allocated(state, identifier, level, reason):
    value = boundary_eligibility(state, identifier, level, 2024, 2020)
    assert not value["eligible"]
    assert value["reason"] == reason


def test_material_county_review_has_an_explicit_window_and_limitations():
    value = boundary_eligibility("TX", "county:48001", "county", 2024, 2020)
    assert value["eligible"]
    assert "Minor" in value["limitation"]
    assert not boundary_eligibility("TX", "county:48001", "county", 2024, 2016)["eligible"]
    assert not boundary_eligibility("TX", "county:48001", "county", 2024, 2020, review_available=False)["eligible"]


def test_same_state_can_compare_when_county_review_is_unavailable():
    assert boundary_eligibility("TX", "state:TX", "state", 2024, 2020, review_available=False)["eligible"]


def test_comparison_uses_matched_denominator_and_signed_r_minus_d(database, tmp_path):
    path = archive_shape(tmp_path, [("A", 100, 80, 20)])
    source = {"id": "fixture", "title": "Fixture", "state": "TX", "tier": 3}
    rows = []
    for year, dem, rep in [(2020, 100, 80), (2024, 90, 110)]:
        contest = f"contest:{year}"
        for party, votes in [("DEM", dem), ("REP", rep)]:
            rows.append({"state": "TX", "year": year, "office": "PRESIDENT", "contest_id": contest,
                "contest_name": "President · STATEWIDE", "district": "STATEWIDE", "stage": "GEN", "special": False,
                "date": f"{year}-11-05", "magnitude": 1, "kind": "candidate", "candidate": party, "party": party,
                "option_id": f"option:{year}:{party}", "geography_id": "state:TX", "geography_level": "state",
                "geography_name": "Texas", "votes": votes, "mode": "TOTAL", "round": "reported",
                "source_modes": ["TOTAL"], "parties": [party], "partial_suppression": False, "writein": False})
    _publish(database, source, doc(path), rows, {})
    value = compare_results(database, state="TX", year=2024, baseline=2020, geography_level="state")
    assert value["eligible"]
    assert value["coverage"]["matched_current_votes"] == 200
    assert value["coverage"]["matched_baseline_votes"] == 180
    assert value["rows"][0]["change_pp"] == pytest.approx(21.1111111111)
    assert value["rows"][0]["vote_change"] == 20


def test_boundary_review_must_be_available_at_the_pinned_revision(database, tmp_path):
    from observatory.historical_comparisons import _review
    reference = tmp_path / "reference.txt"
    reference.write_text("Original Census reference")
    path = database.settings.data_dir / "geometry" / "county-boundary-review.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"revision": 5, "sources": [{"archive_path": str(reference),
        "sha256": hashlib.sha256(reference.read_bytes()).hexdigest()}]}))
    assert _review(database, 4) is None
    assert _review(database, 5) is not None
    reference.write_text("changed")
    assert _review(database, 5) is None


def test_structural_contest_correction_is_append_only_and_revision_scoped(database, tmp_path):
    from observatory.atlas.models import AtlasResultValidation
    from observatory.atlas.result_validation import invalidated_result_contests
    from observatory.atlas.store import result_query
    from observatory.db import Revision
    path = archive_shape(tmp_path, [("A", 100, 80, 20)])
    source = next(row for row in precinct_sources() if row["id"] == "vest_2020_ME")
    _, rows, metadata = _vest_bundle(source, doc(path), DOCUMENTATION)
    published = _publish(database, {**source, "tier": 3}, doc(path), rows, metadata)
    contest_id = rows[0]["contest_id"]
    with database.session() as session, session.begin():
        decision = Revision(reason="Correct grouped contest", source_id=source["id"])
        session.add(decision)
        session.flush()
        current = decision.id
        session.add(AtlasResultValidation(dataset_id=source["id"], revision=current,
            invalidated_contest_ids=[contest_id], reason="A mixed option set is not one contest", payload={}))
    assert contest_id not in invalidated_result_contests(database, published["revision"])
    assert contest_id in invalidated_result_contests(database, current)
    earlier = result_query(database, state="ME", year=2020, baseline=None,
        geography_level="precinct", revision=published["revision"])
    assert earlier["geographies"]
    assert any("Present-day validation" in value for value in earlier["warnings"])
    latest = result_query(database, state="ME", year=2020, baseline=None, geography_level="precinct")
    assert latest["geographies"] == []
    _publish(database, {"id": "independent_correct_producer", "title": "Independent compatible producer", "state": "ME", "tier": 1},
        doc(path), rows, {})
    latest = result_query(database, state="ME", year=2020, baseline=None, geography_level="precinct")
    assert latest["geographies"][0]["total_votes"] == 200
    assert contest_id not in invalidated_result_contests(database, database.latest_revision())
    assert all(ref['source_id'] == 'independent_correct_producer' for ref in latest['geographies'][0]['source_refs'])
