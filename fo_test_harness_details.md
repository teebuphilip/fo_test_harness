# FO Test Harness — Technical Details

This document explains how `fo_test_harness.py` works internally and how to operate advanced flows. For quick-start usage, see `FO_TEST_HARNESS_README.md`. For the interview-friendly overview, see `fo_test_harness_details_short.md`.

---

## 0. Pre-Intake Gap Analysis (Pass0)

Before intake, use the gap-analysis pipeline to convert raw ideas into a build-ready brief and hero JSON:

```
./gap-analysis/run_full_pipeline.sh /path/to/preintake.json --verbose
```

Outputs:
- `gap-analysis/outputs/*_business_brief.json`
- `intake/ai_text/<picked_name>.json`

See `gap-analysis/README_DETAILED.md` for the full flow.

## 0.05 Munger (Hero Answers QA)

Run the munger full loop on the hero JSON before intake:

```
./munger/run_munger_full.sh intake/ai_text/<picked_name>.json
```

Outputs:
- `munger/<picked_name>.munged.json` (use this as the hero JSON for intake)
- `munger/<picked_name>_munger_out.json`
- `munger/<picked_name>_munger_ai_fixed.json`

## 0.1 Intake QA + Boilerplate Fit

After intake generation, run boilerplate fit and grill-me QA:

```
python check_boilerplate_fit.py intake/intake_runs/<startup>/<startup>.json
cd intake
./grill_me.sh intake_runs/<startup>/<startup>.json
```

Notes:
- `check_boilerplate_fit.py` uses a slim manifest (exact high-signal files only) and logs prompt size.
- `grill_me.sh` defaults to block B only, auto-resume, and auto-answer with Stripe-only assumptions and minimal roles/edge cases.

## 0.2 Run Analysis (Post-Build)

After builds complete, use the run analysis tool to mine QA defects, integration issues,
and iteration counts into summary reports.

```
# Global summary
python analyze_runs.py

# Per-startup summaries (prefix match)
./analyze_by_prefix.sh invoicetool
```

Outputs:
- `analysis_output/runs_summary.json`
- `analysis_output/failure_patterns.txt`
- `analysis_output/gate_breakdown.csv`
- `analysis_output/iteration_heatmap.csv`
- `analysis_output/qa_report.md`

## 1. Architecture Overview

The harness orchestrates two competing AI systems in a GAN-like loop:

```
                    ┌──────────────────────────────────────────┐
                    │           fo_test_harness.py             │
                    │                                          │
  Intake JSON ────► │  ┌─────────┐     ┌──────────┐          │
  Governance ZIP ──►│  │  Claude  │────►│ ChatGPT  │          │
                    │  │ (build)  │◄────│  (QA)    │          │
                    │  └─────────┘     └──────────┘          │
                    │       │               │                  │
                    │       ▼               ▼                  │
                    │  ┌─────────────────────────────┐        │
                    │  │   5 QA Gates (sequential)    │        │
                    │  │   Circuit Breaker (3 detectors)│      │
                    │  │   Defect Filter (7 checks)    │      │
                    │  │   Feature State Tracker        │      │
                    │  └─────────────────────────────┘        │
                    │       │                                  │
                    │       ▼                                  │
                    │  Accepted? ──YES──► ZIP + deploy        │
                    │       │                                  │
                    │      NO                                  │
                    │       │                                  │
                    │       ▼                                  │
                    │  Triage → ROOT_CAUSE → Scoped Fix       │
                    │  (loop back to Claude)                   │
                    └──────────────────────────────────────────┘
```

**Key design decisions:**
- Claude builds, ChatGPT validates — adversarial separation prevents self-validation bias
- Every defect must carry verbatim evidence + concrete "What breaks" — no speculative bugs
- Fix iterations are scoped to failing features only — passing features are locked
- Three independent circuit breakers halt non-converging loops before burning money

---

## 2. AI Call Flow

### Claude Build Calls

- **Endpoint**: Anthropic Messages API (`/v1/messages`)
- **Prompt structure**: Governance ZIP contents (cached) + intake JSON + iteration context
- **Prompt caching**: First message block marked cacheable via `anthropic-beta: prompt-caching-2024-07-31` — governance rules are ~50K tokens, cached after first call
- **Output cap**: 16,384 tokens per response
- **Timeout**: 600s first call (cache warm-up), 300s subsequent
- **Retry**: Exponential backoff on 429/500/529, up to 3 attempts

### Claude Multipart Recovery

Large builds exceed the output token limit. Claude is instructed to split output:

```
<!-- PART 1/3 -->
**FILE: business/models/clients.py**
...code...
<!-- END PART 1/3 -->
REMAINING FILES: services/clients_service.py, routes/clients.py
```

