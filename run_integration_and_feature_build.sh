#!/usr/bin/env bash
# run_integration_and_feature_build.sh — Full feature-by-feature build pipeline
# with post-build integration validation and fix loop.
#
# Flow:
#   1. Runs phase_planner.py to split intake into data layer + feature list
#   2. Builds Phase 1 (data layer, --no-polish)
#   3. For each intelligence feature: runs feature_adder.py then fo_test_harness.py
#      - All but the last feature: --no-polish
#      - Last feature: full polish (README, .env, tests)
#   4. Runs integration_check.py, fixes via harness resume, re-checks
#   5. Merges all ZIPs into a single final deliverable
#
# Usage:
#   ./run_integration_and_feature_build.sh --intake <path/to/intake.json> [options]
#
# Required:
#   --intake        Path to original intake JSON
#
# Optional:
#   --startup-id         Base name for final ZIP (default: derived from intake stem)
#   --build-gov          Path to FOBUILFINALLOCKED100.zip (default: last known)
#   --max-iterations N   Per-phase/feature iteration cap (default: 20)
#   --no-ai              Skip AI classifier in phase_planner (faster, rule-based only)
#   --start-from-feature N  Skip Phase 1 + features 1..(N-1); resume from feature N (1-indexed).
#                           Requires --phase1-zip to supply the Phase 1 output ZIP.
#   --phase1-zip PATH    Use an existing Phase 1 ZIP instead of rebuilding.
#                        Implies --start-from-feature 1 if --start-from-feature not set.
#
# Resume example (Phase 1 done, restart from feature 2):
#   ./run_integration_and_feature_build.sh \
#     --intake intake/intake_runs/awi/awi.5.json \
#     --phase1-zip fo_harness_runs/awi_p1_BLOCK_B_20260309_070205.zip \
#     --start-from-feature 2
#
# Normal example:
#   ./run_integration_and_feature_build.sh \
#     --intake intake/intake_runs/ai_workforce_intelligence/ai_workforce_intelligence.5.json \
#     --startup-id awi

set -euo pipefail

# ── Defaults ──────────────────────────────────────────────────────────────────
BUILD_GOV="$(ls FOBUILFINALLOCKED*.zip 2>/dev/null | head -1)"
MAX_ITER=20
STARTUP_ID=""
INTAKE=""
NO_AI=""
START_FROM_FEATURE=0   # skip Phase 1 + features 1..(N-1), resume from feature N (1-indexed)
PHASE1_ZIP_OVERRIDE="" # if set, use this ZIP as Phase 1 output (implies --start-from-feature 1)

# ── Helpers ──────────────────────────────────────────────────────────────────
latest_artifacts_dir() {
  local run_dir="$1"
  local candidate=""

  # Prefer standard build path
  if [[ -d "$run_dir/build" ]]; then
    candidate=$(ls -d "$run_dir/build/iteration_"*"_artifacts" 2>/dev/null | \
      sed -E 's/.*iteration_([0-9]+)_artifacts/\1 &/' | \
      sort -n | tail -1 | awk '{print $2}')
  fi

  # Fallback to _harness/build
  if [[ -z "$candidate" && -d "$run_dir/_harness/build" ]]; then
    candidate=$(ls -d "$run_dir/_harness/build/iteration_"*"_artifacts" 2>/dev/null | \
      sed -E 's/.*iteration_([0-9]+)_artifacts/\1 &/' | \
      sort -n | tail -1 | awk '{print $2}')
  fi

  echo "$candidate"
}

latest_iteration_num() {
  local artifacts_dir="$1"
  if [[ -z "$artifacts_dir" ]]; then
    echo ""
    return
  fi
  echo "$artifacts_dir" | sed -E 's/.*iteration_([0-9]+)_artifacts/\1/'
}

# ── Parse args ─────────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --intake)              INTAKE="$2";               shift 2 ;;
    --startup-id)          STARTUP_ID="$2";           shift 2 ;;
    --build-gov)           BUILD_GOV="$2";            shift 2 ;;
    --max-iterations)      MAX_ITER="$2";             shift 2 ;;
    --no-ai)               NO_AI="--no-ai";           shift 1 ;;
    --start-from-feature)  START_FROM_FEATURE="$2";  shift 2 ;;
    --phase1-zip)          PHASE1_ZIP_OVERRIDE="$2"; shift 2 ;;
    *) echo "Unknown flag: $1"; exit 1 ;;
  esac
