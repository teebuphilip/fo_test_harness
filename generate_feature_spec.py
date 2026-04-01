#!/usr/bin/env python3
"""
generate_feature_spec.py — Generate an HLD/LLD spec for a single feature
before it enters the build harness.

Flow:
  Round 1 — GPT drafts HLD + LLD from scoped intake
  Round 2 — Claude reviews GPT draft, accepts or overrides, flags CONFLICT:
  Round 3 — Claude closes: resolves all conflicts as he sees fit using frozen
             architectural decisions as authority. GPT gets no vote on resolution.
             Only HALT if Claude himself writes UNRESOLVABLE:.
  Termination after round 2 if no conflicts (round 3 skipped entirely).

Output:
  <output_dir>/<stem>_spec.txt       — clean spec, consumed by feature_adder --spec-file
  <output_dir>/<stem>_spec_HALT.json — written only on HALT (exit non-zero)
  <output_dir>/<stem>_spec_rounds.json — full audit trail

Usage:
  python generate_feature_spec.py \
    --intake intake/intake_runs/invoicetool/invoicetool_feature_vendor_invoices.json \
    --output-dir intake/intake_runs/invoicetool/

  # Both ANTHROPIC_API_KEY and OPENAI_API_KEY must be set in environment.

# TODO: Extract FROZEN_ARCHITECTURAL_DECISIONS and GOLDEN_EXAMPLES into
#       directives/build_governance.py and import from there.
#       Both fo_test_harness.py and this script currently duplicate them.
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

import requests

# ============================================================
# CONFIGURATION — mirrors fo_test_harness.py Config
# ============================================================

class Config:
    ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY')
    OPENAI_API_KEY    = os.getenv('OPENAI_API_KEY')

    ANTHROPIC_API = 'https://api.anthropic.com/v1/messages'
    OPENAI_API    = 'https://api.openai.com/v1/chat/completions'

    # Claude is the builder/closer — always use the same model as harness
    CLAUDE_MODEL  = 'claude-sonnet-4-20250514'
    GPT_MODEL     = 'gpt-4o-mini'

    CLAUDE_MAX_TOKENS = 4096   # Spec output is small — no need for 16k
    GPT_MAX_TOKENS    = 4096

    MAX_RETRIES     = 6
    RETRY_SLEEP     = 5
    RETRY_SLEEP_429 = 60
    REQUEST_TIMEOUT = 120


# ============================================================
# COLOR OUTPUT — mirrors fo_test_harness.py
# ============================================================

class Colors:
    BLUE   = '\033[94m'
    CYAN   = '\033[96m'
    GREEN  = '\033[92m'
    YELLOW = '\033[93m'
    RED    = '\033[91m'
    BOLD   = '\033[1m'
    END    = '\033[0m'

def print_header(text):
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*70}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{text}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'='*70}{Colors.END}\n")

def print_success(text): print(f"{Colors.GREEN}✓ {text}{Colors.END}")
def print_error(text):   print(f"{Colors.RED}✗ {text}{Colors.END}")
def print_warning(text): print(f"{Colors.YELLOW}⚠ {text}{Colors.END}")
def print_info(text):    print(f"{Colors.CYAN}→ {text}{Colors.END}")


# ============================================================
# FROZEN ARCHITECTURAL DECISIONS
# TODO: move to directives/build_governance.py
# Duplicated from fo_test_harness.py — keep in sync until refactored.
# ============================================================

FROZEN_ARCHITECTURAL_DECISIONS = """
## FROZEN ARCHITECTURAL DECISIONS — NON-NEGOTIABLE
These decisions are already made. Do not deviate. Do not invent alternatives.

### Service layer
- All service methods are synchronous unless the feature spec explicitly requires async
- Service methods raise HTTPException directly — no custom exception classes
- Every service method that touches the DB accepts `db: Session` as first argument

### Error handling
- All error responses: `return JSONResponse({"error": "message"}, status_code=N)`
- 400 for bad input, 401 for auth failure, 403 for permission, 404 for not found, 500 for server error
- Never return bare strings or unstructured error bodies

### Auth
- Always use `Depends(get_current_user)` on protected routes — never custom middleware
- User identity: `current_user["sub"]` — never hardcode a user ID
- Never implement your own JWT logic — boilerplate handles it