The harness:
1. Detects `PART X/N` markers via `detect_multipart()`
2. Requests subsequent parts using `directives/prompts/part_prompt.md`, passing files already received + remaining list
3. Appends each part to build output
4. Stops when `BUILD STATE: COMPLETED_CLOSED` appears or `--max-parts` (default 10) is hit

### Fallback Continuation Recovery

If no multipart markers but output is truncated (no `COMPLETED_CLOSED`, unclosed code blocks):
1. `detect_truncation()` flags the output
2. Harness requests continuation via `directives/prompts/continuation_prompt.md` with last 1500 chars of previous output
3. Continuation appended with `<!-- CONTINUATION -->` separator
4. Stops when `COMPLETED_CLOSED` appears or `--max-continuations` (default 9) is hit

### ChatGPT QA Calls

- **Endpoint**: OpenAI Chat Completions API
- **Model**: `gpt-4o` (default); `gpt-4o-mini` available for high-TPM scenarios
- **429 handling**: Reads `Retry-After` header, waits exact duration. Falls back to exponential backoff + jitter capped at 60s
- **TPM cooldown**: 60s delay injected before QA call on iteration 2+ (TPM window reset)
- **Response parsing**: Extracts `QA STATUS: ACCEPTED` or `QA STATUS: REJECTED` + structured defect blocks

---

## 3. The Five QA Gates

Gates run sequentially inside `execute_build_qa_loop()`. Any gate failure → targeted fix → back to Gate 1.

| Order | Gate | Type | What It Does | Failure Action |
|-------|------|------|--------------|----------------|
| 1 | COMPILE | Deterministic | Python AST parse of every `.py` artifact | `defect_source='static'` → patch prompt |
| 2 | STATIC | Deterministic | 10+ checks: duplicate `__tablename__`, wrong Base import, unauthenticated routes, missing methods, async misuse | `defect_source='static'` → patch prompt |
| 3 | CONSISTENCY | AI (Claude Sonnet) | Cross-file structural checks: model↔service field names, schema↔model alignment, route↔schema contracts, import chain resolution | `defect_source='consistency'` → surgical fix. Falls through to Gate 5 after 4 consecutive failures |
| 4 | QUALITY | AI (GPT-4o) | Deployability, enhanceability, completeness vs intake spec | `defect_source='quality'` → targeted fix |
| 5 | FEATURE_QA | AI (GPT-4o) | Full spec compliance, scope verification, functional bug detection, security review | `defect_source='qa'` → enriched fix with architectural context |

**Gate locks**: Once a gate passes, it's locked for the current run. Unlock only when relevant files change. COMPILE and STATIC are never locked (cheap + mandatory).

**Factory mode** (`--factory-mode`): CONSISTENCY skipped entirely. QUALITY only checks deployability. Iteration cap reduced to 10.

---

## 4. Defect Lifecycle

```
QA Report (raw)
    ↓
_filter_hallucinated_defects()     ← 7 removal checks
    ↓
Dual-condition exit check          ← ACCEPTED + defects = override to REJECTED
    ↓
_triage_and_sharpen_defects()      ← CLASSIFICATION + ROOT_CAUSE + SHARPENED_FIX
    ↓
_update_feature_state()            ← map defects to features by file path
    ↓
_enrich_defects_with_fix_context() ← add boilerplate patterns, architecture notes
    ↓
_build_feature_preamble()          ← "Passing: X. Failing: Y. Fix ONLY failing."
    ↓
BUILD prompt (Claude)              ← scoped to failing feature files only
```

### Hallucination Filter (7 Checks)

`_filter_hallucinated_defects()` runs after every QA report, before defects are acted on:

| # | Check | Removes If |
|---|-------|-----------|
| 1 | Out-of-scope location | Location doesn't start with `business/` |
| 2 | Banned evidence phrases | Evidence contains "N/A", "not applicable", "presence confirmed" etc. |
| 3 | Fabricated evidence | Backtick-quoted evidence (>8 chars) not found in actual build output |
| 4 | Presence claims | QA claims files missing but they exist in artifacts |
| 5 | Already-handled | Defect matches a previously resolved item |
| 6 | Comment-only evidence | ALL evidence snippets are comments (`#` or `//`) |
| 7 | Chain-of-evidence | No backtick-quoted code snippet in Evidence, OR "What breaks" uses hedge phrase ("may cause", "could lead", "potentially") |

If all defects removed → verdict flipped to ACCEPTED. Raw report saved to logs/ for audit.

### Triage and Sharpening

`_triage_and_sharpen_defects()` runs after Feature QA rejection:

