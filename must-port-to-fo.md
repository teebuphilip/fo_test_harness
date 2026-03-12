# Must Port to FO

## Static Gate Fix (additions 2026-03-12)

66. fix: CHECK 10 — async def methods not counted → permanent false-positive missing-method loop
- `_run_static_check()` CHECK 10 only handled `ast.FunctionDef`; `async def` creates
  `ast.AsyncFunctionDef` — those methods were never added to the `methods` set, so every
  `async def` service method was always flagged as "Call to missing method".
- Root cause of 13-iteration static oscillation on adversarial_ai_validator.
- Fix: `isinstance(item, ast.FunctionDef)` → `isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))` at line ~5222.
- Files: `fo_test_harness.py` (`_run_static_check()` CHECK 10)
⬜ TODO for FO codebase

## Harness Config Generation (additions 2026-03-12)

65. fix: full business_config.json schema coverage — all boilerplate keys populated
- Schema audit of all boilerplate frontend components found 5 top-level keys missing and 2 incomplete.
- Added: `pricing`, `contact`, `faq`, `terms_of_service`, `privacy_policy`
- Fixed: `home` (added icon/social_proof/final_cta), `footer` (added tagline, href→url)
- Files: `fo_test_harness.py` (`_generate_business_config()` ~line 3186)
⬜ TODO for FO codebase

64. fix: home block missing from business_config.json — white-screen crash on every deploy
- `_generate_business_config()` never set a `home` key. `Home.jsx` reads `home.hero` at line 30
  unconditionally — null home crashes the entire app before any page renders.
- Fix: added `home.hero` (headline, subheadline, cta_primary, cta_secondary) and `home.features`
  list derived from intake must-have features.
- Files: `fo_test_harness.py` (`_generate_business_config()` ~line 3186)
⬜ TODO for FO codebase

63. fix: footer block missing from business_config.json — white-screen crash on every deploy
- `_generate_business_config()` never set a `footer` key. `Footer.jsx` calls `footer.columns.map()`
  on load — null footer crashes the entire app with TypeError before any page renders.
- Fix: added `footer.columns` (3 columns derived from intake) and `copyright` to the generated config.
- Files: `fo_test_harness.py` (`_generate_business_config()` ~line 3187)
⬜ TODO for FO codebase

## Deploy Pipeline (additions 2026-03-11)

61. new: preflight check for business page imports after copy into frontend/src
- CRA only compiles files in `frontend/src`, so deploy copies `business/frontend/pages`
  into `frontend/src/business/pages`.
- Relative imports in those pages must resolve from the *copied* location.
- New script `deploy/check_business_imports.py` scans the business pages and validates
  relative imports as if copied; can optionally rewrite `../utils/api` → `../../utils/api`
  and auto-commit the change.
- Files: `deploy/check_business_imports.py`
⬜ TODO for FO codebase

62. feat: preflight can report all imports and validate assets
- `deploy/check_business_imports.py` now supports `--report-all` and `--include-assets`
  (plus `--ext` for extra file types) so post-copy resolution issues are visible before deploy.
- Files: `deploy/check_business_imports.py`
⬜ TODO for FO codebase

63. fix: add root requirements.txt for Railway/Nixpacks detection
- Nixpacks scans the repo root; without a root `requirements.txt`, Python detection fails.
- Pipeline now writes root `requirements.txt` with `-r backend/requirements.txt` and fails fast
  if `backend/requirements.txt` is missing.
- Files: `deploy/pipeline_deploy.py`
⬜ TODO for FO codebase

64. feat: skip Git push on redeploys
- `pipeline_deploy.py` now supports `--skip-git-push` to bypass git add/commit/push
  when you only want to redeploy from the current commit.
- Files: `deploy/pipeline_deploy.py`
⬜ TODO for FO codebase

65. feat: configurable Railway wait time (default 10 minutes)
- Railway deploy polling now defaults to 10 minutes and can be overridden with
  `--railway-wait-minutes N`.
- Files: `deploy/pipeline_deploy.py`, `deploy/railway_deploy.py`
⬜ TODO for FO codebase

## Deploy Pipeline (additions 2026-03-10 evening)

60. fix: Railway set_root_directory("backend") excludes business/ from container
- `railway_deploy.py` was setting root dir to "backend/" — only backend/ gets deployed to /app.
- business/ lives at repo root → never copied in → 0 business routes loaded.
- Fix: removed set_root_directory call entirely. railway.toml startCommand handles cd backend.
- Files: deploy/railway_deploy.py
⬜ N/A — deploy pipeline fix already applied locally

59. fix: Session not imported — NameError at Railway startup
- `db: Session = Depends(get_db)` used at line 1556 but `Session` never imported.
- Fix: added `from sqlalchemy.orm import Session` after `core.database` import.
- Files: saas-boilerplate/backend/main.py (in teebu-saas-platform repo)
⬜ N/A — boilerplate fix already applied locally

58. fix: require_ajax_header defined after first use in boilerplate main.py
- NameError: name 'require_ajax_header' is not defined at Railway container startup.
- Python evaluates Depends() default args at module load — function was at line ~628 but used at line 268.
- Fix: moved definition above AUTH ENDPOINTS section, removed duplicate.
- Files: saas-boilerplate/backend/main.py (in teebu-saas-platform repo)
⬜ N/A — boilerplate fix already applied locally

## Gate Fixes (2026-03-10 late session)

57. fix: static/compile defect file injection broken by business/ prefix filter
- defect_target_files collection filtered startswith('business/') for all gate sources.
- Static checker reports file paths relative to artifacts dir → wrong-path files
  (e.g. models/AnalysisRequest.py) had no prefix → excluded from target list.
- _read_target_file_contents() got empty list → returned {} → Claude saw
  "no current file contents found" → reconstructed from memory → identical wrong
  content → static gate cycled 6 times on same defect (iters 11-16 in adversarial run).
- Fix: for defect_source in ('static', 'compile'), skip the startswith('business/') filter;
  collect all non-empty file paths from _raw_pending_defects.
- Files: fo_test_harness.py (line ~5989, defect_target_files collection block)
⬜ TODO for FO codebase

## Deploy Pipeline (additions 2026-03-10)

56. fix: email-validator missing from boilerplate requirements.txt
- main.py uses pydantic EmailStr → requires email-validator package separately.
- Was not in requirements.txt → ImportError crash at Railway container startup.
- Files: saas-boilerplate/backend/requirements.txt (in teebu-saas-platform repo)
⬜ N/A — boilerplate fix already applied locally


