#!/usr/bin/env python3
"""
Aggregate AI cost CSVs into a single report.

Output headers:
date,time,app,ai,cost,input tokens,output tokens
"""

import csv
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "ai_costs_aggregated.csv"
DAILY_OUTPUT = ROOT / "ai_costs_daily.csv"

CANDIDATES = [
    ("munger_ai_fixer", ROOT / "munger" / "munger_ai_costs.csv"),
    ("postintakeassist", ROOT / "postintakeassist" / "post_intake_ai_costs.csv"),
    ("summarize_harness_runs", ROOT / "harness_summary_costs.csv"),
]


def _read_rows(path: Path):
    if not path.exists():
        return []
    with path.open("r", newline="") as f:
        reader = csv.DictReader(f)
        return list(reader)


def _read_intake_runs():
    rows_out = []
    intake_root = ROOT / "intake" / "intake_runs"
    if not intake_root.exists():
        return rows_out
    for path in intake_root.rglob("intake_run_costs.csv"):
        for r in _read_rows(path):
            rows_out.append(r)
    return rows_out


def _read_run_log():
    path = ROOT / "fo_run_log.csv"
    if not path.exists():
        return []
    rows = _read_rows(path)
    out = []
    for r in rows:
        out.append({
            "date": r.get("date", ""),
            "time": r.get("time", ""),
            "app": "harness_run",
            "ai": "claude",
            "cost": r.get("cost_claude", ""),
            "input tokens": "",
            "output tokens": "",
        })
        out.append({
            "date": r.get("date", ""),
            "time": r.get("time", ""),
            "app": "harness_run",
            "ai": "chatgpt",
            "cost": r.get("cost_chatgpt", ""),
            "input tokens": "",
            "output tokens": "",
        })
    return out


def main():
    rows_out = []
    for app, path in CANDIDATES:
        rows = _read_rows(path)
        for r in rows:
            cost_val = float(r.get("cost") or 0)
            cost_rounded = math.ceil(cost_val * 100) / 100
            rows_out.append({
                "date": r.get("date", ""),
                "time": r.get("time", ""),
                "app": app,
                "ai": r.get("provider", ""),
                "cost": f"{cost_rounded:.2f}",
                "input tokens": r.get("input_tokens", ""),
                "output tokens": r.get("output_tokens", ""),
            })

    for r in _read_intake_runs():
        cost_val = float(r.get("cost") or 0)
        cost_rounded = math.ceil(cost_val * 100) / 100
        rows_out.append({
            "date": r.get("date", ""),
            "time": r.get("time", ""),
            "app": "intake",
            "ai": r.get("provider", ""),
            "cost": f"{cost_rounded:.2f}",
            "input tokens": r.get("input_tokens", ""),
            "output tokens": r.get("output_tokens", ""),
        })

    for r in _read_run_log():
        cost_val = float(r.get("cost") or 0)
        cost_rounded = math.ceil(cost_val * 100) / 100
        rows_out.append({
            "date": r.get("date", ""),
            "time": r.get("time", ""),
            "app": r.get("app", "harness_run"),
            "ai": r.get("ai", ""),
            "cost": f"{cost_rounded:.2f}",
            "input tokens": r.get("input tokens", ""),
            "output tokens": r.get("output tokens", ""),
        })

    with OUTPUT.open("w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["date", "time", "app", "ai", "cost", "input tokens", "output tokens"],
        )
        writer.writeheader()
        for r in rows_out:
            writer.writerow(r)

    print(f"Wrote: {OUTPUT}")

    # Daily summary by AI provider (cost only)
    daily = {}
    for r in rows_out:
        date = r.get("date", "")
        ai = r.get("ai", "")
        key = (date, ai)
        if key not in daily:
            daily[key] = {"cost": 0.0}
        try:
            daily[key]["cost"] += float(r.get("cost") or 0)
        except ValueError:
            pass

    with DAILY_OUTPUT.open("w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["date", "ai", "cost"],
        )
        writer.writeheader()
        for (date, ai), vals in sorted(daily.items()):
            cost_rounded = math.ceil(vals["cost"] * 100) / 100
            writer.writerow({
                "date": date,
                "ai": ai,
                "cost": f"{cost_rounded:.2f}",
            })

    print(f"Wrote: {DAILY_OUTPUT}")


if __name__ == "__main__":
    main()
