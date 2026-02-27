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
orig = comparison["original_score"]
fixed = comparison["fixed_score"]
print(f"Spec Quality: original {orig.total}/100 → fixed {fixed.total}/100")
print("Original breakdown:")
print(f"  Completeness: {orig.completeness}/30")
print(f"  Consistency: {orig.consistency}/25")
print(f"  Specificity: {orig.specificity}/20")
print(f"  Business Intel: {orig.business_intel}/15")
print(f"  Technical Depth: {orig.technical_depth}/10")
print("Fixed breakdown:")
print(f"  Completeness: {fixed.completeness}/30")
print(f"  Consistency: {fixed.consistency}/25")
print(f"  Specificity: {fixed.specificity}/20")
print(f"  Business Intel: {fixed.business_intel}/15")
print(f"  Technical Depth: {fixed.technical_depth}/10")
print(f"Spec Quality Verdict: {comparison['verdict']}")
PY
