# TODO

## Intake / pre-planner improvements

- Add two-mode flow for intake → pre-planner:
  - Shared steps (factory + quality): Intake → PRD structuring → Grill-me pass → Patch intake + freeze decisions → Pre-planner slices (vertical tracer bullets) → Build.
  - Quality-only add-on: Vision/positioning + audience feel + "what must be surprisingly good?"
- Reference/inspiration: mattpocock/skills (write-a-prd, grill-me, prd-to-plan)
  - https://github.com/mattpocock/skills
- Triage enhancement (do NOT implement yet): add a lightweight root-cause note to the existing ChatGPT triage step (not Feature QA).
  - Context: Feature QA prompt is pure QA; triage happens post-QA rejection in `fo_test_harness.py` via `_triage_and_sharpen_defects()`.
  - Desired change: update triage prompt to include `ROOT_CAUSE: <one sentence>` per defect, alongside `CLASSIFICATION` and `SHARPENED_FIX`.
  - Trigger: only when QA rejects (current behavior). No new calls; just extend triage output format.
  - Output handling: log root-cause note for each defect (e.g., in `iteration_##_triage_output`) and optionally surface in console for audit.
  - Goal: capture a minimal causal hypothesis to reduce fix thrash without bloating QA or adding extra API calls.

## Boilerplate fixes needed (teebu-saas-platform)

