#!/usr/bin/env python3
"""
Convert raw founder answers (text file) to structured hero JSON.

This is Step 0 of the intake pipeline:
  Step 0: Raw answers → Hero JSON (this script)
  Step 1: Hero JSON → Intake evaluation (run_intake_v7.sh)
  Step 2: Intake JSON → Build (fo_test_harness.py)

Usage:
  python convert_hero_answers.py <raw_answers.txt> [output.json]

Examples:
  python convert_hero_answers.py hero_text/jose_hernandez_02_11_2026.txt
  python convert_hero_answers.py my_answers.txt hero_text/mystartup.json
"""

import os
import sys
import json
import re
from datetime import datetime
from typing import Tuple, Dict, Any

import requests
from anthropic import Anthropic

def read_raw_answers(file_path: str) -> str:
    """Read the raw text file with founder answers."""
    with open(file_path, 'r', encoding='utf-8') as f:
        return f.read()

def _log_cost(provider: str, model: str, usage: Dict[str, Any]) -> float:
    log_path = os.path.join(os.path.dirname(__file__), "hero_answers_ai_costs.csv")
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
    new_file = not os.path.exists(log_path)
    now = datetime.now()
    with open(log_path, "a", encoding="utf-8") as f:
        if new_file:
            f.write("date,time,provider,model,input_tokens,output_tokens,cost_usd\n")
        f.write(
            f"{now.strftime('%Y-%m-%d')},{now.strftime('%H:%M:%S')},{provider},{model},"
            f"{in_tokens},{out_tokens},{total:.6f}\n"
        )
    return total


def _call_openai(prompt: str) -> Tuple[str, Dict[str, Any]]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable not set")
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a precise JSON-only assistant."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,
        "max_tokens": 4096,
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=60)
    if resp.status_code >= 400:
        raise RuntimeError(f"OpenAI error {resp.status_code}: {resp.text}")
    data = resp.json()
    content = data["choices"][0]["message"]["content"]
    usage = data.get("usage", {})
    cost = _log_cost("openai", model, usage)
    return content, usage, cost


def _call_claude(prompt: str) -> Tuple[str, Dict[str, Any]]:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY environment variable not set")
    client = Anthropic(api_key=api_key)
    model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
    response = client.messages.create(
        model=model,
        max_tokens=4096,
        temperature=0.3,
        messages=[{"role": "user", "content": prompt}]
    )
    content = response.content[0].text.strip()
    usage = getattr(response, "usage", None)
    usage_dict = {}
    if usage:
        usage_dict = {
            "input_tokens": getattr(usage, "input_tokens", 0) or 0,
            "output_tokens": getattr(usage, "output_tokens", 0) or 0,
        }
    cost = _log_cost("anthropic", model, usage_dict)
    return content, usage_dict, cost


