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
