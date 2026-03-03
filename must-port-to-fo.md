# Must Port to FO

## Priority 0 (First)
1. Truncation recovery fix
- Run fallback continuations whenever output remains truncated, regardless of multipart mode.

2. Patch manifest consistency fix
- Refresh `artifact_manifest.json` after patch file writes before re-validation.

3. Required-file recovery expansion
- Include required files missing from manifest in patch targets (not only extracted-missing files).

4. Package path normalization
- If `business/package.json` missing and `business/frontend/package.json` exists, normalize before validation.

## Priority 1
1. Defect-iteration file inventory lock
- Inject prior required file inventory into defect build prompts.
- Inject defect target files for minimal-change repair behavior.

2. Boilerplate path contract alignment
- Enforce frontend pages under `business/frontend/pages`.
- Enforce backend routes under `business/backend/routes`.

3. Move integration README to post-QA polish
- Do not block QA on missing `business/README-INTEGRATION.md`.
- Generate it in post-QA polish.

## Priority 2
1. CLI operational overrides
- `--max-iterations`
- `--max-parts`
- `--max-continuations`
- `--platform-boilerplate-dir`

2. Logging and observability
- Add BIG BUILD mode logs.
- Log applied normalizations and patch-recovery outcomes.

## Governance Alignment
- Keep default iteration cap aligned to locked policy (`5`) but allow CLI override for controlled exception runs.

