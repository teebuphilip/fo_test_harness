# Learnings From AF to FO

## Latest Learnings (2026-03-08, session 10)

- When a targeted fix prompt doesn't include the current file content, Claude reconstructs from memory
  and introduces new errors even when trying to make a minimal change. 12+ iterations of static churn
  on the AWI build were caused entirely by integration fix prompts that asked Claude to "add a column to
  Assessment.py" without showing it what the file currently contained. Claude rewrote the whole file,
  getting the Base import wrong each time. The fix: always pass current file text when doing surgical
  patches. Without it, Claude invents the file and makes mistakes on boilerplate patterns.
- Model field additions are the riskiest type of prompt for static gate stability. Adding a SQLAlchemy
  Column to a model causes Claude to regenerate the entire class, which means every existing import,
  `__tablename__`, and inheritance line is at risk of mutation. Hard-prohibiting those specific elements
  in the prompt (not just "don't change other files") is essential — and showing Claude the exact current
  file removes the need to guess.
- Integration issues (missing model fields, missing libraries, missing KPI methods) are structurally
  different from static issues (wrong imports, duplicate tablenames) and should not share the same fix
  prompt or defect_source. They need their own route so their fix doesn't collide with the static gate.
- Consistency fixes have the same need as integration fixes: current file contents in the prompt.
  Without them, Claude rewrites service/model files from memory and drops existing methods — turning
  a 1-issue consistency fix into 6 new static defects.
- There is no defect type for which showing Claude the current file content is wrong. The boilerplate
  reference (which import to use, which Base class) is already in the governance section — that covers
  pattern guidance. The file content covers method/field preservation. ALL targeted patch types need both.
  The final correct split: ALL non-QA sources → surgical (file contents); feature QA → full build prompt.

## Latest Learnings (2026-03-08, session 9)

- Railway's GraphQL `variableUpsert` mutation requires a real `environmentId` — passing null
  causes it to try resolving via GitHub repo URL, which fails on private repos. Always store
  the environment_id in `railway.deploy.json` after first deploy and read it back. Don't rely
  on the API lookup — it silently fails for many account types.
- Vercel returns 400 (not 409) for duplicate env var POSTs on newer API versions. The
  set_env_var method must upsert: GET existing ID on 400/409, then PATCH. A simple 409
  skip is not enough.
- The right deploy sequence for a new app is: Auth0 setup → Railway (with Auth0 vars) →
  Vercel → patch Railway CORS with Vercel URL → patch Auth0 callbacks with Vercel URL.
  All of this can and should be automated in the pipeline — any step left manual will be forgotten.
- "Repository not found or not accessible" in Railway is a GitHub App permission issue, not
  a code or token issue. Railway's GitHub App must be explicitly granted access to each repo
  via GitHub Settings → Applications → Railway → Configure. This can be done via GitHub API:
  `PUT /user/installations/{installation_id}/repositories/{repo_id}`. Run repo_setup.py once
  per new repo before pipeline_deploy, otherwise Railway cannot pull code OR set env vars.
- When Railway GraphQL API is unauthorized for env var setting, the CLI (`railway variables --set`)
  works fine with the same `RAILWAY_TOKEN` env var. Always check if the CLI is installed before
  giving up on programmatic var setting. The CLI is installed by default in most Node environments
  and respects RAILWAY_TOKEN without any browser login.
- Railway's `variableUpsert` GraphQL mutation validates GitHub repo access even though
  setting env vars has nothing to do with GitHub. This causes "Repository not accessible"
  errors for tokens that can deploy but don't have GitHub integration permissions. The
  `variableCollectionUpsert` bulk mutation bypasses this check. Always try bulk first.
- Railway env vars set via API do NOT immediately trigger a redeploy in all account types.
  Setting CORS_ORIGINS after Vercel is up is safe but may require a manual redeploy in Railway
  dashboard to take effect if the service doesn't auto-restart on var changes.

## Latest Learnings (2026-03-08, session 8)

- Vercel silently sets `CI=true` for all builds. With `react-scripts` (CRA), this promotes
  every ESLint warning to a hard build error. The boilerplate itself has pre-existing lint
  warnings (unused vars, exhaustive-deps) that were never caught locally — they only surface
  on first Vercel deploy. Always inject `CI=false` as a project env var in the Vercel deploy
  step so builds don't fail on lint noise. Vite-based projects are not affected.

