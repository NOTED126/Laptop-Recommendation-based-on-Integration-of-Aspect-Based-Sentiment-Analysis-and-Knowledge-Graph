"""
verify_neo4j_graph.py
=====================

Read-only verification utility for the laptop thesis graph.

Example:
    python knowledge_graph/scripts/verify_neo4j_graph.py

Connection settings are read from:
    NEO4J_URI
    NEO4J_USERNAME
    NEO4J_PASSWORD
    NEO4J_DATABASE
"""

import argparse
import json
import os
from pathlib import Path

from neo4j import GraphDatabase

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = PROJECT_ROOT / "backend" / ".env"

load_dotenv(ENV_FILE)


def run_scalar(session, query, **parameters):
    record = session.run(query, **parameters).single()
    return record["count"]


def run_verification(session):
    counts = {
        "Laptop": run_scalar(
            session, "MATCH (n:Laptop) RETURN count(n) AS count"
        ),
        "Brand": run_scalar(
            session, "MATCH (n:Brand) RETURN count(n) AS count"
        ),
        "Processor": run_scalar(
            session, "MATCH (n:Processor) RETURN count(n) AS count"
        ),
        "GPU": run_scalar(
            session, "MATCH (n:GPU) RETURN count(n) AS count"
        ),
        "OperatingSystem": run_scalar(
            session, "MATCH (n:OperatingSystem) RETURN count(n) AS count"
        ),
        "Aspect": run_scalar(
            session, "MATCH (n:Aspect) RETURN count(n) AS count"
        ),
        "MADE_BY": run_scalar(
            session, "MATCH ()-[r:MADE_BY]->() RETURN count(r) AS count"
        ),
        "HAS_PROCESSOR": run_scalar(
            session,
            "MATCH ()-[r:HAS_PROCESSOR]->() RETURN count(r) AS count",
        ),
        "HAS_GPU": run_scalar(
            session, "MATCH ()-[r:HAS_GPU]->() RETURN count(r) AS count"
        ),
        "RUNS_OS": run_scalar(
            session, "MATCH ()-[r:RUNS_OS]->() RETURN count(r) AS count"
        ),
        "HAS_ASPECT_SCORE": run_scalar(
            session,
            "MATCH ()-[r:HAS_ASPECT_SCORE]->() RETURN count(r) AS count",
        ),
    }

    checks = {
        "laptops_without_brand": run_scalar(
            session,
            """
            MATCH (l:Laptop)
            WHERE NOT (l)-[:MADE_BY]->(:Brand)
            RETURN count(l) AS count
            """,
        ),
        "laptops_without_processor": run_scalar(
            session,
            """
            MATCH (l:Laptop)
            WHERE NOT (l)-[:HAS_PROCESSOR]->(:Processor)
            RETURN count(l) AS count
            """,
        ),
        "laptops_without_gpu": run_scalar(
            session,
            """
            MATCH (l:Laptop)
            WHERE NOT (l)-[:HAS_GPU]->(:GPU)
            RETURN count(l) AS count
            """,
        ),
        "laptops_without_os": run_scalar(
            session,
            """
            MATCH (l:Laptop)
            WHERE NOT (l)-[:RUNS_OS]->(:OperatingSystem)
            RETURN count(l) AS count
            """,
        ),
        "invalid_aspect_score_ranges": run_scalar(
            session,
            """
            MATCH ()-[r:HAS_ASPECT_SCORE]->()
            WHERE r.adjusted_score < 0 OR r.adjusted_score > 1
               OR r.evidence_confidence < 0
               OR r.evidence_confidence > 1
            RETURN count(r) AS count
            """,
        ),
        "invalid_sentiment_count_sums": run_scalar(
            session,
            """
            MATCH ()-[r:HAS_ASPECT_SCORE]->()
            WHERE coalesce(r.positive_reviews, 0)
                + coalesce(r.negative_reviews, 0)
                + coalesce(r.neutral_reviews, 0)
                + coalesce(r.mixed_reviews, 0)
                <> coalesce(r.mention_count, 0)
            RETURN count(r) AS count
            """,
        ),
    }

    aspect_count = counts["Aspect"]

    checks["laptops_with_incomplete_aspect_matrix"] = run_scalar(
        session,
        """
        MATCH (l:Laptop)
        OPTIONAL MATCH (l)-[r:HAS_ASPECT_SCORE]->(:Aspect)
        WITH l, count(r) AS score_count, $aspect_count AS aspect_count
        WHERE score_count <> aspect_count
        RETURN count(l) AS count
        """,
        aspect_count=aspect_count,
    )

    print("=" * 72)
    print("NEO4J THESIS GRAPH - READ-ONLY VERIFICATION")
    print("=" * 72)

    print("\nCounts:")
    for name, count in counts.items():
        print(f"  {name:<24} {count:>6}")

    print("\nIntegrity checks (all should be 0):")
    passed = True
    for name, count in checks.items():
        status = "PASS" if count == 0 else "FAIL"
        if count != 0:
            passed = False
        print(f"  {name:<42} {count:>6}  {status}")

    print("\nOverall:", "PASS" if passed else "FAIL")
    print("=" * 72)

    if not passed:
        raise RuntimeError("Graph verification failed.")


def parse_args():
    parser = argparse.ArgumentParser()

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

    return parser.parse_args()


def main():
    args = parse_args()

    if not args.password:
        raise ValueError(
            "Set NEO4J_PASSWORD or supply --password."
        )

    driver = GraphDatabase.driver(
        args.uri,
        auth=(args.username, args.password),
    )
    driver.verify_connectivity()

    try:
        with driver.session(database=args.database) as session:
            run_verification(session)
    finally:
        driver.close()


if __name__ == "__main__":
    main()
