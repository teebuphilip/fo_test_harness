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
                "cost": f"{float(r.get('cost') or 0):.2f}",
                "input tokens": r.get("input_tokens", ""),
                "output tokens": r.get("output_tokens", ""),
            })

    for r in _read_intake_runs():
        rows_out.append({
            "date": r.get("date", ""),
            "time": r.get("time", ""),
            "app": "intake",
            "ai": r.get("provider", ""),
            "cost": f"{float(r.get('cost') or 0):.2f}",
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

    # Daily summary by AI provider
    daily = {}
    for r in rows_out:
        date = r.get("date", "")
        ai = r.get("ai", "")
        key = (date, ai)
        if key not in daily:
            daily[key] = {"cost": 0.0, "input": 0, "output": 0}
        try:
            daily[key]["cost"] += float(r.get("cost") or 0)
        except ValueError:
            pass
        try:
            daily[key]["input"] += int(float(r.get("input tokens") or 0))
        except ValueError:
            pass
        try:
            daily[key]["output"] += int(float(r.get("output tokens") or 0))
        except ValueError:
            pass

    with DAILY_OUTPUT.open("w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["date", "ai", "cost", "input tokens", "output tokens"],
        )
        writer.writeheader()
        for (date, ai), vals in sorted(daily.items()):
            writer.writerow({
                "date": date,
                "ai": ai,
                "cost": f"{vals['cost']:.2f}",
                "input tokens": vals["input"],
                "output tokens": vals["output"],
            })

    print(f"Wrote: {DAILY_OUTPUT}")


if __name__ == "__main__":
    main()
