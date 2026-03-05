# QA_TESTCASE_DOC_DIRECTIVE

Purpose:
- Produce a complete, execution-ready testcase document after QA acceptance.

Scope:
- Cover only delivered/intended behavior from intake + built artifacts.
- Do not invent features not present in intake/artifacts.

Required sections:
1. Test Objectives
2. Test Environment + Preconditions
3. Test Data/Fixtures
4. End-to-End Test Cases (manual)
5. API Test Cases
6. Negative/Failure Test Cases
7. Security/AuthZ/AuthN checks
8. Regression Smoke Pack
9. Playwright Conversion Plan
10. Postman Suite Conversion Plan
11. Risks/Unknowns/Out-of-scope

Manual testcase format:
- `TC-ID`
- `Title`
- `Priority`
- `Preconditions`
- `Steps`
- `Expected Result`
- `Artifacts/Logs to Capture`

Playwright conversion format:
- `PW-ID` mapped to one or more `TC-ID`s
- file path suggestion (e.g., `tests/e2e/<feature>.spec.ts`)
- selector/data requirements
- auth strategy (interactive login / token seeding)
- expected assertions

Postman conversion format:
- `PM-ID` mapped to one or more `TC-ID`s (especially API cases)
- collection/folder suggestion (e.g., `postman/<startup>.collection.json` and folder names)
- required variables (`baseUrl`, `token`, tenant/client IDs, etc.)
- pre-request script requirements (auth token acquisition/refresh)
- test script assertions (status, schema, key fields, error payloads, latency budget where relevant)
- execution notes for Newman (`newman run ...`) and CI integration suggestions

Output quality rules:
- Be explicit and reproducible.
- Prefer deterministic assertions over subjective checks.
- Separate "must pass" vs "nice to have" checks.
- Include at least one download/report validation case when reporting/export is in scope.
