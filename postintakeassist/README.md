# Post-Intake Assist v2.1

Deterministic validation + issue detection for Intake outputs (Block A + Block B), with optional AI revision responses.

## What It Does
- Validates Block A, Block B, and Build Contract schemas (basic required-field checks)
- Detects consistency and completeness issues using rules
- Emits a `build_contract` for downstream build/QA
- Optionally generates AI revision responses (`--use-ai`)

## Usage

### Deterministic Only (Default)
```bash
python postintakeassist/post_intake_assist.py input.json --out post_intake_out.json
```

### With AI Revision Responses
```bash
python postintakeassist/post_intake_assist.py input.json --use-ai --out post_intake_out.json
```

Optional provider:
```bash
python postintakeassist/post_intake_assist.py input.json --use-ai --provider claude --out post_intake_out.json
```

## Input Format
Input JSON must contain:
- `block_a_final`
- `block_b_final`

These should align to `BLOCK_A_SCHEMA.json` and `BLOCK_B_SCHEMA.json`.

## Output
```json
{
  "build_contract": { ... },
  "post_intake_report": {
    "status": "PASS | NEEDS_REVISION | REJECTED",
    "score": 0-100,
    "critical_issues": 0,
    "issues": [ ... ],
    "revision_requests": [ ... ],
    "ai_revision_responses": [ ... ]   // only with --use-ai
  }
}
```

## AI Cost Logging
When `--use-ai` is enabled, costs are logged to:
`postintakeassist/post_intake_ai_costs.csv`

Env overrides:
`OPENAI_INPUT_PER_MTOK`, `OPENAI_OUTPUT_PER_MTOK`, `ANTHROPIC_INPUT_PER_MTOK`, `ANTHROPIC_OUTPUT_PER_MTOK`

## Files
- `post_intake_assist.py` — main runner
- `post_intake_detection_rules.v2.1.json` — detection rules
- `post_intake_validation_rules.v2.1.json` — validation rules
- `post_intake_revision_templates.v2.1.json` — revision templates
- `post_intake_vocabulary.v2.1.json` — keyword lists
- `BUILD_CONTRACT_SCHEMA.json` — build contract schema
- `BLOCK_A_SCHEMA.json`, `BLOCK_B_SCHEMA.json` — intake schemas
