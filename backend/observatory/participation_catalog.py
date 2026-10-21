"""Current-cycle extension: explicit evidence collection, never inferred counts."""
from sqlalchemy import select

from .db import SourceState
from .registry import sources


def participation_datasets(database, state=None):
    with database.session() as session:
        states = {r.id: r for r in session.scalars(select(SourceState))}
    result = []
    for source in sources():
        if source.get('connector') != 'uf_tracker' or (state and source['state'] != state.upper()):
            continue
        stored = states.get(source['id'])
        result.append({**source, 'id': source['id'], 'title': source['name'], 'producer': 'University of Florida Election Lab / Michael McDonald',
            'years': [2026], 'states': [source['state']], 'offices': [], 'geography_levels': ['state', 'county'],
            'provider': 'participation', 'on_demand': True, 'status': stored.status if stored else 'availability_unverified',
            'record_count': None, 'loaded_states': [source['state']] if stored and stored.last_changed else [],
            'checked_at': stored.last_checked if stored else None, 'error': stored.error if stored else None,
            'license': 'CC BY-NC-ND 4.0; personal noncommercial research',
            'warnings': ['Attributed academic bridge. Upstream authority and state-specific inferences travel with each observation.',
                'Office-independent election participation; party registration does not identify candidate votes.',
                'County exports are used only when reconciled with the dated statewide report.'] + (stored.warnings if stored else [])})
    return result
