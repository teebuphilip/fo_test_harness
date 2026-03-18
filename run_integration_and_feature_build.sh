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
#   --max-iterations N   Per-phase/feature iteration cap (default: 20; capped at 10 in factory mode)
#   --clean              Remove only the final ZIP — pipeline re-runs from last completed
#                        feature (phase/feature ZIPs kept for auto-resume).
#   --fullclean          Remove ALL ZIPs for this startup (phase1, feature, full).
#                        Run dirs are left untouched. Forces a full rebuild.
#   --mode factory|quality  Build mode (default: quality)
#                           quality  = all gates, 20 iters max, 2 integration fix passes
#                           factory  = no Gate 3 (AI Consistency), Gate 4 Deployability-only,
#                                      10 iters max, 1 integration fix pass
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
MODE="quality"         # quality | factory
FACTORY_FLAG=""        # set to --factory-mode when MODE=factory
CLEAN=0                # if 1, remove only the final ZIP so auto-resume re-runs
FULLCLEAN=0            # if 1, remove ALL ZIPs for this startup (phase1, feature, full)
START_FROM_FEATURE=0   # skip Phase 1 + features 1..(N-1), resume from feature N (1-indexed)
PHASE1_ZIP_OVERRIDE="" # if set, use this ZIP as Phase 1 output (implies --start-from-feature 1)
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
    --phase1-zip)          PHASE1_ZIP_OVERRIDE="$2"; shift 2 ;;
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
ASSESSMENT="${INTAKE_DIR}/${INTAKE_STEM}_phase_assessment.json"
PHASE1_INTAKE="${INTAKE_DIR}/${INTAKE_STEM}_phase1.json"

# ── Clean: remove only the final ZIP so auto-resume can re-run ────────────────
if [[ $CLEAN -eq 1 ]]; then
  _FINAL_TO_CLEAN=$(ls -t "fo_harness_runs/${STARTUP_ID}_BLOCK_B_full_"*.zip 2>/dev/null | head -1 || true)
  if [[ -n "$_FINAL_TO_CLEAN" ]]; then
    echo "⚠  --clean: removing final ZIP so build will re-run:"
    echo "   $_FINAL_TO_CLEAN"
    rm -f "$_FINAL_TO_CLEAN"
    echo "   Done — prior phase/feature ZIPs kept for auto-resume."
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
echo "  Mode            : $MODE"
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
  # --start-from-feature without --phase1-zip: find the most recent p1 ZIP for THIS intake stem
  LATEST_ZIP=$(ls -t "fo_harness_runs/${INTAKE_STEM}_p1_BLOCK_B_"*.zip 2>/dev/null | head -1 || true)
  if [[ -z "$LATEST_ZIP" ]]; then
    echo "ERROR: --start-from-feature set but no Phase 1 ZIP found for '${INTAKE_STEM}' in fo_harness_runs/."
    echo "       Pass --phase1-zip <path> to specify it explicitly."
    exit 1
  fi
  LATEST_RUN_DIR="${LATEST_ZIP%.zip}"
  ALL_ZIPS+=("$LATEST_ZIP")
  echo "  ↩ Skipping Phase 1 build — auto-found: $LATEST_ZIP"
