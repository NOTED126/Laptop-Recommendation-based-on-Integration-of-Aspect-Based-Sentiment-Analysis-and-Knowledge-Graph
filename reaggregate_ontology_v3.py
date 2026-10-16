"""Reclassify saved ATE+ABSA raw predictions with ontology v3.

This script does NOT rerun DistilBERT. It reuses raw_aspect_predictions.csv,
updates ontology decisions, then regenerates canonical review- and laptop-level
CSV outputs.

Example:
    python reaggregate_ontology_v3.py \
        --raw "pipeline_output/raw_aspect_predictions.csv" \
        --output-dir "pipeline_output_v3"
"""

from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from pathlib import Path

from aspect_ontology import classify_aspect, ontology_table


RAW_ONTOLOGY_COLUMNS = [
    "ontology_status",
    "canonical_aspect",
    "canonical_label",
    "aspect_type",
    "mapping_method",
    "mapping_reason",
]


def read_csv(path: Path):
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows, fieldnames):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def reclassify_rows(rows):
    out = []
    for row in rows:
        new_row = dict(row)
        decision = classify_aspect(row.get("aspect", ""), row.get("context", ""))
        new_row.update(
            {
                "ontology_status": decision.ontology_status,
                "canonical_aspect": decision.canonical_aspect,
                "canonical_label": decision.canonical_label,
                "aspect_type": decision.aspect_type,
                "mapping_method": decision.mapping_method,
                "mapping_reason": decision.mapping_reason,
            }
        )
        out.append(new_row)
    return out


def collapse_to_canonical_review_level(rows):
    grouped = defaultdict(list)
    raw_forms = defaultdict(list)
    metadata = {}

    for row in rows:
        if row.get("ontology_status") != "mapped" or not row.get("canonical_aspect"):
            continue
        key = (
            row.get("laptop", ""),
            row.get("source_file", ""),
            row.get("review_id", ""),
            row.get("canonical_aspect", ""),
        )
        grouped[key].append(row.get("sentiment", ""))
        raw_forms[key].append(row.get("aspect", ""))
        metadata[key] = (row.get("canonical_label", ""), row.get("aspect_type", ""))

    output = []
    for key, sentiments in grouped.items():
        laptop, source_file, review_id, canonical = key
        counts = Counter(sentiments)
        highest = max(counts.values())
        winners = [sentiment for sentiment, count in counts.items() if count == highest]
        review_sentiment = winners[0] if len(winners) == 1 else "mixed"

        unique_forms = []
        seen = set()
        for form in raw_forms[key]:
            normalized = str(form).strip().casefold()
            if normalized not in seen:
                seen.add(normalized)
                unique_forms.append(form)

        label, aspect_type = metadata[key]
        output.append(
            {
                "laptop": laptop,
                "source_file": source_file,
                "review_id": review_id,
                "canonical_aspect": canonical,
                "canonical_label": label,
                "aspect_type": aspect_type,
                "review_sentiment": review_sentiment,
                "positive_mentions": counts.get("positive", 0),
                "negative_mentions": counts.get("negative", 0),
                "neutral_mentions": counts.get("neutral", 0),
                "raw_aspects": " | ".join(unique_forms),
            }
        )

    output.sort(
        key=lambda r: (
            r["laptop"],
            int(r["review_id"]) if str(r["review_id"]).isdigit() else str(r["review_id"]),
            r["aspect_type"],
            r["canonical_aspect"],
        )
    )
    return output


def aggregate_laptop(canonical_review_rows, aspect_type):
    grouped = defaultdict(list)
    metadata = {}
    for row in canonical_review_rows:
        if row.get("aspect_type") != aspect_type:
            continue
        key = (row["laptop"], row["canonical_aspect"])
        grouped[key].append(row["review_sentiment"])
        metadata[key] = (row["canonical_label"], row["aspect_type"])

    output = []
    for (laptop, canonical), sentiments in grouped.items():
        counts = Counter(sentiments)
        total = len(sentiments)
        positive = counts.get("positive", 0)
        label, current_type = metadata[(laptop, canonical)]
        output.append(
            {
                "laptop": laptop,
                "canonical_aspect": canonical,
                "canonical_label": label,
                "aspect_type": current_type,
                "positive_reviews": positive,
                "negative_reviews": counts.get("negative", 0),
                "neutral_reviews": counts.get("neutral", 0),
                "mixed_reviews": counts.get("mixed", 0),
                "reviews_mentioning_aspect": total,
                "positive_ratio": positive / total if total else 0.0,
            }
        )

    output.sort(
        key=lambda r: (
            r["laptop"],
            -int(r["reviews_mentioning_aspect"]),
            -float(r["positive_ratio"]),
        )
    )
    return output


def summarize_exceptions(rows, status):
    grouped = defaultdict(list)
    for row in rows:
        if row.get("ontology_status") == status:
            grouped[row.get("aspect_key", "")].append(row)

    output = []
    for aspect_key, group in grouped.items():
        forms = Counter(row.get("aspect", "") for row in group).most_common(5)
        reviews = {(row.get("source_file", ""), row.get("review_id", "")) for row in group}
        laptops = {row.get("laptop", "") for row in group}
        methods = sorted({row.get("mapping_method", "") for row in group if row.get("mapping_method")})
        reasons = sorted({row.get("mapping_reason", "") for row in group if row.get("mapping_reason")})

        output.append(
            {
                "aspect_key": aspect_key,
                "example_forms": " | ".join(form for form, _ in forms),
                "raw_mentions": len(group),
                "reviews_mentioning": len(reviews),
                "laptops_mentioning": len(laptops),
                "positive_mentions": sum(row.get("sentiment") == "positive" for row in group),
                "negative_mentions": sum(row.get("sentiment") == "negative" for row in group),
                "neutral_mentions": sum(row.get("sentiment") == "neutral" for row in group),
                "mapping_methods": " | ".join(methods),
                "mapping_reasons": " | ".join(reasons),
            }
        )

    output.sort(key=lambda r: (-r["reviews_mentioning"], -r["raw_mentions"], r["aspect_key"]))
    return output


