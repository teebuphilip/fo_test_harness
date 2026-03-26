# CLAUDE.md — FO_TEST_HARNESS

## SESSION STARTUP — DO THIS FIRST, EVERY TIME

```bash
# 1. Confirm location
pwd   # must be inside fo-test-harness repo root

# 2. Check APIs are live + TPM headroom
python check_openai.py

# 3. Confirm governance ZIP exists
ls FOBUILFINALLOCKED*.zip

# 4. Confirm boilerplate exists
ls /Users/teebuphilip/Documents/work/teebu-saas-platform/saas-boilerplate/

# 5. Read last 5 changelog entries to know where previous session left off
tail -80 changelog.md
```

Do not touch code until all 5 steps are done.

---

## WHAT THIS REPO DOES

End-to-end pipeline: Intake JSON → Claude builds full-stack code → ChatGPT QA validates → deploy to Railway + Vercel.

- **Builder**: Claude (Anthropic)
- **Validator**: ChatGPT (OpenAI)
- **Loop**: Defects feed back into Claude until clean or max iterations (default 20)

---

## THREE-STAGE PIPELINE

| Stage | Entry Point | Purpose |
|-------|-------------|---------|
| 1. Intake | `intake/generate_intake.sh` | Founder answers → structured intake JSON |
| 2. Build-QA | `run_integration_and_feature_build.sh` | Phase-by-phase BUILD + QA + integration check |
| 2b. Build-QA (quality) | `run_slicer_and_feature_build.sh` | Slice-by-slice BUILD + QA + integration check |
| 3. Deploy | `deploy/zip_to_repo.py` → `deploy/pipeline_deploy.py` | ZIP → GitHub → Railway / Vercel |
| 4. Post-Deploy QA | `post-deploy-qa/trigger_qa.py` | Newman + Playwright tests against deployed app |

**Auto-route between phase and slice:** `run_auto_build.sh` calls `planner_router.py` to decide.

---

## SEQUENCE FLOW (what runs in what order)

```
Intake JSON
    ↓
Stage 1: python check_openai.py          ← API readiness + TPM headroom
    ↓
Stage 2: python phase_planner.py --intake <file>
    ↓ outputs: <stem>_phase_assessment.json
    ↓          <stem>_phase1.json + <stem>_phase2.json (if 2-phase)
    ↓
Stage 3: run_integration_and_feature_build.sh (or slice/auto variant)
    → phase_planner.py splits intake into data layer + feature list
    → builds Phase 1 (data layer: models, auth, core routes)
    → for each intelligence feature:
        feature_adder.py → scoped intake → fo_test_harness.py → integration_check.py
        up to 2 fix passes per feature
    → merges all ZIPs → final deliverable
    → generate_business_config.py runs post-merge (scans built pages, writes business_config.json)
    ↓
Stage 4: deploy/zip_to_repo.py → deploy/pipeline_deploy.py
    ↓
Stage 5 (optional): post-deploy-qa/generate_tests.py → trigger_qa.py
```

---

## COMMON WORKFLOWS

### New greenfield build (standard)
```bash
cd intake && ./generate_intake.sh hero_text/<startup>.json && cd ..
./run_integration_and_feature_build.sh \
  --intake intake/intake_runs/<startup>/<startup>.json \
  --startup-id <startup>
```

### New greenfield build (quality/slice mode)
```bash
./run_slicer_and_feature_build.sh \
  --intake intake/intake_runs/<startup>/<startup>.json \
  --startup-id <startup>
```

### Auto-route (let planner decide)
```bash
./run_auto_build.sh \
  --intake intake/intake_runs/<startup>/<startup>.json \
  --startup-id <startup>
```

### Factory mode (high-volume AFH catalog)
```bash
./run_integration_and_feature_build.sh \
  --intake intake/intake_runs/<startup>/<startup>.json \
  --startup-id <startup> \
  --mode factory
# Shell translates to --factory-mode for harness
# Caps iterations at 10, skips CONSISTENCY gate, relaxes QUALITY gate
```

