#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  gap-analysis/run_pricing_modeler.sh <business_brief.json> <one_liner.txt> [--no-ai]

Output:
  gap-analysis/outputs/<brief_basename>_business_brief.json (updated)
USAGE
}

if [[ ${1:-} == "-h" || ${1:-} == "--help" ]]; then
  usage
  exit 0
fi

BRIEF=${1:-}
ONE_LINER=${2:-}
if [[ -z "$BRIEF" || -z "$ONE_LINER" ]]; then
  usage
  exit 1
fi
shift 2 || true

NO_AI=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-ai)
      NO_AI=1
      shift
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
done

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

CMD=(python "$REPO_ROOT/gap-analysis/pricing_modeler.py" \
  --brief "$BRIEF" \
  --one-liner "$ONE_LINER" \
  --out "$BRIEF")

if [[ $NO_AI -eq 1 ]]; then
  CMD+=(--no-ai)
fi

"${CMD[@]}"
