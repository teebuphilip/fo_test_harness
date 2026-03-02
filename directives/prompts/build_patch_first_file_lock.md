**PATCH-FIRST + FILE INVENTORY LOCK (NON-NEGOTIABLE):**

You are in recovery mode for a large lowcode build.
Your primary objective is stability: preserve file completeness while fixing only targeted defects.

**EXECUTION PRIORITY (STRICT ORDER):**
1. Patch targeted defect files first.
2. Preserve all previously accepted files unchanged unless explicitly listed in defects.
3. Only if patch cannot satisfy defect requirements, regenerate the minimum necessary additional files.

**FILE INVENTORY LOCK:**
- The file inventory below is the required output set for this iteration.
- You MUST output every file in the required inventory list.
- If a file is not part of defect scope, output the same semantics/content as prior version.
- Never drop a required file.

**REQUIRED FILE INVENTORY:**
{{required_file_inventory_bullets}}

**DEFECT TARGET FILES (edit only these unless absolutely necessary):**
{{defect_target_files_bullets}}

**HARD CONSTRAINTS (ALIGN WITH BOILERPLATE RULES):**
- Output files ONLY under `business/**`.
- REQUIRED: `business/package.json`.
- Frontend pages only in `business/frontend/pages/*.jsx`.
- Backend routes only in `business/backend/routes/*.py`.
- Every code block MUST have: **FILE: path/to/file.ext**
- No unlabeled code fences.

**DO NOT DO:**
- Do not introduce new features.
- Do not rename/move files unless defect explicitly requires it.
- Do not change framework wiring files outside `business/**`.
- Do not emit partial snippets for required files.

**OUTPUT CONTRACT:**
1. First line: `PATCH_PLAN: <1-3 lines explaining exact defect-only edits>`
2. Then output complete file blocks for required inventory.
3. Last line: `PATCH_SET_COMPLETE`

**SELF-CHECK BEFORE FINAL OUTPUT:**
- Every required inventory file is present in your response.
- `business/package.json` is present.
- No file path outside `business/**`.
- No new scope beyond defects.