done

if [[ -z "$INTAKE" ]]; then
  echo "ERROR: --intake is required"
  echo "Usage: $0 --intake <path/to/intake.json> [--startup-id name]"
  exit 1
fi

if [[ ! -f "$INTAKE" ]]; then
  echo "ERROR: Intake not found: $INTAKE"
  exit 1
fi

if [[ -z "$BUILD_GOV" || ! -f "$BUILD_GOV" ]]; then
  echo "ERROR: Build governance ZIP not found."
  echo "  Drop FOBUILFINALLOCKED*.zip into this directory, or pass --build-gov <path>"
  exit 1
fi

# Derive startup-id from intake stem if not provided
if [[ -z "$STARTUP_ID" ]]; then
  STARTUP_ID=$(basename "$INTAKE" .json | sed 's/\\./_/g')
fi

INTAKE_DIR=$(dirname "$INTAKE")
INTAKE_STEM=$(basename "$INTAKE" .json)
ASSESSMENT="${INTAKE_DIR}/${INTAKE_STEM}_phase_assessment.json"
PHASE1_INTAKE="${INTAKE_DIR}/${INTAKE_STEM}_phase1.json"

# ── Auto-resume: detect prior run state from ZIPs on disk ─────────────────────
# Only engages when user did not pass --phase1-zip or --start-from-feature manually.
_AUTO_RESUMED=0

# 1. Early-exit if final ZIP already exists
_FINAL_ZIP_DONE=$(ls -t fo_harness_runs/${STARTUP_ID}_BLOCK_B_full_*.zip 2>/dev/null | head -1 || true)
if [[ -n "$_FINAL_ZIP_DONE" ]]; then
  echo "✓ Already complete — final ZIP exists: $_FINAL_ZIP_DONE"
  echo "  Delete it and rerun to rebuild from scratch."
  exit 0
fi

# 2. Auto-detect Phase 1 ZIP
if [[ -z "$PHASE1_ZIP_OVERRIDE" && $START_FROM_FEATURE -eq 0 ]]; then
  _AUTO_P1=$(ls -t fo_harness_runs/${INTAKE_STEM}_p1_BLOCK_B_*.zip 2>/dev/null | head -1 || true)
  if [[ -n "$_AUTO_P1" ]]; then
    PHASE1_ZIP_OVERRIDE="$_AUTO_P1"
    START_FROM_FEATURE=1
    _AUTO_RESUMED=1
    echo "  ↩ Auto-resume: Phase 1 ZIP found: $_AUTO_P1"
  fi
fi

# 3. Auto-scan completed features — find the last one with a ZIP on disk
if [[ -n "$PHASE1_ZIP_OVERRIDE" && -f "$ASSESSMENT" ]]; then
  _TMP_FNUM=0
  _TMP_HIGHEST=0
  while IFS= read -r _F; do
    [[ -z "$_F" ]] && continue
    _TMP_FNUM=$((_TMP_FNUM + 1))
    _FSLUG=$(python3 -c "import re; print(re.sub(r'[^a-z0-9]+','_','$_F'.lower()).strip('_')[:40])")
    _FINTAKE="${INTAKE_DIR}/${INTAKE_STEM}_feature_${_FSLUG}.json"
    if [[ ! -f "$_FINTAKE" ]]; then
      break  # intake not yet generated → feature was never started
    fi
    _FSLUG_ID=$(python3 -c "import json; d=json.load(open('$_FINTAKE')); print(d.get('startup_idea_id','unknown'))")
    _FZIP=$(ls -t "fo_harness_runs/${_FSLUG_ID}_BLOCK_B_"*.zip 2>/dev/null | grep -v '_full_' | head -1 || true)
    if [[ -n "$_FZIP" ]]; then
      _TMP_HIGHEST=$_TMP_FNUM
    else
      break  # no ZIP → this is the resume point
    fi
  done <<< "$(python3 -c "import json; [print(f) for f in json.load(open('$ASSESSMENT')).get('intelligence_features',[])]")"

  _AUTO_FROM=$((_TMP_HIGHEST + 1))
  if [[ $_AUTO_FROM -gt $START_FROM_FEATURE ]]; then
    START_FROM_FEATURE=$_AUTO_FROM
    _AUTO_RESUMED=1
    if [[ $_TMP_HIGHEST -gt 0 ]]; then
      echo "  ↩ Auto-resume: $_TMP_HIGHEST feature(s) already done — resuming from feature $_AUTO_FROM"
    fi
  fi
