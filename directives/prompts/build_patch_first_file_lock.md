**PATCH-FIRST + FILE INVENTORY LOCK (NON-NEGOTIABLE):**

You are in recovery mode for a large lowcode build.
Your primary objective is stability: preserve file completeness while fixing only targeted defects.

**EXECUTION PRIORITY (STRICT ORDER):**
1. Output ONLY the files listed in DEFECT TARGET FILES below.
2. Do NOT output any other files — the harness will carry all non-defect files forward automatically.
3. Outputting a non-defect file risks overwriting a working version with a regressed one.

**FILE INVENTORY (for reference only — do NOT output these):**
The full required file set is listed below so you understand the complete artifact scope.
Do NOT output these files. They are preserved by the harness as-is from the previous iteration.

**REQUIRED FILE INVENTORY:**
{{required_file_inventory_bullets}}

**DEFECT TARGET FILES (edit only these unless absolutely necessary):**
{{defect_target_files_bullets}}

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

**DO NOT DO:**
- Do not introduce new features.
- Do not rename/move files unless defect explicitly requires it.
- Do not change framework wiring files outside `business/**`.
- Do not emit partial snippets for required files.

**OUTPUT CONTRACT:**
1. First line: `PATCH_PLAN: <1-3 lines explaining exact defect-only edits>`
2. Then output ONLY the defect-target file blocks.
3. Last line: `PATCH_SET_COMPLETE`

**SELF-CHECK BEFORE FINAL OUTPUT:**
- You are outputting ONLY files from DEFECT TARGET FILES — nothing else.
- No file path outside `business/**`.
- No new scope beyond defects.
- No non-defect files included.
