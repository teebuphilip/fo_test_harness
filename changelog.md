# Changelog

## 2026-03-22 (session 15 — config shape fix)

### fix: cta_primary/cta_secondary crash — objects → strings
`generate_business_config.py` generated `home.hero.cta_primary` and `cta_secondary` as
`{"label": "...", "href": "..."}` objects. Home.jsx renders these directly as JSX text
(`{home.hero.cta_primary}`), which crashes React when it receives an object instead of a string.
Fixed to emit plain strings: `"Get Started"`, `"Learn More"`.

Re-ran on wynwood-thoroughbreds and committed fixed config.

Files: `generate_business_config.py`

---

## 2026-03-20 (session 14 — business_config.json + pipeline logging)

### feat: generate_business_config.py — standalone post-merge config generator
- New script that inspects actual built artifacts (`business/frontend/pages/*.jsx`) to discover pages
- Converts PascalCase → kebab-case (same logic as boilerplate `loader.js`)
- Populates `dashboard.nav_items` and `footer.columns["Product"]` from real built pages
- Fills business metadata, branding, pricing, Stripe/Auth0/Mailerlite placeholders from intake
- Writes to all config locations: `business/*/config/`, `frontend/src/config/`, `backend/config/`
- Supports `--dir` (flat/merged dir), `--zip` (extract → generate → re-pack), and `--dry-run`
- No AI cost — pure file inspection + JSON generation

### fix: business_config.json missing from final ZIP (TODO #12)
**Root cause:** `fo_test_harness.py:_generate_business_config()` only ran inside `_post_qa_polish()`,
which is skipped with `--no-polish`. All Phase 1, intermediate feature, and integration fix pass
builds use `--no-polish` → final merged ZIP never got a startup-specific config. The deployed app
read the boilerplate InboxTamer config → wrong business name, missing nav items, blank screen.

**Additional problem:** The harness config generator derived nav/footer from intake feature names,
not from actual built `.jsx` pages. Dashboard links pointed to generic `/dashboard` instead of
real routes like `/dashboard/horse-profiles`.

**Fix:** New standalone `generate_business_config.py` runs after final ZIP merge in
`run_integration_and_feature_build.sh`, inspecting the merged artifact tree. Wired into the
merge step between unzip and zip commands. Non-blocking (warns on failure, continues merge).

Files: `generate_business_config.py`, `run_integration_and_feature_build.sh`

### feat: riaf-logs pipeline logging
- `run_integration_and_feature_build.sh` now tees all stdout+stderr to `riaf-logs/`
- Log files are timestamped: `riaf-logs/riaf_YYYYMMDD_HHMMSS.log`
- Uses `exec > >(tee -a ...)` so all pipeline output (harness, integration check, merge) is captured

Files: `run_integration_and_feature_build.sh`

---

## 2026-03-20 (session 13 — Railway/Vercel deploy hardening)

### feat: Railway deploy automation now completes end-to-end domain provisioning
- `deploy/railway_deploy.py` now links GitHub repos with Railway `serviceConnect` instead of the broken `serviceUpdate` path
- Normalizes GitHub input from full URL to `owner/repo`
- Defaults branch to `main` and derives project name from the GitHub repo slug when not provided
- Reuses existing Railway project/service IDs via `--reuse` when `railway.deploy.json` is present
- Reuses an existing Railway service domain when present; otherwise generates one automatically
- Returns clearer result payloads: `deploy_status`, `url_pending`, and `environment_id`
- Distinguishes successful deploys with missing URL from real failures

### feat: pipeline_deploy.py now captures full run logs
- Added tee logging so all console output is written to `deploy/pipeline-deploy-logs/`
- Log filenames are timestamped per run
- Every log line in the file is prefixed with date + time

### feat: pipeline_deploy.py now persists Railway environment IDs
- Saves `environment_id` back into `railway.deploy.json`
- Uses Railway domain lookup first when resolving backend URLs for Vercel injection

### fix: Vercel CRA deploys no longer fail on CI lint gate
- `deploy/vercel_deploy.py` now injects `CI=false`
- For `create-react-app`, also injects `DISABLE_ESLINT_PLUGIN=true`
- Added explicit console output so the CRA lint-bypass guardrails are visible during deploy

### docs: deploy runbook updated
- `deploy/README.md` now documents:
  - automatic Railway domain generation/reuse
  - `pipeline_deploy.py` log file location
  - current deploy behavior around backend URL injection into Vercel

### note: upstream build artifact bug identified
- Final phase-planner ZIPs can miss generated `business_config.json` because post-QA polish is suppressed on the runs feeding the merged ZIP
- This was the root cause of Wynwood’s missing `business.description` crash on Railway startup


## 2026-03-19 (session 12 — slice planner repair bound)
### feat: slice_planner.py — bounded extra repair pass
- Added `--extra-repair` to allow one additional AI repair pass before strict validation
- Default remains single repair + deterministic sanitize; no infinite loops

## 2026-03-19 (session 11 — ubiquitous language extractor)

### feat: ubiquity.py — pre-planner terminology lock
- New `ubiquity.py` extracts canonical domain terms from intake JSON
- Extracts: entities, KPIs, user roles, integrations, synonym conflicts
- Deterministic synonym detection with known synonym groups
- Optional AI refinement via Claude Haiku (relationships, ambiguities)
- Outputs `<stem>_ubiquitous_language.json` with glossary + `prompt_lock_block`
- Costs logged to `phase_planner_ai_costs.csv`

### feat: wired into pipeline (run_integration_and_feature_build.sh)
- Added Step 0 before phase_planner (Step 1)
- Skips on resume if glossary already exists
- `$NO_AI` flag passed through from CLI

### feat: glossary injected into BUILD + QA prompts (fo_test_harness.py)
- `FOHarness.__init__` loads `_ubiquitous_language.json` at startup
- Falls back to base stem for entity-level intakes (`_p1_<entity>` suffix stripped)
- `PromptTemplates.build_prompt()` accepts `ubiquitous_language_block` kwarg
- Injected before PRE_OUTPUT_CHECKLIST in dynamic section
- `PromptTemplates.qa_prompt()` accepts `ubiquitous_language_block` kwarg
- Injected via `{{ubiquitous_language_context}}` in `qa_prompt.md` template

### inspiration
- Adapted from Matt Pocock's `ubiquitous-language` skill (https://github.com/mattpocock/skills)
- DDD-style glossary extraction, tailored for the FO pipeline

---

## 2026-03-19 (session 10 — slice planner + planner router)

### feat: slice_planner.py (AI-first, heuristic fallback)
- New `slice_planner.py` for quality-mode vertical slice planning
- Uses ChatGPT by default; `--no-ai` keeps heuristic-only behavior
- Logs AI costs to `slice_planner_ai_costs.csv` and prints cost summary

### feat: planner_router.py (phase vs slice selector)
- New lightweight router that recommends `phase` vs `slice` based on intake signals
- Outputs reasons and feature count; supports JSON output via `--json`

### feat: run_slicer_and_feature_build.sh (slice pipeline)
- New slice-based pipeline that consumes `*_slice_assessment.json` + slice intakes
- Chains slices via `--prior-run`, then runs integration check + ZIP merge

### feat: run_auto_build.sh (auto-route)
- Auto-routes to `run_slicer_and_feature_build.sh` or `run_integration_and_feature_build.sh`
- Supports `--force slice|phase` override

---

## 2026-03-18 (session 9 — Check 17 fix, check_final_zip.py)

### fix: Check 17 false positives on snake_case backend filenames (integration_check.py)
- `check_orphaned_pages()` now adds underscore-stripped variants to model/route/service name sets
- `horse_profile` → adds `horseprofile`, `horseprofiles` in addition to `horse_profile`, `horse_profiles`
- Fixes: `HorseProfiles.jsx` (stem `horseprofiles`) was never matched against `horse_profile.py`
- Helper `_name_variants()` centralises plural/singular/flat-underscore logic for all three sets
- Verified: Wynwood Check 17 now 0 issues (was 2 HIGH false positives)

### feat: check_final_zip.py — standalone quality check on final multi-entity ZIP
- Extracts full ZIP, finds last iteration per entity, merges all `business/**` trees
- Runs static check (Gate 1) + full integration check (Gate 2) on merged artifact set
- Usage: `python check_final_zip.py --zip <full_zip> --intake <phase_assessment.json>`
- Options: `--output <path>`, `--no-static`, `--no-integration`
- Output written to `<zip_stem>_check.json` by default

---

## 2026-03-18 (session 8 — factory mode, ZIP fixes, boilerplate lazy-load, tooling)

### fix: --clean / --fullclean flags for run_integration_and_feature_build.sh
- `--clean`: removes only the final `_full_` ZIP so auto-resume re-runs from last completed feature
- `--fullclean`: removes all ZIPs for this startup (phase1, feature, full); run dirs untouched

### fix: LATEST_RUN_DIR unbound variable on first entity build
- Initialized `LATEST_ZIP` and `LATEST_RUN_DIR` to empty string at top of script
- Was latent bug exposed by `--fullclean` wiping all ZIPs before entity loop

### fix: ZIP selection bugs in run_integration_and_feature_build.sh
- Phase 1 fallback glob scoped to `${INTAKE_STEM}` (was global wildcard — could grab wrong project)
- Integration fix pass ZIP fallback scoped to run dir prefix (was global `fo_harness_runs/*`)

### fix: stripe/mailerlite/auth0 libs — no startup crash on missing keys (teebu-saas-platform)
- All three libs now load silently in DISABLED mode when keys are absent
- `RuntimeError` raised only when an API method is actually called
- Prevents uvicorn crash on deploy for apps that don't use those integrations

### feat: entity/feature completion banners in pipeline output
- Clear `════` separator printed after each entity and feature build completes
- Prevents harness init output of next build running directly into prior build's summary

---

## 2026-03-18 (session 8 — factory mode, daily rollup, reddit post, various tooling)

### feat: --mode factory for run_integration_and_feature_build.sh

New build mode for high-volume AFH catalog builds (60 products).

**Changes:**
- `run_integration_and_feature_build.sh`: `--mode factory|quality` flag (default: quality).
  Factory mode: caps MAX_ITER at 10, MAX_FIX_PASSES at 1, passes `--factory-mode` to all harness calls.
- `fo_test_harness.py`: `--factory-mode` flag.
  - Gate 3 (AI Consistency): SKIPPED entirely
  - Gate 4 (Quality Gate): passes unless DEPLOYABILITY=FAIL (ignores Completeness/Code Quality LOW/FAIL)
  - Logged in harness init output as "Factory mode: ON"

**Rationale:** AFH catalog builds are small, simple, self-contained SaaS tools. Gate 3 burns ~$0.10/iter
on cross-file consistency checks that rarely catch real issues in isolated single-feature builds.
Gate 4 can accept incomplete completeness and imperfect code quality as long as the app deploys.

### feat: daily cost rollup + GitHub Actions automation

- `daily_cost_rollup.py`: reads all AI cost CSVs, groups by date, outputs ai_costs_daily.csv
- `.github/workflows/daily_rollup.yml`: runs at 6am EST daily, commits ai_costs_daily.csv + harness_summary

### feat: weekly Reddit post automation

- `post_to_reddit.py`: parses latest harness_summary, posts to r/microsaas via PRAW
- `.github/workflows/weekly_reddit_post.yml`: runs every Monday at 6am EST

