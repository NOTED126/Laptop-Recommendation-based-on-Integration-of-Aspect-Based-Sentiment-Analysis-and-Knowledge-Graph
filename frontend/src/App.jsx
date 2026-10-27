import { useEffect, useMemo, useState } from "react";
import {
  getAspectEvidence,
  getAspects,
  getFilters,
  getHealth,
  getLaptop,
  getRecommendations,
  refineRecommendations,
} from "./api";
import ComparisonPanel from "./ComparisonPanel";
import { splitExperienceSummary } from "./summaryFormatting";

const DEFAULT_WEIGHTS = {
  BATTERY_LIFE: 50,
  PERFORMANCE: 30,
  THERMAL_PERFORMANCE: 20,
};

// Keep the underlying Neo4j evidence but exclude overlapping umbrella aspects
// from the recommendation preferences and user-facing aspect breakdowns.
const RETIRED_ASPECT_IDS = new Set(["FEATURE_SET"]);

const EMPTY_FILTERS = {
  min_ram: "",
  min_storage: "",
  min_price: "",
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

// This quantity-based measure is not a calibrated probability of correctness.
const EVIDENCE_SUPPORT_EXPLANATION =
  "Evidence support measures the quantity of review mentions across the selected aspects. " +
  "It is not the probability that this recommendation is correct.";

function hasDirectReviewEvidence(aspect) {
  return Number(aspect.mention_count ?? 0) > 0;
}

// Suppress prior-only estimates from user-facing score bars and numerical tables.
// The unchanged backend may still use the aspect prior when ranking laptops.
function supportedScore100(aspect) {
  if (!hasDirectReviewEvidence(aspect) || aspect.adjusted_score == null) return null;
  const score = Number(aspect.adjusted_score) * 100;
  return Number.isFinite(score) ? Math.max(0, Math.min(100, score)) : null;
}

function getPreviewAspects(breakdown, mode) {
  const available = breakdown.filter(
    (aspect) => !RETIRED_ASPECT_IDS.has(aspect.aspect_id) &&
      Number(aspect.normalized_weight) > 0
  );

  if (mode === "custom" || mode === "guided") {
    // Weighted modes are explanatory breakdowns, not limited highlights.
    // Show every selected, positively weighted aspect (including no-evidence
    // rows), ordered by weight, so the displayed breakdown is complete.
    return [...available]
      .sort((a, b) => Number(b.normalized_weight) - Number(a.normalized_weight) ||
        a.aspect_name.localeCompare(b.aspect_name));
  }

  // Balanced rankings have equal weights. Show both higher- and lower-scoring
  // aspects, preferring those with >= 10 mentions (moderate/strong support).
  // Add aspects with >= 5 mentions only if fewer than four stronger rows exist.
  const wellSupported = available.filter((a) => Number(a.mention_count) >= 10);
  const limited = available.filter(
    (a) => Number(a.mention_count) >= 5 && Number(a.mention_count) < 10
  );
  const candidates = wellSupported.length >= 4
    ? wellSupported
    : [...wellSupported, ...limited];

  const sorted = candidates
    .filter((a) => supportedScore100(a) !== null)
    .sort((a, b) => supportedScore100(b) - supportedScore100(a) ||
      a.aspect_name.localeCompare(b.aspect_name));
  const total = Math.min(6, sorted.length);
  const higher = sorted.slice(0, Math.ceil(total / 2));
  const lowerCount = Math.floor(total / 2);
  const lower = lowerCount > 0 ? sorted.slice(-lowerCount) : [];
  return [...higher, ...lower].sort(
    (a, b) => supportedScore100(b) - supportedScore100(a) ||
      a.aspect_name.localeCompare(b.aspect_name)
  );
}

function App() {
  const [health, setHealth] = useState(null);
  const [aspects, setAspects] = useState([]);
  const [filterOptions, setFilterOptions] = useState(null);
  const [weights, setWeights] = useState({});
  const [recommendationMode, setRecommendationMode] = useState("balanced");
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const [topN, setTopN] = useState(5);
  const [guidedInitialIds, setGuidedInitialIds] = useState([]);
  const [guidedAdditionalIds, setGuidedAdditionalIds] = useState([]);
  const [guidedInitialWeights, setGuidedInitialWeights] = useState({});
  const [guidedRefinedWeights, setGuidedRefinedWeights] = useState({});
  // Freeze the initial candidate IDs, original filter values, and original
  // aspect weights. They are never recomputed from edited form values.
  const [guidedShortlist, setGuidedShortlist] = useState(null);
  const [guidedStage, setGuidedStage] = useState("initial");

  const [results, setResults] = useState([]);
  // Capture the mode that generated the displayed results. Changing the
  // preference form afterwards must not silently change the preview logic.
  const [resultsMode, setResultsMode] = useState("balanced");
  const [hasSearched, setHasSearched] = useState(false);
  const [selectedLaptop, setSelectedLaptop] = useState(null);
  // Comparison is local to the displayed recommendation result set.
  const [compareIds, setCompareIds] = useState([]);
  const [compareOpen, setCompareOpen] = useState(false);

  const [loading, setLoading] = useState(true);
  const [searching, setSearching] = useState(false);
  const [searchPhase, setSearchPhase] = useState("initial");
  const [searchSlow, setSearchSlow] = useState(false);
  const [initialConnectionSlow, setInitialConnectionSlow] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([getHealth(), getAspects(), getFilters()])
      .then(([h, a, f]) => {
        setHealth(h);
        setAspects(a.filter((aspect) => !RETIRED_ASPECT_IDS.has(aspect.aspect_id)));
        setFilterOptions(f);
      })
      .catch((err) => {
        setError(`Could not load backend data: ${err.message}`);
      })
      .finally(() => setLoading(false));
  }, []);

  // Pending is the only trustworthy progress signal without a streaming API.
  // After 10 seconds, explain that a cloud service may be waking from idle.
  useEffect(() => {
    setSearchSlow(false);
    if (!searching) return;
    const timer = setTimeout(() => setSearchSlow(true), 10000);
    return () => clearTimeout(timer);
  }, [searching]);

  useEffect(() => {
    if (!loading) return;
    const timer = setTimeout(() => setInitialConnectionSlow(true), 10000);
    return () => clearTimeout(timer);
  }, [loading]);

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

  function resetGuidedShortlist() {
    setGuidedShortlist(null);
    setGuidedAdditionalIds([]);
    setGuidedRefinedWeights({});
    setGuidedStage("initial");
    setResults([]);
    setHasSearched(false);
    setCompareIds([]);
    setCompareOpen(false);
    setSelectedLaptop(null);
  }

  function selectRecommendationMode(mode) {
    if (mode === recommendationMode) return;
    setRecommendationMode(mode);
    setError("");
    resetGuidedShortlist();
  }

  function toggleGuidedInitial(aspectId) {
    const wasSelected = guidedInitialIds.includes(aspectId);
    if (!wasSelected && guidedInitialIds.length >= Math.max(0, aspects.length - 1)) return;
    setGuidedInitialIds((current) => wasSelected
      ? current.filter((id) => id !== aspectId) : [...current, aspectId]);
    setGuidedInitialWeights((current) => {
      const next = { ...current };
      if (wasSelected) delete next[aspectId];
      else next[aspectId] = 50;
      return next;
    });
    if (guidedShortlist) resetGuidedShortlist();
  }

  function undoRefinedRanking() {
    if (guidedStage === "refined" && guidedShortlist) {
      setResults(guidedShortlist.recommendations);
      setGuidedStage("shortlist");
      setCompareIds([]);
      setCompareOpen(false);
      setSelectedLaptop(null);
    }
  }

  function updateGuidedInitialWeight(aspectId, value) {
    setGuidedInitialWeights((current) => ({ ...current, [aspectId]: Number(value) }));
    // The original weights determine Stage 1 shortlist membership.
    if (guidedShortlist) resetGuidedShortlist();
  }

  function toggleGuidedAdditional(aspectId) {
    const wasSelected = guidedAdditionalIds.includes(aspectId);
    if (!wasSelected && guidedAdditionalIds.length >= aspects.length - guidedInitialIds.length) return;
    setGuidedAdditionalIds((current) => wasSelected
      ? current.filter((id) => id !== aspectId) : [...current, aspectId]);
    setGuidedRefinedWeights((current) => {
      const next = { ...current };
      if (wasSelected) delete next[aspectId];
      else next[aspectId] = 50;
      return next;
    });
    undoRefinedRanking();
  }

  function updateGuidedRefinedWeight(aspectId, value) {
    setGuidedRefinedWeights((current) => ({ ...current, [aspectId]: Number(value) }));
    undoRefinedRanking();
  }

  function updateFilter(event) {
    const { name, value } = event.target;
    setFilters((current) => ({ ...current, [name]: value }));
    if (recommendationMode === "guided" && guidedShortlist) resetGuidedShortlist();
  }

  function updateWeight(aspectId, value) {
    setWeights((current) => ({
      ...current,
      [aspectId]: Number(value),
    }));
  }

  function toggleCompare(laptopId) {
    setCompareIds((current) => {
      if (current.includes(laptopId)) {
        return current.filter((id) => id !== laptopId);
      }
      return current.length < 3 ? [...current, laptopId] : current;
    });
  }

  function removeComparisonLaptop(laptopId) {
    const updated = compareIds.filter((id) => id !== laptopId);
    setCompareIds(updated);
    // The comparison requires at least two laptops to remain meaningful.
    if (updated.length < 2) setCompareOpen(false);
  }

  const comparedLaptops = compareIds
    .map((id) => results.find((item) => item.laptop_id === id))
    .filter(Boolean);

  function buildCleanFilters() {
    const cleanFilters = {};

    for (const key of [
      "min_ram",
      "min_storage",
      "min_price",
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

    return cleanFilters;
  }

  function buildPayload() {
    const cleanFilters = buildCleanFilters();
    let cleanWeights = {};

    if (recommendationMode === "balanced") {
      cleanWeights = Object.fromEntries(
        aspects.map((aspect) => [aspect.aspect_id, 1])
      );
    } else {
      for (const [aspectId, value] of Object.entries(weights)) {
        if (Number(value) > 0 && !RETIRED_ASPECT_IDS.has(aspectId)) {
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

    if (filters.min_price !== "" && filters.max_price !== "" &&
        Number(filters.min_price) > Number(filters.max_price)) {
      setError("The minimum price cannot exceed the maximum price. Check your budget range.");
      return;
    }

    if (recommendationMode === "custom" && totalWeight <= 0) {
      setError("Set at least one aspect weight above zero in Custom mode.");
      return;
    }
    if (recommendationMode === "guided" && guidedInitialIds.length < 1) {
      setError("Select at least 1 experience aspect to create the initial shortlist.");
      return;
    }

    setSearchPhase("initial");
    setSearching(true);
    setError("");

    try {
      const stageOneFilters = buildCleanFilters();
      const stageOneWeights = Object.fromEntries(
        guidedInitialIds.map((id) => [id, guidedInitialWeights[id] ?? 50])
      );
      const response = await getRecommendations(recommendationMode === "guided"
        ? { filters: stageOneFilters, weights: stageOneWeights, top_n: 10 }
        : buildPayload());
      if (recommendationMode === "guided") {
        setGuidedShortlist(response.recommendations.length > 0 ? {
          candidateIds: response.recommendations.map((item) => item.laptop_id),
          recommendations: response.recommendations,
          filters: stageOneFilters,
          initialWeights: stageOneWeights,
        } : null);
        setGuidedAdditionalIds([]);
        setGuidedRefinedWeights({ ...stageOneWeights });
        setGuidedStage(response.recommendations.length > 0 ? "shortlist" : "initial");
      }
      setResults(response.recommendations);
      setResultsMode(recommendationMode);
      setHasSearched(true);
      // A new ranking may exclude earlier candidates or use different weights.
      // Clear comparisons instead of comparing stale recommendation results.
      setCompareIds([]);
      setCompareOpen(false);

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

  async function submitGuidedRefinement() {
    if (!guidedShortlist || guidedAdditionalIds.length < 1) {
      setError("Select at least 1 new aspect to refine your existing shortlist.");
      return;
    }
    setSearchPhase("refined");
    setSearching(true);
    setError("");
    try {
      const response = await refineRecommendations({
        filters: guidedShortlist.filters,
        initial_weights: guidedShortlist.initialWeights,
        refined_weights: Object.fromEntries(
          [...guidedInitialIds, ...guidedAdditionalIds]
            .map((id) => [id, guidedRefinedWeights[id] ?? 50])
        ),
        candidate_laptop_ids: guidedShortlist.candidateIds,
      });
      const returnedIds = response.recommendations.map((item) => item.laptop_id);
      if (returnedIds.length !== guidedShortlist.candidateIds.length ||
          !returnedIds.every((id) => guidedShortlist.candidateIds.includes(id))) {
        throw new Error("The refined response did not preserve the original candidate set.");
      }
      setResults(response.recommendations);
      setResultsMode("guided");
      setGuidedStage("refined");
      setCompareIds([]);
      setCompareOpen(false);
      setSelectedLaptop(null);
    } catch (err) {
      setError(`Refinement failed: ${err.message}`);
    } finally {
      setSearching(false);
    }
  }

  function restoreOriginalShortlist() {
    if (!guidedShortlist) return;
    setResults(guidedShortlist.recommendations);
    setGuidedStage("shortlist");
    setCompareIds([]);
    setCompareOpen(false);
    setSelectedLaptop(null);
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
        {initialConnectionSlow && <p className="loading-slow-note">The recommendation server may be waking after inactivity. Please wait; if this does not finish, refresh to retry.</p>}
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
                  onClick={() => {
                    setFilters(EMPTY_FILTERS);
                    if (recommendationMode === "guided" && guidedShortlist) resetGuidedShortlist();
                  }}
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

              <fieldset className="price-range-filter">
                <legend>Price range (USD)</legend>
                <div className="price-range-inputs">
                  <label>
                    From (minimum)
                    <input name="min_price" type="number" min="0" step="0.01"
                      value={filters.min_price} onChange={updateFilter}
                      placeholder="No minimum" />
                  </label>
                  <label>
                    To (maximum)
                    <input name="max_price" type="number" min="0" step="0.01"
                      value={filters.max_price} onChange={updateFilter}
                      placeholder="No maximum" />
                  </label>
                </div>
                <p className="price-range-hint">
                  {filterOptions?.min_price_usd != null && filterOptions?.max_price_usd != null
                    ? `Laptop prices in this dataset range from ${money(filterOptions.min_price_usd)} to ${money(filterOptions.max_price_usd)}. `
                    : "Set your preferred budget. "}
                  Leave either box blank for no limit.
                </p>
              </fieldset>

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
              text="Choose Balanced, Custom weights, or Guided refinement to narrow an initial shortlist with additional preferences."
            />

            <div className="mode-grid">
              <button
                type="button"
                className={`mode-card ${
                  recommendationMode === "balanced" ? "selected" : ""
                }`}
                onClick={() => selectRecommendationMode("balanced")}
                disabled={searching}
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
                onClick={() => selectRecommendationMode("custom")}
                disabled={searching}
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
              <button
                type="button"
                className={`mode-card ${recommendationMode === "guided" ? "selected" : ""}`}
                onClick={() => selectRecommendationMode("guided")}
                disabled={searching}
                aria-pressed={recommendationMode === "guided"}
              >
                <span className="mode-radio">{recommendationMode === "guided" ? "●" : "○"}</span>
                <div>
                  <strong>Guided two-stage refinement</strong>
                  <p>Choose and weight your initial aspects, shortlist up to 10 eligible laptops, then refine the same candidates with updated weights and new aspects.</p>
                </div>
              </button>
            </div>

            {recommendationMode === "guided" ? (
              <div className="guided-initial">
                <div className="guided-initial-head">
                  <div>
                    <h3>Stage 1 · Choose your initial aspects</h3>
                    <p>Select 1 or more aspects (up to {Math.max(0, aspects.length - 1)}) and adjust their importance. Raw weights are automatically normalized; hardware filters apply first. Leave at least one aspect for Stage 2.</p>
                  </div>
                  <span className="guided-selection-count">{guidedInitialIds.length} selected · min 1</span>
                </div>
                <GuidedAspectPicker aspects={aspects} selectedIds={guidedInitialIds}
                  maxCount={Math.max(0, aspects.length - 1)} onToggle={toggleGuidedInitial} locked={searching} />
                <GuidedWeightControls aspects={aspects} selectedIds={guidedInitialIds}
                  values={guidedInitialWeights} onChange={updateGuidedInitialWeight}
                  disabled={searching} title="Stage 1 aspect importance" />
                <p className="guided-note">Generating a shortlist freezes these starting weights and candidates for verification. Changing the initial aspects, weights or hardware filters starts a new Stage 1 search.</p>
              </div>
            ) : recommendationMode === "balanced" ? (
              <div className="balanced-summary">
                <div className="balanced-icon">=</div>
                <div>
                  <strong>Equal weighting across all experience aspects</strong>
                  <p>
                    Each of the {aspects.length} canonical aspects receives
                    approximately{" "}
                    {aspects.length > 0
                      ? (100 / aspects.length).toFixed(3)
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
                  : recommendationMode === "guided"
                    ? "your weighted initial aspects (top 10 eligible laptops), then your adjusted preferences for refinement"
                    : "your custom experience weights"}.
              </p>
            </div>

            <div className="rank-actions">
              {recommendationMode === "guided" ? (
                <div className="guided-shortlist-cap">Top 10 eligible laptops (or fewer if filtered)</div>
              ) : (
                <label>
                  Results
                  <select value={topN} onChange={(e) => setTopN(Number(e.target.value))}>
                    <option value="5">Top 5</option>
                    <option value="10">Top 10</option>
                    <option value="20">Top 20</option>
                    <option value="30">All 30</option>
                  </select>
                </label>
              )}

              <button
                className="primary"
                disabled={
                  searching ||
                  (recommendationMode === "custom" && totalWeight <= 0) ||
                  (recommendationMode === "guided" && guidedInitialIds.length < 1)
                }
              >
                {searching ? "Ranking laptops…" : recommendationMode === "guided" ? "Generate initial shortlist" : "Find my laptops"}
              </button>
            </div>
            {searching && searchPhase === "initial" && <RequestProgress slow={searchSlow} guided={recommendationMode === "guided"} />}
          </section>
        </form>

        <section id="results" className="results">
          <SectionHeader
            number="03"
            title={resultsMode === "guided" && hasSearched
              ? guidedStage === "refined" ? "Your refined shortlist" : "Your initial shortlist"
              : "Your recommendations"}
            text={resultsMode === "guided" && hasSearched
              ? "These are the same shortlisted laptops; only their ranking and preference-dependent scores change in Stage 2."
              : "Recommendation score and evidence support are shown separately."}
            action={
              hasSearched ? (
                <span className="count">{results.length} results</span>
              ) : null
            }
          />

          {hasSearched && resultsMode === "guided" && guidedShortlist && (
            <section className="guided-refinement" aria-label="Stage 2 preference refinement">
              <div className="guided-refinement-head">
                <div>
                  <h3>Stage 2 · Add more aspects</h3>
                  <p>Add at least 1 new aspect (up to {aspects.length - guidedInitialIds.length} more). You can also readjust the weights of your Stage 1 aspects; the updated weights are normalized together.</p>
                </div>
                <span className="guided-selection-count">{guidedAdditionalIds.length} added · {guidedInitialIds.length + guidedAdditionalIds.length} total</span>
              </div>
              <p className="guided-shortlist-explanation" role="note">
                <strong>Stage 1 shortlist is locked:</strong> Stage 2 reranks only the {guidedShortlist.candidateIds.length} shortlisted {guidedShortlist.candidateIds.length === 1 ? "laptop" : "laptops"}, even if you change the weights of your original aspects. Laptops excluded in Stage 1 are not reconsidered. To search all eligible laptops again, edit your Stage 1 preferences or filters above and generate a new shortlist.
              </p>
              <div className="guided-locked-aspects">
                <strong>Stage 1 aspects (retained; weights editable):</strong>
                {guidedInitialIds.map((id) => (
                  <span key={id}>{aspects.find((a) => a.aspect_id === id)?.aspect_name || id}</span>
                ))}
              </div>
              <GuidedAspectPicker aspects={aspects.filter((aspect) => !guidedInitialIds.includes(aspect.aspect_id))}
                selectedIds={guidedAdditionalIds} maxCount={aspects.length - guidedInitialIds.length} onToggle={toggleGuidedAdditional} locked={searching} />
              <GuidedWeightControls aspects={aspects} selectedIds={[...guidedInitialIds, ...guidedAdditionalIds]}
                values={guidedRefinedWeights} onChange={updateGuidedRefinedWeight}
                disabled={searching} title="Stage 2 refined importance (all selected aspects)" />
              <div className="guided-refinement-actions">
                <button type="button" className="primary" onClick={submitGuidedRefinement}
                  disabled={searching || guidedAdditionalIds.length < 1}>
                  {searching ? "Reranking shortlist…" : `Rerank shortlist (${guidedInitialIds.length + guidedAdditionalIds.length} aspects)`}
                </button>
                {guidedStage === "refined" && (
                  <button type="button" className="secondary" onClick={restoreOriginalShortlist}>
                    View original Stage 1 ranking
                  </button>
                )}
                <span className="guided-candidate-lock">{guidedStage === "refined" ? "Refined ranking active" : "Initial ranking shown"} · Candidate set locked</span>
              </div>
              {searching && searchPhase === "refined" && <RequestProgress slow={searchSlow} guided refinement />}
            </section>
          )}

          {!hasSearched ? (
            <Empty
              title="No ranking generated yet"
              text={recommendationMode === "guided"
                ? "Select at least 1 initial experience aspect and click Generate initial shortlist."
                : "Choose your requirements and preferences, then click Find my laptops."}
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
                  resultsMode={resultsMode}
                  onDetails={showDetails}
                  detailLoading={detailLoading}
                  isCompared={compareIds.includes(item.laptop_id)}
                  comparisonFull={compareIds.length >= 3}
                  onToggleCompare={toggleCompare}
                />
              ))}
            </div>
          )}
        </section>
      </main>

      {comparedLaptops.length > 0 && !compareOpen && (
        <section className="comparison-tray" aria-label="Selected laptops for comparison">
          <div className="comparison-tray-copy">
            <strong>Compare laptops</strong>
            <span>{comparedLaptops.length}/3 selected · Choose 2 or 3</span>
          </div>
          <div className="comparison-tray-chips">
            {comparedLaptops.map((laptop) => (
              <button
                type="button"
                key={laptop.laptop_id}
                className="comparison-tray-chip"
                onClick={() => removeComparisonLaptop(laptop.laptop_id)}
                title={`Remove ${laptop.laptop} from comparison`}
                aria-label={`Remove ${laptop.laptop} from comparison`}
              >
                <span>{laptop.laptop}</span> ×
              </button>
            ))}
          </div>
          <div className="comparison-tray-actions">
            <button type="button" className="secondary comparison-clear" onClick={() => setCompareIds([])}>
              Clear
            </button>
            <button
              type="button"
              className="primary comparison-start"
              disabled={comparedLaptops.length < 2}
              onClick={() => {
                setSelectedLaptop(null);
                setCompareOpen(true);
              }}
            >
              Compare selected ({comparedLaptops.length})
            </button>
          </div>
        </section>
      )}

      {compareOpen && comparedLaptops.length >= 2 && (
        <ComparisonPanel
          items={comparedLaptops}
          resultsMode={resultsMode}
          onClose={() => setCompareOpen(false)}
          onRemove={removeComparisonLaptop}
        />
      )}

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

function RequestProgress({ slow, guided = false, refinement = false }) {
  return <div className="request-progress" role="status" aria-live="polite" aria-label="Recommendation request in progress">
    <div className="request-progress-text">
      <strong>{refinement ? "Reranking your shortlist…" : guided ? "Generating your initial shortlist…" : "Finding your laptops…"}</strong>
      <span>{slow
        ? "This is taking longer than usual. The cloud server may be waking up after inactivity, or the connection may be slow."
        : "Request in progress. Retrieving and ranking laptops using your current preferences."}</span>
    </div>
    <div className="request-progress-track" aria-hidden="true"><span /></div>
    <small>Progress is indeterminate; no completion percentage is estimated.</small>
  </div>;
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

function GuidedWeightControls({ aspects, selectedIds, values, onChange, disabled = false, title }) {
  if (!selectedIds.length) return null;
  const total = selectedIds.reduce((sum, id) => sum + Number(values[id] ?? 50), 0);
  return (
    <div className="guided-weight-controls" aria-label={title}>
      <div className="guided-weight-controls-head">
        <strong>{title}</strong>
        <span>Raw weights 1–100 · automatically normalized to 100%</span>
      </div>
      <div className="guided-weight-list">
        {selectedIds.map((id) => {
          const aspect = aspects.find((item) => item.aspect_id === id);
          const value = Number(values[id] ?? 50);
          const normalized = total > 0 ? (100 * value / total) : 0;
          return (
            <label className="guided-weight-row" key={id}>
              <span className="guided-weight-name">{aspect?.aspect_name || id}</span>
              <input type="range" min="1" max="100" step="1" value={value}
                onChange={(event) => onChange(id, event.target.value)} disabled={disabled} />
              <span className="guided-weight-raw">{value} / 100</span>
              <strong className="guided-weight-normalized">{normalized.toFixed(1)}%</strong>
            </label>
          );
        })}
      </div>
      <p className="guided-note">These percentages are relative preference weights, not review scores. Adjust any slider; the total is normalized automatically.</p>
    </div>
  );
}

function GuidedAspectPicker({ aspects, selectedIds, maxCount, onToggle, locked = false }) {
  return (
    <div className="guided-aspect-grid" role="group" aria-label="Experience aspect selection">
      {aspects.map((aspect) => {
        const selected = selectedIds.includes(aspect.aspect_id);
        const disabled = !selected && selectedIds.length >= maxCount;
        return (
          <button type="button" key={aspect.aspect_id}
            className={`guided-aspect-option ${selected ? "selected" : ""}`}
            aria-pressed={selected} disabled={disabled || locked} onClick={() => onToggle(aspect.aspect_id)}>
            <span className="guided-aspect-check" aria-hidden="true">{selected ? "✓" : "+"}</span>
            <span>{aspect.aspect_name}</span>
          </button>
        );
      })}
    </div>
  );
}

function RecommendationCard({
  item, resultsMode, onDetails, detailLoading,
  isCompared, comparisonFull, onToggleCompare,
}) {
  const preview = getPreviewAspects(item.aspect_breakdown, resultsMode);

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
              <span className="evidence-support-title">
                Evidence support
                <span
                  className="evidence-support-help"
                  tabIndex={0}
                  role="note"
                  aria-label={EVIDENCE_SUPPORT_EXPLANATION}
                  title={EVIDENCE_SUPPORT_EXPLANATION}
                >ⓘ</span>
              </span>
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
              Direct review mentions for {item.selected_aspects_with_evidence}/
              {item.selected_aspects} selected aspects · not a correctness probability
            </small>
          </div>
        </div>

        <div className="aspect-preview" aria-label={(resultsMode === "custom" || resultsMode === "guided")
          ? "All selected weighted aspect scores"
          : "Aspect score highlights"}>
          <div className="aspect-preview-heading">
            <div>
              <strong>{(resultsMode === "custom" || resultsMode === "guided")
                ? "Selected aspect score breakdown"
                : "Aspect score highlights"}</strong>
              <small>
                {(resultsMode === "custom" || resultsMode === "guided")
                  ? "Every selected aspect, ordered by preference weight"
                  : "Higher and lower scores with review support"}
              </small>
            </div>
            <span>0–100 score</span>
          </div>
          {preview.length === 0 ? (
            <p className="aspect-preview-empty">
              Not enough direct review evidence for a meaningful score preview.
              Open the evidence details for all aspects.
            </p>
          ) : (
            <div className="aspect-preview-list">
              <div className="aspect-preview-columns" aria-label="Aspect highlight column headings">
                <span>{(resultsMode === "custom" || resultsMode === "guided") ? "Aspect / Weight" : "Aspect"}</span>
                <span>Score bar</span>
                <span>Score</span>
                <span>Evidence</span>
              </div>
              {preview.map((aspect) => {
                const score = supportedScore100(aspect);
                const label = (aspect.evidence_level || "no_evidence").replaceAll("_", " ");
                return (
                  <div className={`aspect-preview-row ${score === null ? "no-direct-evidence" : ""}`}
                    key={aspect.aspect_id}
                    title={score === null
                      ? `${aspect.aspect_name}: no direct review evidence; a global aspect prior is used internally for ranking.`
                      : `${aspect.aspect_name}: ${score.toFixed(1)}/100 adjusted score; ${aspect.mention_count} review mentions; ${label} evidence.`}
                  >
                    <div className="aspect-preview-name">
                      <strong>{aspect.aspect_name}</strong>
                      {(resultsMode === "custom" || resultsMode === "guided") && (
                        <small>{(aspect.normalized_weight * 100).toFixed(3)}% weight</small>
                      )}
                    </div>
                    <div className="aspect-preview-track"
                      role="img"
                      aria-label={score === null
                        ? `${aspect.aspect_name}: no direct evidence`
                        : `${aspect.aspect_name}: ${score.toFixed(1)} out of 100`}
                    >
                      {score !== null && (
                        <div className="aspect-preview-fill" style={{ width: `${score}%` }} />
                      )}
                    </div>
                    <strong className="aspect-preview-value">
                      {score === null ? "N/A" : score.toFixed(1)}
                    </strong>
                    <b className={evidenceClass(aspect.evidence_level)}>{label}</b>
                  </div>
                );
              })}
            </div>
          )}
          <p className="aspect-preview-note">
            Adjusted sentiment scores, not hardware benchmarks. N/A means no
            direct review mentions; ranking may still use a corpus-wide prior.
            <span className="aspect-preview-more"> All selectable aspects and source reviews are in Evidence Details.</span>
          </p>
        </div>
        <div className="actions">
          <button
            type="button"
            className={`compare-pick-button ${isCompared ? "selected" : ""}`}
            aria-pressed={isCompared}
            disabled={comparisonFull && !isCompared}
            title={comparisonFull && !isCompared
              ? "Maximum 3 laptops selected. Remove one to choose another."
              : isCompared ? "Remove from comparison" : "Add to comparison"}
            onClick={() => onToggleCompare(item.laptop_id)}
          >
            {isCompared ? "✓ Selected" : comparisonFull ? "Max 3 selected" : "+ Compare"}
          </button>
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


// The approved review summary is rendered as safe text fragments, not HTML.
// Emphasized phrases remain character-for-character identical to the database.
function ExperienceSummaryText({ text, fallback }) {
  return <>{splitExperienceSummary(text || fallback).map((part, index) =>
    part.tone
      ? <strong key={index} className={`laptop-summary-keyword laptop-summary-keyword-${part.tone}`}>{part.text}</strong>
      : <span key={index}>{part.text}</span>
  )}</>;
}

function LaptopModal({ laptop, onClose }) {
  // Keep all 23 selectable aspects in both the chart and detailed table.
  // Rows without mentions display N/A and cannot request source reviews.
  const selectableAspects = laptop.aspects.filter(
    (a) => !RETIRED_ASPECT_IDS.has(a.aspect_id)
  );
  const aspects = [...selectableAspects]
    .sort((a, b) => b.mention_count - a.mention_count ||
      a.aspect_name.localeCompare(b.aspect_name));

  const [selectedEvidence, setSelectedEvidence] = useState(null);
  const [evidenceLoading, setEvidenceLoading] = useState(false);
  const [loadingAspectId, setLoadingAspectId] = useState(null);
  const [evidenceError, setEvidenceError] = useState("");

  async function loadEvidence(aspect) {
    if (!hasDirectReviewEvidence(aspect)) return;
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

        {(laptop.strengths_summary || laptop.weaknesses_summary) && (
          <section className="laptop-experience-summary" aria-label="AI-assisted laptop experience summary">
            <div className="laptop-experience-summary-head">
              <div>
                <h3>Laptop experience summary</h3>
                <p>Fixed, AI-assisted summary of this laptop’s review-derived aspect evidence.</p>
              </div>
              <span className="laptop-experience-summary-tag">Offline · Reviewed</span>
            </div>
            <div className="laptop-summary-two-col">
              <div className="laptop-summary-strength">
                <strong>Supported strengths</strong>
                <p><ExperienceSummaryText text={laptop.strengths_summary} fallback="No clearly supported strengths identified." /></p>
              </div>
              <div className="laptop-summary-weakness">
                <strong>Potential weaknesses</strong>
                <p><ExperienceSummaryText text={laptop.weaknesses_summary} fallback="No clearly supported weaknesses identified." /></p>
              </div>
            </div>
            {laptop.summary_evidence_note && (
              <p className="laptop-summary-caution"><strong>Evidence limitations:</strong> {laptop.summary_evidence_note}</p>
            )}
            <p className="laptop-summary-disclaimer">
              Generated offline from ABSA-predicted review sentiment and validated before publication.
              Describes review evidence, not measured hardware performance; does not depend on your selected preference weights.
            </p>
          </section>
        )}

        <AspectScoreChart aspects={selectableAspects} />

        <div className="modal-evidence-heading">
          <div>
            <h3>Review-derived aspect evidence</h3>
            <p>
              Adjusted scores are shown only when direct reviews exist.
              Select “Show reviews” to inspect source snippets; N/A means no
              direct evidence, although ranking may use a global prior.
            </p>
          </div>
        </div>

        <div className="evidence-table">
          <div className="table-head evidence-table-six">
            <span>Aspect</span>
            <span>Adjusted Score</span>
            <span>Mentions</span>
            <span>Support</span>
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
              <span title={hasDirectReviewEvidence(aspect)
                ? "Stored adjusted sentiment score from review evidence and the corpus-wide prior."
                : "N/A: no direct review mentions. A corpus-wide prior is used internally for ranking."}>
                {supportedScore100(aspect) === null
                  ? "N/A"
                  : supportedScore100(aspect).toFixed(1)}
              </span>
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
                disabled={evidenceLoading || !hasDirectReviewEvidence(aspect)}
                title={!hasDirectReviewEvidence(aspect)
                  ? "No reviews mention this aspect for this laptop."
                  : undefined}
                onClick={() => loadEvidence(aspect)}
              >
                {!hasDirectReviewEvidence(aspect)
                  ? "No reviews"
                  : loadingAspectId === aspect.aspect_id
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

// Visualize stored, offline-calculated scores. This chart never runs ATE/ABSA
// or changes the user's preference-based recommendation ranking.
function AspectScoreChart({ aspects }) {
  const ordered = [...aspects].sort((a, b) => {
    const aSupported = hasDirectReviewEvidence(a);
    const bSupported = hasDirectReviewEvidence(b);
    if (aSupported !== bSupported) return aSupported ? -1 : 1;
    return (supportedScore100(b) ?? -1) - (supportedScore100(a) ?? -1) ||
      a.aspect_name.localeCompare(b.aspect_name);
  });

  return (
    <section className="aspect-score-chart" aria-labelledby="aspect-chart-title">
      <div className="aspect-score-chart-heading">
        <div>
          <h3 id="aspect-chart-title">Aspect score overview</h3>
          <p>
            All {aspects.length} selectable aspects. Supported aspects are ordered
            by adjusted score, with no-evidence aspects last. Scores do not depend
            on your current preference weights.
          </p>
        </div>
        <span className="aspect-score-chart-count">0–100 scale</span>
      </div>

      <div className="aspect-score-chart-legend">
        <span className="aspect-score-chart-key" aria-hidden="true" />
        <span>Adjusted sentiment score</span>
        <span className="aspect-score-chart-legend-divider" aria-hidden="true">·</span>
        <span>Evidence strength is shown separately</span>
      </div>

      <div
        className="aspect-score-chart-scroll"
        role="region"
        aria-label="All selectable laptop aspects, with unsupported aspects listed last"
        tabIndex={0}
      >
        <div className="aspect-score-chart-columns" aria-label="Aspect score column headings">
          <span>Aspect</span>
          <span>Score bar</span>
          <span>Score</span>
          <span>Evidence</span>
        </div>
        {ordered.map((aspect) => {
          const score = supportedScore100(aspect);
          const label = (aspect.evidence_level || "no_evidence").replaceAll("_", " ");
          const mentions = aspect.mention_count ?? 0;
          const confidence = Number(aspect.evidence_confidence ?? 0) * 100;
          const scoreLabel = score === null ? "N/A (no direct evidence)" : `${score.toFixed(1)}/100`;

          return (
            <div
              className={`aspect-score-chart-row ${
                hasDirectReviewEvidence(aspect) ? "" : "no-direct-evidence"
              }`}
              key={aspect.aspect_id}
              title={`${aspect.aspect_name}: ${scoreLabel}; ${mentions} mentions; ${confidence.toFixed(1)}% evidence support; ${label} evidence`}
            >
              <span className="aspect-score-chart-name">{aspect.aspect_name}</span>
              <div
                className="aspect-score-chart-track"
                role="img"
                aria-label={score === null
                  ? `${aspect.aspect_name}: no direct review evidence`
                  : `${aspect.aspect_name}: ${scoreLabel}`}
              >
                {score !== null && (
                  <div
                    className="aspect-score-chart-fill"
                    style={{ width: `${score}%` }}
                    aria-hidden="true"
                  />
                )}
              </div>
              <strong className="aspect-score-chart-value">
                {score === null ? "N/A" : score.toFixed(1)}
              </strong>
              <span className="aspect-score-chart-evidence">
                <b className={evidenceClass(aspect.evidence_level)}>{label}</b>
              </span>
            </div>
          );
        })}
      </div>

      <p className="aspect-score-chart-note">
        Bars show stored, prior-adjusted review sentiment scores, not hardware
        benchmarks. N/A means zero direct mentions; these aspects have no plotted
        score, even though the ranking engine uses their global prior as a fallback.
        Limited or insufficient evidence should not be treated as confirmed quality.
      </p>
    </section>
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
          <span title={EVIDENCE_SUPPORT_EXPLANATION}>Evidence support ⓘ</span>
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
        text using aspect phrases detected by the ATE and canonical aspect categorization and normalization pipeline.
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
