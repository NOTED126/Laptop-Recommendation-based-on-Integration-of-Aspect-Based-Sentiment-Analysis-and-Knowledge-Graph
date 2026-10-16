"""
query_recommendations.py
========================

Query the local Neo4j/Aura knowledge graph for evidence-aware laptop
recommendations.

Workflow
--------
1. Apply hard specification filters.
2. Normalize user aspect weights.
3. Rank eligible laptops using HAS_ASPECT_SCORE.adjusted_score.
4. Calculate evidence confidence separately.
5. Return the top N laptops.
6. Retrieve per-aspect breakdowns for explainability.
7. Optionally save both tables as CSV files.

The same script works against local Neo4j and AuraDB by changing the
NEO4J_* environment variables.

Examples
--------
No specification filters, weighted experience ranking:

    python knowledge_graph/scripts/query_recommendations.py ^
      --weights "BATTERY_LIFE=50,PERFORMANCE=30,THERMAL_PERFORMANCE=20"

With specification filters:

    python knowledge_graph/scripts/query_recommendations.py ^
      --min-ram 16 ^
      --min-storage 512 ^
      --max-price 1500 ^
      --weights "BATTERY_LIFE=50,PERFORMANCE=30,THERMAL_PERFORMANCE=20"

Brand / CPU / GPU filters:

    python knowledge_graph/scripts/query_recommendations.py ^
      --brand "Lenovo" ^
      --cpu-brand "AMD" ^
      --gpu-brand "NVIDIA" ^
      --weights "PERFORMANCE=60,BATTERY_LIFE=40"

PowerShell line continuation uses the backtick (`), while CMD uses ^.
Putting the command on one line works in both shells.
"""

import argparse
import csv
import os
from pathlib import Path

from neo4j import GraphDatabase

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = PROJECT_ROOT / "backend" / ".env"

load_dotenv(ENV_FILE)


DEFAULT_WEIGHTS = {
    "BATTERY_LIFE": 0.50,
    "PERFORMANCE": 0.30,
    "THERMAL_PERFORMANCE": 0.20,
}


def parse_weights(text):
    """
    Parse:
        BATTERY_LIFE=50,PERFORMANCE=30
    or:
        BATTERY_LIFE=0.5,PERFORMANCE=0.3

    Values are normalized to sum to 1.
    """
    if not text:
        raw = dict(DEFAULT_WEIGHTS)
    else:
        raw = {}
        for item in text.split(","):
            item = item.strip()
            if not item:
                continue

            if "=" not in item:
                raise ValueError(
                    f"Invalid weight entry '{item}'. "
                    "Expected ASPECT_ID=value."
                )

            aspect_id, value = item.split("=", 1)
            aspect_id = aspect_id.strip().upper()
            value = float(value.strip())

            if value < 0:
                raise ValueError(
                    f"Weight for {aspect_id} cannot be negative."
                )

            raw[aspect_id] = value

    if not raw:
        raise ValueError("At least one aspect weight is required.")

    total = sum(raw.values())
    if total <= 0:
        raise ValueError("The sum of aspect weights must be greater than zero.")

    return [
        {
            "aspect_id": aspect_id,
            "weight": value / total,
        }
        for aspect_id, value in raw.items()
    ]


def connect(uri, username, password):
    driver = GraphDatabase.driver(
        uri,
        auth=(username, password),
    )
    driver.verify_connectivity()
    return driver


def fetch_valid_aspects(session):
    result = session.run(
        """
        MATCH (a:Aspect)
        RETURN a.aspect_id AS aspect_id,
               a.aspect_name AS aspect_name
        ORDER BY a.aspect_id
        """
    )

    return {
        row["aspect_id"]: row["aspect_name"]
        for row in result
    }


def validate_weights(weights, valid_aspects):
    invalid = [
        item["aspect_id"]
        for item in weights
        if item["aspect_id"] not in valid_aspects
    ]

    if invalid:
        valid_text = ", ".join(sorted(valid_aspects))
        raise ValueError(
            "Unknown canonical aspect ID(s): "
            + ", ".join(invalid)
            + "\nValid aspect IDs are:\n"
            + valid_text
        )