### Data types
- All monetary values stored as integers (cents) — never floats
- All timestamps stored as UTC — never naive datetimes
- All IDs are strings (UUID4) — never integers for primary keys unless intake spec requires it

### Schema naming convention — non-negotiable
- Request schema class name: `XCreate` — NEVER `XCreateRequest`, `XRequest`, `XInput`
- Response schema class name: `XResponse` — NEVER `XResponseModel`, `XOut`, `XOutput`
- Update schema class name: `XUpdate` — NEVER `XUpdateRequest`, `XPatch`
- The route `response_model=XResponse` and `payload: XCreate` MUST use these exact suffixes
- The schema file MUST define classes with exactly these names — no alternatives

### Cross-file contracts
- Route request/response schemas MUST match schema definitions exactly
- Service return types MUST match route `response_model` exactly
- Frontend fetch() payload MUST match backend request schema exactly

### Route structure
- Function-based routes only — no class-based views
- Route files import router from fastapi — no app-level route registration
- Every route file exports exactly one APIRouter instance named `router`

### Frontend
- .jsx files only — never .tsx or .ts
- pages/ router only — never app/ router
- All API calls via fetch() with Authorization Bearer token from Auth0
- No inline styles — Tailwind classes only

### Standard model fields — always include, never remove
- Every SQLAlchemy model MUST include: `status`, `created_at`, `updated_at`
- These are infrastructure fields — do NOT remove them even if a QA report flags them as scope creep
- `status = Column(String(50), default="active")` — always present
- `created_at = Column(DateTime(timezone=True), server_default=func.now())` — always present
- `updated_at = Column(DateTime(timezone=True), onupdate=func.now())` — always present

### File count constraints
- Minimize number of files — prefer adding to existing files over creating new ones
- Only create a new file if it represents a new domain entity OR the feature spec explicitly requires it
- Maximum files per feature: 1 route file, 1 service file, 1 model file, 1 schema file, 1 frontend page
- Do NOT create helper files, utility files, or additional services unless strictly required

### Route and file naming — CRITICAL
- Backend route file names MUST use underscores, NEVER hyphens: `stable_updates.py` NOT `stable-updates.py`
- Python modules cannot contain hyphens — a hyphenated filename will fail to import
- The frontend fetch URL MUST match the underscore filename: `fetch('/api/stable_updates')` NOT `fetch('/api/stable-updates')`
- This applies to ALL route files

### Dependencies
- Never add a dependency that duplicates boilerplate capability
- Never add a dependency for something Python stdlib handles
- Never pin to a specific version unless the feature spec requires it

## BASELINE DEPENDENCIES — already available, do not re-add

### Python (requirements.txt baseline — already installed)
fastapi>=0.109.0, uvicorn[standard]>=0.27.0,
pydantic>=2.5.0, email-validator>=2.0.0,
python-multipart>=0.0.6, python-dotenv>=1.0.0,
sqlalchemy>=2.0.0, alembic>=1.13.0,
PyJWT>=2.8.0, cryptography>=41.0.0,
stripe>=7.0.0, requests>=2.31.0, httpx>=0.24.1,
meilisearch>=0.21.0, anthropic>=0.28.0, openai>=1.30.0,
sentry-sdk[fastapi]>=1.40.0,
praw>=7.7.0, tweepy>=4.14.0, linkedin-api>=2.2.0,
facebook-sdk>=3.1.0, ratelimit>=2.2.1

### JavaScript (package.json baseline — already installed)
react@^18.2.0, react-dom@^18.2.0, react-router-dom@^6.21.0,
axios@^1.6.0, @auth0/auth0-react@^2.2.4, react-scripts@5.0.1,
tailwindcss@^3.4.0, autoprefixer@^10.4.16, postcss@^8.4.32
"""


# ============================================================
# GOLDEN EXAMPLES
# TODO: move to directives/build_governance.py
# Duplicated from fo_test_harness.py — keep in sync until refactored.
# ============================================================

GOLDEN_EXAMPLES = """
## REFERENCE IMPLEMENTATION — follow these patterns exactly

These are real files from a production build in this stack.
Copy the structure, naming conventions, import patterns, and error handling exactly.
Replace the domain logic with the feature you are building.

