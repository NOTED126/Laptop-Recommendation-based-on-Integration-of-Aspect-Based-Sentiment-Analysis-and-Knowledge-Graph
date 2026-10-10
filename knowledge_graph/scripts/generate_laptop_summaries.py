"""Create, generate (via Gemini), validate and review fixed laptop summaries.

This is an OFFLINE workflow, not called by FastAPI or the frontend.
The Gemini API key must be set locally as GEMINI_API_KEY; never commit it.

Examples from Program/:
    python knowledge_graph/scripts/generate_laptop_summaries.py --mode prepare
    python knowledge_graph/scripts/generate_laptop_summaries.py --mode generate --limit 1
    python knowledge_graph/scripts/generate_laptop_summaries.py --mode generate
    python knowledge_graph/scripts/generate_laptop_summaries.py --mode review

Gemini chooses evidence-eligible aspect themes and proposes prose. Python
validates each proposed sentence against deterministic sentiment patterns and
replaces unsupported wording locally. Original model proposals remain for audit.
"""
from __future__ import annotations

import argparse
import csv
import shutil
import hashlib
import json
import os
import re
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib import error, request

RETIRED_IDS = {"FEATURE_SET"}
PROMPT_VERSION = "aspect-evidence-v2.1"
SUPPORTED_LEVELS = {"strong", "moderate"}
STRENGTH_MIN = 75.0
WEAKNESS_MAX = 55.0
API_ROOT = "https://generativelanguage.googleapis.com/v1beta/models"
DEFAULT_MODEL = "gemini-3.5-flash-lite"
# Exact, model-facing terms make individual claims auditable by Python.
# Do not infer these nouns from review snippets or hardware specifications.
SUMMARY_TERMS = {
    "AI_FEATURES": "AI features",
    "AUDIO": "audio quality",
    "BATTERY_LIFE": "battery life",
    "BIOMETRIC_SECURITY": "biometric security",
    "BUILD_QUALITY": "build quality",
    "CAMERA_QUALITY": "camera quality",
    "CHARGING": "charging",
    "CONNECTIVITY_PORTS": "connectivity and ports",
    "DESIGN": "design",
    "DISPLAY_QUALITY": "display quality",
    "EASE_OF_USE": "ease of use",
    "FAN_NOISE": "fan noise",
    "GAMING_PERFORMANCE": "gaming performance",
    "KEYBOARD": "keyboard",
    "PERFORMANCE": "performance",
    "PORTABILITY": "portability",
    "RELIABILITY_STABILITY": "reliability and stability",
    "SOFTWARE_EXPERIENCE": "software experience",
    "THERMAL_PERFORMANCE": "thermal performance",
    "TOUCHSCREEN_EXPERIENCE": "touchscreen experience",
    "TRACKPAD": "trackpad",
    "UPGRADEABILITY": "upgradeability",
    "VALUE_FOR_MONEY": "value for money",
}

# These summaries are interpretations of predicted review labels, not measured
# laptop performance. Negative scores with split P/N/U/M evidence need care.
BANNED_CLAIMS = re.compile(
    r"\b(?:exceptional|outstanding|flawless|perfect|guaranteed|objectively|"
    r"proven|certified|vibrant|long[- ]lasting|reliable|unreliable|"
    r"best|worst|superior|inferior|benchmark(?:s|ed)?|"
    r"universally|consistently|unanimously|everyone|all users|"
    r"frequent complaints|widespread complaints|"
    r"preloaded|firmware|drivers|specific bugs|"
    r"gaming fps|frames per second)\b", re.IGNORECASE
)


def sentiment_pattern(a):
    """Count-based interpretation; adjusted scores govern eligibility separately.

    Conservative *descriptive* rule. Exactly 50% negative, provided N>P,
    qualifies as negative-majority (predominantly negative at >=50% of all
    predictions); otherwise unresolved distributions stay mixed/divided.
    """
    n = a["mentions"]
    if not n:
        return "no_evidence"
    positive, negative = a["positive_reviews"], a["negative_reviews"]
    if positive > negative and positive / n >= 0.60:
        return "positive_majority"
    if negative > positive and negative / n >= 0.50:
        return "negative_majority"
    if a["neutral_reviews"] + a["mixed_reviews"] > positive + negative:
        return "neutral_or_inconclusive"
    return "mixed_or_divided"


def join_terms(terms):
    """Readable grammatical conjunction for 1–3 exact audit terms."""
    if len(terms) == 1:
        return terms[0]
    if len(terms) == 2:
        return f"{terms[0]} and {terms[1]}"
    return ", ".join(terms[:-1]) + ", and " + terms[-1]


