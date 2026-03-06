# TODO

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
