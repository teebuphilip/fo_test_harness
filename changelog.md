# Changelog

## 2026-03-07

### fix: npm install before frontend compile check

- `_run_static_check()` GATE 0 frontend compile: now runs
  `npm install --prefer-offline --silent` before `npm run build`.
- Root cause: generated artifacts have no `node_modules` — vite and all
  other devDependencies are absent, causing `sh: vite: command not found`
  on every Next.js/Vite project regardless of code correctness.
- `node_modules` persists in the iteration artifacts dir between iterations
  so subsequent iterations are fast (`--prefer-offline` uses local npm cache).

## 2026-03-06

### --no-polish flag + run_phased_build.sh wrapper

- `fo_test_harness.py`: new `--no-polish` CLI flag skips `_post_qa_polish` on both
  exit paths (early consistency return and main-loop post-break). Prints
  `Polish: SKIP (--no-polish)` in run header for visibility.
- `run_phased_build.sh`: new wrapper script for phased builds.
  - Runs Phase 1 with `--no-polish` (data layer, no README/env/test generation).
  - If Phase 1 fails: stops, prints `--resume-run` instructions, exits non-zero.
  - Runs Phase 2 without flag (full polish on final intelligence layer).
  - After both phases accepted: merges Phase 1 + Phase 2 ZIPs (Phase 2 wins conflicts)
    into `fo_harness_runs/<startup>_BLOCK_<B>_phased_<timestamp>.zip`.
  - Default gov ZIP baked in from last known path.
- Usage: `./run_phased_build.sh --intake-base <stem> --startup-id <id>`

### Iteration defect batching (priority-capped fix scope)

- Added per-iteration defect cap:
  - `Config.MAX_DEFECTS_PER_ITERATION = 6`
- Added `_prioritize_and_cap_defects()` to rank and trim defects before sending fix targets:
  - severity-first (`HIGH` -> `MEDIUM` -> `LOW`)
  - then runtime/contract/import blockers.
- Applied batching to compile/static/consistency/quality gate failures and warm-start defect paths.
- Added strict scope-lock header in structured defect payloads sent to Claude:
  - “Fix ONLY the defects listed below. Do NOT refactor, rename, or add features.”

### phase_planner.py: lower default threshold to 3

- `FEATURE_COUNT_THRESHOLD` changed from 5 to 3.
- Rationale: 2 phases × 3 iterations each is strictly better than 1 phase × 30 iterations
  that fails. Conservative splitting is cheaper and produces more coherent builds.
- `--threshold N` flag still available to override per-run.

### New tool: phase_planner.py

- Standalone pre-processor at project root.
- Reads an intake JSON and determines whether to build in 1 or 2 phases.
- Classification: rule-based keyword matching (DATA_LAYER vs INTELLIGENCE_LAYER);
  Claude Haiku AI fallback for ambiguous features.
- Force-2-phase signals: 3+ KPIs, 'downloadable executive report', 'trend analysis',
  'scoring engine', 'analytics dashboard', etc.
- Feature count threshold (default 5) as secondary gate.
- If 2-phase: produces `<stem>_phase1.json` (data layer only) and
  `<stem>_phase2.json` (full scope + `_phase_context` scoping block).
- Usage: `python phase_planner.py --intake <file> [--no-ai] [--threshold N]`
- Root cause: AWI convergence failures traced to single-shot generation of 8+
  interdependent features exceeding reliable first-pass coherence ceiling.

### CHECK 10 fix: exclude SQLAlchemy models from route↔service contract checks

- Updated `_run_static_check()` CHECK 10 (`Route↔service contract sanity`) to avoid false positives on ORM model classes.
- Classes are now marked as ORM models when they:
  - define `__tablename__`, or
  - inherit from `Base` or `TenantMixin`.
- For ORM model classes, CHECK 10 now skips:
  - constructor arity validation
  - method-existence validation
- This prevents invalid defects on valid SQLAlchemy usage (`ModelClass(**data)` / metaclass constructor behavior).

### Gate order update: `0 -> 2 -> 3 -> 4 -> 1` (Quality mandatory)

- Updated main gate flow in `execute_build_qa_loop()`:
  - `GATE 0` Compile
  - `GATE 2` Static deterministic checks
  - `GATE 3` AI consistency
  - `GATE 4` Quality (**mandatory**)
  - `GATE 1` Feature QA (final gate before success)
- Quality gate is now always ON in harness runtime.
- `--quality-gate` CLI option is retained as deprecated/no-op compatibility flag.

### Gate order change: `0 -> 2 -> 3 -> 1 -> 4`

- Reordered main loop gates in `execute_build_qa_loop()`:
  - `GATE 0` Compile (mandatory)
  - `GATE 2` Static deterministic checks (mandatory)
  - `GATE 3` AI consistency check (mandatory)
  - `GATE 1` Feature QA (ChatGPT)
  - `GATE 4` Quality gate (optional)
- Result: static/consistency defects are surfaced before Feature QA, so structural issues no longer wait for a prior QA acceptance.
- Added local backup copy for this edit session under `backup-20260306-3/`:
  - `fo_test_harness.py.pre_reorder`
  - `fo_test_harness.py.post_reorder`

### Fix 0 + generalized intake contracts (M/N)

- **Fix 0 (Auth0 hallucination filter)** updated in `_filter_hallucinated_defects()`:
  - Removed exact-literal dependency on `user.getAccessTokenSilently`.
  - Now suppresses Auth0 false positives when evidence shows correct `useAuth0()` + `getAccessTokenSilently`
    destructuring, even if QA paraphrases the problem text.

- **Check 11 (KPI contract) generalized** in `_run_static_check()`:
  - No longer depends on one intake schema path.
  - Recursively scans intake for KPI-like keys (`kpi_definitions`, `kpis`, `metrics`, `key_metrics`, etc.).
  - Flags missing KPI implementations in `business/services`.
  - Flags KPI duplication across multiple service files (single-source-of-truth drift risk).

- **Check 12 (download/export contract) generalized** in `_run_static_check()`:
  - No longer tied to `block_b.hero_answers`.
  - Detects downloadable/exportable requirements from full intake text.
  - Validates backend route files for both route decorators and download/export markers
    (`FileResponse`, `StreamingResponse`, `/download`, `/export`, etc.).

### Post-QA polish: ChatGPT testcase doc generation (templated directive)

Added a new post-polish output pass that generates a complete testcase document via ChatGPT:

- New directive file: `directives/qa_testcase_doc_directive.md`
- New wrapper prompt: `directives/prompts/polish_testcases_wrapper_prompt.md`
- New polish step writes: `business/docs/TEST_CASES.md`
- New CLI override:
  - `--qa-testcase-directive <path>`
  - Precedence: CLI path -> `Config.QA_TESTCASE_DIRECTIVE_FILE`
- Harness metadata now records `qa_testcase_directive_path`.

This is designed to be user-editable so scope/format requirements can be added or removed over time
without changing code.

