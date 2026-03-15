#!/usr/bin/env bash
# add_feature.sh — Add ONE new feature to an existing built codebase.
#
# Lifecycle:
#   1. Run feature_adder.py to generate a scoped feature intake from the existing ZIP
#   2. Build the feature via fo_test_harness.py
#   3. Run integration_check.py; if HIGH issues → fix loop (up to 2 passes)
#   4. Merge existing ZIP + feature ZIP → new final ZIP
#
# Usage:
#   ./add_feature.sh \
#     --intake  intake/intake_runs/awi/awi.5.json \
#     --feature "Competitor benchmarking dashboard" \
#     --existing-zip fo_harness_runs/awi_downloadable_exec_report_FINAL_20260309.zip
#
# Required:
#   --intake        Path to original intake JSON (the same one used for the original build)
#   --feature       Name of the new feature to add (wrap in quotes)
#   --existing-zip  Path to the current final ZIP (baseline codebase)
#
# Optional:
#   --startup-id       Base name used for run directories (default: derived from intake stem)
#   --build-gov        Path to FOBUILFINALLOCKED*.zip (default: auto-detected in cwd)
#   --max-iterations N Per-run iteration cap (default: 20)
#
# Resume behaviour (automatic):
#   - If a feature intake JSON already exists and a matching feature ZIP exists → skip build
#   - If a feature ZIP exists but no final ZIP → skip straight to integration check
#   - If a final ZIP already exists → exit immediately

set -euo pipefail

# ── Defaults ──────────────────────────────────────────────────────────────────
BUILD_GOV="$(ls FOBUILFINALLOCKED*.zip 2>/dev/null | head -1 || true)"
MAX_ITER=20
STARTUP_ID=""
INTAKE=""
FEATURE=""
EXISTING_ZIP=""

# ── Helpers ───────────────────────────────────────────────────────────────────
latest_artifacts_dir() {
  local run_dir="$1"
  python3 - "$run_dir" <<'PYEOF'
import os, re, sys
run_dir = sys.argv[1]
for build_sub in ('build', '_harness/build'):
    build = os.path.join(run_dir, build_sub)
    if not os.path.isdir(build):
        continue
    dirs = [d for d in os.listdir(build)
            if re.match(r'iteration_\d+_artifacts$', d)
            and os.path.isdir(os.path.join(build, d))]
    if dirs:
        best = max(dirs, key=lambda d: int(re.search(r'(\d+)', d).group(1)))
        print(os.path.join(build, best))
        sys.exit(0)
PYEOF
}

latest_iteration_num() {
  local artifacts_dir="$1"
  [[ -z "$artifacts_dir" ]] && echo "" && return
  python3 -c "
import re, sys
m = re.search(r'iteration_(\d+)_artifacts', '$artifacts_dir')
print(int(m.group(1)) if m else '')
"
}

slugify() {
  python3 -c "import re, sys; print(re.sub(r'[^a-z0-9]+','_',sys.argv[1].lower()).strip('_')[:40])" "$1"
}

# ── Parse args ────────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --intake)           INTAKE="$2";       shift 2 ;;
    --feature)          FEATURE="$2";      shift 2 ;;
    --existing-zip)     EXISTING_ZIP="$2"; shift 2 ;;
    --startup-id)       STARTUP_ID="$2";   shift 2 ;;
    --build-gov)        BUILD_GOV="$2";    shift 2 ;;
    --max-iterations)   MAX_ITER="$2";     shift 2 ;;
    *) echo "Unknown flag: $1"; exit 1 ;;
  esac
done

# ── Validate required args ────────────────────────────────────────────────────
if [[ -z "$INTAKE" ]]; then
  echo "ERROR: --intake is required"
  echo "Usage: $0 --intake <path> --feature \"Feature Name\" --existing-zip <path>"
  exit 1
fi
if [[ -z "$FEATURE" ]]; then
  echo "ERROR: --feature is required"
  exit 1
fi
if [[ -z "$EXISTING_ZIP" ]]; then
  echo "ERROR: --existing-zip is required (path to current final ZIP)"
  exit 1
