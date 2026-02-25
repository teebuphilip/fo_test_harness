#!/usr/bin/env python3
"""
Summarize FounderOps harness runs from CSV log.

Usage:
    python summarize_harness_runs.py runs.csv
    
Output: Clean markdown table ready to paste into your post.
"""

import csv
import sys
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


def main():
    if len(sys.argv) != 2:
        print("Usage: python summarize_harness_runs.py runs.csv")
        sys.exit(1)
    
    csv_path = Path(sys.argv[1])
    
    if not csv_path.exists():
        print(f"Error: {csv_path} not found")
        sys.exit(1)
    
    summaries = summarize_runs(csv_path)
    table = format_table(summaries)

    output = "\n".join([
        "Here's what the harness logged:",
        "",
        table,
        "",
        "(Copy the table above and paste into your post)"
    ])

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
