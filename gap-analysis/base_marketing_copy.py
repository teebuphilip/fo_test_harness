#!/usr/bin/env python3
"""Generate marketing copy from business brief + SEO config."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
DEFAULT_ANTHROPIC_MODEL = "claude-haiku-4-5-20251001"


def _read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: Path, data: Dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def _build_prompt(brief: Dict[str, Any], seo: Dict[str, Any]) -> str:
    schema = {
        "taglines": ["string"],
        "hero_headlines": ["string"],
        "hero_subheads": ["string"],
        "value_props": ["string"],
        "feature_bullets": ["string"],
        "cta_variants": ["string"],
    }

    return (
        "You generate concise marketing copy. Return ONLY valid JSON matching this schema:\n"
        f"{json.dumps(schema, indent=2)}\n\n"
        "Rules:\n"
        "- Keep phrases short and concrete.\n"
        "- Avoid hype and vague words (revolutionary, platform, solution).\n"
        "- Do NOT use words like automate/automation/automated.\n"
        "- Emphasize manual-first workflows (manual entry, simple tracking, reminders).\n"
        "- Mention the persona explicitly in at least 3 items per list.\n"
        "- Use the persona and pain from the business brief.\n"
        "- Use SEO keywords as phrasing inspiration, not verbatim stuffing.\n"
        "- Provide 5 items per list.\n\n"
        "Business brief:\n"
        f"{json.dumps(brief, indent=2)}\n\n"
        "SEO config:\n"
        f"{json.dumps(seo, indent=2)}\n"
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
        "temperature": 0.5,
        "max_tokens": 1200,
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
        "max_tokens": 1200,
        "temperature": 0.5,
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


def _validate_output(data: Dict[str, Any]) -> None:
    required = [
        "taglines",
        "hero_headlines",
        "hero_subheads",
        "value_props",
        "feature_bullets",
        "cta_variants",
    ]
    for key in required:
        if key not in data or not isinstance(data[key], list) or len(data[key]) < 3:
            raise ValueError(f"Missing or invalid field: {key}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Base marketing copy generator")
    parser.add_argument("--brief", required=True, help="Path to business brief JSON")
    parser.add_argument("--seo", required=True, help="Path to seo.json")
    parser.add_argument("--out", required=True, help="Path to output marketing copy JSON")
    parser.add_argument("--provider", choices=["openai", "anthropic"], default="openai")
    parser.add_argument("--model", default=None)
    args = parser.parse_args()

    brief = _read_json(Path(args.brief))
    seo = _read_json(Path(args.seo))
    prompt = _build_prompt(brief, seo)

    if args.provider == "openai":
        model = args.model or DEFAULT_OPENAI_MODEL
        resp = _call_openai(prompt, model)
    else:
        model = args.model or DEFAULT_ANTHROPIC_MODEL
        resp = _call_anthropic(prompt, model)

    data = _extract_json(resp["content"])
    _validate_output(data)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    _write_json(out_path, data)

    log_path = Path(__file__).resolve().parent / "marketing_copy_ai_costs.csv"
    _log_cost(args.provider, model, resp.get("usage", {}), log_path)
    print(f"Wrote: {out_path}")


if __name__ == "__main__":
    main()
