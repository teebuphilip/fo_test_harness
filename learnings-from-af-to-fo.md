# Learnings From AF to FO

## Latest Learnings (2026-03-22 session 15 — config shape fix)

- Config generators must match the exact types that boilerplate JSX pages expect. Home.jsx renders `{home.hero.cta_primary}` as raw JSX text — if the value is an object (`{label, href}`) instead of a string, React crashes with "[object Object]" or a blank screen. Every config key must be audited against the page that consumes it: JSX `{value}` = string, `{value.label}` = object.

- Boilerplate components that accept config values as props must handle the data type they actually receive. FeatureCard rendered `{icon}` as raw text with no icon library — string icon names like `"star"` appeared literally on screen. If a component is supposed to show icons, it needs either (a) an icon library + lookup map, or (b) the config must provide something that renders visually in raw text (emoji). We chose (a) with lucide-react + a string→component map, with emoji fallback for backward compat.

- Config icon assignment should be contextual, not generic. A rotating fallback set (`star`, `rocket`, `chart`...) looks placeholder-ish. Keyword matching against feature/page names produces much better results (e.g. "Horse Profiles" → horse icon, "Email Subscribers" → mail icon) with zero AI cost.

---

## Latest Learnings (2026-03-20 session 14 — business_config + pipeline logging)

- `business_config.json` must be generated AFTER the final merge, not during individual harness runs. Individual runs use `--no-polish` which skips config generation, and even when polish runs, the harness only sees its own feature's pages — not the full set across all entities/features. Only the merged artifact tree has the complete picture.

- The harness-internal `_generate_business_config()` derived nav items and footer links from intake feature names, not from actual built `.jsx` pages. This produced generic `/dashboard` links instead of real routes like `/dashboard/horse-profiles`. Config generation must inspect the artifact tree to be accurate.

- The boilerplate reads `business_config.json` from `frontend/src/config/` (imported by `useConfig.js`), not from `business/frontend/config/` (the harness convention). Config must be written to both paths — the harness path for builds and the deployed path for the running app. Missing either causes blank screens (frontend) or startup crashes (backend).

- Pipeline scripts that orchestrate multi-step builds need persistent logs. When a build fails at step 7 of 12, the terminal scrollback is already gone. Timestamped log files in a dedicated directory (`riaf-logs/`) make post-mortem trivial.

---

## Latest Learnings (2026-03-20 session 13 — deploy pipeline hardening)

- Railway GitHub repo linking should use the dedicated `serviceConnect` path, not a generic service update mutation. Once that was corrected and the repo input was normalized to `owner/repo`, automated backend deploys started working reliably again.

- A successful Railway deploy and a discoverable public URL are separate states. The deploy worker needs to report those separately, otherwise a healthy backend looks like a failed deploy just because the URL or domain lookup lags behind.

- Domain generation should be part of the backend deploy worker. Reusing an existing Railway public domain when present, and generating one only when missing, prevents repeated manual GUI work and stops domain sprawl on repeated deploys.

- `pipeline_deploy.py` needs its own persistent run logs. In a directory with many overlapping scripts, timestamped logs are the only sane way to reconstruct what happened during a long deploy and to separate Railway failures from Vercel failures from app-code failures.

- CRA-on-Vercel will still fail builds on lint warnings because Vercel sets `CI=true`. For this pipeline, deploy automation should force `CI=false` and `DISABLE_ESLINT_PLUGIN=true` for CRA builds rather than relying on humans to remember why a frontend failed on lint instead of code.

## Latest Learnings (2026-03-19 session 11 — ubiquitous language)

- Claude and ChatGPT drift from intake terminology during multi-iteration builds. Claude invents synonyms ("metric" instead of "KPI"), QA flags them as defects, Claude "fixes" by using yet another synonym. This burns 2-3 iterations per run on pure terminology churn.

- Locking terminology BEFORE planning (not during build) means the phase planner also uses canonical terms, so feature names stay consistent from planning through build through QA. The glossary is generated once and never changes.

- Deterministic synonym detection catches 80% of conflicts (known synonym groups). AI refinement adds entity relationships and ambiguity resolution but is optional — the pipeline works without it.

---

## Latest Learnings (2026-03-19 session 10 — slice planner + routing)