else
  # Check if decomposer produced entity-level mini specs
  DECOMP_MODE=$(python3 -c "
import json, sys
a = json.load(open('$ASSESSMENT'))
print(a.get('decomposition_mode', 'monolithic'))
" 2>/dev/null || echo "monolithic")

  if [[ "$DECOMP_MODE" == "ai_mini_specs" ]]; then
    # ── Entity-by-entity build (AI decomposer mode) ───────────────────────
    echo "  Mode: AI mini specs (entity-by-entity build)"
    echo ""

    ENTITY_INTAKES=$(python3 -c "
import json
a = json.load(open('$ASSESSMENT'))
for ei in a.get('entity_intakes', []):
    print(ei['intake_file'])
")

    ENTITY_NUM=0
    ENTITY_TOTAL=$(echo "$ENTITY_INTAKES" | grep -c . || true)

    while IFS= read -r ENTITY_INTAKE_FILE; do
      [[ -z "$ENTITY_INTAKE_FILE" ]] && continue
      ENTITY_NUM=$((ENTITY_NUM + 1))

      ENTITY_NAME=$(python3 -c "
import json
d = json.load(open('$ENTITY_INTAKE_FILE'))
print(d.get('_mini_spec', {}).get('entity', 'unknown'))
")
      ENTITY_STARTUP_ID=$(python3 -c "
import json
d = json.load(open('$ENTITY_INTAKE_FILE'))
print(d.get('startup_idea_id', 'unknown'))
")

      # Check if this entity's ZIP already exists (auto-resume)
      EXISTING_ENTITY_ZIP=$(ls -t "fo_harness_runs/${ENTITY_STARTUP_ID}_BLOCK_B_"*.zip 2>/dev/null | head -1 || true)
      if [[ -n "$EXISTING_ENTITY_ZIP" ]]; then
        echo "  ↩ SKIP Entity $ENTITY_NUM/$ENTITY_TOTAL: $ENTITY_NAME → $EXISTING_ENTITY_ZIP"
        ALL_ZIPS+=("$EXISTING_ENTITY_ZIP")
        LATEST_ZIP="$EXISTING_ENTITY_ZIP"
        LATEST_RUN_DIR="${EXISTING_ENTITY_ZIP%.zip}"
        continue
      fi

      echo "  ▶ Entity $ENTITY_NUM/$ENTITY_TOTAL: $ENTITY_NAME"
      echo "  ─────────────────────────────────────────"

      ENTITY_EXIT=0
      # First entity has no prior run; subsequent entities chain from previous ZIP
      PRIOR_RUN_FLAG=""
      if [[ -n "$LATEST_RUN_DIR" && -d "$LATEST_RUN_DIR" ]]; then
        PRIOR_RUN_FLAG="--prior-run $LATEST_RUN_DIR"
      fi

      python fo_test_harness.py \
        "$ENTITY_INTAKE_FILE" \
        "$BUILD_GOV" \
        --max-iterations "$MAX_ITER" \
        --no-polish \
        $FACTORY_FLAG \
        $PRIOR_RUN_FLAG || ENTITY_EXIT=$?

      if [[ $ENTITY_EXIT -ne 0 ]]; then
        echo ""
        echo "✗ Entity '$ENTITY_NAME' FAILED (exit $ENTITY_EXIT)"
        echo "  Rerun the same command — completed entities will be auto-skipped."
        exit 1
      fi

      # Find the ZIP for this entity
      ENTITY_ZIP=$(ls -t "fo_harness_runs/${ENTITY_STARTUP_ID}_BLOCK_B_"*.zip 2>/dev/null | head -1 || true)
      if [[ -z "$ENTITY_ZIP" ]]; then
        echo "ERROR: ZIP not found for entity '$ENTITY_NAME' (startup_id: $ENTITY_STARTUP_ID)"
        exit 1
      fi

      echo "  ✓ Entity ZIP: $ENTITY_ZIP"
      ALL_ZIPS+=("$ENTITY_ZIP")
      LATEST_ZIP="$ENTITY_ZIP"
      LATEST_RUN_DIR="${ENTITY_ZIP%.zip}"
      echo ""
      echo "════════════════════════════════════════════════════════"
      echo "  ✓ ENTITY $ENTITY_NUM/$ENTITY_TOTAL COMPLETE: $ENTITY_NAME"
      echo "════════════════════════════════════════════════════════"
      echo ""

    done <<< "$ENTITY_INTAKES"

  else
    # ── Monolithic Phase 1 build (legacy mode) ────────────────────────────
    echo "  Mode: monolithic (single Phase 1 build)"
    P1_EXIT=0
    python fo_test_harness.py \
      "$PHASE1_INTAKE" \
      "$BUILD_GOV" \
      --max-iterations "$MAX_ITER" \
      --no-polish \
      $FACTORY_FLAG || P1_EXIT=$?

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
    $FACTORY_FLAG \
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
  echo "════════════════════════════════════════════════════════"
  echo "  ✓ FEATURE $FEATURE_NUM/$TOTAL_INTEL COMPLETE: $FEATURE"
  echo "════════════════════════════════════════════════════════"
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

  # Use FEATURE_INTAKE if set (inside feature loop), else fall back to phase 1 INTAKE
  _FIX_INTAKE="${FEATURE_INTAKE:-$INTAKE}"
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
echo "  FEATURE BUILD COMPLETE"
echo ""
for i in "${!ALL_ZIPS[@]}"; do
  echo "  Phase/Feature $((i+1)): ${ALL_ZIPS[$i]}"
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
