# FO Test Harness

End-to-end pipeline for the FounderOps **BUILD → QA → DEPLOY** workflow.

- **Builder**: Claude (Anthropic) generates full-stack code + docs
- **Validator**: ChatGPT (OpenAI) checks against intake spec
- **Loop**: Defects feed back into Claude until clean or max iterations (default 20)

---

## Three-Stage Pipeline

| Stage | Script | Purpose |
|-------|--------|---------|
| 1. Intake | `intake/generate_intake.sh` | Founder answers → structured intake JSON |
| 2. Build-QA | `run_integration_and_feature_build.sh` | Phase-by-phase BUILD + QA + integration check |
| 2b. Build-QA (quality) | `run_slicer_and_feature_build.sh` | Slice-by-slice BUILD + QA + integration check |
| 3. Deploy | `deploy/zip_to_repo.py` → `deploy/pipeline_deploy.py` | ZIP → GitHub → Railway / Vercel |

---

## Prerequisites

```bash
pip install anthropic openai requests

export ANTHROPIC_API_KEY=sk-ant-xxxxx
export OPENAI_API_KEY=sk-xxxxx

# Governance ZIP must be in the project root
ls FOBUILFINALLOCKED*.zip   # should find one
```

Check both APIs are live before running:

```bash
python check_openai.py          # Claude + OpenAI health check
python check_openai.py --openai # shows remaining TPM quota
```

---

## Quick Start — New Build

### Step 1: Generate Intake

```bash
cd intake
./generate_intake.sh hero_text/my_startup.json
# Output: intake/intake_runs/my_startup/my_startup.json
cd ..
```

### Optional: Pre-Intake Gap Analysis (Pass0)

If you start with a raw idea or pre-intake JSON, run the gap-analysis pipeline first. It produces:
- a locked business brief,
- pricing model,
- name + domain check,
- SEO + marketing + GTM,
- hero answers + hero JSON in `intake/ai_text/`.

```bash
./gap-analysis/run_full_pipeline.sh /path/to/preintake.json --verbose
# Hero JSON output: intake/ai_text/<picked_name>.json
```

### Optional: Block B Quality Check (Deterministic)

After intake (or grilled intake), you can run a deterministic quality check:

```bash
python check_block_b.py intake/intake_runs/<startup>/<startup>.json
python check_block_b.py intake/intake_runs/<startup>/<startup>.grilled.json
```

Exit codes:
- `0` PASS (score ≥ 80)
- `1` WARN (60–79)
- `2` FAIL (< 60)
- `3` ERROR (file missing/invalid)

### Optional: HERO (QUALITY) — Apply AI Fixes to Hero JSON

**Special build step for quality mode (not factory mode).**

If you already ran `munger_ai_fixer.py` and want to apply its output to a hero JSON:

```bash
munger/write_aifixed.sh intake/ai_text/<startup>.json munger/<startup>_munger_ai_fixed.json
```

This writes `aifixed.<startup>.json` next to the original hero file with `hero_answers` replaced by the fixer output.

### Optional: HERO (QUALITY) — Proposal From Blocks

**HERO (QUALITY) / SPECIAL BUILD step (not factory mode).**

Generates a proposal document to send to the hero based on Block A + Block B:

```bash
intake/generate_proposal_from_blocks.sh intake/intake_runs/<startup>
```

### Step 2: Run Build-QA Pipeline

```bash
./run_integration_and_feature_build.sh \
  --intake intake/intake_runs/my_startup/my_startup.json \
  --startup-id my_startup
```

This script handles everything automatically:
1. Runs `phase_planner.py` — splits intake into data layer + feature list
2. Builds Phase 1 (data layer models, auth, core routes)
3. For each intelligence feature: generates scoped intake → builds → integration check
4. Fixes integration issues via harness resume (up to 2 fix passes per feature)
5. Merges all ZIPs into a single final deliverable

**Output:** `fo_harness_runs/my_startup_BLOCK_B_full_<timestamp>.zip`

