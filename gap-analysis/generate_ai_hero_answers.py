#!/usr/bin/env python3
"""Generate Q1-Q10 hero answer text from pipeline artifacts."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, List


def _read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _list_or_default(items: List[str], default: List[str]) -> List[str]:
    cleaned = [i.strip() for i in items if i and i.strip()]
    return cleaned if cleaned else default


def _infer_name(name_suggestions: Path | None, fallback: str) -> str:
    if name_suggestions and name_suggestions.exists():
        data = _read_json(name_suggestions)
        picked = data.get("picked") or {}
        slug = picked.get("slug") or picked.get("name")
        if slug:
            return _clean(slug).replace(" ", "_").lower()
    return _clean(fallback).replace(" ", "_").lower()


def _maybe_integrations(features: List[str]) -> str:
    if any("integrat" in f.lower() for f in features):
        return "Basic integrations mentioned in features (lightweight only)."
    return "No external integrations required for v1."

def _load_external_api_keywords() -> List[str]:
    default_keywords = [
        "integrat",
        "integration",
        "sync",
        "api",
        "webhook",
        "import",
        "export",
        "shopify",
        "quickbooks",
        "xero",
        "stripe",
        "paypal",
        "gmail",
        "outlook",
        "slack",
        "zapier",
        "salesforce",
        "hubspot",
    ]
    keywords_path = Path(__file__).resolve().parent / "external_api_keywords.txt"
    if not keywords_path.exists():
        return default_keywords
    lines = keywords_path.read_text(encoding="utf-8").splitlines()
    custom = [ln.strip().lower() for ln in lines if ln.strip() and not ln.strip().startswith("#")]
    return custom or default_keywords

def _needs_external_api(brief: Dict[str, Any], one_liner: str) -> bool:
    hay = " ".join(
        [
            str(brief.get("description", "")),
            str(brief.get("problem_solved", "")),
            str(brief.get("target_audience", "")),
            str(one_liner),
        ]
        + [str(f) for f in brief.get("features", [])]
    ).lower()
    keywords = _load_external_api_keywords()
    return any(k in hay for k in keywords)

def _build_answers(brief: Dict[str, Any], one_liner: str) -> str:
    persona = _clean(brief.get("target_audience") or "Target users")
    problem = _clean(brief.get("problem_solved") or "A recurring workflow problem")
    features = _list_or_default(
        [str(f) for f in brief.get("features", [])],
        ["Manual data entry", "Basic tracking", "Email reminders"],
    )
    pricing = _clean(brief.get("pricing_model") or "Subscription (price TBD)")
    description = _clean(brief.get("description") or one_liner)

    q3 = f"Manual-first MVP with {features[0]}, {features[1]}, and {features[2]}."
    q4 = f"Users can {features[0].lower()}, {features[1].lower()}, and {features[2].lower()}."
    q5 = "Inputs: user-entered records, due dates, and basic customer/vendor details."
    q6 = "Outputs: reminders, payment status visibility, and simple schedules or summaries."
    q7 = _maybe_integrations(features)
    q8 = f"Revenue model: {pricing}."
    q9 = (
        f"In 30 days: 25 {persona} signups, 8 active users, and 2 paying customers."
    )
    q10 = (
        "Constraints: manual-first workflow, no heavy integrations, no automation claims, "
        "and keep scope narrow."
    )
    needs_api = _needs_external_api(brief, one_liner)
    q11_lines = [
        "Will users need to create accounts and log in? (Y)",
        "Will different types of users see different things? (Y)",
        "Will users save data that must still exist tomorrow? (Y)",
        "Will users pay money inside this system? (Y)",
        "Will the system generate reports, dashboards, or downloadable files? (Y)",
        f"Will this system need to connect to another software tool or API? ({'Y' if needs_api else 'NONE'})",
        "Will the system need to automatically send emails, reminders, or background tasks? (Y)",
        "Will an internal admin need to manage users or content? (Y)",
    ]

    return f"""# Founder Questionnaire - Answer Template

1. What problem are we solving?

{problem} Primary users: {persona}.

2. Who is our primary customer?

{persona}

3. What is the simplest version of our product that still delivers value?

{q3}

4. What actions should our users be able to take?

{q4}

5. What inputs do we need from the user?

{q5}

6. What outputs do we deliver back to them?

{q6}

7. Do we need external integrations or data sources?

{q7}

8. Are payments or transactions involved?

{q8}

9. What does success look like in the first 30 days?

{q9}

10. What constraints or non-goals must we respect?

{q10}

11. Build Reality Checklist (Behavior-Based)

{chr(10).join(q11_lines)}
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate hero Q1-Q10 answers from pipeline outputs")
    parser.add_argument("--brief", required=True, help="Path to business brief JSON")
    parser.add_argument("--one-liner", required=True, help="Path to one-liner text file")
    parser.add_argument("--name-suggestions", default=None, help="Path to name suggestions JSON")
    parser.add_argument(
        "--out-dir",
        default=str(Path(__file__).resolve().parents[1] / "intake" / "ai_text"),
        help="Output directory for hero answers text",
    )
    parser.add_argument("--base", default=None, help="Fallback base name")
    args = parser.parse_args()

    brief = _read_json(Path(args.brief))
    one_liner = _read_text(Path(args.one_liner))
    base = args.base or Path(args.brief).stem.replace("_business_brief", "")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    name_suggestions = Path(args.name_suggestions) if args.name_suggestions else None
    startup_name = _infer_name(name_suggestions, base)

    content = _build_answers(brief, one_liner)
    out_path = out_dir / f"{startup_name}_hero_answers.txt"
    out_path.write_text(content, encoding="utf-8")
    print(f"Wrote hero answers: {out_path}")


if __name__ == "__main__":
    main()
