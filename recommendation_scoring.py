"""
Evidence-aware recommendation scoring for the laptop recommendation thesis.

This script consumes the FINAL canonical aspect v3 laptop-level experience summary and
creates reusable aspect scores for recommendation and Neo4j import.

Default input
-------------
pipeline_output_v3/laptop_experience_aspect_summary_v3.csv

Core scoring policy
-------------------
For one laptop l and aspect a:

    n = positive + negative + neutral + mixed

    raw_score = (
        1.0 * positive
        + neutral_weight * neutral
        + mixed_weight * mixed
        + 0.0 * negative
    ) / n

The global aspect prior is calculated with the same formula using all laptops.
The evidence-aware score is then:

    adjusted_score = (n * raw_score + k * prior_score) / (n + k)

where k is the prior strength (default 10 review-equivalents).

Confidence is kept SEPARATE from quality:

    confidence = n / (n + k)

Evidence labels
---------------
0 reviews      -> no_evidence
1-4 reviews    -> insufficient
5-9 reviews    -> limited
10-19 reviews  -> moderate
20+ reviews    -> strong

Missing laptop-aspect combinations are explicitly created. They receive:
    adjusted_score = global aspect prior
    confidence = 0
    evidence_level = no_evidence

This avoids incorrectly treating missing evidence as a score of zero.

Optional weighted ranking
-------------------------
Pass weights using canonical aspect identifiers, e.g.:

    python recommendation_scoring.py \
        --weights "BATTERY_LIFE=50,PERFORMANCE=30,THERMAL_PERFORMANCE=20"

Weights do not need to sum to 100; they are normalized automatically.
Recommendation score and evidence confidence are both reported on 0-100 scales
but remain separate values.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, Iterable, Tuple

import numpy as np
import pandas as pd


DEFAULT_INPUT = Path("pipeline_output_v3/laptop_experience_aspect_summary_v3.csv")
DEFAULT_OUTPUT_DIR = Path("recommendation_scores")
DEFAULT_PRIOR_STRENGTH = 10.0
DEFAULT_NEUTRAL_WEIGHT = 0.5
DEFAULT_MIXED_WEIGHT = 0.5

REQUIRED_COLUMNS = {
    "laptop",
    "canonical_aspect",
    "canonical_label",
    "aspect_type",
    "positive_reviews",
    "negative_reviews",
    "neutral_reviews",
    "mixed_reviews",
    "reviews_mentioning_aspect",
}

COUNT_COLUMNS = [
    "positive_reviews",
    "negative_reviews",
    "neutral_reviews",
    "mixed_reviews",
    "reviews_mentioning_aspect",
]


def evidence_level(n: int) -> str:
    """Convert review support count into a human-readable evidence tier."""
    if n <= 0:
        return "no_evidence"
    if n < 5:
        return "insufficient"
    if n < 10:
        return "limited"
    if n < 20:
        return "moderate"
    return "strong"


def validate_input(df: pd.DataFrame) -> pd.DataFrame:
    """Validate schema and aggregation arithmetic, then return a clean copy."""
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(
            "Input file is missing required columns: "
            + ", ".join(sorted(missing))
        )

    clean = df.copy()

    # The recommendation layer should only use user-experience aspects.
    clean = clean[clean["aspect_type"].astype(str).str.lower() == "experience"].copy()
    if clean.empty:
        raise ValueError("No rows with aspect_type='experience' were found.")

    for col in COUNT_COLUMNS:
        clean[col] = pd.to_numeric(clean[col], errors="raise").astype(int)
        if (clean[col] < 0).any():
            raise ValueError(f"Column '{col}' contains negative counts.")

    calculated_mentions = (
        clean["positive_reviews"]
        + clean["negative_reviews"]
        + clean["neutral_reviews"]
        + clean["mixed_reviews"]
    )

    mismatch = calculated_mentions != clean["reviews_mentioning_aspect"]
    if mismatch.any():
        examples = clean.loc[
            mismatch,
            [
                "laptop",
                "canonical_aspect",
                "positive_reviews",
                "negative_reviews",
                "neutral_reviews",
                "mixed_reviews",
                "reviews_mentioning_aspect",
            ],
        ].head(5)
        raise ValueError(
            "Aggregation validation failed: sentiment counts do not equal "
            "reviews_mentioning_aspect for some rows. Examples:\n"
            + examples.to_string(index=False)
        )

    duplicate_pairs = clean.duplicated(["laptop", "canonical_aspect"], keep=False)
    if duplicate_pairs.any():
        examples = clean.loc[
            duplicate_pairs, ["laptop", "canonical_aspect"]
        ].head(10)
        raise ValueError(
            "Duplicate laptop/canonical_aspect rows were found. Examples:\n"
            + examples.to_string(index=False)
        )

    return clean.reset_index(drop=True)


def score_from_counts(
    positive: pd.Series,
    neutral: pd.Series,
    mixed: pd.Series,
    mentions: pd.Series,
    neutral_weight: float,
    mixed_weight: float,
) -> pd.Series:
    """Calculate direct sentiment score. Returns NaN where mentions == 0."""
    numerator = (
        positive.astype(float)
        + neutral_weight * neutral.astype(float)
        + mixed_weight * mixed.astype(float)
    )

    denominator = mentions.astype(float)
    return numerator.div(denominator.where(denominator > 0))


def compute_aspect_priors(
    df: pd.DataFrame,
    neutral_weight: float = DEFAULT_NEUTRAL_WEIGHT,
    mixed_weight: float = DEFAULT_MIXED_WEIGHT,
) -> pd.DataFrame:
    """Compute one global prior for every canonical experience aspect."""
    grouped = (
        df.groupby(["canonical_aspect", "canonical_label"], as_index=False)
        .agg(
            total_positive_reviews=("positive_reviews", "sum"),
            total_negative_reviews=("negative_reviews", "sum"),
            total_neutral_reviews=("neutral_reviews", "sum"),
            total_mixed_reviews=("mixed_reviews", "sum"),
            total_reviews_mentioning_aspect=("reviews_mentioning_aspect", "sum"),
            laptops_with_evidence=("laptop", "nunique"),
        )
    )

    grouped["prior_positive_ratio"] = (
        grouped["total_positive_reviews"]
        / grouped["total_reviews_mentioning_aspect"].replace(0, np.nan)
    )

    grouped["prior_score"] = score_from_counts(
        grouped["total_positive_reviews"],
        grouped["total_neutral_reviews"],
        grouped["total_mixed_reviews"],
        grouped["total_reviews_mentioning_aspect"],
        neutral_weight,
        mixed_weight,
    )

    grouped["prior_score_0_100"] = 100.0 * grouped["prior_score"]

    return grouped.sort_values(
        ["total_reviews_mentioning_aspect", "canonical_aspect"],
        ascending=[False, True],
    ).reset_index(drop=True)


def build_complete_laptop_aspect_scores(
    df: pd.DataFrame,
    priors: pd.DataFrame,
    prior_strength: float = DEFAULT_PRIOR_STRENGTH,
    neutral_weight: float = DEFAULT_NEUTRAL_WEIGHT,
    mixed_weight: float = DEFAULT_MIXED_WEIGHT,
) -> pd.DataFrame:
    """
    Create a complete laptop x canonical-aspect matrix and calculate evidence-aware scores.

    Missing combinations are retained with zero observed reviews, prior-only adjusted score,
    and zero evidence confidence.
    """
    if prior_strength <= 0:
        raise ValueError("prior_strength must be greater than zero.")

    laptops = pd.DataFrame({"laptop": sorted(df["laptop"].unique())})
    aspects = priors[["canonical_aspect", "canonical_label"]].drop_duplicates().copy()

    # Cross join to ensure zero-evidence combinations are represented explicitly.
    laptops["_key"] = 1
    aspects["_key"] = 1
    complete = laptops.merge(aspects, on="_key").drop(columns="_key")

    observed_cols = [
        "laptop",
        "canonical_aspect",
        "positive_reviews",
        "negative_reviews",
        "neutral_reviews",
        "mixed_reviews",
        "reviews_mentioning_aspect",
    ]

    complete = complete.merge(
        df[observed_cols],
        on=["laptop", "canonical_aspect"],
        how="left",
        validate="one_to_one",
    )

    for col in COUNT_COLUMNS:
        complete[col] = complete[col].fillna(0).astype(int)

    complete["has_direct_evidence"] = complete["reviews_mentioning_aspect"] > 0

    complete["positive_ratio"] = (
        complete["positive_reviews"]
        / complete["reviews_mentioning_aspect"].replace(0, np.nan)
    )

    complete["raw_sentiment_score"] = score_from_counts(
        complete["positive_reviews"],
        complete["neutral_reviews"],
        complete["mixed_reviews"],
        complete["reviews_mentioning_aspect"],
        neutral_weight,
        mixed_weight,
    )

    prior_cols = [
        "canonical_aspect",
        "prior_positive_ratio",
        "prior_score",
        "prior_score_0_100",
        "total_reviews_mentioning_aspect",
        "laptops_with_evidence",
    ]
    complete = complete.merge(
        priors[prior_cols],
        on="canonical_aspect",
        how="left",
        validate="many_to_one",
    )

    n = complete["reviews_mentioning_aspect"].astype(float)

    # Algebraically equivalent to n*raw_score, but this form also works when n=0.
    observed_weighted_sum = (
        complete["positive_reviews"].astype(float)
        + neutral_weight * complete["neutral_reviews"].astype(float)
        + mixed_weight * complete["mixed_reviews"].astype(float)
    )

    complete["adjusted_score"] = (
        observed_weighted_sum + prior_strength * complete["prior_score"]
    ) / (n + prior_strength)

    complete["evidence_confidence"] = n / (n + prior_strength)
    complete["evidence_level"] = complete["reviews_mentioning_aspect"].map(evidence_level)

    complete["raw_sentiment_score_0_100"] = 100.0 * complete["raw_sentiment_score"]
    complete["adjusted_score_0_100"] = 100.0 * complete["adjusted_score"]
    complete["evidence_confidence_0_100"] = 100.0 * complete["evidence_confidence"]

    # Useful for explanations and auditability.
    complete["prior_strength"] = float(prior_strength)
    complete["neutral_weight"] = float(neutral_weight)
    complete["mixed_weight"] = float(mixed_weight)

    output_order = [
        "laptop",
        "canonical_aspect",
        "canonical_label",
        "positive_reviews",
        "negative_reviews",
        "neutral_reviews",
        "mixed_reviews",
        "reviews_mentioning_aspect",
        "positive_ratio",
        "raw_sentiment_score",
        "raw_sentiment_score_0_100",
        "prior_score",
        "prior_score_0_100",
        "adjusted_score",
        "adjusted_score_0_100",
        "evidence_confidence",
        "evidence_confidence_0_100",
        "evidence_level",
        "has_direct_evidence",
        "prior_positive_ratio",
        "total_reviews_mentioning_aspect",
        "laptops_with_evidence",
        "prior_strength",
        "neutral_weight",
        "mixed_weight",
    ]

    return complete[output_order].sort_values(
        ["laptop", "canonical_aspect"]
    ).reset_index(drop=True)


def parse_weights(weight_string: str) -> Dict[str, float]:
    """Parse 'ASPECT=weight,ASPECT=weight' into a dictionary."""
    weights: Dict[str, float] = {}

    if not weight_string or not weight_string.strip():
        raise ValueError("Weight string is empty.")

    for item in weight_string.split(","):
        item = item.strip()
        if not item:
            continue
        if "=" not in item:
            raise ValueError(
                f"Invalid weight entry '{item}'. Expected CANONICAL_ASPECT=weight."
            )

        aspect, value = item.split("=", 1)
        aspect = aspect.strip().upper()
        if not aspect:
            raise ValueError(f"Invalid blank aspect in weight entry '{item}'.")

        try:
            weight = float(value.strip())
        except ValueError as exc:
            raise ValueError(f"Invalid numeric weight in '{item}'.") from exc

        if weight < 0:
            raise ValueError(f"Weights cannot be negative: '{item}'.")
        if aspect in weights:
            raise ValueError(f"Aspect '{aspect}' was supplied more than once.")

        weights[aspect] = weight

    if not weights:
        raise ValueError("No usable weights were supplied.")
    if sum(weights.values()) <= 0:
        raise ValueError("At least one weight must be greater than zero.")

    return weights


def normalize_weights(
    weights: Dict[str, float], available_aspects: Iterable[str]
) -> Dict[str, float]:
    """Validate aspect keys and normalize positive weights to sum to 1."""
    available = set(available_aspects)
    unknown = sorted(set(weights) - available)
    if unknown:
        raise ValueError(
            "Unknown canonical aspect(s): "
            + ", ".join(unknown)
            + "\nAvailable aspects: "
            + ", ".join(sorted(available))
        )

    positive = {aspect: weight for aspect, weight in weights.items() if weight > 0}
    total = sum(positive.values())
    return {aspect: weight / total for aspect, weight in positive.items()}


def rank_laptops(
    scores: pd.DataFrame,
    weights: Dict[str, float],
    top_n: int | None = None,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Calculate weighted recommendation scores and separate evidence confidence.

    Returns
    -------
    ranking_df:
        One row per laptop.
    breakdown_df:
        One row per laptop x selected aspect showing each contribution.
    """
    normalized_weights = normalize_weights(
        weights,
        scores["canonical_aspect"].unique(),
    )

    selected = scores[
        scores["canonical_aspect"].isin(normalized_weights)
    ].copy()
    selected["normalized_weight"] = selected["canonical_aspect"].map(normalized_weights)

    selected["score_contribution"] = (
        selected["normalized_weight"] * selected["adjusted_score"] * 100.0
    )
    selected["confidence_contribution"] = (
        selected["normalized_weight"] * selected["evidence_confidence"] * 100.0
    )

    selected["aspect_score_0_100"] = selected["adjusted_score"] * 100.0
    selected["aspect_confidence_0_100"] = selected["evidence_confidence"] * 100.0

    ranking = (
        selected.groupby("laptop", as_index=False)
        .agg(
            recommendation_score=("score_contribution", "sum"),
            evidence_confidence=("confidence_contribution", "sum"),
            selected_aspects=("canonical_aspect", "count"),
            aspects_with_direct_evidence=("has_direct_evidence", "sum"),
            total_selected_aspect_mentions=("reviews_mentioning_aspect", "sum"),
            minimum_aspect_confidence=("aspect_confidence_0_100", "min"),
        )
    )

    # A compact indicator that can be displayed in UI or used as a tie-break diagnostic.
    no_evidence_counts = (
        selected.assign(no_evidence=(~selected["has_direct_evidence"]).astype(int))
        .groupby("laptop")["no_evidence"]
        .sum()
    )
    ranking["selected_aspects_without_evidence"] = (
        ranking["laptop"].map(no_evidence_counts).fillna(0).astype(int)
    )

    ranking = ranking.sort_values(
        ["recommendation_score", "evidence_confidence", "laptop"],
        ascending=[False, False, True],
    ).reset_index(drop=True)
    ranking.insert(0, "rank", range(1, len(ranking) + 1))

    if top_n is not None:
        if top_n <= 0:
            raise ValueError("top_n must be greater than zero when supplied.")
        ranking = ranking.head(top_n).copy()

    ranking["recommendation_score"] = ranking["recommendation_score"].round(4)
    ranking["evidence_confidence"] = ranking["evidence_confidence"].round(4)
    ranking["minimum_aspect_confidence"] = ranking["minimum_aspect_confidence"].round(4)

    breakdown_cols = [
        "laptop",
        "canonical_aspect",
        "canonical_label",
        "normalized_weight",
        "aspect_score_0_100",
        "aspect_confidence_0_100",
        "evidence_level",
        "reviews_mentioning_aspect",
        "positive_reviews",
        "negative_reviews",
        "neutral_reviews",
        "mixed_reviews",
        "positive_ratio",
        "score_contribution",
        "confidence_contribution",
    ]

    breakdown = selected[breakdown_cols].copy()
    rank_map = ranking.set_index("laptop")["rank"]
    breakdown["rank"] = breakdown["laptop"].map(rank_map)
    breakdown = breakdown[breakdown["rank"].notna()].copy()
    breakdown["rank"] = breakdown["rank"].astype(int)

    breakdown = breakdown.sort_values(
        ["rank", "normalized_weight", "canonical_aspect"],
        ascending=[True, False, True],
    ).reset_index(drop=True)

    for col in [
        "normalized_weight",
        "aspect_score_0_100",
        "aspect_confidence_0_100",
        "score_contribution",
        "confidence_contribution",
    ]:
        breakdown[col] = breakdown[col].round(4)

    return ranking, breakdown


