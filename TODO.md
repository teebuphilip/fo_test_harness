# TODO

- Sanitize/normalize filenames extracted from model output to prevent path traversal.
- Support unlabeled code fences (``` with no language) in artifact extraction.
- Enforce governance ZIP size limits or selective inclusion to avoid prompt bloat.
- Warm-start from existing build: accept a run directory + iteration number as CLI args, hydrate artifact state from extracted files, and enter the loop at QA (fresh QA pass) or FIX (inject existing QA report as defects) — skipping the initial Claude BUILD call.