- A single phase-planner is insufficient for quality builds that need clear sequencing and acceptance criteria. Vertical slice plans make scope explicit (API + data + UI) and reduce ambiguity before build.
- AI-first slice planning is worth it for messy intakes, but a heuristic fallback is mandatory to keep the pipeline resilient when API keys are missing or calls fail.
- Auto-routing between slice vs phase planning should be driven by intake signals (feature count, integrations, analytics, multi-role, subjective UX). This keeps factory mode lean without sacrificing quality-mode rigor.
- A slice pipeline should chain outputs via `--prior-run` to preserve accumulated state and avoid ZIP merge collisions; file-ownership constraints help keep slices isolated.

## Latest Learnings (2026-03-17 session 7 — AI decomposer + mini specs)

- Monolithic Phase 1 builds with the full intake cannot converge when the intake contains 10+ intelligence features. Claude reads the full spec and builds entities for features not yet in scope. QA flags them as out-of-scope. Claude removes them. Next iteration, it reads the spec again and re-adds them. This oscillation is structural — no prompt engineering can fix it because the information is in the context window.

- The fix is to remove future-phase information from the context window entirely. Each entity gets its own mini spec with only the fields and operations it needs. The mini spec is the single source of truth — Claude cannot hallucinate extra fields because the spec explicitly lists what's allowed and what's forbidden.

- AI (ChatGPT) is better than deterministic keyword extraction for entity decomposition because it understands semantic relationships. A keyword-based extractor finds "Horse" as an entity but misses that `stable_id` on Horse is a foreign key to Stable. The AI reads the full intake and produces dependency graphs that the deterministic validator then enforces.

- However, AI output cannot be trusted directly. The deterministic validator is essential: it catches `.tsx` extensions the AI prefers, hyphenated filenames, external integration IDs (stripe_id, auth0_id) that shouldn't be in Phase 1, and standard fields (id, created_at) that the AI includes but the harness adds automatically.

- Evidence requirements prevent hallucinated entities. If the AI must cite an intake phrase for every entity, it can't invent entities that aren't in the spec. This is more reliable than trying to filter phantom entities after the fact.

- Wave-based dependency ordering (independent entities first, then dependents) prevents missing-FK errors. If Horse depends on Stable, building Horse first means `stable_id = Column(Integer, ForeignKey('stables.id'))` references a table that doesn't exist yet. Building Stable first and chaining via `--prior-run` means the table is already in the artifact set.

- The mini spec approach has a QA alignment risk: if QA reads the full intake while the build reads only the mini spec, QA will flag missing future-phase items and recreate the oscillation. The QA prompt may need `_mini_spec` awareness to constrain its validation scope to only the current entity.

## Latest Learnings (2026-03-17 session 7 — consistency type false positives)

- The consistency AI does not understand that SQLAlchemy and Pydantic use different type systems that are nonetheless correctly aligned. `Column(String, nullable=True)` paired with `Optional[str] = None` is the correct mapping, but the AI sees "different" types and flags it as a mismatch. This produces consistency issues that can never be resolved because there's nothing to fix — the code is already correct. After 2 surgical failures, the triage escalates to SYSTEMIC, which passes 25+ files as context and invites Claude to make sweeping changes to correct code.

- The fix is an explicit type mapping table in the consistency prompt's DO NOT FLAG section. Every standard Column type is paired with its correct Pydantic equivalent. This is more effective than a general rule ("don't flag type alignment") because the AI needs concrete examples to override its pattern-matching instinct.

- Default value alignment (`Column(String(50), default="basic")` ↔ `Optional[str] = "basic"`) and nullable alignment (`nullable=True` ↔ `Optional[...]`) must be called out explicitly or the AI will flag them as "default conflicts" or "phantom fields."

## Latest Learnings (2026-03-17 session 7 — consistency oscillation)

- Consistency FIELD_MISMATCH defects require simultaneous fixes to both sides of the relationship. When the fix prompt only receives the primary file (the first file listed before `<->`), it patches that file's field name correctly, but the other file retains the old name. The next consistency check sees the mismatch in reverse and fires again. This oscillates for the full 4-cap before falling through to QA — wasting 4 iterations on what should be a 1-iteration fix. The fix is to extract all files from the `<->` relationship and pass them all to Claude in one surgical patch.

- `_parse_consistency_report()` storing only `file` (primary) and not `all_files` (both sides) was the structural gap. Rather than changing the parse structure, the fix was added as Fix 3 in the defect_target_files building block — minimally invasive and located where the target set is already being assembled.

## Latest Learnings (2026-03-17 session 7 — status column filter)