### Model (business/models/example.py):
```python
from sqlalchemy import Column, String, DateTime
from sqlalchemy.sql import func
from core.database import Base
import uuid

class ExampleModel(Base):
    __tablename__ = "examples"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    owner_id = Column(String, nullable=False, index=True)
    name = Column(String, nullable=False)
    status = Column(String(50), default="active")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
```

### Schema (business/schemas/example_schema.py):
```python
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class ExampleCreate(BaseModel):
    name: str

class ExampleResponse(BaseModel):
    id: str
    owner_id: str
    name: str
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True
```

### Service (business/services/example_service.py):
```python
from sqlalchemy.orm import Session
from fastapi import HTTPException
from business.models.example import ExampleModel
from business.schemas.example_schema import ExampleCreate

class ExampleService:
    @staticmethod
    def list_for_user(db: Session, user_id: str) -> list[ExampleModel]:
        return db.query(ExampleModel).filter(
            ExampleModel.owner_id == user_id
        ).all()

    @staticmethod
    def create(db: Session, payload: ExampleCreate, user_id: str) -> ExampleModel:
        record = ExampleModel(owner_id=user_id, name=payload.name)
        db.add(record)
        db.commit()
        db.refresh(record)
        return record
```

### Route (business/backend/routes/example_routes.py):
```python
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from core.database import get_db
from core.rbac import get_current_user
from business.services.example_service import ExampleService
from business.schemas.example_schema import ExampleCreate, ExampleResponse

router = APIRouter()

@router.get("/examples", response_model=list[ExampleResponse])
def list_examples(db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    return ExampleService.list_for_user(db, current_user["sub"])

@router.post("/examples", response_model=ExampleResponse)
def create_example(payload: ExampleCreate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    return ExampleService.create(db, payload, current_user["sub"])
```

