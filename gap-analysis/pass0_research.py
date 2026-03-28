#!/usr/bin/env python3
"""Optional research providers for Pass 0 Gap Check."""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, Optional
from datetime import datetime
from pathlib import Path


DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
DEFAULT_ANTHROPIC_MODEL = "claude-haiku-4-5-20251001"


class ResearchError(RuntimeError):
    pass


def _calculate_cost_openai(usage: Dict[str, Any]) -> Dict[str, Any]:
    in_tokens = usage.get("prompt_tokens", 0) or 0
    out_tokens = usage.get("completion_tokens", 0) or 0

    in_rate = float(os.getenv("OPENAI_INPUT_PER_MTOK", "2.50"))
    out_rate = float(os.getenv("OPENAI_OUTPUT_PER_MTOK", "10.00"))

    in_cost = in_tokens * in_rate / 1_000_000
    out_cost = out_tokens * out_rate / 1_000_000
    total = in_cost + out_cost

    return {
        "input_tokens": in_tokens,
        "output_tokens": out_tokens,
        "cost_usd": total,
        "provider": "openai",
    }


def _calculate_cost_anthropic(usage: Dict[str, Any]) -> Dict[str, Any]:
    in_tokens = usage.get("input_tokens", 0) or 0
    out_tokens = usage.get("output_tokens", 0) or 0

    in_rate = float(os.getenv("ANTHROPIC_INPUT_PER_MTOK", "3.00"))
    out_rate = float(os.getenv("ANTHROPIC_OUTPUT_PER_MTOK", "15.00"))

    in_cost = in_tokens * in_rate / 1_000_000
    out_cost = out_tokens * out_rate / 1_000_000
    total = in_cost + out_cost

    return {
        "input_tokens": in_tokens,
        "output_tokens": out_tokens,
        "cost_usd": total,
        "provider": "anthropic",
    }


def _log_cost(cost_meta: Dict[str, Any], model: str) -> None:
    log_path = Path(__file__).resolve().parent / "pass0_ai_costs.csv"
    new_file = not log_path.exists()
    now = datetime.now()

    with log_path.open("a", newline="") as f:
        if new_file:
            f.write("date,time,provider,model,input_tokens,output_tokens,cost_usd\n")
        f.write(
            f"{now.strftime('%Y-%m-%d')},"
            f"{now.strftime('%H:%M:%S')},"
            f"{cost_meta.get('provider')},"
            f"{model},"
            f"{cost_meta.get('input_tokens', 0)},"
            f"{cost_meta.get('output_tokens', 0)},"
            f"{cost_meta.get('cost_usd', 0):.6f}\n"
        )


def _extract_json(text: str) -> Dict[str, Any]:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ResearchError("Research response did not contain JSON.")

    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise ResearchError(f"Failed to parse JSON from research response: {exc}") from exc


def build_research_prompt(
    idea_text: str,
    intake_summary: str,
    explicit_non_features: str,
    non_goals: str,
    allowlist: str,
) -> str:
    return (
        "You are a market-research assistant. Return ONLY valid JSON that matches this schema:\n"
        "{\n"
        "  \"ranked_personas\": [{\"persona\": \"string\", \"score\": 0-100, \"notes\": \"string\"}],\n"
        "  \"recommended_primary_user\": \"string\",\n"
        "  \"primary_problem\": \"string\",\n"
        "  \"primary_gap_type\": \"workflow gap|distribution gap|pricing gap|compliance gap|integration gap\",\n"
        "  \"current_alternative\": \"string\",\n"
        "  \"mvp_wedge\": \"string\",\n"
        "  \"must_have_features\": [\"string\"],\n"
        "  \"persona_channels\": [\"string\"],\n"
        "  \"saturation_signal\": \"LOW|MEDIUM|HIGH\",\n"
        "  \"build_readiness\": \"BUILD|HOLD\",\n"
        "  \"disqualifying_signals\": [\"string\"],\n"
        "  \"confidence\": 0-100,\n"
        "  \"notes\": \"string\"\n"
        "}\n\n"
        "Idea:\n"
        f"{idea_text}\n\n"
        "Context:\n"
        "- Choose ONE narrow persona.\n"
        "- Provide a ranked_personas list with scores (0-100). Choose the top score as recommended_primary_user.\n"
        "- Persona must be specific (include a platform, niche industry, or a numeric volume range like 5–15 invoices/month).\n"
        "- Persona and wedge MUST include at least one keyword from the allowlist below.\n"
        "- Wedge MUST follow this exact template and include numeric specificity:\n"
        "  \"For [persona] processing [N–M invoices/month], [pain] causes [consequence]. We [solution] instead of [current alternative].\"\n"
        "- The [consequence] must be explicit (e.g., late orders, supplier penalties, missed discounts, cash flow gaps).\n"
        "- Avoid generic AP/invoicing claims.\n"
        "- Do NOT propose features or integrations unless they are explicitly present in the input.\n"
        "- If unsure about integrations, omit them.\n"
        "- You MUST still propose exactly 3 minimal must_have_features (manual-first, low-scope, no integrations) even if input is sparse.\n"
        "- No URLs or raw blobs.\n\n"
        "Distribution requirement:\n"
        "- Provide persona_channels with at least 2 channels that are reachable for free marketing.\n"
        "- Prefer: Reddit, IndieHackers, Product Hunt, Hacker News, Twitter/X, Facebook Groups, LinkedIn, Discord.\n\n"
        "Persona allowlist (MUST include at least one keyword):\n"
        f"{allowlist}\n\n"
        "Explicit non-features (must avoid):\n"
        f"{explicit_non_features}\n\n"
        "Non-goals (must avoid):\n"
        f"{non_goals}\n\n"
        "Additional intake context:\n"
        f"{intake_summary}\n"
    )


