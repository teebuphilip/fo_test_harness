#!/usr/bin/env bash
set -euo pipefail

CSV_PATH="${1:-./fo_run_log.csv}"

python summarize_harness_runs.py "${CSV_PATH}"
