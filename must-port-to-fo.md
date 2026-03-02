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

## Priority 3 (QA Convergence)
1. QA defect `Fix:` field
   - Add `Fix:` to defect output format so QA provides exact code change, not just problem description.

2. Boilerplate data layer prohibitions
   - Explicitly prohibit dict storage, sequential IDs, hardcoded data, in-memory state in boilerplate path rules.
   - Must be present at iteration 1, not just defect iterations.

3. Defect enrichment before injection
   - Detect mock-storage and frontend-hardcode patterns in QA report before feeding to next build iteration.
   - Prepend architectural fix guide (exact patterns to use/avoid) on match.

## Acceptance Criteria for Port
- No pre-QA false-fail caused by manifest staleness.
- No skipped continuation when output is still truncated.
- Defect iterations preserve required file set across retries.
- QA rejections are primarily real implementation defects, not artifact drift.
- Boilerplate builds do not produce dict/mock storage on any iteration.
- Defect count trends downward across iterations (convergence).
