# FO Test Harness - BUILD → QA → DEPLOY Orchestration

**Production-ready test harness** that orchestrates Claude (tech/builder) and ChatGPT (QA/validator) to build and deploy businesses automatically.

---

## Features

✅ **Automated BUILD → QA Loop**
- Claude builds according to FO Build Governance
- ChatGPT validates against intake requirements
- Automatically iterates until no defects (max 5 iterations)
- All artifacts and QA reports saved

✅ **Smart Defect Handling**
- ChatGPT classifies defects (IMPLEMENTATION_BUG, SPEC_COMPLIANCE_ISSUE, SCOPE_CHANGE_REQUEST)
- Claude fixes defects in next iteration
- Loop continues until QA accepts

✅ **Full Deployment Pipeline**
- After QA acceptance, automatically deploys
- Uses FO Deploy Governance for validation
- Supports POC and PRODUCTION environments

✅ **Complete Artifact Tracking**
- All BUILD outputs saved (by iteration)
- All QA reports saved (by iteration)
- All prompts logged
- Artifact manifest with SHA256 checksums
- Organized directory structure

---

## Installation

### 1. Install Dependencies

```bash
pip install requests
```

### 2. Set Environment Variables

```bash
# API Keys (required)
export ANTHROPIC_API_KEY='your-anthropic-key-here'
export OPENAI_API_KEY='your-openai-key-here'

# Governance Files (optional - defaults can be set in script)
export BUILD_GOVERNANCE_ZIP='/path/to/FOBUILFINALLOCKED100.zip'
export DEPLOY_GOVERNANCE_ZIP='/path/to/fo_deploy_governance_v1_2_CLARIFIED.zip'
```

### 3. Make Executable

```bash
chmod +x fo_test_harness.py
```

---

## Usage

### Basic Usage

```bash
./fo_test_harness.py <intake_file> <block>
```

**Arguments:**
- `intake_file`: Path to MCv6-SCHEMA v21.4 JSON file
- `block`: Which block to build (A or B)

### Examples

**Build Block A (Tier 1) for InboxTamer:**
```bash
./fo_test_harness.py inboxtamer_intake.json A
```

**Build Block B (Tier 2) for Watercooler:**
```bash
./fo_test_harness.py iteration_9.json B
```

**Build Block A, skip deployment:**
```bash
./fo_test_harness.py inboxtamer_intake.json A --skip-deploy
```

**Deploy to PRODUCTION:**
```bash
./fo_test_harness.py inboxtamer_intake.json A --environment PRODUCTION
```

---

## How It Works

### Pipeline Flow

```
START
  ↓
ITERATION 1:
  ├─→ Claude: BUILD (reads governance, generates code)
  ├─→ Save: build_output.txt
  ├─→ ChatGPT: QA (validates against intake)
  ├─→ Save: qa_report.txt
  └─→ Check: Defects found?
        ├─ NO → Continue to DEPLOY
        └─ YES → Go to ITERATION 2

ITERATION 2 (if defects):
  ├─→ Claude: BUILD + FIX (fixes defects from QA)
  ├─→ Save: build_output.txt, fix.txt
  ├─→ ChatGPT: QA (re-validate)
  ├─→ Save: qa_report.txt
  └─→ Check: Defects found?
        ├─ NO → Continue to DEPLOY
        └─ YES → Go to ITERATION 3

[Continues up to 5 iterations]

DEPLOY:
  ├─→ Claude: DEPLOY (validates artifacts, deploys to environment)
  ├─→ Save: deploy_output.txt
  └─→ Generate: artifact_manifest.json

SUCCESS ✓
```

---

## Output Structure

Each run creates a timestamped directory:

```
./fo_harness_runs/
└── inboxtamer_BLOCK_A_20250119_143022/
    ├── build/
    │   ├── iteration_01_build.txt
    │   ├── iteration_02_build.txt
    │   ├── iteration_02_fix.txt
    │   └── code/
    │       ├── index.js
    │       ├── package.json
    │       └── README.md
    ├── qa/
    │   ├── iteration_01_qa_report.txt
    │   └── iteration_02_qa_report.txt
    ├── deploy/
    │   └── deploy_output.txt
    ├── logs/
    │   ├── iteration_01_build_prompt.log
    │   ├── iteration_01_qa_prompt.log
    │   ├── iteration_02_build_prompt.log
    │   ├── iteration_02_qa_prompt.log
    │   └── deploy_prompt.log
    └── artifact_manifest.json
```

