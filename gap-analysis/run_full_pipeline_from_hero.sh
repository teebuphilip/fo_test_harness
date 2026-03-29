#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  gap-analysis/run_full_pipeline_from_hero.sh <hero_json> [--no-ai] [--verbose]

Runs:
  1) Build brief + one-liner from hero JSON
  2) Pricing modeler (updates brief)
  3) Auto name picker (cheapest among top-5)
  4) SEO generator (uses brief)
  5) Marketing copy (uses brief + SEO)
  6) GTM plan (uses brief + one-liner)
USAGE
}

if [[ ${1:-} == "-h" || ${1:-} == "--help" ]]; then
  usage
  exit 0
fi

HERO=${1:-}
if [[ -z "$HERO" ]]; then
  usage
  exit 1
fi
shift || true

NO_AI=0
VERBOSE=0
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
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
 done

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

BASE=$(python - "$HERO" <<'PY'
import json, sys, os
with open(sys.argv[1], "r", encoding="utf-8") as f:
    data = json.load(f)
base = data.get("startup_idea_id") or os.path.splitext(os.path.basename(sys.argv[1]))[0]
print(base)
PY
)

OUT_DIR="$REPO_ROOT/gap-analysis/outputs"
BRIEF="$OUT_DIR/${BASE}_business_brief.json"
ONE_LINER="$OUT_DIR/${BASE}_one_liner.txt"
INTAKE_STUB="$OUT_DIR/${BASE}_intake_stub.json"

echo "============================================================"
echo "[pipeline] build_brief_from_hero.py"
python "$REPO_ROOT/gap-analysis/build_brief_from_hero.py" \
  --hero "$HERO" \
  --out-brief "$BRIEF" \
  --out-one-liner "$ONE_LINER"
echo "============================================================"

PRICING_CMD=("$REPO_ROOT/gap-analysis/run_pricing_modeler.sh" "$BRIEF" "$ONE_LINER")
if [[ $NO_AI -eq 1 ]]; then
  PRICING_CMD+=(--no-ai)
fi
echo "[pipeline] run_pricing_modeler.sh"
"${PRICING_CMD[@]}"
echo "Updated business brief:"
cat "$BRIEF"
echo "============================================================"

python - "$HERO" "$INTAKE_STUB" <<'PY'
import json, sys
from pathlib import Path

hero_path = Path(sys.argv[1])
stub_path = Path(sys.argv[2])
with hero_path.open("r", encoding="utf-8") as f:
    hero = json.load(f)

name = hero.get("startup_name") or hero.get("startup_idea_id") or "Startup"
summary = hero.get("startup_description") or ""

stub = {
    "startup_name": name,
    "summary": summary,
    "block_a": {
        "pass_1": {"one_liner": summary, "target_user_persona": ""},
        "pass_3": {"tier_1_core_features": []},
    },
    "block_b": {"pass_1": {"one_liner": ""}},
}
stub_path.parent.mkdir(parents=True, exist_ok=True)
with stub_path.open("w", encoding="utf-8") as f:
    json.dump(stub, f, indent=2)
    f.write("\n")
print(f"[pipeline] Wrote intake stub: {stub_path}")
PY

echo "============================================================"
echo "[pipeline] run_name_picker.sh"
"$REPO_ROOT/gap-analysis/run_name_picker.sh" "$INTAKE_STUB" "$BRIEF"
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

GTM_CMD=("$REPO_ROOT/gap-analysis/run_gtm_plan.sh" "$BRIEF" "$ONE_LINER")
if [[ $NO_AI -eq 1 ]]; then
  GTM_CMD+=(--no-ai)
fi
echo "[pipeline] run_gtm_plan.sh"
"${GTM_CMD[@]}"
echo "============================================================"
