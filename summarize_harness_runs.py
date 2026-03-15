#!/usr/bin/env python3
"""
Summarize FounderOps harness runs from CSV log.

Usage:
    python summarize_harness_runs.py runs.csv
    
Output: Clean markdown table ready to paste into your post.
"""

import csv
import sys
import os
import argparse
import requests
from collections import defaultdict
from pathlib import Path
from datetime import datetime


CLAUDE_API = "https://api.anthropic.com/v1/messages"
DEFAULT_CLAUDE_MODEL = "claude-sonnet-4-20250514"


# Maps startup_id prefix → clean product name.
# Any startup_id starting with the key is grouped under that product.
PRODUCT_PREFIXES = {
    "ai_workforce_intelligence": "AI Workforce Intelligence",
    "adversarial_ai_validator":  "Adversarial AI Validator",
}

# startup_ids to skip entirely (test runs, noise)
SKIP_STARTUPS = {"startup"}


def _product_name(startup_id: str) -> str:
    """Return the canonical product name for a startup_id."""
    for prefix, name in PRODUCT_PREFIXES.items():
        if startup_id.startswith(prefix):
            return name
    # Clean up: replace underscores, title-case
    return startup_id.replace("_", " ").title()


def _is_feature_run(startup_id: str) -> bool:
    """True if this startup_id is a feature/phase run rather than a top-level build."""
    for prefix in PRODUCT_PREFIXES:
        if startup_id.startswith(prefix) and startup_id != prefix:
            return True
    return False


def summarize_runs(csv_path):
    """Parse CSV and generate summary statistics grouped by product."""

    # product_name -> list of run records
    runs_by_product = defaultdict(list)
    # product_name -> set of distinct feature startup_ids
    features_by_product = defaultdict(set)

    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            startup = row['startup']
            if startup in SKIP_STARTUPS:
                continue
            product = _product_name(startup)
            runs_by_product[product].append(row)
            if _is_feature_run(startup):
                features_by_product[product].add(startup)

    summaries = []

    for product, runs in runs_by_product.items():
        total_runs = len(runs)
        qa_accepted = sum(1 for r in runs if r['run_end_reason'] == 'QA_ACCEPTED')

        # Average cost for QA_ACCEPTED runs only
        accepted_costs = [
            float(r['total_cost'])
            for r in runs
            if r['run_end_reason'] == 'QA_ACCEPTED' and float(r['total_cost']) > 0
        ]
        avg_cost = sum(accepted_costs) / len(accepted_costs) if accepted_costs else 0

        # Total spend across ALL runs
        total_cost = sum(float(r['total_cost']) for r in runs if r.get('total_cost'))

        # Most common failure mode (excluding QA_ACCEPTED)
        failures = [r['run_end_reason'] for r in runs if r['run_end_reason'] != 'QA_ACCEPTED']
        failure_counts = defaultdict(int)
        for f in failures:
            failure_counts[f] += 1
        main_failure = max(failure_counts.items(), key=lambda x: x[1])[0] if failure_counts else "None"

        # Call out expensive non-converging runs
        expensive_failures = [
            (r['run_end_reason'], r['iterations'], r['total_cost'])
            for r in runs
            if r['run_end_reason'] == 'NON_CONVERGING' and float(r['total_cost']) > 3.0
        ]
        failure_detail = main_failure
        if expensive_failures:
            reason, iters, cost = expensive_failures[0]
            failure_detail = f"{reason} ({iters} iters, ${cost})"

        feature_count = len(features_by_product[product])

        summaries.append({
            'product':       product,
            'features':      feature_count,
            'runs':          total_runs,
            'passes':        qa_accepted,
            'avg_cost':      avg_cost,
            'total_cost':    total_cost,
            'failure':       failure_detail,
        })

    return summaries


def format_table(summaries):
    """Format summary data as markdown table."""

    COL = 32  # product name column width

    header  = f"{'Product':<{COL}} | Feat | Runs | Passes | Avg Cost | Total Cost | Main Failure Mode"
    divider = f"{'-'*COL}-|------|------|--------|----------|------------|-------------------"
    lines   = [header, divider]

    for s in summaries:
        name    = s['product'][:COL]
        feat    = str(s['features']).rjust(4)
        runs    = str(s['runs']).rjust(4)
        passes  = str(s['passes']).rjust(6)
        avg     = f"${s['avg_cost']:.2f}".rjust(8)
        total   = f"${s['total_cost']:.2f}".rjust(10)
        failure = s['failure'][:45]

        lines.append(f"{name:<{COL}} | {feat} | {runs} | {passes} | {avg} | {total} | {failure}")

    return "\n".join(lines)

