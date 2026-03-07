#!/usr/bin/env bash
# run_feature_build.sh — Full feature-by-feature build pipeline.
#
# Flow:
#   1. Runs phase_planner.py to split intake into data layer + feature list
#   2. Builds Phase 1 (data layer, --no-polish)
#   3. For each intelligence feature: runs feature_adder.py then fo_test_harness.py
#      - All but the last feature: --no-polish
#      - Last feature: full polish (README, .env, tests)
#   4. Merges all ZIPs into a single final deliverable
#
# Usage:
#   ./run_feature_build.sh --intake <path/to/intake.json> [options]
#
# Required:
#   --intake        Path to original intake JSON
#
# Optional:
#   --startup-id    Base name for final ZIP (default: derived from intake stem)
#   --build-gov     Path to FOBUILFINALLOCKED100.zip (default: last known)
#   --deploy-gov    Path to deploy governance ZIP (default: last known)
#   --max-iterations N  Per-phase/feature iteration cap (default: 20)
#   --no-ai         Skip AI classifier in phase_planner (faster, rule-based only)
#
# Example:
#   ./run_feature_build.sh \
#     --intake intake/intake_runs/ai_workforce_intelligence/ai_workforce_intelligence.5.json \
#     --startup-id awi

set -euo pipefail

# ── Defaults ──────────────────────────────────────────────────────────────────
BUILD_GOV="/Users/teebuphilip/Documents/work/FounderOps/docs/architecture/BUILD/build_rules/FOBUILFINALLOCKED100.zip"
DEPLOY_GOV="/Users/teebuphilip/Documents/work/FounderOps/docs/architecture/BUILD/deployment_rules/fo_deploy_governance_v1_2_CLARIFIED.zip"
MAX_ITER=20
STARTUP_ID=""
INTAKE=""
NO_AI=""

# ── Parse args ─────────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --intake)         INTAKE="$2";        shift 2 ;;
    --startup-id)     STARTUP_ID="$2";    shift 2 ;;
    --build-gov)      BUILD_GOV="$2";     shift 2 ;;
    --deploy-gov)     DEPLOY_GOV="$2";    shift 2 ;;
    --max-iterations) MAX_ITER="$2";      shift 2 ;;
    --no-ai)          NO_AI="--no-ai";    shift 1 ;;
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

# Derive startup-id from intake stem if not provided
if [[ -z "$STARTUP_ID" ]]; then
  STARTUP_ID=$(basename "$INTAKE" .json | sed 's/\\./_/g')
fi

INTAKE_DIR=$(dirname "$INTAKE")
INTAKE_STEM=$(basename "$INTAKE" .json)
ASSESSMENT="${INTAKE_DIR}/${INTAKE_STEM}_phase_assessment.json"
PHASE1_INTAKE="${INTAKE_DIR}/${INTAKE_STEM}_phase1.json"

echo "========================================================"
echo "  FEATURE BUILD PIPELINE"
echo "  Intake     : $INTAKE"
echo "  Startup ID : $STARTUP_ID"
echo "  Max iter   : $MAX_ITER (per feature)"
echo "  Build GOV  : $BUILD_GOV"
echo "========================================================"
echo ""

# ── Step 1: Run phase_planner ──────────────────────────────────────────────────
echo "▶ STEP 1 — Phase Planner (classifying features)"
echo "────────────────────────────────────────────────────────"
python phase_planner.py --intake "$INTAKE" $NO_AI
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

python fo_test_harness.py \
  "$PHASE1_INTAKE" \
  "$BUILD_GOV" \
  "$DEPLOY_GOV" \
  --max-iterations "$MAX_ITER" \
  --no-polish

P1_EXIT=$?
if [[ $P1_EXIT -ne 0 ]]; then
  echo ""
  echo "✗ PHASE 1 FAILED (exit $P1_EXIT)"
  echo "  Resume: python fo_test_harness.py --resume-run fo_harness_runs/<p1_run_dir> --resume-mode qa"
  exit 1
fi

# Find Phase 1 ZIP (most recent _p1_ ZIP)
LATEST_ZIP=$(ls -t fo_harness_runs/*_p1_BLOCK_B_*.zip 2>/dev/null | head -1 || true)
if [[ -z "$LATEST_ZIP" ]]; then
  echo "ERROR: Phase 1 ZIP not found in fo_harness_runs/"
  exit 1
fi
echo "✓ Phase 1 ZIP: $LATEST_ZIP"
ALL_ZIPS+=("$LATEST_ZIP")
echo ""

# ── Step 3: Build each intelligence feature ────────────────────────────────────
FEATURE_NUM=0
TOTAL_INTEL=$INTEL_COUNT

while IFS= read -r FEATURE; do
  [[ -z "$FEATURE" ]] && continue
  FEATURE_NUM=$((FEATURE_NUM + 1))

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

  python fo_test_harness.py \
    "$FEATURE_INTAKE" \
    "$BUILD_GOV" \
    "$DEPLOY_GOV" \
    --max-iterations "$MAX_ITER" \
    $POLISH_FLAG

  FEAT_EXIT=$?
  if [[ $FEAT_EXIT -ne 0 ]]; then
    echo ""
    echo "✗ FEATURE '$FEATURE' FAILED (exit $FEAT_EXIT)"
    echo ""
    echo "  Prior ZIPs built so far:"
    for Z in "${ALL_ZIPS[@]}"; do echo "    $Z"; done
    echo ""
    echo "  To resume this feature:"
    echo "  python fo_test_harness.py --resume-run fo_harness_runs/<run_dir> --resume-mode qa"
    echo ""
    echo "  Then re-run this script from this feature onward by passing the latest ZIP"
    echo "  as --manifest to feature_adder.py manually and continuing."
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
  echo ""

done <<< "$INTEL_FEATURES"

# ── Step 4: Merge all ZIPs ────────────────────────────────────────────────────
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