Follow-up update:
- Testcase directive extended with explicit **Postman Suite Conversion Plan** requirements:
  - `PM-ID` mapping to testcase IDs
  - collection/folder structure guidance
  - required variables
  - pre-request auth scripts
  - test assertion scripts
  - Newman/CI execution notes

Safety update:
- Post-QA testcase-doc generation is now **non-fatal**:
  - If testcase doc generation call fails, harness logs warning and continues.
  - If testcase directive file is missing, harness warns and skips testcase-doc step.
  - Build result is not marked failed due to testcase-doc polish failure.

### Optional Gate 4: Quality gate (default OFF) + LOW-accept policy

- Added optional Gate 4 (`--quality-gate`) after AI consistency:
  - Completeness vs intake
  - Code quality
  - Enhanceability
  - Deployability
- Prompt is templatized in `directives/prompts/build_quality_gate.md`.
- LOW-accept policy enabled:
  - Gate passes if **Completeness**, **Code quality**, and **Deployability** are `PASS` or `LOW`.
  - Enhanceability remains visible in report but does not block under this policy.

### Static + QA hardening: false-negative filter narrowed, deterministic checks expanded, gate telemetry added

Implemented multi-part harness hardening to catch real integration/runtime defects earlier and surface terminal consistency issues:

- **Check 6 narrowed** in `_filter_hallucinated_defects()`:
  - Comment-only evidence is now filtered **only** when snippets explicitly indicate scope exclusion
    (e.g., "not in scope", "per intake requirements", "out of scope").
  - Prevents over-filtering legitimate missing-implementation defects.

- **`_run_static_check()` expanded** and now accepts optional intake context:
  - Signature: `_run_static_check(artifacts_dir: Path, intake_data: dict = None)`
  - Added checks for:
    - `business/backend/requirements.txt` YAML contamination path (plus existing candidates)
    - file-role mismatch (router code in `business/models/*`, executable route file with no endpoints)
    - frontend config mismatch (`next.config.js`/`postcss.config.js`/`tailwind.config.*`)
    - local import integrity (module existence, case-sensitive path alignment, imported symbol existence)
    - route↔service contract sanity (constructor arity + missing method call detection)
    - intake-aware KPI contract verification
    - intake-aware downloadable-report contract verification

- **Gate telemetry (O)** in `execute_build_qa_loop()`:
  - Added structured `gate_trace` logging for Feature QA / Static / Consistency gates.
  - Saved via `artifacts.save_log('gate_telemetry', ...)`.

- **Final consistency-on-terminal-path (I)**:
  - Added final consistency pass on terminal failure paths (`NON_CONVERGING`, `MAX_ITERATIONS`, unclear QA verdict, and post-loop non-success path).
  - Writes `final_consistency_report` log when issues are found.

- **AI consistency prompt extended** (`directives/prompts/build_ai_consistency.md`):
  - Added frontend API URL ↔ backend route integrity check.
  - Added React hook misuse check for runtime-breaking cases.

- **Call-site updates**:
  - Main static gate and warm-start static gate now pass `intake_data=self.intake_data`.
  - Standalone static mode explicitly passes `intake_data=None`.

## 2026-03-06

### Filter Check 6: comment-only evidence → stub files are intentional

**Root cause**: Claude creates stub files with Python/JS comments like
`# No endpoints - X is not in scope per intake requirements` to satisfy prior scope-boundary
QA complaints. QA then flags those same comment strings as evidence of a new scope violation
(SCOPE-BOUNDARY or SCOPE-CHANGE defect). The evidence is a code comment — not executable code.
This is always invalid.

**Fix**: Added Check 6 to `_filter_hallucinated_defects()`:
- If every meaningful backtick-quoted evidence snippet starts with `#` (Python comment) or `//` (JS comment), the defect is removed.
- Defects removed with reason: `"Comment-only evidence: all backtick snippets are code comments (...) — stub files with scope explanations are intentional"`

**Observed at**: iter 40 of `ai_workforce_intelligence_BLOCK_B_20260305_063802`
- Raw DEFECT-2: `# No endpoints - engagement tracking is not in scope per intake requirements`
- Raw DEFECT-5: `# No model - workforce data management beyond KPI calculations is not in scope`
- Raw DEFECT-7: `# No endpoints - workforce data management is not in scope per intake requirements`
All three now correctly removed. Previous 9-defect report → 3 remaining real defects.

**Docstring updated**: Check ordering now reflects actual execution order (1, 1b, 2, 3, 6, 5a, 5b, 4).

---

### Unified QA loop: Feature QA → Static → AI Consistency (all three gates must pass)

**Architecture redesign**: Replaced the nested `_run_static_fix_loop` sub-loop with a single
unified main loop. All three QA gates must pass in sequence before the build exits:

```
GATE 1: Feature QA (ChatGPT)      — spec compliance, bugs, scope
GATE 2: Static check (harness)    — deterministic: AST syntax, duplicate models, wrong imports, unauthenticated routes
GATE 3: AI Consistency (Claude)   — cross-file: model↔service fields, schema↔model, route↔schema, import chains
```

Any gate failure triggers a targeted Claude fix iteration and **restarts from GATE 1**.
No separate sub-loops. `defect_source` ('qa'|'static'|'consistency') tracks the failure source
and selects the correct prompt for the next Claude build:
- `'qa'` → full `build_prompt` with QA defects
- `'static'` → `static_fix_prompt` (targeted patch, PATCH_SET_COMPLETE contract)
- `'consistency'` → same `static_fix_prompt` format (targeted patch for consistency issues)

**New: AI Consistency check (`_run_ai_consistency_check`)**
- Calls Claude Sonnet to read all `business/` artifact files
- Checks 5 cross-file issue types: model↔service fields, schema↔model, route↔schema, import chains, duplicate subsystems
- New template: `directives/prompts/build_ai_consistency.md`
- Output: `CONSISTENCY CHECK: PASS` or structured `CONSISTENCY REPORT` with `ISSUE-N:` blocks
- Parsed by `_parse_consistency_report()`, formatted by `_format_consistency_defects_for_claude()`

**New: `--ai-check <artifacts_dir>` standalone CLI mode**
- Calls Claude directly on a `iteration_NN_artifacts/` dir, no intake/governance needed
- Requires `ANTHROPIC_API_KEY`. Exits 0 (PASS) or 1 (FAIL).
- Uses `_run_ai_consistency_check_standalone()` @staticmethod

**New: `--resume-mode consistency`**
- Like `--resume-mode static` but skips static check, goes straight to AI consistency check
- If all checks pass: polish + return True; if fail: falls through to main loop for fix iterations

**Updated: `--resume-mode static`**
- Now runs **both** static check AND AI consistency check (unified)
- If all clean: polish + return True (early exit, no main loop needed)
- If either fails: sets defect_source, falls through to main while loop

