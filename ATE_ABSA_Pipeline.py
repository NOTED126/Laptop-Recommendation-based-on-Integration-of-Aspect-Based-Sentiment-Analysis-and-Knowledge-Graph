import argparse
import os
import re
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd
import torch
from transformers import (
    AutoModelForSequenceClassification,
    AutoModelForTokenClassification,
    AutoTokenizer,
)

from ATE_train_model import extract_aspects
from ABSA_train_model import predict_aspect_sentiment
from canonical_aspect_mapping import classify_aspect, canonical_aspect_table


ATE_MODEL_PATH = "aspect_extraction/best_model"
ABSA_MODEL_PATH = "aspect_sentiment/best_model"
DEFAULT_MAX_LENGTH = 128
DEFAULT_OVERLAP_TOKENS = 16


# -----------------------------
# Model loading
# -----------------------------
def load_pipeline_models(
    ate_model_path=ATE_MODEL_PATH,
    absa_model_path=ABSA_MODEL_PATH,
):
    if not os.path.exists(ate_model_path) or not os.path.exists(absa_model_path):
        raise FileNotFoundError(
            "Make sure both fine-tuned models have been generated before running. "
            f"Expected '{ate_model_path}' and '{absa_model_path}'."
        )

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Executing ATE+ABSA inference using device: {device}\n")

    print(f"Loading ATE model from: {ate_model_path}")
    aspect_model = AutoModelForTokenClassification.from_pretrained(ate_model_path).to(device)
    aspect_tokenizer = AutoTokenizer.from_pretrained(ate_model_path)
    aspect_model.eval()

    print(f"Loading ABSA model from: {absa_model_path}")
    sentiment_model = AutoModelForSequenceClassification.from_pretrained(absa_model_path).to(device)
    sentiment_tokenizer = AutoTokenizer.from_pretrained(absa_model_path)
    sentiment_model.eval()

    return (
        aspect_model,
        aspect_tokenizer,
        sentiment_model,
        sentiment_tokenizer,
        device,
    )


# -----------------------------
# Text preparation
# -----------------------------
def clean_review_text(text):
    """Normalize whitespace without changing the review's wording."""
    if pd.isna(text):
        return ""
    return re.sub(r"\s+", " ", str(text)).strip()


def split_into_sentences(text):
    """
    Lightweight sentence splitter with no external dependency.

    Best Buy reviews often contain multiple aspect opinions in one review. Running
    the models sentence-by-sentence keeps local sentiment context and prevents a
    long review from being silently truncated as one 128-token sequence.
    """
    text = clean_review_text(text)
    if not text:
        return []

    sentences = re.split(r"(?<=[.!?])\s+", text)
    return [sentence.strip() for sentence in sentences if sentence.strip()]


def split_text_into_token_windows(
    text,
    tokenizer,
    max_length=DEFAULT_MAX_LENGTH,
    overlap_tokens=DEFAULT_OVERLAP_TOKENS,
):
    """
    Split one unusually long sentence into overlapping token windows while
    slicing from the original text using tokenizer offsets.

    This preserves the original wording used by ATE's offset-based extraction.
    """
    text = clean_review_text(text)
    if not text:
        return []

    encoded = tokenizer(
        text,
        add_special_tokens=False,
        return_offsets_mapping=True,
        truncation=False,
    )
    offsets = encoded["offset_mapping"]

    special_tokens = tokenizer.num_special_tokens_to_add(pair=False)
    content_window = max_length - special_tokens
    if content_window <= 0:
        raise ValueError("max_length is too small for the tokenizer's special tokens")

    if len(offsets) <= content_window:
        return [text]

    if overlap_tokens >= content_window:
        raise ValueError("overlap_tokens must be smaller than the usable token window")

    step = content_window - overlap_tokens
    windows = []

    for token_start in range(0, len(offsets), step):
        token_end = min(token_start + content_window, len(offsets))
        if token_start >= token_end:
            break

        char_start = offsets[token_start][0]
        char_end = offsets[token_end - 1][1]
        chunk = text[char_start:char_end].strip()
        if chunk:
            windows.append(chunk)

        if token_end == len(offsets):
            break

    return windows


