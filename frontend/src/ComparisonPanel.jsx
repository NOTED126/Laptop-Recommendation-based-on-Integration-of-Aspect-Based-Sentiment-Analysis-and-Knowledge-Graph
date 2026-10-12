import { useEffect, useMemo, useState } from "react";
import { getLaptop } from "./api";
import {
  aspectScore, numericExtremes, radarSelection, sortedAspects,
  specificationSummaries, radarLabelLayout, selectedEvidenceCoverage,
} from "./comparisonLogic";

const RETIRED_ASPECT_IDS = new Set(["FEATURE_SET"]);
const ACCENT_COLORS = ["#3157d5", "#008e83", "#bb741e"];

function formatMoney(value) {
  if (value == null) return "Unavailable";
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(value);
}
function formatNumber(value, suffix = "") {
  return value == null ? "Unavailable" : `${value}${suffix}`;
}
function evidenceLabel(aspect) {
  return (aspect?.evidence_level || "no_evidence").replaceAll("_", " ");
}
function ComparisonCell({ children, first = false, className = "" }) {
  return <div className={`compare-cell ${first ? "compare-label-cell" : ""} ${className}`}>{children}</div>;
}

function ComparisonRow({ row, items }) {
  // Only explicitly configured numerical criteria receive comparative highlights.
  const highlights = row.metric
    ? numericExtremes(items, (item) => item[row.metric], row.better)
    : items.map(() => null);
  return (
    <div className="comparison-grid-row">
      <ComparisonCell first><strong>{row.label}</strong></ComparisonCell>
      {items.map((item, index) => {
        const coverage = row.coverage ? selectedEvidenceCoverage(item) : null;
        const coverageLabel = coverage === "full" ? "Full coverage" : coverage === "partial"
          ? "Partial coverage" : coverage === "none" ? "No coverage" : null;
        const cellClass = coverage ? `compare-coverage-${coverage}`
          : highlights[index] ? `compare-spec-${highlights[index]}` : "";
        return <ComparisonCell key={item.laptop_id} className={cellClass}>
          <span className="comparison-spec-value">{row.get(item)}</span>
          {coverageLabel && <span className="compare-coverage-label" title="Coverage indicates which selected aspects have at least one direct review mention; it does not measure evidence strength.">{coverageLabel}</span>}
          {highlights[index] && <span className="compare-extreme-label">
            {highlights[index] === "best" ? "Preferred numeric value" : "Other numeric extreme"}
          </span>}
        </ComparisonCell>;
      })}
    </div>
  );
}