**Removed**:
- `_run_static_fix_loop()` method (logic now inline in unified loop)
- `Config.MAX_STATIC_ITERATIONS` constant
- `self.max_static_iterations` instance attr
- `--max-static-iterations` CLI flag

**Post-loop structure**:
- Loop breaks (not returns) on success or static/consistency max-iter exhaustion
- `_qa_accepted_at_iter` variable gates whether polish runs after the loop
- `_loop_success` determines return value (`True`=all three passed, `False`=max-iter during static/consistency fix)

**commit**: b936a01

## 2026-03-05

### Bugfix: _run_static_fix_loop used non-existent extract_artifacts method
`self.artifacts.extract_artifacts()` does not exist on `ArtifactManager`.
Fix: use `save_build_output(next_iter, fix_output, extract_from=...)` (saves raw + extracts)
then `extract_file_paths_from_output(fix_output_for_extraction)` for the merge_forward path list.
Same pattern as the main loop.

### Static check: standalone CLI mode + resume-mode static

Two new ways to invoke the static check from the command line:

**Standalone check (`--static-check <artifacts_dir>`):**
```bash
python fo_test_harness.py --static-check fo_harness_runs/.../build/iteration_26_artifacts
```
No intake/governance args needed. Runs all 6 static checks, prints
coloured pass/fail report, exits 0 (PASS) or 1 (FAIL). No API calls.
- Positional args made optional (`nargs='?'`) with validation that they're
  required unless `--static-check` is present.
- `_run_static_check` and `_format_static_defects_for_claude` made `@staticmethod`
  so they can be called from main() without a full FOHarness instance.

**Resume at static phase (`--resume-mode static`):**
```bash
python fo_test_harness.py intake.json build.zip deploy.zip \
  --resume-run fo_harness_runs/... \
  [--resume-iteration N]   # optional: auto-detects last ACCEPTED iter if omitted
  --resume-mode static
```
Auto-detects the last QA-ACCEPTED iteration from the run dir's `qa/` reports
(or uses `--resume-iteration N` as override). Rebuilds prohibition tracker,
builds governance_section for prompt caching, then calls `_run_static_fix_loop`
→ `_post_qa_polish` → returns. Skips the main BUILD-QA loop entirely.
- New `_find_last_accepted_iteration(run_dir)` static method.
- `--resume-mode` choices extended to `['qa', 'fix', 'static']`.

**Smoke test result (iteration 26 of ai_workforce_intelligence converged run):**
```
STATIC CHECK: FAIL — 5 defect(s)  [HIGH: 2  MEDIUM: 3]
  STATIC-1 [HIGH] business/backend/routes/client.py — Duplicate __tablename__ = "clients"
  STATIC-2 [HIGH] business/models/data_source.py — from app.models.base import Base (wrong path)
  STATIC-3 [MEDIUM] business/backend/routes/assessments.py — unauthenticated routes
  STATIC-4 [MEDIUM] business/backend/routes/kpis.py — unauthenticated routes
  STATIC-5 [MEDIUM] business/backend/routes/reports.py — unauthenticated routes
```
Confirmed: exactly the ship-blockers identified in manual review.

### Post-QA static check loop: deterministic code quality pass before polish

Root cause: Feature QA (ChatGPT) is a feature auditor, not a static analyzer. It cannot see
cross-file bugs (duplicate models, wrong imports, unauthenticated routes) and DO NOT FLAG rules
suppress legitimate code-quality issues. Build ai_workforce_intelligence iter 26 had 8 ship-blocker
bugs that QA missed: requirements.txt YAML contamination, duplicate SQLAlchemy models, missing
TenantMixin import, wrong Base import path, and fully unauthenticated backend routes.

**Pipeline change**: After Feature QA ACCEPTED, before post-QA polish, run a deterministic static
check loop (cap: `--max-static-iterations`, default 5):

**6 static checks in `_run_static_check(artifacts_dir)`:**
1. **AST syntax** — parse every .py file; SyntaxError → HIGH
2. **Duplicate `__tablename__`** — two model files share same DB table name → HIGH
3. **Missing TenantMixin import** — class inherits TenantMixin but import from core.tenancy absent → HIGH
4. **Wrong Base import** — `from app.models.base import` or raw `declarative_base()` instead of `from core.database import Base` → HIGH
5. **Requirements.txt YAML** — docker-compose YAML keys (services:, image:, etc.) in pip file → HIGH
6. **Unauthenticated routes** — backend route file has endpoints but zero `get_current_user` refs → MEDIUM

**If defects found — static fix loop:**
1. Format defects → call Claude with `build_static_fix.md` prompt (patch-first contract)
2. Truncate at PATCH_SET_COMPLETE, extract artifacts, merge forward
3. Run Feature QA — if REJECTED (fix broke feature compliance) → revert to last-good, stop loop
4. If QA ACCEPTED → run static check again → loop until clean or cap hit

**New files + methods:**
- `directives/prompts/build_static_fix.md` — thin template, same FILE:/PATCH_SET_COMPLETE contract as build_patch_first_file_lock.md, no DEFECT ANALYSIS section, boilerplate import reference
- `PromptTemplates.static_fix_prompt()` — static method; renders build_static_fix.md
- `FOHarness._run_static_check(artifacts_dir)` — returns list of defect dicts
- `FOHarness._format_static_defects_for_claude(defects)` — formats defect list for Claude prompt
- `FOHarness._run_static_fix_loop(...)` — orchestrates the loop, returns (passed, final_iter, output)
- `Config.MAX_STATIC_ITERATIONS = 5`
- `self.max_static_iterations` on FOHarness
- `--max-static-iterations` CLI flag (default 5)
- Main loop: ACCEPTED block now calls `_run_static_fix_loop()` before `_post_qa_polish()`

### Fix A: Rebuild recurring_tracker on resume (prohibition knowledge survives restart)
Root cause: `--resume-run` started a fresh process with `recurring_tracker = {}` —
12 iterations of accumulated prohibitions were silently discarded. Claude had no
constraints on iter 13 → regenerated workforce_data.py, analytics.py, etc. → 1 defect
exploded back to 6.

Fix: After the warm-start setup block, if `--resume-run` is given, scan all
`qa/iteration_*_qa_report.txt` files in the run dir and reconstruct `recurring_tracker`
(and `prohibitions_block`) before the loop starts. Console: "Warm-start tracker rebuilt:
N defect(s) tracked, M prohibition(s) active."

### Fix B: Truncate build output at PATCH_SET_COMPLETE before extraction
Root cause: Claude correctly outputs the defect-target file then `PATCH_SET_COMPLETE`,
then appends a `<!-- CONTINUATION -->` block with 10+ extra files. The harness extracted
ALL `**FILE:**` headers from the full output, overwriting good files with hallucinated
collateral. This is the collateral regression problem in its most severe form.

