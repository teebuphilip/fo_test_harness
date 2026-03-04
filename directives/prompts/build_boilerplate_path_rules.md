**CRITICAL FILE PATH RULES (BOILERPLATE MODE):**
- Output files ONLY under `business/**`.
- REQUIRED: include `business/README-INTEGRATION.md`.
- REQUIRED: include `business/package.json`.
- Frontend pages MUST be in `business/frontend/pages/*.jsx` — `.jsx` extension, NOT `.tsx`, NOT `.ts`.
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
- NEVER output files under `app/`, `app/api/`, `app/core/`, `src/`, `tests/`, `backend/`, `frontend/` — these paths are FORBIDDEN. The harness will silently discard them and your logic will be lost.
- NEVER use `business/frontend/app/` (Next.js app router) — the boilerplate uses pages router. Use `business/frontend/pages/` ONLY.
- NEVER use `.tsx` or `.ts` extensions for frontend pages — use `.jsx` ONLY.
- NEVER create `business/tests/**` — tests are generated separately by the harness after QA.
- NEVER create `business/backend/__init__.py` or `business/backend/app.py` — these are boilerplate internals, do not touch them.
- NEVER create `business/backend/services/**` — services belong in `business/services/` (not inside backend/).
- NEVER create `business/app/**` — this path is forbidden.

**BOILERPLATE BOUNDARY — THE BOILERPLATE IS A BLACK BOX. DO NOT RECREATE ITS INTERNALS.**

If you feel the urge to create any of these — STOP. Use the import instead:

| If you want to create...                        | WRONG                                      | CORRECT                                              |
|-------------------------------------------------|--------------------------------------------|------------------------------------------------------|
| Auth middleware / JWT verification              | `backend/app/middleware/auth.py`           | `from core.rbac import get_current_user`             |
| Database connection / session factory           | `backend/app/db.py`, `database.py`         | `from core.database import Base, get_db`             |
| Utility helpers / calculation functions         | `backend/app/utils/calculations.py`        | Put in `business/services/MyService.py`              |
| Tenant isolation logic                          | `backend/app/middleware/tenant.py`         | `from core.tenancy import get_tenant_db`             |
| Auth0 / user management                        | `backend/app/auth/auth0.py`               | `from lib.auth0_lib import load_auth0_lib`           |

The boilerplate already provides all of the above. Any file you create at `backend/app/middleware/`, `backend/app/utils/`, `backend/app/core/`, or `backend/app/auth/` will be **silently deleted** by the harness. Your code will vanish and QA will fail.
- `user.getAccessTokenSilently()` anywhere in any file is a HARD FAIL — this method does not exist on the Auth0 user object. The build will be REJECTED by QA every single time this appears. Use `const { getAccessTokenSilently } = useAuth0();` and call `getAccessTokenSilently()` directly.

**DATA LAYER PROHIBITIONS (HARD — NO EXCEPTIONS):**
- NEVER use Python dicts as storage: `x_db = {}`, `data = []`, `store = {}` — all forbidden.
- NEVER use `len(collection) + 1` for ID generation. Use `import uuid; str(uuid.uuid4())`.
- NEVER return hardcoded or static data from route handlers (no mock payloads, no example dicts).
- NEVER use in-memory state between requests. If the process restarts, all data must survive.
- ALWAYS use the boilerplate's database ORM/service for any read or write operation.
- ALWAYS fetch dynamic data from the backend in frontend components — no hardcoded arrays.
- NEVER use Flask (Blueprint, request, jsonify). The boilerplate backend is FastAPI. Use APIRouter.

**BOILERPLATE DATABASE REFERENCE — USE THESE EXACT PATTERNS:**

Backend routes use FastAPI + SQLAlchemy. Here are the exact imports and patterns:

```python
# FILE: business/backend/routes/clients.py
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy import Column, String, DateTime, ForeignKey
from sqlalchemy.orm import Session, relationship
from datetime import datetime
from core.database import Base, get_db
import uuid

# 1. Define your model (inherits from Base)
class Client(Base):
    __tablename__ = "clients"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)
    industry = Column(String)
    employee_count = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# 2. Define your router
router = APIRouter()

# 3. CRUD routes using db: Session = Depends(get_db)
@router.get("/clients")
def list_clients(db: Session = Depends(get_db)):
    return db.query(Client).all()

@router.post("/clients", status_code=201)
def create_client(data: dict, db: Session = Depends(get_db)):
    client = Client(**data)
    db.add(client)
    db.commit()
    db.refresh(client)
    return client

@router.get("/clients/{client_id}")
def get_client(client_id: str, db: Session = Depends(get_db)):
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    return client

@router.put("/clients/{client_id}")
def update_client(client_id: str, data: dict, db: Session = Depends(get_db)):
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    for key, value in data.items():
        setattr(client, key, value)
    client.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(client)
    return client

@router.delete("/clients/{client_id}")
def delete_client(client_id: str, db: Session = Depends(get_db)):
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    db.delete(client)
    db.commit()
    return {"deleted": True}
```

**RULES FROM THE ABOVE REFERENCE:**
- Import: `from core.database import Base, get_db` — always this exact path
- Session injection: `db: Session = Depends(get_db)` — always this pattern in every route
- Query: `db.query(Model).filter(Model.id == id).first()` — not `.get()`, not a dict lookup
- Create: `db.add(obj)` → `db.commit()` → `db.refresh(obj)` — always all three
- Primary key: `Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))` — UUID string, never Integer autoincrement
- Timestamps: `Column(DateTime, default=datetime.utcnow)` — always on created_at/updated_at
- Router variable MUST be named `router` (not `bp`, not `blueprint`) — the auto-loader expects `router`

