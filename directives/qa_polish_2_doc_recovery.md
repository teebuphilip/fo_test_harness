# QA_POLISH_2_DOC_RECOVERY

You are running after QA acceptance. Generate missing documentation that matches the accepted artifacts exactly.

## Inputs
- Final accepted artifact set from `build/iteration_XX_artifacts/`
- Intake context and QA reports from this run

## Output Contract
- Output only file blocks using this exact format:
  - `**FILE: relative/path.ext**`
  - fenced markdown block with file contents
- Default output location: `business/docs/`

## Required Docs
1. `business/docs/HLD.md`
2. `business/docs/TECH_SPEC.md`
3. `business/docs/QA_TESTCASES.md`
4. `business/docs/INTEGRATION_GUIDE.md`

## Accuracy Rules
- Do not invent files, APIs, services, routes, or tables that are not in artifacts.
- Every file path, module name, and service/model/component reference must exist in the artifacts.
- If data is missing, state assumptions explicitly in a dedicated "Assumptions" section.
- Keep docs concise and implementation-aligned.

## Content Requirements
### HLD.md
- System overview
- Architecture/modules
- Data flow
- Key constraints and assumptions

### TECH_SPEC.md
- Components/services/models
- Interfaces and data contracts
- Environment/config dependencies
- Error handling and edge cases

### QA_TESTCASES.md
- Test strategy
- Test case matrix (ID, objective, setup, steps, expected)
- Positive, negative, and boundary scenarios

### INTEGRATION_GUIDE.md
- Repo integration steps
- Required DB objects and config
- Runtime validation checklist
- Rollback notes
