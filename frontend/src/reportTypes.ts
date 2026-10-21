import type { ResearchQuery } from './types';
export interface ReportSectionChoice { id: string; enabled: boolean; caption: string }
export interface ResultsScope { year: number; baseline: number | null; office: string; contest_id?: string | null; geography_level: 'state'|'county'|'district'|'municipality'|'precinct'; geography_ids: string[]; offset: number; limit: number }
export interface ReportRequest { title: string; template: string; query: ResearchQuery; results: ResultsScope; context_metric: 'population'|'median_age'|'median_household_income'; map_metric: 'dem_margin_pp'|'total_votes'; sections: ReportSectionChoice[]; notes: string; include_notes: boolean }
export interface ReportPreview { title: string; revision: number; html: string; request: ReportRequest; sources: {id:number;url:string;sha256:string}[]; sections: {id:string;title:string;figures:unknown[];tables:{rows:unknown[]}[];warnings:string[]}[]; content_sha256: string; boundary_files: {file:string;vintage:string}[]; limitations:string[] }
export const reportSections = [
  {id:'ev_call',title:'Experimental Senate EV-led call',kind:'EV model',description:'Exact conditional margin, EV inputs, assumptions and validation limits.'},
  {id:'summary', title:'Research findings', kind:'Summary', description:'Exact scope, evidence date and findings.'},
  {id:'ev_trajectory',title:'Participation through time',kind:'Early voting',description:'Actual observation steps and aligned cycles.'},
  {id:'ev_changes',title:'Newly reported ballots',kind:'Early voting',description:'Reporting increments and negative corrections.'},
  {id:'ev_map',title:'Participation geography',kind:'Early voting',description:'Volume symbols with area proportional to count.'},
  {id:'ev_places',title:'Geographic contributors',kind:'Early voting',description:'Ranked places and separate labeled trajectories.'},
  {id:'ev_composition',title:'Published composition',kind:'Early voting',description:'Supported marginal groups and unknown shares.'},
  {id:'results_map',title:'Historical results map',kind:'Results',description:'Original returns, numeric legend and boundary vintage.'},
  {id:'results_distribution',title:'Candidates and ballot options',kind:'Results',description:'Candidate shares, write-ins and all named responses.'},
  {id:'historical_trend',title:'Long-run historical context',kind:'Results',description:'Statewide presidential history, where collected.'},
  {id:'comparison',title:'Historical comparison',kind:'Results',description:'Original margins and compatibility-qualified changes.'},
  {id:'context_map',title:'Resident context map',kind:'Census context',description:'ACS population, age or household income.'},
  {id:'context_ranking',title:'Resident context rankings',kind:'Census context',description:'Published estimates and 90% margins of error.'},
  {id:'polls',title:'Original polling inventory',kind:'Polling',description:'Actual questions, populations and complete responses.'},
  {id:'evidence',title:'Sources and reproducibility',kind:'Evidence',description:'Source hashes, definitions, caveats and exact query.'},
];
export const reportTemplates = [
  {id:'ev_senate',label:'Senate EV-led forecast dossier',description:'A conditional Senate call, the actual early-vote evidence, model assumptions and explicit limits.',sections:['ev_call','summary','ev_trajectory','ev_changes','ev_map','ev_composition','polls','evidence']},
  {id:'state',label:'Complete state dossier',description:'The full state story, with voting, results, context and original evidence.',sections:['summary','ev_trajectory','ev_changes','ev_map','ev_places','ev_composition','results_map','results_distribution','historical_trend','comparison','context_ranking','polls','evidence']},
  {id:'daily',label:'Early-voting daily brief',description:'What changed, how reporting developed, and which places contributed.',sections:['summary','ev_trajectory','ev_changes','ev_map','ev_places','evidence']},
  {id:'history',label:'Historical election comparison',description:'Maps, candidate distributions, long-run context and honest comparisons.',sections:['summary','results_map','results_distribution','historical_trend','comparison','evidence']},
  {id:'context',label:'Resident context and geography',description:'A sourced population and household research packet with uncertainty.',sections:['summary','context_map','context_ranking','evidence']},
  {id:'polls',label:'Polling methodology review',description:'Original releases, disclosed methodology and complete responses.',sections:['summary','polls','evidence']},
  {id:'custom',label:'Custom research packet',description:'Choose any combination of figures, tables and sourced findings.',sections:['summary','results_map','ev_trajectory','context_map','evidence']},
];
