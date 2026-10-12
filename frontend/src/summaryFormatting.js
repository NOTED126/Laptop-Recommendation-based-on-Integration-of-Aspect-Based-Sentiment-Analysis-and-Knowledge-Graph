// Presentation-only formatting for approved, offline-generated review summaries.
// Never edits the summary text or treats it as HTML.
const aspectNames = [
  "software / os experience", "connectivity / ports", "reliability / stability",
  "design / form factor", "connectivity and ports", "overall system performance",
  "overall build quality", "touchscreen experience", "gaming performance",
  "thermal performance", "software experience", "connectivity and port selection",
  "biometric security", "display quality", "battery life", "audio quality",
  "camera quality", "build quality", "value for money", "ease of use",
  "charging", "fan noise", "trackpad", "touchscreen", "portability",
  "performance", "keyboard", "connectivity", "reliability", "stability",
  "design", "display", "audio", "ports",
];

const meaningfulPhrases = [
  { text: "negative review predictions outnumber positive predictions", tone: "caution" },
  { text: "negative predictions outnumber positive ones", tone: "caution" },
  { text: "negative predictions outnumber positive predictions", tone: "caution" },
  { text: "no notable areas meeting the threshold for primary weaknesses", tone: "neutral" },
  { text: "no notable weaknesses identified", tone: "neutral" },
  { text: "no significant weaknesses identified", tone: "neutral" },
  { text: "no clearly supported weaknesses identified", tone: "neutral" },
  { text: "no clearly supported strengths identified", tone: "neutral" },
  { text: "predominantly negative sentiment", tone: "caution" },
  { text: "mostly neutral or mixed predictions", tone: "caution" },
  { text: "mixed or divided feedback", tone: "caution" },
  { text: "mixed or divided sentiment", tone: "caution" },
  { text: "mixed and negative predictions", tone: "caution" },
  { text: "mixed or divided", tone: "caution" },
  { text: "lower adjusted sentiment scores", tone: "caution" },
  { text: "negative sentiment", tone: "caution" },
  { text: "remains divided", tone: "caution" },
  { text: "is divided", tone: "caution" },
  { text: "divided feedback", tone: "caution" },
  { text: "predominantly positive", tone: "positive" },
  { text: "predominantly favorable", tone: "positive" },
  { text: "strong positive sentiment", tone: "positive" },
  { text: "positive feedback", tone: "positive" },
  { text: "favorable opinions", tone: "positive" },
  { text: "favorable impressions", tone: "positive" },
  { text: "high praise", tone: "positive" },
];

const terms = [
  ...meaningfulPhrases,
  ...aspectNames.map((text) => ({ text, tone: "aspect" })),
].sort((a, b) => b.text.length - a.text.length);
const toneByTerm = new Map(terms.map((item) => [item.text, item.tone]));
const quoteRegex = (text) => text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const matchTerms = new RegExp(`\\b(?:${terms.map(({text}) => quoteRegex(text)).join("|")})\\b`, "gi");

/** Return plain and emphasized segments, preserving every character verbatim. */
export function splitExperienceSummary(text) {
  const value = typeof text === "string" ? text : "";
  if (!value) return [];
  const segments = [];
  let lastEnd = 0;
  // A fresh regex per call avoids cross-render shared lastIndex state.
  for (const match of value.matchAll(new RegExp(matchTerms.source, "gi"))) {
    const index = match.index;
    if (index > lastEnd) segments.push({ text: value.slice(lastEnd, index), tone: null });
    segments.push({ text: match[0], tone: toneByTerm.get(match[0].toLowerCase()) });
    lastEnd = index + match[0].length;
  }
  if (lastEnd < value.length) segments.push({ text: value.slice(lastEnd), tone: null });
  return segments;
}
