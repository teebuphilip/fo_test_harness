#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  gap-analysis/run_ai_hero_answers.sh <business_brief.json> <one_liner.txt> <name_suggestions.json>

Output:
  intake/ai_text/<picked_name>_hero_answers.txt
USAGE
}

if [[ ${1:-} == "-h" || ${1:-} == "--help" ]]; then
  usage
  exit 0
fi

BRIEF=${1:-}
ONE_LINER=${2:-}
NAMES=${3:-}
if [[ -z "$BRIEF" || -z "$ONE_LINER" || -z "$NAMES" ]]; then
  usage
  exit 1
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

python "$REPO_ROOT/gap-analysis/generate_ai_hero_answers.py" \
  --brief "$BRIEF" \
  --one-liner "$ONE_LINER" \
  --name-suggestions "$NAMES"

picked_slug=$(jq -r '.picked.slug // .picked.name // empty' "$NAMES")
if [[ -z "$picked_slug" ]]; then
  base=$(basename "$BRIEF" .json)
  picked_slug="${base%_business_brief}"
fi

hero_txt="$REPO_ROOT/intake/ai_text/${picked_slug}_hero_answers.txt"
hero_json="$REPO_ROOT/intake/ai_text/${picked_slug}.json"

startup_name=$(python - <<PY
import re
s = "${picked_slug}"
parts = re.split(r"[_\\-\\s]+", s.strip())
print("".join(p.capitalize() for p in parts if p))
PY
)

python "$REPO_ROOT/intake/convert_hero_answers.py" "$hero_txt" "$hero_json" \
  --startup-id "$picked_slug" \
  --startup-name "$startup_name"
echo "Wrote hero JSON: $hero_json"
