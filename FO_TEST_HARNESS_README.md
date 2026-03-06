# FO Test Harness v2 - BUILD → QA → ZIP/DEPLOY

Runs Claude (builder) and ChatGPT (QA checker) back-to-back to build a business automatically.
You give it a JSON file and two ZIP files. It does the rest.

**Default behavior: build, QA check, ZIP the output. Done. No deployment unless you ask for it.**

---

## What It Does

1. Claude reads your business intake file and builds everything (code, docs, configs)
2. ChatGPT checks Claude's work for bugs and missing pieces
3. If ChatGPT finds problems, Claude fixes them — up to 5 rounds
4. When ChatGPT says it's good, the output gets packaged into a ZIP file you can pick up

If you pass `--deploy`, it deploys instead of zipping. But you probably don't want that yet.

## Latest QA Hardening (2026-03-06)

- Auth0 hallucination filtering now handles paraphrased QA wording when evidence already shows
  correct `useAuth0()` + `getAccessTokenSilently` destructuring.
- Static Gate KPI check is intake-schema-agnostic (recursive KPI extraction from intake JSON).
- Static Gate download/export check is intake-schema-agnostic and verifies explicit backend route support.
- Gate execution order is now:
  - `GATE 0` compile
  - `GATE 2` static
  - `GATE 3` AI consistency
  - `GATE 4` quality (mandatory)
  - `GATE 1` feature QA

---

## What You Need Before Running

**Three files on your machine:**

1. Your intake JSON — the combined output from `run_intake_v7.sh`, looks like:
   ```
   intake_hero_runs/wynwood_thoroughbreds/wynwood_thoroughbreds.json
   ```

2. BUILD governance ZIP — your locked build rules:
   ```
   /Users/teebuphilip/Documents/work/FounderOps/docs/architecture/BUILD/build_rules/FOBUILFINALLOCKED100.zip
   ```

3. DEPLOY governance ZIP — your locked deploy rules:
   ```
   /Users/teebuphilip/Documents/work/FounderOps/docs/architecture/BUILD/deployment_rules/fo_deploy_governance_v1_2_CLARIFIED.zip
   ```

**Two API keys in your terminal session:**

```bash
export ANTHROPIC_API_KEY='sk-ant-your-key-here'
export OPENAI_API_KEY='sk-your-openai-key-here'
```

You only need to do this once per terminal session. If you close the terminal and reopen it, you need to set them again.

---

## Installation

### Step 1 — Install the one dependency

```bash
pip install requests
```

### Step 2 — Make the script executable

```bash
chmod +x fo_test_harness.py
```

That's it.

---

## Running It

### The command structure

```bash
./fo_test_harness.py <intake_json> <build_zip> <deploy_zip> [--block-a] [--deploy]
```

The first three arguments are always required. The flags are optional.

Additional optional polish directive override:

```bash
--qa-testcase-directive /path/to/qa_testcase_doc_directive.md
```

This lets you template and evolve post-QA testcase document requirements without code changes.

Optional Gate 4:

```bash
--quality-gate
```

Runs a fourth QA gate (default OFF) for:
- completeness vs intake
- code quality
- enhanceability
- deployability

Current pass policy:
- Gate passes when completeness, code quality, and deployability are `PASS` or `LOW`.

### Real example — Wynwood, Block B (default), no deploy (default)

```bash
./fo_test_harness.py \
  intake_hero_runs/wynwood_thoroughbreds/wynwood_thoroughbreds.json \
  /Users/teebuphilip/Documents/work/FounderOps/docs/architecture/BUILD/build_rules/FOBUILFINALLOCKED100.zip \
  /Users/teebuphilip/Documents/work/FounderOps/docs/architecture/BUILD/deployment_rules/fo_deploy_governance_v1_2_CLARIFIED.zip
```

This runs Block B (Tier 2). Output is a ZIP file. No deployment.

### Block A instead of Block B

Add `--block-a` at the end:

```bash
./fo_test_harness.py \
  intake_hero_runs/wynwood_thoroughbreds/wynwood_thoroughbreds.json \
  /Users/teebuphilip/Documents/work/FounderOps/docs/architecture/BUILD/build_rules/FOBUILFINALLOCKED100.zip \
  /Users/teebuphilip/Documents/work/FounderOps/docs/architecture/BUILD/deployment_rules/fo_deploy_governance_v1_2_CLARIFIED.zip \
  --block-a
```

### With deployment (you probably don't need this yet)

Add `--deploy` at the end:

```bash
./fo_test_harness.py \
  intake_hero_runs/wynwood_thoroughbreds/wynwood_thoroughbreds.json \
  /Users/teebuphilip/Documents/work/FounderOps/docs/architecture/BUILD/build_rules/FOBUILFINALLOCKED100.zip \
  /Users/teebuphilip/Documents/work/FounderOps/docs/architecture/BUILD/deployment_rules/fo_deploy_governance_v1_2_CLARIFIED.zip \
  --deploy
```