def build_filter_clause(args):
    """
    Return (Cypher WHERE expressions, parameters).

    Only supplied filters are included.
    """
    clauses = []
    params = {}

    if args.min_ram is not None:
        clauses.append("l.ram_gb >= $min_ram")
        params["min_ram"] = args.min_ram

    if args.min_storage is not None:
        clauses.append("l.storage_gb >= $min_storage")
        params["min_storage"] = args.min_storage

    if args.max_price is not None:
        clauses.append("l.price_usd <= $max_price")
        params["max_price"] = args.max_price

    if args.min_price is not None:
        clauses.append("l.price_usd >= $min_price")
        params["min_price"] = args.min_price

    if args.min_screen_size is not None:
        clauses.append("l.screen_size_in >= $min_screen_size")
        params["min_screen_size"] = args.min_screen_size

    if args.max_screen_size is not None:
        clauses.append("l.screen_size_in <= $max_screen_size")
        params["max_screen_size"] = args.max_screen_size

    if args.touch_screen is not None:
        clauses.append("l.touch_screen = $touch_screen")
        params["touch_screen"] = args.touch_screen

    if args.brand:
        clauses.append(
            "EXISTS { "
            "MATCH (l)-[:MADE_BY]->(filterBrand:Brand) "
            "WHERE toLower(filterBrand.brand_name) = toLower($brand) "
            "}"
        )
        params["brand"] = args.brand

    if args.cpu_brand:
        clauses.append(
            "EXISTS { "
            "MATCH (l)-[:HAS_PROCESSOR]->(filterCPU:Processor) "
            "WHERE toLower(filterCPU.processor_brand) "
            "= toLower($cpu_brand) "
            "}"
        )
        params["cpu_brand"] = args.cpu_brand

    if args.cpu_contains:
        clauses.append(
            "EXISTS { "
            "MATCH (l)-[:HAS_PROCESSOR]->(filterCPU2:Processor) "
            "WHERE toLower(coalesce(filterCPU2.processor_display_name, '')) "
            "CONTAINS toLower($cpu_contains) "
            "}"
        )
        params["cpu_contains"] = args.cpu_contains

    if args.gpu_brand:
        clauses.append(
            "EXISTS { "
            "MATCH (l)-[:HAS_GPU]->(filterGPU:GPU) "
            "WHERE toLower(filterGPU.gpu_brand) = toLower($gpu_brand) "
            "}"
        )
        params["gpu_brand"] = args.gpu_brand

    if args.gpu_contains:
        clauses.append(
            "EXISTS { "
            "MATCH (l)-[:HAS_GPU]->(filterGPU2:GPU) "
            "WHERE toLower(coalesce(filterGPU2.graphics_name, '')) "
            "CONTAINS toLower($gpu_contains) "
            "}"
        )
        params["gpu_contains"] = args.gpu_contains

    return clauses, params