def review_segments(
    review_text,
    aspect_tokenizer,
    max_length=DEFAULT_MAX_LENGTH,
    overlap_tokens=DEFAULT_OVERLAP_TOKENS,
):
    """Yield sentence/window metadata for one full review."""
    segments = []

    for sentence_id, sentence in enumerate(split_into_sentences(review_text), start=1):
        windows = split_text_into_token_windows(
            sentence,
            aspect_tokenizer,
            max_length=max_length,
            overlap_tokens=overlap_tokens,
        )

        for window_id, window in enumerate(windows, start=1):
            segments.append(
                {
                    "sentence_id": sentence_id,
                    "window_id": window_id,
                    "text": window,
                }
            )

    return segments


# -----------------------------
# ATE + ABSA inference
# -----------------------------
def ate_absa_pipeline(
    text,
    aspect_model,
    aspect_tokenizer,
    sentiment_model,
    sentiment_tokenizer,
    max_length=DEFAULT_MAX_LENGTH,
):
    """Run ATE followed by ABSA on one sentence or token window."""
    aspects = extract_aspects(
        text,
        aspect_model,
        aspect_tokenizer,
        max_length=max_length,
    )

    # Case-insensitive de-duplication while preserving the first original form.
    seen = set()
    unique_aspects = []
    for aspect in aspects:
        aspect = aspect.strip()
        key = aspect.casefold()
        if aspect and key not in seen:
            seen.add(key)
            unique_aspects.append(aspect)

    results = []
    for aspect in unique_aspects:
        sentiment = predict_aspect_sentiment(
            text,
            aspect,
            sentiment_model,
            sentiment_tokenizer,
            max_length=max_length,
        )
        results.append((aspect, sentiment))

    return results


def normalize_aspect_text(aspect):
    """
    Apply only surface-form normalization.

    Semantic mappings such as 'screen' -> 'display' or 'thermals' -> 'cooling'
    should be added later in a dedicated canonical laptop aspect categorization and normalization scheme after inspecting
    the real extraction output.
    """
    aspect = clean_review_text(aspect).casefold()
    aspect = aspect.strip(" \t\n\r.,;:!?\"'()[]{}")
    return aspect


def process_review(
    review_text,
    review_id,
    aspect_model,
    aspect_tokenizer,
    sentiment_model,
    sentiment_tokenizer,
    max_length=DEFAULT_MAX_LENGTH,
    overlap_tokens=DEFAULT_OVERLAP_TOKENS,
):
    """Return raw aspect-sentiment predictions for one complete review."""
    rows = []
    overlap_dedup = set()

    for segment in review_segments(
        review_text,
        aspect_tokenizer,
        max_length=max_length,
        overlap_tokens=overlap_tokens,
    ):
        predictions = ate_absa_pipeline(
            segment["text"],
            aspect_model,
            aspect_tokenizer,
            sentiment_model,
            sentiment_tokenizer,
            max_length=max_length,
        )

        for aspect, sentiment in predictions:
            aspect_key = normalize_aspect_text(aspect)
            if not aspect_key:
                continue

            # Overlapping windows may detect the same aspect twice. Remove only
            # those duplicate observations within the same sentence.
            dedup_key = (segment["sentence_id"], aspect_key, sentiment)
            if dedup_key in overlap_dedup:
                continue
            overlap_dedup.add(dedup_key)

            mapping_decision = classify_aspect(aspect, segment["text"])

            rows.append(
                {
                    "review_id": review_id,
                    "sentence_id": segment["sentence_id"],
                    "window_id": segment["window_id"],
                    "context": segment["text"],
                    "aspect": aspect,
                    "aspect_key": aspect_key,
                    "sentiment": sentiment,
                    "mapping_status": mapping_decision.mapping_status,
                    "canonical_aspect": mapping_decision.canonical_aspect,
                    "canonical_label": mapping_decision.canonical_label,
                    "aspect_type": mapping_decision.aspect_type,
                    "mapping_method": mapping_decision.mapping_method,
                    "mapping_reason": mapping_decision.mapping_reason,
                }
            )

    return rows


