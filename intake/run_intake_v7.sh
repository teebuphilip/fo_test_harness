#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# FOUNDEROPS INTAKE RUNNER v7 — DUAL MODE ARCHITECTURE
#
# MODE DETECTION (via $1):
#   Hero mode    → $1 is a .json file path (existing hero file)
#   Generate mode → $1 is a positive integer (number of runs)
#
# USAGE:
#   Hero mode:
#     ./run_intake_v7.sh <hero.json> <output_dir> <pass_directive>
#
#   Generate mode:
#     ./run_intake_v7.sh <N> <output_dir> <pass_directive> <idea_directive>
#
# EXAMPLES:
#   ./run_intake_v7.sh hero_text/wynwoodracing.json ./intake_hero_runs ./claude_directive.txt
#   ./run_intake_v7.sh 5 ./claude_runs ./claude_directive.txt ./idea_generation_directive.txt
#
# OUTPUT (both modes):
#   <output_dir>/<run_id>/block_a.json         → Tier 1 passes
#   <output_dir>/<run_id>/block_b.json         → Tier 2 passes
#   <output_dir>/<run_id>/<startup_id>.txt     → One-line description
#   <output_dir>/<run_id>/<startup_id>.json    → Both blocks merged
#
# run_id in hero mode    → startup_idea_id from hero file
# run_id in generate mode → run_N (loop counter)
# ============================================================

# ------------------------------------------------------------
# ARGUMENT PARSING & MODE DETECTION
# ------------------------------------------------------------

