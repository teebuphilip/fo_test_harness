**CRITICAL FILE PATH RULES (BOILERPLATE MODE):**
- Output files ONLY under `business/**`.
- REQUIRED: include `business/README-INTEGRATION.md`.
- Frontend pages MUST be in `business/frontend/pages/*.jsx`.
- Backend API routes MUST be in `business/backend/routes/*.py`.
- Every code block MUST have an explicit **FILE: path/to/file** header.
- Do NOT emit unlabeled code fences.

**AUTO-LOADER CONTRACT (NON-NEGOTIABLE):**
- Frontend: files in `business/frontend/pages/*.jsx` auto-route to `/dashboard/<kebab-case>`.
- Backend: files in `business/backend/routes/*.py` auto-mount at `/api/<filename>`.
- Do NOT edit `frontend/src/App.js` for route registration.
- Do NOT edit backend `main.py` for router registration.

**HARD FAIL CONDITIONS:**
- If you output ANY file outside `business/**`, the build FAILS.
- If you omit the FILE header on any code block, the build FAILS.
- If you place frontend pages outside `business/frontend/pages/`, the build FAILS.
- If you place backend routes outside `business/backend/routes/`, the build FAILS.

**VALID EXAMPLES:**
**FILE: business/frontend/pages/ClientDashboard.jsx**
**FILE: business/backend/routes/assessments.py**
**FILE: business/models/Client.js**
**FILE: business/services/ReportService.js**
**FILE: business/README-INTEGRATION.md**

**INVALID EXAMPLES (DO NOT OUTPUT):**
**FILE: business/components/ClientDashboard.jsx**
**FILE: business/routes/assessments.py**
**FILE: frontend/src/components/ClientList.jsx**
**FILE: backend/tests/test_clients.py**
**FILE: package.json**

**PRE-PROMPT CHECKLIST (MUST PASS BEFORE YOU OUTPUT):**
- All files are under `business/**`.
- Frontend pages are in `business/frontend/pages/`.
- Backend routes are in `business/backend/routes/`.
- `business/README-INTEGRATION.md` is included.
- Every code block has a **FILE:** header.
- No unlabeled code fences.
