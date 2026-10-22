"""Reviewed semantic aliases; native wording is preserved in archived records.

NCSBE's counts file and daily-report parser describe the same absentee cast
measure, including early in-person voting. No fuzzy matching or general
cast/received/accepted equivalence is permitted across other sources.
"""
from __future__ import annotations

NC_CAST_DEFINITIONS = {
    'Counts of absentee ballots cast, including in-person early voting',
    'Total absentee and in-person early ballots cast (NCSBE daily report)',
}


def metric_definition(metadata: dict, metric: str, state: str | None = None) -> str:
    if metadata.get('metric_definition'):
        return metadata['metric_definition']
    native = metadata.get('native_definition')
    if state == 'NC' and metric == 'ballots_cast' and native in NC_CAST_DEFINITIONS:
        return 'nc_absentee_cast_including_early_in_person'
    return native or metric
