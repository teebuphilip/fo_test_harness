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


def summarize_runs(csv_path):
    """Parse CSV and generate summary statistics by startup."""
    
    # Data structure: startup_name -> list of run records
    runs_by_startup = defaultdict(list)
    
    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            startup = row['startup']
            runs_by_startup[startup].append(row)
    
    # Calculate stats for each startup
    summaries = []
    
    for startup, runs in runs_by_startup.items():
        total_runs = len(runs)
        qa_accepted = sum(1 for r in runs if r['run_end_reason'] == 'QA_ACCEPTED')
        
        # Calculate average cost for QA_ACCEPTED runs only
        accepted_costs = [
            float(r['total_cost']) 
            for r in runs 
            if r['run_end_reason'] == 'QA_ACCEPTED' and float(r['total_cost']) > 0
        ]
        avg_cost = sum(accepted_costs) / len(accepted_costs) if accepted_costs else 0
        
        # Find most common failure mode (excluding QA_ACCEPTED)
        failures = [r['run_end_reason'] for r in runs if r['run_end_reason'] != 'QA_ACCEPTED']
        failure_counts = defaultdict(int)
        for f in failures:
            failure_counts[f] += 1
        
        main_failure = max(failure_counts.items(), key=lambda x: x[1])[0] if failure_counts else "None"
        
        # Look for expensive non-converging runs
        expensive_failures = [
            (r['run_end_reason'], r['iterations'], r['total_cost'])
            for r in runs
            if r['run_end_reason'] == 'NON_CONVERGING' and float(r['total_cost']) > 3.0
        ]
        
        failure_detail = main_failure
        if expensive_failures:
            reason, iters, cost = expensive_failures[0]
            failure_detail = f"{reason} ({iters} iters, ${cost})"
        
        summaries.append({
            'startup': startup,
            'runs': total_runs,
            'passes': qa_accepted,
            'avg_cost': avg_cost,
            'failure': failure_detail
        })
    
    return summaries


def format_table(summaries):
    """Format summary data as markdown table."""
    
    # Calculate totals
    total_runs = sum(s['runs'] for s in summaries)
    total_passes = sum(s['passes'] for s in summaries)
    pass_rate = (total_passes / total_runs * 100) if total_runs > 0 else 0
    
    # Build table
    lines = []
    lines.append("Product                      | Runs | Passes | Avg Cost | Main Failure Mode")
    lines.append("-----------------------------|------|--------|----------|-------------------")
    
    for s in summaries:
        name = s['startup'].replace('_', ' ').title()[:28]  # Truncate long names
        runs = str(s['runs']).rjust(4)
        passes = str(s['passes']).rjust(6)
        cost = f"${s['avg_cost']:.2f}".rjust(8)
        failure = s['failure'][:40]  # Truncate long failure messages
        
        lines.append(f"{name:<28} | {runs} | {passes} | {cost} | {failure}")
    
    lines.append("")
    lines.append(f"Total: {total_runs} runs, {total_passes} clean builds ({pass_rate:.0f}% first-pass success)")

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
    return data["choices"][0]["message"]["content"].strip()


def format_post(summaries, csv_path: Path, learned_section: str) -> str:
    table = format_table(summaries)
    total_cost = total_spend(csv_path)
    total_runs = sum(s['runs'] for s in summaries)
    total_passes = sum(s['passes'] for s in summaries)
    pass_rate = (total_passes / total_runs * 100) if total_runs > 0 else 0

    return "\n".join([
        "Title: Building 70 SaaS products to stress-test my AI build harness — 3 down, 67 to go",
        "Body:",
        "I spent 25 years in DevOps. I hate vibe-coded bullshit.",
        "I built a deterministic SaaS harness with 53 capabilities (auth, payments, fraud detection, GDPR compliance, the works). Now I need to know if it actually works at scale.",
        "So I'm building 70 different SaaS products through it. Real FastAPI + React + Stripe deployments. If the harness breaks, I fix it. If it holds, I know it's solid.",
        "Here's what the harness logged from builds 1-3:",
        table,
        "",
        f"Total: {total_runs} runs, {total_passes} clean builds ({pass_rate:.0f}% first-pass success), ${total_cost:.2f} spent",
        learned_section,
        "",
        "Following this for the next 6 months. Will post failures and edge cases as I find them."
    ])

def main():
    parser = argparse.ArgumentParser(description="Summarize harness runs and draft a post")
    parser.add_argument("csv_path", help="Path to fo_run_log.csv")
    parser.add_argument("--model", default="gpt-4o-mini", help="OpenAI model for 'What I learned'")
    parser.add_argument("--no-chatgpt", action="store_true", help="Skip ChatGPT and use fallback bullets")
    args = parser.parse_args()

    csv_path = Path(args.csv_path)
    
    if not csv_path.exists():
        print(f"Error: {csv_path} not found")
        sys.exit(1)
    
    summaries = summarize_runs(csv_path)
    table = format_table(summaries)

    learned_section = None
    if args.no_chatgpt:
        learned_section = "\n".join([
            "What I learned:",
            "- Need convergence detection at iteration 7 (one build hit 15 iterations, $5.40 before I killed it)",
            "- Complex DB schemas break build truncation logic",
            "- Average $3 per accepted build is way cheaper than I expected"
        ])
    else:
        try:
            learned_section = generate_learned_via_chatgpt(table, csv_path, args.model)
        except Exception as e:
            learned_section = "\n".join([
                "What I learned:",
                f"- (ChatGPT call failed: {e})",
                "- Need convergence detection at iteration 7 (one build hit 15 iterations, $5.40 before I killed it)",
                "- Complex DB schemas break build truncation logic",
                "- Average $3 per accepted build is way cheaper than I expected"
            ])

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