### Add feature to existing build
```bash
# From ZIP
./add_feature.sh \
  --intake intake/intake_runs/<startup>/<startup>.json \
  --feature "Feature description" \
  --existing-zip fo_harness_runs/<startup>_FINAL.zip

# From live repo (local path or GitHub URL)
./add_feature.sh \
  --intake intake/intake_runs/<startup>/<startup>.json \
  --feature "Feature description" \
  --existing-repo ~/Documents/work/<startup>
```
Flow: `feature_adder.py` → `fo_test_harness.py` → `integration_check.py` → merge → new final ZIP

### Run harness directly (manual / resume)
```bash
python fo_test_harness.py \
  intake/intake_runs/<startup>/<startup>.json \
  FOBUILFINALLOCKED100.zip \
  --max-iterations 20
```

### Deploy
```bash
python deploy/zip_to_repo.py fo_harness_runs/<startup>_BLOCK_B_full_*.zip
python deploy/pipeline_deploy.py --repo ~/Documents/work/<startup>

# Config only (no deploy, skip git push)
python deploy/pipeline_prepare.py --repo . --configs-only
```

### Generate business config with SEO
```bash
python generate_business_config.py \
  --dir /path/to/merged --intake intake.json \
  --seo seo/my_startup_seo.json   # optional
```

### Generate post-deploy tests from build artifacts
```bash
python post-deploy-qa/generate_tests.py \
  --artifacts fo_harness_runs/<startup>_BLOCK_B_*/build/iteration_19_artifacts \
  --intake intake/intake_runs/<startup>/<startup>.json \
  --output tests/
```

---

## RESUME SCENARIOS

**Run killed mid-build (429 / timeout):**
```bash
# run_integration_and_feature_build.sh — just rerun, it auto-resumes from last completed ZIP
./run_integration_and_feature_build.sh --intake my_intake.json --startup-id my_startup

# fo_test_harness.py directly
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

**Feed integration issues back in for targeted fix:**
```bash
python fo_test_harness.py my_intake.json FOBUILFINALLOCKED100.zip \
  --resume-run fo_harness_runs/my_startup_BLOCK_B_<ts> \
  --resume-iteration 19 \
  --integration-issues my_integration_issues.json
```

---

## KEY FLAGS — fo_test_harness.py

| Flag | Purpose |
|------|---------|
| `--block A\|B` | Tier 1 or Tier 2 intake block (default B) |
| `--max-iterations N` | Iteration cap (default 20) |
| `--no-polish` | Skip README / .env / tests (intermediate phases) |
| `--prior-run <dir>` | Seed QA prohibition tracker from previous run |
| `--resume-run <dir>` | Resume from existing run directory |
| `--resume-iteration N` | Which iteration to resume from |
| `--resume-mode qa\|fix\|consistency` | qa: fresh QA; fix: load QA report as defects; consistency: re-run consistency check |
| `--integration-issues <file>` | Targeted integration fix pass |
| `--factory-mode` | High-volume: cap iterations, skip CONSISTENCY, relax QUALITY |
| `--deploy` | Run deploy pipeline after build acceptance |

---

## QA GATES

Five sequential gates inside `fo_test_harness.py`, then one post-build gate:

| # | Gate | Type | What it checks |
|---|------|------|----------------|
| 1 | COMPILE | Deterministic | Python AST parse — syntax errors |
| 2 | STATIC | Deterministic | Duplicate `__tablename__`, wrong Base import, unauthenticated routes, missing methods |
| 3 | CONSISTENCY | AI (GPT-4o) | Cross-file structural: model↔service, schema↔model, route↔schema, import chains |
| 4 | QUALITY | AI (GPT-4o) | Deployability, enhanceability, completeness vs intake |
| 5 | FEATURE_QA | AI (GPT-4o) | Spec compliance, scope, functional bugs |
| 6 | INTEGRATION (post-build) | Deterministic | 15-check structural validator via `integration_check.py` |

**CONSISTENCY rule:** Pre-filter only, not the authority. After 4 consecutive CONSISTENCY failures, fall through to FEATURE_QA regardless. Never trigger a full rebuild based solely on CONSISTENCY — fix surgically, fall through. If FEATURE_QA accepts the build, the CONSISTENCY issue wasn't real.

**QUALITY gate (factory mode):** Skipped unless deployability fails. CONSISTENCY skipped entirely.

**Dual-condition exit:** Build only ACCEPTED when (1) ChatGPT verdict = ACCEPTED AND (2) zero CRITICAL/HIGH defects in structured defect list. ChatGPT saying ACCEPTED while listing defects → treated as REJECTED.

**Deflationary scoring:** QA must answer three questions before filing each defect: "What breaks? Who cares? Can I prove it?" Bias toward acceptance. Speculative or hedged defects get filtered.

---

## CONVERGENCE FEATURES — LIVE

Do not re-implement or remove any of these:

**Circuit breaker** — Three detectors inside `execute_build_qa_loop()`:
- Stagnation: artifact manifest hash unchanged 3 consecutive iterations → exit with diagnostic
- Oscillation: same defect fingerprint (location+type) repeating 5+ times → exit
- Degradation: byte count drops below 30% of previous iteration → exit
- Writes `circuit_breaker_report.json` on trigger.

**ROOT_CAUSE in triage** — `_triage_and_sharpen_defects()` emits per defect:
```
DEFECT-N:
  CLASSIFICATION: <scope|hallucination|real>
  ROOT_CAUSE: <one sentence — WHY this happened, not WHAT is wrong>
  SHARPENED_FIX: <exact code change>
