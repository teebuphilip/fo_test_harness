# Prompts Overview

This file summarizes each prompt template in `directives/prompts/`.

- `build_ai_consistency.md`: ChatGPT cross-file consistency audit (models, schemas, routes, imports, frontend↔backend API alignment). Outputs PASS or a structured consistency report.
- `build_boilerplate_capabilities.md`: Reference library of boilerplate capabilities and exact imports/patterns to reuse instead of rebuilding.
- `build_boilerplate_path_rules.md`: Hard path and file-format rules for boilerplate builds (required locations, forbidden paths, file header rules).
- `build_boilerplate_sample_code.md`: Canonical sample snippets showing correct boilerplate usage patterns.
- `build_dynamic_base.md`: Core build prompt scaffold (iteration context, intake extraction, governance and scope rules).
- `build_governance.md`: Injects the governance ZIP contents into the build prompt context.
- `build_integration_fix.md`: Targeted fix prompt for integration defects (driven by `integration_issues.json`).
- `build_patch_first_file_lock.md`: Patch guidance that locks the first file(s) to prevent scope creep during fixes.
- `build_previous_defects.md`: Provides prior QA defects and resolution context for the current fix iteration.
- `build_quality_gate.md`: Quality gate evaluation prompt (completeness, quality, enhanceability, deployability) for ChatGPT.
- `build_static_fix.md`: Deterministic static-fix prompt; outputs only defect-target files.
- `continuation_prompt.md`: Fallback continuation prompt when Claude output truncates mid-build.
- `deploy_prompt.md`: Deployment executor prompt using deploy governance rules.
- `part_prompt.md`: Multipart continuation prompt requesting a specific part X/N of Claude output.
- `patch_prompt.md`: Missing-file patch prompt when manifest lists files not present in output.
- `polish_docs_wrapper_prompt.md`: Wrapper for post‑QA documentation polish using an external directive.
- `polish_env_prompt.md`: Generates `.env.example` based on detected environment variable usage.
- `polish_integration_readme_prompt.md`: Generates `business/README-INTEGRATION.md` with boilerplate integration notes.
- `polish_readme_prompt.md`: Generates project `README.md` from build artifacts.
- `polish_testcases_wrapper_prompt.md`: Generates a comprehensive testcase document using an external directive.
- `polish_tests_prompt.md`: Generates unit/integration test files for key services/models.
- `qa_prompt.md`: Feature QA prompt to ChatGPT, producing structured QA report and acceptance/rejection markers.
