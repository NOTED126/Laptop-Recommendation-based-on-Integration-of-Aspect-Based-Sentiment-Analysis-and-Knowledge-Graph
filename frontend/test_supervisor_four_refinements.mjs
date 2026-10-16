import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { radarLabelLayout, wrapRadarLabel, numericExtremes, specificationSummaries } from './src/comparisonLogic.js';

assert.deepEqual(wrapRadarLabel('Software / OS Experience'), ['Software / OS', 'Experience']);
const titles = ['Design / Form Factor','Reliability / Stability','Software / OS Experience','Battery Life','Display Quality','Thermal Performance','Connectivity / Ports','Camera Quality','Build Quality','Gaming Performance','Keyboard','Audio','Value for Money','Fan Noise','Ease of Use','Portability','Charging','Biometric Security'];
for (const n of [3, 4, 5, 6, 8, 12, 18]) {
  const axes = titles.slice(0, n).map((aspect_name, i) => ({ aspect_id: String(i), aspect_name }));
  const { width, height, labels } = radarLabelLayout(axes);
  assert.equal(labels.length, n);
  assert.equal(width, 1060);
  for (const label of labels) {
    assert(label.x > 0 && label.x < width);
    assert(label.y > 30 && label.y < height - 30);
    assert.equal(label.lines.join(' '), label.aspect_name);
  }
  for (const side of ['left','right']) {
    const sideLabels = labels.filter(x => x.side === side).sort((a, b) => a.y - b.y);
    for (let i = 1; i < sideLabels.length; i++) assert(sideLabels[i].y - sideLabels[i-1].y >= 47.999);
  }
}
const items = [
  { laptop_id: 'a', laptop: 'A', price_usd: 700, ram_gb: 16, storage_gb: 512, weight_lb: 4.5, refresh_rate_hz: 120, processor: 'CPU A', gpu: 'GPU A', screen_resolution: '1920×1200' },
  { laptop_id: 'b', laptop: 'B', price_usd: 900, ram_gb: 32, storage_gb: 1024, weight_lb: 4, refresh_rate_hz: 144, processor: 'CPU B', gpu: 'GPU B' },
  { laptop_id: 'c', laptop: 'C', price_usd: 900, ram_gb: 16, storage_gb: 512, weight_lb: 5, refresh_rate_hz: 144 },
];
const summaries = specificationSummaries(items);
assert.match(summaries[0].facts, /price: \$700\.00/);
assert.match(summaries[1].facts, /32 GB RAM/);
assert(summaries[0].factsParts.some(p=>p.emphasis && p.text==='$700.00'));
assert(summaries[0].differenceParts.some(p=>p.tone==='best' && p.text.includes('lowest listed price')));
assert(summaries[2].differenceParts.some(p=>p.tone==='worst' && p.text.includes('highest listed weight')));
for (const summary of summaries) {
  assert.equal(summary.factsParts.map(p=>p.text).join(''), summary.facts);
  assert.equal(summary.differenceParts.map(p=>p.text).join(''), summary.differences);
}
assert.deepEqual(numericExtremes([{x:87},{x:null},{x:80}], o=>o.x), ['best',null,'worst']);
assert.deepEqual(numericExtremes([{x:87},{x:87}], o=>o.x), [null,null]);
assert.deepEqual(numericExtremes([{x:87},{x:null}], o=>o.x), [null,null]);
const panel = readFileSync(new URL('./src/ComparisonPanel.jsx', import.meta.url), 'utf8');
const app = readFileSync(new URL('./src/App.jsx', import.meta.url), 'utf8');
const css = readFileSync(new URL('./src/styles.css', import.meta.url), 'utf8');
assert.match(panel, /radarLabelLayout\(axes\)/);
assert.match(panel, /label\.lines\.map/);
assert.match(panel, /compare-radar-score-best/);
assert.match(panel, /summary\.factsParts/);
assert.match(panel, /summary\.differenceParts/);
assert.doesNotMatch(panel, /Axes are numbered/);
assert.doesNotMatch(app, /<strong>Overall assessment<\/strong>/);
assert.match(app, /laptop\.strengths_summary \|\| laptop\.weaknesses_summary/);
assert.match(css, /compare-summary-extreme-best/);
console.log('PASS: named radar axes, label collision spacing, aspect highlighting, structured specifications, and omission of Overall assessment.');
