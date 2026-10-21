import test from 'node:test';
import assert from 'node:assert/strict';
import {marginCallLabel} from '../src/researchCallMath.ts';
test('research calls preserve Republican-minus-Democratic direction and units',()=>{
  assert.equal(marginCallLabel(3.04),'R +3.0');
  assert.equal(marginCallLabel(-5.12),'D +5.1');
  assert.equal(marginCallLabel(0),'Even');
});
test('missing or malformed research estimates never become an even race',()=>{
  for(const value of [null,undefined,NaN,Infinity,-Infinity])assert.equal(marginCallLabel(value),'Unavailable');
});
