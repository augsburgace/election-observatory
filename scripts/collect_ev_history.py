#!/usr/bin/env python3
"""Inspect or explicitly collect the reviewed historical EV source program.

The default is an inventory-only dry run. Collection uses the ordinary bounded
collector and immutable archive; no direct database inserts or source bypasses.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from observatory.collector import collect_sources  # noqa: E402
from observatory.db import Database  # noqa: E402
from observatory.registry import sources  # noqa: E402
from observatory.settings import get_settings  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collect", action="store_true", help="Archive and validate source evidence; default only lists the source program")
    parser.add_argument("--offline", action="store_true", help="Reparse archived responses without a network request")
    parser.add_argument("--states", nargs="*", default=[])
    parser.add_argument("--cycles", nargs="*", type=int, default=[])
    parser.add_argument("--source-ids", nargs="*", default=[])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    inventory = [row for row in sources() if row.get("historical") and
                 (row.get("connector") in {"electproject_history", "iowa_history", "nc_reports", "sc_early", "oh_history", "ohio_history", "nc_record_history"}) and
                 (not args.states or row.get("state") in {state.upper() for state in args.states}) and
                 (not args.cycles or row.get("cycle") in args.cycles) and
                 (not args.source_ids or row["id"] in args.source_ids)]
    if not inventory:
        raise SystemExit("No reviewed historical EV sources match. Ensure the source program is registered.")
    report = {"mode": "collect" if args.collect else "inventory_only", "source_count": len(inventory),
              "sources": [{key: row.get(key) for key in ("id", "state", "cycle", "name", "url", "connector", "tier", "notes")} for row in inventory]}
    if args.collect:
        database = Database(get_settings())
        report["collection"] = collect_sources(database, source_ids=[row["id"] for row in inventory],
                                                 include_historical=True, offline=args.offline)
    value = json.dumps(report, indent=2, default=str)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(value + "\n")
    print(value)


if __name__ == "__main__":
    main()
