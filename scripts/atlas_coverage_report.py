"""Rebuild installed nationwide coverage from actual evidence, without fetching."""
from collections import Counter

from observatory.atlas import dataset_catalog, state_catalog
from observatory.atlas.models import Contest, ContextEstimate, ElectionResult
from observatory.db import Database
from observatory.domain import utc_now
from observatory.settings import PROJECT_ROOT, get_settings
from sqlalchemy import func, select


def main():
    db = Database(get_settings())
    catalog = state_catalog(db)
    datasets = dataset_catalog(db)['datasets']
    with db.session() as session:
        result_count = session.scalar(select(func.count()).select_from(ElectionResult))
        contest_count = session.scalar(select(func.count()).select_from(Contest))
        context_count = session.scalar(select(func.count()).select_from(ContextEstimate))
        counts = Counter({state: count for state, count in session.execute(select(ElectionResult.state, func.count()).group_by(ElectionResult.state))})
    lines = ['# Installed nationwide atlas coverage', '', f"Generated {utc_now()}. Revision **{catalog['revision']}**. Counts describe collected records, including revisions; they are not turnout totals.", '',
        f"**50 states**; {result_count:,} result versions; {contest_count:,} distinct contest records; {context_count:,} context-estimate versions.", '',
        'Historical candidate returns are separate from current voting participation. Office availability below refers to collected historical contests. Deeper original-producer archives load by state and retain their source definitions, reporting units, suppression and electoral rounds.', '',
        '| State | Years collected | Offices collected | Geographic levels | Result versions |', '|---|---|---|---|---:|']
    for state in catalog['states']:
        years = state['years']
        lines.append(f"| {state['name']} | {min(years)}–{max(years)}" + f" ({len(years)} election years) | {', '.join(state['offices'])} | {', '.join(state['geography_levels'])} | {counts[state['code']]:,} |")
    lines += ['', '## Verified source inventory and installed depth', '', '| Dataset | Producer / layer | Years | Status | Records |', '|---|---|---|---|---:|']
    for source in datasets:
        if source.get('on_demand') and source['status'] == 'available':
            continue
        years = source['years']
        lines.append(f"| [{source['title']}]({source['url']}) | {source['producer']} / {source['tier']} | {min(years)}–{max(years)} | {source['status']} | {source['record_count']:,} |")
    lines += ['', '## Interpretation and remaining coverage', '',
        '- All 50 states have historical statewide presidential and Senate records. Not every state holds each office in each year.',
        '- Alaska native election districts are retained. County-equivalent returns are not manufactured from those districts.',
        '- County presidential history uses the archived MIT 2000–2016 release and a labeled secondary 2020/2024 bridge where original-producer data has not been loaded. Guestbook-gated Harvard files are not bypassed.',
        '- County sums, statewide certified compilations, and precinct compilation totals may differ. Reconciliation warnings disclose the gap and do not rescale published candidate counts.',
        '- Detailed 2024 and 2022 state archives vary in local-office coverage. An advertised category is not a claim that every local election has been collected.',
        '- Precinct result records can be inspected and searched. Precinct map rendering requires a separately validated boundary crosswalk; identifiers alone do not establish a boundary match.',
        '- Cross-vintage county/district swing requires a verified crosswalk. Matching names or numeric identifiers alone do not prove identical boundaries.',
        '- ACS population, age, and household-income context covers 2020–2024 residents/households and retains published 90% margins of error. These are not measured voter demographics or registration denominators.',
        '- Current participation remains a separately validated source program. Additional UF state files load on demand, and original authority lineage and academic-source caveats remain visible.',
        '- Official 2026 candidate rosters and every primary, special, runoff, or municipal contest are not exhaustively collected. Search/catalog results identify installed evidence rather than an imagined complete election universe.',
        '- Forecast publication remains gated by timestamp-safe historical validation and actual election rules.']
    path = PROJECT_ROOT/'docs'/'ATLAS_COVERAGE.md'
    path.write_text('\n'.join(lines)+'\n')
    print(path)

if __name__ == '__main__':
    main()
