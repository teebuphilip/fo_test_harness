#!/usr/bin/env bash
# run_slicer_and_feature_build.sh — Full slice-by-slice build pipeline
# with post-build integration validation and fix loop.
#
# Flow:
#   1. Runs slice_planner.py to emit slice intakes
#   2. Builds each slice intake in order (chained via --prior-run)
#   3. Runs integration_check.py, fixes via harness resume, re-checks
#   4. Merges all ZIPs into a single final deliverable
#
# Usage:
#   ./run_slicer_and_feature_build.sh --intake <path/to/intake.json> [options]
#
# Required:
#   --intake        Path to original intake JSON
#
# Optional:
#   --startup-id         Base name for final ZIP (default: derived from intake stem)
#   --build-gov          Path to FOBUILFINALLOCKED100.zip (default: last known)
#   --max-iterations N   Per-slice iteration cap (default: 20; capped at 10 in factory mode)
#   --clean              Remove only the final ZIP — pipeline re-runs from last completed
#                        slice (slice ZIPs kept for auto-resume).
#   --fullclean          Remove ALL ZIPs for this startup (slice, full).
#                        Run dirs are left untouched. Forces a full rebuild.
#   --mode factory|quality  Build mode (default: quality)
#                           quality  = all gates, 20 iters max, 2 integration fix passes
#                           factory  = no Gate 3 (AI Consistency), Gate 4 Deployability-only,
#                                      10 iters max, 1 integration fix pass
#   --no-ai              Skip AI in slice_planner (faster, heuristic-only)
#   --start-from-feature N  Skip slices 1..(N-1); resume from slice N (1-indexed).
#
# Resume example (restart from slice 2):
#   ./run_slicer_and_feature_build.sh \
#     --intake intake/intake_runs/awi/awi.5.json \
#     --start-from-feature 2
#
# Normal example:
#   ./run_slicer_and_feature_build.sh \
#     --intake intake/intake_runs/ai_workforce_intelligence/ai_workforce_intelligence.5.json \
#     --startup-id awi

set -euo pipefail

# ── Defaults ──────────────────────────────────────────────────────────────────
BUILD_GOV="$(ls FOBUILFINALLOCKED*.zip 2>/dev/null | head -1)"
MAX_ITER=20
STARTUP_ID=""
INTAKE=""
NO_AI=""
MODE="quality"         # quality | factory
FACTORY_FLAG=""        # set to --factory-mode when MODE=factory
CLEAN=0                # if 1, remove only the final ZIP so auto-resume re-runs
FULLCLEAN=0            # if 1, remove ALL ZIPs for this startup (slice, full)
START_FROM_FEATURE=0   # skip slices 1..(N-1), resume from slice N (1-indexed)
LATEST_ZIP=""
LATEST_RUN_DIR=""

# ── Helpers ──────────────────────────────────────────────────────────────────
latest_artifacts_dir() {
  # Use Python for reliable numeric sort — sed+sort is fragile on macOS BSD.
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
  # Returns plain integer (no leading zeros) — safe for bash arithmetic.
  local artifacts_dir="$1"
  [[ -z "$artifacts_dir" ]] && echo "" && return
  python3 -c "
import re, sys
m = re.search(r'iteration_(\d+)_artifacts', '$artifacts_dir')
print(int(m.group(1)) if m else '')
"
}

# ── Parse args ─────────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --intake)              INTAKE="$2";               shift 2 ;;
    --startup-id)          STARTUP_ID="$2";           shift 2 ;;
    --build-gov)           BUILD_GOV="$2";            shift 2 ;;
    --max-iterations)      MAX_ITER="$2";             shift 2 ;;
    --no-ai)               NO_AI="--no-ai";           shift 1 ;;
    --mode)                MODE="$2";                 shift 2 ;;
    --clean)               CLEAN=1;                   shift 1 ;;
    --fullclean)           FULLCLEAN=1;               shift 1 ;;
    --start-from-feature)  START_FROM_FEATURE="$2";  shift 2 ;;
    *) echo "Unknown flag: $1"; exit 1 ;;
  esac
done

if [[ "$MODE" != "quality" && "$MODE" != "factory" ]]; then
  echo "ERROR: --mode must be 'quality' or 'factory' (got: $MODE)"
  exit 1
fi

# Factory mode: cap iterations and set harness flag
if [[ "$MODE" == "factory" ]]; then
  FACTORY_FLAG="--factory-mode"
  if [[ $MAX_ITER -gt 10 ]]; then
    MAX_ITER=10
  fi
