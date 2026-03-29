#!/usr/bin/env python3
"""Build business brief + one-liner from hero JSON."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, List


def _read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.strip() + "\n", encoding="utf-8")


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _pick_primary_user(hero_answers: Dict[str, Any]) -> str:
    users = hero_answers.get("Q2_target_user") or []
    if isinstance(users, list) and users:
        return _clean(str(users[0]))
    return _clean(hero_answers.get("Q1_problem_customer", "")) or "Primary users"


def _pick_features(hero_answers: Dict[str, Any]) -> List[str]:
    feats = hero_answers.get("Q4_must_have_features") or []
    cleaned = [str(f).strip() for f in feats if str(f).strip()]
    return cleaned[:5] if cleaned else ["Manual data entry", "Basic tracking", "Email reminders"]


def _pricing_from_q8(hero_answers: Dict[str, Any]) -> str:
    q8 = hero_answers.get("Q8_integrations")  # placeholder if Q8 not present
    pricing = hero_answers.get("Q8_pricing_model") or hero_answers.get("Q8_payments") or ""
    if isinstance(pricing, str) and pricing.strip():
        return _clean(pricing)
    # Fallback: try to infer from free-form Q8 text stored in constraints/other
    if isinstance(q8, str) and q8.strip():
        return _clean(q8)
    return "unknown"


def _build_one_liner(persona: str, problem: str, features: List[str]) -> str:
    problem = _clean(problem)
    persona = _clean(persona)
    feature_hint = features[0].lower() if features else "manual tracking"
    return (
        f"For {persona}, {problem} We use {feature_hint} instead of spreadsheets."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Build brief + one-liner from hero JSON")
    parser.add_argument("--hero", required=True, help="Path to hero JSON")
    parser.add_argument("--out-brief", required=True, help="Path to output business brief JSON")
    parser.add_argument("--out-one-liner", required=True, help="Path to output one-liner text")
    args = parser.parse_args()

    hero = _read_json(Path(args.hero))
    hero_answers = hero.get("hero_answers") or {}

    startup_name = _clean(hero.get("startup_name") or "")
    startup_id = _clean(hero.get("startup_idea_id") or "")
    description = _clean(hero.get("startup_description") or "")

    persona = _pick_primary_user(hero_answers)
    problem = _clean(hero_answers.get("Q1_problem_customer") or "") or "A recurring workflow problem"
    features = _pick_features(hero_answers)
    pricing = _pricing_from_q8(hero_answers)

    brief = {
        "schema_version": "1.0.0",
        "name": startup_name or (startup_id.title() if startup_id else "Unknown"),
        "description": description or _build_one_liner(persona, problem, features),
        "target_audience": persona,
        "problem_solved": problem,
        "features": features,
        "pricing_model": pricing,
        "category": "saas",
    }

    one_liner = _build_one_liner(persona, problem, features)

    _write_json(Path(args.out_brief), brief)
    _write_text(Path(args.out_one_liner), one_liner)

    print(f"Wrote: {args.out_brief}")
    print(f"Wrote: {args.out_one_liner}")


if __name__ == "__main__":
    main()
