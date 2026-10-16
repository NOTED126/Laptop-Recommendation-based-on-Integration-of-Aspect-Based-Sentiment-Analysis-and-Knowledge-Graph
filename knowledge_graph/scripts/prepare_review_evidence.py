"""
prepare_review_evidence.py
==========================

Create Neo4j-ready review provenance data from:
1. reviews/*.csv
2. pipeline_output_v3/canonical_review_level_aspects_v3.csv
3. knowledge_graph/data/laptops.csv

Output
------
knowledge_graph/review_evidence/
    review_nodes.csv
    laptop_review_edges.csv
    review_aspect_edges.csv
    review_evidence_manifest.json

The evidence model is:

    (Laptop)-[:HAS_REVIEW]->(Review)
    (Review)-[:MENTIONS]->(Aspect)

`MENTIONS` retains:
- review-level aspect sentiment
- positive / negative / neutral mention counts
- raw aspect strings
- a short evidence snippet taken from the original review
"""

import argparse
import hashlib
import json
import re
from pathlib import Path

import pandas as pd


def clean(value):
    if pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


def stable_review_key(source_file, review_id):
    raw = f"{source_file}::{review_id}"
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:14]
    return f"review__{digest}"


def normalize_text(text):
    text = str(text).lower()
    text = text.replace("’", "'").replace("“", '"').replace("”", '"')
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def split_sentences(text):
    """
    Lightweight sentence/list splitter.

    Reviews often contain bullets and paragraph breaks, so newline boundaries
    are useful evidence boundaries as well as normal punctuation.
    """
    text = str(text).replace("\r\n", "\n").replace("\r", "\n")
    chunks = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [chunk.strip(" \t-*•") for chunk in chunks if chunk.strip(" \t-*•")]


STOPWORDS = {
    "the", "and", "for", "with", "this", "that", "from", "into", "are",
    "was", "were", "has", "have", "had", "its", "it's", "not", "but",
    "you", "your", "all", "very", "some", "more", "less", "good", "great",
    "laptop", "computer", "device",
}


def term_tokens(text):
    return {
        token
        for token in re.findall(r"[a-z0-9]+", normalize_text(text))
        if len(token) >= 3 and token not in STOPWORDS
    }


def evidence_snippet(review_text, raw_aspects, canonical_label, max_chars=420):
    """
    Pick one concise sentence/list item that most clearly supports the
    review-aspect relationship.

    Priority:
    1. Sentence containing an exact raw-aspect phrase.
    2. Sentence with the largest token overlap with raw-aspect phrases.
    3. Sentence overlapping the canonical aspect label.
    4. No snippet rather than pretending unrelated text is evidence.
    """
    sentences = split_sentences(review_text)
    if not sentences:
        return None

    raw_terms = [
        term.strip()
        for term in str(raw_aspects or "").split("|")
        if term.strip()
    ]

    # Prefer the most specific/longest exact phrase.
    exact_candidates = []
    for sentence in sentences:
        normalized_sentence = normalize_text(sentence)
        matched_lengths = [
            len(normalize_text(term))
            for term in raw_terms
            if normalize_text(term) in normalized_sentence
        ]
        if matched_lengths:
            exact_candidates.append(
                (max(matched_lengths), len(sentence), sentence)
            )

    if exact_candidates:
        # Most-specific phrase, then shorter sentence for readability.
        exact_candidates.sort(key=lambda x: (-x[0], x[1]))
        chosen = exact_candidates[0][2]
        return truncate(chosen, max_chars)

    target_tokens = set()
    for term in raw_terms:
        target_tokens.update(term_tokens(term))

    fallback_candidates = []
    for sentence in sentences:
        tokens = term_tokens(sentence)
        overlap = len(tokens & target_tokens)
        if overlap:
            fallback_candidates.append((overlap, len(sentence), sentence))

    if fallback_candidates:
        fallback_candidates.sort(key=lambda x: (-x[0], x[1]))
        return truncate(fallback_candidates[0][2], max_chars)

    canonical_tokens = term_tokens(canonical_label or "")
    if canonical_tokens:
        canonical_candidates = []
        for sentence in sentences:
            overlap = len(term_tokens(sentence) & canonical_tokens)
            if overlap:
                canonical_candidates.append((overlap, len(sentence), sentence))

        if canonical_candidates:
            canonical_candidates.sort(key=lambda x: (-x[0], x[1]))
            return truncate(canonical_candidates[0][2], max_chars)

    return None