function RadarPlot({ title, description, data, items, aspectMaps, plotId }) {
  const axes = data.axes;
  const count = axes.length;
  if (count < 3) return (
    <section className="compare-radar-card">
      <h3>{title}</h3><p>{description}</p>
      <p className="compare-radar-unavailable">Fewer than three aspects meet the current evidence requirement. Choose “All direct evidence” to include aspects with fewer reviews, or review the aspect table.</p>
    </section>
  );
  const { width, height, center, radius, labels } = radarLabelLayout(axes);
  const point = (i, score) => {
    const angle = -Math.PI / 2 + (2 * Math.PI * i) / count;
    return { x: center.x + radius * score / 100 * Math.cos(angle), y: center.y + radius * score / 100 * Math.sin(angle) };
  };
  const position = (i, score) => {
    const p = point(i, score);
    return `${p.x.toFixed(2)},${p.y.toFixed(2)}`;
  };
  const series = items.map((item, i) => ({
    item,
    color: ACCENT_COLORS[i],
    scores: axes.map((aspect) => aspectScore(aspectMaps[i].get(aspect.aspect_id))),
  }));
  return (
    <section className="compare-radar-card" aria-label={title}>
      <h3>{title}</h3>
      <p>{description}</p>
      <div className="compare-radar-legend">
        {series.map(({ item, color }, index) => (
          <span key={item.laptop_id}><i style={{ background: color }} aria-hidden="true"/>Laptop {index + 1}: {item.laptop}</span>
        ))}
      </div>
      <div className="compare-radar-plot-scroll">
        <svg viewBox={`0 0 ${width} ${height}`} className="compare-radar-svg" role="img"
          aria-label={`${title}: overlaid adjusted sentiment scores for ${items.length} laptops on ${count} common aspect axes; missing review evidence is omitted, not plotted as zero.`}>
          <title>{title}</title>
          {[20, 40, 60, 80, 100].map((tick) => (
            <g key={tick}>
              <polygon points={axes.map((_, i) => position(i, tick)).join(" ")}
                fill="none" stroke="#dfe6f2" strokeWidth="1" />
              <text x={center.x + 6} y={center.y - radius * tick / 100 - 3} fontSize="9" fill="#7a8496">{tick}</text>
            </g>
          ))}
          {axes.map((aspect, i) => {
            const outer = point(i, 100);
            const label = labels[i];
            const leaderStart = point(i, 106);
            const leaderEnd = {
              x: label.side === "left" ? label.x + 7 : label.side === "right" ? label.x - 7 : label.x,
              y: label.y,
            };
            return <g key={aspect.aspect_id}>
              <line x1={center.x} y1={center.y} x2={outer.x} y2={outer.y} stroke="#e1e6f0" />
              <line x1={leaderStart.x} y1={leaderStart.y} x2={leaderEnd.x} y2={leaderEnd.y}
                stroke="#d5ddeb" strokeWidth="1" />
              <text x={label.x} y={label.y} fontSize="14" fontWeight="650" fill="#344054"
                textAnchor={label.anchor}>
                <title>{aspect.aspect_name}</title>
                {label.lines.map((line, lineIndex) => <tspan key={lineIndex} x={label.x}
                  dy={lineIndex === 0 ? -8 * (label.lines.length - 1) : 16}>{line}</tspan>)}
              </text>
            </g>;
          })}
          {series.map(({ item, color, scores }) => {
            const full = scores.every((score) => score !== null);
            const segments = scores.flatMap((score, i) => {
              const next = (i + 1) % count;
              if (score === null || scores[next] === null) return [];
              const p1 = point(i, score), p2 = point(next, scores[next]);
              return [<line key={`${i}-${next}`} x1={p1.x} y1={p1.y} x2={p2.x} y2={p2.y}
                stroke={color} strokeWidth="2.5" strokeLinecap="round"/>];
            });
            return <g key={item.laptop_id}>
              {full && <polygon points={scores.map((score, i) => position(i, score)).join(" ")}
                fill={color} fillOpacity="0.095" stroke="none" />}
              {segments}
              {scores.map((score, i) => score === null ? null : (
                <circle key={axes[i].aspect_id} cx={point(i, score).x} cy={point(i, score).y}
                  r="4" fill={color} stroke="white" strokeWidth="1.5">
                  <title>{item.laptop} — {axes[i].aspect_name}: {score.toFixed(1)}/100</title>
                </circle>
              ))}
            </g>;
          })}
        </svg>
      </div>
      <p className="compare-radar-caption">Aspect names label the shared axes for all compared laptops. On smaller screens, scroll horizontally to read every label. Missing review evidence produces gaps, not zero-valued points.</p>
      <div className="compare-radar-score-legend" role="note">
        <span className="compare-radar-score compare-radar-score-best">Highest available score</span>
        <span className="compare-radar-score compare-radar-score-worst">Lowest available score</span>
        <span>Compared within each aspect; equal scores, N/A, and single available scores remain neutral.</span>
      </div>
      <div className="compare-radar-data-scroll" tabIndex={0} role="region" aria-label={`${title} numeric comparison`}>
        <table className="compare-radar-data">
          <thead><tr><th scope="col">Aspect</th>{items.map((item, index) => <th scope="col" key={item.laptop_id}>Laptop {index + 1}</th>)}</tr></thead>
          <tbody>{axes.map((aspect, index) => {
            const extremes = numericExtremes(series, ({ scores }) => scores[index], "higher");
            return <tr key={aspect.aspect_id}>
              <th scope="row">{aspect.aspect_name}</th>
              {series.map(({ item, scores }, i) => <td key={item.laptop_id}>
                <span className={`compare-radar-score ${extremes[i] ? `compare-radar-score-${extremes[i]}` : ""}`}
                  title={extremes[i] === "best" ? "Highest available adjusted score for this aspect" :
                    extremes[i] === "worst" ? "Lowest available adjusted score for this aspect" : undefined}>
                  {scores[index] === null ? "N/A" : scores[index].toFixed(1)}
                </span>
                {data.selectedByLaptop[i].some((a) => a.aspect_id === aspect.aspect_id) &&
                  <span className="compare-radar-picked" title={`Among this laptop's ${plotId} selected aspects`}>Selected</span>}
              </td>)}
            </tr>;
          })}</tbody>
        </table>
      </div>
    </section>
  );
}

