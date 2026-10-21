# Native precinct cartography

Precinct maps are historical election context. They do not show how current early voters voted. Current voting remains a separate research layer with its own definition, reporting date, geography, and source.

## Original evidence and acquisition

- The [Voting and Election Science Team's 2020 original release](https://doi.org/10.7910/DVN/K7760H), Harvard Dataverse version 49, provides a public paired shapefile and candidate returns for every state. `config/precinct_sources.json` records the actual unrestricted file IDs, producer checksums, sizes, and discovery metadata verified October 21, 2026. Attribution is CC BY 4.0. The original ZIP, state methodology, and Dataverse metadata are archived with SHA-256 hashes.
- North Carolina uses dated official NCSBE precinct shapefiles from the [election authority's boundary archive](https://www.ncsbe.gov/results-data/voting-maps-redistricting), paired only through unique original county and precinct identifiers in the installed MEDSL records. The July 23, 2024 file has 2,656 polygons; 2,654 match uniquely. Durham precinct 48 and Union 020B remain unmatched. No fuzzy matching or allocation closes these gaps.
- The [NCSBE results documentation](https://www.ncsbe.gov/results-data/election-results/historical-election-results-data) distinguishes physical and administrative reporting precincts. Absentee, early-voting-site, provisional, transfer, and otherwise unmatched totals remain in the map's unmapped-evidence table. A physical-precinct map is not necessarily the full residential distribution of votes.
- VEST's 2024 UF distribution requires a subscription. This release does not bypass the gate or substitute public Census VTDs as if they were 2024 election precincts.

VEST is the original producer of a harmonized research dataset, not the authority that counted each ballot. Read each state's included methodology. Some non-geographic absentee/provisional returns are allocated or estimated by VEST. The app retains that distinction and never calls these distributions independently observed early votes.

## Join and contest rules

VEST geometry and vote fields originate in the same DBF record. An internal ID contains state, election year, archived bundle hash, and record index. It is deliberately not a cross-election precinct ID or Census VTD assertion. Original precinct labels and county identifiers are retained where published.

NCSBE joins use a unique canonical county plus exact native precinct code. Numeric-only zero padding is the reviewed exception (`0003` and `3`); letters and punctuation stay exact. Ambiguous keys and unmatched polygons remain inspectable. Original return units are never spread across polygons.

Named VEST options are read from the producer's state-specific codebook. Repeated judicial office codes use distinct contiguous documented option sets. A repeated office label does not combine different seats into one contest. Recount columns remain separate from general-election columns. Unsupported unnamed fields are withheld and listed. A revisioned structural validation overlay preserves any earlier parsing interpretation for pinned evidence while withholding invalid grouped contests in current analysis.

Candidate totals belong to one contest. When an office contains several contests, the map requests a contest selection and withholds a combined vote total. Multi-seat or unspecified ranked-choice-round results cannot establish a unique eventual winner.

## Spatial processing and offline use

`pyproj` transforms the source's declared CRS to EPSG:4326. A missing CRS fails validation. Shapely validates polygon geometry; any repair is recorded. Immutable source files remain unchanged.

Three local, topology-preserving display levels are cached outside Git:

| Level | Simplification tolerance | Purpose |
|---|---:|---|
| Overview | 0.002 degrees | State-wide visual review |
| Detail | 0.0002 degrees | Regional inspection |
| Full | None | Source-resolution inspection |

Each file has a SHA-256 checksum in `data/geometry/<dataset>/r<revision>/manifest.json`. An explicit revision cannot use a later geometry manifest. Bounding-box requests select intersecting native polygons without changing their values. Dateline-spanning boxes are supported. Requests are bounded to 20,000 geometries and state/year scope; national precinct geometry is never fetched at startup. The source file remains the precision authority: display simplification is not an analytical boundary transformation.

## Operating commands

```bash
.venv/bin/python scripts/precinct_data.py --state TX
.venv/bin/python scripts/precinct_data.py --dataset vest_2020_TX
.venv/bin/python scripts/precinct_data.py --dataset ncsbe_precinct_2024
.venv/bin/python scripts/precinct_data.py --review-counties
.venv/bin/python scripts/precinct_data.py --state TX --year 2020 --map --bbox=-97.0,32.5,-96.5,33.0 --lod detail
```

An already validated bundle is reused. `--force` explicitly revalidates; `--offline` requires archived source responses and never invents a missing download. On-demand API jobs expose acquisition, geometry validation, caching, and completion. Failures preserve prior validated bundles.

## Coverage and limits

The all-state inventory provides an acquisition path, not a claim that every source is downloaded. The live representative installation includes official North Carolina 2024 precinct boundaries and the public VEST 2020 Texas, Maine, and Alaska bundles. Exact current counts, revision, mapped vote share, non-geographic returns, and source hashes are returned with every map. A precinct map becomes useful only when its reporting definition and coverage are understood.

Precinct-level cross-election swing remains gated until both geometry and reporting definitions have a documented compatible crosswalk. Reusing the same precinct number across years is insufficient. County comparisons provide the nearest supported alternative.
