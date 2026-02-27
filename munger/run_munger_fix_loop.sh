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

python munger/munger_ai_fixer.py "$input" --out "$tmp_fixer"
munger/write_aifixed.sh "$input" "$tmp_fixer"

echo "Clean output: $out"
