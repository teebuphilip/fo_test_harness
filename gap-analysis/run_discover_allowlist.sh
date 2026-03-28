#!/usr/bin/env bash
set -euo pipefail

# Defaults
CONTEXT="Broad SaaS markets across ops, finance, HR, ecommerce, and services."
PROVIDER="openai"
MODEL="gpt-4o-mini"
SUGGESTED="gap-analysis/pass0_allowlist_suggested.txt"
ALLOWLIST="gap-analysis/pass0_allowlist.txt"

python gap-analysis/discover_allowlist.py \
  --context "$CONTEXT" \
  --provider "$PROVIDER" \
  --model "$MODEL" \
  --out "$SUGGESTED" \
  --append-to "$ALLOWLIST"