def recommendation_query(filter_clauses):
    where_text = ""
    if filter_clauses:
        where_text = "WHERE " + "\n  AND ".join(filter_clauses)

    return f"""
    MATCH (l:Laptop)
    {where_text}

    WITH l
    UNWIND $weights AS w

    MATCH (l)-[score:HAS_ASPECT_SCORE]->(
        aspect:Aspect {{aspect_id: w.aspect_id}}
    )

    WITH
        l,
        sum(w.weight * score.adjusted_score) AS recommendation_score,
        sum(w.weight * score.evidence_confidence) AS evidence_confidence,
        sum(
            CASE
                WHEN score.has_direct_evidence = true THEN 1
                ELSE 0
            END
        ) AS selected_aspects_with_evidence,
        count(*) AS selected_aspects

    OPTIONAL MATCH (l)-[:MADE_BY]->(brand:Brand)
    OPTIONAL MATCH (l)-[:HAS_PROCESSOR]->(cpu:Processor)
    OPTIONAL MATCH (l)-[:HAS_GPU]->(gpu:GPU)
    OPTIONAL MATCH (l)-[:RUNS_OS]->(os:OperatingSystem)

    RETURN
        l.laptop_id AS laptop_id,
        l.product_name AS laptop,
        brand.brand_name AS brand,
        cpu.processor_display_name AS processor,
        gpu.graphics_name AS gpu,
        os.os_name AS operating_system,
        l.price_usd AS price_usd,
        l.ram_gb AS ram_gb,
        l.storage_gb AS storage_gb,
        l.storage_type AS storage_type,
        l.screen_size_in AS screen_size_in,
        l.screen_resolution AS screen_resolution,
        l.refresh_rate_hz AS refresh_rate_hz,
        l.touch_screen AS touch_screen,
        l.weight_lb AS weight_lb,
        l.image_url AS image_url,
        l.product_url AS product_url,

        recommendation_score AS recommendation_score,
        100.0 * recommendation_score AS recommendation_score_0_100,

        evidence_confidence AS evidence_confidence,
        100.0 * evidence_confidence AS evidence_confidence_0_100,

        selected_aspects AS selected_aspects,
        selected_aspects_with_evidence AS selected_aspects_with_evidence,
        selected_aspects - selected_aspects_with_evidence
            AS selected_aspects_without_evidence

    ORDER BY
        recommendation_score DESC,
        evidence_confidence DESC,
        l.product_name ASC

    LIMIT $top_n
    """


BREAKDOWN_QUERY = """
UNWIND $laptop_ids AS laptop_id
MATCH (l:Laptop {laptop_id: laptop_id})

UNWIND $weights AS w
MATCH (l)-[score:HAS_ASPECT_SCORE]->(
    aspect:Aspect {aspect_id: w.aspect_id}
)

RETURN
    l.laptop_id AS laptop_id,
    l.product_name AS laptop,

    aspect.aspect_id AS aspect_id,
    aspect.aspect_name AS aspect_name,
    w.weight AS normalized_weight,

    score.positive_reviews AS positive_reviews,
    score.negative_reviews AS negative_reviews,
    score.neutral_reviews AS neutral_reviews,
    score.mixed_reviews AS mixed_reviews,
    score.mention_count AS mention_count,

    score.positive_ratio AS positive_ratio,
    score.raw_sentiment_score AS raw_sentiment_score,
    score.prior_score AS prior_score,
    score.adjusted_score AS adjusted_score,

    score.evidence_confidence AS evidence_confidence,
    score.evidence_level AS evidence_level,
    score.has_direct_evidence AS has_direct_evidence,

    w.weight * score.adjusted_score AS weighted_score_contribution,
    w.weight * score.evidence_confidence
        AS weighted_confidence_contribution

ORDER BY
    l.product_name ASC,
    normalized_weight DESC,
    aspect.aspect_id ASC
"""


def execute_recommendation(
    session,
    weights,
    filter_clauses,
    filter_parameters,
    top_n,
):
    query = recommendation_query(filter_clauses)

    params = dict(filter_parameters)
    params["weights"] = weights
    params["top_n"] = top_n

    return [
        dict(record)
        for record in session.run(query, **params)
    ]


def execute_breakdown(session, ranking, weights):
    laptop_ids = [row["laptop_id"] for row in ranking]

    if not laptop_ids:
        return []

    return [
        dict(record)
        for record in session.run(
            BREAKDOWN_QUERY,
            laptop_ids=laptop_ids,
            weights=weights,
        )
    ]


