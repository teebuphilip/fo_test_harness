#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  gap-analysis/run_pass0.sh <intake_json> [--no-ai] [--out-dir DIR] [--provider openai|anthropic] [--model MODEL] [--verbose] [--persona-allowlist LIST]

Defaults:
  --provider openai
  --model gpt-4o-mini
  --out-dir gap-analysis/outputs
  allowlist: PASS0_ALLOWLIST env var, or gap-analysis/pass0_allowlist.txt, or built-in defaults
USAGE
}

if [[ ${1:-} == "-h" || ${1:-} == "--help" ]]; then
  usage
  exit 0
fi

INPUT=${1:-}
if [[ -z "$INPUT" ]]; then
  usage
  exit 1
fi
shift || true

NO_AI=0
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT_DIR="${SCRIPT_DIR}/outputs"
PROVIDER="openai"
MODEL="gpt-4o-mini"
VERBOSE=0
ALLOWLIST=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-ai)
      NO_AI=1
      shift
      ;;
    --out-dir)
      OUT_DIR="$2"
      shift 2
      ;;
    --provider)
      PROVIDER="$2"
      shift 2
      ;;
    --model)
      MODEL="$2"
      shift 2
      ;;
    --verbose)
      VERBOSE=1
      shift
      ;;
    --persona-allowlist)
      ALLOWLIST="$2"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
 done

mkdir -p "$OUT_DIR"
BASE=$(basename "$INPUT" .json)
OUT="$OUT_DIR/${BASE}_pass0.json"
BRIEF="$OUT_DIR/${BASE}_brief.json"
ONE="$OUT_DIR/${BASE}_one_liner.txt"

CMD=(python "${SCRIPT_DIR}/pass0_gap_check.py" --input "$INPUT" --out "$OUT" --brief-out "$BRIEF" --one-liner-out "$ONE")
if [[ $NO_AI -eq 0 ]]; then
  CMD+=(--research-provider "$PROVIDER" --research-model "$MODEL")
fi
if [[ $VERBOSE -eq 1 ]]; then
  CMD+=(--verbose)
fi
if [[ -n "$ALLOWLIST" ]]; then
  CMD+=(--persona-allowlist "$ALLOWLIST")
fi

"${CMD[@]}"

echo "Pass 0 output: $OUT"
echo "Builder brief: $BRIEF"
echo "One-liner: $ONE"
echo ""
echo "Builder brief content:"
cat "$BRIEF"
echo ""
echo "Run cost:"
python - "$OUT" <<'PY'
import json
import sys
import math
path = sys.argv[1]
with open(path, "r", encoding="utf-8") as f:
    data = json.load(f)
cost = data.get("research_summary", {}).get("cost_usd")
if cost is None:
    print("$0.00")
else:
    rounded = math.ceil(float(cost) * 100.0) / 100.0
    print(f"${rounded:.2f}")
PY

echo ""
echo "Writing business_brief.json (outputs)"
python - "$BRIEF" "$BASE" <<'PY'
import json
import sys
from pathlib import Path

brief_path = Path(sys.argv[1])
base = sys.argv[2]
repo_root = Path(__file__).resolve().parent.parent
out_path = repo_root / "gap-analysis" / "outputs" / f"{base}_business_brief.json"

with brief_path.open("r", encoding="utf-8") as f:
    data = json.load(f)

locked = data.get("locked_fields", {})

name = locked.get("primary_user", "Unknown Audience")
problem = locked.get("primary_problem", "Unknown problem")
features = locked.get("must_have_features", [])
description = locked.get("mvp_wedge") or data.get("one_liner") or ""

business_brief = {
    "schema_version": "1.0.0",
    "name": f"{name} tool",
    "description": description,
    "target_audience": name,
    "problem_solved": problem,
    "features": features if isinstance(features, list) else [],
    "pricing_model": "unknown",
    "category": "saas",
}

with out_path.open("w", encoding="utf-8") as f:
    json.dump(business_brief, f, indent=2)
    f.write("\n")

print(f"Wrote: {out_path}")
PY
