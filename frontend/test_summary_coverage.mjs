import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { selectedEvidenceCoverage } from './src/comparisonLogic.js';
import { splitExperienceSummary } from './src/summaryFormatting.js';

const coverageCases = [
  [{ selected_aspects_with_evidence: 3, selected_aspects: 3 }, 'full'],
  [{ selected_aspects_with_evidence: 2, selected_aspects: 3 }, 'partial'],
  [{ selected_aspects_with_evidence: 0, selected_aspects: 3 }, 'none'],
  [{ selected_aspects_with_evidence: 2, selected_aspects: 2 }, 'full'],
  [{ selected_aspects_with_evidence: '1', selected_aspects: '3' }, 'partial'],
  [{ selected_aspects_with_evidence: 0, selected_aspects: 0 }, null],
  [{ selected_aspects_with_evidence: 4, selected_aspects: 3 }, null],
  [{ selected_aspects_with_evidence: -1, selected_aspects: 3 }, null],
  [{ selected_aspects_with_evidence: 1.5, selected_aspects: 3 }, null],
  [{ selected_aspects_with_evidence: null, selected_aspects: 3 }, null],
  [{ selected_aspects_with_evidence: 1, selected_aspects: undefined }, null],
  [null, null],
];
for (const [row, expected] of coverageCases) {
  assert.equal(selectedEvidenceCoverage(row), expected, JSON.stringify(row));
}
// Partial is not upgraded when both compared laptops have identical partial coverage.
assert.equal(selectedEvidenceCoverage({ selected_aspects_with_evidence: 2, selected_aspects: 3 }), 'partial');
assert.equal(selectedEvidenceCoverage({ selected_aspects_with_evidence: 2, selected_aspects: 3 }), 'partial');

const examples = [
  'Predicted customer-review sentiment is predominantly positive for performance, touchscreen experience, and design.',
  'Users express predominantly favorable opinions regarding performance, gaming performance, and display quality.',
  'Negative review predictions outnumber positive predictions for fan noise. Feedback on battery life is divided; the lower adjusted sentiment scores should be interpreted cautiously.',
  'There are no notable weaknesses identified under the current policy thresholds.',
  'There are no notable areas meeting the threshold for primary weaknesses based on the current review set.',
  'The software experience and audio quality receive mixed or divided feedback from reviewers.',
  'An <img src=x onerror=alert(1)> is not executable when React renders text nodes.',
  'Ordinary punctuation, numbers, and unknown descriptions remain untouched.',
];
for (const sentence of examples) {
  const parts = splitExperienceSummary(sentence);
  assert.equal(parts.map(part => part.text).join(''), sentence, sentence);
  assert(parts.every(part => part.tone === null || ['aspect','positive','caution','neutral'].includes(part.tone)));
}
const s = splitExperienceSummary(examples[0]);
assert(s.some(p => p.text === 'predominantly positive' && p.tone === 'positive'));
assert(s.some(p => p.text === 'touchscreen experience' && p.tone === 'aspect'));
const n = splitExperienceSummary(examples[3]);
assert(n.some(p => p.text === 'no notable weaknesses identified' && p.tone === 'neutral'));
assert(!n.some(p => p.tone === 'positive'));
const warning = splitExperienceSummary(examples[2]);
assert(warning.some(p => p.text === 'Negative review predictions outnumber positive predictions' && p.tone === 'caution'));
assert(!warning.some(p => p.tone === 'positive'));
assert.deepEqual(splitExperienceSummary(null), []);
assert.deepEqual(splitExperienceSummary(''), []);
const app = readFileSync(new URL('./src/App.jsx', import.meta.url),'utf8');
const panel = readFileSync(new URL('./src/ComparisonPanel.jsx', import.meta.url),'utf8');
const css = readFileSync(new URL('./src/styles.css', import.meta.url),'utf8');
assert.match(app, /<ExperienceSummaryText text=\{laptop\.strengths_summary\}/);
assert.match(app, /<ExperienceSummaryText text=\{laptop\.weaknesses_summary\}/);
assert.match(app, /splitExperienceSummary\(text \|\| fallback\)/);
assert.doesNotMatch(app, /dangerouslySetInnerHTML/);
assert.match(panel, /coverage: true/);
assert.match(panel, /selectedEvidenceCoverage\(item\)/);
assert.match(panel, /Partial coverage/);
assert.match(panel, /Full coverage/);
assert.match(panel, /No coverage/);
assert.match(css, /\.laptop-summary-keyword-positive/);
assert.match(css, /\.compare-coverage-partial/);
console.log('PASS: evidence coverage states and edge cases, summary wording preservation, safe emphasis, and frontend wiring.');
