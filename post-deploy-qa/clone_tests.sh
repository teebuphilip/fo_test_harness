#!/bin/bash
# clone_tests.sh
# Clones the test repo if tests aren't already present (baked in at build time)
# Called by entrypoint.py before running tests

set -e

REPO_URL="${TEST_REPO_URL}"
REPO_BRANCH="${TEST_REPO_BRANCH:-main}"
DEST="/app/tests"

if [ -z "$REPO_URL" ]; then
  echo "[clone_tests] TEST_REPO_URL not set — assuming tests already present at /app/tests"
  exit 0
fi

if [ -d "$DEST/.git" ]; then
  echo "[clone_tests] Repo already cloned, pulling latest..."
  cd "$DEST" && git pull origin "$REPO_BRANCH"
else
  echo "[clone_tests] Cloning $REPO_URL (branch: $REPO_BRANCH) -> $DEST"
  git clone --branch "$REPO_BRANCH" --depth 1 "$REPO_URL" "$DEST"
fi

echo "[clone_tests] Done."
