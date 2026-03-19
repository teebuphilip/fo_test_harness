#!/usr/bin/env bash
# run_auto_build.sh — auto-route to slice or phase pipeline based on intake.
#
# Defaults:
# - If planner_router recommends "slice" → run_slicer_and_feature_build.sh
# - Otherwise → run_integration_and_feature_build.sh
#
# Usage:
#   ./run_auto_build.sh --intake <path/to/intake.json> [--force slice|phase] [other args...]

set -euo pipefail

INTAKE=""
FORCE=""
ARGS=("$@")

for ((i=0; i<${#ARGS[@]}; i++)); do
  if [[ "${ARGS[$i]}" == "--intake" ]]; then
    INTAKE="${ARGS[$((i+1))]:-}"
    break
  elif [[ "${ARGS[$i]}" == "--force" ]]; then
    FORCE="${ARGS[$((i+1))]:-}"
  fi
done

if [[ -z "$INTAKE" ]]; then
  echo "ERROR: --intake is required"
  echo "Usage: $0 --intake <path/to/intake.json> [other args...]"
  exit 1
fi

if [[ ! -f "$INTAKE" ]]; then
  echo "ERROR: Intake not found: $INTAKE"
  exit 1
fi

if [[ -n "$FORCE" ]]; then
  if [[ "$FORCE" != "slice" && "$FORCE" != "phase" ]]; then
    echo "ERROR: --force must be 'slice' or 'phase' (got: $FORCE)"
    exit 1
  fi
  REC="$FORCE"
else
  REC_JSON=$(python3 planner_router.py --intake "$INTAKE" --json)
  REC=$(python3 -c "import json; print(json.loads('''$REC_JSON''').get('recommended_planner','phase'))")
fi

if [[ "$REC" == "slice" ]]; then
  echo "Auto-route: slice planner → run_slicer_and_feature_build.sh"
  ./run_slicer_and_feature_build.sh "$@"
else
  echo "Auto-route: phase planner → run_integration_and_feature_build.sh"
  ./run_integration_and_feature_build.sh "$@"
fi
