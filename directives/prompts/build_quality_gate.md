**QUALITY GATE CHECK — Intake/Code Quality/Enhanceability/Deployability (OPTIONAL):**

You are a strict quality auditor for the generated `business/**` artifact set.

Evaluate across exactly these 4 dimensions:
1. **Completeness vs intake**
2. **Code quality**
3. **Enhanceability**
4. **Deployability**

Use the intake JSON and artifact files provided below.

Scoring scale per dimension:
- PASS
- LOW
- FAIL

When a dimension is FAIL or LOW, include concrete defects with actionable fixes.

**DO NOT FLAG:**
- Style-only preferences without runtime/product impact.
- Files outside `business/**`.
- Missing boilerplate internals under `core.*`/`lib.*` that are platform-provided.

**INTAKE JSON:**
```json
{{intake_json}}
```

**ARTIFACT FILES:**
{{artifact_contents}}

**OUTPUT CONTRACT:**
- If all dimensions are PASS, output exactly:
`QUALITY GATE: PASS`

- Otherwise output:
```
QUALITY GATE REPORT

DIMENSION-1: COMPLETENESS_VS_INTAKE = PASS|LOW|FAIL
DIMENSION-2: CODE_QUALITY = PASS|LOW|FAIL
DIMENSION-3: ENHANCEABILITY = PASS|LOW|FAIL
DIMENSION-4: DEPLOYABILITY = PASS|LOW|FAIL

ISSUE-1:
  - Dimension: [one of the 4]
  - Files: [file1] <-> [file2] (or single file)
  - Evidence: [quote exact offending code/contract mismatch]
  - Problem: [why this is a real quality gap]
  - Fix: [specific file-level fix]
  - Severity: HIGH | MEDIUM | LOW
```

Last line:
`QUALITY_GATE_COMPLETE`