# -----------------------------
# Review/laptop aggregation
# -----------------------------
def collapse_to_review_level(raw_predictions):
    """
    Give each review at most one final label per surface-normalized aspect.

    Repeated mentions use majority sentiment. A tie becomes 'mixed' rather than
    being incorrectly forced into the model's 'neutral' class.
    """
    if not raw_predictions:
        return []

    grouped = defaultdict(list)
    display_forms = defaultdict(list)

    for row in raw_predictions:
        key = (row["review_id"], row["aspect_key"])
        grouped[key].append(row["sentiment"])
        display_forms[key].append(row["aspect"])

    rows = []
    for (review_id, aspect_key), sentiments in grouped.items():
        counts = Counter(sentiments)
        highest_count = max(counts.values())
        winners = [label for label, count in counts.items() if count == highest_count]
        final_sentiment = winners[0] if len(winners) == 1 else "mixed"
        display_aspect = Counter(display_forms[(review_id, aspect_key)]).most_common(1)[0][0]

        rows.append(
            {
                "review_id": review_id,
                "aspect": display_aspect,
                "aspect_key": aspect_key,
                "review_sentiment": final_sentiment,
                "positive_mentions": counts.get("positive", 0),
                "negative_mentions": counts.get("negative", 0),
                "neutral_mentions": counts.get("neutral", 0),
            }
        )

    return rows



def collapse_to_canonical_review_level(raw_predictions):
    """
    Collapse mapped raw predictions to one sentiment per canonical aspect per review.

    This is different from ``collapse_to_review_level``: synonyms such as
    ``screen`` and ``display`` are merged into one ``DISPLAY_QUALITY`` opinion.
    Rejected and unmapped ATE terms are deliberately excluded from canonical
    aggregation but remain available in the raw output for canonical aspect mapping refinement.
    """
    if isinstance(raw_predictions, pd.DataFrame):
        rows_in = raw_predictions.to_dict("records")
    else:
        rows_in = list(raw_predictions)

    mapped = [
        row for row in rows_in
        if row.get("mapping_status") == "mapped" and row.get("canonical_aspect")
    ]
    if not mapped:
        return pd.DataFrame(
            columns=[
                "laptop", "source_file", "review_id", "canonical_aspect",
                "canonical_label", "aspect_type", "review_sentiment",
                "positive_mentions", "negative_mentions", "neutral_mentions",
                "raw_aspects",
            ]
        )

    grouped = defaultdict(list)
    raw_forms = defaultdict(list)
    labels = {}
    types = {}

    for row in mapped:
        key = (
            row.get("laptop", ""),
            row.get("source_file", ""),
            row["review_id"],
            row["canonical_aspect"],
        )
        grouped[key].append(row["sentiment"])
        raw_forms[key].append(row["aspect"])
        labels[key] = row.get("canonical_label", row["canonical_aspect"])
        types[key] = row.get("aspect_type", "experience")

    output = []
    for key, sentiments in grouped.items():
        laptop, source_file, review_id, canonical = key
        counts = Counter(sentiments)
        highest = max(counts.values())
        winners = [sentiment for sentiment, count in counts.items() if count == highest]
        review_sentiment = winners[0] if len(winners) == 1 else "mixed"

        # Keep a readable trace of the surface forms that fed the canonical aspect.
        unique_forms = []
        seen_forms = set()
        for form in raw_forms[key]:
            form_key = normalize_aspect_text(form)
            if form_key not in seen_forms:
                seen_forms.add(form_key)
                unique_forms.append(form)

        output.append(
            {
                "laptop": laptop,
                "source_file": source_file,
                "review_id": review_id,
                "canonical_aspect": canonical,
                "canonical_label": labels[key],
                "aspect_type": types[key],
                "review_sentiment": review_sentiment,
                "positive_mentions": int(counts.get("positive", 0)),
                "negative_mentions": int(counts.get("negative", 0)),
                "neutral_mentions": int(counts.get("neutral", 0)),
                "raw_aspects": " | ".join(unique_forms),
            }
        )

    return pd.DataFrame(output).sort_values(
        ["laptop", "review_id", "aspect_type", "canonical_aspect"]
    ).reset_index(drop=True)