### feat: summarize_harness_runs.py — product grouping

- Groups feature runs under parent products (PRODUCT_PREFIXES mapping)
- Skips fake test entries (SKIP_STARTUPS)
- Shows "Feat" column with distinct feature count per product

### feat: phase_planner.py — ZIP guard

- Skips re-run if a completed final ZIP already exists for the startup
- Prevents wasting $0.03 on re-decomposing already-built products

### feat: check_block_b.py — lightweight Block B quality checker

- 15 deterministic signals across 6 passes, no AI, exit codes 0/1/2/3
- PASS>=80, WARN 60-79, FAIL<60

### fix: postintakeassist — block_a/block_b key normalization

- Adds `block_a_final`/`block_b_final` aliases when only `block_a`/`block_b` present
- NOT wired into build pipeline (Block A schema incompatible with intake pass_1..pass_6 format)

---

## 2026-03-17 (session 7 — AI decomposer + mini specs for Phase 1)

### feat: AI-powered entity decomposer replaces keyword-based phase planner

**Problem:** Phase 1 monolithic builds failed to converge (35+ iterations) because the full intake
contained Phase 2 references (intelligence features, external integrations). Claude would build
entities for features not yet in scope → QA flagged → oscillation.

**Solution:** Three-part pipeline:
1. **AI Decomposer** (`phase_planner.py:decompose_intake()`) — ChatGPT (gpt-4o) reads full intake
   and produces structured mini specs: one per domain entity with exact fields, CRUD ops, file
   contracts, dependencies, and forbidden expansions. Every entity must cite intake evidence.
2. **Deterministic Validator** (`phase_planner.py:validate_mini_specs()`) — enforces harness rules
   on AI output: underscore filenames, .jsx not .tsx, strip external IDs, remove standard fields
   (id/created_at/updated_at/owner_id), underscore CRUD URLs.
3. **Entity-by-entity building** (`run_integration_and_feature_build.sh`) — each entity built as
   a separate harness run, chained via `--prior-run`. Independent entities (no FK deps) in Wave 1,
   dependents in Wave 2+. Mirrors the existing feature loop structure.

**Mini spec injection:** `fo_test_harness.py:PromptTemplates.build_prompt()` detects `_mini_spec`
key in intake_data and injects structured entity definition (fields, CRUD, deps, allowed files,
forbidden expansions) into the dynamic section of the build prompt.

**Phase 1 intake stripping:** `build_phase1_intake()` aggressively strips HLD, engineering questions,
QA docs, and task lists of Phase 2 references using `PHASE2_STRIP_KEYWORDS` (~60 keywords).

**Fallback:** If OpenAI key unavailable or decomposer fails, falls back to monolithic Phase 1 build.

Files: `phase_planner.py`, `fo_test_harness.py`, `run_integration_and_feature_build.sh`

---

## 2026-03-17 (session 7 — consistency type alignment false positives)

### fix: SQLAlchemy↔Pydantic type mappings added to consistency DO NOT FLAG

**Root cause:** Consistency AI flagged correct type alignments as FIELD_MISMATCH:
- `Column(String, nullable=True)` ↔ `Optional[str] = None` flagged as "phantom field"
- `Column(JSON)` ↔ `Optional[Dict[str, Any]]` flagged as "potential validation failure"
- `Column(String(50), default="basic")` ↔ `Optional[str] = "basic"` flagged as "default conflict"
These are all correct SQLAlchemy↔Pydantic mappings. The false positives caused 2 consecutive
surgical failures → escalation to SYSTEMIC → wide 25-file context patch → collateral damage.

**Fix:** Added comprehensive type alignment table to `build_ai_consistency.md` DO NOT FLAG section:
- All standard Column types mapped to their correct Pydantic equivalents
- Explicitly: nullable=True ↔ Optional, default=X ↔ = X or = None
- Infrastructure fields (status/created_at/updated_at) — never flag
- Derived/computed fields in service responses (e.g. `is_published`) — valid transformations

Files: `directives/prompts/build_ai_consistency.md`

---

## 2026-03-17 (session 7 — consistency fix joint file targeting)

### fix: consistency fixes now target ALL files in the <-> relationship simultaneously

**Root cause:** `_parse_consistency_report()` sets `issue['file']` to only the first file from
`Files: A <-> B`. The defect_target_files builder at the fix iteration only reads `d.get('file')`
— so only one side of a FIELD_MISMATCH gets patched. The other side stays wrong → next consistency
run fires the same issue in reverse → oscillates for all 4 cap iterations before falling to QA.

**Fix:** Added Fix 3 in the defect_target_files building block:
- For `defect_source == 'consistency'`, parse all files from `d.get('files', '')` via `<->` split
- Add any `business/` prefixed files not already in `defect_target_files`
- Both the service AND the model (or whichever two files are involved) get passed to Claude
- Claude sees current content of both files and fixes field names on both sides in one pass

**Expected impact:** FIELD_MISMATCH between model and service resolves in 1 consistency iteration
instead of oscillating for 4 before falling to QA.

Files: `fo_test_harness.py`

---

## 2026-03-17 (session 7 — status column harness filter)

### fix: status/created_at/updated_at column defects now filtered at harness level

**Root cause:** QA absolute rule prohibiting status column flagging is non-binding — QA ignored it
at iterations 10 and 15, generating SCOPE-BOUNDARY defects targeting status columns in models,
services (dict keys), and Alembic migrations.

**Fix:** Added Check 1d to `_filter_hallucinated_defects()`. Patterns cover all citation forms:
- ORM column assignment: `status = Column(...)`
- Dict key / Alembic positional: `"status": ...`, `sa.Column('status', ...)`
- Attribute access in service/route: `update.status`, `.created_at`

If ALL backtick evidence snippets match any infrastructure pattern → defect removed.
If all defects removed → verdict flips to ACCEPTED.

**Iteration 15 caught:** DEFECT-1 evidence `"status": update.status,` (dict key → pattern 2),
DEFECT-2 evidence `sa.Column('status', sa.String(50), default='active'),` (Alembic → pattern 2).

Files: `fo_test_harness.py`

---

## 2026-03-17 (session 7 — hyphen filename normalization)

### fix: hyphenated route filenames caused permanent INT-ROUTE false positives

**Root cause:** `HorseDetailsPage.jsx` called `fetch('/api/stable-updates')`. Claude generated
`business/backend/routes/stable-updates.py` (with hyphen). Two bugs in `integration_check.py`:
1. Route file regex `\w+\.py$` excludes hyphens — file was never loaded into `route_stems`
2. Cross-check compared raw URL stem `stable-updates` against normalized route stems — would
   never match even if the file was loaded

**Fixes:**
- `integration_check.py` line 196: regex changed to `[\w-]+\.py$` (allows hyphens in filenames)
- `integration_check.py` stem extraction: `Path(path).stem.replace('-', '_')` — normalize to underscore
- `integration_check.py` cross-check: `stem.replace('-', '_')` before lookup; report uses normalized stem
- `FROZEN_ARCHITECTURAL_DECISIONS` in `fo_test_harness.py`: added "Route and file naming — CRITICAL" section
  locking route filenames to underscores and requiring fetch URLs to match

Files: `integration_check.py`, `fo_test_harness.py`

---

## 2026-03-17 (session 7 — schema naming + pyc filter)

### fix: schema naming convention locked + __pycache__/.pyc filter added

**Schema naming oscillation:** Routes importing `ContentCreateRequest`, `HorseCreateRequest`,
`MemberCreateRequest` (with `Request` suffix) while schemas defined `ContentCreate`, `HorseCreate`
etc. (no suffix). Static check fired the same 6 defects every iteration — Claude fixed routes but
not schemas or vice versa, causing permanent oscillation.
Fix: added schema naming convention to `FROZEN_ARCHITECTURAL_DECISIONS`:
- Request schema: `XCreate` — NEVER `XCreateRequest`
- Response schema: `XResponse` — NEVER `XResponseModel`
- Update schema: `XUpdate` — NEVER `XUpdateRequest`

**__pycache__/.pyc filter:** QA flagged `business/backend/routes/__pycache__/content.cpython-39.pyc`
and `horses.cpython-39.pyc` as SYSTEMIC defects. These inflated defect count and triggered a wider
fix scope than needed. Added Check 1c to `_filter_hallucinated_defects()` — any location containing
`__pycache__` or ending in `.pyc` is removed immediately before triage.

Files: `fo_test_harness.py`

---

## 2026-03-17 (session 7 — status column false positive fix)

### fix: status/created_at/updated_at columns must never be flagged as scope creep

**Root cause:** QA flagged `status = Column(String(50), default="active")` as SCOPE-BOUNDARY on
Member, Horse, Update, and BreedingData models in wynwood run. The existing DO NOT FLAG rule was
ignored. Claude removed the columns → services still referenced them → INTEGRATION_FAST fired on
every subsequent iteration → 6-iteration cascade from a single false positive.

**Fix 1 — qa_prompt.md:** Moved `status`/`processing_status`/`created_at`/`updated_at` ban into
ABSOLUTE RULES (top of section, not buried in DO NOT FLAG). Extended to cover `created_at` and
`updated_at`. Removed the now-duplicate weaker DO NOT FLAG entry (replaced with a pointer).

**Fix 2 — fo_test_harness.py FROZEN_ARCHITECTURAL_DECISIONS:** Added "Standard model fields"
section — every model MUST include status/created_at/updated_at with exact Column definitions.
Claude must not remove them even if QA flags them. This prevents the fix-removes-column→service-
breaks cascade at generation time, not just at QA time.

Files: `directives/prompts/qa_prompt.md`, `fo_test_harness.py`

---

## 2026-03-17 (session 7 — QA cross-file contract verification)

### feat: qa_prompt.md STEP 1.5 — systematic cross-file contract verification

Added 6 explicit contracts QA must verify on every build before per-file evaluation:
1. Route `response_model=XResponse` → schema defines `class XResponse(BaseModel)`
2. Route `XService.method(...)` call → service defines `def method(...)`
3. Service `model.field` access → model defines `field = Column(...)`
4. Service/route `from business.X import Y` → file exists in artifact inventory
5. Frontend `fetch("/api/X")` → backend `@router.get/post("/X")` exists
6. Frontend `Authorization: Bearer` fetch → route has `Depends(get_current_user)`

Rules: must quote conflicting lines from BOTH files; skip if callee file absent (caught by Contract 4/STEP 1);
no inference from function names alone.

Also fixed DO NOT FLAG package list — removed `python-jose`, `passlib`, `celery`, `redis`, `boto3`,
`aiohttp` (not in actual boilerplate); added actual packages: `PyJWT`, `cryptography`, `meilisearch`,
`praw`, `tweepy`, `linkedin-api`, `facebook-sdk`, `ratelimit`, `email-validator`.

Files: `directives/prompts/qa_prompt.md`

---

## 2026-03-17 (session 7 — build prompt quality improvements)

### feat: FROZEN_ARCHITECTURAL_DECISIONS + GOLDEN_EXAMPLES + PRE_OUTPUT_CHECKLIST injected into every build

**Problem:** Claude has too much decision surface at build time — sync/async choice, error shape,
auth pattern, file structure, dependency selection all vary between builds. Small divergences from
boilerplate create integration failures → QA failures → extra iterations → cost.

**Changes (all in `fo_test_harness.py`):**