12. QA required structure checklist ✅ DONE (2026-03-03)
    - QA had no structural checklist — "verify required artifacts" with no definition of required.
    - Missing frontend (no business/frontend/pages/*.jsx) went unflagged; QA evaluated pruned app/ files instead.
    - Fix: added REQUIRED STRUCTURE block to qa_prompt.md:
      - business/frontend/pages/*.jsx absent → HIGH SPEC_COMPLIANCE_ISSUE
      - business/backend/routes/*.py absent → HIGH SPEC_COMPLIANCE_ISSUE
      - business/README-INTEGRATION.md absent → MEDIUM
      - business/package.json absent → MEDIUM
      - Files outside business/ (app/, src/, tests/) → ignore entirely, do not reference in defects

11. Forbidden path prohibition strengthened ✅ DONE (2026-03-03)
    - Claude generated duplicate logic under `app/api/`, `app/core/`, `tests/` alongside correct `business/` files.
    - Harness pruned them silently → logic lost, wasted iterations.
    - Fix: added explicit forbidden path list to HARD FAIL CONDITIONS and INVALID EXAMPLES in
      `build_boilerplate_path_rules.md`: `app/`, `app/api/`, `app/core/`, `src/`, `tests/`, `backend/`, `frontend/`
    - Includes counterexamples mapping wrong path → correct `business/` equivalent.

## Priority 3 (QA Convergence)
1. QA defect `Fix:` field ✅ DONE (2026-03-02)
   - Added `Fix:` to defect output format so QA provides exact code change, not just problem description.

2. Boilerplate data layer prohibitions ✅ DONE (2026-03-02)
   - Explicitly prohibit dict storage, sequential IDs, hardcoded data, in-memory state in boilerplate path rules.
   - Must be present at iteration 1, not just defect iterations.

3. Defect enrichment before injection ✅ DONE (2026-03-02)
   - Detect mock-storage and frontend-hardcode patterns in QA report before feeding to next build iteration.
   - Prepend architectural fix guide (exact patterns to use/avoid) on match.

4. Boilerplate DB reference injection ✅ DONE (2026-03-02)
   - Root cause: Claude defaults to Flask; boilerplate is FastAPI. Flask has no Depends(get_db) so
     Claude cannot use the boilerplate DB layer and falls back to in-memory storage every iteration.
   - Fix: injected exact FastAPI+SQLAlchemy patterns (imports, model, CRUD) into:
     - `directives/prompts/build_boilerplate_path_rules.md` (initial build)
     - `directives/prompts/build_previous_defects.md` (defect fix iterations)
   - Also added: `NEVER use Flask (Blueprint, request, jsonify). Use APIRouter.`
   - Removed "write a TODO comment if unsure" fallback — was giving Claude permission to defer DB impl.

5. Collateral regeneration lock ⬜ TODO
   - When fixing defects, Claude regenerates adjacent files (tests, config) unnecessarily, causing regressions.
   - Fix: add explicit file-level output lock to `build_patch_first_file_lock.md`:
     "ONLY output files whose paths appear in the DEFECTS TO FIX section. Do NOT output any other files."
   - Observed: iteration 7 had 2 defects; iteration 8 fixed them but regressed 3 other files to 3 defects.

6. Patch code fence requirement ✅ DONE (2026-03-02)
   - Root cause: Claude outputs file content as raw text after **FILE:** headers in patch iterations,
     without wrapping in code fences (```language...```). ArtifactManager regex only extracts files
     inside code fences. Result: patch iterations produce 0-2 files instead of full set → QA skipped.
   - Observed: iterations 2, 3, 8 extracted only package.json/README despite 1900+ line build outputs.
   - Fix: added explicit code fence requirement to `build_patch_first_file_lock.md` HARD CONSTRAINTS:
     "Every file MUST use **FILE: path**\n```language\n...\n``` format. NEVER output raw file content."
   - Also added: "NEVER output raw file content without a code fence — extraction requires code fences."

7. Auth context pattern for consultant_id ✅ DONE (2026-03-02)
   - Root cause: Claude hardcodes `consultant_id: 'consultant_1'` with `// TODO: Get from auth context`.
     Defect fix says "use auth context" but doesn't specify the exact pattern. TODO comment gives
     Claude permission to defer the fix.
   - Real pattern: backend `from core.rbac import get_current_user` → `current_user["sub"]`.
     Frontend: `import { useAuth0 } from '@auth0/auth0-react'; const { user } = useAuth0();`
   - Fix: added AUTH CONTEXT FIX PATTERN section to `build_previous_defects.md` with exact import + usage.

10. QA boilerplate module recognition ✅ DONE (2026-03-03)
    - QA (ChatGPT) didn't know what correct boilerplate integration looks like, so it flagged
      valid patterns as defects: `Depends(get_current_user)` flagged as "missing auth",
      `call_ai()` flagged as "no AI implementation", etc.
    - Fix: added BOILERPLATE MODULES — WHAT CORRECT INTEGRATION LOOKS LIKE section to
      `tech_stack_context` in `fo_test_harness.py` (QA prompt).
    - For each capability: shows correct import pattern + "DO NOT flag X when Y is present"
    - Also explicitly lists WHAT TO FLAG: hardcoded IDs, dict storage, Flask patterns, etc.

9. All 44 boilerplate capabilities injected into build prompt ✅ DONE (2026-03-03)
   - Created `directives/prompts/build_boilerplate_capabilities.md` — compact reference of all 44
     capabilities with exact import paths and key function signatures.
   - Wired into harness at BOTH boilerplate_path_instruction injection points (lines ~1186, ~1444).
   - Claude now sees: core.rbac, core.tenancy, core.entitlements, core.usage_limits, core.ai_governance,
     core.onboarding, core.trial, core.activation, core.listings, core.purchase_delivery,
     core.posting, core.legal_consent, core.offboarding, core.account_closure, core.fraud,
     core.financial_governance, core.expense_tracking + lib.stripe_lib, lib.mailerlite_lib,
     lib.analytics_lib, lib.meilisearch_lib
   - Claude instructed to scan intake and USE applicable ones, never rebuild from scratch.

8. Boilerplate core module interfaces not injected ✅ DONE (2026-03-02)
   - Root cause: Build prompt only told Claude about `core.database`. It did not know about
     `core.rbac.get_current_user` (auth), `core.tenancy.TenantMixin` (multi-tenancy), or
     `core.posting` (social media). `FO_BOILERPLATE_INTEGRATION_RULES.txt` says "boilerplate has auth"
     but never gives the import path — so Claude writes its own auth from scratch every time.
   - Fix: added BOILERPLATE AUTH REFERENCE section to `build_boilerplate_path_rules.md`:
     - Exact import: `from core.rbac import get_current_user`
     - Exact return shape: `{"sub": ..., "email": ..., "roles": ..., "tenant_id": ...}`
     - Correct route pattern: `Depends(get_current_user)`, use `current_user["sub"]` as owner ID
     - Auth prohibitions: no hardcoded IDs, no TODO comments, no custom JWT parsing
     - Frontend: `useAuth0()` → `user.sub`

## Acceptance Criteria for Port
- No pre-QA false-fail caused by manifest staleness.
- No skipped continuation when output is still truncated.
- Defect iterations preserve required file set across retries.
- QA rejections are primarily real implementation defects, not artifact drift.
- Boilerplate builds do not produce dict/mock storage on any iteration.
- Defect count trends downward across iterations (convergence).
