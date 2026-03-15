# CLAUDE.md — FO_TEST_HARNESS

## Project Overview

End-to-end pipeline for testing the FounderOps BUILD → QA → DEPLOY workflow. Takes a structured intake JSON + governance ZIP and produces a fully-built, QA-validated ZIP of application artifacts.

- **Builder**: Claude (Anthropic) generates full-stack code + docs
- **Validator**: ChatGPT (OpenAI) checks against intake spec
- **Loop**: Defects feed back into Claude until clean or max iterations (default 20)

---

## Three-Stage Pipeline

| Stage | Entry Point | Purpose |
|-------|------------|---------|
| 1. Intake | `intake/generate_intake.sh` | Founder answers → structured intake JSON |
| 2. Build-QA | `run_integration_and_feature_build.sh` | Phase-by-phase BUILD + QA + integration check |
| 3. Deploy | `deploy/zip_to_repo.py` → `deploy/pipeline_deploy.py` | ZIP → GitHub → Railway/Vercel |

---

## Key Files

| File | Purpose |
|------|---------|
| `run_integration_and_feature_build.sh` | **Main pipeline** — greenfield phase-by-phase build |
| `add_feature.sh` | Add one feature to an existing built/deployed repo |
| `fo_test_harness.py` | Core BUILD-QA orchestrator (~4000 lines) |
| `integration_check.py` | 15-check deterministic post-build validator |
| `phase_planner.py` | Splits intake into data layer + intelligence feature list |
| `feature_adder.py` | Generates scoped feature intake from existing ZIP or repo |
| `check_openai.py` | Pre-run API health check — Claude + OpenAI, shows TPM quota |
| `check_boilerplate_fit.py` | Checks if intake suits boilerplate (YES/NO + file list) |
| `aggregate_ai_costs.py` | Merges cost CSVs |
| `summarize_harness_runs.py` | Generates run summaries |
| `deploy/pipeline_deploy.py` | Full deploy orchestrator (Railway + Vercel) |
| `deploy/pipeline_prepare.py` | Config-only mode (AI config gen + Git push, no deploy) |
| `deploy/zip_to_repo.py` | ZIP extraction → git init → GitHub push |
| `deploy/railway_deploy.py` | Railway backend deployment |
| `deploy/vercel_deploy.py` | Vercel frontend deployment |
| `munger/munger.py` | Spec quality scorer |
| `munger/munger_ai_fixer.py` | AI-based spec fixing loop |

---

## fo_test_harness.py — Class Structure

| Class | Line | Role |
|-------|------|------|
| `Config` | ~36 | Static config: models, token limits, timeouts |
| `ClaudeClient` | ~452 | Anthropic API wrapper with retry + backoff |
| `ChatGPTClient` | ~564 | OpenAI API wrapper with Retry-After + exponential backoff |
| `ArtifactManager` | ~647 | Extracts `**FILE: path**` artifacts; remaps wrong-path files |
| `DirectiveTemplateLoader` | ~425 | Loads prompt markdown files from `directives/prompts/` |
| `PromptTemplates` | ~1130 | Prompt construction (600+ lines) |
| `FOHarness` | ~1800 | Main orchestrator; `execute_build_qa_loop()` entry |

**Key FOHarness methods:**
- `execute_build_qa_loop()` — main iteration loop
- `run_claude_build()` — calls Claude for BUILD
- `run_chatgpt_qa()` — calls ChatGPT for QA
- `_enrich_defects_with_fix_context()` — adds architectural guidance to defects
- `_apply_patch_recovery()` — recovers missing files
- `_validate_pre_qa()` — pre-QA checks

---

## Running the Harness

### Prerequisites
```bash
pip install anthropic openai requests

export ANTHROPIC_API_KEY=sk-ant-xxxxx
export OPENAI_API_KEY=sk-xxxxx

# Governance ZIP must be in the project root
ls FOBUILFINALLOCKED*.zip   # should find one
```

**Check APIs before running:**
```bash
python check_openai.py          # both Claude + OpenAI
python check_openai.py --openai # shows TPM quota remaining
```

