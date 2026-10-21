#!/usr/bin/env python3
"""Run the deterministic local Senate EV/turnout audit without collecting data."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from observatory.db import Database
from observatory.ev_forecast import early_vote_forecasts
from observatory.settings import get_settings, local_today


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--revision', type=int, help='Pin a retained dataset revision; default latest')
    parser.add_argument('--as-of', default=local_today(), help='Research cutoff (YYYY-MM-DD)')
    parser.add_argument('--state', default='NC', help='Selected state for the full research response')
    parser.add_argument('--output', type=Path, required=True, help='Write the complete source-backed JSON response')
    args = parser.parse_args()
    database = Database(get_settings())
    result = early_vote_forecasts(database, state=args.state, revision=args.revision, as_of=args.as_of)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False))
    audit = result['backtesting']
    print(json.dumps({'output': str(args.output.resolve()), 'revision': result['revision'],
        'as_of': result['as_of'], 'ev_cases': len(audit['cases']), 'independent_ev_contests': audit['independent_contests'],
        'independent_ev_cycles': audit['independent_cycles'], 'metrics': audit['metrics'],
        'turnout_metrics': audit['turnout']['metrics'], 'trained_ev_holdouts': audit['trained_ev_holdout_cases'],
        'probabilities_published': audit['probabilities_published']}, indent=2))


if __name__ == '__main__':
    main()
