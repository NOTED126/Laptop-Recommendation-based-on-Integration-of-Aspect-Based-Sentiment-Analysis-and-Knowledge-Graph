"""
Small-subset tester for the revised ATE_ABSA_Pipeline.py.

Purpose
-------
Run the trained ATE + ABSA models on a small, reproducible subset of real
Best Buy review CSVs before processing the full review collection.

Place this file in the same project directory as:
    ATE_ABSA_Pipeline.py
    ATE_train_model.py
    ABSA_train_model.py
    aspect_extraction/best_model/
    aspect_sentiment/best_model/

Example
-------
python test_pipeline_subset.py --reviews-dir "reviews"

A slightly larger sample:
python test_pipeline_subset.py --reviews-dir "reviews" --laptops 3 --reviews-per-laptop 15

Test specific CSV files:
python test_pipeline_subset.py --reviews-dir "reviews" --files "Laptop_A_reviews.csv" "Laptop_B_reviews.csv"
"""

import argparse
import random
from pathlib import Path

import pandas as pd

from ATE_ABSA_Pipeline import (
    ABSA_MODEL_PATH,
    ATE_MODEL_PATH,
    DEFAULT_MAX_LENGTH,
    DEFAULT_OVERLAP_TOKENS,
    aggregate_laptop_aspects,
    clean_review_text,
    collapse_to_review_level,
    detect_review_column,
    infer_laptop_name,
    load_pipeline_models,
    process_review,
)


def choose_csv_files(reviews_dir, requested_files=None, laptop_count=2, seed=42):
    """Choose specific CSVs or a reproducible random subset of review CSVs."""
    reviews_dir = Path(reviews_dir)

    if not reviews_dir.exists():
        raise FileNotFoundError(f"Review directory not found: {reviews_dir}")

    all_csv_files = sorted(reviews_dir.glob("*.csv"))
    if not all_csv_files:
        raise FileNotFoundError(f"No CSV files found in: {reviews_dir}")

    if requested_files:
        selected = []
        for filename in requested_files:
            path = reviews_dir / filename
            if not path.exists():
                raise FileNotFoundError(f"Requested CSV not found: {path}")
            selected.append(path)
        return selected

    if laptop_count <= 0:
        raise ValueError("--laptops must be at least 1")

    laptop_count = min(laptop_count, len(all_csv_files))
    rng = random.Random(seed)
    return sorted(rng.sample(all_csv_files, laptop_count))


def sample_reviews_from_file(csv_path, review_column="Review", review_count=10, seed=42):
    """Load, clean, de-duplicate and reproducibly sample reviews from one CSV."""
    df = pd.read_csv(csv_path)
    column = detect_review_column(df, review_column)
    laptop = infer_laptop_name(df, csv_path)

    review_df = df[[column]].copy()
    review_df[column] = review_df[column].map(clean_review_text)
    review_df = review_df[review_df[column] != ""]
    review_df = review_df.drop_duplicates(subset=[column], keep="first").reset_index(drop=True)

    if review_df.empty:
        return laptop, pd.DataFrame(columns=["source_row", "review_text"])

    review_count = min(review_count, len(review_df))
    sampled = review_df.sample(n=review_count, random_state=seed).sort_index()

    sampled = sampled.reset_index().rename(columns={"index": "source_row", column: "review_text"})
    # source_row is zero-based from pandas; make it one-based for easier manual lookup.
    sampled["source_row"] = sampled["source_row"] + 1

    return laptop, sampled


def print_review_result(laptop, sample_number, source_row, review_text, predictions):
    """Print one sampled review and its aspect/sentiment predictions."""
    print("\n" + "=" * 110)
    print(f"LAPTOP: {laptop}")
    print(f"SAMPLE REVIEW: {sample_number} | ORIGINAL CSV ROW: {source_row}")
    print("-" * 110)
    print(review_text)
    print("-" * 110)

    if not predictions:
        print("No aspects detected.")
        return

    for i, row in enumerate(predictions, start=1):
        print(
            f"{i:>2}. sentence={row['sentence_id']} | "
            f"aspect='{row['aspect']}' | sentiment={row['sentiment'].upper()}"
        )
        print(f"    context: {row['context']}")


