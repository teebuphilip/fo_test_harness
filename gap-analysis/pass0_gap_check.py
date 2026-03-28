#!/usr/bin/env python3
"""Pass 0 Gap Check: deterministic validation + optional research + builder brief output."""

from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from pass0_research import (
    ResearchError,
    OpenAIResearchProvider,
    AnthropicResearchProvider,
    FileResearchProvider,
)

SCHEMA_VERSION = "0.1.0"

DECISION_BUILD = "BUILD_APPROVED"
DECISION_REPOSITION = "REPOSITION_AND_BUILD"
DECISION_HOLD = "HOLD"
DECISION_KILL = "KILL"

ALLOWED_GAP_TYPES = {
    "workflow gap",
    "distribution gap",
    "pricing gap",
    "compliance gap",
    "integration gap",
}

MIN_CONFIDENCE = 60
MIN_BUILD_DISTRIBUTION = 80
MIN_BUILD_WEDGE = 80

DEFAULT_ALLOWLIST = [
    "etsy",
    "shopify",
    "amazon",
    "fbm",
    "fba",
    "indiehackers",
    "indie hackers",
    "substack",
    "gumroad",
    "wix",
    "squarespace",
    "woocommerce",
    "webflow",
    "upwork",
    "fiverr",
]

ALLOWED_CHANNELS = {
    "reddit",
    "indiehackers",
    "indie hackers",
    "hacker news",
    "product hunt",
    "twitter",
    "x",
    "facebook groups",
    "linkedin",
    "discord",
    "slack communities",
}

MANUAL_FEATURE_BANK = [
    "Manual invoice entry form",
    "Vendor list management",
    "Payment schedule calculator",
    "Invoice status tracking",
    "Payment due reminders",
    "Cash flow calendar view",
]
@dataclass
class DeterministicResult:
    idea_text: str
    intake_summary: str
    primary_user_candidates: List[str]
    primary_problem: Optional[str]
    current_alternative: Optional[str]
    alternative_source: Optional[str]
    must_have_features: List[str]
    primary_gap_type: Optional[str]
    mvp_wedge: Optional[str]
    fatal_flags: List[Dict[str, str]]
    warnings: List[str]
    explicit_non_features: List[str]
    non_goals: List[str]


def _load_allowlist(explicit_allowlist: Optional[List[str]]) -> List[str]:
    if explicit_allowlist is not None:
        return [x.lower() for x in explicit_allowlist if x]

    env_allowlist = os.getenv("PASS0_ALLOWLIST")
    if env_allowlist:
        return [x.strip().lower() for x in env_allowlist.split(",") if x.strip()]

    allowlist_path = Path(__file__).resolve().parent / "pass0_allowlist.txt"
    if allowlist_path.exists():
        raw = allowlist_path.read_text(encoding="utf-8")
        tokens = [t.strip().lower() for t in raw.replace("\n", ",").split(",") if t.strip()]
        if tokens:
            return tokens

    return DEFAULT_ALLOWLIST


def _has_numeric_specificity(text: Optional[str]) -> bool:
    if not text:
        return False
    return any(ch.isdigit() for ch in text)


def _select_ranked_persona(research: Dict[str, Any]) -> Optional[str]:
    ranked = research.get("ranked_personas")
    if isinstance(ranked, list) and ranked:
        valid = []
        for entry in ranked:
            if not isinstance(entry, dict):
                continue
            persona = entry.get("persona")
            score = entry.get("score")
            if isinstance(persona, str) and isinstance(score, (int, float)):
                valid.append((score, persona))
        if valid:
            valid.sort(reverse=True, key=lambda x: x[0])
            return valid[0][1]
    return None


def _get_nested(data: Dict[str, Any], *keys: str) -> Optional[Any]:
    cur: Any = data
    for key in keys:
        if not isinstance(cur, dict) or key not in cur:
            return None
        cur = cur[key]
    return cur


def _normalize_text(value: str) -> str:
    return "".join(ch.lower() for ch in value if ch.isalnum() or ch.isspace()).strip()


