# Observatory API contract

All routes start `/api/v1`. Missing measured quantities are null/empty, never fabricated zero. Dates ISO8601; state codes USPS. All workspace panels share `revision` and `query`.

## GET /bootstrap

```ts
{
 app: {name: string, version:string, election_date:string, today:string},
 latest_revision: number,
 states: Array<{code:string,name:string,fips:string,watchlist:boolean,seat_party:string,election_system:string}>,
 races: Array<{id:string,state:string,name:string,cycle:number,election_date:string,watchlist:boolean,election_system:string,seat_party:string,candidates:any[]}>,
 metrics: Array<{id:string,label:string,unit:string,description:string}>,
 cycles: number[],
 coverage: {states_with_data:number,selected_states:number,poll_count:number,source_count:number}
}
```

## GET /workspace

Query parameters: state=NC, cycle=2026, baseline=2022, as_of=YYYY-MM-DD (inclusive cutoff; omitted=latest), time_basis=reported|reconstructed|final, revision=integer(optional pinned revision), metric=ballots_cast, mode=all, geography_ids=comma-separated IDs, category_dimension/category (optional), alignment=days_to_election|calendar|days_since_open. Nonavailable joint dimensions produce a warning and no invented result. Response:

```ts
{
 revision:number, latest_revision:number, query:ResearchQuery,
 state:{code,name,fips,watchlist,seat_party,election_system},
 summary:{total:number|null, latest_date:string|null, newly_reported:number|null,
   baseline_total:number|null, pace_ratio:number|null, geography_count:number,
   coverage_status:string, poll_count:number,metric_label:string,unit:string},
 observations:Array<Observation & {id:number,source_id:string,snapshot_id:number,observed_at:string,revision:number}>,
 series:Array<{date:string,days_to_election:number,cycle:number,value:number,metric:string,mode:string,time_basis:string,observation_ids:number[],source_ids:string[]}>,
 geographies:Array<{id:string,name:string,type:string,value:number,baseline_value:number|null,change:number|null,share:number|null,denominator:number|null,source_ids:string[],observation_ids:number[]}>,
 composition:Array<{dimension:string,category:string,value:number,metric:string,mode:string,source_ids:string[],observation_ids:number[]}>,
 polls:Array<Poll & {id:number,source_id:string,snapshot_id:number}>,
 polling:{available:boolean,average:any|null,eligible_count:number,reason:string,included:any[],excluded:any[],sensitivity:any[]},
 sources:Array<Source>,
 brief:Array<{id:string,title:string,text:string,observation_ids:number[],source_ids:string[]}>,
 coverage:{status:string,available_metrics:string[],available_modes:string[],available_dimensions:string[],available_cycles:number[],geographic_count:number,as_reported_available:boolean,reconstructed_available:boolean},
 warnings:string[],
 national:Array<{code:string,name:string,fips:string,watchlist:boolean,value:number|null,latest_date:string|null,source_count:number,poll_count:number,coverage_status:string,metric:string}>,
 calendar:Array<{date:string,label:string,source_url:string}>
}
```

`Observation` and `Poll` fields are in backend/observatory/domain.py. Source has id,state,name,url,connector,tier,enabled,expected_hours, status,last_checked,last_changed,data_as_of,error,observation_count,poll_count,warnings. Status distinguishes not_collected/ready/unchanged/partial/failed/unavailable.

## GET /geography/{state}

GeoJSON FeatureCollection. Properties include name, id and GEOID. Boundary/source metadata is in `metadata` and headers. GET /geography/US serves national states. Geometry load failure returns a meaningful error, not invented shapes.

## GET /sources

`{sources:Source[],revision:number,latest_revision:number}`

## GET /evidence/{observation_id}

`{observation,source,snapshot:{id,url,sha256,retrieved_at,content_type,byte_count},revisions:[],calculation:string,warnings:[]}`. GET /documents/{snapshot_id} serves source document (bounded, local only; no arbitrary path).

## Research persistence

GET /research -> `{items:Array<{id:number,kind:string,title:string,body:string,view:object,created_at:string,updated_at:string}>}`.
POST /research body `{kind:'note'|'view'|'bookmark'|'scenario'|'report'|'correction',title:string,body?:string,view?:object}` -> item.
PUT /research/{id} same body -> item. DELETE /research/{id} -> `{deleted:true}` (UI requires explicit user action).
Saved view stores full query, revision, selected geographies, active route, layout. Open exact retains revision; open latest explicitly clears revision/as_of as selected.