**BOILERPLATE AUTH REFERENCE — USE THESE EXACT PATTERNS:**

The boilerplate provides Auth0-based authentication. NEVER write your own auth. NEVER hardcode user IDs.

```python
# Backend: get the authenticated user
from core.rbac import get_current_user
from fastapi import Depends

# get_current_user returns:
# {
#   "sub": "auth0|abc123",   ← use this as user_id / consultant_id / owner_id
#   "email": "user@example.com",
#   "roles": {"user"},
#   "tenant_id": "myapp",
# }

@router.get("/clients")
async def list_clients(current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    user_id = current_user["sub"]   # This is the real user ID — NEVER hardcode this
    return db.query(Client).filter(Client.owner_id == user_id).all()

@router.post("/clients", status_code=201)
async def create_client(data: dict, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    data["owner_id"] = current_user["sub"]   # Inject real user ID before save
    client = Client(**data)
    db.add(client)
    db.commit()
    db.refresh(client)
    return client
```

**AUTH PROHIBITIONS:**
- NEVER write `consultant_id: 'consultant_1'` or any hardcoded user ID string
- NEVER write `# TODO: Get from auth context` — use `current_user["sub"]` directly
- NEVER roll your own JWT parsing — `get_current_user` handles it
- NEVER add `user_id` as a query parameter that the caller provides — get it from `current_user`

**Frontend: get the authenticated user**
```jsx
import { useAuth0 } from '@auth0/auth0-react';

export default function MyPage() {
  // ALWAYS destructure getAccessTokenSilently — it is NOT a method on user
  const { user, isLoading, getAccessTokenSilently } = useAuth0();

  // user.sub is the user ID (same as backend current_user["sub"])
  // user.email is the email

  const [formData, setFormData] = useState({
    name: '',
    // DO NOT hardcode owner_id here — send request without it,
    // the backend injects it from the JWT via current_user["sub"]
  });

  // CORRECT: call getAccessTokenSilently() directly (destructured above)
  const fetchData = async () => {
    const token = await getAccessTokenSilently();
    const response = await fetch('/api/something', {
      headers: { 'Authorization': `Bearer ${token}` }
    });
    // ...
  };

  // WRONG (never do this): user.getAccessTokenSilently() — method does not exist on user object
}
```

**AUTH0 TOKEN RULE:** `getAccessTokenSilently` MUST be destructured from `useAuth0()`.
- CORRECT: `const { user, getAccessTokenSilently } = useAuth0();` then `const token = await getAccessTokenSilently();`
- WRONG: `user.getAccessTokenSilently()` — `user` is a profile object, it has NO `getAccessTokenSilently` method

**VALID EXAMPLES:**
**FILE: business/frontend/pages/ClientDashboard.jsx**
**FILE: business/backend/routes/assessments.py**
**FILE: business/models/Client.js**
**FILE: business/services/ReportService.js**
**FILE: business/README-INTEGRATION.md**
**FILE: business/package.json**

**INVALID EXAMPLES (DO NOT OUTPUT):**
**FILE: business/components/ClientDashboard.jsx**
**FILE: business/routes/assessments.py**
**FILE: frontend/src/components/ClientList.jsx**
**FILE: backend/tests/test_clients.py**
**FILE: package.json**
**FILE: app/api/assessments.py** ← FORBIDDEN (use business/backend/routes/assessments.py)
**FILE: app/core/scoring.py** ← FORBIDDEN (use business/services/ScoringService.py)
**FILE: app/api/auth.py** ← FORBIDDEN (auth is handled by boilerplate core)
**FILE: tests/test_assessments.py** ← FORBIDDEN (tests are generated separately, not by you)
**FILE: src/components/Dashboard.jsx** ← FORBIDDEN (use business/frontend/pages/)
**FILE: business/frontend/app/assessments/page.tsx** ← FORBIDDEN (app router + .tsx — use business/frontend/pages/Assessments.jsx)
**FILE: business/frontend/app/page.tsx** ← FORBIDDEN (use business/frontend/pages/Dashboard.jsx)
**FILE: business/frontend/components/Navigation.tsx** ← FORBIDDEN (.tsx not allowed; components belong in business/frontend/pages/ or business/frontend/lib/)
**FILE: business/tests/test_clients.py** ← FORBIDDEN (tests are generated by the harness)
**FILE: business/backend/services/ScoringService.py** ← FORBIDDEN (use business/services/ScoringService.py)
**FILE: business/backend/__init__.py** ← FORBIDDEN (boilerplate internal, do not create)
**FILE: business/backend/app.py** ← FORBIDDEN (boilerplate internal, do not create)
**FILE: business/app/routers.py** ← FORBIDDEN (use business/backend/routes/)

**PRE-PROMPT CHECKLIST (MUST PASS BEFORE YOU OUTPUT):**
- All files are under `business/**`.
- Frontend pages are in `business/frontend/pages/` with `.jsx` extension (NOT app/, NOT .tsx).
- Backend routes are in `business/backend/routes/`.
- `business/README-INTEGRATION.md` is included.
- `business/package.json` is included.
- Every code block has a **FILE:** header.
- No unlabeled code fences.
- Scan every `.jsx` file you wrote: does ANY line contain `user.getAccessTokenSilently()`? If yes — fix it before outputting. Replace with `const { getAccessTokenSilently } = useAuth0();` at the top of the component and call `getAccessTokenSilently()` directly.
