#!/usr/bin/env python3
"""
check_block_b.py — Lightweight Block B quality checker.

Reads an intake JSON and validates Block B content quality.
No AI. Deterministic. Fast.

Usage:
    python check_block_b.py intake/intake_runs/my_startup/my_startup.json
    python check_block_b.py intake/intake_runs/my_startup/my_startup.json --json

Exit codes:
    0 = PASS  (score >= 80)
    1 = WARN  (score 60-79, build can proceed but review flagged issues)
    2 = FAIL  (score < 60, intake likely to produce bad builds)
    3 = ERROR (file not found / not parseable)
"""

import argparse
import json
import sys
from pathlib import Path

PASS_THRESHOLD = 80
WARN_THRESHOLD = 60

VALID_TECH_STACKS  = {"lowcode", "boilerplate", "custom"}
VALID_ARCHETYPES   = {"community", "marketplace", "saas", "tool", "saas_tool", "platform", "service", "content"}
VALID_VALUE_LOOPS  = {"retainer", "transactional", "usage", "subscription", "freemium", "one-time"}
VALID_HERO_DECISIONS = {"buy_tier2_build"}


def _text(val) -> str:
    if isinstance(val, str):
        return val.strip()
    if isinstance(val, list):
        return " ".join(_text(v) for v in val)
    if isinstance(val, dict):
        return " ".join(_text(v) for v in val.values())
    return str(val) if val is not None else ""


def check(block_b: dict) -> list[dict]:
    """Return list of issues: {severity, pass, field, message}"""
    issues = []

    def flag(severity, pass_num, field, message):
        issues.append({"severity": severity, "pass": pass_num, "field": field, "message": message})

    p1 = block_b.get("pass_1") or {}
    p2 = block_b.get("pass_2") or {}
    p3 = block_b.get("pass_3") or {}
    p4 = block_b.get("pass_4") or {}
    p5 = block_b.get("pass_5") or {}
    p6 = block_b.get("pass_6") or {}

    # ── Pass presence ──────────────────────────────────────────────────────────
    for i in range(1, 7):
        if not block_b.get(f"pass_{i}"):
            flag("CRITICAL", i, f"pass_{i}", f"pass_{i} is missing entirely")

    # ── Pass 1 ─────────────────────────────────────────────────────────────────
    summary = _text(p1.get("bdr_summary"))
    if not summary:
        flag("CRITICAL", 1, "bdr_summary", "bdr_summary is empty")
    elif len(summary) < 50:
        flag("HIGH", 1, "bdr_summary", f"bdr_summary too short ({len(summary)} chars) — not enough product context")

    archetype = p1.get("selected_archetype", "")
    if not archetype:
        flag("HIGH", 1, "selected_archetype", "selected_archetype is missing")
    elif archetype.lower() not in VALID_ARCHETYPES:
        flag("LOW", 1, "selected_archetype", f"Unrecognised archetype '{archetype}' — may not map to a known build template")

    value_loop = p1.get("primary_value_loop", "")
    if not value_loop:
        flag("HIGH", 1, "primary_value_loop", "primary_value_loop is missing — revenue model undefined")

    if not p1.get("economics_snapshot"):
        flag("MEDIUM", 1, "economics_snapshot", "economics_snapshot missing — commercial framing absent")

    # ── Pass 2 ─────────────────────────────────────────────────────────────────
    tech_stack = p2.get("tech_stack_selection", "")
    if not tech_stack:
        flag("CRITICAL", 2, "tech_stack_selection", "tech_stack_selection is missing — harness won't know which build path to use")
    elif tech_stack.lower() not in VALID_TECH_STACKS:
        flag("HIGH", 2, "tech_stack_selection", f"Unrecognised tech stack '{tech_stack}' — expected one of {sorted(VALID_TECH_STACKS)}")

    templates = p2.get("component_templates_selected") or []
    if not templates:
        flag("HIGH", 2, "component_templates_selected", "No component templates selected — build may lack core scaffolding")

    approved_bdr = _text(p2.get("approved_bdr"))
    if not approved_bdr:
        flag("MEDIUM", 2, "approved_bdr", "approved_bdr is empty — no confirmed product description")
    elif len(approved_bdr) < 30:
        flag("LOW", 2, "approved_bdr", f"approved_bdr very short ({len(approved_bdr)} chars)")

    if not p2.get("hld_document"):
        flag("MEDIUM", 2, "hld_document", "hld_document missing — high-level design not captured")

    # ── Pass 3 ─────────────────────────────────────────────────────────────────
    test_vectors = p3.get("test_vectors") or []
    if not test_vectors:
        flag("HIGH", 3, "test_vectors", "No test vectors — QA has nothing to validate against")
    elif len(test_vectors) < 2:
        flag("MEDIUM", 3, "test_vectors", f"Only {len(test_vectors)} test vector(s) — at least 2 recommended")

    qa_doc = _text(p3.get("qa_hlt_document"))
    if not qa_doc:
        flag("MEDIUM", 3, "qa_hlt_document", "qa_hlt_document is empty — QA scope not defined")

    # ── Pass 4 ─────────────────────────────────────────────────────────────────
    tasks = p4.get("combined_task_list") or []
    if not tasks:
        flag("CRITICAL", 4, "combined_task_list", "No tasks in combined_task_list — build has nothing to implement")
    elif len(tasks) < 3:
        flag("HIGH", 4, "combined_task_list", f"Only {len(tasks)} task(s) — suspiciously sparse for a real product")
    else:
        empty_desc = [t.get("task_id", "?") for t in tasks if isinstance(t, dict) and not _text(t.get("description"))]
        if empty_desc:
            flag("MEDIUM", 4, "combined_task_list", f"Tasks with empty description: {empty_desc[:5]}")

    # ── Pass 5 ─────────────────────────────────────────────────────────────────
    milestones = p5.get("final_milestone_map") or []
    if not milestones:
        flag("LOW", 5, "final_milestone_map", "No milestones defined")

    # ── Pass 6 ─────────────────────────────────────────────────────────────────
    hero_decision = p6.get("hero_decision", "")
    if not hero_decision:
        flag("CRITICAL", 6, "hero_decision", "hero_decision is missing — founder never committed to build")
    elif hero_decision not in VALID_HERO_DECISIONS:
        flag("CRITICAL", 6, "hero_decision",
             f"hero_decision is '{hero_decision}' — expected 'buy_tier2_build'. Founder did not approve build.")

    return issues


