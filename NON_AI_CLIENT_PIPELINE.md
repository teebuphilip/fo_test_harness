# Non-AI Client Pipeline

How to go from a human founder's raw answers to a fully built, QA-validated application.

---

## Overview

```
Founder fills out questionnaire (text file)
        ↓
  Step 0: convert_hero_answers.py     raw text → hero JSON
        ↓
  Step 1: generate_intake.sh          hero JSON → structured intake JSON
        ↓
  Step 2: munger.py                   score the intake (find gaps)
        ↓
  Step 3: munger_ai_fixer.py          fix the gaps (rewrites intake JSON)
        ↓
  Step 4: run_integration_and_feature_build.sh   build → QA → ZIP
        ↓
  Step 5: check_final_zip.py          auto-runs at end of Step 4
        ↓
  Step 6: deploy/zip_to_repo.py       ZIP → GitHub repo
        ↓
  Step 7: deploy/pipeline_deploy.py   GitHub → Railway + Vercel
```

---

## Prerequisites

```bash
pip install anthropic openai requests
export ANTHROPIC_API_KEY=sk-ant-xxxxx
export OPENAI_API_KEY=sk-xxxxx

# Unzip governance pack (required for build)
unzip fobuilgov100.zip -d /tmp/fobuilgov100/
```

---

## Step 0 — Get Founder Answers

Give the founder `intake/STEP_0_TEMPLATE.txt` to fill out. They return it as a `.txt` file.

Save it to:
```
intake/hero_text/<startup_id>_<date>.txt
```

Example: `intake/hero_text/reggie_padin_02_19_2026.txt`

---

## Step 1 — Convert Raw Text → Hero JSON

```bash
cd intake
python convert_hero_answers.py hero_text/reggie_padin_02_19_2026.txt hero_text/reggie_padin.json
```

Claude parses the raw answers and produces a structured hero JSON. **Review the output** before proceeding — check that names, features, and pricing are captured correctly.

---

## Step 2 — Generate Structured Intake JSON

```bash
cd intake   # if not already there
./generate_intake.sh reggie_padin.json
```

Output: `intake/intake_runs/reggie_padin/reggie_padin.json`

This produces the full block_a + block_b intake JSON that the build harness consumes.

---

## Step 3 — Score the Intake (find gaps)

```bash
cd ..   # back to FO_TEST_HARNESS root
python munger/munger.py --intake intake/intake_runs/reggie_padin/reggie_padin.json
```

Read the score report. Look for LOW-scored sections — these are the ambiguities that will
cause QA to keep finding defects that Claude can't resolve. Fix them before building.

---

## Step 4 — Fix the Intake (rewrite weak sections)

```bash
python munger/munger_ai_fixer.py --intake intake/intake_runs/reggie_padin/reggie_padin.json
```

This rewrites the intake JSON in place, tightening vague descriptions, adding missing fields,
and resolving ambiguities. Re-run `munger.py` after to confirm the score improved.

> **Why this matters:** The intake spec is the ceiling for build quality. A vague spec means
> QA will keep finding legitimate defects that Claude cannot fix because the source of truth
> is unclear. Fixing the intake before building prevents wasted iterations.

---

## Step 5 — Build

```bash
./run_integration_and_feature_build.sh \
  --intake intake/intake_runs/reggie_padin/reggie_padin.json \
  --startup-id reggie_padin \
  --build-gov /tmp/fobuilgov100
```

**Key optional flags:**
- `--mode factory` — faster/cheaper for simple single-entity builds (Gate 3 off, 10 iter cap)
- `--mode quality` — default; full Gate 3 AI consistency check, strict Gate 4
- `--max-iterations N` — override iteration cap (default 10 factory / unlimited quality)

The pipeline will:
1. Run the phase planner (splits into Phase 1 data layer + intelligence features)
2. Build and QA-validate each entity/feature in sequence
3. Merge all entity ZIPs into a single final ZIP
4. **Auto-run `check_final_zip.py`** on the final ZIP (static + integration check)

Output: `fo_harness_runs/<startup_id>_BLOCK_B_full_<timestamp>.zip`

---

## Step 6 — Review Quality Check

The final quality check runs automatically and writes:
```
fo_harness_runs/<startup_id>_BLOCK_B_full_<timestamp>_check.json
```

If any HIGH severity issues are reported, fix them before deploying:
```bash
# Re-run integration fix pass on the relevant entity
python fo_test_harness.py <intake> \
  --resume-run fo_harness_runs/<entity_run_dir> \
  --resume-iteration <N> \
  --integration-issues integration_issues.json
```

---

## Step 7 — Deploy

> **See `deploy/README.md` for the full deploy sequence.**
> Everything from ZIP → GitHub → Railway + Vercel is documented there.

```bash
# Extract ZIP → git repo → push to GitHub
python deploy/zip_to_repo.py fo_harness_runs/reggie_padin_BLOCK_B_full_<ts>.zip

# Full deploy to Railway (backend) + Vercel (frontend)
python deploy/pipeline_deploy.py --repo ~/Documents/work/reggie_padin

# Or: generate configs only (no deploy) for manual review
python deploy/pipeline_prepare.py --repo ~/Documents/work/reggie_padin
```

---

## Quick Reference

| Step | Command | Output |
|------|---------|--------|
| 0. Get answers | Give founder `intake/STEP_0_TEMPLATE.txt` | `.txt` file |
| 1. Convert | `python intake/convert_hero_answers.py answers.txt hero.json` | hero JSON |
| 2. Intake | `cd intake && ./generate_intake.sh hero.json` | intake JSON |
| 3. Score | `python munger/munger.py --intake <intake.json>` | score report |
| 4. Fix | `python munger/munger_ai_fixer.py --intake <intake.json>` | fixed intake JSON |
| 5. Build | `./run_integration_and_feature_build.sh --intake ... --startup-id ...` | final ZIP |
| 6. Check | auto-runs at end of Step 5 | `*_check.json` |
| 7. Deploy | `python deploy/zip_to_repo.py <zip>` then `pipeline_deploy.py` | live app |

---

## Troubleshooting

**Hero JSON looks wrong after Step 1**
Edit `intake/hero_text/<startup>.json` directly before running `generate_intake.sh`.
Common issues: feature list too short, pricing not captured, target customer too vague.

**Munger score is LOW after Step 4**
Run `munger_ai_fixer.py` again — it can be run multiple times. Check the specific
low-scored fields and edit the intake JSON manually if the AI fix doesn't resolve them.

**Build hits max iterations without converging**
Almost always caused by a vague intake spec. Stop the run, go back to Step 4, tighten the
spec, and restart. More iterations won't fix a spec problem.

**QA keeps flagging the same defect across iterations**
The defect description may be ambiguous. Check `fo_harness_runs/<run>/qa/` for the raw QA
reports. If the defect refers to something not clearly defined in the intake, fix the intake.
