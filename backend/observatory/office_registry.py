"""Dated 2026 office universe, independent of ballot/candidate verification."""
from .registry import ELECTION_DATES, all_states, races

OFFICES = ('US SENATE', 'US HOUSE', 'GOVERNOR')
GOVERNOR_STATES = set('AL AK AZ AR CA CO CT FL GA HI ID IL IA KS ME MD MA MI MN NE NV NH NM NY OH OK OR PA RI SC SD TN TX VT WI WY'.split())
HOUSE_SEATS = dict(zip(
    'AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY'.split(),
    [7,1,9,4,52,8,5,1,28,14,2,2,17,9,4,4,6,6,2,8,9,13,8,4,8,2,3,4,2,12,3,26,14,1,15,5,6,17,2,7,1,9,38,4,1,11,10,2,8,1], strict=True))
SOURCES = [
    {'title': 'Census 2020 apportionment: 435 seats among 50 states', 'url': 'https://www.census.gov/data/tables/time-series/dec/apportionment-data-text.html'},
    {'title': 'National Governors Association election calendar (includes territories)', 'url': 'https://www.nga.org/governors/elections/'},
    {'title': 'FEC election dates and state ballot authority', 'url': 'https://www.fec.gov/introduction-campaign-finance/election-results-and-voting-information/'},
    {'title': 'Alaska general-election ranked-choice rules', 'url': 'https://www.elections.alaska.gov/election-information/'},
    {'title': 'Maine office-specific ranked-choice rules', 'url': 'https://www3.maine.gov/sos/elections-voting/ranked-choice-voting-frequently-asked-questions'},
    {'title': 'Georgia majority/runoff rules', 'url': 'https://georgia.gov/vote-runoff-elections'},
    {'title': 'Louisiana 2026 House open primary and potential December 12 runoff', 'url': 'https://www.sos.la.gov/elections-voting/election-dates'},
]


def election_system(state, office):
    if state == 'AK' or (state == 'ME' and office in {'US HOUSE', 'US SENATE'}):
        return 'ranked_choice'
    if state == 'LA' and office == 'US HOUSE':
        return 'open_primary_runoff'
    if state == 'GA':
        return 'majority_runoff'
    return 'plurality'


def race_catalog(office='US SENATE'):
    """Regular November seats; special-election inventories remain explicit."""
    if office not in OFFICES:
        raise ValueError('Choose US SENATE, US HOUSE or GOVERNOR')
    if office == 'US SENATE':
        return [{**r, 'office': office} for r in races()]
    output = []
    for state in all_states():
        code = state['code']
        if office == 'GOVERNOR' and code not in GOVERNOR_STATES:
            continue
        districts = range(1, HOUSE_SEATS[code]+1) if office == 'US HOUSE' else [None]
        for district in districts:
            at_large = office == 'US HOUSE' and HOUSE_SEATS[code] == 1
            label = ('At-large' if at_large else f'District {district}') if district is not None else 'Governor'
            output.append({'id': f'2026-{code}-' + (f'HOUSE-{district:02}' if district else 'GOV'),
                'state': code, 'state_name': state['name'], 'office': office, 'cycle': 2026,
                'name': f"{state['name']} · {label}", 'district': district, 'at_large': at_large,
                'election_date': ELECTION_DATES[2026], 'election_system': election_system(code, office),
                'possible_runoff_date': '2026-12-12' if code == 'LA' and office == 'US HOUSE' else None,
                'watchlist': state['watchlist'], 'special': False, 'candidates': [],
                'candidate_verification': 'Current official ballot roster not yet verified; historical candidates are not current nominees.'})
    return output
