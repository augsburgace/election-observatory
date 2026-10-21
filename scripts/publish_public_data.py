#!/usr/bin/env python3
"""Build the public aggregate data edition from an existing evidence snapshot."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from observatory.public_publish import publish_public_data, readonly_database
from observatory.settings import Settings, get_settings

from scripts.publication_runtime import PublicationRuntime


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--as-of")
    parser.add_argument("--revision", type=int)
    parser.add_argument("--state", action="append", dest="states")
    parser.add_argument("--skip-forecasts", action="store_true")
    parser.add_argument("--skip-reports", action="store_true")
    parser.add_argument("--skip-results", action="store_true")
    parser.add_argument("--skip-precincts", action="store_true")
    parser.add_argument("--replace", action="store_true")
    parser.add_argument("--max-logical-files", type=int, default=100_000,
                        help="Logical evidence-object budget before the hosting packer combines small files")
    args = parser.parse_args()
    settings = Settings(args.data_dir.expanduser()) if args.data_dir else get_settings()
    database = readonly_database(settings)
    try:
        with PublicationRuntime(lambda value: print(json.dumps(value), flush=True)) as runtime:
            manifest = publish_public_data(database, args.output, as_of=args.as_of, revision=args.revision,
                states=args.states, include_forecasts=not args.skip_forecasts, include_reports=not args.skip_reports,
                include_results=not args.skip_results, include_precincts=not args.skip_precincts,
                replace=args.replace, max_files=args.max_logical_files, progress=runtime.progress)
        print(json.dumps({"publication_runtime": runtime.summary()}), flush=True)
        print(json.dumps({"output": str(args.output.resolve()), "revision": manifest["dataset_revision"],
            "requests": len(manifest["requests"]), "footprint": manifest["footprint"]}), flush=True)
    finally:
        database.engine.dispose()


if __name__ == "__main__":
    main()