fi
if [[ ! -f "$INTAKE" ]]; then
  echo "ERROR: Intake not found: $INTAKE"
  exit 1
fi
if [[ ! -f "$EXISTING_ZIP" ]]; then
  echo "ERROR: Existing ZIP not found: $EXISTING_ZIP"
  exit 1
fi
if [[ -z "$BUILD_GOV" || ! -f "$BUILD_GOV" ]]; then
  echo "ERROR: Build governance ZIP not found."
  echo "  Drop FOBUILFINALLOCKED*.zip into this directory, or pass --build-gov <path>"
  exit 1
fi

# ── Derive identifiers ────────────────────────────────────────────────────────
if [[ -z "$STARTUP_ID" ]]; then
  STARTUP_ID=$(basename "$INTAKE" .json | sed 's/\./_/g')
fi

INTAKE_DIR=$(dirname "$INTAKE")
INTAKE_STEM=$(basename "$INTAKE" .json)
FEATURE_SLUG=$(slugify "$FEATURE")
FEATURE_INTAKE="${INTAKE_DIR}/${INTAKE_STEM}_feature_${FEATURE_SLUG}.json"

# startup_idea_id for the feature run: base_id + slug (mirrors feature_adder.py)
BASE_ID=$(python3 -c "import json; print(json.load(open('$INTAKE')).get('startup_idea_id','unknown').rstrip('_'))")
STARTUP_SLUG="${BASE_ID}_${FEATURE_SLUG}"

echo "========================================================"
echo "  ADD FEATURE PIPELINE"
echo "  Intake        : $INTAKE"
echo "  Feature       : $FEATURE"
echo "  Feature slug  : $FEATURE_SLUG"
echo "  Existing ZIP  : $EXISTING_ZIP"
echo "  Max iter      : $MAX_ITER"
echo "  Build GOV     : $BUILD_GOV"
echo "========================================================"
echo ""

# ── Early exit: new final ZIP already exists ──────────────────────────────────
EXISTING_FINAL=$(ls -t "fo_harness_runs/${STARTUP_ID}_${FEATURE_SLUG}_FINAL_"*.zip 2>/dev/null | head -1 || true)
if [[ -n "$EXISTING_FINAL" ]]; then
  echo "✓ Already complete — final ZIP exists: $EXISTING_FINAL"
  echo "  Delete it and rerun to rebuild."
  exit 0
fi

# ── Step 1: Generate scoped feature intake ────────────────────────────────────
echo "▶ STEP 1 — Generate Feature Intake"
echo "────────────────────────────────────────────────────────"

if [[ -f "$FEATURE_INTAKE" ]]; then
  echo "  ↩ Feature intake already exists — skipping generation:"
  echo "    $FEATURE_INTAKE"
else
  python feature_adder.py \
    --intake "$INTAKE" \
    --manifest "$EXISTING_ZIP" \
    --feature "$FEATURE"

  if [[ ! -f "$FEATURE_INTAKE" ]]; then
    echo "ERROR: feature_adder.py did not produce: $FEATURE_INTAKE"
    exit 1
  fi
  echo "✓ Feature intake: $FEATURE_INTAKE"
fi
echo ""

# ── Step 2: Build feature via harness ─────────────────────────────────────────
echo "▶ STEP 2 — Build Feature: $FEATURE"
echo "────────────────────────────────────────────────────────"

# Check if a feature ZIP already exists (auto-resume)
FEATURE_ZIP=$(ls -t "fo_harness_runs/${STARTUP_SLUG}_BLOCK_B_"*.zip 2>/dev/null | grep -v '_full_' | head -1 || true)
FEATURE_RUN_DIR=""

if [[ -n "$FEATURE_ZIP" ]]; then
  echo "  ↩ Feature ZIP already exists — skipping harness build:"
  echo "    $FEATURE_ZIP"
  FEATURE_RUN_DIR="${FEATURE_ZIP%.zip}"
