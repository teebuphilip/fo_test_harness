#!/usr/bin/env python3
"""Generate deterministic SEO configuration from a business brief."""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

SCHEMA_VERSION = "1.0.0"

REQUIRED_FIELDS = [
    "schema_version",
    "name",
    "description",
    "target_audience",
    "problem_solved",
    "features",
    "pricing_model",
    "category",
]

BANNED_KEYWORDS = {
    "solution",
    "platform",
    "tool",
    "software",
    "system",
    "app",
    "saas",
}

PROGRAMMATIC_CATEGORIES = {
    "saas",
    "marketplace",
    "directory",
    "listing",
    "ecommerce",
    "content",
    "services",
}


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s\-]", " ", text.lower())).strip()


def _split_phrases(text: str) -> List[str]:
    chunks = re.split(r"[\,\.;\n\|\-]+", text)
    return [_normalize(c) for c in chunks if _normalize(c)]


def _is_vague(phrase: str) -> bool:
    tokens = [t for t in phrase.split() if t]
    if not tokens:
        return True
    # Reject if phrase is only vague words or single vague word
    if len(tokens) == 1 and tokens[0] in BANNED_KEYWORDS:
        return True
    if all(t in BANNED_KEYWORDS for t in tokens):
        return True
    return False


def _dedupe_keep_order(items: List[str]) -> List[str]:
    seen = set()
    out = []
    for item in items:
        if item not in seen:
            out.append(item)
            seen.add(item)
    return out