### Step 1: Generate Intake
```bash
cd intake
./generate_intake.sh hero_text/twofaced_ai.json
# Output: intake/intake_runs/twofaced_ai/twofaced_ai.json
cd ..
```

### Step 2: Run Build-QA Pipeline
```bash
./run_integration_and_feature_build.sh \
  --intake intake/intake_runs/twofaced_ai/twofaced_ai.json \
  --startup-id twofaced_ai
```

This script handles everything automatically:
1. Runs `phase_planner.py` — splits intake into data layer + feature list
2. Builds Phase 1 (data layer models, auth, core routes)
3. For each intelligence feature: generates scoped intake → builds → integration check
4. Fixes integration issues via harness resume (up to 2 fix passes per feature)
5. Merges all ZIPs into a single final deliverable

**Output:** `fo_harness_runs/twofaced_ai_BLOCK_B_full_<timestamp>.zip`

**Auto-resume:** If interrupted, rerun the exact same command — the script detects which ZIPs already exist and picks up where it left off.

### Running the Harness Directly

For manual control or resume scenarios:

```bash
python fo_test_harness.py \
  intake/intake_runs/twofaced_ai/twofaced_ai.json \
  FOBUILFINALLOCKED100.zip \
  --max-iterations 20
```

**Key CLI flags:**

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

### Adding a Feature to an Existing Build

```bash
# From an existing ZIP
./add_feature.sh \
  --intake intake/intake_runs/twofaced_ai/twofaced_ai.json \
  --feature "Some new feature" \
  --existing-zip fo_harness_runs/twofaced_ai_FINAL.zip

# From a live deployed repo (local path or GitHub URL)
./add_feature.sh \
  --intake intake/intake_runs/twofaced_ai/twofaced_ai.json \
  --feature "Some new feature" \
  --existing-repo ~/Documents/work/twofaced_ai
```

**Flow:** `feature_adder.py` → `fo_test_harness.py` → `integration_check.py` → merge → new final ZIP

### Step 3: Deploy
```bash
# Extract ZIP → git repo → GitHub
python deploy/zip_to_repo.py fo_harness_runs/twofaced_ai_BLOCK_B_full_*.zip

# Full deploy (Railway + Vercel)
python deploy/pipeline_deploy.py --repo ~/Documents/work/twofaced_ai

# Configs only (no deploy)
python deploy/pipeline_prepare.py --repo ~/Documents/work/twofaced_ai
python deploy/pipeline_prepare.py --repo . --configs-only  # skip git push too
```

---

## Output Structure

```
fo_harness_runs/<startup>_BLOCK_<X>_<timestamp>/
├── build/
│   ├── iteration_01_build.txt        # Raw Claude output
│   ├── iteration_01_artifacts/       # Extracted files (business/**)
│   └── iteration_02_fix.txt          # Defect-fix iteration
├── qa/
│   └── iteration_01_qa_report.txt    # ChatGPT QA report
├── logs/
│   ├── iteration_01_build_prompt.log
│   ├── iteration_01_qa_prompt.log
│   └── claude_questions.txt
├── integration_issues.json           # Integration check output
├── artifact_manifest.json            # File checksums
└── build_state.json                  # Run metadata
```

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

## Critical Patterns

### Artifact Extraction
- Pattern: `**FILE: path/to/file.ext**` header + code fence
- Handled by `ArtifactManager.extract_artifacts()`
- Boilerplate files: `business/frontend/pages/*.jsx`, `business/backend/routes/*.py`

### Multipart Output
- Claude may split large builds: `<!-- PART 1/3 -->...<!-- END PART 1/3 -->`
- Harness concatenates parts; falls back to continuation prompts on truncation
- Detection: `detect_truncation()`, `detect_multipart()`

### Defect Injection
- QA report → `PREVIOUS_DEFECTS` block in next BUILD prompt
- QA defects must include `Fix:` field (exact code change, not just description)
- QA defects must include `Evidence:` field (exact wrong line quoted verbatim — no quote = invalid defect)
- Enrichment: `_enrich_defects_with_fix_context()` prepends architectural guidance for boilerplate patterns