def render_evidence_grounded_text(packet, strength_ids, weakness_ids):
    """Python owns the polarity language, Gemini only picks eligible themes.

    This prevents the old failure mode: Fan Noise (N=14, P=7, n=23) must not
    be described as 'mixed' merely because the score is evidence-adjusted.
    Templates deliberately avoid product attributes, causal assumptions, and
    claims about true laptop quality. No extra Gemini calls are involved.
    """
    by_id = {a["aspect_id"]: a for a in packet["aspects"]}
    s_groups, w_groups = defaultdict(list), defaultdict(list)
    for aid in strength_ids:
        a = by_id[aid]
        s_groups[a["sentiment_pattern"]].append(a["summary_term"])
    for aid in weakness_ids:
        a = by_id[aid]
        w_groups[a["sentiment_pattern"]].append(a["summary_term"])

    strengths = []
    if s_groups["positive_majority"]:
        strengths.append(
            "Predicted customer-review sentiment is predominantly positive for "
            + join_terms(s_groups["positive_majority"]) + "."
        )
    if s_groups["mixed_or_divided"]:
        strengths.append(
            "Adjusted sentiment scores are favourable for "
            + join_terms(s_groups["mixed_or_divided"])
            + ", although predicted review opinions are divided."
        )
    if s_groups["neutral_or_inconclusive"]:
        strengths.append(
            "Adjusted sentiment scores are favourable for "
            + join_terms(s_groups["neutral_or_inconclusive"])
            + ", but neutral or mixed predictions dominate the available reviews."
        )
    if s_groups["negative_majority"]:
        strengths.append(
            "Despite favourable adjusted scores for "
            + join_terms(s_groups["negative_majority"])
            + ", negative review predictions outnumber positive ones."
        )
    if not strengths:
        strengths = ["Available review evidence does not establish a sufficiently supported strength."]

    weaknesses = []
    if w_groups["negative_majority"]:
        weaknesses.append(
            "Negative review predictions outnumber positive predictions for "
            + join_terms(w_groups["negative_majority"]) + "."
        )
    if w_groups["mixed_or_divided"]:
        weaknesses.append(
            "Feedback on " + join_terms(w_groups["mixed_or_divided"])
            + " is divided; the lower adjusted sentiment scores should be interpreted cautiously."
        )
    if w_groups["neutral_or_inconclusive"]:
        weaknesses.append(
            "Reviews of " + join_terms(w_groups["neutral_or_inconclusive"])
            + " contain mostly neutral or mixed predictions; the adjusted scores should be interpreted cautiously."
        )
    if w_groups["positive_majority"]:
        weaknesses.append(
            "Despite relatively low adjusted scores for "
            + join_terms(w_groups["positive_majority"])
            + ", positive review predictions predominate, so a negative consensus is not established."
        )
    if not weaknesses:
        weaknesses = ["Available review evidence does not establish a sufficiently supported weakness."]

    # A concise overview uses the same Python-computed categories but avoids
    # repeating the complete strengths/weaknesses paragraphs verbatim.
    intro, concerns = [], []
    if s_groups["positive_majority"]:
        intro.append("Customer reviews show predominantly positive sentiment for "
                     + join_terms(s_groups["positive_majority"]))
    if s_groups["mixed_or_divided"]:
        intro.append("favourable adjusted scores for "
                     + join_terms(s_groups["mixed_or_divided"])
                     + " coincide with divided review opinions")
    if s_groups["neutral_or_inconclusive"]:
        intro.append("adjusted sentiment scores favour "
                     + join_terms(s_groups["neutral_or_inconclusive"])
                     + " but neutral and mixed review labels predominate")
    if s_groups["negative_majority"]:
        intro.append("negative predictions outweigh positive ones for "
                     + join_terms(s_groups["negative_majority"])
                     + " despite favourable adjusted scores")
    if w_groups["negative_majority"]:
        concerns.append("negative predictions outnumber positive ones for "
                        + join_terms(w_groups["negative_majority"]))
    if w_groups["mixed_or_divided"]:
        concerns.append("feedback on " + join_terms(w_groups["mixed_or_divided"])
                        + " remains divided despite lower adjusted scores")
    if w_groups["neutral_or_inconclusive"]:
        concerns.append("feedback on " + join_terms(w_groups["neutral_or_inconclusive"])
                        + " is mainly neutral or mixed despite lower adjusted scores")
    if w_groups["positive_majority"]:
        concerns.append("review labels are more positive than negative for "
                        + join_terms(w_groups["positive_majority"])
                        + " despite lower adjusted scores")
    if intro and concerns:
        overview = "; ".join(intro).capitalize() + ". " + "; ".join(concerns).capitalize() + "."
    elif intro:
        overview = "; ".join(intro).capitalize() + "."
    elif concerns:
        overview = "; ".join(concerns).capitalize() + "."
    else:
        overview = (
            "Available customer reviews do not establish sufficiently supported "
            "strengths or weaknesses under the evidence rules."
        )
    # Capitalize() would lower-case ID terms if added in the future. We use
    # plain English summary_terms, so lower-case is intentional.
    overall = overview
    note = (
        "Sentiment was automatically predicted from customer reviews; "
        "these predictions may contain errors and do not measure hardware quality."
    )
    return {
        "overall_summary": overall,
        "strengths_summary": " ".join(strengths),
        "weaknesses_summary": " ".join(weaknesses),
        "evidence_note": note,
    }