def aggregate_canonical_laptop_aspects(canonical_review_df, aspect_type="experience"):
    """
    Aggregate canonical review-level opinions per laptop.

    By default only user-experience aspects are included in the recommendation
    summary. Passing ``aspect_type='specification'`` produces a separate summary
    of specification-related review mentions.
    """
    columns = [
        "laptop", "canonical_aspect", "canonical_label", "aspect_type",
        "positive_reviews", "negative_reviews", "neutral_reviews",
        "mixed_reviews", "reviews_mentioning_aspect", "positive_ratio",
    ]

    if canonical_review_df is None or canonical_review_df.empty:
        return pd.DataFrame(columns=columns)

    working = canonical_review_df.copy()
    if aspect_type is not None:
        working = working[working["aspect_type"] == aspect_type]

    if working.empty:
        return pd.DataFrame(columns=columns)

    output = []
    for (laptop, canonical, label, current_type), group in working.groupby(
        ["laptop", "canonical_aspect", "canonical_label", "aspect_type"],
        dropna=False,
    ):
        counts = group["review_sentiment"].value_counts()
        total = len(group)
        positive = int(counts.get("positive", 0))

        output.append(
            {
                "laptop": laptop,
                "canonical_aspect": canonical,
                "canonical_label": label,
                "aspect_type": current_type,
                "positive_reviews": positive,
                "negative_reviews": int(counts.get("negative", 0)),
                "neutral_reviews": int(counts.get("neutral", 0)),
                "mixed_reviews": int(counts.get("mixed", 0)),
                "reviews_mentioning_aspect": total,
                "positive_ratio": positive / total if total else 0.0,
            }
        )

    return pd.DataFrame(output).sort_values(
        ["laptop", "reviews_mentioning_aspect", "positive_ratio"],
        ascending=[True, False, False],
    ).reset_index(drop=True)


def summarize_mapping_exceptions(raw_df, status="unmapped"):
    """Summarize unmapped or rejected ATE outputs for iterative canonical aspect mapping review."""
    columns = [
        "aspect_key", "example_forms", "raw_mentions", "reviews_mentioning",
        "laptops_mentioning", "positive_mentions", "negative_mentions",
        "neutral_mentions", "mapping_methods", "mapping_reasons",
    ]

    if raw_df is None or raw_df.empty or "mapping_status" not in raw_df.columns:
        return pd.DataFrame(columns=columns)

    working = raw_df[raw_df["mapping_status"] == status]
    if working.empty:
        return pd.DataFrame(columns=columns)

    output = []
    for aspect_key, group in working.groupby("aspect_key"):
        forms = Counter(group["aspect"].astype(str)).most_common(5)
        output.append(
            {
                "aspect_key": aspect_key,
                "example_forms": " | ".join(form for form, _ in forms),
                "raw_mentions": len(group),
                "reviews_mentioning": group[["source_file", "review_id"]].drop_duplicates().shape[0]
                if "source_file" in group.columns else group["review_id"].nunique(),
                "laptops_mentioning": group["laptop"].nunique() if "laptop" in group.columns else 0,
                "positive_mentions": int((group["sentiment"] == "positive").sum()),
                "negative_mentions": int((group["sentiment"] == "negative").sum()),
                "neutral_mentions": int((group["sentiment"] == "neutral").sum()),
                "mapping_methods": " | ".join(sorted(set(group["mapping_method"].dropna().astype(str)))),
                "mapping_reasons": " | ".join(sorted(set(group["mapping_reason"].dropna().astype(str)))),
            }
        )

    return pd.DataFrame(output).sort_values(
        ["reviews_mentioning", "raw_mentions"], ascending=[False, False]
    ).reset_index(drop=True)


