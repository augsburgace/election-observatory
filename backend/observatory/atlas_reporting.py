"""Sourced vector figures and aggregate context reports, without external services."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import zipfile
from html import escape

from .domain import utc_now


def result_figure_data(view):
    areas = view['geographies']
    total = view.get('summary', {}).get('total_votes')
    if not total or any(r.get('partial_suppression') for r in areas):
        options = []
    else:
        options = {}
        for area in areas:
            for option in area['options']:
                key = (option['name'], option['party'])
                item = options.setdefault(key, {**option, 'votes': 0})
                item['votes'] += option['votes'] or 0
        options = sorted(options.values(), key=lambda row: -row['votes'])[:12]
    return {'options': options, 'total': total, 'history': view.get('history', []),
            'places': sorted(areas, key=lambda r: -r['total_votes'])[:12] if total else []}


def party_color(party):
    return {'DEM': '#1559be', 'REP': '#c41439', 'LIB': '#9a6711', 'GRN': '#0c876d'}.get(party, '#8058ac')


def report_footer(canvas, document, revision):
    from reportlab.lib.colors import HexColor
    canvas.saveState()
    canvas.setFillColor(HexColor('#52657e'))
    canvas.setFont('Helvetica', 8)
    canvas.drawString(40, 28, f'Observatory Election Atlas - evidence revision {revision}')
    canvas.drawRightString(document.pagesize[0]-40, 28, f'Page {document.page}')
    canvas.restoreState()


def result_figures_svg(view):
    data = result_figure_data(view)
    output = []
    if data['options']:
        rows = data['options']
        items = ['<svg viewBox="0 0 900 %d" role="img" aria-label="Complete contest distribution">' % (len(rows) * 36 + 45),
                 '<text x="0" y="20" font-size="18" font-weight="700">Candidate / ballot-option distribution</text>']
        for i, row in enumerate(rows):
            y = 48 + 36 * i
            share = row['votes'] / data['total'] * 100
            items.append(f'<text x="0" y="{y}" font-size="12">{escape(row["name"])}</text><rect x="280" y="{y-13}" height="18" width="{share*4.2:.2f}" fill="{party_color(row["party"])}"/><text x="{290+share*4.2:.2f}" y="{y}" font-size="12">{share:.1f}% · {row["votes"]:,.0f}</text>')
        output.append(''.join(items) + '</svg>')
    history = data['history']
    if len(history) > 1:
        items = ['<svg viewBox="0 0 900 290" role="img" aria-label="Historical statewide candidate shares"><text x="0" y="20" font-size="18" font-weight="700">Statewide presidential history · published returns</text>']
        lo, hi = min(r['year'] for r in history), max(r['year'] for r in history)
        for value in (0, 25, 50, 75, 100):
            y = 240 - value * 1.8
            items.append(f'<line x1="60" x2="790" y1="{y}" y2="{y}" stroke="#dae3ec"/><text x="5" y="{y+4}" font-size="12">{value}%</text>')
        for field, color in [('dem_share_pct', '#1559be'), ('rep_share_pct', '#c41439')]:
            points = [(60 + (r['year']-lo)/(hi-lo)*730, 240-r[field]*1.8) for r in history if r[field] is not None]
            coordinates = ' '.join(f'{x:.2f},{y:.2f}' for x,y in points)
            items.append(f'<polyline points="{coordinates}" fill="none" stroke="{color}" stroke-width="3"/>')
            items += [f'<circle cx="{x:.2f}" cy="{y:.2f}" r="3" fill="{color}"/>' for x,y in points]
            if points:
                items.append(f'<text x="800" y="{points[-1][1]+4:.2f}" fill="{color}" font-size="12">{"Democratic" if field=="dem_share_pct" else "Republican"}</text>')
        items += [f'<text x="60" y="270">{lo}</text><text x="760" y="270">{hi}</text></svg>']
        output.append(''.join(items))
    return '<section class="research-figures">' + ''.join(output) + '</section>'


def result_pdf_figures(view):
    from reportlab.graphics.shapes import Circle, Drawing, Line, PolyLine, Rect, String
    from reportlab.lib.colors import HexColor
    from reportlab.platypus import Spacer
    data = result_figure_data(view)
    output = []
    if data['options']:
        height = 32 + 25 * len(data['options'])
        drawing = Drawing(450, height)
        drawing.add(String(0, height-12, 'Candidate / ballot-option distribution', fontSize=12))
        for i, row in enumerate(data['options']):
            y = height - 40 - i*25
            share = row['votes'] / data['total'] * 100
            drawing.add(String(0, y+3, row['name'][:28], fontSize=8))
            drawing.add(Rect(170, y, share*1.9, 13, fillColor=HexColor(party_color(row['party'])), strokeColor=None))
            drawing.add(String(177 + share*1.9, y+3, f'{share:.1f}% / {row["votes"]:,.0f}', fontSize=8))
        output += [drawing, Spacer(1, 12)]
    history = data['history']
    if len(history) > 1:
        drawing = Drawing(450, 175)
        drawing.add(String(0,160,'Statewide presidential history / published returns',fontSize=12))
        lo,hi = min(r['year'] for r in history),max(r['year'] for r in history)
        for value in (0,25,50,75,100):
            y=25+value*1.1
            drawing.add(Line(35,y,385,y,strokeColor=HexColor('#dae3ec')))
            drawing.add(String(0,y-3,f'{value}%',fontSize=8))
        for field,color in [('dem_share_pct','#1559be'),('rep_share_pct','#c41439')]:
            points=[(35+(r['year']-lo)/(hi-lo)*350,25+r[field]*1.1) for r in history if r[field] is not None]
            if len(points)>1:
                drawing.add(PolyLine([v for point in points for v in point],strokeColor=HexColor(color),strokeWidth=2))
            for x,y in points:
                drawing.add(Circle(x,y,2,fillColor=HexColor(color),strokeColor=None))
            if points:
                drawing.add(String(392,points[-1][1]-3,'Democratic' if field=='dem_share_pct' else 'Republican',fontSize=8,fillColor=HexColor(color)))
        drawing.add(String(35,8,str(lo),fontSize=8))
        drawing.add(String(367,8,str(hi),fontSize=8))
        output += [drawing,Spacer(1,16)]
    return output


def context_export(view, format, presentation=None):
    view = {**view, 'sources': [{k:v for k,v in s.items() if k != 'path'} for s in view['sources']]}
    manifest = {'schema':'observatory-context-research-v1','created_at':utc_now(),'dataset_revision':view['revision'],
        'query':view['query'],'source_snapshots':view['sources'],'limitations':view['warnings'],
        'private_notes_included':False,'presentation':presentation or {},
        'result_sha256':hashlib.sha256(json.dumps(view,sort_keys=True).encode()).hexdigest()}
    fields=['state','geography_id','metric','estimate','moe','unit','period_start','period_end','snapshot_id','revision']
    stream=io.StringIO(newline='')
    writer=csv.DictWriter(stream,fieldnames=fields,extrasaction='ignore')
    writer.writeheader()
    writer.writerows(view['estimates'])
    csv_bytes=stream.getvalue().encode('utf-8-sig')
    rows=''.join('<tr>'+''.join('<td>'+escape(str(r.get(k) if r.get(k) is not None else 'Unavailable'))+'</td>' for k in fields)+'</tr>' for r in view['estimates'])
    html=(f'<!doctype html><html lang="en"><meta charset="utf-8"><title>Census resident context</title><style>body{{font:15px system-ui;max-width:1200px;margin:35px auto;color:#172b43}}table{{border-collapse:collapse;font-variant-numeric:tabular-nums;width:100%}}th,td{{padding:8px;text-align:left;border-bottom:1px solid #d4dfeb}}th{{background:#e2f3ef}}h1{{font-family:Georgia}}</style><h1>Census resident and household context</h1><p>Revision {view["revision"]}. ACS 2020–2024 five-year estimates, with published 90% margins of error. These describe residents/households, not measured voter characteristics.</p><table><thead><tr>'+''.join(f'<th>{escape(k.replace("_"," "))}</th>' for k in fields)+'</tr></thead><tbody>'+rows+'</tbody></table><h2>Evidence</h2>'+''.join(f'<p>{escape(s["url"])} · SHA256 {s["sha256"]}</p>' for s in view['sources'])+'</html>').encode()
    if format=='csv':
        return csv_bytes,'text/csv'
    if format=='json':
        return json.dumps({'context':view,'manifest':manifest},indent=2).encode(),'application/json'
    if format=='html':
        return html,'text/html'
    if format=='pdf':
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
        output=io.BytesIO()
        styles=getSampleStyleSheet()
        story=[Paragraph('Census resident and household context',styles['Title']),Paragraph(f'Revision {view["revision"]}. ACS 2020-2024 estimates and 90% margins of error; not voter demographics.',styles['Normal']),Spacer(1,16)]
        values=[['Place / GEOID','Metric','Estimate','90% MOE','Unit']]
        for r in view['estimates']:
            values.append([r['geography_id'],r['metric'].replace('_',' '),'Unavailable' if r['estimate'] is None else f'{r["estimate"]:,.1f}',
                'Unavailable' if r['moe'] is None else f'{r["moe"]:,.1f}',Paragraph(escape(r['unit']),styles['Normal'])])
        table=Table(values,repeatRows=1,colWidths=[95,110,85,85,110])
        table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e2f3ef')),('FONTSIZE',(0,0),(-1,-1),8),('VALIGN',(0,0),(-1,-1),'TOP'),('BOTTOMPADDING',(0,0),(-1,-1),8),('LINEBELOW',(0,0),(-1,-1),.2,colors.lightgrey)]))
        story.append(table)
        story += [Paragraph(escape(w),styles['Normal']) for w in view['warnings']]
        story += [Paragraph(escape(f'{s["url"]} | SHA256 {s["sha256"]}'),styles['Normal']) for s in view['sources']]
        def footer(canvas, doc):
            report_footer(canvas, doc, view['revision'])
        SimpleDocTemplate(output,title='Census resident context').build(story,onFirstPage=footer,onLaterPages=footer)
        return output.getvalue(),'application/pdf'
    output=io.BytesIO()
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('manifest.json',json.dumps(manifest,indent=2))
        archive.writestr('context.json',json.dumps(view,indent=2))
        archive.writestr('context.csv',csv_bytes)
        archive.writestr('report.html',html)
        archive.writestr('saved_view.json',json.dumps({'revision':view['revision'],'query':view['query'],'presentation':presentation or {}},indent=2))
    return output.getvalue(),'application/zip'