## Latest Learnings (2026-03-07, session 7)

- Whitelist entries can be as harmful as missing prune rules. BOILERPLATE_VALID_PATHS
  explicitly said tailwind/next/postcss configs under business/frontend/ were "valid to keep."
  This meant Claude could generate broken config files, static Check 8 would flag them every
  iteration, but the pruner would never remove them — infinite static loop. The whitelist
  comment even said "Claude-generated, valid to keep" which was wrong.
- Dashboard/styled features reliably trigger boilerplate config generation. Any feature
  with "dashboard", "charts", "custom styling", or "theme" in scope will cause Claude to
  generate tailwind.config.js. The right fix is pruner-level, not prompt-only — Claude
  will always try, so the harness must silently drop these files before they reach static check.

## Latest Learnings (2026-03-07, session 6)

- Language-specific regex in extraction code silently discards output. The test generation
  regex only matched JS/TS fences — Claude always generates Python tests with ```python.
  Result: 62s Claude call, $0.09 spent, 0 files saved, no error raised. Always use `(?:\w+)?`
  for language fence matching rather than enumerating specific languages.

## Latest Learnings (2026-03-07, session 5)

- Patch iterations are being billed at full-build token rates. Static/consistency/quality
  fix iterations output 1-3 files but were capped at 16384 tokens — same as a full 20-file
  initial build. The right token budget for a patch is 8192: plenty for any single file,
  never causes truncation on the narrow output, halves the per-iter output cost.
- Every sub-loop needs both a token budget AND an iteration cap. The static loop got both
  (Fix 3 + 8192 tokens). Consistency was identical in structure but had neither — meaning
  a consistency deadlock burned full-price iterations indefinitely. Pattern: whenever you
  add a new sub-loop gate, immediately add MAX_X_CONSECUTIVE and PATCH token sizing.
- Cost is dominated by Claude output tokens on fix iterations, not API call overhead.
  GPT quality + QA calls are negligible (<$0.01 each). The $10+ runs came entirely from
  30 × $0.25 Claude output charges. Reducing output tokens and capping iteration counts
  is the only lever that moves the number.

## Latest Learnings (2026-03-07, session 4)

- Claude will output backend-only builds and call them complete when the token budget
  runs out before frontend pages. "COMPLETED_CLOSED" in the output does NOT mean all
  required files were generated — it just means Claude stopped producing output.
- The QA filter can mask a skeleton build. When Claude outputs no frontend pages, QA
  hallucinates defects about `.jsx` files that don't exist, the harness removes them as
  fabricated evidence, and flips the verdict to ACCEPTED. A clean QA report ≠ complete build.
- Shopify integration confuses Claude about frontend responsibility. Claude interprets
  "Shopify integration = Shopify handles the storefront" and skips the React dashboard
  pages entirely. The prompt must explicitly say "Shopify is the store, the React
  boilerplate dashboard still needs .jsx pages for admin/member features."
- Static checks are the right gate for structural completeness. A deterministic check
  (routes exist but zero .jsx files → HIGH defect) will always fire before QA gets
  a chance to hallucinate. Never rely on ChatGPT to detect missing file categories.

## Latest Learnings (2026-03-07, session 3)

- Static check infinite loops are the dominant cost driver. Root cause: route calls
  `calculate_score()` but service defines `calculate_assessment_score()`. Claude fixes
  arity but not the method name because the targeted patch prompt only shows the route
  file — it never sees the service file's actual method names. The fix is simple:
  include the service file in the target list whenever a missing-method defect fires.
- Method-name mismatches cannot be fixed by single-file patches. The route and its
  service are a coupled interface — both must be regenerated together in one shot for
  names to align. Targeted single-file static fix is the wrong tool for contract mismatches.
- A fallthrough to Feature QA after N static iterations breaks cross-file deadlocks.
  Feature QA with the full artifact set sees BOTH sides of the interface and can
  describe the mismatch coherently. A full QA-driven rebuild prompt resolves what 6
  targeted patches could not.
- Hard caps on any sub-loop are necessary. Any loop that can iterate independently of
  the main max-iterations counter will hit the overall limit without any user control.
  Every sub-loop needs its own explicit ceiling.

## Latest Learnings (2026-03-07, session 2)

- QA prohibition knowledge must chain across feature builds. The warm-start tracker
  is per-run-directory by default — switching to a new feature run silently resets it.
  In a 5-phase feature pipeline, Phase 1's 17 iterations of learning what Claude gets
  wrong are completely discarded for Feature 1's run. --prior-run solves this.
- Default CLI args should be established on day 1. Typing 200-character gov ZIP paths
  for every run is friction that accumulates across hundreds of runs. Any path that
  never changes belongs in a default, not on the command line.

## Latest Learnings (2026-03-07)

- Feature-by-feature is the right default for intelligence-heavy projects. The 2-phase
  split (data vs intelligence) is still useful as a planning tool, but the intelligence
  layer should be built one feature at a time to keep Claude's coherence ceiling from being
  exceeded. Each feature run is 3-7 iterations; a 4-intel-feature project is 4 × 7 = 28
  max vs 1 × 30 that fails. Same cost ceiling, much higher success rate.
- Not every project needs the phased pipeline. Wynwood (member portal, payments, content)
  is pure DATA_LAYER with 0 KPIs — straight harness run is correct. The pipeline adds
  overhead with no benefit when there are no intelligence features to sequence.
- Intake format normalization is an ongoing problem. `Q4_must_have_features` vs
  `combined_task_list` are two known formats; others likely exist. Phase_planner and
  feature_adder need progressive fallback detection, not hard-coded key assumptions.
- npm install is required before any frontend build check. Generated artifacts never
  have node_modules — every frontend compile check will fail without it. This is a
  universal harness requirement, not project-specific.

## Latest Learnings (2026-03-06, session 3)

- Post-QA polish must be suppressed for intermediate phases. Running README/.env/test
  generation after Phase 1 (data layer) wastes tokens and produces incomplete docs
  that will be regenerated or overwritten after Phase 2. `--no-polish` flag addresses this.
- Phased build ZIP merge is safe: Phase 2 intake `_phase_context` block instructs Claude
  to generate only intelligence-layer files, so Phase 1 and Phase 2 artifact sets are
  naturally disjoint. Phase 2 overwrites on top as a safety net — no manual conflict resolution.
- Wrapper scripts are the right abstraction for multi-step harness workflows. A bash wrapper
  that sequences two harness invocations and merges artifacts is simpler and more debuggable
  than embedding phase logic inside the harness itself.

## Latest Learnings (2026-03-06, session 2)

- Static checks with false positives are worse than no static checks. CHECK 10 (constructor
  arity) created an infinite static-fix loop on AWI by flagging valid SQLAlchemy ORM
  instantiation. Every new deterministic check must be validated against known-good artifacts
  before deployment — a false positive HIGH blocks every iteration indefinitely.
- SQLAlchemy ORM classes must be excluded from constructor arity and method-existence checks.
  The metaclass generates `__init__(self, **kwargs)` automatically; source showing no explicit
  `__init__` does not imply arity 0.
- Single-shot generation has a complexity ceiling. Projects with 8+ features and cross-cutting
  intelligence layers (KPI calc → scoring → report generation → analytics) exceed reliable
  first-pass coherence. The right fix is phased builds, not more iterations.
- The DATA_LAYER / INTELLIGENCE_LAYER split is a natural architectural boundary in most SaaS
  projects: data collection is always Phase 1, computed intelligence always Phase 2. This
  maps directly to how human devs scope sprints.
- Projects that converged reliably (adversarial_ai_validator, wynwood_thoroughbreds,
  property_manager_maintenance_scheduler, freelance_invoice_tracker) all had ≤5 features
  with no cross-service computation. That is the empirical 1-phase ceiling.
- Conservative threshold (3) is correct default. 2 phases × 3 iterations = 6 total is
  always preferable to 1 phase × 30 iterations that fails. Extra setup cost is negligible.
- The harness is not broken — it is calibrated for a complexity level AWI exceeds. The
  answer is a planning layer (phase_planner.py) upstream, not deeper iteration limits.

## Latest Learnings (2026-03-06)
- Comment-only QA evidence needs scope-language gating. A blanket "comment-only = ignore" rule hides real misses.
- Deterministic static checks should validate role contracts, not just syntax:
  - models must be models (no routers)
  - routes/services must match constructor+method contracts
  - imports must resolve with symbol existence and case-sensitive filenames.
- Frontend config sanity checks catch high-frequency broken artifact swaps quickly with zero AI cost.
- Intake-aware static checks close a major gap:
  - KPI definitions in intake must map to implemented KPI logic
  - "downloadable report" must map to explicit export/download capability.
- Gate telemetry is required for operator trust: always log which gates ran/skipped and why.
- Final consistency-on-terminal-failure gives actionable post-mortem defects instead of silent exits.
- Post-QA polish is a good insertion point for testcase documentation generation:
  - the system already has intake + final manifest + final build context
  - ChatGPT can generate a complete testcase doc from a directive template
  - keeping the directive external (template file) makes testcase policy easy to evolve across startups.
- For API-heavy apps, include a Postman conversion section in the same directive:
  - this gives a direct path from testcase doc -> collection/newman execution
  - complements Playwright (UI/E2E) with API contract automation.
- A fourth quality gate is useful as an operator control, but should be optional by default.
- Using a LOW-accept policy on high-signal dimensions (completeness, code quality, deployability)
  reduces false blocks while still surfacing quality debt for follow-up.

## What Broke Most Often
- Large lowcode outputs hit token limits and dropped required files.
- Multipart metadata from model can be inconsistent (e.g., declares final part while still truncated).
- Required files missing from manifest caused pre-QA skip loops.
- Path drift occurred under pressure (e.g., `business/frontend/package.json` vs `business/package.json`).

## What Improved Reliability
- Treat build process as stateful in harness (manifest-driven), not in model memory.
- Patch-first recovery before full regenerate reduces drift and cost.
- Carry forward prior required file inventory to defect iterations.
- Force continuation recovery whenever output remains truncated (even after multipart).
- Normalize known path drifts before validation.
- Keep pre-QA strict only for true blockers; move non-blockers to post-QA polish.

## Prompt/Contract Learnings
- Directory contract must match runtime loader contract exactly.
- Defect iterations need explicit file inventory lock + targeted edit scope.
- Required outputs must be enforced with both:
  - prompt contract
  - harness validation + automatic recovery

## Process Learnings
- Add CLI overrides for operational pressure points (iterations, parts, continuations, boilerplate path).
- Keep safety defaults aligned to governance, with explicit runtime overrides when needed.
- Always refresh manifest after any out-of-band file mutation (e.g., patch writes).

## QA Convergence Learnings
- QA correctly identifies defects but defect descriptions alone are insufficient for convergence.
  "Use database-backed storage" is accurate but does not tell Claude which ORM, import, or pattern to use.
  Defects must include a `Fix:` field with the exact change — not just the expected outcome.
- Claude reads defects and acts on them literally. If the defect says "use DB", Claude adds a comment
  saying "replace with DB later" and keeps the dict. The fix instruction must say "remove the dict, period".
- Mock/in-memory storage is Claude's default fallback when uncertain about the boilerplate DB interface.
  Prohibiting it explicitly (not just prescribing the alternative) breaks this pattern.
- Defect enrichment at injection time is more reliable than expecting QA to always produce perfect Fix: fields.
  Harness-side detection of known bad patterns (dict storage, sequential IDs, hardcoded data) allows
  prepending targeted architectural guidance before Claude sees the defect list.
- **Framework mismatch is the deepest root cause of in-memory storage persistence.**
  Claude defaults to Flask (Blueprint, request, jsonify) for Python backend routes. The boilerplate is
  FastAPI (APIRouter, Depends). Flask has no `Depends(get_db)` — so Claude cannot use the boilerplate
  DB layer at all and falls back to in-memory storage regardless of how many times the prohibition is stated.
  Fix: inject the exact FastAPI+SQLAlchemy import paths and CRUD pattern so Claude has a concrete template.
  The prompt must say "NEVER use Flask" explicitly — prohibition + reference pattern together.
- A "write a TODO comment if unsure" fallback is counterproductive. It gives Claude permission to defer
  DB implementation, which QA then flags every iteration. Remove fallback; provide the reference instead.

- **Claude needs the exact import + function signature to use a boilerplate module — not a description.**
  Listing "Authentication ✅" tells Claude nothing. It needs: `from core.rbac import get_current_user`,
  the return shape `{"sub": ..., "tenant_id": ...}`, and an example route. Same for every capability.
  The 44-capability reference in `build_boilerplate_capabilities.md` gives Claude exactly what it needs
  to select and integrate the right modules for each intake without rebuilding anything from scratch.
- **Listing what the boilerplate provides is not enough — Claude needs the exact import path.**
  `FO_BOILERPLATE_INTEGRATION_RULES.txt` says "Authentication ✅" but Claude still hardcodes user IDs
  because it doesn't know that `from core.rbac import get_current_user` exists. High-level descriptions
  of what the boilerplate provides have zero effect unless the exact module, import path, and usage
  pattern are in the prompt. Same applies to tenancy, posting, etc.
- **Missing code fences in patch iterations cause silent extraction failure.**
  Claude outputs file content as raw text after `**FILE:**` headers in patch/defect iterations — no code
  fences. ArtifactManager only extracts files within triple-backtick fences. The PATCH_FIRST prompt said
  "every code block must have **FILE:** header" but never said "every file must be in a code block".
  Claude satisfied both rules separately, producing raw text files that were invisible to the extractor.
  Fix: patch prompt must say "wrap every file in ```language...``` fences; never output raw file content".
- **Vague auth context fixes defer the problem instead of solving it.**
  "Get consultant_id from auth context" causes Claude to write `// TODO: Get from auth context` — which
  QA catches again next iteration. The fix must name the exact import and usage:
  `import { useAuth0 } from '@auth0/auth0-react'; const { user } = useAuth0(); consultant_id: user?.sub`.

