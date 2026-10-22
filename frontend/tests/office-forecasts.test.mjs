import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {createServer} from 'vite';
import React from 'react';
import {renderToString} from 'react-dom/server';

test('actual Ohio House and governor histories retain office, election year, full options and boundary caveats',async(t)=>{
  const server=await createServer({root:fileURLToPath(new URL('..',import.meta.url)),configFile:false,esbuild:{jsx:'automatic'},optimizeDeps:{noDiscovery:true,include:[]},server:{middlewareMode:true,watch:null,hmr:false,ws:false},appType:'custom'});
  t.after(()=>server.close());
  const {OfficeResultHistory}=await server.ssrLoadModule('/src/components/forecasts/OfficeForecastDesk.tsx');
  const {officeSummaryParagraphs}=await server.ssrLoadModule('/src/officeReport.ts');
  const fixtures=JSON.parse(await readFile(new URL('./fixtures/office-races-r593.json',import.meta.url),'utf8'));
  for(const office of ['US HOUSE','GOVERNOR']){
    const race=fixtures[office],before=JSON.stringify(race);
    const markup=renderToString(React.createElement(OfficeResultHistory,{race})).replace(/<!-- -->/g,'');
    assert.match(markup,/Actual R−D margin/);
    assert.match(markup,/Candidate votes/);
    assert.match(markup,/2022/);
    assert.match(markup,/Midterm/);
    assert.match(markup,/does not mean a tie/);
    assert.equal(JSON.stringify(race),before);
    assert.equal(race.validation.ev_model_promoted,false);
    const summary=officeSummaryParagraphs(race).join(' ');
    assert.match(summary,/Senate polling summaries and model estimates are excluded/);
    assert.match(summary,/No verified office-matched polling/);
    assert.ok(summary.includes(race.finding));
    if(office==='US HOUSE'){
      assert.match(markup,/Matching numbers do not establish matching geography/);
      assert.equal(race.call.margin_pp,null);
      assert.equal(race.district,1);
    }else{
      assert.match(markup,/Actual governor candidate-vote margins/);
      assert.equal(race.historical_reference.cycles.length,3);
    }
  }
});