def save_outputs(
    input_path: Path,
    output_dir: Path,
    priors: pd.DataFrame,
    scores: pd.DataFrame,
    prior_strength: float,
    neutral_weight: float,
    mixed_weight: float,
    ranking: pd.DataFrame | None = None,
    breakdown: pd.DataFrame | None = None,
    weights: Dict[str, float] | None = None,
) -> None:
    """Save all generated artifacts and a machine-readable scoring configuration."""
    output_dir.mkdir(parents=True, exist_ok=True)

    priors_path = output_dir / "aspect_priors.csv"
    scores_path = output_dir / "laptop_aspect_scores.csv"
    config_path = output_dir / "scoring_config.json"

    priors.to_csv(priors_path, index=False)
    scores.to_csv(scores_path, index=False)

    config = {
        "input_file": str(input_path),
        "prior_strength_k": prior_strength,
        "positive_weight": 1.0,
        "negative_weight": 0.0,
        "neutral_weight": neutral_weight,
        "mixed_weight": mixed_weight,
        "evidence_levels": {
            "no_evidence": "0 reviews",
            "insufficient": "1-4 reviews",
            "limited": "5-9 reviews",
            "moderate": "10-19 reviews",
            "strong": "20+ reviews",
        },
        "weighted_ranking_weights": weights,
    }
    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")

    print(f"Saved aspect priors:          {priors_path}")
    print(f"Saved laptop-aspect scores:   {scores_path}")
    print(f"Saved scoring configuration:  {config_path}")

    if ranking is not None and breakdown is not None:
        ranking_path = output_dir / "recommendation_ranking.csv"
        breakdown_path = output_dir / "recommendation_ranking_breakdown.csv"
        ranking.to_csv(ranking_path, index=False)
        breakdown.to_csv(breakdown_path, index=False)
        print(f"Saved weighted ranking:       {ranking_path}")
        print(f"Saved ranking breakdown:      {breakdown_path}")


