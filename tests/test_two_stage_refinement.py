"""Regression tests for the flexible, weighted two-stage refinement workflow.

Run from Program/:
    python -m pytest -q tests/test_two_stage_refinement.py
These tests simulate Neo4j responses; live DB and external services aren't needed.
"""
import importlib
import sys
import types
from pathlib import Path

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))
# Stub only the db dependency; services and validators are executed unchanged.
if "app.db" not in sys.modules:
    fake_db_module = types.ModuleType("app.db")
    fake_db_module.db = None
    sys.modules["app.db"] = fake_db_module

models = importlib.import_module("app.models")
services = importlib.import_module("app.services")

ASPECTS = ["BATTERY_LIFE", "PERFORMANCE", "DISPLAY_QUALITY", "PORTABILITY", "AUDIO"]
DEFAULT_INITIAL = {"BATTERY_LIFE": 50, "PERFORMANCE": 30, "DISPLAY_QUALITY": 20}
DEFAULT_REFINED = {"BATTERY_LIFE": 35, "PERFORMANCE": 25, "DISPLAY_QUALITY": 15, "PORTABILITY": 15, "AUDIO": 10}


class FakeGraph:
    """15 deterministic laptop records with distinct sentiment profiles and prices."""
    def __init__(self):
        self.queries = []

    def execute_read(self, query, params=None):
        params = params or {}
        self.queries.append((query, dict(params)))
        if "MATCH (a:Aspect)" in query:
            return [{"aspect_id": aspect, "aspect_name": aspect} for aspect in ASPECTS]
        if "LIMIT $top_n" in query:
            weights = {d["aspect_id"]: d["weight"] for d in params["weights"]}
            rows = []
            for index in range(15):
                lid = f"laptop_{index:02d}"
                price = 500 + 150 * index
                if "candidate_laptop_ids" in params and lid not in params["candidate_laptop_ids"]:
                    continue
                if "min_ram" in params and 8 + index < params["min_ram"]:
                    continue
                if "min_price" in params and price < params["min_price"]:
                    continue
                if "max_price" in params and price > params["max_price"]:
                    continue
                scores = {
                    "BATTERY_LIFE": .95 - .045 * index,
                    "PERFORMANCE": .90 - .030 * index,
                    "DISPLAY_QUALITY": .88 - .040 * index,
                    "PORTABILITY": .10 + .060 * index,
                    "AUDIO": .10 + .060 * index,
                }
                score = sum(scores[aspect] * weight for aspect, weight in weights.items())
                rows.append({
                    "laptop_id": lid,
                    "laptop": f"Laptop {index}",
                    "price_usd": price,
                    "recommendation_score": score,
                    "recommendation_score_0_100": score * 100,
                    "evidence_confidence": .8,
                    "evidence_confidence_0_100": 80,
                    "selected_aspects": len(weights),
                    "selected_aspects_with_evidence": len(weights),
                    "selected_aspects_without_evidence": 0,
                })
            rows.sort(key=lambda row: (-row["recommendation_score"], row["laptop"]))
            return rows[:params["top_n"]]
        if "UNWIND $laptop_ids AS laptop_id" in query:
            return [{"laptop_id": lid, "aspect_id": w["aspect_id"],
                     "normalized_weight": w["weight"]}
                    for lid in params["laptop_ids"] for w in params["weights"]]
        raise AssertionError("Unexpected Cypher query")


@pytest.fixture
def fake_graph(monkeypatch):
    fake = FakeGraph()
    monkeypatch.setattr(services, "db", fake)
    return fake


def shortlist(filters=None, initial=None):
    return services.get_recommendations(models.RecommendationRequest(
        filters=filters or {},
        weights=initial if initial is not None else DEFAULT_INITIAL,
        top_n=10,
    ))


def refine_request(ids, filters=None, initial=None, refined=None):
    return models.TwoStageRefinementRequest(
        filters=filters or {},
        initial_weights=initial if initial is not None else DEFAULT_INITIAL,
        refined_weights=refined if refined is not None else DEFAULT_REFINED,
        candidate_laptop_ids=ids,
    )


def ids_from(result):
    return [item["laptop_id"] for item in result["recommendations"]]


def test_stage1_caps_at_top_10(fake_graph):
    initial = shortlist()
    assert initial["result_count"] == 10
    assert len(set(ids_from(initial))) == 10


def test_stage1_with_exactly_10_eligible(fake_graph):
    initial = shortlist(filters={"max_price": 1850})
    assert initial["result_count"] == 10
    assert all(row["price_usd"] <= 1850 for row in initial["recommendations"])


