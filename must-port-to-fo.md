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

15. QA hallucination + Auth0 token pattern fix ✅ DONE (2026-03-03)
    - QA (ChatGPT) hallucinated .tsx/app/ files that didn't exist in artifacts → burned iters 1-6 on ghost defects.
    - Build prompt showed `const { user, isLoading } = useAuth0()` without `getAccessTokenSilently` →
      Claude always generated `user.getAccessTokenSilently()` (not a method on user object) → recurring unfixable bug.
    - QA misdescribed the bug as "missing await" instead of "called on wrong object" → Claude couldn't fix it.
    - Fix (3 parts):
      a) `qa_prompt.md`: Added "CRITICAL: ONLY FLAG WHAT YOU CAN ACTUALLY SEE" block — must see `**FILE: path/file.tsx**`
         header before flagging .tsx; .tsx rule is now "ONLY IF you see a header". Also added anti-hallucination
         rules for app/ directory files.
      b) `build_boilerplate_path_rules.md`: Updated Auth0 frontend template to include `getAccessTokenSilently`
         in destructuring + explicit CORRECT/WRONG examples showing `user.getAccessTokenSilently()` is invalid.
      c) `build_previous_defects.md`: Added AUTH0 TOKEN FIX PATTERN section with exact correct/wrong patterns.
      d) `qa_prompt.md` DO NOT FLAG: added correct token patterns; added Auth0 BUG section with exact defect
         description and fix so QA describes it correctly when it does appear.

