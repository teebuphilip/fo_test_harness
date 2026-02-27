#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "Usage: $0 <original_hero.json> <fixer_output.json>" >&2
  exit 1
fi

orig="$1"
fixer="$2"

dir="$(cd "$(dirname "$orig")" && pwd)"
base="$(basename "$orig")"
out="$dir/aifixed.$base"

python - <<'PY'
import json
import sys
from pathlib import Path

orig = Path(sys.argv[1])
fixer = Path(sys.argv[2])
out = Path(sys.argv[3])

src = json.loads(orig.read_text())
fx = json.loads(fixer.read_text())

src["hero_answers"] = fx["updated_q1_q11"]
out.write_text(json.dumps(src, indent=2))
print(f"Wrote: {out}")
PY "$orig" "$fixer" "$out"
