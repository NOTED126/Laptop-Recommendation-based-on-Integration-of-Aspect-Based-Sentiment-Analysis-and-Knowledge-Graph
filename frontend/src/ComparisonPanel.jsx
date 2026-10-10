import { useEffect, useMemo, useState } from "react";
import { getLaptop } from "./api";

// The existing laptop detail endpoint supplies all canonical aspect scores.
// No new API endpoint, ranking calculation, or KG migration is required.
const RETIRED_ASPECT_IDS = new Set(["FEATURE_SET"]);
const ACCENT_COLORS = ["#3157d5", "#008e83", "#bb741e"];

function formatMoney(value) {
  if (value == null) return "Unavailable";
  return new Intl.NumberFormat("en-US", {
    style: "currency", currency: "USD",
  }).format(value);
}

function formatNumber(value, suffix = "") {
  return value == null ? "Unavailable" : `${value}${suffix}`;
}

function formatAspectScore(aspect) {
  // Suppress prior-only estimates in the UI, but preserve the unchanged ranking.
  if (!aspect || Number(aspect.mention_count ?? 0) <= 0) return null;
  const value = Number(aspect.adjusted_score) * 100;
  return Number.isFinite(value) ? Math.min(100, Math.max(0, value)) : null;
}

function evidenceLabel(aspect) {
  return (aspect?.evidence_level || "no_evidence").replaceAll("_", " ");
}

function ComparisonCell({ children, first = false, className = "" }) {
  return (
    <div className={`compare-cell ${first ? "compare-label-cell" : ""} ${className}`}>
      {children}
    </div>
  );
}

function ComparisonRow({ label, items, getValue }) {
  return (
    <div className="comparison-grid-row">
      <ComparisonCell first><strong>{label}</strong></ComparisonCell>
      {items.map((item) => (
        <ComparisonCell key={item.laptop_id}>
          <span className="comparison-spec-value">{getValue(item)}</span>
        </ComparisonCell>
      ))}
    </div>
  );
}