fi

if [[ -z "$INTAKE" ]]; then
  echo "ERROR: --intake is required"
  echo "Usage: $0 --intake <path/to/intake.json> [--startup-id name] [--mode factory|quality]"
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
SLICE_ASSESSMENT="${INTAKE_DIR}/${INTAKE_STEM}_slice_assessment.json"

# ── Clean: remove only the final ZIP so auto-resume can re-run ────────────────
if [[ $CLEAN -eq 1 ]]; then
  _FINAL_TO_CLEAN=$(ls -t "fo_harness_runs/${STARTUP_ID}_BLOCK_B_full_"*.zip 2>/dev/null | head -1 || true)
  if [[ -n "$_FINAL_TO_CLEAN" ]]; then
    echo "⚠  --clean: removing final ZIP so build will re-run:"
    echo "   $_FINAL_TO_CLEAN"
    rm -f "$_FINAL_TO_CLEAN"
    echo "   Done — prior slice ZIPs kept for auto-resume."
    echo ""
  else
    echo "ℹ  --clean: no final ZIP found, nothing to remove."
    echo ""
  fi
fi

# ── Full clean: remove ALL ZIPs for this startup ──────────────────────────────
if [[ $FULLCLEAN -eq 1 ]]; then
  echo "⚠  --fullclean: removing all ZIPs for '$STARTUP_ID' / '$INTAKE_STEM'"
  _FC_ZIPS=$(ls "fo_harness_runs/${INTAKE_STEM}_"*.zip "fo_harness_runs/${STARTUP_ID}_BLOCK_B_full_"*.zip 2>/dev/null || true)
  if [[ -n "$_FC_ZIPS" ]]; then
    echo "$_FC_ZIPS" | while IFS= read -r _z; do
      echo "  rm $_z"
      rm -f "$_z"
    done
  else
    echo "  No ZIPs found for this startup."
  fi
  echo "  Done — run dirs untouched."
  echo ""
fi

# ── Auto-resume: detect prior run state from ZIPs on disk ─────────────────────
# Only engages when user did not pass --start-from-feature manually.
_AUTO_RESUMED=0

# 1. Early-exit if final ZIP already exists
_FINAL_ZIP_DONE=$(ls -t fo_harness_runs/${STARTUP_ID}_BLOCK_B_full_*.zip 2>/dev/null | head -1 || true)
if [[ -n "$_FINAL_ZIP_DONE" ]]; then
  echo "✓ Already complete — final ZIP exists: $_FINAL_ZIP_DONE"
  echo "  Delete it and rerun to rebuild from scratch."
  exit 0
fi

# 2. Auto-scan completed slices — find the last one with a ZIP on disk
if [[ $START_FROM_FEATURE -eq 0 && -f "$SLICE_ASSESSMENT" ]]; then
  _TMP_SNUM=0
  _TMP_HIGHEST=0
  while IFS= read -r _S; do
    [[ -z "$_S" ]] && continue
    _TMP_SNUM=$((_TMP_SNUM + 1))
    _SSTEM=$(basename "$_S" .json)
    _SZIP=$(ls -t "fo_harness_runs/${_SSTEM}_BLOCK_B_"*.zip 2>/dev/null | grep -v '_full_' | head -1 || true)
    if [[ -n "$_SZIP" ]]; then
      _TMP_HIGHEST=$_TMP_SNUM
    else
      break
    fi
  done <<< "$(python3 -c "import json; [print(s.get('intake_path','')) for s in json.load(open('$SLICE_ASSESSMENT')).get('slice_intakes',[])]")"

  _AUTO_FROM=$((_TMP_HIGHEST + 1))
  if [[ $_AUTO_FROM -gt $START_FROM_FEATURE ]]; then
    START_FROM_FEATURE=$_AUTO_FROM
    _AUTO_RESUMED=1
    if [[ $_TMP_HIGHEST -gt 0 ]]; then
      echo "  ↩ Auto-resume: $_TMP_HIGHEST slice(s) already done — resuming from slice $_AUTO_FROM"
    fi
  fi
fi
# ── End auto-resume detection ──────────────────────────────────────────────────

