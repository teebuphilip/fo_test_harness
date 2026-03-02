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

## Bottom Line
- Reliability came from harness-side deterministic controls, not expecting model session continuity.
- QA convergence requires both: specific defect descriptions (Fix: field) AND upfront prohibitions
  that prevent the failure pattern from appearing in the first place.
