import test from 'node:test';
import assert from 'node:assert/strict';
import {quantileThresholds,quantileBin,marginHistogram,pairedDifferences,sharedMarginMaximum,BIVARIATE_COLORS} from '../src/atlasDepthMath.ts';
import {createMapSpec} from '../src/mapSpec.ts';

test('bivariate thresholds ignore absent/nonfinite estimates and preserve equal-boundary groups',()=>{
  const thresholds=quantileThresholds([10,20,30,40,50,60,70,NaN,Infinity]);
  assert.deepEqual(thresholds,[30,50]);
  assert.equal(quantileBin(30,thresholds),0);
  assert.equal(quantileBin(50,thresholds),1);
  assert.equal(quantileBin(70,thresholds),2);
  assert.equal(BIVARIATE_COLORS.flat().length,9);
});
test('geographic margin distribution includes exact endpoints, excludes missing and malformed margins',()=>{
  const histogram=marginHistogram([-100,-1,0,100,null,NaN,101,-101]);
  assert.equal(histogram.reduce((n,row)=>n+row.count,0),4);
  assert.equal(histogram[0].count,1);
  assert.equal(histogram.at(-1).count,1);
  assert.equal(histogram.find(row=>row.start===0).count,1);
});
test('no difference graphic can promote an unreviewed boundary link or missing margin to a numeric change',()=>{
  const valid={id:'county:1',name:'One',current_votes:100,baseline_votes:90,current_margin_pp:10,baseline_margin_pp:5,change_pp:5,eligible:true};
  const rows=[valid,{...valid,id:'county:2',eligible:false,reason:'Boundary vintage unreviewed'},{...valid,id:'county:3',current_margin_pp:null},{...valid,id:'county:4',change_pp:null}];
  assert.deepEqual(pairedDifferences(rows).map(row=>row.id),['county:1']);
  assert.equal(sharedMarginMaximum(rows),10);
});
test('shared original-map domain uses both cycles including unmatched source extremes',()=>{
  assert.equal(sharedMarginMaximum([{current_margin_pp:-81,baseline_margin_pp:42},{current_margin_pp:20,baseline_margin_pp:null}]),81);
  assert.equal(sharedMarginMaximum([]),1);
});
test('a native precinct without a reported count remains missing instead of becoming a zero-volume observation',()=>{
  const row={id:'precinct:one',name:'Missing source area',type:'precinct',value:null,change:null,share:null,denominator:null,baseline_value:null,source_ids:[],observation_ids:[]};
  assert.equal(createMapSpec([row],'volume').value(row),null);
  assert.equal(createMapSpec([row],'margin').value(row),null);
});
test('both precinct renderers can consume authoritative uneven bins without inventing equal-width thresholds',()=>{
  const spec=createMapSpec([],'margin',undefined,{domain:[-100,100],bins:[-100,-5,0,5,100],colors:['blue','pale-blue','pale-red','red']});
  assert.equal(spec.color(-20),'blue');
  assert.equal(spec.color(-3),'pale-blue');
  assert.equal(spec.color(3),'pale-red');
  assert.equal(spec.color(20),'red');
  assert.equal(spec.color(100),'red');
});
