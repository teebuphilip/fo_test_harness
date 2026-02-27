#!/usr/bin/env bash
set -euo pipefail

CSV_PATH="${1:-./fo_run_log.csv}"

python aggregate_ai_costs.py
python summarize_harness_runs.py "${CSV_PATH}"
