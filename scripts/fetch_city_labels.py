"""Small, source-backed orientation labels; editorial selection, not population rank."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import zipfile
from pathlib import Path

import httpx

CITY_CHOICES = {
'AL':'Birmingham|Montgomery|Huntsville|Mobile','AK':'Anchorage|Fairbanks|Juneau','AZ':'Phoenix|Tucson|Flagstaff',
'AR':'Little Rock|Fayetteville|Fort Smith','CA':'Los Angeles|San Francisco|San Diego|Sacramento|Fresno',
'CO':'Denver|Colorado Springs|Fort Collins|Grand Junction','CT':'Hartford|New Haven|Stamford|Bridgeport',
'DE':'Wilmington|Dover','FL':'Miami|Orlando|Tampa|Jacksonville|Tallahassee','GA':'Atlanta|Savannah|Augusta|Columbus',
'HI':'Urban Honolulu|Hilo|Kahului','ID':'Boise City|Idaho Falls|Coeur d\u0027Alene','IL':'Chicago|Springfield|Peoria|Rockford',
'IN':'Indianapolis|Fort Wayne|Evansville|South Bend','IA':'Des Moines|Cedar Rapids|Davenport|Sioux City',
'KS':'Wichita|Topeka|Overland Park|Manhattan','KY':'Louisville|Lexington-Fayette|Frankfort|Bowling Green',
'LA':'New Orleans|Baton Rouge|Shreveport|Lafayette','ME':'Portland|Augusta|Bangor|Lewiston',
'MD':'Baltimore|Annapolis|Frederick|Salisbury','MA':'Boston|Worcester|Springfield|Pittsfield',
'MI':'Detroit|Lansing|Grand Rapids|Traverse City|Marquette','MN':'Minneapolis|St. Paul|Duluth|Rochester',
'MS':'Jackson|Gulfport|Hattiesburg|Tupelo','MO':'Kansas City|St. Louis|Jefferson City|Springfield',
'MT':'Billings|Helena|Missoula|Great Falls','NE':'Omaha|Lincoln|Grand Island|Scottsbluff',
'NV':'Las Vegas|Reno|Carson City|Elko','NH':'Manchester|Concord|Portsmouth|Berlin',
'NJ':'Newark|Trenton|Jersey City|Atlantic City','NM':'Albuquerque|Santa Fe|Las Cruces|Roswell',
'NY':'New York|Buffalo|Albany|Rochester|Syracuse','NC':'Charlotte|Raleigh|Greensboro|Wilmington|Asheville|Fayetteville',
'ND':'Fargo|Bismarck|Grand Forks|Minot','OH':'Columbus|Cleveland|Cincinnati|Toledo|Dayton',
'OK':'Oklahoma City|Tulsa|Lawton','OR':'Portland|Salem|Eugene|Bend|Medford',
'PA':'Philadelphia|Pittsburgh|Harrisburg|Erie|Scranton','RI':'Providence|Newport|Warwick',
'SC':'Charleston|Columbia|Greenville|Florence','SD':'Sioux Falls|Pierre|Rapid City|Aberdeen',
'TN':'Nashville-Davidson|Memphis|Knoxville|Chattanooga','TX':'Houston|Dallas|Austin|San Antonio|El Paso|Amarillo|Corpus Christi',
'UT':'Salt Lake City|Provo|St. George','VT':'Burlington|Montpelier|Rutland',
'VA':'Richmond|Norfolk|Roanoke|Alexandria|Charlottesville','WA':'Seattle|Olympia|Spokane|Tacoma|Yakima',
'WV':'Charleston|Huntington|Morgantown|Wheeling','WI':'Milwaukee|Madison|Green Bay|Eau Claire',
'WY':'Cheyenne|Casper|Laramie|Jackson'}


def main():
    root=Path(__file__).resolve().parents[1]/'frontend'/'public'/'geography'
    url='https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2024_Gazetteer/2024_Gaz_place_national.zip'
    response=httpx.get(url,timeout=60,follow_redirects=True)
    response.raise_for_status()
    archive=zipfile.ZipFile(io.BytesIO(response.content))
    name=next(n for n in archive.namelist() if n.endswith('.txt'))
    rows=csv.DictReader(io.StringIO(archive.read(name).decode('utf-8-sig')),delimiter='\t')
    labels=[]
    matched=set()
    for raw in rows:
        row={k.strip():v.strip() for k,v in raw.items()}
        state=row['USPS']
        if state not in CITY_CHOICES:
            continue
        for priority,choice in enumerate(CITY_CHOICES[state].split('|')):
            pattern=r'^'+re.escape(choice)+r'(?: city.*| town.*| municipality.*| borough.*| CDP| consolidated government.*| metro government.*| metropolitan government.*)?$'
            if re.match(pattern,row['NAME'],flags=re.I):
                key=(state,choice)
                if key in matched:
                    continue
                matched.add(key)
                labels.append({'state':state,'name':choice.replace('Urban Honolulu','Honolulu').replace('Boise City','Boise'),
                    'census_name':row['NAME'],'geoid':row['GEOID'],'longitude':float(row['INTPTLONG']),
                    'latitude':float(row['INTPTLAT']),'priority':priority})
    root.mkdir(parents=True,exist_ok=True)
    (root/'cities.json').write_text(json.dumps({'vintage':'2024','source':url,'labels':labels},separators=(',',':')))
    (root/'cities-manifest.json').write_text(json.dumps({'url':url,'source_sha256':hashlib.sha256(response.content).hexdigest(),
        'vintage':'2024','producer':'U.S. Census Bureau','license':'U.S. public domain',
        'definition':'Editorially selected place orientation labels using Census Gazetteer representative points; not population rankings or election reporting units.',
        'matched':len(labels),'missing_choices':[(s,c) for s,cs in CITY_CHOICES.items() for c in cs.split('|') if (s,c) not in matched]},indent=2))
    print(f'Wrote {len(labels)} verified orientation labels')

if __name__=='__main__':
    main()