14. Whitelist-based business path pruning ✅ DONE (2026-03-03)
    - Junk files under business/ (tests/, backend/services/, backend/__init__.py, backend/app.py, app/)
      survived pruning because they started with business/. Merge_forward then froze them in permanently.
      Duplicate ScoringService in both business/services/ and business/backend/services/ caused ongoing confusion.
    - Fix: added BOILERPLATE_VALID_PATHS whitelist to harness. Second pass in prune_non_business_artifacts
      removes any business/** file not matching the whitelist. merge_forward_from_previous_iteration
      updated to also use whitelist — never carries forward invalid paths.
    - Valid paths: business/frontend/pages/*.jsx, business/backend/routes/*.py, business/models/*.py,
      business/services/*.py, business/frontend/lib/*.js|jsx, business/README-INTEGRATION.md, business/package.json
    - Build prompt: added forbidden paths (business/tests/, business/backend/services/, business/backend/__init__.py,
      business/backend/app.py, business/app/).
    - QA: added DO NOT FLAG for business/frontend/pages/*.jsx, business/models/*.py, business/services/*.py.

13. Forbid business/frontend/app/ and .tsx extensions ✅ DONE (2026-03-03)
    - Claude switched from root-level app/ (blocked) to business/frontend/app/ with .tsx files.
    - Boilerplate uses pages router — business/frontend/pages/*.jsx only.
    - Fix: added to HARD FAIL CONDITIONS and INVALID EXAMPLES in build_boilerplate_path_rules.md.
    - Added .tsx detection to QA required structure check in qa_prompt.md.

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

5. Collateral regeneration lock ✅ DONE (2026-03-03)
   - When fixing defects, Claude regenerated adjacent files from memory → regressions. Iter 9→10: 1 defect → 6.
   - Fix (three parts):
     a) Prompts: `build_patch_first_file_lock.md` + `build_previous_defects.md` — Claude now outputs ONLY
        defect-target files. Non-defect files explicitly excluded.
     b) Harness: `ArtifactManager.merge_forward_from_previous_iteration()` — after extraction, copies any
        business/** file from previous iteration that Claude didn't output into current iteration's dir.
     c) Harness: `ArtifactManager.build_synthetic_qa_output()` — builds full merged artifact set as
        FILE: headers + code fences. QA receives this for defect iterations (not Claude's partial output).
   - Also fixed: false QA defect on `from core.database import Base, get_db` — added to DO NOT FLAG in qa_prompt.md.

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

18. Structural QA verification gate — quote-it-or-drop-it ✅ DONE (2026-03-03)
    - Per-capability DO NOT FLAG rules are whack-a-mole: ChatGPT will pattern-match any
      "flag this" rule without verifying the code, for every capability one by one.
    - Fix: added universal VERIFY BEFORE YOU FLAG block to qa_prompt.md:
      - Every defect requires quoting the exact offending line verbatim
      - If you cannot quote it, you cannot write the defect
      - Any import from core.* or lib.*_lib = capability correctly integrated — DO NOT FLAG
      - No inference from pattern names or descriptions — only literal quoted evidence
    - Also added same rule to tech_stack_context in fo_test_harness.py BOILERPLATE MODULES block.
    - This one rule prevents all future per-capability hallucinations, not just Auth0.

17. QA Auth0 + ORM hallucination fix ✅ DONE (2026-03-03)
    - Home.jsx had CORRECT Auth0 pattern from iteration 4 onwards: `const { user, isLoading, getAccessTokenSilently } = useAuth0()`
    - QA hallucinated the Auth0 defect for 9 consecutive iterations (4-12) by pattern-matching on `useAuth0`
      in the code without actually checking if `user.getAccessTokenSilently()` was present.
    - Fix: added VERIFICATION REQUIRED block to Auth0 BUG section in qa_prompt.md:
      QA must QUOTE the exact line containing `user.getAccessTokenSilently()` before flagging.
      If it can't quote it, it cannot flag. If destructuring already has getAccessTokenSilently — correct, do NOT flag.
    - Also fixed: SQLAlchemy `.query().filter()` chains flagged as "inline SQL without ORM" — added to DO NOT FLAG.
    - Also fixed: QA flagging ABSENCE of .tsx files as a defect (inverted logic) — added to DO NOT FLAG.

16. Full capability coverage — all missing modules added ✅ DONE (2026-03-03)
    - `build_boilerplate_capabilities.md` was missing: data_retention (#41-44), monitoring/sentry,
      webhook_entitlements router, auth0_lib (user management), betteruptime_lib (uptime monitoring).
    - Also missing entire FRONTEND CAPABILITIES section:
      - Auth0 correct pattern (getAccessTokenSilently destructured from useAuth0, NOT user.getAccessTokenSilently)
      - api.js axios instance usage (pre-auth'd, never raw fetch)
      - useEntitlements / useCanAccess hooks
      - EntitlementGate component (auto upgrade prompt)
      - useAnalytics hook (trackEvent, trackPageView)
    - Fix: appended new BACKEND INFRASTRUCTURE, SHARED LIBS — MANAGEMENT, and FRONTEND CAPABILITIES
      sections to `build_boilerplate_capabilities.md`.
    - HOW TO USE guidance updated with complete intake-capability mapping.
    - Anti-regression rule added: "ALWAYS destructure getAccessTokenSilently from useAuth0() — NEVER user.getAccessTokenSilently()"

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

19. Wrong-path file salvage (remap instead of discard) ✅ DONE (2026-03-04)
    - Pruner was silently deleting files Claude generated in wrong paths (app/api/foo.py)
      even when no correct-path equivalent existed — logic permanently lost.
    - Fix: added `_remap_to_valid_path()` to ArtifactManager. Before pruning, check if a
      valid-path equivalent already exists. If YES → prune duplicate. If NO → rename/move
      the file to the correct business/ path instead of deleting it.
    - Remap rules: app/api/*.py → business/backend/routes/, models/*.py → business/models/,
      services/*.py → business/services/, *.jsx/*.tsx → business/frontend/pages/ or lib/.

20. Warm-start resume (skip Claude BUILD on 429-killed runs) ✅ DONE (2026-03-04)
    - ChatGPT 429 was killing runs after a good Claude build — throwing away the build output
      and forcing a full re-run from scratch (wasting Claude tokens + time).
    - Fix: added --resume-run, --resume-iteration, --resume-mode cli flags.
      qa mode: reuse existing build artifacts, skip Claude BUILD, run fresh QA.
      fix mode: load existing QA report as previous_defects, start Claude fix at iter N+1.
    - --resume-run alone defaults to qa mode (no need to specify --resume-mode).
    - Run dir is reused in-place (no copying).
    - Bug fix: qa mode was not setting loop start iteration to --resume-iteration,
      so the loop started at 1 and called Claude anyway. Fixed: set iteration = _ws_iteration
      before the while loop (mirrors how fix mode sets iteration = _ws_iteration + 1).

21. ChatGPT 429 retry: Retry-After header + exponential backoff + jitter + 120s penalty ✅ DONE (2026-03-04)
    - Flat 60s retry was ignoring OpenAI's Retry-After header and had no jitter.
    - Fix: (1) read Retry-After header and use it exactly when present.
      (2) if no header: exponential backoff (RETRY_SLEEP * 2^attempt) capped at 60s
      with 50-100% jitter + 120s penalty so retries back off aggressively.
    - Formula: base * (0.5 + random() * 0.5) + 120

22. 120s TPM cooldown before QA on iteration 2+ ✅ DONE (2026-03-04)
    - Claude fix calls complete in <60s, so the previous QA call's 30k TPM window
      hasn't reset when the next QA call fires immediately — instant 429.
    - Fix: sleep 120s before the ChatGPT QA call on iteration 2+.

23. QA hallucination: Evidence: required field + ban "hypothetical" ✅ DONE (2026-03-04)
    - QA wrote defects with location "(hypothetical for reference)" — fabricated entirely.
      Also cited real files (reports.py) but invented Flask imports that weren't there.
      quote-it-or-drop-it rule was advisory and being ignored.
    - Fix: (1) added Evidence: as a required field in the defect output format — QA must
      paste the exact wrong line verbatim before writing Problem/Fix. No paste = no defect.
      (2) ABSOLUTE RULES block: "hypothetical", "for reference", "based on guidelines"
      in a location field = fabricated defect = must be deleted.

30. Pruner: fix _remap_business_path — routers + drop app guard ✅ DONE (2026-03-04)
    - 'routers' was missing from Pass 2 route marker check (Pass 1 checks api/routers/routes).
    - 'if app in parts' guard was too strict — business/backend/models/ without 'app'
      in the path returned None and got pruned instead of remapped to business/models/.
    - Fix: Pass 2 now mirrors Pass 1 exactly. No 'app' guard needed.

29. Pruner: remap business/backend/app/ subdirectories ✅ DONE (2026-03-04)
    - Claude generates business/backend/app/models/, schemas/, services/ — all were pruned
      because _remap_business_path only handled backend/api/ → routes/.
    - Fix: added remap rules for all business/backend/app/ subdirs:
      business/backend/app/models/*.py   → business/models/
      business/backend/app/schemas/*.py  → business/schemas/
      business/backend/app/services/*.py → business/services/
      business/backend/app/api/*.py      → business/backend/routes/

28. Pruner: schemas, components, backend/main.py, frontend .js remap ✅ DONE (2026-03-04)
    - business/schemas/*.py (Pydantic), business/backend/main.py (FastAPI entry point),
      business/frontend/components/*.jsx/.js were all being silently pruned.
    - frontend/app/*.js page files not remapped (only .jsx/.tsx were handled).
    - frontend/components/*.js, frontend/package.json, frontend/next.config.js not remapped.
    - Fix: expanded BOILERPLATE_VALID_PATHS + updated both _remap_to_valid_path (Pass 1)
      and _remap_business_path (Pass 2) to cover all missing cases.

    | File                              | Was    | Now                                      |
    |-----------------------------------|--------|------------------------------------------|
    | business/schemas/*.py             | pruned | kept (added to whitelist)                |
    | business/backend/main.py          | pruned | kept (added to whitelist)                |
    | business/frontend/components/     | pruned | kept (added to whitelist)                |
    | frontend/app/*.js                 | pruned | remapped → business/frontend/pages/      |
    | frontend/components/*.js          | pruned | remapped → business/frontend/components/ |
    | frontend/package.json etc.        | pruned | remapped → business/frontend/<name>      |
    | business/frontend/app/*.js        | pruned | remapped → business/frontend/pages/      |
    | business/tests/                   | pruned | still pruned ✓ (correct)                 |

25. Pruner whitelist too aggressive — config files and app/ router remapping ✅ DONE (2026-03-04)
    - BOILERPLATE_VALID_PATHS only listed pages/*.jsx, routes/*.py, lib/ — so legitimate
      frontend config files (next.config.js, package.json, postcss.config.js, tailwind.config.ts)
      were being pruned. Also, business/frontend/app/ (App Router) files were deleted instead
      of being remapped to the correct pages/ (Pages Router) location.
    - Fix 1: Expanded BOILERPLATE_VALID_PATHS to include business/frontend/ config files:
      package.json, next.config.js/ts, postcss.config.js/ts, tailwind.config.js/ts,
      tsconfig.json, jsconfig.json, styles/*.css, public/*.
    - Fix 2: Added _remap_business_path() static method — handles Pass 2 remapping:
      business/frontend/app/*.tsx|.jsx → business/frontend/pages/*.jsx
      business/frontend/app/*.css → business/frontend/styles/*.css
      business/backend/api/*.py → business/backend/routes/*.py
    - Fix 3: Pass 2 now tries _remap_business_path() before deleting, same pattern as Pass 1.

27. Switch QA model to gpt-4o-mini + --gpt-model CLI flag ✅ DONE (2026-03-04)
    - gpt-4o TPM limit is 30k on the current org tier. QA prompts are ~33k tokens.
      The single request is larger than the window — no retry can ever succeed.
    - Fix: changed default GPT_MODEL to gpt-4o-mini (200k TPM on same tier).
    - Added --gpt-model CLI flag to override at runtime without touching code.

26. API error diagnostics: dump body + rate-limit headers on every transient error ✅ DONE (2026-03-04)
    - 429s were retrying blind — no visibility into which limit was hit (RPM vs TPM vs
      daily quota vs org cap) or when the window resets.
    - Fix: on every ChatGPT 429 and every Claude 429/500/529, print:
        error type, error code, message (from response JSON body)
        all x-ratelimit-* headers (ChatGPT) / anthropic-ratelimit-* headers (Claude):
        limit-requests, remaining-requests, reset-requests,
        limit-tokens, remaining-tokens, reset-tokens, retry-after
    - reset-req / reset-tok timestamps tell you the exact UTC time the window clears.

24. Timestamps on every Claude + ChatGPT API call ✅ DONE (2026-03-04)
    - No visibility into when API requests were sent or how long they took — hard to
      diagnose 429 timing or slow responses.
    - Fix: added datetime.now() timestamp prints before requests.post() and after
      successful response in both ClaudeClient.call() and ChatGPTClient.call().
    - Format: [YYYY-MM-DD HH:MM:SS] → <API> request sent / ← response received (Xs)
    - One edit covers all call sites (13 total) — no per-call changes needed.

## Acceptance Criteria for Port
- No pre-QA false-fail caused by manifest staleness.
- No skipped continuation when output is still truncated.
- Defect iterations preserve required file set across retries.
- QA rejections are primarily real implementation defects, not artifact drift.
- Boilerplate builds do not produce dict/mock storage on any iteration.
- Defect count trends downward across iterations (convergence).
