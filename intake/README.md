# Intake Generation

Converts founder answers into structured intake JSON files for the FO build harness.

---

## Pipeline Position

```
Founder answers (text/JSON)
        ↓
  convert_hero_answers.py    ← Step 0: raw text → hero JSON (first-time founders)
        ↓
  generate_intake.sh         ← Step 1: hero JSON → full intake JSON (block_a + block_b)
        ↓
  intake_runs/<startup>/     ← Output consumed by run_integration_and_feature_build.sh
```

---

## Directory Structure

```
intake/
├── generate_intake.sh          # Preferred wrapper — runs run_intake_v7.sh
├── run_intake_v7.sh            # Core intake generator (calls Claude API)
├── convert_hero_answers.py     # Step 0: raw text answers → hero JSON
├── validate_hero_answers.py    # Validates hero JSON structure before intake gen
├── STEP_0_TEMPLATE.txt         # Blank questionnaire to give new founders
├── claude_directive.txt        # Pass/fail evaluation directive for Claude
├── idea_generation_directive.txt  # Directive for generating random startup ideas
├── generate_proposal_from_blocks.sh  # Generate a narrative proposal from block A/B
├── post_intake_fix_batch.py    # Batch-fix common intake JSON issues
├── hero_text/                  # Founder answer files (one per startup)
├── inputs/                     # Context files Claude uses during evaluation
│   ├── mc_v6_schema.json
│   ├── intake_business_rules.json
│   ├── hero_touchpoint_policy.json
│   └── scheduling_policy.json
├── intake_runs/                # Generated intakes (output)
│   └── <startup_id>/
│       ├── block_a.json        # Tier 1 evaluation
│       ├── block_b.json        # Tier 2 evaluation
│       └── <startup_id>.json   # Combined — use this with the harness
└── failures/                   # Failed runs for debugging
```

---

## Prerequisites

```bash
pip install anthropic
export ANTHROPIC_API_KEY=sk-ant-xxxxx
```

---

## Step 0 — Raw Answers → Hero JSON (first-time founders)

Give new founders `STEP_0_TEMPLATE.txt` to fill out. Then convert their answers:

```bash
cd intake

# Auto-generate output filename from input
python convert_hero_answers.py hero_text/jose_hernandez.txt

# Or specify output name explicitly
python convert_hero_answers.py hero_text/my_answers.txt hero_text/my_startup.json
```

Claude parses the raw text and produces a structured hero JSON at `hero_text/<startup>.json`. Review it — minor edits may be needed before Step 1.

---

## Step 1 — Hero JSON → Intake JSON

```bash
cd intake
./generate_intake.sh hero_text/my_startup.json
```

**Output:** `intake_runs/my_startup/my_startup.json`

This runs Claude against the hero answers using `claude_directive.txt` and produces:
- `block_a.json` — Tier 1 evaluation
- `block_b.json` — Tier 2 evaluation (full scope)
- `my_startup.json` — Combined intake (pass this to the harness)

---

## Using the Intake with the Build Pipeline

After generating an intake, pass it to the build pipeline:

```bash
cd ..   # back to FO_TEST_HARNESS root

./run_integration_and_feature_build.sh \
  --intake intake/intake_runs/my_startup/my_startup.json \
  --startup-id my_startup
```

The pipeline will call `phase_planner.py` to split the intake into:
- **Phase 1** — data layer (models, auth, core routes)
- **Intelligence features** — each built and validated separately

The phase planner outputs `<startup_id>_phase_assessment.json` and `<startup_id>_phase1.json` into the same `intake_runs/<startup>/` directory.

---

## Adding a Feature to an Existing Build

If the original build is already deployed and you need to add a new feature not in the original intake, use `feature_adder.py` (called automatically by `add_feature.sh`):

```bash
cd ..   # back to FO_TEST_HARNESS root

./add_feature.sh \
  --intake intake/intake_runs/my_startup/my_startup.json \
  --feature "New feature name" \
  --existing-repo ~/Documents/work/my_startup
```

See the root `README.md` for full `add_feature.sh` options.

---

## Generating Random Startup Ideas

For testing the pipeline with synthetic intakes:

```bash
cd intake
./run_intake_v7.sh 5 ./intake_runs ./claude_directive.txt ./idea_generation_directive.txt
```

Produces `intake_runs/run_1/` through `intake_runs/run_5/`.

---

## Batch-Fixing Intake Issues

`post_intake_fix_batch.py` applies common fixes to existing intake JSONs (field normalisation, missing keys, schema alignment). Run it against an `intake_runs/` directory if the harness rejects an intake:

```bash
python post_intake_fix_batch.py intake/intake_runs/my_startup/my_startup.json
```

---

## Troubleshooting

**"ANTHROPIC_API_KEY not set"**
```bash
export ANTHROPIC_API_KEY=sk-ant-xxxxx
```

**Generated intake is incomplete (missing block_b)**

Check `failures/` for error logs. Verify all files exist in `inputs/`. If the hero JSON is malformed, re-run `convert_hero_answers.py` and review the output before Step 1.

**phase_planner.py produces empty intelligence_features list**

The intake's `Q4_must_have_features` may describe only data-layer features (CRUD, forms, auth). Add at least one analytics/reporting/intelligence feature to the hero JSON and regenerate.