**A+E — FROZEN_ARCHITECTURAL_DECISIONS (module-level constant, injected into `governance_section`):**
- Locks: sync-by-default service methods, JSONResponse error shape, `current_user["sub"]` auth,
  UUID string IDs, function-based routes, `router` naming, .jsx-only frontend, pages/ router only
- Adds cross-file contract rules: route schema ↔ service return type ↔ frontend fetch payload
- Adds file count constraints: max 1 route/service/model/schema/page per feature — no helper files
- Adds seeded dependency baseline: Python stdlib list (never add to requirements.txt),
  boilerplate packages already installed (fastapi, sqlalchemy, auth0, etc.)
- Injected into `governance_section` (cacheable) — paid once per run, not per iteration

**C — GOLDEN_EXAMPLES (module-level constant, injected into `governance_section`):**
- 5 reference files: model, schema (Pydantic — was missing from original doc), service, route, JSX page
- Exact patterns: `from core.database import Base`, UUID primary key, `from_attributes = True`,
  `get_current_user["sub"]`, `getAccessTokenSilently()` destructured from useAuth0
- Injected into `governance_section` (cacheable) — paid once per run

**B — PRE_OUTPUT_CHECKLIST (module-level constant, injected at end of `dynamic_section`):**
- 5 check categories: structure, scope, dependencies, frontend, output format
- Failure is explicitly blocking — "fix your plan before outputting"
- Injected as last instruction before "BEGIN BUILD EXECUTION NOW" — stays per-iteration

**Injection point:** `PromptTemplates.build_prompt()` ~line 1973–1995

**Expected outcome:** First-pass build quality improves. Iteration count on simple builds drops
from ~15–20 to ~8–12. Convergence failures from sync/async, wrong path, wrong imports reduced.

Files: `fo_test_harness.py`

---

## 2026-03-16 (session 6 — CONSISTENCY full-build escalation removed)

### fix: CONSISTENCY hard cap no longer escalates to full-build; added no-file filter

**Bug: full-build escalation for 1 HIGH CONSISTENCY issue**
When `_consistency_consecutive_iters >= MAX_CONSISTENCY_CONSECUTIVE (4)` with any HIGH issue,
the harness set `defect_source='qa'` and issued a full 16384-token build prompt.
Claude regenerated all files from scratch → invented wrong-path architectures (`app/`, `backend/`,
`frontend/`) → PATCH_SET_COMPLETE fired → collateral wrong-path files extracted → prior surgical
fixes destroyed. Triggered by a single GPT-4o hallucinated HIGH issue at iter 4 → exploded to 30.

**Fix 1: Remove full-build escalation — always fall through to QA at hard cap**
QA is the authoritative validator. If a CONSISTENCY issue is a real AttributeError it will
appear as a QA defect with concrete evidence. A full build for 1 stubborn issue is never correct.

**Fix 2: Drop issues with no files named (N/A <-> N/A)**
ISSUE-5 in iter 4 had `files = "N/A <-> N/A"` — consistency cannot identify a cross-file
mismatch without naming both files. These are always fabrications. Added pre-filter check:
if `files` is empty / `N/A` / `N/A <-> N/A` → filtered immediately.

Files: `fo_test_harness.py` — `_run_ai_consistency_check()`, `execute_build_qa_loop()`

---

## 2026-03-16 (session 6 — CONSISTENCY filter bug 2)

### fix: CONSISTENCY filter — DUPLICATE_SUBSYSTEM not caught + BROKEN_IMPORT incorrectly removed

**Bug 1 — DUPLICATE_SUBSYSTEM not caught:**
`_UNVERIFIABLE_ISSUE_TYPES` check scanned `issue['issue']` (Problem text) + evidence.
The type string `DUPLICATE_SUBSYSTEM` only appears in the block header `[DUPLICATE_SUBSYSTEM]`,
never in the Problem or Evidence fields → set membership check always missed it.
Fix: `_parse_consistency_report` now captures the `[TYPE]` from the header into `issue['type']`.
The unverifiable check tests `issue_type in _UNVERIFIABLE_ISSUE_TYPES` first.

**Bug 2 — BROKEN_IMPORT incorrectly filtered:**
The "token found in file → hallucination" logic was applied to ALL issue types.
For FIELD_MISMATCH, finding the field name in the file proves the "missing" claim is false.
For BROKEN_IMPORT, finding the wrong import string in the file confirms the defect is real.
Applying FIELD_MISMATCH logic to BROKEN_IMPORT caused real import bugs to be filtered out.
Fix: `_FIELD_MISMATCH_TYPES` set — token-in-file filter only applied for FIELD_MISMATCH/
SCHEMA_FIELD_MISMATCH/MODEL_FIELD_MISMATCH. All other types pass through to verified unchanged.

**Result:** iter 30 (3 issues: 2 FIELD_MISMATCH, 1 DUPLICATE_SUBSYSTEM) → 0 surviving.
iter 29 (4 issues: 2 FIELD_MISMATCH, 2 BROKEN_IMPORT) → 2 surviving (real BROKEN_IMPORTs).

Files: `fo_test_harness.py` — `_parse_consistency_report()`, `_run_ai_consistency_check()`

---

## 2026-03-16 (session 6 — PDR060 intake check)

### feat: postintakeassist PDR060 — UI deliverable missing data specification

New intake-level rule that catches the "page with nothing behind it" problem (AWI pattern)
**before** the build starts, not just after.

**Rule:** `PDR060_ui_deliverable_missing_data_spec` (severity: HIGH, mode: `ui_feature_missing_data_spec`)

**Logic:** For each deliverable whose name contains UI keywords (dashboard, management, tracker,
portal, list, hub, panel, board, console, monitor, browser, manager, viewer, explorer):
1. Look at all tasks mapped to the same feature IDs
2. If no task title contains a data operation keyword (create, add, form, input, enter, edit,
   update, delete, save, store, upload, import, export, field, record, log, submit, crud, model,
   schema, database, persist, table, entry) → flag HIGH
3. Skip static/auth pages (login, home page, about, sidebar, etc.)

**Fallback:** If feature_id mapping is absent, checks ALL task titles as context.

**Revision template:** `PRT008_add_data_spec` — AI asks for entity name, fields, and CRUD operations
for each flagged deliverable.

**Tested:** 5 unit cases — AWI hollow dashboard+tracker flagged; backed management dashboard cleared;
home page skipped; "Assessment Management" with UI-only task flagged; "Report List" with export task cleared.

Files: `postintakeassist/post_intake_detection_rules.v2.1.json`,
`postintakeassist/post_intake_revision_templates.v2.1.json`,
`postintakeassist/post_intake_assist.py`

---

## 2026-03-16 (session 6 — checks 16 & 17)

### feat: integration_check.py Check 16 (hollow services) + Check 17 (orphaned pages)

**Check 16 — Hollow service detection (HIGH)**
Scans every `business/services/*.py` public method that accepts a `db` parameter.
If the method body has no `db.query/add/execute/commit` call AND returns a literal
`[]`, `{}`, `None`, `""`, or is `pass`/`# TODO` — flags HIGH HOLLOW_SERVICE.
Root cause of AWI pattern: Claude generates a page + route + service but the service
method just returns `[]` with no DB query. Page renders, API responds, but data is
always empty. Silent at runtime, invisible to all other checks.

**Check 17 — Orphaned page detection (HIGH)**
For every `business/frontend/pages/*.jsx` that makes an API call (`api.get/post/...`
or `fetch(...)`), derives the domain entity name from the filename and checks for
any corresponding model/route/service file. If none found → flags HIGH ORPHANED_PAGE.
Skips generic pages (dashboard, home, login, settings, etc.).
Root cause of AWI assessments pattern: Assessments.jsx existed and called `/api/assessments`
but there was no Assessment model, no assessments route, no AssessmentService.
All API calls 404'd silently.

Files: `integration_check.py`

---

## 2026-03-16 (session 6 — hotfix 2)

### fix: CONSISTENCY gate false-positive FIELD_MISMATCH deadlock

**Root cause:** Claude Sonnet (CONSISTENCY gate) repeatedly flagged fields as missing from
`_to_dict` service methods (e.g. `status`, `membership_start`, `publish_date`) even when
those fields were present in the actual artifact. AI hallucinated the defect every
iteration — CONSISTENCY never passed, QA never ran, all 20 iterations consumed.

**Evidence:** `HorseService._to_dict` contained `"status": horse.status` verbatim.
Consistency output still reported `Evidence: "status"` as a missing field. Pure hallucination.

**Fix:** Post-parse verification filter in `_run_ai_consistency_check()`.
For each parsed issue with a non-empty Evidence token:
1. Extract involved `.py` file paths from the `Files:` field
2. Check if the evidence token appears in those files' actual content (`file_contents` dict, in scope)
3. If found → log "Filtered false positive" + remove
4. If not found → real defect, keep

Files: `fo_test_harness.py` — `_run_ai_consistency_check()`

---

## 2026-03-16 (session 6)

### feat: canonical code skeletons directive + Flask Blueprint static fix

**New file: `directives/prompts/build_code_skeletons.md`**
- Four canonical skeletons (route, model, service, JSX page) extracted from real production builds
- Injected into ALL build prompts (not just lowcode) via `{{code_skeletons_instruction}}` slot in `build_dynamic_base.md`
- Hard prohibition table at top: NEVER Flask/Blueprint, NEVER .tsx, NEVER app/ router, NEVER raw SQL, NEVER wrong import paths
- Substitution guide: exact naming conventions for route/model/service/page files
- Goal: eliminate all architectural decisions from Claude's scope; implementation only

**`fo_test_harness.py` — Flask Blueprint static check upgrade (CHECK 7 area)**
- Added explicit Flask detection before the generic "no @router endpoints" defect
- Regex: `from flask import|Blueprint\(|@router\.route\(`
- Severity upgraded from MEDIUM → HIGH on Flask detection
- Fix field now contains exact FastAPI conversion (APIRouter import, router = APIRouter(), @router.get pattern)
- Previous MEDIUM defect was too vague — Claude kept generating Flask despite repeated flag

**`fo_test_harness.py` — both `build_iteration_prompt()` functions updated**
- `code_skeletons_instruction` variable added; loads `build_code_skeletons.md` unconditionally
- Template variable `{{code_skeletons_instruction}}` added to `build_dynamic_base.md`
- Second (inline) prompt function also injects `code_skeletons_instruction` before `BEGIN BUILD EXECUTION NOW.`

Files: `fo_test_harness.py`, `directives/prompts/build_code_skeletons.md`, `directives/prompts/build_dynamic_base.md`

---

## 2026-03-16 (session 5 — hotfix)

### fix: static CHECK 8 deadlock on boilerplate-owned frontend configs

**Root cause:** CHECK 8 in `_run_static_check()` flagged `business/frontend/tailwind.config.ts`
for missing `content:` paths. The file reached the static checker in iteration 1 via wrong-path
remap (survived pruner). Iterations 2+ sent surgical fix for that file, Claude output it, pruner
immediately deleted it (boilerplate-owned), only 2 files survived — BUILD VALIDATION FAILED.
Loop repeated until max iterations.

**Fix:** All three config checks in CHECK 8 now skip if `cfg.name` is in
`BOILERPLATE_OWNED_FRONTEND_CONFIGS`. Boilerplate owns `tailwind.config.js/ts`,
`next.config.js/ts`, and `postcss.config.js/ts` — pruner always deletes them; no point
flagging their content.