### Frontend page (business/frontend/pages/ExamplePage.jsx):
```jsx
import { useState, useEffect } from "react";
import { useAuth0 } from "@auth0/auth0-react";

export default function ExamplePage() {
  const { getAccessTokenSilently } = useAuth0();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => { fetchItems(); }, []);

  async function fetchItems() {
    try {
      const token = await getAccessTokenSilently();
      const res = await fetch("/api/examples", {
        headers: { Authorization: `Bearer ${token}` }
      });
      setItems(await res.json());
    } catch (err) {
      console.error("Failed to fetch items:", err);
    } finally {
      setLoading(false);
    }
  }

  if (loading) return <div className="p-4">Loading...</div>;
  return (
    <div className="p-4">
      <h1 className="text-2xl font-bold mb-4">Examples</h1>
      <ul className="space-y-2">
        {items.map(item => (
          <li key={item.id} className="p-3 border rounded">{item.name}</li>
        ))}
      </ul>
    </div>
  );
}
```
"""


# ============================================================
# API CLIENTS — same retry/timeout pattern as fo_test_harness.py
# ============================================================

class ClaudeClient:
    """Claude — builder/closer. Wins all ties."""

    def __init__(self):
        if not Config.ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY not set")

    def call(self, prompt: str, max_tokens: int = None) -> str:
        if max_tokens is None:
            max_tokens = Config.CLAUDE_MAX_TOKENS

        payload = {
            "model":      Config.CLAUDE_MODEL,
            "max_tokens": max_tokens,
            "messages":   [{"role": "user", "content": prompt}]
        }
        headers = {
            "content-type":      "application/json",
            "x-api-key":         Config.ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
        }

        last_error = None
        for attempt in range(1, Config.MAX_RETRIES + 1):
            try:
                ts = datetime.now()
                print_info(f"[{ts.strftime('%H:%M:%S')}] → Claude API request sent (attempt {attempt})")
                r = requests.post(Config.ANTHROPIC_API, json=payload, headers=headers,
                                  timeout=Config.REQUEST_TIMEOUT)
                if r.status_code in (400, 401, 403):
                    r.raise_for_status()
                if r.status_code in (429, 500, 529):
                    wait = Config.RETRY_SLEEP * attempt
                    print_warning(f"Claude {r.status_code} — retry {attempt}/{Config.MAX_RETRIES} in {wait}s")
                    time.sleep(wait)
                    last_error = f"HTTP {r.status_code}"
                    continue
                r.raise_for_status()
                data = r.json()
                text = data['content'][0]['text']
                usage = data.get('usage', {})
                cost = _estimate_claude_cost(usage)
                print_success(f"Claude response received ({len(text)} chars) cost≈${cost:.4f}")
                return text
            except requests.exceptions.Timeout:
                print_warning(f"Claude timeout — retry {attempt}/{Config.MAX_RETRIES}")
                last_error = "Timeout"
                time.sleep(Config.RETRY_SLEEP)
            except requests.exceptions.RequestException as e:
                print_warning(f"Claude error — retry {attempt}/{Config.MAX_RETRIES}: {e}")
                last_error = str(e)
                time.sleep(Config.RETRY_SLEEP)

        raise RuntimeError(f"Claude API failed after {Config.MAX_RETRIES} attempts: {last_error}")


class ChatGPTClient:
    """GPT — architect/reviewer. Flags conflicts, defers to Claude on ties."""

    def __init__(self):
        if not Config.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY not set")

    def call(self, prompt: str, system: str = None, max_tokens: int = None) -> str:
        if max_tokens is None:
            max_tokens = Config.GPT_MAX_TOKENS

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model":      Config.GPT_MODEL,
            "max_tokens": max_tokens,
            "messages":   messages
        }
        headers = {
            "Content-Type":  "application/json",
            "Authorization": f"Bearer {Config.OPENAI_API_KEY}"
        }

        last_error = None
        for attempt in range(1, Config.MAX_RETRIES + 1):
            try:
                ts = datetime.now()
                print_info(f"[{ts.strftime('%H:%M:%S')}] → ChatGPT API request sent (attempt {attempt})")
                r = requests.post(Config.OPENAI_API, json=payload, headers=headers,
                                  timeout=Config.REQUEST_TIMEOUT)
                if r.status_code in (400, 401, 403):
                    r.raise_for_status()
                if r.status_code in (429, 500, 529):
                    wait = Config.RETRY_SLEEP_429 if r.status_code == 429 else Config.RETRY_SLEEP * attempt
                    print_warning(f"ChatGPT {r.status_code} — retry {attempt}/{Config.MAX_RETRIES} in {wait}s")
                    time.sleep(wait)
                    last_error = f"HTTP {r.status_code}"
                    continue
                r.raise_for_status()
                data = r.json()
                text = data['choices'][0]['message']['content']
                usage = data.get('usage', {})
                cost = _estimate_gpt_cost(usage)
                print_success(f"ChatGPT response received ({len(text)} chars) cost≈${cost:.4f}")
                return text
            except requests.exceptions.Timeout:
                print_warning(f"ChatGPT timeout — retry {attempt}/{Config.MAX_RETRIES}")
                last_error = "Timeout"
                time.sleep(Config.RETRY_SLEEP)
            except requests.exceptions.RequestException as e:
                print_warning(f"ChatGPT error — retry {attempt}/{Config.MAX_RETRIES}: {e}")
                last_error = str(e)
                time.sleep(Config.RETRY_SLEEP)

        raise RuntimeError(f"ChatGPT API failed after {Config.MAX_RETRIES} attempts: {last_error}")


# ============================================================
# COST HELPERS
# ============================================================

def _estimate_claude_cost(usage: dict) -> float:
    # claude-sonnet-4: $3/1M input, $15/1M output (approximate)
    inp = usage.get('input_tokens', 0)
    out = usage.get('output_tokens', 0)
    return (inp * 3 + out * 15) / 1_000_000

def _estimate_gpt_cost(usage: dict) -> float:
    # gpt-4o-mini: $0.15/1M input, $0.60/1M output (approximate)
    inp = usage.get('prompt_tokens', 0)
    out = usage.get('completion_tokens', 0)
    return (inp * 0.15 + out * 0.60) / 1_000_000


# ============================================================
# PROMPT BUILDERS
# ============================================================

GOVERNANCE_BLOCK = f"""
{FROZEN_ARCHITECTURAL_DECISIONS}

{GOLDEN_EXAMPLES}
""".strip()


def build_gpt_round1_prompt(intake: dict) -> str:
    feature = _extract_feature_name(intake)
    classification = intake.get('_phase_context', {}).get('classification', 'UNKNOWN')
    already_built = intake.get('_phase_context', {}).get('already_built_features', [])
    do_not_regen = intake.get('_phase_context', {}).get('do_not_regenerate', [])

    return f"""