def normalize_generated(generated, packet):
    """Keep supported Gemini prose; repair ungrounded wording without API calls.

    The AI selects aspect IDs and proposes prose. Python assigns each selected
    aspect a count-based sentiment pattern and checks the text. Invalid claims
    receive a conservative deterministic substitute, recorded for human review.
    Raw proposed text remains under model_proposal for transparency.
    """
    if not isinstance(generated, dict):
        raise ValueError("Gemini output must be a JSON object")
    chosen = {}
    actions = []
    for field, whitelist in (
        ("strength_aspect_ids", packet["eligible_strength_aspect_ids"]),
        ("weakness_aspect_ids", packet["eligible_weakness_aspect_ids"]),
    ):
        items = generated.get(field)
        if not isinstance(items, list) or not all(isinstance(x, str) for x in items):
            raise ValueError(f"Invalid list: {field}")
        if len(items) != len(set(items)):
            raise ValueError(f"Duplicate aspect IDs in {field}")
        if not set(items).issubset(whitelist):
            raise ValueError(f"Output contains unsupported aspect IDs in {field}: {items}")
        if bool(items) != bool(whitelist):
            raise ValueError(f"Missing selected aspect IDs in {field}: eligible aspects exist")
        if len(items) > 3:
            actions.append(f"{field}: {len(items)} eligible IDs trimmed to first 3")
        chosen[field] = items[:3]

    fallback = render_evidence_grounded_text(
        packet, chosen["strength_aspect_ids"], chosen["weakness_aspect_ids"]
    )
    result = {**fallback, **chosen}
    # Validate one candidate field at a time, with the others still grounded.
    # Importer sees ONLY the safe resulting four prose fields, not proposals.
    for field in ("strengths_summary", "weaknesses_summary", "overall_summary", "evidence_note"):
        candidate = generated.get(field)
        result[field] = candidate
        try:
            validate_output(result, packet)
        except ValueError as exc:
            result[field] = fallback[field]
            actions.append(f"{field}: replaced proposed wording ({exc})")
        validate_output(result, packet)
    return {
        **result,
        "generation_method": "gemini_draft_python_count_grounded_validation",
        "model_proposal": {name: generated.get(name) for name in (
            "overall_summary", "strengths_summary", "weaknesses_summary", "evidence_note",
            "strength_aspect_ids", "weakness_aspect_ids")},
        "normalization_warnings": actions,
    }


def aspect_terms_in(text, packet):
    """Identify exact audited summary terms, longest first (gaming vs performance)."""
    found = set()
    remaining = text.lower()
    for aspect in sorted(packet["aspects"], key=lambda x: -len(x["summary_term"])):
        phrase = aspect["summary_term"].lower()
        pat = r"(?<!\w)" + re.escape(phrase) + r"(?!\w)"
        if re.search(pat, remaining):
            found.add(aspect["aspect_id"])
            remaining = re.sub(pat, " ", remaining)
    return found

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REQUIRED_CSV_COLUMNS = {
    "laptop", "canonical_aspect", "canonical_label", "positive_reviews",
    "negative_reviews", "neutral_reviews", "mixed_reviews",
    "reviews_mentioning_aspect", "adjusted_score_0_100", "evidence_level",
    "evidence_confidence_0_100",
}
OUTPUT_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "overall_summary": {"type": "STRING"},
        "strengths_summary": {"type": "STRING"},
        "weaknesses_summary": {"type": "STRING"},
        "evidence_note": {"type": "STRING"},
        "strength_aspect_ids": {"type": "ARRAY", "items": {"type": "STRING"}},
        "weakness_aspect_ids": {"type": "ARRAY", "items": {"type": "STRING"}},
    },
    "required": [
        "overall_summary", "strengths_summary", "weaknesses_summary",
        "evidence_note", "strength_aspect_ids", "weakness_aspect_ids"
    ],
}


def canonical_json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def draft_name(laptop):
    return hashlib.sha256(laptop.encode("utf-8")).hexdigest()[:18] + ".json"