## Scenarios

POST /scenarios accepts `{state:string,revision?:number,observed_ballots?:number,final_turnout:number,early_share:number,early_support:number,election_day_support:number,undecided_share?:number,undecided_allocation?:number}`; support/share inputs use proportions 0..1. Result `{assumptions,observed_ballots,remaining_ballots,early_ballots,election_day_ballots,candidate_a_votes,candidate_b_votes,candidate_a_share,margin,components:[],sensitivity:[],grid:[],warnings:[]}`. Scenarios are assumptions, not observed candidate votes.

## Forecasts

GET /forecasts?state=NC&revision=... -> `{status:'unavailable'|'validated',reason:string,methodology:string,validation:object|null,runs:[],requirements:[],warnings:[]}`. No calibrated live probability without historical evidence. POST /forecast/backtest runs normalized, cutoff-safe historical inputs (documented separately). Specialist systems remain gated.

## Collection jobs

POST /refresh `{source_ids?:string[],state?:string,include_historical?:boolean}` -> `{id:number,status:'queued'}`. GET /jobs -> `{jobs:[{id,kind,status,created_at,started_at,finished_at,progress,result,error}]}`. GET /jobs/{id} -> job. One collection run at a time; previous validated evidence persists. Actual checking cadence is launchd/collector, no fake live status.

## Exports

GET /exports?format=csv|json|html|pdf|zip&state=NC&...same workspace parameters produces filtered reproducible download. Optional sections=overview,voting,geography,polls,sources and include_notes=false. Includes query/revision/source manifest, no raw voter records. Direct download through relative `/api/v1/exports?...` URL. SVG/PNG chart export is frontend native and must include evidence labels. POST /exports accepts {query:ResearchQuery,format,title?,note?,sections?:string[],include_notes?:boolean}; section order is preserved in HTML and PDF. Private annotations are included only with include_notes=true. This renders a local download. Research ZIPs include archive hashes and a reproducibility manifest.

POST /corrections `{observation_id:number,replacement:number,reason:string}` records auditable overlay. Shared analytical queries include active correction at the pinned revision; original remains in evidence.

## Reproducibility and payload scope

Workspace `observation_scope` states the complete selected row count and separately identifies latest statewide rows retained only as voting-mode context. Selected observations are not row-capped. Native verbose metadata is retrieved through `/evidence/{id}`. Calendar references include their archived snapshot/hash and activate only with the appropriate revision, cutoff, method, and evidence chronology. CSV excludes other-mode context rows. Research-package manifests include metric definitions, boundary vintage/source hashes, application/parser fingerprints, original source snapshots, and optional selected notes.

`observatory reproduce package.zip` uses the manifest query and section configuration, verifies source hashes against the matching local store, compares recomputed totals/trajectories, and writes a new report without overwriting an existing file.

## Nationwide atlas v2

The legacy `/api/v1` evidence, research, polling, scenario, export and saved-view interfaces remain supported. `ResearchQuery.date_window` is optional; GET requests encode the ordered date pair as `date_window=2026-10-15,2026-10-20`. A date brush constrains the evidence cutoff and plotted/exported observation window. It does not create intervening observations.

