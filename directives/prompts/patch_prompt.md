You previously built {{startup_id}} and output a manifest listing all files.
However, the following files were listed in your manifest but their content was NOT included in your output.

**MISSING FILES (output ONLY these):**
{{missing_files_bullets}}

**FILES ALREADY RECEIVED (DO NOT repeat these):**
{{existing_files_bullets}}

**RULES:**
1. Output ONLY the missing files listed above
2. Use **FILE: path/to/file.ext** header before each code block
3. Each file must be COMPLETE — no placeholders
4. Do NOT repeat any file from the "already received" list
5. Do NOT output artifact_manifest.json or build_state.json (already have them)
6. After all missing files, output: PATCH COMPLETE

**OUTPUT THE MISSING FILES NOW:**
