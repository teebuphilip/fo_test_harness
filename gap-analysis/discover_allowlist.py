#!/usr/bin/env python3
"""Ad-hoc allowlist discovery for Pass 0 (AI-assisted)."""

from __future__ import annotations

import argparse
import json
import os
from typing import Any, Dict, Optional

from pass0_research import (
    ResearchError,
    OpenAIResearchProvider,
    AnthropicResearchProvider,
    _calculate_cost_openai,
    _calculate_cost_anthropic,
    _log_cost,
)


def _load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _build_prompt(context: str) -> str:
    return (
        "You are generating a broad allowlist of platforms, niches, or market keywords to constrain persona selection. "
        "Return ONLY valid JSON in this schema:\n"
        "{\n"
        "  \"allowlist\": [\"string\"],\n"
        "  \"notes\": \"string\"\n"
        "}\n\n"
        "Rules:\n"
        "- Provide 40-80 items.\n"
        "- Mix platforms (e.g., Shopify), verticals (e.g., property managers), and role-based niches (e.g., bookkeepers).\n"
        "- Keep items short (1-3 words).\n"
        "- Do NOT include generic terms like 'small business'.\n\n"
        f"Context:\n{context}\n"
    )


def _extract_json(text: str) -> Dict[str, Any]:
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass
    # fallback: try to find JSON object
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        return json.loads(text[start : end + 1])
    raise ValueError("Could not parse JSON from response")


def _call_openai(prompt: str, model: str) -> Dict[str, Any]:
    import requests
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise ResearchError("OPENAI_API_KEY not set")
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "max_tokens": 1200,
    }
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    resp = requests.post("https://api.openai.com/v1/chat/completions", json=payload, headers=headers, timeout=60)
    if resp.status_code != 200:
        raise ResearchError(f"OpenAI error {resp.status_code}: {resp.text[:200]}")
    data = resp.json()
    content = data["choices"][0]["message"]["content"]
    usage = data.get("usage", {})
    cost_meta = _calculate_cost_openai(usage)
    _log_cost(cost_meta, model)
    result = _extract_json(content)
    result["_cost"] = cost_meta
    return result


def _call_anthropic(prompt: str, model: str) -> Dict[str, Any]:
    import requests
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        raise ResearchError("ANTHROPIC_API_KEY not set")
    payload = {
        "model": model,
        "max_tokens": 1200,
        "temperature": 0,
        "messages": [{"role": "user", "content": prompt}],
    }
    headers = {
        "x-api-key": key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    resp = requests.post("https://api.anthropic.com/v1/messages", json=payload, headers=headers, timeout=60)
    if resp.status_code != 200:
        raise ResearchError(f"Anthropic error {resp.status_code}: {resp.text[:200]}")
    data = resp.json()
    content = data["content"][0]["text"]
    usage = data.get("usage", {})
    cost_meta = _calculate_cost_anthropic(usage)
    _log_cost(cost_meta, model)
    result = _extract_json(content)
    result["_cost"] = cost_meta
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Discover a Pass 0 allowlist (ad-hoc)")
    parser.add_argument("--context", help="Free-text context for allowlist discovery")
    parser.add_argument("--intake", help="Optional intake JSON to seed context")
    parser.add_argument("--provider", choices=["openai", "anthropic"], default="openai")
    parser.add_argument("--model", help="Model override")
    parser.add_argument("--out", default="gap-analysis/pass0_allowlist_suggested.txt")
    parser.add_argument("--append-to", help="Append results to this allowlist file after backing it up")
    args = parser.parse_args()

    context = args.context or ""
    if args.intake:
        intake = _load_json(args.intake)
        for key in ["startup_name", "summary"]:
            if isinstance(intake.get(key), str):
                context += f"\n{intake.get(key)}"

    if not context.strip():
        context = "General SaaS markets across SMBs, operations, finance, HR, and ecommerce."

    prompt = _build_prompt(context.strip())

    model = args.model or ("gpt-4o-mini" if args.provider == "openai" else "claude-haiku-4-5-20251001")
    if args.provider == "openai":
        result = _call_openai(prompt, model)
    else:
        result = _call_anthropic(prompt, model)

    allowlist = result.get("allowlist", [])
    if not isinstance(allowlist, list):
        raise SystemExit("Invalid allowlist returned")

    lines = [str(x).strip() for x in allowlist if str(x).strip()]
    with open(args.out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
        f.write("\n")

    if args.append_to:
        target = args.append_to
        if os.path.exists(target):
            from datetime import datetime
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup = f"{target}.{stamp}.bak"
            with open(target, "r", encoding="utf-8") as src, open(backup, "w", encoding="utf-8") as dst:
                dst.write(src.read())
        with open(target, "a", encoding="utf-8") as f:
            f.write("\n".join(lines))
            f.write("\n")
        print(f"Appended to: {target}")

    cost = result.get("_cost", {}).get("cost_usd")
    if cost is None:
        print("Cost: $0.00")
    else:
        rounded = (int(float(cost) * 100 + 0.999999) / 100.0)
        print(f"Cost: ${rounded:.2f}")
    print(f"Wrote: {args.out}")


if __name__ == "__main__":
    main()
