import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { DOMParser } from 'linkedom';
import { createServer } from 'vite';

test('public office composition removes replaced and disabled original DOM sections', async t => {
  const server = await createServer({root:fileURLToPath(new URL('..',import.meta.url)),configFile:false,optimizeDeps:{noDiscovery:true,include:[]},server:{middlewareMode:true,watch:null,hmr:false,ws:false},appType:'custom'});
  const originals = {fetch:globalThis.fetch,window:globalThis.window,DOMParser:globalThis.DOMParser};
  t.after(async()=>{ Object.assign(globalThis,originals); await server.close(); });
  globalThis.DOMParser = DOMParser;
  globalThis.window = {OBSERVATORY_PUBLIC_MODE:true,dispatchEvent(){}};
  const fixture = JSON.parse(await readFile(new URL('./fixtures/office-races-r593.json',import.meta.url),'utf8'));
  const query = {state:'OH',cycle:2026,revision:593,as_of:'2026-10-21'};
  const request = {query,title:'Ohio governor report',template:'office',race_id:fixture.GOVERNOR.id,results:{office:'GOVERNOR'},notes:'',include_notes:false,sections:[{id:'office_call',enabled:true,caption:''},{id:'summary',enabled:true,caption:''}]};
  const base = {revision:593,request:{...request,results:{office:'PRESIDENT'}},sources:[],limitations:[],content_sha256:'a'.repeat(64),sections:[{id:'summary',title:'Old summary',figures:[],tables:[]},{id:'polls',title:'Old polls',figures:[],tables:[]}],html:'<!doctype html><html><head><title>State packet</title></head><body><main><header><h1>Original report</h1></header><section id="section-summary"><p>INHERITED SENATE AVERAGE</p></section><section id="section-polls"><p>DISABLED SENATE POLL TABLE</p></section><footer>Reproducibility</footer></main></body></html>'};
  const publication = {schema_version:'observatory-public-v1',dataset_revision:593,published_at:'2026-10-21T12:00:00Z',data_as_of:'2026-10-21',reports:{OH:'objects/report.json'},requests:{'/api/v2/forecasts/offices?as_of=2026-10-21&cycle=2026&office=GOVERNOR&revision=593':'objects/governor.json'}};
  globalThis.fetch = async input => {
    const path = new URL(String(input),'https://test.invalid').pathname;
    if(path.endsWith('/manifest.json')) return Response.json(publication);
    if(path.endsWith('/objects/report.json')) return Response.json(base);
    if(path.endsWith('/objects/governor.json')) return Response.json({calls:[fixture.GOVERNOR],sources:[]});
    assert.fail('Unexpected fixture request: '+path);
  };
  const {previewPublicReport} = await server.ssrLoadModule('/src/publicReports.ts');
  const report = await previewPublicReport(request);
  assert.doesNotMatch(report.html,/INHERITED SENATE AVERAGE|DISABLED SENATE POLL TABLE/);
  assert.match(report.html,/Senate polling summaries and model estimates are excluded/);
  assert.equal((report.html.match(/id="section-summary"/g)||[]).length,1);
  assert.equal(report.sections.length,2);
  assert.ok(report.html.includes(fixture.GOVERNOR.finding));
  assert.match(base.html,/INHERITED SENATE AVERAGE/);
});