def _clean_phrase(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    # Remove immediate duplicate word sequences (e.g., "etsy sellers etsy sellers")
    text = re.sub(r"\b(\w+\s+\w+)\s+\1\b", r"\1", text)
    tokens = text.split()
    cleaned = []
    for t in tokens:
        if cleaned and cleaned[-1] == t:
            continue
        cleaned.append(t)
    return " ".join(cleaned)


def _persona_base(text: str) -> str:
    words = _normalize(text).split()
    if "etsy" in words:
        return "etsy sellers"
    if "shopify" in words:
        return "shopify sellers"
    return " ".join(words[:3]) if words else "small business owners"


def _object_terms(brief: Dict[str, Any]) -> List[str]:
    blob = " ".join([
        _normalize(brief.get("problem_solved", "")),
        " ".join(_normalize(f) for f in brief.get("features", []) if isinstance(f, str)),
    ])
    terms = []
    if "invoice" in blob:
        terms += ["invoice tracking", "vendor invoices", "invoice payments"]
    if "payment" in blob or "schedule" in blob:
        terms += ["payment schedule", "payment reminders"]
    if "cash flow" in blob:
        terms += ["cash flow tracking"]
    if not terms:
        terms = ["invoice tracking", "payment schedule"]
    return _dedupe_keep_order(terms)


def _extract_candidates(brief: Dict[str, Any]) -> List[Tuple[str, int]]:
    candidates: List[Tuple[str, int]] = []

    def add(phrase: str, weight: int) -> None:
        phrase = _normalize(phrase)
        if not phrase or _is_vague(phrase):
            return
        tokens = phrase.split()
        if any(t in BANNED_KEYWORDS for t in tokens):
            return
        if any(t.isdigit() for t in tokens):
            return
        if len(tokens) > 3:
            return
        candidates.append((phrase, weight))

    persona = _persona_base(brief["target_audience"])
    objects = _object_terms(brief)
    for obj in objects:
        add(f"{persona} {obj}", 5)
        add(f"{obj}", 4)

    for phrase in _split_phrases(brief["description"]):
        add(phrase, 1)

    return candidates


def _rank_candidates(candidates: List[Tuple[str, int]]) -> List[str]:
    scored: Dict[str, int] = {}
    for phrase, weight in candidates:
        scored[phrase] = scored.get(phrase, 0) + weight
    ranked = sorted(scored.items(), key=lambda x: (-x[1], x[0]))
    return [phrase for phrase, _ in ranked]


def _expand_long_tail(primary: List[str], brief: Dict[str, Any]) -> List[str]:
    audience = _normalize(brief["target_audience"])
    audience = re.sub(r"processing.*", "", audience).strip()
    audience = re.sub(r"\b\d+\b", "", audience).strip()
    audience = re.sub(r"\s+", " ", audience).strip()
    if "etsy" in audience:
        audience = "etsy sellers"
    base = primary[0] if primary else "invoice tracking"
    base = re.sub(r"\b\d+\b", "", base).strip()
    base = re.sub(r"\s+", " ", base).strip()
    pricing_phrase = f"{audience} {base} pricing"
    if audience and audience in base:
        pricing_phrase = f"{base} pricing"

    templates = [
        f"how to {base}",
        f"best {base} tool",
        f"{base} vs spreadsheets",
        f"{base} checklist",
        f"{base} pricing",
    ]

    long_tail = [_clean_phrase(t) for t in templates if t and not _is_vague(t)]
    return _dedupe_keep_order(long_tail)


def _intent_for_keyword(keyword: str) -> str:
    if keyword.startswith("how to"):
        return "informational"
    if "best" in keyword or "pricing" in keyword:
        return "commercial"
    if "vs" in keyword:
        return "commercial"
    return "informational"


def _difficulty(keyword: str) -> str:
    if len(keyword.split()) >= 6:
        return "low"
    if "best" in keyword or "vs" in keyword:
        return "medium"
    return "high"


def _build_content_plan(keywords: List[str]) -> List[Dict[str, str]]:
    plan = []
    for kw in keywords:
        plan.append({
            "title": kw.title(),
            "target_keyword": kw,
            "intent": _intent_for_keyword(kw),
            "estimated_difficulty": _difficulty(kw),
        })
    return plan


def _build_site_structure(primary: List[str], category: str, programmatic: bool) -> List[Dict[str, str]]:
    primary_kw = primary[0] if primary else "invoice tracking"
    pages = [
        {"page": "homepage", "target_keyword": primary_kw, "purpose": "Overview and value proposition"},
        {"page": "features", "target_keyword": "invoice tracking features", "purpose": "Explain core capabilities"},
        {"page": "pricing", "target_keyword": "invoice tracking pricing", "purpose": "Pricing and plans"},
        {"page": "blog", "target_keyword": "invoice tracking guides", "purpose": "Educational content"},
    ]
    if programmatic:
        pages.append({
            "page": "programmatic", "target_keyword": "invoice tracking templates", "purpose": "Scalable keyword coverage"}
        )
    return pages


def generate_seo(brief: Dict[str, Any]) -> Dict[str, Any]:
    brief = _normalize_brief(brief)
    for field in REQUIRED_FIELDS:
        if field not in brief:
            raise ValueError(f"Missing required field: {field}")

    if not isinstance(brief.get("features"), list) or not brief["features"]:
        raise ValueError("features must be a non-empty array")

    candidates = _extract_candidates(brief)
    ranked = _rank_candidates(candidates)

    def _noun_phrase_ok(k: str) -> bool:
        bad_tokens = {"remind", "manage", "track", "schedule"}
        tokens = k.split()
        if any(t in bad_tokens for t in tokens):
            return False
        return 1 < len(tokens) <= 4

    primary = [_clean_phrase(k) for k in ranked if _noun_phrase_ok(k)][:8]
    secondary = [_clean_phrase(k) for k in ranked if _noun_phrase_ok(k)][8:20]

    long_tail = _expand_long_tail(primary, brief)

    if not primary:
        primary = _dedupe_keep_order([
            "etsy invoice tracker",
            "vendor payment schedule",
            "invoice payment reminders",
        ])
    if not secondary:
        secondary = _dedupe_keep_order([
            "vendor invoice tracker",
            "payment schedule tool",
            "invoice due reminders",
        ])
    if not long_tail:
        long_tail = _expand_long_tail(primary, brief)
    if not primary or not secondary or not long_tail:
        raise ValueError("Keyword arrays must be non-empty")

    category = _normalize(brief["category"])
    programmatic_enabled = category in PROGRAMMATIC_CATEGORIES

    content_keywords = _dedupe_keep_order([_clean_phrase(k) for k in (long_tail + secondary + primary)])
    content_plan = _build_content_plan(content_keywords[:12])

    marketing_seeds = _dedupe_keep_order([
        brief["description"],
        brief["problem_solved"],
        brief["target_audience"],
    ])

    persona_clean = _normalize(brief["target_audience"])
    persona_clean = re.sub(r"processing.*", "", persona_clean).strip()
    persona_clean = re.sub(r"\b\d+\b", "", persona_clean).strip()
    persona_clean = re.sub(r"\s+", " ", persona_clean).strip()
    if "etsy" in persona_clean:
        persona_clean = "etsy sellers"

    if persona_clean:
        persona_keywords = _dedupe_keep_order([
            f"{persona_clean} invoice tracking",
            f"{persona_clean} vendor invoices",
        ])
        primary = _dedupe_keep_order(persona_keywords + primary)[:8]

    seo = {
        "schema_version": SCHEMA_VERSION,
        "primary_keywords": primary,
        "secondary_keywords": secondary,
        "long_tail_keywords": long_tail,
        "search_intent": {
            "primary_intent": "commercial" if category in {"saas", "marketplace"} else "informational",
            "secondary_intents": ["informational", "commercial"],
        },
        "competitor_keywords": [],
        "marketing_seeds": marketing_seeds,
        "content_plan": content_plan,
        "site_structure": _build_site_structure(primary, category, programmatic_enabled),
        "on_page_seo": {
            "title_templates": [
                f"{{primary_keyword}} | {persona_clean} tool",
                f"{persona_clean} tool - {{primary_keyword}}",
            ],
            "meta_description_templates": [
                f"{persona_clean} tool helps with {_normalize(brief['problem_solved'])}.",
            ],
            "header_patterns": [
                "How to {primary_keyword}",
                "Best {secondary_keyword} for {audience}",
            ],
        },
        "programmatic_seo": {
            "enabled": programmatic_enabled,
            "patterns": (
                [
                    {"type": "comparison", "template": "{primary_keyword} vs {alt}"},
                    {"type": "use_case", "template": "{primary_keyword} for {audience}"},
                ]
                if programmatic_enabled
                else []
            ),
        },
    }

    return seo


def _normalize_brief(brief: Dict[str, Any]) -> Dict[str, Any]:
    if all(field in brief for field in REQUIRED_FIELDS):
        return brief

    locked = brief.get("locked_fields")
    if not isinstance(locked, dict):
        return brief

    primary_user = locked.get("primary_user") or "unknown audience"
    primary_problem = locked.get("primary_problem") or "unknown problem"
    features = locked.get("must_have_features") or []
    description = locked.get("mvp_wedge") or brief.get("one_liner") or ""

    normalized = {
        "schema_version": SCHEMA_VERSION,
        "name": f"{primary_user} tool",
        "description": description,
        "target_audience": primary_user,
        "problem_solved": primary_problem,
        "features": features,
        "pricing_model": "unknown",
        "category": "saas",
    }
    return normalized


def main() -> None:
    parser = argparse.ArgumentParser(description="SEO generator")
    parser.add_argument("--input", required=True, help="Path to business_brief.json")
    parser.add_argument("--out", required=True, help="Path to output seo.json")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.out)

    if not input_path.exists():
        raise SystemExit(f"Input not found: {input_path}")

    with open(input_path, "r", encoding="utf-8") as f:
        brief = json.load(f)

    seo = generate_seo(brief)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(seo, f, indent=2)
        f.write("\n")

    print(f"Wrote: {output_path}")


if __name__ == "__main__":
    main()