**Auto-resume:** If the run is interrupted, rerun the exact same command — the script detects which ZIPs already exist and picks up where it left off.

### Optional: Auto-Route Build (Slice vs Phase)

If you want the system to choose the build pipeline for you:

```bash
./run_auto_build.sh --intake intake/intake_runs/<startup>/<startup>.json
```

This calls `planner_router.py` and routes to:
- `run_slicer_and_feature_build.sh` when a slice plan is recommended
- `run_integration_and_feature_build.sh` otherwise

**Phase vs Slice execution chains**
- **Phase chain:** `run_auto_build.sh` → `planner_router.py` → `run_integration_and_feature_build.sh` → `ubiquity.py` → `phase_planner.py` → `generate_feature_spec.py` → `feature_adder.py --spec-file` → `fo_test_harness.py` → `integration_check.py` → merge ZIPs → `check_final_zip.py` (optional)
- **Slice chain:** `run_auto_build.sh` → `planner_router.py` → `run_slicer_and_feature_build.sh` → `ubiquity.py` → `slice_planner.py` → `generate_feature_spec.py` → `inject_spec.py` → `fo_test_harness.py` → `integration_check.py` → merge ZIPs → `check_final_zip.py` (optional)

### Step 3: Deploy

```bash
# Extract ZIP → git repo → push to GitHub
python deploy/zip_to_repo.py fo_harness_runs/my_startup_BLOCK_B_full_<timestamp>.zip

# Full deploy (Railway backend + Vercel frontend)
python deploy/pipeline_deploy.py --repo ~/Documents/work/my_startup
```

Deploy notes:
1. `deploy/pipeline_deploy.py` now writes a timestamped run log to `deploy/pipeline-deploy-logs/`.
2. Railway backend deploy now reuses or generates a public `*.up.railway.app` domain automatically.
3. The resolved backend URL is injected into the Vercel frontend deploy.

---

## Gap-Analysis Tools

**Primary pipelines**
- `gap-analysis/run_full_pipeline.sh` — Full gap-analysis pipeline from raw idea JSON.
- `gap-analysis/run_full_pipeline_from_hero.sh` — Full gap-analysis pipeline from hero JSON.

**Pipeline chain (run_full_pipeline.sh)**
- `run_full_pipeline.sh`
  - `run_pass0.sh` → `pass0_gap_check.py` (writes pass0 + brief + one-liner)
  - `run_pricing_modeler.sh` → `pricing_modeler.py` (updates business brief)
  - `run_name_picker.sh` → `auto_name_picker.py` (writes named + suggestions)
  - `run_ai_hero_answers.sh` → `generate_ai_hero_answers.py` → `intake/convert_hero_answers.py`
  - `run_seo_generator.sh` → `seo_generator.py`
  - `run_marketing_copy.sh` → `base_marketing_copy.py`
  - `run_gtm_plan.sh` → `base_gtm_plan.py`

**Gap-analysis scripts (details)**
- `gap-analysis/auto_name_picker.py` — Auto name picker.
- `gap-analysis/base_gtm_plan.py` — Base GTM plan template.
- `gap-analysis/base_marketing_copy.py` — Base marketing copy template.
- `gap-analysis/build_brief_from_hero.py` — Build brief from hero input.
- `gap-analysis/discover_allowlist.py` — Discovery allowlist builder.
- `gap-analysis/generate_ai_hero_answers.py` — AI hero answers generator.
- `gap-analysis/pass0_gap_check.py` — Pass‑0 gap check.
- `gap-analysis/pass0_research.py` — Pass‑0 research.
- `gap-analysis/pricing_modeler.py` — Pricing modeler.
- `gap-analysis/run_ai_hero_answers.sh` — Runs AI hero answers generator.
- `gap-analysis/run_discover_allowlist.sh` — Runs discover allowlist pipeline.
- `gap-analysis/run_full_pipeline.sh` — Full gap‑analysis pipeline.
- `gap-analysis/run_full_pipeline_from_hero.sh` — Full pipeline from hero input.
- `gap-analysis/run_gtm_plan.sh` — Runs GTM plan generation.
- `gap-analysis/run_marketing_copy.sh` — Runs marketing copy generation.
- `gap-analysis/run_name_picker.sh` — Runs name picker.
- `gap-analysis/run_pass0.sh` — Runs pass‑0 steps.
- `gap-analysis/run_pricing_modeler.sh` — Runs pricing modeler.
- `gap-analysis/run_seo_generator.sh` — Runs SEO generator.
- `gap-analysis/seo_generator.py` — SEO generator.
- `gap-analysis/tests/test_pass0_gap_check.py` — Tests for pass‑0 gap check.