Fix: On patch iterations (iter > 1 with previous_defects), if `PATCH_SET_COMPLETE` is
present, build `build_output_for_extraction` = everything up to and including the marker.
Files appearing after the marker are logged as `[PATCH_SET_COMPLETE] Truncated N collateral
file(s)` and discarded. Full raw output still saved to disk for audit. `save_build_output`
gains an optional `extract_from` param. `merge_forward` and `pending_resolution` extraction
also use the truncated string so merge-forward doesn't re-import the collateral.

### Resolved defects tracker: senior dev anti-ping-pong mechanism
Root cause of Auth0 and other ping-pong defects: Claude fixes a defect, QA re-flags it next
iteration without verbatim evidence — wasting 4-6 extra iterations on already-resolved issues.

**Mechanism** (harness only, 3 new static methods + loop wiring):
- `_extract_fixed_from_patch(build_output, previous_qa)`: parses PATCH_PLAN for FIXED defect IDs,
  maps them to (location, classification, fix_text) from the previous QA report. Returns a `pending`
  set — defects Claude claims fixed, awaiting confirmation.
- `_confirm_resolutions(pending, current_qa, resolved_tracker, iteration)`: after QA filter, checks
  which pending (location, classification) pairs are ABSENT from the new QA report. Absent = confirmed
  resolved → added to `resolved_tracker`. Present = ping-pong → warns and returns as still-pending.
- `_build_resolved_defects_block(resolved_tracker)`: formats resolved list for QA injection:
  "Do NOT re-flag unless you can quote the EXACT wrong line verbatim — senior dev ruling."
- Main loop: `resolved_tracker = {}` and `pending_resolution = set()` initialized alongside
  `recurring_tracker`. After each Claude build: `_extract_fixed_from_patch` populates pending.
  After each QA + filter: `_confirm_resolutions` updates tracker. Console logs: `[RESOLVED]` on
  confirm, `[PING-PONG]` warning on re-flag, `[PENDING RESOLUTION]` on new FIXED claims.
- `qa_prompt()` method: `resolved_defects_block: str = ''` param added; passed to render.
- `qa_prompt.md`: `{{resolved_defects_block}}` placeholder added after `{{defect_history_block}}`.
  Block appears before intake requirements — QA sees the resolved list before evaluating artifacts.

### QA middle-tier: defect history, prohibition awareness, root cause classification
QA (gpt-4o-mini) had no memory — evaluated each build cold with no awareness of previous
iterations, recurring patterns, or accumulated prohibitions.

- `qa_prompt.md`: two new context blocks injected before intake:
  - `{{prohibitions_block}}`: same hard-constraint list Claude receives — QA knows what's
    already been prohibited and can flag violations immediately as PROHIBITION VIOLATED HIGH
  - `{{defect_history_block}}`: summary of all tracked defects with occurrence counts so QA
    can classify RECURRING-PATTERN vs ONE-TIME-BUG without re-evaluating from scratch
- `qa_prompt.md`: new ROOT CAUSE TYPES section (ONE-TIME-BUG | SCOPE-BOUNDARY | RECURRING-PATTERN)
- `qa_prompt.md`: new FIX FIELD RULES — SCOPE-BOUNDARY and RECURRING-PATTERN fixes must be
  categorical ("file must not contain X or any equivalent") not just "remove X"
- `qa_prompt.md`: `Root cause type:` field added to DEFECT output format
- Harness: `_build_qa_defect_history(recurring_tracker)` — formats history block from tracker
- Harness: `qa_prompt()` signature extended: `prohibitions_block`, `defect_history_block` params
- Harness: call site passes both blocks; defect_history_block built from shared recurring_tracker

### Claude thinking stage + permanent prohibitions for scope oscillation
Root cause of non-convergence: Claude acts as a junior dev fixing a ticket — removes the named
field but regenerates the same concept next iteration. No commitment step, no pattern awareness.

**Claude thinking stage** (`build_patch_first_file_lock.md`):
- Added `## DEFECT ANALYSIS` as step 1 of OUTPUT CONTRACT — must be written before PATCH_PLAN
  and before any file output. Per defect: root cause, pattern type (ONE-TIME-BUG | SCOPE-BOUNDARY |
  RECURRING-VIOLATION), reintroduction risk (HIGH/LOW), and categorical commitment of what will NOT
  be output. Forces Claude to demonstrate understanding of the scope boundary before touching files.

**Permanent prohibitions** (harness + both prompt templates):
- `_extract_defects_for_tracking()`: parses QA report into (location, classification, problem, fix) entries
- `_build_prohibitions_block()`: formats promoted entries as hard constraints with categorical rules
- `recurring_tracker` in main loop: tracks (location, classification) → occurrence count
- After 2+ appearances: promoted to `PERMANENT PROHIBITIONS` block, injected into every subsequent
  patch prompt via `{{prohibitions_block}}` placeholder in both `build_previous_defects.md` and
  `build_patch_first_file_lock.md`. Phrased as hard product boundary decisions, not fix instructions.
- `build_prompt()` signature: new `prohibitions_block` optional param
- Console: `[PROHIBITIONS] N recurring defect(s) promoted to hard prohibition` on promotion

### QA prompt + harness filter: ignore `__init__.py` defects
- `qa_prompt.md`: added `__init__.py` to DO NOT FLAG list — QA must never write a defect
  whose Location is an `__init__.py` file, and must never flag a missing `__init__.py`.
- `_filter_hallucinated_defects()`: added check 1b — any defect whose Location resolves to
  an `__init__.py` filename is auto-removed before the defect reaches the patch loop.

### Exclude `__init__.py` from whitelist and remap
- `business/backend/routes/*.py`, `business/models/*.py`, `business/schemas/*.py` all
  matched `__init__.py` via fnmatch — so Claude's `__init__.py` files were carried forward
  indefinitely by `merge_forward`, freezing them into the artifact set. They then attracted
  bogus QA defects (e.g. health check assertions found inside `__init__.py`).
- Fix: `_is_valid_business_path()` now returns False for any file named `__init__.py`.
- Fix: `_remap_to_valid_path()` returns None for `__init__.py` (prune, never remap).
- Fix: `build_boilerplate_path_rules.md` — added blanket prohibition on any `__init__.py`
  under `business/**` with explanation that the boilerplate handles Python packaging.

## 2026-03-04

### ZIP packager: guard against empty run_dir + skip nested ZIPs
- **Root cause**: `package_output_zip()` had no guard on `run_dir.name`. When `run_dir` resolved
  to `Path('.')` (e.g. via `--resume-run .`), `run_dir.name == ''` → ZIP named `.zip` in harness
  runs dir, and `Path('.').rglob('*')` swept the **entire repo** (36GB of fo_harness_runs/) into it.
  Produced a 38GB corrupt `.zip` file in `fo_harness_runs/` → ZIP64 RuntimeError on Ctrl+C.
