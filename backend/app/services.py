from collections import defaultdict, deque
from typing import Dict, List

from fastapi import HTTPException

from .db import db
from .models import RecommendationRequest


# Retain historical evidence in Neo4j, but do not use overlapping
# umbrella aspects as user-selectable recommendation preferences.
RETIRED_RECOMMENDATION_ASPECT_IDS = frozenset({"FEATURE_SET"})


def normalize_weights(weights: Dict[str, float]) -> List[dict]:
    total = sum(weights.values())

    return [
        {
            "aspect_id": aspect_id,
            "weight": value / total,
        }
        for aspect_id, value in weights.items()
    ]


def build_filter_clause(filters):
    clauses = []
    params = {}

    if filters.min_ram is not None:
        clauses.append("l.ram_gb >= $min_ram")
        params["min_ram"] = filters.min_ram

    if filters.min_storage is not None:
        clauses.append("l.storage_gb >= $min_storage")
        params["min_storage"] = filters.min_storage

    if filters.min_price is not None:
        clauses.append("l.price_usd >= $min_price")
        params["min_price"] = filters.min_price

    if filters.max_price is not None:
        clauses.append("l.price_usd <= $max_price")
        params["max_price"] = filters.max_price

    if filters.min_screen_size is not None:
        clauses.append("l.screen_size_in >= $min_screen_size")
        params["min_screen_size"] = filters.min_screen_size

    if filters.max_screen_size is not None:
        clauses.append("l.screen_size_in <= $max_screen_size")
        params["max_screen_size"] = filters.max_screen_size

    if filters.touch_screen is not None:
        clauses.append("l.touch_screen = $touch_screen")
        params["touch_screen"] = filters.touch_screen

    if filters.brand:
        clauses.append(
            """
            EXISTS {
                MATCH (l)-[:MADE_BY]->(filterBrand:Brand)
                WHERE toLower(filterBrand.brand_name)
                      = toLower($brand)
            }
            """
        )
        params["brand"] = filters.brand

    if filters.cpu_brand:
        clauses.append(
            """
            EXISTS {
                MATCH (l)-[:HAS_PROCESSOR]->(filterCPU:Processor)
                WHERE toLower(filterCPU.processor_brand)
                      = toLower($cpu_brand)
            }
            """
        )
        params["cpu_brand"] = filters.cpu_brand

    if filters.cpu_contains:
        clauses.append(
            """
            EXISTS {
                MATCH (l)-[:HAS_PROCESSOR]->(filterCPU2:Processor)
                WHERE toLower(
                    coalesce(filterCPU2.processor_display_name, '')
                )
                CONTAINS toLower($cpu_contains)
            }
            """
        )
        params["cpu_contains"] = filters.cpu_contains

    if filters.gpu_brand:
        clauses.append(
            """
            EXISTS {
                MATCH (l)-[:HAS_GPU]->(filterGPU:GPU)
                WHERE toLower(filterGPU.gpu_brand)
                      = toLower($gpu_brand)
            }
            """
        )
        params["gpu_brand"] = filters.gpu_brand

    if filters.gpu_contains:
        clauses.append(
            """
            EXISTS {
                MATCH (l)-[:HAS_GPU]->(filterGPU2:GPU)
                WHERE toLower(
                    coalesce(filterGPU2.graphics_name, '')
                )
                CONTAINS toLower($gpu_contains)
            }
            """
        )
        params["gpu_contains"] = filters.gpu_contains

    return clauses, params


def get_aspects():
    query = """
    MATCH (a:Aspect)
    WHERE NOT (a.aspect_id IN $retired_aspect_ids)
    RETURN
        a.aspect_id AS aspect_id,
        a.aspect_name AS aspect_name,
        a.prior_score AS prior_score,
        a.prior_positive_ratio AS prior_positive_ratio,
        a.laptops_with_evidence AS laptops_with_evidence,
        a.total_reviews_mentioning_aspect
            AS total_reviews_mentioning_aspect
    ORDER BY a.aspect_name
    """

    return db.execute_read(
        query,
        {"retired_aspect_ids": sorted(RETIRED_RECOMMENDATION_ASPECT_IDS)},
    )


def get_valid_aspect_ids():
    return {
        row["aspect_id"]
        for row in get_aspects()
    }


def validate_aspect_ids(weights):
    valid = get_valid_aspect_ids()
    invalid = sorted(
        aspect_id
        for aspect_id in weights
        if aspect_id not in valid
    )

    if invalid:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Unknown or retired recommendation aspect ID(s).",
                "invalid_aspects": invalid,
                "valid_aspects": sorted(valid),
            },
        )