## Post-Build Config

Generate `business_config.json` from a final ZIP (optionally include `_harness/build` copies):

```bash
python generate_business_config.py \
  --zip fo_harness_runs/<startup>_BLOCK_B_full_<timestamp>.zip \
  --intake intake/intake_runs/<startup>/<startup>_phase_assessment.json \
  --seo seo/<startup>_business_brief_seo.json \
  --marketing gap-analysis/outputs/<startup>_business_brief_marketing_copy.json \
  --gtm gap-analysis/outputs/<startup>_business_brief_gtm.json \
  --include-harness-build
```

## Adding a Feature to an Existing Build

Use `add_feature.sh` when the codebase is already built and deployed. This is distinct from `run_integration_and_feature_build.sh` which is for greenfield builds.

### From an existing ZIP

```bash
./add_feature.sh \
  --intake  intake/intake_runs/awi/awi.5.json \
  --feature "Competitor benchmarking dashboard" \
  --existing-zip fo_harness_runs/awi_FINAL_20260309.zip
```

### From a live deployed repo (local path or GitHub URL)

```bash
# Local path
./add_feature.sh \
  --intake  intake/intake_runs/awi/awi.5.json \
  --feature "Competitor benchmarking dashboard" \
  --existing-repo ~/Documents/work/ai_workforce_intelligence

# GitHub URL (clones with --depth=1 automatically)
./add_feature.sh \
  --intake  intake/intake_runs/awi/awi.5.json \
  --feature "Competitor benchmarking dashboard" \
  --existing-repo https://github.com/yourorg/ai_workforce_intelligence
```

**Flow:** `feature_adder.py` → `fo_test_harness.py` → `integration_check.py` → merge → new final ZIP

**Auto-resume:** If interrupted, rerun the same command — skips any stage already completed.

**Spec injection notes (used by the build pipelines):**
- `run_integration_and_feature_build.sh`: generates a feature spec and passes it into `feature_adder.py --spec-file`, which embeds it into the feature intake before `fo_test_harness.py`.
- `run_slicer_and_feature_build.sh`: generates a spec and runs `inject_spec.py` to embed it into the slice intake before `fo_test_harness.py`.

---

## Running the Harness Directly

For manual control or resume scenarios:

```bash
python fo_test_harness.py \
  intake/intake_runs/my_startup/my_startup.json \
  FOBUILFINALLOCKED100.zip \
  --max-iterations 20
```

**Key flags:**

| Flag | Purpose |
|------|---------|
| `--block A\|B` | Tier 1 or Tier 2 intake block (default B) |
| `--max-iterations N` | Iteration cap (default 20) |
| `--no-polish` | Skip README / .env / tests (for intermediate phases) |
| `--prior-run <dir>` | Seed QA prohibition tracker from a previous run |
| `--resume-run <dir>` | Resume a killed run from existing run directory |
| `--resume-iteration N` | Which iteration to resume from |
| `--resume-mode qa\|fix\|consistency` | `qa`: fresh QA on existing artifacts; `fix`: load QA report as defects; `consistency`: re-run AI consistency check |
| `--integration-issues <file>` | Targeted integration fix pass (routes to surgical patch prompt) |
| `--deploy` | Run deploy pipeline after build acceptance |

---

## Integration Check

Run `integration_check.py` on any build to get a deterministic (no AI) report of structural bugs. Used automatically by `run_integration_and_feature_build.sh` and `add_feature.sh` after each feature build.