def extract_startup_info(raw_text: str) -> dict:
    """
    Use Claude to intelligently extract structured data from raw answers.

    The 10 questions founders answer:
    1. What problem are we solving?
    2. Who is our primary customer?
    3. What is the simplest version of our product?
    4. What actions should our users be able to take?
    5. What inputs do we need from the user?
    6. What outputs do we deliver back to them?
    7. Do we need external integrations or data sources?
    8. Are payments or transactions involved?
    9. What does success look like in the first 30 days?
    10. What constraints or non-goals must we respect?
    """

    prompt = f"""You are a structured data extractor. Convert the founder's raw answers into a structured JSON format.

The founder answered 10 questions about their startup. Parse their answers and extract the following fields:

**OUTPUT FORMAT (strict JSON):**
{{
  "startup_idea_id": "<lowercase_snake_case_name>",
  "startup_name": "<proper name>",
  "startup_description": "<1-2 sentence summary>",
  "hero_answers": {{
    "Q1_problem_customer": "<extract from Q1: what problem, who has it>",
    "Q2_target_user": ["<user segment 1>", "<user segment 2>", ...],
    "Q3_success_metric": "<extract from Q9: what does success look like in 30 days>",
    "Q4_must_have_features": ["<feature 1>", "<feature 2>", ...],
    "Q5_non_goals": ["<non-goal 1>", "<non-goal 2>", ...],
    "Q6_constraints": {{
      "brand_positioning": "<positioning statement>",
      "compliance": "<compliance requirements>",
      "promise_limits": "<what not to overpromise>",
      "scale_limits": "<scaling constraints>"
    }},
    "Q7_data_sources": ["<data source 1>", "<data source 2>", ...],
    "Q8_integrations": ["<integration 1>", "<integration 2>", ...],
    "Q9_risks": ["<risk 1>", "<risk 2>", ...],
    "Q10_shipping_preference": "<how to start shipping>"
  }}
}}

**EXTRACTION RULES:**

1. **startup_idea_id**: Create from the startup name (lowercase, underscores, no spaces)
2. **startup_name**: Extract or infer from Q1 or anywhere they mention their company name
3. **startup_description**: Write a concise 1-2 sentence summary of what they're building
4. **Q1_problem_customer**: Combine "what problem" and "who has it" from questions 1-2
5. **Q2_target_user**: Extract customer segments as an array (from Q2)
6. **Q3_success_metric**: From Q9 - what does success look like in 30 days
7. **Q4_must_have_features**: Extract from Q3, Q4, Q6 - core features/capabilities
8. **Q5_non_goals**: From Q10 - what they want to AVOID doing
9. **Q6_constraints**: Extract positioning, compliance, limits from Q10
10. **Q7_data_sources**: From Q7 - external data needed (Equineline, etc.)
11. **Q8_integrations**: From Q7, Q8 - payment processors, tools, APIs
12. **Q9_risks**: From Q10 and Q8 - what could go wrong
13. **Q10_shipping_preference**: From Q3 and Q10 - how to start (MVP approach)

**RAW FOUNDER ANSWERS:**
{raw_text}

Extract and output ONLY the JSON. No explanation, no markdown, just valid JSON."""

    # Default to ChatGPT, fallback to Claude
    content = ""
    cost = 0.0
    try:
        content, _, cost = _call_openai(prompt)
    except Exception as openai_err:
        try:
            content, _, cost = _call_claude(prompt)
        except Exception as claude_err:
            raise RuntimeError(f"OpenAI failed: {openai_err} | Claude failed: {claude_err}")
    print(f"AI hero cost: ${cost:.2f}")

    # Remove markdown code blocks if present
    if content.startswith('```'):
        content = re.sub(r'^```(?:json)?\n', '', content)
        content = re.sub(r'\n```$', '', content)

    try:
        return json.loads(content)
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON from Claude response:")
        print(content)
        raise e

def save_hero_json(data: dict, output_path: str):
    """Save the structured data as a hero JSON file."""
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Convert raw founder answers to hero JSON")
    parser.add_argument("input_file", help="Path to raw answers text file")
    parser.add_argument("output_file", nargs="?", help="Optional output JSON file path")
    parser.add_argument("--startup-id", dest="startup_id", default=None, help="Override startup_idea_id")
    parser.add_argument("--startup-name", dest="startup_name", default=None, help="Override startup_name")
    args = parser.parse_args()

    input_file = args.input_file
    startup_id_override = args.startup_id
    startup_name_override = args.startup_name

    if not os.path.exists(input_file):
        print(f"Error: File not found: {input_file}")
        sys.exit(1)

    # Determine output filename
    if args.output_file:
        output_file = args.output_file
    else:
        # Auto-generate output filename
        base_name = os.path.splitext(os.path.basename(input_file))[0]
        output_file = f"hero_text/{base_name}.json"

    print(f"🚀 Converting raw founder answers to hero JSON")
    print(f"📄 Input:  {input_file}")
    print(f"📄 Output: {output_file}")
    print("")

    # Read raw answers
    print("📖 Reading raw answers...")
    raw_text = read_raw_answers(input_file)

    # Extract structured data using ChatGPT (fallback to Claude)
    print("🤖 Using ChatGPT to extract structured data (fallback to Claude)...")
    hero_data = extract_startup_info(raw_text)

    # Override startup id/name if provided
    if startup_id_override:
        hero_data["startup_idea_id"] = startup_id_override
    if startup_name_override:
        hero_data["startup_name"] = startup_name_override

    # Save output
    print("💾 Saving hero JSON...")
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    save_hero_json(hero_data, output_file)

    print("")
    print("✅ Complete!")
    print(f"   Startup: {hero_data['startup_name']}")
    print(f"   ID: {hero_data['startup_idea_id']}")
    print(f"   File: {output_file}")
    print("")
    print("Next steps:")
    print(f"  1. Review the generated JSON: cat {output_file}")
    print(f"  2. Generate intake: ./generate_intake.sh {os.path.basename(output_file)}")

if __name__ == "__main__":
    main()
