#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  gap-analysis/run_name_picker.sh <intake_json> <business_brief_json>

Output:
  gap-analysis/outputs/<intake_basename>_named.json
  gap-analysis/outputs/<intake_basename>_name_suggestions.json
USAGE
}

if [[ ${1:-} == "-h" || ${1:-} == "--help" ]]; then
  usage
  exit 0
fi

INTAKE=${1:-}
BRIEF=${2:-}
if [[ -z "$INTAKE" || -z "$BRIEF" ]]; then
  usage
  exit 1
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python "$REPO_ROOT/gap-analysis/auto_name_picker.py" --intake "$INTAKE" --brief "$BRIEF" --out-dir "$REPO_ROOT/gap-analysis/outputs"
