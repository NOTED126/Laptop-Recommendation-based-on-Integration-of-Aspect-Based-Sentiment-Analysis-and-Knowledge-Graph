"""
Laptop aspect ontology (version 3) for the thesis recommendation system.

Purpose
-------
The ATE model produces open-ended surface forms such as:
    "battery", "battery life", "screen", "display", "fan noise", ...

This module converts those surface forms into a controlled laptop ontology while
remaining conservative:

1. Known laptop-experience terms are mapped to canonical user-experience aspects.
2. Hardware/specification terms are mapped separately so they can be retained for
   analysis without being mixed into review-experience rankings.
3. Clearly irrelevant/generic/noisy extractions are rejected.
4. Unknown terms remain UNMAPPED instead of being guessed.

Version 3 refines the ontology using the complete Best Buy corpus after the
full ATE+ABSA inference run. It targets recurring high-confidence variants found
across the 30-laptop corpus, adds upgradeability and NPU hardware concepts, and
keeps context-sensitive or rare long-tail terms conservative.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from typing import Dict, Iterable, Optional, Tuple


# -----------------------------------------------------------------------------
# Canonical aspect metadata
# -----------------------------------------------------------------------------
CANONICAL_ASPECTS: Dict[str, Dict[str, str]] = {
    # User-experience aspects used for recommendation/reranking.
    "PERFORMANCE": {
        "type": "experience",
        "label": "Performance",
        "description": "General speed, responsiveness, multitasking and workload performance.",
    },
    "GAMING_PERFORMANCE": {
        "type": "experience",
        "label": "Gaming Performance",
        "description": "User experience when running games, including smoothness and gaming capability.",
    },
    "BATTERY_LIFE": {
        "type": "experience",
        "label": "Battery Life",
        "description": "Runtime, battery endurance and battery longevity reported by users.",
    },
    "CHARGING": {
        "type": "experience",
        "label": "Charging",
        "description": "Charging speed, charging convenience and charger-related experience.",
    },
    "DISPLAY_QUALITY": {
        "type": "experience",
        "label": "Display Quality",
        "description": "Screen/display quality including clarity, resolution, brightness and visual experience.",
    },
    "TOUCHSCREEN_EXPERIENCE": {
        "type": "experience",
        "label": "Touchscreen Experience",
        "description": "Responsiveness and usability of the touchscreen function.",
    },
    "THERMAL_PERFORMANCE": {
        "type": "experience",
        "label": "Thermal Performance",
        "description": "Heat, temperatures, thermals and the laptop's ability to stay cool.",
    },
    "FAN_NOISE": {
        "type": "experience",
        "label": "Fan Noise",
        "description": "Fan loudness, acoustic behaviour and fan-noise experience.",
    },
    "KEYBOARD": {
        "type": "experience",
        "label": "Keyboard",
        "description": "Typing experience, key feel, keypad and keyboard lighting.",
    },
    "TRACKPAD": {
        "type": "experience",
        "label": "Trackpad",
        "description": "Trackpad/touchpad usability and click/gesture experience.",
    },
    "AUDIO": {
        "type": "experience",
        "label": "Audio",
        "description": "Speaker and audio quality.",
    },
    "BUILD_QUALITY": {
        "type": "experience",
        "label": "Build Quality",
        "description": "Physical robustness, rigidity, hinges and construction quality.",
    },
    "DESIGN": {
        "type": "experience",
        "label": "Design / Form Factor",
        "description": "Physical design, 2-in-1 form factor, appearance and versatility.",
    },
    "PORTABILITY": {
        "type": "experience",
        "label": "Portability",
        "description": "Ease of carrying, compactness, weight and travel suitability.",
    },
    "VALUE_FOR_MONEY": {
        "type": "experience",
        "label": "Value for Money",
        "description": "Price, affordability and perceived value relative to what the laptop provides.",
    },
    "EASE_OF_USE": {
        "type": "experience",
        "label": "Ease of Use",
        "description": "Ease of setup, configuration and general usability.",
    },
    "CAMERA_QUALITY": {
        "type": "experience",
        "label": "Camera Quality",
        "description": "Webcam/camera quality and camera usability.",
    },
    "CONNECTIVITY_PORTS": {
        "type": "experience",
        "label": "Connectivity / Ports",
        "description": "Port selection, USB connectivity, Wi-Fi and Bluetooth experience.",
    },
    "SOFTWARE_EXPERIENCE": {
        "type": "experience",
        "label": "Software / OS Experience",
        "description": "Operating-system and bundled software experience.",
    },
    "AI_FEATURES": {
        "type": "experience",
        "label": "AI Features",
        "description": "User experience with Copilot or other AI-oriented laptop features.",
    },
    "BIOMETRIC_SECURITY": {
        "type": "experience",
        "label": "Biometric Security",
        "description": "Fingerprint, face-unlock and related biometric-login experience.",
    },
    "FEATURE_SET": {
        "type": "experience",
        "label": "Feature Set",
        "description": "General comments about the laptop's available features.",
    },
    "RELIABILITY_STABILITY": {
        "type": "experience",
        "label": "Reliability / Stability",
        "description": "Reliability, stability, failures or persistent operational issues.",
    },

    # Specification-like aspects. These are retained but are not intended to be
    # mixed into the default user-experience ranking because the structured Best
    # Buy specification data is the more reliable source of factual values.
    "RAM_MEMORY": {
        "type": "specification",
        "label": "RAM / Memory",
        "description": "RAM/memory capacity or memory-related hardware mentions.",
    },
    "STORAGE": {
        "type": "specification",
        "label": "Storage",
        "description": "SSD/storage capacity or storage hardware mentions.",
    },
    "PROCESSOR_CPU": {
        "type": "specification",
        "label": "Processor / CPU",
        "description": "CPU/APU/processor hardware mentions.",
    },
    "GRAPHICS_GPU": {
        "type": "specification",
        "label": "Graphics / GPU",
        "description": "GPU/iGPU/graphics hardware mentions.",
    },
}


# -----------------------------------------------------------------------------
# Surface normalization
# -----------------------------------------------------------------------------
def normalize_surface(text: object) -> str:
    """Normalize an extracted surface form for ontology lookup."""
    if text is None:
        return ""

    value = str(text).casefold()
    value = re.sub(r"[‐‑‒–—−]", "-", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip(" \t\n\r.,;:!?\"'()[]{}")


# -----------------------------------------------------------------------------
# Explicit aliases from the exploratory sample
# -----------------------------------------------------------------------------
EXPERIENCE_ALIASES: Dict[str, Iterable[str]] = {
    "PERFORMANCE": {
        "performance", "speed", "multitasking", "boot times", "boots",
        "runs", "run", "handles", "power", "productivity", "performance modes",
    },
    "GAMING_PERFORMANCE": {
        "gaming", "game", "games", "video games", "gaming performance",
        "gaming performance on", "gaming handheld", "frame rate", "dlss",
        "fsr3", "ray tracing",
    },
    "BATTERY_LIFE": {
        "battery life", "battery", "battery capacity", "battery power",
    },
    "CHARGING": {
        "charge", "charging", "charger", "gan charger", "charging brick",
        "charging port",
    },
    "DISPLAY_QUALITY": {
        "screen", "display", "screen size", "screen quality", "screen display",
        "screens", "resolution", "resolutions", "p resolution", "brightness",
        "contrast", "panel", "2k", "hd screen", "180hz display", "refresh rate",
        "variable refresh mode", "vrr", "vrr display", "vrr enabled",
        "backlit display", "led display", "mini led", "oled",
        "color accuracy", "light bleed", "bleed", "amd freesync",
    },
    "TOUCHSCREEN_EXPERIENCE": {
        "touchscreen", "touch screen", "touchscreen display", "screen rotation",
        "touch", "touch input", "pen", '14" 2k touch display',
    },
    "THERMAL_PERFORMANCE": {
        "cooling", "thermals", "thermal performance", "heat", "temperature",
        "temperatures", "thermal",
    },
    "FAN_NOISE": {
        "fan noise", "fan loudness", "fans loud", "fan behavior", "fan behaviour",
    },
    "KEYBOARD": {
        "keyboard", "keys", "10 key", "number pad", "numerical pad",
        "alphanumeric keyboards", "keyboard backlight", "lighted keys", "typing",
    },
    "TRACKPAD": {
        "trackpad", "touchpad", "mousepad", "haptic trackpad",
    },
    "AUDIO": {
        "speakers", "speaker", "speaker sound", "audio", "sound quality",
    },
    "BUILD_QUALITY": {
        "build quality", "build", "hinge", "kickstand hinge", "chassis",
        "tablet body",
    },
    "DESIGN": {
        "design", "2-in-1 design", "2-in-1 flip design", "2-in-1", "2‑in‑1",
        "form factor", "flexibility", "tablet", "tablet modes", "tablet rotation",
        "flip", "kickstand", "style", "rgb", "finish",
        "design elements", "designwork", "lighting",
        "motherboard glass lighting", "atmospheric blue color",
        "atmospheric blue finish", "blue color", "black finish",
        "built-in kickstand",
    },
    "PORTABILITY": {
        "portability", "portable", "compact size", "weight", "travel",
        "transport",
    },
    "VALUE_FOR_MONEY": {
        "price", "prices", "value", "affordability", "priced", "price point",
        "sale price", "cost", "budget",
    },
    "EASE_OF_USE": {
        "set up", "setting up", "setup", "ease of use", "usability",
        "instructions", "configuration",
    },
    "CAMERA_QUALITY": {
        "camera", "camera sensor", "webcam", "windows hello front camera", "lens",
    },
    "CONNECTIVITY_PORTS": {
        "ports", "port", "wifi", "usb", "usb c", "usb3", "usb4", "usbc",
        "bluetooth", "bluetooth controller", "docking station",
        "microsd card slot", "micro sd card slot", "magnetic pogo pins",
    },
    "SOFTWARE_EXPERIENCE": {
        "windows", "windows 10", "windows 11", "windows operating system", "os",
        "software experience", "windows software", "support app", "armoury crate menu",
        "drivers", "interface",
    },
    "AI_FEATURES": {
        "copilot", "copilot works", "copilot+ ai capabilities",
        "copilot+ features", "ai", "ai models", "ai workflow", "ais",
    },
    "BIOMETRIC_SECURITY": {
        "fingerprint", "fingerprint sensor", "face unlocking", "face unlock",
    },
    "FEATURE_SET": {
        "features", "feature", "action button", "productivity features",
    },
    "RELIABILITY_STABILITY": {
        "reliability", "stability",
    },
}


SPECIFICATION_ALIASES: Dict[str, Iterable[str]] = {
    "RAM_MEMORY": {
        "ram", "memory", "16gb", "16 gb", "16gb ram", "16gb of ram",
        "16gb of memory", "4gb of ram", "64gb of memory", "64gb model",
        "64gb of", "integrated ram",
    },
    "STORAGE": {
        "storage", "ssd", "drive", "hard drive", "512gb ssd", "512 gb", "m.2 ssd",
    },
    "PROCESSOR_CPU": {
        "processor", "cpu", "apu", "cores", "chips", "amd processor",
        "8-core amd processor", "intel core ultra 5", "intel core ultra 5 processor",
        "celeron", "m3 pro", "ai max+ 395 cpu", "ryzen ai max+ 395",
    },
    "GRAPHICS_GPU": {
        "graphics", "gpu", "igpu", "integrated graphics", "arc b", "fsr",
        "egpus", "rtx",
    },
}


# Clearly non-domain/generic extractions. These are rejected rather than treated
# as user-experience dimensions. The original raw predictions are still saved.
REJECT_EXACT = {
    "purchase", "product", "user", "users", "buyer", "buyers", "job",
    "homework", "work", "working", "school work", "watching", "tabs", "tab",
    "applications", "programs", "chrome", "browsing", "web browsing",
    "streaming", "cad", "image processing", "document editing", "accounts",
    "note", "notes", "table", "bestbuy", "best buy", "package", "packaging",
    "included protective sleeve", "included jacket case", "cover bag",
    "acer", "idea pad", "rog flow z13", "flow z", "labtop", "laptop",
    "computer", "chromebook", "chromebrook", "device", "specs", "hardware",
    "software developers", "needs", "thing", "things", "items", "settings",
    "overall", "daily use", "everyday use", "values", "back", "multi",
    "works", "internet", "storage sleeve", "apps", "browser", "3d model",
    "adobe photoshop", "ally", "bill", "bills", "bility", "efficacy",
    'silent mode', 'energy saving mode', 'operating mode', 'mode', 'default', 'acer tv monitor', 'mac', 'switch 2', 'xbox ally x', 'surface pro devices', 'surface pro 11 type cover', 'up surface pro', 'internet browsing', 'internet surfing', 'web browsing with', 'web tasks', 'media streaming', 'online class', 'paper work', 'microsoft office', 'microsoft office work', 'programming', 'video calls', 'video conferencing', 'workstation', 'writing', 'tech purchases', 'customer satisfaction', 'cup of tea', 'choice', 'class', 'classes', 'cleaning', 'devices', 'devide', 'function', 'improvements', 'input', 'load', 'loading', 'marks', 'media', 'operation', 'operate', 'operates', 'personal', 'program', 'proprietary', 'resource', 'service', 'staff', 'system', 'tasks', 'unit', 'usage', 'using', 'utilities', 'waiting', 'window', 'word', 'zone', 'spec', 'arrangement', 'dedicated', 'hardware ecosystem', 'headroom', 'native', 'note-taking', 'prints', 'software tools', 'surface', 'tablets', 'tuning', 'view',
}


# Some short strings are legitimate laptop aspects; every other very short token
# is treated as probable ATE noise.
VALID_SHORT_TERMS = {
    "ai", "os", "2k", "ssd", "ram", "cpu", "apu", "gpu", "fsr", "vrr",
    "rgb", "usb",
}


# -----------------------------------------------------------------------------
# Lookup tables
# -----------------------------------------------------------------------------
def _build_alias_lookup() -> Dict[str, Tuple[str, str]]:
    lookup: Dict[str, Tuple[str, str]] = {}

    for canonical, aliases in EXPERIENCE_ALIASES.items():
        for alias in aliases:
            lookup[normalize_surface(alias)] = (canonical, "experience")

    for canonical, aliases in SPECIFICATION_ALIASES.items():
        for alias in aliases:
            lookup[normalize_surface(alias)] = (canonical, "specification")

    return lookup


ALIAS_LOOKUP = _build_alias_lookup()


# Conservative keyword rules for variants that did not appear exactly in the
# 100-review sample. Rule order is important: more specific concepts first.
REGEX_RULES = [
    (re.compile(r"\b(gaming|game|games)\b"), "GAMING_PERFORMANCE", "experience"),
    (re.compile(r"\b(touch\s*screen|touchscreen)\b"), "TOUCHSCREEN_EXPERIENCE", "experience"),
    (re.compile(r"\b(battery)\b"), "BATTERY_LIFE", "experience"),
    (re.compile(r"\b(charge|charging|charger)\b"), "CHARGING", "experience"),
    (re.compile(r"\b(screen|display|resolution|brightness|contrast|panel|refresh rate|oled|mini led|vrr|color accuracy)\b"), "DISPLAY_QUALITY", "experience"),
    (re.compile(r"\b(keyboard|keys|keypad|number pad|numerical pad)\b"), "KEYBOARD", "experience"),
    (re.compile(r"\b(trackpad|touchpad|mousepad)\b"), "TRACKPAD", "experience"),
    (re.compile(r"\b(speaker|speakers|audio)\b"), "AUDIO", "experience"),
    (re.compile(r"\b(thermal|thermals|cooling|heat|temperature|temperatures)\b"), "THERMAL_PERFORMANCE", "experience"),
    (re.compile(r"\b(fan noise|fan loudness)\b"), "FAN_NOISE", "experience"),
    (re.compile(r"\b(build quality|hinge|chassis)\b"), "BUILD_QUALITY", "experience"),
    (re.compile(r"\b(portability|portable|compact|travel|transport|weight)\b"), "PORTABILITY", "experience"),
    (re.compile(r"\b(price|value|affordab\w*|cost)\b"), "VALUE_FOR_MONEY", "experience"),
    (re.compile(r"\b(set ?up|setting up|ease of use|usability)\b"), "EASE_OF_USE", "experience"),
    (re.compile(r"\b(camera|webcam)\b"), "CAMERA_QUALITY", "experience"),
    (re.compile(r"\b(usb\w*|ports?|wifi|bluetooth|docking station|microsd|micro sd)\b"), "CONNECTIVITY_PORTS", "experience"),
    (re.compile(r"\b(copilot|ai feature\w*|ai capabilities)\b"), "AI_FEATURES", "experience"),
    (re.compile(r"\b(windows|operating system|software experience)\b"), "SOFTWARE_EXPERIENCE", "experience"),
    (re.compile(r"\b(2-in-1|design|form factor|kickstand|tablet mode|tablet modes)\b"), "DESIGN", "experience"),
    (re.compile(r"\b(performance|multitask\w*|speed|boot time\w*|handles|power)\b"), "PERFORMANCE", "experience"),
    (re.compile(r"\b(ram|memory)\b"), "RAM_MEMORY", "specification"),
    (re.compile(r"\b(storage|ssd|hard drive)\b"), "STORAGE", "specification"),
    (re.compile(r"\b(processor|cpu|apu|ryzen|intel core|celeron|cores?)\b"), "PROCESSOR_CPU", "specification"),
    (re.compile(r"\b(gpu|igpu|graphics|egpu|rtx)\b"), "GRAPHICS_GPU", "specification"),
]


@dataclass(frozen=True)
class AspectDecision:
    raw_aspect: str
    aspect_key: str
    ontology_status: str
    canonical_aspect: str
    canonical_label: str
    aspect_type: str
    mapping_method: str
    mapping_reason: str

    def to_dict(self) -> Dict[str, str]:
        return asdict(self)


def _mapped_decision(
    raw_aspect: str,
    aspect_key: str,
    canonical_aspect: str,
    aspect_type: str,
    mapping_method: str,
    mapping_reason: str,
) -> AspectDecision:
    metadata = CANONICAL_ASPECTS[canonical_aspect]
    return AspectDecision(
        raw_aspect=raw_aspect,
        aspect_key=aspect_key,
        ontology_status="mapped",
        canonical_aspect=canonical_aspect,
        canonical_label=metadata["label"],
        aspect_type=aspect_type,
        mapping_method=mapping_method,
        mapping_reason=mapping_reason,
    )


def classify_aspect(aspect: object, context: object = "") -> AspectDecision:
    """
    Classify one extracted aspect.

    Unknown terms are intentionally returned as ``unmapped`` rather than guessed.
    That makes ontology coverage measurable and lets the mapping evolve safely.
    """
    raw_aspect = "" if aspect is None else str(aspect)
    aspect_key = normalize_surface(raw_aspect)
    context_key = normalize_surface(context)

    if not aspect_key:
        return AspectDecision(
            raw_aspect=raw_aspect,
            aspect_key=aspect_key,
            ontology_status="rejected",
            canonical_aspect="",
            canonical_label="",
            aspect_type="rejected",
            mapping_method="reject",
            mapping_reason="empty aspect",
        )

    # Known irrelevant/generic domain terms.
    if aspect_key in REJECT_EXACT:
        return AspectDecision(
            raw_aspect=raw_aspect,
            aspect_key=aspect_key,
            ontology_status="rejected",
            canonical_aspect="",
            canonical_label="",
            aspect_type="rejected",
            mapping_method="reject_exact",
            mapping_reason="generic, use-case, product-name or non-laptop-quality term",
        )

    # Common generic verbs need context before they are considered useful.
    if aspect_key == "use":
        if re.search(r"\b(easy|simple|intuitive|hard|difficult|confusing)\b", context_key):
            return _mapped_decision(
                raw_aspect, aspect_key, "EASE_OF_USE", "experience", "context_rule",
                "'use' appears in an ease/difficulty context",
            )
        return AspectDecision(
            raw_aspect, aspect_key, "rejected", "", "", "rejected",
            "reject_context", "generic 'use' without an ease-of-use cue",
        )

    # Context-sensitive ambiguous nouns/verbs.
    if aspect_key in {"run", "runs"} and re.search(r"\b(gaming|game|games)\b", context_key):
        return _mapped_decision(
            raw_aspect, aspect_key, "GAMING_PERFORMANCE", "experience", "context_rule",
            "run/runs refers specifically to games in the local context",
        )

    if aspect_key == "backlit":
        if re.search(r"\b(keyboard|key|keys)\b", context_key):
            return _mapped_decision(raw_aspect, aspect_key, "KEYBOARD", "experience", "context_rule", "backlighting refers to keyboard")
        if re.search(r"\b(screen|display|panel)\b", context_key):
            return _mapped_decision(raw_aspect, aspect_key, "DISPLAY_QUALITY", "experience", "context_rule", "backlighting refers to display")

    if aspect_key == "light":
        if re.search(r"\b(lightweight|carry|portable|travel|weight)\b", context_key):
            return _mapped_decision(raw_aspect, aspect_key, "PORTABILITY", "experience", "context_rule", "light refers to device weight/portability")
        if re.search(r"\b(screen|display|brightness)\b", context_key):
            return _mapped_decision(raw_aspect, aspect_key, "DISPLAY_QUALITY", "experience", "context_rule", "light refers to display")

    if aspect_key == "quality":
        if re.search(r"\b(camera|webcam)\b", context_key):
            return _mapped_decision(raw_aspect, aspect_key, "CAMERA_QUALITY", "experience", "context_rule", "quality refers to camera/webcam")
        if re.search(r"\b(screen|display|panel)\b", context_key):
            return _mapped_decision(raw_aspect, aspect_key, "DISPLAY_QUALITY", "experience", "context_rule", "quality refers to screen/display")
        if re.search(r"\b(build|hinge|chassis)\b", context_key):
            return _mapped_decision(raw_aspect, aspect_key, "BUILD_QUALITY", "experience", "context_rule", "quality refers to construction")
        if re.search(r"\b(price|value|pay|paid)\b", context_key):
            return _mapped_decision(raw_aspect, aspect_key, "VALUE_FOR_MONEY", "experience", "context_rule", "quality is discussed relative to price/value")
        return AspectDecision(raw_aspect, aspect_key, "unmapped", "", "", "unmapped", "ambiguous", "'quality' has no reliable target in the local context")

    if aspect_key == "color":
        if re.search(r"\b(screen|display|panel|pixel|resolution)\b", context_key):
            return _mapped_decision(raw_aspect, aspect_key, "DISPLAY_QUALITY", "experience", "context_rule", "color refers to display output")
        return _mapped_decision(raw_aspect, aspect_key, "DESIGN", "experience", "context_rule", "color treated as physical/aesthetic design")

    if aspect_key == "size":
        if re.search(r"\b(screen|display|inch|\d{2}[\"”]|resolution)\b", context_key):
            return _mapped_decision(raw_aspect, aspect_key, "DISPLAY_QUALITY", "experience", "context_rule", "size refers to the display")
        if re.search(r"\b(light|heavy|portable|compact|carry|travel)\b", context_key):
            return _mapped_decision(raw_aspect, aspect_key, "PORTABILITY", "experience", "context_rule", "size is discussed as a portability characteristic")
        return AspectDecision(raw_aspect, aspect_key, "unmapped", "", "", "unmapped", "ambiguous", "'size' has no reliable target in the local context")

    # Version-2 context-sensitive refinements.
    if aspect_key in {"fan", "fans"}:
        if re.search(r"\b(loud|louder|noise|noisy|quiet|quieter|silent|acoustic)\b", context_key):
            return _mapped_decision(
                raw_aspect, aspect_key, "FAN_NOISE", "experience", "context_rule",
                "fan/fans is discussed in an acoustic/noise context",
            )
        if re.search(r"\b(hot|heat|cool|cooling|thermal|temperature|temperatures)\b", context_key):
            return _mapped_decision(
                raw_aspect, aspect_key, "THERMAL_PERFORMANCE", "experience", "context_rule",
                "fan/fans is discussed in a thermal/cooling context",
            )
        return _mapped_decision(
            raw_aspect, aspect_key, "FAN_NOISE", "experience", "context_rule",
            "plain fan/fans mention is treated as fan-behaviour/noise experience",
        )

    if aspect_key == "noise":
        if re.search(r"\b(fan|fans|cooling|thermal)\b", context_key):
            return _mapped_decision(
                raw_aspect, aspect_key, "FAN_NOISE", "experience", "context_rule",
                "noise refers to cooling fans in the local context",
            )

    if aspect_key == "sensor":
        if re.search(r"\b(camera|webcam|lens|face|meeting|video)\b", context_key):
            return _mapped_decision(
                raw_aspect, aspect_key, "CAMERA_QUALITY", "experience", "context_rule",
                "sensor is discussed as part of the camera/webcam",
            )

    if aspect_key in {"amd", "intel"}:
        if re.search(r"\b(cpu|apu|processor|core|cores|chip|chips)\b", context_key):
            return _mapped_decision(
                raw_aspect, aspect_key, "PROCESSOR_CPU", "specification", "context_rule",
                "vendor name appears in a processor/APU context",
            )
        if re.search(r"\b(gpu|graphics|igpu|radeon|arc)\b", context_key):
            return _mapped_decision(
                raw_aspect, aspect_key, "GRAPHICS_GPU", "specification", "context_rule",
                "vendor name appears in a graphics/GPU context",
            )

    if aspect_key == "8gb":
        if re.search(r"\b(16gb|ram|memory|model)\b", context_key):
            return _mapped_decision(
                raw_aspect, aspect_key, "RAM_MEMORY", "specification", "context_rule",
                "8GB is contrasted with RAM/memory capacity in context",
            )

    if aspect_key == "scrolling":
        if re.search(r"\b(trackpad|touchpad|mousepad|gesture)\b", context_key):
            return _mapped_decision(
                raw_aspect, aspect_key, "TRACKPAD", "experience", "context_rule",
                "scrolling refers to trackpad/touchpad interaction",
            )
        return _mapped_decision(
            raw_aspect, aspect_key, "SOFTWARE_EXPERIENCE", "experience", "context_rule",
            "scrolling direction/behaviour is treated as software/UI experience",
        )

    if aspect_key == "volume":
        return _mapped_decision(
            raw_aspect, aspect_key, "AUDIO", "experience", "context_rule",
            "volume control is part of the audio experience",
        )

    # Exact aliases are preferred over general regex rules.
    if aspect_key in ALIAS_LOOKUP:
        canonical, aspect_type = ALIAS_LOOKUP[aspect_key]
        return _mapped_decision(
            raw_aspect, aspect_key, canonical, aspect_type, "exact_alias",
            f"matched ontology alias '{aspect_key}'",
        )

    # Probable ATE fragments/noise. Numeric-only strings are also discarded.
    compact = re.sub(r"[^a-z0-9]+", "", aspect_key)
    if (
        (len(compact) < 3 and aspect_key not in VALID_SHORT_TERMS)
        or bool(re.fullmatch(r"\d+", compact or ""))
    ):
        return AspectDecision(
            raw_aspect, aspect_key, "rejected", "", "", "rejected",
            "noise_filter", "very short or numeric-only extraction likely caused by ATE boundary noise",
        )

    # General variants.
    for pattern, canonical, aspect_type in REGEX_RULES:
        if pattern.search(aspect_key):
            return _mapped_decision(
                raw_aspect, aspect_key, canonical, aspect_type, "regex_rule",
                f"matched rule: {pattern.pattern}",
            )

    return AspectDecision(
        raw_aspect=raw_aspect,
        aspect_key=aspect_key,
        ontology_status="unmapped",
        canonical_aspect="",
        canonical_label="",
        aspect_type="unmapped",
        mapping_method="unmapped",
        mapping_reason="no conservative ontology rule matched",
    )


def ontology_table():
    """Return canonical ontology metadata as a list of dictionaries."""
    rows = []
    for canonical, metadata in CANONICAL_ASPECTS.items():
        rows.append(
            {
                "canonical_aspect": canonical,
                "canonical_label": metadata["label"],
                "aspect_type": metadata["type"],
                "description": metadata["description"],
            }
        )
    return rows


# =============================================================================
# Version 3 full-corpus refinement
# =============================================================================
# Keep the v2 classifier available as the conservative fallback. The v3 rules
# below were derived from recurring terms in the complete 30-laptop Best Buy
# corpus. Specific context rules are evaluated before exact mappings/rejections.
_classify_aspect_v2 = classify_aspect

CANONICAL_ASPECTS.update({
    "UPGRADEABILITY": {
        "type": "experience",
        "label": "Upgradeability",
        "description": "Ease and flexibility of accessing or upgrading internal RAM/storage components.",
    },
    "NPU_AI_ACCELERATOR": {
        "type": "specification",
        "label": "NPU / AI Accelerator",
        "description": "Neural processing unit or other dedicated AI accelerator hardware mentions.",
    },
})

V3_EXACT_MAP = {
    # Performance and gaming.
    "performs": ("PERFORMANCE", "experience"),
    "processing": ("PERFORMANCE", "experience"),
    "load times": ("PERFORMANCE", "experience"),
    "boot": ("PERFORMANCE", "experience"),
    "boot up": ("PERFORMANCE", "experience"),
    "startup": ("PERFORMANCE", "experience"),
    "gameplay": ("GAMING_PERFORMANCE", "experience"),
    "frame rates": ("GAMING_PERFORMANCE", "experience"),
    "framerates": ("GAMING_PERFORMANCE", "experience"),
    "framerate": ("GAMING_PERFORMANCE", "experience"),
    "fps": ("GAMING_PERFORMANCE", "experience"),
    "max settings": ("GAMING_PERFORMANCE", "experience"),
    "frame generation": ("GAMING_PERFORMANCE", "experience"),
    "frame gen": ("GAMING_PERFORMANCE", "experience"),
    "dlss 4": ("GAMING_PERFORMANCE", "experience"),

    # Display and audio.
    "colors": ("DISPLAY_QUALITY", "experience"),
    "blacks": ("DISPLAY_QUALITY", "experience"),
    "visuals": ("DISPLAY_QUALITY", "experience"),
    "picture quality": ("DISPLAY_QUALITY", "experience"),
    "hdr": ("DISPLAY_QUALITY", "experience"),
    "displays": ("DISPLAY_QUALITY", "experience"),
    "bezels": ("DISPLAY_QUALITY", "experience"),
    "bezel": ("DISPLAY_QUALITY", "experience"),
    "viewing angles": ("DISPLAY_QUALITY", "experience"),
    "aspect ratio": ("DISPLAY_QUALITY", "experience"),
    "resh rate": ("DISPLAY_QUALITY", "experience"),
    "refresh rates": ("DISPLAY_QUALITY", "experience"),
    "glare": ("DISPLAY_QUALITY", "experience"),
    "pixels": ("DISPLAY_QUALITY", "experience"),
    "detail": ("DISPLAY_QUALITY", "experience"),
    "details": ("DISPLAY_QUALITY", "experience"),
    "sound": ("AUDIO", "experience"),
    "sounds": ("AUDIO", "experience"),
    "bass": ("AUDIO", "experience"),
    "dolby atmos": ("AUDIO", "experience"),

    # Physical experience.
    "carry": ("PORTABILITY", "experience"),
    "traveling": ("PORTABILITY", "experience"),
    "look": ("DESIGN", "experience"),
    "looks": ("DESIGN", "experience"),
    "appearance": ("DESIGN", "experience"),
    "aesthetic": ("DESIGN", "experience"),
    "aesthetics": ("DESIGN", "experience"),
    "rgb lighting": ("DESIGN", "experience"),
    "rgb lights": ("DESIGN", "experience"),
    "leds": ("DESIGN", "experience"),
    "lid": ("BUILD_QUALITY", "experience"),
    "hinges": ("BUILD_QUALITY", "experience"),
    "plastic": ("BUILD_QUALITY", "experience"),
    "construction": ("BUILD_QUALITY", "experience"),
    "materials": ("BUILD_QUALITY", "experience"),
    "material": ("BUILD_QUALITY", "experience"),
    "aluminum": ("BUILD_QUALITY", "experience"),
    "body": ("BUILD_QUALITY", "experience"),

    # Value/ease/features/software.
    "money": ("VALUE_FOR_MONEY", "experience"),
    "sale": ("VALUE_FOR_MONEY", "experience"),
    "pricing": ("VALUE_FOR_MONEY", "experience"),
    "discount": ("VALUE_FOR_MONEY", "experience"),
    "navigate": ("EASE_OF_USE", "experience"),
    "navigation": ("EASE_OF_USE", "experience"),
    "functionality": ("FEATURE_SET", "experience"),
    "capability": ("FEATURE_SET", "experience"),
    "capabilities": ("FEATURE_SET", "experience"),
    "functions": ("FEATURE_SET", "experience"),
    "software": ("SOFTWARE_EXPERIENCE", "experience"),
    "softwares": ("SOFTWARE_EXPERIENCE", "experience"),
    "bios": ("SOFTWARE_EXPERIENCE", "experience"),
    "compatibility": ("SOFTWARE_EXPERIENCE", "experience"),
    "driver": ("SOFTWARE_EXPERIENCE", "experience"),
    "firmware": ("SOFTWARE_EXPERIENCE", "experience"),
    "updates": ("SOFTWARE_EXPERIENCE", "experience"),
    "linux": ("SOFTWARE_EXPERIENCE", "experience"),
    "armoury crate": ("SOFTWARE_EXPERIENCE", "experience"),
    "armory crate": ("SOFTWARE_EXPERIENCE", "experience"),
    "asus software": ("SOFTWARE_EXPERIENCE", "experience"),

    # Input / biometrics.
    "key": ("KEYBOARD", "experience"),
    "keyboards": ("KEYBOARD", "experience"),
    "typing sessions": ("KEYBOARD", "experience"),
    "track pad": ("TRACKPAD", "experience"),
    "touch pad": ("TRACKPAD", "experience"),
    "mouse pad": ("TRACKPAD", "experience"),
    "gestures": ("TRACKPAD", "experience"),
    "stylus": ("TOUCHSCREEN_EXPERIENCE", "experience"),
    "pen support": ("TOUCHSCREEN_EXPERIENCE", "experience"),
    "fingerprint reader": ("BIOMETRIC_SECURITY", "experience"),
    "facial recognition": ("BIOMETRIC_SECURITY", "experience"),
    "face recognition": ("BIOMETRIC_SECURITY", "experience"),

    # Connectivity / charging / thermals.
    "hdmi": ("CONNECTIVITY_PORTS", "experience"),
    "hdmi 2": ("CONNECTIVITY_PORTS", "experience"),
    "headphone jack": ("CONNECTIVITY_PORTS", "experience"),
    "connectivity": ("CONNECTIVITY_PORTS", "experience"),
    "connection": ("CONNECTIVITY_PORTS", "experience"),
    "displayport": ("CONNECTIVITY_PORTS", "experience"),
    "ethernet": ("CONNECTIVITY_PORTS", "experience"),
    "wi-fi": ("CONNECTIVITY_PORTS", "experience"),
    "wi-fi 7": ("CONNECTIVITY_PORTS", "experience"),
    "thunderbolt": ("CONNECTIVITY_PORTS", "experience"),
    "thunderbolt 4": ("CONNECTIVITY_PORTS", "experience"),
    "dock": ("CONNECTIVITY_PORTS", "experience"),
    "dongle": ("CONNECTIVITY_PORTS", "experience"),
    "dongles": ("CONNECTIVITY_PORTS", "experience"),
    "card reader": ("CONNECTIVITY_PORTS", "experience"),
    "sd card slot": ("CONNECTIVITY_PORTS", "experience"),
    "charges": ("CHARGING", "experience"),
    "charged": ("CHARGING", "experience"),
    "temps": ("THERMAL_PERFORMANCE", "experience"),
    "heating": ("THERMAL_PERFORMANCE", "experience"),
    "airflow": ("THERMAL_PERFORMANCE", "experience"),
    "vents": ("THERMAL_PERFORMANCE", "experience"),
    "heats": ("THERMAL_PERFORMANCE", "experience"),
    "quiet": ("FAN_NOISE", "experience"),

    # Specification-oriented review mentions.
    "vram": ("GRAPHICS_GPU", "specification"),
    "nvidia": ("GRAPHICS_GPU", "specification"),
    "nvidia geforce": ("GRAPHICS_GPU", "specification"),
    "geforce": ("GRAPHICS_GPU", "specification"),
    "gpus": ("GRAPHICS_GPU", "specification"),
    "dgpu": ("GRAPHICS_GPU", "specification"),
    "radeon": ("GRAPHICS_GPU", "specification"),
    "video card": ("GRAPHICS_GPU", "specification"),
    "processors": ("PROCESSOR_CPU", "specification"),
    "snapdragon": ("PROCESSOR_CPU", "specification"),
    "snapdragon chip": ("PROCESSOR_CPU", "specification"),
    "512gb": ("STORAGE", "specification"),
    "nvme": ("STORAGE", "specification"),
    "nvme drive": ("STORAGE", "specification"),
    "npu": ("NPU_AI_ACCELERATOR", "specification"),
    "neural processing unit": ("NPU_AI_ACCELERATOR", "specification"),
}

# High-confidence non-aspects discovered repeatedly in the full corpus. These
# are retained in the raw output but intentionally excluded from recommendation
# aggregation.
V3_REJECT_EXACT = {
    # Brands/models/comparisons.
    "dell", "alienware", "rog flow", "flow", "hp victus", "acer predator",
    "msi", "asus", "legion", "xps", "xps 16", "g flow", "g strix",
    "victus", "strix", "rog", "us rog flow", "acer swift go 16 ai",
    "dell inspiron", "rog strix", "lenovo loq", "surface pro",
    "microsoft surface", "thinkpad",

    # Retail/service/accessories.
    "customer service", "warranty", "geek squad", "shipping", "delivery",
    "salesman", "manager", "shopping", "open box", "store", "sales",
    "case", "headphones", "headset", "external mouse", "external drive",
    "sleeve", "equipment", "cooler", "cable", "cord",

    # Workloads/apps/games rather than product-quality aspects.
    "video editing", "editing", "rendering", "school", "office", "office work",
    "coding", "content creation", "browser tabs", "content", "microsoft",
    "photoshop", "photo editing", "lightroom", "spreadsheets", "word processing",
    "engineering", "development", "computing", "productivity apps", "downloads",
    "download", "web surfing", "media consumption", "3d modeling", "autocad",
    "drawing", "llm", "llms", "zoom", "minecraft", "roblox", "steam",
    "cyberpunk", "fortnite", "sims", "sims 4", "valorant", "arc raiders",
    "warzone", "battlefield 6", "aaa", "4k video", "music", "video", "videos",
    "stream", "application", "apps", "app", "gamer", "use case", "workflow",
    "files", "brows", "web", "code", "uses", "mods", "architecture",

    # Generic/noisy extractions.
    "buy", "machine", "tech", "technology", "box", "boxes", "components",
    "motherboard", "product", "products", "item", "electronics", "parts",
    "support", "specifications", "specification", "specs", "basic", "data",
    "excel", "phones", "controller", "systems", "operating", "peripherals",
    "marketing", "local", "services", "process", "experience", "lap", "lap top",
    "room", "field", "business", "king", "atware", "ware", "cyberpu", "rix",
    "len", "ing", "ref", "side", "numbers", "stock", "full", "water",
}


def _v3_mapped(raw_aspect, aspect_key, canonical, aspect_type, reason, method="v3_full_corpus"):
    return _mapped_decision(
        raw_aspect, aspect_key, canonical, aspect_type, method, reason
    )


def _v3_rejected(raw_aspect, aspect_key, reason):
    return AspectDecision(
        raw_aspect, aspect_key, "rejected", "", "", "rejected",
        "v3_reject", reason,
    )


def _v3_unmapped(raw_aspect, aspect_key, reason):
    return AspectDecision(
        raw_aspect, aspect_key, "unmapped", "", "", "unmapped",
        "v3_unmapped", reason,
    )


def classify_aspect(aspect: object, context: object = "") -> AspectDecision:
    """Version-3 classifier using full-corpus recurring terms plus v2 fallback."""
    raw_aspect = "" if aspect is None else str(aspect)
    aspect_key = normalize_surface(raw_aspect)
    context_key = normalize_surface(context)

    # ------------------------------------------------------------------
    # High-value ambiguous/context-sensitive terms.
    # ------------------------------------------------------------------
    if aspect_key == "quality":
        if re.search(r"\b(speaker|speakers|audio|sound|bass|volume)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "AUDIO", "experience", "quality refers to audio")
        if re.search(r"\b(keyboard|keys|typing)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "KEYBOARD", "experience", "quality refers to keyboard")
        if re.search(r"\b(trackpad|touchpad|mousepad)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "TRACKPAD", "experience", "quality refers to trackpad")
        if re.search(r"\b(camera|webcam)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "CAMERA_QUALITY", "experience", "quality refers to camera")
        if re.search(r"\b(screen|display|panel|resolution|1080p|oled)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "DISPLAY_QUALITY", "experience", "quality refers to display")
        if re.search(r"\b(price|value|pay|paid)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "VALUE_FOR_MONEY", "experience", "quality is discussed relative to price/value")
        return _v3_mapped(raw_aspect, aspect_key, "BUILD_QUALITY", "experience", "generic product quality treated as overall build/product quality")

    if aspect_key == "size":
        if re.search(r"\b(screen|display|panel|inch|inches|oled|touchscreen)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "DISPLAY_QUALITY", "experience", "size refers to display")
        if re.search(r"\b(storage|ssd|drive|disk|gb|tb|files?)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "STORAGE", "specification", "size refers to storage capacity")
        if re.search(r"\b(carry|portable|travel|backpack|weight|compact|small|large|thin|slim)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "PORTABILITY", "experience", "size refers to physical portability")
        return _v3_mapped(raw_aspect, aspect_key, "DESIGN", "experience", "general device size treated as form factor")

    if aspect_key == "light":
        if re.search(r"\b(light gaming|light use|light usage|light photo|light workload)\b", context_key):
            return _v3_rejected(raw_aspect, aspect_key, "light is a workload qualifier, not a laptop aspect")
        if re.search(r"\b(rgb|keyboard|backlight|lightbar|lighting|led)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "DESIGN", "experience", "light refers to lighting/design")
        if re.search(r"\b(thin|slim|weight|carry|portable|travel|heavy)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "PORTABILITY", "experience", "light refers to weight/portability")
        if re.search(r"\b(screen|display|bright|brightness)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "DISPLAY_QUALITY", "experience", "light refers to display")
        return _v3_rejected(raw_aspect, aspect_key, "ambiguous workload/lighting adjective without reliable aspect cue")

    if aspect_key == "space":
        if re.search(r"\b(storage|ssd|drive|disk|gb|tb|files?|capacity|microsd)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "STORAGE", "specification", "space refers to storage")
        if re.search(r"\b(small|compact|desk|footprint|takes up)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "PORTABILITY", "experience", "space refers to physical footprint")
        return _v3_rejected(raw_aspect, aspect_key, "generic space mention without storage/footprint cue")

    if aspect_key in {"monitor", "monitors", "external monitor", "external monitors"}:
        if re.search(r"\b(external|hdmi|displayport|usb[- ]?c|thunderbolt|connect|signal|dock)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "CONNECTIVITY_PORTS", "experience", "monitor refers to external-display connectivity")
        if re.search(r"\b(screen|display|resolution|refresh|oled|2k|1080|1600p|4k|panel|native)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "DISPLAY_QUALITY", "experience", "monitor refers to display quality")
        return _v3_rejected(raw_aspect, aspect_key, "external/ambiguous monitor mention without reliable laptop aspect cue")

    if aspect_key == "feel":
        if re.search(r"\b(keyboard|keys|typing)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "KEYBOARD", "experience", "feel refers to keyboard")
        if re.search(r"\b(trackpad|touchpad|mousepad)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "TRACKPAD", "experience", "feel refers to trackpad")
        if re.search(r"\b(chassis|build|premium|solid|durable|glass|cover|material|metal|plastic)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "BUILD_QUALITY", "experience", "feel refers to physical build/materials")
        return _v3_mapped(raw_aspect, aspect_key, "DESIGN", "experience", "general physical feel treated as design/form-factor experience")

    if aspect_key == "mouse":
        if re.search(r"\b(trackpad|touchpad|pad|cursor|finger|click)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "TRACKPAD", "experience", "mouse mention is tied to trackpad usability")
        return _v3_rejected(raw_aspect, aspect_key, "external mouse/accessory rather than laptop aspect")

    if aspect_key == "built":
        if re.search(r"\b(well|solid|premium|sturdy|durable|quality|plastic|metal|chassis)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "BUILD_QUALITY", "experience", "built describes construction quality")
        return _v3_unmapped(raw_aspect, aspect_key, "built is too generic without construction-quality cue")

    if aspect_key == "upgrade":
        if re.search(r"\b(old|previous|from my|from an|replacement|years?)\b", context_key) and not re.search(r"\b(ssd|ram|memory|slot|internals?|panel|nvme)\b", context_key):
            return _v3_rejected(raw_aspect, aspect_key, "upgrade refers to replacing an older device")
        if re.search(r"\b(ssd|ram|memory|slot|internals?|panel|nvme|component|easy|access)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "UPGRADEABILITY", "experience", "upgrade refers to internal component upgradeability")
        return _v3_unmapped(raw_aspect, aspect_key, "upgrade meaning is ambiguous")

    if aspect_key == "access":
        if re.search(r"\b(ssd|ram|memory|slot|internals?|bottom panel|back panel|upgrade|cleaning)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "UPGRADEABILITY", "experience", "access refers to internal component access")
        if re.search(r"\b(easy|easier|quick|parental controls|apps?|websites?)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "EASE_OF_USE", "experience", "access refers to ease of use/navigation")
        return _v3_unmapped(raw_aspect, aspect_key, "access is ambiguous")

    if aspect_key in {"turbo mode", "turbo", "eco mode", "balanced", "balance"}:
        if re.search(r"\b(fan|fans|loud|noise|quiet|silent)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "FAN_NOISE", "experience", "control mode discussed with fan/noise")
        if re.search(r"\b(temp|temps|temperature|thermal|heat|cool)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "THERMAL_PERFORMANCE", "experience", "control mode discussed with thermals")
        if re.search(r"\b(battery|hours|remaining|power saving)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "BATTERY_LIFE", "experience", "control mode discussed with battery")
        if re.search(r"\b(game|gaming|fps|frame|performance|speed)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "PERFORMANCE", "experience", "control mode discussed as a performance mode")
        return _v3_mapped(raw_aspect, aspect_key, "SOFTWARE_EXPERIENCE", "experience", "control mode treated as software/control experience")

    if aspect_key == "noise":
        return _v3_mapped(raw_aspect, aspect_key, "FAN_NOISE", "experience", "laptop noise treated as acoustic/fan-noise experience")

    if aspect_key == "efficiency":
        if re.search(r"\b(battery|battery life|energy|eco|power saving)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "BATTERY_LIFE", "experience", "efficiency discussed in battery/energy context")
        if re.search(r"\b(performance|cpu|gpu|igpu|game|gaming|workload)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "PERFORMANCE", "experience", "efficiency discussed as compute/performance efficiency")
        return _v3_unmapped(raw_aspect, aspect_key, "efficiency is ambiguous")

    if aspect_key == "support":
        if re.search(r"\b(driver|software|app|apps|compatib|amd|intel|windows|linux|pytorch|game)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "SOFTWARE_EXPERIENCE", "experience", "support refers to software/platform compatibility")
        return _v3_rejected(raw_aspect, aspect_key, "customer/vendor support is outside laptop-quality ontology")

    if aspect_key == "slot":
        if re.search(r"\b(m\.?2|nvme|ssd|ram|memory|second|extra|upgrade)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "UPGRADEABILITY", "experience", "slot refers to internal expansion/upgrade")
        if re.search(r"\b(sd|microsd|micro sd|card)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "CONNECTIVITY_PORTS", "experience", "slot refers to memory-card connectivity")
        return _v3_unmapped(raw_aspect, aspect_key, "slot type is ambiguous")

    if aspect_key == "air":
        if re.search(r"\b(airflow|hot|heat|cool|cooling|vent|thermal|temperature)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "THERMAL_PERFORMANCE", "experience", "air refers to airflow/thermal behaviour")
        return _v3_rejected(raw_aspect, aspect_key, "air is not a reliable laptop aspect in this context")

    if aspect_key == "capacity":
        if re.search(r"\b(battery|wh|mah)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "BATTERY_LIFE", "experience", "capacity refers to battery")
        if re.search(r"\b(storage|ssd|drive|disk|files?|tb|gb|microsd|nvme)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "STORAGE", "specification", "capacity refers to storage")
        return _v3_unmapped(raw_aspect, aspect_key, "capacity type is ambiguous")

    if aspect_key == "handle":
        if re.search(r"\b(handle on|sleeve|bag|backpack)\b", context_key):
            return _v3_rejected(raw_aspect, aspect_key, "physical accessory handle, not laptop quality")
        if re.search(r"\b(game|games|gaming|workload|multitask|task|everything|program|app|render|editing)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "PERFORMANCE", "experience", "handle describes workload capability")
        return _v3_rejected(raw_aspect, aspect_key, "ambiguous handle verb/accessory without workload cue")

    if aspect_key == "running":
        if re.search(r"\b(game|games|gaming)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "GAMING_PERFORMANCE", "experience", "running refers to games")
        if re.search(r"\b(smooth|smoothly|fast|quick|slow|lag|responsive|programs?|apps?|multiple|day one)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "PERFORMANCE", "experience", "running describes system performance")
        return _v3_rejected(raw_aspect, aspect_key, "generic verb/use case")

    if aspect_key in {"play", "plays"}:
        if re.search(r"\b(game|games|gaming|title|fps|frame|settings|minecraft|fortnite|cyberpunk|valorant)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "GAMING_PERFORMANCE", "experience", "play/plays refers to gaming")
        return _v3_rejected(raw_aspect, aspect_key, "generic media/use-case verb")

    if aspect_key == "backlight":
        if re.search(r"\b(keyboard|key|keys)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "KEYBOARD", "experience", "backlight refers to keyboard")
        if re.search(r"\b(screen|display|panel)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "DISPLAY_QUALITY", "experience", "backlight refers to display")
        return _v3_mapped(raw_aspect, aspect_key, "DESIGN", "experience", "backlight treated as lighting/design feature")

    if aspect_key == "lights":
        return _v3_mapped(raw_aspect, aspect_key, "DESIGN", "experience", "lights treated as laptop lighting/design")

    if aspect_key == "speeds":
        if re.search(r"\b(fan|fans|rpm)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "FAN_NOISE", "experience", "speeds refer to fan operation")
        return _v3_mapped(raw_aspect, aspect_key, "PERFORMANCE", "experience", "general speed experience")

    if aspect_key == "threads":
        if re.search(r"\b(cpu|processor|core|cores|intel|amd|ryzen)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "PROCESSOR_CPU", "specification", "threads refer to processor configuration")
        return _v3_unmapped(raw_aspect, aspect_key, "threads context is ambiguous")

    if aspect_key == "integrated":
        if re.search(r"\b(graphics|gpu|radeon|arc|igpu)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "GRAPHICS_GPU", "specification", "integrated refers to graphics")
        return _v3_unmapped(raw_aspect, aspect_key, "integrated is incomplete without hardware context")

    if aspect_key in {"intel", "chip", "chipset", "arm"}:
        if re.search(r"\b(gpu|graphics|arc|radeon)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "GRAPHICS_GPU", "specification", "hardware term occurs in GPU/graphics context")
        if re.search(r"\b(cpu|processor|core|cores|snapdragon|x plus|ultra|ryzen|apu|chip|celeron)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "PROCESSOR_CPU", "specification", "hardware term occurs in CPU/processor context")
        if aspect_key == "arm" and re.search(r"\b(compatibility|software|windows|app)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "SOFTWARE_EXPERIENCE", "experience", "ARM discussed in software compatibility context")
        return _v3_unmapped(raw_aspect, aspect_key, "hardware term lacks clear CPU/GPU context")

    if aspect_key == "silent":
        if re.search(r"\b(fan|fans|noise|mode|quiet)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "FAN_NOISE", "experience", "silent refers to fan/acoustic mode")
        return _v3_unmapped(raw_aspect, aspect_key, "silent is ambiguous")

    if aspect_key == "plug":
        if re.search(r"\b(charge|charger|battery|power|outlet)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "CHARGING", "experience", "plug refers to charging/power")
        if re.search(r"\b(port|usb|hdmi|displayport)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "CONNECTIVITY_PORTS", "experience", "plug refers to connectivity")
        return _v3_unmapped(raw_aspect, aspect_key, "plug is ambiguous")

    if aspect_key == "watt":
        if re.search(r"\b(charger|charging|usb[- ]?c|power supply)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "CHARGING", "experience", "watt refers to charging power")
        if re.search(r"\b(gpu|rtx|tgp)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "GRAPHICS_GPU", "specification", "watt refers to GPU power/TGP")
        if re.search(r"\b(performance/watt|efficien)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "PERFORMANCE", "experience", "watt appears in performance-efficiency context")
        return _v3_unmapped(raw_aspect, aspect_key, "watt lacks clear hardware context")

    if aspect_key == "black":
        if re.search(r"\b(oled|screen|display|deep black|blacks|contrast)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "DISPLAY_QUALITY", "experience", "black refers to display black level")
        return _v3_mapped(raw_aspect, aspect_key, "DESIGN", "experience", "generic black treated as chassis/design color")

    if aspect_key in {"picture", "clarity", "motion", "text"}:
        if aspect_key == "clarity" and re.search(r"\b(sound|audio|speaker)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "AUDIO", "experience", "clarity refers to audio")
        if aspect_key == "text" and not re.search(r"\b(screen|display|contrast|sharp|fuzzy|resolution|readable)\b", context_key):
            return _v3_rejected(raw_aspect, aspect_key, "text is content rather than a display-quality aspect")
        return _v3_mapped(raw_aspect, aspect_key, "DISPLAY_QUALITY", "experience", "term refers to visual/display quality")

    if aspect_key in {"frames", "response time"}:
        if aspect_key == "response time" and not re.search(r"\b(pixel|screen|display|ghost|game|gaming|hz|input lag)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "PERFORMANCE", "experience", "response time treated as system responsiveness")
        return _v3_mapped(raw_aspect, aspect_key, "GAMING_PERFORMANCE" if aspect_key == "frames" else "DISPLAY_QUALITY", "experience", "gaming/display response metric")

    if aspect_key == "drains":
        return _v3_mapped(raw_aspect, aspect_key, "BATTERY_LIFE", "experience", "drain refers to battery endurance")

    if aspect_key == "workload":
        if re.search(r"\b(handle|handles|fast|performance|heavy|demanding|smooth)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "PERFORMANCE", "experience", "workload discussed as performance capability")
        return _v3_rejected(raw_aspect, aspect_key, "workload is a use-case term")

    if aspect_key in {"modes", "app"}:
        if aspect_key == "app" and not re.search(r"\b(acer|asus|predator|armoury|armory|control|software|bug|polish|settings)\b", context_key):
            return _v3_rejected(raw_aspect, aspect_key, "generic third-party app/use case")
        return _v3_mapped(raw_aspect, aspect_key, "SOFTWARE_EXPERIENCE", "experience", "laptop control/software experience")

    if aspect_key == "internals":
        if re.search(r"\b(access|upgrade|slot|ram|ssd|nvme)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "UPGRADEABILITY", "experience", "internals discussed for access/upgrade")
        return _v3_rejected(raw_aspect, aspect_key, "generic internal hardware mention")

    if aspect_key == "vidia":
        if re.search(r"\b(nvidia|rtx|gpu|graphics|geforce)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "GRAPHICS_GPU", "specification", "ATE fragment refers to NVIDIA/GPU")
        return _v3_rejected(raw_aspect, aspect_key, "ATE fragment without clear GPU cue")

    if aspect_key == "card":
        if re.search(r"\b(nvidia|rtx|gpu|graphics|video card|4060|5070|5080)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "GRAPHICS_GPU", "specification", "card refers to GPU/video card")
        if re.search(r"\b(sd|microsd|memory card|reader)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "CONNECTIVITY_PORTS", "experience", "card refers to SD/memory-card connectivity")
        return _v3_rejected(raw_aspect, aspect_key, "generic card without reliable hardware target")

    if aspect_key == "cover":
        if re.search(r"\b(keyboard|type|typing|magnetic)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "KEYBOARD", "experience", "cover refers to keyboard cover")
        if re.search(r"\b(ssd|m\.2|nvme|access|upgrade|bottom)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "UPGRADEABILITY", "experience", "cover refers to service/upgrade access")
        if re.search(r"\b(plastic|board|chassis|build)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "BUILD_QUALITY", "experience", "cover refers to physical construction")
        return _v3_rejected(raw_aspect, aspect_key, "accessory/protective cover outside core laptop aspects")

    if aspect_key in {"8gb", "12gb", "16gb of", "32gb", "32 gb", "32gb of", "64gb", "gb of"}:
        if re.search(r"\b(vram|gpu|video memory)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "GRAPHICS_GPU", "specification", "GB amount refers to VRAM")
        if re.search(r"\b(ram|memory|ddr|lpddr)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "RAM_MEMORY", "specification", "GB amount refers to RAM")
        if re.search(r"\b(storage|ssd|emmc|drive|flash)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "STORAGE", "specification", "GB amount refers to storage")
        return _v3_unmapped(raw_aspect, aspect_key, "GB amount is ambiguous between memory/storage/VRAM")

    if aspect_key in {"16-inch", "14-inch", "inch"}:
        if re.search(r"\b(screen|display|touchscreen|panel|oled|mini led|laptop|tablet)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "DISPLAY_QUALITY", "experience", "inch measurement refers to display/device screen size")
        return _v3_rejected(raw_aspect, aspect_key, "generic measurement without display cue")

    if aspect_key == "premium":
        if re.search(r"\b(case|sleeve)\b", context_key):
            return _v3_rejected(raw_aspect, aspect_key, "premium describes accessory")
        if re.search(r"\b(design|look|appearance|finish)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "DESIGN", "experience", "premium refers to design")
        if re.search(r"\b(build|feel|chassis|quality|material)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "BUILD_QUALITY", "experience", "premium refers to build quality")
        return _v3_rejected(raw_aspect, aspect_key, "generic marketing adjective")

    if aspect_key == "ratio":
        if re.search(r"\b(16:10|aspect|display|screen)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "DISPLAY_QUALITY", "experience", "ratio refers to display aspect ratio")
        return _v3_rejected(raw_aspect, aspect_key, "ambiguous ratio")

    if aspect_key == "board":
        if re.search(r"\b(keyboard|type|typing|keys)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "KEYBOARD", "experience", "board refers to keyboard cover/typing board")
        return _v3_rejected(raw_aspect, aspect_key, "motherboard/ambiguous board is not a canonical ranking aspect")

    if aspect_key == "graphic":
        if re.search(r"\b(gpu|graphics|nvidia|radeon|rtx|intel arc)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "GRAPHICS_GPU", "specification", "graphic refers to GPU/graphics hardware")
        if re.search(r"\b(game|gaming|intensive|visual)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "GAMING_PERFORMANCE", "experience", "graphic refers to graphics-intensive gaming experience")
        return _v3_rejected(raw_aspect, aspect_key, "generic graphic/use-case term")

    if aspect_key == "horsepower":
        return _v3_mapped(raw_aspect, aspect_key, "PERFORMANCE", "experience", "horsepower is a performance metaphor")

    if aspect_key == "investment":
        if re.search(r"\b(price|cost|worth|value|premium)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "VALUE_FOR_MONEY", "experience", "investment refers to value/price")
        return _v3_rejected(raw_aspect, aspect_key, "generic purchase framing")

    if aspect_key == "option":
        if re.search(r"\b(price|affordable|value)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "VALUE_FOR_MONEY", "experience", "option discussed as affordability/value")
        return _v3_rejected(raw_aspect, aspect_key, "generic option term")

    if aspect_key == "layout":
        if re.search(r"\b(keyboard|keys|keypad)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "KEYBOARD", "experience", "layout refers to keyboard")
        return _v3_mapped(raw_aspect, aspect_key, "DESIGN", "experience", "layout treated as physical design")

    if aspect_key == "security":
        if re.search(r"\b(fingerprint|face|facial|windows hello|biometric)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "BIOMETRIC_SECURITY", "experience", "security refers to biometric login")
        return _v3_rejected(raw_aspect, aspect_key, "generic security topic outside aspect ontology")

    if aspect_key == "bottom":
        if re.search(r"\b(plate|panel|cover|screw|access|upgrade)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "UPGRADEABILITY", "experience", "bottom panel discussed for service/upgrade access")
        return _v3_rejected(raw_aspect, aspect_key, "generic positional term")

    if aspect_key == "headphone":
        if re.search(r"\b(jack|port|3\.5)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "CONNECTIVITY_PORTS", "experience", "headphone refers to headphone jack")
        return _v3_rejected(raw_aspect, aspect_key, "external audio accessory")

    if aspect_key == "factor":
        if re.search(r"\b(form factor|tablet|compact|design)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "DESIGN", "experience", "factor refers to form factor")
        return _v3_rejected(raw_aspect, aspect_key, "generic factor")

    if aspect_key == "brick":
        if re.search(r"\b(power|charger|charging|usb-c|200w)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "CHARGING", "experience", "brick refers to charger/power brick")
        return _v3_rejected(raw_aspect, aspect_key, "generic object")

    if aspect_key == "tdp":
        if re.search(r"\b(gpu|rtx|graphics|tgp)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "GRAPHICS_GPU", "specification", "TDP/TGP refers to GPU power")
        return _v3_mapped(raw_aspect, aspect_key, "PROCESSOR_CPU", "specification", "TDP refers to processor power")

    if aspect_key == "ice blue color":
        return _v3_mapped(raw_aspect, aspect_key, "DESIGN", "experience", "chassis color/design")

    # ------------------------------------------------------------------
    # Stable exact mappings/rejections identified across the full corpus.
    # ------------------------------------------------------------------
    if aspect_key in V3_EXACT_MAP:
        canonical, aspect_type = V3_EXACT_MAP[aspect_key]
        return _v3_mapped(raw_aspect, aspect_key, canonical, aspect_type, "recurring full-corpus variant")

    if aspect_key in V3_REJECT_EXACT:
        return _v3_rejected(raw_aspect, aspect_key, "brand/model/use-case/service/accessory/generic term outside canonical laptop-quality aspects")

    # Preserve the original conservative ontology for everything not covered by
    # the full-corpus v3 refinement.
    return _classify_aspect_v2(aspect, context)


# -----------------------------------------------------------------------------
# Version 3 residual long-tail cleanup
# -----------------------------------------------------------------------------
# A final conservative pass handles recurring terms that remained after the main
# v3 rules. The goal is not zero unmapped terms; it is to remove obvious generic
# noise while mapping only recurring, defensible laptop concepts.
_classify_aspect_v3_core = classify_aspect

V3_RESIDUAL_EXACT_MAP = {
    "perform": ("PERFORMANCE", "experience"),
    "performing": ("PERFORMANCE", "experience"),
    "responsiveness": ("PERFORMANCE", "experience"),
    "chipset": ("PROCESSOR_CPU", "specification"),
    "ddr5": ("RAM_MEMORY", "specification"),
    "upgradeability": ("UPGRADEABILITY", "experience"),
    "air flow": ("THERMAL_PERFORMANCE", "experience"),
    "liquid metal": ("THERMAL_PERFORMANCE", "experience"),
    "connections": ("CONNECTIVITY_PORTS", "experience"),
    "connectivity options": ("CONNECTIVITY_PORTS", "experience"),
    "hub": ("CONNECTIVITY_PORTS", "experience"),
    "adapter": ("CHARGING", "experience"),
    "g-sync": ("DISPLAY_QUALITY", "experience"),
    "keycaps": ("KEYBOARD", "experience"),
    "fit": ("DESIGN", "experience"),
    "convenience": ("EASE_OF_USE", "experience"),
    "ai tools": ("AI_FEATURES", "experience"),
    "amd software": ("SOFTWARE_EXPERIENCE", "experience"),
    "nvidia drivers": ("SOFTWARE_EXPERIENCE", "experience"),
    "controls": ("FEATURE_SET", "experience"),
    "deal": ("VALUE_FOR_MONEY", "experience"),
    "drives": ("STORAGE", "specification"),
    "x86": ("PROCESSOR_CPU", "specification"),
    "multicore": ("PROCESSOR_CPU", "specification"),
}

V3_RESIDUAL_REJECT = {
    "desktop", "setting", "entertainment", "max", "handling", "type", "install",
    "set", "condition", "juice", "processes", "3dmark", "brand", "purchases",
    "spreads", "versa", "sketchup", "companion", "dell 16 plus", "flow z13",
    "rus", "chrome tabs", "language models", "inspiron", "lenovo", "gta 6",
    "home use", "area", "book", "cloud", "external", "standard", "front",
}


def classify_aspect(aspect: object, context: object = "") -> AspectDecision:
    raw_aspect = "" if aspect is None else str(aspect)
    aspect_key = normalize_surface(raw_aspect)
    context_key = normalize_surface(context)

    if aspect_key in V3_RESIDUAL_EXACT_MAP:
        canonical, aspect_type = V3_RESIDUAL_EXACT_MAP[aspect_key]
        return _v3_mapped(raw_aspect, aspect_key, canonical, aspect_type, "recurring residual full-corpus variant", "v3_residual")

    if aspect_key in V3_RESIDUAL_REJECT:
        return _v3_rejected(raw_aspect, aspect_key, "generic/use-case/brand/noisy residual term")

    if aspect_key in {"tools", "tool"}:
        if re.search(r"\b(app|apps|software|utility|utilities|acer|asus|predator|armoury|armory|control|settings)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "SOFTWARE_EXPERIENCE", "experience", "tool(s) refers to laptop software utilities", "v3_residual_context")
        return _v3_rejected(raw_aspect, aspect_key, "generic tool/use-case term")

    if aspect_key == "ran":
        if re.search(r"\b(game|games|gaming|title|fps|frame)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "GAMING_PERFORMANCE", "experience", "ran describes game execution", "v3_residual_context")
        if re.search(r"\b(smooth|smoothly|fast|perfect|well|hiccup|freeze|lag)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "PERFORMANCE", "experience", "ran describes system performance", "v3_residual_context")
        return _v3_rejected(raw_aspect, aspect_key, "generic past-tense verb")

    if aspect_key in {"loads", "load"}:
        if re.search(r"\b(fast|quick|instant|time|times|slow|speed)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "PERFORMANCE", "experience", "load(s) refers to load-time performance", "v3_residual_context")
        return _v3_rejected(raw_aspect, aspect_key, "generic workload verb")

    if aspect_key == "frame":
        if re.search(r"\b(fps|frames|frame rate|framerate|game|gaming|dlss|generation)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "GAMING_PERFORMANCE", "experience", "frame refers to gaming frame-rate/frame-generation", "v3_residual_context")
        return _v3_rejected(raw_aspect, aspect_key, "ambiguous frame term")

    if aspect_key == "options":
        if re.search(r"\b(port|ports|connect|configuration|feature|features|mode|modes)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "FEATURE_SET", "experience", "options refer to available laptop features/configuration", "v3_residual_context")
        return _v3_rejected(raw_aspect, aspect_key, "generic options term")

    if aspect_key == "stand":
        if re.search(r"\b(kickstand|tablet|angle|lap|desk)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "DESIGN", "experience", "stand refers to kickstand/form factor", "v3_residual_context")
        return _v3_rejected(raw_aspect, aspect_key, "external stand/accessory or generic use")

    if aspect_key in {"buttons", "button"}:
        if re.search(r"\b(keyboard|key|keys)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "KEYBOARD", "experience", "button refers to keyboard/key input", "v3_residual_context")
        return _v3_mapped(raw_aspect, aspect_key, "FEATURE_SET", "experience", "physical control button treated as feature set", "v3_residual_context")

    if aspect_key == "rate":
        if re.search(r"\b(frame|fps|game|gaming)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "GAMING_PERFORMANCE", "experience", "rate refers to frame rate", "v3_residual_context")
        if re.search(r"\b(refresh|screen|display|hz)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "DISPLAY_QUALITY", "experience", "rate refers to display refresh rate", "v3_residual_context")
        return _v3_rejected(raw_aspect, aspect_key, "ambiguous rate term")

    if aspect_key in {"image", "images"}:
        if re.search(r"\b(screen|display|quality|sharp|visual|pixel|resolution|color|colour)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "DISPLAY_QUALITY", "experience", "image refers to visual/display quality", "v3_residual_context")
        return _v3_rejected(raw_aspect, aspect_key, "image content/use-case rather than laptop aspect")

    if aspect_key == "worked":
        if re.search(r"\b(not|never|stopped|failed|issue|problem|fine|well|perfectly)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "RELIABILITY_STABILITY", "experience", "worked refers to operational reliability", "v3_residual_context")
        return _v3_rejected(raw_aspect, aspect_key, "generic verb")

    if aspect_key == "base":
        if re.search(r"\b(hinge|chassis|heavy|metal|plastic|build|solid)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "BUILD_QUALITY", "experience", "base refers to chassis/build", "v3_residual_context")
        return _v3_rejected(raw_aspect, aspect_key, "generic positional term")

    if aspect_key == "capacity":
        # Give the core v3 classifier first chance at battery/storage context.
        core = _classify_aspect_v3_core(aspect, context)
        if core.ontology_status != "unmapped":
            return core
        return _v3_rejected(raw_aspect, aspect_key, "capacity remains ambiguous without battery/storage cue")

    if aspect_key == "feeling":
        if re.search(r"\b(trackpad|touchpad|mousepad)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "TRACKPAD", "experience", "feeling refers to trackpad", "v3_residual_context")
        if re.search(r"\b(keyboard|keys|typing)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "KEYBOARD", "experience", "feeling refers to keyboard", "v3_residual_context")
        if re.search(r"\b(build|premium|solid|material|chassis)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "BUILD_QUALITY", "experience", "feeling refers to build/material quality", "v3_residual_context")
        return _v3_mapped(raw_aspect, aspect_key, "DESIGN", "experience", "general physical feeling treated as design/form factor", "v3_residual_context")

    if aspect_key == "life":
        if re.search(r"\b(battery|hours|charge|runtime)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "BATTERY_LIFE", "experience", "life refers to battery life", "v3_residual_context")
        return _v3_rejected(raw_aspect, aspect_key, "generic life term")

    if aspect_key == "lighted":
        if re.search(r"\b(keyboard|key|keys|wasd)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "KEYBOARD", "experience", "lighted refers to keyboard lighting", "v3_residual_context")
        return _v3_mapped(raw_aspect, aspect_key, "DESIGN", "experience", "lighted treated as lighting/design feature", "v3_residual_context")

    if aspect_key == "pad":
        if re.search(r"\b(touch|track|mouse|cursor|finger|click)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "TRACKPAD", "experience", "pad refers to trackpad/touchpad", "v3_residual_context")
        return _v3_rejected(raw_aspect, aspect_key, "external/cooling pad or ambiguous pad term")

    if aspect_key == "start up":
        if re.search(r"\b(set up|setup|frustrat|easy|difficult)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "EASE_OF_USE", "experience", "start-up refers to setup experience", "v3_residual_context")
        return _v3_mapped(raw_aspect, aspect_key, "PERFORMANCE", "experience", "start-up treated as boot performance", "v3_residual_context")

    if aspect_key == "texture":
        if re.search(r"\b(keyboard|keys|keycaps)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "KEYBOARD", "experience", "texture refers to keys/keycaps", "v3_residual_context")
        return _v3_mapped(raw_aspect, aspect_key, "BUILD_QUALITY", "experience", "texture treated as material/build feel", "v3_residual_context")

    if aspect_key == "bottom cover":
        if re.search(r"\b(upgrade|ssd|ram|access|remove|screw)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "UPGRADEABILITY", "experience", "bottom cover discussed for upgrade/service access", "v3_residual_context")
        return _v3_mapped(raw_aspect, aspect_key, "BUILD_QUALITY", "experience", "bottom cover treated as physical construction", "v3_residual_context")

    if aspect_key == "mux switch":
        return _v3_mapped(raw_aspect, aspect_key, "GRAPHICS_GPU", "specification", "MUX switch is part of GPU/display routing hardware", "v3_residual")

    if aspect_key == "read":
        if re.search(r"\b(write|speed|speeds|ssd|drive|storage)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "PERFORMANCE", "experience", "read refers to storage read/write performance", "v3_residual_context")
        return _v3_rejected(raw_aspect, aspect_key, "generic reading/content term")

    if aspect_key == "depth":
        if re.search(r"\b(bass|treble|sound|audio|speaker)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "AUDIO", "experience", "depth refers to audio depth", "v3_residual_context")
        return _v3_rejected(raw_aspect, aspect_key, "ambiguous depth term")

    if aspect_key == "effects":
        if re.search(r"\b(light|lighting|rgb|color|colour|led)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "DESIGN", "experience", "effects refer to lighting/design effects", "v3_residual_context")
        return _v3_rejected(raw_aspect, aspect_key, "generic effects term")

    if aspect_key == "form":
        if re.search(r"\b(form factor|tablet|design|compact)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "DESIGN", "experience", "form refers to form factor", "v3_residual_context")
        return _v3_rejected(raw_aspect, aspect_key, "generic form term")

    if aspect_key == "longevity":
        if re.search(r"\b(battery|charge|runtime|hours)\b", context_key):
            return _v3_mapped(raw_aspect, aspect_key, "BATTERY_LIFE", "experience", "longevity refers to battery endurance", "v3_residual_context")
        return _v3_mapped(raw_aspect, aspect_key, "RELIABILITY_STABILITY", "experience", "device longevity treated as reliability", "v3_residual_context")

    if aspect_key == "metal":
        return _v3_mapped(raw_aspect, aspect_key, "BUILD_QUALITY", "experience", "metal refers to chassis/build material", "v3_residual")

    if aspect_key == "flex":
        return _v3_mapped(raw_aspect, aspect_key, "BUILD_QUALITY", "experience", "flex refers to chassis/keyboard/screen rigidity", "v3_residual")

    if aspect_key == "exterior":
        return _v3_mapped(raw_aspect, aspect_key, "DESIGN", "experience", "exterior refers to physical design/finish", "v3_residual")

    if aspect_key == "fold":
        return _v3_mapped(raw_aspect, aspect_key, "DESIGN", "experience", "fold refers to convertible/form-factor behaviour", "v3_residual")

    # Otherwise use all main v3 + v2 rules.
    return _classify_aspect_v3_core(aspect, context)