fi
# ── End auto-resume detection ──────────────────────────────────────────────────

echo "========================================================"
echo "  FEATURE + INTEGRATION BUILD PIPELINE"
echo "  Intake          : $INTAKE"
echo "  Startup ID      : $STARTUP_ID"
echo "  Max iter        : $MAX_ITER (per feature)"
echo "  Build GOV       : $BUILD_GOV"
if [[ -n "$PHASE1_ZIP_OVERRIDE" ]]; then
  echo "  Phase 1 ZIP     : $PHASE1_ZIP_OVERRIDE (pre-built, skipping rebuild)"
fi
if [[ $START_FROM_FEATURE -gt 0 ]]; then
  echo "  Start from feat : $START_FROM_FEATURE (skipping earlier features)"
fi
echo "========================================================"
echo ""

# ── Step 1: Run phase_planner ──────────────────────────────────────────────────
echo "▶ STEP 1 — Phase Planner (classifying features)"
echo "────────────────────────────────────────────────────────"

# Skip re-running planner if assessment file already exists and we're resuming
if [[ -f "$ASSESSMENT" && ( -n "$PHASE1_ZIP_OVERRIDE" || $START_FROM_FEATURE -gt 0 ) ]]; then
  echo "  ↩ Skipping phase_planner — assessment already exists and --start-from-feature set"
else
  python phase_planner.py --intake "$INTAKE" $NO_AI
fi
echo ""

if [[ ! -f "$ASSESSMENT" ]]; then
  echo "ERROR: Phase assessment not found: $ASSESSMENT"
  exit 1
fi