def save_csv(rows, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if not rows:
        path.write_text("", encoding="utf-8")
        return

    columns = list(rows[0].keys())

    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def print_weights(weights, valid_aspects):
    print("\nSelected experience weights:")

    for item in sorted(
        weights,
        key=lambda x: x["weight"],
        reverse=True,
    ):
        aspect_id = item["aspect_id"]
        name = valid_aspects.get(aspect_id, aspect_id)
        print(
            f"  {name:<30} "
            f"{100 * item['weight']:>6.2f}% "
            f"({aspect_id})"
        )


def print_filters(args):
    filters = []

    if args.min_ram is not None:
        filters.append(f"RAM >= {args.min_ram:g} GB")

    if args.min_storage is not None:
        filters.append(f"Storage >= {args.min_storage:g} GB")

    if args.min_price is not None:
        filters.append(f"Price >= ${args.min_price:g}")

    if args.max_price is not None:
        filters.append(f"Price <= ${args.max_price:g}")

    if args.min_screen_size is not None:
        filters.append(
            f"Screen size >= {args.min_screen_size:g} inches"
        )

    if args.max_screen_size is not None:
        filters.append(
            f"Screen size <= {args.max_screen_size:g} inches"
        )

    if args.touch_screen is not None:
        filters.append(
            "Touchscreen = "
            + ("Yes" if args.touch_screen else "No")
        )

    if args.brand:
        filters.append(f"Brand = {args.brand}")

    if args.cpu_brand:
        filters.append(f"CPU brand = {args.cpu_brand}")

    if args.cpu_contains:
        filters.append(f"CPU contains '{args.cpu_contains}'")

    if args.gpu_brand:
        filters.append(f"GPU brand = {args.gpu_brand}")

    if args.gpu_contains:
        filters.append(f"GPU contains '{args.gpu_contains}'")

    print("\nSpecification filters:")
    if filters:
        for item in filters:
            print(f"  - {item}")
    else:
        print("  None")


def print_ranking(ranking):
    print("\n" + "=" * 118)
    print("TOP LAPTOP RECOMMENDATIONS")
    print("=" * 118)

    if not ranking:
        print(
            "No laptops satisfy the supplied specification filters."
        )
        print("=" * 118)
        return

    header = (
        f"{'Rank':<5}"
        f"{'Laptop':<58}"
        f"{'Score':>10}"
        f"{'Confidence':>13}"
        f"{'Price':>12}"
        f"{'Evidence':>12}"
    )
    print(header)
    print("-" * 118)

    for rank, row in enumerate(ranking, start=1):
        name = row["laptop"]
        if len(name) > 55:
            name = name[:52] + "..."

        price = row["price_usd"]
        price_text = (
            f"${price:,.2f}"
            if isinstance(price, (int, float))
            else "N/A"
        )

        evidence_text = (
            f"{row['selected_aspects_with_evidence']}/"
            f"{row['selected_aspects']}"
        )

        print(
            f"{rank:<5}"
            f"{name:<58}"
            f"{row['recommendation_score_0_100']:>9.2f}"
            f"{row['evidence_confidence_0_100']:>12.2f}%"
            f"{price_text:>12}"
            f"{evidence_text:>12}"
        )

    print("=" * 118)


def print_breakdown(ranking, breakdown):
    by_laptop = {}
    for row in breakdown:
        by_laptop.setdefault(row["laptop_id"], []).append(row)

    print("\nEXPLANATION BREAKDOWN")

    for rank, recommendation in enumerate(ranking, start=1):
        print("\n" + "-" * 118)
        print(
            f"#{rank} {recommendation['laptop']}\n"
            f"Recommendation score: "
            f"{recommendation['recommendation_score_0_100']:.2f}/100 | "
            f"Evidence confidence: "
            f"{recommendation['evidence_confidence_0_100']:.2f}%"
        )

        rows = by_laptop.get(
            recommendation["laptop_id"],
            [],
        )

        for row in sorted(
            rows,
            key=lambda x: x["normalized_weight"],
            reverse=True,
        ):
            weight_pct = 100 * row["normalized_weight"]
            score_pct = 100 * row["adjusted_score"]
            confidence_pct = 100 * row["evidence_confidence"]

            if row["has_direct_evidence"]:
                mention_text = (
                    f"{row['positive_reviews']}/"
                    f"{row['mention_count']} positive reviews"
                )
            else:
                mention_text = "no direct review evidence"

            print(
                f"  {row['aspect_name']:<28} "
                f"weight={weight_pct:>6.2f}% | "
                f"score={score_pct:>6.2f} | "
                f"confidence={confidence_pct:>6.2f}% | "
                f"{mention_text} | "
                f"{row['evidence_level']}"
            )


def str_to_bool(value):
    normalized = value.strip().lower()

    if normalized in {"true", "yes", "1", "y"}:
        return True

    if normalized in {"false", "no", "0", "n"}:
        return False

    raise argparse.ArgumentTypeError(
        "Expected true/false, yes/no, or 1/0."
    )


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Filter and rank laptops directly from the Neo4j thesis "
            "knowledge graph."
        )
    )

    parser.add_argument(
        "--uri",
        default=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
    )
    parser.add_argument(
        "--username",
        default=os.getenv("NEO4J_USERNAME", "neo4j"),
    )
    parser.add_argument(
        "--password",
        default=os.getenv("NEO4J_PASSWORD"),
    )
    parser.add_argument(
        "--database",
        default=os.getenv("NEO4J_DATABASE", "neo4j"),
    )

    parser.add_argument(
        "--weights",
        default=None,
        help=(
            "Comma-separated canonical aspect weights, e.g. "
            "'BATTERY_LIFE=50,PERFORMANCE=30,"
            "THERMAL_PERFORMANCE=20'."
        ),
    )

    parser.add_argument(
        "--top-n",
        type=int,
        default=5,
        help="Number of recommendations to return (default: 5).",
    )

    # Hard specification filters
    parser.add_argument("--min-ram", type=float)
    parser.add_argument("--min-storage", type=float)
    parser.add_argument("--min-price", type=float)
    parser.add_argument("--max-price", type=float)
    parser.add_argument("--min-screen-size", type=float)
    parser.add_argument("--max-screen-size", type=float)

    parser.add_argument(
        "--touch-screen",
        type=str_to_bool,
        default=None,
        help="true/false",
    )

    parser.add_argument("--brand")
    parser.add_argument("--cpu-brand")
    parser.add_argument("--cpu-contains")
    parser.add_argument("--gpu-brand")
    parser.add_argument("--gpu-contains")

    parser.add_argument(
        "--output-dir",
        default="recommendation_query_output",
        help=(
            "Directory for recommendation_ranking.csv and "
            "recommendation_breakdown.csv."
        ),
    )

    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Do not save CSV outputs.",
    )

    parser.add_argument(
        "--no-breakdown",
        action="store_true",
        help="Do not print the detailed aspect explanation breakdown.",
    )

    return parser.parse_args()


