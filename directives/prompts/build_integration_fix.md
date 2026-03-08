**INTEGRATION FIX — SURGICAL PATCH (NON-NEGOTIABLE):**

You are fixing cross-file integration defects detected by automated static analysis.
These are concrete structural errors: missing model fields, missing library declarations, missing KPI implementations.

**The CURRENT content of each target file is provided below. You MUST use it as your exact base.**
Do NOT reconstruct files from memory. Copy the existing content verbatim and add ONLY what the defect specifies.

---

**REQUIRED FILE INVENTORY (for reference — DO NOT output these):**
{{required_file_inventory_bullets}}

**TARGET FILES (output ONLY these):**
{{defect_target_files_bullets}}

**INTEGRATION DEFECTS TO FIX:**
{{integration_defects}}

---

**CURRENT FILE CONTENTS (base these files on exactly what is shown — change NOTHING that is not in the defect list):**

{{current_file_contents}}

---

**BOILERPLATE IMPORT REFERENCE — use exactly these, do not invent variants:**
- DB Base + session: `from core.database import Base, get_db` → `db: Session = Depends(get_db)`
- Auth guard: `from core.rbac import get_current_user` → `current_user: dict = Depends(get_current_user)`
- SQLAlchemy Column types: `from sqlalchemy import Column, String, Integer, Float, Boolean, Text, DateTime, ForeignKey`
- Every SQLAlchemy model MUST inherit `Base` from `core.database` — NEVER from `declarative_base()`

**HARD CONSTRAINTS:**
- Output ONLY the files listed in TARGET FILES above.
- The harness carries all other files forward — do NOT touch them.
- Every file MUST use this exact format (FILE header immediately followed by a code fence):
  ```
  **FILE: business/path/to/file.ext**
  ```language
  <complete file content>
  ```
  ```
- Language tags: `python` for .py, `jsx` for .jsx/.js, `json` for .json, `markdown` for .md.
- NEVER output raw file content without a code fence.
- No unlabeled code fences — every ``` block must have a language tag.

**ABSOLUTE DO-NOTS:**
- Do NOT change `__tablename__` values.
- Do NOT change the Base class or its import (`from core.database import Base`).
- Do NOT modify existing Column definitions — only ADD new ones.
- Do NOT add new routes, endpoints, or services beyond what the defect specifies.
- Do NOT change any file not listed in TARGET FILES.
- Do NOT add docstrings or comments beyond what already exists.
- Do NOT restructure, rename, or reorder anything.

**OUTPUT CONTRACT:**
1. Output ONLY the defect-target file blocks, each with a FILE header + code fence.
2. Last line of your response MUST be exactly: `PATCH_SET_COMPLETE`