You are a senior software architect. Your job is to write a precise HLD and LLD
for a single feature that will be built by Claude using the stack below.

You MUST follow the frozen architectural decisions and reference patterns exactly.
Do not invent alternatives. Do not deviate from naming conventions.

{GOVERNANCE_BLOCK}

============================================================
SCOPED INTAKE FOR THIS FEATURE
============================================================
Feature: {feature}
Classification: {classification}
Already built (do not touch): {json.dumps(already_built)}
Files that must not be regenerated: {json.dumps(do_not_regen[:10])}{"..." if len(do_not_regen) > 10 else ""}

Full intake JSON:
{json.dumps(intake, indent=2)}

============================================================
YOUR OUTPUT — write exactly this structure, no more:
============================================================

FEATURE: {feature}
CLASSIFICATION: {classification}

HLD:
- <3-5 bullet points describing what this feature does at a high level>

LLD:
MODEL: business/models/<name>.py — fields: <list key fields including status/created_at/updated_at>
SCHEMA: business/schemas/<name>_schema.py — classes: <XCreate, XResponse, XUpdate if needed>
SERVICE: business/services/<name>_service.py — methods: <list static methods with signatures>
ROUTE: business/backend/routes/<name>_routes.py — endpoints: <METHOD /path (request->response)>
FRONTEND: business/frontend/pages/<Name>Page.jsx — component: <brief description>

NEW_DEPENDENCIES: <none | package==version if strictly required>

AMBIGUITIES:
- <list any genuine ambiguities in the intake — or write NONE>

Do not write any code. Write the spec only.
Flag any item that violates the frozen architectural decisions with:
ARCH_VIOLATION: <what and why>
""".strip()


def build_claude_round2_prompt(intake: dict, gpt_draft: str) -> str:
    feature = _extract_feature_name(intake)

    return f"""
You are the builder. You will implement this feature in the next step.
Your job RIGHT NOW is to review the architect's HLD/LLD draft and produce
the final agreed spec.

Rules:
- Accept everything that is correct and compliant with the frozen architectural decisions.
- Override anything that violates the frozen decisions. Prefix overrides with: OVERRIDE:
- If you find a genuine unresolvable conflict that would block the build, prefix it with: CONFLICT:
- Claude wins all ties — if in doubt, keep your version.
- Do NOT write any code. Write the spec only.

{GOVERNANCE_BLOCK}

============================================================
SCOPED INTAKE
============================================================
{json.dumps(intake, indent=2)}

============================================================
ARCHITECT DRAFT (GPT Round 1)
============================================================
{gpt_draft}

============================================================
YOUR OUTPUT — produce the final spec in this exact format:
============================================================

FEATURE: {feature}
CLASSIFICATION: <value>

HLD:
- <accepted or overridden bullets>

LLD:
MODEL: <file> — fields: <list>
SCHEMA: <file> — classes: <list>
SERVICE: <file> — methods: <list>
ROUTE: <file> — endpoints: <list>
FRONTEND: <file> — component: <description>

NEW_DEPENDENCIES: <none | package if strictly required>

OVERRIDES_APPLIED: <NONE | list what you changed from GPT draft and why>

CONFLICTS: <NONE | CONFLICT: description of unresolvable issue>
""".strip()


def build_claude_round3_close_prompt(intake: dict, gpt_draft: str, claude_review: str, conflicts: list) -> str:
    """
    Claude closes the spec himself. He reads his own conflicts from round 2,
    resolves them using the frozen architectural decisions as sole authority,
    and writes the final spec. GPT gets no vote on resolution.
    Only HALT if Claude himself writes UNRESOLVABLE:.
    """
    feature = _extract_feature_name(intake)

    return f"""
You are the builder. In round 2 you flagged the following conflicts with the
architect's draft. Now resolve them yourself using the frozen architectural
decisions as your sole authority. You do not need GPT's input.

Resolution rules:
- Use FROZEN_ARCHITECTURAL_DECISIONS as the final word on all disputes.
- If the conflict is about naming, patterns, or structure — frozen decisions win.
- If the conflict is about business logic ambiguity — make the simplest defensible choice.
- Only write UNRESOLVABLE: if the conflict is a genuine logical impossibility
  (e.g. two requirements that directly contradict each other with no valid middle ground).
  Do NOT write UNRESOLVABLE: just because something is unclear — make a decision.