def aggregate_laptop_aspects(review_level_df):
    """Aggregate review-level aspect labels into per-laptop statistics."""
    if review_level_df.empty:
        return pd.DataFrame(
            columns=[
                "laptop",
                "aspect",
                "aspect_key",
                "positive_reviews",
                "negative_reviews",
                "neutral_reviews",
                "mixed_reviews",
                "reviews_mentioning_aspect",
                "positive_ratio",
            ]
        )

    output_rows = []

    for (laptop, aspect_key), group in review_level_df.groupby(["laptop", "aspect_key"]):
        counts = group["review_sentiment"].value_counts()
        total = len(group)
        positive = int(counts.get("positive", 0))
        display_aspect = group["aspect"].value_counts().index[0]

        output_rows.append(
            {
                "laptop": laptop,
                "aspect": display_aspect,
                "aspect_key": aspect_key,
                "positive_reviews": positive,
                "negative_reviews": int(counts.get("negative", 0)),
                "neutral_reviews": int(counts.get("neutral", 0)),
                "mixed_reviews": int(counts.get("mixed", 0)),
                "reviews_mentioning_aspect": total,
                "positive_ratio": positive / total if total else 0.0,
            }
        )

    return pd.DataFrame(output_rows).sort_values(
        ["laptop", "reviews_mentioning_aspect", "positive_ratio"],
        ascending=[True, False, False],
    ).reset_index(drop=True)


def detect_review_column(df, requested_column="Review"):
    """Find the review text column case-insensitively."""
    lookup = {str(column).strip().casefold(): column for column in df.columns}
    requested_key = requested_column.strip().casefold()

    if requested_key in lookup:
        return lookup[requested_key]

    for candidate in ("review", "review text", "review_text", "text"):
        if candidate in lookup:
            return lookup[candidate]

    raise KeyError(
        f"Could not find a review column. Available columns: {list(df.columns)}"
    )


def infer_laptop_name(df, csv_path):
    """Prefer CSV metadata; otherwise derive a readable name from the filename."""
    column_lookup = {str(column).strip().casefold(): column for column in df.columns}

    if "brand" in column_lookup and "model" in column_lookup:
        brand_values = df[column_lookup["brand"]].dropna()
        model_values = df[column_lookup["model"]].dropna()
        if not brand_values.empty and not model_values.empty:
            return f"{brand_values.iloc[0]} {model_values.iloc[0]}".strip()

    for candidate in ("laptop", "laptop name", "product", "product name", "name", "model"):
        if candidate in column_lookup:
            values = df[column_lookup[candidate]].dropna()
            if not values.empty:
                return str(values.iloc[0]).strip()

    stem = Path(csv_path).stem
    stem = re.sub(r"_reviews?$", "", stem, flags=re.IGNORECASE)
    return stem.replace("_", " ").strip()


def process_review_file(
    csv_path,
    aspect_model,
    aspect_tokenizer,
    sentiment_model,
    sentiment_tokenizer,
    review_column="Review",
    max_length=DEFAULT_MAX_LENGTH,
    overlap_tokens=DEFAULT_OVERLAP_TOKENS,
):
    """Process one laptop review CSV and return raw/review-level DataFrames."""
    csv_path = Path(csv_path)
    df = pd.read_csv(csv_path)
    column = detect_review_column(df, review_column)
    laptop = infer_laptop_name(df, csv_path)

    reviews = df[[column]].copy()
    reviews[column] = reviews[column].map(clean_review_text)
    reviews = reviews[reviews[column] != ""]

    before_dedup = len(reviews)
    reviews = reviews.drop_duplicates(subset=[column], keep="first").reset_index(drop=True)
    removed_duplicates = before_dedup - len(reviews)

    print(f"\nProcessing: {csv_path.name}")
    print(f"Laptop: {laptop}")
    print(f"Usable reviews: {len(reviews)} | Duplicate texts removed: {removed_duplicates}")

    raw_rows = []
    review_level_rows = []

    for row_number, review_text in enumerate(reviews[column], start=1):
        predictions = process_review(
            review_text,
            row_number,
            aspect_model,
            aspect_tokenizer,
            sentiment_model,
            sentiment_tokenizer,
            max_length=max_length,
            overlap_tokens=overlap_tokens,
        )

        for row in predictions:
            row["laptop"] = laptop
            row["source_file"] = csv_path.name
        raw_rows.extend(predictions)

        collapsed = collapse_to_review_level(predictions)
        for row in collapsed:
            row["laptop"] = laptop
            row["source_file"] = csv_path.name
        review_level_rows.extend(collapsed)

        if row_number % 25 == 0 or row_number == len(reviews):
            print(f"  Processed {row_number}/{len(reviews)} reviews")

    return pd.DataFrame(raw_rows), pd.DataFrame(review_level_rows)


