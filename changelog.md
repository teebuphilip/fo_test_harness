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
- **Exponential backoff + jitter**: when no Retry-After header, waits
  `RETRY_SLEEP * 2^attempt` capped at 60s, randomised 50–100% so retries
  don't all land at the same time after a burst.
- Added 60s TPM cooldown before the ChatGPT QA call on iteration 2+.
  Claude fix calls complete in <60s; without a pause the next QA call fires
  before the previous call's 30k TPM window has cleared → instant 429.

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