def get_filter_options():
    query = """
    MATCH (l:Laptop)

    OPTIONAL MATCH (l)-[:MADE_BY]->(b:Brand)
    OPTIONAL MATCH (l)-[:HAS_PROCESSOR]->(cpu:Processor)
    OPTIONAL MATCH (l)-[:HAS_GPU]->(gpu:GPU)

    WITH
        collect(DISTINCT b.brand_name) AS brands,
        collect(DISTINCT cpu.processor_brand) AS cpu_brands,
        collect(DISTINCT gpu.gpu_brand) AS gpu_brands,
        collect(DISTINCT l.ram_gb) AS ram_options,
        collect(DISTINCT l.storage_gb) AS storage_options,
        collect(DISTINCT l.screen_size_in) AS screen_size_options,
        min(l.price_usd) AS min_price,
        max(l.price_usd) AS max_price

    RETURN
        [x IN brands WHERE x IS NOT NULL] AS brands,
        [x IN cpu_brands WHERE x IS NOT NULL] AS cpu_brands,
        [x IN gpu_brands WHERE x IS NOT NULL] AS gpu_brands,
        [x IN ram_options WHERE x IS NOT NULL] AS ram_options_gb,
        [x IN storage_options WHERE x IS NOT NULL]
            AS storage_options_gb,
        [x IN screen_size_options WHERE x IS NOT NULL]
            AS screen_size_options_in,
        min_price AS min_price_usd,
        max_price AS max_price_usd
    """

    rows = db.execute_read(query)
    if not rows:
        return {
            "brands": [],
            "cpu_brands": [],
            "gpu_brands": [],
            "ram_options_gb": [],
            "storage_options_gb": [],
            "screen_size_options_in": [],
            "min_price_usd": None,
            "max_price_usd": None,
        }

    row = rows[0]

    row["brands"] = sorted(row["brands"])
    row["cpu_brands"] = sorted(row["cpu_brands"])
    row["gpu_brands"] = sorted(row["gpu_brands"])
    row["ram_options_gb"] = sorted(row["ram_options_gb"])
    row["storage_options_gb"] = sorted(row["storage_options_gb"])
    row["screen_size_options_in"] = sorted(
        row["screen_size_options_in"]
    )

    return row


def recommendation_query(filter_clauses):
    where_text = ""

    if filter_clauses:
        where_text = (
            "WHERE "
            + "\nAND ".join(filter_clauses)
        )

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
        sum(
            w.weight * score.adjusted_score
        ) AS recommendation_score,
        sum(
            w.weight * score.evidence_confidence
        ) AS evidence_confidence,
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

        recommendation_score,
        100.0 * recommendation_score
            AS recommendation_score_0_100,

        evidence_confidence,
        100.0 * evidence_confidence
            AS evidence_confidence_0_100,

        selected_aspects,
        selected_aspects_with_evidence,
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
    aspect.aspect_id AS aspect_id,
    aspect.aspect_name AS aspect_name,
    w.weight AS normalized_weight,

    coalesce(score.positive_reviews, 0)
        AS positive_reviews,
    coalesce(score.negative_reviews, 0)
        AS negative_reviews,
    coalesce(score.neutral_reviews, 0)
        AS neutral_reviews,
    coalesce(score.mixed_reviews, 0)
        AS mixed_reviews,
    coalesce(score.mention_count, 0)
        AS mention_count,

    score.positive_ratio AS positive_ratio,
    score.raw_sentiment_score AS raw_sentiment_score,
    score.prior_score AS prior_score,
    score.adjusted_score AS adjusted_score,

    score.evidence_confidence AS evidence_confidence,
    score.evidence_level AS evidence_level,
    score.has_direct_evidence AS has_direct_evidence,

    w.weight * score.adjusted_score
        AS weighted_score_contribution,

    w.weight * score.evidence_confidence
        AS weighted_confidence_contribution