```bash
# Against an artifacts directory
python integration_check.py \
  --artifacts fo_harness_runs/my_startup_BLOCK_B_<ts>/build/iteration_19_artifacts \
  --intake intake/intake_runs/my_startup/my_startup.json \
  --output my_integration_issues.json

# Against a ZIP
python integration_check.py \
  --zip fo_harness_runs/my_startup_BLOCK_B_<ts>.zip \
  --intake intake/intake_runs/my_startup/my_startup.json
```

**15 checks across backend and frontend:**

| # | Category | What it catches |
|---|----------|-----------------|
| 1 | Route inventory | Frontend fetch() calls vs backend @router endpoints |
| 2 | Model field refs | Service model.field accesses vs Column definitions |
| 3 | Spec compliance | Intake keywords (PDF, KPI names) missing from artifacts |
| 4 | Import chains | `from business.X import Y` vs actual artifact files |
| 5 | Route double-path | @router decorators that repeat the filename stem |
| 6 | Auth contract | Routes with `Depends(get_current_user)` vs frontend Authorization headers |
| 7 | Async misuse | `await` called on non-async (sync) functions |
| 8 | gather() sync args | `asyncio.gather(sync_func())` → TypeError at runtime |
| 9 | npm integrity | JSX imports vs `business/package.json` dependencies |
| 10 | Bare except | Silent error swallow (`except:` / `except Exception: pass`) |
| 11 | Unbounded polling | `setTimeout(fn, N)` with no attempt cap → infinite loop |
| 12 | Background timeout | `BackgroundTasks.add_task()` with no timeout when intake has SLA |
| 13 | Config object as text | JSX renders `{config.section.key}` where config value is a dict → `[object Object]` |
| 14 | Dead buttons | `<button>` with no onClick (not submit), `<a href="#">` placeholder links |
| 15 | Form state mismatch | `useState` fields not in `business_config.json` form definitions → silent data loss |

To feed issues back into the harness for a targeted fix:

```bash
python fo_test_harness.py \
  my_startup.json FOBUILFINALLOCKED100.zip \
  --resume-run fo_harness_runs/my_startup_BLOCK_B_<ts> \
  --resume-iteration 19 \
  --integration-issues my_integration_issues.json
```

---

## Cleanup Script

Use `cleanup_fo_harness_runs.py` to reduce disk usage under `fo_harness_runs/` while
keeping cost tracking viable.

Default behavior:
- Keeps all `.zip` files
- Keeps latest **5** run directories per prefix
- Removes heavy subfolders (`build/`, `qa/`, `logs/`, `tmp/`) from older runs

Example:
```bash
python cleanup_fo_harness_runs.py --runs-dir fo_harness_runs --keep 5 --dry-run
python cleanup_fo_harness_runs.py --runs-dir fo_harness_runs --keep 5 --apply
```

---

## QA Gates

Every build iteration passes through **five sequential gates** inside `fo_test_harness.py`, then one post-build gate:

| # | Gate | Type | Validator | Directive | What it checks |
|---|------|------|-----------|-----------|----------------|
| 1 | **COMPILE** | Deterministic | Harness (Python AST parse) | — | Syntax errors — file rejected if unparseable |
| 2 | **STATIC** | Deterministic | Harness (AST analysis) | — | Duplicate `__tablename__`, wrong Base import, unauthenticated routes, missing methods, `async def` |
| 3 | **CONSISTENCY** | AI | ChatGPT / GPT-4o | `directives/prompts/build_ai_consistency.md` | Cross-file structural: model↔service, schema↔model, route↔schema, import chains |
| 4 | **QUALITY** | AI | ChatGPT / GPT-4o | `directives/prompts/build_quality_gate.md` | Deployability, enhanceability, code quality, completeness vs intake |
| 5 | **FEATURE_QA** | AI | ChatGPT / GPT-4o | `directives/prompts/qa_prompt.md` | Spec compliance, scope, functional bugs |
| 6 | **INTEGRATION** (post-build) | Deterministic | `integration_check.py` (15 checks) | — | Backend structure/auth/async + frontend config rendering, dead buttons, form state |

