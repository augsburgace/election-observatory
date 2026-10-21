import { isPublicMode } from "../publicData";
import { useEffect, useMemo, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowDown, ArrowUp, Check, ChevronDown, Eye, FileChartColumnIncreasing, FileText, GripVertical, LoaderCircle, LockKeyhole, RefreshCw, Save, Settings2, Table2 } from 'lucide-react';
import type { AppContext, ResearchObject } from '../types';
import { api } from '../api';
import { Badge, Field, Notice, Panel, Select } from '../components/ui';
import { stateName } from '../utils';
import { exportComposedReport, previewReport } from '../reportApi';
import { reportSections, reportTemplates, type ReportRequest, type ReportSectionChoice } from '../reportTypes';
import './reports.css';

function initialReport(ctx:AppContext):ReportRequest{
  const params=new URLSearchParams(location.search);
  const question=ctx.researchQuestion??new URLSearchParams(location.search).get('ui_question');
  const template=params.get('ui_report_template')==='ev_senate'?'ev_senate':question==='historical'?'history':question==='population'?'context':ctx.workspace.summary?.total==null?'history':'state';
  const choice=reportTemplates.find(t=>t.id===template)!;
  const selected=choice.sections;
  const selectedPlaces=ctx.query.geography_ids.filter(id=>id.startsWith('county:')||id.startsWith('state:'));
  return {title:`${stateName(ctx.query.state)} · ${choice.label}`,template,query:{...ctx.workspace.query,revision:ctx.workspace.revision},
    results:{year:ctx.resultYear??Number(params.get('ui_result_year')||2024),baseline:2020,office:ctx.resultOffice??params.get('ui_result_office')??'PRESIDENT',contest_id:params.get('ui_result_contest'),geography_level:ctx.query.state==='AK'?'state':'county',geography_ids:selectedPlaces,offset:0,limit:200},
    context_metric:'population',map_metric:'dem_margin_pp',sections:[...selected,...reportSections.map(s=>s.id).filter(id=>!selected.includes(id))].map(id=>({id,enabled:selected.includes(id),caption:''})),notes:'',include_notes:false};
}
function researchItems(value:ResearchObject[]|{items:ResearchObject[]}|undefined){return value?Array.isArray(value)?value:value.items:[];}
export default function Reports(ctx:AppContext){
  const {notify}=ctx;
  const cache=useQueryClient();
  const [draft,setDraft]=useState<ReportRequest>(()=>initialReport(ctx));
  const [renderRequest,setRenderRequest]=useState(draft);
  const [busy,setBusy]=useState('');
  const [savedId,setSavedId]=useState<number>();
  const [activeSection,setActiveSection]=useState('');
  const [showSources,setShowSources]=useState(false);
  const loadedId=useRef<number|undefined>(undefined);
  const previewFrame=useRef<HTMLIFrameElement>(null);
  const collection=useQuery({queryKey:['research'],queryFn:api.research});
  const savedReports=researchItems(collection.data).filter(r=>r.kind==='report');
  const selected=draft.sections.filter(s=>s.enabled);
  const hasResults=selected.some(s=>reportSections.find(v=>v.id===s.id)?.kind==='Results');
  const hasContext=selected.some(s=>reportSections.find(v=>v.id===s.id)?.kind==='Census context');
  const preview=useQuery({queryKey:['composed-report',renderRequest],queryFn:({signal})=>previewReport(renderRequest,signal),retry:false,staleTime:30_000});
  const isDirty=JSON.stringify(draft)!==JSON.stringify(renderRequest);
  const figureCount=preview.data?.sections.reduce((sum,s)=>sum+s.figures.length,0)??0;
  const tableCount=preview.data?.sections.reduce((sum,s)=>sum+s.tables.length,0)??0;
  const rows=preview.data?.sections.reduce((sum,s)=>sum+s.tables.reduce((t,v)=>t+v.rows.length,0),0)??0;
  function patch(value:Partial<ReportRequest>){setDraft(current=>({...current,...value}));}
  function restore(saved:ResearchObject){
    const request=saved.view?.report_request as ReportRequest|undefined;
    if(request){setDraft(request);setRenderRequest(request);}
    else{
      const legacy=initialReport(ctx),ids=Array.isArray(saved.view?.sections)?saved.view.sections as string[]:[];
      const mapping:Record<string,string[]>={overview:['summary'],voting:['ev_trajectory','ev_changes'],geography:['ev_map','ev_places'],polls:['polls'],sources:['evidence']};
      const translated=ids.flatMap(id=>mapping[id]??[]);
      const next={...legacy,title:saved.title,notes:saved.body??'',include_notes:saved.view?.include_notes===true,query:(saved.view?.query as ReportRequest['query'])??legacy.query,
        sections:legacy.sections.map(s=>({...s,enabled:translated.includes(s.id)}))};
      if(!next.sections.some(s=>s.enabled))next.sections[0].enabled=true;
      setDraft(next);setRenderRequest(next);
    }
    setSavedId(saved.id);loadedId.current=saved.id;notify(`Opened saved report: ${saved.title}`);
  }
  useEffect(()=>{
    const id=Number(new URLSearchParams(location.search).get('research_id'));
    if(id&&loadedId.current!==id){const saved=savedReports.find(r=>r.id===id);if(saved)restore(saved);}
  },[collection.data]); // Exact saved report is restored once, without following background refreshes.
  function chooseTemplate(id:string){
    const value=reportTemplates.find(t=>t.id===id)!;
    const ordered=[...value.sections,...reportSections.map(s=>s.id).filter(s=>!value.sections.includes(s))];
    patch({template:id,title:`${stateName(draft.query.state)} · ${value.label}`,sections:ordered.map(id=>({id,enabled:value.sections.includes(id),caption:draft.sections.find(s=>s.id===id)?.caption??''}))});
  }
  function changeSection(id:string,value:Partial<ReportSectionChoice>){patch({sections:draft.sections.map(s=>s.id===id?{...s,...value}:s)});}
  function move(id:string,direction:number){const items=[...draft.sections],i=items.findIndex(s=>s.id===id);[items[i],items[i+direction]]=[items[i+direction],items[i]];patch({sections:items});}
  async function save(){
    setBusy('save');
    try{
      // Saved locally even when private notes are excluded from exports.
      const request=preview.data&&!isDirty?{...draft,query:preview.data.request.query}:draft;
      const payload={kind:'report',title:draft.title,body:draft.notes,view:{page:'reports',query:request.query,report_request:request,template:draft.template}};
      const item=savedId?await api.updateResearch(savedId,payload):await api.saveResearch(payload);
      setSavedId(item.id);loadedId.current=item.id;cache.invalidateQueries({queryKey:['research']});notify('Report layout, evidence revision and notes saved locally.');
    }catch(e){notify((e as Error).message);}finally{setBusy('');}
  }
  async function download(format:string){
    setBusy(format);
    try{
      const exact=preview.data&&!isDirty?{...draft,query:preview.data.request.query}:draft;
      await exportComposedReport(exact,format);notify(format==='pdf'&&isPublicMode()?'Printable report opened. Choose Save as PDF in your browser.':`${format.toUpperCase()} exported with the report layout and source references.`);
    }catch(e){notify((e as Error).message);}finally{setBusy('');}
  }
  function useCurrent(){const next=initialReport(ctx);setDraft({...draft,query:next.query,results:{...draft.results,geography_ids:next.results.geography_ids}});notify('Current investigation copied into the draft. Refresh the preview to apply it.');}
  const selectionText=useMemo(()=>draft.query.geography_ids.length?`${draft.query.geography_ids.length} selected places`:'Statewide participation',[draft.query.geography_ids]);
  return <>
    <div className="page-intro no-print"><div><span className="eyebrow">RESEARCH → PUBLISH</span><h2>Your evidence. A report worth reading.</h2><p>Compose sourced maps, charts and findings into one reproducible research packet.</p></div><Badge tone="violet"><FileChartColumnIncreasing size={13}/> Report studio</Badge></div>
    <div className="report-studio-meta"><span><LockKeyhole size={14}/> Pinned revision {draft.query.revision??'latest'}</span><span>{stateName(draft.query.state)} · {draft.query.cycle}</span><span>{selectionText}</span><span>{draft.query.as_of?`Cutoff ${draft.query.as_of.slice(0,10)}`:'Revision cutoff'}</span><button className="text-button" onClick={useCurrent}><RefreshCw size={13}/> Use current investigation</button></div>
    <div className="report-studio">
      <aside className="report-studio-controls">
        <Panel title="1. Start with a useful template">
          <Field label="Report template"><Select label="Report template" value={draft.template} onChange={chooseTemplate} options={reportTemplates.map(t=>({value:t.id,label:t.label}))}/></Field>
          <p className="report-control-help">{reportTemplates.find(t=>t.id===draft.template)?.description}</p>
          <Field label="Report title"><input maxLength={250} value={draft.title} onChange={e=>patch({title:e.target.value})}/></Field>
          <details className="report-scope-details"><summary><Settings2 size={14}/> Evidence and comparison settings <ChevronDown size={13}/></summary>
            <p>Participation uses the pinned investigation above. Historical results and Census context retain their own definitions.</p>
            {hasResults&&<>
              <div className="report-fields-two"><Field label="Election year"><input type="number" min="1700" max="2100" value={draft.results.year} onChange={e=>patch({results:{...draft.results,year:Number(e.target.value)}})}/></Field><Field label="Baseline year"><input type="number" min="1700" max="2100" value={draft.results.baseline??''} onChange={e=>patch({results:{...draft.results,baseline:e.target.value?Number(e.target.value):null}})}/></Field></div>
              <Field label="Historical office"><Select label="Historical report office" value={draft.results.office} onChange={office=>patch({results:{...draft.results,office,contest_id:null}})} options={[{value:'PRESIDENT',label:'President'},{value:'US SENATE',label:'U.S. Senate'},{value:'US HOUSE',label:'U.S. House'},{value:'GOVERNOR',label:'Governor'},{value:draft.results.office,label:draft.results.office}].filter((v,i,a)=>a.findIndex(r=>r.value===v.value)===i)}/></Field>
              <Field label="Reporting geography"><Select label="Report reporting geography" value={draft.results.geography_level} onChange={value=>patch({results:{...draft.results,geography_level:value as ReportRequest['results']['geography_level'],geography_ids:[],offset:0}})} options={['state','county','district','municipality','precinct'].map(value=>({value,label:value[0].toUpperCase()+value.slice(1)}))}/></Field>
              <Field label="Results map"><Select label="Report map measure" value={draft.map_metric} onChange={value=>patch({map_metric:value as ReportRequest['map_metric']})} options={[{value:'dem_margin_pp',label:'Democratic margin (D minus R)'},{value:'total_votes',label:'Candidate votes (symbol area)'}]}/></Field>
              <p className="report-control-help">Precinct reports include one complete page of up to 200 places. Unverified boundaries remain tables; no county polygon stands in for a precinct.</p>
            </>}
            {hasContext&&<Field label="Resident context"><Select label="Report Census metric" value={draft.context_metric} onChange={value=>patch({context_metric:value as ReportRequest['context_metric']})} options={[{value:'population',label:'Resident population'},{value:'median_age',label:'Median age'},{value:'median_household_income',label:'Median household income'}]}/></Field>}
          </details>
          {savedReports.length>0&&<Field label="Open a saved report"><Select label="Open saved report" value={String(savedId??'')} onChange={id=>{const saved=savedReports.find(r=>r.id===Number(id));if(saved)restore(saved);}} options={[{value:'',label:'Choose a saved layout…'},...savedReports.map(r=>({value:String(r.id),label:r.title}))]}/></Field>}
        </Panel>
        <Panel title="2. Arrange the story">
          <p className="report-control-help">Choose sections, move them into reading order, and add figure captions. Maps, charts and their full tables travel together.</p>
          <div className="report-composer-sections">{draft.sections.map((choice,index)=>{const section=reportSections.find(s=>s.id===choice.id)!;return <div key={choice.id} className={`report-composer-section ${choice.enabled?'enabled':''}`}>
            <div className="report-choice-row"><GripVertical size={13} aria-hidden="true"/><label><input type="checkbox" checked={choice.enabled} onChange={e=>changeSection(choice.id,{enabled:e.target.checked})}/><span>{section.title}<small>{section.kind}</small></span></label><button className="icon-button" title="Move section up" aria-label={`Move ${section.title} up`} disabled={index===0} onClick={()=>move(choice.id,-1)}><ArrowUp size={13}/></button><button className="icon-button" title="Move section down" aria-label={`Move ${section.title} down`} disabled={index===draft.sections.length-1} onClick={()=>move(choice.id,1)}><ArrowDown size={13}/></button></div>
            {choice.enabled&&<><p>{section.description}</p><button className="text-button" onClick={()=>setActiveSection(activeSection===choice.id?'':choice.id)}>{choice.caption?'Edit researcher caption':'Add a caption'}</button>{activeSection===choice.id&&<textarea rows={3} maxLength={4000} aria-label={`Caption for ${section.title}`} placeholder="Your explanation, labeled separately from measured evidence." value={choice.caption} onChange={e=>changeSection(choice.id,{caption:e.target.value})}/>}</>}
          </div>;})}</div>
          <Field label="Personal research notes"><textarea rows={4} maxLength={30000} value={draft.notes} onChange={e=>patch({notes:e.target.value})} placeholder="Interpretation, questions and follow-up. Saved locally."/></Field>
          <label className="checkbox-label"><input type="checkbox" checked={draft.include_notes} onChange={e=>patch({include_notes:e.target.checked})}/> Explicitly include my private notes in preview and exports</label>
        </Panel>
        <Panel title="3. Preview, save and export">
          <button className="button primary wide" disabled={!selected.length||!draft.title.trim()||preview.isFetching} onClick={()=>setRenderRequest({...draft})}>{preview.isFetching?<LoaderCircle size={15} className="spin"/>:<Eye size={15}/>} {preview.isFetching?'Building sourced preview…':'Update preview'}</button>
          <div className="report-export-grid"><button className="button secondary" disabled={!!busy||!selected.length} onClick={()=>download('pdf')}>{busy==='pdf'?'Preparing…':'PDF'}</button><button className="button secondary" disabled={!!busy||!selected.length} onClick={()=>download('html')}>HTML</button><button className="button secondary" disabled={!!busy||!selected.length} onClick={()=>download(isPublicMode()?'json':'zip')}>{isPublicMode()?'Research JSON':busy==='zip'?'Packaging…':'Research ZIP'}</button><button className="button secondary" disabled={!!busy||!selected.length} onClick={()=>download('csv')}>Tables CSV</button></div>
          <button className="button secondary wide" disabled={!!busy||!selected.length} onClick={save}><Save size={14}/> {savedId?'Update saved report':'Save report configuration'}</button>
          {savedId&&<button className="text-button" onClick={()=>{setSavedId(undefined);notify('The next save will create a separate report.');}}>Save a separate copy</button>}
          <Notice>{isPublicMode()?"Compose published sections privately in your browser. Export HTML, tables CSV or a research JSON packet; PDF opens your browser’s print dialog. Unsupported evidence selections are explained explicitly. Full ZIP packaging remains available in the local edition.":"Research ZIP includes a printable PDF, HTML, individual SVG figures, tables, exact layout, query and source hashes. Raw voter records are excluded."}</Notice>
        </Panel>
      </aside>
      <div className="report-studio-reading">
        <div className="report-preview-toolbar"><div><Badge tone="teal"><Eye size={12}/> Exact export preview</Badge><small>{figureCount} figures · {tableCount} tables · {rows.toLocaleString()} evidence rows</small></div><button className="text-button" onClick={()=>setShowSources(!showSources)}><Table2 size={13}/> {showSources?'Hide':'Inspect'} evidence</button></div>
        {isDirty&&<div className="report-draft-notice"><FileText size={15}/><span>The draft has changes. Update the preview to see their exact figures and wording.</span><button onClick={()=>setRenderRequest({...draft})} disabled={!selected.length}>Update preview</button></div>}
        {preview.isError&&<div className="report-preview-error"><h3>The report needs attention</h3><p>{(preview.error as Error).message}</p><button className="button secondary" onClick={()=>preview.refetch()}>Try again</button></div>}
        {preview.isFetching&&!preview.data&&<div className="report-loading"><LoaderCircle size={25} className="spin"/><h3>Composing your evidence packet</h3><p>Reading the pinned revision, calculating figures and attaching original source references.</p></div>}
        {showSources&&preview.data&&<div className="report-evidence-summary"><h3>What this report contains</h3><p><b>Revision {preview.data.revision}</b> · {preview.data.sources.length} archived source documents · {preview.data.boundary_files.length} hashed boundary files</p><ol>{preview.data.sources.map(source=><li key={source.id}><a href={source.url} target="_blank" rel="noreferrer">Snapshot {source.id} · Original source</a><code>{source.sha256}</code></li>)}</ol><p>Content fingerprint</p><code>{preview.data.content_sha256}</code><p>Reproduction validates the same data, layout, archives and geographic files.</p></div>}
        {preview.data&&<iframe ref={previewFrame} className="report-document-frame" sandbox="allow-same-origin" srcDoc={preview.data.html} title={`${draft.title} — exact report preview`} onLoad={()=>{const iframe=previewFrame.current;if(iframe?.contentDocument){const body=iframe.contentDocument.body;iframe.style.height=`${Math.max(1100,body.scrollHeight+24)}px`;}}}/>}
        {preview.data&&<p className="report-proof-line"><Check size={13}/> Preview, PDF and SVG use the same figure geometry and values. Personal notes {draft.include_notes?'explicitly included':'excluded from exports'}.</p>}
      </div>
    </div>
  </>;
}
