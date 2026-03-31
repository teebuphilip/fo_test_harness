#!/usr/bin/env bash
set -euo pipefail
trap 'echo "======================="; echo "======================="' EXIT

usage() {
  cat <<'USAGE'
Usage:
  munger/run_munger_full.sh <hero_input.json> [--out <munged.json>] [--fixer-out <fixer.json>] [--report-out <report.json>] [--max-loops <n>] [--resume]

Flow:
  1) Run munger.py on original hero input
  2) If PASS -> write <slug>.munged.json (normalized) and exit 0
  3) If NEEDS_CLARIFICATION -> run munger_ai_fixer.py
  4) Write <slug>.munged.json using updated_q1_q11
  5) Re-run munger.py on munged file and report status

Defaults:
  --out        munger/<slug>.munged.json
  --fixer-out  munger/<slug>_munger_ai_fixed.json
  --report-out munger/<slug>_munger_out.json
  --max-loops  5
USAGE
}

if [[ ${1:-} == "-h" || ${1:-} == "--help" ]]; then
  usage
  exit 0
fi

INPUT=${1:-}
if [[ -z "$INPUT" ]]; then
  usage
  exit 1
fi
shift || true

OUT=""
FIXER_OUT=""
REPORT_OUT=""
MAX_LOOPS=5
RESUME=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --out)
      OUT=${2:-}
      shift 2
      ;;
    --fixer-out)
      FIXER_OUT=${2:-}
      shift 2
      ;;
    --report-out)
      REPORT_OUT=${2:-}
      shift 2
      ;;
    --max-loops)
      MAX_LOOPS=${2:-5}
      shift 2
      ;;
    --resume)
      RESUME=1
      shift 1
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-}"
if [[ -z "$PYTHON_BIN" ]]; then
  if [[ -n "${VIRTUAL_ENV:-}" && -x "$VIRTUAL_ENV/bin/python" ]]; then
    PYTHON_BIN="$VIRTUAL_ENV/bin/python"
  else
    PYTHON_BIN="python"
  fi
fi

SLUG="$(basename "$INPUT" .json)"
OUT=${OUT:-"$ROOT/munger/${SLUG}.munged.json"}
FIXER_OUT=${FIXER_OUT:-"$ROOT/munger/${SLUG}_munger_ai_fixed.json"}
REPORT_OUT=${REPORT_OUT:-"$ROOT/munger/${SLUG}_munger_out.json"}

echo "[MungerFull] Input: $INPUT"
echo "[MungerFull] Munged output: $OUT"
echo "[MungerFull] Fixer output: $FIXER_OUT"
echo "[MungerFull] Report output: $REPORT_OUT"
echo "[MungerFull] Python: $PYTHON_BIN"
echo "[MungerFull] Max loops: $MAX_LOOPS"
if [[ "$RESUME" == "1" ]]; then
  echo "[MungerFull] Resume: enabled"
fi

CURRENT_INPUT="$INPUT"
if [[ "$RESUME" == "1" && -f "$OUT" ]]; then
  echo "[MungerFull] Resume enabled and munged output exists — starting from munged file"
  CURRENT_INPUT="$OUT"
fi

write_munged_from_report() {
  local report_path="$1"
  local base_input="$2"
  local out_path="$3"
  python - "$report_path" "$base_input" "$out_path" <<'PY'
import json, sys
from pathlib import Path

report_path = Path(sys.argv[1])
input_path = Path(sys.argv[2])
out_path = Path(sys.argv[3])

report = json.loads(report_path.read_text(encoding="utf-8"))
clean = report.get("clean_hero_answers", {})

mapping = {
    "problem_customer": "Q1_problem_customer",
    "target_user": "Q2_target_user",
    "success_metric": "Q3_success_metric",
    "must_have_features": "Q4_must_have_features",
    "non_goals": "Q5_non_goals",
    "constraints": "Q6_constraints",
    "data_sources": "Q7_data_sources",
    "integrations": "Q8_integrations",
    "risks": "Q9_risks",
    "shipping_preference": "Q10_shipping_preference",
    "architecture": "Q11_architecture",
}

hero_answers = {}
for src, dst in mapping.items():
    if src in clean:
        hero_answers[dst] = clean[src]

base = json.loads(input_path.read_text(encoding="utf-8"))
base["hero_answers"] = hero_answers

integrations = base.get("hero_answers", {}).get("Q8_integrations")
if isinstance(integrations, list) and len(integrations) > 1:
    cleaned = [x for x in integrations if str(x).strip().lower() != "none"]
    if cleaned:
        base["hero_answers"]["Q8_integrations"] = cleaned

out_path.parent.mkdir(parents=True, exist_ok=True)
out_path.write_text(json.dumps(base, indent=2, ensure_ascii=False))
print(f"Wrote: {out_path}")
PY
}