Files: `fo_test_harness.py` — CHECK 8 (`_run_static_check`)

---

## 2026-03-16 (session 5)

### perf: qa_prompt.md restructure for prefix caching + QA inventory step

**`directives/prompts/qa_prompt.md` — restructured for OpenAI prefix caching**
- Moved all 170 lines of static rules to the TOP of the prompt (before any dynamic blocks)
- Dynamic content (`{{tech_stack_context}}`, `{{prohibitions_block}}`, `{{defect_history_block}}`, `{{resolved_defects_block}}`, `{{block_data_json}}`, `{{build_output}}`) moved to BOTTOM
- Static prefix now ~150+ lines before any dynamic content — well above 1024-token caching threshold
- All existing rules preserved word-for-word; order only

**New: STEP -1 — BUILD ARTIFACT INVENTORY**
- First thing QA does: scan build output for all `**FILE: path/to/file**` headers, output a FILE INVENTORY table with artifact types (FRONTEND_PAGE, BACKEND_ROUTE, BACKEND_MODEL, BACKEND_SERVICE, CONFIG, DOCUMENTATION)
- Hard rule: files not in the inventory MUST NOT be referenced in any defect
- Targets root cause of hallucinated defects — model re-scans full prompt repeatedly; inventory creates stable working set

**New: STEP 1 — REQUIRED STRUCTURE CHECK (reframed from inline section)**
- Existing required-structure rules promoted to an explicit numbered step after inventory

**New: STEP 2 — EVALUATE ARTIFACTS IN FIXED ORDER**
- Deterministic traversal: BACKEND_ROUTEs → BACKEND_MODELs → BACKEND_SERVICEs → FRONTEND_PAGEs → CONFIG → DOCUMENTATION
- Reduces non-determinism in defect ordering across iterations

**`fo_test_harness.py` — CACHE CHECK logging for all three AI gates**
- Added `CACHE CHECK [CONSISTENCY]` log line after every CONSISTENCY ChatGPT call
- Added `CACHE CHECK [QUALITY]` log line after every QUALITY ChatGPT call
- Added `CACHE CHECK [FEATURE_QA]` log line inside `_log_chatgpt_usage()` (covers all FEATURE_QA calls)
- Format: `CACHE CHECK [GATE] iteration N: cached=X / total_prompt=Y (Z% cached)`
- Correct dict-based access: `usage.get('prompt_tokens_details', {}).get('cached_tokens', 0)` — not SDK object access

---

## 2026-03-15 (session 4)

### perf: fo_harness_improvements_v2.md — 4 of 5 improvements implemented

**Improvement 1 (Prompt Caching) — SKIPPED.** All three AI gates (CONSISTENCY, QUALITY, FEATURE_QA) now go to ChatGPT. OpenAI's caching is automatic — no `cache_control` required.

**Improvement 2 — Gate Locking (`fo_test_harness.py`)**
- `gate_locks` dict initialized once before the loop; persists across iterations
- `_files_changed_in_last_fix()` and `_load_iteration_manifest()` helpers added as closure functions
- CONSISTENCY gate: locks after PASS; unlocks only if `models/`, `services/`, `routes/`, or `schemas/` files changed
- QUALITY gate: locks after PASS; unlocks only if any `business/` file changed; cost counters skip when locked
- FEATURE_QA gate: locks after PASS; unlocks only if any `business/` file changed; when locked sets `qa_report` to ACCEPTED and skips ChatGPT call entirely
- Each gate logs `[GATE] LOCKED — skipped` or `[GATE] UNLOCKED — relevant files changed`

**Improvement 3 — Repair vs Acceptance Mode Split (`fo_test_harness.py`, `ChatGPTClient`)**
- `acceptance_threshold = max_iterations - 2` set before loop; `_quality_ran_in_acceptance_mode` tracker added
- `REPAIR_MODE_RULES` constant added (system message text for focused QA)
- `build_mode` (`'repair'` or `'acceptance'`) determined each iteration; early acceptance triggers when CONSISTENCY + FEATURE_QA both locked
- QUALITY gate: skipped entirely in repair mode — logs `QUALITY GATE SKIPPED — repair mode, iteration N of M`
- FEATURE_QA: passes `REPAIR_MODE_RULES` as ChatGPT system message in repair mode (not inline prepend); acceptance mode uses no system override
- `ChatGPTClient.call()` gained optional `system_message` param; builds messages list with system role when provided
- Acceptance check: if QUALITY never ran in acceptance mode, forces one final acceptance-mode run before accepting build; if that run fails, continues fix loop

**Improvement 4 — Artifact Filtering Per Gate (`fo_test_harness.py`)**
- `GATE_FILE_FILTERS` and `GATE_FILE_EXCLUDES` class-level constants on `FOHarness`
- `filter_artifacts_for_gate()` static method — falls back to full artifact set if filter yields empty result
- CONSISTENCY: receives only `models/`, `services/`, `routes/`, `schemas/` files — logs `sending N files (filtered from M total)`
- QUALITY: receives all `business/` files minus `README-INTEGRATION.md`, `.env.example`, `.gitignore`

**Improvement 5 — Integration Checks Before AI Gates (`integration_check.py`, `fo_test_harness.py`)**
- `integration_check.py`: added `run_fast_checks()` function (checks 1, 2, 4, 6, 7 only — existing check functions called as-is, no logic modified); added `--fast` CLI flag to `main()`
- `fo_test_harness.py`: added `_run_integration_fast_gate()` method (calls `integration_check.py --fast` via subprocess, parses output JSON, returns issues list)
- New GATE 1.5 `INTEGRATION_FAST` inserted between STATIC and CONSISTENCY in main loop
- Failure path: issues converted to harness defect format, routed to `defect_source='integration'` structural fix, AI gates skipped for that iteration
- Post-build full 15-check integration run unchanged

**Gate sequence is now:** COMPILE → STATIC → INTEGRATION_FAST → CONSISTENCY → QUALITY → FEATURE_QA (loop) + INTEGRATION full (post-build)

| # | Status | What was done |
|---|--------|---------------|
| 1 | SKIPPED | All AI gates are ChatGPT — OpenAI caching is automatic, no `cache_control` needed |
| 2 | ✅ | Gate locking — CONSISTENCY/QUALITY/FEATURE_QA lock after PASS, unlock only when relevant files change |
| 3 | ✅ | Repair/acceptance mode split — QUALITY skipped in repair mode; FEATURE_QA gets system-message repair rules; forced acceptance-mode QUALITY run required before final accept |
| 4 | ✅ | Artifact filtering — CONSISTENCY gets models/services/routes/schemas only; QUALITY gets business/ minus doc files |
| 5 | ✅ | INTEGRATION_FAST gate (checks 1,2,4,6,7) inserted before CONSISTENCY; failure skips AI gates, routes to structural fix |

Source doc: `fo_harness_improvements_v2.md` (copied into repo)

**Also (earlier this session):**
- Gate 3 CONSISTENCY moved from Claude Sonnet to ChatGPT/GPT-4o
- README gate table updated: added Directive column, corrected to 6 gates, correct model assignments

---

## 2026-03-15 (session 3)

### feat: generate_feature_spec.py — feature spec before build

Closes the gap where `add_feature.sh --feature "Name"` gave Claude only a feature name, causing it to invent the feature rather than build what was intended.

**Two modes:**

`--questions-only` — prints an 8-question template to stdout and saves it to `feature_specs/<slug>_questions.txt`. No API call. Questions cover: what it does, who uses it, data requirements, UI/UX, user actions, integrations with existing features, explicit scope exclusions, and acceptance criteria.

`--answers-file <path>` — reads your filled-in answers (or AI-assisted answers), optionally loads the original intake for product context, calls Claude Sonnet to structure them into a precise feature spec (`feature_specs/<slug>_spec.txt`). Claude fills obvious gaps from context but does not invent functionality not mentioned.

**Downstream wiring:**

`feature_adder.py` — new `--spec-file` flag + `apply_spec_file()` function. Embeds spec text into `_phase_context.note` so the build prompt receives the full spec alongside the do-not-regenerate file list.

`add_feature.sh` — new `--spec-file` passthrough to `feature_adder.py`.

Files: `generate_feature_spec.py` (new), `feature_adder.py`, `add_feature.sh`

### feat: add_feature.sh + feature_adder.py — --existing-repo support

`add_feature.sh` accepts `--existing-repo` (local path or GitHub URL) as alternative to `--existing-zip`. GitHub URLs are cloned with `--depth=1` and cleaned up on exit.

`feature_adder.py` gains `--repo` flag that walks the repo's `business/` directory to build the do-not-regenerate list instead of reading a ZIP manifest. Handles repos where `business/` is a subdirectory or the root.

Files: `add_feature.sh`, `feature_adder.py`

### feat: add_feature.sh — post-deploy single-feature pipeline (initial)

New script for adding features to an already-built, already-deployed codebase. Distinct from `run_integration_and_feature_build.sh` (greenfield). Flow: `feature_adder.py` → `fo_test_harness.py` → `integration_check.py` → merge → new final ZIP. Auto-resume at each stage.

Files: `add_feature.sh` (new)

### feat: integration_check.py — Checks 13-15 (frontend structural bugs)

Root cause: all prior checks were backend-only. Three AWI bugs survived all 5 QA gates because no check cross-referenced JSX against the config JSON.

- **Check 13 CONFIG_OBJECT_AS_TEXT (HIGH):** Flattens `business_config.json`, finds dict/list-valued paths, flags JSX `{expr.path}` expressions that render them without a scalar suffix → `[object Object]`.
- **Check 14 DEAD_BUTTON (HIGH/MEDIUM):** `<button>` with no `onClick` (skips submit/disabled/`.map()`). Also flags `<a href="#">` placeholders.
- **Check 15 FORM_STATE_CONFIG_MISMATCH (MEDIUM):** `useState` field keys not in `business_config.json` form field lists → silent data loss on submit.

Files: `integration_check.py`

### docs: README rewrites (root, deploy/, intake/)

Root `README.md` fully rewritten — correct CLI, all scripts, 15-check integration table, three QA gates, all resume modes, deploy prerequisites.
`deploy/README.md` — new file covering full deploy sequence and all 10 deploy scripts.
`intake/README.md` — updated for current pipeline: generate_intake.sh wrapper, phase planner outputs, add_feature.sh cross-reference, post_intake_fix_batch.py.

---

## 2026-03-15 (session 2)

### feat: integration_check.py — Checks 13-15 (frontend structural bugs)

Root cause: all prior checks were backend-only. Three AWI bugs survived all 5 QA gates because no check cross-referenced JSX against the config JSON.

**Check 13 — CONFIG_OBJECT_AS_TEXT (HIGH)**
Flattens `business_config.json`, finds all dict/list-valued paths, then scans JSX pages for `{expr.dotted.path}` expressions that access one of those object-valued paths without a scalar suffix (`.label`, `.text`, etc.). Catches `{home.hero.cta_primary}` → `[object Object]`.

**Check 14 — DEAD_BUTTON (HIGH/MEDIUM)**
Scans JSX for `<button>` / `<Button>` tags with no `onClick` (skips `type="submit"` inside `<form>`, disabled, and `.map()` list items). Also flags `<a href="#">` placeholder anchors (MEDIUM).