if [[ $# -lt 3 ]]; then
  echo "❌ Usage:"
  echo "   Hero mode:     $0 <hero.json> <output_dir> <pass_directive>"
  echo "   Generate mode: $0 <N> <output_dir> <pass_directive> <idea_directive>"
  exit 1
fi

MODE=""
FIRST_ARG="$1"

# Detect mode: if $1 is a .json file → hero mode, if positive integer → generate mode
if [[ -f "$FIRST_ARG" && "$FIRST_ARG" == *.json ]]; then
  MODE="hero"
  HERO_FILE=$(cd "$(dirname "$FIRST_ARG")" && pwd)/$(basename "$FIRST_ARG")
elif [[ "$FIRST_ARG" =~ ^[1-9][0-9]*$ ]]; then
  MODE="generate"
  RUNS="$FIRST_ARG"
else
  echo "❌ Could not detect mode from first argument: '$FIRST_ARG'"
  echo "   Expected: path to a .json hero file, or a positive integer (number of runs)"
  exit 1
fi

OUT_DIR="$2"
PASS_DIRECTIVE="$3"

# Convert to absolute paths before any cd operations
PASS_DIRECTIVE=$(cd "$(dirname "$PASS_DIRECTIVE")" && pwd)/$(basename "$PASS_DIRECTIVE")
OUT_DIR_ABS=$(mkdir -p "$OUT_DIR" && cd "$OUT_DIR" && pwd)

# Validate pass directive
if [[ ! -f "$PASS_DIRECTIVE" ]]; then
  echo "❌ Pass directive not found: $PASS_DIRECTIVE"
  exit 1
fi

# Generate mode requires idea directive as $4
if [[ "$MODE" == "generate" ]]; then
  if [[ $# -lt 4 ]]; then
    echo "❌ Generate mode requires <idea_directive> as 4th argument"
    exit 1
  fi
  IDEA_DIRECTIVE="$4"
  IDEA_DIRECTIVE=$(cd "$(dirname "$IDEA_DIRECTIVE")" && pwd)/$(basename "$IDEA_DIRECTIVE")
  if [[ ! -f "$IDEA_DIRECTIVE" ]]; then
    echo "❌ Idea directive not found: $IDEA_DIRECTIVE"
    exit 1
  fi
fi

# ------------------------------------------------------------
# API / GLOBAL CONFIG
# ------------------------------------------------------------

ANTHROPIC_KEY="${ANTHROPIC_API_KEY:-}"
OPENAI_KEY="${OPENAI_API_KEY:-}"
MODEL_CLAUDE="claude-sonnet-4-20250514"
MODEL_CHATGPT="${OPENAI_MODEL:-gpt-4o-mini}"
# Cost rates (USD per 1M tokens). Override via env if needed.
CLAUDE_INPUT_PER_MTOK="${CLAUDE_INPUT_PER_MTOK:-3.00}"
CLAUDE_OUTPUT_PER_MTOK="${CLAUDE_OUTPUT_PER_MTOK:-15.00}"
OPENAI_INPUT_PER_MTOK="${OPENAI_INPUT_PER_MTOK:-2.50}"
OPENAI_OUTPUT_PER_MTOK="${OPENAI_OUTPUT_PER_MTOK:-10.00}"
FAILURES_DIR="./failures"

mkdir -p "$FAILURES_DIR"

# Store absolute path to inputs directory
INPUTS_DIR=$(pwd)/inputs

# Counters
SUCCESSFUL_RUNS=0
FAILED_RUNS=0

# ------------------------------------------------------------
# STARTUP BANNER
# ------------------------------------------------------------

echo "============================================================"
echo "🚀 FOUNDEROPS INTAKE RUNNER v7"
echo "Mode: $MODE"
if [[ "$MODE" == "hero" ]]; then
  echo "Hero file: $HERO_FILE"
else
  echo "Runs: $RUNS"
  echo "Idea directive: $IDEA_DIRECTIVE"
fi
echo "Output dir: $OUT_DIR_ABS"
echo "Pass directive: $PASS_DIRECTIVE"
echo "============================================================"
echo

# ============================================================
# FUNCTION: build_base_bundle
# Purpose: Load all input JSON files from inputs/ dir and
#          format each with BEGIN/END markers for model context
# Args: none
# Returns: formatted context string via stdout
# ============================================================
build_base_bundle() {
  local bundle=""
  for json_file in "$INPUTS_DIR"/*.json; do
    [[ -f "$json_file" ]] || continue
    local fname
    fname=$(basename "$json_file")
    bundle+="<<<BEGIN_INPUT_FILE: $fname>>>"
    bundle+=$'\n'
    bundle+=$(cat "$json_file")
    bundle+=$'\n'
    bundle+="<<<END_INPUT_FILE>>>"
    bundle+=$'\n'
    bundle+=$'\n'
  done
  echo "$bundle"
}

# ============================================================
# FUNCTION: call_claude
# Purpose: Make API call to Claude with given parameters
# Args:
#   $1 - prompt text
#   $2 - max_tokens
#   $3 - temperature
# Returns: raw API response via stdout
# ============================================================
call_claude() {
  local prompt="$1"
  local max_tokens="$2"
  local temperature="$3"

  if [[ -z "$ANTHROPIC_KEY" ]]; then
    echo "❌ ANTHROPIC_API_KEY not set" >&2
    return 1
  fi

  local payload
  payload=$(jq -n \
    --arg model "$MODEL_CLAUDE" \
    --argjson max_tokens "$max_tokens" \
    --argjson temperature "$temperature" \
    --arg content "$prompt" \
    '{
      model: $model,
      max_tokens: $max_tokens,
      temperature: $temperature,
      messages: [
        {
          role: "user",
          content: $content
        }
      ]
    }')

  curl -s https://api.anthropic.com/v1/messages \
    -H "x-api-key: $ANTHROPIC_KEY" \
    -H "anthropic-version: 2023-06-01" \
    -H "content-type: application/json" \
    -d "$payload"
}

# ============================================================
# FUNCTION: call_chatgpt
# Purpose: Make API call to OpenAI Chat Completions
# Args:
#   $1 - prompt text
#   $2 - max_tokens
#   $3 - temperature
# Returns: raw API response via stdout
# ============================================================
call_chatgpt() {
  local prompt="$1"
  local max_tokens="$2"
  local temperature="$3"

  if [[ -z "$OPENAI_KEY" ]]; then
    echo "❌ OPENAI_API_KEY not set" >&2
    return 1
  fi

  local payload
  payload=$(jq -n \
    --arg model "$MODEL_CHATGPT" \
    --argjson max_tokens "$max_tokens" \
    --argjson temperature "$temperature" \
    --arg content "$prompt" \
    '{
      model: $model,
      max_tokens: $max_tokens,
      temperature: $temperature,
      messages: [
        { role: "user", content: $content }
      ]
    }')

  curl -s https://api.openai.com/v1/chat/completions \
    -H "Authorization: Bearer '"$OPENAI_KEY"'" \
    -H "Content-Type: application/json" \
    -d "$payload"
}

# ============================================================
# FUNCTION: select_provider
# Purpose: Default to ChatGPT unless directive says Claude/Anthropic
# Args:
#   $1 - directive file path
# Returns: "chatgpt" or "claude"
# ============================================================
select_provider() {
  local directive_file="$1"
  local content
  content=$(tr '[:upper:]' '[:lower:]' < "$directive_file" 2>/dev/null || echo "")

  if [[ "$content" == *"claude"* || "$content" == *"anthropic"* ]]; then
    echo "claude"
    return
  fi

  if [[ "$content" == *"chatgpt"* || "$content" == *"openai"* ]]; then
    echo "chatgpt"
    return
  fi

  echo "chatgpt"
}
# ============================================================
# FUNCTION: extract_text_or_fail
# Purpose: Extract text content from API response or fail loudly
# Args:
#   $1 - raw API response JSON
# Returns: extracted text via stdout, exits on fatal error,
#          returns 1 on retryable error
# ============================================================
extract_text_or_fail() {
  local raw_response="$1"
  local provider="${2:-unknown}"

  local error_type
  error_type=$(echo "$raw_response" | jq -r '.error.type // empty')

  if [[ -n "$error_type" ]]; then
    local error_msg
    error_msg=$(echo "$raw_response" | jq -r '.error.message // "Unknown error"')

    if is_fatal_api_error "$error_type"; then
      local expected_key="API key"
      if [[ "$provider" == "chatgpt" ]]; then
        expected_key="OPENAI_API_KEY"
      elif [[ "$provider" == "claude" ]]; then
        expected_key="ANTHROPIC_API_KEY"
      fi
      echo "❌ FATAL API ERROR: $error_type - $error_msg" >&2
      echo "❌ Expected key: $expected_key" >&2
      return 2
    else
      echo "⚠️  API ERROR (retryable): $error_type - $error_msg" >&2
      return 1
    fi
  fi

  local text
  text=$(echo "$raw_response" | jq -r '.content[0].text // empty')

  if [[ -z "$text" ]]; then
    # Try OpenAI response format
    text=$(echo "$raw_response" | jq -r '.choices[0].message.content // empty')
    if [[ -z "$text" ]]; then
      echo "❌ API response missing text content" >&2
      return 1
    fi
  fi

  echo "$text"
}

# ============================================================
# FUNCTION: is_fatal_api_error
# Purpose: Determine if API error is fatal (no retry) or transient
# Args:
#   $1 - error type string from API response
# Returns: 0 if fatal, 1 if retryable
# ============================================================
is_fatal_api_error() {
  local error_type="$1"
  case "$error_type" in
    authentication_error|permission_error|invalid_request_error)
      return 0  # Fatal — do not retry
      ;;
    *)
      return 1  # Retryable (rate limit, overload, etc.)
      ;;
  esac
}

# ============================================================
# FUNCTION: check_token_usage
# Purpose: Warn if response is near token limit (possible truncation)
# Args:
#   $1 - raw API response JSON
#   $2 - max_tokens limit used in the call
# Returns: nothing, prints warning to stderr if near limit
# ============================================================
check_token_usage() {
  local response="$1"
  local max_tokens="$2"

  local output_tokens
  output_tokens=$(echo "$response" | jq -r '.usage.output_tokens // .usage.completion_tokens // 0')

  echo "🔍 Token usage: $output_tokens / $max_tokens"

  if (( output_tokens >= max_tokens - 100 )); then
    echo "⚠️  WARNING: Response near token limit, may be truncated" >&2
  fi
}

# ============================================================
# FUNCTION: log_cost_estimate
# Purpose: Print tokens + cost estimate for a response
# Args:
#   $1 - raw API response JSON
#   $2 - provider ("claude" or "chatgpt")
# Returns: nothing
# ============================================================
log_cost_estimate() {
  local response="$1"
  local provider="$2"

  local in_tokens out_tokens
  if [[ "$provider" == "claude" ]]; then
    in_tokens=$(echo "$response" | jq -r '.usage.input_tokens // 0')
    out_tokens=$(echo "$response" | jq -r '.usage.output_tokens // 0')
    local in_cost out_cost total
    in_cost=$(python - <<PY
print(f"{float($in_tokens) * $CLAUDE_INPUT_PER_MTOK / 1_000_000:.4f}")
PY
)
    out_cost=$(python - <<PY
print(f"{float($out_tokens) * $CLAUDE_OUTPUT_PER_MTOK / 1_000_000:.4f}")
PY
)
    total=$(python - <<PY
print(f"{float($in_cost) + float($out_cost):.4f}")
PY
)
    echo "💰 Claude cost estimate: \$$total (in: $in_tokens, out: $out_tokens)"
  else
    in_tokens=$(echo "$response" | jq -r '.usage.prompt_tokens // 0')
    out_tokens=$(echo "$response" | jq -r '.usage.completion_tokens // 0')
    local in_cost out_cost total
    in_cost=$(python - <<PY
print(f"{float($in_tokens) * $OPENAI_INPUT_PER_MTOK / 1_000_000:.4f}")
PY
)
    out_cost=$(python - <<PY
print(f"{float($out_tokens) * $OPENAI_OUTPUT_PER_MTOK / 1_000_000:.4f}")
PY
)
    total=$(python - <<PY
print(f"{float($in_cost) + float($out_cost):.4f}")
PY
)
    echo "💰 ChatGPT cost estimate: \$$total (in: $in_tokens, out: $out_tokens)"
  fi
}

# ============================================================
# FUNCTION: generate_idea
# Purpose: Generate a single startup idea using creative directive
#          Only called in generate mode (temp=1 for creativity)
# Args: none
# Returns: "startup_idea_id|name|description" via stdout
# ============================================================
generate_idea() {
  local idea_prompt
  idea_prompt=$(cat "$IDEA_DIRECTIVE")

  local provider
  provider=$(select_provider "$IDEA_DIRECTIVE")

  local attempt
  for attempt in {1..3}; do
    local raw_response
    if [[ "$provider" == "claude" ]]; then
      raw_response=$(call_claude "$idea_prompt" 500 1)
    else
      raw_response=$(call_chatgpt "$idea_prompt" 500 1)
    fi
    log_cost_estimate "$raw_response" "$provider"

    local text
    text=$(extract_text_or_fail "$raw_response" "$provider")
    rc=$?
    if [[ "$rc" -ne 0 ]]; then
      if [[ "$rc" -eq 2 ]]; then
        echo "❌ Fatal error — aborting run" >&2
        exit 1
      fi
      echo "  ⚠️  Attempt $attempt/3 failed for idea generation" >&2
      sleep 2
      continue
    fi

    # Extract content between markers
    local idea
    idea=$(echo "$text" | sed -n '/<<<BEGIN_IDEA>>>/,/<<<END_IDEA>>>/p' | grep -v '<<<' | head -1)

    if [[ -z "$idea" ]]; then
      echo "  ⚠️  Attempt $attempt/3: No idea found between markers" >&2
      sleep 2
      continue
    fi

    # Validate format: id|name|description (exactly 3 pipe-delimited fields)
    local field_count
    field_count=$(echo "$idea" | awk -F'|' '{print NF}')

    if [[ "$field_count" -ne 3 ]]; then
      echo "  ⚠️  Attempt $attempt/3: Invalid idea format (expected 3 fields, got $field_count)" >&2
      sleep 2
      continue
    fi

    # Success
    echo "$idea"
    return 0
  done

  echo "❌ Failed to generate idea after 3 attempts" >&2
  return 1
}

# ============================================================
# FUNCTION: extract_json_block
# Purpose: Extract JSON between BEGIN_JSON and END_JSON markers
#          from a file containing model response text
# Args:
#   $1 - file path containing response text
# Returns: extracted JSON via stdout
# ============================================================
extract_json_block() {
  local file="$1"
  sed -n '/<<<BEGIN_JSON>>>/,/<<<END_JSON>>>/p' "$file" | grep -v '<<<'
}

# ============================================================
# FUNCTION: validate_root_shape
# Purpose: Verify JSON has all required root-level fields
# Args:
#   $1 - JSON file path
# Returns: 0 if valid, 1 if any required field is missing
# ============================================================
validate_root_shape() {
  local json_file="$1"

  local has_block_id has_startup_id has_pass1 has_pass6
  has_block_id=$(jq 'has("block_id")' "$json_file")
  has_startup_id=$(jq 'has("startup_idea_id")' "$json_file")
  has_pass1=$(jq 'has("pass_1")' "$json_file")
  has_pass6=$(jq 'has("pass_6")' "$json_file")

  if [[ "$has_block_id" == "true" && "$has_startup_id" == "true" &&
        "$has_pass1" == "true" && "$has_pass6" == "true" ]]; then
    return 0
  else
    echo "  ❌ Missing required root fields (block_id, startup_idea_id, pass_1, pass_6)" >&2
    return 1
  fi
}

# ============================================================
# FUNCTION: validate_block_id
# Purpose: Verify block_id in JSON matches expected value
# Args:
#   $1 - JSON file path
#   $2 - expected block_id ("A" or "B")
# Returns: 0 if match, 1 if mismatch
# ============================================================
validate_block_id() {
  local json_file="$1"
  local expected="$2"

  local actual
  actual=$(jq -r '.block_id' "$json_file")

  if [[ "$actual" == "$expected" ]]; then
    return 0
  else
    echo "  ❌ block_id mismatch: expected '$expected', got '$actual'" >&2
    return 1
  fi
}

# ============================================================
# FUNCTION: reject_if_wrapped
# Purpose: Fail if JSON is wrapped in extra container objects
#          (model should return flat block, not nested)
# Args:
#   $1 - JSON file path
# Returns: 0 if clean flat JSON, 1 if wrapped
# ============================================================
reject_if_wrapped() {
  local json_file="$1"

  if jq -e 'has("block_a") or has("block_b") or has("run_id")' "$json_file" >/dev/null 2>&1; then
    echo "  ❌ JSON wrapped in block_a/block_b/run_id (model returned invalid container)" >&2
    return 1
  fi

  return 0
}

# ============================================================
# FUNCTION: run_block
# Purpose: Execute one block (A or B) with validation and retry
#
# In hero mode:  mode_payload is the raw hero_answers JSON block
# In generate mode: mode_payload is the startup_description string
#
# Args:
#   $1 - block_id ("A" or "B")
#   $2 - startup_idea_id
#   $3 - startup_name
#   $4 - mode_payload (hero_answers JSON string OR description string)
#   $5 - source_mode ("hero" or "generate")
# Returns: creates block_{a|b}.json in current run directory
# ============================================================
run_block() {
  local block_id="$1"
  local startup_id="$2"
  local startup_name="$3"
  local mode_payload="$4"
  local source_mode="$5"

  local base_bundle
  base_bundle=$(build_base_bundle)

  # Build mode instruction — hero mode injects full hero_answers JSON,
  # generate mode injects the description string as before
  local mode_instruction
  if [[ "$block_id" == "A" ]]; then
    if [[ "$source_mode" == "hero" ]]; then
      mode_instruction="MODE A — BLOCK A
Generate a NEW startup analysis with these details:
- startup_idea_id: $startup_id
- startup_name: $startup_name
- block_id = \"A\"
- Tier 1 ONLY

Hero answers (use these as the authoritative source for all pass analysis):
$mode_payload"
    else
      mode_instruction="MODE A — BLOCK A
Generate a NEW startup idea with these details:
- startup_idea_id: $startup_id
- startup_name: $startup_name
- startup_description: $mode_payload
- block_id = \"A\"
- Tier 1 ONLY"
    fi
  else
    if [[ "$source_mode" == "hero" ]]; then
      mode_instruction="MODE B — BLOCK B
Expand the SAME startup analysis:
- startup_idea_id: $startup_id (MUST MATCH)
- startup_name: $startup_name
- block_id = \"B\"
- Tier 2 ONLY

Hero answers (use these as the authoritative source for all pass analysis):
$mode_payload"
    else
      mode_instruction="MODE B — BLOCK B
Expand the SAME startup idea:
- startup_idea_id: $startup_id (MUST MATCH)
- startup_name: $startup_name
- startup_description: $mode_payload
- block_id = \"B\"
- Tier 2 ONLY"
    fi
  fi

  local full_directive
  full_directive=$(cat "$PASS_DIRECTIVE")

  local prompt="${base_bundle}

${full_directive}

${mode_instruction}"

  local provider
  provider=$(select_provider "$PASS_DIRECTIVE")

  local attempt
  for attempt in {1..5}; do
    echo "  ▶ Attempt $attempt/5 for block $block_id"

    local raw_response
    if [[ "$provider" == "claude" ]]; then
      raw_response=$(call_claude "$prompt" 4096 0)
    else
      raw_response=$(call_chatgpt "$prompt" 4096 0)
    fi
    log_cost_estimate "$raw_response" "$provider"

    check_token_usage "$raw_response" 4096

    local text
    text=$(extract_text_or_fail "$raw_response" "$provider")
    rc=$?
    if [[ "$rc" -ne 0 ]]; then
      if [[ "$rc" -eq 2 ]]; then
        echo "❌ Fatal error — aborting run" >&2
        exit 1
      fi
      sleep 2
      continue
    fi

    local temp_file="temp_block_${block_id}.txt"
    echo "$text" > "$temp_file"

    local json_file="block_$(echo "$block_id" | tr '[:upper:]' '[:lower:]').json"
    extract_json_block "$temp_file" > "$json_file"

    if ! jq empty "$json_file" >/dev/null 2>&1; then
      echo "  ❌ Attempt $attempt: Invalid JSON syntax" >&2
      rm -f "$temp_file" "$json_file"
      sleep 2
      continue
    fi

    if ! validate_root_shape "$json_file"; then
      rm -f "$temp_file" "$json_file"
      sleep 2
      continue
    fi

    if ! validate_block_id "$json_file" "$block_id"; then
      rm -f "$temp_file" "$json_file"
      sleep 2
      continue
    fi

    if ! reject_if_wrapped "$json_file"; then
      rm -f "$temp_file" "$json_file"
      sleep 2
      continue
    fi

    if ! grep -q '<<<END OF BLOCK>>>' "$temp_file"; then
      echo "  ⚠️  Missing <<<END OF BLOCK>>> marker" >&2
    fi

    rm -f "$temp_file"
    echo "  ✅ Valid block $block_id"
    return 0
  done

  echo "❌ Block $block_id failed after 5 attempts" >&2
  return 1
}

# ============================================================
# FUNCTION: finalize_run
# Purpose: Write .txt summary and combined JSON after both blocks
# Args:
#   $1 - run_dir (absolute path)
#   $2 - run_id
#   $3 - startup_id
#   $4 - startup_name
#   $5 - summary_line (one-line description for .txt file)
# Returns: creates {startup_id}.txt and {startup_id}.json in run_dir
# ============================================================
finalize_run() {
  local run_dir="$1"
  local run_id="$2"
  local startup_id="$3"
  local startup_name="$4"
  local summary_line="$5"

  # Write one-line summary file
  local idea_file="$run_dir/${startup_id}.txt"
  echo "$summary_line" > "$idea_file"
  echo "📄 Created: ${startup_id}.txt"

  # Merge block_a and block_b into single combined JSON
  local combined_json="$run_dir/${startup_id}.json"

  jq -n \
    --arg run_id "$run_id" \
    --arg startup_idea_id "$startup_id" \
    --arg startup_name "$startup_name" \
    --arg summary "$summary_line" \
    --slurpfile a "$run_dir/block_a.json" \
    --slurpfile b "$run_dir/block_b.json" \
    '{
      run_id: $run_id,
      startup_idea_id: $startup_idea_id,
      startup_name: $startup_name,
      summary: $summary,
      block_a: $a[0],
      block_b: $b[0]
    }' > "$combined_json"

  if ! jq empty "$combined_json" >/dev/null 2>&1; then
    echo "❌ Invalid combined JSON — merge failed" >&2
    return 1
  fi

  echo "📦 Created: ${startup_id}.json"
  return 0
}

# ============================================================
# HERO MODE EXECUTION
# Single run — identity sourced from hero.json file
# run_id = startup_idea_id from hero file
# mode_payload = full hero_answers block as raw JSON
# ============================================================

if [[ "$MODE" == "hero" ]]; then

  # Validate hero file has required fields
  STARTUP_ID=$(jq -r '.startup_idea_id // empty' "$HERO_FILE")
  STARTUP_NAME=$(jq -r '.startup_name // empty' "$HERO_FILE")
  HERO_ANSWERS=$(jq '.hero_answers' "$HERO_FILE")

  if [[ -z "$STARTUP_ID" ]]; then
    echo "❌ Hero file missing: startup_idea_id"
    exit 1
  fi

  if [[ -z "$STARTUP_NAME" ]]; then
    echo "❌ Hero file missing: startup_name"
    exit 1
  fi

  if [[ "$HERO_ANSWERS" == "null" || -z "$HERO_ANSWERS" ]]; then
    echo "❌ Hero file missing: hero_answers block"
    exit 1
  fi

  # run_id = startup_idea_id in hero mode
  RUN_ID="$STARTUP_ID"
  RUN_DIR="$OUT_DIR_ABS/$RUN_ID"
  mkdir -p "$RUN_DIR"
  cd "$RUN_DIR"

  echo "============================================================"
  echo "🦸 HERO MODE"
  echo "ID:        $STARTUP_ID"
  echo "Name:      $STARTUP_NAME"
  echo "Run ID:    $RUN_ID"
  echo "Directory: $RUN_DIR"
  echo "============================================================"
  echo

  # Block A
  echo "⚙️  Running Block A (Tier 1)..."
  if ! run_block "A" "$STARTUP_ID" "$STARTUP_NAME" "$HERO_ANSWERS" "hero"; then
    echo "❌ HERO RUN FAILED: Block A failed"
    exit 1
  fi

  # Block B
  echo "⚙️  Running Block B (Tier 2)..."
  if ! run_block "B" "$STARTUP_ID" "$STARTUP_NAME" "$HERO_ANSWERS" "hero"; then
    echo "❌ HERO RUN FAILED: Block B failed"
    exit 1
  fi

  # Build summary line from hero file fields
  STARTUP_DESC=$(jq -r '.startup_description // ""' "$HERO_FILE")
  SUMMARY_LINE="$STARTUP_NAME - $STARTUP_DESC"

  # Finalize: write .txt and combined JSON
  cd - >/dev/null
  if ! finalize_run "$RUN_DIR" "$RUN_ID" "$STARTUP_ID" "$STARTUP_NAME" "$SUMMARY_LINE"; then
    echo "❌ HERO RUN FAILED: Finalization failed"
    exit 1
  fi

  echo
  echo "============================================"
  echo "✅ HERO RUN COMPLETE"
  echo "Output: $RUN_DIR/"
  echo "  block_a.json           → Tier 1 passes"
  echo "  block_b.json           → Tier 2 passes"
  echo "  ${STARTUP_ID}.txt      → Summary"
  echo "  ${STARTUP_ID}.json     → Combined blocks"
  echo "============================================"
  exit 0
fi

# ============================================================
# GENERATE MODE EXECUTION
# Loops N times — identity sourced from generate_idea()
# run_id = run_N (loop counter)
# mode_payload = startup_description string
# ============================================================

echo "[INFO] Runs: $RUNS"
echo "[INFO] Pass directive: $PASS_DIRECTIVE"
echo "[INFO] Idea directive: $IDEA_DIRECTIVE"
echo "[INFO] Idea generation: temp=1"
echo "[INFO] Pass execution:  temp=0"
echo

for i in $(seq 1 "$RUNS"); do
  echo
  echo "================ RUN $i / $RUNS ================"

  RUN_ID="run_$i"
  RUN_DIR="$OUT_DIR_ABS/$RUN_ID"
  mkdir -p "$RUN_DIR"
  cd "$RUN_DIR"

  # ----------------------------------------------------------
  # STEP 1: Generate startup idea (temp=1, creative)
  # ----------------------------------------------------------

  echo "🎲 Generating startup idea..."

  IDEA_OUTPUT=$(generate_idea)

  if [[ -z "$IDEA_OUTPUT" ]]; then
    echo "❌ RUN $i FAILED: Idea generation failed"
    FAILED_RUNS=$((FAILED_RUNS+1))
    cd - >/dev/null
    continue
  fi

  STARTUP_ID=$(echo "$IDEA_OUTPUT" | cut -d'|' -f1)
  STARTUP_NAME=$(echo "$IDEA_OUTPUT" | cut -d'|' -f2)
  STARTUP_DESC=$(echo "$IDEA_OUTPUT" | cut -d'|' -f3)

  echo "💡 Idea: $STARTUP_ID - $STARTUP_NAME"

  # ----------------------------------------------------------
  # STEP 2: Run Block A (temp=0, Tier 1)
  # ----------------------------------------------------------

  echo "⚙️  Running Block A (Tier 1)..."

  if ! run_block "A" "$STARTUP_ID" "$STARTUP_NAME" "$STARTUP_DESC" "generate"; then
    echo "❌ RUN $i FAILED: Block A failed"
    FAILED_RUNS=$((FAILED_RUNS+1))
    cd - >/dev/null
    continue
  fi

  # ----------------------------------------------------------
  # STEP 3: Run Block B (temp=0, Tier 2, SAME idea)
  # ----------------------------------------------------------

  echo "⚙️  Running Block B (Tier 2)..."

  if ! run_block "B" "$STARTUP_ID" "$STARTUP_NAME" "$STARTUP_DESC" "generate"; then
    echo "❌ RUN $i FAILED: Block B failed"
    FAILED_RUNS=$((FAILED_RUNS+1))
    cd - >/dev/null
    continue
  fi

  # ----------------------------------------------------------
  # STEP 4 + 5: Finalize — .txt summary and combined JSON
  # ----------------------------------------------------------

  SUMMARY_LINE="$STARTUP_NAME - $STARTUP_DESC"

  cd - >/dev/null

  if ! finalize_run "$RUN_DIR" "$RUN_ID" "$STARTUP_ID" "$STARTUP_NAME" "$SUMMARY_LINE"; then
    echo "❌ RUN $i FAILED: Finalization failed"
    FAILED_RUNS=$((FAILED_RUNS+1))
    continue
  fi

  SUCCESSFUL_RUNS=$((SUCCESSFUL_RUNS+1))
  echo "✅ RUN $i COMPLETE"
done

echo
echo "============================================"
echo "ALL RUNS COMPLETE"
echo "Successful: $SUCCESSFUL_RUNS / $RUNS"
echo "Failed:     $FAILED_RUNS / $RUNS"
echo "============================================"
echo
echo "OUTPUT: $OUT_DIR_ABS/"
echo "  run_N/block_a.json       → Tier 1 passes"
echo "  run_N/block_b.json       → Tier 2 passes"
echo "  run_N/{startup_id}.txt   → One-line summary"
echo "  run_N/{startup_id}.json  → Both blocks merged"
echo "============================================"

exit 0
