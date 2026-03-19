#!/bin/bash
set -euo pipefail

# Lightweight wrapper for post-deploy QA.
# Requires:
#   TARGET_URL
#   RAILWAY_QA_SERVICE_ID
#   RAILWAY_API_TOKEN

missing=()

if [[ -z "${TARGET_URL:-}" ]]; then
  missing+=("TARGET_URL")
fi
if [[ -z "${RAILWAY_QA_SERVICE_ID:-}" ]]; then
  missing+=("RAILWAY_QA_SERVICE_ID")
fi
if [[ -z "${RAILWAY_API_TOKEN:-}" ]]; then
  missing+=("RAILWAY_API_TOKEN")
fi

if (( ${#missing[@]} > 0 )); then
  echo "[post-deploy-qa] Missing required env vars: ${missing[*]}"
  echo "Example:"
  echo "  export TARGET_URL=https://your-app.vercel.app"
  echo "  export RAILWAY_QA_PROJECT_ID=xxx"
  echo "  export RAILWAY_QA_SERVICE_ID=yyy"
  echo "  export RAILWAY_API_TOKEN=zzz"
  exit 1
fi

python "$(dirname "$0")/trigger_qa.py"
