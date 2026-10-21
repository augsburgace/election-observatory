#!/usr/bin/env python3
"""Evaluate extra EV features against identical prior-only Senate holdouts.

This reads local archived evidence only. Supply --backtest-input to reuse a
pinned full forecast/stage-audit JSON instead of rebuilding geographic cases.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from observatory.db import Database
from observatory.ev_feature_validation import build_feature_validation
from observatory.settings import get_settings, local_today


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--revision', type=int, help='Pinned dataset revision; defaults to input revision or latest')
    parser.add_argument('--as-of', help='Research cutoff, YYYY-MM-DD; defaults to input cutoff or today')
    parser.add_argument('--backtest-input', type=Path, help='Existing forecast response or stage audit JSON')
    parser.add_argument('--output', type=Path, required=True, help='Complete evidence, fits, cases and exclusions JSON')
    args = parser.parse_args()
    audit = None
    if args.backtest_input:
        document = json.loads(args.backtest_input.read_text())
        audit = document.get('backtesting', document)
    revision = args.revision if args.revision is not None else (audit or {}).get('manifest', {}).get('dataset_revision')
    cutoff = args.as_of or (audit or {}).get('manifest', {}).get('as_of') or local_today()
    database = Database(get_settings())
    result = build_feature_validation(database, revision, cutoff, backtesting=audit)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False))
    print(json.dumps({'output': str(args.output.resolve()), 'revision': result['revision'], 'as_of': result['as_of'],
        'features': [{key: row[key] for key in ('id', 'available_cases', 'available_state_cycles', 'available_cycles')}
                     for row in result['feature_inventory']],
        'headline_experiments': [{key: row[key] for key in ('experiment_id', 'eligible_cases', 'eligible_state_cycles', 'paired_metrics', 'promotion')}
                                for row in result['headline_experiments']]}, indent=2))


if __name__ == '__main__':
    main()