def read_and_prepare(csv_path):
    with csv_path.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        missing = REQUIRED_CSV_COLUMNS - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Missing scoring CSV columns: {sorted(missing)}")
        rows = list(reader)
    groups = defaultdict(list)
    for row in rows:
        groups[row["laptop"]].append(row)
    aspect_ids = {r["canonical_aspect"] for r in rows} - RETIRED_IDS
    if len(groups) != 30 or len(aspect_ids) != 23 or len(rows) != 720:
        raise ValueError(
            f"Expected 30 laptops × 24 stored aspects, 23 selectable: "
            f"found {len(groups)} laptops, {len(rows)} rows, {len(aspect_ids)} selectable aspects"
        )
    packets = []
    for laptop in sorted(groups):
        group = groups[laptop]
        if len(group) != 24 or len({r["canonical_aspect"] for r in group}) != 24:
            raise ValueError(f"Expected 24 unique aspect rows for {laptop!r}")
        aspects = []
        for r in group:
            if r["canonical_aspect"] in RETIRED_IDS:
                continue
            counts = {key: int(r[key]) for key in (
                "positive_reviews", "negative_reviews", "neutral_reviews", "mixed_reviews"
            )}
            n = int(r["reviews_mentioning_aspect"])
            if sum(counts.values()) != n:
                raise ValueError(f"Count inconsistency: {laptop}, {r['canonical_aspect']}")
            aspect = {
                "aspect_id": r["canonical_aspect"],
                "aspect_name": r["canonical_label"],
                "adjusted_score_0_100": round(float(r["adjusted_score_0_100"]), 3) if n else None,
                "mentions": n,
                "evidence_level": r["evidence_level"].lower(),
                "evidence_support_0_100": round(float(r["evidence_confidence_0_100"]), 3),
                "summary_term": SUMMARY_TERMS[r["canonical_aspect"]],
                **counts,
            }
            aspect["sentiment_pattern"] = sentiment_pattern(aspect)
            aspects.append(aspect)
        aspects.sort(key=lambda a: a["aspect_id"])
        if len(aspects) != 23 or set(SUMMARY_TERMS) != {a["aspect_id"] for a in aspects}:
            raise ValueError("Summary term dictionary must cover the 23 selectable aspects")
        strengths = [a for a in aspects if a["evidence_level"] in SUPPORTED_LEVELS
                     and a["mentions"] >= 10 and a["adjusted_score_0_100"] >= STRENGTH_MIN]
        weaknesses = [a for a in aspects if a["evidence_level"] in SUPPORTED_LEVELS
                      and a["mentions"] >= 10 and a["adjusted_score_0_100"] <= WEAKNESS_MAX]
        strengths.sort(key=lambda a: -a["adjusted_score_0_100"])
        weaknesses.sort(key=lambda a: a["adjusted_score_0_100"])
        core = {
            "laptop": laptop,
            "aspects": aspects,
            "eligible_strength_aspect_ids": [a["aspect_id"] for a in strengths],
            "eligible_weakness_aspect_ids": [a["aspect_id"] for a in weaknesses],
            "policy": {
                "retired_aspects": sorted(RETIRED_IDS),
                "min_mentions_for_claims": 10,
                "permitted_evidence_levels": sorted(SUPPORTED_LEVELS),
                "strength_score_min": STRENGTH_MIN,
                "weakness_score_max": WEAKNESS_MAX,
                "zero_mention_scores_are_hidden": True,
                "sentiment_pattern_rule": (
                    "positive_majority: P>N and P/n>=0.60; negative_majority: "
                    "N>P and N/n>=0.50; neutral_or_inconclusive when "
                    "(U+M)>(P+N); otherwise mixed_or_divided"
                ),
                "sentiment_rendering": "deterministic_python_v2.1",
            },
            "prompt_version": PROMPT_VERSION,
        }
        core["input_sha256"] = hashlib.sha256(canonical_json(core).encode("utf-8")).hexdigest()
        packets.append(core)
    return packets


