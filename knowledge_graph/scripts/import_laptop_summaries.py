"""Verify and optionally import REVIEWED Gemini-generated laptop summaries to Neo4j.

Safeguards:
- All 30 summaries must be explicitly reviewed and approved.
- The current evidence CSV must match each draft's source-data hash.
- Existing Laptop nodes are MATCHED, never MERGEd/deleted.
- --apply is required to write. Without it, this performs file checks only.
- Never use --clear-existing or rerun the main graph importer for summaries.

From project root (Program/):
    python knowledge_graph/scripts/import_laptop_summaries.py
    python knowledge_graph/scripts/import_laptop_summaries.py --apply
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from generate_laptop_summaries import (
    PROJECT_ROOT, draft_name, read_and_prepare, validate_output
)


def read_approved(scores_path, output_dir):
    packets = read_and_prepare(scores_path)
    summaries = []
    for packet in packets:
        path = output_dir / "drafts" / draft_name(packet["laptop"])
        if not path.exists():
            raise ValueError(f"Not generated yet: {packet['laptop']}")
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("laptop") != packet["laptop"]:
            raise ValueError(f"Laptop-name mismatch in {path}")
        if data.get("input_sha256") != packet["input_sha256"]:
            raise ValueError(f"Stale summary (source CSV changed): {packet['laptop']}")
        validate_output(data, packet)
        if data.get("approved") is not True or not data.get("reviewed_at"):
            raise ValueError(f"Draft needs explicit human approval: {packet['laptop']}")
        if not data.get("model") or not data.get("prompt_version") or not data.get("generated_at"):
            raise ValueError(f"Missing summary audit metadata: {packet['laptop']}")
        summaries.append({
            "laptop": data["laptop"],
            "overall_summary": data["overall_summary"],
            "strengths_summary": data["strengths_summary"],
            "weaknesses_summary": data["weaknesses_summary"],
            "summary_evidence_note": data["evidence_note"],
            "summary_model": data["model"],
            "summary_prompt_version": data["prompt_version"],
            "summary_source_hash": data["input_sha256"],
            "summary_generated_at": data["generated_at"],
            "summary_reviewed_at": data["reviewed_at"],
        })
    if len(summaries) != 30 or len({s["laptop"] for s in summaries}) != 30:
        raise ValueError("Expected exactly 30 distinct approved summaries")
    return summaries


def apply_to_neo4j(summaries, uri, username, password, database):
    from neo4j import GraphDatabase

    if not uri or not password:
        raise RuntimeError("Set NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD and NEO4J_DATABASE before --apply")
    print(f"Target URI: {uri} | database: {database} (credentials never displayed)")
    driver = GraphDatabase.driver(uri, auth=(username, password))
    try:
        driver.verify_connectivity()
        with driver.session(database=database) as session:
            existing = session.run(
                "MATCH (l:Laptop) RETURN l.product_name AS name, l.laptop_id AS id"
            ).data()
            found_names = [row["name"] for row in existing]
            expected_names = [row["laptop"] for row in summaries]
            if len(existing) != 30 or len(set(found_names)) != 30 or set(found_names) != set(expected_names):
                raise RuntimeError(
                    "Laptop identity preflight failed: expected exactly 30 unique matching Laptop "
                    "nodes. No summaries were changed."
                )

            def update(transaction):
                record = transaction.run(
                    """
                    UNWIND $summaries AS s
                    MATCH (l:Laptop {product_name: s.laptop})
                    SET l.overall_summary = s.overall_summary,
                        l.strengths_summary = s.strengths_summary,
                        l.weaknesses_summary = s.weaknesses_summary,
                        l.summary_evidence_note = s.summary_evidence_note,
                        l.summary_model = s.summary_model,
                        l.summary_prompt_version = s.summary_prompt_version,
                        l.summary_source_hash = s.summary_source_hash,
                        l.summary_generated_at = s.summary_generated_at,
                        l.summary_reviewed_at = s.summary_reviewed_at,
                        l.summary_status = 'approved'
                    RETURN count(l) AS updated
                    """,
                    summaries=summaries,
                ).single()
                if record["updated"] != 30:
                    raise RuntimeError(f"Expected 30 laptop updates, got {record['updated']}")
                return record["updated"]

            updated = session.execute_write(update)
            verified = session.run(
                "MATCH (l:Laptop) WHERE l.summary_status = 'approved' AND l.overall_summary IS NOT NULL "
                "RETURN count(l) AS count"
            ).single()["count"]
            if verified != 30:
                raise RuntimeError(f"Post-update verification failed: {verified} of 30 approved")
            print(f"SUCCESS: updated {updated} existing Laptop nodes; verified {verified} approved summaries.")
    finally:
        driver.close()


def cli():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scores", type=Path, default=PROJECT_ROOT / "recommendation_scores/laptop_aspect_scores.csv")
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "knowledge_graph/generated_summaries")
    parser.add_argument("--apply", action="store_true", help="Actually write to the configured Neo4j database")
    args = parser.parse_args()
    summaries = read_approved(args.scores, args.output_dir)
    print(f"PASS: {len(summaries)} approved, current, structurally checked summaries.")
    if not args.apply:
        print("DRY RUN ONLY — no Neo4j write. Re-run with --apply to update existing Laptop nodes.")
        return

    # Mirror the project's established backend/.env loader while allowing
    # explicit PowerShell environment variables to override .env values.
    try:
        from dotenv import load_dotenv
    except ImportError:
        load_dotenv = None
    if load_dotenv:
        load_dotenv(PROJECT_ROOT / "backend" / ".env", override=False)
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    database = os.getenv("NEO4J_DATABASE", "neo4j")
    print(f"ABOUT TO WRITE to {uri} / {database} (no nodes created or deleted).")
    confirm = input("Type UPDATE to write approved summaries to that database: ").strip()
    if confirm != "UPDATE":
        print("Cancelled. No Neo4j write performed.")
        return
    apply_to_neo4j(
        summaries,
        uri,
        os.getenv("NEO4J_USERNAME", "neo4j"),
        os.getenv("NEO4J_PASSWORD"),
        database,
    )


if __name__ == "__main__":
    cli()
