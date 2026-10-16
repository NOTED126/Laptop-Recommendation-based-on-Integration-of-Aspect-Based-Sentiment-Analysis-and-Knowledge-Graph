"""
import_review_evidence.py
=========================

Import the prepared review provenance layer into the existing Neo4j/AuraDB
thesis graph.

Creates:
    (:Review)
    (Laptop)-[:HAS_REVIEW]->(Review)
    (Review)-[:MENTIONS]->(Aspect)

Connection settings are loaded from backend/.env automatically.
"""

import argparse
import math
import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from neo4j import GraphDatabase


PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / "backend" / ".env")


def scalar(value):
    if value is None:
        return None

    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass

    if hasattr(value, "item"):
        try:
            value = value.item()
        except Exception:
            pass

    if isinstance(value, float) and (
        math.isnan(value) or math.isinf(value)
    ):
        return None

    return value


def rows(path):
    df = pd.read_csv(path)
    return [
        {
            key: scalar(value)
            for key, value in row.items()
        }
        for row in df.to_dict(orient="records")
    ]


def batches(items, size):
    for start in range(0, len(items), size):
        yield items[start : start + size]


def run_batches(session, query, records, batch_size):
    for batch in batches(records, batch_size):
        session.run(query, rows=batch).consume()


def count(session, query):
    return session.run(query).single()["count"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--data-dir",
        default="knowledge_graph/review_evidence",
    )
    parser.add_argument("--batch-size", type=int, default=500)
    args = parser.parse_args()

    uri = os.getenv("NEO4J_URI")
    username = os.getenv("NEO4J_USERNAME")
    password = os.getenv("NEO4J_PASSWORD")
    database = os.getenv("NEO4J_DATABASE")

    if not all([uri, username, password, database]):
        raise ValueError(
            "Neo4j settings are missing. Check backend/.env."
        )

    data_dir = Path(args.data_dir)

    review_nodes = rows(data_dir / "review_nodes.csv")
    laptop_review = rows(
        data_dir / "laptop_review_edges.csv"
    )
    review_aspects = rows(
        data_dir / "review_aspect_edges.csv"
    )

    driver = GraphDatabase.driver(
        uri,
        auth=(username, password),
    )
    driver.verify_connectivity()

    try:
        with driver.session(database=database) as session:
            print("Creating Review uniqueness constraint...")
            session.run(
                """
                CREATE CONSTRAINT review_key_unique IF NOT EXISTS
                FOR (r:Review)
                REQUIRE r.review_key IS UNIQUE
                """
            ).consume()

            print(f"Importing {len(review_nodes)} Review nodes...")
            run_batches(
                session,
                """
                UNWIND $rows AS row
                MERGE (r:Review {review_key: row.review_key})
                SET r += row
                """,
                review_nodes,
                args.batch_size,
            )

            print(
                f"Importing {len(laptop_review)} "
                "HAS_REVIEW relationships..."
            )
            run_batches(
                session,
                """
                UNWIND $rows AS row
                MATCH (l:Laptop {laptop_id: row.laptop_id})
                MATCH (r:Review {review_key: row.review_key})
                MERGE (l)-[:HAS_REVIEW]->(r)
                """,
                laptop_review,
                args.batch_size,
            )

            print(
                f"Importing {len(review_aspects)} "
                "MENTIONS relationships..."
            )
            run_batches(
                session,
                """
                UNWIND $rows AS row
                MATCH (r:Review {review_key: row.review_key})
                MATCH (a:Aspect {aspect_id: row.aspect_id})
                MERGE (r)-[m:MENTIONS]->(a)
                SET m.review_sentiment = row.review_sentiment,
                    m.positive_mentions = row.positive_mentions,
                    m.negative_mentions = row.negative_mentions,
                    m.neutral_mentions = row.neutral_mentions,
                    m.raw_aspects = row.raw_aspects,
                    m.evidence_snippet = row.evidence_snippet
                """,
                review_aspects,
                args.batch_size,
            )

            actual_reviews = count(
                session,
                "MATCH (r:Review) RETURN count(r) AS count",
            )
            actual_has_review = count(
                session,
                """
                MATCH (:Laptop)-[r:HAS_REVIEW]->(:Review)
                RETURN count(r) AS count
                """,
            )
            actual_mentions = count(
                session,
                """
                MATCH (:Review)-[r:MENTIONS]->(:Aspect)
                RETURN count(r) AS count
                """,
            )

            print("\n" + "=" * 72)
            print("REVIEW EVIDENCE IMPORT VERIFICATION")
            print("=" * 72)
            print(f"Review nodes:              {actual_reviews}")
            print(f"HAS_REVIEW relationships:  {actual_has_review}")
            print(f"MENTIONS relationships:    {actual_mentions}")

            expected = (
                len(review_nodes),
                len(laptop_review),
                len(review_aspects),
            )
            actual = (
                actual_reviews,
                actual_has_review,
                actual_mentions,
            )

            if actual != expected:
                raise RuntimeError(
                    f"Count mismatch. Expected {expected}, got {actual}"
                )

            print("Result: PASS")
            print("=" * 72)

    finally:
        driver.close()

    print("\nReview evidence layer imported successfully.")


if __name__ == "__main__":
    main()
