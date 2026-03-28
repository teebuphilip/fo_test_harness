#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  gap-analysis/run_marketing_copy.sh <business_brief.json> <seo.json>

Output:
  gap-analysis/outputs/<brief_basename>_marketing_copy.json
USAGE
}

if [[ ${1:-} == "-h" || ${1:-} == "--help" ]]; then
  usage
  exit 0
fi

BRIEF=${1:-}
SEO=${2:-}
if [[ -z "$BRIEF" || -z "$SEO" ]]; then
  usage
  exit 1
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASE=$(basename "$BRIEF" .json)
OUT="$REPO_ROOT/gap-analysis/outputs/${BASE}_marketing_copy.json"

python "$REPO_ROOT/gap-analysis/base_marketing_copy.py" --brief "$BRIEF" --seo "$SEO" --out "$OUT"
echo "Marketing copy output:"
cat "$OUT"