- QA instruction compliance for ABSOLUTE RULES is unreliable across model families and temperature settings. A rule written in all-caps at the top of a section will still be ignored if the model has strong prior associations between "extra database column" and "scope violation". The only reliable fix is a harness-level filter that enforces the rule deterministically — the harness sees the same evidence text QA produced and can reject the defect before it reaches Claude.

- The pattern "all backtick evidence snippets are infrastructure column definitions" is a precise enough signal that false positives from this filter are near-zero. A real scope violation would never cite only `status = Column(...)` as evidence; it would cite a business-logic field or a route.

- Duplicate defects (DEFECT-1/DEFECT-3 both citing Horse.py status, DEFECT-2/DEFECT-4 both citing Update.py status) are a QA output artifact when the model processes the same file twice through different lenses (IMPLEMENTATION_BUG vs SPEC_COMPLIANCE_ISSUE). The filter eliminates both the original and the duplicate since both hit Check 1d.

## Latest Learnings (2026-03-17 session 7 — hyphen filename bug)

- Python route files with hyphens (`stable-updates.py`) cannot be imported by Python's module system — hyphens are not valid in module names. Despite this, Claude will generate hyphenated filenames when the frontend calls `/api/stable-updates`, because the URL uses a hyphen. The fix has two sides: (1) FROZEN_ARCHITECTURAL_DECISIONS must prohibit hyphenated filenames and require underscore filenames with matching underscore URLs; (2) the integration check must normalize hyphens to underscores when matching URLs to route files, so that a hyphenated file doesn't produce a false INT-ROUTE positive that oscillates indefinitely.

- The integration check regex `\w+\.py$` is too strict — `\w` excludes hyphens, so any hyphenated file is silently dropped from the route inventory, which makes every fetch call targeting that endpoint appear as a missing route. This is a false positive that can never be resolved by Claude because the file exists but the check can't see it. Regex should be `[\w-]+\.py$` and stems should be normalized to underscores on both sides of the comparison.

## Latest Learnings (2026-03-17 session 7 — schema naming + pyc)

- Schema class naming ambiguity causes permanent static oscillation. When the golden example shows `ExampleCreate` but doesn't explicitly prohibit `ExampleCreateRequest`, Claude freely chooses the longer form. Routes then import one name, schemas define another. The static check fires the same 6 defects every iteration regardless of which side Claude fixes — fixing routes makes schemas wrong, fixing schemas makes routes wrong. The only fix is to make the naming convention non-negotiable in the frozen decisions block so both sides are generated consistently from iteration 1.

- Compiled bytecode files (`__pycache__/*.pyc`) appearing as QA defect locations are always fabrications — QA cannot read `.pyc` content. When triage classifies these as SYSTEMIC, it inflates the fix scope to a wide rebuild instead of the 1-3 surgical files that actually need changing. Filtering these before triage is the correct fix — they should never reach the strategy decision.

## Latest Learnings (2026-03-17 session 7 — status column cascade)

- A QA rule buried in the DO NOT FLAG list is not an absolute constraint — it is guidance that the model can and will ignore under certain conditions. Any rule whose violation triggers a multi-iteration cascade must be in ABSOLUTE RULES at the top of the section, not in a long bulleted list that the model reads opportunistically.

- Infrastructure fields (`status`, `created_at`, `updated_at`) must be protected at both ends: (1) QA must be absolutely prohibited from flagging them as scope creep, and (2) Claude must be told in the build prompt to always include them and never remove them. A single-sided fix (only QA rule, or only build rule) is insufficient — if QA flags and Claude complies, the model column disappears and every service that references it produces an AttributeError at runtime.

- The cascade pattern from a single infrastructure field false positive: QA flags column → Claude removes it from model → service still accesses the field → INTEGRATION_FAST fires on every subsequent iteration → each fix pass is surgical and doesn't touch the model → the service reference persists → loop. The fix must address both the QA false positive prevention and the build-time guarantee that Claude never removes these fields.

- `status`, `created_at`, and `updated_at` should be treated as part of the boilerplate model contract, not as application-specific fields. They are as fixed as `id` and `owner_id`. QA cannot have authority over them regardless of what the intake spec says.

## Latest Learnings (2026-03-17 session 7 — QA cross-file contracts)

- QA finds cross-file mismatches opportunistically when reading individual files. Opportunistic detection means a mismatch is only caught if it happens to be visible while reviewing the specific file in focus. A systematic contract checklist forces QA to actively verify each cross-file relationship regardless of whether it surfaces during per-file review — turning a probabilistic catch into a guaranteed check.

