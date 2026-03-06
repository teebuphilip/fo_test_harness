#!/usr/bin/env bash
# run_phased_build.sh — Run a 2-phase build (DATA_LAYER → INTELLIGENCE_LAYER)
# and merge the two output ZIPs into a single deliverable.
#
# Usage:
#   ./run_phased_build.sh --intake-base <stem> [options]
#
# Required:
#   --intake-base   Path stem WITHOUT _phase1.json / _phase2.json suffix
#                   e.g. intake/intake_runs/ai_workforce_intelligence/ai_workforce_intelligence.5
#
# Optional:
#   --startup-id    Base name for run dirs (default: derived from intake stem)
#   --build-gov     Path to FOBUILFINALLOCKED100.zip
#   --max-iterations N  Per-phase iteration cap (default: 5)
#   --block         A or B (default: B)
#
# Example:
#   ./run_phased_build.sh \
#     --intake-base intake/intake_runs/ai_workforce_intelligence/ai_workforce_intelligence.5 \
#     --startup-id awi \
#     --build-gov /Users/teebuphilip/Documents/work/FounderOps/docs/architecture/BUILD/build_rules/FOBUILFINALLOCKED100.zip

set -euo pipefail

# ── Defaults ──────────────────────────────────────────────────────────────────
BUILD_GOV="/Users/teebuphilip/Documents/work/FounderOps/docs/architecture/BUILD/build_rules/FOBUILFINALLOCKED100.zip"
BLOCK="B"
MAX_ITER=5
STARTUP_ID=""
INTAKE_BASE=""

# ── Parse args ─────────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --intake-base)    INTAKE_BASE="$2";    shift 2 ;;
    --startup-id)     STARTUP_ID="$2";     shift 2 ;;
    --build-gov)      BUILD_GOV="$2";      shift 2 ;;
    --max-iterations) MAX_ITER="$2";       shift 2 ;;
    --block)          BLOCK="$2";          shift 2 ;;
    *) echo "Unknown flag: $1"; exit 1 ;;
  esac
done

if [[ -z "$INTAKE_BASE" ]]; then
  echo "ERROR: --intake-base is required"
  echo "Usage: $0 --intake-base <path/to/intake_stem> [--startup-id name] [--build-gov /path/to/gov.zip]"
  exit 1
fi

PHASE1_INTAKE="${INTAKE_BASE}_phase1.json"
PHASE2_INTAKE="${INTAKE_BASE}_phase2.json"

if [[ ! -f "$PHASE1_INTAKE" ]]; then
  echo "ERROR: Phase 1 intake not found: $PHASE1_INTAKE"
  echo "Run phase_planner.py first:"
  echo "  python phase_planner.py --intake <original_intake.json>"
  exit 1
fi

if [[ ! -f "$PHASE2_INTAKE" ]]; then
  echo "ERROR: Phase 2 intake not found: $PHASE2_INTAKE"
  exit 1
fi

# Derive startup-id from intake stem if not provided
if [[ -z "$STARTUP_ID" ]]; then
  STEM=$(basename "$INTAKE_BASE")
  STARTUP_ID="${STEM//./_}"
fi

P1_ID="${STARTUP_ID}_p1"
P2_ID="${STARTUP_ID}_p2"

echo "========================================================"
echo "  PHASED BUILD"
echo "  Phase 1 intake : $PHASE1_INTAKE"
echo "  Phase 2 intake : $PHASE2_INTAKE"
echo "  Startup IDs    : $P1_ID / $P2_ID"
echo "  Block          : $BLOCK"
echo "  Max iterations : $MAX_ITER"
echo "  Gov ZIP        : $BUILD_GOV"
echo "========================================================"
echo ""

# ── Phase 1 ───────────────────────────────────────────────────────────────────
echo "▶ PHASE 1 — Data Layer"
echo "────────────────────────────────────────────────────────"