def test_stage1_with_fewer_than_10_eligible(fake_graph):
    initial = shortlist(filters={"max_price": 1100})
    assert initial["result_count"] == 5
    assert all(row["price_usd"] <= 1100 for row in initial["recommendations"])
    refined = services.get_refined_recommendations(refine_request(ids_from(initial), filters={"max_price": 1100}))
    assert refined["result_count"] == 5
    assert set(ids_from(refined)) == set(ids_from(initial))


def test_stage1_with_price_minimum_and_maximum(fake_graph):
    initial = shortlist(filters={"min_price": 650, "max_price": 950})
    assert initial["result_count"] == 3
    assert all(650 <= row["price_usd"] <= 950 for row in initial["recommendations"])


def test_stage1_with_zero_eligible(fake_graph):
    assert shortlist(filters={"max_price": 100})["result_count"] == 0


def test_stage2_preserves_and_reorders_candidates(fake_graph):
    initial = shortlist()
    original_ids = ids_from(initial)
    refined = services.get_refined_recommendations(refine_request(original_ids, refined={
        "BATTERY_LIFE": 1, "PERFORMANCE": 1, "DISPLAY_QUALITY": 1,
        "PORTABILITY": 100, "AUDIO": 100,
    }))
    new_ids = ids_from(refined)
    assert len(new_ids) == len(original_ids) == 10
    assert set(new_ids) == set(original_ids)
    assert new_ids != original_ids
    assert len(refined["normalized_weights"]) == 5
    assert sum(refined["normalized_weights"].values()) == pytest.approx(1)
    ranking = [(q, p) for q, p in fake_graph.queries if "LIMIT $top_n" in q]
    assert "l.laptop_id IN $candidate_laptop_ids" in ranking[-1][0]
    assert ranking[-1][1]["candidate_laptop_ids"] == original_ids
    assert "l.laptop_id IN $candidate_laptop_ids" not in ranking[0][0]


def test_stage2_uses_reweighted_stage1_aspects(fake_graph):
    initial = shortlist()
    original_ids = ids_from(initial)
    adjusted = {"BATTERY_LIFE": 5, "PERFORMANCE": 90, "DISPLAY_QUALITY": 5,
                "PORTABILITY": 100}
    result = services.get_refined_recommendations(refine_request(original_ids, refined=adjusted))
    weights = result["normalized_weights"]
    assert weights == pytest.approx({key: value / 200 for key, value in adjusted.items()})
    assert set(ids_from(result)) == set(original_ids)
    # Server must verify against original Stage 1 weights, not edited Stage 2 weights.
    requests = [p for q, p in fake_graph.queries if "LIMIT $top_n" in q]
    assert requests[1]["weights"] == pytest.approx([
        {"aspect_id": k, "weight": v / 100} for k, v in DEFAULT_INITIAL.items()
    ])


@pytest.mark.parametrize("initial,refined", [
    ({"BATTERY_LIFE": 20}, {"BATTERY_LIFE": 50, "PORTABILITY": 50}),
    ({"BATTERY_LIFE": 50, "PERFORMANCE": 50},
     {"BATTERY_LIFE": 50, "PERFORMANCE": 40, "AUDIO": 10}),
    ({"BATTERY_LIFE": 10, "PERFORMANCE": 20, "DISPLAY_QUALITY": 30, "PORTABILITY": 40},
     {"BATTERY_LIFE": 5, "PERFORMANCE": 5, "DISPLAY_QUALITY": 5, "PORTABILITY": 5, "AUDIO": 80}),
])
def test_variable_stage_lengths_and_weights(fake_graph, initial, refined):
    first = shortlist(initial=initial)
    refined_response = services.get_refined_recommendations(
        refine_request(ids_from(first), initial=initial, refined=refined)
    )
    assert set(ids_from(refined_response)) == set(ids_from(first))
    assert refined_response["normalized_weights"] == pytest.approx(
        {aspect: weight / sum(refined.values()) for aspect, weight in refined.items()}
    )


def test_can_select_all_23_aspects_in_total():
    initial = {f"ASPECT_{i}": 50 for i in range(22)}
    refined = {**initial, "ASPECT_22": 50}
    req = models.TwoStageRefinementRequest(initial_weights=initial, refined_weights=refined,
                                           candidate_laptop_ids=["one"])
    assert len(req.initial_weights) == 22
    assert len(req.refined_weights) == 23


