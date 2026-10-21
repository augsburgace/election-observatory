#!/usr/bin/env python3
"""Acquire/validate Ohio originals in isolated local storage, without publishing a DB.

This uses the application's bounded fetcher and exact same source connector. The
output contains only aggregate findings and source evidence, never voter records.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from observatory.archive import Fetcher
from observatory.connectors import ohio_history, uf_history
from observatory.settings import Settings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("config/ohio_historical_sources.json"))
    parser.add_argument("--source-id", action="append", default=[])
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--work-dir", type=Path, default=Path(".local/ev-gap-source/audit"))
    args = parser.parse_args()
    sources = json.loads(args.config.read_text())["sources"]
    if args.source_id:
        unknown = set(args.source_id) - {source["id"] for source in sources}
        if unknown:
            parser.error(f"Unknown source IDs: {sorted(unknown)}")
        sources = [source for source in sources if source["id"] in args.source_id]
    settings = Settings(data_dir=args.work_dir.resolve())
    fetcher = Fetcher(settings, offline=args.offline)
    results = []
    try:
        for source in sources:
            start = len(fetcher.documents)
            try:
                adapter = {"ohio_history": ohio_history, "uf_history": uf_history}[source["connector"]]
                batch = adapter.collect(source, fetcher)
                entry = {"source_id": source["id"], "status": "validated", "date": batch.data_as_of,
                         "observations": len(batch.observations), "metadata": batch.metadata,
                         "warnings": batch.warnings, "state_values": [row.model_dump() for row in batch.observations
                             if row.geography_type == "state" and row.time_basis == "reconstructed"]}
            except Exception as exc:
                entry = {"source_id": source["id"], "status": "failed", "error": str(exc)}
            entry["documents"] = [{key: getattr(doc, key) for key in ("url", "sha256", "byte_count", "retrieved_at")}
                                  for doc in fetcher.documents[start:]]
            results.append(entry)
            (args.work_dir / "proof.json").write_text(json.dumps(results, indent=2) + "\n")
            print(json.dumps({key: entry[key] for key in ("source_id", "status")}), flush=True)
    finally:
        fetcher.close()
    if any(row["status"] != "validated" for row in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
