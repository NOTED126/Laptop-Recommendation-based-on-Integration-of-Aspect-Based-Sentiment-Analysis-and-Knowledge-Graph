import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const src = fs.readFileSync(new URL('./src/App.jsx', import.meta.url), 'utf8');
const start = src.indexOf('function hasDirectReviewEvidence(aspect)');
const end = src.indexOf('function App() {', start);
assert.ok(start >= 0 && end > start, 'Could not find aspect-preview implementation');
const ctx = { RETIRED_ASPECT_IDS: new Set(['FEATURE_SET']) };
vm.createContext(ctx);
vm.runInContext(src.slice(start, end), ctx);

const aspects = (count) => Array.from({length: count}, (_, i) => ({
  aspect_id: `ASPECT_${i + 1}`,
  aspect_name: `Aspect ${i + 1}`,
  normalized_weight: (i + 1) / (count * (count + 1) / 2),
  mention_count: i % 4 === 0 ? 0 : 15,
  adjusted_score: (i + 1) / (count + 1),
  evidence_level: i % 4 === 0 ? 'no_evidence' : 'moderate',
}));

function run() {
  let x = aspects(8);
  assert.equal(ctx.getPreviewAspects(x, 'custom').length, 8, 'custom must show 8 of 8');
  assert.equal(ctx.getPreviewAspects(x, 'custom')[0].aspect_id, 'ASPECT_8', 'weighted rows sorted descending');
  assert.ok(ctx.getPreviewAspects(x, 'custom').some(a => a.mention_count === 0), 'weighted aspect without evidence retained');

  x = aspects(7);
  assert.equal(ctx.getPreviewAspects(x, 'guided').length, 7, 'guided refinement must show 7 of 7');
  x = aspects(23);
  assert.equal(ctx.getPreviewAspects(x, 'guided').length, 23, 'guided must not be capped at 6');
  assert.equal(ctx.getPreviewAspects(x, 'custom').length, 23, 'custom must not be capped at 6');
  assert.ok(ctx.getPreviewAspects(x, 'balanced').length <= 6, 'balanced must remain capped at six');

  const withRetired = [...aspects(8), {aspect_id: 'FEATURE_SET', aspect_name: 'Feature Set', normalized_weight: .5, mention_count: 12, adjusted_score: .9}];
  assert.equal(ctx.getPreviewAspects(withRetired, 'custom').length, 8, 'retired aspect excluded');
  const withZero = [...aspects(8), {aspect_id: 'ZERO', aspect_name: 'Zero', normalized_weight: 0, mention_count: 12, adjusted_score: .9}];
  assert.equal(ctx.getPreviewAspects(withZero, 'custom').length, 8, 'zero-weight aspect excluded');

  assert.match(src, /candidate_laptop_ids:\s*guidedShortlist\.candidateIds/, 'Stage 2 must lock candidate set');
  assert.match(src, /initial_weights:\s*guidedShortlist\.initialWeights/, 'Stage 2 must preserve initial weights');
  assert.match(src, /refined_weights:\s*Object\.fromEntries/, 'Stage 2 must transmit refined weights');
  assert.match(src, /guided-shortlist-explanation/, 'visible shortlist explanation required');
  assert.match(src, /Laptops excluded in Stage 1 are not reconsidered/, 'specific limitation required');
  console.log('PASS (all assertions): weighted 8/8, guided 7/7 and 23/23, balanced <=6, no-evidence, sorting, exclusions, locked shortlist, explanation.');
}
run();