---

## Configuration

### In-Script Configuration

Edit `fo_test_harness.py` to configure:

```python
class Config:
    # Models
    CLAUDE_MODEL = 'claude-sonnet-4-20250514'  # Tech/Builder
    GPT_MODEL = 'gpt-4o'  # QA/Validator
    
    # Token Limits
    CLAUDE_MAX_TOKENS = 200000  # Prevent truncation
    GPT_MAX_TOKENS = 16000
    
    # Iteration Limits
    MAX_QA_ITERATIONS = 5  # Max BUILD → QA cycles
    
    # Governance Files
    BUILD_GOVERNANCE_ZIP = '/path/to/FOBUILFINALLOCKED100.zip'
    DEPLOY_GOVERNANCE_ZIP = '/path/to/fo_deploy_governance_v1_2_CLARIFIED.zip'
```

---

## Cost Estimation

### Per Business (Block A - Tier 1)

**BUILD Phase:**
- Iteration 1: ~$0.80 (Claude generates code)
- Iteration 2 (if needed): ~$0.60 (Claude fixes defects)
- Average: **$1.00** (1-2 iterations typical)

**QA Phase:**
- Iteration 1: ~$0.15 (ChatGPT validates)
- Iteration 2 (if needed): ~$0.15
- Average: **$0.20** (1-2 iterations typical)

**DEPLOY Phase:**
- Deployment: ~$0.40 (Claude deploys)

**Total per business (T1):** **~$1.60**

### Per Business (Block B - Tier 2)

**BUILD Phase:** ~$1.80 (more complex code)
**QA Phase:** ~$0.30 (more validation)
**DEPLOY Phase:** ~$0.50 (more complex deployment)

**Total per business (T2):** **~$2.60**

### For 25 Businesses

**If all T2:** 25 × $2.60 = **$65**

---

## QA Report Format

ChatGPT generates structured QA reports:

```
## QA REPORT

### SUMMARY
- Total defects found: 2
- IMPLEMENTATION_BUG: 1
- SPEC_COMPLIANCE_ISSUE: 1
- SCOPE_CHANGE_REQUEST: 0

### DEFECTS

DEFECT-001: IMPLEMENTATION_BUG
  - Location: api/login.js:15
  - Problem: Password validation missing
  - Expected: Validate password length (min 8 chars)
  - Severity: HIGH

DEFECT-002: SPEC_COMPLIANCE_ISSUE
  - Location: README.md
  - Problem: Setup instructions incomplete
  - Expected: Include database migration steps
  - Severity: MEDIUM

### VERDICT
QA STATUS: REJECTED - 2 defects require fixing
```

---

## Typical Execution

