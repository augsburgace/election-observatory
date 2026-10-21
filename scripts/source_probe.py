#!/usr/bin/env python3
"""Fetch and validate an individual registry source without editing the database."""
import argparse
import json

from observatory.archive import Fetcher
from observatory.connectors import collect
from observatory.registry import sources
from observatory.settings import get_settings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", help="Source registry id")
    parser.add_argument("--offline", action="store_true", help="Replay archived response")
    args = parser.parse_args()
    source = next((s for s in sources() if s["id"] == args.source), None)
    if not source:
        parser.error("Unknown source id")
    fetcher = Fetcher(get_settings(), offline=args.offline)
    try:
        result = collect(source, fetcher)
        print(json.dumps({"source": source["id"], "observations": len(result.observations),
                          "polls": len(result.polls), "data_as_of": result.data_as_of,
                          "warnings": result.warnings,
                          "documents": [{"url": d.url, "sha256": d.sha256, "bytes": d.byte_count} for d in fetcher.documents]}, indent=2))
    finally:
        fetcher.close()


if __name__ == "__main__":
    main()
