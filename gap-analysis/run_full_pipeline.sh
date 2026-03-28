#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  gap-analysis/run_full_pipeline.sh <intake_json> [--no-ai] [--verbose] [--force]

Runs:
  1) Pass0 gap check (writes brief)
  2) Pricing modeler (updates brief)
  3) Auto name picker (cheapest among top-5)
  4) AI hero answers (writes Q1-Q11 to intake/ai_text)
  5) SEO generator (uses brief)
  6) Marketing copy (uses brief + SEO)
  7) GTM plan (uses brief + one-liner)
USAGE
}

if [[ ${1:-} == "-h" || ${1:-} == "--help" ]]; then
  usage
  exit 0
fi

INTAKE=${1:-}
if [[ -z "$INTAKE" ]]; then
  usage
  exit 1
fi
shift || true

NO_AI=0
VERBOSE=0
FORCE=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-ai)
      NO_AI=1
      shift
      ;;
    --verbose)
      VERBOSE=1
      shift
      ;;
    --force)
      FORCE=1
      shift
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
 done

BASE=$(basename "$INTAKE" .json)
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRIEF="$REPO_ROOT/gap-analysis/outputs/${BASE}_business_brief.json"
INTAKE_FOR_NAMES="$INTAKE"

if python - "$INTAKE" <<'PY'
import json
import sys
path = sys.argv[1]
with open(path, "r", encoding="utf-8") as f:
    data = json.load(f)
sys.exit(0 if "idea_text" in data else 1)
PY
then
  STUB="$REPO_ROOT/gap-analysis/outputs/${BASE}_intake_stub.json"
  python - "$INTAKE" "$STUB" <<'PY'
import json
import sys
from pathlib import Path

src = Path(sys.argv[1])
dst = Path(sys.argv[2])
with src.open("r", encoding="utf-8") as f:
    data = json.load(f)

idea = data.get("idea_text", "")
stub = {
    "startup_name": idea,
    "summary": idea,
    "block_a": {
        "pass_1": {"one_liner": idea, "target_user_persona": ""},
        "pass_3": {"tier_1_core_features": []},
    },
    "block_b": {"pass_1": {"one_liner": ""}},
}
dst.parent.mkdir(parents=True, exist_ok=True)
with dst.open("w", encoding="utf-8") as f:
    json.dump(stub, f, indent=2)
    f.write("\n")
print(f"[pipeline] Wrote intake stub: {dst}")
PY
  INTAKE_FOR_NAMES="$STUB"
fi

PASS0_CMD=("$REPO_ROOT/gap-analysis/run_pass0.sh" "$INTAKE")
if [[ $NO_AI -eq 1 ]]; then
  PASS0_CMD+=(--no-ai)
fi
if [[ $VERBOSE -eq 1 ]]; then
  PASS0_CMD+=(--verbose)
fi

echo "============================================================"
echo "[pipeline] run_pass0.sh"
"${PASS0_CMD[@]}"
echo "============================================================"

if [[ ! -f "$BRIEF" ]]; then
  echo "Missing brief: $BRIEF" >&2
  exit 1
fi

PASS0_OUT="$REPO_ROOT/gap-analysis/outputs/${BASE}_pass0.json"
if [[ -f "$PASS0_OUT" ]]; then
  STATUS=$(python - "$PASS0_OUT" <<'PY'
import json
import sys
with open(sys.argv[1], "r", encoding="utf-8") as f:
    data = json.load(f)
print(data.get("decision_status", ""))
PY
)
  if [[ "$STATUS" != "BUILD_APPROVED" && $FORCE -eq 0 ]]; then
    echo "Pass0 status is $STATUS. Halting pipeline. Use --force to override."
    exit 2
  fi
fi

PRICING_CMD=("$REPO_ROOT/gap-analysis/run_pricing_modeler.sh" "$BRIEF" "$REPO_ROOT/gap-analysis/outputs/${BASE}_one_liner.txt")
if [[ $NO_AI -eq 1 ]]; then
  PRICING_CMD+=(--no-ai)
fi

echo "[pipeline] run_pricing_modeler.sh"
"${PRICING_CMD[@]}"
echo "Updated business brief:"
cat "$BRIEF"
echo "============================================================"

echo "[pipeline] run_name_picker.sh"
"$REPO_ROOT/gap-analysis/run_name_picker.sh" "$INTAKE_FOR_NAMES" "$BRIEF"
echo "============================================================"

echo "[pipeline] run_ai_hero_answers.sh"
"$REPO_ROOT/gap-analysis/run_ai_hero_answers.sh" \
  "$BRIEF" \
  "$REPO_ROOT/gap-analysis/outputs/${BASE}_one_liner.txt" \
  "$REPO_ROOT/gap-analysis/outputs/${BASE}_intake_stub_name_suggestions.json"

echo "============================================================"

echo "[pipeline] run_seo_generator.sh"
"$REPO_ROOT/gap-analysis/run_seo_generator.sh" "$BRIEF"
echo "============================================================"

SEO_OUT="$REPO_ROOT/seo/$(basename "$BRIEF" .json)_seo.json"
if [[ ! -f "$SEO_OUT" ]]; then
  echo "Missing SEO output: $SEO_OUT" >&2
  exit 1
fi

echo "[pipeline] run_marketing_copy.sh"
"$REPO_ROOT/gap-analysis/run_marketing_copy.sh" "$BRIEF" "$SEO_OUT"
echo "============================================================"

ONE_LINER="$REPO_ROOT/gap-analysis/outputs/${BASE}_one_liner.txt"
if [[ ! -f "$ONE_LINER" ]]; then
  echo "Missing one-liner: $ONE_LINER" >&2
  exit 1
fi

GTM_CMD=("$REPO_ROOT/gap-analysis/run_gtm_plan.sh" "$BRIEF" "$ONE_LINER")
if [[ $NO_AI -eq 1 ]]; then
  GTM_CMD+=(--no-ai)
fi

echo "[pipeline] run_gtm_plan.sh"
"${GTM_CMD[@]}"
echo "============================================================"