class ResearchProvider:
    def research(
        self,
        idea_text: str,
        intake_summary: str,
        explicit_non_features: str,
        non_goals: str,
        allowlist: str,
    ) -> Dict[str, Any]:
        raise NotImplementedError


class OpenAIResearchProvider(ResearchProvider):
    def __init__(self, model: Optional[str] = None, timeout: int = 45):
        self.model = model or DEFAULT_OPENAI_MODEL
        self.timeout = timeout

    def research(
        self,
        idea_text: str,
        intake_summary: str,
        explicit_non_features: str,
        non_goals: str,
        allowlist: str,
    ) -> Dict[str, Any]:
        import requests
        key = os.getenv("OPENAI_API_KEY")
        if not key:
            raise ResearchError("OPENAI_API_KEY not set")

        prompt = build_research_prompt(idea_text, intake_summary, explicit_non_features, non_goals, allowlist)
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "max_tokens": 900,
        }
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            json=payload,
            headers=headers,
            timeout=self.timeout,
        )
        if resp.status_code != 200:
            raise ResearchError(f"OpenAI error {resp.status_code}: {resp.text[:200]}")
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        research = _extract_json(content)
        usage = data.get("usage", {})
        cost_meta = _calculate_cost_openai(usage)
        _log_cost(cost_meta, self.model)
        research["_usage"] = usage
        research["_cost"] = cost_meta
        return research


class AnthropicResearchProvider(ResearchProvider):
    def __init__(self, model: Optional[str] = None, timeout: int = 45):
        self.model = model or DEFAULT_ANTHROPIC_MODEL
        self.timeout = timeout

    def research(
        self,
        idea_text: str,
        intake_summary: str,
        explicit_non_features: str,
        non_goals: str,
        allowlist: str,
    ) -> Dict[str, Any]:
        import requests
        key = os.getenv("ANTHROPIC_API_KEY")
        if not key:
            raise ResearchError("ANTHROPIC_API_KEY not set")

        prompt = build_research_prompt(idea_text, intake_summary, explicit_non_features, non_goals, allowlist)
        payload = {
            "model": self.model,
            "max_tokens": 900,
            "temperature": 0,
            "messages": [{"role": "user", "content": prompt}],
        }
        headers = {
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            json=payload,
            headers=headers,
            timeout=self.timeout,
        )
        if resp.status_code != 200:
            raise ResearchError(f"Anthropic error {resp.status_code}: {resp.text[:200]}")
        data = resp.json()
        content = data["content"][0]["text"]
        research = _extract_json(content)
        usage = data.get("usage", {})
        cost_meta = _calculate_cost_anthropic(usage)
        _log_cost(cost_meta, self.model)
        research["_usage"] = usage
        research["_cost"] = cost_meta
        return research


class FileResearchProvider(ResearchProvider):
    def __init__(self, path: str):
        self.path = path

    def research(
        self,
        idea_text: str,
        intake_summary: str,
        explicit_non_features: str,
        non_goals: str,
        allowlist: str,
    ) -> Dict[str, Any]:
        with open(self.path, "r", encoding="utf-8") as f:
            return json.load(f)