**Check 15 — FORM_STATE_CONFIG_MISMATCH (MEDIUM)**
Finds `useState({field: '',...})` initializers in JSX files that contain a form. Cross-references state keys against all `name`-keyed field lists in `business_config.json`. Orphan state fields → silent data loss on submit.

Files: `integration_check.py`

---

## 2026-03-15

### feat: add_feature.sh — post-deploy feature addition pipeline

New script for adding features to an already-built, already-deployed codebase.
Distinct from `run_integration_and_feature_build.sh` which is for greenfield builds.

Flow:
1. `feature_adder.py` generates scoped feature intake from `--existing-zip` as the manifest
2. `fo_test_harness.py` builds the feature (with `--prior-run` if run dir exists)
3. `integration_check.py` validates; fix loop (up to 2 passes) for HIGH issues only
4. Merges existing ZIP + feature ZIP → new final ZIP (later ZIP wins on conflict)

Auto-resume at each stage: if feature intake / feature ZIP / final ZIP already exist, skips that step.

Files: `add_feature.sh` (new), `feature_adder.py` (--repo flag added)

Usage:
```bash
./add_feature.sh \
  --intake intake/intake_runs/awi/awi.5.json \
  --feature "Competitor benchmarking dashboard" \
  --existing-zip fo_harness_runs/awi_downloadable_exec_report_FINAL_20260309.zip
```

---

## 2026-03-14 (session 2)

### fix: integration fix pass — 4 bugs fixed, adversarial_ai completes end-to-end

**Bug 1 — NEW FILE skipped in surgical patch**
`_read_target_file_contents` silently dropped target files that didn't exist yet (e.g. MISSING_ROUTE `analysis.py`). Claude saw the file in TARGET FILES but got no entry in CURRENT FILE CONTENTS → skipped creating it. QA accepted anyway → same MISSING_ROUTE recurred every fix pass.
Fix: insert `# NEW FILE — does not exist yet` placeholder for missing targets; updated `build_integration_fix.md` directive to say "if NEW FILE → create from scratch, do NOT skip".

**Bug 2 — iter 21 > max 20 → instant fail**
Integration fix pass resumed at `LATEST_ITER + 1`. When run dir was already at iteration 20 (max), harness started loop at 21 > 20 → "Should not reach here" before doing any work.
Fix: `INT_MAX_ITER = max(LATEST_ITER + 5, MAX_ITER)` in fix pass call.

**Bug 3 — octal arithmetic crash on iter 08/09**
`$(( LATEST_ITER + 5 ))` with `LATEST_ITER=08` → bash octal error ("08 invalid in base 8").
Fix: `$(( 10#${LATEST_ITER} + 5 ))` and `$((10#${LATEST_ITER}))` for `--resume-iteration`.

**Bug 4 — MEDIUM-only integration issues triggered fix pass**
KPI string mentions ("SDK", "MVP" not in code) are MEDIUM, not actionable. Fix pass wasted iterations on them.
Fix: count HIGH issues from `integration_issues.json`; skip fix pass entirely if HIGH count = 0.

**Bug 5 — bash 3.2 negative array index**
`ALL_ZIPS[-1]` unsupported on macOS bash 3.2.
Fix: `ALL_ZIPS[$(( ${#ALL_ZIPS[@]} - 1 ))]`.

**Result**: adversarial_ai_validator builds end-to-end → `adversarial_ai_validator_BLOCK_B_full_20260314_093048.zip` (5.0MB)

Files: `fo_test_harness.py`, `run_integration_and_feature_build.sh`, `directives/prompts/build_integration_fix.md`

## 2026-03-14

### feat: run_integration_and_feature_build.sh — auto-resume from prior run state

Script now detects completed phases/features from ZIPs on disk at startup. No flags needed on rerun.

Detection order (filesystem only, no state file):
1. If `*_BLOCK_B_full_*.zip` exists → exit immediately (already done)
2. If `<INTAKE_STEM>_p1_BLOCK_B_*.zip` exists → skip Phase 1, set PHASE1_ZIP_OVERRIDE
3. Walk each intelligence feature in order; for each feature intake JSON that exists, check for
   its `<startup_slug>_BLOCK_B_*.zip` — stop at the first gap → that's the resume point

On failure, the error message now just says: rerun the same command. The script picks up automatically.

Files: `run_integration_and_feature_build.sh`

## 2026-03-13

### fix: run_integration_and_feature_build.sh — sed \0 not valid on macOS, causes \0 artifact dir

`latest_artifacts_dir()` and `latest_iteration_num()` used `\\0` in sed replacement strings,
intending "whole match". BSD sed (macOS) does not support `\0` — it emitted the literal string `\0`.
Result: `ARTIFACTS_DIR=\0`, `LATEST_ITER=\0`, then `--resume-iteration '\0'` crashed the harness.
Fix: replaced `\\0` with `&` (whole match in POSIX/BSD sed) in all three sed calls.
Files: `run_integration_and_feature_build.sh`

### fix: prune __pycache__ from artifacts; QA/consistency prompt fixes for recurring false positives

**fo_test_harness.py** — `prune_non_business_artifacts()` now removes all `__pycache__` dirs via
`shutil.rmtree` before the main pruning loop. Python bytecode was being extracted and carried
forward by merge_forward, causing QA to flag `__pycache__/analysis.py` as a defect.

**qa_prompt.md** — Added to DO NOT FLAG:
- `status`/`processing_status` columns — standard state tracking, never scope creep
- Internal helpers (`_extract_*`, `_parse_*`, `_format_*`, `_calculate_*`) — private impl details
- `__pycache__` / `.pyc` files
- JavaScript destructuring order (has no effect on behavior)

**build_ai_consistency.md** — Added to DO NOT FLAG:
- `../utils/api`, `../core/useEntitlements`, `../core/EntitlementGate`, `../hooks/useAnalytics` — boilerplate frontend utils always present at runtime
- Internal helper methods

Root cause of feature 2 (adversarial_ai Anthropic SDK) 20-iter failure: QA removed `status`
from Analysis model as "scope creep"; Consistency re-added it as "AttributeError at runtime".
Direct QA↔Consistency contradiction → infinite loop across 8 QA rejections.

## 2026-03-12

### fix: CHECK 10 static gate — async def methods not counted, causing permanent false-positive loops

`_run_static_check()` CHECK 10 (route↔service contract) built the `methods` set for each
class using `isinstance(item, ast.FunctionDef)` only. In Python's AST, `async def` creates
`ast.AsyncFunctionDef` — a completely different node type. So any service method declared
`async def` was never added to `methods`, and every call to it was flagged as
"Call to missing method `X.method()`" regardless of whether the method actually existed.

Observed: `process_adversarial_analysis()` correctly defined as `async def` on
`AIOrchestrationService`, yet the static gate fired the same defect 13 consecutive iterations
(iters 8-11, 14-17, 19, 20 on adversarial_ai_validator feature run). The surgical fix added
the method each time, but CHECK 10 could never see it because it only saw `def`, not `async def`.

Fix: `isinstance(item, ast.FunctionDef)` → `isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))`
at `fo_test_harness.py` line ~5222.

Impact: Any project whose services use `async def` was permanently stuck in a static loop.
This is the root cause of the 13-iteration adversarial_ai_validator oscillation.

### fix: full business_config.json schema coverage — all boilerplate keys populated

Full schema audit of every boilerplate frontend component that reads `business_config.json`
revealed 5 top-level keys missing entirely and 2 keys incomplete.

**Added (missing entirely):**
- `pricing` — headline, subheadline, faq array
- `contact` — headline, methods, form fields definition
- `faq` — categorised Q&A (General + Billing)
- `terms_of_service` — 5 standard legal sections
- `privacy_policy` — 5 standard legal sections

**Fixed (incomplete):**
- `home` — added `features[].icon`, `social_proof` (stats + testimonials), `final_cta`
- `footer` — added `tagline`; changed link key `href` → `url` to match boilerplate schema

All values are derived from intake (startup name, tagline, must-have features) or safe
generic defaults. No AI call required.

### fix: add home block to business_config.json generation

`Home.jsx` crashes with `TypeError: can't access property "hero", a is undefined` at line 30
because `_generate_business_config()` never set a `home` key — absent/null in every generated ZIP.

Fix: added `home` block to the config dict (~line 3186):
- `hero.headline` — startup name
- `hero.subheadline` — tagline from intake
- `hero.cta_primary` / `hero.cta_secondary` — Get Started / Learn More
- `features` — first 6 must-have features as `{title, description}` objects

Same root cause as the footer fix (same session): boilerplate reads top-level config keys
unconditionally at render time; harness must generate a safe default for every one of them.

### fix: add footer block to business_config.json generation

`Footer.jsx` in the boilerplate calls `footer.columns.map(...)` on startup. The harness
`_generate_business_config()` never set a `footer` key — it was absent/null in every
generated ZIP — causing a runtime TypeError that white-screened the entire app.

Fix: added `footer` block to the config dict in `_generate_business_config()` (line ~3187):
- Column 1 — startup name, links: Home / Dashboard / Pricing
- Column 2 — "Product" with first 4 must-have features from intake (as `{label, href}` objects)
- Column 3 — "Company" with About / Contact (support email) / Privacy / Terms
- `copyright` — derived from startup name

No AI call — pure intake derivation, same pattern as the rest of `_generate_business_config()`.
Root cause found via post-deploy QA on AWI build.

## 2026-03-11

### fix: add business-page import preflight + auto-fix helper

Vercel builds failed after moving business pages into `frontend/src/business/pages` because
those copied files referenced `../utils/api`, which only resolves from their original
`business/frontend/pages` location. CRA only compiles files inside `frontend/src`, so the
copy step is required — but it changes relative import paths.

New script: `deploy/check_business_imports.py`
- Scans `business/frontend/pages/*.jsx` and validates relative imports *as if copied* to
  `frontend/src/business/pages`.
- Prints unresolved imports and optionally rewrites `../utils/api` → `../../utils/api`.
- If you confirm the fix, it auto-commits the changed business pages.

### feat: import preflight can now report all relative imports and check assets

`deploy/check_business_imports.py` now supports:
- `--report-all` to list *all* relative imports and their post-copy resolution
- `--include-assets` to validate css/images/fonts
- `--ext .mjs` (repeatable) to include extra extensions

### fix: ensure Railway/Nixpacks sees Python by adding root requirements.txt

Railway/Nixpacks failed to detect Python when the repo root had no `requirements.txt`.
The backend lives in `backend/`, so Nixpacks had no language signal and aborted.

Pipeline now writes a root `requirements.txt` containing:
```
-r backend/requirements.txt
```
and fails fast if `backend/requirements.txt` is missing.

### feat: add --skip-git-push for redeploys

`pipeline_deploy.py` now supports `--skip-git-push` to bypass git add/commit/push
when you only want to redeploy from existing commits.

### feat: configurable Railway wait time (default 10 minutes)

Railway deploy URL polling now defaults to 10 minutes and can be overridden with
`--railway-wait-minutes N` when running `pipeline_deploy.py`.

### fix: Railway URL fallback + deployment ID logging

When `deployment.url` is delayed, the pipeline now falls back to `railway domain` (CLI) to
surface a usable URL and logs the detected deployment ID + status once a new deploy appears.

### feat: helper to write deploy state JSON files

New `deploy/write_deploy_state.py` writes `railway.deploy.json` or `vercel.deploy.json`
from CLI args (project IDs, service IDs, service domain) to streamline first-time setup.