def run_subset_test(
    reviews_dir,
    output_dir="subset_test_output",
    laptop_count=2,
    reviews_per_laptop=10,
    requested_files=None,
    review_column="Review",
    seed=42,
    max_length=DEFAULT_MAX_LENGTH,
    overlap_tokens=DEFAULT_OVERLAP_TOKENS,
    ate_model_path=ATE_MODEL_PATH,
    absa_model_path=ABSA_MODEL_PATH,
):
    """Run the ATE+ABSA pipeline on a small subset and save inspection files."""
    if reviews_per_laptop <= 0:
        raise ValueError("--reviews-per-laptop must be at least 1")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    selected_files = choose_csv_files(
        reviews_dir,
        requested_files=requested_files,
        laptop_count=laptop_count,
        seed=seed,
    )

    print("\nSelected review files:")
    for path in selected_files:
        print(f"  - {path.name}")

    (
        aspect_model,
        aspect_tokenizer,
        sentiment_model,
        sentiment_tokenizer,
        device,
    ) = load_pipeline_models(
        ate_model_path=ate_model_path,
        absa_model_path=absa_model_path,
    )

    print(f"\nModels loaded on: {device}")
    print(f"Testing up to {reviews_per_laptop} reviews per selected laptop.")

    all_selected_reviews = []
    all_raw_rows = []
    all_review_level_rows = []

    global_review_id = 0

    for file_index, csv_path in enumerate(selected_files, start=1):
        # Offset seed per file so each laptop gets a different but reproducible sample.
        laptop, sampled_reviews = sample_reviews_from_file(
            csv_path,
            review_column=review_column,
            review_count=reviews_per_laptop,
            seed=seed + file_index,
        )

        print("\n" + "#" * 110)
        print(f"FILE {file_index}/{len(selected_files)}: {csv_path.name}")
        print(f"LAPTOP: {laptop}")
        print(f"SAMPLED REVIEWS: {len(sampled_reviews)}")
        print("#" * 110)

        for sample_number, sample in enumerate(sampled_reviews.itertuples(index=False), start=1):
            global_review_id += 1
            review_text = sample.review_text
            source_row = int(sample.source_row)

            all_selected_reviews.append(
                {
                    "review_id": global_review_id,
                    "laptop": laptop,
                    "source_file": csv_path.name,
                    "source_row": source_row,
                    "review_text": review_text,
                }
            )

            predictions = process_review(
                review_text=review_text,
                review_id=global_review_id,
                aspect_model=aspect_model,
                aspect_tokenizer=aspect_tokenizer,
                sentiment_model=sentiment_model,
                sentiment_tokenizer=sentiment_tokenizer,
                max_length=max_length,
                overlap_tokens=overlap_tokens,
            )

            for row in predictions:
                row["laptop"] = laptop
                row["source_file"] = csv_path.name
                row["source_row"] = source_row
                row["review_text"] = review_text
            all_raw_rows.extend(predictions)

            review_level = collapse_to_review_level(predictions)
            for row in review_level:
                row["laptop"] = laptop
                row["source_file"] = csv_path.name
                row["source_row"] = source_row
            all_review_level_rows.extend(review_level)

            print_review_result(
                laptop=laptop,
                sample_number=sample_number,
                source_row=source_row,
                review_text=review_text,
                predictions=predictions,
            )

    selected_reviews_df = pd.DataFrame(all_selected_reviews)
    raw_df = pd.DataFrame(all_raw_rows)
    review_level_df = pd.DataFrame(all_review_level_rows)

    if review_level_df.empty:
        summary_df = aggregate_laptop_aspects(pd.DataFrame())
    else:
        summary_df = aggregate_laptop_aspects(review_level_df)

    selected_path = output_dir / "subset_reviews_used.csv"
    raw_path = output_dir / "subset_raw_aspect_predictions.csv"
    review_level_path = output_dir / "subset_review_level_aspects.csv"
    summary_path = output_dir / "subset_laptop_aspect_summary.csv"
    manual_path = output_dir / "manual_inspection_template.csv"

    selected_reviews_df.to_csv(selected_path, index=False)
    raw_df.to_csv(raw_path, index=False)
    review_level_df.to_csv(review_level_path, index=False)
    summary_df.to_csv(summary_path, index=False)

    # A convenient sheet for manually checking a sample of individual predictions.
    if raw_df.empty:
        manual_df = pd.DataFrame(
            columns=[
                "laptop",
                "review_id",
                "source_file",
                "source_row",
                "context",
                "predicted_aspect",
                "predicted_sentiment",
                "aspect_correct",
                "sentiment_correct",
                "correct_aspect_if_needed",
                "correct_sentiment_if_needed",
                "notes",
            ]
        )
    else:
        manual_df = raw_df[
            [
                "laptop",
                "review_id",
                "source_file",
                "source_row",
                "context",
                "aspect",
                "sentiment",
            ]
        ].copy()
        manual_df = manual_df.rename(
            columns={
                "aspect": "predicted_aspect",
                "sentiment": "predicted_sentiment",
            }
        )
        manual_df["aspect_correct"] = ""
        manual_df["sentiment_correct"] = ""
        manual_df["correct_aspect_if_needed"] = ""
        manual_df["correct_sentiment_if_needed"] = ""
        manual_df["notes"] = ""

    manual_df.to_csv(manual_path, index=False)

    print("\n" + "=" * 110)
    print("SUBSET TEST COMPLETE")
    print("=" * 110)
    print(f"Selected reviews:         {selected_path}")
    print(f"Raw predictions:          {raw_path}")
    print(f"Review-level predictions: {review_level_path}")
    print(f"Laptop aspect summary:    {summary_path}")
    print(f"Manual inspection sheet:  {manual_path}")

    print("\nQuick counts:")
    print(f"  Reviews tested:        {len(selected_reviews_df)}")
    print(f"  Raw aspect predictions:{len(raw_df):>6}")
    print(f"  Review-level aspects:  {len(review_level_df):>6}")

    if not summary_df.empty:
        print("\nMost frequently mentioned extracted aspects in this subset:")
        preview = summary_df.sort_values(
            "reviews_mentioning_aspect", ascending=False
        ).head(20)
        print(
            preview[
                [
                    "laptop",
                    "aspect",
                    "reviews_mentioning_aspect",
                    "positive_reviews",
                    "negative_reviews",
                    "neutral_reviews",
                    "mixed_reviews",
                    "positive_ratio",
                ]
            ].to_string(index=False)
        )

    return selected_reviews_df, raw_df, review_level_df, summary_df


