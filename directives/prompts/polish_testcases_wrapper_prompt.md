Generate a complete testcase document as markdown using the directive below.

{{qa_testcase_directive}}

Context:
- startup_id: {{startup_id}}
- block: {{block}}
- iteration: {{iteration}} ({{iteration_padded}})

Intake JSON:
```json
{{intake_json}}
```

Artifact manifest sample:
{{manifest_sample}}

Build output sample:
{{build_output_sample}}

Output contract:
1) Return markdown only.
2) Include:
- Test strategy and scope
- Environment + data prerequisites
- End-to-end manual test cases (with IDs, steps, expected results)
- API contract test cases
- Negative/error-path test cases
- Regression pack (smoke) test cases
- A Playwright conversion section mapping manual cases to automated specs
- A Postman Suite conversion section mapping API/manual cases to Postman collections/folders/tests
3) Name frontend/backend routes and files when possible from provided context.
4) Keep all requirements grounded in the intake and produced artifacts.
