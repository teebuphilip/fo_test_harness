**ITERATION:** {{iteration}} of {{max_iterations}}
**YOUR TASK:**
1. Extract {{block}} intake data from the INTAKE DATA section below
2. Execute BUILD according to governance state machine
3. Follow all enforcement rules (tier, scope, iteration, QA routing)
4. Produce COMPLETED_CLOSED state with all required artifacts
5. You are on iteration {{iteration}} - Max 5 iterations per task

**PHASED FEATURE RULE (NON-NEGOTIABLE):**
- If a feature/integration is marked "optional", "phase 2", "phase 3", or "later",
  you MUST NOT implement it now. Provide only a stub/interface and TODO notes.

{{previous_defects_section}}

**INTAKE DATA ({{block}} — key: {{block_key}}):**
{{block_data_json}}
{{tech_stack_instructions}}{{integration_instructions}}{{boilerplate_path_instruction}}
**BEGIN BUILD EXECUTION NOW.**