55. fix: _generate_business_config missing description field
- main.py hard-requires BUSINESS_CONFIG["business"]["description"] → KeyError on startup.
- Added "description": tagline to the business block.
- Files: fo_test_harness.py (_generate_business_config, line ~3128)
⬜ TODO for FO codebase

54. fix: boilerplate backend/config example files — wrong JSON key names
- stripe_config.example.json: secret_key → stripe_secret_key
- mailerlite_config.example.json: api_key → mailerlite_api_key
- auth0_config.example.json: domain/client_id/client_secret/audience → auth0_-prefixed
- Pipeline copies example → real on first deploy; wrong keys caused hard startup crashes.
- Files: saas-boilerplate/backend/config/*.example.json (in teebu-saas-platform repo)
⬜ N/A — boilerplate fix already applied locally

53. feat: harness generates business_config.json from intake at polish step
- Boilerplate InboxTamer placeholder landed in every ZIP and deployed repo.
- New _generate_business_config() on FOHarness, called at top of _post_qa_polish().
- Derives startup name, tagline, pricing, entitlements, branding, SEO from intake_data.
- Writes to business/frontend/config/ and business/backend/config/ in artifacts dir.
- Files: fo_test_harness.py (_generate_business_config, _post_qa_polish)
⬜ TODO for FO codebase

52. pipeline_deploy.py — force-add backend/config/business_config.json before push
- Railway container fails with FileNotFoundError if backend/config/business_config.json
  is gitignored and not pushed. Fix in _ensure_frontend_business_config():
  copy from .example.json if missing, then `git add -f` to force-include.
- Files: `deploy/pipeline_deploy.py` (_ensure_frontend_business_config)
⬜ TODO for FO codebase

51. pipeline_deploy.py — railway.toml written to BOTH repo root AND backend/
- Railway scans from repo root; toml only in backend/ wasn't found → Nixpacks couldn't
  detect Python. Now writes two files: root (with `cd backend &&` prefix) + backend/ (bare).
- Files: `deploy/pipeline_deploy.py` (_ensure_railway_toml)
⬜ TODO for FO codebase

50. new: deploy/repo_setup.py — GitHub repo + App installation helper
- PAT/gh CLI 403 on /user/installations → falls back to browser for App install.
- Reads GITHUB_USERNAME from ACCESSKEYS env file automatically.
- Files: `deploy/repo_setup.py` (new)
⬜ N/A for FO codebase (deploy tooling only)

50. Railway project creation — workspaceId + CLI logout + name truncation
- Railway API requires workspaceId on projectCreate → added get_workspace_id() + passes to create_project().
- Railway CLI session conflicts with API token → pipeline now runs `railway logout` before STEP 2.
- Name truncation at word boundary (last hyphen before 40 chars) — hard 50-char cut rejected by Railway.
- Files: `deploy/railway_deploy.py` (get_workspace_id, create_project), `deploy/pipeline_deploy.py` (logout + truncation)
⬜ TODO for FO codebase

49. pipeline_deploy.py + vercel_deploy.py — updated for flat repo layout
- zip_to_repo switched to flat layout: backend/ frontend/ business/ at repo root.
  All saas-boilerplate/ paths in pipeline updated to match.
- railway.toml now written to backend/ (Railway root = backend/, no cd needed).
- Vercel root_directory = frontend/ (was saas-boilerplate/frontend).
- business pages copy + loader.js patch support both old and new relative paths.
- Railway project name truncated to 50 chars (API rejects longer names).
- Removed broken serviceUpdate rootDirectory API call + non-existent githubReposRefresh mutation.
- Files: `deploy/pipeline_deploy.py`, `deploy/vercel_deploy.py`, `deploy/railway_deploy.py`
⬜ TODO for FO codebase

## Deploy Pipeline (additions 2026-03-08)

## Build Pipeline (2026-03-09)

46. fix: deploy/zip_to_repo.py — flat repo layout for Railway/Vercel compatibility
- extract_zip() copied saas-boilerplate/ as a nested dir → Railway couldn't find main.py
  (was at saas-boilerplate/backend/main.py, Railway root was business/backend/).
- Fix: unpack boilerplate contents flat into repo root:
    saas-boilerplate/backend/  → repo/backend/   (main.py, core/, lib/, requirements.txt)
    saas-boilerplate/frontend/ → repo/frontend/
    harness business/ artifacts → repo/business/
- Railway root = backend/, Vercel root = frontend/
- Files: deploy/zip_to_repo.py (extract_zip method)
⬜ TODO for FO codebase

45. fix: run_integration_and_feature_build.sh — set -e kills + missing flags + loop
- `IC_EXIT=$?` / `P1_EXIT=$?` / `FEAT_EXIT=$?` never executed under set -euo pipefail
  because script exits before assignment. Fix: `VAR=0; command || VAR=$?` pattern throughout.
- Integration fix pass missing `--max-iterations "$MAX_ITER" --no-polish`.
- Second re-check was a hard exit; replaced with `while` loop (MAX_FIX_PASSES=2).
- Extracted `_run_integration_check()` helper to deduplicate calls + refresh ARTIFACTS_DIR.
- Files: run_integration_and_feature_build.sh (Step 2/3/4 sections)
⬜ N/A — script is harness-only, not in FO production codebase

44. fix: --resume-mode fix + --integration-issues conflict
- When both flags passed together: fix warm-start block ran AFTER integration block and
  overwrote previous_defects with old QA report. Loop started at _ws_iteration+1 which
  could exceed --max-iterations → while condition immediately false → "Should not reach here".
- Fix: added `and not _integration_loaded` to fix mode block (same guard qa mode already had).
  Integration block owns previous_defects/iteration when --integration-issues is loaded.
- Files: fo_test_harness.py (warm-start fix block condition, line ~5715)
⬜ TODO for FO codebase

43. Consistency fix sharpening before Claude patch
- Consistency A↔B oscillation: Fix field said "align X with Y" — no indication of which
  side changes, which function, or exact new code. Claude guessed and oscillated indefinitely.
- New _sharpen_consistency_issues(): reads current file contents for each issue file pair,
  calls gpt-4o-mini with SHARP-N format (FILE_TO_CHANGE, FUNCTION, exact CHANGE line).
  Replaces vague Fix with precise one-sided instruction. Saves to logs/iteration_N_consistency_sharpen.log.
- Same sharpening pattern as QA triage, applied at the consistency gate.
- New methods: _sharpen_consistency_issues()
- Files: fo_test_harness.py
⬜ TODO for FO codebase

42. SYSTEMIC pre-QA uses wide surgical patch, not cold-start full build
- Full build for SYSTEMIC static/consistency was 89K chars (historical prohibitions + full intake)
  → too much noise, overwhelms Claude, risks regression of correct files.
- Wide surgical patch: surgical template + ALL current artifact files as context. ~20K chars.
  Claude sees every existing file + all defects → fixes coupled issues without cold-start noise.
- Files: fo_test_harness.py (SYSTEMIC branch in prompt routing block)
⬜ TODO for FO codebase

41. Pre-QA triage for static + consistency gates (SURGICAL vs SYSTEMIC)
- Static/consistency always used surgical patch → missing-file + multi-file defects burned 6+
  iterations before reaching Feature QA (no-frontend-pages, schema missing, coupled imports).
- New _triage_pre_qa_strategy(): rule-based, no AI call. SYSTEMIC when: consecutive_iters>=2,
  ≥4 target files, or missing-file pattern in defect text.
- SYSTEMIC → full build prompt (16384 tokens). SURGICAL → existing surgical patch.
- quality/compile/integration always surgical (narrow defects, no change).
- Files: fo_test_harness.py (_triage_pre_qa_strategy + routing block + max_tokens override)
⬜ TODO for FO codebase

40. Triage content extraction bug — wrong key on ChatGPTClient response
- `_triage_and_sharpen_defects()` called `result.get('content','')` but ChatGPTClient returns
  raw OpenAI dict: content is at `choices[0].message.content`. Triage silently returned empty
  string on every call — zero sharpening for the entire first run with the feature.
- Fix: `result.get('choices',[{}])[0].get('message',{}).get('content','')`
- Files: `fo_test_harness.py` (_triage_and_sharpen_defects)
⬜ TODO for FO codebase

39. Defect triage + fix sharpening after Feature QA rejection
- Root cause: vague Fix fields ("update the validation logic") → Claude guesses differently each
  time → defect oscillates 10+ iterations. Even surgical patch can't help if the Fix is ambiguous.
- New step after hallucination filter: _triage_and_sharpen_defects() calls gpt-4o-mini on all
  surviving defects. Classifies each as SURGICAL (line-level, sharpened Fix), SYSTEMIC (architectural
  rethink, full build), or INVALID (scope creep, drop). ALL invalid → flip verdict to ACCEPTED.
- _triage_strategy loop variable routes into prompt selection: SYSTEMIC → full build forced.
- Non-QA gate iterations reset _triage_strategy='surgical' so it doesn't bleed across gate types.
- New methods: _triage_and_sharpen_defects(), _parse_triage_output(), _build_intake_summary_for_triage()
- Files: fo_test_harness.py
⬜ TODO for FO codebase

38. QA defect fix — surgical patch for targeted QA fixes (≤5 defect files)
- Single-file QA defect triggered full build prompt → Claude regenerated all files from memory
  → new consistency defects undid a clean consistency pass.
- Fix: defect_source='qa' with ≤5 known target files → surgical patch (integration_fix_prompt)
  with current file contents. >5 files or no known targets → full build (unchanged).
- Files: `fo_test_harness.py` (new QA surgical branch in prompt selection logic)
⬜ TODO for FO codebase

## Build Pipeline (2026-03-08)

36. Consistency fallthrough with HIGH issues → full-build fix, not QA passthrough
- Fallthrough with HIGH issues cleared all defect context → QA accepted broken builds.
- Fix: HIGH issues at fallthrough → full-build Claude pass (defect_source='qa', 16384 tokens)
  with consistency issues as QA defects. Only LOW/MEDIUM → fall through to QA as before.
- Files: `fo_test_harness.py` (consistency fallthrough block in execute_build_qa_loop)
⬜ TODO for FO codebase

35. Dynamic token limit for multi-file surgical patches
- get_max_tokens() now takes n_target_files: 1 file → 8192, ≥2 files → 16384.
- With current file contents in the prompt, 8192 output tokens forces Claude to compress
  complete files to fit — dropping methods/logic and creating new defects.
- Files: `fo_test_harness.py` (Config.get_max_tokens signature + call site)
⬜ TODO for FO codebase

34. Surgical patch for ALL targeted fix types (static/consistency/quality/compile/integration)
- All non-QA defect sources now use the same surgical patch: current file contents passed
  to Claude for every targeted fix. The previous static→pattern-based split was wrong.
- Single branch, single prompt (integration_fix_prompt / build_integration_fix.md).
- build_integration_fix.md header updated to generic "SURGICAL PATCH", added Tenancy + auth
  import rules from old static_fix template so nothing is lost.
- Files: `fo_test_harness.py` (collapsed to single branch), `directives/prompts/build_integration_fix.md`
⬜ TODO for FO codebase

33. Consistency fix — surgical patch with current file contents (extends item 32)
- Same root cause as integration: consistency patch had no current file contents → Claude
  rewrote service files from memory → dropped existing methods → static gate looped.
- defect_source='consistency' now routes to integration_fix_prompt (surgical) instead of
  static_fix_prompt. Both consistency and integration use build_integration_fix.md template.
- static/quality/compile keep static_fix_prompt (pattern-based — their defects are structural).
- New FOHarness._read_target_file_contents(iteration, target_files) helper shared by both paths.
- Files: `fo_test_harness.py` (prompt routing, new helper method)
⬜ TODO for FO codebase

32. Integration fix — surgical patch with current file contents (defect_source='integration')
- Root cause: integration warm-start used defect_source='static' → static_fix_prompt → Claude
  reconstructs model files from memory → wrong Base import / duplicate __tablename__ → static
  gate loops 12+ iterations → integration issues never resolved.
- Fix: new defect_source='integration' routes to new integration_fix_prompt() which reads actual
  current file text from prev-iteration artifacts dir and passes it in the prompt.
- New template: build_integration_fix.md — hard-prohibits touching __tablename__, Base import,
  existing Columns. Claude only adds the specific fields/lines listed in the defect.
- Config.get_max_tokens() includes 'integration' in patch group (8192 tokens, not 16384).
- Files: `fo_test_harness.py` (defect_source, prompt branch, file-content reader),
  `directives/prompts/build_integration_fix.md` (new template)
⬜ TODO for FO codebase

31. integration_check.py — post-build integration validator
- Standalone script: 4 deterministic checks (no AI), outputs integration_issues.json
- Checks: route inventory, model field refs, spec compliance, import chains
- fo_test_harness.py: --integration-issues flag seeds Claude fix pass from JSON
- Catches missing routes, model field gaps, spec mismatches AFTER QA accepts
- Validated: caught 4 real bugs manually missed in AWI final build
- Files: `integration_check.py` (new), `fo_test_harness.py` (--integration-issues arg + warm-start block)
⬜ TODO for FO codebase

## Deploy Pipeline (2026-03-08)

27. Full pipeline auto-wiring: Auth0 + CORS + ENVIRONMENT
- `pipeline_deploy.py` now handles the full post-deploy wiring automatically:
  - Pre-flight: checks ACCESSKEYS for auth0_<app>.env, injects into repo .env
  - After Vercel: pushes CORS_ORIGINS + ENVIRONMENT=production to Railway via API
  - After Vercel: patches Auth0 SPA callback URLs (if AUTH0_MGMT_TOKEN set)
- One-time per app: `python deploy/auth0_setup.py --app-name <name>`
- All 40 apps share one Auth0 tenant; each gets its own Application + API
⬜ TODO for FO codebase

30. repo_setup.py — grant Railway + Vercel GitHub App access to a repo
- Railway errors "Repository not found or not accessible" because Railway's GitHub App
  isn't granted access to the repo. Must be done before pipeline_deploy runs.
- `GET /user/installations` API fails with 403 for PATs (requires special OAuth scope).
- `deploy/repo_setup.py`: verifies repo exists via GitHub API, then opens
  github.com/settings/installations in browser with printed step-by-step instructions.
- Reads GITHUB_USERNAME + token from ACCESSKEYS automatically. Run once per new repo.
⬜ TODO for FO codebase

29. Railway env var three-tier fallback: API → CLI → console paste
- GraphQL `variableUpsert` fails for project tokens and some personal tokens.
- Tier 1: `variableCollectionUpsert` (bulk GraphQL)
- Tier 2: `railway variables --set` CLI via subprocess with RAILWAY_TOKEN env var
- Tier 3: print failed vars + dashboard URL to console for manual paste
- Applies to both initial .env vars (railway_deploy.py) and post-Vercel CORS/ENVIRONMENT (pipeline_deploy.py)
⬜ TODO for FO codebase

28. Railway variableCollectionUpsert fallback
- `variableUpsert` fails with "Repository not accessible" for some Railway token types
  even when deploy/trigger works. The mutation validates GitHub repo access unnecessarily.
- Fix: try `variableCollectionUpsert` (bulk mutation) first — bypasses GitHub validation.
  Falls back to `variableUpsert` if bulk also fails.
⬜ TODO for FO codebase

26. railway.deploy.json stores environment_id
- Railway GraphQL `get_environment_id` silently fails for some account types.
- Fix: store `environment_id` in `railway.deploy.json` after first deploy.
  Script reads it directly, skipping the unreliable API lookup.
⬜ TODO for FO codebase

25. Vercel set_env_var upserts (PATCH on 400/409)
- Vercel returns 400 (not 409) for duplicate env vars on some API versions.
- Fix: on 400/409, fetch existing env var ID and PATCH instead of failing.
⬜ TODO for FO codebase

24. Set CI=false in Vercel deploy
- Vercel sets `CI=true` by default → `react-scripts build` treats ESLint warnings as errors → build fails.
- Fix: `deploy/vercel_deploy.py` injects `CI=false` into env vars before triggering deploy.
- Affects any CRA (create-react-app) frontend. Vite frontends are not affected.
⬜ TODO for FO codebase

## New Hardening Bundle (2026-03-07)

23. Prune boilerplate-owned frontend configs
- `BOILERPLATE_VALID_PATHS` whitelisted tailwind/next/postcss configs under business/frontend/.
  Claude generates them for dashboard builds → static Check 8 fires → static loop.
- Fix: `BOILERPLATE_OWNED_FRONTEND_CONFIGS` set; pruner drops them before whitelist check.
- Also updated `build_boilerplate_path_rules.md` with explicit NEVER rules per filename.
⬜ TODO for FO codebase

22. Polish test generation regex fix
- Test extraction regex `(?:javascript|js|typescript|ts)?` missed Python fences entirely.
- 62-second Claude call, $0.09 cost, 0 files saved every run with Python backend.
- Fixed to `(?:\w+)?` — matches any language tag.
⬜ TODO for FO codebase

21. Patch iteration token reduction (16384 → 8192) + consistency hard cap
- `Config.get_max_tokens(iteration, defect_source)` returns 8192 for
  static/consistency/quality/compile patch iterations (only 1-3 files output).
  Returns 16384 for QA-driven or first-build iterations (full regeneration).
- `Config.CLAUDE_MAX_TOKENS_PATCH = 8192`, `Config.MAX_CONSISTENCY_CONSECUTIVE = 4`
- Consistency hard cap: after 4 consecutive consistency-only iterations, fall through
  to Feature QA. Same pattern as MAX_STATIC_CONSECUTIVE=6 (Fix 3).
- FO production equivalent: any AI patch loop needs both a token budget cap
  (patch ≠ full build) and an iteration hard cap with fallthrough.
⬜ TODO for FO codebase

19. Static Check 13: missing frontend pages in boilerplate mode
- If backend routes exist (`business/backend/routes/*.py`) but no
  `business/frontend/pages/*.jsx` files found → HIGH defect.
- Catches zero-frontend builds before QA filter removes all evidence-fabricated
  defects and flips verdict to ACCEPTED on a skeleton.
- Also added MANDATORY OUTPUT REQUIREMENTS to `build_boilerplate_path_rules.md`
  explicitly requiring at least 1 .jsx page per user-facing feature, and clarifying
  that Shopify integration does NOT substitute for React dashboard pages.
⬜ TODO for FO codebase

18. Static loop anti-repetition: Fix 1/2/3
- Fix 1: Defect fingerprint tracking — when same (file, issue) appears 3+
  consecutive static iterations, marks defect `stuck=True` to trigger joint rebuild.
- Fix 2: `_run_static_check` Check 10 now embeds `related_files=[service_file]` on
  missing-method defects; `defect_target_files` calculation auto-includes these so
  Claude regenerates BOTH route and service in one shot.
- Fix 3: `Config.MAX_STATIC_CONSECUTIVE = 6` hard cap — after 6 consecutive
  static-only iterations, fall through to Feature QA instead of continuing to burn
  iterations on targeted patches that can't resolve cross-file method name mismatches.
- All three implemented in `fo_test_harness.py`: `Config`, `_run_static_check`,
  `defect_target_files` calculation block, and GATE 2 static check fail block.
⬜ TODO for FO codebase

17. --prior-run flag: cross-run prohibition tracker seeding
- New `--prior-run <dir>` flag on `fo_test_harness.py` seeds the warm-start
  recurring_tracker from a prior run's QA reports before the build loop starts.
- Without this, every new feature run starts with an empty prohibition tracker
  even when prior phases burned many iterations learning Claude's failure modes.
- FO production equivalent: the build orchestrator should carry prohibition
  state forward across all sequential builds in a feature pipeline.
⬜ TODO for FO codebase

16. run_feature_build.sh + feature_adder.py — feature-by-feature build pipeline
- `feature_adder.py`: scopes a single-feature intake from an existing build ZIP;
  auto-populates do-not-regenerate list; chains sequentially between features.
- `run_feature_build.sh`: full pipeline wrapper — phase_planner → Phase 1 →
  feature loop → final ZIP merge. Default 20 iterations per step.
- FO production equivalent: a pipeline orchestrator in the intake/build system
  that sequences phased builds and feature additions automatically.
  Candidate for a standalone FO build orchestration service.
⬜ TODO for FO codebase

15. phase_planner: combined_task_list fallback for task-list format intakes
- phase_planner now reads `pass_4.combined_task_list` (build-classified tasks)
  when standard FEATURE_KEYS scan returns 0 features.
- Required for older intake format (wynwood_thoroughbreds style).
⬜ TODO for FO codebase

13. Frontend compile check: npm install before npm run build
- GATE 0 frontend compile now runs `npm install --prefer-offline --silent`
  before `npm run build` on the generated artifacts dir.
- Without this, vite/webpack/next are never installed and the compile check
  always fails with `sh: vite: command not found` even on correct code.
- FO production equivalent: same fix needed in any harness or CI pipeline
  that runs a build check on freshly generated frontend artifacts.
⬜ TODO for FO codebase

## New Hardening Bundle (2026-03-06)
1. Narrowed QA comment-only filter (Check 6)
- Only suppresses comment-only defects when evidence explicitly states scope exclusion
  (`not in scope`, `per intake requirements`, etc.).
- Prevents false negatives on real missing implementations hidden behind comments.

2. Static check expansions
- Added deterministic checks for:
  - router code inside `business/models/*`
  - executable route files with no endpoints
  - frontend config file swaps/mismatches (`next.config.js`, `postcss.config.js`, `tailwind.config.*`)
  - local import integrity (module exists, case-sensitive path match, imported symbol exists)
  - route↔service contract sanity (constructor arity + missing method call)
  - intake-aware KPI contract validation
  - intake-aware downloadable-report contract validation

3. Static requirements path bug fix
- `business/backend/requirements.txt` now checked for YAML/docker-compose contamination.

4. Gate telemetry + terminal consistency pass
- Added per-iteration gate telemetry logging (Feature QA / Static / Consistency).
- Added final consistency pass on terminal failure paths (max-iter/non-converging/verdict unclear)
  with `final_consistency_report` log output.

5. AI consistency prompt extensions
- Added frontend API URL ↔ backend route check guidance.
- Added React hook misuse check guidance.
⬜ TODO for FO codebase

6. Post-QA testcase doc generation (ChatGPT, directive-driven)
- New polish pass generates `business/docs/TEST_CASES.md`.
- New directive template file: `directives/qa_testcase_doc_directive.md`.
- New wrapper prompt: `directives/prompts/polish_testcases_wrapper_prompt.md`.
- New CLI override: `--qa-testcase-directive <path>`.
- Directive is intended to be edited over time (add/remove testcase requirements without code edits).
- Directive now includes:
  - Playwright conversion plan
  - Postman suite conversion plan (collection/folder layout, vars, auth scripts, Newman/CI notes)
⬜ TODO for FO codebase

7. Optional Gate 4 quality gate + LOW-accept policy
- New optional flag: `--quality-gate` (default OFF).
- New prompt template: `directives/prompts/build_quality_gate.md`.
- Gate evaluates: completeness vs intake, code quality, enhanceability, deployability.
- Current policy: gate passes when completeness/code quality/deployability are PASS or LOW.
⬜ TODO for FO codebase

8. Auth0 hallucination filter hardening (Fix 0)
- QA problem text matching is now paraphrase-tolerant for Auth0 false positives.
- If evidence shows correct `useAuth0()` destructuring of `getAccessTokenSilently`, defect is removed
  regardless of exact problem wording.
⬜ TODO for FO codebase

10. CHECK 10 SQLAlchemy ORM exclusion
- Constructor arity and method-existence checks now skip ORM model classes
  (classes with `__tablename__` or inheriting from `Base`/`TenantMixin`).
- Without this, `ModelClass(**data)` is incorrectly flagged as arity mismatch
  (SQLAlchemy metaclass generates `__init__` automatically).
⬜ TODO for FO codebase

12. --no-polish flag + phased build wrapper
- New `--no-polish` CLI flag on `fo_test_harness.py`: skips `_post_qa_polish` on all
  exit paths. Designed for Phase 1 of a phased build where polish on the intermediate
  data layer is wasteful — README/.env/tests should only be generated once, after the
  final intelligence layer is accepted.
- New `run_phased_build.sh`: orchestrates Phase 1 (--no-polish) → Phase 2 (with polish)
  → ZIP merge. Not a harness change — an operator workflow tool.
- FO production equivalent: phased build orchestration in the intake pipeline or
  a CI job that sequences two harness runs and merges their artifacts.
⬜ TODO for FO codebase

11. phase_planner.py — phased build pre-processor (threshold: 3 features)
- New standalone tool: `phase_planner.py` in project root.
- Not a harness change — a pre-run planning tool.
- Produces scoped phase1/phase2 intake JSON files for complex projects.
- FO production equivalent: intake pipeline pre-processor step before BUILD.
- Port consideration: integrate phase assessment into intake pipeline output
  so operators are warned before attempting a single-shot build of a
  complex project (>5 features or 3+ KPIs).
⬜ TODO for FO codebase

9. Intake-aware contracts generalized (Checks 11/12)
- KPI contract check now recursively discovers KPI keys/values across intake JSON (not just one schema path).
- Download/export contract check now derives requirement from intake-wide text and validates backend routes
  for explicit download/export markers.
⬜ TODO for FO codebase

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

31. Filter Check 6: comment-only evidence removal ✅ DONE (2026-03-06)
    - If ALL backtick evidence snippets in a defect start with # or //, it's a code comment.
    - Stub files Claude creates to satisfy scope complaints (e.g. `# No endpoints - X not in scope`)
      are intentional — QA flagging the comment is invalid.
    - Added after Check 3 (fabricated evidence) in _filter_hallucinated_defects().
    - Removes stub-comment defects like: clients.py, workforce_data.py, engagements.py scope complaints.
    ⬜ TODO for FO codebase

30. Unified QA loop: Compile → Static → AI Consistency → Quality → Feature QA ✅ DONE (2026-03-06)
    - Updated gate order: `0 -> 2 -> 3 -> 4 -> 1` (`compile -> static -> consistency -> quality -> feature QA`).
    - Single unified while loop; no nested sub-loops. Mandatory gates pass in sequence before success.
    - defect_source ('qa'|'static'|'consistency') selects build prompt type for Claude.
    - GATE 2: _run_static_check() runs pre-QA each iteration.
    - GATE 3: _run_ai_consistency_check() runs pre-QA each iteration; Claude reads all business/ files, checks cross-file
      consistency (model↔service, schema↔model, route↔schema, import chains, duplicate subsystems).
    - GATE 4: quality gate is mandatory (no optional runtime behavior).
    - CHECK 10 guard added: SQLAlchemy ORM model classes (`__tablename__` or `Base`/`TenantMixin`) are excluded
      from route↔service constructor/method contract validation to prevent false-positive loops.
    - Per-iteration defect batching added: cap to 6 prioritized defects (severity + runtime/contract/import criticality)
      to reduce fix-churn and prevent broad unintended code changes.
    - _parse_consistency_report(), _format_consistency_defects_for_claude() for parsing/formatting.
    - _run_ai_consistency_check_standalone() for --ai-check CLI mode.
    - New template: directives/prompts/build_ai_consistency.md (5-check prompt, PASS/REPORT contract).
    - PromptTemplates.ai_consistency_prompt(file_contents: dict): renders template with artifact contents.
    - --ai-check <artifacts_dir>: standalone AI check, requires ANTHROPIC_API_KEY, exits 0/1.
    - --resume-mode consistency: skip static, run AI check only; fall through to main loop if fails.
    - --resume-mode static: updated to run both static + AI consistency; early exit if all pass.
    - Removed: _run_static_fix_loop(), Config.MAX_STATIC_ITERATIONS, --max-static-iterations.
    - Post-loop: _qa_accepted_at_iter gates polish; _loop_success sets return value.
    ⬜ TODO for FO codebase

29. Bugfix: _run_static_fix_loop wrong extraction method ✅ DONE (2026-03-05)
    - self.artifacts.extract_artifacts() does not exist. Use save_build_output(extract_from=...)
      then extract_file_paths_from_output() for merge_forward path list. Same pattern as main loop.
    ⬜ TODO for FO codebase

28. Static check CLI modes ✅ DONE (2026-03-05)
    - --static-check <artifacts_dir>: standalone lint, no API calls, exits 0/1.
    - --resume-mode static: skip main loop, find last accepted iter, run static fix loop + polish.
    - _find_last_accepted_iteration(run_dir): scans qa/ for highest ACCEPTED report.
    - _run_static_check + _format_static_defects_for_claude promoted to @staticmethod.
    - Positional args made optional (nargs='?') with conditional validation.
    ⬜ TODO for FO codebase

27. Post-QA static check loop ✅ DONE (2026-03-05)
    - Config.MAX_STATIC_ITERATIONS = 5; --max-static-iterations CLI flag.
    - FOHarness._run_static_check(): 6 checks (AST syntax, duplicate __tablename__, missing TenantMixin
      import, wrong Base import, requirements.txt YAML contamination, unauthenticated routes).
    - FOHarness._format_static_defects_for_claude(): formats list for Claude prompt.
    - FOHarness._run_static_fix_loop(): Claude fix → merge → Feature QA → static check loop (cap N).
    - PromptTemplates.static_fix_prompt(): renders new build_static_fix.md template.
    - directives/prompts/build_static_fix.md: thin template, patch-first contract, boilerplate imports.
    - Main loop ACCEPTED block: calls _run_static_fix_loop() before _post_qa_polish().
    ⬜ TODO for FO codebase

26. Fix B: Truncate build output at PATCH_SET_COMPLETE before artifact extraction ✅ DONE (2026-03-05)
    - PATCH_SET_COMPLETE_MARKER constant added at module level.
    - save_build_output(): new optional extract_from param — saves full raw output to disk,
      runs extraction on extract_from if provided.
    - Main loop: on patch iterations, if PATCH_SET_COMPLETE is in build_output, truncate to
      build_output_for_extraction = text up to and including marker. Extra files after marker
      logged as [PATCH_SET_COMPLETE] warning and discarded. merge_forward and pending_resolution
      also use build_output_for_extraction, not full build_output.
    ⬜ TODO for FO codebase

25. Fix A: Rebuild recurring_tracker on resume ✅ DONE (2026-03-05)
    - After warm-start setup block: if _ws_run_dir.is_dir(), scan qa/iteration_*_qa_report.txt
      and reconstruct recurring_tracker + prohibitions_block before loop starts.
    - Console: "Warm-start tracker rebuilt: N defect(s) tracked, M prohibition(s) active"
    - Prevents prohibition knowledge loss across --resume-run restarts.
    ⬜ TODO for FO codebase

24. Resolved defects tracker (anti-ping-pong) ✅ DONE (2026-03-05)
    - Harness: _extract_fixed_from_patch(), _confirm_resolutions(), _build_resolved_defects_block()
      Three new static methods on FOHarness. Loop wired: pending_resolution set + resolved_tracker dict
      initialized in execute_build_qa_loop(). After each Claude build: extract pending FIXED.
      After each QA+filter: confirm or warn PING-PONG. Console: [RESOLVED] / [PING-PONG] / [PENDING].
    - qa_prompt(): resolved_defects_block param added; passed to DirectiveTemplateLoader.render().
    - qa_prompt.md: {{resolved_defects_block}} placeholder added after {{defect_history_block}}.
      Block tells QA: these were senior-dev-confirmed fixed — only re-flag with verbatim evidence.
    ⬜ TODO for FO codebase

23. QA middle-tier: defect history + prohibition awareness + root cause classification ✅ DONE (2026-03-05)
    - qa_prompt.md: {{prohibitions_block}} and {{defect_history_block}} injected before intake.
      Root cause types (ONE-TIME-BUG | SCOPE-BOUNDARY | RECURRING-PATTERN) added to defect format.
      Fix field rules require categorical statements for scope/recurring defects.
      Root cause type field added to DEFECT output format.
    - Harness: _build_qa_defect_history(), qa_prompt() extended, call site wired.

22. Claude thinking stage + permanent prohibitions ✅ DONE (2026-03-05)
    - build_patch_first_file_lock.md: ## DEFECT ANALYSIS section added as step 1 of OUTPUT CONTRACT.
      Per defect: root cause, pattern type, reintroduction risk, categorical commitment.
    - build_previous_defects.md + build_patch_first_file_lock.md: {{prohibitions_block}} placeholder.
    - Harness: _extract_defects_for_tracking(), _build_prohibitions_block(), recurring_tracker dict,
      prohibitions_block var — after 2+ appearances of same (location, classification), promoted to
      hard prohibition and injected into every subsequent patch prompt.
    - build_prompt(): new prohibitions_block param passed to both template renders.

21. QA prompt + harness filter: ignore __init__.py defects ✅ DONE (2026-03-05)
    - qa_prompt.md: __init__.py added to DO NOT FLAG list.
    - _filter_hallucinated_defects() check 1b: removes any defect whose Location is an __init__.py.

20. Exclude __init__.py from whitelist and remap ✅ DONE (2026-03-05)
    - `*.py` patterns in BOILERPLATE_VALID_PATHS matched __init__.py via fnmatch → carried forward
      indefinitely by merge_forward → attracted bogus QA defects.
    - Fix: _is_valid_business_path() rejects __init__.py; _remap_to_valid_path() returns None for it.
    - build_boilerplate_path_rules.md: blanket prohibition on any __init__.py under business/**.

19. ZIP packager: guard against empty run_dir + skip nested ZIPs ✅ DONE (2026-03-04)
    - `run_dir = Path('.')` caused `run_dir.name == ''` → ZIP named `.zip`, rglob swept entire repo → 38GB corrupt file.
    - Fix: early ValueError guard on empty name / cwd resolve; `.zip` excluded from all rglob passes;
      write-then-rename pattern; `resume_run` validation in FOHarness.__init__ rejects . / .. / cwd.

18. Filter: banned evidence phrases + presence validation + ORM package allowlist ✅ DONE (2026-03-04)
    - Three new checks added to _filter_hallucinated_defects():
      Check 2: Evidence containing N/A/"not applicable"/"presence of the file is confirmed" etc. → auto-remove
      Check 4: Presence claim ("no .jsx files", "missing routes") contradicted by actual build output → auto-remove
    - qa_prompt.md: Added sqlalchemy, psycopg2, pydantic, fastapi, uvicorn, httpx, python-jose etc. to
      DO NOT FLAG — these are valid external packages, not stdlib. QA was flagging sqlalchemy as stdlib.
    - New class attributes on FOHarness: _BANNED_EVIDENCE_PHRASES (10 phrases), _PRESENCE_CLAIMS (8 patterns)

17. EXPLAINED resolution path per fo_build_qa_defect_routing_rules.json ✅ DONE (2026-03-04)
    - Build governance defines FIXED + EXPLAINED as the two valid resolution modes.
      Our prompts only implemented FIXED. EXPLAINED path was completely absent.
    - Fix (4 parts):
      a) `build_previous_defects.md`: Added EXPLAINED format. Claude can emit `## DEFECT RESOLUTIONS`
         block with `DEFECT-N: EXPLAINED` + governance rule citation. Valid cases listed.
      b) `build_patch_first_file_lock.md`: Same. OUTPUT CONTRACT updated.
      c) `qa_prompt.md`: Added STEP 0 — evaluate EXPLAINED resolutions before artifact check.
         QA uses a validity table to accept or reject each explanation.
      d) `fo_test_harness.py`: `_extract_defect_resolutions()` detects resolutions block in
         Claude's output; prepends as `## CLAUDE DEFECT RESOLUTIONS` in qa_build_output.

16. Harness-level defect filter: remove hallucinated/out-of-scope QA defects ✅ DONE (2026-03-04)
    - gpt-4o-mini fabricates evidence (quotes code that doesn't exist) and evaluates files outside business/**.
      This caused 3-iteration runs on 100% invalid defects with zero real fixes needed.
    - Fix: `_filter_hallucinated_defects(qa_report, qa_build_output)` added to FOHarness.
      Two checks per defect:
      1. Location must start with `business/` — else remove
      2. Backtick-quoted snippets (>8 chars) in Evidence must appear in build output — else remove (fabricated)
    - If all defects filtered → verdict flipped to ACCEPTED (saves full patch iteration)
    - Raw QA report saved to logs/ for debugging when filtering occurs
    - Called immediately after QA response, before save_qa_report()
    - Verified: would have caught all 7 invalid defects across 3 iterations of run 20260303_131548

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

33. Stop pruning unmappable business/ files — leave for QA ✅ DONE (2026-03-04)
    - Whitelist was growing every run. Wrong approach — whack-a-mole.
    - Pass 2 now only hard-deletes exact duplicates of canonical-path files.
      Everything else unmappable is left in place for QA to evaluate.
    - merge_forward already gates on whitelist — unmapped files won't accumulate.

    | What happens now                              | Why                                      |
    |-----------------------------------------------|------------------------------------------|
    | Non-business file with a remap                | Moved to canonical path                  |
    | Non-business file, no remap                   | Deleted (truly outside the project)      |
    | business/ file with a remap                   | Moved to canonical path                  |
    | business/ file that's a duplicate             | Deleted (canonical version exists)       |
    | business/ file, no remap, not duplicate       | Left in place for QA                     |
    | Any file in merge_forward not on whitelist    | Not carried forward (no accumulation)    |

32. Pruner: keep business/frontend/*.jsx and *.css ✅ DONE (2026-03-04)
    - App.jsx and App.css at the frontend root were pruned — whitelist only covered
      pages/*.jsx and styles/*.css, not root-level frontend files.
    - Fix: added business/frontend/*.jsx and business/frontend/*.css to whitelist.

31. Test file handling: visible to QA, not carried forward, included in ZIP ✅ DONE (2026-03-04)
    - Tests were pruned before QA saw them → QA flagged "missing tests" MEDIUM → wasted iteration.
    - Fix: tests survive pruner (added to whitelist), excluded from merge_forward (no accumulation).
    - Tests ARE included in ZIP — ZIP is a full project handoff, founder needs tests for local dev.

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

45. Extractor: checksum-based overwrite — prefer new over size heuristic ✅ DONE (2026-03-04)
    - Size heuristic (keep larger) caused defect-fix output to be discarded when fix made
      file slightly smaller. New logic: identical → skip; tiny stub → skip; otherwise → prefer new.

44. QA prompt: ban "Not applicable" evidence phrases ✅ DONE (2026-03-04)
    - "(Not applicable as specific dependencies are missing)" was being used as Evidence
      for fabricated defects. Added to banned Evidence phrases alongside "Content not present".

43. Build prompt: block boilerplate internal file creation ✅ DONE (2026-03-04)
    - Claude generated backend/app/middleware/auth.py, backend/app/utils/calculations.py
      despite backend/ being in the HARD FAIL list. When defects mention "missing auth" or
      "missing utils", Claude creates infrastructure files instead of using boilerplate imports.
    - Fix: BOILERPLATE BOUNDARY table in build_boilerplate_path_rules.md maps each wrong
      urge to the correct import. Rule 6 added to defect fix CRITICAL RULES. "IF A DEFECT
      MENTIONS MISSING AUTH" section added to build_previous_defects.md.

42. Pruner: remap requirements.txt + root-level config files + JS tests ✅ DONE (2026-03-04)
    - requirements.txt (at any path) → business/backend/requirements.txt (added to whitelist)
    - Root-level package.json, next.config.js, postcss.config.js, tailwind.config.js,
      jest.config.js, jest.setup.js: remap now unconditional (was only when 'frontend' in parts)
    - .test.js / .spec.js files: added JS test remap → business/tests/<name>
    - Whitelist: added business/backend/requirements.txt, business/tests/*.js|jsx|ts|tsx,
      business/frontend/jest.config.js|ts, business/frontend/jest.setup.js|ts

41. Build prompt: harden Auth0 token rule — prevent per-file regression ✅ DONE (2026-03-04)
    - user.getAccessTokenSilently() appeared in every new JSX file Claude generated across
      3 iterations. Rule existed as explanatory text but not in enforcement gates.
    - Fix: (1) Added to HARD FAIL CONDITIONS in build_boilerplate_path_rules.md with "QA will
      REJECT every time" framing. (2) Added to PRE-PROMPT CHECKLIST — Claude must scan every
      .jsx file before output. (3) Made rule unconditional in build_previous_defects.md —
      was "if any defect mentions it", now "applies to every JSX file, no exceptions".

40. QA prompt: current_user["sub"] + package version DO NOT FLAG rules ✅ DONE (2026-03-04)
    - `current_user["sub"]` flagged as "hardcoded user ID" — it's the correct dynamic auth ID
      from Depends(get_current_user). Added explicit DO NOT FLAG with definition of what
      hardcoding actually means (literal strings like "user_123", not current_user["sub"]).
    - React 18 flagged as "should upgrade to React 19" — version choices are not defects.
      Added DO NOT FLAG: versions are not wrong unless intake spec requires a specific one.

39. Pruner: checksum-based duplicate detection ✅ DONE (2026-03-04)
    - Before: duplicate detection was size-based heuristic; conflicts silently discarded.
    - Now: SHA256 both files before pruning. Identical → safe prune. Different → CONFLICT
      warning visible in log so content loss is never silent.
    - Added _sha256() static helper on ArtifactManager.

38. Pruner: remap tests/*.py + fix app router page.tsx name collision ✅ DONE (2026-03-04)
    - tests/test_*.py had no remap → pruned. Fix: added tests/ rule → business/tests/<name>.
    - frontend/src/app/clients/page.tsx, app/assessments/page.tsx etc. all remapped to
      business/frontend/pages/page.jsx (same name → overwrote each other). Fix: when
      name is page.tsx/jsx/js and 'app' in path, derive component name from route segments:
      app/clients/page.tsx → Clients.jsx, app/clients/new/page.tsx → ClientsNew.jsx.

37. QA prompt: hedged language + self-contradicting evidence + inference bans ✅ DONE (2026-03-04)
    - iter 3 DEFECT-3: Evidence said "No .jsx files are absent" but Problem said ".jsx absent" —
      self-contradicting. iter 4 DEFECT-1: inferred handleDelete is broken from call site only.
      iter 4 DEFECT-2: used correct Auth0 destructuring as evidence for a missing auth check.
      iter 3+4 DEFECT-4: flagged a Column default value as a scope violation.
    - Fix: 4 new ABSOLUTE RULES in qa_prompt.md:
      1. Hedged language ban: "does not seem to", "may suggest", "could indicate" etc. = delete
      2. Self-contradicting Evidence ban: Evidence must support the Problem, not contradict it
      3. SCOPE_CHANGE column ban: column/field/default alone ≠ user-facing feature
      4. Call-site inference ban: must quote function body, not just the call site

36. QA prompt: fabricated Evidence phrases + core.database false positive ✅ DONE (2026-03-04)
    - QA was writing MEDIUM defects for package.json and README-INTEGRATION.md with Evidence
      "Content of this file is not present in the build output" — fabricating content defects
      for files it never read. Existing absence-of-thing rule was not specific enough.
    - QA was also flagging `from core.database import Base, get_db` as a DB integration bug
      despite an existing DO NOT FLAG rule — the rule was buried in the DO NOT FLAG list and ignored.
    - Fix: added two new ABSOLUTE RULES to qa_prompt.md (violations = invalid QA report):
      1. Evidence fields with "Content of this file is not present", "file not shown", or
         equivalent phrases are forbidden — if you can't read the file, delete the defect.
      2. Any defect citing `from core.database import Base, get_db` as wrong must be deleted —
         this is the correct boilerplate import.

35. QA prompt: test file rules, absence defects, stdlib in requirements ✅ DONE (2026-03-04)
    - QA flagged intentional test behaviour as IMPLEMENTATION_BUG (test sending invalid JSON).
      Fix: only flag literal bugs in test code; never flag what a test intentionally tests.
    - QA invented defects about missing comments/tests for specific files (absence-of-thing).
      Fix: absence defects invalid unless intake spec required them; Evidence must be quotable.
    - Added: stdlib modules in requirements.txt (uuid, os, etc.) = MEDIUM defect.

34. --qa-wait CLI flag for TPM cooldown, default 0 ✅ DONE (2026-03-04)
    - Hardcoded 120s wait before iteration 2+ QA calls removed; now --qa-wait <seconds>.
    - Default 0 (no wait). Use --qa-wait 120 when hitting TPM 429s.

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
