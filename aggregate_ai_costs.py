#!/usr/bin/env python3
"""
Aggregate AI cost CSVs into a single report.

Output headers:
date,time,app,ai,cost,input tokens,output tokens
"""

import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "ai_costs_aggregated.csv"

CANDIDATES = [
    ("munger_ai_fixer", ROOT / "munger" / "munger_ai_costs.csv"),
    ("postintakeassist", ROOT / "postintakeassist" / "post_intake_ai_costs.csv"),
    ("summarize_harness_runs", ROOT / "harness_summary_costs.csv"),
    ("intake", ROOT / "intake" / "intake_run_costs.csv"),
]


def _read_rows(path: Path):
    if not path.exists():
        return []
    with path.open("r", newline="") as f:
        reader = csv.DictReader(f)
        return list(reader)


def main():
    rows_out = []
    for app, path in CANDIDATES:
        rows = _read_rows(path)
        for r in rows:
            rows_out.append({
                "date": r.get("date", ""),
                "time": r.get("time", ""),
                "app": app,
                "ai": r.get("provider", ""),
                "cost": r.get("cost", ""),
                "input tokens": r.get("input_tokens", ""),
                "output tokens": r.get("output_tokens", ""),
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


if __name__ == "__main__":
    main()