- The direction of evidence matters for cross-file contracts. For a route→service contract, QA must quote the call site (route) and confirm absence in the callee (service). Quoting only the call site proves the call exists but not that it's broken. Quoting only the callee proves the method is absent but not that it's referenced. Both sides are required to establish a real contract violation.

- QA's existing "no inference" rule must be explicitly preserved in contract checks. Contract 3 (service field access → model Column) is the most likely false positive source — a service may access `model.field` where `field` is a Python property or relationship, not a Column. The rule "read the actual definition, not the name" prevents QA from flagging legitimate ORM patterns.

- The DO NOT FLAG package list in qa_prompt.md must be sourced from the actual boilerplate requirements.txt. Using a generic or assumed list causes QA to incorrectly accept wrong imports (e.g. `from jose import jwt` when the boilerplate uses PyJWT) or incorrectly flag correct ones. The list drifted significantly: python-jose, passlib, celery, redis, boto3, aiohttp were listed as correct but are not installed; PyJWT, cryptography, meilisearch, social libs were missing.

## Latest Learnings (2026-03-17 session 7 — build prompt quality)

- Unconstrained generation is the root cause of most convergence failures, not model capability or QA gate design. When Claude makes micro-decisions about sync vs async, error response shape, auth pattern, and file structure on every build, the decisions drift from the boilerplate on every run. Locking all architectural decisions as frozen constraints before the feature spec eliminates this drift class entirely.

- Pattern cloning is more reliable than rule following. Five reference files showing exact import paths, decorator patterns, and data access patterns produce better structural conformance than equivalent paragraphs of written rules. Claude copies structure; it interprets rules. Rules leave room for "reasonable" deviations. Examples do not.

- The Pydantic schema layer is the most commonly missing reference file in build quality improvements. Route/service/model examples are standard. The schema file (BaseModel subclasses with `from_attributes = True` for ORM mode, Optional fields, correct response shape) is what bridges model columns to route response_model — omitting it leaves Claude to invent the schema shape, which diverges from the route and model on every build.

- File explosion increases QA surface area, import chain complexity, and integration failure rate proportionally. Claude's default behaviour is to create helper utilities, abstract base classes, and additional service files beyond what the spec requires. A hard constraint of 1 route/service/model/schema/page per feature with an explicit ban on helper/utility files reduces the defect count on first-pass builds.

- The seeded dependency baseline prevents two common first-pass errors: adding Python stdlib modules (uuid, os, json) to requirements.txt (caught by static check, but better to prevent) and re-adding packages already in the boilerplate (pydantic, sqlalchemy, stripe) with wrong version pins. The baseline must be sourced from the actual boilerplate requirements.txt — using a generic list risks listing packages that are not installed (e.g. python-jose was listed but the boilerplate uses PyJWT; passlib listed but not installed).

- Governance-section vs dynamic-section placement is a cost decision, not just an organisational one. Content that never changes between builds or iterations belongs in governance_section — Anthropic's prompt caching reuses it at ~10% of full input cost on iterations 2+. Frozen decisions, golden examples, and seeded dependencies are all static — injecting them into governance_section means a 300-line constant costs ~30 lines of tokens on every iteration after the first.

## Latest Learnings (2026-03-16 session 6 — CONSISTENCY escalation)

- Full-build escalation as a response to a persistent CONSISTENCY issue is strictly worse than falling through to QA. The full-build forces Claude to regenerate all files from memory without seeing the current artifact state, producing invented architectures and wrong-path files. The QA gate sees the actual artifacts and reports real defects. One stubborn hallucinated CONSISTENCY issue should never trigger a complete rebuild.

- CONSISTENCY issues with no files named (`N/A <-> N/A`) are structurally unverifiable. Cross-file consistency requires two specific files. If the AI cannot name them, it cannot have observed the mismatch. Filter immediately — these are always fabrications.

- The escalation path `surgical → wide surgical → full-build` creates a feedback loop: full-build generates fresh wrong-path files → PATCH_SET_COMPLETE fires → collateral files discarded → 10 files lost → next CONSISTENCY has even more missing imports → more issues → another escalation. The right path is always `surgical → wide surgical → fall through to QA`.

## Latest Learnings (2026-03-16 session 6 — CONSISTENCY filter)