### Quick reference

| What you want | Command suffix |
|---|---|
| Block B, no deploy (most common) | _(nothing — it's the default)_ |
| Block A, no deploy | `--block-a` |
| Block B, with deploy | `--deploy` |
| Block A, with deploy | `--block-a --deploy` |

---

## How It Works Step by Step

```
START
  ↓
Load governance ZIPs into memory (Claude reads these as rules)
  ↓
ITERATION 1:
  ├─→ Claude reads governance + your intake data → builds everything
  ├─→ Check: Did Claude ask questions instead of building?
  │     └─ YES → Save questions to logs/claude_questions.txt → STOP
  ├─→ ChatGPT checks Claude's work against your intake
  └─→ Defects found?
        ├─ NO  → Continue to ZIP (or DEPLOY if --deploy)
        └─ YES → Go to ITERATION 2

ITERATION 2 (if defects found):
  ├─→ Claude fixes the defects reported by ChatGPT
  ├─→ ChatGPT re-checks
  └─→ Defects found?
        ├─ NO  → Continue to ZIP (or DEPLOY if --deploy)
        └─ YES → Go to ITERATION 3

[Continues up to 5 iterations max]

After QA accepts:
  ├─→ Generate artifact_manifest.json (checksums of all files)
  ├─→ DEFAULT: Package everything into a ZIP at fo_harness_runs/
  └─→ IF --deploy: Run Claude deployment instead of ZIP

SUCCESS ✓
```

---

## What You Get When It Finishes

### The ZIP (default behavior)

Right in `fo_harness_runs/`, a ZIP named after your run:

```
./fo_harness_runs/wynwood_thoroughbreds_BLOCK_B_20250213_143022.zip
```

Open it and you have everything Claude built.

### The run directory (always created)

```
./fo_harness_runs/
└── wynwood_thoroughbreds_BLOCK_B_20250213_143022/   ← run folder
    ├── build/
    │   ├── iteration_01_build.txt                   ← what Claude built
    │   ├── iteration_02_build.txt                   ← Claude's fix (if needed)
    │   ├── iteration_02_fix.txt                     ← the specific fixes made
    │   └── code/                                    ← actual code files
    │       ├── index.js
    │       ├── package.json
    │       └── README.md
    ├── qa/
    │   ├── iteration_01_qa_report.txt               ← ChatGPT's first check
    │   └── iteration_02_qa_report.txt               ← ChatGPT's second check
    ├── deploy/
    │   └── deploy_output.txt                        ← only if --deploy was used
    ├── logs/
    │   ├── iteration_01_build_prompt.log            ← exact prompt sent to Claude
    │   ├── iteration_01_qa_prompt.log               ← exact prompt sent to ChatGPT
    │   └── claude_questions.txt                     ← only if Claude asked questions
    └── artifact_manifest.json                       ← checksums of all files

./fo_harness_runs/wynwood_thoroughbreds_BLOCK_B_20250213_143022.zip  ← your deliverable
```

Post-QA polish can also generate:
- `business/docs/TEST_CASES.md` (ChatGPT-generated complete testcase doc using your testcase directive template)

---

## What Happens If Claude Asks Questions

Sometimes Claude will ask for clarification instead of just building. The harness detects this automatically.

When it happens:
- The pipeline **stops immediately** — no QA, no ZIP
- Claude's questions are saved to `logs/claude_questions.txt`
- You see this in the terminal:

```
✗ Claude asked clarifying questions on iteration 1 — stopping pipeline
⚠ Review questions in: logs/claude_questions.txt
⚠ Answer questions, update intake, and re-run
```

**What to do:** Open `logs/claude_questions.txt`, read the questions, update your intake JSON with the answers, and run again.

This applies to all iterations — if Claude asks questions during a defect fix round, it stops there too.

---

## What a Normal Run Looks Like

```bash
$ ./fo_test_harness.py wynwood_thoroughbreds.json FOBUILFINALLOCKED100.zip fo_deploy_governance_v1_2_CLARIFIED.zip

======================================================================
FO HARNESS INITIALIZED
======================================================================

→ Startup:       wynwood_thoroughbreds
→ Block:         BLOCK_B
→ Deploy:        NO — ZIP output only
→ Run directory: ./fo_harness_runs/wynwood_thoroughbreds_BLOCK_B_20250213_143022

======================================================================
STARTING BUILD → QA LOOP (BLOCK_B)
======================================================================

======================================================================
ITERATION 1/5
======================================================================

→ Calling Claude for BUILD...
✓ BUILD completed in 52.3s
✓ Saved BUILD output: build/iteration_01_build.txt

→ Calling ChatGPT for QA...
✓ QA completed in 14.1s
✓ Saved QA report: qa/iteration_01_qa_report.txt

⚠ QA REJECTED — defects found
⚠   → 2 defects to fix
→ Starting iteration 2 with defect fixes...

======================================================================
ITERATION 2/5
======================================================================

→ Calling Claude for BUILD...
✓ BUILD completed in 41.2s
✓ Saved BUILD output: build/iteration_02_build.txt
✓ Saved defect fix: build/iteration_02_fix.txt

→ Calling ChatGPT for QA...
✓ QA completed in 12.8s
✓ Saved QA report: qa/iteration_02_qa_report.txt

✓ QA ACCEPTED on iteration 2
✓ BUILD → QA loop complete — no defects

✓ Generated artifact manifest: artifact_manifest.json
→ Packaging output ZIP: wynwood_thoroughbreds_BLOCK_B_20250213_143022.zip
✓ ZIP created: ./fo_harness_runs/wynwood_thoroughbreds_BLOCK_B_20250213_143022.zip (1.24 MB)

======================================================================
EXECUTION SUMMARY
======================================================================

Startup:        wynwood_thoroughbreds
Block:          BLOCK_B
Status:         ✓ SUCCESS
Total time:     120.4s (2.0 minutes)
Deployed:       No
ZIP output:     ./fo_harness_runs/wynwood_thoroughbreds_BLOCK_B_20250213_143022.zip

Run directory:  ./fo_harness_runs/wynwood_thoroughbreds_BLOCK_B_20250213_143022

Generated files:
  - BUILD outputs:   3
  - QA reports:      2
  - DEPLOY outputs:  0
  - Logs:            4

✓ PIPELINE COMPLETED SUCCESSFULLY
```

---

## When Things Go Wrong

### Claude asked questions

```
✗ Claude asked clarifying questions on iteration 1 — stopping pipeline
```

Open `logs/claude_questions.txt` in the run directory. Answer the questions by updating your intake JSON. Re-run.

### QA never accepted after 5 rounds

```
✗ Max iterations (5) reached — loop failed to converge
✗ PIPELINE FAILED
```

Open the `qa/` directory in the run folder. Read the last QA report. The defects listed there are what Claude couldn't fix. You may need to adjust your intake JSON or governance rules.

### API key not set

```
✗ ANTHROPIC_API_KEY environment variable not set
→ Set it with: export ANTHROPIC_API_KEY='sk-ant-...'
```

Run the export command and try again.

### Intake file not found

```
✗ Intake file not found: wynwood_thoroughbreds.json
```

Check the path. The intake file is the combined JSON output from `run_intake_v7.sh`, usually at:
```
intake_hero_runs/<startup_id>/<startup_id>.json
```

### Governance ZIP not found

```
✗ BUILD governance ZIP not found: /path/to/FOBUILFINALLOCKED100.zip
```

Check that the ZIP path you typed is correct and the file exists at that location.

### API call timed out or rate limited

The script retries automatically up to 3 times on timeouts and rate limit errors. If it fails all 3 attempts you'll see:

```
✗ Claude API failed after 3 attempts: Timeout
```

Wait a minute and try again.

---

## Running Multiple Businesses

```bash
# Build Block B for all businesses in a folder
BUILD_ZIP="/Users/teebuphilip/Documents/work/FounderOps/docs/architecture/BUILD/build_rules/FOBUILFINALLOCKED100.zip"
DEPLOY_ZIP="/Users/teebuphilip/Documents/work/FounderOps/docs/architecture/BUILD/deployment_rules/fo_deploy_governance_v1_2_CLARIFIED.zip"

for intake in intake_hero_runs/*/*.json; do
  ./fo_test_harness.py "$intake" "$BUILD_ZIP" "$DEPLOY_ZIP"
done
```

---

## Adjusting Settings

Open `fo_test_harness.py` and find the `Config` class near the top. The only things worth changing:

```python
class Config:
    CLAUDE_MODEL      = 'claude-sonnet-4-20250514'  # Claude model to use
    GPT_MODEL         = 'gpt-4o'                    # ChatGPT model to use
    CLAUDE_MAX_TOKENS = 8192                         # Max output from Claude
    GPT_MAX_TOKENS    = 16000                        # Max output from ChatGPT
    MAX_QA_ITERATIONS = 5                            # Max fix rounds before giving up
    REQUEST_TIMEOUT   = 180                          # Seconds before API call times out
    MAX_RETRIES       = 3                            # Retry attempts on failure
```

---

## Limitations

- Max 5 QA rounds — after that, manual review required
- Claude and ChatGPT are called one at a time, not in parallel
- Requires internet connection throughout the entire run
- Very large builds may approach token limits

---

## Future Enhancements

- [ ] Parallel builds for multiple businesses
- [ ] Resume from checkpoint if interrupted mid-run
- [ ] Cost tracking per run
- [ ] Slack/email notification on completion

---

## License

MIT

---

**Built for the AutoFounder hermit empire.** 🏔️

No humans required.