def total_spend(csv_path: Path) -> float:
    total = 0.0
    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                total += float(row.get('total_cost', 0) or 0)
            except ValueError:
                continue
    return total


def load_ai_costs_daily() -> str:
    return ""

def generate_learned_via_chatgpt(table: str, csv_path: Path, model: str) -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set")

    csv_text = csv_path.read_text(encoding="utf-8")

    system_msg = (
        "You are a blunt, technical editor. Produce concise, specific bullet points "
        "based only on the provided data."
    )
    user_msg = "\n".join([
        "You are helping me draft the “What I learned” bullets for a public post about stress-testing my AI SaaS build harness.",
        "",
        "Inputs:",
        "- Summary table (markdown)",
        "- Full CSV run log",
        "",
        "Task:",
        "1. Read the table and CSV to identify the 3–5 most meaningful, non-obvious insights.",
        "2. Focus on cost, convergence, failure modes, and scalability issues.",
        "3. Write a short “What I learned:” section with 3–5 bullet points.",
        "4. Be blunt, technical, and specific. Avoid hype.",
        "5. Do NOT invent data not present in the table/CSV.",
        "6. Keep each bullet under 140 characters.",
        "",
        "Output format:",
        "What I learned:",
        "- bullet 1",
        "- bullet 2",
        "- bullet 3",
        "(optional bullet 4/5)",
        "",
        "Summary table:",
        table,
        "",
        "CSV:",
        csv_text
    ])

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg}
        ],
        "max_tokens": 400,
        "temperature": 0.2
    }

    resp = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=60
    )
    resp.raise_for_status()
    data = resp.json()
    _log_chatgpt_cost(data)
    return data["choices"][0]["message"]["content"].strip()

def generate_learned_via_claude(table: str, csv_path: Path, model: str) -> str:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")

    csv_text = csv_path.read_text(encoding="utf-8")

    prompt = "\n".join([
        "You are a blunt, technical editor. Produce concise, specific bullet points based only on the provided data.",
        "",
        "You are helping me draft the “What I learned” bullets for a public post about stress-testing my AI SaaS build harness.",
        "",
        "Inputs:",
        "- Summary table (markdown)",
        "- Full CSV run log",
        "",
        "Task:",
        "1. Read the table and CSV to identify the 3–5 most meaningful, non-obvious insights.",
        "2. Focus on cost, convergence, failure modes, and scalability issues.",
        "3. Write a short “What I learned:” section with 3–5 bullet points.",
        "4. Be blunt, technical, and specific. Avoid hype.",
        "5. Do NOT invent data not present in the table/CSV.",
        "6. Keep each bullet under 140 characters.",
        "",
        "Output format:",
        "What I learned:",
        "- bullet 1",
        "- bullet 2",
        "- bullet 3",
        "(optional bullet 4/5)",
        "",
        "Summary table:",
        table,
        "",
        "CSV:",
        csv_text
    ])

    payload = {
        "model": model,
        "max_tokens": 400,
        "messages": [{"role": "user", "content": prompt}]
    }

    resp = requests.post(
        CLAUDE_API,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json=payload,
        timeout=60
    )
    resp.raise_for_status()
    data = resp.json()
    _log_claude_cost(data, model)
    return data["content"][0]["text"].strip()

def _log_chatgpt_cost(response: dict):
    """Append ChatGPT token usage + cost to a CSV log."""
    usage = response.get("usage", {})
    in_tokens = usage.get("prompt_tokens", 0) or 0
    out_tokens = usage.get("completion_tokens", 0) or 0

    in_rate = float(os.getenv("OPENAI_INPUT_PER_MTOK", "2.50"))
    out_rate = float(os.getenv("OPENAI_OUTPUT_PER_MTOK", "10.00"))

    in_cost = in_tokens * in_rate / 1_000_000
    out_cost = out_tokens * out_rate / 1_000_000
    total = in_cost + out_cost

    log_path = Path("./harness_summary_costs.csv")
    new_file = not log_path.exists()
    now = datetime.now()

    with log_path.open("a", newline="") as f:
        writer = csv.writer(f)
        if new_file:
            writer.writerow([
                "date", "time", "provider", "model",
                "input_tokens", "output_tokens", "cost"
            ])
        writer.writerow([
            now.strftime("%Y-%m-%d"),
            now.strftime("%H:%M:%S"),
            "chatgpt",
            os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            in_tokens,
            out_tokens,
            f"{total:.6f}"
        ])

