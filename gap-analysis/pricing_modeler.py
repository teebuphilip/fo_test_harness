#!/usr/bin/env python3
"""Infer pricing_model for business brief using AI with deterministic fallback."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

import requests

DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
DEFAULT_ANTHROPIC_MODEL = "claude-haiku-4-5-20251001"
FALLBACK_PRICING = "subscription, $19/mo starter"


def _read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: Path, data: Dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def _extract_json(text: str) -> Dict[str, Any]:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("No JSON object found")
    return json.loads(text[start : end + 1])


def _build_prompt(brief: Dict[str, Any], one_liner: str) -> str:
    schema = {"pricing_model": "string"}
    return (
        "You set a simple, buildable pricing model. Return ONLY valid JSON:\n"
        f"{json.dumps(schema, indent=2)}\n\n"
        "Rules:\n"
        "- Keep it simple: subscription with 1-2 tiers.\n"
        "- Prefer low price points ($9-$49) for solo/small teams.\n"
        "- Avoid complex enterprise or usage pricing.\n"
        "- One short line only.\n\n"
        "Business brief:\n"
        f"{json.dumps(brief, indent=2)}\n\n"
        "One-liner:\n"
        f"{one_liner}\n"
    )


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
        "temperature": 0.3,
        "max_tokens": 300,
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=60)
    if resp.status_code >= 400:
        raise RuntimeError(f"OpenAI error {resp.status_code}: {resp.text}")
    data = resp.json()
    return {"content": data["choices"][0]["message"]["content"], "usage": data.get("usage", {})}


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
        "max_tokens": 300,
        "temperature": 0.3,
        "messages": [{"role": "user", "content": prompt}],
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=60)
    if resp.status_code >= 400:
        raise RuntimeError(f"Anthropic error {resp.status_code}: {resp.text}")
    data = resp.json()
    parts = data.get("content", [])
    text = "".join(p.get("text", "") for p in parts)
    return {"content": text, "usage": data.get("usage", {})}


def _log_cost(provider: str, model: str, usage: Dict[str, Any], log_path: Path) -> float:
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
    now = datetime.now()
    with log_path.open("a", encoding="utf-8") as f:
        if new_file:
            f.write("date,time,provider,model,input_tokens,output_tokens,cost_usd\n")
        f.write(
            f"{now.strftime('%Y-%m-%d')},{now.strftime('%H:%M:%S')},{provider},{model},"
            f"{in_tokens},{out_tokens},{total:.6f}\n"
        )
    return total


def main() -> None:
    parser = argparse.ArgumentParser(description="Pricing model inferrer")
    parser.add_argument("--brief", required=True, help="Path to business brief JSON")
    parser.add_argument("--one-liner", required=True, help="Path to one-liner text file")
    parser.add_argument("--out", required=True, help="Path to output business brief JSON")
    parser.add_argument("--no-ai", action="store_true", help="Disable AI and use fallback")
    parser.add_argument("--provider", choices=["openai", "anthropic"], default="openai")
    parser.add_argument("--model", default=None)
    args = parser.parse_args()

    brief = _read_json(Path(args.brief))
    one_liner = Path(args.one_liner).read_text(encoding="utf-8").strip()

    if (brief.get("pricing_model") or "").strip() not in ("", "unknown", "tbd", "na"):
        _write_json(Path(args.out), brief)
        print(f"Wrote (unchanged): {args.out}")
        return

    if args.no_ai:
        brief["pricing_model"] = FALLBACK_PRICING
        _write_json(Path(args.out), brief)
        print(f"Wrote (fallback): {args.out}")
        return

    prompt = _build_prompt(brief, one_liner)
    try:
        if args.provider == "openai":
            model = args.model or DEFAULT_OPENAI_MODEL
            resp = _call_openai(prompt, model)
        else:
            model = args.model or DEFAULT_ANTHROPIC_MODEL
            resp = _call_anthropic(prompt, model)
        data = _extract_json(resp["content"])
        pricing = (data.get("pricing_model") or "").strip()
        brief["pricing_model"] = pricing or FALLBACK_PRICING
        _write_json(Path(args.out), brief)
        log_path = Path(__file__).resolve().parent / "pricing_model_ai_costs.csv"
        cost = _log_cost(args.provider, model, resp.get("usage", {}), log_path)
        print(f"Wrote: {args.out}")
        print(f"AI pricing cost: ${cost:.2f}")
    except Exception as exc:
        brief["pricing_model"] = FALLBACK_PRICING
        _write_json(Path(args.out), brief)
        print(f"AI pricing failed, wrote fallback: {args.out}")
        print(f"Error: {exc}")


if __name__ == "__main__":
    main()
