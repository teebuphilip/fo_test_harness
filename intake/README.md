# FO Intake Generation

This directory contains everything needed to convert founder answers into intake JSON files for the FO build harness.

## Complete Pipeline

```
Step 0: Raw Answers → Hero JSON (convert_hero_answers.py)
Step 1: Hero JSON → Intake Evaluation (run_intake_v7.sh)
Step 2: Intake JSON → Build (fo_test_harness.py)
```

## Directory Structure

```
intake/
├── convert_hero_answers.py     # STEP 0: Convert raw answers → hero JSON
├── run_intake_v7.sh           # STEP 1: Generate intake from hero JSON
├── generate_intake.sh         # Simplified wrapper
├── STEP_0_TEMPLATE.txt        # Blank questionnaire for founders
├── claude_directive.txt        # Pass evaluation directive
├── idea_generation_directive.txt  # Startup idea generation directive
├── hero_text/                  # Hero answer files (founders' answers)
│   ├── twofacedai.json        # ← Structured (ready for Step 1)
│   ├── wynwoodracing.json     # ← Structured (ready for Step 1)
│   └── jose_hernandez.txt     # ← Raw answers (need Step 0 first)
├── inputs/                     # Context files (schemas, policies, rules)
│   ├── mc_v6_schema.json
│   ├── intake_business_rules.json
│   ├── hero_touchpoint_policy.json
│   └── scheduling_policy.json
├── intake_runs/                # Generated intakes (output)
│   ├── twofaced_ai/
│   │   ├── block_a.json
│   │   ├── block_b.json
│   │   └── twofaced_ai.json  # ← Use this with test harness
│   └── ...
└── failures/                   # Failed runs for debugging
```

## Prerequisites

1. **Python 3.8+** with anthropic package:
   ```bash
   pip install anthropic
   ```

2. **API Key**:
   ```bash
   export ANTHROPIC_API_KEY=sk-ant-xxxxx
   ```

## Usage

### Step 0: Convert Raw Answers (First Time Setup)

When a founder gives you their answers in text format:

```bash
cd intake

# Option 1: Auto-generate output filename
python convert_hero_answers.py hero_text/jose_hernandez_02_11_2026.txt

# Option 2: Specify output name
python convert_hero_answers.py hero_text/my_answers.txt hero_text/mystartup.json
```

**What this does:**
- Uses Claude to intelligently parse the raw text
- Extracts structured data (problem, customers, features, etc.)
- Generates a hero JSON file
- Output: `hero_text/<startup_name>.json`

**For new founders:**
1. Give them `STEP_0_TEMPLATE.txt` to fill out
2. Run the conversion script on their answers
3. Review the generated JSON (may need minor edits)
4. Continue to Step 1

### Step 1: Hero Mode (Existing Founder Answers)

Use this when you have a hero JSON file with the founder's answers:

```bash
cd intake

./run_intake_v7.sh \
  hero_text/twofacedai.json \
  ./intake_runs \
  ./claude_directive.txt
```

**Output:** `intake_runs/twofaced_ai/twofaced_ai.json`

### Generate Mode (Random Startup Ideas)

Use this to generate N random startup ideas:

```bash
cd intake

./run_intake_v7.sh \
  5 \
  ./intake_runs \
  ./claude_directive.txt \
  ./idea_generation_directive.txt
```

**Output:**
- `intake_runs/run_1/run_1.json`
- `intake_runs/run_2/run_2.json`
- etc.

## Using with Test Harness

After generating an intake, use it with the build harness:

```bash
cd ..  # Back to FO_TEST_HARNESS

python fo_test_harness.py \
  --intake intake/intake_runs/twofaced_ai/twofaced_ai.json \
  --startup-id twofaced_ai \
  --block B \
  --build-gov /tmp/fobuilgov100 \
  --tech-stack lowcode
```

## Adding New Hero Files

To test a new startup idea:

1. Create `hero_text/your_startup.json` with this format:
```json
{
  "startup_idea_id": "your_startup",
  "Q1_problem_customer": "...",
  "Q2_target_user": ["..."],
  "Q3_success_metric": "...",
  ...
}
```

2. Run the intake generator:
```bash
./run_intake_v7.sh hero_text/your_startup.json ./intake_runs ./claude_directive.txt
```

3. Use the generated intake with the test harness

## Troubleshooting

**Error: "ANTHROPIC_API_KEY not set"**
- Solution: `export ANTHROPIC_API_KEY=sk-ant-xxxxx`

**Error: "Pass directive not found"**
- Solution: Make sure you're running from the `intake/` directory

**Generated intake is incomplete (missing block_b)**
- Check `failures/` directory for error logs
- Verify all input files are present in `inputs/`

## Files Explained

- **run_intake_v7.sh**: Main script that calls Claude API to generate intakes
- **claude_directive.txt**: Instructions for how Claude should evaluate pass/fail for tiers
- **idea_generation_directive.txt**: Instructions for generating random startup ideas
- **inputs/*.json**: Context files (schemas, business rules) that Claude uses for evaluation
- **hero_text/*.json**: Founder answer files (one per startup idea)
