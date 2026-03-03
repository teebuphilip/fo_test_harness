**PREVIOUS QA ITERATION — DEFECTS TO FIX:**
ChatGPT QA reported the following defects. Fix ALL of them.

**CRITICAL RULES FOR DEFECT FIXES:**
1. **Fix ONLY the reported defects** - Do NOT change unrelated code
2. **Output ONLY defect files** - Only output files explicitly referenced in the DEFECTS TO FIX section. The harness carries all other files forward automatically. Do NOT output non-defect files.
3. **No scope changes** - Do NOT add new features or functionality
4. **No over-engineering** - Fix exactly what QA asks, nothing more
5. **Follow the Fix: field** - Each defect includes a `Fix:` field with the exact change required. Apply it literally. Do not interpret or substitute.

**BOILERPLATE DATA LAYER — MANDATORY FIX PATTERNS:**
If any defect mentions "in-memory", "mock data", "hardcoded", "dict storage", or "use database/ORM":
- NEVER use Python dicts as storage (`reports_db = {}`, `clients_db = {}`, `data = []` etc.)
- NEVER return hardcoded/static data from route handlers
- NEVER use `len(db) + 1` for ID generation — use `import uuid; str(uuid.uuid4())`
- NEVER use Flask (Blueprint, request, jsonify). Backend is FastAPI. Use APIRouter.
- For frontend: ALL data must come from `/api/` fetch calls — no hardcoded arrays or objects

**EXACT FIX PATTERN FOR DB DEFECTS — replace in-memory storage with this:**
```python
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy import Column, String, DateTime
from sqlalchemy.orm import Session
from datetime import datetime
from core.database import Base, get_db
import uuid

class MyModel(Base):
    __tablename__ = "my_models"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

router = APIRouter()  # MUST be named 'router', not 'bp' or 'blueprint'

@router.get("/items")
def list_items(db: Session = Depends(get_db)):
    return db.query(MyModel).all()

@router.post("/items", status_code=201)
def create_item(data: dict, db: Session = Depends(get_db)):
    item = MyModel(**data)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item

@router.get("/items/{item_id}")
def get_item(item_id: str, db: Session = Depends(get_db)):
    item = db.query(MyModel).filter(MyModel.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Not found")
    return item
```

**AUTH CONTEXT FIX PATTERN:**
If any defect mentions "hardcoded consultant_id", "hardcoded user id", "hardcoded owner_id", or "get from auth context":
- Backend routes: Add `current_user: dict = Depends(get_current_user)` as a parameter (import from `core.rbac`). Use `current_user["sub"]` as the user/owner/consultant ID. Never accept user_id as a caller-provided query param.
- Frontend (JSX): Remove the hardcoded value from formData entirely. The backend injects the user ID from the JWT. If you must display it, use `import { useAuth0 } from '@auth0/auth0-react'; const { user } = useAuth0();` and `user.sub`.
- Do NOT use `'consultant_1'`, `'current_user'`, or any other hardcoded string placeholder.
- Do NOT add a `// TODO:` comment — implement the actual pattern.

**DEFECTS TO FIX:**
{{previous_defects}}

**REMEMBER:** Output ONLY the files referenced in the DEFECTS TO FIX section above. Nothing else.
