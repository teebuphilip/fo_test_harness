#!/usr/bin/env bash
# add_feature.sh — Add ONE new feature to an existing built codebase.
#
# Lifecycle:
#   1. Run feature_adder.py to generate a scoped feature intake
#      (reads existing files from --existing-zip OR --existing-repo)
#   2. Build the feature via fo_test_harness.py
#   3. Run integration_check.py; if HIGH issues → fix loop (up to 2 passes)
#   4. Merge existing codebase + feature ZIP → new final ZIP
#
# Usage (from ZIP):
#   ./add_feature.sh \
#     --intake  intake/intake_runs/awi/awi.5.json \
#     --feature "Competitor benchmarking dashboard" \
#     --existing-zip fo_harness_runs/awi_downloadable_exec_report_FINAL_20260309.zip
#
# Usage (from live repo):
#   ./add_feature.sh \
#     --intake  intake/intake_runs/awi/awi.5.json \
#     --feature "Competitor benchmarking dashboard" \
#     --existing-repo ~/Documents/work/ai_workforce_intelligence
#
#   --existing-repo also accepts a GitHub HTTPS URL — the script clones it first:
#   ./add_feature.sh \
#     --intake  intake/intake_runs/awi/awi.5.json \
#     --feature "Competitor benchmarking dashboard" \
#     --existing-repo https://github.com/myorg/ai_workforce_intelligence
#
# Required:
#   --intake          Path to original intake JSON
#   --feature         Name of the new feature (wrap in quotes)
#   --existing-zip    Path to current final ZIP   } one of
#   --existing-repo   Local path OR GitHub URL    } these two
#
# Optional:
#   --startup-id       Base name for run dirs (default: derived from intake stem)
#   --build-gov        Path to FOBUILFINALLOCKED*.zip (default: auto-detected in cwd)
#   --max-iterations N Per-run iteration cap (default: 20)
#
# Resume behaviour (automatic):
#   - Feature intake JSON already exists → skip generation
#   - Feature ZIP already exists → skip harness build
#   - Final ZIP already exists → exit immediately

set -euo pipefail

# ── Defaults ──────────────────────────────────────────────────────────────────
BUILD_GOV="$(ls FOBUILFINALLOCKED*.zip 2>/dev/null | head -1 || true)"
MAX_ITER=20
STARTUP_ID=""
INTAKE=""
FEATURE=""
EXISTING_ZIP=""
EXISTING_REPO=""
_CLONED_REPO_TMP=""   # set if we cloned a URL; cleaned up on exit

cleanup() {
  if [[ -n "$_CLONED_REPO_TMP" && -d "$_CLONED_REPO_TMP" ]]; then
    rm -rf "$_CLONED_REPO_TMP"
  fi
}
trap cleanup EXIT

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
    --intake)           INTAKE="$2";        shift 2 ;;
    --feature)          FEATURE="$2";       shift 2 ;;
    --existing-zip)     EXISTING_ZIP="$2";  shift 2 ;;
    --existing-repo)    EXISTING_REPO="$2"; shift 2 ;;
    --startup-id)       STARTUP_ID="$2";    shift 2 ;;
    --build-gov)        BUILD_GOV="$2";     shift 2 ;;
    --max-iterations)   MAX_ITER="$2";      shift 2 ;;
    *) echo "Unknown flag: $1"; exit 1 ;;
  esac
done

# ── Validate args ─────────────────────────────────────────────────────────────
if [[ -z "$INTAKE" ]]; then
  echo "ERROR: --intake is required"
  echo "Usage: $0 --intake <path> --feature \"Feature Name\" (--existing-zip <path> | --existing-repo <path|url>)"
  exit 1
fi
if [[ -z "$FEATURE" ]]; then
  echo "ERROR: --feature is required"
  exit 1
fi
if [[ -z "$EXISTING_ZIP" && -z "$EXISTING_REPO" ]]; then
  echo "ERROR: one of --existing-zip or --existing-repo is required"
  exit 1
fi
if [[ -n "$EXISTING_ZIP" && -n "$EXISTING_REPO" ]]; then
  echo "ERROR: --existing-zip and --existing-repo are mutually exclusive"
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

