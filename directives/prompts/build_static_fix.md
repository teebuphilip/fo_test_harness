**STATIC CODE FIX — TARGETED PATCH (NON-NEGOTIABLE):**

You are fixing deterministic static analysis defects in a lowcode build.
These are concrete code errors detected by automated checks — not QA opinion.
Each defect has exact file paths and specific errors that must be corrected.

**EXECUTION PRIORITY (STRICT ORDER):**
1. Output ONLY the files listed in DEFECT TARGET FILES below.
2. Do NOT output any other files — the harness carries all non-defect files forward.
3. No new scope. No new features. Fix ONLY the exact defects listed.

**REQUIRED FILE INVENTORY (for reference — DO NOT output these):**
{{required_file_inventory_bullets}}

**DEFECT TARGET FILES (edit ONLY these):**
{{defect_target_files_bullets}}

**STATIC DEFECTS TO FIX:**
{{static_defects}}

**BOILERPLATE IMPORT REFERENCE (use exactly these — do not invent variants):**
- DB Base + session: `from core.database import Base, get_db` → `db: Session = Depends(get_db)`
- Auth guard: `from core.rbac import get_current_user` → `current_user: dict = Depends(get_current_user)`
- Tenancy: `from core.tenancy import TenantMixin, get_tenant_db`
- Every SQLAlchemy model MUST inherit `Base` from `core.database`, NOT `declarative_base()`
- Every SQLAlchemy model using multi-tenancy MUST inherit `TenantMixin` AND import it from `core.tenancy`
- Every backend route that accesses user data MUST include `Depends(get_current_user)` on the endpoint

**HARD CONSTRAINTS (ALIGN WITH BOILERPLATE RULES):**
- Output files ONLY under `business/**`.
- REQUIRED: `business/package.json`.
- Frontend pages only in `business/frontend/pages/*.jsx`.
- Backend routes only in `business/backend/routes/*.py`.
- Every file MUST use this exact format — the FILE header immediately followed by a code fence:
  ```
  **FILE: business/path/to/file.ext**
  ```language
  <complete file content>
  ```
  ```
- Use language tags: `python` for .py, `jsx` for .jsx/.js, `json` for .json, `markdown` for .md.
- NEVER output raw file content without a code fence — the extraction system requires code fences.
- No unlabeled code fences (every ``` block must have a language tag).

{{prohibitions_block}}
**DO NOT DO:**
- Do not introduce new features or change business logic beyond the defect.
- Do not rename or move files unless the defect explicitly requires it.
- Do not emit partial snippets — output complete file content.
- Do not change imports or class structure in files not listed as defect targets.

**OUTPUT CONTRACT:**
1. Output ONLY the defect-target file blocks for each defect.
2. Last line: `PATCH_SET_COMPLETE`
