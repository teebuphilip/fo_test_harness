Execute QA_POLISH_2_DOC_RECOVERY using the directive below.

**DIRECTIVE (external file):**
{{qa_polish_2_directive}}

**CONTEXT:**
- startup_id: {{startup_id}}
- block: BLOCK_{{block}}
- iteration: {{iteration}}
- artifacts_dir: iteration_{{iteration_padded}}_artifacts

**BUILD ARTIFACTS (sample):**
{{manifest_sample}}

**BUILD OUTPUT SUMMARY (truncated):**
{{build_output_sample}}

**HARD REQUIREMENTS:**
1. Output only file blocks with this exact pattern:
   **FILE: relative/path.ext**
   ```markdown
   ...
   ```
2. Use paths under `business/docs/` unless directive says otherwise.
3. Do not include explanations outside file blocks.