{GOVERNANCE_BLOCK}

============================================================
FEATURE: {feature}
============================================================

ORIGINAL ARCHITECT DRAFT (GPT Round 1):
{gpt_draft}

YOUR ROUND 2 REVIEW:
{claude_review}

CONFLICTS YOU FLAGGED:
{chr(10).join(f'- {c}' for c in conflicts)}

============================================================
OUTPUT — final clean spec. No more rounds after this.
============================================================

FEATURE: {feature}
CLASSIFICATION: <value>

HLD:
- <bullets>

LLD:
MODEL: <file> — fields: <list>
SCHEMA: <file> — classes: <list>
SERVICE: <file> — methods: <list>
ROUTE: <file> — endpoints: <list>
FRONTEND: <file> — component: <description>

NEW_DEPENDENCIES: <none | package if strictly required>

OVERRIDES_APPLIED: <NONE | list what changed from GPT draft>

CONFLICTS_RESOLVED: <for each conflict you flagged: RESOLVED: summary → how you resolved it>

Or if genuinely impossible:
UNRESOLVABLE: <specific logical contradiction that cannot be resolved>
""".strip()


# ============================================================
# HELPERS
# ============================================================

def _extract_feature_name(intake: dict) -> str:
    return (
        intake.get('_phase_context', {}).get('feature')
        or intake.get('_mini_spec', {}).get('entity')
        or intake.get('startup_idea_id', 'unknown')
    )

def _extract_conflicts(text: str) -> list:
    """Pull all CONFLICT: lines from Claude's review."""
    conflicts = []
    for line in text.splitlines():
        line = line.strip()
        if line.upper().startswith('CONFLICT:'):
            conflicts.append(line[len('CONFLICT:'):].strip())
    return conflicts

def _has_unresolvable(text: str) -> bool:
    return 'UNRESOLVABLE:' in text.upper()

def _write_halt(out_path: Path, reason: str, rounds: dict):
    halt = {
        "status": "HALT",
        "reason": reason,
        "rounds": rounds,
        "timestamp": datetime.now().isoformat()
    }
    out_path.write_text(json.dumps(halt, indent=2))
    print_error(f"HALT written: {out_path}")


# ============================================================
# MAIN SPEC GENERATION LOGIC
# ============================================================