else
  # Resolve the existing ZIP's run dir for --prior-run (passes QA prohibitions)
  EXISTING_RUN_DIR="${EXISTING_ZIP%.zip}"

  BUILD_EXIT=0
  if [[ -d "$EXISTING_RUN_DIR" ]]; then
    python fo_test_harness.py \
      "$FEATURE_INTAKE" \
      "$BUILD_GOV" \
      --max-iterations "$MAX_ITER" \
      --prior-run "$EXISTING_RUN_DIR" || BUILD_EXIT=$?
  else
    python fo_test_harness.py \
      "$FEATURE_INTAKE" \
      "$BUILD_GOV" \
      --max-iterations "$MAX_ITER" || BUILD_EXIT=$?
  fi

  if [[ $BUILD_EXIT -ne 0 ]]; then
    echo ""
    echo "✗ FEATURE BUILD FAILED (exit $BUILD_EXIT)"
    echo ""
    echo "  Rerun the same command — the script will auto-resume:"
    echo "  ./add_feature.sh --intake $INTAKE --feature \"$FEATURE\" --existing-zip $EXISTING_ZIP"
    exit 1
  fi

  # Find the feature ZIP (most recent matching startup_slug)
  FEATURE_ZIP=$(ls -t "fo_harness_runs/${STARTUP_SLUG}_BLOCK_B_"*.zip 2>/dev/null | grep -v '_full_' | head -1 || true)
  if [[ -z "$FEATURE_ZIP" ]]; then
    echo "ERROR: Feature ZIP not found in fo_harness_runs/ for startup_id: $STARTUP_SLUG"
    exit 1
  fi
  FEATURE_RUN_DIR="${FEATURE_ZIP%.zip}"
fi

echo "✓ Feature ZIP: $FEATURE_ZIP"
echo ""

# ── Step 3: Integration check + fix loop ──────────────────────────────────────
echo "▶ STEP 3 — Integration Check"
echo "────────────────────────────────────────────────────────"

LATEST_ZIP="$FEATURE_ZIP"
LATEST_RUN_DIR="$FEATURE_RUN_DIR"
INTEGRATION_ISSUES="${LATEST_RUN_DIR}/integration_issues.json"

_run_integration_check() {
  local issues_file="$1"
  local artifacts_dir
  artifacts_dir=$(latest_artifacts_dir "$LATEST_RUN_DIR")
  IC_EXIT=0
  if [[ -n "$artifacts_dir" ]]; then
    echo "  Using artifacts dir: $artifacts_dir"
    python integration_check.py \
      --artifacts "$artifacts_dir" \
      --intake "$INTAKE" \
      --output "$issues_file" || IC_EXIT=$?
  else
    echo "  Falling back to ZIP: $LATEST_ZIP"
    python integration_check.py \
      --zip "$LATEST_ZIP" \
      --intake "$INTAKE" \
      --output "$issues_file" || IC_EXIT=$?
  fi
}

_run_integration_check "$INTEGRATION_ISSUES"