Gates 1–5 run inside the iterative loop. Gate 6 runs once after the loop exits (via `run_integration_and_feature_build.sh` or `add_feature.sh`). Any gate failure → targeted Claude fix → back to Gate 1.

**Gate design principle — CONSISTENCY is a pre-filter, not the authority:**

CONSISTENCY (Gate 3) catches obvious cross-file structural bugs cheaply before the expensive QA call. It is not the authoritative validator. After 4 consecutive CONSISTENCY failures the harness falls through to Feature QA regardless of issue severity. This is intentional:

- If CONSISTENCY has failed 4 times on the same issue, it is either a stubborn GPT-4o hallucination (the filter catches most but not all) or a minor gap that doesn't break the running app.
- Escalating to a full rebuild for 1 unresolved CONSISTENCY issue is strictly worse — Claude regenerates all files from memory, inventing wrong-path architectures and destroying the surgical fixes from prior iterations.
- Feature QA sees the actual artifacts and the full spec. If the CONSISTENCY issue is a real AttributeError it will surface as a QA defect with concrete evidence. If QA accepts the build, the issue wasn't real.

**Rule:** never treat a CONSISTENCY failure as a reason to do a full build. Fix surgically, fall through to QA at the cap.

---

## Key Scripts

| Script | Purpose |
|--------|---------|
| `run_integration_and_feature_build.sh` | **Main pipeline** — greenfield phase-by-phase build |
| `run_slicer_and_feature_build.sh` | Slice-based pipeline (quality mode) using `slice_planner.py` |
| `run_auto_build.sh` | Auto-route to slice vs phase pipeline via `planner_router.py` |
| `add_feature.sh` | Add one feature to an existing built/deployed repo |
| `fo_test_harness.py` | Core BUILD-QA orchestrator (~4000 lines) |
| `integration_check.py` | 15-check deterministic post-build validator |
| `phase_planner.py` | Splits intake into data layer + intelligence feature list |
| `slice_planner.py` | Builds vertical slice plans + runnable slice intakes (`--extra-repair` optional second repair pass) |
| `ubiquity.py` | Extracts canonical domain terms from intake and writes a ubiquitous language glossary |
| `planner_router.py` | Intake router: recommends slice vs phase |
| `feature_adder.py` | Generates scoped feature intake from existing ZIP or repo |
| `generate_business_config.py` | Post-merge config generator — scans built pages, writes `business_config.json` |
| `generate_feature_spec.py` | Generates feature specs used by build pipelines (internal helper) |
| `check_openai.py` | Pre-run API health check (Claude + OpenAI, TPM quota) |
| `check_boilerplate_fit.py` | Checks if intake suits the boilerplate (YES/NO + file list) |
| `aggregate_ai_costs.py` | Merges all cost CSVs into `ai_costs_aggregated.csv` |
| `summarize_harness_runs.py` | Generates run summary table from `fo_run_log.csv` |
| `inject_spec.py` | Injects feature specs into intake before build (internal helper) |
| `deploy/zip_to_repo.py` | ZIP extraction → git init → GitHub push |
| `deploy/pipeline_deploy.py` | Full deploy orchestrator (Railway + Vercel) |
| `deploy/pipeline_prepare.py` | Config-only mode (AI config gen + git push, no deploy) |
| `munger/munger.py` | Spec quality scorer |
| `munger/munger_ai_fixer.py` | AI-based spec quality fix loop |

---

## Output Structure

```
fo_harness_runs/<startup>_BLOCK_B_<timestamp>/
├── build/
│   ├── iteration_01_build.txt          # Raw Claude output
│   ├── iteration_01_artifacts/         # Extracted files (business/**)
│   └── iteration_02_fix.txt            # Defect-fix iteration
├── qa/
│   └── iteration_01_qa_report.txt      # ChatGPT QA report
├── logs/
│   ├── iteration_01_build_prompt.log
│   ├── iteration_01_qa_prompt.log
│   └── claude_questions.txt
├── integration_issues.json             # Integration check output
├── artifact_manifest.json              # File checksums
└── build_state.json                    # Run metadata
```

