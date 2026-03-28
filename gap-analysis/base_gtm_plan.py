#!/usr/bin/env python3
"""Generate a structured GTM plan from a business brief + one-liner."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict, List

import requests

DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
DEFAULT_ANTHROPIC_MODEL = "claude-haiku-4-5-20251001"


def _read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""


def _write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def _safe_list(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return []


def _deterministic_template(brief: Dict[str, Any], one_liner: str) -> Dict[str, Any]:
    persona = (brief.get("target_audience") or brief.get("name") or "Target users").strip()
    problem = (brief.get("problem_solved") or "A recurring workflow problem").strip()
    offer = (one_liner or brief.get("description") or "A simple manual-first workflow tool").strip()
    features = _safe_list(brief.get("features"))
    pricing = (brief.get("pricing_model") or "simple monthly subscription").strip()

    feature_hint = features[:3] if features else ["manual entry", "reminders", "basic tracking"]

    return {
        "schema_version": "1.0.0",
        "who": persona,
        "offer": offer,
        "problem": problem,
        "channels_free": [
            f"Post in Reddit communities where {persona} ask for help",
            "Indie Hackers posts and comments on similar workflows",
            f"DM outreach to 20-50 {persona} with a short demo video",
            f"Community forums/groups where {persona} share tools",
        ],
        "try_it": f"Let users try {feature_hint[0]} and {feature_hint[1]} on 1-3 items",
        "pay": f"{pricing} with a clear upgrade path",
        "cheap_execution_checklist": [
            "1-page landing page with the one-liner and CTA",
            "Short demo video showing the manual-first workflow",
            "Collect 10 short interviews from target users",
            "Offer early-access onboarding for first 10 users",
            "Post a weekly progress update in a relevant community",
        ],
        "automation_simplification_ideas": [
            "Save common inputs as templates",
            "Default reminder schedule presets",
            "CSV import for existing data",
            "One-click export of a simple report",
            "Fewer steps in onboarding",
        ],
    }


def _build_prompt(template: Dict[str, Any], brief: Dict[str, Any], one_liner: str) -> str:
    schema = {
        "schema_version": "1.0.0",
        "who": "string",
        "offer": "string",
        "problem": "string",
        "channels_free": ["string"],
        "try_it": "string",
        "pay": "string",
        "cheap_execution_checklist": ["string"],
        "automation_simplification_ideas": ["string"],
    }

    return (
        "You generate a GTM plan. Return ONLY valid JSON that matches this schema:\n"
        f"{json.dumps(schema, indent=2)}\n\n"
        "Rules:\n"
        "- Use the persona/problem/offer from the brief and one-liner.\n"
        "- Free channels only. Do NOT mention paid ads.\n"
        "- Keep each list item under 12 words.\n"
        "- Avoid words: automate, automation, automated.\n"
        "- Keep the same keys and list counts as the template.\n\n"
        "Template (fill and improve, do not remove keys):\n"
        f"{json.dumps(template, indent=2)}\n\n"
        "Business brief:\n"
        f"{json.dumps(brief, indent=2)}\n\n"
        "One-liner:\n"
        f"{one_liner}\n"
    )


def _extract_json(text: str) -> Dict[str, Any]:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("No JSON object found in model output")
    return json.loads(text[start : end + 1])


def _call_openai(prompt: str, model: str) -> Dict[str, Any]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set")
    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a precise JSON-only assistant."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.4,
        "max_tokens": 1400,
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=60)
    if resp.status_code >= 400:
        raise RuntimeError(f"OpenAI error {resp.status_code}: {resp.text}")
    data = resp.json()
    return {
        "content": data["choices"][0]["message"]["content"],
        "usage": data.get("usage", {}),
    }


def _call_anthropic(prompt: str, model: str) -> Dict[str, Any]:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    payload = {
        "model": model,
        "max_tokens": 1400,
        "temperature": 0.4,
        "messages": [
            {"role": "user", "content": prompt},
        ],
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=60)
    if resp.status_code >= 400:
        raise RuntimeError(f"Anthropic error {resp.status_code}: {resp.text}")
    data = resp.json()
    parts = data.get("content", [])
    text = "".join(p.get("text", "") for p in parts)
    return {
        "content": text,
        "usage": data.get("usage", {}),
    }


def _log_cost(provider: str, model: str, usage: Dict[str, Any], log_path: Path) -> None:
    if provider == "openai":
        in_tokens = usage.get("prompt_tokens", 0) or 0
        out_tokens = usage.get("completion_tokens", 0) or 0
        in_rate = float(os.getenv("OPENAI_INPUT_PER_MTOK", "2.50"))
        out_rate = float(os.getenv("OPENAI_OUTPUT_PER_MTOK", "10.00"))
    else:
        in_tokens = usage.get("input_tokens", 0) or 0
        out_tokens = usage.get("output_tokens", 0) or 0
        in_rate = float(os.getenv("ANTHROPIC_INPUT_PER_MTOK", "3.00"))
        out_rate = float(os.getenv("ANTHROPIC_OUTPUT_PER_MTOK", "15.00"))

    total = (in_tokens * in_rate + out_tokens * out_rate) / 1_000_000
    new_file = not log_path.exists()
    from datetime import datetime
    now = datetime.now()
    with log_path.open("a", newline="") as f:
        if new_file:
            f.write("date,time,provider,model,input_tokens,output_tokens,cost_usd\n")
        f.write(
            f"{now.strftime('%Y-%m-%d')},{now.strftime('%H:%M:%S')},{provider},{model},"
            f"{in_tokens},{out_tokens},{total:.6f}\n"
        )


def _validate_output(data: Dict[str, Any], template: Dict[str, Any]) -> None:
    required = list(template.keys())
    for key in required:
        if key not in data:
            raise ValueError(f"Missing field: {key}")
    list_fields = ["channels_free", "cheap_execution_checklist", "automation_simplification_ideas"]
    for key in list_fields:
        if not isinstance(data.get(key), list) or len(data[key]) < 3:
            raise ValueError(f"Invalid list field: {key}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Structured GTM plan generator")
    parser.add_argument("--brief", required=True, help="Path to business brief JSON")
    parser.add_argument("--one-liner", required=True, help="Path to one-liner text file")
    parser.add_argument("--out", required=True, help="Path to output gtm JSON")
    parser.add_argument("--no-ai", action="store_true", help="Use deterministic template only")
    parser.add_argument("--provider", choices=["openai", "anthropic"], default="openai")
    parser.add_argument("--model", default=None)
    args = parser.parse_args()

    brief = _read_json(Path(args.brief))
    one_liner = _read_text(Path(args.one_liner))
    template = _deterministic_template(brief, one_liner)

    if args.no_ai:
        _write_json(Path(args.out), template)
        print(f"Wrote: {args.out}")
        return

    prompt = _build_prompt(template, brief, one_liner)
    try:
        if args.provider == "openai":
            model = args.model or DEFAULT_OPENAI_MODEL
            resp = _call_openai(prompt, model)
        else:
            model = args.model or DEFAULT_ANTHROPIC_MODEL
            resp = _call_anthropic(prompt, model)
        data = _extract_json(resp["content"])
        _validate_output(data, template)
        _write_json(Path(args.out), data)
        log_path = Path(__file__).resolve().parent / "gtm_plan_ai_costs.csv"
        usage = resp.get("usage", {})
        _log_cost(args.provider, model, usage, log_path)
        print(f"Wrote: {args.out}")
        if args.provider == "openai":
            in_tokens = usage.get("prompt_tokens", 0) or 0
            out_tokens = usage.get("completion_tokens", 0) or 0
            in_rate = float(os.getenv("OPENAI_INPUT_PER_MTOK", "2.50"))
            out_rate = float(os.getenv("OPENAI_OUTPUT_PER_MTOK", "10.00"))
        else:
            in_tokens = usage.get("input_tokens", 0) or 0
            out_tokens = usage.get("output_tokens", 0) or 0
            in_rate = float(os.getenv("ANTHROPIC_INPUT_PER_MTOK", "3.00"))
            out_rate = float(os.getenv("ANTHROPIC_OUTPUT_PER_MTOK", "15.00"))
        total = (in_tokens * in_rate + out_tokens * out_rate) / 1_000_000
        print(f"AI GTM cost: ${total:.2f}")
    except Exception as exc:
        _write_json(Path(args.out), template)
        print(f"AI GTM failed, wrote deterministic template: {args.out}")
        print(f"Error: {exc}")


if __name__ == "__main__":
    main()