```
ROOT_CAUSE injected into `build_previous_defects.md` alongside fix. Logged to `iteration_##_triage_output`.

**Bounded defect memory** — `PREVIOUS_DEFECTS` capped to last 2 iterations. Older recurring defects summarized to one line, not full evidence blocks.

**Chain-of-evidence** — QA output requires `What breaks` field per defect. Harness Check 7 in `_filter_hallucinated_defects()` validates backtick-quoted evidence snippets exist in actual artifacts. Hedge phrases ("may cause", "could lead") in `What breaks` → defect removed.

**Self-verification gate** — STEP 3 within `qa_prompt.md`: QA re-reads its own defect list before output, verifies evidence is real, "What breaks" is concrete, no duplicates, severity is honest. Updates counts; if zero survive → ACCEPTED. This is NOT a separate API call — it's part of the same QA prompt.

**Contrastive rules** — 7 VALID/INVALID example pairs in STEP 2.75 of `qa_prompt.md`. Covers: fabricated evidence, Auth0 hallucination, Fix==Evidence, absence claims, infrastructure columns, vague "What breaks", comment stubs. Teaches QA what NOT to flag based on real past hallucinations.

**Feature-level pass/fail tracking** — Phase planner and slice planner both emit `feature_state` with `acceptance_criteria` + `allowed_files` per feature. Harness loads feature state, maps defects to features by file path after each QA rejection, tracks pass/fail across iterations. Fix prompts get structured preamble: "Features passing: X. Failing: Y. Fix ONLY failing." Saves `feature_state.json` to run dir on exit.

**run_status.json** — All 11 exit paths write structured JSON (status, reason, detail, iteration, timestamp).

---

## INTEGRATION CHECK — 15 CHECKS

```bash
python integration_check.py \
  --artifacts fo_harness_runs/<startup>_BLOCK_B_<ts>/build/iteration_19_artifacts \
  --intake intake/intake_runs/<startup>/<startup>.json \
  --output my_integration_issues.json
```

| # | What it catches |
|---|-----------------|
| 1 | Frontend fetch() calls vs backend @router endpoints |
| 2 | Service model.field accesses vs Column definitions |
| 3 | Intake keywords (PDF, KPI names) missing from artifacts |
| 4 | `from business.X import Y` vs actual artifact files |
| 5 | @router decorators that repeat the filename stem |
| 6 | Routes with `Depends(get_current_user)` vs frontend Authorization headers |
| 7 | `await` called on non-async (sync) functions |
| 8 | `asyncio.gather(sync_func())` → TypeError at runtime |
| 9 | JSX imports vs `business/package.json` dependencies |
| 10 | Silent error swallow (`except:` / `except Exception: pass`) |
| 11 | `setTimeout(fn, N)` with no attempt cap → infinite loop |
| 12 | `BackgroundTasks.add_task()` with no timeout when intake has SLA |
| 13 | JSX renders `{config.section.key}` where value is a dict → `[object Object]` |
| 14 | `<button>` with no onClick (not submit), `<a href="#">` placeholder links |
| 15 | `useState` fields not in `business_config.json` form definitions → silent data loss |

False positive notes:
- Check 14: buttons inside dynamic `.map()` lists and `type="submit"` inside `<form>` are auto-skipped
- Check 10: ORM constructors excluded; targeted exclusions for dynamic framework behavior apply