- **Fixes** (`package_output_zip` + `FOHarness.__init__`):
  - Early guard: validate `run_dir.name` is non-empty and doesn't resolve to cwd — raises clear
    `ValueError` instead of silently creating a multi-GB ZIP.
  - `_EXCLUDED_EXTS = {'.zip'}`: all three rglob passes skip existing ZIP files.
  - `allowZip64=True` explicit (defensive, was default but now stated).
  - Write-then-rename: write to `.zip.tmp` first, rename to `.zip` on success; `finally` block
    deletes the temp file if write is interrupted (Ctrl+C or exception) — no corrupt partials left.
  - `resume_run` validation in `FOHarness.__init__`: a path with empty name, `.`, `..`, or that
    resolves to cwd is now rejected — falls through to fresh run directory creation.
- Deleted the 38GB `fo_harness_runs/.zip` file.

### CSVs: Run data updated
- `fo_run_log.csv`: 3 new ai_workforce_intelligence BLOCK_B runs appended
- `ai_costs_aggregated.csv`: refreshed aggregate totals
- `harness_summary_costs.csv`: updated summary with latest runs

### Harness Filter: Three New Removal Checks (N/A evidence, presence claims, ORM packages)
- **Check 2 — Banned absence phrases**: Evidence containing N/A, "not applicable", "presence of the file is confirmed",
  "the presence of the file", "not present in the build output", "file not shown", "not visible in output"
  is auto-removed. Catches gpt-4o-mini's pattern of writing `Evidence: N/A (the presence of the file is confirmed)`
  which bypassed the backtick check. 3 defects from run 20260304 iter 2 would have been caught.