export default function ComparisonPanel({ items, resultsMode, onClose, onRemove }) {
  const [snapshot, setSnapshot] = useState({ key: "", laptops: [] });
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const [onlyWeighted, setOnlyWeighted] = useState(false);
  const selectionKey = items.map((item) => item.laptop_id).join("|");

  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const handleKeyDown = (event) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [onClose]);

  useEffect(() => {
    let cancelled = false;
    setError("");
    setSnapshot({ key: "", laptops: [] });
    Promise.all(items.map((item) => getLaptop(item.laptop_id)))
      .then((laptops) => {
        if (!cancelled) setSnapshot({ key: selectionKey, laptops });
      })
      .catch((err) => {
        if (!cancelled) setError(`Unable to load comparison details: ${err.message}`);
      });
    return () => { cancelled = true; };
    // Using the ID string, rather than the array identity, prevents repeat fetches.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectionKey, retry]);

  const ready = snapshot.key === selectionKey && snapshot.laptops.length === items.length;
  const detailsById = useMemo(() => {
    const byId = new Map();
    for (const laptop of snapshot.laptops) byId.set(laptop.laptop_id, laptop);
    return byId;
  }, [snapshot]);

  const weightedBreakdown = items[0]?.aspect_breakdown || [];
  const weightByAspect = new Map(weightedBreakdown.map((aspect) => [
    aspect.aspect_id, Number(aspect.normalized_weight),
  ]));
  const weightedIDs = new Set(weightedBreakdown
    .filter((aspect) => Number(aspect.normalized_weight) > 0)
    .map((aspect) => aspect.aspect_id));

  const aspectList = useMemo(() => {
    if (!ready) return [];
    const found = new Map();
    for (const laptop of snapshot.laptops) {
      for (const aspect of laptop.aspects || []) {
        if (!RETIRED_ASPECT_IDS.has(aspect.aspect_id)) {
          found.set(aspect.aspect_id, aspect.aspect_name);
        }
      }
    }
    return [...found].map(([aspect_id, aspect_name]) => ({ aspect_id, aspect_name }))
      .sort((a, b) => a.aspect_name.localeCompare(b.aspect_name));
  }, [ready, snapshot]);

  const canFilterWeighted = (resultsMode === "custom" || resultsMode === "guided") &&
    weightedIDs.size > 0 && weightedIDs.size < aspectList.length;
  const shownAspects = onlyWeighted && canFilterWeighted
    ? aspectList.filter((aspect) => weightedIDs.has(aspect.aspect_id))
    : aspectList;
  const aspectMaps = items.map((item) => new Map(
    (detailsById.get(item.laptop_id)?.aspects || []).map((aspect) => [aspect.aspect_id, aspect])
  ));

  const specRows = [
    { label: "Current rank", get: (item) => `#${item.rank}` },
    { label: "Recommendation score", get: (item) => `${item.recommendation_score_0_100.toFixed(1)} / 100` },
    { label: "Evidence support", get: (item) => `${item.evidence_confidence_0_100.toFixed(1)}%` },
    { label: "Selected aspects with evidence", get: (item) =>
      `${item.selected_aspects_with_evidence} / ${item.selected_aspects}` },
    { label: "Price (USD)", get: (item) => formatMoney(item.price_usd) },
    { label: "Processor", get: (item) => item.processor || "Unavailable" },
    { label: "Graphics", get: (item) => item.gpu || "Unavailable" },
    { label: "RAM", get: (item) => formatNumber(item.ram_gb, " GB") },
    { label: "Storage", get: (item) =>
      item.storage_gb == null ? "Unavailable" : `${item.storage_gb} GB ${item.storage_type || ""}`.trim() },
    { label: "Screen size", get: (item) => formatNumber(item.screen_size_in, " in") },
    { label: "Resolution", get: (item) => item.screen_resolution || "Unavailable" },
    { label: "Refresh rate", get: (item) => formatNumber(item.refresh_rate_hz, " Hz") },
    { label: "Touchscreen", get: (item) =>
      item.touch_screen == null ? "Unavailable" : item.touch_screen ? "Yes" : "No" },
    { label: "Weight", get: (item) => formatNumber(item.weight_lb, " lb") },
    { label: "Operating system", get: (item) => item.operating_system || "Unavailable" },
  ];

  return (
    <div
      className="compare-backdrop"
      role="presentation"
      onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}
    >
      <section className="compare-dialog" role="dialog" aria-modal="true" aria-labelledby="compare-title">
        <div className="compare-dialog-heading">
          <div>
            <p className="compare-kicker">Side-by-side laptop comparison</p>
            <h2 id="compare-title">Compare selected laptops</h2>
            <p>Comparing {items.length} laptops from the current recommendation results.</p>
          </div>
          <button type="button" className="compare-close" onClick={onClose} aria-label="Close comparison">×</button>
        </div>

        <p className="compare-explanation">
          Ranking and evidence support reflect the preferences used for the current results.
          Individual aspect scores are stored review-derived estimates and do not change with those weights.
        </p>

        <div className="compare-scroll" role="region" aria-label="Laptop comparison table" tabIndex={0}>
          <div className="comparison-matrix" style={{ "--compare-count": items.length, minWidth: items.length === 3 ? 850 : 650 }}>
            <div className="comparison-grid-row comparison-product-row">
              <ComparisonCell first className="compare-product-label">
                <strong>Laptops</strong>
                <span>Remove a laptop to choose another</span>
              </ComparisonCell>
              {items.map((item, index) => (
                <ComparisonCell className="compare-product-cell" key={item.laptop_id}>
                  <div className="compare-product-accent" style={{ background: ACCENT_COLORS[index] }} />
                  {item.image_url ? (
                    <img src={item.image_url} alt={item.laptop} loading="lazy" />
                  ) : <div className="compare-image-empty">No image</div>}
                  <strong title={item.laptop}>{item.laptop}</strong>
                  <span className="compare-product-price">{formatMoney(item.price_usd)}</span>
                  <button type="button" className="compare-remove" onClick={() => onRemove(item.laptop_id)}>
                    Remove laptop
                  </button>
                </ComparisonCell>
              ))}
            </div>
            <div className="compare-group-title">Ranking and specifications</div>
            {specRows.map((row) => (
              <ComparisonRow key={row.label} label={row.label} items={items} getValue={row.get} />
            ))}
            <div className="compare-group-title compare-aspects-heading">
              <span>Aspect score comparison</span>
              {ready && <span>{shownAspects.length} of {aspectList.length} selectable aspects</span>}
            </div>
            {ready && canFilterWeighted && (
              <div className="compare-aspect-controls">
                <button type="button" className={!onlyWeighted ? "active" : ""}
                  aria-pressed={!onlyWeighted} onClick={() => setOnlyWeighted(false)}>
                  All {aspectList.length} aspects
                </button>
                <button type="button" className={onlyWeighted ? "active" : ""}
                  aria-pressed={onlyWeighted} onClick={() => setOnlyWeighted(true)}>
                  Selected preferences ({weightedIDs.size})
                </button>
              </div>
            )}
            {!ready ? (
              <div className="compare-loading" role="status">
                {error ? (
                  <>
                    <p>{error}</p>
                    <button type="button" className="secondary" onClick={() => setRetry((n) => n + 1)}>
                      Retry loading details
                    </button>
                  </>
                ) : <p>Loading all 23 aspect scores from the existing laptop-detail API…</p>}
              </div>
            ) : shownAspects.map((aspect) => (
              <div className="comparison-grid-row compare-aspect-row" key={aspect.aspect_id}>
                <ComparisonCell first className="compare-aspect-label">
                  <strong>{aspect.aspect_name}</strong>
                  {weightByAspect.has(aspect.aspect_id) && (resultsMode === "custom" || resultsMode === "guided") && (
                    <span>Preference weight: {(weightByAspect.get(aspect.aspect_id) * 100).toFixed(2)}%</span>
                  )}
                </ComparisonCell>
                {items.map((item, index) => {
                  const itemAspect = aspectMaps[index].get(aspect.aspect_id);
                  const score = formatAspectScore(itemAspect);
                  return (
                    <ComparisonCell key={item.laptop_id} className="compare-aspect-value">
                      <div className="compare-barline">
                        <div className={`compare-bartrack ${score === null ? "unsupported" : ""}`}
                          role="img"
                          aria-label={`${item.laptop}: ${aspect.aspect_name}, ${score === null ? "no direct evidence" : `${score.toFixed(1)} out of 100`}`}>
                          {score !== null && <span className="compare-barfill"
                            style={{ width: `${score}%`, background: ACCENT_COLORS[index] }} />}
                        </div>
                        <strong>{score === null ? "N/A" : score.toFixed(1)}</strong>
                      </div>
                      <div className="compare-aspect-meta">
                        <span className={`evidence ${itemAspect?.evidence_level || "no_evidence"}`}>
                          {evidenceLabel(itemAspect)}
                        </span>
                        <span>{Number(itemAspect?.mention_count ?? 0)} mentions</span>
                      </div>
                    </ComparisonCell>
                  );
                })}
              </div>
            ))}
          </div>
        </div>
        <p className="compare-footer-note">
          N/A means no direct review mentions for that laptop and aspect. The recommendation engine
          may use a corpus-wide prior internally. Scores are not hardware benchmarks, and evidence
          support is not a probability of correctness. Limited or insufficient evidence should be
          interpreted cautiously.
        </p>
        <div className="compare-dialog-footer">
          <button type="button" className="secondary" onClick={onClose}>Back to recommendations</button>
        </div>
      </section>
    </div>
  );
}
