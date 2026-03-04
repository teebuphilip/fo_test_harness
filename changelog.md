# Changelog

## 2026-03-04

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
