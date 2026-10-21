"""Generate an honest dated coverage report from the installed evidence store."""
from __future__ import annotations

import sqlite3

from observatory.db import Database
from observatory.domain import utc_now
from observatory.registry import all_states, state_info
from observatory.service import source_inventory
from observatory.settings import PROJECT_ROOT, get_settings


def main():
    settings = get_settings()
    database = Database(settings)
    inventory = source_inventory(database)
    revision, cutoff = database.latest_revision(), utc_now()
    capability_rows = []
    with sqlite3.connect(settings.database_path) as connection:
        total = connection.execute('SELECT COUNT(*) FROM observations').fetchone()[0]
        studies = connection.execute('SELECT COUNT(DISTINCT study_id) FROM polls').fetchone()[0]
        snapshots = connection.execute('SELECT COUNT(*), COUNT(DISTINCT sha256) FROM snapshots').fetchone()
        rows = []
        for code in sorted(row['code'] for row in all_states()):
            catalog = database.observation_catalog(revision=revision, state=code, cutoff=cutoff)
            current = [r for r in catalog if r['cycle'] == 2026 and r['time_basis'] == 'reported' and r['metric'] != 'market_price_pct']
            metrics = sorted({r['metric'] for r in current})
            cycles = sorted({r['cycle'] for r in catalog if r['metric'] != 'market_price_pct'})
            observations = [r for r in database.observations(revision=revision, state=code, cycle=2026, cutoff=cutoff)
                if r.get('time_basis') == 'reported' and r.get('metric') != 'market_price_pct' and r.get('validation', {}).get('status') != 'quarantined']
            geographies = sorted({r['geography_type'] for r in observations})
            valid_sources = {r['source_id'] for r in current}
            polls = connection.execute('SELECT COUNT(DISTINCT study_id) FROM polls WHERE state=?',(code,)).fetchone()[0]
            primary = [s['id'] for s in inventory if s['id'] in valid_sources and s.get('tier')==1]
            academic = any(s['id'] in valid_sources and s.get('tier')==3 for s in inventory)
            layer = ('Official aggregate/record extraction' if primary else 'No parsed official voting source') + ('; labeled UF fallback' if academic else '')
            capability_rows.append({'state':code,'available':bool(metrics),'metrics':metrics,'current_sources':sorted(valid_sources),'cycles':cycles,'geographies':geographies})
            rows.append(f"| {state_info(code)['name']} | {', '.join(m.replace('_',' ') for m in metrics) or 'Unavailable'} | {', '.join(geographies) or 'Unavailable'} | {', '.join(map(str,cycles)) or 'Unavailable'} | {polls} | {layer} |")
    import json
    proof = PROJECT_ROOT/'.local'/'atlas-depth'/'participation-coverage.json'
    proof.parent.mkdir(parents=True,exist_ok=True)
    proof.write_text(json.dumps({'revision':revision,'cutoff':cutoff,'states':capability_rows},indent=2))
    available = [r for r in capability_rows if r['available']]
    receipts = [r for r in capability_rows if set(r['metrics']) & {'ballots_cast','ballots_accepted','ballots_returned','ballot_records_returned'}]
    absent = [r['state'] for r in capability_rows if not r['available']]
    lines = ['# Evidence coverage', '', f'Generated {utc_now()}. Dataset revision **{database.latest_revision()}**. This records what is installed, not a claim of exhaustive public-data coverage.', '',
             f'The store contains {total:,} observation versions, {studies} distinct survey identifiers across original releases and secondary discovery summaries, and {snapshots[0]} attributable source snapshots backed by {snapshots[1]} distinct archived documents. Counts of observation versions include revisions and separate reported/reconstructed representations; they are not ballot totals.', '',
             f"Current validated reported measures are installed for **{len(available)} states**; **{len(receipts)} states** have a cast/received/accepted measure (definitions differ and are not summed nationally). No validated current measure is installed for {', '.join(absent)}. Issuance and requests alone do not establish votes. Quarantined proxies and Maine request-date trajectories are excluded from this table.", '',
             '| State | Installed 2026 voting metrics | Published geographic grain | Installed voting cycles | Survey identifiers | Voting-source layer |', '|---|---|---|---|---:|---|', *rows, '',
             '## Material limits', '',
             '- New Hampshire has no validated repeatable public early-voting aggregate connector. Its current destination includes original polling references, official source discovery, research notes, and clear coverage limits.',
             '- Current official Iowa and Ohio automated access has not been established from this network; historical original reports are separately archived and validated; labeled University of Florida aggregates provide usable interim evidence. These do not satisfy the official-PDF/dashboard connector milestone.',
             '- Several other official dashboards are blocked or discovery-only. HTTP success is kept separate from extraction of validated observations.',
             '- Polling includes original university/producer releases and explicitly secondary RCP browser-captured discovery tables. These remain separate from full-questionnaire averages. Some releases are older or hypothetical; RCP requires a fresh browser capture rather than unattended HTTP scraping.',
             '- North Carolina provides the deepest daily official-PDF historical coverage across 2018, 2020, 2022, 2024, and 2026. A conflicting 2020 report is withheld. Contemporary publication and later-revised PDF chronology remain distinct.',
             '- Historical daily coverage elsewhere varies. Later voter-history reconstruction is not contemporary as-reported evidence. No intermediate reports or demographic intersections are invented.',
             '- Verified North Carolina in-person opening/closing calendars support days-since-opening only for that method and when archival evidence is available at the selected revision. Calendar days do not establish county-level voting opportunities.',
             '- Candidate names in survey questions are producer-reported question options. The race registry does not yet claim an independently verified official candidate roster.',
             '- EV-led Senate research calls now publish conditional directional party-margin estimates, source inputs and unvalidated sensitivity ranges. The empirical frozen-formula EV audit and separate added-factor tests expose real cases, dependence and missing training history; they have not established reliable transferable improvement. Validated winner probabilities and Senate-control probabilities remain gated; Alaska/Maine eventual-winner calls are withheld.',
             '- Source-native precinct maps, reviewed county comparisons, swipe/difference/bivariate maps, advanced charts and the reproducible report studio are implemented. Actual precinct acquisition paths cover all 50 states; installed depth is documented separately. Joint demographic filters and coherent ballot-status flows still require appropriate evidence.',
             '- Religion and candidate choice are not inferred for individual early voters. Published registration, primary-history affiliation, demographics, resident context and prior results retain separate meanings.', '',
             '## Source diagnostics', '', '| Source | Layer | Status | Data date | Limitation or last error |', '|---|---:|---|---|---|']
    for source in inventory:
        note=source.get('error') or '; '.join(source.get('warnings',[])[:2]) or source.get('notes') or ''
        lines.append(f"| [{source['id']}]({source['url']}) | {source.get('tier',1)} | {source['status']} | {source.get('data_as_of') or 'Not established'} | {str(note).replace('|','/').replace(chr(10),' ')[:340]} |")
    output = PROJECT_ROOT/'docs'/'COVERAGE.md'
    output.write_text('\n'.join(lines)+'\n')
    print(output)


if __name__=='__main__':
    main()