def prompt_for(packet):
    eligible = {a["aspect_id"] for a in packet["aspects"]}
    if not set(SUMMARY_TERMS) == eligible:
        raise ValueError("Incomplete 23-aspect summary term mapping")
    return (
        "TASK: Help prepare a concise, review-derived summary from the supplied "
        "aggregate ABSA prediction counts ONLY. No external product knowledge. "
        "The prior-adjusted sentiment score is NOT measured laptop quality. "
        "Never infer specifications, benchmarks, causes, defects, or durability.\n"
        "SELECTION: Select 1–3 IDs from eligible_strength_aspect_ids when nonempty "
        "and 1–3 from eligible_weakness_aspect_ids when nonempty; otherwise [] for "
        "the empty category. Return EXACT IDs and never include an ineligible ID. "
        "Prefer high mention counts, strong evidence, and clear sentiment trends. "
        "Write naturally phrased summary sentences grounded in each chosen ID. "
        "Python independently checks the text against count-based sentiment "
        "patterns, replacing incorrect or unsupported wording when needed.\n"
        "POLARITY: For negative_majority (N > P and N / mentions >= 0.50), "
        "negative predictions outnumber positive; do NOT call it simply mixed. "
        "For mixed_or_divided the negative-majority conclusion is unsupported. "
        "For neutral_or_inconclusive, neutral and mixed predictions outnumber "
        "positive and negative combined. "
        "For positive_majority (P > N and P / mentions >= 0.60), positive "
        "predictions predominate. Treat all as predictions.\n"
        "OUTPUT: JSON matching the schema, with one or two brief sentences in "
        "each text field and no figures, promotional language, or Markdown. "
        "evidence_note must mention that review sentiment is automatically "
        "predicted and may contain errors.\n\n"
        "EVIDENCE PACKET:\n" + canonical_json(packet)
    )