- **CLASSIFICATION**: `scope` (out of scope), `hallucination` (QA made it up), or `real` (legitimate defect)
- **ROOT_CAUSE**: One sentence — WHY this happened, not WHAT is wrong. Injected into fix prompt so Claude understands the pattern, not just the symptom.
- **SHARPENED_FIX**: Exact code change with file path and line context
- **Strategy**: `surgical` (default, patch specific files) or `systemic` (full rebuild with architectural direction, rare)

### Feature-Level Tracking

Defects are mapped to features by matching file paths against `allowed_files` in the feature state:

```json
{
  "feature": "Client Profile Management",
  "entity": "clients",
  "status": "failing",
  "allowed_files": [
    "business/models/clients.py",
    "business/schemas/clients.py",
    "business/services/clients_service.py",
    "business/backend/routes/clients.py",
    "business/frontend/pages/ClientsPage.jsx"
  ],
  "acceptance_criteria": [
    "SQLAlchemy model class exists with appropriate Columns",
    "CRUD service has create/get/list/update/delete methods",
    "FastAPI routes expose GET/POST/PUT/DELETE endpoints"
  ]
}
```

Fix prompts only target failing feature files. Passing features are locked — Claude cannot touch them.

---

## 5. Convergence Protection

### Circuit Breaker (3 Detectors)

Lives inside `execute_build_qa_loop()`. Any trigger → exit with diagnostic report.

| Detector | Trigger | What It Means |
|----------|---------|---------------|
| Stagnation | Artifact manifest hash unchanged 3 consecutive iterations | Claude is outputting the same code — stuck |
| Oscillation | Same defect fingerprint (hash of location+classification) appears 5+ times | Fix/reflag cycle — defect is unfixable or hallucinated |
| Degradation | Byte count drops below 30% of previous iteration | Claude is destroying prior work in fix attempts |

On trigger: writes `circuit_breaker_report.json` with detector name, evidence, iteration history. Saves `run_status.json` with status `CIRCUIT_BREAKER`.

### Bounded Defect Memory

`PREVIOUS_DEFECTS` in the BUILD prompt is capped to the last 2 iterations. Older recurring defects get summarized to one line ("DEFECT-3: clients.py missing tenant_filter — recurring since iter 4"). This prevents prompt bloat and keeps Claude focused on current issues.

### Dual-Condition Exit

ChatGPT verdict = `ACCEPTED` but structured defect list contains CRITICAL or HIGH severity items → override to `REJECTED`. Prevents "ACCEPTED with caveats" from ending the loop prematurely.

---

## 6. Resuming Builds

### Auto-Resume (Shell Scripts)

`run_integration_and_feature_build.sh` detects which ZIPs already exist and picks up where it left off. Just rerun the same command.

### Manual Resume (fo_test_harness.py)

| Flag Combo | What Happens |
|------------|-------------|
| `--resume-run <dir>` | Reuse existing run directory (no new run created) |
| `--resume-run <dir> --resume-iteration N` | Start loop at iteration N |
| `--resume-run <dir> --resume-iteration N --resume-mode qa` | Load existing build artifacts from iter N, run fresh QA (skip Claude BUILD) |
| `--resume-run <dir> --resume-iteration N --resume-mode fix` | Load QA report from iter N as defects, start Claude fix at iter N+1 |
| `--resume-run <dir> --resume-iteration N --resume-mode consistency` | Re-run AI consistency check on existing iter N artifacts |
| `--resume-run <dir> --resume-iteration N --integration-issues <file>` | Targeted integration fix — routes to `integration_fix_prompt()` which passes actual file contents |

**Critical**: Integration issues must use `defect_source='integration'`, NOT `'static'`. The static route doesn't pass current file contents — Claude reconstructs from memory → wrong imports → 12+ iteration churn.

---

## 7. Feature Layering

Recommended flow for multi-feature builds:

```
Phase 1 (data layer) ──► ZIP accepted
    ↓
Feature 1: feature_adder.py → scoped intake
    → fo_test_harness.py --prior-run <phase1_run> --no-polish
    → integration_check.py → fix pass if needed
    → ZIP accepted
    ↓
Feature 2: feature_adder.py → scoped intake (using Feature 1 ZIP as manifest)
    → fo_test_harness.py --prior-run <feature1_run> --no-polish
    → integration_check.py → fix pass if needed
    → ZIP accepted
    ↓
Feature N (last): same flow, but DROP --no-polish → generates README, .env, tests
    ↓
Merge all ZIPs → final deliverable
    → generate_business_config.py --dir <merged> --intake <intake> [--seo <seo.json>]
```

`--prior-run` seeds the QA prohibition tracker so QA doesn't re-flag issues already accepted in previous features.

---

## 8. Slice Pipeline (Quality Mode)