# Read intelligence features from assessment JSON
INTEL_FEATURES=$(python3 -c "
import json, sys
a = json.load(open('$ASSESSMENT'))
features = a.get('intelligence_features', [])
for f in features:
    print(f)
")

INTEL_COUNT=$(echo "$INTEL_FEATURES" | grep -c . || true)
echo "  Data layer  : Phase 1"
echo "  Intel features ($INTEL_COUNT): $(echo "$INTEL_FEATURES" | tr '\n' ',' | sed 's/,$//')"
echo ""

# Track all ZIPs for final merge
declare -a ALL_ZIPS=()

# ── Step 2: Build Phase 1 (data layer) ────────────────────────────────────────
echo "▶ STEP 2 — Phase 1: Data Layer"
echo "────────────────────────────────────────────────────────"

# Resolve --phase1-zip: implies start-from-feature >= 1
if [[ -n "$PHASE1_ZIP_OVERRIDE" ]]; then
  if [[ ! -f "$PHASE1_ZIP_OVERRIDE" ]]; then
    echo "ERROR: --phase1-zip not found: $PHASE1_ZIP_OVERRIDE"
    exit 1
  fi
  LATEST_ZIP="$PHASE1_ZIP_OVERRIDE"
  LATEST_RUN_DIR="${LATEST_ZIP%.zip}"
  ALL_ZIPS+=("$LATEST_ZIP")
  echo "  ↩ Skipping Phase 1 build — using: $LATEST_ZIP"
  # Default START_FROM_FEATURE to 1 if not set when phase1-zip is provided
  if [[ $START_FROM_FEATURE -eq 0 ]]; then
    START_FROM_FEATURE=1
  fi
elif [[ $START_FROM_FEATURE -gt 0 ]]; then
  # --start-from-feature without --phase1-zip: find the most recent p1 ZIP automatically
  LATEST_ZIP=$(ls -t fo_harness_runs/*_p1_BLOCK_B_*.zip 2>/dev/null | head -1 || true)
  if [[ -z "$LATEST_ZIP" ]]; then
    echo "ERROR: --start-from-feature set but no Phase 1 ZIP found in fo_harness_runs/."
    echo "       Pass --phase1-zip <path> to specify it explicitly."
    exit 1
  fi
  LATEST_RUN_DIR="${LATEST_ZIP%.zip}"
  ALL_ZIPS+=("$LATEST_ZIP")
  echo "  ↩ Skipping Phase 1 build — auto-found: $LATEST_ZIP"
else
  P1_EXIT=0
  python fo_test_harness.py \
    "$PHASE1_INTAKE" \
    "$BUILD_GOV" \
    --max-iterations "$MAX_ITER" \
    --no-polish || P1_EXIT=$?

  if [[ $P1_EXIT -ne 0 ]]; then
    echo ""
    echo "✗ PHASE 1 FAILED (exit $P1_EXIT)"
    echo "  Phase 1 did not produce a ZIP. Fix the issue then rerun the same command:"
    echo "  ./run_integration_and_feature_build.sh --intake $INTAKE"
    echo "  The script will auto-detect the Phase 1 ZIP once it exists."
    exit 1
  fi

  # Find Phase 1 ZIP (most recent _p1_ ZIP)
  LATEST_ZIP=$(ls -t fo_harness_runs/*_p1_BLOCK_B_*.zip 2>/dev/null | head -1 || true)
  if [[ -z "$LATEST_ZIP" ]]; then
    echo "ERROR: Phase 1 ZIP not found in fo_harness_runs/"
    exit 1
  fi
  LATEST_RUN_DIR="${LATEST_ZIP%.zip}"
  ALL_ZIPS+=("$LATEST_ZIP")
fi

echo "✓ Phase 1 ZIP: $LATEST_ZIP"
echo ""

# ── Step 3: Build each intelligence feature ────────────────────────────────────
FEATURE_NUM=0
TOTAL_INTEL=$INTEL_COUNT

while IFS= read -r FEATURE; do
  [[ -z "$FEATURE" ]] && continue
  FEATURE_NUM=$((FEATURE_NUM + 1))

  # ── Skip features before START_FROM_FEATURE ──────────────────────────────────
  if [[ $FEATURE_NUM -lt $START_FROM_FEATURE ]]; then
    FEATURE_SLUG=$(python3 -c "
import re; print(re.sub(r'[^a-z0-9]+','_','$FEATURE'.lower()).strip('_')[:40])
")
    FEATURE_INTAKE="${INTAKE_DIR}/${INTAKE_STEM}_feature_${FEATURE_SLUG}.json"
    if [[ ! -f "$FEATURE_INTAKE" ]]; then
      echo "ERROR: --start-from-feature $START_FROM_FEATURE set but feature intake not found: $FEATURE_INTAKE"
      echo "       The skipped feature must have been built previously."
      exit 1
    fi
    STARTUP_SLUG=$(python3 -c "
import json
d = json.load(open('$FEATURE_INTAKE'))
print(d.get('startup_idea_id','unknown'))
")
    SKIP_ZIP=$(ls -t "fo_harness_runs/${STARTUP_SLUG}_BLOCK_B_"*.zip 2>/dev/null | head -1 || true)
    if [[ -z "$SKIP_ZIP" ]]; then
      echo "ERROR: --start-from-feature $START_FROM_FEATURE: no ZIP found for skipped feature '$FEATURE' (startup_id: $STARTUP_SLUG)"
      echo "       Build it first or lower --start-from-feature."
      exit 1
    fi
    echo "  ↩ SKIP Feature $FEATURE_NUM/$TOTAL_INTEL: $FEATURE  →  $SKIP_ZIP"
    ALL_ZIPS+=("$SKIP_ZIP")
    LATEST_ZIP="$SKIP_ZIP"
    LATEST_RUN_DIR="${SKIP_ZIP%.zip}"
    continue
  fi

  echo "▶ STEP $((FEATURE_NUM + 2)) — Feature $FEATURE_NUM/$TOTAL_INTEL: $FEATURE"
  echo "────────────────────────────────────────────────────────"

  # Generate scoped intake for this feature
  python feature_adder.py \
    --intake "$INTAKE" \
    --manifest "$LATEST_ZIP" \
    --feature "$FEATURE"

  FEATURE_SLUG=$(python3 -c "
import re; print(re.sub(r'[^a-z0-9]+','_','$FEATURE'.lower()).strip('_')[:40])
")
  FEATURE_INTAKE="${INTAKE_DIR}/${INTAKE_STEM}_feature_${FEATURE_SLUG}.json"

  if [[ ! -f "$FEATURE_INTAKE" ]]; then
    echo "ERROR: Feature intake not generated: $FEATURE_INTAKE"
    exit 1
  fi

  # Last feature gets full polish; all others skip it
  POLISH_FLAG="--no-polish"
  if [[ $FEATURE_NUM -eq $TOTAL_INTEL ]]; then
    POLISH_FLAG=""
    echo "  (final feature — polish ON)"
  else
    echo "  (intermediate feature — polish OFF)"
  fi

  FEAT_EXIT=0
  python fo_test_harness.py \
    "$FEATURE_INTAKE" \
    "$BUILD_GOV" \
    --max-iterations "$MAX_ITER" \
    --prior-run "$LATEST_RUN_DIR" \
    $POLISH_FLAG || FEAT_EXIT=$?

  if [[ $FEAT_EXIT -ne 0 ]]; then
    echo ""
    echo "✗ FEATURE '$FEATURE' FAILED (exit $FEAT_EXIT)"
    echo ""
    echo "  Just rerun the same command — the script will pick up where it left off:"
    echo "  ./run_integration_and_feature_build.sh --intake $INTAKE"
    echo ""
    echo "  Prior ZIPs built so far:"
    for Z in "${ALL_ZIPS[@]}"; do echo "    $Z"; done
    exit 1
  fi

  # Find the ZIP for this feature (most recent matching its startup_id slug)
  STARTUP_SLUG=$(python3 -c "
import json
d = json.load(open('$FEATURE_INTAKE'))
print(d.get('startup_idea_id','unknown'))
")
  FEATURE_ZIP=$(ls -t "fo_harness_runs/${STARTUP_SLUG}_BLOCK_B_"*.zip 2>/dev/null | head -1 || true)
  if [[ -z "$FEATURE_ZIP" ]]; then
    echo "ERROR: ZIP not found for startup_id '$STARTUP_SLUG'"
    exit 1
  fi

  echo "✓ Feature ZIP: $FEATURE_ZIP"
  ALL_ZIPS+=("$FEATURE_ZIP")
  LATEST_ZIP="$FEATURE_ZIP"  # chain: next feature_adder reads this
  LATEST_RUN_DIR="${FEATURE_ZIP%.zip}"  # chain: next feature inherits QA prohibitions
  echo ""

done <<< "$INTEL_FEATURES"

# ── Step 4: Integration check + fix loop ─────────────────────────────────────
echo "▶ STEP $((FEATURE_NUM + 3)) — Integration Check"
echo "────────────────────────────────────────────────────────"

INTEGRATION_ISSUES="${LATEST_RUN_DIR}/integration_issues.json"
ARTIFACTS_DIR=$(latest_artifacts_dir "$LATEST_RUN_DIR")

# Helper: run integration_check without dying under set -e on non-zero exit.
# Sets outer IC_EXIT; updates ARTIFACTS_DIR from current LATEST_RUN_DIR.
_run_integration_check() {
  local issues_file="$1"
  ARTIFACTS_DIR=$(latest_artifacts_dir "$LATEST_RUN_DIR")
  IC_EXIT=0
  if [[ -n "$ARTIFACTS_DIR" ]]; then
    echo "  Using artifacts dir: $ARTIFACTS_DIR"
    python integration_check.py \
      --artifacts "$ARTIFACTS_DIR" \
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

MAX_FIX_PASSES=2
FIX_PASS=0

while [[ $IC_EXIT -ne 0 && $FIX_PASS -lt $MAX_FIX_PASSES ]]; do
  FIX_PASS=$((FIX_PASS + 1))
  echo ""
  echo "⚠ Integration issues found — running fix pass $FIX_PASS/$MAX_FIX_PASSES"

  # Determine latest iteration for resume
  ARTIFACTS_DIR=$(latest_artifacts_dir "$LATEST_RUN_DIR")
  LATEST_ITER=$(latest_iteration_num "$ARTIFACTS_DIR")
  if [[ -z "$LATEST_ITER" ]]; then
    echo "ERROR: Unable to determine latest iteration number for resume."
    exit 1
  fi

  FIX_EXIT=0
  python fo_test_harness.py \
    "$FEATURE_INTAKE" \
    "$BUILD_GOV" \
    --resume-run "$LATEST_RUN_DIR" \
    --resume-iteration "$LATEST_ITER" \
    --integration-issues "$INTEGRATION_ISSUES" \
    --max-iterations "$MAX_ITER" \
    --no-polish || FIX_EXIT=$?

  if [[ $FIX_EXIT -ne 0 ]]; then
    echo ""
    echo "✗ INTEGRATION FIX PASS $FIX_PASS FAILED (exit $FIX_EXIT)"
    exit 1
  fi

  # Update latest ZIP after fix pass
  FIX_ZIP="${LATEST_RUN_DIR}.zip"
  if [[ ! -f "$FIX_ZIP" ]]; then
    FIX_ZIP=$(ls -t "fo_harness_runs/"*_BLOCK_B_*.zip 2>/dev/null | head -1 || true)
  fi
  if [[ -z "$FIX_ZIP" ]]; then
    echo "ERROR: ZIP not found after integration fix pass $FIX_PASS."
    exit 1
  fi
  LATEST_ZIP="$FIX_ZIP"
  LATEST_RUN_DIR="${FIX_ZIP%.zip}"

  # Replace the last ZIP in the merge list with the fixed ZIP
  if [[ ${#ALL_ZIPS[@]} -gt 0 ]]; then
    ALL_ZIPS[-1]="$LATEST_ZIP"
  fi

  # Re-run integration check to see if issues are cleared
  echo ""
  echo "▶ Re-checking integration (pass $FIX_PASS/$MAX_FIX_PASSES)"
  echo "────────────────────────────────────────────────────────"
  INTEGRATION_ISSUES="${LATEST_RUN_DIR}/integration_issues.json"
  _run_integration_check "$INTEGRATION_ISSUES"
done

if [[ $IC_EXIT -ne 0 ]]; then
  echo ""
  echo "✗ INTEGRATION CHECK STILL FAILING AFTER $FIX_PASS FIX PASS(ES)"
  echo "  Manual review required. See: $INTEGRATION_ISSUES"
  exit 1
fi

echo "✓ Integration check clean."
echo ""

# ── Step 5: Merge all ZIPs ────────────────────────────────────────────────────
echo "▶ FINAL STEP — Merging ${#ALL_ZIPS[@]} ZIP(s) into final deliverable"
echo "────────────────────────────────────────────────────────"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
FINAL_ZIP="fo_harness_runs/${STARTUP_ID}_BLOCK_B_full_${TIMESTAMP}.zip"
MERGE_TMP=$(mktemp -d)

echo "  ZIPs to merge (in order):"
for Z in "${ALL_ZIPS[@]}"; do
  echo "    $Z"
done
echo ""

for Z in "${ALL_ZIPS[@]}"; do
  unzip -q -o "$Z" -d "$MERGE_TMP"
done

(cd "$MERGE_TMP" && zip -qr - .) > "$FINAL_ZIP"
rm -rf "$MERGE_TMP"

FINAL_SIZE=$(du -sh "$FINAL_ZIP" | cut -f1)

echo "========================================================"
echo "  FEATURE BUILD COMPLETE"
echo ""
for i in "${!ALL_ZIPS[@]}"; do
  echo "  Phase/Feature $((i+1)): ${ALL_ZIPS[$i]}"
done
echo ""
echo "  FINAL ZIP : $FINAL_ZIP  ($FINAL_SIZE)"
echo "========================================================"
echo ""
echo "Next step — deploy:"
echo "  python deploy/zip_to_repo.py $FINAL_ZIP"