def invoke_gemini(packet, api_key, model, timeout_seconds=90):
    if not re.fullmatch(r"[A-Za-z0-9._-]+", model):
        raise ValueError("Invalid Gemini model name")
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt_for(packet)}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": OUTPUT_SCHEMA,
            "temperature": 0.15,
            "maxOutputTokens": 1600,
        },
    }
    req = request.Request(
        f"{API_ROOT}/{model}:generateContent",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=timeout_seconds) as response:
            response_data = json.load(response)
    except error.HTTPError as exc:
        try:
            error_data = json.loads(
                exc.read().decode("utf-8", errors="replace")
            )
            error_message = error_data.get("error", {}).get(
                "message", "Unknown API error"
            )
        except (json.JSONDecodeError, UnicodeDecodeError):
            error_message = "Unable to parse Gemini API error response."

        raise RuntimeError(
            f"Gemini API returned HTTP {exc.code}: {error_message}"
        ) from None
    except error.URLError as exc:
        raise RuntimeError(f"Gemini API connection failed: {exc.reason}") from None
    parts = response_data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
    response_text = "".join(p.get("text", "") for p in parts)
    if not response_text:
        raise RuntimeError("Gemini returned no text (possibly blocked or truncated).")
    try:
        return json.loads(response_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Gemini returned malformed JSON: {exc}") from None


# Keep these cues precise. The fallback renderer uses the first phrase of each
# category verbatim; Gemini can use natural equivalents when equally grounded.
POSITIVE_LANGUAGE = re.compile(
    r"\b(?:predominantly positive|mostly positive|largely positive|positive majority|"
    r"favourable|favorable|positive sentiment|positive feedback|"
    r"positive review predictions|positive predictions predominate|praised|praise)\b", re.I
)
NEGATIVE_LANGUAGE = re.compile(
    r"\b(?:negative (?:review )?predictions? outnumber|negative (?:review )?"
    r"sentiment(?:s)? (?:outweighs?|predominates?)|"
    r"more negative than positive|predominantly negative|mostly negative|"
    r"negative majority|negative (?:predictions?|feedback) outweigh)\b", re.I
)
MIXED_LANGUAGE = re.compile(r"\b(?:mixed|divided|split|varied)\b", re.I)
NEUTRAL_LANGUAGE = re.compile(r"\b(?:neutral|inconclusive)\b", re.I)
NEGATIVE_CONSENSUS_LANGUAGE = re.compile(
    r"\b(?:dissatisfaction|dissatisfied|poor|terrible|bad|"
    r"hate|hated|widely criticised|widely criticized|negative consensus)\b", re.I
)


def split_claim_clauses(text):
    # Separate contrastive clauses to attach sentiment words to the right ID.
    return [p.strip() for p in re.split(
        r"(?<=[.!?;])\s+|;\s*|\s*,?\s+(?:while|whereas|however|but)\s+",
        text, flags=re.I
    ) if p.strip()]


def check_sentiment_wording(text, packet, selected_ids, field):
    by_id = {a["aspect_id"]: a for a in packet["aspects"]}
    # In the overview, generic text without aspect names is permitted; any
    # named aspect is checked against its own observed category.
    for aid in selected_ids:
        aspect = by_id[aid]
        related = [cl for cl in split_claim_clauses(text)
                   if aid in aspect_terms_in(cl, packet)]
        if not related:
            continue  # Presence is enforced elsewhere for strengths/weaknesses.
        pattern = aspect["sentiment_pattern"]
        for clause in related:
            if pattern == "positive_majority":
                valid = bool(POSITIVE_LANGUAGE.search(clause))
                # An unsupported 'mixed' label must not replace a clear majority.
                valid = valid and not bool(MIXED_LANGUAGE.search(clause))
            elif pattern == "negative_majority":
                valid = bool(NEGATIVE_LANGUAGE.search(clause))
                valid = valid and not bool(MIXED_LANGUAGE.search(clause))
            elif pattern == "mixed_or_divided":
                valid = bool(MIXED_LANGUAGE.search(clause))
                valid = valid and not bool(NEGATIVE_LANGUAGE.search(clause))
                valid = valid and not bool(NEGATIVE_CONSENSUS_LANGUAGE.search(clause))
            elif pattern == "neutral_or_inconclusive":
                valid = bool(NEUTRAL_LANGUAGE.search(clause))
                valid = valid and not bool(NEGATIVE_LANGUAGE.search(clause))
                valid = valid and not bool(NEGATIVE_CONSENSUS_LANGUAGE.search(clause))
            else:
                valid = False  # no-evidence can never be a selected aspect
            if not valid:
                raise ValueError(
                    f"Sentiment mismatch for {aid} ({pattern}) in {field}; "
                    f"clause={clause!r}"
                )


def validate_output(generated, packet):
    """Conservative machine checks; human review remains mandatory for semantics."""
    if not isinstance(generated, dict):
        raise ValueError("Gemini output must be a JSON object")
    text_fields = (
        "overall_summary", "strengths_summary", "weaknesses_summary", "evidence_note"
    )
    for field in text_fields:
        value = generated.get(field)
        if not isinstance(value, str) or not (15 <= len(value.strip()) <= 650):
            raise ValueError(f"Missing or unusually sized text field: {field}")
        if re.search(r"\d", value):
            raise ValueError(f"Unapproved numerical assertion in {field} (no numbers allowed)")
        if BANNED_CLAIMS.search(value):
            raise ValueError(f"Unsupported or overconfident wording in {field}")
        if re.search(r"(?:https?://|<[^>]+>|\*\*|```)", value):
            raise ValueError(f"Unsupported markup or URL in {field}")

    aspect_index = {a["aspect_id"]: a for a in packet["aspects"]}
    for field, whitelist in (
        ("strength_aspect_ids", packet["eligible_strength_aspect_ids"]),
        ("weakness_aspect_ids", packet["eligible_weakness_aspect_ids"]),
    ):
        values = generated.get(field)
        if (not isinstance(values, list) or len(values) > 3 or
                not all(isinstance(v, str) for v in values) or
                len(set(values)) != len(values)):
            raise ValueError(f"Invalid list: {field}")
        if not set(values) <= set(whitelist):
            raise ValueError(f"Output contains unsupported aspect IDs in {field}: {values}")
        if bool(whitelist) != bool(values):
            raise ValueError(f"Missing selected aspect IDs in {field}: eligible aspects exist")

    chosen_strengths = set(generated["strength_aspect_ids"])
    chosen_weaknesses = set(generated["weakness_aspect_ids"])
    chosen = chosen_strengths | chosen_weaknesses
    for field, expected in (
        ("strengths_summary", chosen_strengths),
        ("weaknesses_summary", chosen_weaknesses),
    ):
        mentioned = aspect_terms_in(generated[field], packet)
        if mentioned != expected:
            missing = sorted(expected - mentioned)
            extra = sorted(mentioned - expected)
            raise ValueError(
                f"Aspect term mismatch in {field}; missing={missing}, unsupported={extra}. "
                "Use each chosen aspect's exact summary_term."
            )
    # The overview can omit names, but any names it includes must be chosen.
    for field in ("overall_summary", "evidence_note"):
        extra = aspect_terms_in(generated[field], packet) - chosen
        if extra:
            raise ValueError(f"Unselected aspect claim in {field}: {sorted(extra)}")

    # Each aspect's claimed sentiment must agree with Python's counted labels.
    # This is scoped per aspect and per clause; a single global 'mixed' word
    # cannot make a negative-majority fan-noise description valid.
    for field, IDs in (
        ("strengths_summary", chosen_strengths),
        ("weaknesses_summary", chosen_weaknesses),
        ("overall_summary", chosen),
    ):
        check_sentiment_wording(generated[field], packet, IDs, field)

    note = generated["evidence_note"]
    if not (re.search(r"(?i)\b(predicted|predictions?|automatically|automated|model[- ]generated)\b", note)
            and re.search(r"(?i)\b(may|can|possible|uncertain|errors?|inaccurac(?:y|ies))\b", note)
            and re.search(r"(?i)\breviews?\b", note)):
        raise ValueError("evidence_note must mention predicted review sentiment and possible errors")

    return True


def current_draft_matches(data, packet, model):
    return (
        data.get("laptop") == packet["laptop"]
        and data.get("input_sha256") == packet["input_sha256"]
        and data.get("prompt_version") == PROMPT_VERSION
        and data.get("model") == model
    )


def archive_outdated_drafts(packets, draft_dir, model, archive_root):
    """Explicit non-destructive migration from older prompt/model drafts."""
    packet_by_name = {p["laptop"]: p for p in packets}
    if not draft_dir.exists():
        print("No drafts directory yet; nothing to archive.")
        return 0
    to_move = []
    for path in sorted(draft_dir.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        packet = packet_by_name.get(data.get("laptop"))
        if packet is None or not current_draft_matches(data, packet, model):
            to_move.append(path)
    if not to_move:
        print("No outdated or different-model drafts need archiving.")
        return 0
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = archive_root / (stamp + "_before_" + PROMPT_VERSION)
    suffix = 1
    while target.exists():
        target = archive_root / (stamp + "_" + str(suffix) + "_before_" + PROMPT_VERSION)
        suffix += 1
    target.mkdir(parents=True)
    for source in to_move:
        shutil.move(str(source), str(target / source.name))
    print(f"Archived {len(to_move)} drafts, including approvals, at: {target}")
    print("All archived files remain recoverable; no summary was deleted or imported.")
    return len(to_move)


def run(args):
    packets = read_and_prepare(args.scores)
    input_dir = args.output_dir / "inputs"
    draft_dir = args.output_dir / "drafts"
    for p in packets:
        input_path = input_dir / draft_name(p["laptop"])
        if input_path.exists():
            previous = json.loads(input_path.read_text(encoding="utf-8"))
            if previous.get("input_sha256") != p["input_sha256"]:
                # Preserve v1 evidence packets before writing the revised packets.
                target = args.output_dir / "archive" / "prior_inputs" / previous.get(
                    "input_sha256", "unknown"
                ) / input_path.name
                if not target.exists():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(input_path, target)
        write_json(input_path, p)
    print(f"Prepared {len(packets)} evidence packets ({args.scores}).")

    if args.mode == "prepare":
        return
    if args.mode == "archive":
        archive_outdated_drafts(
            packets, draft_dir, args.model, args.output_dir / "archive"
        )
        return
    if args.mode == "recover":
        recovered = 0
        for p in packets:
            rejected_path = args.output_dir / "rejected" / draft_name(p["laptop"])
            draft_path = draft_dir / draft_name(p["laptop"])
            if not rejected_path.exists():
                continue
            if draft_path.exists():
                print(f"Skipping rejected candidate; draft already exists: {p['laptop']}")
                continue
            draft = json.loads(rejected_path.read_text(encoding="utf-8"))
            if not current_draft_matches(draft, p, args.model):
                raise RuntimeError(f"Rejected candidate is stale or uses another model: {p['laptop']}")
            # For rejected output, edit the model_proposal ID arrays, then
            # normalize locally without consuming another request.
            source = draft.get("model_proposal", draft)
            draft.update(normalize_generated(source, p))
            validate_output(draft, p)
            draft.pop("validation_error", None)
            draft["approved"] = False
            draft["reviewed_at"] = None
            write_json(draft_path, draft)
            recovered += 1
            print(f"Recovered corrected draft: {p['laptop']}")
        print(f"Recovered {recovered} manually corrected drafts; review before approval.")
        return
    if args.mode == "generate":
        key = os.environ.get("GEMINI_API_KEY", "").strip()
        if not key:
            raise RuntimeError("GEMINI_API_KEY is not set. Set it privately in your PowerShell session.")
        generated_count = 0
        for p in packets:
            path = draft_dir / draft_name(p["laptop"])
            if path.exists() and not args.force:
                current = json.loads(path.read_text(encoding="utf-8"))
                if current_draft_matches(current, p, args.model):
                    print(f"Skipping existing draft: {p['laptop']}")
                    continue
                raise RuntimeError(
                    f"Existing draft uses old evidence/prompt or a different model: {p['laptop']}. "
                    "Run --mode archive (makes a backup) before regenerating."
                )
            if args.limit and generated_count >= args.limit:
                break
            print(f"Generating draft for: {p['laptop']}", flush=True)
            # On invalid model output, fail rather than store an unsupported claim.
            for attempt in range(3):
                try:
                    generated = invoke_gemini(p, key, args.model)
                    break
                except RuntimeError as exc:
                    # Retry transient congestion, never burn requests against
                    # a daily quota error or a permanent model/configuration error.
                    if "HTTP 503" not in str(exc) or attempt == 2:
                        raise
                    wait = 4 * (attempt + 1)
                    print(f"  Gemini busy (503); retrying in {wait}s...", flush=True)
                    time.sleep(wait)
            draft = {
                "laptop": p["laptop"],
                "input_sha256": p["input_sha256"],
                "prompt_version": PROMPT_VERSION,
                "model": args.model,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "approved": False,
                "reviewed_at": None,
            }
            try:
                draft.update(normalize_generated(generated, p))
                validate_output(draft, p)
            except ValueError as exc:
                # Preserve the quota-consuming response for offline fixes;
                # DO NOT mark it approved or put it in importable drafts.
                # Keep model_proposal even when normalization fails.
                draft.setdefault("model_proposal", generated)
                draft["validation_error"] = str(exc)
                rejected_path = args.output_dir / "rejected" / draft_name(p["laptop"])
                write_json(rejected_path, draft)
                raise RuntimeError(
                    f"Gemini output did not pass evidence validation: {exc}. "
                    f"Saved for manual correction at {rejected_path}; "
                    "run --mode recover after editing it to pass validation."
                ) from None
            if path.exists():
                # Even --force never silently destroys an approved or prior draft.
                stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
                backup_dir = args.output_dir / "archive" / ("forced_" + stamp)
                backup_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, backup_dir / path.name)
                print(f"  Backed up replaced draft to {backup_dir}")
            write_json(path, draft)
            generated_count += 1
            print(f"  Saved draft ({generated_count} generated this run).")
            if args.delay > 0:
                time.sleep(args.delay)
        print(f"Generation completed: {generated_count} NEW drafts; not yet imported.")
        return
    if args.mode == "review":
        approved_now = 0
        for p in packets:
            path = draft_dir / draft_name(p["laptop"])
            if not path.exists():
                print(f"MISSING draft: {p['laptop']}")
                continue
            draft = json.loads(path.read_text(encoding="utf-8"))
            if not current_draft_matches(draft, p, args.model):
                raise RuntimeError(
                    f"Old prompt, model, or evidence in draft: {p['laptop']}. "
                    "Run --mode archive for the selected model before regenerating."
                )
            validate_output(draft, p)
            if draft.get("approved"):
                continue
            print("\n" + "=" * 68)
            print(p["laptop"])
            print("Eligible strengths:", ", ".join(p["eligible_strength_aspect_ids"]) or "none")
            print("Eligible weaknesses:", ", ".join(p["eligible_weakness_aspect_ids"]) or "none")
            for f in ("overall_summary", "strengths_summary", "weaknesses_summary", "evidence_note"):
                print(f"{f}: {draft[f]}")
            if draft.get("normalization_warnings"):
                print("Python grounding adjustments (check carefully):")
                for action in draft["normalization_warnings"]:
                    print("  -", action)
            by_id = {a["aspect_id"]: a for a in p["aspects"]}
            for label, field in (("Selected strengths", "strength_aspect_ids"),
                                 ("Selected weaknesses", "weakness_aspect_ids")):
                print(label + ":")
                for aspect_id in draft[field]:
                    a = by_id[aspect_id]
                    print(f"  {aspect_id}: score={a['adjusted_score_0_100']}, "
                          f"n={a['mentions']}, P={a['positive_reviews']}, "
                          f"N={a['negative_reviews']}, U={a['neutral_reviews']}, "
                          f"M={a['mixed_reviews']}; {a['sentiment_pattern']}")
            choice = input("Approve this fixed summary? [y]es/[n]ot yet/[q]uit: ").strip().lower()
            if choice in {"q", "quit"}:
                break
            if choice in {"y", "yes"}:
                draft["approved"] = True
                draft["reviewed_at"] = datetime.now(timezone.utc).isoformat()
                write_json(path, draft)
                approved_now += 1
        print(f"Approved {approved_now} additional summaries. Review all 30 before import.")


def cli():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("prepare", "archive", "generate", "recover", "review"), default="prepare")
    parser.add_argument("--scores", type=Path, default=PROJECT_ROOT / "recommendation_scores/laptop_aspect_scores.csv")
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "knowledge_graph/generated_summaries")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--limit", type=int, default=None, help="Limit NEW Gemini API requests, e.g. --limit 1")
    parser.add_argument("--delay", type=float, default=5.0, help="Seconds between requests; default 5 (helps respect RPM quotas)")
    parser.add_argument("--force", action="store_true", help="Regenerate and BACK UP existing draft; approval resets")
    args = parser.parse_args()
    if args.delay < 0 or (args.limit is not None and args.limit < 1):
        parser.error("--delay must be >= 0 and --limit >= 1")
    run(args)


if __name__ == "__main__":
    cli()