- **Collateral regeneration is the primary cause of defect count explosions in late iterations.**
  Claude doesn't have previous file content in the prompt — only file paths. When told to output all files
  with only the defects changed, it regenerates non-defect files from memory → drift → regression.
  1 defect can become 6 defects in a single iteration this way.
  Fix requires three parts: (1) prompt change so Claude only outputs defect files, (2) harness merge-forward
  to copy unchanged files from previous iteration, (3) synthetic QA input built from merged artifact set
  so QA evaluates the complete picture. Changing the prompt alone is insufficient — the harness must fill in
  the non-defect files or QA will flag them as missing.

- **QA false positives on known-good boilerplate imports waste iterations.**
  QA hallucinated `from core.database import Base, get_db` as an incorrect import path — burning 2 iterations.
  Any import that is part of the boilerplate must be listed explicitly in the DO NOT FLAG section of qa_prompt.md.

- **QA needs to know correct boilerplate patterns, not just what the boilerplate provides.**
  Telling QA "the boilerplate has auth" doesn't prevent it from flagging `Depends(get_current_user)`
  as a defect. QA needs to see: "this import IS the auth — do not flag missing auth when it's present".
  The QA prompt must include the exact correct pattern for each capability, paired with explicit
  DO NOT FLAG / DO FLAG rules. Otherwise QA creates false defects that block convergence.