def print_summary(priors: pd.DataFrame, scores: pd.DataFrame) -> None:
    """Print useful validation information after scoring."""
    laptops = scores["laptop"].nunique()
    aspects = scores["canonical_aspect"].nunique()
    expected_rows = laptops * aspects

    print("\n" + "=" * 92)
    print("RECOMMENDATION SCORING SUMMARY")
    print("=" * 92)
    print(f"Laptops:                         {laptops}")
    print(f"Experience aspects:              {aspects}")
    print(f"Complete laptop-aspect rows:     {len(scores)} / {expected_rows}")
    print(f"Rows with direct evidence:       {int(scores['has_direct_evidence'].sum())}")
    print(f"Rows with no direct evidence:    {int((~scores['has_direct_evidence']).sum())}")

    print("\nEvidence-level distribution:")
    counts = scores["evidence_level"].value_counts()
    ordered_levels = ["no_evidence", "insufficient", "limited", "moderate", "strong"]
    for level in ordered_levels:
        print(f"  {level:13s}: {int(counts.get(level, 0))}")

    print("\nAspect priors (highest support first):")
    preview = priors[
        [
            "canonical_aspect",
            "canonical_label",
            "total_reviews_mentioning_aspect",
            "prior_score_0_100",
        ]
    ].copy()
    preview["prior_score_0_100"] = preview["prior_score_0_100"].round(2)
    print(preview.to_string(index=False))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create evidence-aware laptop aspect scores and optionally a weighted "
            "recommendation ranking."
        )
    )

    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help=(
            "Canonical aspect v3 laptop experience summary CSV "
            f"(default: {DEFAULT_INPUT})."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Output directory (default: {DEFAULT_OUTPUT_DIR}).",
    )
    parser.add_argument(
        "--prior-strength",
        type=float,
        default=DEFAULT_PRIOR_STRENGTH,
        help=(
            "Global-prior strength k in equivalent reviews "
            f"(default: {DEFAULT_PRIOR_STRENGTH:g})."
        ),
    )
    parser.add_argument(
        "--neutral-weight",
        type=float,
        default=DEFAULT_NEUTRAL_WEIGHT,
        help=f"Neutral sentiment value on 0-1 scale (default: {DEFAULT_NEUTRAL_WEIGHT}).",
    )
    parser.add_argument(
        "--mixed-weight",
        type=float,
        default=DEFAULT_MIXED_WEIGHT,
        help=f"Mixed sentiment value on 0-1 scale (default: {DEFAULT_MIXED_WEIGHT}).",
    )
    parser.add_argument(
        "--weights",
        type=str,
        default=None,
        help=(
            "Optional user ranking weights, e.g. "
            '"BATTERY_LIFE=50,PERFORMANCE=30,THERMAL_PERFORMANCE=20".'
        ),
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=None,
        help="Optionally keep only the top N laptops in weighted ranking output.",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if not 0 <= args.neutral_weight <= 1:
        raise ValueError("--neutral-weight must be between 0 and 1.")
    if not 0 <= args.mixed_weight <= 1:
        raise ValueError("--mixed-weight must be between 0 and 1.")
    if args.prior_strength <= 0:
        raise ValueError("--prior-strength must be greater than zero.")

    if not args.input.exists():
        raise FileNotFoundError(
            f"Input file not found: {args.input}\n"
            "If your file is elsewhere, supply --input with its path."
        )

    print(f"Reading final experience summary: {args.input}")
    source_df = pd.read_csv(args.input)
    source_df = validate_input(source_df)

    priors = compute_aspect_priors(
        source_df,
        neutral_weight=args.neutral_weight,
        mixed_weight=args.mixed_weight,
    )

    scores = build_complete_laptop_aspect_scores(
        source_df,
        priors,
        prior_strength=args.prior_strength,
        neutral_weight=args.neutral_weight,
        mixed_weight=args.mixed_weight,
    )

    ranking = None
    breakdown = None
    normalized_weight_config = None

    if args.weights:
        user_weights = parse_weights(args.weights)
        normalized_weight_config = normalize_weights(
            user_weights,
            scores["canonical_aspect"].unique(),
        )
        ranking, breakdown = rank_laptops(
            scores,
            user_weights,
            top_n=args.top_n,
        )

    save_outputs(
        input_path=args.input,
        output_dir=args.output_dir,
        priors=priors,
        scores=scores,
        prior_strength=args.prior_strength,
        neutral_weight=args.neutral_weight,
        mixed_weight=args.mixed_weight,
        ranking=ranking,
        breakdown=breakdown,
        weights=normalized_weight_config,
    )

    print_summary(priors, scores)

    if ranking is not None:
        print("\nWeighted recommendation ranking:")
        print(
            ranking[
                [
                    "rank",
                    "laptop",
                    "recommendation_score",
                    "evidence_confidence",
                    "selected_aspects_without_evidence",
                ]
            ].to_string(index=False)
        )


if __name__ == "__main__":
    main()
