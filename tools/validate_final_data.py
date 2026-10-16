#!/usr/bin/env python3
"""Read-only consistency checks for this package's finalized CSV artifacts."""
import csv, json, hashlib
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parents[1]

def rows(path):
    with (ROOT / path).open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))

def require(ok, label):
    if not ok: raise AssertionError(label)
    print("PASS:", label)

def main():
    raw = rows("pipeline_output/raw_aspect_predictions.csv")
    can = rows("pipeline_output_v3/canonical_review_level_aspects_v3.csv")
    scores = rows("recommendation_scores/laptop_aspect_scores.csv")
    laptops = rows("knowledge_graph/data/laptops.csv")
    aspects = rows("knowledge_graph/data/aspects.csv")
    edges = rows("knowledge_graph/data/laptop_aspect_score_edges.csv")
    review_nodes = rows("knowledge_graph/review_evidence/review_nodes.csv")
    review_edges = rows("knowledge_graph/review_evidence/review_aspect_edges.csv")
    review_laptop_edges = rows("knowledge_graph/review_evidence/laptop_review_edges.csv")
    require(len(raw) == 49424, "49,424 corrected raw predictions")
    require(len(rows("pipeline_output_v3/raw_aspect_predictions_v3.csv")) == len(raw), "v3 prediction count matches")
    require(len(can) == 18794, "18,794 corrected canonical review-aspects")
    require(len(laptops) == 30 and len({r["laptop_id"] for r in laptops}) == 30, "30 unique laptops")
    require(len(aspects) == 24 and len({r["aspect_id"] for r in aspects}) == 24, "24 unique aspects")
    require(len(scores) == len(edges) == 720, "720 score rows and graph edges")
    pairs = {(r["laptop_id"], r["aspect_id"]) for r in edges}
    require(len(pairs) == 720, "No duplicate laptop-aspect graph pairs")
    require(pairs == {(l["laptop_id"], a["aspect_id"]) for l in laptops for a in aspects}, "Complete 30 x 24 matrix")
    review_keys = {r["review_key"] for r in review_nodes}
    require(len(review_nodes) == len(review_keys) == 6000, "6,000 unique review nodes")
    require(len(review_laptop_edges) == 6000, "6,000 laptop-review edges")
    require(len(review_edges) == 15943, "15,943 review-aspect edges")
    require(all(r["review_key"] in review_keys for r in review_edges), "Review-aspect sources all exist")
    require(all(r["aspect_id"] in {a["aspect_id"] for a in aspects} for r in review_edges), "Review-aspect targets all exist")
    for path in ["knowledge_graph/data/kg_manifest.json", "knowledge_graph/review_evidence/review_evidence_manifest.json"]:
        require((ROOT / path).is_file(), f"Saved manifest exists: {path}")
    approved = list((ROOT / "knowledge_graph/generated_summaries/drafts").glob("*.json"))
    require(len(approved) == 30 and all(json.loads(p.read_text(encoding="utf-8")).get("approved") is True for p in approved), "30 explicitly approved summary drafts")
    print("STATIC FINAL-DATA CHECKS COMPLETE. Run import_laptop_summaries.py for source-hash and text-policy validation.")

if __name__ == "__main__": main()