| Route | Purpose |
|---|---|
| `GET /api/v2/catalog/states` | All 50 states with installed historical years, offices, levels and coverage |
| `GET /api/v2/catalog/datasets?state=TX` | Verified source inventory, installed status, attributed participation bridges and on-demand depth |
| `GET /api/v2/catalog/availability/TX` | Historical catalog plus current participation capabilities |
| `GET /api/v2/catalog/elections` | Searchable, paginated installed elections |
| `GET /api/v2/catalog/contests` | Filter `state`, `year`, `office`, `q`; paginate with `offset`, `limit` |
| `GET /api/v2/search?q=Harris` | States, places, contests, ballot options and saved research |
| `GET /api/v2/results` | Revisioned contest returns, complete response options, source references and coverage |
| `GET /api/v2/analysis/results` | Shared findings, rankings, concentration, option distributions and population-context scatter values |
| `GET /api/v2/context` | Resident/household estimates, periods, margins of error and source snapshots |
| `GET /api/v2/analytics` | Compact coordinated participation workspace and separate place trajectories |
| `GET /api/v2/trajectories` | Geographic contribution, concentration and individually labeled observed series |
| `GET /api/v2/observations` | Paginated evidence for the exact participation query |
| `GET /api/v2/places/{geography_id}?state=TX` | Durable place dossier, paginated historical years, participation and resident context |
| `GET /api/v2/contests/{contest_id}` | Contest identity, options, applicable round and result evidence |
| `GET /api/v2/candidates/{option_id}` | Ballot option identity scoped to its contest; measures remain response options |
| `POST /api/v2/datasets/{id}/load` | Queue a source download/validation job; body optionally supplies `state` for a source family |
| `GET /api/v1/jobs/{id}` | Durable queued/running/completed/failed progress, source stages and errors |
| `GET /api/v2/results/exports` | CSV, JSON, printable HTML, PDF and reproducible research ZIP using the same result calculation |
| `GET /api/v2/participation/quality` | Exact participation-query interpretation: definitions, source chronology, geographic reconciliation, corrections and comparison limits |
| `GET /api/v2/comparisons/results` | Paired historical county/state results with reviewed comparison eligibility, matched coverage and source references |
| `GET /api/v2/precincts/catalog?state=OH&year=2020` | Verified source-native geometry inventory, cached status and available acquisition paths |
| `POST /api/v2/precincts/{dataset_id}/load` | Durable on-demand native geometry/results download job |
| `GET /api/v2/precincts/map` | Source-native results joined to geometry; `bbox`, `lod`, `contest_id`, revision and bounded feature count |
| `GET /api/v2/forecasts/early-vote` | Experimental EV-led Senate party-margin calls, exact evidence, assumptions, ranges and validation limitations |
| `POST /api/v2/reports/preview` | Compose pinned sections, vector figures, complete tables, captions and source appendix from a `ReportRequest` |
| `POST /api/v2/reports/exports?format=zip` | The same report as HTML/PDF/CSV/JSON or reproducible ZIP, with optional explicitly selected private notes |

Results parameters: `state` (omit for national), `year`, `office`, `contest_id`, `baseline`, `geography_level`, `geography_ids`, `revision`. The nationwide presidential view uses `geography_level=state`; initial navigation never requires national precinct geometry. Source datasets may provide precinct results without sufficient boundaries for a precinct map.

Result semantics: `total_votes` means candidate/ballot-option votes in the chosen contest and geographic coverage. It is not ballots cast or unique voters. A multi-contest response withholds an aggregate total. `dem_margin_pp` is D minus R, `rep_margin_pp` is R minus D, and `swing_pp` is the change in D minus R. Ties, incomplete suppression, multi-seat offices and first-choice ranked-choice records do not establish a certified winner. Geographic change requires a reviewed boundary comparison. Source reconciliation warnings preserve county-versus-state disagreements instead of rescaling original values.

Every result query retains its revision, normalized parameters, units, geographic vintage, original source snapshots and limitations. A package contains `results.json`, aggregate CSV, printable report and `manifest.json` with hashes. Reproduce it using `observatory reproduce package.zip --format html`. Matching original source archives and the pinned evidence database are required.

Additional v2 details: geography discovery supports `state`, `level`, `vintage`, `q`, `revision`, `offset`, and `limit`. Dated registration evidence is available at `/api/v2/denominators`; resident population is never silently substituted. Precinct result queries use a default and maximum of **200 complete reporting areas per page** before loading option records. Their totals explicitly describe the page, with `pagination.total_geographies` and `has_more`. Source-native districts without validated geometry remain table research.

`/api/v2/evidence/results/{id}` provides the normalized aggregate, option/contest identity, source snapshot, revision trail, calculation, and archived-document link. Candidate identity dossiers include relevant collected option results and original source references.

`/api/v2/context/exports` exports Census context in CSV, JSON, HTML, PDF or ZIP, retaining missing estimates, units, periods and margins of error. Result and context exports accept a bounded `view_state` JSON object for non-sensitive `ui_*` settings and map layer/legend/viewport/selected-place metadata. ZIPs include `saved_view.json`; manifests retain that presentation descriptor independently of the analytical query. Reproduction verifies the original data and source hashes before regeneration. Historical reports include vector candidate distributions and available statewide historical-share figures; chart/map image exports retain their visible legends separately.