def parse_args():
    parser = argparse.ArgumentParser(
        description="Test ATE+ABSA on a small subset of real Best Buy laptop reviews."
    )
    parser.add_argument(
        "--reviews-dir",
        required=True,
        help="Directory containing your Best Buy review CSV files.",
    )
    parser.add_argument(
        "--output-dir",
        default="subset_test_output",
        help="Directory for subset-test CSV outputs.",
    )
    parser.add_argument(
        "--laptops",
        type=int,
        default=2,
        help="Number of laptop CSV files to randomly test (default: 2).",
    )
    parser.add_argument(
        "--reviews-per-laptop",
        type=int,
        default=10,
        help="Number of reviews sampled per laptop (default: 10).",
    )
    parser.add_argument(
        "--files",
        nargs="*",
        default=None,
        help="Optional exact CSV filenames. If supplied, --laptops is ignored.",
    )
    parser.add_argument(
        "--review-column",
        default="Review",
        help="Review text column name (default: Review).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducible sampling (default: 42).",
    )
    parser.add_argument(
        "--max-length",
        type=int,
        default=DEFAULT_MAX_LENGTH,
        help=f"Model maximum sequence length (default: {DEFAULT_MAX_LENGTH}).",
    )
    parser.add_argument(
        "--overlap-tokens",
        type=int,
        default=DEFAULT_OVERLAP_TOKENS,
        help=f"Overlap for long-sentence token windows (default: {DEFAULT_OVERLAP_TOKENS}).",
    )
    parser.add_argument(
        "--ate-model-path",
        default=ATE_MODEL_PATH,
        help=f"ATE saved-model directory (default: {ATE_MODEL_PATH}).",
    )
    parser.add_argument(
        "--absa-model-path",
        default=ABSA_MODEL_PATH,
        help=f"ABSA saved-model directory (default: {ABSA_MODEL_PATH}).",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    run_subset_test(
        reviews_dir=args.reviews_dir,
        output_dir=args.output_dir,
        laptop_count=args.laptops,
        reviews_per_laptop=args.reviews_per_laptop,
        requested_files=args.files,
        review_column=args.review_column,
        seed=args.seed,
        max_length=args.max_length,
        overlap_tokens=args.overlap_tokens,
        ate_model_path=args.ate_model_path,
        absa_model_path=args.absa_model_path,
    )


if __name__ == "__main__":
    main()
