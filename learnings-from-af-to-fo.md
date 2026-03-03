# Learnings From AF to FO

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

- **Claude hedges by generating code in BOTH the correct path and familiar wrong paths.**
  Even when the prompt says "output only under `business/**`", Claude generates correct `business/backend/routes/`
  files AND duplicate logic under `app/api/`, `app/core/`, `tests/`. The harness pruner silently discards the
  wrong-path files — but they contained real logic, wasting iterations and tokens.
  Fix: explicitly name the forbidden paths (`app/`, `tests/`, `src/`, etc.) in HARD FAIL CONDITIONS and
  INVALID EXAMPLES with ← FORBIDDEN annotations and the correct equivalent path. Vague "only business/" is
  insufficient — Claude needs to see the exact wrong paths it tends to produce.

## Bottom Line
- Reliability came from harness-side deterministic controls, not expecting model session continuity.
- QA convergence requires both: specific defect descriptions (Fix: field) AND upfront prohibitions
  that prevent the failure pattern from appearing in the first place.
