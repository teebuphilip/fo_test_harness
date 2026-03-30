#!/usr/bin/env bash
set -euo pipefail

PROVIDER="chatgpt"
MODEL=""
IN_PLACE=""
NO_APPLY=""
OUT=""
REPORT=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --provider)
      PROVIDER="$2"; shift 2;;
    --model)
      MODEL="$2"; shift 2;;
    --in-place)
      IN_PLACE="--in-place"; shift;;
    --no-apply)
      NO_APPLY="--no-apply"; shift;;
    --provide-answers)
      PROVIDE_ANSWERS="--provide-answers"; shift;;
    --architecture-context)
      ARCH_CONTEXT="--architecture-context $2"; shift 2;;
    --max-iterations)
      MAX_ITERS="--max-iterations $2"; shift 2;;
    --block-b-only)
      BLOCK_B_ONLY="--block-b-only"; shift;;
    --resume)
      RESUME="--resume"; shift;;
    --out)
      OUT="--out $2"; shift 2;;
    --report)
      REPORT="--report $2"; shift 2;;
    *)
      break;;
  esac
 done

if [[ $# -lt 1 ]]; then
  echo "Usage: ./grill_me.sh <intake.json> [--provider chatgpt|claude] [--model <model>] [--in-place] [--no-apply] [--provide-answers] [--max-iterations <n>] [--block-b-only] [--resume] [--architecture-context <path>] [--out <path>] [--report <path>]"
  exit 1
fi

INTAKE="$1"; shift || true

CMD=("python" "$(dirname "$0")/grill_me.py" --intake "$INTAKE" --provider "$PROVIDER")

if [[ -n "$MODEL" ]]; then CMD+=(--model "$MODEL"); fi
if [[ -n "$IN_PLACE" ]]; then CMD+=(--in-place); fi
if [[ -n "$NO_APPLY" ]]; then CMD+=(--no-apply); fi
if [[ -n "$OUT" ]]; then CMD+=($OUT); fi
if [[ -n "$REPORT" ]]; then CMD+=($REPORT); fi
if [[ -n "${PROVIDE_ANSWERS:-}" ]]; then CMD+=($PROVIDE_ANSWERS); fi
if [[ -n "${ARCH_CONTEXT:-}" ]]; then CMD+=($ARCH_CONTEXT); fi
if [[ -n "${MAX_ITERS:-}" ]]; then CMD+=($MAX_ITERS); fi
if [[ -n "${BLOCK_B_ONLY:-}" ]]; then CMD+=($BLOCK_B_ONLY); fi
if [[ -n "${RESUME:-}" ]]; then CMD+=($RESUME); fi

"${CMD[@]}"
