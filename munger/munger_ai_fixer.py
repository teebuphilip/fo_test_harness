#!/usr/bin/env python3
"""
AI Fixer for Munger v2.0
Generates clarification responses for Munger issues using LLMs, then re-runs Munger.

Usage:
  python munger/munger_ai_fixer.py <hero_input.json> --out fixer_output.json
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
import importlib.util


ROOT = Path(__file__).resolve().parent

OPENAI_API = "https://api.openai.com/v1/chat/completions"
CLAUDE_API = "https://api.anthropic.com/v1/messages"

DEFAULT_OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
DEFAULT_CLAUDE_MODEL = "claude-sonnet-4-20250514"
AI_COST_LOG = ROOT / "munger_ai_costs.csv"


def _append_ai_cost(provider: str, model: str, input_tokens: int, output_tokens: int) -> float:
    in_rate = float(os.getenv("OPENAI_INPUT_PER_MTOK", "2.50"))
    out_rate = float(os.getenv("OPENAI_OUTPUT_PER_MTOK", "10.00"))
    if provider == "claude":
        in_rate = float(os.getenv("ANTHROPIC_INPUT_PER_MTOK", "3.00"))
        out_rate = float(os.getenv("ANTHROPIC_OUTPUT_PER_MTOK", "15.00"))

    in_cost = input_tokens * in_rate / 1_000_000
    out_cost = output_tokens * out_rate / 1_000_000
    total = in_cost + out_cost

    new_file = not AI_COST_LOG.exists()
    with AI_COST_LOG.open("a", newline="") as f:
        if new_file:
            f.write("date,time,provider,model,input_tokens,output_tokens,cost\n")
        now = datetime.now()
        f.write(",".join([
            now.strftime("%Y-%m-%d"),
            now.strftime("%H:%M:%S"),
            provider,
            model,
            str(input_tokens),
            str(output_tokens),
            f"{total:.6f}",
        ]) + "\n")
    return total


def _sum_total_cost() -> float:
    if not AI_COST_LOG.exists():
        return 0.0
    total = 0.0
    with AI_COST_LOG.open("r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            if i == 0:
                continue
            parts = line.strip().split(",")
            if len(parts) < 7:
                continue
            try:
                total += float(parts[6])
            except ValueError:
                continue
    return total


def _load_munger_module():
    path = ROOT / "munger.py"
    spec = importlib.util.spec_from_file_location("munger", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to load munger.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _extract_json(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("No JSON object found in model response")
    return json.loads(match.group(0))


def _validate_response_schema(schema: dict, answers: dict) -> Tuple[bool, str]:
    required = schema.get("required", [])
    for key in required:
        if key not in answers:
            return False, f"Missing required key: {key}"
    for key, spec in schema.get("properties", {}).items():
        if key not in answers:
            continue
        val = answers[key]
        t = spec.get("type")
        if t == "string" and not isinstance(val, str):
            return False, f"{key} must be string"
        if t == "boolean" and not isinstance(val, bool):
            return False, f"{key} must be boolean"
        if t == "integer" and not isinstance(val, int):
            return False, f"{key} must be integer"
        if t == "array" and not isinstance(val, list):
            return False, f"{key} must be array"
        if t == "object" and not isinstance(val, dict):
            return False, f"{key} must be object"
    return True, "ok"


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
        "max_tokens": 900,
        "temperature": 0.0,
    }
    resp = requests.post(
        OPENAI_API,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    usage = data.get("usage", {})
    cost = _append_ai_cost(
        "chatgpt",
        model,
        int(usage.get("prompt_tokens", 0) or 0),
        int(usage.get("completion_tokens", 0) or 0),
    )
    print(f"[MungerFixer] Tokens: in={usage.get('prompt_tokens', 0)} out={usage.get('completion_tokens', 0)}")
    print(f"[MungerFixer] Cost: ${cost:.4f}")
    text = data["choices"][0]["message"]["content"].strip()
    return _extract_json(text)


def _call_claude(prompt: str, model: str) -> dict:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    payload = {
        "model": model,
        "max_tokens": 900,
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
    usage = data.get("usage", {})
    cost = _append_ai_cost(
        "claude",
        model,
        int(usage.get("input_tokens", 0) or 0),
        int(usage.get("output_tokens", 0) or 0),
    )
    print(f"[MungerFixer] Tokens: in={usage.get('input_tokens', 0)} out={usage.get('output_tokens', 0)}")
    print(f"[MungerFixer] Cost: ${cost:.4f}")
    text = data["content"][0]["text"].strip()
    return _extract_json(text)


def _inference_hints(rule_id: str) -> str:
    if rule_id == "DR030_pricing_range_without_tiers":
        return (
            "If a pricing range is given, infer 2 tiers using range endpoints. "
            "Use target market upper bound for the top tier limit."
        )
    if rule_id == "DR040_quantitative_range_without_bounds":
        return (
            "If a range X-Y is given, set minimum=X, target=(X+Y)/2, maximum=Y."
        )
    if rule_id == "DR050_unresolved_either_or_choice":
        return (
            "If an either/or appears, prefer the option best aligned with tech stack; "
            "otherwise pick the first option."
        )
    if rule_id == "DR070_success_metrics_before_build_complete":
        return (
            "If success timeline is shorter than build timeline, interpret success as "
            "'after launch' and update text accordingly."
        )
    if rule_id == "DR082_q4_feature_missing_q11_flag":
        return (
            "If a feature implies an architecture flag, set the flag to true."
        )
    return "Use conservative inference based on Q1–Q11 context. Avoid guessing."


def _build_prompt(original_q1_q11: dict, issue: dict, clarification: dict) -> str:
    rule_id = issue.get("rule_id", "UNKNOWN")
    response_schema = clarification.get("response_schema", {})
    question = clarification.get("question", "")

    return "\n".join([
        "You are an AI assistant resolving ambiguities in startup specs.",
        "Return ONLY JSON with the exact shape below.",
        "",
        "CONTEXT: Original Q1-Q11:",
        json.dumps(original_q1_q11, ensure_ascii=False, indent=2),
        "",
        "DETECTED ISSUE:",
        json.dumps(issue, ensure_ascii=False, indent=2),
        "",
        "CLARIFICATION NEEDED:",
        question,
        "",
        "RESPONSE SCHEMA:",
        json.dumps(response_schema, ensure_ascii=False, indent=2),
        "",
        "INFERENCE RULES:",
        _inference_hints(rule_id),
        "",
        "OUTPUT FORMAT (JSON):",
        "{",
        '  "response": { /* must match response_schema */ },',
        '  "reasoning": "brief rationale",',
        '  "confidence": 0.0',
        "}",
    ])


def _generate_clarification(original_q1_q11: dict, issue: dict, clarification: dict,
                            provider: str, openai_model: str, claude_model: str) -> dict:
    prompt = _build_prompt(original_q1_q11, issue, clarification)
    if provider == "chatgpt":
        return _call_chatgpt(prompt, openai_model)
    if provider == "claude":
        return _call_claude(prompt, claude_model)

    # auto: try ChatGPT then Claude
    try:
        return _call_chatgpt(prompt, openai_model)
    except Exception:
        return _call_claude(prompt, claude_model)


def _map_canonical_to_q1_q11(hero: dict) -> dict:
    return {
        "Q1_problem_customer": hero.get("problem_customer"),
        "Q2_target_user": hero.get("target_user"),
        "Q3_success_metric": hero.get("success_metric"),
        "Q4_must_have_features": hero.get("must_have_features"),
        "Q5_non_goals": hero.get("non_goals"),
        "Q6_constraints": hero.get("constraints"),
        "Q7_data_sources": hero.get("data_sources"),
        "Q8_integrations": hero.get("integrations"),
        "Q9_risks": hero.get("risks"),
        "Q10_shipping_preference": hero.get("shipping_preference"),
        "Q11_architecture": hero.get("architecture"),
    }


def run_fixer(input_data: dict, max_loops: int, provider: str,
              openai_model: str, claude_model: str) -> dict:
    munger = _load_munger_module()

    original_q1_q11 = input_data.get("hero_answers", {})
    fixer_session_id = f"fixer_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"

    loops = 0
    clarifications_generated = 0
    confidences = []

    munger_output = munger.run_munger(input_data, None, 1)

    while loops < max_loops:
        status = munger_output.get("munger_report", {}).get("status")
        if status == "PASS":
            issues = munger_output.get("munger_report", {}).get("issues", [])
            if not any(i.get("severity") == "LOW" for i in issues):
                break
        if status == "REJECTED":
            break

        # Prefer loop-1 clarifications; fall back to loop-2/3 to include HIGH/MEDIUM/LOW
        clarifications = munger_output.get("munger_report", {}).get("clarifications", [])
        if not clarifications:
            clarifications = munger.run_munger(input_data, None, 1).get("munger_report", {}).get("clarifications", [])
        if not clarifications:
            clarifications = munger.run_munger(input_data, None, 2).get("munger_report", {}).get("clarifications", [])
        if not clarifications:
            clarifications = munger.run_munger(input_data, None, 3).get("munger_report", {}).get("clarifications", [])
        if not clarifications:
            break

        responses = []
        for item in clarifications:
            issue = item.get("issue", {})
            response_schema = item.get("response_schema", {})

            print(f"[MungerFixer] Calling AI for template {item.get('template_id')} (provider={provider})")
            raw = _generate_clarification(original_q1_q11, issue, item, provider, openai_model, claude_model)
            response = raw.get("response")
            reasoning = raw.get("reasoning", "")
            confidence = raw.get("confidence", 0.0)

            ok, msg = _validate_response_schema(response_schema, response or {})
            if not ok:
                responses.append({
                    "template_id": item.get("template_id"),
                    "error": f"Invalid response schema: {msg}",
                })
                continue

            responses.append({
                "template_id": item.get("template_id"),
                "answers": response,
                "reasoning": reasoning,
                "confidence": confidence,
            })
            print(f"[MungerFixer] AI response for {item.get('template_id')}: {json.dumps(response, ensure_ascii=False)}")
            confidences.append(float(confidence) if confidence is not None else 0.0)
            clarifications_generated += 1

        if not responses:
            break

        clarif_envelopes = [{"template_id": r["template_id"], "answers": r["answers"]} for r in responses if "answers" in r]
        munger_output = munger.run_munger(input_data, clarif_envelopes, loops + 1)
        loops += 1

        if munger_output.get("munger_report", {}).get("status") == "PASS":
            break

    status = munger_output.get("munger_report", {}).get("status", "UNKNOWN")
    confidence_avg = sum(confidences) / len(confidences) if confidences else 0.0

    updated_q1_q11 = _map_canonical_to_q1_q11(munger_output.get("clean_hero_answers", {}))

    return {
        "fixer_session_id": fixer_session_id,
        "status": "SUCCESS" if status == "PASS" else status,
        "loops": loops,
        "clarifications_generated": clarifications_generated,
        "confidence_avg": round(confidence_avg, 3),
        "updated_q1_q11": updated_q1_q11,
        "munger_output": munger_output,
    }


def main():
    parser = argparse.ArgumentParser(description="Munger AI Fixer")
    parser.add_argument("input_json", help="Hero input JSON (MUNGER_INPUT_SCHEMA)")
    parser.add_argument("--out", help="Write fixer output to path")
    parser.add_argument("--max-loops", type=int, default=2)
    parser.add_argument("--provider", choices=["chatgpt", "claude"], default="chatgpt")
    parser.add_argument("--openai-model", default=DEFAULT_OPENAI_MODEL)
    parser.add_argument("--claude-model", default=DEFAULT_CLAUDE_MODEL)
    args = parser.parse_args()

    start = time.time()
    if args.provider == "chatgpt" and not os.getenv("OPENAI_API_KEY"):
        print("Error: OPENAI_API_KEY not set")
        sys.exit(2)
    if args.provider == "claude" and not os.getenv("ANTHROPIC_API_KEY"):
        print("Error: ANTHROPIC_API_KEY not set")
        sys.exit(3)

    input_path = Path(args.input_json)
    if not input_path.exists():
        print(f"Error: {input_path} not found")
        sys.exit(1)

    print(f"[MungerFixer] Input: {input_path}")
    if args.out:
        print(f"[MungerFixer] Output: {Path(args.out)}")
    print(f"[MungerFixer] Provider: {args.provider}")
    print(f"[MungerFixer] OpenAI model: {args.openai_model}")
    print(f"[MungerFixer] Claude model: {args.claude_model}")
    print(f"[MungerFixer] Max loops: {args.max_loops}")

    total_before = _sum_total_cost()

    input_data = json.loads(input_path.read_text(encoding="utf-8"))

    output = run_fixer(input_data, args.max_loops, args.provider, args.openai_model, args.claude_model)
    output_json = json.dumps(output, indent=2, ensure_ascii=False)

    if args.out:
        Path(args.out).write_text(output_json, encoding="utf-8")
        print(f"Wrote: {args.out}")
    else:
        print(output_json)

    elapsed = time.time() - start
    total_after = _sum_total_cost()
    print(f"[MungerFixer] Status: {output.get('status', 'UNKNOWN')}")
    print(f"[MungerFixer] Loops: {output.get('loops', 0)}")
    print(f"[MungerFixer] Clarifications generated: {output.get('clarifications_generated', 0)}")
    print(f"[MungerFixer] Confidence avg: {output.get('confidence_avg', 0)}")
    print(f"[MungerFixer] Duration: {elapsed:.2f}s")
    print(f"[MungerFixer] Cost: ${total_after - total_before:.4f} (cumulative: ${total_after:.4f})")
    print(f"[MungerFixer] Cost CSV: {AI_COST_LOG.resolve()}")

    if output.get("status") == "SUCCESS":
        sys.exit(0)
    sys.exit(1)


if __name__ == "__main__":
    main()
