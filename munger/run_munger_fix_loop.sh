#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 <hero_input.json>" >&2
  exit 1
fi

input="$1"
dir="$(cd "$(dirname "$input")" && pwd)"
base="$(basename "$input")"
out="$dir/aifixed.$base"

tmp_fixer="/tmp/munger_fixer_out.json"

python munger_ai_fixer.py "$input" --out "$tmp_fixer"
./write_aifixed.sh "$input" "$tmp_fixer"

echo "Clean output: $out"

python - "$input" "$out" <<'PY'
import json
import sys
from spec_quality_scorer import compare_specs

orig = sys.argv[1]
fixed = sys.argv[2]

with open(orig) as f:
    original_spec = json.load(f)['hero_answers']
with open(fixed) as f:
    fixed_spec = json.load(f)['hero_answers']

comparison = compare_specs(original_spec, fixed_spec)
print(f"Spec Quality Verdict: {comparison['verdict']}")
PY