def canonical_coverage(canonical_review_rows):
    grouped = defaultdict(list)
    for row in canonical_review_rows:
        if row.get("aspect_type") != "experience":
            continue
        grouped[row["canonical_aspect"]].append(row)

    output = []
    for canonical, group in grouped.items():
        reviews = {(row["source_file"], row["review_id"]) for row in group}
        laptops = {row["laptop"] for row in group}
        counts = Counter(row["review_sentiment"] for row in group)
        total = len(group)
        output.append(
            {
                "canonical_aspect": canonical,
                "canonical_label": group[0]["canonical_label"],
                "laptops_mentioning": len(laptops),
                "reviews_mentioning": len(reviews),
                "positive_reviews": counts.get("positive", 0),
                "negative_reviews": counts.get("negative", 0),
                "neutral_reviews": counts.get("neutral", 0),
                "mixed_reviews": counts.get("mixed", 0),
                "positive_ratio": counts.get("positive", 0) / total if total else 0.0,
            }
        )
    output.sort(key=lambda r: (-r["reviews_mentioning"], -r["laptops_mentioning"], r["canonical_aspect"]))
    return output


def main():
    parser = argparse.ArgumentParser(description="Reaggregate saved raw predictions with ontology v3 without rerunning ATE/ABSA.")
    parser.add_argument("--raw", required=True, help="Path to raw_aspect_predictions.csv")
    parser.add_argument("--output-dir", default="pipeline_output_v3", help="Output directory")
    args = parser.parse_args()

    raw_path = Path(args.raw)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    rows = read_csv(raw_path)
    if not rows:
        raise ValueError(f"No rows found in {raw_path}")

    reclassified = reclassify_rows(rows)
    canonical_review = collapse_to_canonical_review_level(reclassified)
    experience_summary = aggregate_laptop(canonical_review, "experience")
    specification_summary = aggregate_laptop(canonical_review, "specification")
    unmapped = summarize_exceptions(reclassified, "unmapped")
    rejected = summarize_exceptions(reclassified, "rejected")
    coverage = canonical_coverage(canonical_review)
    ontology_rows = ontology_table()

    raw_fields = list(rows[0].keys())
    for col in RAW_ONTOLOGY_COLUMNS:
        if col not in raw_fields:
            raw_fields.append(col)

    write_csv(output_dir / "raw_aspect_predictions_v3.csv", reclassified, raw_fields)
    write_csv(
        output_dir / "canonical_review_level_aspects_v3.csv",
        canonical_review,
        ["laptop", "source_file", "review_id", "canonical_aspect", "canonical_label", "aspect_type", "review_sentiment", "positive_mentions", "negative_mentions", "neutral_mentions", "raw_aspects"],
    )
    write_csv(
        output_dir / "laptop_experience_aspect_summary_v3.csv",
        experience_summary,
        ["laptop", "canonical_aspect", "canonical_label", "aspect_type", "positive_reviews", "negative_reviews", "neutral_reviews", "mixed_reviews", "reviews_mentioning_aspect", "positive_ratio"],
    )
    write_csv(
        output_dir / "laptop_specification_review_mentions_v3.csv",
        specification_summary,
        ["laptop", "canonical_aspect", "canonical_label", "aspect_type", "positive_reviews", "negative_reviews", "neutral_reviews", "mixed_reviews", "reviews_mentioning_aspect", "positive_ratio"],
    )
    exception_fields = ["aspect_key", "example_forms", "raw_mentions", "reviews_mentioning", "laptops_mentioning", "positive_mentions", "negative_mentions", "neutral_mentions", "mapping_methods", "mapping_reasons"]
    write_csv(output_dir / "unmapped_aspects_v3.csv", unmapped, exception_fields)
    write_csv(output_dir / "rejected_aspects_v3.csv", rejected, exception_fields)
    write_csv(
        output_dir / "canonical_aspect_coverage_v3.csv",
        coverage,
        ["canonical_aspect", "canonical_label", "laptops_mentioning", "reviews_mentioning", "positive_reviews", "negative_reviews", "neutral_reviews", "mixed_reviews", "positive_ratio"],
    )
    write_csv(
        output_dir / "canonical_aspect_ontology_v3.csv",
        ontology_rows,
        ["canonical_aspect", "canonical_label", "aspect_type", "description"],
    )

    old_counts = Counter(row.get("ontology_status", "") for row in rows)
    new_counts = Counter(row.get("ontology_status", "") for row in reclassified)
    total = len(reclassified)

    print("\nOntology v3 reaggregation complete")
    print(f"Raw predictions: {total:,}")
    print("\nPrevious ontology status:")
    for status in ("mapped", "rejected", "unmapped"):
        count = old_counts.get(status, 0)
        print(f"  {status:8s}: {count:6,d} ({count / total:6.2%})")
    print("\nOntology v3 status:")
    for status in ("mapped", "rejected", "unmapped"):
        count = new_counts.get(status, 0)
        print(f"  {status:8s}: {count:6,d} ({count / total:6.2%})")

    if unmapped:
        top = unmapped[0]
        print(
            "\nMost frequent remaining unmapped term: "
            f"'{top['aspect_key']}' in {top['reviews_mentioning']} reviews"
        )

    print(f"\nOutputs written to: {output_dir}")


if __name__ == "__main__":
    main()
