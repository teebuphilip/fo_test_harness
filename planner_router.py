#!/usr/bin/env python3
"""
planner_router.py — Lightweight selector for phase_planner vs slice_planner.

Reads an intake JSON and recommends "phase" or "slice" with reasons.
"""

import argparse
import json
from pathlib import Path
from typing import Any, List


FEATURE_KEYS = {
    'must_have_features', 'q4_must_have_features', 'features',
    'required_features', 'feature_list', 'capabilities', 'requirements',
    'must_haves', 'core_features', 'key_features', 'product_features',
}

TASK_LIST_KEYS = {'combined_task_list', 'task_list', 'tasks'}


def _recursive_get_lists(obj: Any, keys: set) -> list:
    if isinstance(obj, dict):
        out = []
        for k, v in obj.items():
            if k.lower() in keys and isinstance(v, list):
                out.extend(v)
            out.extend(_recursive_get_lists(v, keys))
        return out
    if isinstance(obj, list):
        out = []
        for item in obj:
            out.extend(_recursive_get_lists(item, keys))
        return out
    return []


def _extract_features(intake: dict) -> list:
    raw = _recursive_get_lists(intake, FEATURE_KEYS)
    features = []
    for item in raw:
        if isinstance(item, str) and item.strip():
            features.append(item.strip())
        elif isinstance(item, dict):
            text = (item.get('feature') or item.get('name') or
                    item.get('description') or item.get('title') or '')
            if text:
                features.append(str(text).strip())

    if not features:
        task_raw = _recursive_get_lists(intake, TASK_LIST_KEYS)
        for item in task_raw:
            if isinstance(item, dict) and item.get('classification') == 'build':
                desc = item.get('description', '')
                if desc:
                    features.append(str(desc).strip())

    # Deduplicate preserving order
    seen = set()
    result = []
    for f in features:
        key = f.lower()
        if key not in seen:
            seen.add(key)
            result.append(f)
    return result


def _flatten_text(obj: Any) -> str:
    if isinstance(obj, str):
        return obj.lower() + ' '
    if isinstance(obj, dict):
        return ''.join(_flatten_text(v) for v in obj.values())
    if isinstance(obj, list):
        return ''.join(_flatten_text(v) for v in obj)
    return ''


INTEGRATION_KEYWORDS = [
    'integration', 'webhook', 'api key', 'oauth', 'auth0', 'stripe',
    'gmail', 'google', 'calendar', 'slack', 'github', 'twilio',
]

ANALYTICS_KEYWORDS = [
    'dashboard', 'analytics', 'kpi', 'metric', 'report', 'export', 'download',
    'chart', 'graph', 'insight', 'analysis', 'trend', 'score',
]

AMBIGUITY_KEYWORDS = [
    'custom', 'bespoke', 'brand', 'tone', 'voice', 'polish', 'beautiful',
    'delight', 'premium', 'taste', 'vibe',
]

ROLE_KEYWORDS = [
    'admin', 'owner', 'manager', 'staff', 'member', 'client', 'user role',
    'permission', 'rbac',
]


def recommend_planner(intake: dict) -> dict:
    features = _extract_features(intake)
    text_blob = _flatten_text(intake)

    reasons: List[str] = []
    score = 0

    if len(features) > 3:
        score += 2
        reasons.append(f"feature_count={len(features)} (>3)")

    if any(k in text_blob for k in INTEGRATION_KEYWORDS):
        score += 2
        reasons.append("external_integration_signal")

    if any(k in text_blob for k in ANALYTICS_KEYWORDS):
        score += 1
        reasons.append("analytics/kpi_signal")

    if any(k in text_blob for k in AMBIGUITY_KEYWORDS):
        score += 1
        reasons.append("subjective_quality_signal")

    if any(k in text_blob for k in ROLE_KEYWORDS):
        score += 1
        reasons.append("multi_role_signal")

    planner = "slice" if score >= 2 else "phase"

    return {
        "recommended_planner": planner,
        "score": score,
        "reasons": reasons,
        "feature_count": len(features),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Recommend phase_planner vs slice_planner.")
    parser.add_argument("--intake", required=True, help="Path to intake JSON")
    parser.add_argument("--json", action="store_true", help="Output JSON only")
    args = parser.parse_args()

    intake_path = Path(args.intake)
    if not intake_path.exists():
        raise SystemExit(f"Intake file not found: {intake_path}")

    with intake_path.open("r", encoding="utf-8") as f:
        intake = json.load(f)

    rec = recommend_planner(intake)
    if args.json:
        print(json.dumps(rec))
        return

    print(f"Recommended planner: {rec['recommended_planner']}")
    print(f"Score: {rec['score']}")
    if rec["reasons"]:
        print("Reasons:")
        for r in rec["reasons"]:
            print(f"- {r}")
    else:
        print("Reasons: (none)")


if __name__ == "__main__":
    main()