function RadarDashboard({ items, aspectList, aspectMaps }) {
  const [count, setCount] = useState(4);
  const [minMentions, setMinMentions] = useState(10);
  const strongest = useMemo(() => radarSelection(aspectList, aspectMaps, count, minMentions, "top"),
    [aspectList, aspectMaps, count, minMentions]);
  const weakest = useMemo(() => radarSelection(aspectList, aspectMaps, count, minMentions, "bottom"),
    [aspectList, aspectMaps, count, minMentions]);
  const summaries = useMemo(() => specificationSummaries(items), [items]);
  return <div className="compare-radar-dashboard">
    <div className="compare-radar-toolbar">
      <label>Aspects per laptop
        <select value={count} onChange={(event) => setCount(Number(event.target.value))}>
          <option value={4}>4</option><option value={5}>5</option><option value={6}>6</option>
        </select>
      </label>
      <label>Review evidence requirement
        <select value={minMentions} onChange={(event) => setMinMentions(Number(event.target.value))}>
          <option value={10}>At least 10 mentions (moderate+)</option>
          <option value={1}>All direct evidence (1+ mentions)</option>
        </select>
      </label>
    </div>
    <p className="compare-radar-description">Each laptop contributes its own strongest and weakest aspects; the union forms shared axes for every laptop. Charts use adjusted review-sentiment scores (0–100), not hardware benchmarks. Low counts warrant caution.</p>
    <RadarPlot title="Strongest sentiment aspects" description={`Up to ${count} highest-scoring supported aspects from each laptop · ${strongest.axes.length} shared axes`}
      plotId="top" data={strongest} items={items} aspectMaps={aspectMaps}/>
    <RadarPlot title="Weakest sentiment aspects" description={`Up to ${count} lowest-scoring supported aspects from each laptop · ${weakest.axes.length} shared axes`}
      plotId="bottom" data={weakest} items={items} aspectMaps={aspectMaps}/>
    <section className="compare-spec-summary" aria-label="Rule-based specification comparison summary">
      <h3>Specification comparison summary</h3>
      <p>Generated instantly from the current comparison specifications using fixed, transparent rules; no AI-generated performance claims or additional API calls.</p>
      {summaries.map((summary, index) => (
        <article key={items[index].laptop_id} className="compare-summary-laptop">
          <h4><i style={{ background: ACCENT_COLORS[index] }} />Laptop {index + 1}: {summary.name}</h4>
          <p>{summary.factsParts.map((part, partIndex) => part.emphasis
            ? <strong key={partIndex} className="compare-summary-key-fact">{part.text}</strong>
            : <span key={partIndex}>{part.text}</span>)}</p>
          <p>{summary.differenceParts.map((part, partIndex) => part.tone
            ? <strong key={partIndex} className={`compare-summary-extreme compare-summary-extreme-${part.tone}`}>{part.text}</strong>
            : <span key={partIndex}>{part.text}</span>)}</p>
        </article>
      ))}
      <p className="compare-summary-note">These statements compare listed capacities, prices, dimensions and refresh rates only. Processor, graphics, operating system and resolution are not ranked as inherently better or worse.</p>
    </section>
  </div>;
}