def test_missing_candidate_rejected(fake_graph):
    ids = ids_from(shortlist())
    with pytest.raises(HTTPException) as error:
        services.get_refined_recommendations(refine_request(ids[:-1]))
    assert error.value.status_code == 409


def test_forged_candidate_rejected(fake_graph):
    ids = ids_from(shortlist())
    ids[-1] = "laptop_14"
    with pytest.raises(HTTPException) as error:
        services.get_refined_recommendations(refine_request(ids))
    assert error.value.status_code == 409


def test_forged_shortlist_order_rejected(fake_graph):
    ids = list(reversed(ids_from(shortlist())))
    with pytest.raises(HTTPException) as error:
        services.get_refined_recommendations(refine_request(ids))
    assert error.value.status_code == 409


def test_changed_filters_rejected(fake_graph):
    ids = ids_from(shortlist())
    with pytest.raises(HTTPException) as error:
        services.get_refined_recommendations(refine_request(ids, filters={"min_ram": 16}))
    assert error.value.status_code == 409


def test_changed_stage1_weights_rejected_when_shortlist_changes(fake_graph):
    ids = ids_from(shortlist())
    altered_initial = {"PORTABILITY": 100, "PERFORMANCE": 1, "DISPLAY_QUALITY": 1}
    with pytest.raises(HTTPException) as error:
        services.get_refined_recommendations(refine_request(ids, initial=altered_initial))
    assert error.value.status_code == 409


@pytest.mark.parametrize("initial,refined,ids", [
    ({}, {"PORTABILITY": 1}, ["one"]),
    ({"BATTERY_LIFE": 1}, {}, ["one"]),
    ({"BATTERY_LIFE": 1}, {"PORTABILITY": 1}, ["one"]), # discarded initial
    ({"BATTERY_LIFE": 1}, {"BATTERY_LIFE": 30}, ["one"]), # nothing new
    ({"BATTERY_LIFE": 1}, {"BATTERY_LIFE": 1, "AUDIO": 1}, ["one", "one"]),
    ({"BATTERY_LIFE": 1}, {"BATTERY_LIFE": 1, "AUDIO": 0}, ["one"]),
    ({"BATTERY_LIFE": 1}, {"BATTERY_LIFE": 1, "AUDIO": -1}, ["one"]),
    ({"BATTERY_LIFE": 1}, {"BATTERY_LIFE": 1, "AUDIO": float("inf")}, ["one"]),
    ({"BATTERY_LIFE": 1}, {"BATTERY_LIFE": 1, "AUDIO": 1}, []),
    ({"BATTERY_LIFE": 1}, {"BATTERY_LIFE": 1, "AUDIO": 1}, [str(i) for i in range(11)]),
    ({"BATTERY_LIFE": 1, " battery_life ": 1}, {"BATTERY_LIFE": 1, "AUDIO": 1}, ["one"]),
])
def test_invalid_stage_requests(initial, refined, ids):
    with pytest.raises(ValidationError):
        models.TwoStageRefinementRequest(initial_weights=initial,
                                         refined_weights=refined, candidate_laptop_ids=ids)


def test_invalid_price_range_rejected():
    with pytest.raises(ValidationError):
        models.RecommendationFilters(min_price=1500, max_price=1000)
    with pytest.raises(ValidationError):
        models.RecommendationRequest(filters={"min_price": 1500, "max_price": 1000},
                                     weights={"BATTERY_LIFE": 50})


def test_unknown_aspect_rejected(fake_graph):
    ids = ids_from(shortlist())
    with pytest.raises(HTTPException) as error:
        services.get_refined_recommendations(refine_request(ids,
            refined={**DEFAULT_INITIAL, "UNKNOWN_ASPECT": 40}))
    assert error.value.status_code == 400


def test_retired_aspect_rejected(fake_graph):
    ids = ids_from(shortlist())
    with pytest.raises(HTTPException) as error:
        services.get_refined_recommendations(refine_request(ids,
            refined={**DEFAULT_INITIAL, "FEATURE_SET": 40}))
    assert error.value.status_code == 400


def test_original_laptop_evidence_and_summary_queries_untouched():
    source = (BACKEND / "app" / "services.py").read_text(encoding="utf-8")
    assert "def get_laptop_detail" in source
    assert "l.overall_summary" in source
    assert "def get_aspect_evidence" in source


def test_single_eligible_candidate_is_preserved(fake_graph):
    first = shortlist(filters={"max_price": 500})
    assert first["result_count"] == 1
    refined = services.get_refined_recommendations(
        refine_request(ids_from(first), filters={"max_price": 500})
    )
    assert ids_from(refined) == ids_from(first)