### fix: prefer Vercel production URL for CORS

Pipeline now derives the stable production domain (`https://<project>.vercel.app`) from
`vercel.deploy.json` and uses that for downstream CORS instead of ephemeral preview URLs.

### feat: auto-update Auth0 URLs after frontend deploy

New `deploy/auth0_update_urls.py` updates Auth0 callback/logout/origin URLs. The pipeline
now runs it automatically after a successful frontend deploy when `AUTH0_MGMT_TOKEN` is set.

### new: cleanup_fo_harness_runs.py (targeted cleanup)

Adds a helper to clean older run directories in `fo_harness_runs` by removing heavy
subfolders while keeping the latest N runs per prefix and all ZIPs. Default keep = 5.

## 2026-03-10 (late session)

### fix: static/compile file contents not injected — business/ prefix filter was too strict

Static gate defects use file paths relative to the artifacts dir (e.g. `models/AnalysisRequest.py`).
The `defect_target_files` collection at line ~5989 filtered `startswith('business/')`, so wrong-path
files were excluded → `_read_target_file_contents` returned `{}` → Claude got
"no current file contents found" → reconstructed from memory → same wrong content each iteration
→ static gate cycled 6 times on the same defect (iters 11-16 in adversarial_ai_validator_p1).

Fix: removed `startswith('business/')` requirement for `defect_source in ('static', 'compile')`.
These sources find files wherever the static checker found them; Claude still gets the actual
file content and can fix the specific issue without memory reconstruction.

## 2026-03-10 (deploy fix #19)

### fix: Railway root_directory "backend" excludes business/ from container

`railway_deploy.py` was calling `set_root_directory(service_id, "backend")` — this scopes
Railway's deployed container to `backend/` only, so `business/` at repo root never gets
copied in. Loader correctly resolves the path but the directory doesn't exist.
Fix: removed the `set_root_directory` call. Root stays at repo root; `railway.toml`
`startCommand = "cd backend && uvicorn ..."` handles the subdirectory.
Manual fix required for live AWI: clear Root Directory in Railway dashboard.

## 2026-03-10 (deploy fix #18)

### fix: add missing Session import from sqlalchemy.orm

`main.py` uses `db: Session = Depends(get_db)` as a type annotation evaluated at module load time.
`Session` was never imported — only `get_db` was pulled from `core.database`.
Fix: added `from sqlalchemy.orm import Session` after the `core.database` import in both AWI repo
(`f61a0a8`) and boilerplate (`b54ec0d`).

## 2026-03-10 (deploy fix #16)

### fix: add email-validator to boilerplate requirements.txt

`main.py` uses `EmailStr` from pydantic which requires the separate `email-validator` package.
It wasn't in `requirements.txt` → Railway container crashed at import with:
`ImportError: email-validator is not installed`

Fix: added `email-validator>=2.0.0` to `saas-boilerplate/backend/requirements.txt`.
Also pushed directly to AWI repo (`b4c82a2`).

## 2026-03-10 (late)

### fix: fo_test_harness.py — _generate_business_config missing description field

`main.py` hard-requires `BUSINESS_CONFIG["business"]["description"]`. The harness-generated
`business_config.json` was missing this field → Railway crashed on startup with `KeyError: 'description'`.

Fix: added `"description": tagline` to the `business` block in `_generate_business_config()`.

### fix: boilerplate backend/config example files — wrong JSON key names

All `*.example.json` files used short key names that didn't match what the shared libs read:
- `stripe_config.example.json`: `secret_key` → `stripe_secret_key`
- `mailerlite_config.example.json`: `api_key` → `mailerlite_api_key`
- `auth0_config.example.json`: `domain/client_id/client_secret/audience` → `auth0_`-prefixed

Pipeline copies example → real file on first deploy; wrong keys caused hard startup crashes.

## 2026-03-10

### feat: harness generates business_config.json from intake at polish step

Boilerplate ships with InboxTamer placeholder in business_config.json.
Harness never replaced it — every ZIP had wrong branding/pricing/entitlements.

Fix: added `_generate_business_config()` to FOHarness, called unconditionally
at the start of `_post_qa_polish()`. Derives startup name, tagline, pricing,
entitlements, and branding from intake_data. Writes to both
`business/frontend/config/` and `business/backend/config/` in artifacts dir.
No AI call — pure intake derivation.

### fix: pipeline_deploy.py — force-add backend/config/business_config.json before push

Railway container was failing with `FileNotFoundError: Missing config: /app/config/business_config.json`
because `backend/config/business_config.json` is gitignored and was never pushed to the repo.

Fix in `_ensure_frontend_business_config()`:
- If `backend/config/business_config.json` doesn't exist but `.example.json` does → copy it.
- Force-add via `git add -f` so Railway container gets it even if .gitignore excludes it.

### fix: pipeline_deploy.py — railway.toml written to BOTH repo root AND backend/

Railway scans from repo root. If `railway.toml` was only in `backend/` it wasn't found.
Now writes two files:
- Repo root: `startCommand = "cd backend && uvicorn main:app --host 0.0.0.0 --port $PORT"`
- `backend/railway.toml`: `startCommand = "uvicorn main:app --host 0.0.0.0 --port $PORT"`
Nixpacks now reliably detects Python (root railway.toml exists + requirements.txt in backend/).

### new: deploy/repo_setup.py — GitHub repo + App installation helper

New script to handle GitHub repo setup outside of the deploy pipeline:
- Reads `GITHUB_USERNAME` from `~/Downloads/ACCESSKEYS/ACCESSKEYS` env file automatically.
- Creates GitHub repo via API (if not exists).
- For App installation (required for Railway): PAT/gh CLI can't hit `/user/installations` (403).
  Falls back to opening `github.com/settings/installations` in browser and printing instructions.
- Usage: `python deploy/repo_setup.py --repo <name>`

### new: deploy/auth0_setup.py — Auth0 SPA app + API creation

New script to automate Auth0 app/API setup per deployment:
- Reads `AUTH0_DOMAIN` and `AUTH0_KEY` (Management API token) from env.
- Creates SPA application + Resource Server API for the project.
- Strips whitespace from all values (`"".join(value.split())`).
- Saves credentials to `~/Downloads/ACCESSKEYS/auth0_<app>.env`.

## 2026-03-09

### fix: Railway project creation — workspaceId + CLI logout + name truncation

Three separate Railway project creation failures fixed:

1. **workspaceId required**: Railway API now requires `workspaceId` on `projectCreate`.
   Added `RailwayAPI.get_workspace_id()` (reads from `me.workspaces[0].id`) and passes it
   to `create_project()` automatically.

2. **CLI session conflict**: Railway CLI session token overrides API token → auth failures.
   `pipeline_deploy.py` now runs `railway logout` before STEP 2 so API token takes precedence.

3. **Name truncation at word boundary**: 50-char hard truncation cut mid-word → Railway
   rejected the name. Now truncates at last hyphen before 40 chars.
   e.g. `ai-workforce-intelligence-downloadable-executive-report` → `ai-workforce-intelligence-downloadable`

### fix: pipeline_deploy.py + vercel_deploy.py — updated for flat repo layout

After zip_to_repo.py switched to flat layout (backend/ frontend/ business/ at root),
the pipeline was still referencing saas-boilerplate/ paths everywhere.