---

## POST-DEPLOY QA

```
post-deploy-qa/
  generate_tests.py              # Scans build artifacts → Postman + Playwright tests
  Dockerfile                     # Playwright + Newman container
  entrypoint.py                  # Runs Newman + Playwright, writes qa_report.json
  clone_tests.sh                 # Clones test repo at container startup
  trigger_qa.py                  # Triggers Railway container, polls, extracts report
  run_post_deploy_qa.sh          # One-line wrapper
  requirements.txt               # Python deps for container
  templates/
    playwright_golden_rules.md   # Playwright best practices reference
```

**Test scaffolder** (`generate_tests.py`): Scans `business/backend/routes/*.py` for FastAPI endpoints and `business/frontend/pages/*.jsx` for React page features. Generates:
- Newman Postman collection (per-entity CRUD tests + smoke folder)
- Playwright E2E suite (smoke, auth, per-entity, dashboard tests)

```bash
python post-deploy-qa/generate_tests.py \
  --artifacts <artifacts_dir> --intake <intake.json> --output tests/
```

**QA container**: Railway one-shot container runs Newman + Playwright against deployed TARGET_URL. Prints `QA_REPORT_JSON:{json}` to stdout for `trigger_qa.py` to extract from logs.

```bash
python post-deploy-qa/trigger_qa.py \
  --target-url https://myapp.vercel.app \
  --service-id <railway-qa-service-id>
```

---

## KEY SCRIPTS

| Script | Purpose |
|--------|---------|
| `run_integration_and_feature_build.sh` | Main pipeline — greenfield phase-by-phase |
| `run_slicer_and_feature_build.sh` | Slice-based pipeline (quality mode) |
| `run_auto_build.sh` | Auto-routes to slice vs phase via `planner_router.py` |
| `add_feature.sh` | Add one feature to existing built/deployed repo |
| `fo_test_harness.py` | Core BUILD-QA orchestrator (~4000+ lines) |
| `integration_check.py` | 15-check deterministic post-build validator |
| `phase_planner.py` | Splits intake into data layer + intelligence feature list |
| `slice_planner.py` | Builds vertical slice plans + runnable slice intakes (`--extra-repair` for second repair pass) |
| `planner_router.py` | Recommends slice vs phase for a given intake |
| `feature_adder.py` | Scoped feature intake from existing ZIP or repo |
| `generate_business_config.py` | Post-merge config generator — scans built pages, writes `business_config.json`; `--seo` flag for optional SEO merge |
| `check_openai.py` | Pre-run API health check (Claude + OpenAI, TPM quota) |
| `check_boilerplate_fit.py` | Checks if intake suits boilerplate (YES/NO + file list) |
| `check_final_zip.py` | Static + integration checks on final merged ZIP |
| `aggregate_ai_costs.py` | Merges all cost CSVs |
| `cleanup_fo_harness_runs.py` | Reduces disk usage — keeps ZIPs + last N run dirs |
| `summarize_harness_runs.py` | Generates run summary table from `fo_run_log.csv` |
| `deploy/zip_to_repo.py` | ZIP → git init → GitHub push |
| `deploy/pipeline_deploy.py` | Full deploy orchestrator (Railway + Vercel) — writes timestamped run log |
| `deploy/pipeline_prepare.py` | Config-only mode (AI config gen + git push, no deploy) |
| `post-deploy-qa/generate_tests.py` | Auto-generate Postman + Playwright tests from build artifacts |
| `post-deploy-qa/trigger_qa.py` | Trigger QA container on Railway, poll, extract report |
| `munger/munger.py` | Spec quality scorer |
| `munger/munger_ai_fixer.py` | AI-based spec quality fix loop |

---

## fo_test_harness.py — CLASS MAP

Line numbers are approximate — they shift as code changes.

| Class | ~Line | Role |
|-------|-------|------|
| `Config` | ~36 | Static config: models, token limits, timeouts |
| `ClaudeClient` | ~452 | Anthropic API wrapper with retry + backoff |
| `ChatGPTClient` | ~564 | OpenAI API wrapper with Retry-After + exponential backoff |
| `ArtifactManager` | ~647 | Extracts `**FILE: path**` artifacts; remaps wrong-path files |
| `DirectiveTemplateLoader` | ~425 | Loads prompt markdown files from `directives/prompts/` |
| `PromptTemplates` | ~1130 | Prompt construction (600+ lines) |
| `FOHarness` | ~1800 | Main orchestrator; `execute_build_qa_loop()` entry |

