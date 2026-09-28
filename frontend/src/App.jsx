import { useEffect, useMemo, useState } from "react";
import {
  getAspectEvidence,
  getAspects,
  getFilters,
  getHealth,
  getLaptop,
  getRecommendations,
} from "./api";

const DEFAULT_WEIGHTS = {
  BATTERY_LIFE: 50,
  PERFORMANCE: 30,
  THERMAL_PERFORMANCE: 20,
};

const EMPTY_FILTERS = {
  min_ram: "",
  min_storage: "",
  max_price: "",
  brand: "",
  cpu_brand: "",
  cpu_contains: "",
  gpu_brand: "",
  gpu_contains: "",
  touch_screen: "",
  min_screen_size: "",
};

function money(value) {
  if (value == null) return "Price unavailable";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
  }).format(value);
}

function evidenceClass(level) {
  return `evidence ${level || "no_evidence"}`;
}

function App() {
  const [health, setHealth] = useState(null);
  const [aspects, setAspects] = useState([]);
  const [filterOptions, setFilterOptions] = useState(null);
  const [weights, setWeights] = useState({});
  const [recommendationMode, setRecommendationMode] = useState("balanced");
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const [topN, setTopN] = useState(5);

  const [results, setResults] = useState([]);
  const [hasSearched, setHasSearched] = useState(false);
  const [selectedLaptop, setSelectedLaptop] = useState(null);

  const [loading, setLoading] = useState(true);
  const [searching, setSearching] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([getHealth(), getAspects(), getFilters()])
      .then(([h, a, f]) => {
        setHealth(h);
        setAspects(a);
        setFilterOptions(f);
      })
      .catch((err) => {
        setError(`Could not load backend data: ${err.message}`);
      })
      .finally(() => setLoading(false));
  }, []);

  const totalWeight = useMemo(
    () =>
      Object.values(weights).reduce(
        (sum, value) => sum + (Number(value) || 0),
        0
      ),
    [weights]
  );

  const activeWeights = useMemo(
    () =>
      Object.values(weights).filter((value) => Number(value) > 0)
        .length,
    [weights]
  );

  function updateFilter(event) {
    const { name, value } = event.target;
    setFilters((current) => ({ ...current, [name]: value }));
  }

  function updateWeight(aspectId, value) {
    setWeights((current) => ({
      ...current,
      [aspectId]: Number(value),
    }));
  }

  function buildPayload() {
    const cleanFilters = {};

    for (const key of [
      "min_ram",
      "min_storage",
      "max_price",
      "min_screen_size",
    ]) {
      if (filters[key] !== "") {
        cleanFilters[key] = Number(filters[key]);
      }
    }

    if (filters.touch_screen !== "") {
      cleanFilters.touch_screen = filters.touch_screen === "true";
    }

    for (const key of [
      "brand",
      "cpu_brand",
      "cpu_contains",
      "gpu_brand",
      "gpu_contains",
    ]) {
      if (filters[key].trim()) {
        cleanFilters[key] = filters[key].trim();
      }
    }

    let cleanWeights = {};

    if (recommendationMode === "balanced") {
      cleanWeights = Object.fromEntries(
        aspects.map((aspect) => [aspect.aspect_id, 1])
      );
    } else {
      for (const [aspectId, value] of Object.entries(weights)) {
        if (Number(value) > 0) {
          cleanWeights[aspectId] = Number(value);
        }
      }
    }

    return {
      filters: cleanFilters,
      weights: cleanWeights,
      top_n: Number(topN),
    };
  }

  async function submit(event) {
    event.preventDefault();

    if (recommendationMode === "custom" && totalWeight <= 0) {
      setError("Set at least one aspect weight above zero in Custom mode.");
      return;
    }

    setSearching(true);
    setError("");

    try {
      const response = await getRecommendations(buildPayload());
      setResults(response.recommendations);
      setHasSearched(true);

      setTimeout(() => {
        document
          .getElementById("results")
          ?.scrollIntoView({ behavior: "smooth" });
      }, 30);
    } catch (err) {
      setError(`Recommendation failed: ${err.message}`);
    } finally {
      setSearching(false);
    }
  }

  async function showDetails(laptopId) {
    setDetailLoading(true);
    setError("");

    try {
      setSelectedLaptop(await getLaptop(laptopId));
    } catch (err) {
      setError(`Could not load laptop details: ${err.message}`);
    } finally {
      setDetailLoading(false);
    }
  }

  if (loading) {
    return (
      <div className="loading">
        <div className="spinner" />
        <p>Connecting to FastAPI and AuraDB…</p>
      </div>
    );
  }

  return (
    <>
      <header className="hero">
        <nav>
          <div className="brand">
            <span className="logo">L</span>
            <div>
              <strong>Laptop Insight</strong>
              <small>Evidence-aware recommendation system</small>
            </div>
          </div>

          <div
            className={`status ${
              health?.database_connected ? "online" : "offline"
            }`}
          >
            <span />
            {health?.database_connected
              ? "AuraDB connected"
              : "Database unavailable"}
          </div>
        </nav>

        <div className="hero-grid">
          <div>
            <p className="eyebrow">
              Knowledge graph + aspect-based sentiment analysis
            </p>
            <h1>
              Find a laptop based on
              <em> what matters to you.</em>
            </h1>
            <p className="hero-copy">
              Apply hard specification requirements, choose the
              real-world qualities you care about, and rank laptops
              using review evidence from the knowledge graph.
            </p>
            <div className="pills">
              <span>30 laptops</span>
              <span>{aspects.length} experience aspects</span>
              <span>Evidence confidence included</span>
            </div>
          </div>

          <div className="method-card">
            <p className="method-title">How ranking works</p>
            <Method n="01" title="Filter specifications">
              RAM, storage, price, brand, CPU, GPU and more.
            </Method>
            <Method n="02" title="Weight experience aspects">
              Prioritize battery life, performance, display, thermals
              and other review-derived qualities.
            </Method>
            <Method n="03" title="Rank with evidence">
              Recommendation score and evidence confidence are kept
              separate for transparency.
            </Method>
          </div>
        </div>
      </header>

      <main>
        {error && (
          <div className="alert">
            <div>
              <strong>Something needs attention.</strong>
              <p>{error}</p>
            </div>
            <button onClick={() => setError("")}>×</button>
          </div>
        )}

        <form onSubmit={submit}>
          <section className="panel">
            <SectionHeader
              number="01"
              title="Specification requirements"
              text="These are hard filters. Every returned laptop must satisfy every requirement you set."
              action={
                <button
                  type="button"
                  className="link-button"
                  onClick={() => setFilters(EMPTY_FILTERS)}
                >
                  Clear filters
                </button>
              }
            />

            <div className="filters">
              <Field label="Minimum RAM">
                <select
                  name="min_ram"
                  value={filters.min_ram}
                  onChange={updateFilter}
                >
                  <option value="">Any RAM</option>
                  {filterOptions?.ram_options_gb?.map((v) => (
                    <option key={v} value={v}>
                      {v} GB
                    </option>
                  ))}
                </select>
              </Field>

              <Field label="Minimum storage">
                <select
                  name="min_storage"
                  value={filters.min_storage}
                  onChange={updateFilter}
                >
                  <option value="">Any storage</option>
                  {filterOptions?.storage_options_gb?.map((v) => (
                    <option key={v} value={v}>
                      {v >= 1000 ? `${v / 1000} TB` : `${v} GB`}
                    </option>
                  ))}
                </select>
              </Field>

              <Field label="Maximum price (USD)">
                <input
                  name="max_price"
                  type="number"
                  min="0"
                  value={filters.max_price}
                  onChange={updateFilter}
                  placeholder="No maximum"
                />
              </Field>

              <Field label="Brand">
                <select
                  name="brand"
                  value={filters.brand}
                  onChange={updateFilter}
                >
                  <option value="">Any brand</option>
                  {filterOptions?.brands?.map((v) => (
                    <option key={v}>{v}</option>
                  ))}
                </select>
              </Field>

              <Field label="CPU brand">
                <select
                  name="cpu_brand"
                  value={filters.cpu_brand}
                  onChange={updateFilter}
                >
                  <option value="">Any CPU brand</option>
                  {filterOptions?.cpu_brands?.map((v) => (
                    <option key={v}>{v}</option>
                  ))}
                </select>
              </Field>

              <Field label="GPU brand">
                <select
                  name="gpu_brand"
                  value={filters.gpu_brand}
                  onChange={updateFilter}
                >
                  <option value="">Any GPU brand</option>
                  {filterOptions?.gpu_brands?.map((v) => (
                    <option key={v}>{v}</option>
                  ))}
                </select>
              </Field>

              <Field label="CPU model contains">
                <input
                  name="cpu_contains"
                  value={filters.cpu_contains}
                  onChange={updateFilter}
                  placeholder="e.g. Ryzen 7"
                />
              </Field>

              <Field label="GPU model contains">
                <input
                  name="gpu_contains"
                  value={filters.gpu_contains}
                  onChange={updateFilter}
                  placeholder="e.g. RTX 4060"
                />
              </Field>

              <Field label="Touchscreen">
                <select
                  name="touch_screen"
                  value={filters.touch_screen}
                  onChange={updateFilter}
                >
                  <option value="">Either</option>
                  <option value="true">Required</option>
                  <option value="false">Not required</option>
                </select>
              </Field>

              <Field label="Minimum screen size">
                <select
                  name="min_screen_size"
                  value={filters.min_screen_size}
                  onChange={updateFilter}
                >
                  <option value="">Any size</option>
                  {filterOptions?.screen_size_options_in?.map((v) => (
                    <option key={v} value={v}>
                      {v}″
                    </option>
                  ))}
                </select>
              </Field>
            </div>
          </section>

          <section className="panel">
            <SectionHeader
              number="02"
              title="Experience preferences"
              text="Choose Balanced for an equal-weight baseline, or Custom to tell the system which review-derived qualities matter more to you."
            />

            <div className="mode-grid">
              <button
                type="button"
                className={`mode-card ${
                  recommendationMode === "balanced" ? "selected" : ""
                }`}
                onClick={() => {
                  setRecommendationMode("balanced");
                  setError("");
                }}
              >
                <span className="mode-radio">
                  {recommendationMode === "balanced" ? "●" : "○"}
                </span>
                <div>
                  <strong>Balanced</strong>
                  <p>
                    Rank eligible laptops using all {aspects.length} experience
                    aspects equally. No preference sliders are required.
                  </p>
                </div>
              </button>

              <button
                type="button"
                className={`mode-card ${
                  recommendationMode === "custom" ? "selected" : ""
                }`}
                onClick={() => {
                  setRecommendationMode("custom");
                  setError("");
                }}
              >
                <span className="mode-radio">
                  {recommendationMode === "custom" ? "●" : "○"}
                </span>
                <div>
                  <strong>Custom preferences</strong>
                  <p>
                    Choose exactly which experience aspects matter and how
                    strongly each one should influence the ranking.
                  </p>
                </div>
              </button>
            </div>

            {recommendationMode === "balanced" ? (
              <div className="balanced-summary">
                <div className="balanced-icon">=</div>
                <div>
                  <strong>Equal weighting across all experience aspects</strong>
                  <p>
                    Each of the {aspects.length} canonical aspects receives
                    approximately{" "}
                    {aspects.length > 0
                      ? (100 / aspects.length).toFixed(2)
                      : "0.00"}
                    % of the total recommendation weight.
                  </p>
                </div>
                <div className="balanced-metric">
                  <strong>{aspects.length}</strong>
                  <span>equally weighted aspects</span>
                </div>
              </div>
            ) : (
              <>
                <div className="custom-toolbar">
                  <div className="weight-summary">
                    <Summary value={activeWeights} label="active aspects" />
                    <Summary value={totalWeight} label="raw weight total" />
                    <Summary
                      value={totalWeight > 0 ? "Automatic" : "—"}
                      label="normalization"
                    />
                  </div>

                  <div className="preset-actions">
                    <button
                      type="button"
                      className="link-button"
                      onClick={() => setWeights(DEFAULT_WEIGHTS)}
                    >
                      Use example 50/30/20 preset
                    </button>
                    <button
                      type="button"
                      className="link-button subtle"
                      onClick={() => setWeights({})}
                    >
                      Clear all weights
                    </button>
                  </div>
                </div>

                <div className="preset-note">
                  Example preset: Battery Life 50, Performance 30, Thermal
                  Performance 20. This is only a convenience preset and is not
                  assumed for every user.
                </div>

                <div className="aspects">
                  {aspects.map((aspect) => {
                    const value = weights[aspect.aspect_id] || 0;
                    const normalized =
                      totalWeight > 0 ? (value / totalWeight) * 100 : 0;

                    return (
                      <div
                        className={`aspect ${value > 0 ? "active" : ""}`}
                        key={aspect.aspect_id}
                      >
                        <div className="aspect-head">
                          <div>
                            <strong>{aspect.aspect_name}</strong>
                            <small>{aspect.aspect_id}</small>
                          </div>
                          <b>{value}</b>
                        </div>

                        <input
                          type="range"
                          min="0"
                          max="100"
                          step="5"
                          value={value}
                          onChange={(e) =>
                            updateWeight(aspect.aspect_id, e.target.value)
                          }
                        />

                        <div className="aspect-meta">
                          <span>{normalized.toFixed(1)}% normalized</span>
                          <span>
                            evidence on {aspect.laptops_with_evidence ?? 0}/30
                          </span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </>
            )}
          </section>

          <section className="rank-bar">
            <div>
              <h2>Ready to rank?</h2>
              <p>
                Filters are applied first. Eligible laptops are then ranked
                using {recommendationMode === "balanced"
                  ? `equal weighting across all ${aspects.length} experience aspects`
                  : "your custom experience weights"}.
              </p>
            </div>

            <div className="rank-actions">
              <label>
                Results
                <select
                  value={topN}
                  onChange={(e) => setTopN(Number(e.target.value))}
                >
                  <option value="5">Top 5</option>
                  <option value="10">Top 10</option>
                  <option value="20">Top 20</option>
                  <option value="30">All 30</option>
                </select>
              </label>

              <button
                className="primary"
                disabled={
                  searching ||
                  (recommendationMode === "custom" && totalWeight <= 0)
                }
              >
                {searching ? "Ranking laptops…" : "Find my laptops"}
              </button>
            </div>
          </section>
        </form>

        <section id="results" className="results">
          <SectionHeader
            number="03"
            title="Your recommendations"
            text="Recommendation score and evidence confidence are shown separately."
            action={
              hasSearched ? (
                <span className="count">{results.length} results</span>
              ) : null
            }
          />

          {!hasSearched ? (
            <Empty
              title="No ranking generated yet"
              text="Choose your requirements and preferences, then click Find my laptops."
            />
          ) : results.length === 0 ? (
            <Empty
              title="No laptops matched every filter"
              text="Relax one or more specification requirements and try again."
            />
          ) : (
            <div className="cards">
              {results.map((item) => (
                <RecommendationCard
                  key={item.laptop_id}
                  item={item}
                  onDetails={showDetails}
                  detailLoading={detailLoading}
                />
              ))}
            </div>
          )}
        </section>
      </main>

      <footer>
        <div>
          <strong>Laptop Insight</strong>
          <span>Neo4j AuraDB · FastAPI · ABSA</span>
        </div>
        <p>
          Scores summarize the current thesis dataset and review
          evidence. Retail prices and availability may change.
        </p>
      </footer>

      {selectedLaptop && (
        <LaptopModal
          laptop={selectedLaptop}
          onClose={() => setSelectedLaptop(null)}
        />
      )}
    </>
  );
}

function Method({ n, title, children }) {
  return (
    <div className="method">
      <span>{n}</span>
      <div>
        <strong>{title}</strong>
        <p>{children}</p>
      </div>
    </div>
  );
}

function SectionHeader({ number, title, text, action }) {
  return (
    <div className="section-head">
      <div>
        <p className="section-no">{number}</p>
        <h2>{title}</h2>
        <p>{text}</p>
      </div>
      {action}
    </div>
  );
}

function Field({ label, children }) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
    </label>
  );
}

function Summary({ value, label }) {
  return (
    <div>
      <strong>{value}</strong>
      <span>{label}</span>
    </div>
  );
}

function Empty({ title, text }) {
  return (
    <div className="empty">
      <div>↗</div>
      <h3>{title}</h3>
      <p>{text}</p>
    </div>
  );
}

function RecommendationCard({ item, onDetails, detailLoading }) {
  return (
    <article className="card">
      <div className="rank">
        <small>Rank</small>
        <strong>{item.rank}</strong>
      </div>

      <div className="image-wrap">
        {item.image_url ? (
          <img
            src={item.image_url}
            alt={item.laptop}
            loading="lazy"
            onError={(event) => {
              event.currentTarget.style.display = "none";
              event.currentTarget.nextElementSibling.style.display =
                "flex";
            }}
          />
        ) : null}
        <div
          className="image-placeholder"
          style={{ display: item.image_url ? "none" : "flex" }}
        >
          No image
        </div>
      </div>

      <div className="card-main">
        <div className="title-row">
          <div>
            <span className="brand-label">{item.brand || "Laptop"}</span>
            <h3>{item.laptop}</h3>
          </div>
          <strong>{money(item.price_usd)}</strong>
        </div>

        <div className="chips">
          {item.processor && <span>{item.processor}</span>}
          {item.gpu && <span>{item.gpu}</span>}
          {item.ram_gb != null && <span>{item.ram_gb} GB RAM</span>}
          {item.storage_gb != null && (
            <span>{item.storage_gb} GB storage</span>
          )}
        </div>

        <div className="score-box">
          <div>
            <span>Recommendation score</span>
            <strong>{item.recommendation_score_0_100.toFixed(1)}</strong>
            <small>/100</small>
          </div>

          <div className="confidence">
            <div>
              <span>Evidence confidence</span>
              <strong>
                {item.evidence_confidence_0_100.toFixed(1)}%
              </strong>
            </div>
            <div className="track">
              <i
                style={{
                  width: `${Math.min(
                    item.evidence_confidence_0_100,
                    100
                  )}%`,
                }}
              />
            </div>
            <small>
              direct evidence for {item.selected_aspects_with_evidence}/
              {item.selected_aspects} selected aspects
            </small>
          </div>
        </div>

        <div className="breakdown">
          {[...item.aspect_breakdown]
            .sort((a, b) => b.normalized_weight - a.normalized_weight)
            .map((aspect) => (
              <div key={aspect.aspect_id}>
                <div>
                  <strong>{aspect.aspect_name}</strong>
                  <small>
                    {(aspect.normalized_weight * 100).toFixed(0)}% weight
                  </small>
                </div>
                <span>
                  {(aspect.adjusted_score * 100).toFixed(1)}
                </span>
                <b className={evidenceClass(aspect.evidence_level)}>
                  {aspect.evidence_level.replace("_", " ")}
                </b>
              </div>
            ))}
        </div>

        <div className="actions">
          <button
            type="button"
            className="secondary"
            disabled={detailLoading}
            onClick={() => onDetails(item.laptop_id)}
          >
            View evidence details
          </button>

          {item.product_url && (
            <a
              href={item.product_url}
              target="_blank"
              rel="noopener noreferrer"
            >
              View product ↗
            </a>
          )}
        </div>
      </div>
    </article>
  );
}


function LaptopModal({ laptop, onClose }) {
  const aspects = [...laptop.aspects]
    .filter((a) => a.has_direct_evidence || a.mention_count > 0)
    .sort((a, b) => b.mention_count - a.mention_count);

  const [selectedEvidence, setSelectedEvidence] = useState(null);
  const [evidenceLoading, setEvidenceLoading] = useState(false);
  const [loadingAspectId, setLoadingAspectId] = useState(null);
  const [evidenceError, setEvidenceError] = useState("");

  async function loadEvidence(aspect) {
    if (
      selectedEvidence?.aspect_id === aspect.aspect_id &&
      !evidenceLoading
    ) {
      setSelectedEvidence(null);
      setEvidenceError("");
      return;
    }

    setEvidenceLoading(true);
    setLoadingAspectId(aspect.aspect_id);
    setEvidenceError("");

    try {
      const response = await getAspectEvidence(
        laptop.laptop_id,
        aspect.aspect_id,
        6
      );
      setSelectedEvidence(response);
    } catch (error) {
      setEvidenceError(
        `Could not load review evidence: ${error.message}`
      );
    } finally {
      setEvidenceLoading(false);
      setLoadingAspectId(null);
    }
  }

  return (
    <div
      className="modal-backdrop"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="modal">
        <button className="close" onClick={onClose}>
          ×
        </button>

        <div className="modal-head">
          <div className="modal-image">
            {laptop.image_url ? (
              <img src={laptop.image_url} alt={laptop.product_name} />
            ) : (
              <div className="image-placeholder">No image</div>
            )}
          </div>

          <div>
            <span className="brand-label">{laptop.brand}</span>
            <h2>{laptop.product_name}</h2>
            <strong>{money(laptop.price_usd)}</strong>
            {laptop.product_url && (
              <a
                className="product-button"
                href={laptop.product_url}
                target="_blank"
                rel="noopener noreferrer"
              >
                Open product page ↗
              </a>
            )}
          </div>
        </div>

        <div className="details">
          <Detail label="Processor" value={laptop.processor} />
          <Detail label="GPU" value={laptop.gpu} />
          <Detail
            label="RAM"
            value={
              laptop.ram_gb != null
                ? `${laptop.ram_gb} GB ${laptop.ram_type || ""}`
                : null
            }
          />
          <Detail
            label="Storage"
            value={
              laptop.storage_gb != null
                ? `${laptop.storage_gb} GB ${
                    laptop.storage_type || ""
                  }`
                : null
            }
          />
          <Detail
            label="Display"
            value={[
              laptop.screen_size_in
                ? `${laptop.screen_size_in}″`
                : null,
              laptop.screen_resolution,
              laptop.display_type,
            ]
              .filter(Boolean)
              .join(" · ")}
          />
          <Detail
            label="Refresh rate"
            value={
              laptop.refresh_rate_hz != null
                ? `${laptop.refresh_rate_hz} Hz`
                : null
            }
          />
          <Detail
            label="Weight"
            value={
              laptop.weight_lb != null
                ? `${laptop.weight_lb} lb`
                : null
            }
          />
          <Detail
            label="Battery spec"
            value={
              laptop.battery_life_hours != null
                ? `Up to ${laptop.battery_life_hours} hours`
                : null
            }
          />
        </div>

        <div className="modal-evidence-heading">
          <div>
            <h3>Review-derived aspect evidence</h3>
            <p>
              Select “Show reviews” to trace an aspect score back to
              representative source-review snippets.
            </p>
          </div>
        </div>

        <div className="evidence-table">
          <div className="table-head evidence-table-six">
            <span>Aspect</span>
            <span>Score</span>
            <span>Mentions</span>
            <span>Confidence</span>
            <span>Evidence</span>
            <span>Reviews</span>
          </div>

          {aspects.map((aspect) => (
            <div
              className={`table-row evidence-table-six ${
                selectedEvidence?.aspect_id === aspect.aspect_id
                  ? "selected-evidence-row"
                  : ""
              }`}
              key={aspect.aspect_id}
            >
              <strong>{aspect.aspect_name}</strong>
              <span>{(aspect.adjusted_score * 100).toFixed(1)}</span>
              <span>{aspect.mention_count}</span>
              <span>
                {(aspect.evidence_confidence * 100).toFixed(1)}%
              </span>
              <b className={evidenceClass(aspect.evidence_level)}>
                {aspect.evidence_level.replace("_", " ")}
              </b>
              <button
                type="button"
                className="review-evidence-button"
                disabled={evidenceLoading}
                onClick={() => loadEvidence(aspect)}
              >
                {loadingAspectId === aspect.aspect_id
                  ? "Loading…"
                  : selectedEvidence?.aspect_id === aspect.aspect_id
                    ? "Hide reviews"
                    : "Show reviews"}
              </button>
            </div>
          ))}
        </div>

        {evidenceError && (
          <div className="inline-evidence-error">
            {evidenceError}
          </div>
        )}

        {selectedEvidence && (
          <AspectReviewEvidence evidence={selectedEvidence} />
        )}
      </div>
    </div>
  );
}

function AspectReviewEvidence({ evidence }) {
  const summary = evidence.summary;

  return (
    <section className="review-evidence-panel">
      <div className="review-evidence-header">
        <div>
          <p className="review-evidence-kicker">
            Source review evidence
          </p>
          <h3>{evidence.aspect_name}</h3>
          <p>
            {evidence.total_available_reviews} review
            {evidence.total_available_reviews === 1 ? "" : "s"} in
            this laptop mention this aspect. Showing{" "}
            {evidence.returned_reviews} sentiment-diverse snippet
            {evidence.returned_reviews === 1 ? "" : "s"}.
          </p>
        </div>

        <div className="review-evidence-score">
          <span>Adjusted score</span>
          <strong>
            {evidence.adjusted_score_0_100.toFixed(1)}
          </strong>
          <small>/100</small>
        </div>
      </div>

      <div className="model-disclaimer">
        <strong>Model-generated evidence</strong>
        <span>
          Sentiment labels are predicted by the ABSA model and may occasionally
          be incorrect.
        </span>
      </div>

      <div className="review-evidence-summary">
        <SentimentCount
          sentiment="positive"
          label="Positive"
          value={summary.positive_reviews}
        />
        <SentimentCount
          sentiment="negative"
          label="Negative"
          value={summary.negative_reviews}
        />
        <SentimentCount
          sentiment="neutral"
          label="Neutral"
          value={summary.neutral_reviews}
        />
        <SentimentCount
          sentiment="mixed"
          label="Mixed"
          value={summary.mixed_reviews}
        />
        <div className="evidence-confidence-tile">
          <span>Evidence confidence</span>
          <strong>
            {evidence.evidence_confidence_0_100.toFixed(1)}%
          </strong>
          <b className={evidenceClass(evidence.evidence_level)}>
            {evidence.evidence_level.replace("_", " ")}
          </b>
        </div>
      </div>

      {evidence.reviews.length === 0 ? (
        <div className="no-review-snippets">
          No review snippets are available for this aspect.
        </div>
      ) : (
        <div className="review-snippet-list">
          {evidence.reviews.map((review) => (
            <article
              className="review-snippet"
              key={review.review_key}
            >
              <div className="review-snippet-meta">
                <span
                  className={`sentiment-pill ${review.sentiment}`}
                >
                  Predicted sentiment: {review.sentiment}
                </span>
                {review.review_date && (
                  <span>{review.review_date}</span>
                )}
                {review.source_review_id != null && (
                  <span>Review #{review.source_review_id}</span>
                )}
              </div>

              <p>“{review.snippet}”</p>
            </article>
          ))}
        </div>
      )}

      <p className="review-evidence-note">
        Review snippets are automatically selected from the original review
        text using aspect phrases detected by the ATE and ontology pipeline.
        Sentiment labels are predictions produced by the trained ABSA model
        and may contain classification errors. These snippets are provided
        for transparency and supporting evidence; recommendation scores are
        calculated from aggregated evidence-aware aspect scores rather than
        from any single review prediction.
      </p>
    </section>
  );
}

function SentimentCount({ sentiment, label, value }) {
  return (
    <div className={`sentiment-count ${sentiment}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function Detail({ label, value }) {
  if (!value) return null;
  return (
    <div>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

export default App;