Changes:
- `_ensure_railway_toml()`: writes to `backend/railway.toml` (not repo root or business/backend/).
  Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT` (no cd needed, Railway root = backend/).
- `_ensure_frontend_business_config()`: path updated from `saas-boilerplate/frontend/src/config/` → `frontend/src/config/`
- `_ensure_business_pages_in_src()`: dest updated from `saas-boilerplate/frontend/src/business/pages/` → `frontend/src/business/pages/`.
  loader.js patch now supports both old (`../../../../business/frontend/pages`) and new (`../../../business/frontend/pages`) relative paths.
- `vercel_deploy.py`: default `root_directory` changed from `saas-boilerplate/frontend` → `frontend`.
  Default env file path changed from `saas-boilerplate/frontend/.env` → `frontend/.env`.
- Removed broken `serviceUpdate rootDirectory` API call (always 400) and `githubReposRefresh` mutation (doesn't exist).
  railway.toml inside backend/ is the definitive fix — no API call needed.
- Railway project name truncated to 50 chars (API rejects longer names).

### fix: zip_to_repo.py — flat repo layout (backend/ frontend/ business/ at root)

`extract_zip()` was copying `saas-boilerplate/` as a nested directory into the repo.
Railway's root was set to `business/backend/` but `main.py` and `requirements.txt` live at
`saas-boilerplate/backend/` — Railway couldn't detect Python, build failed.

Fix: extract the boilerplate's contents flat into the repo root:
- `saas-boilerplate/backend/`  → `repo/backend/`   (main.py, core/, lib/, requirements.txt)
- `saas-boilerplate/frontend/` → `repo/frontend/`
- harness artifacts `business/` → `repo/business/`

Railway root dir = `backend/`, Vercel root dir = `frontend/`.
Affects AWI and Wynwood ZIPs (both had same nested structure).

### fix: run_integration_and_feature_build.sh — set -e kills + missing flags + loop

Three bugs fixed in `run_integration_and_feature_build.sh`:

1. **`set -e` kills script before exit-code capture** — `IC_EXIT=$?` (and `P1_EXIT`, `FEAT_EXIT`)
   never ran because `set -euo pipefail` exits the script the moment the command returns non-zero.
   Fix: initialize each exit var to 0 before the call, append `|| VAR=$?` to capture without dying.
   Applies to Phase 1 build, every feature build, and integration_check calls.

2. **Missing `--max-iterations` and `--no-polish` on integration fix pass** — fix pass ran with
   default iteration cap and polish enabled, causing unnecessary token spend.
   Fix: pass `--max-iterations "$MAX_ITER" --no-polish` to the fix pass harness call.

3. **Single integration re-check that hard-exits on failure** — after one fix pass the script
   exited with error if issues persisted (no retry).
   Fix: converted to `while [[ $IC_EXIT -ne 0 && $FIX_PASS -lt $MAX_FIX_PASSES ]]` loop
   (MAX_FIX_PASSES=2). Also extracted `_run_integration_check()` helper to deduplicate
   the two integration_check calls and correctly refresh `ARTIFACTS_DIR` from `LATEST_RUN_DIR`.

### fix: --resume-mode fix + --integration-issues conflict

When both `--resume-mode fix` and `--integration-issues` were passed together, the `fix`
warm-start block ran after the integration block and overwrote `previous_defects` with the
old QA report, discarding the integration issues entirely. The loop then started at
`_ws_iteration + 1` which could exceed `--max-iterations`, causing zero iterations and
"Should not reach here" exit.

Fix: added `and not _integration_loaded` guard to the `fix` mode block (same guard the `qa`
mode block already had). When `--integration-issues` is loaded, the integration block owns
`previous_defects` and `iteration` — `fix`/`qa` warm-start blocks are suppressed.

### feat: consistency fix sharpening before Claude patch

Consistency A↔B oscillation: Claude kept shifting mismatches between files because the
Fix field only said "align ReportService with ScoringService" — no indication of which side
changes, which function, or what the exact new code looks like.

New `_sharpen_consistency_issues()` method — called after `_parse_consistency_report()` and
before `_format_consistency_defects_for_claude()`:
- Reads current file contents for every file pair involved in each consistency issue
- Calls gpt-4o-mini with SHARP-N format: `FILE_TO_CHANGE`, `FUNCTION`, `CHANGE` (exact line)
- Replaces vague Fix field with precise one-sided instruction → Claude touches one file only
- Saves sharpened output to `logs/iteration_N_consistency_sharpen.log`

Same pattern as QA triage sharpening, applied at the consistency gate.

New methods: `_sharpen_consistency_issues()`

### fix: SYSTEMIC pre-QA uses wide surgical patch, not cold-start full build

Full build prompt for SYSTEMIC static/consistency escalations was 89K chars — included all
historical prohibitions from warm-start + full intake. Too much noise, risks regression of
already-correct files, overwhelms Claude on a pre-QA fix.

Wide surgical patch: surgical prompt template but with ALL current artifact files as context
(not just 2-3 defect targets). Claude sees every existing file + all defects → fixes missing
methods, adds missing files, preserves correct files. Prompt stays ~20K chars not 89K.

### feat: pre-QA triage for static + consistency gates (SURGICAL vs SYSTEMIC)

Static and consistency defect sources always routed to surgical patch, burning 6+ iterations
on missing-file defects, no-frontend-pages, and multi-file coupling before ever reaching
Feature QA. Same pattern that broke Feature QA is now fixed at the pre-QA layer.

New `_triage_pre_qa_strategy()` method — rule-based, no extra API call:
- `consecutive_iters >= 2` → SYSTEMIC (surgical already failed twice)
- `≥4 distinct target files` → SYSTEMIC (too many moving parts)
- Missing-file patterns in defect text ("no frontend pages", "does not resolve",
  "does not exist in artifacts", etc.) → SYSTEMIC

SYSTEMIC → full build prompt with all defects + full governance context (16384 tokens).
SURGICAL → existing surgical patch path (unchanged).
quality/compile/integration always remain surgical (their defects are narrow by nature).

### fix: triage content extraction — wrong key on ChatGPTClient response

Triage was calling `result.get('content', '')` but `ChatGPTClient.call()` returns the raw
OpenAI response dict where content is at `choices[0].message.content`. Every triage call
returned empty string silently — zero sharpening happened across the entire first run with
the triage feature. Fixed to `result['choices'][0]['message']['content']`.

### feat: defect triage + fix sharpening after Feature QA rejection

Root cause of oscillation: QA returns a vague Fix field ("update the validation logic") → Claude
interprets it differently each time → defect ping-pongs for 10+ iterations without resolving.
Even with surgical patch, if the Fix instruction is ambiguous, Claude guesses and may make things
worse or touch the wrong thing.

New step: after `_filter_hallucinated_defects()` and before triggering any build, run
`_triage_and_sharpen_defects()` which calls gpt-4o-mini on all surviving defects to:

1. **SURGICAL**: isolated 1-5 line fix. Replaces vague Fix field with exact function name, current
   line, and what it must change to. No interpretation needed — Claude reads and applies.
2. **SYSTEMIC**: defect is architectural, OR has appeared 3+ times (surgical approach failed) →
   forces full build with architectural direction, not a line-level patch.
3. **INVALID**: scope creep or not in intake spec → drops defect. If ALL drop → verdict flips to
   ACCEPTED without triggering another build.

`_triage_strategy` loop variable carries the decision into prompt routing:
- SURGICAL + ≤5 files → existing surgical patch path
- SYSTEMIC → forces full build prompt regardless of file count
- ACCEPTED → no build triggered, loop exits cleanly

Triage output saved to `logs/iteration_N_triage_output.log`.
INVALID dropped defects saved to `logs/iteration_N_triage_contested.log`.

New methods: `_triage_and_sharpen_defects()`, `_parse_triage_output()`,
`_build_intake_summary_for_triage()`

### fix: QA defect fix — surgical patch for targeted QA fixes (≤5 defect files)

Root cause: a single-file QA defect (Auth0 `user.getAccessTokenSilently()` in Assessments.jsx)
triggered a full build prompt → Claude regenerated all files from memory → 3 new consistency
defects appeared at the next iteration, undoing a clean consistency pass.

New behavior: when `defect_source='qa'` and defect_target_files are known and ≤5 files,
the harness uses the surgical patch prompt (`integration_fix_prompt` / `build_integration_fix.md`)
instead of the full build prompt. Current file contents loaded from prev-iteration artifacts.

- Threshold: ≤5 target files → surgical; >5 or no known targets → full build (unchanged)
- Logs: `[QA] Using surgical patch for N targeted QA defect file(s)` vs full-build fallback
- Files: `fo_test_harness.py` (new QA surgical branch in prompt selection logic)

## 2026-03-08

### fix: railway_deploy.py — set root directory to business/backend

Railway's Railpack scans repo root and can't find the Python app because
the backend lives in `business/backend/`. Added `serviceUpdate` mutation
call after service create/reuse to set `rootDirectory = "business/backend"`.

- `RailwayAPI.set_root_directory(service_id, root_directory)` — new method
- Called in `deploy_backend()` as Step 3b, before env vars and deploy trigger

### fix: consistency fallthrough with HIGH issues escalates to full-build fix (not QA passthrough)

Root cause: on consistency hard cap (4 iters), harness cleared all defect context and fell
through to ChatGPT QA. QA evaluated cold, its defects got filtered as fabricated evidence,
build "accepted" with real AttributeError bugs (contact_email vs email, assessment.title, etc.).

New behavior on fallthrough:
- HIGH issues remain → full-build Claude fix pass (defect_source='qa', 16384 tokens, full
  governance context, consistency issues formatted as QA defects). Claude fixes holistically
  across all files. Consistency consecutive counter reset → 4 more surgical attempts after.
- Only LOW/MEDIUM issues remain → fall through to Feature QA as before (safe to accept).

### fix: dynamic token limit for multi-file surgical patches (8192→16384 when ≥2 target files)

With surgical patches now including current file contents in the prompt, 8192 output tokens
is insufficient when fixing ≥2 files simultaneously. Claude compresses/drops methods to fit
(ReportService.py shrank 4731→2256 chars, assessments.py 2285→1060) — creating new defects
instead of fixing old ones.

`Config.get_max_tokens(iteration, defect_source, n_target_files)` now accepts file count:
- 1 target file → 8192 tokens (single file, safe to cap, saves ~$0.12/iter)
- ≥2 target files → 16384 tokens (each file needs full room, can't compress)

### fix: surgical patch applied to ALL targeted fix types (static/consistency/quality/compile/integration)

All non-QA defect sources now use the same surgical patch approach — current file contents
passed to Claude for every targeted fix, regardless of defect type. Previous split
(consistency+integration → surgical, static+quality+compile → pattern-based) was wrong:
even for wrong-import or missing-method static defects, seeing the actual file prevents
accidental restructuring. The boilerplate reference in the governance section already
covers pattern guidance — the file content is the missing piece for ALL patch types.

- Single prompt branch for all defect sources: `integration_fix_prompt()` with `_read_target_file_contents()`
- `build_integration_fix.md` renamed conceptually to generic "SURGICAL PATCH" — header updated,
  added Tenancy import reference + `Depends(get_current_user)` rule from old static_fix template
- `_read_target_file_contents(iteration, target_files)` helper shared across all sources

### fix: surgical patch extended to consistency fixes + _read_target_file_contents helper

Same root cause as integration fix churn: consistency patch prompt had no current file contents
→ Claude rewrote ReportService.py from memory → dropped get_all_reports/create_report/update_report
→ static gate caught 6 missing-method defects → wasted static fix cycle.

- `defect_source='consistency'` now routes to `integration_fix_prompt` (surgical, with file contents)
  alongside `defect_source='integration'` — both use `build_integration_fix.md` template
- `defect_source='static'/'quality'/'compile'` keep `static_fix_prompt` (pattern-based, no file contents)
  since their defects are structural (wrong imports, Base class) not method-preservation issues
- New `FOHarness._read_target_file_contents(iteration, target_files)` helper — reads prev-iteration
  artifact files from disk; used by both integration and consistency patch paths; no duplication

### fix: integration fix pass — surgical patch with current file contents (defect_source='integration')

Root cause: `--integration-issues` warm-start set `defect_source='static'`, routing into `static_fix_prompt`.
That prompt doesn't include current file contents → Claude reconstructs model files from memory → introduces
wrong `Base` import or duplicate `__tablename__` → static gate loops for 12+ iterations → integration issues
never actually fixed (observed on AWI iter 20–32).

Fix:
- New `defect_source='integration'` — separate route, never confused with static churn
- New `PromptTemplates.integration_fix_prompt()` — reads actual current file content from prev iteration
  artifacts dir and passes it verbatim in the prompt so Claude patches surgically
- New `directives/prompts/build_integration_fix.md` — hard-prohibits touching `__tablename__`, Base import,
  existing Column definitions (the exact triggers of prior static gate failures)
- `Config.get_max_tokens()` includes `'integration'` in the patch-token group (8192, not 16384)
- Integration warm-start now prints `[INTEGRATION] Loaded N current file(s) for surgical patch`

### feat: integration_check.py + --integration-issues harness flag

New standalone post-build integration validator with 4 deterministic checks (no AI):
1. **Route inventory** — frontend fetch()/api calls vs backend @router decorators
2. **Model field refs** — service model.field accesses vs SQLAlchemy Column definitions
3. **Spec compliance** — intake keywords (PDF, email, KPI names) vs artifacts
4. **Import chains** — from business.X import Y vs actual files in artifact set

Outputs `integration_issues.json` in harness-compatible format.

`fo_test_harness.py`: added `--integration-issues JSON_FILE` flag.
- Loads issues, converts to static defect format, seeds Claude targeted fix pass
- After fix pass, full QA loop runs normally (GATE 0 → GATE 1)
- Use with `--resume-run` + `--resume-iteration` to target the accepted iteration

Usage:
```bash
python integration_check.py --zip fo_harness_runs/foo.zip --intake intake/foo.json
python fo_test_harness.py <intake> --resume-run <run_dir> --resume-iteration 19 --integration-issues integration_issues.json
```

Validated on AWI downloadable report ZIP — caught all 4 bugs found by manual review:
missing assessments route, client.email field gap, assessment.title field gap, missing PDF library.

### fix: repo_setup.py — browser fallback for GitHub App access (API 403)

`GET /user/installations` requires a special OAuth scope not available in PATs.
Updated repo_setup.py to open `https://github.com/settings/installations` in browser
and print step-by-step instructions (Click Configure → add repo → Save).
Still verifies repo exists via GitHub API before opening browser.
- Usage: `python deploy/repo_setup.py --repo wynwood-thoroughbreds`
  (GITHUB_USERNAME read from env var / ACCESSKEYS automatically)

### feat: repo_setup.py — grant Railway + Vercel GitHub App access via API

Root cause of "Repository not found or not accessible" errors in Railway:
Railway's GitHub App wasn't granted access to the repo. Previously required
clicking through GitHub Settings → Applications → Railway → Configure.

- `deploy/repo_setup.py`: new script, verifies repo on GitHub then opens
  GitHub App settings page in browser with printed instructions.
- Reads GITHUB_USERNAME + token from ACCESSKEYS automatically
- Usage: `python deploy/repo_setup.py --repo wynwood-thoroughbreds`
- Should be run once per new repo before pipeline_deploy