def _unique_strings(values: List[str]) -> List[str]:
    seen = set()
    unique = []
    for value in values:
        norm = _normalize_text(value)
        if norm and norm not in seen:
            unique.append(value.strip())
            seen.add(norm)
    return unique


def _dedupe_keep_order(values: List[str]) -> List[str]:
    seen = set()
    out = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def _infer_alternative(idea_text: str) -> Optional[str]:
    text = idea_text.lower()
    if "invoice" in text or "payment schedule" in text:
        return "Spreadsheets + calendar reminders"
    if "crm" in text:
        return "Spreadsheets + email threads"
    return None


def _infer_gap_type(problem: Optional[str], idea_text: str) -> Optional[str]:
    text = " ".join([problem or "", idea_text]).lower()
    if "manual" in text or "tracking" in text or "messy" in text:
        return "workflow gap"
    return None


def _build_wedge(primary_user: Optional[str], primary_problem: Optional[str], current_alternative: Optional[str]) -> Optional[str]:
    if not primary_user or not primary_problem or not current_alternative:
        return None
    return (
        f"For {primary_user}, we solve {primary_problem.lower()} without relying on {current_alternative}."
    )


def _build_intake_summary(intake: Dict[str, Any]) -> str:
    parts = []
    idea_text = intake.get("idea_text")
    if isinstance(idea_text, str) and idea_text.strip():
        parts.append(idea_text.strip())
    for path in [
        ("startup_name",),
        ("summary",),
        ("block_a", "pass_1", "one_liner"),
        ("block_b", "pass_1", "one_liner"),
        ("block_a", "pass_2", "problem_statement"),
        ("block_b", "pass_1", "core_problem"),
    ]:
        value = _get_nested(intake, *path)
        if isinstance(value, str) and value.strip():
            parts.append(value.strip())
    return " | ".join(parts)


def _normalize_intake_for_pass0(intake: Dict[str, Any]) -> Dict[str, Any]:
    if "idea_text" in intake and "startup_name" not in intake:
        idea_text = intake.get("idea_text", "")
        return {
            "startup_name": idea_text,
            "summary": idea_text,
            "block_a": {
                "pass_1": {"one_liner": idea_text, "target_user_persona": ""},
                "pass_2": {"problem_statement": ""},
                "pass_3": {"tier_1_core_features": []},
            },
            "block_b": {"pass_1": {"one_liner": ""}},
            "idea_text": idea_text,
        }
    return intake