- Sanitize/normalize filenames extracted from model output to prevent path traversal.
- Support unlabeled code fences (``` with no language) in artifact extraction.
- Enforce governance ZIP size limits or selective inclusion to avoid prompt bloat.
- Warm-start from existing build: accept a run directory + iteration number as CLI args, hydrate artifact state from extracted files, and enter the loop at QA (fresh QA pass) or FIX (inject existing QA report as defects) — skipping the initial Claude BUILD call.
- Config-driven static check architecture (Plan P):
  - Add `fo_static_check_rules.json` with profile support (`default_profile`, `profiles`).
  - First profile: `fastapi_nextjs` with:
    - `local_import_prefixes`
    - `requirements_files`
    - `directories` (`models`, `routes`, `services`, `frontend`)
    - `markers` (route/model/auth symbols/regex)
    - `config_rules` for `next.config.js`, `postcss.config.js`, `tailwind.config.*`
    - `checks` toggles and `thresholds`
  - Refactor `_run_static_check()` to load rules by profile and fall back safely to current defaults when rules are missing/invalid.
  - Keep intake-aware checks (KPI/download-export) in Python logic for now; only policy/toggles move to config.
  - Validate against known-good and known-bad artifact runs before enabling additional profiles.
- Continue false-positive static-check hardening (Item #1):
  - Add targeted exclusions for dynamic framework behavior beyond CHECK 10 (ORM constructors).
  - Require every new static rule to be validated against known-good artifacts before enabling.
  - Add quick per-check kill-switch/toggle support to isolate regressions fast.
- Quality-gate redundancy tuning (Item #4):
  - Keep Gate 4 enabled, but avoid duplicate defect classes already covered by static/consistency.
  - Add quality-issue de-duplication against Gate 2/3 issue fingerprints before creating fix payloads.
  - Consider running Gate 4 only on "stable" iterations (e.g., after first clean 2+3 pass), while preserving final strict pass requirement.

- feature_adder.py — incremental feature build tool:
  - Companion to phase_planner.py for adding a single new feature to an already-deployed project.
  - Inputs: existing deployed manifest (artifact list from prior run ZIP), new feature description.
  - What it does:
    - Classifies the new feature as DATA_LAYER or INTELLIGENCE_LAYER (same logic as phase_planner).
    - Produces a scoped intake JSON with only the new feature in must_have_features.
    - Adds a _phase_context block listing all existing deployed files (do-not-regenerate list).
    - Outputs the scoped intake ready to pass directly to fo_test_harness.py.
  - Why: right now adding a feature requires manually scoping the intake. feature_adder.py
    automates that scoping step — existing codebase is never touched, harness generates only
    the delta files for the new feature.
  - Workflow once built:
    1. Describe new feature in plain text or as an intake snippet.
    2. Run: python feature_adder.py --manifest <prior_run.zip> --feature "description"
    3. Run harness on the output intake — small build, 1-3 iterations, low cost.
    4. Merge new files into deployed repo via deploy pipeline.

- Full AI product development loop (vision):
  - Once the codebase is working and deployed, the entire feature development cycle
    can be AI-driven end-to-end:
    1. Ideation: give Claude or ChatGPT the product description → generate a
       prioritized feature backlog grouped by value and complexity.
    2. Feature intake: run each feature (or related batch) through a lightweight
       intake generator — a slim version of generate_intake.sh that takes a feature
       description + existing product context and produces the must_have_features
       JSON block. Could be a single Claude prompt.
    3. phase_planner.py: classifies as DATA_LAYER or INTELLIGENCE_LAYER, determines
       if the feature needs its own phase or can be bundled.
    4. feature_adder.py: scopes the intake against the existing deployed manifest,
       produces the delta intake (do-not-regenerate list auto-populated).
    5. fo_test_harness.py: builds the delta, QA validates, outputs new files only.
    6. Deploy pipeline: merges new files into live repo, ships.
  - Human input required: feature idea + deploy approval. Everything else is
    automated or AI-assisted.
  - Missing piece today: the feature intake generator (step 2). Everything else
    either exists or is on this TODO. That is the next logical tool after feature_adder.py.

## Harness pipeline risks (from review)

- ✅ FIXED 2026-03-18: run_integration_and_feature_build.sh: Phase 1 ZIP auto-detect scoped to `${INTAKE_STEM}_p1_BLOCK_B_*.zip`
- ✅ FIXED 2026-03-18: run_integration_and_feature_build.sh: Integration fix pass fallback scoped to run dir prefix (strips timestamp)
- run_integration_and_feature_build.sh: final merged ZIP can miss startup-specific `business_config.json` because the phase/feature pipeline suppresses post-QA polish on the runs that feed the final merge.
  - Evidence: `fo_test_harness.py` generates `business/backend/config/business_config.json` and `business/frontend/config/business_config.json` during post-QA polish, but the Wynwood final ZIP `fo_harness_runs/wynwood_thoroughbreds_BLOCK_B_full_20260318_103929.zip` contains neither file.
  - Current failure mode: final ZIP keeps boilerplate `saas-boilerplate/.../business_config.json` (`InboxTamer`) while runtime app reads `backend/config/business_config.json`, causing deploy-time mismatch and startup crashes.
  - Likely cause: Phase 1/entity runs use `--no-polish`, intermediate features use `--no-polish`, and integration fix passes also resume with `--no-polish`, so the final accepted artifact path never carries forward the generated config files.
  - Required fix: ensure the last artifact that feeds final ZIP assembly runs polish, or explicitly generate/copy startup-specific `business_config.json` into the final merged deliverable.
- run_integration_and_feature_build.sh: Feature ZIP lookup uses broad `startup_idea_id` slug pattern;
  if IDs are reused across runs, wrong ZIP can be selected. Consider scoping to current intake/run.

## Convergence improvements (Claude build + ChatGPT QA)

- Add strict file inventory enforcement: force Claude to output only files in manifest + explicit new files list.
  If a file is missing, auto-carry-forward rather than allow silent deletion.
- Add "known-good boilerplate snippets" retrieval for common patterns (auth, DB, errors) to reduce hallucinated variants.
- Add a deterministic "schema contract validator" (route ↔ schema ↔ model ↔ service) before AI QA; only send
  failing contracts to Claude as surgical fixes.
- Add a "defect fingerprint budget": if the same defect repeats 2+ times, auto-escalate to SYSTEMIC with
  larger context + explicit patch instructions.
- Add a structured output schema for Claude fixes (JSON with file list + rationale) and reject if missing
  required files; forces completeness.
- QA: add calibration on hallucinated defects by checking evidence snippets against file contents; if evidence
  lines are missing, auto-drop the defect before sending to Claude.
- QA: enforce "single-source-of-truth" for business_config defaults (home/footer) in harness generation so
  QA doesn't flag missing UI sections repeatedly.
