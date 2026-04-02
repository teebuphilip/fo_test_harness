#!/usr/bin/env bash
set -euo pipefail

PREFIX="${1:-}"
if [[ -z "$PREFIX" ]]; then
  echo "Usage: $0 <startup_prefix>"
  exit 1
fi

OUT_BASE="analysis_output/by_startup"
mkdir -p "$OUT_BASE"

# Only consider directories in fo_harness_runs
find fo_harness_runs -maxdepth 1 -type d -name "${PREFIX}*" -print \
  | sed 's#.*/##' \
  | grep -v '\.' \
  | sed 's/_BLOCK_.*$//' \
  | sort -u \
  | while read -r SID; do
      [[ -z "$SID" ]] && continue
      echo "=== $SID ==="
      python analyze_runs.py --startup-id "$SID" --output-dir "${OUT_BASE}/${SID}"
    done
