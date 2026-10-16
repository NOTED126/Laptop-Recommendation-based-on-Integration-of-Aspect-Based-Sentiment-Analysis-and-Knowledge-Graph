import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import {
  aspectScore, numericExtremes, radarSelection, sortedAspects, specificationSummaries,
} from './src/comparisonLogic.js';

const laptops = [
  { laptop_id: 'a', laptop: 'Laptop A', price_usd: 800, ram_gb: 16, storage_gb: 256, weight_lb: 3, refresh_rate_hz: 60, processor: 'Processor A' },
  { laptop_id: 'b', laptop: 'Laptop B', price_usd: 600, ram_gb: 32, storage_gb: 512, weight_lb: 4, refresh_rate_hz: 60, processor: 'Processor B' },
  { laptop_id: 'c', laptop: 'Laptop C', price_usd: 600, ram_gb: 8, storage_gb: 512, weight_lb: 5, refresh_rate_hz: 120, processor: 'Processor C' },
];
assert.deepEqual(numericExtremes(laptops, x => x.price_usd, 'lower'), ['worst','best','best']);
assert.deepEqual(numericExtremes(laptops, x => x.ram_gb, 'higher'), [null,'best','worst']);
assert.deepEqual(numericExtremes(laptops, x => x.refresh_rate_hz, 'higher'), ['worst','worst','best']);
assert.deepEqual(numericExtremes(laptops, x => x.weight_lb, 'lower'), ['best',null,'worst']);
assert.deepEqual(numericExtremes(laptops.map(x=>({ ...x, ram_gb: 16 })), x=>x.ram_gb), [null,null,null]);
assert.deepEqual(numericExtremes([{ ram_gb: null },{ ram_gb: 8 }, { ram_gb: 16 }],x=>x.ram_gb),[null,'worst','best']);
assert.deepEqual(numericExtremes([{ ram_gb: null },{ ram_gb: 16 }],x=>x.ram_gb),[null,null]);
assert.equal(aspectScore({ adjusted_score: 0.83, mention_count: 0 }),null);
assert.equal(aspectScore({ adjusted_score: 0.67, mention_count: 2 }),67);
assert.equal(aspectScore({ adjusted_score: 1.5, mention_count: 2 }),100);
assert.equal(aspectScore({ adjusted_score: NaN, mention_count: 2 }),null);

const names = ['Battery Life','Performance','Audio','Design','Keyboard','Portability','Display Quality'];
const aspects = names.map((name, i) => ({ aspect_id:'asp'+i, aspect_name:name }));
const maps = [
  new Map([0,1,2,3,4,5,6].map((id,i) => ['asp'+id,{adjusted_score:[.8,.96,.3,.92,.78,.6,.88][i],mention_count: i===6?0:20}])),
  new Map([0,1,2,3,4,5,6].map((id,i) => ['asp'+id,{adjusted_score:[.9,.5,.15,.8,.7,.94,.91][i],mention_count: i===2?2:25}])),
  new Map([0,1,2,3,4,5,6].map((id,i) => ['asp'+id,{adjusted_score:[.6,.99,.6,.3,.75,.98,.65][i],mention_count: i===4?0:30}])),
];
const top = radarSelection(aspects,maps,4,10,'top');
const bottom = radarSelection(aspects,maps,4,10,'bottom');
assert.equal(top.selectedByLaptop.length,3);
assert(top.selectedByLaptop.every(items=>items.length===4));
assert(bottom.selectedByLaptop.every(items=>items.length===4));
assert(top.axes.length>=4 && top.axes.length<=12);
assert(bottom.axes.length>=4 && bottom.axes.length<=12);
assert(!top.selectedByLaptop[0].some(a=>a.aspect_id==='asp6')); // no direct evidence
assert(!bottom.selectedByLaptop[1].some(a=>a.aspect_id==='asp2')); // insufficient if threshold 10
const all = radarSelection(aspects,maps,6,1,'top');
assert(all.selectedByLaptop.every(arr=>arr.length===6));
const refHigh=sortedAspects(aspects,maps,'a','desc',laptops);
const refLow=sortedAspects(aspects,maps,'a','asc',laptops);
assert.equal(refHigh[0].aspect_id,'asp1');
assert.equal(refLow[0].aspect_id,'asp2');
assert.equal(refHigh.at(-1).aspect_id,'asp6'); // N/A last even when descending
assert.equal(refLow.at(-1).aspect_id,'asp6');
assert.equal(sortedAspects(aspects,maps,'alphabetical')[0].aspect_name,'Audio');
const avg=sortedAspects(aspects,maps,'average','desc',laptops);
assert.equal(avg.length,aspects.length);
const sums=specificationSummaries(laptops);
assert.equal(sums.length,3);
assert.match(sums[1].differences,/lowest listed price/);
assert.match(sums[1].facts,/Processor B/);
assert.match(sums[0].differences,/lowest listed weight/);

const cmp=readFileSync(new URL('./src/ComparisonPanel.jsx',import.meta.url),'utf8');
const app=readFileSync(new URL('./src/App.jsx',import.meta.url),'utf8');
const api=readFileSync(new URL('./src/api.js',import.meta.url),'utf8');
assert.match(cmp,/RadarDashboard/);
assert.match(cmp,/Selected preferences/);
assert.match(cmp,/Sort by/);
assert.match(cmp,/specificationSummaries/);
assert.match(app,/RequestProgress/);
assert.match(app,/searchSlow/);
assert.match(api,/timeoutMs: 150000/);
console.log('PASS: numeric spec extremes/ties/missing, sentiment N/A, union radar selection, evidence threshold, aligned sorting, factual summaries, progress and timeout wiring.');