# Only run fix pass for HIGH severity issues
IC_HIGH=0
if [[ $IC_EXIT -ne 0 && -f "$INTEGRATION_ISSUES" ]]; then
  IC_HIGH=$(python3 -c "
import json, sys
d = json.load(open('$INTEGRATION_ISSUES'))
print(sum(1 for i in d.get('issues', []) if i.get('severity','').upper() == 'HIGH'))
" 2>/dev/null || echo 0)
  if [[ $IC_HIGH -eq 0 ]]; then
    echo "ℹ Integration issues are MEDIUM-only — skipping fix pass"
    IC_EXIT=0
  fi
fi

MAX_FIX_PASSES=2
FIX_PASS=0

while [[ $IC_EXIT -ne 0 && $FIX_PASS -lt $MAX_FIX_PASSES ]]; do
  FIX_PASS=$((FIX_PASS + 1))
  echo ""
  echo "⚠ Integration issues found (HIGH: $IC_HIGH) — running fix pass $FIX_PASS/$MAX_FIX_PASSES"

  ARTIFACTS_DIR=$(latest_artifacts_dir "$LATEST_RUN_DIR")
  LATEST_ITER=$(latest_iteration_num "$ARTIFACTS_DIR")
  if [[ -z "$LATEST_ITER" ]]; then
    echo "ERROR: Unable to determine latest iteration number for resume."
    exit 1
  fi

  INT_MAX_ITER=$(( LATEST_ITER + 5 ))
  if [[ $INT_MAX_ITER -lt $MAX_ITER ]]; then INT_MAX_ITER=$MAX_ITER; fi

  FIX_EXIT=0
  python fo_test_harness.py \
    "$FEATURE_INTAKE" \
    "$BUILD_GOV" \
    --resume-run "$LATEST_RUN_DIR" \
    --resume-iteration "$LATEST_ITER" \
    --integration-issues "$INTEGRATION_ISSUES" \
    --max-iterations "$INT_MAX_ITER" \
    --no-polish || FIX_EXIT=$?

  if [[ $FIX_EXIT -ne 0 ]]; then
    echo ""
    echo "✗ INTEGRATION FIX PASS $FIX_PASS FAILED (exit $FIX_EXIT)"
    exit 1
  fi

  # Update latest ZIP after fix pass
  FIX_ZIP=$(ls -t "fo_harness_runs/${STARTUP_SLUG}_BLOCK_B_"*.zip 2>/dev/null | grep -v '_full_' | head -1 || true)
  if [[ -z "$FIX_ZIP" ]]; then
    echo "ERROR: ZIP not found after integration fix pass $FIX_PASS."
    exit 1
  fi
  LATEST_ZIP="$FIX_ZIP"
  LATEST_RUN_DIR="${FIX_ZIP%.zip}"

  echo ""
  echo "▶ Re-checking integration (pass $FIX_PASS/$MAX_FIX_PASSES)"
  echo "────────────────────────────────────────────────────────"
  INTEGRATION_ISSUES="${LATEST_RUN_DIR}/integration_issues.json"
  _run_integration_check "$INTEGRATION_ISSUES"

  # Recount HIGH issues for next loop guard
  if [[ $IC_EXIT -ne 0 && -f "$INTEGRATION_ISSUES" ]]; then
    IC_HIGH=$(python3 -c "
import json
d = json.load(open('$INTEGRATION_ISSUES'))
print(sum(1 for i in d.get('issues', []) if i.get('severity','').upper() == 'HIGH'))
" 2>/dev/null || echo 0)
    if [[ $IC_HIGH -eq 0 ]]; then
      echo "ℹ Remaining issues are MEDIUM-only — accepting"
      IC_EXIT=0
    fi
  fi
done

if [[ $IC_EXIT -ne 0 ]]; then
  echo ""
  echo "✗ INTEGRATION CHECK STILL FAILING AFTER $FIX_PASS FIX PASS(ES)"
  echo "  Manual review required. See: $INTEGRATION_ISSUES"
  exit 1
fi

echo "✓ Integration check clean."
echo ""

# ── Step 4: Merge existing ZIP + feature ZIP → new final ZIP ──────────────────
echo "▶ STEP 4 — Merge into new final ZIP"
echo "────────────────────────────────────────────────────────"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
FINAL_ZIP="fo_harness_runs/${STARTUP_ID}_${FEATURE_SLUG}_FINAL_${TIMESTAMP}.zip"
MERGE_TMP=$(mktemp -d)

echo "  Layering (later ZIP wins on conflict):"
echo "    Base : $EXISTING_ZIP"
echo "    New  : $LATEST_ZIP"
echo ""

unzip -q -o "$EXISTING_ZIP" -d "$MERGE_TMP"
unzip -q -o "$LATEST_ZIP"   -d "$MERGE_TMP"

(cd "$MERGE_TMP" && zip -qr - .) > "$FINAL_ZIP"
rm -rf "$MERGE_TMP"

FINAL_SIZE=$(du -sh "$FINAL_ZIP" | cut -f1)

echo "========================================================"
echo "  FEATURE ADD COMPLETE"
echo ""
echo "  Feature       : $FEATURE"
echo "  Base ZIP      : $EXISTING_ZIP"
echo "  Feature ZIP   : $LATEST_ZIP"
echo "  FINAL ZIP     : $FINAL_ZIP  ($FINAL_SIZE)"
echo "========================================================"
echo ""
echo "Next step — deploy:"
echo "  python deploy/zip_to_repo.py $FINAL_ZIP"