def truncate(text, max_chars):
    text = re.sub(r"\s+", " ", str(text)).strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


def load_reviews(reviews_dir):
    reviews_dir = Path(reviews_dir)
    files = sorted(reviews_dir.glob("*.csv"))
    if not files:
        raise FileNotFoundError(f"No review CSVs found in {reviews_dir}")

    frames = []

    required = {"Review Count", "Brand", "Model", "Product", "Date", "Review"}

    for path in files:
        df = pd.read_csv(path)
        missing = required - set(df.columns)
        if missing:
            raise ValueError(
                f"{path.name} is missing review columns: {sorted(missing)}"
            )

        df = df.copy()
        df["source_file"] = path.name
        df["review_id"] = df["Review Count"]
        frames.append(df)

    reviews = pd.concat(frames, ignore_index=True)

    if reviews.duplicated(["source_file", "review_id"]).any():
        raise ValueError("Duplicate (source_file, review_id) review keys found.")

    return reviews


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--reviews-dir",
        default="reviews",
    )
    parser.add_argument(
        "--canonical",
        default="pipeline_output_v3/canonical_review_level_aspects_v3.csv",
    )
    parser.add_argument(
        "--laptops",
        default="knowledge_graph/data/laptops.csv",
    )
    parser.add_argument(
        "--output-dir",
        default="knowledge_graph/review_evidence",
    )

    args = parser.parse_args()

    reviews = load_reviews(args.reviews_dir)
    canonical = pd.read_csv(args.canonical)
    laptops = pd.read_csv(args.laptops)

    required_canonical = {
        "laptop",
        "source_file",
        "review_id",
        "canonical_aspect",
        "canonical_label",
        "aspect_type",
        "review_sentiment",
        "positive_mentions",
        "negative_mentions",
        "neutral_mentions",
        "raw_aspects",
    }

    missing = required_canonical - set(canonical.columns)
    if missing:
        raise ValueError(
            f"Canonical file missing columns: {sorted(missing)}"
        )

    # The recommendation graph's (:Aspect) nodes represent only the
    # 24 user-experience aspects. Specification mentions such as RAM,
    # CPU, GPU, storage and NPU are already represented by structured
    # laptop specifications and are not part of HAS_ASPECT_SCORE.
    #
    # Therefore review provenance for recommendation explainability
    # must use experience rows only.
    total_canonical_rows = len(canonical)
    specification_rows = int(
        (canonical["aspect_type"] == "specification").sum()
    )

    canonical = canonical[
        canonical["aspect_type"] == "experience"
    ].copy()

    experience_rows = len(canonical)

    print("Canonical review-aspect input:")
    print(f"  Total rows:          {total_canonical_rows}")
    print(f"  Experience rows:     {experience_rows}")
    print(f"  Specification rows:  {specification_rows} (excluded)")

    laptop_lookup = dict(
        zip(laptops["product_name"], laptops["laptop_id"])
    )

    unknown_laptops = sorted(
        set(reviews["Product"]) - set(laptop_lookup)
    )
    if unknown_laptops:
        raise ValueError(
            "Review Product names missing from laptops.csv:\n"
            + "\n".join(unknown_laptops)
        )

    review_lookup = reviews[
        [
            "source_file",
            "review_id",
            "Product",
            "Brand",
            "Model",
            "Date",
            "Review",
        ]
    ]

    joined = canonical.merge(
        review_lookup,
        on=["source_file", "review_id"],
        how="left",
        validate="many_to_one",
        indicator=True,
    )

    missing_joins = joined["_merge"].ne("both").sum()
    if missing_joins:
        raise ValueError(
            f"{missing_joins} canonical aspect rows could not be joined "
            "to original reviews."
        )

    if not (
        joined["laptop"].astype(str).str.strip()
        == joined["Product"].astype(str).str.strip()
    ).all():
        raise ValueError(
            "Laptop names do not match review Product values after joining."
        )

    reviews = reviews.copy()
    reviews["review_key"] = reviews.apply(
        lambda row: stable_review_key(
            row["source_file"],
            row["review_id"],
        ),
        axis=1,
    )
    reviews["laptop_id"] = reviews["Product"].map(laptop_lookup)

    review_nodes = pd.DataFrame(
        {
            "review_key": reviews["review_key"],
            "source_file": reviews["source_file"],
            "source_review_id": reviews["review_id"],
            "brand": reviews["Brand"],
            "model": reviews["Model"],
            "product_name": reviews["Product"],
            "review_date": reviews["Date"],
            "review_text": reviews["Review"],
        }
    )

    laptop_review_edges = reviews[
        ["laptop_id", "review_key"]
    ].copy()

    key_lookup = {
        (row.source_file, row.review_id): row.review_key
        for row in reviews[
            ["source_file", "review_id", "review_key"]
        ].itertuples(index=False)
    }

    edge_records = []
    snippet_count = 0

    for row in joined.itertuples(index=False):
        review_key = key_lookup[(row.source_file, row.review_id)]

        snippet = evidence_snippet(
            review_text=row.Review,
            raw_aspects=row.raw_aspects,
            canonical_label=row.canonical_label,
        )

        if snippet:
            snippet_count += 1

        edge_records.append(
            {
                "review_key": review_key,
                "aspect_id": row.canonical_aspect,
                "review_sentiment": row.review_sentiment,
                "positive_mentions": int(row.positive_mentions),
                "negative_mentions": int(row.negative_mentions),
                "neutral_mentions": int(row.neutral_mentions),
                "raw_aspects": row.raw_aspects,
                "evidence_snippet": snippet,
            }
        )

    review_aspect_edges = pd.DataFrame(edge_records)

    if review_aspect_edges.duplicated(
        ["review_key", "aspect_id"]
    ).any():
        raise ValueError(
            "Duplicate (Review, Aspect) evidence relationships found."
        )

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    review_nodes.to_csv(
        output_dir / "review_nodes.csv",
        index=False,
    )
    laptop_review_edges.to_csv(
        output_dir / "laptop_review_edges.csv",
        index=False,
    )
    review_aspect_edges.to_csv(
        output_dir / "review_aspect_edges.csv",
        index=False,
    )

    referenced_reviews = review_aspect_edges["review_key"].nunique()

    manifest = {
        "canonical_input_rows_total": int(total_canonical_rows),
        "canonical_experience_rows_used": int(experience_rows),
        "canonical_specification_rows_excluded": int(specification_rows),
        "review_nodes": len(review_nodes),
        "laptop_review_relationships": len(laptop_review_edges),
        "review_aspect_relationships": len(review_aspect_edges),
        "reviews_with_canonical_aspect_evidence": referenced_reviews,
        "reviews_without_canonical_aspect_evidence": (
            len(review_nodes) - referenced_reviews
        ),
        "evidence_snippets_created": snippet_count,
        "evidence_snippet_coverage": (
            snippet_count / len(review_aspect_edges)
            if len(review_aspect_edges)
            else 0
        ),
        "join_integrity": {
            "missing_canonical_to_review_joins": int(missing_joins),
            "exact_laptop_product_name_match": True,
        },
    }

    (output_dir / "review_evidence_manifest.json").write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )

    print("=" * 72)
    print("REVIEW EVIDENCE PREPARATION COMPLETE")
    print("=" * 72)
    print(f"Review nodes:                    {len(review_nodes):>7}")
    print(
        f"Laptop -> Review relationships:  "
        f"{len(laptop_review_edges):>7}"
    )
    print(
        f"Review -> Aspect relationships:  "
        f"{len(review_aspect_edges):>7} (experience only)"
    )
    print(
        f"Reviews with aspect evidence:    "
        f"{referenced_reviews:>7}"
    )
    print(
        f"Evidence snippets:               "
        f"{snippet_count:>7} "
        f"({100 * manifest['evidence_snippet_coverage']:.2f}%)"
    )
    print("Canonical -> original review joins: PASS")
    print(f"Output directory: {output_dir}")
    print("=" * 72)


if __name__ == "__main__":
    main()