- The CONSISTENCY filter has two opposing failure modes depending on issue type. For FIELD_MISMATCH, finding the evidence token in the file proves the AI hallucinated ("field is missing" when it's present). For BROKEN_IMPORT, finding the wrong import string in the file proves the defect is real ("wrong path" when the wrong path is there). Applying one filter direction to both issue types simultaneously filters real bugs and keeps hallucinations. The fix is to partition by issue type before applying the token-in-file test.

- Issue type metadata (`[DUPLICATE_SUBSYSTEM]`) appears only in the block header line, never in the Problem or Evidence text. Checking evidence + problem text for `DUPLICATE_SUBSYSTEM` always fails. The parser must extract the `[TYPE]` bracket from the header explicitly and store it as a separate field. Text-scanning the output for type names is fragile and unreliable.

- A filter that passes one class of hallucinations (DUPLICATE_SUBSYSTEM due to type-extraction bug) at 30+ iterations costs approximately the same token budget as 2-3 full QA passes. The filter needs to be comprehensive — every AI issue type the consistency AI can produce must be explicitly handled (either filtered or passed through), not left to fall through to the "keep" path.

## Latest Learnings (2026-03-16 session 6 — intake checks)

- A UI deliverable name is not a data specification. "Executive Dashboard" tells Claude to render a page. It does not tell Claude what data model backs it, what fields to persist, or what CRUD operations the page performs. Without that information Claude will generate a page + route + hollow service that returns `[]`. The page renders. The API responds 200. But the data is always empty. This is the AWI pattern.

- The correct fix is a two-layer defense: (1) catch it at intake time with PDR060 before the build runs — force the founder to name the entity, fields, and operations for every UI-named deliverable; (2) catch what slips through at build time with integration_check.py Checks 16 (hollow services) and 17 (orphaned pages).

- Intake-level detection is better than post-build detection because: fixing intake costs zero AI tokens, fixing post-build costs 2-4 extra fix iterations + integration check pass. The PDR060 rule fires before `run_integration_and_feature_build.sh` even starts. If the founder answers "the dashboard lists client assessments with fields: name, score, date — create and delete" then that information flows into the build prompt as a concrete spec, not as an ambiguous feature name.

- UI keyword matching on deliverable names is a reliable proxy for data-model requirement. Names containing "dashboard", "management", "tracker", "portal", "list", "board", "hub", "console", "monitor", "browser", "manager", "viewer", "explorer" almost always imply a database table. Names containing "login", "home page", "sidebar", "about" almost never do. The false-positive rate on the skip list is low enough that this heuristic is production-ready without AI.

## Latest Learnings (2026-03-16 session 6)

- Vague defect messages cause indefinite loops when Claude cannot infer the correct fix. "Route file has executable code but defines no @router endpoints" with Fix "Define route decorators" is insufficient — Claude regenerates Flask Blueprint code because it doesn't know what framework to use. The fix message must name the exact wrong pattern and provide the exact correct replacement code, not a description of what to do.

- Claude generates Flask/Blueprint routes when it has no architectural constraint specifying otherwise. The model defaults to Flask for Python web routes in the absence of an explicit FastAPI instruction. A canonical skeleton showing `from fastapi import APIRouter`, `router = APIRouter()`, `@router.get(...)` eliminates this immediately — it is not ambiguous.

- Prose build instructions ("use FastAPI, not Flask") are less effective than concrete code patterns. Showing Claude an actual file with the correct imports and decorator patterns it must copy is more reliable than telling it the framework name. Architecture defined as code, not text.

- The distinction between architectural freedom and implementation freedom matters. When Claude is asked to build a feature, it should only decide: what entities exist, what fields they have, what business logic runs. It should not also decide: what framework, what decorator pattern, what import path, what file structure. These are already decided by the boilerplate. Canonical skeletons encode those decisions so they are removed from Claude's scope entirely.

- Detecting the wrong framework (Flask) explicitly in the static check is more actionable than detecting the absence of the right framework (FastAPI). "No @router endpoints found" is ambiguous — Claude may respond by adding Flask route decorators. "FLASK BLUEPRINT DETECTED" with exact conversion instructions is unambiguous.

## Latest Learnings (2026-03-15 session 4)

- Running all AI gates on every iteration regardless of what changed is the single largest source of wasted tokens in the loop. CONSISTENCY and FEATURE_QA are expensive ChatGPT calls that produce identical results when no files they care about have changed. Gate locking (comparing artifact manifests between iterations) eliminates these redundant calls with zero impact on QA correctness.

- The QUALITY gate (deployability, enhanceability, code quality) is useless in early repair iterations when the build is structurally broken. Checking enhanceability on code with unresolved AttributeErrors wastes tokens and produces noise. Splitting repair vs acceptance mode — skipping QUALITY in repair mode, running it fully only in the final iterations — reduces cost without losing coverage.

- Sending the full artifact set to every AI gate inflates token counts significantly on frontend-heavy builds. The CONSISTENCY gate only needs backend structural files (models/services/routes/schemas) to check cross-file alignment. Sending JSX pages, config files, and README docs to CONSISTENCY adds ~50-70% extra tokens with zero benefit — the gate cannot act on frontend content.

- REPAIR_MODE_RULES must be passed as a ChatGPT system message, NOT prepended inline to the user prompt. Inline prepend disrupts the prompt's instruction hierarchy and causes the model to partially ignore the repair focus rules. System role content is processed before the user turn and reliably scopes the model's attention.

- Structural bugs (missing routes, broken import chains, auth contract violations, async misuse) caught by deterministic checks early in the loop are invisible to AI gates until they cause runtime failures. Running INTEGRATION_FAST (checks 1,2,4,6,7) before CONSISTENCY catches these cheaply and skips AI gates for that iteration — preventing AI gates from generating defect reports about symptoms of a structural failure they cannot directly see.

- A build must not be marked accepted unless QUALITY explicitly ran in acceptance mode. Without enforcement, a build that only ever hit repair-mode iterations (QUALITY always skipped) could slip through with deployability or completeness gaps. The acceptance check must verify `_quality_ran_in_acceptance_mode = True` and force a final quality run if not.

## Latest Learnings (2026-03-15)

- Frontend bugs are structurally invisible to all five QA gates when no check reads JSX against config JSON. The AWI build shipped with 8 bugs — config objects rendered as text (`[object Object]`), dead buttons with no onClick, and a form state field silently dropped on submit — none caught by Feature QA, Static check, AI Consistency, or integration_check.py. Root cause: every check was backend-focused. Fix: integration_check.py Checks 13-15 cross-reference JSX expressions against `business_config.json` data shapes, scan for buttons missing onClick, and compare useState keys against config form field definitions.

- QA's anti-hallucination rules (`NEVER use hedged language`, `absence-of-thing defects are NOT valid`) correctly prevent false positives but also suppress valid cross-file inference bugs. A missing `onClick` is an absence; `{home.hero.cta_primary}` rendering an object looks syntactically fine. QA cannot flag what it can only infer. The right fix is deterministic checks in integration_check.py, not loosening QA rules — loosening QA rules would re-introduce the hallucination problem.

- A feature name alone is not a feature spec. Giving Claude only `--feature "Competitor benchmarking dashboard"` causes it to invent the data model, UI layout, scope, and acceptance criteria from scratch. In a feature-add context (not greenfield), invented behaviour conflicts with existing models and navigation. Fix: `generate_feature_spec.py` structures founder answers into a spec (data requirements, UI, actions, scope exclusions, AC) before the build runs. The spec is embedded in `_phase_context.note` so Claude implements exactly what was described.

## Latest Learnings (2026-03-13)

- QA and the Consistency gate can produce a direct logical contradiction on the same field. QA
  removes `status` from the Analysis model as "scope creep"; Consistency re-adds it as "AttributeError
  at runtime". Neither gate knows the other exists. The result is an infinite loop that consumes the
  entire iteration budget with real money spent. The fix must be in the QA prompt — QA must never flag
  standard infrastructure columns (`status`, `processing_status`) as scope violations. The rule of thumb:
  a database column is not a user-facing feature and is never scope creep by itself.
- Private helper methods (`_extract_*`, `_parse_*`, `_format_*`) are implementation details of a
  service, not spec-mandated interfaces. Both QA and the Consistency gate were flagging them. QA
  saw `_extract_strengths()` as an undocumented feature; Consistency tried to align callers and
  callee signatures for private methods. The fix: both prompts must exclude `_*` methods from their
  respective checks entirely.
- `__pycache__` directories were being extracted from Claude output and carried forward by
  merge_forward into subsequent iterations. This caused QA to flag `__pycache__/analysis.py`
  (a `.pyc` file!) as a scope violation, wasting an iteration on a phantom defect. Bytecode dirs
  must be pruned at artifact extraction time, not left for QA to encounter.
- Boilerplate frontend utilities (`../utils/api`, `../core/useEntitlements`) are not part of the
  business artifact set but are always present at runtime via the boilerplate. The Consistency gate
  was flagging `import api from '../utils/api'` as a "broken import" because the file wasn't in
  the business/ artifact dir. Any import from boilerplate paths must be in the DO NOT FLAG list.

## Latest Learnings (2026-03-12)

- Python's AST has two separate node types for function definitions: `ast.FunctionDef` (regular `def`)
  and `ast.AsyncFunctionDef` (`async def`). They are NOT related by inheritance. Any static check that
  uses `isinstance(x, ast.FunctionDef)` silently ignores all async methods. In the adversarial_ai_validator
  feature run, CHECK 10 built a `methods` set that excluded every `async def` service method —
  so `process_adversarial_analysis()` was permanently flagged as "missing" for 13 iterations even
  after being correctly implemented. The surgical fix added the method each iteration; CHECK 10 could
  never see it. Any AST-based check that walks class bodies must use
  `isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))`.
- A static check false positive that fires every iteration is worse than no static check at all.
  It burns all iteration budget on phantom fixes, blocks QA from running, and masks real issues.
  When a static defect fires 3+ consecutive times on the same file with the same "fix" applied each
  time, that is a signal the check is wrong — not Claude. The right response is to audit the check
  logic, not to sharpen the fix prompt.

- Two consecutive white-screen crashes (footer, home) from the same root cause: boilerplate
  components read top-level config keys unconditionally at render time. Every key the boilerplate
  reads at startup must be present in the generated config. The right audit is to read every
  boilerplate component that touches `business_config.json` and enumerate all keys it accesses —
  then ensure `_generate_business_config()` covers all of them. Fixing one crash at a time is
  whack-a-mole; a full schema audit up front closes all of them at once.
- Full schema audit (2026-03-12) found 5 top-level keys missing entirely: `pricing`, `contact`,
  `faq`, `terms_of_service`, `privacy_policy`. Also found two structural bugs: `footer.links`
  used `href` but boilerplate expects `url`; `home.features` was missing the `icon` field and
  `home` had no `social_proof` or `final_cta` blocks. Lesson: when adding a new config generator,
  read every boilerplate component that consumes the config — not just the one that just crashed.

- A missing top-level config key crashes the entire React app, not just one component.
  `Footer.jsx` calls `footer.columns.map(...)` at render time — if `footer` is absent from
  `business_config.json`, the TypeError propagates up and white-screens the whole app before
  any page loads. Every config key the boilerplate reads at startup must be present in the
  generated config, even if the harness doesn't explicitly use it.
- `_generate_business_config()` must stay in sync with the boilerplate's config schema.
  When the boilerplate adds a new top-level key that it reads unconditionally (footer, nav, etc.),
  the harness must generate a safe default for it. The fix is always Option A (populate the config)
  not Option B (defensive null-checks in JSX) — config is the source of truth, not component code.

## Latest Learnings (2026-03-11)

- CRA only compiles files inside `frontend/src`, so business pages must be copied from
  `business/frontend/pages` into `frontend/src/business/pages` during deploy. That copy
  step changes the relative import base; any `../utils/api` import that worked in the
  business folder breaks after the copy (it must be `../../utils/api` from inside `src`).
  Build failures on Vercel were caused by this mismatch, not by the deployment pipeline.
- A preflight static check that resolves imports from the **post-copy** location is
  required to catch these issues early. A targeted auto-fix for known paths (e.g.
  `../utils/api` → `../../utils/api`) keeps the source-of-truth business pages valid
  without relying on manual Vercel debugging.
- The import preflight should optionally report *all* relative imports (not just failures)
  and include asset references (CSS/images/fonts), because these files are also resolved
  relative to the post-copy location. This avoids build-only surprises on Vercel.
- Railway/Nixpacks language detection fails if the repo root doesn't contain a language
  signal. With a flat layout, `backend/requirements.txt` lives in a subdir, so Nixpacks
  reports "unable to generate a build plan." The fix is a root `requirements.txt` that
  delegates to `backend/requirements.txt`.
- Redeploys don't always need a Git push; separating "push" from "deploy" avoids multiple
  overlapping builds. Adding a `--skip-git-push` flag makes redeploy-only runs cheaper and faster.
- Railway deploys can take longer than 2 minutes for larger repos or cold starts. The default
  polling window should be longer (10 minutes) and overrideable so the pipeline doesn't report
  false negatives while a deploy is still building.
- Railway often delays `deployment.url`. Falling back to `railway domain` in the CLI provides a
  stable URL quickly, and logging the deployment ID gives a reliable pointer for debugging.
- Manual deploy state setup is error-prone. A small helper that writes `railway.deploy.json` /
  `vercel.deploy.json` from CLI args makes first-time setup deterministic and auditable.
- Using Vercel preview URLs for CORS causes unnecessary backend redeploys. Prefer the stable
  production domain (`https://<project>.vercel.app`) when setting `CORS_ORIGINS`.
- Auth0 must explicitly allow the production domain in callbacks/logout/origins. Automating
  this after frontend deploy (via a helper + `AUTH0_MGMT_TOKEN`) removes a brittle manual step.
- Long-lived runs directories accumulate large `build/`, `qa/`, and `logs/` trees. A targeted
  cleanup that preserves ZIPs + latest N runs per prefix keeps cost tracking viable while
  reclaiming space.

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
- Consistency fallthrough is not a neutral exit — it's an active failure path. When the harness
  clears all defect context and hands off to QA after N failed consistency attempts, QA evaluates
  cold and the harness filter removes its evidence-based defects. Result: a "clean" build with real
  AttributeError bugs at runtime. The fix: only fall through to QA when remaining issues are LOW/MEDIUM.
  HIGH issues at fallthrough must trigger a full-build Claude pass (16384 tokens, full governance
  context) so the model can fix all cross-file mismatches holistically in one shot.
- The 8192 patch token cap breaks down as soon as ≥2 files need to be output. With current file contents
  now in the prompt (necessary for surgical patches), each output file is full-size — Claude cannot
  compress all of them into 8192 tokens without dropping content. Observed: ReportService 4731→2256 chars,
  assessments.py 2285→1060 chars after a "fix". The token cap must scale with target file count:
  1 file → 8192 (safe), ≥2 files → 16384 (necessary).

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

## Session 5 — 2026-03-16: Prompt Caching + QA Inventory

### OpenAI prefix caching requires static content FIRST, dynamic content LAST

OpenAI automatically caches prompt prefixes ≥1024 tokens within a 5-10 minute window. No
`cache_control` parameter is needed — it is fully automatic. But it only caches the
**prefix** (leading tokens). If any dynamic content appears before your static rules, the
static rules are not in the cached prefix and caching never fires.

`qa_prompt.md` had `{{build_output}}` on line 13 of 183 — 170 lines of static rules came
AFTER the dynamic build output. Zero caching on any call.

Fix: move ALL dynamic blocks (`{{tech_stack_context}}`, `{{prohibitions_block}}`,
`{{defect_history_block}}`, `{{resolved_defects_block}}`, `{{block_data_json}}`,
`{{build_output}}`) to the very end. Static rules first, always.

Rule: **any `{{template_var}}` in a prompt file = everything from that line onward is NOT
in the cacheable prefix.** Check every prompt file: if dynamic vars appear before static
rules, the static rules don't cache.

### QA hallucination root cause: repeated full-prompt re-scanning during reasoning

GPT-4o re-scans the entire build_output multiple times while reasoning (for routes, then
models, then services, then frontend). On large builds (4k-15k tokens) this causes context
drift — the model loses track of what it has and hasn't seen, producing hallucinated missing
files and duplicate defects.

Fix: add a STEP -1 inventory instruction as static content. Force the model to build an
explicit FILE INVENTORY (typed by artifact category) from all `**FILE:**` headers before any
analysis. Hard-gate: files not in inventory must not appear in defects.

This shifts hallucination prevention from post-QA harness filtering to pre-analysis model
discipline. Earlier is better — filtering removes hallucinations after they're generated;
inventory prevents them from being generated at all.

### Cache hit logging is mandatory before claiming caching works

You cannot assume OpenAI caching is firing. Even with correct prompt ordering, caching can
fail if: (a) calls are >5-10 min apart (cache expires), (b) a dynamic field mutates the
static prefix, (c) prompt is under 1024 tokens at the static prefix boundary.

Always add `CACHE CHECK [GATE] iteration N: cached=X / total_prompt=Y` log lines to every
AI gate call. Check iteration 2+: if cached=0 consistently, find the root cause before
assuming savings.

Access pattern for plain-dict ChatGPT responses (NOT SDK objects):
`usage.get('prompt_tokens_details', {}).get('cached_tokens', 0)`
Not: `response.usage.prompt_tokens_details.cached_tokens` (SDK object — wrong here).