def main():
    args = parse_args()

    if not args.password:
        raise ValueError(
            "Neo4j password not provided. Set NEO4J_PASSWORD "
            "or use --password."
        )

    if args.top_n <= 0:
        raise ValueError("--top-n must be at least 1.")

    weights = parse_weights(args.weights)

    driver = connect(
        uri=args.uri,
        username=args.username,
        password=args.password,
    )

    try:
        with driver.session(database=args.database) as session:
            valid_aspects = fetch_valid_aspects(session)
            validate_weights(weights, valid_aspects)

            filter_clauses, filter_parameters = build_filter_clause(
                args
            )

            print("=" * 72)
            print("NEO4J LAPTOP RECOMMENDATION QUERY")
            print("=" * 72)
            print(f"Database: {args.database}")

            print_weights(weights, valid_aspects)
            print_filters(args)

            ranking = execute_recommendation(
                session=session,
                weights=weights,
                filter_clauses=filter_clauses,
                filter_parameters=filter_parameters,
                top_n=args.top_n,
            )

            breakdown = execute_breakdown(
                session=session,
                ranking=ranking,
                weights=weights,
            )

    finally:
        driver.close()

    print_ranking(ranking)

    if not args.no_breakdown:
        print_breakdown(ranking, breakdown)

    if not args.no_save:
        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        ranking_rows = []
        for rank, row in enumerate(ranking, start=1):
            output = {"rank": rank}
            output.update(row)
            ranking_rows.append(output)

        ranking_path = output_dir / "recommendation_ranking.csv"
        breakdown_path = output_dir / "recommendation_breakdown.csv"

        save_csv(ranking_rows, ranking_path)
        save_csv(breakdown, breakdown_path)

        print("\nSaved:")
        print(f"  {ranking_path}")
        print(f"  {breakdown_path}")


if __name__ == "__main__":
    main()