"""


def get_recommendations(request: RecommendationRequest):
    validate_aspect_ids(request.weights)

    weights = normalize_weights(request.weights)

    filter_clauses, params = build_filter_clause(
        request.filters
    )

    params["weights"] = weights
    params["top_n"] = request.top_n

    ranking = db.execute_read(
        recommendation_query(filter_clauses),
        params,
    )

    if not ranking:
        return {
            "normalized_weights": {
                item["aspect_id"]: item["weight"]
                for item in weights
            },
            "filters": request.filters,
            "result_count": 0,
            "recommendations": [],
        }

    laptop_ids = [
        row["laptop_id"]
        for row in ranking
    ]

    breakdown = db.execute_read(
        BREAKDOWN_QUERY,
        {
            "laptop_ids": laptop_ids,
            "weights": weights,
        },
    )

    breakdown_by_laptop = {}
    for row in breakdown:
        breakdown_by_laptop.setdefault(
            row["laptop_id"],
            [],
        ).append(row)

    recommendations = []

    for rank, row in enumerate(ranking, start=1):
        laptop_id = row["laptop_id"]

        item = dict(row)
        item["rank"] = rank
        item["aspect_breakdown"] = sorted(
            breakdown_by_laptop.get(laptop_id, []),
            key=lambda x: x["normalized_weight"],
            reverse=True,
        )

        recommendations.append(item)

    return {
        "normalized_weights": {
            item["aspect_id"]: item["weight"]
            for item in weights
        },
        "filters": request.filters,
        "result_count": len(recommendations),
        "recommendations": recommendations,
    }


def get_laptop_detail(laptop_id: str):
    laptop_query = """
    MATCH (l:Laptop {laptop_id: $laptop_id})

    OPTIONAL MATCH (l)-[:MADE_BY]->(b:Brand)
    OPTIONAL MATCH (l)-[:HAS_PROCESSOR]->(cpu:Processor)
    OPTIONAL MATCH (l)-[:HAS_GPU]->(gpu:GPU)
    OPTIONAL MATCH (l)-[:RUNS_OS]->(os:OperatingSystem)

    RETURN
        l.laptop_id AS laptop_id,
        l.product_name AS product_name,
        b.brand_name AS brand,
        l.model AS model,

        cpu.processor_display_name AS processor,
        gpu.graphics_name AS gpu,
        os.os_name AS operating_system,

        l.price_usd AS price_usd,

        l.ram_gb AS ram_gb,
        l.ram_type AS ram_type,
        l.ram_speed_mhz AS ram_speed_mhz,

        l.storage_gb AS storage_gb,
        l.storage_type AS storage_type,

        l.screen_size_in AS screen_size_in,
        l.screen_resolution AS screen_resolution,
        l.display_type AS display_type,
        l.screen_type AS screen_type,
        l.refresh_rate_hz AS refresh_rate_hz,
        l.brightness_nits AS brightness_nits,
        l.touch_screen AS touch_screen,

        l.weight_lb AS weight_lb,
        l.battery_life_hours AS battery_life_hours,

        l.image_url AS image_url,
        l.product_url AS product_url,

        // Only approved offline summaries are visible to website visitors.
        CASE WHEN l.summary_status = 'approved' THEN l.overall_summary ELSE null END
            AS overall_summary,
        CASE WHEN l.summary_status = 'approved' THEN l.strengths_summary ELSE null END
            AS strengths_summary,
        CASE WHEN l.summary_status = 'approved' THEN l.weaknesses_summary ELSE null END
            AS weaknesses_summary,
        CASE WHEN l.summary_status = 'approved' THEN l.summary_evidence_note ELSE null END
            AS summary_evidence_note,
        CASE WHEN l.summary_status = 'approved' THEN l.summary_model ELSE null END
            AS summary_model,
        CASE WHEN l.summary_status = 'approved' THEN l.summary_prompt_version ELSE null END
            AS summary_prompt_version,
        CASE WHEN l.summary_status = 'approved' THEN l.summary_source_hash ELSE null END
            AS summary_source_hash
    """

    rows = db.execute_read(
        laptop_query,
        {"laptop_id": laptop_id},
    )

    if not rows:
        raise HTTPException(
            status_code=404,
            detail="Laptop not found.",
        )

    laptop = rows[0]

    aspect_query = """
    MATCH (l:Laptop {laptop_id: $laptop_id})
          -[r:HAS_ASPECT_SCORE]->(a:Aspect)

    RETURN
        a.aspect_id AS aspect_id,
        a.aspect_name AS aspect_name,

        r.positive_reviews AS positive_reviews,
        r.negative_reviews AS negative_reviews,
        r.neutral_reviews AS neutral_reviews,
        r.mixed_reviews AS mixed_reviews,
        r.mention_count AS mention_count,

        r.positive_ratio AS positive_ratio,
        r.adjusted_score AS adjusted_score,
        r.evidence_confidence AS evidence_confidence,
        r.evidence_level AS evidence_level,
        r.has_direct_evidence AS has_direct_evidence

    ORDER BY a.aspect_name
    """

    laptop["aspects"] = db.execute_read(
        aspect_query,
        {"laptop_id": laptop_id},
    )

    return laptop


def _balanced_review_sample(rows, limit):
    """
    Return a deterministic, sentiment-diverse evidence sample.

    We round-robin positive, negative, neutral and mixed evidence so a large
    positive majority does not hide the smaller amount of critical or neutral
    evidence. Within each sentiment, the Cypher query uses a deterministic
    source-review order.
    """
    if limit <= 0:
        return []

    groups = defaultdict(deque)
    for row in rows:
        groups[row["sentiment"]].append(row)

    order = ["positive", "negative", "neutral", "mixed"]
    selected = []

    while len(selected) < limit:
        added_this_round = False

        for sentiment in order:
            if groups[sentiment] and len(selected) < limit:
                selected.append(groups[sentiment].popleft())
                added_this_round = True

        if not added_this_round:
            break

    return selected


def get_aspect_evidence(
    laptop_id: str,
    aspect_id: str,
    limit: int = 6,
):
    """
    Return aggregated aspect statistics plus a small, sentiment-diverse set
    of source review snippets for one laptop and one canonical aspect.
    """
    summary_query = """
    MATCH (l:Laptop {laptop_id: $laptop_id})
          -[score:HAS_ASPECT_SCORE]->
          (a:Aspect {aspect_id: $aspect_id})

    RETURN
        l.laptop_id AS laptop_id,
        l.product_name AS laptop,
        a.aspect_id AS aspect_id,
        a.aspect_name AS aspect_name,

        score.adjusted_score AS adjusted_score,
        100.0 * score.adjusted_score
            AS adjusted_score_0_100,

        score.evidence_confidence
            AS evidence_confidence,
        100.0 * score.evidence_confidence
            AS evidence_confidence_0_100,

        score.evidence_level AS evidence_level,
        score.has_direct_evidence AS has_direct_evidence,

        coalesce(score.positive_reviews, 0)
            AS positive_reviews,
        coalesce(score.negative_reviews, 0)
            AS negative_reviews,
        coalesce(score.neutral_reviews, 0)
            AS neutral_reviews,
        coalesce(score.mixed_reviews, 0)
            AS mixed_reviews,
        coalesce(score.mention_count, 0)
            AS mention_count
    """

    summary_rows = db.execute_read(
        summary_query,
        {
            "laptop_id": laptop_id,
            "aspect_id": aspect_id,
        },
    )

    if not summary_rows:
        raise HTTPException(
            status_code=404,
            detail=(
                "Laptop/aspect combination not found in the "
                "recommendation graph."
            ),
        )

    summary = summary_rows[0]

    evidence_query = """
    MATCH (l:Laptop {laptop_id: $laptop_id})
          -[:HAS_REVIEW]->
          (r:Review)
          -[m:MENTIONS]->
          (a:Aspect {aspect_id: $aspect_id})

    WHERE m.evidence_snippet IS NOT NULL
      AND trim(m.evidence_snippet) <> ''

    RETURN
        r.review_key AS review_key,
        r.source_review_id AS source_review_id,
        r.review_date AS review_date,
        m.review_sentiment AS sentiment,
        m.evidence_snippet AS snippet,
        m.raw_aspects AS raw_aspects

    ORDER BY
        r.source_review_id ASC,
        r.review_key ASC
    """

    evidence_rows = db.execute_read(
        evidence_query,
        {
            "laptop_id": laptop_id,
            "aspect_id": aspect_id,
        },
    )

    selected = _balanced_review_sample(
        evidence_rows,
        limit,
    )

    return {
        "laptop_id": summary["laptop_id"],
        "laptop": summary["laptop"],

        "aspect_id": summary["aspect_id"],
        "aspect_name": summary["aspect_name"],

        "adjusted_score": summary["adjusted_score"],
        "adjusted_score_0_100": summary["adjusted_score_0_100"],
        "evidence_confidence": summary["evidence_confidence"],
        "evidence_confidence_0_100":
            summary["evidence_confidence_0_100"],
        "evidence_level": summary["evidence_level"],
        "has_direct_evidence": summary["has_direct_evidence"],

        "summary": {
            "positive_reviews": summary["positive_reviews"],
            "negative_reviews": summary["negative_reviews"],
            "neutral_reviews": summary["neutral_reviews"],
            "mixed_reviews": summary["mixed_reviews"],
            "mention_count": summary["mention_count"],
        },

        "total_available_reviews": len(evidence_rows),
        "returned_reviews": len(selected),
        "reviews": selected,
    }