**Key FOHarness methods:**
- `execute_build_qa_loop()` — main iteration loop (circuit breaker + feature tracking live here)
- `run_claude_build()` — calls Claude for BUILD
- `run_chatgpt_qa()` — calls ChatGPT for QA
- `_enrich_defects_with_fix_context()` — adds architectural guidance to defects
- `_triage_and_sharpen_defects()` — post-QA rejection: CLASSIFICATION + ROOT_CAUSE + SHARPENED_FIX per defect
- `_filter_hallucinated_defects()` — 7 checks: out-of-scope files, fabricated evidence, comment-only evidence, chain-of-evidence, hedge phrases
- `_apply_patch_recovery()` — recovers missing files
- `_validate_pre_qa()` — pre-QA checks

---

## CRITICAL PATTERNS (read before touching harness code)

**Artifact extraction:** `**FILE: path/to/file.ext**` header + code fence. Handled by `ArtifactManager.extract_artifacts()`. Boilerplate files live under `business/frontend/pages/*.jsx` and `business/backend/routes/*.py`.

**Multipart output:** Claude may split large builds with `<!-- PART 1/3 -->...<!-- END PART 1/3 -->`. Harness concatenates parts; falls back to continuation prompts on truncation. Detection: `detect_truncation()`, `detect_multipart()`.

**Defect injection:** QA report → `PREVIOUS_DEFECTS` block in next BUILD prompt. Every defect must have a `Fix:` field (exact code change) and an `Evidence:` field (exact wrong line quoted verbatim). No quote = invalid defect. Capped to last 2 iterations.

**Wrong-path file salvage:** If Claude generates files in wrong paths (e.g. `app/api/foo.py`): if a valid-path equivalent exists → prune duplicate; if no equivalent exists → remap to correct `business/` path, never discard. Handled by `ArtifactManager._remap_to_valid_path()`.

**Boilerplate default:** `/Users/teebuphilip/Documents/work/teebu-saas-platform`. Skipped when `--tech-stack lowcode`. Hard-prohibited: dict storage, sequential IDs, hardcoded data.

**Token / timeout:** Max tokens: 16384. Timeout: 600s first call, 300s subsequent.

**ChatGPT 429:** Reads `Retry-After` header; waits exact duration. Falls back to exponential backoff + jitter capped at 60s. 60s TPM cooldown injected before QA call on iteration 2+.

---

## PROMPT TEMPLATES

Modular prompts in `directives/prompts/` (17 markdown files):
- `build_*.md` — Build iteration prompts
- `qa_prompt.md` — QA validation prompt (includes deflationary scoring at STEP 2.5, contrastive rules at STEP 2.75, chain-of-evidence in OUTPUT FORMAT, self-verification at STEP 3)
- `build_patch_first_file_lock.md` — Defect fix iteration (locks first file)
- `build_ai_consistency.md` — CONSISTENCY gate prompt
- `build_quality_gate.md` — QUALITY gate prompt

Loaded by `DirectiveTemplateLoader`. Hardcoded fallbacks in `PromptTemplates` for all critical prompts.

---

## OUTPUT STRUCTURE

```
fo_harness_runs/<startup>_BLOCK_B_<timestamp>/
├── build/
│   ├── iteration_01_build.txt
│   ├── iteration_01_artifacts/         # Extracted files (business/**)
│   └── iteration_02_fix.txt
├── qa/
│   └── iteration_01_qa_report.txt
├── logs/
│   ├── iteration_01_build_prompt.log
│   ├── iteration_01_qa_prompt.log
│   ├── iteration_01_triage_output      # ROOT_CAUSE + CLASSIFICATION + SHARPENED_FIX per defect
│   └── claude_questions.txt
├── integration_issues.json
├── artifact_manifest.json
├── build_state.json
├── feature_state.json                  # Feature-level pass/fail tracking
└── run_status.json                     # Structured exit status (all 11 paths)
```

---

## CONFIG OVERRIDES