- **QA cannot detect missing frontend if it evaluates pruned files Claude generated in wrong paths.**
  If Claude generates `app/api/assessments.py` (pruned) but no `business/frontend/pages/*.jsx`, QA sees
  a seemingly complete build and accepts. The missing frontend is invisible because QA has no structural
  checklist — "verify required artifacts" is undefined without an explicit path-level requirement.
  Fix: add a REQUIRED STRUCTURE block to qa_prompt.md with explicit path patterns and severity levels.
  Also instruct QA to ignore files outside business/ entirely — not evaluate, not reference in defects.

- **Pruning only non-business files leaves junk accumulating inside business/.**
  business/tests/, business/backend/services/, business/backend/__init__.py, business/backend/app.py,
  business/app/routers.py all start with business/ so the prune step ignored them. Merge_forward then
  carried them into every subsequent iteration. Duplicate ScoringService in two locations persisted for
  12 iterations. Fix: whitelist-based second-pass pruning — only keep files matching the boilerplate
  contract (pages/*.jsx, routes/*.py, models/*.py, services/*.py, README-INTEGRATION.md, package.json).
  Both pruning and merge_forward must use the same whitelist for consistency.

- **Blocking one wrong path causes Claude to invent another wrong path.**
  Prohibiting root-level `app/` caused Claude to generate `business/frontend/app/` (Next.js app router)
  with `.tsx` extensions instead of `.jsx`. Each prohibition must include all known variants.
  The boilerplate uses pages router — `business/frontend/pages/*.jsx` is the only valid frontend path.
  Prohibitions must name the exact wrong paths with ← FORBIDDEN annotations and the correct equivalent.

- **Claude hedges by generating code in BOTH the correct path and familiar wrong paths.**
  Even when the prompt says "output only under `business/**`", Claude generates correct `business/backend/routes/`
  files AND duplicate logic under `app/api/`, `app/core/`, `tests/`. The harness pruner silently discards the
  wrong-path files — but they contained real logic, wasting iterations and tokens.
  Fix: explicitly name the forbidden paths (`app/`, `tests/`, `src/`, etc.) in HARD FAIL CONDITIONS and
  INVALID EXAMPLES with ← FORBIDDEN annotations and the correct equivalent path. Vague "only business/" is
  insufficient — Claude needs to see the exact wrong paths it tends to produce.

- **Per-capability DO NOT FLAG rules are whack-a-mole — the fix must be structural.**
  Each new capability in the boilerplate will produce the same class of hallucination: QA reads
  a "flag this" rule, sees something related in the code, and fires the defect without verifying.
  The correct fix is a single universal rule: "quote the exact offending line verbatim before writing
  any defect — if you cannot quote it, you cannot write it." This one rule prevents all future
  per-capability hallucinations. Also: "any import from core.* or lib.*_lib = correctly integrated,
  do not flag as missing or broken." These two structural rules make per-capability DO NOT FLAG entries
  mostly unnecessary.

- **A "flag this pattern" rule in the QA prompt causes hallucinated defects when the pattern isn't present.**
  The Auth0 BUG TO FLAG section instructed QA to flag `user.getAccessTokenSilently()`. ChatGPT read this
  rule, saw `useAuth0` anywhere in the code, and reported the defect without verifying the wrong pattern was present.
  Home.jsx had CORRECT code (`const { user, isLoading, getAccessTokenSilently } = useAuth0()`) from iteration 4.
  QA still flagged it as broken for 9 straight iterations — consuming the entire iteration budget on phantom bugs.
  Fix: every "flag this pattern" rule must include a VERIFICATION REQUIREMENT: quote the exact wrong line verbatim
  before writing the defect. If you cannot quote it, you cannot flag it. This forces ChatGPT to actually read
  the code rather than pattern-match on the rule description.
  General rule: any QA instruction that says "flag X" must have a corresponding "ONLY if you see literal X in output".

- **SQLAlchemy ORM query chains look like "inline SQL" to an LLM without explicit guidance.**
  `tenant_db.query(Model).filter(Model.column == value).all()` is correct SQLAlchemy ORM.
  QA flagged it as "inline SQL without ORM abstraction" because it sees `.filter()` calls and infers raw SQL.
  Fix: add to DO NOT FLAG in qa_prompt.md: `.query().filter().all()`, `.query().filter().first()` are ORM.
  "Inline SQL" only means raw SQL strings: `db.execute("SELECT * FROM ...")`.

- **Absence-of-pattern rules invert in QA output.**
  "Do NOT flag .tsx unless you see a .tsx header" caused QA to flag "Missing .tsx reference that confirms .jsx usage" —
  the absence of .tsx became a defect about the absence of .tsx. Rules about what NOT to flag should always be
  written as positive confirmations: "If all frontend files are .jsx — this is CORRECT."

- **Partial capability coverage causes the same recurring bugs as no coverage.**
  Having 20 of 44 capabilities in the build directive means the 24 missing ones will always be
  hallucinated or reimplemented from scratch. The Auth0 `user.getAccessTokenSilently()` bug is
  an example: the frontend Auth0 pattern was absent from the directive → Claude inferred it from
  the backend-only pattern → wrong. Every capability the boilerplate provides must be in the directive
  with exact import path + working code sample — especially frontend hooks and components.
  Missing infrastructure modules (data_retention, monitoring, webhook_entitlements) lead to Claude
  inventing its own GDPR deletion, error tracking, and Stripe webhook handlers — all incorrect.
  Fix: enumerate ALL capabilities in `build_boilerplate_capabilities.md` with exact code patterns:
  backend core, shared libs, AND frontend hooks/components. Include anti-patterns (WRONG examples)
  for any capability that has a known hallucination tendency (like Auth0 token access).

- **Wrong-path files must be remapped, not deleted.**
  When Claude generates app/api/foo.py with no business/backend/routes/foo.py equivalent,
  deleting the wrong-path file permanently loses the only copy of that logic.
  Fix: check for a valid-path equivalent first. If it exists → prune the duplicate.
  If not → rename/move to the correct business/ path.

- **QA "Evidence:" field forces honest defect reporting.**
  Requiring QA to paste the exact wrong line verbatim before writing a defect prevents
  fabrication. If QA can't paste it, it can't write the defect. Advisory "quote it or
  drop it" rules are ignored — the field must be part of the required output format.

- **The word "hypothetical" in a defect location = fabricated. Ban it explicitly.**
  QA wrote `(hypothetical for reference)` in the Location field — admitting the defect
  was invented. Adding an ABSOLUTE RULES block that forbids this word closes the loophole.

- **OpenAI's Retry-After header must be obeyed, not ignored.**
  Flat retry delays ignore what OpenAI explicitly tells you to wait. Read the header;
  use it when present. Fall back to exponential backoff + jitter when absent.

- **Resume mode must set the loop start iteration explicitly, not just the skip condition.**
  qa resume mode checked `iteration == _ws_iteration` to skip Claude BUILD, but never set
  `iteration = _ws_iteration` before the loop. Loop started at 1, called Claude on iter 1,
  then would have skipped BUILD on iter 2. Fix: set iteration = _ws_iteration before the
  while loop, same pattern fix mode already used (iteration = _ws_iteration + 1).

- **TPM quota resets per minute — a 120s pause before iteration 2+ QA prevents 429 storms.**
  Claude fix calls complete in <60s. Without a deliberate pause, the next QA call fires
  before the previous call's token window has cleared. Two minutes of patience eliminates
  the most common 429 failure mode in multi-iteration runs.

- **Persistent 429s after 120s+ waits are not TPM — log the error body and rate-limit headers.**
  If retrying every 2 minutes still hits 429, the limit is RPM (requests per minute), daily
  token quota, or an org-level spend cap — none of which reset in under a minute.
  The OpenAI 429 response body contains `error.type` and `error.message` that name the exact
  limit. The `x-ratelimit-reset-requests` / `x-ratelimit-reset-tokens` headers give the exact
  UTC reset time. Without logging these, you're guessing. Same applies to Anthropic:
  `anthropic-ratelimit-*` headers carry the same information.
  Fix: always dump error body + all rate-limit headers on every transient error (429/500/529)
  for both Claude and ChatGPT clients.

- **A QA prompt larger than the model's TPM limit will never succeed — switch models, don't retry.**
  gpt-4o has a 30k TPM limit on lower org tiers. A QA prompt with a large build output is
  ~33k tokens. No amount of waiting clears a per-minute window when the single request exceeds
  the limit. The error message says exactly this: "Request too large... Limit 30000, Requested 33160."
  Fix: use gpt-4o-mini which has 200k TPM on the same tier and is sufficient for structured
  QA validation. Add a --gpt-model CLI flag so the model can be swapped without code changes.

- **QA flags intentional test behaviour as bugs — the test file rule must say what counts as a bug.**
  A test that sends invalid JSON is testing error handling, not broken. QA needs explicit guidance:
  only flag literal bugs in the test code itself (wrong assertion, broken import, syntax error).
  Never flag a test for what it intentionally exercises. Never flag missing test coverage for
  a specific route/model unless the intake spec explicitly required it.

- **Absence-of-thing defects waste iterations — ban them unless the spec required the thing.**
  "Missing docstring on /reports endpoint" and "missing test cases for clients.py" are not
  defects if the intake spec never asked for them. QA invents these because it sees a route
  and reasons backwards to what should accompany it. The Evidence rule already blocks these
  in theory (you can't quote a missing line), but an explicit ban is needed in practice.

- **A whitelist pruner on business/ is whack-a-mole — use remap + merge_forward gate instead.**
  Every run produced new legitimate files not on the whitelist. The right design:
  Pass 1 remaps non-business wrong-path files. Pass 2 remaps wrong-location business/ files
  and prunes only exact duplicates. Anything unmappable stays for QA to evaluate.
  merge_forward gates on the whitelist so unmapped files don't carry forward between iterations.
  QA is the right place to catch structural problems, not a pruner that guesses what's valid.

  | What happens now                              | Why                                      |
  |-----------------------------------------------|------------------------------------------|
  | Non-business file with a remap                | Moved to canonical path                  |
  | Non-business file, no remap                   | Deleted (truly outside the project)      |
  | business/ file with a remap                   | Moved to canonical path                  |
  | business/ file that's a duplicate             | Deleted (canonical version exists)       |
  | business/ file, no remap, not duplicate       | Left in place for QA                     |
  | Any file in merge_forward not on whitelist    | Not carried forward (no accumulation)    |

- **Pruning tests before QA creates a self-defeating loop: delete tests → QA flags missing tests → regen tests → repeat.**
  Tests are not runtime artifacts but QA needs to see them to validate the build, and the
  founder needs them in the project handoff ZIP for local dev and CI/CD.
  The right split: tests survive pruner (QA-visible), excluded from merge_forward (no accumulation
  across iterations), included in ZIP (full project handoff). Two gates, not three.

- **Pass 1 and Pass 2 remap logic must be kept in sync — any marker in Pass 1 must also appear in Pass 2.**
  Pass 1 (`_remap_to_valid_path`) checked `(api, routers, routes)` for route files.
  Pass 2 (`_remap_business_path`) only checked `api` and `routes` — missing `routers`.
  `business/backend/app/routers/*.py` files fell through to `None` and were pruned.
  Also: a guard like `if 'app' in parts` that's not in Pass 1 creates silent gaps —
  `business/backend/models/` (no `app` in path) wouldn't remap without it.
  Rule: Pass 2 remap conditions must be a superset of Pass 1 conditions, not a subset.

- **Claude nests correct logic inside wrong intermediate directories — remap rules must handle full path depth.**
  `business/backend/app/models/assessment.py` is correct logic in the wrong location.
  A remap rule that only checks `'api' in parts` misses `business/backend/app/models/`.
  Every subdirectory pattern Claude generates needs an explicit rule: models/, schemas/,
  services/, api/ under business/backend/app/ all need separate remap targets.

- **The pruner whitelist must cover every file type Claude legitimately generates — not just the happy path.**
  Pydantic schemas (business/schemas/*.py), FastAPI entry point (business/backend/main.py),
  and frontend components (business/frontend/components/) are all real output that belongs in the build.
  A whitelist that only lists pages/*.jsx and routes/*.py silently discards an entire layer of the app.
  The remap logic must also handle .js files, not just .jsx/.tsx — Claude generates both.
  frontend/app/*.js, frontend/components/*.js, and frontend root config files (package.json,
  next.config.js) all need explicit remap rules in _remap_to_valid_path (Pass 1).

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

- **Pruner whitelist must include frontend config files, not just page/route source files.**
  next.config.js, postcss.config.js, tailwind.config.ts, package.json are required for the
  frontend to build and run. They are not junk. A whitelist that only lists pages/*.jsx and
  routes/*.py silently deletes the entire Next.js config layer every iteration.
  Fix: add all known frontend config/infrastructure paths to BOILERPLATE_VALID_PATHS.
  Also: business/frontend/app/ (App Router) files must be remapped to pages/ (Pages Router),
  not deleted — same salvage-or-prune logic used for non-business wrong-path files in Pass 1.

## Bottom Line
- Reliability came from harness-side deterministic controls, not expecting model session continuity.
- QA convergence requires both: specific defect descriptions (Fix: field) AND upfront prohibitions
  that prevent the failure pattern from appearing in the first place.
- Full capability coverage (not partial) is required — missing capabilities = recurring unfixable bugs.
