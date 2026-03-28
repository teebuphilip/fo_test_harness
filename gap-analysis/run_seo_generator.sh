#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  gap-analysis/run_seo_generator.sh [business_brief.json]

Input:
  If provided, uses that file. Otherwise uses the newest *_business_brief.json in gap-analysis/outputs.

Output:
  seo/<input_basename>_seo.json
USAGE
}

if [[ ${1:-} == "-h" || ${1:-} == "--help" ]]; then
  usage
  exit 0
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ -n ${1:-} ]]; then
  INPUT="$1"
else
  INPUT="$(ls -t "$REPO_ROOT/gap-analysis/outputs/"*_business_brief.json 2>/dev/null | head -n 1)"
fi

if [[ -z "${INPUT:-}" ]]; then
  echo "No business brief found. Run run_pass0.sh first." >&2
  exit 1
fi

BASE=$(basename "$INPUT" .json)
OUT="$REPO_ROOT/seo/${BASE}_seo.json"

python "$REPO_ROOT/gap-analysis/seo_generator.py" --input "$INPUT" --out "$OUT"
echo "SEO output:"
cat "$OUT"