def score(issues: list[dict]) -> int:
    s = 100
    deductions = {"CRITICAL": 25, "HIGH": 10, "MEDIUM": 4, "LOW": 1}
    for issue in issues:
        s -= deductions.get(issue["severity"], 0)
    return max(s, 0)


def status(s: int) -> str:
    if s >= PASS_THRESHOLD:
        return "PASS"
    if s >= WARN_THRESHOLD:
        return "WARN"
    return "FAIL"


def main():
    parser = argparse.ArgumentParser(description="Block B quality checker")
    parser.add_argument("intake_json", help="Path to intake JSON")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    path = Path(args.intake_json)
    if not path.exists():
        print(f"ERROR: file not found: {path}", file=sys.stderr)
        sys.exit(3)

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"ERROR: invalid JSON: {e}", file=sys.stderr)
        sys.exit(3)

    block_b = data.get("block_b") or data.get("block_b_final")
    if not block_b:
        print("ERROR: no block_b found in intake JSON", file=sys.stderr)
        sys.exit(3)

    startup_id = data.get("startup_idea_id") or path.stem
    issues     = check(block_b)
    sc         = score(issues)
    st         = status(sc)

    if args.json:
        print(json.dumps({"startup_id": startup_id, "score": sc, "status": st, "issues": issues}, indent=2))
    else:
        print(f"\nBlock B Quality Check — {startup_id}")
        print("=" * 52)
        print(f"Score  : {sc} / 100")
        print(f"Status : {st}")
        print(f"Issues : {len(issues)}")
        if issues:
            print()
            for iss in issues:
                print(f"  [{iss['severity']:<8}] pass_{iss['pass']} / {iss['field']}")
                print(f"             {iss['message']}")
        print()

    exit_codes = {"PASS": 0, "WARN": 1, "FAIL": 2}
    sys.exit(exit_codes[st])


if __name__ == "__main__":
    main()
