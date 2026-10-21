#!/usr/bin/env python3
"""Download one verified native precinct bundle, retaining original evidence."""
import argparse
import json

from observatory.db import Database
from observatory.historical_comparisons import archive_boundary_review
from observatory.precincts import load_precinct_dataset, precinct_catalog, precinct_map
from observatory.settings import get_settings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", help="For example vest_2020_TX or ncsbe_precinct_2024")
    parser.add_argument("--state", help="Two-letter state")
    parser.add_argument("--year", type=int)
    parser.add_argument("--map", action="store_true", help="Print a viewport-bounded map JSON after download")
    parser.add_argument("--bbox", help="west,south,east,north")
    parser.add_argument("--lod", choices=["overview", "detail", "full"], default="overview")
    parser.add_argument("--office", default="PRESIDENT")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--review-counties", action="store_true")
    arguments = parser.parse_args()
    database = Database(get_settings())
    if arguments.review_counties:
        result = archive_boundary_review(database, offline=arguments.offline)
    elif arguments.dataset:
        result = load_precinct_dataset(database, arguments.dataset, offline=arguments.offline,
            force=arguments.force, progress=lambda value: print(json.dumps(value), flush=True))
    else:
        result = precinct_catalog(database, state=arguments.state, year=arguments.year)
    if arguments.map:
        if not arguments.state or not arguments.year:
            parser.error("--map requires --state and --year")
        result = precinct_map(database, state=arguments.state, year=arguments.year, office=arguments.office,
            dataset_id=arguments.dataset, bbox=arguments.bbox, lod=arguments.lod)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