echo "========================================================"
echo "  SLICE + INTEGRATION BUILD PIPELINE"
echo "  Intake          : $INTAKE"
echo "  Startup ID      : $STARTUP_ID"
echo "  Mode            : $MODE"
echo "  Max iter        : $MAX_ITER (per slice)"
echo "  Build GOV       : $BUILD_GOV"
if [[ $START_FROM_FEATURE -gt 0 ]]; then
  echo "  Start from slice: $START_FROM_FEATURE (skipping earlier slices)"
fi
echo "========================================================"
echo ""

# ── Step 0: Ubiquitous Language Extraction ────────────────────────────────────
UBIQUITOUS_LANG="${INTAKE_DIR}/${INTAKE_STEM}_ubiquitous_language.json"

echo "▶ STEP 0 — Ubiquitous Language (locking terminology)"
echo "────────────────────────────────────────────────────────"

if [[ -f "$UBIQUITOUS_LANG" && ( -n "$PHASE1_ZIP_OVERRIDE" || $START_FROM_FEATURE -gt 0 ) ]]; then
  echo "  ↩ Skipping ubiquity — glossary already exists and resuming"
else
  python ubiquity.py --intake "$INTAKE" $NO_AI
fi

if [[ ! -f "$UBIQUITOUS_LANG" ]]; then
  echo "WARNING: Ubiquitous language file not found: $UBIQUITOUS_LANG — continuing without it"
fi
echo ""

# ── Step 1: Run slice_planner ─────────────────────────────────────────────────
echo "▶ STEP 1 — Slice Planner (emitting slice intakes)"
echo "────────────────────────────────────────────────────────"

# Skip re-running planner if assessment file already exists and we're resuming
if [[ -f "$SLICE_ASSESSMENT" && $START_FROM_FEATURE -gt 0 ]]; then
  echo "  ↩ Skipping slice_planner — assessment already exists and --start-from-feature set"
else
  python slice_planner.py --intake "$INTAKE" $NO_AI
fi
echo ""

if [[ ! -f "$SLICE_ASSESSMENT" ]]; then
  echo "ERROR: Slice assessment not found: $SLICE_ASSESSMENT"
  exit 1
fi

