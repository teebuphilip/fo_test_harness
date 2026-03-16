# CANONICAL CODE SKELETONS — USE THESE EXACTLY

These are real, working code patterns extracted from the production boilerplate.
**Your job is to substitute entity names and business fields — NOT to invent architecture.**
Copy the skeleton. Rename `Entity`/`entities` to your domain object. Add the business-specific columns and logic. Stop there.

---

## HARD PROHIBITIONS — INSTANT STATIC CHECK FAILURE

NEVER generate any of the following. These will fail automated validation and loop indefinitely:

| Forbidden | Reason |
|-----------|--------|
| `from flask import Blueprint` | Wrong framework. Backend is FastAPI. |
| `router = Blueprint(...)` | Flask pattern. Use `router = APIRouter()`. |
| `@router.route('/path', methods=['GET'])` | Flask decorator. Use `@router.get('/path')`. |
| `from flask import Flask, request, jsonify` | Flask. All of it. Wrong. |
| `.tsx` or `.ts` frontend files | Frontend is `.jsx` only. |
| `business/frontend/app/` paths | App Router is forbidden. Use `business/frontend/pages/`. |
| `user.getAccessTokenSilently()` | Not a method on the Auth0 user object. Destructure it from `useAuth0()`. |
| `import fetch from 'node-fetch'` | Use `import api from '../utils/api'` (pre-configured axios). |
| `db.execute("SELECT * FROM ...")` | Raw SQL. Use SQLAlchemy ORM: `db.query(Model).filter(...)`. |
| `from app.database import ...` | Wrong path. Use `from core.database import Base, get_db`. |
| `from app.auth import ...` | Wrong path. Use `from core.rbac import get_current_user`. |
| `sequential_id = max(ids) + 1` | Never generate sequential IDs manually. Use `Column(Integer, primary_key=True)`. |
| `data = {}` (in-memory dict storage) | Never store data in dicts. Always use SQLAlchemy + DB. |

---

## SKELETON 1 — BACKEND ROUTE FILE

**File location**: `business/backend/routes/entities.py`
*(Replace `entities` with your resource name — lowercase, plural, no spaces)*

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from core.database import get_db
from core.rbac import get_current_user
from services.EntityService import EntityService

router = APIRouter()