def process_review_directory(
    reviews_dir,
    output_dir,
    aspect_model,
    aspect_tokenizer,
    sentiment_model,
    sentiment_tokenizer,
    review_column="Review",
    max_length=DEFAULT_MAX_LENGTH,
    overlap_tokens=DEFAULT_OVERLAP_TOKENS,
):
    """
    Process every review CSV and save both raw and canonical aspect normalized outputs.

    The raw files preserve model traceability. Canonical files are the intended
    inputs for the later Neo4j/recommendation stages.
    """
    reviews_dir = Path(reviews_dir)
    output_dir = Path(output_dir)

    if not reviews_dir.exists():
        raise FileNotFoundError(f"Review directory not found: {reviews_dir}")

    csv_files = sorted(reviews_dir.glob("*.csv"))
    if not csv_files:
        raise FileNotFoundError(f"No CSV files found in: {reviews_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)

    all_raw = []
    all_raw_review_level = []

    for csv_path in csv_files:
        raw_df, raw_review_level_df = process_review_file(
            csv_path,
            aspect_model,
            aspect_tokenizer,
            sentiment_model,
            sentiment_tokenizer,
            review_column=review_column,
            max_length=max_length,
            overlap_tokens=overlap_tokens,
        )

        if not raw_df.empty:
            all_raw.append(raw_df)
        if not raw_review_level_df.empty:
            all_raw_review_level.append(raw_review_level_df)

    raw_output = pd.concat(all_raw, ignore_index=True) if all_raw else pd.DataFrame()
    raw_review_output = (
        pd.concat(all_raw_review_level, ignore_index=True)
        if all_raw_review_level else pd.DataFrame()
    )

    canonical_review_output = collapse_to_canonical_review_level(raw_output)
    experience_summary = aggregate_canonical_laptop_aspects(
        canonical_review_output, aspect_type="experience"
    )
    specification_summary = aggregate_canonical_laptop_aspects(
        canonical_review_output, aspect_type="specification"
    )
    unmapped_output = summarize_mapping_exceptions(raw_output, status="unmapped")
    rejected_output = summarize_mapping_exceptions(raw_output, status="rejected")
    canonical_aspects_df = pd.DataFrame(canonical_aspect_table())

    raw_path = output_dir / "raw_aspect_predictions.csv"
    raw_review_path = output_dir / "raw_review_level_aspects.csv"
    canonical_review_path = output_dir / "canonical_review_level_aspects.csv"
    summary_path = output_dir / "laptop_experience_aspect_summary.csv"
    spec_path = output_dir / "laptop_specification_review_mentions.csv"
    unmapped_path = output_dir / "unmapped_aspects.csv"
    rejected_path = output_dir / "rejected_aspects.csv"
    canonical_aspects_path = output_dir / "canonical_aspect_categories.csv"

    raw_output.to_csv(raw_path, index=False)
    raw_review_output.to_csv(raw_review_path, index=False)
    canonical_review_output.to_csv(canonical_review_path, index=False)
    experience_summary.to_csv(summary_path, index=False)
    specification_summary.to_csv(spec_path, index=False)
    unmapped_output.to_csv(unmapped_path, index=False)
    rejected_output.to_csv(rejected_path, index=False)
    canonical_aspects_df.to_csv(canonical_aspects_path, index=False)

    print("\nFinished processing all review files with canonical aspect categorization and normalization.")
    print(f"Raw predictions:                {raw_path}")
    print(f"Raw review-level aspects:       {raw_review_path}")
    print(f"Canonical review-level aspects: {canonical_review_path}")
    print(f"Experience summary:             {summary_path}")
    print(f"Specification mentions:         {spec_path}")
    print(f"Unmapped aspect report:         {unmapped_path}")
    print(f"Rejected aspect report:         {rejected_path}")
    print(f"Canonical aspect categories:            {canonical_aspects_path}")

    if not raw_output.empty:
        status_counts = raw_output["mapping_status"].value_counts()
        total = len(raw_output)
        mapped = int(status_counts.get("mapped", 0))
        print("\nCanonical aspect mapping coverage:")
        print(f"  mapped:   {mapped}/{total} ({mapped / total:.1%})")
        print(f"  unmapped: {int(status_counts.get('unmapped', 0))}/{total}")
        print(f"  rejected: {int(status_counts.get('rejected', 0))}/{total}")

    return (
        raw_output,
        raw_review_output,
        canonical_review_output,
        experience_summary,
        specification_summary,
        unmapped_output,
        rejected_output,
    )


# -----------------------------
# Small interactive/demo mode
# -----------------------------
def run_demo(
    aspect_model,
    aspect_tokenizer,
    sentiment_model,
    sentiment_tokenizer,
    max_length=DEFAULT_MAX_LENGTH,
):
    test_texts = [
        "The computer is great works fast but after a couple months my battery life was not the same taking longer to charge and dying faster.",
        "An excellent machine for the price. It struggles with extensive multitasking, but that's to be expected on a device like this.",
        "I love the display's details, and the keyboard works great. The sound quality is excellent while I'm working.",
        "It runs fast enough for school, but definitely not gaming.",
    ]

    print("\n" + "=" * 45 + " END-TO-END PIPELINE DEMO " + "=" * 45)

    for i, text in enumerate(test_texts, start=1):
        predictions = process_review(
            text,
            i,
            aspect_model,
            aspect_tokenizer,
            sentiment_model,
            sentiment_tokenizer,
            max_length=max_length,
        )

        print(f"\nEXAMPLE {i}: {text}")
        if predictions:
            for idx, row in enumerate(predictions, start=1):
                mapping = (
                    row["canonical_label"]
                    if row.get("mapping_status") == "mapped"
                    else row.get("mapping_status", "unmapped").upper()
                )
                print(
                    f"   - ASPECT {idx}: {row['aspect'].ljust(18)} "
                    f"--> {row['sentiment'].upper():8} | {mapping}"
                )
        else:
            print("   No aspects detected.")

        print("-" * 122)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run the trained ATE+ABSA models on Best Buy laptop reviews."
    )
    parser.add_argument(
        "--reviews-dir",
        type=str,
        default=None,
        help="Directory containing laptop review CSV files. If omitted, demo mode runs.",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="pipeline_output",
        help="Directory used for generated CSV outputs.",
    )
    parser.add_argument(
        "--review-column",
        type=str,
        default="Review",
        help="Name of the review-text column in the CSV files.",
    )
    parser.add_argument(
        "--max-length",
        type=int,
        default=DEFAULT_MAX_LENGTH,
        help="Maximum model sequence length.",
    )
    parser.add_argument(
        "--overlap-tokens",
        type=int,
        default=DEFAULT_OVERLAP_TOKENS,
        help="Overlap between windows for unusually long individual sentences.",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    (
        aspect_model,
        aspect_tokenizer,
        sentiment_model,
        sentiment_tokenizer,
        _,
    ) = load_pipeline_models()

    if args.reviews_dir:
        process_review_directory(
            args.reviews_dir,
            args.output_dir,
            aspect_model,
            aspect_tokenizer,
            sentiment_model,
            sentiment_tokenizer,
            review_column=args.review_column,
            max_length=args.max_length,
            overlap_tokens=args.overlap_tokens,
        )
    else:
        run_demo(
            aspect_model,
            aspect_tokenizer,
            sentiment_model,
            sentiment_tokenizer,
            max_length=args.max_length,
        )


if __name__ == "__main__":
    main()