export default function ComparisonPanel({ items, resultsMode, onClose, onRemove }) {
  const [snapshot, setSnapshot] = useState({ key: "", laptops: [] });
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const [view, setView] = useState("all");
  const [sortReference, setSortReference] = useState("alphabetical");
  const [sortDirection, setSortDirection] = useState("desc");
  const selectionKey = items.map((item) => item.laptop_id).join("|");

  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const handleKeyDown = (event) => { if (event.key === "Escape") onClose(); };
    window.addEventListener("keydown", handleKeyDown);
    return () => { document.body.style.overflow = previousOverflow; window.removeEventListener("keydown", handleKeyDown); };
  }, [onClose]);

  useEffect(() => {
    let cancelled = false;
    setError("");
    setSnapshot({ key: "", laptops: [] });
    Promise.all(items.map((item) => getLaptop(item.laptop_id)))
      .then((laptops) => { if (!cancelled) setSnapshot({ key: selectionKey, laptops }); })
      .catch((err) => { if (!cancelled) setError(`Unable to load comparison details: ${err.message}`); });
    return () => { cancelled = true; };
  // ID-based key prevents needless network requests when parent rerenders.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectionKey, retry]);

  const ready = snapshot.key === selectionKey && snapshot.laptops.length === items.length;
  const detailsById = useMemo(() => new Map(snapshot.laptops.map((item) => [item.laptop_id, item])), [snapshot]);
  const weightedBreakdown = items[0]?.aspect_breakdown || [];
  const weightByAspect = new Map(weightedBreakdown.map((aspect) => [aspect.aspect_id, Number(aspect.normalized_weight)]));
  const weightedIDs = new Set(weightedBreakdown.filter((aspect) => Number(aspect.normalized_weight) > 0).map((aspect) => aspect.aspect_id));
  const aspectList = useMemo(() => {
    if (!ready) return [];
    const found = new Map();
    for (const laptop of snapshot.laptops) for (const aspect of laptop.aspects || []) {
      if (!RETIRED_ASPECT_IDS.has(aspect.aspect_id)) found.set(aspect.aspect_id, aspect.aspect_name);
    }
    return [...found].map(([aspect_id, aspect_name]) => ({ aspect_id, aspect_name }))
      .sort((a, b) => a.aspect_name.localeCompare(b.aspect_name));
  }, [ready, snapshot]);
  const aspectMaps = useMemo(() => items.map((item) => new Map((detailsById.get(item.laptop_id)?.aspects || [])
    .map((aspect) => [aspect.aspect_id, aspect]))), [items, detailsById]);
  const canFilterWeighted = (resultsMode === "custom" || resultsMode === "guided") &&
    weightedIDs.size > 0 && weightedIDs.size < aspectList.length;
  const filteredAspects = view === "selected" && canFilterWeighted
    ? aspectList.filter((aspect) => weightedIDs.has(aspect.aspect_id)) : aspectList;
  const shownAspects = sortedAspects(filteredAspects, aspectMaps, sortReference, sortDirection, items);

  const specRows = [
    { label: "Current rank", get: (item) => `#${item.rank}`, metric: "rank", better: "lower" },
    { label: "Recommendation score", get: (item) => `${item.recommendation_score_0_100.toFixed(1)} / 100`, metric: "recommendation_score_0_100", better: "higher" },
    { label: "Evidence support", get: (item) => `${item.evidence_confidence_0_100.toFixed(1)}%`, metric: "evidence_confidence_0_100", better: "higher" },
    { label: "Selected aspects with evidence", get: (item) => `${item.selected_aspects_with_evidence} / ${item.selected_aspects}`, coverage: true },
    { label: "Price (USD)", get: (item) => formatMoney(item.price_usd), metric: "price_usd", better: "lower" },
    { label: "Processor", get: (item) => item.processor || "Unavailable" },
    { label: "Graphics", get: (item) => item.gpu || "Unavailable" },
    { label: "RAM", get: (item) => formatNumber(item.ram_gb, " GB"), metric: "ram_gb", better: "higher" },
    { label: "Storage", get: (item) => item.storage_gb == null ? "Unavailable" : `${item.storage_gb} GB ${item.storage_type || ""}`.trim(), metric: "storage_gb", better: "higher" },
    { label: "Screen size", get: (item) => formatNumber(item.screen_size_in, " in") },
    { label: "Resolution", get: (item) => item.screen_resolution || "Unavailable" },
    { label: "Refresh rate", get: (item) => formatNumber(item.refresh_rate_hz, " Hz"), metric: "refresh_rate_hz", better: "higher" },
    { label: "Touchscreen", get: (item) => item.touch_screen == null ? "Unavailable" : item.touch_screen ? "Yes" : "No" },
    { label: "Weight", get: (item) => formatNumber(item.weight_lb, " lb"), metric: "weight_lb", better: "lower" },
    { label: "Operating system", get: (item) => item.operating_system || "Unavailable" },
  ];

  return <div className="compare-backdrop" role="presentation" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
    <section className="compare-dialog" role="dialog" aria-modal="true" aria-labelledby="compare-title">
      <div className="compare-dialog-heading">
        <div><p className="compare-kicker">Side-by-side laptop comparison</p>
          <h2 id="compare-title">Compare selected laptops</h2>
          <p>Comparing {items.length} laptops from the current recommendation results.</p></div>
        <button type="button" className="compare-close" onClick={onClose} aria-label="Close comparison">×</button>
      </div>
      <p className="compare-explanation">Ranking and evidence support reflect the preferences used for the current results. Individual aspect scores are stored review-derived estimates and do not change with those weights.</p>
      <div className="compare-scroll" role="region" aria-label="Laptop comparison" tabIndex={0}>
        <div className="comparison-matrix" style={{ "--compare-count": items.length, minWidth: items.length === 3 ? 850 : 650 }}>
          <div className="comparison-grid-row comparison-product-row">
            <ComparisonCell first className="compare-product-label"><strong>Laptops</strong><span>Remove a laptop to choose another</span></ComparisonCell>
            {items.map((item, index) => <ComparisonCell className="compare-product-cell" key={item.laptop_id}>
              <div className="compare-product-accent" style={{ background: ACCENT_COLORS[index] }}/>
              {item.image_url ? <img src={item.image_url} alt={item.laptop} loading="lazy" /> : <div className="compare-image-empty">No image</div>}
              <strong title={item.laptop}>{item.laptop}</strong>
              <span className="compare-product-price">{formatMoney(item.price_usd)}</span>
              <button type="button" className="compare-remove" onClick={() => onRemove(item.laptop_id)}>Remove laptop</button>
            </ComparisonCell>)}
          </div>
          <div className="compare-group-title">Ranking and specifications</div>
          <div className="compare-highlight-legend" role="note">
            <span className="compare-legend-best">Preferred numeric extreme</span>
            <span className="compare-legend-worst">Other numeric extreme</span>
            <span>Compared only among selected laptops. Green is not necessarily objectively better performance; non-comparable specifications remain neutral. Aspect coverage uses full (green), partial (amber), or none (red) based on direct mentions, not evidence strength.</span>
          </div>
          {specRows.map((row) => <ComparisonRow key={row.label} row={row} items={items}/>)}
          <div className="compare-group-title compare-aspects-heading">
            <span>Aspect score comparison</span>
            {ready && <span>{view === "radar" ? "Strongest & weakest visualizations" : `${shownAspects.length} of ${aspectList.length} selectable aspects`}</span>}
          </div>
          {ready && <div className="compare-aspect-controls" aria-label="Comparison view controls">
            <button type="button" className={view === "all" ? "active" : ""} aria-pressed={view === "all"} onClick={() => setView("all")}>All {aspectList.length} aspects</button>
            {canFilterWeighted && <button type="button" className={view === "selected" ? "active" : ""} aria-pressed={view === "selected"} onClick={() => setView("selected")}>Selected preferences ({weightedIDs.size})</button>}
            <button type="button" className={view === "radar" ? "active" : ""} aria-pressed={view === "radar"} onClick={() => setView("radar")}>Radar charts & summary</button>
          </div>}
          {!ready ? <div className="compare-loading" role="status">
            {error ? <><p>{error}</p><button type="button" className="secondary" onClick={() => setRetry((n) => n + 1)}>Retry loading details</button></>
              : <p>Loading all 23 aspect scores from the existing laptop-detail API…</p>}
          </div> : view === "radar"
            ? <RadarDashboard items={items} aspectList={aspectList} aspectMaps={aspectMaps}/>
            : <>
              <div className="compare-sort-controls">
                <label>Sort by
                  <select value={sortReference} onChange={(e) => setSortReference(e.target.value)}>
                    <option value="alphabetical">Aspect name (A–Z)</option>
                    <option value="average">Average of available direct scores</option>
                    {items.map((item, index) => <option value={item.laptop_id} key={item.laptop_id}>Laptop {index + 1}: {item.laptop}</option>)}
                  </select>
                </label>
                <label>Direction
                  <select value={sortDirection} disabled={sortReference === "alphabetical"} onChange={(e) => setSortDirection(e.target.value)}>
                    <option value="desc">Highest first</option><option value="asc">Lowest first</option>
                  </select>
                </label>
                <span>Rows remain aligned across laptops; N/A always sorts last.</span>
              </div>
              {shownAspects.map((aspect) => <div className="comparison-grid-row compare-aspect-row" key={aspect.aspect_id}>
                <ComparisonCell first className="compare-aspect-label"><strong>{aspect.aspect_name}</strong>
                  {weightByAspect.has(aspect.aspect_id) && (resultsMode === "custom" || resultsMode === "guided") &&
                    <span>Preference weight: {(weightByAspect.get(aspect.aspect_id) * 100).toFixed(2)}%</span>}
                </ComparisonCell>
                {items.map((item, index) => {
                  const itemAspect = aspectMaps[index].get(aspect.aspect_id), score = aspectScore(itemAspect);
                  return <ComparisonCell key={item.laptop_id} className="compare-aspect-value">
                    <div className="compare-barline">
                      <div className={`compare-bartrack ${score === null ? "unsupported" : ""}`} role="img"
                        aria-label={`${item.laptop}: ${aspect.aspect_name}, ${score === null ? "no direct evidence" : `${score.toFixed(1)} out of 100`}`}>
                        {score !== null && <span className="compare-barfill" style={{ width: `${score}%`, background: ACCENT_COLORS[index] }}/>}</div>
                      <strong>{score === null ? "N/A" : score.toFixed(1)}</strong>
                    </div>
                    <div className="compare-aspect-meta"><span className={`evidence ${itemAspect?.evidence_level || "no_evidence"}`}>{evidenceLabel(itemAspect)}</span>
                      <span>{Number(itemAspect?.mention_count ?? 0)} mentions</span></div>
                  </ComparisonCell>;
                })}
              </div>)}
            </>}
        </div>
      </div>
      <p className="compare-footer-note">N/A means no direct review mentions for that laptop and aspect. The recommendation engine may use a corpus-wide prior internally. Scores are not hardware benchmarks, and evidence support is not a probability of correctness. Limited or insufficient evidence should be interpreted cautiously.</p>
      <div className="compare-dialog-footer"><button type="button" className="secondary" onClick={onClose}>Back to recommendations</button></div>
    </section>
  </div>;
}
