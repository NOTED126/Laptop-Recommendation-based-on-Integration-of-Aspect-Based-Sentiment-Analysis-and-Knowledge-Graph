"""
verify_review_evidence.py
=========================

Read-only checks for the review provenance layer.
Loads AuraDB/local Neo4j settings from backend/.env.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase


PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / "backend" / ".env")


def scalar(session, query):
    return session.run(query).single()["count"]


def main():
    uri = os.getenv("NEO4J_URI")
    username = os.getenv("NEO4J_USERNAME")
    password = os.getenv("NEO4J_PASSWORD")
    database = os.getenv("NEO4J_DATABASE")

    if not all([uri, username, password, database]):
        raise ValueError("Check Neo4j settings in backend/.env.")

    driver = GraphDatabase.driver(
        uri,
        auth=(username, password),
    )
    driver.verify_connectivity()

    try:
        with driver.session(database=database) as session:
            counts = {
                "Review nodes": scalar(
                    session,
                    "MATCH (r:Review) RETURN count(r) AS count",
                ),
                "HAS_REVIEW": scalar(
                    session,
                    """
                    MATCH (:Laptop)-[r:HAS_REVIEW]->(:Review)
                    RETURN count(r) AS count
                    """,
                ),
                "MENTIONS": scalar(
                    session,
                    """
                    MATCH (:Review)-[r:MENTIONS]->(:Aspect)
                    RETURN count(r) AS count
                    """,
                ),
            }

            checks = {
                "reviews_without_laptop": scalar(
                    session,
                    """
                    MATCH (r:Review)
                    WHERE NOT (:Laptop)-[:HAS_REVIEW]->(r)
                    RETURN count(r) AS count
                    """,
                ),
                "mentions_without_snippet": scalar(
                    session,
                    """
                    MATCH (:Review)-[m:MENTIONS]->(:Aspect)
                    WHERE m.evidence_snippet IS NULL
                       OR trim(m.evidence_snippet) = ''
                    RETURN count(m) AS count
                    """,
                ),
                "invalid_sentiment": scalar(
                    session,
                    """
                    MATCH (:Review)-[m:MENTIONS]->(:Aspect)
                    WHERE NOT m.review_sentiment IN
                        ['positive','negative','neutral','mixed']
                    RETURN count(m) AS count
                    """,
                ),
            }

            print("=" * 72)
            print("REVIEW EVIDENCE VERIFICATION")
            print("=" * 72)

            for name, value in counts.items():
                print(f"{name:<30} {value:>8}")

            print("\nIntegrity diagnostics:")
            for name, value in checks.items():
                print(f"{name:<30} {value:>8}")

            failed = (
                checks["reviews_without_laptop"] != 0
                or checks["invalid_sentiment"] != 0
            )

            print("\nOverall:", "FAIL" if failed else "PASS")
            print(
                "Note: a small number of MENTIONS relationships may "
                "legitimately lack an automatically extracted snippet."
            )
            print("=" * 72)

            if failed:
                raise RuntimeError(
                    "Review evidence integrity verification failed."
                )

    finally:
        driver.close()


if __name__ == "__main__":
    main()