write_munged_from_fixer() {
  local fixer_path="$1"
  local base_input="$2"
  local out_path="$3"
  python - "$fixer_path" "$base_input" "$out_path" <<'PY'
import json, sys
from pathlib import Path

fixer_path = Path(sys.argv[1])
input_path = Path(sys.argv[2])
out_path = Path(sys.argv[3])

fixer = json.loads(fixer_path.read_text(encoding="utf-8"))
updated = fixer.get("updated_q1_q11", {})
if not updated:
    raise SystemExit("No updated_q1_q11 found in fixer output")

base = json.loads(input_path.read_text(encoding="utf-8"))
base["hero_answers"] = updated

integrations = base.get("hero_answers", {}).get("Q8_integrations")
if isinstance(integrations, list) and len(integrations) > 1:
    cleaned = [x for x in integrations if str(x).strip().lower() != "none"]
    if cleaned:
        base["hero_answers"]["Q8_integrations"] = cleaned

out_path.parent.mkdir(parents=True, exist_ok=True)
out_path.write_text(json.dumps(base, indent=2, ensure_ascii=False))
print(f"Wrote: {out_path}")
PY
}

for ((i=1; i<=MAX_LOOPS; i++)); do
  echo "[MungerFull] Loop $i/$MAX_LOOPS"
  "$PYTHON_BIN" "$ROOT/munger/munger.py" "$CURRENT_INPUT" --out "$REPORT_OUT"

  STATUS=$("$PYTHON_BIN" - "$REPORT_OUT" <<'PY'
import json, sys
path = sys.argv[1]
data = json.load(open(path, "r", encoding="utf-8"))
print(data.get("munger_report", {}).get("status", "UNKNOWN"))
PY
)

  LOW_COUNT=$("$PYTHON_BIN" - "$REPORT_OUT" <<'PY'
import json, sys
data = json.load(open(sys.argv[1], "r", encoding="utf-8"))
issues = data.get("munger_report", {}).get("issues", [])
print(sum(1 for i in issues if i.get("severity") == "LOW"))
PY
)

  if [[ "$STATUS" == "PASS" && "$LOW_COUNT" -eq 0 ]]; then
    echo "[MungerFull] Status PASS — writing munged file from clean_hero_answers"
    write_munged_from_report "$REPORT_OUT" "$CURRENT_INPUT" "$OUT"
    exit 0
  fi

  if [[ "$STATUS" == "PASS" && "$LOW_COUNT" -gt 0 ]]; then
    echo "[MungerFull] Status PASS with $LOW_COUNT LOW issues — attempting low-issue cleanup"
  fi

  if [[ "$STATUS" != "NEEDS_CLARIFICATION" && ! ( "$STATUS" == "PASS" && "$LOW_COUNT" -gt 0 ) ]]; then
    echo "[MungerFull] Status $STATUS — stopping"
    exit 1
  fi

  SHOULD_RUN_FIXER=1
  if [[ "$RESUME" == "1" && -f "$FIXER_OUT" && ! ( "$STATUS" == "PASS" && "$LOW_COUNT" -gt 0 ) ]]; then
    FIXER_STATUS=$("$PYTHON_BIN" - "$FIXER_OUT" <<'PY'
import json, sys
try:
    data = json.load(open(sys.argv[1], "r", encoding="utf-8"))
    print(data.get("status", "UNKNOWN"))
except Exception:
    print("UNKNOWN")
PY
)
    if [[ "$FIXER_STATUS" == "SUCCESS" ]]; then
      SHOULD_RUN_FIXER=0
      echo "[MungerFull] Resume enabled and fixer status SUCCESS — skipping fixer call"
    fi
  fi

  if [[ "$SHOULD_RUN_FIXER" == "1" ]]; then
    set +e
    "$PYTHON_BIN" "$ROOT/munger/munger_ai_fixer.py" "$CURRENT_INPUT" --out "$FIXER_OUT" --max-loops "$MAX_LOOPS"
    FIXER_RC=$?
    set -e
    if [[ "$FIXER_RC" -ne 0 ]]; then
      echo "[MungerFull] Fixer failed (rc=$FIXER_RC) — stopping"
      exit 1
    fi
    FIXER_STATUS=$("$PYTHON_BIN" - "$FIXER_OUT" <<'PY'
import json, sys
try:
    data = json.load(open(sys.argv[1], "r", encoding="utf-8"))
    print(data.get("status", "UNKNOWN"))
except Exception:
    print("UNKNOWN")
PY
)
    echo "[MungerFull] Fixer status: $FIXER_STATUS (rc=$FIXER_RC)"
  else
    FIXER_RC=0
  fi

  write_munged_from_fixer "$FIXER_OUT" "$CURRENT_INPUT" "$OUT"
  CURRENT_INPUT="$OUT"
done

echo "[MungerFull] Reached max loops ($MAX_LOOPS) without PASS"
exit 1