```bash
$ ./fo_test_harness.py iteration_9.json A

======================================================================
FO HARNESS INITIALIZED
======================================================================

→ Startup: remote-team-watercooler
→ Block: BLOCK_A
→ Run directory: ./fo_harness_runs/remote-team-watercooler_BLOCK_A_20250119_143022

======================================================================
STARTING BUILD → QA LOOP (BLOCK_A)
======================================================================

======================================================================
ITERATION 1/5
======================================================================

→ Calling Claude for BUILD...
✓ BUILD completed in 47.3s
✓ Saved BUILD output: build/iteration_01_build.txt

→ Calling ChatGPT for QA...
✓ QA completed in 12.1s
✓ Saved QA report: qa/iteration_01_qa_report.txt

⚠ QA REJECTED - defects found
⚠   → 2 defects to fix
→ Starting iteration 2 with defect fixes...

======================================================================
ITERATION 2/5
======================================================================

→ Calling Claude for BUILD...
✓ BUILD completed in 38.7s
✓ Saved BUILD output: build/iteration_02_build.txt
✓ Saved defect fix: build/iteration_02_fix.txt

→ Calling ChatGPT for QA...
✓ QA completed in 11.4s
✓ Saved QA report: qa/iteration_02_qa_report.txt

✓ QA ACCEPTED on iteration 2
✓ BUILD → QA loop complete - no defects

✓ Generated artifact manifest: artifact_manifest.json

======================================================================
STARTING DEPLOYMENT (POC)
======================================================================

→ Calling Claude for DEPLOYMENT...
✓ DEPLOY completed in 15.2s
✓ Saved DEPLOY output: deploy/deploy_output.txt

✓ DEPLOYMENT SUCCESSFUL

======================================================================
EXECUTION SUMMARY
======================================================================

Startup:        remote-team-watercooler
Block:          BLOCK_A
Status:         ✓ SUCCESS
Total time:     124.7s (2.1 minutes)
Deployed:       Yes

Output directory: ./fo_harness_runs/remote-team-watercooler_BLOCK_A_20250119_143022

Generated files:
  - BUILD outputs:   5
  - QA reports:      2
  - DEPLOY outputs:  1
  - Logs:            5

✓ PIPELINE COMPLETED SUCCESSFULLY
```

---

## Error Handling

### If BUILD → QA Loop Fails to Converge

After 5 iterations, if QA still finds defects:

```bash
✗ Max iterations (5) reached
✗ BUILD → QA loop failed to converge

======================================================================
EXECUTION SUMMARY
======================================================================

Status:         ✗ FAILED
```

**What to do:**
1. Review QA reports in `qa/` directory
2. Check if defects are scope changes (may need new intake)
3. Manual intervention may be required

### If Deployment Fails

```bash
✗ DEPLOYMENT FAILED

Status:         ✗ FAILED
```

**What to do:**
1. Review `deploy/deploy_output.txt`
2. Check artifact validation issues
3. Verify environment configuration
4. May need manual deployment

---

## Advanced Usage

### Run Multiple Businesses

```bash
# Build all 25 businesses automatically
for intake in intakes/*.json; do
  ./fo_test_harness.py "$intake" A
  ./fo_test_harness.py "$intake" B
done
```

### Parallel Execution

```bash
# Build 5 businesses in parallel
for intake in intakes/business_{1..5}.json; do
  ./fo_test_harness.py "$intake" A &
done
wait
```

### Custom QA Iterations

Edit script to change max iterations:

```python
class Config:
    MAX_QA_ITERATIONS = 10  # Allow more fix attempts
```

---

## Troubleshooting

### "ANTHROPIC_API_KEY not set"

```bash
export ANTHROPIC_API_KEY='sk-ant-...'
```

### "OPENAI_API_KEY not set"

```bash
export OPENAI_API_KEY='sk-...'
```

### "Could not parse intake JSON"

Ensure intake file is valid MCv6-SCHEMA v21.4 format:

```json
{
  "startup_idea_id": "my-business",
  "block_a": {
    "pass1_output": { ... },
    "pass2_output": { ... },
    ...
  }
}
```

### Claude/ChatGPT API Errors

Check:
- API keys are valid
- You have API credits
- No rate limiting (wait and retry)

---

## Limitations

1. **Max 5 QA iterations** - After 5 cycles, manual intervention required
2. **No parallel QA** - Claude and ChatGPT called sequentially
3. **Token limits** - Very large codebases may hit limits
4. **Network dependency** - Requires internet for API calls

---

## Future Enhancements

- [ ] Parallel BUILD+QA for multiple businesses
- [ ] Resume from checkpoint (if interrupted)
- [ ] Cost tracking per run
- [ ] Slack/email notifications on completion
- [ ] Web dashboard for monitoring
- [ ] Automatic retry on transient failures

---

## License

MIT

---

## Support

For issues or questions:
1. Check `logs/` directory for detailed execution logs
2. Review QA reports in `qa/` directory
3. Check BUILD outputs in `build/` directory

---

**Built for the AutoFounder hermit empire.** 🏔️

No humans required.