### fix: Railway CLI fallback for env var setting + console paste fallback

Railway GraphQL API (`variableUpsert`) is unauthorized for project tokens and some
personal tokens. Added two fallback layers:

1. **Railway CLI** (`railway variables --set`) — already installed, uses `RAILWAY_TOKEN`
   env var, called via subprocess when API fails
2. **Console paste** — if CLI also fails, prints all failed vars + dashboard URL
   in a clean block ready to copy-paste into Railway Variables tab

Both `railway_deploy.py` (initial env vars) and `pipeline_deploy.py` (CORS/ENVIRONMENT
post-Vercel) now use the same three-tier pattern: API → CLI → print.

### fix: Railway variableCollectionUpsert fallback for env var setting

Railway's `variableUpsert` GraphQL mutation fails with "Repository not accessible"
for some token types even when deploy/trigger works fine. Root cause: the mutation
validates GitHub repo access which isn't required for variable setting.

- `railway_deploy.py` `set_variable()`: tries `variableCollectionUpsert` (bulk) first
  when `environment_id` is available — this bypasses the GitHub repo validation
- Falls back to `variableUpsert` if bulk fails

### feat: full pipeline_deploy auto-wiring — Auth0, CORS, ENVIRONMENT

**How the pipeline works now (end-to-end):**

Pre-flight:
- Checks `~/Downloads/ACCESSKEYS/auth0_<app-name>.env` exists — exits with instructions if not
- Injects Auth0 vars (DOMAIN, CLIENT_ID, CLIENT_SECRET, AUDIENCE) into repo `.env`

Step 1 — GitHub push
Step 2 — Railway deploy (backend up with Auth0 vars from .env)
Step 3 — Vercel deploy (frontend up, CI=false so lint warnings don't fail build)

Post-deploy (once Vercel URL is known):
- Sets `CORS_ORIGINS=<vercel-url>` on Railway via API
- Sets `ENVIRONMENT=production` on Railway via API
- Patches Auth0 SPA callback/logout/web_origins with Vercel URL (if AUTH0_MGMT_TOKEN set)

One-time per app:
- `python deploy/auth0_setup.py --app-name <name>` → creates Auth0 app+API, saves to ACCESSKEYS

Fixes in this session:
- `railway_deploy.py`: `set_variable` now accepts `environment_id`; reads from `railway.deploy.json`
  before falling back to API lookup (Railway GraphQL `get_environment_id` silently fails for some accounts)
- `railway.deploy.json`: store `environment_id` so Railway env var pushes work reliably
- `vercel_deploy.py`: upsert env vars (PATCH existing on 400/409) instead of failing on duplicates
- `pipeline_deploy.py`: Auth0 URL patch only runs if Vercel actually succeeded
- `auth0_setup.py`: reads `AUTH0_DOMAIN`/`AUTH0_KEY` from env vars; strips all whitespace from token

### feat: auth0_setup.py + auto Auth0 URL patch in pipeline_deploy

- `deploy/auth0_setup.py`: creates Auth0 SPA Application + API via Management API,
  saves credentials to `~/Downloads/ACCESSKEYS/auth0_<app-name>.env`
- `deploy/pipeline_deploy.py`: after Vercel URL is resolved, automatically patches
  Auth0 callback/logout/web_origins if `AUTH0_MGMT_TOKEN` env var is set and the
  ACCESSKEYS file exists for the app — no second manual command needed
- One-time setup per app: `python deploy/auth0_setup.py --domain ... --mgmt-token ... --app-name ...`
- Ongoing: set `AUTH0_MGMT_TOKEN` in env, pipeline handles the rest

### fix: set CI=false in Vercel deploy to prevent ESLint warnings failing build

Vercel sets `CI=true` by default, which causes `react-scripts build` to treat all ESLint
warnings as hard errors. This broke the wynwood-thoroughbreds frontend deploy with 8 lint
errors across boilerplate files and Claude-generated pages (unused vars, exhaustive-deps).

- `deploy/vercel_deploy.py`: inject `CI=false` into `env_vars` before setting project env vars
- All ESLint warnings remain visible but no longer fail the build

## 2026-03-07

### fix: prune boilerplate-owned frontend config files Claude generates

Root cause: `BOILERPLATE_VALID_PATHS` explicitly whitelisted `tailwind.config.js`,
`next.config.js`, `postcss.config.js` etc. under `business/frontend/` as "valid to keep."
Claude generates these for dashboard/styled features. Static Check 8 correctly flags them
as broken (missing `content:` paths, swapped configs) but the pruner never removes them
because they're on the whitelist → static loop.

- Removed all boilerplate-owned config files from `BOILERPLATE_VALID_PATHS`
- Added `BOILERPLATE_OWNED_FRONTEND_CONFIGS` set (tailwind, next, postcss, tsconfig, jest etc.)
- Pruner now silently drops these before the whitelist check with a clear log message
- Prompt `build_boilerplate_path_rules.md`: explicit NEVER rules for each config filename

### fix: test generation regex — python fences extracted correctly

- Polish step test extraction regex only matched `javascript|js|typescript|ts` fences.
- Claude generates Python tests with ` ```python` fences → 0 files extracted, $0.09 wasted per run.
- Fixed: `(?:\w+)?` matches any language tag (python, js, jsx, blank).
- `fo_test_harness.py` line ~3334.

### fix: reduce patch iteration token cost + consistency hard cap

**Patch iteration max_tokens 16384 → 8192**
- Static/consistency/quality/compile patch iterations only output 1-3 files.
  Using 16384 tokens was paying for 2× the output we actually needed.
- `Config.get_max_tokens(iteration, defect_source)` now returns 8192 when
  `defect_source` is static/consistency/quality/compile; 16384 for QA/full builds.
- `Config.CLAUDE_MAX_TOKENS_PATCH = 8192`
- Savings: ~$0.12 per patch iter. On a 10-patch build: ~$1.20.

**Consistency hard cap (mirrors Fix 3 for static)**
- `Config.MAX_CONSISTENCY_CONSECUTIVE = 4`
- If AI consistency check hasn't cleared after 4 consecutive iterations, falls through
  to Feature QA instead of burning more targeted patches.
- Resets `_consistency_consecutive_iters`, clears defect_source to 'qa'.
- Gate trace records `CONSISTENCY:FALLTHROUGH`.
- Root cause: same as static deadlocks — method name / import mismatches that a
  full-context Feature QA prompt resolves better than targeted consistency patches.

### fix: static Check 13 + prompt — missing frontend pages in boilerplate mode

Root cause: Claude outputs only backend files (routes, models, services) and never
generates any `business/frontend/pages/*.jsx`. The QA filter correctly removed all
4 defects (they referenced non-existent `.jsx` files), flipping verdict to ACCEPTED
on a build with zero frontend. Quality gate also missed the gap.

- **Static Check 13** (`fo_test_harness.py`): if backend routes exist but no
  `business/frontend/pages/*.jsx` files are found → HIGH defect. Will catch this
  on the first iteration rather than letting QA hallucinate about files that aren't there.
- **Prompt** (`directives/prompts/build_boilerplate_path_rules.md`): added explicit
  MANDATORY OUTPUT REQUIREMENTS block at the pre-prompt checklist — "at least one
  .jsx page per user-facing feature" + explicit note that Shopify integration does NOT
  remove the React page requirement. Frontend pages are NOT provided by the boilerplate.

### fix: static check infinite loop — 3 anti-repetition fixes (Fix 1/2/3)

Root cause: route files call e.g. `calculate_score()` but the service defines
`calculate_assessment_score()`. Claude fixes arity but not the name → same
defect every iteration → 20+ static-only iterations burning ~$3/run.

**Fix 1 — Repetition detection + joint rebuild escalation**
- Track defect fingerprints `(file, issue[:80])` across consecutive static iterations.
- When a fingerprint hits 3+ consecutive occurrences, mark defect as `stuck=True`.
- Stuck defects trigger `related_files` inclusion, pulling the service file into
  the target list alongside the route file (joint route+service rebuild).

**Fix 2 — route↔service joint target files**
- `_run_static_check` Check 10: missing-method defects now carry `related_files=[service_file]`
  (the file that defines the class with the missing method).
- `defect_target_files` calculation: if any pending defect has `related_files` or
  `stuck=True`, the service file is automatically added to the target list.
- Result: Claude regenerates BOTH sides of the interface in one shot → method names align.

**Fix 3 — Static hard cap + fallthrough to Feature QA**
- `Config.MAX_STATIC_CONSECUTIVE = 6` — if static check has failed for 6 consecutive
  iterations without clearing, the harness falls through to Feature QA instead of
  burning more static fix iterations.
- Gate trace records `STATIC:FALLTHROUGH`. Resets all static tracking state.
- Feature QA with full context + coherent cross-file view often resolves method-name
  mismatches that targeted single-file patches cannot.

### feat: --prior-run flag seeds prohibition tracker across feature builds

- `fo_test_harness.py`: new `--prior-run <dir>` flag reads
  `qa/iteration_*_qa_report.txt` from a prior run directory and seeds the
  recurring_tracker before the build loop starts. Works alongside `--resume-run`
  — both dirs are scanned if set.
- `run_feature_build.sh`: tracks `LATEST_RUN_DIR` after each phase/feature and
  passes `--prior-run` to every subsequent harness call so prohibitions chain:
  Phase 1 → Feature 1 → Feature 2 → ...
- Root cause: fresh feature runs start with an empty prohibition tracker even
  when Phase 1 burned 17 iterations learning what Claude keeps getting wrong.
  Prior QA knowledge was silently discarded on every new run directory.

### feat: default gov ZIPs + --buildzip/--deployzip flags

- Both governance ZIP paths are now baked in as defaults — no more typing them.
- `--buildzip` and `--deployzip` named flags override when needed.
- Intake file is the only required positional arg for a normal run.
- Should have been done on day 1.

### new: run_feature_build.sh — full feature-by-feature build pipeline

- New wrapper: `run_feature_build.sh` orchestrates the complete build sequence.
  1. Runs `phase_planner.py` to split intake into data layer + intelligence features.
  2. Builds Phase 1 (data layer, `--no-polish`).
  3. For each intelligence feature: runs `feature_adder.py` then `fo_test_harness.py`.
     - All but the last feature: `--no-polish`.
     - Last feature: full polish (README, .env, tests).
  4. Merges all ZIPs into final deliverable.
- Default 20 iterations per phase/feature.
- On any failure: lists all prior ZIPs built + resume instructions.
- Chains feature_adder: each feature's ZIP becomes `--manifest` for the next.

### new: feature_adder.py — single-feature incremental build tool

- Reads original intake + prior run ZIP manifest.
- Produces a tightly-scoped intake for ONE feature with do-not-regenerate list.
- Classifies feature as DATA_LAYER or INTELLIGENCE_LAYER.
- Includes KPIs only for intelligence-layer features.
- Stamps `startup_idea_id` with feature slug for unique run dir/ZIP naming.
- Prints chained run commands for sequential feature builds.
- Usage: `python feature_adder.py --intake <file> --manifest <zip> --feature "<name>"`

### fix: phase_planner falls back to combined_task_list format

- Some intakes store features as `pass_4.combined_task_list` tasks (e.g. wynwood)
  instead of `Q4_must_have_features`. phase_planner now extracts build-classified
  tasks as features when the standard FEATURE_KEYS scan returns empty.

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