---

## Resume Scenarios

**Run killed mid-build (429 / timeout):**
```bash
# For run_integration_and_feature_build.sh — just rerun the same command
./run_integration_and_feature_build.sh --intake my_intake.json

# For fo_test_harness.py directly
python fo_test_harness.py my_intake.json FOBUILFINALLOCKED100.zip \
  --resume-run fo_harness_runs/my_startup_BLOCK_B_<ts> \
  --resume-iteration 7
```

**Re-run QA on existing artifacts without rebuilding:**
```bash
python fo_test_harness.py my_intake.json FOBUILFINALLOCKED100.zip \
  --resume-run fo_harness_runs/my_startup_BLOCK_B_<ts> \
  --resume-iteration 7 \
  --resume-mode qa
```

**Load existing QA report as defects, run fix at next iteration:**
```bash
python fo_test_harness.py my_intake.json FOBUILFINALLOCKED100.zip \
  --resume-run fo_harness_runs/my_startup_BLOCK_B_<ts> \
  --resume-iteration 7 \
  --resume-mode fix
```

---

## Cost Tracking

| File | Contains |
|------|---------|
| `fo_run_log.csv` | Claude + ChatGPT costs per build run |
| `deploy/deploy_ai_costs.csv` | Deploy pipeline AI costs |
| `munger/munger_ai_costs.csv` | Munger AI costs |
| `ai_costs_aggregated.csv` | All costs merged |

```bash
python aggregate_ai_costs.py   # refresh ai_costs_aggregated.csv
```

---

## Config Override Files

| File | Controls |
|------|---------|
| `fo_tech_stack_override.json` | Tech stack defaults (Next.js, Prisma, etc.) |
| `fo_external_integration_override.json` | Rules for Stripe, auth, external APIs |
| `fo_qa_override.json` | QA behaviour adjustments |

---

## Deploy Prerequisites

```bash
export GITHUB_TOKEN=ghp_xxxxx
export GITHUB_USERNAME=yourname
export RAILWAY_TOKEN=xxxxx
export VERCEL_TOKEN=xxxxx
```

---

## Troubleshooting

**QA loop not converging (10+ iterations)**

Check the QA report for the repeating defect pattern:
```bash
cat fo_harness_runs/my_startup_*/qa/iteration_*_qa_report.txt | grep "DEFECT-"
```
Common causes: boilerplate import pattern mismatch, scope-boundary defect that can't be fixed by code. See `learnings-from-af-to-fo.md` for known patterns.

**ChatGPT 429 / rate limit**

The harness reads `Retry-After` headers and waits automatically. If a run is killed, rerun the same command — `run_integration_and_feature_build.sh` auto-resumes from the last completed ZIP.

**Integration check fires false positives on Check 14 (dead buttons)**

Buttons inside dynamic `.map()` lists and `type="submit"` buttons inside `<form>` tags are automatically skipped. If a legitimate pattern is being flagged, check the evidence field in `integration_issues.json` — the exact line is quoted.

**Missing boilerplate**

```bash
ls /Users/teebuphilip/Documents/work/teebu-saas-platform/saas-boilerplate/
```
Should exist. If missing, the harness will warn on startup.

---

## Key Docs

| File | Read for |
|------|---------|
| `CLAUDE.md` | Full project instructions for Claude Code |
| `changelog.md` | Every change made — update after each session |
| `must-port-to-fo.md` | Harness changes not yet in FO production |
| `learnings-from-af-to-fo.md` | Root cause lessons and recurring patterns |
| `intake/README.md` | Intake generation details |
| `FO_ARTIFACT_FORMAT_RULES.txt` | File formatting standards Claude must follow |
| `FO_BOILERPLATE_INTEGRATION_RULES.txt` | Boilerplate constraints |