def _log_claude_cost(response: dict, model: str):
    """Append Claude token usage + cost to a CSV log."""
    usage = response.get("usage", {})
    in_tokens = usage.get("input_tokens", 0) or 0
    out_tokens = usage.get("output_tokens", 0) or 0

    in_rate = float(os.getenv("ANTHROPIC_INPUT_PER_MTOK", "3.00"))
    out_rate = float(os.getenv("ANTHROPIC_OUTPUT_PER_MTOK", "15.00"))

    in_cost = in_tokens * in_rate / 1_000_000
    out_cost = out_tokens * out_rate / 1_000_000
    total = in_cost + out_cost

    log_path = Path("./harness_summary_costs.csv")
    new_file = not log_path.exists()
    now = datetime.now()

    with log_path.open("a", newline="") as f:
        writer = csv.writer(f)
        if new_file:
            writer.writerow([
                "date", "time", "provider", "model",
                "input_tokens", "output_tokens", "cost"
            ])
        writer.writerow([
            now.strftime("%Y-%m-%d"),
            now.strftime("%H:%M:%S"),
            "claude",
            model,
            in_tokens,
            out_tokens,
            f"{total:.6f}"
        ])


def format_post(summaries, csv_path: Path, learned_section: str) -> str:
    table = format_table(summaries)
    total_cost = total_spend(csv_path)
    total_runs = sum(s['runs'] for s in summaries)
    total_passes = sum(s['passes'] for s in summaries)
    pass_rate = (total_passes / total_runs * 100) if total_runs > 0 else 0
    total_targets = 70
    down = len(summaries)
    to_go = max(total_targets - down, 0)

    parts = [
        f"Title: Building {total_targets} SaaS products to stress-test my AI build harness — {down} down, {to_go} to go",
        "Body:",
        "I built a deterministic SaaS harness with 53 capabilities (auth, payments, fraud detection, GDPR compliance, the works). Now I need to know if it actually works at scale.",
        "So I'm building 70 different SaaS products through it. Real FastAPI + React + Stripe deployments. If the harness breaks, I fix it. If it holds, I know it's solid.",
        f"Here's what the harness logged from builds 1-{down}:",
        table,
        "",
        f"Total: {total_runs} runs, {total_passes} clean builds ({pass_rate:.0f}% first-pass success), ${total_cost:.2f} spent",
        learned_section,
        "",
        "Following this for the next 6 months. Will post failures and edge cases as I find them."
    ]
    return "\n".join(parts)

def main():
    parser = argparse.ArgumentParser(description="Summarize harness runs and draft a post")
    parser.add_argument("csv_path", help="Path to fo_run_log.csv")
    parser.add_argument("--model", default="gpt-4o-mini", help="OpenAI model for 'What I learned'")
    parser.add_argument("--no-chatgpt", action="store_true", help="Use Claude instead of ChatGPT")
    parser.add_argument("--claude-model", default=DEFAULT_CLAUDE_MODEL, help="Claude model for 'What I learned'")
    args = parser.parse_args()

    csv_path = Path(args.csv_path)
    
    if not csv_path.exists():
        print(f"Error: {csv_path} not found")
        sys.exit(1)

    if args.no_chatgpt:
        if not os.getenv("ANTHROPIC_API_KEY"):
            print("Error: ANTHROPIC_API_KEY not set. Aborting without generating a summary.")
            sys.exit(2)
    else:
        if not os.getenv("OPENAI_API_KEY"):
            print("Error: OPENAI_API_KEY not set. Aborting without generating a summary.")
            sys.exit(3)
    
    summaries = summarize_runs(csv_path)
    table = format_table(summaries)

    if args.no_chatgpt:
        try:
            learned_section = generate_learned_via_claude(table, csv_path, args.claude_model)
        except Exception as e:
            print(f"Error: Claude call failed: {e}. Aborting without generating a summary.")
            sys.exit(4)
    else:
        try:
            learned_section = generate_learned_via_chatgpt(table, csv_path, args.model)
        except Exception as e:
            print(f"Error: ChatGPT call failed: {e}. Aborting without generating a summary.")
            sys.exit(5)

    output = format_post(summaries, csv_path, learned_section)

    print(f"\n{output}\n")

    # Save output to timestamped file
    out_dir = Path("./harness_summaries")
    out_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"harness_summary_{timestamp}.txt"
    out_path.write_text(output, encoding="utf-8")
    print(f"Saved summary to: {out_path}")


if __name__ == '__main__':
    main()
