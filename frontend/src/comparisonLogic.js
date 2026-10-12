// Pure comparison logic. No backend calls and no change to recommendation scoring.
export const MIN_RADAR_MENTIONS = 10;

export function finiteNumber(value) {
  if (value === null || value === undefined || value === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

export function numericExtremes(items, valueOf, better = "higher") {
  const entries = items.map((item) => finiteNumber(valueOf(item)));
  const valid = entries.filter((n) => n !== null);
  if (valid.length < 2) return entries.map(() => null);
  const min = Math.min(...valid), max = Math.max(...valid);
  if (Math.abs(max - min) < 1e-9) return entries.map(() => null);
  return entries.map((value) => value === null ? null :
    value === (better === "lower" ? min : max) ? "best" :
      value === (better === "lower" ? max : min) ? "worst" : null);
}

// Coverage is an absolute ratio, not a relative ranking or evidence strength.
// Invalid and zero-denominator values are left unhighlighted.
export function selectedEvidenceCoverage(item) {
  const covered = finiteNumber(item?.selected_aspects_with_evidence);
  const selected = finiteNumber(item?.selected_aspects);
  if (covered === null || selected === null || !Number.isInteger(covered) ||
      !Number.isInteger(selected) || selected <= 0 || covered < 0 || covered > selected) return null;
  return covered === selected ? "full" : covered === 0 ? "none" : "partial";
}

export function aspectScore(aspect) {
  if (!aspect || finiteNumber(aspect.mention_count) === null || Number(aspect.mention_count) <= 0) return null;
  const value = finiteNumber(aspect.adjusted_score);
  return value === null ? null : Math.max(0, Math.min(100, value * 100));
}

function byName(a, b) { return a.aspect_name.localeCompare(b.aspect_name); }

export function sortedAspects(aspects, aspectMaps, reference = "alphabetical", order = "desc", items = []) {
  if (reference === "alphabetical") return [...aspects].sort(byName);
  const index = items.findIndex((item) => item.laptop_id === reference);
  function scoreOf(aspect) {
    if (reference === "average") {
      const scores = aspectMaps.map((map) => aspectScore(map.get(aspect.aspect_id))).filter((value) => value !== null);
      return scores.length ? scores.reduce((a, b) => a + b, 0) / scores.length : null;
    }
    return index < 0 ? null : aspectScore(aspectMaps[index].get(aspect.aspect_id));
  }
  return [...aspects].sort((a, b) => {
    const first = scoreOf(a), second = scoreOf(b);
    if (first === null && second !== null) return 1; // N/A is always last.
    if (second === null && first !== null) return -1;
    if (first === null && second === null) return byName(a, b);
    return (order === "asc" ? first - second : second - first) || byName(a, b);
  });
}

export function radarSelection(aspects, aspectMaps, count = 4, minimumMentions = MIN_RADAR_MENTIONS, direction = "top") {
  const selectedByLaptop = aspectMaps.map((map) =>
    aspects.map((aspect) => {
      const data = map.get(aspect.aspect_id);
      return { ...aspect, score: aspectScore(data), mentions: Number(data?.mention_count ?? 0) };
    }).filter((item) => item.score !== null && item.mentions >= minimumMentions)
      .sort((a, b) => (direction === "top" ? b.score - a.score : a.score - b.score) || byName(a, b))
      .slice(0, count)
  );
  const included = new Set(selectedByLaptop.flatMap((part) => part.map((aspect) => aspect.aspect_id)));
  const axes = aspects.filter((aspect) => included.has(aspect.aspect_id));
  // Order axes by average of available direct scores, never by nonexistent zeros.
  const ordered = sortedAspects(axes, aspectMaps, "average", direction === "top" ? "desc" : "asc");
  return { axes: ordered, selectedByLaptop };
}

export function specificationSummaries(items) {
  const specs = [
    { key: "price_usd", label: "listed price", better: "lower", unit: "USD", number: (n) => `$${n.toFixed(2)}` },
    { key: "ram_gb", label: "RAM capacity", better: "higher", number: (n) => `${n} GB` },
    { key: "storage_gb", label: "storage capacity", better: "higher", number: (n) => `${n} GB` },
    { key: "refresh_rate_hz", label: "refresh rate", better: "higher", number: (n) => `${n} Hz` },
    { key: "weight_lb", label: "listed weight", better: "lower", number: (n) => `${n} lb` },
  ];
  const properties = specs.map((spec) => ({
    ...spec,
    extremes: numericExtremes(items, (item) => item[spec.key], spec.better),
    numbers: items.map((item) => finiteNumber(item[spec.key])),
  }));
  return items.map((item, index) => {
    const factEntries = [];
    if (finiteNumber(item.price_usd) !== null) factEntries.push([{ text: "price: " }, { text: `$${Number(item.price_usd).toFixed(2)}`, emphasis: true }]);
    if (item.processor) factEntries.push([{ text: "processor: " }, { text: item.processor, emphasis: true }]);
    if (item.gpu) factEntries.push([{ text: "graphics: " }, { text: item.gpu, emphasis: true }]);
    if (finiteNumber(item.ram_gb) !== null) factEntries.push([{ text: `${item.ram_gb} GB RAM`, emphasis: true }]);
    if (finiteNumber(item.storage_gb) !== null) factEntries.push([{ text: `${item.storage_gb} GB storage`, emphasis: true }]);
    if (finiteNumber(item.screen_size_in) !== null) factEntries.push([{ text: `${item.screen_size_in}-inch screen`, emphasis: true }]);
    if (item.screen_resolution) factEntries.push([{ text: "resolution: " }, { text: item.screen_resolution, emphasis: true }]);
    if (finiteNumber(item.refresh_rate_hz) !== null) factEntries.push([{ text: "refresh rate: " }, { text: `${item.refresh_rate_hz} Hz`, emphasis: true }]);
    if (finiteNumber(item.weight_lb) !== null) factEntries.push([{ text: "weight: " }, { text: `${item.weight_lb} lb`, emphasis: true }]);

    const factsParts = factEntries.length
      ? [ { text: "Listed specifications include " },
          ...factEntries.flatMap((entry, entryIndex) => entryIndex ? [{ text: ", " }, ...entry] : entry),
          { text: "." } ]
      : [{ text: "Several specifications are unavailable in the current comparison data." }];

    const differences = properties.flatMap((property) => {
      const status = property.extremes[index], number = property.numbers[index];
      if (!status || number === null) return [];
      const favorable = status === "best";
      const direction = (property.better === "lower") === favorable ? "lowest" : "highest";
      return [{ text: `${direction} ${property.label} among these laptops (${property.number(number)})`, tone: status }];
    });
    const differenceParts = differences.length
      ? [{ text: "In this comparison, it has the " },
         ...differences.flatMap((entry, entryIndex) => entryIndex ? [{ text: "; the " }, entry] : [entry]),
         { text: "." }]
      : [{ text: "No uniquely different numeric extremes are identified for this laptop." }];
    return {
      name: item.laptop || `Laptop ${index + 1}`,
      facts: factsParts.map((part) => part.text).join(""),
      differences: differenceParts.map((part) => part.text).join(""),
      factsParts, differenceParts,
    };
  });
}

// Geometry and collision-aware labels for a shared-aspect SVG radar chart.
// Using text labels rather than axis numbers keeps the chart readable without
// requiring a lookup in the table beneath it. These functions are UI-only.
export function wrapRadarLabel(text, maxChars = 22) {
  const words = String(text ?? "").trim().split(/\s+/).filter(Boolean);
  const lines = [];
  let current = "";
  for (const word of words) {
    const next = current ? `${current} ${word}` : word;
    if (next.length > maxChars && current) {
      lines.push(current);
      current = word;
    } else {
      current = next;
    }
  }
  if (current) lines.push(current);
  return lines.length ? lines : [""];
}

export function radarLabelLayout(axes) {
  const width = 1060;
  const height = axes.length >= 13 ? 760 : 660;
  const center = { x: width / 2, y: height / 2 };
  const radius = 205;
  const count = axes.length;
  const labels = axes.map((aspect, index) => {
    const angle = -Math.PI / 2 + 2 * Math.PI * index / count;
    const cos = Math.cos(angle);
    const sin = Math.sin(angle);
    const nearVertical = Math.abs(cos) < 0.16;
    const side = nearVertical ? (sin < 0 ? "top" : "bottom") : cos < 0 ? "left" : "right";
    const x = side === "left" ? 278 : side === "right" ? 782 : center.x;
    const y = side === "top" ? center.y - radius - 55
      : side === "bottom" ? center.y + radius + 55
        : center.y + (radius + 24) * sin;
    return {
      aspect_id: aspect.aspect_id, aspect_name: aspect.aspect_name, index,
      side, x, y,
      anchor: side === "left" ? "end" : side === "right" ? "start" : "middle",
      lines: wrapRadarLabel(aspect.aspect_name),
    };
  });

  // Distribute labels separately along each side, keeping their relative axis
  // order and a comfortable minimum gap even for unions of up to 18 aspects.
  for (const side of ["left", "right"]) {
    const group = labels.filter((label) => label.side === side).sort((a, b) => a.y - b.y);
    const margin = 66;
    const gap = 48;
    for (let i = 0; i < group.length; i++) {
      group[i].y = Math.max(group[i].y, i === 0 ? margin : group[i - 1].y + gap);
    }
    const overflow = group.length ? Math.max(0, group.at(-1).y - (height - margin)) : 0;
    if (overflow) for (const label of group) label.y -= overflow;
    const underflow = group.length ? Math.max(0, margin - group[0].y) : 0;
    if (underflow) for (const label of group) label.y += underflow;
  }
  return { width, height, center, radius, labels };
}