SLICE_INTAKES=$(python3 -c "
import json
a = json.load(open('$SLICE_ASSESSMENT'))
for s in a.get('slice_intakes', []):
    print(s.get('intake_path', ''))
")

SLICE_COUNT=$(echo "$SLICE_INTAKES" | grep -c . || true)
echo "  Slices ($SLICE_COUNT): $(echo \"$SLICE_INTAKES\" | tr '\n' ',' | sed 's/,$//')"
echo ""

# Track all ZIPs for final merge
declare -a ALL_ZIPS=()

# ── Step 2: Build slices ─────────────────────────────────────────────────────
echo "▶ STEP 2 — Build Slices"
echo "────────────────────────────────────────────────────────"

SLICE_NUM=0
LAST_SLICE_INTAKE=""
TOTAL_SLICES=$SLICE_COUNT

while IFS= read -r SLICE_INTAKE_FILE; do
  [[ -z "$SLICE_INTAKE_FILE" ]] && continue
  SLICE_NUM=$((SLICE_NUM + 1))

  # ── Skip slices before START_FROM_FEATURE ──────────────────────────────────
  if [[ $SLICE_NUM -lt $START_FROM_FEATURE ]]; then
    SLICE_STARTUP_ID=$(python3 -c "import json; d=json.load(open('$SLICE_INTAKE_FILE')); print(d.get('startup_idea_id','unknown'))")
    SKIP_ZIP=$(ls -t "fo_harness_runs/${SLICE_STARTUP_ID}_BLOCK_B_"*.zip 2>/dev/null | head -1 || true)
    if [[ -z "$SKIP_ZIP" ]]; then
      echo "ERROR: --start-from-feature $START_FROM_FEATURE: no ZIP found for skipped slice (startup_id: $SLICE_STARTUP_ID)"
      echo "       Build it first or lower --start-from-feature."
      exit 1
    fi
    echo "  ↩ SKIP Slice $SLICE_NUM/$TOTAL_SLICES: $SLICE_INTAKE_FILE  →  $SKIP_ZIP"
    ALL_ZIPS+=("$SKIP_ZIP")
    LATEST_ZIP="$SKIP_ZIP"
    LATEST_RUN_DIR="${SKIP_ZIP%.zip}"
    continue
  fi

  SLICE_NAME=$(python3 -c "import json; d=json.load(open('$SLICE_INTAKE_FILE')); print(d.get('_mini_spec', {}).get('entity', 'unknown'))")
  SLICE_STARTUP_ID=$(python3 -c "import json; d=json.load(open('$SLICE_INTAKE_FILE')); print(d.get('startup_idea_id','unknown'))")

  # Check if this slice's ZIP already exists (auto-resume)
  EXISTING_SLICE_ZIP=$(ls -t "fo_harness_runs/${SLICE_STARTUP_ID}_BLOCK_B_"*.zip 2>/dev/null | head -1 || true)
  if [[ -n "$EXISTING_SLICE_ZIP" ]]; then
    echo "  ↩ SKIP Slice $SLICE_NUM/$TOTAL_SLICES: $SLICE_NAME → $EXISTING_SLICE_ZIP"
    ALL_ZIPS+=("$EXISTING_SLICE_ZIP")
    LATEST_ZIP="$EXISTING_SLICE_ZIP"
    LATEST_RUN_DIR="${EXISTING_SLICE_ZIP%.zip}"
    continue
  fi

  echo "▶ STEP $((SLICE_NUM + 1)) — Slice $SLICE_NUM/$TOTAL_SLICES: $SLICE_NAME"
  echo "────────────────────────────────────────────────────────"

  SLICE_EXIT=0
  PRIOR_RUN_FLAG=""
  if [[ -n "$LATEST_RUN_DIR" && -d "$LATEST_RUN_DIR" ]]; then
    PRIOR_RUN_FLAG="--prior-run $LATEST_RUN_DIR"
  fi

  # ── Spec generation: GPT drafts, Claude closes ──────────────────────────────
  echo "▶ Generating slice spec: $SLICE_NAME"
  SPEC_EXIT=0
  python generate_feature_spec.py --intake "$SLICE_INTAKE_FILE" || SPEC_EXIT=$?
  if [[ $SPEC_EXIT -ne 0 ]]; then
    echo ""
    echo "✗ SPEC GENERATION HALTED for slice '$SLICE_NAME'"
    echo "  Review: ${SLICE_INTAKE_FILE%.json}_spec_HALT.json"
    echo "  Fix the intake ambiguities then rerun."
    exit 1
  fi
  SPEC_FILE="${SLICE_INTAKE_FILE%.json}_spec.txt"
  if [[ ! -f "$SPEC_FILE" ]]; then
    echo "ERROR: spec file not found after generation: $SPEC_FILE"
    exit 1
  fi

  # Inject spec into slice intake JSON in place
  python inject_spec.py \
    --intake "$SLICE_INTAKE_FILE" \
    --spec-file "$SPEC_FILE" \
    --output "$SLICE_INTAKE_FILE"

  # ── Harness build ────────────────────────────────────────────────────────────
  python fo_test_harness.py \
    "$SLICE_INTAKE_FILE" \
    "$BUILD_GOV" \
    --max-iterations "$MAX_ITER" \
    $FACTORY_FLAG \
    $PRIOR_RUN_FLAG || SLICE_EXIT=$?

  if [[ $SLICE_EXIT -ne 0 ]]; then
    echo ""
    echo "✗ SLICE '$SLICE_NAME' FAILED (exit $SLICE_EXIT)"
    echo "  Rerun the same command — completed slices will be auto-skipped."
    exit 1
  fi

  SLICE_ZIP=$(ls -t "fo_harness_runs/${SLICE_STARTUP_ID}_BLOCK_B_"*.zip 2>/dev/null | head -1 || true)
  if [[ -z "$SLICE_ZIP" ]]; then
    echo "ERROR: ZIP not found for slice '$SLICE_NAME' (startup_id: $SLICE_STARTUP_ID)"
    exit 1
  fi

  echo "✓ Slice ZIP: $SLICE_ZIP"
  ALL_ZIPS+=("$SLICE_ZIP")
  LATEST_ZIP="$SLICE_ZIP"
  LATEST_RUN_DIR="${SLICE_ZIP%.zip}"
  LAST_SLICE_INTAKE="$SLICE_INTAKE_FILE"
  echo ""
  echo "════════════════════════════════════════════════════════"
  echo "  ✓ SLICE $SLICE_NUM/$TOTAL_SLICES COMPLETE: $SLICE_NAME"
  echo "════════════════════════════════════════════════════════"
  echo ""

done <<< "$SLICE_INTAKES"

# ── Step 4: Integration check + fix loop ─────────────────────────────────────
echo "▶ STEP $((SLICE_NUM + 2)) — Integration Check"
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

# Only run fix pass if there are HIGH severity issues — MEDIUM-only (e.g. KPI
# mentions not in code) are not worth burning fix pass iterations on.
IC_HIGH=0
if [[ $IC_EXIT -ne 0 && -f "$INTEGRATION_ISSUES" ]]; then
  IC_HIGH=$(python3 -c "
import json, sys
d = json.load(open('$INTEGRATION_ISSUES'))
print(sum(1 for i in d.get('issues', []) if i.get('severity','').upper() == 'HIGH'))
" 2>/dev/null || echo 0)
  if [[ $IC_HIGH -eq 0 ]]; then
    echo "ℹ Integration issues are MEDIUM-only — skipping fix pass (not worth burning iterations)"
    IC_EXIT=0
  fi
fi

MAX_FIX_PASSES=2
if [[ "$MODE" == "factory" ]]; then MAX_FIX_PASSES=1; fi
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

  # Allow at least 5 more iterations beyond wherever the run currently is,
  # so the fix pass never hits max-iterations before it can run a single iteration.
  # Use 10# prefix to force decimal — LATEST_ITER may be "08"/"09" which bash
  # would interpret as invalid octal without the prefix.
  INT_MAX_ITER=$(( LATEST_ITER + 5 ))
  if [[ $INT_MAX_ITER -lt $MAX_ITER ]]; then INT_MAX_ITER=$MAX_ITER; fi

  # Use last slice intake if set, else fall back to full intake
  _FIX_INTAKE="${LAST_SLICE_INTAKE:-$INTAKE}"
  FIX_EXIT=0
  python fo_test_harness.py \
    "$_FIX_INTAKE" \
    "$BUILD_GOV" \
    --resume-run "$LATEST_RUN_DIR" \
    --resume-iteration "$LATEST_ITER" \
    --integration-issues "$INTEGRATION_ISSUES" \
    --max-iterations "$INT_MAX_ITER" \
    --no-polish \
    $FACTORY_FLAG || FIX_EXIT=$?

  if [[ $FIX_EXIT -ne 0 ]]; then
    echo ""
    echo "✗ INTEGRATION FIX PASS $FIX_PASS FAILED (exit $FIX_EXIT)"
    exit 1
  fi

  # Update latest ZIP after fix pass
  FIX_ZIP="${LATEST_RUN_DIR}.zip"
  if [[ ! -f "$FIX_ZIP" ]]; then
    # Scoped fallback: only look for ZIPs belonging to this startup's last run dir prefix
    _FIX_RUN_PREFIX=$(basename "$LATEST_RUN_DIR" | sed 's/_[0-9]\{8\}_[0-9]\{6\}$//')
    FIX_ZIP=$(ls -t "fo_harness_runs/${_FIX_RUN_PREFIX}_"*.zip 2>/dev/null | grep -v '_full_' | head -1 || true)
  fi
  if [[ -z "$FIX_ZIP" ]]; then
    echo "ERROR: ZIP not found after integration fix pass $FIX_PASS."
    echo "       Expected: ${LATEST_RUN_DIR}.zip"
    exit 1
  fi
  LATEST_ZIP="$FIX_ZIP"
  LATEST_RUN_DIR="${FIX_ZIP%.zip}"

  # Replace the last ZIP in the merge list with the fixed ZIP
  if [[ ${#ALL_ZIPS[@]} -gt 0 ]]; then
    ALL_ZIPS[$(( ${#ALL_ZIPS[@]} - 1 ))]="$LATEST_ZIP"
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
echo "  SLICE BUILD COMPLETE"
echo ""
for i in "${!ALL_ZIPS[@]}"; do
  echo "  Slice $((i+1)): ${ALL_ZIPS[$i]}"
done
echo ""
echo "  FINAL ZIP : $FINAL_ZIP  ($FINAL_SIZE)"
echo "========================================================"
echo ""

# ── Auto quality check on final ZIP ──────────────────────────────────────────
if [[ -n "$INTAKE" ]]; then
  echo "Running final quality check..."
  echo ""
  CHECK_OUTPUT="${FINAL_ZIP%.zip}_check.json"
  python check_final_zip.py \
    --zip "$FINAL_ZIP" \
    --intake "$INTAKE" \
    --output "$CHECK_OUTPUT" || true
  echo ""
fi

echo "Next step — deploy:"
echo "  python deploy/zip_to_repo.py $FINAL_ZIP"
