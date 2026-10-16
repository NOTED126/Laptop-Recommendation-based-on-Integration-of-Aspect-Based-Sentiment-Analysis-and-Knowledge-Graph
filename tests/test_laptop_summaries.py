"""Offline regression tests. No Gemini API key or Neo4j connection required."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "knowledge_graph/scripts/generate_laptop_summaries.py"
spec = importlib.util.spec_from_file_location("laptop_summaries", GENERATOR)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
DATA = ROOT / "recommendation_scores/laptop_aspect_scores.csv"

# Source-only checkout: the validated score CSV is distributed separately.
# When that CSV is restored, all original evidence-based tests run normally.
pytestmark = pytest.mark.skipif(
    not DATA.is_file(),
    reason="Requires finalized recommendation_scores/laptop_aspect_scores.csv (excluded from source-only ZIP)",
)


def packets():
    return module.read_and_prepare(DATA)


def fake_valid(packet):
    sid = packet["eligible_strength_aspect_ids"][:1]
    wid = packet["eligible_weakness_aspect_ids"][:1]
    return module.normalize_generated({
        "overall_summary": "Model-proposed general review summary.",
        "strengths_summary": "Model-proposed strengths summary.",
        "weaknesses_summary": "Model-proposed weaknesses summary.",
        "evidence_note": "Model-proposed note about predicted reviews and possible errors.",
        "strength_aspect_ids": sid,
        "weakness_aspect_ids": wid,
    }, packet)


def test_30_laptops_23_aspects_and_new_version():
    ps = packets()
    assert len(ps) == 30
    assert len({x["laptop"] for x in ps}) == 30
    assert all(len(x["aspects"]) == 23 for x in ps)
    assert all("FEATURE_SET" not in {a["aspect_id"] for a in x["aspects"]} for x in ps)
    assert all(x["prompt_version"] == "aspect-evidence-v2.1" for x in ps)
    assert module.DEFAULT_MODEL == "gemini-3.5-flash-lite"


def test_all_mock_results_validate():
    for p in packets():
        assert module.validate_output(fake_valid(p), p)


def test_reject_retired_strength():
    p = packets()[0]
    out = fake_valid(p)
    out["strength_aspect_ids"] = ["FEATURE_SET"]
    with pytest.raises(ValueError, match="unsupported aspect"):
        module.validate_output(out, p)


def test_reject_numeric_benchmark():
    p = packets()[0]
    out = fake_valid(p)
    out["overall_summary"] = "This computer achieves 50 frames per second on the benchmark."
    with pytest.raises(ValueError, match="numerical assertion"):
        module.validate_output(out, p)


@pytest.mark.parametrize("word", ["exceptional", "vibrant", "long-lasting", "reliable", "unanimously", "preloaded"])
def test_reject_overconfident_and_unsupported_specifics(word):
    p = packets()[0]
    out = fake_valid(p)
    out["overall_summary"] = f"The review sentiment suggests {word} experiences in several areas."
    with pytest.raises(ValueError, match="overconfident wording"):
        module.validate_output(out, p)


def test_mixed_sentiment_weakness_requires_caution():
    ps = packets()
    p = next(p for p in ps if any(
        a["sentiment_pattern"] == "mixed_or_divided" and
        a["aspect_id"] in p["eligible_weakness_aspect_ids"]
        for a in p["aspects"]
    ))
    out = fake_valid(p)
    mixed = next(a for a in p["aspects"] if
                 a["sentiment_pattern"] == "mixed_or_divided" and
                 a["aspect_id"] in p["eligible_weakness_aspect_ids"])
    out["weakness_aspect_ids"] = [mixed["aspect_id"]]
    out = module.normalize_generated(out, p)
    out["weaknesses_summary"] = f"Reviewers report dissatisfaction with {mixed['summary_term']}."
    with pytest.raises(ValueError, match="Sentiment mismatch"):
        module.validate_output(out, p)
    out["weaknesses_summary"] = f"Feedback on {mixed['summary_term']} is divided."
    # A natural, evidence-consistent paraphrase is now accepted.
    assert module.validate_output(out, p)
    normalized = module.normalize_generated(out, p)
    assert module.validate_output(normalized, p)


def test_reject_ineligible_aspect_in_overall_summary():
    p = packets()[0]
    out = fake_valid(p)
    ineligible = next(a for a in p["aspects"] if
                      a["aspect_id"] not in out["strength_aspect_ids"] + out["weakness_aspect_ids"])
    out["overall_summary"] = f"Reviewers also value {ineligible['summary_term']} according to reviews."
    with pytest.raises(ValueError, match="Unselected aspect"):
        module.validate_output(out, p)


def test_reject_missing_selected_term_in_strengths():
    p = packets()[0]
    out = fake_valid(p)
    out["strengths_summary"] = "Several aspects receive favourable customer review sentiment."
    with pytest.raises(ValueError, match="Aspect term mismatch"):
        module.validate_output(out, p)


def test_gaming_performance_does_not_imply_performance():
    p = next(p for p in packets() if "GAMING_PERFORMANCE" in p["eligible_strength_aspect_ids"])
    out = fake_valid(p)
    out["strength_aspect_ids"] = ["GAMING_PERFORMANCE"]
    out["strengths_summary"] = "Review sentiment regarding gaming performance is favourable."
    normalized = module.normalize_generated(out, p)
    assert module.validate_output(normalized, p)


def test_evidence_note_must_disclose_predicted_sentiment_and_errors():
    p = packets()[0]
    out = fake_valid(p)
    out["evidence_note"] = "These insights are drawn from an analysis of reviewer sentiment."
    with pytest.raises(ValueError, match="evidence_note"):
        module.validate_output(out, p)


def test_repeatable_input_hash():
    assert [x["input_sha256"] for x in packets()] == [x["input_sha256"] for x in packets()]


def test_v1_draft_not_silently_skipped():
    p = packets()[0]
    old = {"laptop": p["laptop"], "input_sha256": p["input_sha256"],
           "prompt_version": "aspect-evidence-v1", "model": "gemini-3.8-flash"}
    assert not module.current_draft_matches(old, p, module.DEFAULT_MODEL)
    new = {**old, "prompt_version": p["prompt_version"], "model": module.DEFAULT_MODEL}
    assert module.current_draft_matches(new, p, module.DEFAULT_MODEL)


def test_archive_preserves_approved_old_drafts(tmp_path):
    packet = packets()[0]
    draft_dir = tmp_path / "drafts"
    draft_dir.mkdir()
    name = module.draft_name(packet["laptop"])
    old = {"laptop": packet["laptop"], "approved": True,
           "input_sha256": "old-hash", "prompt_version": "aspect-evidence-v1",
           "model": "gemini-3.8-flash"}
    module.write_json(draft_dir / name, old)
    count = module.archive_outdated_drafts([packet], draft_dir, module.DEFAULT_MODEL,
                                           tmp_path / "archive")
    assert count == 1
    assert not (draft_dir / name).exists()
    copies = list((tmp_path / "archive").rglob(name))
    assert len(copies) == 1
    assert json.loads(copies[0].read_text())["approved"] is True


def test_prepare_without_api_or_graph(tmp_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    args = SimpleNamespace(scores=DATA, output_dir=tmp_path, mode="prepare",
                           model=module.DEFAULT_MODEL, force=False, limit=None, delay=0)
    module.run(args)
    files = list((tmp_path / "inputs").glob("*.json"))
    assert len(files) == 30
    assert list((tmp_path / "drafts").glob("*.json")) == []


def test_no_model_api_invoked_for_matching_draft(tmp_path, monkeypatch):
    packet = packets()[0]
    path = tmp_path / "drafts" / module.draft_name(packet["laptop"])
    module.write_json(path, {
        "laptop": packet["laptop"],
        "input_sha256": packet["input_sha256"],
        "prompt_version": module.PROMPT_VERSION,
        "model": module.DEFAULT_MODEL,
        **fake_valid(packet)
    })
    assert module.current_draft_matches(json.loads(path.read_text()), packet, module.DEFAULT_MODEL)


def test_old_marketing_text_rejected():
    p = packets()[0]
    proposed = {
        "strength_aspect_ids": p["eligible_strength_aspect_ids"][:1],
        "weakness_aspect_ids": p["eligible_weakness_aspect_ids"][:1],
        "overall_summary": "An exceptional and perfect laptop with frequent complaints.",
    }
    out = module.normalize_generated(proposed, p)
    assert module.validate_output(out, p)
    assert "exceptional" not in out["overall_summary"]
    assert out["model_proposal"]["overall_summary"] == proposed["overall_summary"]


def test_zenbook_split_sentiment_remains_mixed():
    zenbook = next(x for x in packets() if x["laptop"].startswith("ASUS Zenbook A14"))
    aspects = {a["aspect_id"]: a for a in zenbook["aspects"]}
    assert aspects["AUDIO"]["positive_reviews"] == 6
    assert aspects["AUDIO"]["negative_reviews"] == 6
    assert aspects["AUDIO"]["sentiment_pattern"] == "mixed_or_divided"
    assert aspects["SOFTWARE_EXPERIENCE"]["sentiment_pattern"] == "mixed_or_divided"
    assert "AUDIO" in zenbook["eligible_weakness_aspect_ids"]
    assert "SOFTWARE_EXPERIENCE" in zenbook["eligible_weakness_aspect_ids"]


def test_invalid_gemini_response_saved_for_recovery(tmp_path, monkeypatch):
    packet = packets()[0]
    bad = fake_valid(packet)
    bad["strength_aspect_ids"] = ["FEATURE_SET"]  # rejected ID cannot be normalized
    monkeypatch.setenv("GEMINI_API_KEY", "fake-for-offline-test-only")
    monkeypatch.setattr(module, "invoke_gemini", lambda *_: bad)
    args = SimpleNamespace(scores=DATA, output_dir=tmp_path, mode="generate",
                           model=module.DEFAULT_MODEL, force=False, limit=1, delay=0)
    with pytest.raises(RuntimeError, match="Saved for manual correction"):
        module.run(args)
    rejected_path = tmp_path / "rejected" / module.draft_name(packet["laptop"])
    assert rejected_path.exists()
    assert not (tmp_path / "drafts" / rejected_path.name).exists()
    rejected = json.loads(rejected_path.read_text())
    assert rejected["approved"] is False
    rejected["model_proposal"]["strength_aspect_ids"] = fake_valid(packet)["strength_aspect_ids"]
    module.write_json(rejected_path, rejected)
    args.mode = "recover"
    module.run(args)
    draft_path = tmp_path / "drafts" / rejected_path.name
    assert draft_path.exists()
    assert json.loads(draft_path.read_text())["approved"] is False
    assert "validation_error" not in json.loads(draft_path.read_text())


def test_flow_z13_negative_fan_noise_not_mixed_in_any_published_field():
    packet = next(p for p in packets() if p["laptop"].startswith("ASUS ROG Flow Z13"))
    by_id = {a["aspect_id"]: a for a in packet["aspects"]}
    fan = by_id["FAN_NOISE"]
    assert fan["negative_reviews"] == 14
    assert fan["positive_reviews"] == 7
    assert fan["mentions"] == 23
    assert fan["sentiment_pattern"] == "negative_majority"
    bad_proposal = {
        "strength_aspect_ids": ["DESIGN", "PERFORMANCE", "TOUCHSCREEN_EXPERIENCE"],
        "weakness_aspect_ids": ["FAN_NOISE"],
        "overall_summary": "Design is praised, but fan noise is mixed.",
        "weaknesses_summary": "Review feedback on fan noise is mixed.",
    }
    out = module.normalize_generated(bad_proposal, packet)
    assert "negative review predictions" in out["weaknesses_summary"].lower()
    assert "fan noise" in out["overall_summary"].lower()
    assert "mixed" not in out["weaknesses_summary"].lower()
    assert "mixed" not in out["overall_summary"].lower()
    assert module.validate_output(out, packet)


def test_zenbook_a14_audio_software_are_divided_not_negative_majorities():
    packet = next(p for p in packets() if p["laptop"].startswith("ASUS Zenbook A14"))
    index = {a["aspect_id"]: a for a in packet["aspects"]}
    assert index["AUDIO"]["positive_reviews"] == index["AUDIO"]["negative_reviews"] == 6
    assert index["SOFTWARE_EXPERIENCE"]["positive_reviews"] == index["SOFTWARE_EXPERIENCE"]["negative_reviews"] == 11
    assert index["AUDIO"]["sentiment_pattern"] == "mixed_or_divided"
    assert index["SOFTWARE_EXPERIENCE"]["sentiment_pattern"] == "mixed_or_divided"
    normalized = module.normalize_generated({
        "strength_aspect_ids": ["BATTERY_LIFE", "DISPLAY_QUALITY", "PERFORMANCE"],
        "weakness_aspect_ids": ["AUDIO", "SOFTWARE_EXPERIENCE"],
        "weaknesses_summary": "Everyone hates audio quality and software experience.",
    }, packet)
    assert "divided" in normalized["weaknesses_summary"]
    assert "negative review predictions outnumber" not in normalized["weaknesses_summary"].lower()
    assert module.validate_output(normalized, packet)


def test_four_eligible_strengths_trimmed_locally_without_more_api_calls():
    p = next(p for p in packets() if len(p["eligible_strength_aspect_ids"]) >= 4)
    selected = p["eligible_strength_aspect_ids"][:4]
    out = module.normalize_generated({
        "strength_aspect_ids": selected,
        "weakness_aspect_ids": p["eligible_weakness_aspect_ids"][:1],
    }, p)
    assert out["strength_aspect_ids"] == selected[:3]
    assert out["model_proposal"]["strength_aspect_ids"] == selected
    assert out["normalization_warnings"]
    assert module.validate_output(out, p)


def test_ineligible_selection_never_silently_trimmed():
    p = packets()[0]
    with pytest.raises(ValueError, match="unsupported aspect"):
        module.normalize_generated({
            "strength_aspect_ids": p["eligible_strength_aspect_ids"][:1] + ["FEATURE_SET"],
            "weakness_aspect_ids": p["eligible_weakness_aspect_ids"][:1],
        }, p)


def test_all_three_by_three_choices_under_validation_limits():
    for p in packets():
        out = module.normalize_generated({
            "strength_aspect_ids": p["eligible_strength_aspect_ids"][:3],
            "weakness_aspect_ids": p["eligible_weakness_aspect_ids"][:3],
        }, p)
        assert module.validate_output(out, p)
        assert all(15 <= len(out[f]) <= 650 for f in (
            "overall_summary", "strengths_summary", "weaknesses_summary", "evidence_note"
        ))


def test_hand_edited_majority_description_rejected():
    p = next(p for p in packets() if p["laptop"].startswith("ASUS ROG Flow Z13"))
    out = module.normalize_generated({
        "strength_aspect_ids": ["DESIGN"],
        "weakness_aspect_ids": ["FAN_NOISE"],
    }, p)
    out["weaknesses_summary"] = "Review sentiment regarding fan noise is mixed."
    with pytest.raises(ValueError, match="Sentiment mismatch"):
        module.validate_output(out, p)


def test_majority_rule_boundary_and_no_evidence():
    example = {"positive_reviews": 1, "negative_reviews": 0, "neutral_reviews": 0,
               "mixed_reviews": 0, "mentions": 1}
    assert module.sentiment_pattern({**example, "mentions": 0}) == "no_evidence"
    assert module.sentiment_pattern({**example, "positive_reviews": 7,
                                    "negative_reviews": 14, "mentions": 23}) == "negative_majority"
    assert module.sentiment_pattern({**example, "positive_reviews": 6,
                                    "negative_reviews": 6, "mentions": 17}) == "mixed_or_divided"
    assert module.sentiment_pattern({**example, "positive_reviews": 12,
                                    "negative_reviews": 4, "mentions": 20}) == "positive_majority"


def test_neutral_dominated_feedback_is_inconclusive_not_divided():
    packet = next(p for p in packets() if p["laptop"].startswith("ASUS ROG Flow Z13"))
    example = {"mentions": 20, "positive_reviews": 2, "negative_reviews": 3,
               "neutral_reviews": 12, "mixed_reviews": 3}
    assert module.sentiment_pattern(example) == "neutral_or_inconclusive"
    a = next(x for x in packet["aspects"] if x["aspect_id"] == "CHARGING")
    # Controlled input to exercise the neutral-dominant wording while leaving
    # the score/eligibility rules unchanged.
    variant = {**packet, "aspects": [
        {**x, **example, "sentiment_pattern": "neutral_or_inconclusive"}
        if x["aspect_id"] == "CHARGING" else x for x in packet["aspects"]
    ]}
    assert a["aspect_id"] in packet["eligible_weakness_aspect_ids"]
    out = module.normalize_generated({
        "strength_aspect_ids": ["DESIGN"], "weakness_aspect_ids": ["CHARGING"]
    }, variant)
    assert "mostly neutral or mixed" in out["weaknesses_summary"].lower()
    assert "negative predictions outnumber" not in out["overall_summary"].lower()
    assert module.validate_output(out, variant)


def test_valid_natural_gemini_prose_preserved_where_grounded():
    p = next(p for p in packets() if p["laptop"].startswith("ASUS ROG Flow Z13"))
    proposed = {
        "strength_aspect_ids": ["DESIGN", "PERFORMANCE", "TOUCHSCREEN_EXPERIENCE"],
        "weakness_aspect_ids": ["FAN_NOISE"],
        "strengths_summary": (
            "Review sentiment is favourable for design, performance, "
            "and touchscreen experience."
        ),
        "weaknesses_summary": "Negative review predictions outnumber positive ones for fan noise.",
        "overall_summary": (
            "Predicted reviews are favourable for design, performance, and touchscreen experience, "
            "while more negative than positive for fan noise."
        ),
        "evidence_note": "Sentiment was automatically predicted from customer reviews and may contain errors.",
    }
    out = module.normalize_generated(proposed, p)
    for field in ("overall_summary", "strengths_summary", "weaknesses_summary", "evidence_note"):
        assert out[field] == proposed[field]
    assert out["normalization_warnings"] == []
    assert module.validate_output(out, p)


def test_offline_repairs_only_bad_fields_in_original_v2_example():
    p = next(p for p in packets() if p["laptop"].startswith("ASUS ROG Flow Z13"))
    proposed = {
        "strength_aspect_ids": ["DESIGN", "PERFORMANCE", "TOUCHSCREEN_EXPERIENCE"],
        "weakness_aspect_ids": ["FAN_NOISE"],
        "overall_summary": (
            "Review sentiment is favourable for design, performance, and touchscreen experience, "
            "whereas feedback regarding fan noise is mixed."
        ),
        "strengths_summary": (
            "Review sentiment is favourable for design, performance, and touchscreen experience."
        ),
        "weaknesses_summary": "Review sentiment for fan noise raises concerns and reflects a mixed sentiment pattern.",
        "evidence_note": "Sentiment was automatically predicted from customer reviews and predictions may contain errors.",
    }
    out = module.normalize_generated(proposed, p)
    assert out["strengths_summary"] == proposed["strengths_summary"]
    assert out["evidence_note"] == proposed["evidence_note"]
    assert "Negative review predictions outnumber" in out["weaknesses_summary"]
    assert "Negative predictions outnumber" in out["overall_summary"]
    assert len(out["normalization_warnings"]) == 2
    assert module.validate_output(out, p)