- **Check 4 — Presence claims**: If Problem+Evidence claims a required file type is absent (e.g. "No .jsx files
  found", "Missing backend routes") but the actual file IS present in the build output → defect auto-removed.
  Pattern table: 8 claim patterns × 2 file patterns (pages/*.jsx, routes/*.py).
- **`qa_prompt.md` — Valid external packages DO NOT FLAG list**: Added `sqlalchemy`, `alembic`, `psycopg2`,
  `pydantic`, `fastapi`, `uvicorn`, `httpx`, `python-jose`, `passlib`, `celery`, `redis`, `boto3`,
  `stripe`, `requests`, `aiohttp`. These are real external packages — QA was incorrectly flagging
  sqlalchemy as "standard library" (iter 4 DEFECT-2 in latest run).

### EXPLAINED Resolution Path — Per Governance fo_build_qa_defect_routing_rules.json
- Build governance defines two resolution modes: `FIXED` (code change) and `EXPLAINED` (explanation with rule citation).
  Our prompts only implemented `FIXED`. `EXPLAINED` path was completely missing.
- **`build_previous_defects.md`**: Added EXPLAINED format. Claude can now prefix a `## DEFECT RESOLUTIONS` block
  with `DEFECT-N: EXPLAINED` entries before any file output. Valid reasons: file outside business/**,
  feature in intake spec, auto-generated file, fabricated evidence.
- **`build_patch_first_file_lock.md`**: Same addition. OUTPUT CONTRACT updated to allow DEFECT RESOLUTIONS
  block between PATCH_PLAN and file outputs.
- **`qa_prompt.md`**: Added STEP 0 — evaluate EXPLAINED resolutions first. QA reads the
  `## CLAUDE DEFECT RESOLUTIONS` section, checks each explanation against a validity table,
  and marks valid ones as RESOLVED (excluded from defect list).
- **`fo_test_harness.py`**: Added `_extract_defect_resolutions(build_output)` — detects `## DEFECT RESOLUTIONS`
  block in Claude's patch output. If found, prepends it to `qa_build_output` as
  `## CLAUDE DEFECT RESOLUTIONS` so QA sees it before the artifact files.

### Harness: Post-QA Defect Filter — Remove Hallucinated Defects
- Added `_filter_hallucinated_defects(qa_report, qa_build_output)` on `FOHarness`.
- Runs immediately after QA response, before saving the report or acting on REJECTED verdict.
- Removes defects with **two failure modes**:
  1. **Location outside `business/**`** — QA evaluated out-of-scope files (e.g. `frontend/app/`, `backend/api/`)
  2. **Fabricated backtick evidence** — quoted code snippet (>8 chars) that does not appear anywhere in the build output
- If all defects removed → flips verdict to `QA STATUS: ACCEPTED - Ready for deployment`
- Saves raw (unfiltered) report to `logs/iteration_XX_qa_report_raw.log` when filtering occurs
- Recalculates SUMMARY counts (IMPLEMENTATION_BUG / SPEC_COMPLIANCE_ISSUE / SCOPE_CHANGE_REQUEST)
- Renumbers remaining defects sequentially
- Verified against real run (`20260303_131548`): removed all 7 defects across 3 iterations —
  that run would have accepted on iteration 1 instead of burning 3 wasted patch iterations


### Pruner: Checksum-Based Duplicate Detection
- Before pruning a duplicate (wrong-path or wrong-business-path), now checksums both files.
- If SHA256 match → "Pruned identical duplicate" — provably lossless.
- If SHA256 differ → "CONFLICT" warning — canonical kept, wrong-path discarded, but conflict
  is visible so you can investigate rather than silently losing content.
- Added `_sha256(path)` static helper on ArtifactManager; reuses existing hashlib import.

### Pruner: Remap tests/*.py + App Router page.tsx Name Collision
- `tests/test_*.py` had no remap rule — silently pruned instead of going to `business/tests/`.
  Fix: added `'tests' in parts or name.startswith('test_')` → `business/tests/<name>`.
- Next.js app router files (`frontend/src/app/clients/page.tsx`, etc.) all remapped to
  `business/frontend/pages/page.jsx` — every file had the same output name so they overwrote
  each other. Root cause: `name = page.tsx` for all of them; remap used the filename not the route.
  Fix: when `name in ('page.tsx', 'page.jsx', 'page.js')` and `'app' in parts`, derive the
  component name from route segments between `app/` and `page.*`:
  - `app/clients/page.tsx`     → `Clients.jsx`
  - `app/clients/new/page.tsx` → `ClientsNew.jsx`
  - `app/assessments/page.tsx` → `Assessments.jsx`

### Extractor: Checksum-Based Overwrite — Prefer New Over Size
- Old logic: `new_size <= existing_size → skip`. This caused Claude's defect-fix output
  to be discarded when the fix made the file slightly smaller (e.g. removed bad questions
  from AssessmentForm.jsx — 8525 vs 8529 chars → old defective version kept).
- New logic:
  - Identical content (checksum) → skip (no-op)
  - Different content, new < 100 chars AND new < half of existing → truncated stub, skip
  - Different content, otherwise → prefer new (Claude intentionally regenerated it)
- Logged as "Overwriting: (new version smaller but different)" when new is smaller.

### QA Prompt: Ban "Not applicable" Evidence Phrases
- Iter 2 DEFECT-002/003/004 all had Evidence: "(Not applicable as specific dependencies
  are missing)" — fabricated, same pattern as "Content not present". Added to banned phrases.

### Build Prompt: Block Boilerplate Internal File Creation
- Claude was generating `backend/app/middleware/auth.py`, `backend/app/utils/calculations.py`
  etc. despite `backend/` being in the HARD FAIL list. Root cause: when a defect mentions
  "missing auth" or "missing utils", Claude's instinct is to create the infrastructure file
  rather than use the boilerplate import.
- Fix (`build_boilerplate_path_rules.md`): added BOILERPLATE BOUNDARY table mapping the
  wrong urge → correct import for auth, DB, utils, tenancy, Auth0. Explicit warning that
  files created at `backend/app/middleware/`, `backend/app/utils/` etc. will be deleted.
- Fix (`build_previous_defects.md`): added rule 6 to CRITICAL RULES: "DO NOT create
  boilerplate internals". Added IF A DEFECT MENTIONS MISSING AUTH / MIDDLEWARE / UTILS
  section with correct imports for each case.

### Pruner: Remap requirements.txt + Root-Level Config Files + JS Tests
- `requirements.txt` (anywhere) had no remap → pruned. Fix: always remaps to
  `business/backend/requirements.txt`. Added to whitelist.
- Root-level `package.json`, `next.config.js`, `postcss.config.js`, `tailwind.config.js`,
  `jest.config.js`, `jest.setup.js` were pruned when not under `frontend/` — remap rule
  only fired when `'frontend' in parts`. Fix: config file remap is now unconditional —
  these filenames always go to `business/frontend/<name>` regardless of where Claude placed them.
  Added jest config files to remap list and whitelist.
- JS test files (`.test.js`, `.spec.js`) had no remap → pruned. Fix: added `.test.`/`.spec.`
  name check → `business/tests/<name>`. Added `business/tests/*.js|jsx|ts|tsx` to whitelist.

### Build Prompt: Harden Auth0 Token Rule to Prevent Per-File Regression
- Root cause: `user.getAccessTokenSilently()` appeared in EVERY new JSX file Claude generated
  across all 3 iterations, even after explicit CORRECT/WRONG examples were in the build prompt.
  The rule existed but only as explanatory text — it was not in the enforcement gates.
- Fix 1 (`build_boilerplate_path_rules.md`): Added to HARD FAIL CONDITIONS:
  "`user.getAccessTokenSilently()` anywhere = HARD FAIL — QA will REJECT every time".
- Fix 2 (`build_boilerplate_path_rules.md`): Added to PRE-PROMPT CHECKLIST:
  "Scan every .jsx file for `user.getAccessTokenSilently()` — fix before outputting".
- Fix 3 (`build_previous_defects.md`): Made rule unconditional — previously said "if any defect
  mentions getAccessTokenSilently". Now: "applies to EVERY JSX file you output, no exceptions,
  whether or not any defect mentions it."

### QA Prompt: current_user["sub"] + Package Version DO NOT FLAG Rules
- `current_user["sub"]` was being flagged as "hardcoded user ID" — it is the correct dynamic
  auth ID extracted from the JWT via `Depends(get_current_user)`. Added to DO NOT FLAG.
  Only literal strings like `"user_123"` or `"consultant_1"` count as hardcoded.
- Package versions (e.g. `"react": "^18.2.0"`) were being flagged as outdated/requiring upgrade.
  Added to DO NOT FLAG — version choices are not defects unless intake spec requires a specific version.

### QA Prompt: Hedged Language + Self-Contradicting Evidence + Inference Bans
- Added 4 new ABSOLUTE RULES to `qa_prompt.md`:
  1. **Hedged language ban**: "does not seem to", "may suggest", "could indicate", "appears to",
     "might be" in a defect = guessing not evidence — delete the defect.
  2. **Self-contradicting Evidence ban**: if Evidence says files are present but Problem says
     they're absent — delete the defect. QA must read its own Evidence before submitting.
  3. **SCOPE_CHANGE column ban**: a database column, field name, or default value alone is NOT
     a user-facing feature. Only flag scope if intake spec explicitly excludes it AND you can
     quote the wrong implementing line.
  4. **Call-site inference ban**: quoting `onClick={() => handleDelete(id)}` does not prove
     handleDelete is broken. Must quote the function definition body or delete the defect.
- Root cause: iter 3 DEFECT-3 had self-contradictory evidence ("No instances of .jsx are absent"
  → problem "jsx absent"). Iter 4 DEFECT-1 inferred broken delete from call site only.
  Iter 4 DEFECT-2 used correct Auth0 code as evidence for a missing feature. Iter 3/4 DEFECT-4
  flagged a column default as a scope violation.

### QA Prompt: Fabricated Evidence Phrases + core.database False Positive
- Added two new ABSOLUTE RULES to `qa_prompt.md`:
  1. **Fabricated Evidence ban**: Evidence fields that say "Content of this file is not present
     in the build output", "file not shown", "not visible in output", or any equivalent are
     forbidden. If you can't read the file in the build output, you cannot write a content defect
     — delete the defect entirely.
  2. **core.database false positive ban**: `from core.database import Base, get_db` is the correct
     boilerplate DB import. Any defect citing this import as wrong or incomplete must be deleted.
- Root cause: QA was writing MEDIUM defects for package.json and README-INTEGRATION.md with
  Evidence "Content of this file is not present in the build output" — fabricating content defects
  for files it never read. Existing absence-of-thing rule was not specific enough to catch this pattern.

### Warm-Start Resume (Skip Claude BUILD on 429-Killed Runs)
- Added `--resume-run <dir>`, `--resume-iteration N`, `--resume-mode qa|fix` CLI flags.
- `qa` mode: reuse existing build artifacts from the run dir, skip Claude BUILD entirely,
  run a fresh QA pass. Use when ChatGPT 429'd before it could evaluate a completed build.
- `fix` mode: load the existing QA report from iteration N as `previous_defects`, start
  the Claude fix call at iteration N+1. Use when QA ran REJECTED but the fix call 429'd.
- `--resume-run` without `--resume-mode` defaults to `qa` automatically.
- Run directory is reused in-place — no copying, no new timestamp dir.
- Bug fix: `qa` mode was not setting the loop start iteration to `--resume-iteration`,
  so iteration 1 still ran and called Claude. Fixed: set `iteration = _ws_iteration`
  before the while loop (mirrors `fix` mode which sets `iteration = _ws_iteration + 1`).

### ChatGPT 429 Retry Hardening
- Retry count increased from 3 to 6 (`MAX_RETRIES = 6`).
- Added `RETRY_SLEEP_429 = 60` — minimum wait for 429 rate-limit errors.
- **Retry-After header**: now read and obeyed exactly when OpenAI sends it.
- **Exponential backoff + jitter + 120s penalty**: when no Retry-After header, waits
  `base * (0.5 + random() * 0.5) + 120` where base = `min(60, RETRY_SLEEP * 2^attempt)`.
  The +120s ensures aggressive cooldown after each 429 hit.
- **120s TPM cooldown** before the ChatGPT QA call on iteration 2+ (increased from 60s).
  Claude fix calls complete in <60s; without a pause the next QA call fires
  before the previous call's 30k TPM window has cleared → instant 429.

### Stop Pruning Unmappable business/ Files — Leave for QA
- The whitelist was growing every run as legitimate files kept being silently deleted.
  The whitelist approach was wrong — we were playing whack-a-mole.
- Pass 2 now: remap if possible; prune only if an exact duplicate of a canonical-path file.
  If unmappable — leave in place so QA can evaluate it.
- `merge_forward` already gates on the whitelist, so unmapped files won't accumulate
  across iterations. QA is the right place to catch structural issues, not the pruner.

### Pruner: Keep business/frontend/*.jsx and *.css
- `business/frontend/App.jsx` and `business/frontend/App.css` (root-level frontend files)
  were being pruned — whitelist only covered `pages/*.jsx` and `styles/*.css`.
- Added `business/frontend/*.jsx` and `business/frontend/*.css` to whitelist.

### Test File Handling: Visible to QA, Not Carried Forward, Included in ZIP
- Tests were pruned before QA — QA then flagged "missing tests" as MEDIUM, burning an
  iteration to regenerate files we just deleted.
- Fix (2 parts):
  1. `business/tests/` and `business/backend/tests/` added to whitelist — tests survive
     the pruner so QA can evaluate them.
  2. `merge_forward` explicitly excludes test paths — tests don't accumulate across
     iterations; Claude must regenerate them if needed.
- Tests ARE included in the final ZIP — the ZIP is a full project handoff to the founder,
  not just a runtime bundle. Founder needs tests for local dev and CI/CD.

### Pruner: Fix _remap_business_path — routers + drop app guard
- Two bugs vs Pass 1 logic:
  1. `'routers'` was missing from Pass 2 check — Pass 1 checks `(api, routers, routes)`,
     Pass 2 only checked `api` or `routes`. `business/backend/app/routers/` files
     were falling through to `None` and being pruned.
  2. `if 'app' in parts` guard was too strict — `business/backend/models/` or
     `business/backend/schemas/` (no `app` in path) returned `None` and got pruned.
- Fix: now mirrors Pass 1 exactly — `api|routers|routes` anywhere under `backend` →
  `routes/`; `models|schemas|services` anywhere under `backend` → canonical top-level.

### Pruner: Remap business/backend/app/ Subdirectories
- Claude generates `business/backend/app/models/`, `schemas/`, `services/` — all were being
  pruned instead of remapped because `_remap_business_path` only handled `backend/api/`.
- Now remaps:
  - `business/backend/app/models/*.py`   → `business/models/`
  - `business/backend/app/schemas/*.py`  → `business/schemas/`
  - `business/backend/app/services/*.py` → `business/services/`
  - `business/backend/app/api/*.py`      → `business/backend/routes/`

### Pruner: Schemas, Components, backend/main.py, Frontend .js Remap
- `business/schemas/*.py` (Pydantic schemas) were being pruned — added to whitelist.
- `business/backend/main.py` (FastAPI entry point) was being pruned — added to whitelist.
- `business/frontend/components/*.jsx/.js` were being pruned — added to whitelist.
- `frontend/app/*.js` page files were pruned (Pass 1 remap only handled `.jsx`/`.tsx`, not `.js`).
  Now remapped to `business/frontend/pages/`.
- `frontend/components/*.js` were silently dropped. Now remapped to `business/frontend/components/`.
- `frontend/package.json`, `frontend/next.config.js` etc. at frontend root now remapped
  to `business/frontend/<name>` (matched by filename, not extension).
- `business/frontend/app/*.js` (Pass 2): now remapped to `pages/` alongside `.tsx`/`.jsx`.
- `business/tests/` files still correctly pruned (not part of deployment contract).

### Pruner Whitelist Expansion + App Router Remapping
- `BOILERPLATE_VALID_PATHS` only covered `pages/*.jsx`, `routes/*.py`, `lib/` — so legitimate
  frontend config files Claude generates (next.config.js, package.json, postcss.config.js,
  tailwind.config.ts, tsconfig.json, styles/*.css, public/*) were being silently deleted.
- Added all frontend config and infrastructure paths to the whitelist.
- Added `_remap_business_path()`: Pass 2 now remaps instead of deletes when possible:
  - `business/frontend/app/*.tsx|.jsx` → `business/frontend/pages/*.jsx` (App Router → Pages Router)
  - `business/frontend/app/*.css` → `business/frontend/styles/*.css`
  - `business/backend/api/*.py` → `business/backend/routes/*.py`
- If the canonical path already exists, the wrong-path file is pruned as a duplicate.
- Same salvage-or-prune pattern used in Pass 1 for non-business files.

### QA Prompt: Test File Rules, Absence Defects, Stdlib in Requirements
- **Test files**: QA was flagging intentional test behaviour (e.g. sending invalid JSON to
  test error handling) as IMPLEMENTATION_BUG. Now: only flag literal bugs in the test code
  itself. Never flag a test for what it is intentionally testing. Never flag missing test
  coverage for a specific file unless the intake spec required it.
- **Absence-of-thing defects**: Defects about missing comments, docstrings, or tests for a
  specific file are invalid unless the intake spec required them. If your Evidence field
  would be empty or describe an absence — the defect must be deleted.
- **Stdlib in requirements.txt**: `uuid`, `os`, `json`, `re`, `datetime` etc. should NOT be
  in requirements.txt. These are now explicitly called out as MEDIUM defects.

### --qa-wait CLI Flag (TPM Cooldown, Default 0)
- The 120s TPM cooldown before iteration 2+ QA calls is now a CLI option, defaulting to 0.
- Use `--qa-wait 120` when hitting TPM 429s on multi-iteration runs.
- Default of 0 means no wait — don't pay the penalty unless you need it.

### Switch QA Model to gpt-4o-mini + --gpt-model Flag
- QA prompts are ~33k tokens; gpt-4o TPM limit is 30k on this org tier — the request is
  physically larger than the window and will never succeed regardless of retry wait time.
- Switched default `GPT_MODEL` from `gpt-4o` to `gpt-4o-mini` (200k TPM, same tier).
- Added `--gpt-model` CLI flag to override without touching code
  (e.g. `--gpt-model gpt-4o` to switch back on a higher tier).

### API Error Diagnostics (Rate-Limit Headers + Error Body)
- On every **ChatGPT 429** and every **Claude 429/500/529**, now prints:
  - `error type`, `error code`, `message` from the JSON response body
  - All rate-limit headers: `limit-requests`, `remaining-requests`, `reset-requests`,
    `limit-tokens`, `remaining-tokens`, `reset-tokens`, `retry-after`
  - ChatGPT: `x-ratelimit-*` headers; Claude: `anthropic-ratelimit-*` headers
- `reset-req` / `reset-tok` are UTC timestamps — tells you exactly when the window clears.
- Makes it possible to distinguish RPM vs TPM vs daily quota vs org cap without guessing.

### API Call Timestamps
- Added datetime timestamps to every `ClaudeClient.call()` and `ChatGPTClient.call()`.
- Prints `[YYYY-MM-DD HH:MM:SS] → <API> request sent` before each request.
- Prints `[YYYY-MM-DD HH:MM:SS] ← <API> response received (Xs)` with elapsed seconds on success.
- Covers all 13 call sites (build, fix, patch, polish, docs, tests, deploy, QA) in one edit.

### Wrong-Path File Salvage (Remap Instead of Discard)
- Pruner was silently deleting files Claude generated in wrong paths (e.g.
  `app/api/foo.py`) even when no correct-path equivalent existed — logic lost.
- Added `_remap_to_valid_path()` to `ArtifactManager`: before pruning, checks
  if a valid-path equivalent already exists. If YES → prune the duplicate.
  If NO → rename/move to the correct `business/` path instead of deleting.
- Remap rules: `app/api/*.py` → `business/backend/routes/`, `models/*.py` →
  `business/models/`, `services/*.py` → `business/services/`,
  `*.jsx/*.tsx` → `business/frontend/pages/` (or `lib/` if in a lib dir).

### QA Hallucination: Evidence Field + Hypothetical Ban
- QA was writing defects with `Location: (hypothetical for reference)` — fabricated.
  Also cited real files but invented wrong content (e.g. Flask imports in a FastAPI file).
  The `quote-it-or-drop-it` rule was advisory and being ignored.
- Added `Evidence:` as a required field in the defect output format. QA must paste
  the exact wrong line verbatim before writing Problem/Fix. No paste = invalid defect.
- Added ABSOLUTE RULES block to `qa_prompt.md`: the words "hypothetical", "for reference",
  "based on guidelines" in a Location field = fabricated defect = must be deleted.

### API Availability Check Script
- Added `check_openai.py`: quick pre-run check that Claude and OpenAI APIs are responding.
- Shows OpenAI remaining RPM and TPM quota from rate-limit headers.
- Warns if TPM is too low for a large QA call (~10k–30k tokens).
- Flags Claude 529 overload separately from 429 rate-limit.
- Usage: `python check_openai.py` (both), `--claude`, `--openai`.



## 2026-03-02 (Fix A — Boilerplate DB Reference Injection)

### Root Cause Identified
- Build runs for `ai_workforce_intelligence` were NON_CONVERGING (15 iterations, $5+) because
  Claude was generating **Flask** routes (`Blueprint`, `request`, `jsonify`) while the boilerplate
  backend is **FastAPI** (`APIRouter`, `Depends(get_db)`).
- The DB layer prompt only said "use the boilerplate's database ORM/service" with no import paths
  or patterns. Claude couldn't write correct code, so it fell back to in-memory storage every time.
- A "write a TODO comment if unsure" fallback instruction was actively giving Claude permission
  to defer DB implementation, guaranteed to fail QA.

### Fix: Inject Exact Boilerplate DB Patterns
- Updated `directives/prompts/build_boilerplate_path_rules.md`:
  - Added full FastAPI + SQLAlchemy reference (imports, model, CRUD routes)
  - Added explicit prohibition: `NEVER use Flask (Blueprint, request, jsonify). Use APIRouter.`
  - Removed the "write a TODO comment if unsure" fallback
- Updated `directives/prompts/build_previous_defects.md`:
  - Same DB reference added to the defect-fix context
  - Same Flask prohibition added

## 2026-03-02 (QA Convergence Fix)

### QA Defect Specificity
- Added `Fix:` field to QA defect output format in `directives/prompts/qa_prompt.md`.
  QA now provides the exact code change required per defect, not just the problem description.

### Defect Injection Enrichment
- Added `_enrich_defects_with_fix_context()` to `FOHarness` in `fo_test_harness.py`.
  For boilerplate builds, detects mock-storage and frontend-hardcode defect patterns and
  prepends an architectural fix guide before injecting QA report into next iteration prompt.
- Wired enrichment at the `previous_defects = qa_report` assignment in `execute_build_qa_loop`.
- Added `BOILERPLATE DATA LAYER — MANDATORY FIX PATTERNS` block to `directives/prompts/build_previous_defects.md`.
  Explicit dict/mock prohibition + UUID/ORM pattern requirement injected on every defect iteration.

### Boilerplate Data Layer Prohibitions
- Added `DATA LAYER PROHIBITIONS` section to `directives/prompts/build_boilerplate_path_rules.md`.
  Hard-prohibits dict storage, sequential IDs, hardcoded data, and in-memory state for all boilerplate builds
  (iteration 1 and every subsequent iteration). Falls back to TODO comment if ORM import unknown.

## 2026-03-02

### Build/QA Stability
- Modularized and externalized prompt directives under `directives/prompts/`.
- Added `build_patch_first_file_lock.md` and wired it into defect iterations.
- Added prior-iteration required file inventory injection into defect prompts.
- Added defect target file extraction and injection into defect prompts.
- Aligned lowcode boilerplate path contract to:
  - `business/frontend/pages/*.jsx`
  - `business/backend/routes/*.py`
- Added external `QA_POLISH_2` directive loading with CLI override.

### Truncation + Continuation
- Increased defaults to `max_parts=10` and `max_continuations=9`.
- Added CLI overrides:
  - `--max-parts`
  - `--max-continuations`
- Fixed malformed multipart gap: continuation fallback now runs whenever output remains truncated.
- Added explicit BIG BUILD logs for multipart and fallback continuation modes.

### Pre-QA Validation + Patch Recovery
- Pre-QA required file aligned to `business/package.json`.
- Moved `business/README-INTEGRATION.md` from pre-QA hard fail to post-QA polish generation.
- Added `polish_integration_readme_prompt.md` for post-QA integration doc generation.
- Added normalization:
  - auto-copy `business/frontend/package.json` -> `business/package.json` when canonical file missing.
- Expanded patch-recovery targets to include required files missing from manifest.
- Fixed patch flow to refresh `artifact_manifest.json` after patch writes.

### Iteration Controls
- Default iteration cap aligned to governance: `MAX_QA_ITERATIONS = 5`.
- Added CLI override:
  - `--max-iterations`

### Boilerplate Source Control
- Added CLI override for boilerplate source:
  - `--platform-boilerplate-dir`

### zip_to_repo + Runbook
- Added `--clean-existing` and `--hard-delete-existing` to `deploy/zip_to_repo.py`.
- Both cleanup flags require confirmation prompt:
  - `ARE YOU SURE??? (Y/N)`
- Added `rerunziptorepo.md` runbook.

### Deploy Pipeline Hardening (deploy/*)
- Added deploy config sanitation and improved diagnostics for Railway/Vercel.
- Added delay before Vercel step to improve backend URL readiness window.
- Improved URL reporting and fallback handling.