# ── Resolve existing-repo: clone if URL, else validate local path ─────────────
REPO_LOCAL_PATH=""
if [[ -n "$EXISTING_REPO" ]]; then
  if [[ "$EXISTING_REPO" == http://* || "$EXISTING_REPO" == https://* || "$EXISTING_REPO" == git@* ]]; then
    echo "▶ Cloning repo: $EXISTING_REPO"
    _CLONED_REPO_TMP=$(mktemp -d)
    git clone --depth=1 "$EXISTING_REPO" "$_CLONED_REPO_TMP/repo"
    REPO_LOCAL_PATH="$_CLONED_REPO_TMP/repo"
    echo "  Cloned to: $REPO_LOCAL_PATH"
    echo ""
  else
    REPO_LOCAL_PATH=$(python3 -c "import os, sys; print(os.path.abspath(sys.argv[1]))" "$EXISTING_REPO")
    if [[ ! -d "$REPO_LOCAL_PATH" ]]; then
      echo "ERROR: Repo directory not found: $REPO_LOCAL_PATH"
      exit 1
    fi
  fi
fi

# ── Validate ZIP if provided ──────────────────────────────────────────────────
if [[ -n "$EXISTING_ZIP" && ! -f "$EXISTING_ZIP" ]]; then
  echo "ERROR: Existing ZIP not found: $EXISTING_ZIP"
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

BASE_ID=$(python3 -c "import json; print(json.load(open('$INTAKE')).get('startup_idea_id','unknown').rstrip('_'))")
STARTUP_SLUG="${BASE_ID}_${FEATURE_SLUG}"

# ── Print banner ──────────────────────────────────────────────────────────────
echo "========================================================"
echo "  ADD FEATURE PIPELINE"
echo "  Intake        : $INTAKE"
echo "  Feature       : $FEATURE"
echo "  Feature slug  : $FEATURE_SLUG"
if [[ -n "$EXISTING_ZIP" ]]; then
  echo "  Base (ZIP)    : $EXISTING_ZIP"
else
  echo "  Base (repo)   : $REPO_LOCAL_PATH"
fi
echo "  Max iter      : $MAX_ITER"
echo "  Build GOV     : $BUILD_GOV"
echo "========================================================"
echo ""

# ── Early exit: final ZIP already exists ──────────────────────────────────────
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
  echo "  ↩ Feature intake already exists — skipping:"
  echo "    $FEATURE_INTAKE"
else
  if [[ -n "$EXISTING_ZIP" ]]; then
    python feature_adder.py \
      --intake "$INTAKE" \
      --manifest "$EXISTING_ZIP" \
      --feature "$FEATURE"
  else
    python feature_adder.py \
      --intake "$INTAKE" \
      --repo "$REPO_LOCAL_PATH" \
      --feature "$FEATURE"
  fi

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

FEATURE_ZIP=$(ls -t "fo_harness_runs/${STARTUP_SLUG}_BLOCK_B_"*.zip 2>/dev/null | grep -v '_full_' | head -1 || true)
FEATURE_RUN_DIR=""

if [[ -n "$FEATURE_ZIP" ]]; then
  echo "  ↩ Feature ZIP already exists — skipping build:"
  echo "    $FEATURE_ZIP"
  FEATURE_RUN_DIR="${FEATURE_ZIP%.zip}"
else
  BUILD_EXIT=0

  # --prior-run: pass existing ZIP's run dir if it exists (carries QA prohibitions).
  # Not applicable when starting from a live repo.
  PRIOR_RUN_FLAG=""
  if [[ -n "$EXISTING_ZIP" ]]; then
    EXISTING_RUN_DIR="${EXISTING_ZIP%.zip}"
    if [[ -d "$EXISTING_RUN_DIR" ]]; then
      PRIOR_RUN_FLAG="--prior-run $EXISTING_RUN_DIR"
    fi
  fi

  python fo_test_harness.py \
    "$FEATURE_INTAKE" \
    "$BUILD_GOV" \
    --max-iterations "$MAX_ITER" \
    $PRIOR_RUN_FLAG || BUILD_EXIT=$?

  if [[ $BUILD_EXIT -ne 0 ]]; then
    echo ""
    echo "✗ FEATURE BUILD FAILED (exit $BUILD_EXIT)"
    echo ""
    echo "  Rerun the same command — the script will auto-resume:"
    if [[ -n "$EXISTING_ZIP" ]]; then
      echo "  ./add_feature.sh --intake $INTAKE --feature \"$FEATURE\" --existing-zip $EXISTING_ZIP"
    else
      echo "  ./add_feature.sh --intake $INTAKE --feature \"$FEATURE\" --existing-repo $EXISTING_REPO"
    fi
    exit 1
  fi

  FEATURE_ZIP=$(ls -t "fo_harness_runs/${STARTUP_SLUG}_BLOCK_B_"*.zip 2>/dev/null | grep -v '_full_' | head -1 || true)
  if [[ -z "$FEATURE_ZIP" ]]; then
    echo "ERROR: Feature ZIP not found for startup_id: $STARTUP_SLUG"
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

IC_HIGH=0
if [[ $IC_EXIT -ne 0 && -f "$INTEGRATION_ISSUES" ]]; then
  IC_HIGH=$(python3 -c "
import json
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
  echo "⚠ Integration issues found (HIGH: $IC_HIGH) — fix pass $FIX_PASS/$MAX_FIX_PASSES"

  ARTIFACTS_DIR=$(latest_artifacts_dir "$LATEST_RUN_DIR")
  LATEST_ITER=$(latest_iteration_num "$ARTIFACTS_DIR")
  if [[ -z "$LATEST_ITER" ]]; then
    echo "ERROR: Unable to determine latest iteration for resume."
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
    echo "✗ INTEGRATION FIX PASS $FIX_PASS FAILED (exit $FIX_EXIT)"
    exit 1
  fi

  FIX_ZIP=$(ls -t "fo_harness_runs/${STARTUP_SLUG}_BLOCK_B_"*.zip 2>/dev/null | grep -v '_full_' | head -1 || true)
  if [[ -z "$FIX_ZIP" ]]; then
    echo "ERROR: ZIP not found after fix pass $FIX_PASS."
    exit 1
  fi
  LATEST_ZIP="$FIX_ZIP"
  LATEST_RUN_DIR="${FIX_ZIP%.zip}"

  echo ""
  echo "▶ Re-checking integration (pass $FIX_PASS/$MAX_FIX_PASSES)"
  echo "────────────────────────────────────────────────────────"
  INTEGRATION_ISSUES="${LATEST_RUN_DIR}/integration_issues.json"
  _run_integration_check "$INTEGRATION_ISSUES"

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
  echo "✗ INTEGRATION CHECK STILL FAILING AFTER $FIX_PASS FIX PASS(ES)"
  echo "  Manual review required. See: $INTEGRATION_ISSUES"
  exit 1
fi

echo "✓ Integration check clean."
echo ""

# ── Step 4: Merge base + feature ZIP → new final ZIP ──────────────────────────
echo "▶ STEP 4 — Merge into new final ZIP"
echo "────────────────────────────────────────────────────────"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
FINAL_ZIP="fo_harness_runs/${STARTUP_ID}_${FEATURE_SLUG}_FINAL_${TIMESTAMP}.zip"
MERGE_TMP=$(mktemp -d)

if [[ -n "$EXISTING_ZIP" ]]; then
  echo "  Layering (later source wins on conflict):"
  echo "    Base (ZIP)  : $EXISTING_ZIP"
  echo "    Feature     : $LATEST_ZIP"
  unzip -q -o "$EXISTING_ZIP" -d "$MERGE_TMP"
else
  echo "  Layering (later source wins on conflict):"
  echo "    Base (repo) : $REPO_LOCAL_PATH"
  echo "    Feature     : $LATEST_ZIP"
  # Copy business/ from repo into merge dir; maintain path structure
  if [[ -d "$REPO_LOCAL_PATH/business" ]]; then
    cp -r "$REPO_LOCAL_PATH/business" "$MERGE_TMP/business"
  else
    # Repo root is the business layer (no business/ subdirectory)
    cp -r "$REPO_LOCAL_PATH/." "$MERGE_TMP/"
  fi
fi

unzip -q -o "$LATEST_ZIP" -d "$MERGE_TMP"

(cd "$MERGE_TMP" && zip -qr - .) > "$FINAL_ZIP"
rm -rf "$MERGE_TMP"

FINAL_SIZE=$(du -sh "$FINAL_ZIP" | cut -f1)

echo "========================================================"
echo "  FEATURE ADD COMPLETE"
echo ""
echo "  Feature       : $FEATURE"
if [[ -n "$EXISTING_ZIP" ]]; then
  echo "  Base          : $EXISTING_ZIP"
else
  echo "  Base          : $REPO_LOCAL_PATH"
fi
echo "  Feature ZIP   : $LATEST_ZIP"
echo "  FINAL ZIP     : $FINAL_ZIP  ($FINAL_SIZE)"
echo "========================================================"
echo ""
echo "Next step — deploy:"
echo "  python deploy/zip_to_repo.py $FINAL_ZIP"
