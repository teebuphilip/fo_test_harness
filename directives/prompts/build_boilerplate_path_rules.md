**CRITICAL FILE PATH RULES (BOILERPLATE MODE):**
- Output files ONLY under `business/**`.
- REQUIRED: include `business/README-INTEGRATION.md`.
- REQUIRED: include `business/package.json`.
- Every code block MUST have an explicit **FILE: path/to/file** header.
- Do NOT emit unlabeled code fences.
**HARD FAIL CONDITIONS:**
- If you output ANY file outside `business/**`, the build FAILS.
- If you omit the FILE header on any code block, the build FAILS.
**VALID EXAMPLES:**
**FILE: business/models/Client.js**
**FILE: business/services/ReportService.js**
**FILE: business/tests/report_service.test.js**
**FILE: business/package.json**
**INVALID EXAMPLES (DO NOT OUTPUT):**
**FILE: backend/tests/test_clients.py**
**FILE: frontend/src/components/ClientList.jsx**
**FILE: package.json**
**PRE-PROMPT CHECKLIST (MUST PASS BEFORE YOU OUTPUT):**
- All files are under `business/**`.
- `business/README-INTEGRATION.md` is included.
- `business/package.json` is included.
- Every code block has a **FILE:** header.
- No unlabeled code fences.
