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

{{prohibitions_block}}
**DO NOT DO:**
- Do not introduce new features.
- Do not rename/move files unless defect explicitly requires it.
- Do not change framework wiring files outside `business/**`.
- Do not emit partial snippets for required files.

**OUTPUT CONTRACT:**
1. First: `## DEFECT ANALYSIS` — write this section BEFORE any file output or PATCH_PLAN.
   For EACH defect, write exactly:
   ```
   DEFECT-[N]:
   - Root cause: [why this occurred — be specific about your world model vs the intake boundary]
   - Pattern type: ONE-TIME-BUG | SCOPE-BOUNDARY | RECURRING-VIOLATION
   - Reintroduction risk: HIGH | LOW — [if HIGH: name the exact pattern you will avoid, not just the field]
   - Commitment: [what you will NOT output, stated categorically — not just the named field/endpoint]
   ```
2. Then: `PATCH_PLAN: <1-3 lines — for each defect: FIXED or EXPLAINED>`
3. If any defects are EXPLAINED: output a `## DEFECT RESOLUTIONS` block next (see format below).
4. Then output ONLY the defect-target file blocks for FIXED defects.
5. Last line: `PATCH_SET_COMPLETE`

**EXPLAINED RESOLUTION FORMAT:**
Use this for defects that are invalid, out-of-scope, or by-design. No code output for these defects.
```
## DEFECT RESOLUTIONS

DEFECT-[N]: EXPLAINED
- Governance Rule: [cite the exact rule file, e.g. fo_build_file_structure_rules.json]
  OR
- Intake Reference: [cite the exact intake field/section]
- Explanation: [1-2 sentences why this defect is not valid or is by-design]
```

Valid reasons to use EXPLAINED:
- File flagged is outside `business/**` (boilerplate infrastructure — not your build)
- Feature flagged is explicitly in the intake spec (not scope creep — cite the section)
- File is auto-generated post-QA by harness (README-INTEGRATION.md, artifact_manifest.json, etc.)
- QA cited code that does not exist in your output (fabricated evidence)

**SELF-CHECK BEFORE FINAL OUTPUT:**
- `## DEFECT ANALYSIS` section was written before PATCH_PLAN and before any file output.
- Every defect is either FIXED (file output) or EXPLAINED (in DEFECT RESOLUTIONS block).
- No file path outside `business/**`.
- No new scope beyond defects.
- No non-defect files included.
- Any HIGH reintroduction risk from DEFECT ANALYSIS is not present in the output files.
