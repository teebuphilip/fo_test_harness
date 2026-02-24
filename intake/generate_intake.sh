#!/usr/bin/env bash
# Simplified wrapper for intake generation

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [[ $# -eq 0 ]]; then
  echo "Usage:"
  echo "  Hero mode:     $0 <hero_file.json>"
  echo "  Generate mode: $0 <number_of_runs>"
  echo ""
  echo "Examples:"
  echo "  $0 twofacedai.json"
  echo "  $0 5"
  exit 1
fi

FIRST_ARG="$1"

# Check if it's a hero file (exists and ends in .json)
if [[ -f "hero_text/$FIRST_ARG" ]]; then
  # Hero mode
  echo "🚀 Generating intake for hero file: $FIRST_ARG"
  ./run_intake_v7.sh \
    "hero_text/$FIRST_ARG" \
    ./intake_runs \
    ./claude_directive.txt
elif [[ "$FIRST_ARG" =~ ^[0-9]+$ ]]; then
  # Generate mode
  echo "🚀 Generating $FIRST_ARG random startup intakes"
  ./run_intake_v7.sh \
    "$FIRST_ARG" \
    ./intake_runs \
    ./claude_directive.txt \
    ./idea_generation_directive.txt
else
  echo "❌ Invalid argument: $FIRST_ARG"
  echo "   Expected: hero JSON filename (e.g., twofacedai.json) or number (e.g., 5)"
  exit 1
fi