def generate_spec(intake_path: Path, output_dir: Path) -> int:
    """
    Run the GPT→Claude→(optional GPT resolve)→Claude close spec generation.

    Returns 0 on success, 1 on HALT.
    """
    # Load intake
    with open(intake_path) as f:
        intake = json.load(f)

    feature = _extract_feature_name(intake)
    stem = intake_path.stem
    spec_out   = output_dir / f"{stem}_spec.txt"
    halt_out   = output_dir / f"{stem}_spec_HALT.json"
    rounds_log = output_dir / f"{stem}_spec_rounds.json"

    print_header(f"generate_feature_spec — {feature}")
    print_info(f"Intake:     {intake_path}")
    print_info(f"Output:     {spec_out}")

    # Init clients
    gpt    = ChatGPTClient()
    claude = ClaudeClient()

    rounds: dict = {}
    total_cost = 0.0

    # ── Round 1: GPT drafts HLD/LLD ──────────────────────────────────────────
    print_header("Round 1 — GPT drafts HLD/LLD")
    r1_prompt = build_gpt_round1_prompt(intake)
    gpt_draft = gpt.call(r1_prompt)
    rounds['round1_gpt'] = gpt_draft
    print_info(f"GPT draft ({len(gpt_draft)} chars)")

    # ── Round 2: Claude reviews, accepts or overrides ─────────────────────────
    print_header("Round 2 — Claude reviews GPT draft")
    r2_prompt = build_claude_round2_prompt(intake, gpt_draft)
    claude_review = claude.call(r2_prompt)
    rounds['round2_claude'] = claude_review
    print_info(f"Claude review ({len(claude_review)} chars)")

    conflicts = _extract_conflicts(claude_review)

    if not conflicts:
        # No conflicts — Claude's round 2 output IS the final spec
        print_success("No conflicts — Claude round 2 output is final spec")
        spec_text = _build_final_spec_text(claude_review, rounds={
            'round': 2,
            'gpt_draft': gpt_draft,
            'claude_review': claude_review,
        })
        spec_out.write_text(spec_text)
        rounds_log.write_text(json.dumps(rounds, indent=2))
        print_success(f"Spec written: {spec_out}")
        print_info(f"Rounds log:   {rounds_log}")
        return 0

    # ── Round 3: Claude closes — resolves conflicts himself ───────────────────
    print_header(f"Round 3 — Claude closes, resolves {len(conflicts)} conflict(s) himself")
    for c in conflicts:
        print_warning(f"  CONFLICT: {c}")

    r3_prompt = build_claude_round3_close_prompt(intake, gpt_draft, claude_review, conflicts)
    claude_final = claude.call(r3_prompt)
    rounds['round3_claude_close'] = claude_final

    if _has_unresolvable(claude_final):
        # Extract the UNRESOLVABLE line for the halt reason
        unresolvable_lines = [
            line.strip() for line in claude_final.splitlines()
            if line.strip().upper().startswith('UNRESOLVABLE:')
        ]
        reason = (
            f"Claude declared unresolvable conflict in round 3 close. "
            f"Detail: {' | '.join(unresolvable_lines)}"
        )
        print_error(reason)
        _write_halt(halt_out, reason, rounds)
        rounds_log.write_text(json.dumps(rounds, indent=2))
        return 1

    # Claude closed it — write final spec
    spec_text = _build_final_spec_text(claude_final, rounds={
        'round': 3,
        'gpt_draft': gpt_draft,
        'claude_review': claude_review,
        'claude_close': claude_final,
    })
    spec_out.write_text(spec_text)
    rounds_log.write_text(json.dumps(rounds, indent=2))
    print_success(f"Spec written: {spec_out}")
    print_info(f"Rounds log:   {rounds_log}")
    return 0


def _build_final_spec_text(spec_body: str, rounds: dict) -> str:
    """
    Wrap the final spec body with a header block for traceability.
    This is the file consumed by feature_adder --spec-file.
    """
    header = (
        f"# FEATURE SPEC — generated by generate_feature_spec.py\n"
        f"# Rounds: {rounds.get('round', '?')}\n"
        f"# Generated: {datetime.now().isoformat()}\n"
        f"# DO NOT EDIT — re-run generate_feature_spec.py to regenerate\n"
        f"{'='*60}\n\n"
    )
    return header + spec_body.strip() + "\n"


# ============================================================
# CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description='generate_feature_spec.py — GPT→Claude HLD/LLD spec generator',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python generate_feature_spec.py \\
    --intake intake/intake_runs/invoicetool/invoicetool_feature_vendor_invoices.json

  python generate_feature_spec.py \\
    --intake intake/intake_runs/invoicetool/invoicetool_feature_vendor_invoices.json \\
    --output-dir intake/intake_runs/invoicetool/specs/
        """
    )
    parser.add_argument(
        '--intake', required=True,
        help='Path to scoped feature intake JSON (output of feature_adder.py)'
    )
    parser.add_argument(
        '--output-dir', default=None,
        help='Directory to write spec files (default: same dir as intake)'
    )

    args = parser.parse_args()

    intake_path = Path(args.intake)
    if not intake_path.exists():
        print_error(f"Intake not found: {intake_path}")
        sys.exit(1)

    output_dir = Path(args.output_dir) if args.output_dir else intake_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    # Validate API keys
    if not Config.ANTHROPIC_API_KEY:
        print_error("ANTHROPIC_API_KEY not set")
        sys.exit(1)
    if not Config.OPENAI_API_KEY:
        print_error("OPENAI_API_KEY not set")
        sys.exit(1)

    exit_code = generate_spec(intake_path, output_dir)

    if exit_code == 0:
        # Print the --spec-file path so shell scripts can capture it
        stem = intake_path.stem
        spec_path = output_dir / f"{stem}_spec.txt"
        print(f"\nSPEC_FILE={spec_path}")
    else:
        print_error("HALT — manual review required before proceeding to harness")

    sys.exit(exit_code)


if __name__ == '__main__':
    main()
