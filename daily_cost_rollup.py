#!/usr/bin/env python3
"""
daily_cost_rollup.py

Reads all source cost CSVs and produces a daily rollup:
  date, claude_cost, chatgpt_cost, total_cost

Output: ai_costs_daily.csv (overwrites)

Source files:
  - fo_run_log.csv                        (cost_claude / cost_chatgpt columns)
  - deploy/deploy_ai_costs.csv            (provider / cost columns)
  - munger/munger_ai_costs.csv            (provider / cost columns)
  - harness_summary_costs.csv             (provider / cost columns)
  - postintakeassist/post_intake_ai_costs.csv  (provider / cost columns)
"""

import csv
import os
from collections import defaultdict

BASE = os.path.dirname(os.path.abspath(__file__))
OUTPUT = os.path.join(BASE, "ai_costs_daily.csv")

# source files that have explicit cost_claude / cost_chatgpt columns
SPLIT_SOURCES = [
    "fo_run_log.csv",
]

# source files that have provider + cost columns
PROVIDER_SOURCES = [
    "deploy/deploy_ai_costs.csv",
    "munger/munger_ai_costs.csv",
    "harness_summary_costs.csv",
    "postintakeassist/post_intake_ai_costs.csv",
]

# normalize provider strings → "claude" or "chatgpt"
def classify_provider(provider: str) -> str:
    p = provider.lower().strip()
    if p in ("claude", "anthropic"):
        return "claude"
    if p in ("chatgpt", "openai", "gpt"):
        return "chatgpt"
    return None


def main():
    # date → {claude: float, chatgpt: float}
    totals = defaultdict(lambda: {"claude": 0.0, "chatgpt": 0.0})

    # --- split-column sources ---
    for rel in SPLIT_SOURCES:
        path = os.path.join(BASE, rel)
        if not os.path.exists(path):
            print(f"  [skip] not found: {rel}")
            continue
        with open(path, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                date = row.get("date", "").strip()
                if not date:
                    continue
                try:
                    totals[date]["claude"]  += float(row.get("cost_claude",  0) or 0)
                    totals[date]["chatgpt"] += float(row.get("cost_chatgpt", 0) or 0)
                except ValueError:
                    continue
        print(f"  [ok] {rel}")

    # --- provider-column sources ---
    for rel in PROVIDER_SOURCES:
        path = os.path.join(BASE, rel)
        if not os.path.exists(path):
            print(f"  [skip] not found: {rel}")
            continue
        with open(path, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                date = row.get("date", "").strip()
                if not date:
                    continue
                provider = classify_provider(row.get("provider", ""))
                if provider is None:
                    continue
                try:
                    cost = float(row.get("cost", 0) or 0)
                    totals[date][provider] += cost
                except ValueError:
                    continue
        print(f"  [ok] {rel}")

    # --- write output ---
    rows = sorted(totals.items())
    with open(OUTPUT, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["date", "claude_cost", "chatgpt_cost", "total_cost"])
        for date, costs in rows:
            claude  = round(costs["claude"],  4)
            chatgpt = round(costs["chatgpt"], 4)
            total   = round(claude + chatgpt, 4)
            writer.writerow([date, claude, chatgpt, total])

    print(f"\nWrote {len(rows)} days → {OUTPUT}")


if __name__ == "__main__":
    main()