python fo_test_harness.py \
  --intake "$PHASE1_INTAKE" \
  --startup-id "$P1_ID" \
  --block "$BLOCK" \
  --build-gov "$BUILD_GOV" \
  --max-iterations "$MAX_ITER" \
  --no-polish

P1_EXIT=$?

if [[ $P1_EXIT -ne 0 ]]; then
  echo ""
  echo "✗ PHASE 1 FAILED (exit $P1_EXIT) — Phase 2 skipped."
  echo ""
  echo "To resume Phase 1, find the run dir and use:"
  echo "  python fo_test_harness.py --resume-run fo_harness_runs/<p1_run_dir> --resume-mode qa"
  exit 1
fi

echo ""
echo "✓ Phase 1 accepted."
echo ""

# Find Phase 1 output ZIP (most recent matching startup-id)
P1_ZIP=$(ls -t fo_harness_runs/${P1_ID}_BLOCK_${BLOCK}_*.zip 2>/dev/null | head -1)

if [[ -z "$P1_ZIP" ]]; then
  echo "WARNING: Phase 1 ZIP not found — check fo_harness_runs/ manually."
else
  echo "  Phase 1 ZIP: $P1_ZIP"
fi

echo ""

# ── Phase 2 ───────────────────────────────────────────────────────────────────
echo "▶ PHASE 2 — Intelligence Layer"
echo "────────────────────────────────────────────────────────"

python fo_test_harness.py \
  --intake "$PHASE2_INTAKE" \
  --startup-id "$P2_ID" \
  --block "$BLOCK" \
  --build-gov "$BUILD_GOV" \
  --max-iterations "$MAX_ITER"

P2_EXIT=$?

if [[ $P2_EXIT -ne 0 ]]; then
  echo ""
  echo "✗ PHASE 2 FAILED (exit $P2_EXIT)"
  [[ -n "${P1_ZIP:-}" ]] && echo "  Phase 1 output still valid: $P1_ZIP"
  echo "  To resume Phase 2:"
  echo "  python fo_test_harness.py --resume-run fo_harness_runs/<p2_run_dir> --resume-mode qa"
  exit 1
fi

echo ""
echo "✓ Phase 2 accepted."
echo ""

P2_ZIP=$(ls -t fo_harness_runs/${P2_ID}_BLOCK_${BLOCK}_*.zip 2>/dev/null | head -1)

if [[ -z "$P2_ZIP" ]]; then
  echo "WARNING: Phase 2 ZIP not found."
  exit 1
fi

echo "  Phase 2 ZIP: $P2_ZIP"
echo ""

# ── Merge ZIPs ────────────────────────────────────────────────────────────────
echo "▶ MERGING Phase 1 + Phase 2 → final ZIP"
echo "────────────────────────────────────────────────────────"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
FINAL_ZIP="fo_harness_runs/${STARTUP_ID}_BLOCK_${BLOCK}_phased_${TIMESTAMP}.zip"
MERGE_TMP=$(mktemp -d)

echo "  Extracting Phase 1..."
unzip -q "$P1_ZIP" -d "$MERGE_TMP"

echo "  Extracting Phase 2 on top (Phase 2 wins conflicts)..."
unzip -q -o "$P2_ZIP" -d "$MERGE_TMP"

echo "  Repacking..."
(cd "$MERGE_TMP" && zip -qr - .) > "$FINAL_ZIP"

rm -rf "$MERGE_TMP"

FINAL_SIZE=$(du -sh "$FINAL_ZIP" | cut -f1)

echo ""
echo "========================================================"
echo "  PHASED BUILD COMPLETE"
echo "  Phase 1 : $P1_ZIP"
echo "  Phase 2 : $P2_ZIP"
echo "  FINAL   : $FINAL_ZIP  ($FINAL_SIZE)"
echo "========================================================"
echo ""
echo "Next step — deploy:"
echo "  python deploy/zip_to_repo.py $FINAL_ZIP"