| File | Controls |
|------|---------|
| `fo_tech_stack_override.json` | Tech stack defaults (Next.js, Prisma, etc.) |
| `fo_external_integration_override.json` | Rules for Stripe, auth, external APIs |
| `fo_qa_override.json` | QA behavior adjustments |

---

## ENV VARS

```bash
# Required for build
export ANTHROPIC_API_KEY=sk-ant-xxxxx
export OPENAI_API_KEY=sk-xxxxx

# Required for deploy
export GITHUB_TOKEN=ghp_xxxxx
export GITHUB_USERNAME=yourname
export RAILWAY_TOKEN=xxxxx
export VERCEL_TOKEN=xxxxx
```

---

## COST TRACKING

| File | Contains |
|------|---------|
| `fo_run_log.csv` | Claude + ChatGPT costs per build run |
| `deploy/deploy_ai_costs.csv` | Deploy pipeline AI costs |
| `munger/munger_ai_costs.csv` | Munger AI costs |
| `ai_costs_aggregated.csv` | All costs merged |

```bash
python aggregate_ai_costs.py
python summarize_harness_runs.py
python cleanup_fo_harness_runs.py --runs-dir fo_harness_runs --keep 5 --dry-run
python cleanup_fo_harness_runs.py --runs-dir fo_harness_runs --keep 5 --apply
```

---

## DEPLOY NOTES

- `deploy/pipeline_deploy.py` writes timestamped run log to `deploy/pipeline-deploy-logs/`
- Railway backend deploy reuses or generates a public `*.up.railway.app` domain automatically
- Resolved backend URL is injected into the Vercel frontend deploy
- `deploy/pipeline_prepare.py --repo . --configs-only` skips git push entirely

---

## SAFETY RULES — NON-NEGOTIABLE

- Never commit or expose API keys. Keys in env vars only.
- Treat `.claude/settings.local.json` as sensitive — never copy keys from it.
- Do not modify `fo_harness_runs/` or `boilerplate_checks/` unless explicitly asked.
- Always commit `fo_run_log.csv` when it changes.
- Preserve build artifacts and QA logs when changing the harness.
- Outside of actual builds, default to ChatGPT to control costs.
- Never port to FO production until builds are proven through a full run set.

---

## OPEN TODO — DO NOT IMPLEMENT WITHOUT EXPLICIT YES

**Next after validation builds:**
- Targeted re-audit on modified files only (1.4) + Reference-first QA judging (3.1) — big change, validate current fixes first
- Pydantic output contracts (2.3) — big rewrite, hold

**Later (Week 5+):**
- Pre-build file manifest contract (2.1)
- De-sloppify pass (2.2) — needed for AFH production, not harness
- Separate Reflexion call (1.2) — evaluate after ROOT_CAUSE triage proves out

**Known risks:**
- Feature ZIP lookup uses broad `startup_idea_id` slug — if IDs reused, wrong ZIP selected. Scope to current intake/run.
- Static-check false positives: every new static rule must be validated against known-good artifacts before enabling. Per-check kill-switch needed.
- Gate 4 dedup: QUALITY defects should be de-duped against Gate 2/3 fingerprints before fix payloads.

---

## END OF SESSION — DO THIS EVERY TIME

1. Update `changelog.md` with what changed this session.
2. Every code/prompt change: does it belong in `must-port-to-fo.md`? Update if yes.
3. Every new failure pattern: does it belong in `learnings-from-af-to-fo.md`? Update if yes.

---

## REFERENCE DOCS (read only when specifically needed)

| File | Read for |
|------|---------|
| `FO_TEST_HARNESS_README.md` | Quick start, troubleshooting, full pipeline docs |
| `AGENTS.md` | Agent operating instructions summary |
| `FO_ARTIFACT_FORMAT_RULES.txt` | File formatting standards Claude must follow |
| `FO_BOILERPLATE_INTEGRATION_RULES.txt` | Boilerplate constraints |
| `intake/README.md` | Intake generation details |
| `learnings-from-af-to-fo.md` | Root cause lessons and recurring patterns |
| `must-port-to-fo.md` | Harness changes not yet in FO production |
| `sequence-flow-long.md` | Detailed phase planning sequence with exact command examples |
| `fixme.md` | Full steal report — all convergence/QA improvements + implementation status |
| `post-deploy-qa/README.md` | Post-deploy QA container + test scaffolder docs |