@router.get("/entities")
async def list_entities(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    return EntityService.list_all(db)

@router.post("/entities")
async def create_entity(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    return EntityService.create(payload, current_user["sub"], db)

@router.get("/entities/{entity_id}")
async def get_entity(
    entity_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    entity = EntityService.get(entity_id, db)
    if not entity:
        raise HTTPException(status_code=404, detail="Not found")
    return entity

@router.put("/entities/{entity_id}")
async def update_entity(
    entity_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    return EntityService.update(entity_id, payload, db)

@router.delete("/entities/{entity_id}")
async def delete_entity(
    entity_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    EntityService.delete(entity_id, db)
    return {"status": "deleted"}
```

**Rules for this file:**
- `router = APIRouter()` — no arguments, no `tags=`, no `prefix=`
- Every endpoint MUST have `db: Session = Depends(get_db)` AND `current_user: dict = Depends(get_current_user)`
- Decorators MUST be `@router.get`, `@router.post`, `@router.put`, `@router.delete`, `@router.patch` — nothing else
- Use `current_user["sub"]` as the owner/user identifier — do NOT hardcode user IDs

---

## SKELETON 2 — BACKEND MODEL FILE

**File location**: `business/models/Entity.py`
*(PascalCase class name, matches service import)*

```python
from sqlalchemy import Column, String, Integer, DateTime, Text, Float, Boolean
from core.database import Base
from datetime import datetime

class Entity(Base):
    __tablename__ = "entities"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(String, nullable=False)   # stores current_user["sub"]
    name = Column(String(255), nullable=False)
    status = Column(String(50), default="active")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Add business-specific columns here — Column types from sqlalchemy above
    # Example: description = Column(Text, nullable=True)
    # Example: score = Column(Float, nullable=True)
    # Example: is_active = Column(Boolean, default=True)
```

**Rules for this file:**
- `from core.database import Base` — exact import, do not change path
- `__tablename__` = lowercase plural snake_case (e.g. `"horse_profiles"`, `"membership_plans"`)
- `id = Column(Integer, primary_key=True, index=True)` — always this exact pattern
- `owner_id = Column(String, nullable=False)` — always include for multi-tenant data
- `created_at` — always include

---

## SKELETON 3 — BACKEND SERVICE FILE

**File location**: `business/services/EntityService.py`
*(PascalCase, matches route import)*

```python
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from models.Entity import Entity

class EntityService:

    @staticmethod
    def list_all(db: Session) -> List[Dict[str, Any]]:
        items = db.query(Entity).order_by(Entity.created_at.desc()).all()
        return [EntityService._to_dict(item) for item in items]

    @staticmethod
    def create(payload: dict, owner_id: str, db: Session) -> Dict[str, Any]:
        entity = Entity(
            owner_id=owner_id,
            name=payload["name"],
            # map additional payload fields to columns
        )
        db.add(entity)
        db.commit()
        db.refresh(entity)
        return EntityService._to_dict(entity)

    @staticmethod
    def get(entity_id: int, db: Session) -> Optional[Dict[str, Any]]:
        entity = db.query(Entity).filter(Entity.id == entity_id).first()
        if not entity:
            return None
        return EntityService._to_dict(entity)

    @staticmethod
    def update(entity_id: int, payload: dict, db: Session) -> Dict[str, Any]:
        entity = db.query(Entity).filter(Entity.id == entity_id).first()
        if not entity:
            return {"error": "Not found"}
        for key, value in payload.items():
            if hasattr(entity, key):
                setattr(entity, key, value)
        db.commit()
        db.refresh(entity)
        return EntityService._to_dict(entity)

    @staticmethod
    def delete(entity_id: int, db: Session) -> None:
        entity = db.query(Entity).filter(Entity.id == entity_id).first()
        if entity:
            db.delete(entity)
            db.commit()

    @staticmethod
    def _to_dict(entity: Entity) -> Dict[str, Any]:
        return {
            "id": entity.id,
            "owner_id": entity.owner_id,
            "name": entity.name,
            "status": entity.status,
            "created_at": entity.created_at.isoformat() if entity.created_at else None,
        }
```

**Rules for this file:**
- All methods `@staticmethod` — no `self`, no `cls`
- ORM queries: `db.query(Model).filter(...)` — no raw SQL strings
- Always `db.commit()` + `db.refresh(entity)` after write operations
- Private helpers prefixed with `_` (e.g. `_to_dict`, `_calculate_score`)

---

## SKELETON 4 — FRONTEND PAGE FILE

**File location**: `business/frontend/pages/Entities.jsx`
*(PascalCase filename, kebab-case auto-routes to `/dashboard/entities`)*

```jsx
import React, { useState, useEffect } from 'react';
import { useAuth0 } from '@auth0/auth0-react';
import api from '../utils/api';

export default function Entities() {
    const { user, getAccessTokenSilently } = useAuth0();
    const [entities, setEntities] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [formData, setFormData] = useState({ name: '' });

    useEffect(() => {
        fetchEntities();
    }, []);

    const fetchEntities = async () => {
        try {
            const token = await getAccessTokenSilently();
            const response = await api.get('/entities', {
                headers: { Authorization: `Bearer ${token}` }
            });
            setEntities(response.data);
        } catch (err) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    };

    const handleCreate = async (e) => {
        e.preventDefault();
        try {
            const token = await getAccessTokenSilently();
            const response = await api.post('/entities', formData, {
                headers: { Authorization: `Bearer ${token}` }
            });
            setEntities([...entities, response.data]);
            setFormData({ name: '' });
        } catch (err) {
            setError(err.message);
        }
    };

    const handleDelete = async (id) => {
        try {
            const token = await getAccessTokenSilently();
            await api.delete(`/entities/${id}`, {
                headers: { Authorization: `Bearer ${token}` }
            });
            setEntities(entities.filter(e => e.id !== id));
        } catch (err) {
            setError(err.message);
        }
    };

    if (loading) return <div className="p-4">Loading...</div>;
    if (error) return <div className="p-4 text-red-500">Error: {error}</div>;

    return (
        <div className="p-6">
            <h1 className="text-2xl font-bold mb-4">Entities</h1>

            <form onSubmit={handleCreate} className="mb-6 flex gap-2">
                <input
                    type="text"
                    value={formData.name}
                    onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                    placeholder="Name"
                    className="border rounded px-3 py-2 flex-1"
                    required
                />
                <button type="submit" className="bg-blue-600 text-white px-4 py-2 rounded">
                    Add
                </button>
            </form>

            <ul className="space-y-2">
                {entities.map(entity => (
                    <li key={entity.id} className="flex justify-between items-center border rounded p-3">
                        <span>{entity.name}</span>
                        <button
                            onClick={() => handleDelete(entity.id)}
                            className="text-red-500 hover:text-red-700"
                        >
                            Delete
                        </button>
                    </li>
                ))}
            </ul>
        </div>
    );
}
```

**Rules for this file:**
- `const { user, getAccessTokenSilently } = useAuth0()` — destructure BOTH from `useAuth0()`, never `user.getAccessTokenSilently()`
- `const token = await getAccessTokenSilently()` — always await, always in the async function body
- `Authorization: \`Bearer ${token}\`` — always this header format
- `import api from '../utils/api'` — always use pre-configured axios, never raw `fetch()`
- All state: `useState` — no class components
- Extension: `.jsx` always — never `.tsx`, never `.ts`
- Loading and error early returns before the main render

---

## SUBSTITUTION GUIDE

When implementing a feature:

1. **Name your resource** (e.g. "Horse Profile")
   - Route file: `business/backend/routes/horse_profiles.py` (snake_case plural)
   - Model file: `business/models/HorseProfile.py` (PascalCase)
   - Service file: `business/services/HorseProfileService.py` (PascalCase + Service suffix)
   - Page file: `business/frontend/pages/HorseProfiles.jsx` (PascalCase)

2. **Replace `Entity`/`entities`** with your resource name in all four files

3. **Add business columns** to the model — only `Column(...)` definitions

4. **Map payload fields** in the service `create()` and `update()` methods

5. **Add form fields** to the JSX that match the model columns

6. **Do not change** the import paths, decorator patterns, auth patterns, or ORM query patterns

That is the complete scope of your implementation work. Architecture is already decided.
