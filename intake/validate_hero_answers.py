#!/usr/bin/env python3
"""
Validate hero answers for internal consistency (Q1-Q11).

Usage:
  python intake/validate_hero_answers.py <hero.json> [--mode strict|relaxed]

Default provider order: ChatGPT first, Claude second (fallback).
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import requests


OPENAI_API = "https://api.openai.com/v1/chat/completions"
CLAUDE_API = "https://api.anthropic.com/v1/messages"

DEFAULT_OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
DEFAULT_CLAUDE_MODEL = "claude-sonnet-4-20250514"


def _extract_json(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("No JSON object found in model response")
    return json.loads(match.group(0))


def _build_prompt(hero_answers: dict, mode: str) -> str:
    return "\n".join([
        "You are a strict consistency validator for FounderOps hero answers.",
        "Analyze Q1–Q11 for contradictions and incomplete flows.",
        "Return ONLY JSON matching the schema below. Do not add extra keys.",
        "",
        "Checks to run:",
        "CHECK-01 Timeline Coherence: Q9 success timeline >= Q11 build timeline, unless Q9 says 'after launch'.",
        "CHECK-02 Scope vs Timeline: Tier 3+ complexity cannot fit in <60 days nights/weekends.",
        "CHECK-03 Happy Path Input Coverage: Q4 user actions must have inputs in Q5.",
        "CHECK-04 Happy Path Output Coverage: Q4 system actions must be outputs in Q6.",
        "CHECK-05 Revenue Model Alignment: Q8 pricing model must match Q11 subscription_billing.",
        "CHECK-06 API Declaration Consistency: Q7 required APIs must appear in Q11 external_apis.",
        "CHECK-07 Pricing Tier Count Validation: Q8 tier count must match description.",
        "CHECK-08 Authentication Flow Completeness: If Q11 auth required, Q4 includes signup/login.",
        "CHECK-09 Multi-Tenant Data Scope: If Q11 multi_tenant, Q2 must define tenant boundaries.",
        "CHECK-10 Feature Scope Alignment: Q3 exclusions must not appear in Q4/Q5/Q6.",
        "",
        f"Validation mode: {mode}. If relaxed, downgrade borderline issues to MEDIUM instead of FAIL.",
        "",
        "JSON schema:",
        "{",
        '  "validation_result": "PASS" | "FAIL",',
        '  "validation_timestamp": "ISO-8601",',
        '  "checks_run": 10,',
        '  "checks_passed": number,',
        '  "checks_failed": number,',
        '  "issues": [',
        "    {",
        '      "check_id": "CHECK-01",',
        '      "check_name": "Timeline Coherence",',
        '      "severity": "CRITICAL" | "HIGH" | "MEDIUM",',
        '      "questions_involved": ["Q9","Q11"],',
        '      "problem_description": "string",',
        '      "clarifying_question": "string",',
        '      "suggested_resolutions": ["string","string"]',
        "    }",
        "  ],",
        '  "overall_verdict": "string"',
        "}",
        "",
        "Hero answers JSON:",
        json.dumps(hero_answers, ensure_ascii=False, indent=2),
    ])


def _call_chatgpt(prompt: str, model: str) -> dict:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set")
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "Return only JSON. No extra text."},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": 1000,
        "temperature": 0.2,
    }
    resp = requests.post(
        OPENAI_API,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    text = data["choices"][0]["message"]["content"].strip()
    return _extract_json(text)


def _call_claude(prompt: str, model: str) -> dict:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    payload = {
        "model": model,
        "max_tokens": 1000,
        "messages": [{"role": "user", "content": prompt}],
    }
    resp = requests.post(
        CLAUDE_API,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json=payload,
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    text = data["content"][0]["text"].strip()
    return _extract_json(text)


def validate(hero_answers: dict, mode: str, provider: str, openai_model: str, claude_model: str) -> dict:
    prompt = _build_prompt(hero_answers, mode)

    if provider == "chatgpt":
        return _call_chatgpt(prompt, openai_model)
    if provider == "claude":
        return _call_claude(prompt, claude_model)

    raise ValueError("Invalid provider")


def _print_summary(report: dict):
    result = report.get("validation_result", "UNKNOWN")
    issues = report.get("issues", [])
    print(f"Validation Result: {result}")
    if not issues:
        print("No issues found.")
        return
    for issue in issues:
        check_id = issue.get("check_id", "CHECK-??")
        name = issue.get("check_name", "Unknown Check")
        sev = issue.get("severity", "MEDIUM")
        problem = issue.get("problem_description", "")
        print(f"- {check_id} ({sev}) {name}: {problem}")


def main():
    parser = argparse.ArgumentParser(description="Validate hero answers for consistency")
    parser.add_argument("hero_json", help="Path to hero.json")
    parser.add_argument("--mode", choices=["strict", "relaxed"], default="strict")
    parser.add_argument("--provider", choices=["chatgpt", "claude"], default="chatgpt")
    parser.add_argument("--openai-model", default=DEFAULT_OPENAI_MODEL)
    parser.add_argument("--claude-model", default=DEFAULT_CLAUDE_MODEL)
    parser.add_argument("--out", help="Write JSON report to file")
    args = parser.parse_args()

    path = Path(args.hero_json)
    if not path.exists():
        print(f"Error: {path} not found")
        sys.exit(1)

    data = json.loads(path.read_text(encoding="utf-8"))
    hero_answers = data.get("hero_answers")
    if not isinstance(hero_answers, dict):
        print("Error: hero_answers not found or invalid in hero JSON")
        sys.exit(1)

    if args.provider == "chatgpt" and not os.getenv("OPENAI_API_KEY"):
        print("Error: OPENAI_API_KEY not set")
        sys.exit(2)
    if args.provider == "claude" and not os.getenv("ANTHROPIC_API_KEY"):
        print("Error: ANTHROPIC_API_KEY not set")
        sys.exit(3)

    report = validate(hero_answers, args.mode, args.provider, args.openai_model, args.claude_model)

    # Fill timestamp if model omitted it
    if not report.get("validation_timestamp"):
        report["validation_timestamp"] = datetime.utcnow().isoformat() + "Z"

    _print_summary(report)

    output_json = json.dumps(report, indent=2, ensure_ascii=False)
    if args.out:
        Path(args.out).write_text(output_json, encoding="utf-8")
        print(f"Wrote report: {args.out}")
    else:
        print(output_json)


if __name__ == "__main__":
    main()
