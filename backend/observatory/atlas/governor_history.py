"""Documented adapter for Cha, Kuriwaki and Snyder's governor compilation.

The producer supplies only deciding rounds. Runoffs are retained as separate
stages with unknown dates, never assigned the ordinary November voting day.
Published totals exclude candidates with fewer than ten votes, blank/miscellaneous
party records and invalid votes. They are candidate votes, never turnout.
"""
def governor_rows(rows, *, house=False):
    parties = {'D': 'DEM', 'R': 'REP', 'I': 'IND', 'Lbt': 'LIB', 'Grn': 'GRN'}
    for row in rows:
        if row.get('office') != ('H' if house else 'G') or row.get('type') not in {'G', 'S'}:
            continue
        runoff = row.get('runoff') in {'1', '1.0'}
        district = str(int(float(row['dist']))) if house else 'STATEWIDE'
        if house and (row['state'] in {'AK', 'DE', 'ND', 'SD', 'VT', 'WY'} or (row['state'] == 'MT' and int(float(row['year'])) <= 2020)):
            district = 'STATEWIDE'
        stage = ('GEN SPECIAL RUNOFF' if runoff else 'GEN SPECIAL') if row['type'] == 'S' else ('GEN RUNOFF' if runoff else 'GEN')
        yield {'state_po': row['state'], 'year': row['year'], 'office': 'US HOUSE' if house else 'GOVERNOR', 'district': district,
            'candidate': row['name_snyder'], 'candidatevotes': row['candidatevotes'],
            'party': parties.get(row['party'], row.get('party_formal') or row['party']),
            'special': row['type'] == 'S', 'stage': stage, 'mode': 'TOTAL'}