def _collect_constraints(intake: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    explicit_non_features = []
    non_goals = []
    non_features = _get_nested(intake, "block_a", "pass_3", "explicit_non_features")
    if isinstance(non_features, list):
        explicit_non_features = [f for f in non_features if isinstance(f, str)]

    goals = _get_nested(intake, "block_b", "pass_2", "non_goals")
    if isinstance(goals, list):
        non_goals = [g for g in goals if isinstance(g, str)]

    return explicit_non_features, non_goals


def run_deterministic_checks(intake: Dict[str, Any]) -> DeterministicResult:
    intake = _normalize_intake_for_pass0(intake)
    idea_text = _get_nested(intake, "startup_name") or _get_nested(intake, "summary") or intake.get("idea_text") or ""
    intake_summary = _build_intake_summary(intake)
    explicit_non_features, non_goals = _collect_constraints(intake)

    candidates = []
    for path in [
        ("block_a", "pass_1", "target_user_persona"),
        ("block_b", "pass_1", "target_user"),
    ]:
        value = _get_nested(intake, *path)
        if isinstance(value, str) and value.strip():
            candidates.append(value.strip())
    primary_user_candidates = _unique_strings(candidates)

    fatal_flags: List[Dict[str, str]] = []
    warnings: List[str] = []

    if not primary_user_candidates:
        fatal_flags.append({"code": "PRIMARY_USER_MISSING", "detail": "No primary user found."})
    elif len(primary_user_candidates) > 1:
        fatal_flags.append({
            "code": "PRIMARY_USER_AMBIGUOUS",
            "detail": "Multiple primary users found. Exactly one is required.",
        })

    primary_problem = _get_nested(intake, "block_a", "pass_2", "problem_statement")
    if not primary_problem:
        primary_problem = _get_nested(intake, "block_b", "pass_1", "core_problem")
    if not primary_problem:
        fatal_flags.append({"code": "PRIMARY_PROBLEM_MISSING", "detail": "No primary problem found."})

    must_have_features = []
    features = _get_nested(intake, "block_a", "pass_3", "tier_1_core_features")
    if isinstance(features, list):
        must_have_features = [f for f in features if isinstance(f, str)]
    else:
        features = _get_nested(intake, "block_b", "pass_2", "must_have_features")
        if isinstance(features, list):
            must_have_features = [f for f in features if isinstance(f, str)]

    current_alternative = _get_nested(intake, "block_a", "pass_2", "current_alternative")
    alternative_source = None
    if current_alternative:
        alternative_source = "explicit"
    else:
        inferred = _infer_alternative(idea_text)
        if inferred:
            current_alternative = inferred
            alternative_source = "inferred"
            warnings.append("Current alternative inferred from idea text.")

    if not current_alternative:
        fatal_flags.append({"code": "CURRENT_ALTERNATIVE_MISSING", "detail": "No current alternative identified."})

    primary_gap_type = _infer_gap_type(primary_problem, idea_text)
    if not primary_gap_type:
        warnings.append("Primary gap type could not be inferred.")

    primary_user = primary_user_candidates[0] if len(primary_user_candidates) == 1 else None
    mvp_wedge = _build_wedge(primary_user, primary_problem, current_alternative)
    if not mvp_wedge:
        warnings.append("MVP wedge could not be deterministically generated.")

    return DeterministicResult(
        idea_text=idea_text,
        intake_summary=intake_summary,
        primary_user_candidates=primary_user_candidates,
        primary_problem=primary_problem,
        current_alternative=current_alternative,
        alternative_source=alternative_source,
        must_have_features=must_have_features,
        primary_gap_type=primary_gap_type,
        mvp_wedge=mvp_wedge,
        fatal_flags=fatal_flags,
        warnings=warnings,
        explicit_non_features=explicit_non_features,
        non_goals=non_goals,
    )


def _is_specific_persona(persona: Optional[str], allowlist: List[str]) -> bool:
    if not persona:
        return False
    lowered = persona.lower()
    generic_terms = [
        "small business",
        "business owners",
        "consulting firm",
        "consulting firms",
        "smb",
        "small company",
    ]
    if any(term in lowered for term in generic_terms):
        # Require extra qualifiers beyond generic.
        return any(ch.isdigit() for ch in persona) or any(keyword in lowered for keyword in allowlist)
    return True


def _is_specific_wedge(wedge: Optional[str], allowlist: List[str]) -> bool:
    if not wedge:
        return False
    lowered = wedge.lower()
    return any(ch.isdigit() for ch in wedge) or any(keyword in lowered for keyword in allowlist)


def _passes_strict_gate(research: Optional[Dict[str, Any]], allowlist: List[str]) -> bool:
    if not research:
        return False
    persona_ok = _is_specific_persona(research.get("recommended_primary_user"), allowlist)
    wedge_ok = _is_specific_wedge(research.get("mvp_wedge"), allowlist)
    if allowlist:
        persona_text = (research.get("recommended_primary_user") or "").lower()
        wedge_text = (research.get("mvp_wedge") or "").lower()
        allow_ok = any(keyword in persona_text for keyword in allowlist) and any(keyword in wedge_text for keyword in allowlist)
        return persona_ok and wedge_ok and allow_ok
    return persona_ok and wedge_ok


def _matches_wedge_template(wedge: Optional[str]) -> bool:
    if not wedge:
        return False
    lowered = wedge.lower()
    if "for " not in lowered:
        return False
    if "processing" not in lowered:
        return False
    if "instead of" not in lowered:
        return False
    consequence_keywords = [
        "late",
        "penalt",
        "missed",
        "delay",
        "cash flow",
        "stockout",
        "chargeback",
        "supplier",
        "discount",
    ]
    if not any(k in lowered for k in consequence_keywords):
        return False
    return _has_numeric_specificity(wedge)


def _filter_banned_features(features: List[str], banned_phrases: List[str]) -> List[str]:
    if not features or not banned_phrases:
        return features
    lowered_banned = [b.lower() for b in banned_phrases]
    filtered = []
    for feature in features:
        f_lower = feature.lower()
        if any(b in f_lower for b in lowered_banned):
            continue
        filtered.append(feature)
    return filtered


def _filter_manual_first(features: List[str]) -> List[str]:
    if not features:
        return features
    banned = [
        "upload",
        "pdf",
        "ocr",
        "integration",
        "sync",
        "automated",
        "automation",
        "auto-",
        "api",
    ]
    filtered = []
    for feature in features:
        f_lower = feature.lower()
        if any(b in f_lower for b in banned):
            continue
        filtered.append(feature)
    return filtered


def _fill_manual_features(features: List[str]) -> List[str]:
    existing = _dedupe_keep_order([f for f in features if f])
    for candidate in MANUAL_FEATURE_BANK:
        if candidate not in existing:
            existing.append(candidate)
        if len(existing) >= 3:
            break
    return existing[:3]


def _score(d: DeterministicResult, research: Optional[Dict[str, Any]], allowlist: List[str]) -> Dict[str, int]:
    persona_score = 100 if len(d.primary_user_candidates) == 1 else 20 if d.primary_user_candidates else 0
    alternative_score = 100 if d.current_alternative and d.alternative_source == "explicit" else 60 if d.current_alternative else 0

    gap_score = 20
    distribution_score = 20
    wedge_score = 20

    if research:
        if research.get("recommended_primary_user"):
            persona_score = 100 if _is_specific_persona(research.get("recommended_primary_user"), allowlist) else 40
        if research.get("current_alternative"):
            alternative_score = 100
        if research.get("primary_gap_type") in ALLOWED_GAP_TYPES:
            gap_score = 80
        if research.get("persona_channels"):
            channels = [str(c).strip().lower() for c in research.get("persona_channels", []) if str(c).strip()]
            allowed_hits = [c for c in channels if any(a in c for a in ALLOWED_CHANNELS)]
            if len(allowed_hits) >= 2:
                distribution_score = 80
        if research.get("mvp_wedge"):
            wedge_score = 80 if _is_specific_wedge(research.get("mvp_wedge"), allowlist) else 30

    total = int((persona_score + alternative_score + gap_score + distribution_score + wedge_score) / 5)
    return {
        "persona_clarity": persona_score,
        "alternative_mapping": alternative_score,
        "gap_thesis": gap_score,
        "distribution_fit": distribution_score,
        "wedge_validity": wedge_score,
        "total": total,
    }


def _decide(d: DeterministicResult, scores: Dict[str, int], research: Optional[Dict[str, Any]], allowlist: List[str]) -> Tuple[str, List[Dict[str, str]]]:
    fatal_flags = list(d.fatal_flags)

    if research:
        resolved = set()
        if research.get("recommended_primary_user"):
            resolved.update({"PRIMARY_USER_MISSING", "PRIMARY_USER_AMBIGUOUS"})
        if research.get("primary_problem"):
            resolved.add("PRIMARY_PROBLEM_MISSING")
        if research.get("current_alternative"):
            resolved.add("CURRENT_ALTERNATIVE_MISSING")
        fatal_flags = [flag for flag in fatal_flags if flag.get("code") not in resolved]

    if research and research.get("disqualifying_signals"):
        # Treat as warnings only; not automatically fatal.
        d.warnings.append("Disqualifying signals: " + "; ".join(research.get("disqualifying_signals", [])))

    if fatal_flags:
        return DECISION_KILL, fatal_flags

    if not research:
        return DECISION_HOLD, fatal_flags

    confidence = research.get("confidence")
    if isinstance(confidence, (int, float)) and confidence < MIN_CONFIDENCE:
        d.warnings.append(f"Research confidence below floor ({confidence} < {MIN_CONFIDENCE}).")
        return DECISION_HOLD, fatal_flags

    if not _passes_strict_gate(research, allowlist):
        d.warnings.append("Strict persona/wedge gate failed. Require platform/niche or numeric specificity.")
        return DECISION_HOLD, fatal_flags

    if not _matches_wedge_template(research.get("mvp_wedge")):
        d.warnings.append("Wedge does not match required template or lacks numeric specificity.")
        return DECISION_HOLD, fatal_flags

    build_readiness = research.get("build_readiness")
    if build_readiness and str(build_readiness).upper() != "BUILD":
        d.warnings.append("Research marked build_readiness as HOLD.")
        return DECISION_HOLD, fatal_flags

    channels = [str(c).strip().lower() for c in research.get("persona_channels", []) if str(c).strip()]
    allowed_hits = [c for c in channels if any(a in c for a in ALLOWED_CHANNELS)]
    if len(allowed_hits) < 2:
        d.warnings.append("Distribution gate failed. Require at least 2 reachable channels (Reddit/IndieHackers/etc.).")
        return DECISION_HOLD, fatal_flags

    features = research.get("must_have_features") if research else []
    if not isinstance(features, list) or len(features) < 1:
        d.warnings.append("Must provide at least 1 must_have_feature; auto-filling manual-first defaults.")
        features = []

    manual_features = _filter_manual_first(features)
    manual_features = _fill_manual_features(manual_features)

    if scores["distribution_fit"] < MIN_BUILD_DISTRIBUTION or scores["wedge_validity"] < MIN_BUILD_WEDGE:
        d.warnings.append("Per-dimension floor not met (distribution/wedge).")
        return DECISION_REPOSITION, fatal_flags

    saturation = (research.get("saturation_signal") or "").upper()
    if saturation == "HIGH":
        d.warnings.append("High saturation detected. Requires reposition.")
        return DECISION_REPOSITION, fatal_flags

    total = scores["total"]

    if saturation == "HIGH" and total < 70:
        return DECISION_REPOSITION, fatal_flags

    if total >= 75:
        return DECISION_BUILD, fatal_flags
    if total >= 55:
        return DECISION_REPOSITION, fatal_flags
    return DECISION_HOLD, fatal_flags


def _build_locked_fields(d: DeterministicResult, research: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    primary_user = None
    primary_problem = d.primary_problem
    primary_gap_type = d.primary_gap_type
    current_alternative = d.current_alternative
    mvp_wedge = d.mvp_wedge
    must_have_features = d.must_have_features

    if research:
        primary_user = research.get("recommended_primary_user") or primary_user
        primary_problem = research.get("primary_problem") or primary_problem
        gap_type = research.get("primary_gap_type")
        if gap_type in ALLOWED_GAP_TYPES:
            primary_gap_type = gap_type
        current_alternative = research.get("current_alternative") or current_alternative
        mvp_wedge = research.get("mvp_wedge") or mvp_wedge
        if isinstance(research.get("must_have_features"), list):
            must_have_features = research.get("must_have_features")[:3]

    if not primary_user and len(d.primary_user_candidates) == 1:
        primary_user = d.primary_user_candidates[0]

    return {
        "primary_user": primary_user,
        "primary_problem": primary_problem,
        "primary_gap_type": primary_gap_type,
        "mvp_wedge": mvp_wedge,
        "current_alternative": current_alternative,
        "must_have_features": _fill_manual_features(
            _filter_manual_first(
                _filter_banned_features(
                    must_have_features,
                    d.explicit_non_features + d.non_goals,
                )
            )
        ),
    }


def _build_one_liner(locked_fields: Dict[str, Any]) -> Optional[str]:
    primary_user = locked_fields.get("primary_user")
    mvp_wedge = locked_fields.get("mvp_wedge")
    if not primary_user or not mvp_wedge:
        return None
    return mvp_wedge


def _tighten_wedge_language(wedge: Optional[str]) -> Optional[str]:
    if not wedge:
        return wedge
    replacements = {
        "automate invoice processing": "streamline manual invoice tracking",
        "automated invoice processing": "manual invoice tracking workflow",
        "automate payment scheduling": "manual payment schedule calculator",
        "automated payment scheduling": "manual payment schedule calculator",
        "automation": "workflow",
        "instead of manual tracking of invoices and payment schedules": "instead of spreadsheets",
        "instead of manual tracking and payment scheduling": "instead of spreadsheets",
    }
    updated = wedge
    for src, dst in replacements.items():
        updated = re.sub(src, dst, updated, flags=re.IGNORECASE)
    # De-duplicate common repeated phrases
    updated = re.sub(r"(manual invoice tracking)(?:\s+\1)+", r"\1", updated, flags=re.IGNORECASE)
    updated = re.sub(r"\s+instead of\s+manual\s+tracking\s+and\s+payment\s+scheduling", " instead of spreadsheets", updated, flags=re.IGNORECASE)
    updated = re.sub(r"\s+", " ", updated).strip()
    return updated


def _validate_output(output: Dict[str, Any]) -> None:
    required = ["schema_version", "decision_status", "locked_fields", "one_liner"]
    for key in required:
        if key not in output:
            raise ValueError(f"Output missing required field: {key}")

    locked = output["locked_fields"]
    for key in [
        "primary_user",
        "primary_problem",
        "primary_gap_type",
        "mvp_wedge",
        "current_alternative",
        "must_have_features",
        "must_not_build",
    ]:
        if key not in locked:
            raise ValueError(f"Locked fields missing required field: {key}")


def run_gap_check(
    intake: Dict[str, Any],
    research_provider: Optional[str] = None,
    research_model: Optional[str] = None,
    research_from_file: Optional[str] = None,
    verbose: bool = False,
    persona_allowlist: Optional[List[str]] = None,
) -> Dict[str, Any]:
    allowlist = _load_allowlist(persona_allowlist)
    print("[pass0] Starting Pass 0 gap check")
    deterministic = run_deterministic_checks(intake)
    print(f"[pass0] Deterministic checks complete. Primary user candidates: {len(deterministic.primary_user_candidates)}")
    if verbose:
        print(f"[pass0] Primary user candidates: {deterministic.primary_user_candidates}")
        print(f"[pass0] Warnings: {deterministic.warnings}")
    research_data = None
    research_meta = {
        "enabled": False,
        "provider": None,
        "model": None,
    }

    if research_from_file:
        print(f"[pass0] Research enabled via file: {research_from_file}")
        provider = FileResearchProvider(research_from_file)
        research_data = provider.research(
            deterministic.idea_text,
            deterministic.intake_summary,
            "; ".join(deterministic.explicit_non_features),
            "; ".join(deterministic.non_goals),
            ", ".join(allowlist),
        )
        research_meta.update({"enabled": True, "provider": "file", "model": None})
    elif research_provider == "openai":
        print("[pass0] Research enabled via OpenAI")
        provider = OpenAIResearchProvider(model=research_model)
        research_data = provider.research(
            deterministic.idea_text,
            deterministic.intake_summary,
            "; ".join(deterministic.explicit_non_features),
            "; ".join(deterministic.non_goals),
            ", ".join(allowlist),
        )
        research_meta.update({"enabled": True, "provider": "openai", "model": provider.model})
    elif research_provider == "anthropic":
        print("[pass0] Research enabled via Anthropic")
        provider = AnthropicResearchProvider(model=research_model)
        research_data = provider.research(
            deterministic.idea_text,
            deterministic.intake_summary,
            "; ".join(deterministic.explicit_non_features),
            "; ".join(deterministic.non_goals),
            ", ".join(allowlist),
        )
        research_meta.update({"enabled": True, "provider": "anthropic", "model": provider.model})
    else:
        print("[pass0] Research disabled (deterministic-only mode)")

    cost_meta = None
    usage_meta = None
    if research_data:
        cost_meta = research_data.pop("_cost", None)
        usage_meta = research_data.pop("_usage", None)

    if research_data:
        ranked_persona = _select_ranked_persona(research_data)
        if ranked_persona:
            research_data["recommended_primary_user"] = ranked_persona
            if verbose:
                print(f"[pass0] Ranked persona selected: {ranked_persona}")
        elif verbose and research_data.get("ranked_personas"):
            print("[pass0] Ranked personas present but none valid.")

    scores = _score(deterministic, research_data, allowlist)
    decision_status, fatal_flags = _decide(deterministic, scores, research_data, allowlist)
    locked_fields = _build_locked_fields(deterministic, research_data)
    locked_fields["mvp_wedge"] = _tighten_wedge_language(locked_fields.get("mvp_wedge"))
    locked_fields["must_not_build"] = decision_status != DECISION_BUILD

    one_liner = _build_one_liner(locked_fields)
    if decision_status != DECISION_BUILD:
        one_liner = None
    print(f"[pass0] Decision: {decision_status}")
    if verbose:
        print(f"[pass0] Scores: {scores}")
        print(f"[pass0] Locked fields: {locked_fields}")
        print(f"[pass0] Numeric specificity (persona): {_has_numeric_specificity(locked_fields.get('primary_user'))}")
        print(f"[pass0] Numeric specificity (wedge): {_has_numeric_specificity(locked_fields.get('mvp_wedge'))}")

    output = {
        "schema_version": SCHEMA_VERSION,
        "decision_status": decision_status,
        "scores": scores,
        "fatal_flags": fatal_flags,
        "warnings": deterministic.warnings,
        "locked_fields": locked_fields,
        "one_liner": one_liner,
        "research_summary": {
            "enabled": research_meta["enabled"],
            "provider": research_meta["provider"],
            "model": research_meta["model"],
            "notes": research_data.get("notes") if research_data else None,
            "saturation_signal": research_data.get("saturation_signal") if research_data else None,
            "confidence": research_data.get("confidence") if research_data else None,
            "input_tokens": cost_meta.get("input_tokens") if cost_meta else None,
            "output_tokens": cost_meta.get("output_tokens") if cost_meta else None,
            "cost_usd": cost_meta.get("cost_usd") if cost_meta else None,
        },
    }

    _validate_output(output)
    if cost_meta and cost_meta.get("cost_usd") is not None:
        cost_val = float(cost_meta.get("cost_usd"))
        rounded = (int(cost_val * 100 + 0.999999) / 100.0)
        print(f"[pass0] AI research cost: ${rounded:.2f}")
    else:
        print("[pass0] AI research cost: $0.00")
    return output


def _load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: str, data: Dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Pass 0 Gap Check")
    parser.add_argument("--input", required=True, help="Path to intake JSON")
    parser.add_argument("--out", required=False, help="Path to write decision JSON")
    parser.add_argument("--brief-out", required=False, help="Path to write builder brief JSON")
    parser.add_argument("--one-liner-out", required=False, help="Path to write one-liner text")
    parser.add_argument("--research-provider", choices=["openai", "anthropic"], help="Optional research provider")
    parser.add_argument("--research-model", help="Override model name")
    parser.add_argument("--research-from-file", help="Path to JSON research response")
    parser.add_argument("--verbose", action="store_true", help="Print verbose progress output")
    parser.add_argument(
        "--persona-allowlist",
        help="Comma-separated keywords required in persona/wedge (default: Etsy/Shopify/Amazon/etc.)",
    )

    args = parser.parse_args()

    intake = _load_json(args.input)

    allowlist = None
    if args.persona_allowlist:
        allowlist = [x.strip().lower() for x in args.persona_allowlist.split(",") if x.strip()]

    try:
        output = run_gap_check(
            intake,
            research_provider=args.research_provider,
            research_model=args.research_model,
            research_from_file=args.research_from_file,
            verbose=args.verbose,
            persona_allowlist=allowlist,
        )
    except ResearchError as exc:
        raise SystemExit(f"Research failed: {exc}")

    if args.out:
        _write_json(args.out, output)
    else:
        print(json.dumps(output, indent=2))

    if args.brief_out:
        brief = {
            "locked_fields": output["locked_fields"],
            "one_liner": output["one_liner"],
        }
        _write_json(args.brief_out, brief)

    if args.one_liner_out:
        with open(args.one_liner_out, "w", encoding="utf-8") as f:
            f.write(output["one_liner"] or "")
            f.write("\n")


if __name__ == "__main__":
    main()