### Wrong-Path File Salvage
- Pruner detects files Claude generated in wrong paths (e.g. `app/api/foo.py`)
- If a valid-path equivalent exists → prune duplicate, keep correct one
- If NO equivalent exists → remap to correct `business/` path (never discard)
- Handled by `ArtifactManager._remap_to_valid_path()` + `prune_non_business_artifacts()`

### Warm-Start Resume
- Use `--resume-run` to reuse an existing run dir after a 429 kill
- `qa` mode: loads existing build output, skips Claude BUILD, runs fresh QA
- `fix` mode: loads existing QA report as defects, starts Claude fix at N+1
- `consistency` mode: re-runs AI consistency check on existing artifacts
- Loop start iteration is set to `--resume-iteration` (not always 1)

### ChatGPT 429 Handling
- Reads `Retry-After` header and waits exactly that long when present
- Falls back to exponential backoff + jitter: `RETRY_SLEEP * 2^attempt` capped at 60s
- 60s TPM cooldown injected before QA call on iteration 2+ (TPM window reset)

### Boilerplate Decision
- Default: `/Users/teebuphilip/Documents/work/teebu-saas-platform`
- Skipped when `--tech-stack lowcode` (Zapier/Shopify intake)
- Hard-prohibited: dict storage, sequential IDs, hardcoded data

### Token / Timeout Strategy
- Max tokens: 16384 (full regeneration each iteration)
- Timeout: 600s first call (caching overhead), 300s subsequent

---

## Config Override Files

| File | Controls |
|------|---------|
| `fo_tech_stack_override.json` | Tech stack defaults (Next.js, Prisma, etc.) |
| `fo_external_integration_override.json` | Rules for Stripe, auth, etc. |
| `fo_qa_override.json` | QA behavior adjustments |

---

## Prompt Templates

Modular prompts live in `directives/prompts/` (17 markdown files):
- `build_*.md` — Build iteration prompts
- `qa_prompt.md` — QA validation prompt
- `build_patch_first_file_lock.md` — Defect fix iteration (locks first file)

Loaded by `DirectiveTemplateLoader`; hardcoded fallbacks in `PromptTemplates`.

---

## Cost Tracking

| File | Contains |
|------|---------|
| `fo_run_log.csv` | Claude + ChatGPT costs per build run |
| `deploy/deploy_ai_costs.csv` | Deploy pipeline AI costs |
| `munger/munger_ai_costs.csv` | Munger AI costs |
| `ai_costs_aggregated.csv` | Merged all costs |

Run `python aggregate_ai_costs.py` to refresh aggregates.

---

## Dependencies

No `requirements.txt`. Install manually:
```bash
pip install anthropic openai requests
```

Required env vars: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`
For deploy: `GITHUB_TOKEN`, `GITHUB_USERNAME`, `RAILWAY_TOKEN`, `VERCEL_TOKEN`

---

## Important Docs

| File | Read for |
|------|---------|
| `README.md` | Quick start + troubleshooting |
| `AGENTS.md` | Agent operating instructions |
| `changelog.md` | Recent changes — **always update after each session** |
| `must-port-to-fo.md` | Changes in harness not yet in FO production — **always update + evaluate** |
| `learnings-from-af-to-fo.md` | Root cause lessons — **always update with new findings** |
| `intake/README.md` | Intake generation details |
| `FO_ARTIFACT_FORMAT_RULES.txt` | File formatting standards Claude must follow |
| `FO_BOILERPLATE_INTEGRATION_RULES.txt` | Boilerplate constraints |

## Standing Rules for This Codebase

- **After every session:** update `changelog.md` with what changed.
- **After every code/prompt change:** evaluate whether it belongs in `must-port-to-fo.md` (harness-only fix or needs FO port) and `learnings-from-af-to-fo.md` (new root cause or pattern).
- **Never port to FO production** until builds are proven working through a full run set. Port sequence to be determined after ~70 builds.
