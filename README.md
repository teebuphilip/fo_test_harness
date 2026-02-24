# FO Test Harness

Complete pipeline for testing FounderOps BUILD → QA → DEPLOY workflow.

## Directory Structure

```
FO_TEST_HARNESS/
├── fo_test_harness.py          # Main BUILD + QA + DEPLOY orchestrator
├── intake/                      # INTAKE generation (Step 1)
│   ├── run_intake_v7.sh        # Intake generator script
│   ├── generate_intake.sh      # Simplified wrapper
│   ├── README.md               # Intake documentation
│   ├── hero_text/              # Founder answer files
│   ├── inputs/                 # Schemas, policies, rules
│   └── intake_runs/            # Generated intakes (output)
├── fo_harness_runs/            # BUILD outputs (Step 2)
│   └── <startup_id>_BLOCK_B_<timestamp>/
│       ├── build/              # All build iterations
│       ├── qa/                 # QA reports
│       ├── deploy/             # Deployment artifacts
│       └── logs/               # Prompts and debug info
├── fo_external_integration_override.json  # External service policy
├── fo_tech_stack_override.json           # Tech stack overrides
└── README.md                   # This file
```

## Quick Start

### Full Pipeline (Intake → Build → QA)

```bash
# Step 1: Generate intake
cd intake
./generate_intake.sh twofacedai.json

# Step 2: Run build harness
cd ..
python fo_test_harness.py \
  --intake intake/intake_runs/twofaced_ai/twofaced_ai.json \
  --startup-id twofaced_ai \
  --block B \
  --build-gov /tmp/fobuilgov100 \
  --tech-stack lowcode

# Step 3: Check results
open fo_harness_runs/twofaced_ai_BLOCK_B_*/
```

### Just Build Harness (Existing Intake)

If you already have an intake JSON:

```bash
python fo_test_harness.py \
  --intake path/to/intake.json \
  --startup-id your_startup \
  --block B \
  --build-gov /tmp/fobuilgov100 \
  --tech-stack lowcode
```

## Prerequisites

1. **Python 3.8+** with packages:
   ```bash
   pip install anthropic openai requests
   ```

2. **API Keys**:
   ```bash
   export ANTHROPIC_API_KEY=sk-ant-xxxxx
   export OPENAI_API_KEY=sk-xxxxx
   ```

3. **Governance ZIP**: Extract to `/tmp/fobuilgov100/`
   ```bash
   unzip fobuilgov100.zip -d /tmp/fobuilgov100/
   ```

4. **Boilerplate** (for lowcode): Place at `~/Downloads/teebu-saas-platform/`

## Workflow

### 1. Generate Intake (Tier Evaluation)

```bash
cd intake
./generate_intake.sh twofacedai.json
```

**Output:** `intake/intake_runs/twofaced_ai/twofaced_ai.json`

This evaluates the founder's answers against tier criteria and produces:
- `block_a.json` - Tier 1 evaluation
- `block_b.json` - Tier 2 evaluation
- `<startup_id>.json` - Combined intake

### 2. Run Build Harness (BUILD + QA Loop)

```bash
python fo_test_harness.py \
  --intake intake/intake_runs/twofaced_ai/twofaced_ai.json \
  --startup-id twofaced_ai \
  --block B \
  --build-gov /tmp/fobuilgov100 \
  --tech-stack lowcode
```

**What happens:**
1. Claude BUILD generates code from intake
2. ChatGPT QA evaluates code for defects
3. Loop continues until QA accepts or max iterations hit
4. Final ZIP created with all artifacts

**Output:** `fo_harness_runs/twofaced_ai_BLOCK_B_<timestamp>.zip`

### 3. Review Results

```bash
# Unzip the final output
unzip fo_harness_runs/twofaced_ai_*.zip

# Check QA reports
cat fo_harness_runs/twofaced_ai_*/qa/iteration_*_qa_report.txt

# Check build artifacts
ls fo_harness_runs/twofaced_ai_*/build/iteration_*_artifacts/
```

## Configuration

### Token Limits

**Current:** 16384 tokens (increased from 8192)

Located in `fo_test_harness.py`:
```python
CLAUDE_MAX_TOKENS = 16384  # Handles complex builds
```

### Tech Stack Overrides

Edit `fo_tech_stack_override.json` to change default tech stacks:
```json
{
  "default_tech_stack_tier_1": "Next.js 14, React 18, Tailwind CSS",
  "default_tech_stack_tier_2": "Next.js + Prisma + PostgreSQL"
}
```

### External Integration Policy

Edit `fo_external_integration_override.json` to control how external services are handled:
```json
{
  "rules": {
    "if_provider_specified": "use_specified_provider_with_placeholder_config"
  }
}
```

## Troubleshooting

### Build Output Truncated

**Symptoms:** Missing artifact_manifest.json, build_state.json

**Solution:** Already fixed! Token limit increased to 16384.

If still seeing issues, check:
```bash
grep "BUILD OUTPUT TRUNCATED" fo_harness_runs/*/logs/*.log
```

### QA Loop Not Converging

**Symptoms:** 10+ iterations without acceptance

**Check QA reports:**
```bash
cat fo_harness_runs/*/qa/iteration_*_qa_report.txt
```

Common causes:
- Vague intake (add more detail)
- Scope creep (QA rejecting reasonable implementation details)
- Bug ping-pong (fixing one issue introduces another)

**Solution:** The harness now has convergence detection and will stop after 15 iterations if not improving.

### Missing Boilerplate in ZIP

**Symptoms:** ZIP only has custom code, no boilerplate

**Solution:** Check boilerplate location:
```bash
ls ~/Downloads/teebu-saas-platform/
```

Should contain:
- `teebu-shared-libs/`
- `saas-boilerplate/`

## Cost Tracking

The harness tracks API costs for:
- Claude BUILD calls (Anthropic)
- ChatGPT QA calls (OpenAI)

Check costs in console output:
```
TOTAL COST (Claude + ChatGPT): $2.34
  → Claude: $1.89
  → ChatGPT: $0.45
```

## Advanced Usage

### Running Multiple Tests

```bash
# Generate multiple random intakes
cd intake
./generate_intake.sh 5

# Run harness on each
for run in intake_runs/run_*/; do
  id=$(basename "$run")
  python fo_test_harness.py \
    --intake "${run}${id}.json" \
    --startup-id "$id" \
    --block B \
    --build-gov /tmp/fobuilgov100 \
    --tech-stack lowcode
done
```

### Custom Governance

To test with custom governance rules:
```bash
python fo_test_harness.py \
  --intake intake/intake_runs/twofaced_ai/twofaced_ai.json \
  --startup-id twofaced_ai \
  --block B \
  --build-gov /path/to/custom/gov \
  --tech-stack custom
```

## Files Reference

| File | Purpose |
|------|---------|
| `fo_test_harness.py` | Main orchestrator (BUILD + QA + DEPLOY) |
| `intake/run_intake_v7.sh` | Intake generation script |
| `fo_external_integration_override.json` | External service integration rules |
| `fo_tech_stack_override.json` | Tech stack defaults |
| `check_boilerplate_fit.py` | Validates boilerplate compatibility |

## Documentation

- **Intake:** See `intake/README.md`
- **Build:** See inline comments in `fo_test_harness.py`
- **QA:** See governance ZIP for defect routing rules

## Support

For issues or questions, check:
1. Log files in `fo_harness_runs/*/logs/`
2. QA reports in `fo_harness_runs/*/qa/`
3. This README and `intake/README.md`