Alternative to phase pipeline — builds end-to-end vertical slices instead of horizontal layers.

**Entry points:**
- `run_slicer_and_feature_build.sh` — runs `slice_planner.py`, builds each slice, integration check, merge
- `run_auto_build.sh` — auto-routes via `planner_router.py` (override with `--force slice|phase`)

**Slice planner outputs:**
- Per-slice intake JSON with `acceptance_criteria`, `allowed_files`, `file_contract`
- Slice assessment with complexity scoring and dependency ordering

**Extra repair:** `slice_planner.py --extra-repair` adds one bounded repair pass before strict validation. Useful for complex slices that need a second chance.

**Path convention:** Both planners emit full `business/...` paths (e.g. `business/backend/routes/clients.py`). The harness reads these directly — no translation needed.

---

## 9. Post-Build Pipeline

After the build loop accepts:

### Integration Check (Deterministic)
`integration_check.py` runs 15 structural checks (no AI). See CLAUDE.md for full list. Used automatically by the shell pipeline scripts after each feature build.

### Business Config Generation
`generate_business_config.py` scans actual built artifacts to populate:
- Nav items (from discovered pages)
- Footer links
- Home page features
- Stripe product config
- Optional SEO data (`--seo seo/my_startup_seo.json`)

Writes `business_config.json` to all config locations (harness paths + deployed app paths).

### Post-Deploy QA (Test Generation)
`post-deploy-qa/generate_tests.py` scans built artifacts and generates:
- Newman Postman collection (per-entity API tests + smoke tests)
- Playwright E2E suite (auth, CRUD, dashboard, smoke)

These feed into the Railway QA container (`post-deploy-qa/entrypoint.py`) which runs them against the deployed app.

---

## 10. Cost Control

| Mechanism | What It Does |
|-----------|-------------|
| Prompt caching | Governance ZIP (~50K tokens) cached after first call — subsequent iterations pay only for delta |
| Defect cap | Max 6 defects per fix iteration — prevents Claude from context-stuffing |
| Circuit breaker | Halts non-converging loops before burning 20 iterations |
| Factory mode | Caps at 10 iterations, skips CONSISTENCY gate |
| Bounded memory | Only last 2 iterations in PREVIOUS_DEFECTS — prevents prompt bloat |
| TPM cooldown | 60s delay before QA on iteration 2+ — avoids 429 retry storms |

Cost tracking: `fo_run_log.csv` logs per-run Claude + ChatGPT costs. `aggregate_ai_costs.py` merges all cost CSVs.

---

## 11. Class Map

Line numbers are approximate.

| Class | ~Line | Responsibility |
|-------|-------|---------------|
| `Config` | ~36 | Static config: models, token limits, timeouts, file paths |
| `DirectiveTemplateLoader` | ~425 | Loads prompt markdown from `directives/prompts/`, renders template variables |
| `ClaudeClient` | ~452 | Anthropic API wrapper: retry, backoff, prompt caching, multipart assembly |
| `ChatGPTClient` | ~564 | OpenAI API wrapper: Retry-After parsing, exponential backoff, TPM cooldown |
| `ArtifactManager` | ~647 | Extracts `**FILE: path**` artifacts from Claude output, remaps wrong-path files, prunes duplicates |
| `PromptTemplates` | ~1130 | Constructs all prompts (build, fix, QA, consistency, quality, integration fix) — 600+ lines |
| `FOHarness` | ~1800 | Main orchestrator: `execute_build_qa_loop()`, all gate logic, circuit breaker, feature tracking, triage |

### Key FOHarness Methods

| Method | Purpose |
|--------|---------|
| `execute_build_qa_loop()` | Main iteration loop — gates, circuit breaker, feature state, defect routing |
| `run_claude_build()` | Sends BUILD/FIX call to Claude, handles multipart + continuation |
| `run_chatgpt_qa()` | Sends QA call to ChatGPT, parses verdict + defects |
| `_filter_hallucinated_defects()` | 7-check post-QA filter — removes fabricated/speculative defects |
| `_triage_and_sharpen_defects()` | CLASSIFICATION + ROOT_CAUSE + SHARPENED_FIX per defect |
| `_enrich_defects_with_fix_context()` | Adds boilerplate architectural guidance to defects |
| `_apply_patch_recovery()` | Recovers files Claude dropped during fix iterations |
| `merge_forward_from_previous_iteration()` | Copies previous-iteration files Claude didn't touch in patch output |
| `build_synthetic_qa_output()` | Gives QA the full merged artifact set, not Claude's partial patch output |
| `_validate_pre_qa()` | Pre-QA sanity checks before sending to ChatGPT |
| `_save_run_status()` | Writes structured JSON exit status — all 11 exit paths covered |
