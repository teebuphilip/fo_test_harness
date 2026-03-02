**CRITICAL FILE PATH RULES (BOILERPLATE MODE):**
- Output files ONLY under `business/**`.
- REQUIRED: include `business/README-INTEGRATION.md`.
- REQUIRED: include `business/package.json`.
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

**PRE-PROMPT CHECKLIST (MUST PASS BEFORE YOU OUTPUT):**
- All files are under `business/**`.
- Frontend pages are in `business/frontend/pages/`.
- Backend routes are in `business/backend/routes/`.
- `business/README-INTEGRATION.md` is included.
- `business/package.json` is included.
- Every code block has a **FILE:** header.
- No unlabeled code fences.
