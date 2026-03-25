#!/usr/bin/env python3
"""
FO Test Harness v2 - BUILD → QA → DEPLOY Orchestration
Orchestrates Claude (tech/builder) and ChatGPT (QA/validator)

USAGE:
  ./fo_test_harness.py <intake_file> <build_governance_zip> [--block-a] [--deploy]

DEFAULTS:
  Block:    B (Tier 2)   — pass --block-a for Tier 1
  Deploy:   NO           — pass --deploy to trigger deployment

OUTPUT:
  ./fo_harness_runs/{startup_id}_{block}_{timestamp}/   ← run directory
  ./fo_harness_runs/{startup_id}_{block}_{timestamp}.zip ← deliverable ZIP (no-deploy mode)
"""

import os
import sys
import json
import re
import time
import copy
import zipfile
import argparse
import hashlib
import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, Tuple
import requests

# ============================================================
# BUILD PROMPT CONSTANTS — injected into every build call
# FROZEN_ARCHITECTURAL_DECISIONS + SEEDED_DEPENDENCIES go into
# governance_section (cacheable — paid once per run, not per iter).
# GOLDEN_EXAMPLES goes into governance_section (same reason).
# PRE_OUTPUT_CHECKLIST goes into dynamic_section (last instruction
# Claude reads before generating — must stay per-iteration).
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
- This applies to ALL route files: `horse_details.py`, `race_entries.py`, `stable_updates.py` etc.

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

### Do NOT add to requirements.txt — these are Python stdlib, not external packages:
uuid, os, json, re, datetime, typing, pathlib, collections, itertools,
functools, math, hashlib, base64, time, sys, io, copy

### JavaScript (package.json baseline — already installed)
react@^18.2.0, react-dom@^18.2.0, react-router-dom@^6.21.0,
axios@^1.6.0, @auth0/auth0-react@^2.2.4, react-scripts@5.0.1,
tailwindcss@^3.4.0, autoprefixer@^10.4.16, postcss@^8.4.32

### Only add a new dependency if ALL three are true:
1. The feature spec explicitly requires a capability not in the baseline
2. No baseline package provides that capability
3. You can name the exact import you need from that package
"""

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
        record = ExampleModel(
            owner_id=user_id,
            name=payload.name,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return record
```

### Route (business/backend/routes/example_routes.py):
```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from core.database import get_db
from core.rbac import get_current_user
from business.models.example import ExampleModel
from business.services.example_service import ExampleService
from business.schemas.example_schema import ExampleCreate, ExampleResponse

router = APIRouter()

@router.get("/examples", response_model=list[ExampleResponse])
def list_examples(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    return ExampleService.list_for_user(db, current_user["sub"])

@router.post("/examples", response_model=ExampleResponse)
def create_example(
    payload: ExampleCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
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

  useEffect(() => {
    fetchItems();
  }, []);

  async function fetchItems() {
    try {
      const token = await getAccessTokenSilently();
      const res = await fetch("/api/examples", {
        headers: { Authorization: `Bearer ${token}` }
      });
      const data = await res.json();
      setItems(data);
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
          <li key={item.id} className="p-3 border rounded">
            {item.name}
          </li>
        ))}
      </ul>
    </div>
  );
}
```
"""

PRE_OUTPUT_CHECKLIST = """
## REQUIRED: SELF-CHECK BEFORE OUTPUTTING ANY CODE

Before writing any file, verify ALL of the following internally.
If any item fails, fix your plan before outputting.
Failure on any item MUST block output until resolved — do not output partial or invalid builds.

### Structure checks
- [ ] Every route I am writing has a matching Pydantic request/response schema
- [ ] Every service method I call from a route exists in the service file I am writing
- [ ] Every model field I access in a service exists as a Column in the model
- [ ] Every frontend fetch() URL exactly matches a backend route path including prefix
- [ ] Every import from business/ resolves to a file I am outputting

### Scope checks
- [ ] I am only writing files within business/ — no files outside this directory
- [ ] I am not re-implementing anything the boilerplate already provides
- [ ] I am not adding features beyond what the feature spec requires

### Dependency checks
- [ ] I have not added any Python stdlib module to requirements.txt
- [ ] I have not added any package that duplicates boilerplate capability
- [ ] Every package I added to requirements.txt is genuinely required by my code

### Frontend checks
- [ ] All frontend files use .jsx — no .tsx or .ts files
- [ ] All pages are in business/frontend/pages/ — not business/frontend/app/
- [ ] No inline styles — Tailwind classes only
- [ ] Auth0 token retrieved via getAccessTokenSilently() destructured from useAuth0()

### Output format checks
- [ ] Every file starts with the correct **FILE: path/to/file** header
- [ ] No files output outside business/ directory

Only after all checks pass: output your files.
"""

# ============================================================
# CONFIGURATION
# ============================================================

class Config:
    """Runtime configuration — governance ZIPs come from CLI, not env"""

    # API Keys (from environment — these stay as env vars)
    ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY')
    OPENAI_API_KEY    = os.getenv('OPENAI_API_KEY')

    # API Endpoints
    ANTHROPIC_API = 'https://api.anthropic.com/v1/messages'
    OPENAI_API    = 'https://api.openai.com/v1/chat/completions'

    # Models
    CLAUDE_MODEL = 'claude-sonnet-4-20250514'  # Tech/Builder
    GPT_MODEL    = 'gpt-4o-mini'               # QA/Validator — 200k TPM vs gpt-4o's 30k TPM

    # Token Limits
    # FIX #1: 200000 was the context window (input), not output limit.
    # Claude Sonnet 4.5 max output tokens is 16384 (API limit).
    # Complex builds (TwoFaced AI, Adversarial AI, etc.) need 12-15k+ tokens.
    # FIX #8: Testing showed 16384 still causes truncation on complex T2 builds
    # with extensive business logic (10+ services, models, routes, tests, etc.)
    # However, 16384 is the API maximum, so we handle truncation with continuation.
    CLAUDE_MAX_TOKENS = 16384  # API maximum
    GPT_MAX_TOKENS    = 16000

    # FIX #4 & #8: Dynamic max tokens based on iteration
    # WHY: Lowcode builds output ALL files every iteration (not incremental patches).
    # BUILD must regenerate: models, services, routes, tests, README, package.json,
    # config files, artifact_manifest.json, build_state.json - every single time.
    # For large builds (20+ files), even 16384 tokens may truncate.
    # Solution: Use max tokens + improved truncation detection + continuation.
    CLAUDE_MAX_TOKENS_BY_ITERATION = {
        1: 16384,   # Full initial build (API max)
        2: 16384,   # Still need full output (not incremental)
        3: 16384,   # Still need full output (not incremental)
        4: 16384,   # Still need full output (not incremental)
    }
    CLAUDE_MAX_TOKENS_DEFAULT = 16384  # Always use API max - lowcode needs complete output
    CLAUDE_MAX_TOKENS_PATCH   = 8192   # Patch iters: 1-3 files only; 8192 is ample, saves ~$0.12/iter

    @classmethod
    def get_max_tokens(cls, iteration: int, defect_source: str = 'qa',
                       n_target_files: int = 1) -> int:
        """
        Return 16384 for full-build iterations (QA-driven or first build).
        Return 8192 for single-file targeted patch iterations.
        Return 16384 for multi-file patch iterations (≥2 target files) — surgical patches
        now include current file contents in the prompt, so each output file is full-size.
        Truncating to 8192 on multi-file patches causes Claude to compress/drop content.
        """
        if defect_source in ('static', 'consistency', 'quality', 'compile', 'integration'):
            if n_target_files >= 2:
                return cls.CLAUDE_MAX_TOKENS_DEFAULT  # 16384 — multi-file needs full room
            return cls.CLAUDE_MAX_TOKENS_PATCH         # 8192 — single file, safe to cap
        return cls.CLAUDE_MAX_TOKENS_BY_ITERATION.get(
            iteration,
            cls.CLAUDE_MAX_TOKENS_DEFAULT
        )

    # Iteration Limits
    MAX_QA_ITERATIONS = 5      # Default aligns with locked governance; CLI can override.
    MAX_DEFECTS_PER_ITERATION = 6  # Limit fix scope per iteration to reduce churn/regressions.
    MAX_STATIC_CONSECUTIVE = 6       # Fix 3: Fall through to Feature QA after N consecutive static-only iters.
    MAX_CONSISTENCY_CONSECUTIVE = 4  # Fall through to Feature QA after N consecutive consistency-only iters.

    # API call settings
    # FIX #6: Increased timeout for large builds with prompt caching.
    # WHY: First iteration with caching + 16K token output can take 4-6 minutes.
    # Complex builds (adversarial AI, two-faced AI) with full governance context
    # need more time. 180s was too aggressive, causing false timeout failures.
    REQUEST_TIMEOUT = 600    # seconds before giving up (10 minutes for safety)
    REQUEST_TIMEOUT_BY_ITERATION = {
        1: 600,   # First call: prompt cache initialization + large output
        2: 300,   # Subsequent: cache hit, but still complex output
        3: 300,
        4: 300,
    }
    REQUEST_TIMEOUT_DEFAULT = 300  # 5 minutes for later iterations

    MAX_RETRIES        = 6      # retries on transient errors (rate limit, 529)
    RETRY_SLEEP        = 5      # seconds between retries (multiplied by attempt)
    RETRY_SLEEP_429    = 60     # minimum wait on 429 rate-limit (ChatGPT hits this hard)
    MAX_BUILD_PARTS_DEFAULT = 10            # default multipart ceiling
    MAX_BUILD_CONTINUATIONS_DEFAULT = 9     # default fallback continuation ceiling

    @classmethod
    def get_request_timeout(cls, iteration: int) -> int:
        """Get timeout for specific iteration (first call needs more time for caching)"""
        return cls.REQUEST_TIMEOUT_BY_ITERATION.get(
            iteration,
            cls.REQUEST_TIMEOUT_DEFAULT
        )

    # Output base directory
    OUTPUT_DIR = Path('./fo_harness_runs')

    # Governance ZIP contents — populated at runtime from CLI paths
    BUILD_GOVERNANCE_ZIP  = None   # Path set by CLI arg

    # Default SaaS platform boilerplate (preferred for most builds)
    PLATFORM_BOILERPLATE_DIR = Path('/Users/teebuphilip/Documents/work/teebu-saas-platform')

    # Local overrides (testing only)
    TECH_STACK_OVERRIDE_FILE = Path('./fo_tech_stack_override.json')
    EXTERNAL_INTEGRATION_OVERRIDE_FILE = Path('./fo_external_integration_override.json')
    QA_OVERRIDE_FILE = Path('./fo_qa_override.json')
    QA_POLISH_2_DIRECTIVE_FILE = Path('./directives/qa_polish_2_doc_recovery.md')
    QA_TESTCASE_DIRECTIVE_FILE = Path('./directives/qa_testcase_doc_directive.md')
    PROMPT_DIRECTIVES_DIR = Path('./directives/prompts')


# ============================================================
# QUESTION DETECTION
# ============================================================

# Markers and patterns used to detect when Claude is asking
# questions instead of building. If any of these are found in
# the response AND the build completion marker is absent,
# we treat it as a clarification request and stop.
QUESTION_MARKERS = [
    'CLARIFICATION_NEEDED',
    'QUESTIONS:',
    'CLARIFYING QUESTIONS',
    'BEFORE I BEGIN',
    'BEFORE PROCEEDING',
    'PLEASE CLARIFY',
    'PLEASE CONFIRM',
    'CAN YOU CONFIRM',
    'I NEED TO KNOW',
    'COULD YOU CLARIFY',
]

BUILD_COMPLETE_MARKER = 'BUILD STATE: COMPLETED_CLOSED'
PATCH_SET_COMPLETE_MARKER = 'PATCH_SET_COMPLETE'

def should_use_platform_boilerplate(intake_data: dict, block: str) -> bool:
    """
    Default to the platform boilerplate unless the intake explicitly
    indicates a lowcode Zapier/Shopify build.
    """
    block_key = f'block_{block.lower()}'
    block_data = intake_data.get(block_key, {})
    tech_stack = block_data.get('pass_2', {}).get('tech_stack_selection', 'custom')

    # Only skip boilerplate for explicit Zapier/Shopify-native stacks.
    # Check tech_stack_selection value directly — NOT a full-text search of the intake,
    # which would false-positive on projects that merely integrate Shopify as a feature.
    if tech_stack in ('lowcode', 'nocode'):
        stack_val = tech_stack.lower()
        if 'zapier' in stack_val or 'shopify' in stack_val:
            return False
        # Also check if pass_2 explicitly names a Zapier/Shopify platform
        platform = block_data.get('pass_2', {}).get('platform', '').lower()
        if 'zapier' in platform or 'shopify' in platform:
            return False

    return True


def detect_truncation(output: str) -> bool:
    """
    Check if output is truncated (incomplete build).

    FIX #7: Prioritize BUILD STATE marker over code block formatting.
    WHY: After continuation concatenation, code blocks may be malformed
    but if BUILD STATE: COMPLETED_CLOSED is present, the build IS complete.

    Indicators of truncation (in priority order):
    1. Missing BUILD STATE marker (most reliable)
    2. Unclosed code blocks (secondary check)
    3. Has CONTINUATION marker but no proper ending
    """
    # Check 1: Missing BUILD STATE marker (MOST RELIABLE)
    # If this marker is present, build is complete even if formatting is off
    if BUILD_COMPLETE_MARKER not in output:
        return True

    # Check 2: Has CONTINUATION marker without BUILD STATE in last 500 chars
    # (Claude tried to continue but was cut off before completing)
    if '<!-- CONTINUATION -->' in output:
        last_500_chars = output[-500:]
        if BUILD_COMPLETE_MARKER not in last_500_chars:
            return True

    # Check 3: Unclosed code blocks (secondary check)
    # Only flag as truncated if BUILD STATE is missing too
    # WHY: Continuation concatenation can create formatting issues,
    # but if BUILD STATE is present, artifacts are complete
    opening = len(re.findall(r'^```\w+', output, re.MULTILINE))
    closing = len(re.findall(r'^```\s*$', output, re.MULTILINE))
    if opening > closing:
        # Double-check: Is BUILD STATE in the last 1000 chars?
        last_1000_chars = output[-1000:]
        if BUILD_COMPLETE_MARKER not in last_1000_chars:
            return True
        # If BUILD STATE is recent, ignore code block mismatch
        # (continuation concatenation issue, but build is done)

    return False


def detect_multipart(output: str) -> dict:
    """
    Detect TCP-style multi-part output from Claude.

    Claude is instructed to split large builds into parts:
      <!-- PART 1/3 -->
      ...files...
      <!-- END PART 1/3 -->
      REMAINING FILES: file1.js, file2.js, ...

    Returns dict with:
      is_multipart: bool
      current_part: int
      total_parts: int
      remaining_files: list[str]
      is_final: bool (True if BUILD STATE: COMPLETED_CLOSED present)
    """
    result = {
        'is_multipart': False,
        'current_part': 0,
        'total_parts': 0,
        'remaining_files': [],
        'is_final': BUILD_COMPLETE_MARKER in output
    }

    # Look for <!-- PART X/N --> marker
    part_match = re.search(r'<!--\s*PART\s+(\d+)/(\d+)\s*-->', output)
    if not part_match:
        return result

    result['is_multipart'] = True
    result['current_part'] = int(part_match.group(1))
    result['total_parts'] = int(part_match.group(2))

    # Extract REMAINING FILES list
    remaining_match = re.search(r'REMAINING FILES:\s*(.+?)(?:\n\n|$)', output, re.DOTALL)
    if remaining_match:
        raw = remaining_match.group(1).strip()
        # Handle comma-separated or newline-separated lists
        files = [f.strip().strip('-').strip('*').strip() for f in re.split(r'[,\n]', raw)]
        result['remaining_files'] = [f for f in files if f and not f.startswith('<!--')]

    return result


def extract_file_paths_from_output(output: str) -> list:
    """Extract all **FILE: path** declarations from Claude's output."""
    return re.findall(r'\*\*FILE:\s*([^\*\n]+)\*\*', output)


def detect_claude_questions(text: str) -> bool:
    """
    Return True if Claude is asking REAL clarifying questions (not just code with "question" in it).

    STRICT detection to avoid false positives:
    - Only trigger on explicit CLARIFICATION_NEEDED marker
    - Don't trigger on normal code that happens to have "question" or "?" in it
    - Prevents false positives from business logic (e.g., "user questions", "FAQ", etc.)

    Strategy:
    1. If build completed (has BUILD STATE marker) → not questions
    2. If has explicit CLARIFICATION_NEEDED → actual questions
    3. Otherwise → not questions (even if has other question markers)
    """
    if BUILD_COMPLETE_MARKER in text:
        return False  # Build completed — no questions

    # Only trigger on explicit CLARIFICATION_NEEDED marker
    if 'CLARIFICATION_NEEDED' in text.upper():
        return True

    return False


# ============================================================
# COLOR OUTPUT
# ============================================================

class Colors:
    """ANSI color codes for terminal output"""
    HEADER    = '\033[95m'
    BLUE      = '\033[94m'
    CYAN      = '\033[96m'
    GREEN     = '\033[92m'
    YELLOW    = '\033[93m'
    RED       = '\033[91m'
    BOLD      = '\033[1m'
    UNDERLINE = '\033[4m'
    END       = '\033[0m'


def print_header(text: str):
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*70}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{text}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'='*70}{Colors.END}\n")

def print_success(text: str):
    print(f"{Colors.GREEN}✓ {text}{Colors.END}")

def print_error(text: str):
    print(f"{Colors.RED}✗ {text}{Colors.END}")

def print_warning(text: str):
    print(f"{Colors.YELLOW}⚠ {text}{Colors.END}")

def print_info(text: str):
    print(f"{Colors.CYAN}→ {text}{Colors.END}")


# ============================================================
# GOVERNANCE ZIP LOADER
# ============================================================

def load_governance_zip(zip_path: Path) -> str:
    """
    Read all text files from a governance ZIP and return them
    as a single concatenated string with filename markers.

    FIX #5: Previously the ZIP was referenced in prompts but
    never actually read or injected. Claude was told to "read
    governance files" but received nothing. Now we extract and
    inline every file from the ZIP into the prompt context.
    """
    # TODO: Enforce size limits and/or selective inclusion to avoid prompt bloat.
    if not zip_path.exists():
        raise FileNotFoundError(f"Governance ZIP not found: {zip_path}")

    bundle = []
    bundle.append(f"<<<BEGIN_GOVERNANCE_ZIP: {zip_path.name}>>>")

    with zipfile.ZipFile(zip_path, 'r') as zf:
        for name in sorted(zf.namelist()):
            # Skip directories and hidden files
            if name.endswith('/') or name.startswith('__'):
                continue
            try:
                content = zf.read(name).decode('utf-8', errors='replace')
                bundle.append(f"\n<<<BEGIN_GOVERNANCE_FILE: {name}>>>")
                bundle.append(content)
                bundle.append(f"<<<END_GOVERNANCE_FILE: {name}>>>")
            except Exception as e:
                bundle.append(f"\n<<<SKIP_GOVERNANCE_FILE: {name} — could not read: {e}>>>")

    bundle.append(f"\n<<<END_GOVERNANCE_ZIP: {zip_path.name}>>>")
    return '\n'.join(bundle)


def load_tech_stack_override() -> dict:
    """
    Load tech stack override file (local testing only).
    Returns empty dict if file doesn't exist.
    """
    override_path = Config.TECH_STACK_OVERRIDE_FILE
    if not override_path.exists():
        return {}

    try:
        with open(override_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        print_warning(f"Could not load tech stack override: {e}")
        return {}


def load_external_integration_override() -> dict:
    """
    Load external integration override file (local testing only).
    Returns empty dict if file doesn't exist.
    """
    override_path = Config.EXTERNAL_INTEGRATION_OVERRIDE_FILE
    if not override_path.exists():
        return {}

    try:
        with open(override_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        print_warning(f"Could not load external integration override: {e}")
        return {}


def load_qa_override() -> dict:
    """
    Load QA override file (local testing only).
    FIX #8: Allows tightening QA loop without modifying governance ZIP.
    Returns empty dict if file doesn't exist.
    """
    override_path = Config.QA_OVERRIDE_FILE
    if not override_path.exists():
        return {}

    try:
        with open(override_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        print_warning(f"Could not load QA override: {e}")
        return {}


def load_text_file(path: Path) -> str:
    """Load a UTF-8 text file and return stripped content."""
    with open(path, 'r', encoding='utf-8') as f:
        return f.read().strip()


class DirectiveTemplateLoader:
    """Loads and renders external prompt templates from directives/prompts."""

    _cache = {}

    @classmethod
    def load(cls, template_name: str) -> str:
        path = Config.PROMPT_DIRECTIVES_DIR / template_name
        if not path.exists():
            raise FileNotFoundError(f"Prompt template not found: {path}")
        cache_key = str(path.resolve())
        if cache_key not in cls._cache:
            cls._cache[cache_key] = load_text_file(path)
        return cls._cache[cache_key]

    @classmethod
    def render(cls, template_name: str, **kwargs) -> str:
        text = cls.load(template_name)
        for key, value in kwargs.items():
            text = text.replace(f"{{{{{key}}}}}", str(value))
        return text


# ============================================================
# API CLIENTS
# ============================================================

class ClaudeClient:
    """
    Client for Claude API (Tech/Builder).

    FIX #4: Added timeout and retry logic. A single hung call
    previously blocked forever. Transient errors (rate limit,
    overload) now retry up to MAX_RETRIES times.
    """

    def __init__(self):
        if not Config.ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY environment variable not set")

    def call(self, prompt: str, max_tokens: int = None, cacheable_prefix: str = None, timeout: int = None) -> Dict:
        """
        Call Claude API with timeout and retry.

        FIX #1 (Prompt Caching):
        WHY: Governance ZIP is sent every iteration. Caching saves ~90% of input token costs.
        When cacheable_prefix provided, it's marked with cache_control for 5-minute caching.

        FIX #6 (Dynamic Timeout):
        WHY: First iteration with caching + large output needs more time (4-6 min).
        Timeout can be customized per iteration to avoid false failures.

        Args:
            prompt: The main prompt (dynamic content)
            max_tokens: Max output tokens (if None, uses Config default)
            cacheable_prefix: Optional static content to cache (e.g., governance ZIP)
            timeout: Request timeout in seconds (if None, uses Config default)

        Returns:
            API response dict with usage stats including cache metrics
        """
        if max_tokens is None:
            max_tokens = Config.CLAUDE_MAX_TOKENS

        if timeout is None:
            timeout = Config.REQUEST_TIMEOUT

        # Build message content - use array format if caching, string otherwise
        if cacheable_prefix:
            # WHY: Content array format with cache_control enables prompt caching.
            # First block (governance) is cached, second block (dynamic) is not.
            message_content = [
                {
                    "type": "text",
                    "text": cacheable_prefix,
                    "cache_control": {"type": "ephemeral"}
                },
                {
                    "type": "text",
                    "text": prompt
                }
            ]
        else:
            # Backward compatible - no caching
            message_content = prompt

        payload = {
            "model":      Config.CLAUDE_MODEL,
            "max_tokens": max_tokens,
            "messages":   [{"role": "user", "content": message_content}]
        }

        headers = {
            "content-type":      "application/json",
            "x-api-key":         Config.ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "anthropic-beta":    "prompt-caching-2024-07-31"  # Enable caching
        }

        last_error = None
        for attempt in range(1, Config.MAX_RETRIES + 1):
            try:
                _ts_req = datetime.now()
                print_info(f"[{_ts_req.strftime('%Y-%m-%d %H:%M:%S')}] → Claude API request sent")
                response = requests.post(
                    Config.ANTHROPIC_API,
                    json=payload,
                    headers=headers,
                    timeout=timeout
                )
                _ts_resp = datetime.now()

                # Fatal errors — do not retry
                if response.status_code in (400, 401, 403):
                    response.raise_for_status()

                # Transient errors — retry
                if response.status_code in (429, 500, 529):
                    # Dump error body + headers for diagnosis
                    try:
                        err_body = response.json()
                        err_obj  = err_body.get('error', err_body)
                        print_warning(f"  {response.status_code} error type : {err_obj.get('type', '?')}")
                        print_warning(f"  {response.status_code} message    : {str(err_obj.get('message', err_obj))[:200]}")
                    except Exception:
                        print_warning(f"  {response.status_code} body       : {response.text[:300]}")

                    rl_headers = {
                        'retry-after':   response.headers.get('retry-after') or response.headers.get('Retry-After'),
                        'limit-req':     response.headers.get('anthropic-ratelimit-requests-limit'),
                        'remain-req':    response.headers.get('anthropic-ratelimit-requests-remaining'),
                        'reset-req':     response.headers.get('anthropic-ratelimit-requests-reset'),
                        'limit-tok':     response.headers.get('anthropic-ratelimit-tokens-limit'),
                        'remain-tok':    response.headers.get('anthropic-ratelimit-tokens-remaining'),
                        'reset-tok':     response.headers.get('anthropic-ratelimit-tokens-reset'),
                    }
                    for k, v in rl_headers.items():
                        if v is not None:
                            print_warning(f"  {k:12s}: {v}")

                    wait = Config.RETRY_SLEEP * attempt
                    print_warning(f"Claude API transient error {response.status_code} — retry {attempt}/{Config.MAX_RETRIES} in {wait}s")
                    time.sleep(wait)
                    last_error = f"HTTP {response.status_code}"
                    continue

                response.raise_for_status()
                print_info(f"[{_ts_resp.strftime('%Y-%m-%d %H:%M:%S')}] ← Claude API response received ({(_ts_resp - _ts_req).total_seconds():.1f}s)")
                return response.json()

            except requests.exceptions.Timeout:
                print_warning(f"Claude API timeout after {timeout}s — retry {attempt}/{Config.MAX_RETRIES}")
                last_error = f"Timeout ({timeout}s)"
                time.sleep(Config.RETRY_SLEEP)
                continue

            except requests.exceptions.RequestException as e:
                print_warning(f"Claude API error — retry {attempt}/{Config.MAX_RETRIES}: {e}")
                last_error = str(e)
                time.sleep(Config.RETRY_SLEEP)
                continue

        raise RuntimeError(f"Claude API failed after {Config.MAX_RETRIES} attempts: {last_error}")


class ChatGPTClient:
    """
    Client for ChatGPT API (QA/Validator).

    FIX #4: Same timeout and retry logic applied as ClaudeClient.
    """

    def __init__(self):
        if not Config.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY environment variable not set")

    def call(self, prompt: str, max_tokens: int = None, system_message: str = None) -> Dict:
        """Call ChatGPT API with timeout and retry.
        system_message: optional system role content prepended before user message (e.g. repair mode rules).
        """
        if max_tokens is None:
            max_tokens = Config.GPT_MAX_TOKENS

        messages = []
        if system_message:
            messages.append({"role": "system", "content": system_message})
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
                _ts_req = datetime.now()
                print_info(f"[{_ts_req.strftime('%Y-%m-%d %H:%M:%S')}] → ChatGPT API request sent")
                response = requests.post(
                    Config.OPENAI_API,
                    json=payload,
                    headers=headers,
                    timeout=Config.REQUEST_TIMEOUT
                )
                _ts_resp = datetime.now()

                if response.status_code in (400, 401, 403):
                    response.raise_for_status()

                if response.status_code in (429, 500, 529):
                    if response.status_code == 429:
                        # Dump error body so we know WHICH limit we hit
                        try:
                            err_body = response.json()
                            err_msg  = err_body.get('error', {})
                            print_warning(f"  429 error type : {err_msg.get('type', '?')}")
                            print_warning(f"  429 error code : {err_msg.get('code', '?')}")
                            print_warning(f"  429 message    : {err_msg.get('message', '?')[:200]}")
                        except Exception:
                            print_warning(f"  429 body       : {response.text[:300]}")

                        # Dump rate-limit headers so we know limits + resets
                        rl_headers = {
                            'limit-req':     response.headers.get('x-ratelimit-limit-requests'),
                            'remain-req':    response.headers.get('x-ratelimit-remaining-requests'),
                            'reset-req':     response.headers.get('x-ratelimit-reset-requests'),
                            'limit-tok':     response.headers.get('x-ratelimit-limit-tokens'),
                            'remain-tok':    response.headers.get('x-ratelimit-remaining-tokens'),
                            'reset-tok':     response.headers.get('x-ratelimit-reset-tokens'),
                            'Retry-After':   response.headers.get('Retry-After') or response.headers.get('retry-after'),
                        }
                        for k, v in rl_headers.items():
                            if v is not None:
                                print_warning(f"  {k:12s}: {v}")

                        # Honor Retry-After if present; otherwise exponential backoff + jitter
                        retry_after = rl_headers['Retry-After']
                        if retry_after:
                            try:
                                wait = float(retry_after)
                                print_warning(f"ChatGPT API 429 — Retry-After: {wait}s — retry {attempt}/{Config.MAX_RETRIES}")
                            except ValueError:
                                wait = Config.RETRY_SLEEP_429
                                print_warning(f"ChatGPT API 429 — retry {attempt}/{Config.MAX_RETRIES} in {wait}s")
                        else:
                            import random
                            base = min(Config.RETRY_SLEEP_429, Config.RETRY_SLEEP * (2 ** attempt))
                            wait = base * (0.5 + random.random() * 0.5) + 120  # jitter + 120s penalty
                            print_warning(f"ChatGPT API 429 — retry {attempt}/{Config.MAX_RETRIES} in {wait:.0f}s (backoff+jitter+120s)")
                    else:
                        wait = Config.RETRY_SLEEP * attempt
                        print_warning(f"ChatGPT API transient error {response.status_code} — retry {attempt}/{Config.MAX_RETRIES} in {wait}s")
                    time.sleep(wait)
                    last_error = f"HTTP {response.status_code}"
                    continue

                response.raise_for_status()
                print_info(f"[{_ts_resp.strftime('%Y-%m-%d %H:%M:%S')}] ← ChatGPT API response received ({(_ts_resp - _ts_req).total_seconds():.1f}s)")
                return response.json()

            except requests.exceptions.Timeout:
                print_warning(f"ChatGPT API timeout — retry {attempt}/{Config.MAX_RETRIES}")
                last_error = "Timeout"
                time.sleep(Config.RETRY_SLEEP)
                continue

            except requests.exceptions.RequestException as e:
                print_warning(f"ChatGPT API error — retry {attempt}/{Config.MAX_RETRIES}: {e}")
                last_error = str(e)
                time.sleep(Config.RETRY_SLEEP)
                continue

        raise RuntimeError(f"ChatGPT API failed after {Config.MAX_RETRIES} attempts: {last_error}")


# ============================================================
# FILE MANAGEMENT
# ============================================================

# Valid boilerplate business/** paths — anything outside this is pruned.
# Pattern syntax is fnmatch (shell-style wildcards).
BOILERPLATE_VALID_PATHS = [
    # Core deployment contract
    'business/frontend/pages/*.jsx',
    'business/frontend/pages/*.js',
    'business/frontend/components/*.jsx',
    'business/frontend/components/*.js',
    'business/backend/routes/*.py',
    'business/backend/main.py',
    'business/models/*.py',
    'business/services/*.py',
    'business/schemas/*.py',
    'business/frontend/lib/*.js',
    'business/frontend/lib/*.jsx',
    'business/frontend/*.jsx',
    'business/frontend/*.css',
    'business/README-INTEGRATION.md',
    'business/package.json',
    # Backend dependencies
    'business/backend/requirements.txt',
    # Tests — kept so QA can evaluate them, but excluded from ZIP and merge_forward
    'business/tests/*.py',
    'business/tests/*.js',
    'business/tests/*.jsx',
    'business/tests/*.ts',
    'business/tests/*.tsx',
    'business/backend/tests/*.py',
    'business/tests/conftest.py',
    'business/backend/tests/conftest.py',
    # Frontend styles and public assets (valid business additions)
    'business/frontend/styles/*.css',
    'business/frontend/public/*',
    # NOTE: tailwind.config.js, next.config.js, postcss.config.js, package.json etc.
    # are BOILERPLATE-OWNED files. Claude must NOT generate them. If Claude does,
    # they are pruned by BOILERPLATE_OWNED_FRONTEND_CONFIGS below.
]

# Config files that belong to the boilerplate, not to business/ artifacts.
# Claude sometimes generates these for dashboard/styled features.
# They conflict with the boilerplate's own copies and must be silently pruned.
BOILERPLATE_OWNED_FRONTEND_CONFIGS = {
    'tailwind.config.js', 'tailwind.config.ts',
    'next.config.js', 'next.config.ts',
    'postcss.config.js', 'postcss.config.ts',
    'tsconfig.json', 'jsconfig.json',
    'jest.config.js', 'jest.config.ts',
    'jest.setup.js', 'jest.setup.ts',
    'package.json',   # business/frontend/package.json — use business/package.json instead
}

class ArtifactManager:
    """Manages saving artifacts, QA reports, build outputs, and logs"""

    def __init__(self, run_dir: Path):
        self.run_dir = run_dir

        # Subdirectories
        self.build_dir  = run_dir / 'build'
        self.qa_dir     = run_dir / 'qa'
        self.deploy_dir = run_dir / 'deploy'
        self.logs_dir   = run_dir / 'logs'

        for d in [self.build_dir, self.qa_dir, self.deploy_dir, self.logs_dir]:
            d.mkdir(parents=True, exist_ok=True)

    def save_build_output(self, iteration: int, output: str, extract_from: str = None):
        """Save BUILD output from Claude and extract artifacts.

        output      — full raw Claude response (always saved to disk for audit)
        extract_from — if provided, extract artifacts from this string instead of output.
                       Used on patch iterations to ignore anything after PATCH_SET_COMPLETE.
        """
        # Save raw output (always the full response)
        path = self.build_dir / f'iteration_{iteration:02d}_build.txt'
        path.write_text(output)
        print_success(f"Saved BUILD output: build/iteration_{iteration:02d}_build.txt")

        # Extract and save code artifacts
        extraction_source = extract_from if extract_from is not None else output
        extracted_count = self._extract_artifacts_from_output(extraction_source, iteration)
        if extracted_count > 0:
            print_success(f"Extracted {extracted_count} artifact(s) from BUILD output")

        return path

    def _extract_artifacts_from_output(self, output: str, iteration: int) -> int:
        """
        Parse Claude's output and extract code blocks/artifacts into separate files.
        Returns the count of artifacts extracted.
        """
        import re

        # Create artifacts subdirectory for this iteration
        artifacts_dir = self.build_dir / f'iteration_{iteration:02d}_artifacts'
        artifacts_dir.mkdir(exist_ok=True)

        count = 0
        skipped_snippets = []

        # Track when we're in README context to skip documentation snippets
        last_readme_pos = -1

        # Pattern to match code blocks with optional filename hints
        # Matches: [preceding line]\n```language [filename]\n...\n```
        # Captures up to 200 chars before the code fence to check for filename hints
        # TODO: Support unlabeled code fences (``` with no language) to avoid missing artifacts.
        code_block_pattern = r'(?:^|\n)(.{0,200}?)\n?```(\w+)(?:[ \t]+([^\n]+))?\n(.*?)```'

        for match in re.finditer(code_block_pattern, output, re.DOTALL | re.MULTILINE):
            preceding_line = match.group(1).strip() if match.group(1) else ''
            language = match.group(2)
            filename_hint = match.group(3)
            code_content = match.group(4)

            match_pos = match.start()

            # Check if this is a documentation snippet (example code in README/docs)
            is_doc_snippet = False
            # context_before: 500 chars before this match (for doc snippet detection)
            # NOTE: match_pos is the start of the full regex match, which INCLUDES
            # preceding_line. So context_before does NOT contain the FILE: header.
            # We must also check preceding_line for FILE: presence.
            context_before = output[max(0, match_pos - 500):match_pos]
            has_file_header = '**FILE:' in preceding_line or '**File:' in preceding_line

            # Skip if no explicit **FILE:** header AND it looks like a doc snippet
            if not has_file_header and '**FILE:' not in context_before:
                # Indicators this is a documentation example:
                doc_indicators = [
                    '### ',           # Markdown header
                    '## ',            # Markdown header
                    'Add to your',    # Instructional text
                    'In your',        # Instructional text
                    'Mount the',      # Instructional text
                    'Example:',       # Example label
                    'Usage:',         # Usage label
                    'Sample:',        # Sample label
                ]

                # If preceded by doc indicators, it's probably a snippet
                has_doc_indicator = any(indicator in context_before[-200:] for indicator in doc_indicators)

                # Also skip if it's a small snippet (< 300 chars)
                is_tiny_snippet = len(code_content.strip()) < 300

                if has_doc_indicator or is_tiny_snippet:
                    is_doc_snippet = True
                    snippet_context = context_before[-100:].strip().split('\n')[-1] if context_before else 'unknown'
                    print_info(f"  → Skipped: doc snippet ({language}, {len(code_content)} chars) - context: {snippet_context[:50]}...")

            if is_doc_snippet:
                skipped_snippets.append({
                    "language": language,
                    "context": snippet_context if 'snippet_context' in locals() else '',
                    "content": code_content.strip()
                })
                continue

            filename = None

            # STEP 1: Check preceding context for patterns like "**FILE: path/to/file.ext**"
            # preceding_line (from regex group 1) contains the FILE: header most of the time.
            # context_before is 500 chars BEFORE the match (doesn't include preceding_line).
            # Check preceding_line first (most reliable), then context_before as fallback.
            search_area = preceding_line + '\n' + context_before if preceding_line else context_before

            if search_area:
                # Look for filename patterns (case-insensitive)
                preceding_patterns = [
                    r'\*\*FILE:\s*([^\*]+)\*\*',           # **FILE: path/file.ext**
                    r'\*\*File:\s*([^\*]+)\*\*',           # **File: path/file.ext**
                    r'File:\s*([^\n]+)',                    # File: file.ext
                    r'###\s*([^\n]+\.[\w]+)',               # ### file.ext
                    r'##\s*([^\n]+\.[\w]+)',                # ## file.ext
                ]

                for pattern in preceding_patterns:
                    # Search from the end (closest match to code fence)
                    all_matches = list(re.finditer(pattern, search_area, re.IGNORECASE))
                    if all_matches:
                        prec_match = all_matches[-1]  # Take the closest match
                        potential_filename = prec_match.group(1).strip()
                        # Clean and validate the filename
                        if potential_filename and ('.' in potential_filename or potential_filename.startswith('.')):
                            # Remove any remaining markdown or formatting
                            potential_filename = re.sub(r'[\*`]', '', potential_filename)
                            potential_filename = potential_filename.strip()
                            if potential_filename:
                                filename = potential_filename
                                break

            # STEP 2: Check if there's a filename hint on the same line as the language identifier
            if not filename and filename_hint and filename_hint.strip():
                # Clean the filename hint:
                # - Remove leading comment markers (// or # or /* or *)
                # - Remove leading/trailing whitespace
                # - Remove leading slashes
                potential_filename = filename_hint.strip()
                # Strip common comment prefixes
                for prefix in ['//', '/*', '*/', '#', '*']:
                    if potential_filename.startswith(prefix):
                        potential_filename = potential_filename[len(prefix):].strip()
                # Strip leading slashes (fix paths like "//package.json")
                potential_filename = potential_filename.lstrip('/')

                # Validate filename - allow subdirectories and dotfiles
                if potential_filename and ('.' in potential_filename or '/' in potential_filename):
                    filename = potential_filename

            # STEP 3: Check the first line of content for filename comment
            # (e.g., "// app.js" or "# config.py" or "<!-- index.html -->")
            if not filename and code_content:
                first_line = code_content.split('\n')[0].strip()
                # Check for common comment patterns with filenames
                comment_patterns = [
                    (r'^//\s*(.+\.[\w]+)\s*$', '//'),           # JavaScript: // filename.js
                    (r'^#\s*(.+\.[\w]+)\s*$', '#'),             # Python/Bash: # filename.py
                    (r'^/\*\s*(.+\.[\w]+)\s*\*/$', '/*'),       # CSS: /* filename.css */
                    (r'^<!--\s*(.+\.[\w]+)\s*-->$', '<!--'),    # HTML: <!-- filename.html -->
                ]

                for pattern, _ in comment_patterns:
                    comment_match = re.match(pattern, first_line)
                    if comment_match:
                        potential_filename = comment_match.group(1).strip()
                        # Validate it looks like a filename (has extension, no spaces in name)
                        if '.' in potential_filename and ' ' not in potential_filename:
                            filename = potential_filename
                            break

            # Generate filename if hint was invalid or missing
            if not filename:
                # FIX #13: Try to infer filename from code content before falling back to artifact_N
                inferred = None
                # Look for common patterns: class Name, module.exports, export default, router name, etc.
                class_match = re.search(r'(?:class|function)\s+(\w+)', code_content)
                export_match = re.search(r'module\.exports\s*=\s*(?:class\s+)?(\w+)', code_content)
                react_match = re.search(r'export\s+(?:default\s+)?(?:function|class|const)\s+(\w+)', code_content)
                router_match = re.search(r"router\s*=\s*express\.Router\(\)|app\.\w+\(['\"]\/(\w+)", code_content)

                for m in [export_match, react_match, class_match]:
                    if m:
                        name = m.group(1)
                        # Skip generic names
                        if name.lower() not in ('module', 'exports', 'default', 'app', 'router', 'handler'):
                            inferred = name
                            break

                if inferred:
                    extensions_map = {
                        'python': '.py', 'javascript': '.js', 'typescript': '.ts',
                        'json': '.json', 'html': '.html', 'css': '.css',
                        'yaml': '.yaml', 'jsx': '.jsx', 'tsx': '.tsx',
                    }
                    ext = extensions_map.get(language.lower(), '.js')
                    filename = f'{inferred}{ext}'
                    print_info(f"  → Inferred filename from code content: {filename}")
                else:
                    extensions = {
                        'python': '.py',
                        'javascript': '.js',
                        'typescript': '.ts',
                        'json': '.json',
                        'html': '.html',
                        'css': '.css',
                        'yaml': '.yaml',
                        'yml': '.yml',
                        'markdown': '.md',
                        'bash': '.sh',
                        'shell': '.sh',
                    }
                    ext = extensions.get(language.lower(), '.txt')
                    filename = f'artifact_{count + 1}{ext}'

            # TODO: Sanitize/normalize filename to prevent path traversal (e.g., ../ or absolute paths).
            # Save the artifact
            artifact_path = artifacts_dir / filename
            # Create parent directories if the filename contains subdirectories
            artifact_path.parent.mkdir(parents=True, exist_ok=True)

            # Duplicate / overwrite decision:
            #   - Identical content (checksum match) → skip, no point writing
            #   - Different content, new is suspiciously tiny (<100 chars) → likely
            #     a truncated stub; keep existing and warn
            #   - Different content, reasonable size → prefer new (Claude intentionally
            #     regenerated it, e.g. to fix a defect; old version may be defective)
            if artifact_path.exists() and not filename.startswith('artifact_'):
                existing_bytes = artifact_path.read_bytes()
                new_bytes = code_content.encode('utf-8')
                if existing_bytes == new_bytes:
                    # Truly identical — no need to rewrite
                    continue
                existing_size = len(existing_bytes)
                new_size = len(new_bytes)
                if new_size < 100 and new_size < existing_size // 2:
                    print_warning(f"  → Skipped (truncated stub): {filename} (existing {existing_size}b, new only {new_size}b)")
                    continue
                if new_size < existing_size:
                    print_warning(f"  → Overwriting: {filename} (new version smaller but different: {new_size} < {existing_size} chars — keeping new)")
                else:
                    print_warning(f"  → Overwriting: {filename} (new version larger: {new_size} > {existing_size} chars)")

            artifact_path.write_text(code_content)
            count += 1
            print_info(f"  → Extracted: {filename}")

        # ══════════════════════════════════════════════════════════
        # FIX #12: Generate metadata files ourselves instead of
        # depending on Claude. Claude's manifest often gets truncated
        # or has continuation markers embedded in the JSON.
        # ══════════════════════════════════════════════════════════

        # Always generate build_state.json.
        # Both BUILD STATE: COMPLETED_CLOSED (full build) and PATCH_SET_COMPLETE
        # (patch iteration) are valid completion markers.
        build_state_path = artifacts_dir / 'build_state.json'
        has_complete_marker = (
            BUILD_COMPLETE_MARKER in output
            or PATCH_SET_COMPLETE_MARKER in output
        )
        build_state = {
            "state": "COMPLETED_CLOSED" if has_complete_marker else "IN_PROGRESS",
            "timestamp": datetime.now().isoformat(),
            "generated_by": "fo_test_harness"
        }
        with open(build_state_path, 'w') as f:
            json.dump(build_state, f, indent=2)
        if has_complete_marker:
            print_info(f"  → Generated: build_state.json (COMPLETED_CLOSED)")
        else:
            print_warning(f"  → Generated: build_state.json (IN_PROGRESS — no completion marker found)")

        # Persist skipped snippets for post-QA polish
        if skipped_snippets:
            snippets_path = artifacts_dir / 'skipped_snippets.json'
            with open(snippets_path, 'w') as f:
                json.dump(skipped_snippets, f, indent=2)
            print_info(f"  → Saved: skipped_snippets.json ({len(skipped_snippets)} snippet(s))")

        self._write_artifact_manifest(artifacts_dir)

        return count

    def _write_artifact_manifest(self, artifacts_dir: Path):
        """Generate artifact_manifest.json from files in artifacts_dir."""
        manifest_path = artifacts_dir / 'artifact_manifest.json'
        manifest_artifacts = []
        for file_path in sorted(artifacts_dir.rglob('*')):
            if file_path.is_file():
                rel_path = str(file_path.relative_to(artifacts_dir))
                if rel_path in ('artifact_manifest.json', 'build_state.json', 'execution_declaration.json'):
                    continue
                file_content = file_path.read_bytes()
                sha256 = hashlib.sha256(file_content).hexdigest()
                manifest_artifacts.append({
                    "path": rel_path,
                    "sha256": sha256,
                    "size": len(file_content)
                })

        manifest = {
            "artifacts": manifest_artifacts,
            "total_count": len(manifest_artifacts),
            "generated_by": "fo_test_harness",
            "timestamp": datetime.now().isoformat()
        }
        with open(manifest_path, 'w') as f:
            json.dump(manifest, f, indent=2)
        print_info(f"  → Generated: artifact_manifest.json ({len(manifest_artifacts)} files)")

    def refresh_manifest_for_iteration(self, iteration: int):
        """Regenerate manifest for a given iteration after post-processing."""
        artifacts_dir = self.build_dir / f'iteration_{iteration:02d}_artifacts'
        if artifacts_dir.exists():
            self._write_artifact_manifest(artifacts_dir)

    @staticmethod
    def _sha256(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    @staticmethod
    def _is_valid_business_path(rel_path: str) -> bool:
        """Return True if rel_path matches the boilerplate whitelist."""
        import fnmatch, os
        # __init__.py files are Python package plumbing — never a valid business artifact.
        if os.path.basename(rel_path) == '__init__.py':
            return False
        for pattern in BOILERPLATE_VALID_PATHS:
            if fnmatch.fnmatch(rel_path, pattern):
                return True
        return False

    @staticmethod
    def _remap_to_valid_path(rel_path: str):
        """Return the canonical business/ path for a wrong-path file, or None if unmappable.

        Rules:
          *.py  in api/, routers/, routes/          → business/backend/routes/<name>
          *.py  in models/                          → business/models/<name>
          *.py  in services/                        → business/services/<name>
          *.py  in schemas/                         → business/schemas/<name>
          *.jsx|*.tsx                               → business/frontend/pages/<name.jsx>  (or lib/)
          *.js|*.jsx in lib/                        → business/frontend/lib/<name>
          *.js|*.jsx in components/                 → business/frontend/components/<name>
          *.js|*.jsx in app/ or pages/              → business/frontend/pages/<name>
          package.json / *.config.js/ts in frontend/→ business/frontend/<name>
        """
        import os
        name = os.path.basename(rel_path)
        parts = rel_path.replace('\\', '/').split('/')

        # __init__.py is Python package plumbing — never remap, always prune.
        if name == '__init__.py':
            return None

        if name.endswith('.py'):
            for marker in ('api', 'routers', 'routes'):
                if marker in parts:
                    return f'business/backend/routes/{name}'
            if 'models' in parts:
                return f'business/models/{name}'
            if 'services' in parts:
                return f'business/services/{name}'
            if 'schemas' in parts:
                return f'business/schemas/{name}'
            if 'tests' in parts or name.startswith('test_'):
                return f'business/tests/{name}'

        elif name == 'requirements.txt':
            # Backend dependency file — always belongs in business/backend/
            return 'business/backend/requirements.txt'

        elif name.endswith(('.jsx', '.tsx', '.js')):
            # Next.js app router: app/**/page.tsx — derive component name from route segments
            if name in ('page.tsx', 'page.jsx', 'page.js') and 'app' in parts:
                app_idx = len(parts) - 1 - list(reversed(parts)).index('app')
                route_parts = parts[app_idx + 1:-1]  # segments between 'app' and 'page.*'
                if route_parts:
                    component = ''.join(p.capitalize() for p in route_parts)
                else:
                    component = 'index'
                return f'business/frontend/pages/{component}.jsx'

            # JS test files
            if 'tests' in parts or '.test.' in name or '.spec.' in name:
                return f'business/tests/{name}'

            canonical = name.replace('.tsx', '.jsx')
            if 'lib' in parts:
                return f'business/frontend/lib/{canonical}'
            if 'components' in parts:
                return f'business/frontend/components/{canonical}'
            if 'app' in parts or 'pages' in parts:
                return f'business/frontend/pages/{canonical}'
            if 'frontend' in parts:
                return f'business/frontend/{canonical}'

        elif name in ('package.json', 'next.config.js', 'next.config.ts',
                      'postcss.config.js', 'postcss.config.ts',
                      'tailwind.config.js', 'tailwind.config.ts',
                      'tsconfig.json', 'jsconfig.json',
                      'jest.config.js', 'jest.config.ts',
                      'jest.setup.js', 'jest.setup.ts'):
            # Always remap to business/frontend/ regardless of where Claude placed them
            return f'business/frontend/{name}'

        return None  # unmappable — will be pruned

    @staticmethod
    def _remap_business_path(rel_path: str):
        """Remap a wrong-location business/ path to a valid whitelist path.

        Called from Pass 2 before deleting invalid business/ files.
        Rules:
          business/frontend/app/*.tsx|.jsx|.js → business/frontend/pages/*.jsx
          business/frontend/app/*.css          → business/frontend/styles/*.css
          business/backend/**/api|routers|routes/*.py → business/backend/routes/*.py
          business/backend/**/models/*.py            → business/models/*.py
          business/backend/**/schemas/*.py           → business/schemas/*.py
          business/backend/**/services/*.py          → business/services/*.py
        """
        import os
        name = os.path.basename(rel_path)
        parts = rel_path.replace('\\', '/').split('/')

        # business/frontend/app/ → pages/ or styles/
        if 'frontend' in parts and 'app' in parts:
            if name.endswith(('.tsx', '.jsx', '.js')):
                return f'business/frontend/pages/{name.replace(".tsx", ".jsx")}'
            if name.endswith('.css'):
                return f'business/frontend/styles/{name}'

        # business/backend/**/ wrong-location .py files
        if 'backend' in parts and name.endswith('.py'):
            # api/routers/routes anywhere under backend → routes/
            if 'api' in parts or 'routers' in parts or 'routes' in parts:
                return f'business/backend/routes/{name}'
            # models/schemas/services anywhere under backend → canonical top-level
            if 'models' in parts:
                return f'business/models/{name}'
            if 'schemas' in parts:
                return f'business/schemas/{name}'
            if 'services' in parts:
                return f'business/services/{name}'

        return None  # unmappable — will be pruned

    def prune_non_business_artifacts(self, iteration: int):
        """Remove non-business artifacts and regenerate manifest.

        Pass 1: wrong-path files (not under business/).
          - If a valid-path equivalent already exists in this iteration → prune (duplicate).
          - If NO equivalent exists → remap to the canonical business/ path to avoid losing logic.
          - Truly unmappable files are pruned.

        Pass 2: business/** files not on the valid-path whitelist.
                Try to remap to canonical path. If remappable → move.
                If duplicate of canonical → prune.
                If unmappable → leave in place for QA; merge_forward
                gates on the whitelist so it won't carry forward.
        """
        artifacts_dir = self.build_dir / f'iteration_{iteration:02d}_artifacts'
        if not artifacts_dir.exists():
            return

        SKIP = {'artifact_manifest.json', 'build_state.json', 'execution_declaration.json'}

        # Prune __pycache__ directories entirely — bytecode is not an artifact
        import shutil as _shutil
        for pycache_dir in sorted(artifacts_dir.rglob('__pycache__'), reverse=True):
            if pycache_dir.is_dir():
                _shutil.rmtree(pycache_dir, ignore_errors=True)
                print_warning(f"  → Pruned __pycache__: {pycache_dir.relative_to(artifacts_dir)}")

        removed = 0
        remapped = 0
        invalid_business = 0
        for file_path in sorted(artifacts_dir.rglob('*')):
            if not file_path.is_file():
                continue
            rel_path = str(file_path.relative_to(artifacts_dir))
            if rel_path in SKIP:
                continue

            # Prune boilerplate-owned frontend config files wherever Claude puts them
            import os as _os
            if _os.path.basename(rel_path) in BOILERPLATE_OWNED_FRONTEND_CONFIGS and \
                    rel_path.startswith('business/frontend/'):
                file_path.unlink()
                removed += 1
                print_warning(f"  → Pruned boilerplate-owned config: {rel_path} (boilerplate owns this file)")
                continue

            if not rel_path.startswith('business/'):
                canonical = self._remap_to_valid_path(rel_path)
                if canonical:
                    dest = artifacts_dir / canonical
                    if dest.exists():
                        # Correct-path version already present — discard the duplicate
                        if self._sha256(file_path) == self._sha256(dest):
                            print_warning(f"  → Pruned identical duplicate: {rel_path} (kept {canonical})")
                        else:
                            print_warning(f"  → CONFLICT: {rel_path} differs from {canonical} — keeping canonical, discarding wrong-path")
                        file_path.unlink()
                        removed += 1
                    else:
                        # No correct-path version — salvage by remapping
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        file_path.rename(dest)
                        remapped += 1
                        print_warning(f"  → Remapped {rel_path} → {canonical}")
                else:
                    file_path.unlink()
                    removed += 1
                    print_warning(f"  → Pruned (no remap): {rel_path}")
            elif not self._is_valid_business_path(rel_path):
                # Try to remap to canonical path (e.g. app/*.tsx → pages/*.jsx)
                canonical = self._remap_business_path(rel_path)
                if canonical:
                    dest = artifacts_dir / canonical
                    if dest.exists():
                        if self._sha256(file_path) == self._sha256(dest):
                            print_warning(f"  → Pruned identical duplicate: {rel_path} (kept {canonical})")
                        else:
                            print_warning(f"  → CONFLICT: {rel_path} differs from {canonical} — keeping canonical, discarding wrong-path")
                        file_path.unlink()
                        invalid_business += 1
                    else:
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        file_path.rename(dest)
                        remapped += 1
                        print_warning(f"  → Remapped business path: {rel_path} → {canonical}")
                # If no remap: leave the file in place for QA to evaluate.
                # merge_forward gates on the whitelist so it won't accumulate.

        # Remove empty directories
        for dir_path in sorted(artifacts_dir.rglob('*'), reverse=True):
            if dir_path.is_dir() and not any(dir_path.iterdir()):
                dir_path.rmdir()

        if removed:
            print_warning(f"  → Pruned {removed} file(s) total (listed above)")
        if remapped:
            print_success(f"  → Remapped {remapped} wrong-path file(s) to correct business/ paths (listed above)")
        if invalid_business:
            print_warning(f"  → Pruned {invalid_business} duplicate business path(s) (listed above)")
        if removed or remapped or invalid_business:
            self._write_artifact_manifest(artifacts_dir)

    def merge_forward_from_previous_iteration(self, iteration: int, claude_output_paths: list):
        """
        After a defect-only patch iteration, copy any business/** files from the previous
        iteration that Claude did NOT output into the current iteration's artifact dir.
        This prevents non-defect files from being lost when Claude outputs only defect files.
        """
        import shutil
        prev_dir = self.build_dir / f'iteration_{iteration-1:02d}_artifacts'
        curr_dir = self.build_dir / f'iteration_{iteration:02d}_artifacts'
        if not prev_dir.exists() or not curr_dir.exists():
            return

        # Normalize Claude's output paths for comparison
        output_set = set(p.lstrip('./') for p in claude_output_paths)

        # Tests survive the whitelist (so QA can see them) but must NOT accumulate across
        # iterations — Claude should regenerate them each time if needed.
        NO_FORWARD = ('business/tests/', 'business/backend/tests/')

        copied = 0
        for file_path in sorted(prev_dir.rglob('*')):
            if not file_path.is_file():
                continue
            rel_path = str(file_path.relative_to(prev_dir))
            if rel_path in ('artifact_manifest.json', 'build_state.json', 'execution_declaration.json'):
                continue
            if not self._is_valid_business_path(rel_path):
                continue  # Never carry forward invalid paths
            if any(rel_path.startswith(p) for p in NO_FORWARD):
                continue  # Tests visible to QA but not carried forward
            if rel_path in output_set:
                continue  # Claude already output this file — keep Claude's version
            dest = curr_dir / rel_path
            if not dest.exists():
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(file_path, dest)
                copied += 1
                print_info(f"  → Carried forward: {rel_path}")

        if copied > 0:
            print_info(f"  → Carried forward {copied} unchanged file(s) from iteration {iteration-1:02d} (listed above)")
            self._write_artifact_manifest(curr_dir)

    def build_synthetic_qa_output(self, iteration: int) -> str:
        """
        Build a synthetic build_output string from the current iteration's merged artifact
        directory, formatted as FILE: headers + code fences. Used to give QA an accurate
        view of the full artifact set after merge-forward, not just Claude's partial output.
        """
        artifacts_dir = self.build_dir / f'iteration_{iteration:02d}_artifacts'
        if not artifacts_dir.exists():
            return ""

        ext_to_lang = {
            '.py': 'python', '.jsx': 'jsx', '.js': 'jsx', '.ts': 'typescript',
            '.tsx': 'typescript', '.json': 'json', '.md': 'markdown',
            '.css': 'css', '.html': 'html', '.sh': 'bash', '.txt': 'text',
        }
        skip = {'artifact_manifest.json', 'build_state.json', 'execution_declaration.json'}

        parts = []
        for file_path in sorted(artifacts_dir.rglob('*')):
            if not file_path.is_file():
                continue
            rel_path = str(file_path.relative_to(artifacts_dir))
            if rel_path in skip:
                continue
            lang = ext_to_lang.get(file_path.suffix.lower(), 'text')
            try:
                content = file_path.read_text(encoding='utf-8', errors='replace')
            except Exception:
                continue
            parts.append(f'**FILE: {rel_path}**\n```{lang}\n{content}\n```')

        return '\n\n'.join(parts)

    def save_qa_report(self, iteration: int, report: str):
        """Save QA report from ChatGPT"""
        path = self.qa_dir / f'iteration_{iteration:02d}_qa_report.txt'
        path.write_text(report)
        print_success(f"Saved QA report: qa/iteration_{iteration:02d}_qa_report.txt")
        return path

    def save_defect_fix(self, iteration: int, fix: str):
        """
        Save defect fix from Claude (iterations 2+).

        FIX #6: This method existed but was never called. Now invoked
        from execute_build_qa_loop() on every iteration > 1.
        """
        path = self.build_dir / f'iteration_{iteration:02d}_fix.txt'
        path.write_text(fix)
        print_success(f"Saved defect fix: build/iteration_{iteration:02d}_fix.txt")
        return path

    def save_deploy_output(self, output: str):
        """Save DEPLOY output"""
        path = self.deploy_dir / 'deploy_output.txt'
        path.write_text(output)
        print_success(f"Saved DEPLOY output: deploy/deploy_output.txt")
        return path

    def save_artifact(self, name: str, content: str, artifact_type: str = 'code'):
        """Save a build artifact (code file, doc, etc.)"""
        subdir = self.build_dir / artifact_type
        subdir.mkdir(exist_ok=True)
        path = subdir / name
        path.write_text(content)
        return path

    def save_log(self, log_name: str, content: str):
        """Append timestamped entry to a log file"""
        path = self.logs_dir / f'{log_name}.log'
        timestamp = datetime.now().isoformat()
        with open(path, 'a') as f:
            f.write(f"\n[{timestamp}]\n{content}\n")
        return path

    def save_claude_questions(self, iteration: int, questions_text: str):
        """
        Save Claude's clarification questions and stop the pipeline.
        Written to logs/ so they're easy to find.
        """
        path = self.logs_dir / 'claude_questions.txt'
        timestamp = datetime.now().isoformat()
        with open(path, 'w') as f:
            f.write(f"Claude asked clarifying questions at iteration {iteration}\n")
            f.write(f"Timestamp: {timestamp}\n")
            f.write("=" * 60 + "\n\n")
            f.write(questions_text)
        print_warning(f"Claude questions saved: logs/claude_questions.txt")
        return path

    def generate_manifest(self):
        """Generate artifact manifest with SHA256 checksums"""
        manifest = {
            "generated_at": datetime.now().isoformat(),
            "artifacts":    []
        }

        for artifact_file in self.build_dir.rglob('*'):
            if artifact_file.is_file():
                with open(artifact_file, 'rb') as f:
                    content  = f.read()
                    checksum = hashlib.sha256(content).hexdigest()
                manifest["artifacts"].append({
                    "path":   str(artifact_file.relative_to(self.run_dir)),
                    "sha256": checksum,
                    "size":   len(content)
                })

        manifest_path = self.run_dir / 'artifact_manifest.json'
        manifest_path.write_text(json.dumps(manifest, indent=2))
        print_success(f"Generated artifact manifest: artifact_manifest.json")
        return manifest_path


# ============================================================
# ZIP PACKAGER
# ============================================================

def package_output_zip(run_dir: Path, startup_id: str, block: str, use_boilerplate: bool = False) -> Path:
    """
    Package the run directory into a ZIP at the base fo_harness_runs/ level.

    For boilerplate builds, also includes the teebu-saas-platform boilerplate.

    ZIP contains:
      build/     — all Claude build outputs and code
      qa/        — all QA reports
      logs/      — all prompt logs
      artifact_manifest.json
      boilerplate/  — (boilerplate builds only) teebu-saas-platform (legacy layout)

    ZIP name matches the run directory name for easy pairing.
    Returns the path to the created ZIP.
    """
    # Guard: run_dir must be a named, resolvable subdirectory — not '.' or '' which would
    # cause rglob to sweep the entire codebase and produce a multi-GB corrupt ZIP.
    resolved = run_dir.resolve()
    if not run_dir.name or run_dir.name in ('.', '..') or resolved == Path.cwd().resolve():
        raise ValueError(
            f"Invalid run_dir '{run_dir}': must be a named harness run subdirectory, "
            f"not the current working directory or an empty path."
        )
    if not resolved.is_dir():
        raise FileNotFoundError(f"run_dir does not exist: {run_dir}")

    # Excluded file types and directory names for all rglob passes
    _EXCLUDED_DIRS = frozenset(['node_modules', '.git', '.claude', 'scripts', '__pycache__'])
    _EXCLUDED_EXTS = frozenset(['.zip'])  # never recurse existing ZIPs into the archive

    zip_path = Config.OUTPUT_DIR / f'{run_dir.name}.zip'

    print_info(f"Packaging output ZIP: {zip_path.name}")

    # For boilerplate builds, prepare boilerplate source
    boilerplate_source = None
    if use_boilerplate:
        boilerplate_source = Config.PLATFORM_BOILERPLATE_DIR
        if boilerplate_source.exists():
            print_info(f"Including boilerplate: {boilerplate_source}")
        else:
            print_warning(f"Boilerplate not found at {boilerplate_source} - skipping")

    zip_path_tmp = zip_path.with_suffix('.zip.tmp')
    try:
        with zipfile.ZipFile(zip_path_tmp, 'w', zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
            if use_boilerplate and boilerplate_source and boilerplate_source.exists():
                # Assemble a single startup root folder with boilerplate + overlay
                root = Path(startup_id)

                # 1) Add boilerplate under startup root
                for file_path in boilerplate_source.rglob('*'):
                    if file_path.is_file():
                        if any(p in _EXCLUDED_DIRS for p in file_path.parts):
                            continue
                        if file_path.suffix in _EXCLUDED_EXTS:
                            continue
                        rel_path = file_path.relative_to(boilerplate_source)
                        arcname = root / rel_path
                        zf.write(file_path, arcname)

                # 2) Overlay latest build artifacts into saas-boilerplate/business/**
                build_dir = run_dir / 'build'
                artifact_dirs = sorted(build_dir.glob('iteration_*_artifacts'))
                latest_artifacts = artifact_dirs[-1] if artifact_dirs else None
                if latest_artifacts:
                    for file_path in latest_artifacts.rglob('*'):
                        if not file_path.is_file():
                            continue
                        if file_path.suffix in _EXCLUDED_EXTS:
                            continue
                        rel_path = file_path.relative_to(latest_artifacts)
                        if str(rel_path).startswith('business/'):
                            arcname = root / 'saas-boilerplate' / rel_path
                            zf.write(file_path, arcname)

                # 3) Include harness outputs under startup root for traceability
                for file_path in run_dir.rglob('*'):
                    if file_path.is_file():
                        if any(p in _EXCLUDED_DIRS for p in file_path.parts):
                            continue
                        if file_path.suffix in _EXCLUDED_EXTS:
                            continue
                        arcname = root / '_harness' / file_path.relative_to(run_dir)
                        zf.write(file_path, arcname)
            else:
                # Default legacy packaging: add run directory contents
                for file_path in run_dir.rglob('*'):
                    if file_path.is_file():
                        if file_path.suffix in _EXCLUDED_EXTS:
                            continue
                        arcname = file_path.relative_to(Config.OUTPUT_DIR)
                        zf.write(file_path, arcname)

        # Atomic rename: only replace zip_path if write completed successfully
        zip_path_tmp.rename(zip_path)

    except (KeyboardInterrupt, Exception):
        # Clean up the partial/temp ZIP so we don't leave a corrupt file behind
        if zip_path_tmp.exists():
            zip_path_tmp.unlink()
        raise

    zip_size_mb = zip_path.stat().st_size / (1024 * 1024)
    print_success(f"ZIP created: {zip_path} ({zip_size_mb:.2f} MB)")
    return zip_path


# ============================================================
# PROMPT TEMPLATES
# ============================================================

class PromptTemplates:
    """Templates for BUILD, QA, and DEPLOY prompts"""

    @staticmethod
    def build_prompt(
        block: str,
        intake_data: dict,
        build_governance: str,
        iteration: int = 1,
        max_iterations: int = Config.MAX_QA_ITERATIONS,
        previous_defects: Optional[str] = None,
        tech_stack_override: dict = None,
        external_integration_override: dict = None,
        startup_id: str = 'unknown',
        force_tech_stack: Optional[str] = None,
        required_file_inventory: Optional[list] = None,
        defect_target_files: Optional[list] = None,
        prohibitions_block: Optional[str] = None,
        ubiquitous_language_block: Optional[str] = None
    ) -> Tuple[str, str]:
        """
        Generate BUILD prompt for Claude.

        FIX #1 (Prompt Caching):
        WHY: Returns (governance_section, dynamic_section) tuple.
        Governance section is cached (saves ~90% of input token costs).
        Dynamic section varies per iteration (iteration #, defects, intake).

        FIX #5: build_governance (full ZIP contents) now injected inline.
        FIX #2: intake_data keyed as block_a / block_b to match run_intake_v7 output.

        Returns:
            tuple[str, str]: (cacheable_governance_section, dynamic_iteration_section)
        """
        # FIX #2: correct key lookup — run_intake_v7 outputs block_a / block_b
        block_key  = f'block_{block.lower()}'
        block_data = intake_data.get(block_key, {})

        # Extract tech stack for override injection
        tech_stack = force_tech_stack or block_data.get('pass_2', {}).get('tech_stack_selection', 'custom')

        # Build dynamic injections (kept as data inputs; directive text is externalized)
        tech_stack_instructions = ""
        if tech_stack_override and tech_stack == 'lowcode':
            lowcode_def = tech_stack_override.get('tech_stack_definitions', {}).get('lowcode', {})
            if lowcode_def:
                prompt_template = tech_stack_override.get('prompt_injection_template', {}).get('for_lowcode_stack', '')
                if prompt_template:
                    tech_stack_instructions = "\n\n" + prompt_template.replace('{startup_name}', startup_id) + "\n\n"

        integration_instructions = ""
        if external_integration_override:
            prompt_injection = external_integration_override.get('prompt_injection', '')
            if prompt_injection:
                integration_instructions = "\n\n" + prompt_injection + "\n\n"

        boilerplate_path_instruction = ""
        if tech_stack == 'lowcode':
            boilerplate_path_instruction = "\n\n" + DirectiveTemplateLoader.render(
                'build_boilerplate_path_rules.md'
            ) + "\n\n" + DirectiveTemplateLoader.render(
                'build_boilerplate_capabilities.md'
            ) + "\n\n" + DirectiveTemplateLoader.render(
                'build_boilerplate_sample_code.md'
            ) + "\n\n"

        # Inject canonical code skeletons for all builds — prevents Flask/Blueprint patterns
        code_skeletons_instruction = "\n\n" + DirectiveTemplateLoader.render(
            'build_code_skeletons.md'
        ) + "\n\n"

        previous_defects_section = ""
        if previous_defects:
            required_inventory_bullets = "\n".join(f"- {p}" for p in (required_file_inventory or []))
            if not required_inventory_bullets:
                required_inventory_bullets = "- (no prior manifest inventory available)"

            defect_target_bullets = "\n".join(f"- {p}" for p in (defect_target_files or []))
            if not defect_target_bullets:
                defect_target_bullets = "- (no explicit file paths found in defects; infer minimal targets)"

            _prohibitions = prohibitions_block or ''
            previous_defects_section = "\n\n" + DirectiveTemplateLoader.render(
                'build_previous_defects.md',
                previous_defects=previous_defects,
                prohibitions_block=_prohibitions
            ) + "\n\n"
            previous_defects_section += "\n\n" + DirectiveTemplateLoader.render(
                'build_patch_first_file_lock.md',
                required_file_inventory_bullets=required_inventory_bullets,
                defect_target_files_bullets=defect_target_bullets,
                prohibitions_block=_prohibitions
            ) + "\n\n"

        governance_section = DirectiveTemplateLoader.render(
            'build_governance.md',
            block=block,
            build_governance=build_governance
        )
        # FROZEN DECISIONS + SEEDED DEPS (A+E): injected into cacheable governance section.
        # Same for every build/iteration — paid once per run via prompt caching.
        governance_section += "\n\n" + FROZEN_ARCHITECTURAL_DECISIONS
        # GOLDEN EXAMPLES (C): injected into cacheable governance section.
        # Same for every build/iteration — paid once per run via prompt caching.
        governance_section += "\n\n" + GOLDEN_EXAMPLES

        dynamic_section = DirectiveTemplateLoader.render(
            'build_dynamic_base.md',
            iteration=iteration,
            max_iterations=max_iterations,
            block=block,
            block_key=block_key,
            block_data_json=json.dumps(block_data, indent=2),
            previous_defects_section=previous_defects_section,
            tech_stack_instructions=tech_stack_instructions,
            integration_instructions=integration_instructions,
            boilerplate_path_instruction=boilerplate_path_instruction,
            code_skeletons_instruction=code_skeletons_instruction
        )
        # MINI SPEC INJECTION: if intake contains _mini_spec from the AI decomposer,
        # inject it as a hard constraint between intake data and the pre-output checklist.
        # This overrides any ambiguity in the broader intake with exact entity definitions.
        mini_spec = intake_data.get('_mini_spec')
        if mini_spec:
            ms_lines = [
                "\n\n## MINI SPEC — EXACT BUILD CONTRACT (NON-NEGOTIABLE)",
                f"You are building ONLY the **{mini_spec.get('entity', 'unknown')}** entity.",
                "",
                f"**Evidence from intake:** {', '.join(mini_spec.get('evidence', []))}",
                f"**Inclusion reason:** {mini_spec.get('inclusion_reason', 'N/A')}",
                "",
                "### Fields (in addition to standard id/owner_id/status/created_at/updated_at):",
            ]
            for field in mini_spec.get('fields', []):
                constraints = ', '.join(field.get('constraints', []))
                default = f", default={field['default']}" if field.get('default') else ''
                ms_lines.append(f"- `{field['name']}` = Column({field.get('type', 'String')}, {constraints}{default})")

            ms_lines.append("")
            ms_lines.append("### CRUD Operations:")
            for op in mini_spec.get('crud_operations', []):
                ms_lines.append(f"- {op}")

            if mini_spec.get('dependencies'):
                ms_lines.append("")
                ms_lines.append("### Dependencies (these entities already exist in prior ZIPs):")
                for dep in mini_spec['dependencies']:
                    ms_lines.append(f"- {dep}")

            if mini_spec.get('relationship_cardinality'):
                ms_lines.append("")
                ms_lines.append("### Foreign Keys:")
                for rel in mini_spec['relationship_cardinality']:
                    ms_lines.append(f"- {rel['fk_field']}: foreign key to {rel['related_entity']} ({rel['type']})")

            if mini_spec.get('frontend_page'):
                fp = mini_spec['frontend_page']
                ms_lines.append("")
                ms_lines.append(f"### Frontend Page: {fp.get('route', '/unknown')}")
                ms_lines.append(f"- List view columns: {', '.join(fp.get('list_view', []))}")
                ms_lines.append(f"- Detail view fields: {', '.join(fp.get('detail_view', []))}")

            fc = mini_spec.get('file_contract', {})
            if fc.get('allowed_files'):
                ms_lines.append("")
                ms_lines.append("### ALLOWED FILES — create ONLY these files:")
                for af in fc['allowed_files']:
                    ms_lines.append(f"- `business/{af}`")
                ms_lines.append("")
                ms_lines.append("**DO NOT create any file not listed above.**")

            if mini_spec.get('out_of_scope'):
                ms_lines.append("")
                ms_lines.append("### OUT OF SCOPE — do NOT build:")
                for oos in mini_spec['out_of_scope']:
                    ms_lines.append(f"- {oos}")

            if mini_spec.get('forbidden_expansions'):
                ms_lines.append("")
                ms_lines.append("### FORBIDDEN EXPANSIONS:")
                for fe in mini_spec['forbidden_expansions']:
                    ms_lines.append(f"- {fe}")

            dynamic_section += '\n'.join(ms_lines)

        # UBIQUITOUS LANGUAGE: locked terminology from ubiquity.py
        if ubiquitous_language_block:
            dynamic_section += "\n\n" + ubiquitous_language_block

        # PRE-OUTPUT CHECKLIST (B): injected at end of dynamic section.
        # Last instruction Claude reads before generating — must stay per-iteration.
        dynamic_section += "\n\n" + PRE_OUTPUT_CHECKLIST

        return (governance_section, dynamic_section)

        # LEGACY INLINE PROMPT (INACTIVE, kept for reference only)
        # Replaced by external templates:
        # - directives/prompts/build_governance.md
        # - directives/prompts/build_dynamic_base.md
        # - directives/prompts/build_previous_defects.md
        # - directives/prompts/build_boilerplate_path_rules.md
        # ═══════════════════════════════════════════════════════════════
        # CACHEABLE SECTION - Static governance and rules
        # WHY: This content never changes between iterations.
        # Caching this saves 90% of input token costs on rounds 2+.
        # ═══════════════════════════════════════════════════════════════

        governance_section = f"""You are the FO BUILD EXECUTOR running in FOUNDER_FAST_PATH mode.

**YOUR ROLE:**
Execute the build for {block} using the locked FO Build Governance provided below.

**CRITICAL INSTRUCTION:**
Do NOT ask clarifying questions. Do NOT request additional information.
Build immediately using the intake data and governance provided.
If something is ambiguous, make a reasonable assumption and document it.
If you cannot proceed without clarification, output ONLY:
  CLARIFICATION_NEEDED: <your questions, one per line>
And nothing else.

**GOVERNANCE FILES (inline — use these as your build rules):**
{build_governance}

**CRITICAL RULES FROM GOVERNANCE:**
- No inference — follow governance literally
- No scope changes (ABORT_AND_DISCARD if scope change detected)
- Produce all required code artifacts

**DO NOT OUTPUT THESE FILES (the harness generates them automatically):**
- artifact_manifest.json — SKIP, generated by harness
- build_state.json — SKIP, generated by harness
- execution_declaration.json — SKIP, generated by harness
- README.md — SKIP, generated post-QA
- .env.example — SKIP, generated post-QA
- .gitignore — SKIP, generated post-QA
This saves tokens for actual code files.

**ARTIFACT REQUIREMENTS:**
- All code files in separate artifacts (no truncation)
- package.json with dependencies
- All configuration files

**OUTPUT FORMAT:**
1. Provide complete implementation (no placeholders, no "...continued")
2. Use artifacts/code blocks for all files
3. Do NOT include artifact_manifest.json or build_state.json (auto-generated)
4. End with exactly: "BUILD STATE: COMPLETED_CLOSED"

**═══════════════════════════════════════════════════════════════**
**MULTI-PART OUTPUT (CRITICAL FOR LARGE BUILDS)**
**═══════════════════════════════════════════════════════════════**

Your output limit is 16,000 tokens (~12,000 words). If your build has more files than
can fit in a single response, you MUST split your output into numbered parts (like TCP):

1. Start Part 1 with: <!-- PART 1/N --> (estimate N based on total file count)
2. Include as many COMPLETE files as will fit (NEVER cut a file mid-content)
3. End Part 1 with: <!-- END PART 1/N --> followed by a list of remaining files:
   REMAINING FILES: file1.js, file2.js, config.json, ...
4. I will automatically request each subsequent part — do NOT stop or ask
5. The LAST part MUST end with: BUILD STATE: COMPLETED_CLOSED
   (Do NOT output artifact_manifest.json or build_state.json — auto-generated by harness)

**MULTI-PART RULES:**
- Each file appears in EXACTLY ONE part. Never repeat a file across parts.
- Never cut a file in the middle. If a file won't fit, move it entirely to the next part.
- If your build fits in one response, do NOT use parts — just output normally.
- When estimating N, assume ~4-5 files per part depending on file size.

**═══════════════════════════════════════════════════════════════**
**ARTIFACT OUTPUT FORMAT - MANDATORY RULES**
**═══════════════════════════════════════════════════════════════**

You MUST follow these formatting rules exactly for ALL code artifacts:

**CRITICAL: README FILES MUST NOT CONTAIN CODE BLOCKS**
If you are creating README.md or any documentation:
- NEVER use triple-backtick code blocks for bash, sh, javascript, sql, jsx, or any language
- Write commands as plain text: "Run: npm install" or "Execute: npm run dev"
- Use inline code for commands: Run `npm install` to install dependencies
- DO NOT include example code snippets, SQL schemas, or integration examples in code blocks
- Code blocks in README will cause extraction errors - DO NOT USE THEM
- If you need to show SQL schema, database setup, or integration examples, use plain text or inline code

**CRITICAL: ALL CODE MUST HAVE FILE: HEADERS**
- EVERY code block you write MUST have a **FILE: path/to/file.ext** header
- NO example code, integration snippets, or documentation examples outside of FILE: headers
- If you include ANY code block without a FILE: header, it will be extracted as a numbered artifact
- Example snippets should be written as plain text or inline code, NOT code blocks

**RULE 1: File Path Declaration**
Before EVERY code block, declare the file path on its own line:
**FILE: path/to/filename.ext**

**RULE 2: Code Block Format**
Immediately after the file path, start the code block:
```language
code content here
```

**RULE 3: No Inline Filename Hints**
Do NOT put filenames on the code fence line or as comments inside the code.
Only use the **FILE:** declaration above the code block.

**RULE 4: Subdirectories**
You MAY use subdirectories in paths:
- **FILE: src/index.html** ✓
- **FILE: js/app.js** ✓
- **FILE: config/database.json** ✓

**RULE 5: Complete Files Only**
Every file must be complete. NO placeholders like "// ... rest of code".
If output limit is reached, end gracefully and I will request continuation.

**RULE 6: Metadata Files — DO NOT OUTPUT**
The harness auto-generates these files. Do NOT output them:
- artifact_manifest.json (auto-generated with SHA256 checksums)
- build_state.json (auto-generated)
- execution_declaration.json (auto-generated)
Instead, use your token budget for actual code files.
Just end your output with: BUILD STATE: COMPLETED_CLOSED

**EXAMPLE FORMAT:**

**FILE: index.html**
```html
<!DOCTYPE html>
<html>
<head><title>Example</title></head>
<body><h1>Hello World</h1></body>
</html>
```

**FILE: js/app.js**
```javascript
console.log('Hello from app.js');
```

**FILE: package.json**
```json
{{
  "name": "my-app",
  "version": "1.0.0",
  "dependencies": {{}}
}}
```

(No artifact_manifest.json, build_state.json, or README needed — auto-generated by harness)

**═══════════════════════════════════════════════════════════════**
"""

        # ═══════════════════════════════════════════════════════════════
        # DYNAMIC SECTION - Changes per iteration
        # WHY: This content varies (iteration #, defects, intake data).
        # Not cached - sent fresh each time.
        # ═══════════════════════════════════════════════════════════════

        dynamic_section = f"""
**ITERATION:** {iteration} of {Config.MAX_QA_ITERATIONS}
**YOUR TASK:**
1. Extract {block} intake data from the INTAKE DATA section below
2. Execute BUILD according to fo_build_state_machine.json (from governance above)
3. Follow all enforcement rules (tier, scope, iteration, QA routing)
4. Produce COMPLETED_CLOSED state with all required artifacts
5. You are on iteration {iteration} - Max 5 iterations per task

**PHASED FEATURE RULE (NON-NEGOTIABLE):**
- If a feature/integration is marked "optional", "phase 2", "phase 3", or "later",
  you MUST NOT implement it now. Provide only a stub/interface and TODO notes.
  Do NOT add real integration logic until it is explicitly in-scope for this phase.

"""

        if previous_defects:
            dynamic_section += f"""
**PREVIOUS QA ITERATION — DEFECTS TO FIX:**
ChatGPT QA reported the following defects. Fix ALL of them.

**CRITICAL RULES FOR DEFECT FIXES:**
1. **Fix ONLY the reported defects** - Do NOT change unrelated code
2. **Output ALL artifacts** - You MUST include EVERY file from previous iteration
3. **Never drop files** - If a file isn't mentioned in defects, include it unchanged
4. **No scope changes** - Do NOT add new features or functionality
5. **No over-engineering** - Fix exactly what QA asks, nothing more

**WHY THIS MATTERS:**
Lowcode builds regenerate ALL files every iteration. If you don't output a file,
it will be considered DELETED. QA will flag it as missing and you'll loop forever.

**DEFECTS TO FIX:**
{previous_defects}

**REMEMBER:** Output the COMPLETE build (all files) with ONLY the defects fixed.
"""

        # Inject tech stack override if lowcode
        tech_stack_instructions = ""
        if tech_stack_override and tech_stack == 'lowcode':
            lowcode_def = tech_stack_override.get('tech_stack_definitions', {}).get('lowcode', {})
            if lowcode_def:
                prompt_template = tech_stack_override.get('prompt_injection_template', {}).get('for_lowcode_stack', '')
                if prompt_template:
                    tech_stack_instructions = "\n\n" + prompt_template.replace('{startup_name}', startup_id) + "\n\n"

        # Enforce boilerplate-only output paths when lowcode is active
        boilerplate_path_instruction = ""
        if tech_stack == 'lowcode':
            boilerplate_path_instruction = "\n\n" + DirectiveTemplateLoader.render(
                'build_boilerplate_path_rules.md'
            ) + "\n\n" + DirectiveTemplateLoader.render(
                'build_boilerplate_capabilities.md'
            ) + "\n\n" + DirectiveTemplateLoader.render(
                'build_boilerplate_sample_code.md'
            ) + "\n\n"

        # Inject canonical code skeletons for all builds — prevents Flask/Blueprint patterns
        code_skeletons_instruction = "\n\n" + DirectiveTemplateLoader.render(
            'build_code_skeletons.md'
        ) + "\n\n"

        # Inject external integration policy
        integration_instructions = ""
        if external_integration_override:
            prompt_injection = external_integration_override.get('prompt_injection', '')
            if prompt_injection:
                integration_instructions = "\n\n" + prompt_injection + "\n\n"

        dynamic_section += f"""
**INTAKE DATA ({block} — key: {block_key}):**
{json.dumps(block_data, indent=2)}
{tech_stack_instructions}{integration_instructions}{boilerplate_path_instruction}{code_skeletons_instruction}
**BEGIN BUILD EXECUTION NOW.**
"""

        return (governance_section, dynamic_section)

    @staticmethod
    def qa_prompt(build_output: str, intake_data: dict, block: str, tech_stack: str = 'custom', qa_override: dict = None, prohibitions_block: str = '', defect_history_block: str = '', resolved_defects_block: str = '', ubiquitous_language_block: str = '') -> str:
        """
        Generate QA prompt for ChatGPT.

        FIX #2: correct key lookup — block_a / block_b.
        FIX #3: Add tech stack awareness for lowcode builds.
        FIX #8: Add QA override support for tightened evaluation.
        """
        if qa_override is None:
            qa_override = {}

        block_key  = f'block_{block.lower()}'
        block_data = intake_data.get(block_key, {})

        # Build tech stack context for lowcode
        tech_stack_context = ""
        if tech_stack == 'lowcode':
            tech_stack_context = """

**═══════════════════════════════════════════════════════════════**
**TECH STACK CONTEXT - LOWCODE BUILD**
**═══════════════════════════════════════════════════════════════**

This is a LOWCODE build using the teebu-saas-boilerplate framework.

**WHAT THE BOILERPLATE ALREADY PROVIDES:**
- Authentication & authorization (JWT, role-based access control)
- Payment processing infrastructure (Stripe integration)
- Database models, migrations, and ORM setup
- Email service integration
- UI framework (React, Tailwind CSS)
- API infrastructure (REST endpoints, middleware)
- Deployment configuration (Docker, CI/CD)

**WHAT CLAUDE BUILT (Business Logic Only):**
- Custom models specific to this business domain
- Business services and logic
- Domain-specific React components
- Configuration to integrate with boilerplate
- API endpoints for business features

**CRITICAL QA INSTRUCTIONS FOR LOWCODE:**
1. DO NOT flag missing infrastructure (auth, payments, DB setup, email) as defects
   → The boilerplate provides these - they are NOT in Claude's output
2. DO NOT flag "missing deployment config" or "missing Docker files" as defects
   → The boilerplate handles deployment
3. DO NOT flag "no UI framework setup" or "missing Tailwind config" as defects
   → The boilerplate provides the UI foundation
4. DO validate that business logic correctly integrates with boilerplate patterns
5. DO validate that business models/services/components are complete
6. DO flag if Claude built infrastructure that should use boilerplate instead

**BOILERPLATE MODULES — WHAT CORRECT INTEGRATION LOOKS LIKE:**
RULE: If you see any import from `core.*` or `lib.*_lib` in a file, that capability IS correctly integrated. You MUST NOT flag it as missing, broken, or incorrectly implemented unless you can quote a specific wrong line. The presence of the import IS the implementation.
The following imports and patterns ARE correct boilerplate usage. Do NOT flag them as bugs or missing implementations:

Authentication (correct):
  `from core.rbac import get_current_user` + `Depends(get_current_user)` in route signature
  `current_user["sub"]` used as user/owner/consultant ID
  `from core.rbac import require_role` + `Depends(require_role("admin"))` for role gating
  Frontend: `import {{ useAuth0 }} from '@auth0/auth0-react'` + `user.sub`
  → DO NOT flag: "missing authentication", "consultant_id not validated", "hardcoded user check"
  → DO FLAG: hardcoded ID strings like `'consultant_1'`, `'current_user'`, `'user_123'`

Multi-tenancy (correct):
  `from core.tenancy import TenantMixin` on SQLAlchemy models, `get_tenant_db(db, tenant_id)`
  → DO NOT flag: "missing tenant isolation" when TenantMixin is present

Usage limits (correct):
  `from core.usage_limits import check_and_increment` called before metered operations
  → DO NOT flag: "missing quota enforcement" when check_and_increment is called

AI calls (correct):
  `from core.ai_governance import call_ai` — handles Claude/OpenAI, cost tracking, budgets
  → DO NOT flag: "missing AI implementation", "no cost tracking" when call_ai is used

Social posting (correct):
  `from core.posting import post_to_reddit, post_to_twitter, post_to_linkedin` etc.
  → DO NOT flag: "missing social integration" when core.posting is imported

Email (correct):
  `from lib.mailerlite_lib import load_mailerlite_lib` + `.send_welcome_email()` etc.
  → DO NOT flag: "missing email service" when mailerlite_lib is imported

Billing/Stripe (correct):
  `from lib.stripe_lib import load_stripe_lib` + `.create_subscription_product()` etc.
  → DO NOT flag: "missing payment implementation" when stripe_lib is imported

Analytics (correct):
  `from lib.analytics_lib import load_analytics_lib` + `.track_event()` etc.
  → DO NOT flag: "missing analytics" when analytics_lib is imported

Search (correct):
  `from lib.meilisearch_lib import load_meilisearch_lib` + `.search()` etc.
  → DO NOT flag: "missing search" when meilisearch_lib is imported

Onboarding/Trial/Activation (correct):
  `from core.onboarding import get_or_create_onboarding, mark_step_complete`
  `from core.trial import start_trial, is_trial_active`
  `from core.activation import record_activation`
  → DO NOT flag missing onboarding/trial/activation when these are imported

**WHAT TO FLAG (incorrect patterns even in lowcode):**
  - Hardcoded user/owner IDs: `consultant_id: 'consultant_1'`, `user_id = 'test_user'`
  - Dict/in-memory storage: `items_db = {}`, `data = []` used as a database
  - Sequential integer IDs: `id = len(db) + 1`
  - Flask patterns in backend: `from flask import Blueprint`, `@bp.route`, `jsonify()`
  - Hardcoded data arrays in frontend instead of API fetch calls
  - Custom reimplementation of auth, payments, or email that bypasses boilerplate modules

**═══════════════════════════════════════════════════════════════**
**SCOPE VALIDATION RULES FOR LOWCODE**
**═══════════════════════════════════════════════════════════════**

**WHY THIS MATTERS:** Lowcode builds implement business logic only. The intake
specifies HIGH-LEVEL features but not data model details. Distinguish between:
- **Scope creep** = NEW features not in intake
- **Reasonable implementation** = Data model details supporting defined features

**✅ ACCEPTABLE (NOT scope creep):**

**Standard Data Model Properties:**
- Domain-appropriate attributes for models mentioned in HLD
  Examples: Horse (age, color, gender, breed), Member (preferences, contact),
  Race (track, position, earnings, date), Breeding (sire, dam, offspring)
- These are reasonable inferences to implement the HLD features

**Common Service Methods:**
- Standard CRUD operations: findById, findAll, create, update, delete
- Data access methods needed for features: getByOwner, getActive, filter
- These are necessary to implement ANY data-driven feature

**Standard Test Coverage:**
- Unit tests for implemented models and services
- API endpoint tests for implemented routes
- Integration tests for business logic
- Test coverage is EXPECTED for professional builds

**Configuration & Setup Files:**
- jest.config.js, .env.example, .gitignore, package.json
- Database migration/schema files for business models
- These are necessary for ANY working application

**Reasonable Error Handling:**
- Input validation, error messages, status codes
- Authorization checks for protected resources
- These are professional development standards

**❌ SCOPE CREEP (REJECT these):**

**NEW User-Facing Features:**
- Betting/wagering system (if not in intake)
- Social networking/forums (if not in intake)
- Analytics dashboards (if not in intake)
- Mobile app (if only web specified)

**NEW External Integrations:**
- Payment providers (if intake specifies data feeds only)
- SMS/notifications (if only email specified)
- Third-party APIs (unless explicitly required)

**NEW Business Capabilities:**
- Live streaming (if not in intake)
- Automated trading (if not in intake)
- AI/ML features (if not in intake)

**Significant Complexity Not Implied:**
- Complex algorithms beyond stated requirements
- Advanced optimization not requested
- Enterprise features for simple use case

**EXAMPLES OF CORRECT EVALUATION:**

❌ WRONG: "Horse model includes 'age' property - SCOPE CREEP (not in intake)"
✅ RIGHT: "Horse model needs age to display horse information (HLD feature)"

❌ WRONG: "Tests include horse.test.js - SCOPE CREEP (tests not specified)"
✅ RIGHT: "Test coverage is standard practice - ACCEPTABLE"

❌ WRONG: "MembershipService has upgradeMembership() - SCOPE CREEP"
✅ RIGHT: "Membership management is in HLD - method is reasonable"

✅ CORRECT: "Added betting feature - SCOPE CREEP (not in intake)"
✅ CORRECT: "Added SMS notifications - SCOPE CREEP (only email specified)"

**WHEN IN DOUBT:** Ask yourself: "Does this enable a NEW feature not in the HLD,
or is it a reasonable implementation detail to support an existing feature?"

**═══════════════════════════════════════════════════════════════**
"""

        # Inject sample code QA reference for lowcode builds
        if tech_stack == 'lowcode':
            tech_stack_context += "\n\n" + DirectiveTemplateLoader.render(
                'build_boilerplate_sample_code.md'
            ) + "\n\n"

        # FIX #8: Inject QA override if present
        qa_override_context = ""
        if qa_override and 'prompt_injection' in qa_override:
            qa_override_context = "\n\n" + qa_override['prompt_injection'] + "\n\n"

        # Inject ubiquitous language into QA context
        ubiquitous_language_context = ""
        if ubiquitous_language_block:
            ubiquitous_language_context = "\n\n" + ubiquitous_language_block + "\n\n"

        return DirectiveTemplateLoader.render(
            'qa_prompt.md',
            tech_stack_context=tech_stack_context,
            qa_override_context=qa_override_context,
            prohibitions_block=prohibitions_block,
            defect_history_block=defect_history_block,
            resolved_defects_block=resolved_defects_block,
            ubiquitous_language_context=ubiquitous_language_context,
            block=block,
            block_key=block_key,
            block_data_json=json.dumps(block_data, indent=2),
            build_output=build_output
        )

        # LEGACY INLINE PROMPT (INACTIVE, kept for reference only)
        # Replaced by external template:
        # - directives/prompts/qa_prompt.md
        return f"""You are the FO QA OPERATOR (ChatGPT).

**YOUR ROLE:**
Validate the build output from Claude against the intake requirements
and FO Build Governance.
{tech_stack_context}{qa_override_context}
**INTAKE REQUIREMENTS ({block} — key: {block_key}):**
{json.dumps(block_data, indent=2)}

**BUILD OUTPUT FROM CLAUDE:**
{build_output}

**YOUR TASK:**
1. Verify all tasks from intake were completed
2. Verify all required artifacts are present:
   ✅ CRITICAL: All code files for features in intake
   ✅ CRITICAL: package.json (with dependencies)
   ⚠️  MEDIUM: Test files (nice-to-have for POC, required for production)
   ⚠️  Flag MISSING CRITICAL as SPEC_COMPLIANCE_ISSUE, MEDIUM as LOW severity
3. Check for scope compliance (no extra features beyond intake)
4. Check for implementation bugs (code correctness)

**DO NOT FLAG THESE AS DEFECTS (auto-generated by harness after QA):**
- artifact_manifest.json — auto-generated by the test harness with SHA256 checksums
- build_state.json — auto-generated by the test harness
- execution_declaration.json — auto-generated by the test harness
- README.md — auto-generated in post-QA polish step
- .env.example — auto-generated in post-QA polish step
- .gitignore — auto-generated in post-QA polish step
- Test files — auto-generated in post-QA polish step (flag as MEDIUM at most)
These files are NOT expected in Claude's build output. Do NOT flag them as missing.

**DEFECT CLASSIFICATION:**
- IMPLEMENTATION_BUG:     Code doesn't work as specified (logic errors, broken functionality)
- SPEC_COMPLIANCE_ISSUE:  Missing CRITICAL artifacts or doesn't match intake requirements
- SCOPE_CHANGE_REQUEST:   Extra USER-FACING features not in intake (CRITICAL)

**SEVERITY GUIDELINES (FIX #8 - Tightened):**
- CRITICAL: Missing core business logic, broken functionality, major scope creep
- HIGH:     Missing important files (README), incorrect implementation of key features
- MEDIUM:   Missing nice-to-have features (tests for POC), minor deviations from spec
- LOW:      Documentation formatting, code style, non-critical optimizations

**CRITICAL: FOCUS ON WHAT MATTERS**
- DO flag: Missing core features, broken code, new features not in intake
- DO flag: Missing package.json
- DON'T flag: Missing artifact_manifest.json, build_state.json, execution_declaration.json (auto-generated)
- DON'T flag: Missing README.md, .env.example, .gitignore, tests (auto-generated in polish step)
- DON'T flag: Missing tests as HIGH (use MEDIUM at most for POC builds)
- DON'T flag: Code organization preferences (unless clearly wrong)
- DON'T flag: Documentation formatting issues

**OUTPUT FORMAT:**
Provide a structured QA report:

## QA REPORT

### SUMMARY
- Total defects found: [number]
- IMPLEMENTATION_BUG: [count]
- SPEC_COMPLIANCE_ISSUE: [count]
- SCOPE_CHANGE_REQUEST: [count]

### DEFECTS
[List each defect:]
DEFECT-[ID]: [classification]
  - Location: [file/line]
  - Problem: [what's wrong]
  - Expected: [what should be]
  - Severity: HIGH | MEDIUM | LOW

### VERDICT
If ACCEPTED: end with exactly: "QA STATUS: ACCEPTED - Ready for deployment"
If REJECTED: end with exactly: "QA STATUS: REJECTED - [X] defects require fixing"

**BEGIN QA ANALYSIS NOW.**
"""

    @staticmethod
    def static_fix_prompt(
        static_defects: str,
        required_file_inventory: list,
        defect_target_files: list,
        prohibitions_block: str = ''
    ) -> str:
        """
        Generate static fix prompt for Claude.
        Used after feature QA acceptance to fix deterministic code issues
        (syntax errors, duplicate models, missing imports, unauthenticated routes, etc.)
        """
        required_inventory_bullets = "\n".join(f"- {p}" for p in (required_file_inventory or []))
        if not required_inventory_bullets:
            required_inventory_bullets = "- (no prior manifest inventory available)"

        defect_target_bullets = "\n".join(f"- {p}" for p in (defect_target_files or []))
        if not defect_target_bullets:
            defect_target_bullets = "- (no explicit file paths found in defects; infer minimal targets)"

        return DirectiveTemplateLoader.render(
            'build_static_fix.md',
            static_defects=static_defects,
            required_file_inventory_bullets=required_inventory_bullets,
            defect_target_files_bullets=defect_target_bullets,
            prohibitions_block=prohibitions_block
        )

    @staticmethod
    def integration_fix_prompt(
        integration_defects: str,
        required_file_inventory: list,
        defect_target_files: list,
        current_file_contents: dict,
    ) -> str:
        """
        Generate integration fix prompt for Claude.
        Passes CURRENT file contents so Claude patches surgically rather than
        reconstructing from memory (which causes __tablename__/Base import regressions).
        current_file_contents: {rel_path: file_text} for existing files, or NEW FILE placeholder for files that must be created.
        """
        required_inventory_bullets = "\n".join(f"- {p}" for p in (required_file_inventory or []))
        if not required_inventory_bullets:
            required_inventory_bullets = "- (no prior manifest inventory available)"

        defect_target_bullets = "\n".join(f"- {p}" for p in (defect_target_files or []))
        if not defect_target_bullets:
            defect_target_bullets = "- (no explicit file paths found in defects; infer minimal targets)"

        # Build current file content block
        lang_map = {'py': 'python', 'jsx': 'jsx', 'js': 'jsx', 'json': 'json',
                    'md': 'markdown', 'txt': 'text', 'css': 'css'}
        file_blocks = []
        for path in sorted(current_file_contents.keys()):
            content = current_file_contents[path]
            ext = path.rsplit('.', 1)[-1] if '.' in path else 'text'
            lang = lang_map.get(ext, 'text')
            file_blocks.append(f"**FILE: {path}**\n```{lang}\n{content}\n```")
        current_file_contents_block = "\n\n".join(file_blocks) if file_blocks else "(no current file contents found — regenerate from scratch using boilerplate patterns)"

        return DirectiveTemplateLoader.render(
            'build_integration_fix.md',
            integration_defects=integration_defects,
            required_file_inventory_bullets=required_inventory_bullets,
            defect_target_files_bullets=defect_target_bullets,
            current_file_contents=current_file_contents_block,
        )

    @staticmethod
    def ai_consistency_prompt(file_contents: dict) -> str:
        """
        Generate AI consistency check prompt for Claude.
        file_contents: {rel_path: file_text} for all business/ artifacts.
        Returns a prompt asking Claude to check cross-file consistency.
        """
        # Build artifact block
        artifact_lines = []
        for path, content in sorted(file_contents.items()):
            ext = path.rsplit('.', 1)[-1] if '.' in path else 'text'
            lang_map = {'py': 'python', 'jsx': 'jsx', 'js': 'jsx', 'json': 'json',
                        'md': 'markdown', 'txt': 'text', 'css': 'css'}
            lang = lang_map.get(ext, 'text')
            artifact_lines.append(f"**FILE: {path}**\n```{lang}\n{content}\n```")
        artifact_contents = "\n\n".join(artifact_lines) if artifact_lines else "(no business/ files found)"

        return DirectiveTemplateLoader.render(
            'build_ai_consistency.md',
            artifact_contents=artifact_contents
        )

    @staticmethod
    def quality_gate_prompt(file_contents: dict, intake_data: dict) -> str:
        """
        Generate mandatory quality gate prompt for ChatGPT.
        Evaluates: completeness vs intake, code quality, enhanceability, deployability.
        """
        artifact_lines = []
        for path, content in sorted(file_contents.items()):
            ext = path.rsplit('.', 1)[-1] if '.' in path else 'text'
            lang_map = {'py': 'python', 'jsx': 'jsx', 'js': 'jsx', 'json': 'json',
                        'md': 'markdown', 'txt': 'text', 'css': 'css'}
            lang = lang_map.get(ext, 'text')
            artifact_lines.append(f"**FILE: {path}**\n```{lang}\n{content}\n```")
        artifact_contents = "\n\n".join(artifact_lines) if artifact_lines else "(no business/ files found)"
        return DirectiveTemplateLoader.render(
            'build_quality_gate.md',
            intake_json=json.dumps(intake_data, indent=2),
            artifact_contents=artifact_contents
        )

    @staticmethod
    def deploy_prompt(build_output: str, deploy_governance: str) -> str:
        """
        Generate DEPLOY prompt for Claude.

        FIX #5: deploy_governance (full ZIP contents) now injected inline.
        """
        return DirectiveTemplateLoader.render(
            'deploy_prompt.md',
            build_output=build_output,
            deploy_governance=deploy_governance
        )

        # LEGACY INLINE PROMPT (INACTIVE, kept for reference only)
        # Replaced by external template:
        # - directives/prompts/deploy_prompt.md
        return f"""You are the FO DEPLOY EXECUTOR.

**YOUR ROLE:**
Execute deployment using the locked FO Deploy Governance provided below.

**GOVERNANCE FILES (inline — use these as your deploy rules):**
{deploy_governance}

**YOUR TASK:**
1. Validate build_state = COMPLETED_CLOSED
2. Validate all artifacts exist with correct checksums
3. Execute deployment per governance rules
4. Produce terminal state: DEPLOYED or DEPLOY_FAILED

**CRITICAL RULES FROM GOVERNANCE:**
- Follow fo_deploy_artifact_eligibility_rules.json (validate checksums)
- Follow fo_deploy_completion_rules.json (validation procedures)
- Produce deployment_state.json

**BUILD OUTPUT:**
{build_output}

**OUTPUT FORMAT:**
1. Artifact validation results
2. Deployment commands executed
3. Environment validation
4. Final deployment state
5. End with exactly: "DEPLOYMENT STATE: DEPLOYED" or "DEPLOYMENT STATE: DEPLOY_FAILED"

**BEGIN DEPLOYMENT NOW.**
"""


# ============================================================
# ORCHESTRATOR
# ============================================================

class FOHarness:
    """Main orchestrator for BUILD → QA → DEPLOY"""

    def __init__(self, intake_file: Path, block: str, do_deploy: bool, cli_args: argparse.Namespace = None):
        self.intake_file = intake_file
        self.block       = block.upper()   # 'A' or 'B'
        self.do_deploy   = do_deploy
        self.cli_args    = cli_args
        self.confirm_run_log = (getattr(cli_args, "confirm_run_log", "NO").strip().upper() == "YES") if cli_args else False
        self.max_qa_iterations = int(getattr(cli_args, "max_iterations", Config.MAX_QA_ITERATIONS)) if cli_args else Config.MAX_QA_ITERATIONS
        self.max_build_parts = int(getattr(cli_args, "max_parts", Config.MAX_BUILD_PARTS_DEFAULT)) if cli_args else Config.MAX_BUILD_PARTS_DEFAULT
        self.max_build_continuations = int(getattr(cli_args, "max_continuations", Config.MAX_BUILD_CONTINUATIONS_DEFAULT)) if cli_args else Config.MAX_BUILD_CONTINUATIONS_DEFAULT
        # Gate 4 is now mandatory (always ON).
        self.enable_quality_gate = True
        # Factory mode: skip Gate 3 (AI Consistency), Gate 4 fails only on DEPLOYABILITY=FAIL
        self.factory_mode = bool(getattr(cli_args, 'factory_mode', False)) if cli_args else False
        # --no-polish: skip post-QA polish step (use for Phase 1 of a phased build)
        self.skip_polish = bool(getattr(cli_args, 'no_polish', False)) if cli_args else False
        self._last_claude_cost  = 0.0
        self._last_chatgpt_cost = 0.0

        # Load intake JSON
        # Handles both pure JSON and marker-wrapped formats
        with open(intake_file) as f:
            content = f.read()
        if content.strip().startswith('{'):
            self.intake_data = json.loads(content)
        else:
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                self.intake_data = json.loads(json_match.group(0))
            else:
                raise ValueError(f"Could not parse intake JSON from: {intake_file}")

        # Extract startup identity
        self.startup_id = self.intake_data.get('startup_idea_id', 'unknown')

        # Load ubiquitous language glossary (if generated by ubiquity.py)
        self.ubiquitous_language_block = ''
        _ul_path = intake_file.parent / f'{intake_file.stem}_ubiquitous_language.json'
        if not _ul_path.exists():
            # Try the base stem (without _p1_entity suffix) for entity-level intakes
            _base_stem = re.sub(r'_p1_[a-z_]+$', '', intake_file.stem)
            _ul_path = intake_file.parent / f'{_base_stem}_ubiquitous_language.json'
        if _ul_path.exists():
            try:
                with open(_ul_path) as _uf:
                    _ul_data = json.load(_uf)
                self.ubiquitous_language_block = _ul_data.get('prompt_lock_block', '')
                if self.ubiquitous_language_block:
                    print_info(f"Ubiquitous language loaded ({len(self.ubiquitous_language_block)} chars)")
            except Exception as e:
                print_warning(f"Failed to load ubiquitous language: {e}")

        # Extract tech stack from intake
        block_key = f'block_{self.block.lower()}'
        block_data = self.intake_data.get(block_key, {})
        self.tech_stack = block_data.get('pass_2', {}).get('tech_stack_selection', 'custom')
        self.use_boilerplate = should_use_platform_boilerplate(self.intake_data, self.block)
        self.effective_tech_stack = 'lowcode' if self.use_boilerplate else 'custom'

        # Load governance ZIPs into memory (inline for prompts)
        print_info("Loading BUILD governance ZIP...")
        self.build_governance = load_governance_zip(Path(Config.BUILD_GOVERNANCE_ZIP))
        print_success("BUILD governance loaded")

        # Load tech stack override (local testing)
        self.tech_stack_override = load_tech_stack_override()
        if self.tech_stack_override:
            print_info(f"Tech stack override loaded (stack: {self.tech_stack})")

        # Load external integration override (local testing)
        self.external_integration_override = load_external_integration_override()
        if self.external_integration_override:
            print_info("External integration override loaded")

        # Load QA override (local testing - FIX #8)
        self.qa_override = load_qa_override()
        if self.qa_override:
            print_info("QA override loaded (tightened evaluation criteria)")

        # Resolve QA_POLISH_2 directive path (CLI override takes precedence)
        self.qa_polish_2_directive_path = self._resolve_qa_polish_2_directive_path()
        self.qa_polish_2_directive = load_text_file(self.qa_polish_2_directive_path)
        print_info(f"QA_POLISH_2 directive: {self.qa_polish_2_directive_path}")

        # Resolve testcase-doc directive path (templated, user-editable)
        self.qa_testcase_directive_path = self._resolve_qa_testcase_directive_path()
        self.qa_testcase_directive = None
        if self.qa_testcase_directive_path:
            self.qa_testcase_directive = load_text_file(self.qa_testcase_directive_path)
            print_info(f"QA_TESTCASE directive: {self.qa_testcase_directive_path}")
        else:
            print_warning("QA_TESTCASE directive not found — testcase doc polish step will be skipped")

        self.deploy_governance = None

        # Warm-start: reuse an existing run directory if --resume-run was given
        resume_run = Path(getattr(cli_args, 'resume_run', None) or '')
        _cwd = Path.cwd().resolve()
        _valid_resume = (
            resume_run.name  # non-empty name (excludes '.', '..', '')
            and resume_run.name not in ('.', '..')
            and resume_run.resolve() != _cwd
            and resume_run.is_dir()
        )
        if _valid_resume:
            self.run_dir = resume_run
            print_info(f"Warm-start: reusing run directory {self.run_dir}")
        else:
            # Create run directory with timestamp
            timestamp    = datetime.now().strftime('%Y%m%d_%H%M%S')
            self.run_dir = Config.OUTPUT_DIR / f'{self.startup_id}_BLOCK_{self.block}_{timestamp}'
            self.run_dir.mkdir(parents=True, exist_ok=True)
            # Persist run metadata for traceability
            self._write_run_metadata()

        # Initialize components
        self.claude    = ClaudeClient()
        self.chatgpt   = ChatGPTClient()
        self.artifacts = ArtifactManager(self.run_dir)

        print_header("FO HARNESS INITIALIZED")
        print_info(f"Startup:       {self.startup_id}")
        print_info(f"Block:         BLOCK_{self.block}")
        print_info(f"Tech stack:    {self.tech_stack} (effective: {self.effective_tech_stack})")
        print_info(f"Boilerplate:   {'YES' if self.use_boilerplate else 'NO'}")
        print_info(f"Max iterations:{self.max_qa_iterations}")
        print_info(f"Build caps:    max_parts={self.max_build_parts}, max_continuations={self.max_build_continuations}")
        print_info(f"Quality gate:  {'ON' if self.enable_quality_gate else 'OFF'}")
        print_info(f"Factory mode:  {'ON (Gate 3 OFF, Gate 4 Deployability-only)' if self.factory_mode else 'OFF'}")
        print_info(f"Polish:        {'SKIP (--no-polish)' if self.skip_polish else 'ON'}")
        print_info(f"Deploy:        {'YES' if self.do_deploy else 'NO — ZIP output only'}")
        print_info(f"Run directory: {self.run_dir}")

    def _write_run_metadata(self):
        """Write a run metadata file with CLI args and effective settings."""
        def _coerce_jsonable(value):
            if isinstance(value, Path):
                return str(value)
            if isinstance(value, dict):
                return {k: _coerce_jsonable(v) for k, v in value.items()}
            if isinstance(value, (list, tuple)):
                return [_coerce_jsonable(v) for v in value]
            return value

        metadata = {
            "timestamp": datetime.now().isoformat(),
            "intake_file": str(self.intake_file),
            "startup_id": self.startup_id,
            "block": self.block,
            "deploy": self.do_deploy,
            "tech_stack": self.tech_stack,
            "effective_tech_stack": self.effective_tech_stack,
            "use_boilerplate": self.use_boilerplate,
            "build_governance_zip": str(Config.BUILD_GOVERNANCE_ZIP),
            "platform_boilerplate_dir": str(Config.PLATFORM_BOILERPLATE_DIR),
            "qa_polish_2_directive_path": str(self.qa_polish_2_directive_path),
            "qa_testcase_directive_path": str(self.qa_testcase_directive_path) if self.qa_testcase_directive_path else None,
            "cli_args": _coerce_jsonable(vars(self.cli_args)) if self.cli_args else None
        }

        metadata_path = self.run_dir / 'run_metadata.json'
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)

    def _save_run_status(self, status: str, iteration: int = 0,
                         reason: str = '', detail: str = '',
                         accepted_at_iteration: int = None,
                         defect_count: int = None):
        """
        Write run_status.json to run directory on EVERY exit path.

        This is the single source of truth for how a run ended.
        Written at: QA_ACCEPTED, NON_CONVERGING, MAX_ITERATIONS,
        CIRCUIT_BREAKER_*, QA_VERDICT_UNCLEAR, CTRL_C, QUESTIONS_DETECTED,
        RESUME_FAILED, ERROR.

        The circuit breaker (Steal 1.1) will extend this with its own
        status values and diagnostic fields.
        """
        run_status = {
            "status": status,
            "reason": reason,
            "detail": detail,
            "iteration": iteration,
            "accepted_at_iteration": accepted_at_iteration,
            "defect_count": defect_count,
            "timestamp": datetime.now().isoformat(),
            "startup_id": self.startup_id,
            "block": self.block,
            "max_iterations": self.max_qa_iterations,
        }
        # Strip None values for cleaner JSON
        run_status = {k: v for k, v in run_status.items() if v is not None}

        status_path = self.run_dir / 'run_status.json'
        try:
            with open(status_path, 'w') as f:
                json.dump(run_status, f, indent=2)
        except Exception as e:
            print_warning(f"Failed to write run_status.json: {e}")

    def _resolve_qa_polish_2_directive_path(self) -> Path:
        """
        Resolve QA_POLISH_2 directive path with precedence:
        1) CLI override (--qa-polish-2-directive)
        2) Config default (Config.QA_POLISH_2_DIRECTIVE_FILE)
        3) Fail fast if resolved path does not exist
        """
        cli_path = getattr(self.cli_args, 'qa_polish_2_directive', None) if self.cli_args else None
        resolved = Path(cli_path) if cli_path else Path(Config.QA_POLISH_2_DIRECTIVE_FILE)
        if not resolved.exists():
            raise FileNotFoundError(
                "QA_POLISH_2 directive not found. "
                f"Looked for: {resolved}. "
                "Provide --qa-polish-2-directive <path> or create the default file."
            )
        return resolved

    def _resolve_qa_testcase_directive_path(self) -> Optional[Path]:
        """
        Resolve testcase-doc directive path with precedence:
        1) CLI override (--qa-testcase-directive)
        2) Config default (Config.QA_TESTCASE_DIRECTIVE_FILE)
        """
        cli_path = getattr(self.cli_args, 'qa_testcase_directive', None) if self.cli_args else None
        resolved = Path(cli_path) if cli_path else Path(Config.QA_TESTCASE_DIRECTIVE_FILE)
        if not resolved.exists():
            print_warning(
                "QA testcase directive not found. "
                f"Looked for: {resolved}. "
                "Post-QA testcase doc generation will be skipped."
            )
            return None
        return resolved

    def _log_claude_usage(self, response: dict, iteration: int, is_continuation: bool = False, continuation_num: int = 0) -> dict:
        """
        FIX #1: Detailed logging of Claude API usage and cache performance.

        WHY: You asked for DETAILED LOGGING because you're "dumber than a bag of rocks".
        This shows exactly what's happening with caching, tokens, and costs.

        Args:
            response: Claude API response dict
            iteration: Current iteration number
            is_continuation: Whether this was a continuation call
            continuation_num: If continuation, which number (1, 2, 3...)

        Returns:
            dict: Usage stats for accumulation (cache_creation, cache_read, input, output tokens)
        """
        # Extract usage stats from response
        usage = response.get('usage', {})

        # Cache metrics
        cache_creation_tokens = usage.get('cache_creation_input_tokens', 0)
        cache_read_tokens = usage.get('cache_read_input_tokens', 0)
        input_tokens = usage.get('input_tokens', 0)
        output_tokens = usage.get('output_tokens', 0)

        # Determine call type for logging
        call_type = f"CONTINUATION {continuation_num}" if is_continuation else f"ITERATION {iteration}"

        print_info("═══════════════════════════════════════════════════════════")
        print_info(f"CLAUDE API USAGE BREAKDOWN - {call_type}")
        print_info("═══════════════════════════════════════════════════════════")

        # Cache performance
        if cache_creation_tokens > 0:
            print_info("Input tokens:")
            print_info(f"  → Cache creation (write): {cache_creation_tokens:,} tokens")
            print_info(f"  → Non-cached input: {input_tokens:,} tokens")
            print_info(f"  → Total input: {cache_creation_tokens + input_tokens:,} tokens")
            print_info("  → Cache status: FIRST WRITE (will be cached for 5 minutes)")
        elif cache_read_tokens > 0:
            print_success("Input tokens:")
            print_success(f"  → Cache read (hit): {cache_read_tokens:,} tokens ✓ CACHE HIT!")
            print_success(f"  → Non-cached input: {input_tokens:,} tokens")
            print_success(f"  → Total input: {cache_read_tokens + input_tokens:,} tokens")

            # Calculate savings
            # WHY: Cache reads cost ~10% of cache writes. Show the savings!
            cache_write_cost = cache_read_tokens * 0.003 / 1000  # $3/MTok for write
            cache_read_cost = cache_read_tokens * 0.0003 / 1000  # $0.30/MTok for read
            savings = cache_write_cost - cache_read_cost
            savings_percent = (savings / cache_write_cost * 100) if cache_write_cost > 0 else 0

            print_success(f"  → Cache savings: ${savings:.4f} ({savings_percent:.0f}% cheaper than write)")
        else:
            print_info("Input tokens:")
            print_info(f"  → Non-cached input: {input_tokens:,} tokens")
            print_info("  → Cache status: NOT USED (no cacheable prefix provided)")

        # Output tokens
        print_info(f"Output tokens: {output_tokens:,} tokens")

        # Cost estimates
        # Anthropic pricing (as of 2025): Sonnet = $3/MTok input, $15/MTok output
        # Cache write = $3.75/MTok, Cache read = $0.30/MTok
        input_cost = input_tokens * 0.003 / 1000
        cache_write_cost = cache_creation_tokens * 0.00375 / 1000
        cache_read_cost = cache_read_tokens * 0.0003 / 1000
        output_cost = output_tokens * 0.015 / 1000
        total_cost = input_cost + cache_write_cost + cache_read_cost + output_cost

        print_info("Cost estimate:")
        if cache_creation_tokens > 0:
            print_info(f"  → Cache write: ${cache_write_cost:.4f}")
        if cache_read_tokens > 0:
            print_success(f"  → Cache read: ${cache_read_cost:.4f} (vs ${cache_read_tokens * 0.003 / 1000:.4f} without cache)")
        if input_tokens > 0:
            print_info(f"  → Non-cached input: ${input_cost:.4f}")
        print_info(f"  → Output: ${output_cost:.4f}")
        print_info(f"  → Total this call: ${total_cost:.4f}")

        print_info("═══════════════════════════════════════════════════════════")

        # Return usage stats for accumulation
        return {
            'cache_creation_tokens': cache_creation_tokens,
            'cache_read_tokens': cache_read_tokens,
            'input_tokens': input_tokens,
            'output_tokens': output_tokens
        }

    def _log_chatgpt_usage(self, response: dict, iteration: int) -> dict:
        """
        Log ChatGPT API usage and costs.

        WHY: User wants cost tracking for ChatGPT (QA) calls too.
        OpenAI response format: response['usage'] = {prompt_tokens, completion_tokens, total_tokens}

        Args:
            response: OpenAI API response dict
            iteration: Current iteration number

        Returns:
            dict: Usage stats for accumulation (input_tokens, output_tokens)
        """
        # Extract usage from OpenAI response
        usage = response.get('usage', {})
        input_tokens = usage.get('prompt_tokens', 0)
        output_tokens = usage.get('completion_tokens', 0)
        total_tokens = usage.get('total_tokens', 0)

        print_info("═══════════════════════════════════════════════════════════")
        print_info(f"CHATGPT API USAGE - ITERATION {iteration} QA")
        print_info("═══════════════════════════════════════════════════════════")

        print_info(f"Input tokens:  {input_tokens:,} tokens")
        print_info(f"Output tokens: {output_tokens:,} tokens")
        print_info(f"Total tokens:  {total_tokens:,} tokens")

        # Cost calculation (OpenAI GPT-4o pricing as of 2025)
        # Input: $2.50/MTok, Output: $10.00/MTok
        input_cost = input_tokens * 0.0025 / 1000
        output_cost = output_tokens * 0.010 / 1000
        total_cost = input_cost + output_cost

        print_info("")
        print_info("Cost estimate:")
        print_info(f"  → Input:  ${input_cost:.4f}")
        print_info(f"  → Output: ${output_cost:.4f}")
        print_info(f"  → Total:  ${total_cost:.4f}")

        cached_tokens = usage.get('prompt_tokens_details', {}).get('cached_tokens', 0) or 0
        print_info(f'CACHE CHECK [FEATURE_QA] iteration {iteration}: cached={cached_tokens} / total_prompt={input_tokens} ({int(cached_tokens/input_tokens*100) if input_tokens else 0}% cached)')

        print_info("═══════════════════════════════════════════════════════════")

        return {
            'input_tokens': input_tokens,
            'output_tokens': output_tokens
        }

    def _print_defects_summary(self, qa_report: str, iteration: int):
        """
        Print detailed defects to screen so user doesn't have to dig through logs.

        WHY: User wants to see what defects QA found without opening log files.
        Extracts all DEFECT-XXX entries and prints them in a readable format.
        """
        print_info("")
        print_info("═══════════════════════════════════════════════════════════")
        print_info(f"ITERATION {iteration} - DEFECTS FOUND")
        print_info("═══════════════════════════════════════════════════════════")

        # Extract all defects using regex
        defect_pattern = r'(DEFECT-\d+):\s*(\w+)\s*\n\s*-\s*Location:\s*([^\n]+)\n\s*-\s*Problem:\s*([^\n]+)\n\s*-\s*Expected:\s*([^\n]+)\n\s*-\s*Severity:\s*(\w+)'
        defects = re.findall(defect_pattern, qa_report, re.MULTILINE)

        if defects:
            for defect_id, defect_type, location, problem, expected, severity in defects:
                # Color code by type
                if defect_type == "IMPLEMENTATION_BUG":
                    type_display = f"🐛 {defect_type}"
                elif defect_type == "SPEC_COMPLIANCE_ISSUE":
                    type_display = f"📋 {defect_type}"
                elif defect_type == "SCOPE_CHANGE_REQUEST":
                    type_display = f"🔍 {defect_type}"
                else:
                    type_display = defect_type

                print_warning(f"\n{defect_id}: {type_display}")
                print_info(f"  Location:  {location.strip()}")
                print_info(f"  Problem:   {problem.strip()}")
                print_info(f"  Expected:  {expected.strip()}")
                print_info(f"  Severity:  {severity}")
        else:
            # Fallback: print defects section if regex fails
            defects_section = re.search(r'### DEFECTS\n(.*?)### VERDICT', qa_report, re.DOTALL)
            if defects_section:
                print_info(defects_section.group(1).strip())
            else:
                print_warning("Could not parse defects from QA report")

        print_info("═══════════════════════════════════════════════════════════")
        print_info("")

    def _print_cost_summary(
        self,
        iterations: int,
        total_calls: int,
        total_cache_writes: int,
        total_cache_hits: int,
        total_cache_write_tokens: int,
        total_cache_read_tokens: int,
        total_input_tokens: int,
        total_output_tokens: int,
        total_gpt_calls: int = 0,
        total_gpt_input_tokens: int = 0,
        total_gpt_output_tokens: int = 0,
        run_end_reason: str = 'UNKNOWN'
    ):
        """
        FIX #1: Print final cost summary showing cumulative savings.

        WHY: Show the user EXACTLY how much money they saved with caching.
        This is the "bag of rocks" summary they requested.

        Now includes ChatGPT (QA) costs too.
        """
        print_info("")
        print_info("═══════════════════════════════════════════════════════════")
        print_info("FULL RUN COST ANALYSIS")
        print_info("═══════════════════════════════════════════════════════════")
        print_info(f"Total iterations: {iterations}")
        print_info(f"Total Claude calls: {total_calls} ({iterations} builds + {total_calls - iterations} continuations)")

        # Cache performance
        cache_hit_rate = (total_cache_hits / total_calls * 100) if total_calls > 0 else 0
        print_info("")
        print_info("Cache performance:")
        print_info(f"  → Cache writes: {total_cache_writes}")
        print_info(f"  → Cache hits: {total_cache_hits}")
        print_success(f"  → Cache hit rate: {cache_hit_rate:.1f}%")
        print_success(f"  → Total tokens read from cache: {total_cache_read_tokens:,} tokens")

        # Token usage
        print_info("")
        print_info("Token usage:")
        print_info(f"  → Cache write tokens: {total_cache_write_tokens:,} tokens")
        print_info(f"  → Cache read tokens: {total_cache_read_tokens:,} tokens")
        print_info(f"  → Non-cached input tokens: {total_input_tokens:,} tokens")
        print_info(f"  → Output tokens: {total_output_tokens:,} tokens")

        # Cost calculations (Anthropic Sonnet pricing)
        cache_write_cost = total_cache_write_tokens * 0.00375 / 1000
        cache_read_cost = total_cache_read_tokens * 0.0003 / 1000
        input_cost = total_input_tokens * 0.003 / 1000
        output_cost = total_output_tokens * 0.015 / 1000

        total_cost_with_cache = cache_write_cost + cache_read_cost + input_cost + output_cost

        # Calculate what it would have cost WITHOUT caching
        # (all cache reads would have been full writes)
        cost_without_cache = (total_cache_write_tokens + total_cache_read_tokens) * 0.003 / 1000
        cost_without_cache += input_cost + output_cost

        savings = cost_without_cache - total_cost_with_cache
        savings_percent = (savings / cost_without_cache * 100) if cost_without_cache > 0 else 0

        print_info("")
        print_info("Cost breakdown:")
        if cache_write_cost > 0:
            print_info(f"  → Cache writes: ${cache_write_cost:.4f}")
        if cache_read_cost > 0:
            print_success(f"  → Cache reads: ${cache_read_cost:.4f}")
        print_info(f"  → Non-cached input: ${input_cost:.4f}")
        print_info(f"  → Output: ${output_cost:.4f}")
        print_info(f"  → Total with caching: ${total_cost_with_cache:.4f}")

        print_info("")
        print_success(f"Without caching: ${cost_without_cache:.4f}")
        print_success(f"Total saved: ${savings:.4f} ({savings_percent:.0f}% reduction)")

        # Dynamic token limiting savings estimate
        # WHY: Harder to calculate exact savings from dynamic tokens since we don't know
        # what Claude would have output with 8192 limit. Conservative estimate: 10-20% of output cost.
        dynamic_token_savings_estimate = output_cost * 0.15  # Conservative 15%
        print_info("")
        print_info("Dynamic token limiting:")
        print_info(f"  → Estimated additional savings: ${dynamic_token_savings_estimate:.4f} (15% of output)")
        print_success(f"  → Combined Claude savings: ${savings + dynamic_token_savings_estimate:.4f}")

        # ChatGPT (QA) costs
        if total_gpt_calls > 0:
            print_info("")
            print_info("ChatGPT (QA) costs:")
            print_info(f"  → Total QA calls: {total_gpt_calls}")
            print_info(f"  → Input tokens: {total_gpt_input_tokens:,} tokens")
            print_info(f"  → Output tokens: {total_gpt_output_tokens:,} tokens")

            # OpenAI GPT-4o pricing: Input $2.50/MTok, Output $10.00/MTok
            gpt_input_cost = total_gpt_input_tokens * 0.0025 / 1000
            gpt_output_cost = total_gpt_output_tokens * 0.010 / 1000
            gpt_total_cost = gpt_input_cost + gpt_output_cost

            print_info(f"  → Input cost: ${gpt_input_cost:.4f}")
            print_info(f"  → Output cost: ${gpt_output_cost:.4f}")
            print_info(f"  → Total ChatGPT: ${gpt_total_cost:.4f}")

            # Combined totals
            print_info("")
            print_success(f"TOTAL COST (Claude + ChatGPT): ${total_cost_with_cache + gpt_total_cost:.4f}")
            print_success(f"  → Claude: ${total_cost_with_cache:.4f}")
            print_success(f"  → ChatGPT: ${gpt_total_cost:.4f}")
            print_success(f"Total saved from caching: ${savings + dynamic_token_savings_estimate:.4f}")
        else:
            print_info("")
            print_success(f"TOTAL COST (Claude only): ${total_cost_with_cache:.4f}")

        print_info("═══════════════════════════════════════════════════════════")

        # Log run to CSV
        gpt_total_cost = 0
        if total_gpt_calls > 0:
            gpt_total_cost = (total_gpt_input_tokens * 0.0025 / 1000) + (total_gpt_output_tokens * 0.010 / 1000)
        self._last_claude_cost  = total_cost_with_cache
        self._last_chatgpt_cost = gpt_total_cost
        self._log_run_csv(iterations, total_cost_with_cache, gpt_total_cost, run_end_reason)

    def _log_run_csv(self, iterations: int, claude_cost: float, chatgpt_cost: float, run_end_reason: str = 'UNKNOWN'):
        """Log run stats to a persistent CSV file for tracking across runs."""
        import csv

        csv_path = Path(__file__).parent / 'fo_run_log.csv'
        file_exists = csv_path.exists()

        # Safety prompt before modifying run log
        if not self._confirm_sensitive_write(csv_path):
            print_warning(f"Run log not written (confirmation declined): {csv_path}")
            return

        now = datetime.now()
        row = {
            'date': now.strftime('%Y-%m-%d'),
            'time': now.strftime('%H:%M:%S'),
            'startup': self.startup_id,
            'iterations': iterations,
            'cost_claude': f'{claude_cost:.4f}',
            'cost_chatgpt': f'{chatgpt_cost:.4f}',
            'total_cost': f'{claude_cost + chatgpt_cost:.4f}',
            'run_end_reason': run_end_reason
        }

        fieldnames = ['date', 'time', 'startup', 'iterations', 'cost_claude', 'cost_chatgpt', 'total_cost', 'run_end_reason']

        with open(csv_path, 'a', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if not file_exists:
                writer.writeheader()
            writer.writerow(row)

        print_info(f"Run logged to: {csv_path}")

    def _confirm_sensitive_write(self, path: Path) -> bool:
        """
        Safety prompt before writing sensitive files.
        Set --confirm-run-log YES to require a prompt.
        """
        if not self.confirm_run_log:
            return True

        try:
            response = input(f"Confirm write to {path} (type YES to proceed): ").strip()
        except EOFError:
            print_warning("No TTY available; refusing to write without confirmation")
            return False

        return response == "YES"

    def _patch_missing_files(self, iteration: int, missing_files: list,
                              build_output: str, governance_section: str) -> Tuple[bool, dict]:
        """
        FIX #11: Patch call — request only missing files instead of full rebuild.

        When validation fails because files are in manifest but not extracted,
        make a targeted Claude call for just those files. Like TCP retransmission.

        Returns:
            (success: bool, cost_stats: dict)
        """
        print_info("")
        print_info("═══════════════════════════════════════════════════════════")
        print_info(f"PATCH CALL - Requesting {len(missing_files)} missing file(s)")
        print_info("═══════════════════════════════════════════════════════════")

        cost_stats = {
            'calls': 0,
            'input_tokens': 0,
            'output_tokens': 0,
            'cache_read_tokens': 0,
            'cache_creation_tokens': 0
        }

        artifacts_dir = self.artifacts.build_dir / f'iteration_{iteration:02d}_artifacts'

        # Get list of files we DO have for context
        existing_files = extract_file_paths_from_output(build_output)

        # Build targeted prompt
        # Prompt template source: directives/prompts/patch_prompt.md
        patch_prompt = DirectiveTemplateLoader.render(
            'patch_prompt.md',
            startup_id=self.startup_id,
            missing_files_bullets=chr(10).join('- ' + f for f in missing_files),
            existing_files_bullets=chr(10).join('- ' + f for f in existing_files[:25])
        )

        # Estimate tokens needed: ~200-400 tokens per file
        estimated_tokens = min(16384, max(4096, len(missing_files) * 2000))

        print_info(f"  → Missing: {', '.join(missing_files[:8])}")
        if len(missing_files) > 8:
            print_info(f"    ... and {len(missing_files) - 8} more")
        print_info(f"  → Token limit: {estimated_tokens:,}")
        print_info("───────────────────────────────────────────────────────────")

        try:
            start_time = time.time()
            patch_response = self.claude.call(
                patch_prompt,
                max_tokens=estimated_tokens,
                cacheable_prefix=governance_section,
                timeout=300
            )
            patch_output = patch_response['content'][0]['text']
            elapsed = time.time() - start_time

            # Log usage
            usage = patch_response.get('usage', {})
            cost_stats['calls'] = 1
            cost_stats['input_tokens'] = usage.get('input_tokens', 0)
            cost_stats['output_tokens'] = usage.get('output_tokens', 0)
            cost_stats['cache_read_tokens'] = usage.get('cache_read_input_tokens', 0)
            cost_stats['cache_creation_tokens'] = usage.get('cache_creation_input_tokens', 0)

            input_cost = (cost_stats['input_tokens'] / 1_000_000) * 3.00
            output_cost = (cost_stats['output_tokens'] / 1_000_000) * 15.00
            cache_read_cost = (cost_stats['cache_read_tokens'] / 1_000_000) * 0.30
            patch_cost = input_cost + output_cost + cache_read_cost
            print_success(f"Patch response received in {elapsed:.1f}s (cost: ${patch_cost:.4f})")

            # Extract files from patch output
            patched_files = extract_file_paths_from_output(patch_output)
            print_info(f"  → Files in patch response: {len(patched_files)}")

            # Run the artifact extraction on the patch output
            code_block_pattern = r'(?:^|\n)(.{0,200}?)\n?```(\w+)(?:[ \t]+([^\n]+))?\n(.*?)```'
            patched_count = 0

            for match in re.finditer(code_block_pattern, patch_output, re.DOTALL | re.MULTILINE):
                preceding_line = match.group(1).strip() if match.group(1) else ''
                language = match.group(2)
                code_content = match.group(4)
                match_pos = match.start()

                # Find FILE: header
                context_before = patch_output[max(0, match_pos - 500):match_pos]
                search_area = preceding_line + '\n' + context_before if preceding_line else context_before

                filename = None
                file_match = re.search(r'\*\*FILE:\s*([^\*]+)\*\*', search_area, re.IGNORECASE)
                if file_match:
                    filename = re.sub(r'[\*`]', '', file_match.group(1)).strip()

                if filename:
                    artifact_path = artifacts_dir / filename
                    artifact_path.parent.mkdir(parents=True, exist_ok=True)
                    artifact_path.write_text(code_content, encoding='utf-8')
                    patched_count += 1
                    print_success(f"  → Patched: {filename}")

            # Also fix build_state.json if it had wrong state
            build_state_path = artifacts_dir / 'build_state.json'
            if build_state_path.exists():
                try:
                    with open(build_state_path) as f:
                        bs = json.load(f)
                    if bs.get('state') != 'COMPLETED_CLOSED':
                        bs['state'] = 'COMPLETED_CLOSED'
                        with open(build_state_path, 'w') as f:
                            json.dump(bs, f, indent=2)
                        print_success(f"  → Fixed: build_state.json state → COMPLETED_CLOSED")
                except:
                    pass

            # Check how many missing files were recovered
            still_missing = []
            for f in missing_files:
                if not (artifacts_dir / f).exists():
                    still_missing.append(f)

            # Keep manifest in sync with patched artifacts so re-validation
            # sees newly recovered files in artifact_manifest.json.
            if patched_count > 0:
                self.artifacts.refresh_manifest_for_iteration(iteration)

            print_info("")
            print_info(f"Patch results: {patched_count} files recovered, {len(still_missing)} still missing")
            if still_missing:
                print_warning(f"  → Still missing: {', '.join(still_missing[:5])}")

            success = len(still_missing) == 0
            if success:
                print_success("Patch successful — all missing files recovered")
            print_info("═══════════════════════════════════════════════════════════")

            return success, cost_stats

        except Exception as e:
            print_error(f"Patch call failed: {e}")
            return False, cost_stats

    def _generate_business_config(self, artifacts_dir: Path) -> None:
        """
        Generate business_config.json from intake data and write it into the artifact
        directories for both frontend and backend.  Replaces the boilerplate InboxTamer
        placeholder so the ZIP is always startup-specific.
        """
        intake = self.intake_data
        block_b = intake.get('block_b', {})
        hero   = block_b.get('hero_answers', {})
        econ   = intake.get('block_a', {}).get('pass_1', {}).get('economics_snapshot', {})

        startup_name = intake.get('startup_name', 'My Startup')
        startup_id   = intake.get('startup_idea_id', 'my_startup')
        tagline      = hero.get('Q3_success_metric', econ.get('target_customer', ''))[:120]
        price_raw    = econ.get('starter_price', '$99/month')

        # Parse price — extract first number found
        import re as _re
        price_match = _re.search(r'[\d,]+', price_raw.replace(',', ''))
        price_monthly = int(price_match.group(0)) if price_match else 99
        price_annual  = round(price_monthly * 10)   # ~2 months free

        # Derive slug for URLs
        slug = startup_name.lower().replace(' ', '')

        # Build entitlements from must-have features
        must_haves = hero.get('Q4_must_have_features', [])
        entitlements = []
        for f in must_haves:
            key = _re.sub(r'[^a-z0-9]+', '_', f.lower()).strip('_')[:30]
            entitlements.append(key)
        if not entitlements:
            entitlements = ['dashboard']

        features_block = {}
        for i, (key, label) in enumerate(zip(entitlements, must_haves)):
            features_block[key] = {
                "tier": 1 if i < 5 else 2,
                "label": label[:50],
                "description": label
            }

        config = {
            "_comment": "business_config.json — auto-generated from intake by FO harness. Hero fills in API keys.",
            "business": {
                "name": startup_name,
                "tagline": tagline,
                "description": tagline,
                "url": f"https://{slug}.com",
                "support_email": f"support@{slug}.com"
            },
            "stripe": {
                "publishable_key": "pk_live_YOUR_KEY_HERE",
                "secret_key": "sk_live_YOUR_KEY_HERE",
                "webhook_secret": "whsec_YOUR_WEBHOOK_SECRET_HERE"
            },
            "stripe_products": {
                "prod_REPLACE_WITH_STARTER_ID": {
                    "name": "Starter",
                    "description": f"Get started with {startup_name}",
                    "price_monthly": price_monthly,
                    "price_annual": price_annual,
                    "annual_savings": f"Save ${price_monthly * 2}/year",
                    "popular": True,
                    "cta_text": "Start Free Trial",
                    "stripe_price_id_monthly": "price_REPLACE_WITH_MONTHLY_PRICE_ID",
                    "stripe_price_id_annual":  "price_REPLACE_WITH_ANNUAL_PRICE_ID",
                    "features": must_haves[:6] if must_haves else ["Full access"],
                    "limitations": [],
                    "entitlements": entitlements
                }
            },
            "features": features_block,
            "auth0": {
                "domain": "YOUR_AUTH0_DOMAIN.auth0.com",
                "client_id": "YOUR_CLIENT_ID",
                "client_secret": "YOUR_CLIENT_SECRET",
                "audience": "https://YOUR_AUTH0_DOMAIN.auth0.com/api/v2/"
            },
            "mailerlite": {
                "api_key": "YOUR_MAILERLITE_API_KEY",
                "group_id": "YOUR_GROUP_ID"
            },
            "branding": {
                "primary_color": "#1E3A5F",
                "logo_url": "",
                "favicon_url": "",
                "company_name": startup_name
            },
            "dashboard": {
                "theme": "light",
                "show_upgrade_banner": True,
                "nav_items": [
                    {"label": "Dashboard", "path": "/dashboard", "icon": "grid"},
                    {"label": "Settings",  "path": "/settings",  "icon": "cog"}
                ],
                "hero_support_url": "",
                "hero_docs_url": ""
            },
            "metadata": {
                "analytics": {"google_analytics_id": ""},
                "seo": {
                    "title": f"{startup_name}",
                    "description": tagline
                }
            },
            "home": {
                "hero": {
                    "headline": startup_name,
                    "subheadline": tagline,
                    "cta_primary":  {"label": "Get Started", "href": "/signup"},
                    "cta_secondary": {"label": "Learn More",  "href": "#features"}
                },
                "features_heading": "Everything you need",
                "features": [
                    {
                        "icon": "star",
                        "title": (f[:50] if isinstance(f, str) else f.get("label", "Feature")),
                        "description": ""
                    }
                    for f in (must_haves[:6] if must_haves else [{"label": "Core features"}])
                ],
                "social_proof": {
                    "stats": [
                        {"value": "500+", "label": "Customers"},
                        {"value": "99%",  "label": "Uptime"},
                        {"value": "24/7", "label": "Support"}
                    ],
                    "testimonials": [
                        {
                            "quote": f"{startup_name} has transformed how we work.",
                            "author": "Early Customer",
                            "title": "Founder"
                        }
                    ]
                },
                "final_cta": {
                    "headline": f"Ready to get started with {startup_name}?",
                    "subheadline": tagline,
                    "button_text": "Start Free Trial"
                }
            },
            "pricing": {
                "headline": f"{startup_name} Pricing",
                "subheadline": "Simple, transparent pricing",
                "faq": [
                    {"question": "Can I cancel anytime?",      "answer": "Yes, cancel anytime with no penalties."},
                    {"question": "Is there a free trial?",     "answer": "Yes, 14-day free trial on all plans."},
                    {"question": "Do you offer refunds?",      "answer": "Yes, 30-day money-back guarantee."},
                    {"question": "What payment methods?",      "answer": "All major credit cards via Stripe."}
                ]
            },
            "contact": {
                "headline": "Get in touch",
                "subheadline": f"We'd love to hear from you.",
                "methods": [
                    {"label": "Email", "description": "Send us an email", "value": f"support@{slug}.com"}
                ],
                "form": {
                    "title": "Send a message",
                    "submit_text": "Send Message",
                    "success_message": "Thanks! We'll be in touch shortly.",
                    "fields": [
                        {"label": "Name",    "name": "name",    "type": "text",     "required": True},
                        {"label": "Email",   "name": "email",   "type": "email",    "required": True},
                        {"label": "Message", "name": "message", "type": "textarea", "required": True}
                    ]
                }
            },
            "faq": {
                "headline": "Frequently Asked Questions",
                "categories": [
                    {
                        "name": "General",
                        "questions": [
                            {"question": f"What is {startup_name}?",    "answer": tagline},
                            {"question": "How do I get started?",       "answer": "Sign up for a free trial — no credit card required."},
                            {"question": "Is my data secure?",          "answer": "Yes, all data is encrypted in transit and at rest."}
                        ]
                    },
                    {
                        "name": "Billing",
                        "questions": [
                            {"question": "Can I cancel anytime?",       "answer": "Yes, cancel anytime with no penalties."},
                            {"question": "Do you offer refunds?",       "answer": "Yes, 30-day money-back guarantee."}
                        ]
                    }
                ]
            },
            "terms_of_service": {
                "last_updated": "2025-01-01",
                "sections": [
                    {"title": "Acceptance of Terms",    "content": f"By using {startup_name}, you agree to these terms."},
                    {"title": "Use of Service",         "content": "You may use the service for lawful purposes only."},
                    {"title": "Intellectual Property",  "content": f"All content and software is owned by {startup_name}."},
                    {"title": "Limitation of Liability","content": "We are not liable for indirect or consequential damages."},
                    {"title": "Contact",                "content": f"Questions? Email support@{slug}.com"}
                ]
            },
            "privacy_policy": {
                "last_updated": "2025-01-01",
                "sections": [
                    {"title": "Information We Collect", "content": "We collect information you provide when creating an account."},
                    {"title": "How We Use It",          "content": "We use your information to provide and improve the service."},
                    {"title": "Data Sharing",           "content": "We do not sell your personal data to third parties."},
                    {"title": "Security",               "content": "We use industry-standard encryption to protect your data."},
                    {"title": "Contact",                "content": f"Questions? Email support@{slug}.com"}
                ]
            },
            "marketing": {"enabled": False},
            "footer": {
                "tagline": tagline,
                "columns": [
                    {
                        "title": startup_name,
                        "links": [
                            {"label": "Home",      "url": "/"},
                            {"label": "Dashboard", "url": "/dashboard"},
                            {"label": "Pricing",   "url": "/pricing"}
                        ]
                    },
                    {
                        "title": "Product",
                        "links": [
                            {"label": (f[:40] if isinstance(f, str) else f.get("label", "Feature")), "url": "#"}
                            for f in (must_haves[:4] if must_haves else [{"label": "Features"}])
                        ]
                    },
                    {
                        "title": "Company",
                        "links": [
                            {"label": "About",   "url": "/about"},
                            {"label": "Contact", "url": "/contact"},
                            {"label": "Privacy", "url": "/privacy"},
                            {"label": "Terms",   "url": "/terms"}
                        ]
                    }
                ],
                "copyright": f"© 2025 {startup_name}. All rights reserved."
            }
        }

        config_json = json.dumps(config, indent=2)

        targets = [
            artifacts_dir / 'business' / 'frontend' / 'config' / 'business_config.json',
            artifacts_dir / 'business' / 'backend'  / 'config' / 'business_config.json',
        ]
        for target in targets:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(config_json)
            print_success(f"  ✓ business_config.json → {target.relative_to(artifacts_dir)}")

    def _post_qa_polish(self, iteration: int, build_output: str, governance_section: str) -> Tuple[bool, dict]:
        """
        FIX #10: Post-QA polish step to generate missing optional files.

        After QA accepts the build, check for missing optional files (README, etc.)
        and make targeted Claude calls to generate them.

        This solves the 16K token limit issue - core build passes QA, then we
        generate optional files separately.

        Returns:
            (success: bool, cost_stats: dict)
        """
        import re  # For regex extraction

        print_info("")
        print_info("═══════════════════════════════════════════════════════════")
        print_info("POST-QA POLISH - Generating missing optional files")
        print_info("═══════════════════════════════════════════════════════════")

        artifacts_dir = self.artifacts.build_dir / f'iteration_{iteration:02d}_artifacts'
        manifest_path = artifacts_dir / 'artifact_manifest.json'

        cost_stats = {
            'calls': 0,
            'input_tokens': 0,
            'output_tokens': 0,
            'cache_read_tokens': 0
        }

        # Check if artifact_manifest exists
        if not manifest_path.exists():
            print_warning("No artifact_manifest.json found - skipping polish")
            return False, cost_stats

        try:
            with open(manifest_path) as f:
                manifest = json.load(f)
        except json.JSONDecodeError:
            print_warning("Could not parse artifact_manifest.json - skipping polish")
            return False, cost_stats

        manifest_files = [artifact.get('path', '') for artifact in manifest.get('artifacts', [])]

        # Check what's missing
        readme_found = any(path.endswith('README.md') for path in manifest_files)
        env_example_found = any('.env.example' in path for path in manifest_files)
        integration_readme_found = any(path == 'business/README-INTEGRATION.md' for path in manifest_files)
        test_files = [f for f in manifest_files if 'test' in f.lower() or 'spec' in f.lower()]
        has_minimal_tests = len(test_files) < 3  # Consider < 3 test files as "minimal"
        docs_dir = artifacts_dir / 'business' / 'docs'

        # Always generate business_config.json from intake (replaces boilerplate placeholder)
        print_info("→ Generating business_config.json from intake...")
        self._generate_business_config(artifacts_dir)

        polish_items = []
        if not readme_found:
            polish_items.append("README.md")
        if not env_example_found:
            polish_items.append(".env.example")
        if getattr(self, 'use_boilerplate', False) and not integration_readme_found:
            polish_items.append("business/README-INTEGRATION.md")
        if has_minimal_tests:
            polish_items.append(f"Tests (only {len(test_files)} found)")
        # Always ensure docs folder exists and include HLD + QUICKSTART
        polish_items.append("Docs (HLD + QUICKSTART)")

        if not polish_items:
            print_success("✓ All optional files present - no polish needed")
            return True, cost_stats

        print_info(f"→ Missing optional files: {', '.join(polish_items)}")
        print_info("")

        # ============================================================
        # 1. Rename boilerplate README if present and generate README.md
        # ============================================================
        # Rename boilerplate README to README-base.md if it exists
        readme_path = artifacts_dir / 'README.md'
        if readme_path.exists():
            base_path = artifacts_dir / 'README-base.md'
            if not base_path.exists():
                readme_path.rename(base_path)
                print_info("→ Renamed boilerplate README.md → README-base.md")
            readme_found = False  # Force regeneration

        if not readme_found:
            print_info("→ README.md missing - generating...")

            # Create targeted prompt for README generation
            # Prompt template source: directives/prompts/polish_readme_prompt.md
            readme_prompt = DirectiveTemplateLoader.render(
                'polish_readme_prompt.md',
                manifest_sample=chr(10).join(manifest_files[:20]),
                build_output_sample=build_output[:2000]
            )

            try:
                print_info("→ Calling Claude for README generation...")
                start_time = time.time()

                readme_response = self.claude.call(
                    readme_prompt,
                    max_tokens=4096,  # README shouldn't need more
                    cacheable_prefix=None,  # Don't cache for one-off
                    timeout=120  # 2 minutes should be plenty
                )

                readme_content = readme_response['content'][0]['text']
                elapsed = time.time() - start_time

                # Extract markdown from response
                import re
                md_match = re.search(r'```markdown\n(.*?)\n```', readme_content, re.DOTALL)
                if md_match:
                    readme_text = md_match.group(1)
                else:
                    # Maybe just markdown without fence
                    md_match = re.search(r'```\n(.*?)\n```', readme_content, re.DOTALL)
                    if md_match:
                        readme_text = md_match.group(1)
                    else:
                        readme_text = readme_content  # Use as-is

                # Save README to artifacts
                readme_path = artifacts_dir / 'README.md'
                readme_path.write_text(readme_text, encoding='utf-8')

                print_success(f"✓ Generated README.md ({len(readme_text)} chars) in {elapsed:.1f}s")
                print_info(f"  → Saved to: iteration_{iteration:02d}_artifacts/README.md")

                # Update cost stats
                usage = readme_response.get('usage', {})
                cost_stats['calls'] += 1
                cost_stats['input_tokens'] += usage.get('input_tokens', 0)
                cost_stats['output_tokens'] += usage.get('output_tokens', 0)
                cost_stats['cache_read_tokens'] += usage.get('cache_read_input_tokens', 0)

                # Calculate cost
                input_cost = (usage.get('input_tokens', 0) / 1_000_000) * 3.00
                output_cost = (usage.get('output_tokens', 0) / 1_000_000) * 15.00
                readme_cost = input_cost + output_cost
                print_info(f"  → Cost: ${readme_cost:.4f}")
                print_info("")

            except Exception as e:
                print_error(f"Failed to generate README: {e}")
                print_info("")

        # ============================================================
        # 2. Generate .env.example
        # ============================================================
        if not env_example_found:
            print_info("→ .env.example missing - generating...")

            # Read actual source files to find env vars
            source_files = []
            for file_path in manifest_files[:10]:  # Sample first 10 files
                full_path = artifacts_dir / file_path
                if full_path.exists() and full_path.suffix in ['.js', '.ts', '.jsx', '.tsx']:
                    try:
                        content = full_path.read_text(encoding='utf-8')
                        source_files.append(f"**{file_path}:**\n{content[:500]}")  # First 500 chars
                    except:
                        pass

            # Prompt template source: directives/prompts/polish_env_prompt.md
            env_prompt = DirectiveTemplateLoader.render(
                'polish_env_prompt.md',
                source_files_sample=chr(10).join(source_files[:5]),
                manifest_sample=chr(10).join(manifest_files[:15])
            )

            try:
                print_info("→ Calling Claude for .env.example generation...")
                start_time = time.time()

                env_response = self.claude.call(
                    env_prompt,
                    max_tokens=2048,  # .env shouldn't need much
                    cacheable_prefix=None,
                    timeout=90
                )

                env_content = env_response['content'][0]['text']
                elapsed = time.time() - start_time

                # Extract bash/env content from response
                env_match = re.search(r'```(?:bash|env|sh)?\n(.*?)\n```', env_content, re.DOTALL)
                if env_match:
                    env_text = env_match.group(1)
                else:
                    env_text = env_content  # Use as-is

                # Save .env.example to artifacts
                env_path = artifacts_dir / '.env.example'
                env_path.write_text(env_text, encoding='utf-8')

                print_success(f"✓ Generated .env.example ({len(env_text)} chars) in {elapsed:.1f}s")
                print_info(f"  → Saved to: iteration_{iteration:02d}_artifacts/.env.example")

                # Update cost stats
                usage = env_response.get('usage', {})
                cost_stats['calls'] += 1
                cost_stats['input_tokens'] += usage.get('input_tokens', 0)
                cost_stats['output_tokens'] += usage.get('output_tokens', 0)
                cost_stats['cache_read_tokens'] += usage.get('cache_read_input_tokens', 0)

                # Calculate cost
                input_cost = (usage.get('input_tokens', 0) / 1_000_000) * 3.00
                output_cost = (usage.get('output_tokens', 0) / 1_000_000) * 15.00
                env_cost = input_cost + output_cost
                print_info(f"  → Cost: ${env_cost:.4f}")
                print_info("")

            except Exception as e:
                print_error(f"Failed to generate .env.example: {e}")
                print_info("")

        # ============================================================
        # 3. Generate business/README-INTEGRATION.md (boilerplate runs)
        # ============================================================
        if getattr(self, 'use_boilerplate', False) and not integration_readme_found:
            print_info("→ business/README-INTEGRATION.md missing - generating...")
            integration_prompt = DirectiveTemplateLoader.render(
                'polish_integration_readme_prompt.md',
                startup_id=self.startup_id,
                block=self.block,
                manifest_sample=chr(10).join(manifest_files[:40]),
                build_output_sample=build_output[:3000]
            )

            try:
                print_info("→ Calling Claude for integration README generation...")
                start_time = time.time()

                integration_response = self.claude.call(
                    integration_prompt,
                    max_tokens=3072,
                    cacheable_prefix=None,
                    timeout=120
                )

                integration_content = integration_response['content'][0]['text']
                elapsed = time.time() - start_time

                md_match = re.search(r'```markdown\n(.*?)\n```', integration_content, re.DOTALL)
                if md_match:
                    integration_text = md_match.group(1)
                else:
                    md_match = re.search(r'```\n(.*?)\n```', integration_content, re.DOTALL)
                    integration_text = md_match.group(1) if md_match else integration_content

                integration_path = artifacts_dir / 'business' / 'README-INTEGRATION.md'
                integration_path.parent.mkdir(parents=True, exist_ok=True)
                integration_path.write_text(integration_text, encoding='utf-8')

                print_success(f"✓ Generated business/README-INTEGRATION.md ({len(integration_text)} chars) in {elapsed:.1f}s")
                print_info(f"  → Saved to: iteration_{iteration:02d}_artifacts/business/README-INTEGRATION.md")

                usage = integration_response.get('usage', {})
                cost_stats['calls'] += 1
                cost_stats['input_tokens'] += usage.get('input_tokens', 0)
                cost_stats['output_tokens'] += usage.get('output_tokens', 0)
                cost_stats['cache_read_tokens'] += usage.get('cache_read_input_tokens', 0)

                input_cost = (usage.get('input_tokens', 0) / 1_000_000) * 3.00
                output_cost = (usage.get('output_tokens', 0) / 1_000_000) * 15.00
                integration_cost = input_cost + output_cost
                print_info(f"  → Cost: ${integration_cost:.4f}")
                print_info("")
            except Exception as e:
                print_warning(f"Failed to generate business/README-INTEGRATION.md: {e}")
                print_info("")

        # ============================================================
        # 4. Generate additional tests (if minimal)
        # ============================================================
        if has_minimal_tests:
            print_info(f"→ Only {len(test_files)} test file(s) found - generating additional tests...")

            # Get list of testable files
            testable_files = [f for f in manifest_files
                            if ('service' in f.lower() or 'model' in f.lower() or 'api' in f.lower())
                            and 'test' not in f.lower()]

            # Prompt template source: directives/prompts/polish_tests_prompt.md
            tests_prompt = DirectiveTemplateLoader.render(
                'polish_tests_prompt.md',
                existing_test_files=(chr(10).join(test_files) if test_files else "None"),
                testable_files=chr(10).join(testable_files[:10])
            )

            try:
                print_info("→ Calling Claude for test generation...")
                start_time = time.time()

                tests_response = self.claude.call(
                    tests_prompt,
                    max_tokens=6144,  # Tests can be longer
                    cacheable_prefix=None,
                    timeout=180
                )

                tests_content = tests_response['content'][0]['text']
                elapsed = time.time() - start_time

                # Extract test files using FILE: pattern — match any language fence (python, js, etc.)
                test_pattern = r'\*\*FILE:\s*([^\*]+)\*\*\s*```(?:\w+)?\n(.*?)```'
                test_matches = re.findall(test_pattern, tests_content, re.DOTALL)

                tests_generated = 0
                for file_path, test_code in test_matches:
                    file_path = file_path.strip()
                    test_file_path = artifacts_dir / file_path
                    test_file_path.parent.mkdir(parents=True, exist_ok=True)
                    test_file_path.write_text(test_code, encoding='utf-8')
                    tests_generated += 1
                    print_success(f"✓ Generated {file_path}")

                print_success(f"✓ Generated {tests_generated} test file(s) in {elapsed:.1f}s")
                print_info(f"  → Saved to: iteration_{iteration:02d}_artifacts/")

                # Update cost stats
                usage = tests_response.get('usage', {})
                cost_stats['calls'] += 1
                cost_stats['input_tokens'] += usage.get('input_tokens', 0)
                cost_stats['output_tokens'] += usage.get('output_tokens', 0)
                cost_stats['cache_read_tokens'] += usage.get('cache_read_input_tokens', 0)

                # Calculate cost
                input_cost = (usage.get('input_tokens', 0) / 1_000_000) * 3.00
                output_cost = (usage.get('output_tokens', 0) / 1_000_000) * 15.00
                tests_cost = input_cost + output_cost
                print_info(f"  → Cost: ${tests_cost:.4f}")
                print_info("")

            except Exception as e:
                print_error(f"Failed to generate tests: {e}")
                print_info("")

        # ============================================================
        # 5. Save skipped doc snippets (if any)
        # ============================================================
        snippets_path = artifacts_dir / 'skipped_snippets.json'
        if snippets_path.exists():
            try:
                snippets = json.loads(snippets_path.read_text(encoding='utf-8'))
                if snippets:
                    print_info("→ Saving skipped doc snippets...")
                    docs_dir = artifacts_dir / 'business' / 'docs'
                    docs_dir.mkdir(parents=True, exist_ok=True)
                    out_path = docs_dir / 'snippets.md'

                    lines = ["# Snippets", "", "Captured documentation snippets from build output.", ""]
                    for idx, snip in enumerate(snippets, 1):
                        lang = snip.get('language') or ''
                        context = snip.get('context') or ''
                        content = snip.get('content') or ''
                        lines.append(f"## Snippet {idx}")
                        if context:
                            lines.append(f"Context: {context}")
                        lines.append(f"```{lang}".strip())
                        lines.append(content)
                        lines.append("```")
                        lines.append("")

                    out_path.write_text("\n".join(lines), encoding='utf-8')
                    print_success(f"✓ Saved snippets to {out_path}")
            except Exception as e:
                print_warning(f"Failed to save skipped snippets: {e}")

        # ============================================================
        # 6. Generate Docs (HLD + QUICKSTART)
        # ============================================================
        try:
            docs_dir.mkdir(parents=True, exist_ok=True)
            # Prompt template source: directives/prompts/polish_docs_wrapper_prompt.md
            docs_prompt = DirectiveTemplateLoader.render(
                'polish_docs_wrapper_prompt.md',
                qa_polish_2_directive=self.qa_polish_2_directive,
                startup_id=self.startup_id,
                block=self.block,
                iteration=iteration,
                iteration_padded=f"{iteration:02d}",
                manifest_sample=chr(10).join(manifest_files[:50]),
                build_output_sample=build_output[:3000]
            )
            print_info("→ Calling Claude for docs generation...")
            docs_response = self.claude.call(
                docs_prompt,
                max_tokens=4096,
                cacheable_prefix=None,
                timeout=120
            )
            docs_content = docs_response['content'][0]['text']
            docs_matches = re.findall(r'\*\*FILE:\s*([^\*]+)\*\*\\s*```markdown\\n(.*?)```', docs_content, re.DOTALL)
            docs_generated = 0
            for file_path, md in docs_matches:
                file_path = file_path.strip()
                full_path = artifacts_dir / file_path
                full_path.parent.mkdir(parents=True, exist_ok=True)
                full_path.write_text(md, encoding='utf-8')
                docs_generated += 1
            if docs_generated:
                print_success(f"✓ Generated {docs_generated} doc file(s)")

            usage = docs_response.get('usage', {})
            cost_stats['calls'] += 1
            cost_stats['input_tokens'] += usage.get('input_tokens', 0)
            cost_stats['output_tokens'] += usage.get('output_tokens', 0)
            cost_stats['cache_read_tokens'] += usage.get('cache_read_input_tokens', 0)
        except Exception as e:
            print_warning(f"Failed to generate docs: {e}")

        # ============================================================
        # 7. Generate complete testcase doc (ChatGPT, directive-driven)
        # ============================================================
        if not self.qa_testcase_directive:
            print_info("→ Skipping testcase doc generation (no QA_TESTCASE directive configured)")
        else:
            try:
                docs_dir.mkdir(parents=True, exist_ok=True)
                testcase_prompt = DirectiveTemplateLoader.render(
                    'polish_testcases_wrapper_prompt.md',
                    qa_testcase_directive=self.qa_testcase_directive,
                    startup_id=self.startup_id,
                    block=self.block,
                    iteration=iteration,
                    iteration_padded=f"{iteration:02d}",
                    intake_json=json.dumps(self.intake_data, indent=2),
                    manifest_sample=chr(10).join(manifest_files[:80]),
                    build_output_sample=build_output[:5000]
                )

                print_info("→ Calling ChatGPT for testcase doc generation...")
                tc_response = self.chatgpt.call(testcase_prompt, max_tokens=8192)
                tc_content = tc_response['choices'][0]['message']['content']

                # Extract markdown if fenced, else keep as-is
                md_match = re.search(r'```markdown\\n(.*?)\\n```', tc_content, re.DOTALL)
                if md_match:
                    tc_text = md_match.group(1)
                else:
                    md_match = re.search(r'```\\n(.*?)\\n```', tc_content, re.DOTALL)
                    tc_text = md_match.group(1) if md_match else tc_content

                tc_path = docs_dir / 'TEST_CASES.md'
                tc_path.write_text(tc_text, encoding='utf-8')
                print_success(f"✓ Generated testcase doc: {tc_path}")

                usage = tc_response.get('usage', {})
                cost_stats['calls'] += 1
                cost_stats['input_tokens'] += usage.get('prompt_tokens', 0)
                cost_stats['output_tokens'] += usage.get('completion_tokens', 0)
            except Exception as e:
                print_warning(f"Failed to generate testcase doc: {e}")

        # ============================================================
        # Summary
        # ============================================================
        self.artifacts.refresh_manifest_for_iteration(iteration)
        total_polish_cost = (cost_stats['input_tokens'] / 1_000_000) * 3.00 + (cost_stats['output_tokens'] / 1_000_000) * 15.00
        print_success(f"✓ Post-QA polish complete")
        print_info(f"  → Generated {cost_stats['calls']} file(s)")
        print_info(f"  → Total polish cost: ${total_polish_cost:.4f}")
        print_info("═══════════════════════════════════════════════════════════")
        print_info("")

        return True, cost_stats

    def _display_cumulative_cost(self, iteration: int, total_calls: int,
                                  total_cache_writes: int, total_cache_hits: int,
                                  total_cache_read_tokens: int, total_cache_write_tokens: int,
                                  total_input_tokens: int, total_output_tokens: int,
                                  total_gpt_calls: int, total_gpt_input_tokens: int,
                                  total_gpt_output_tokens: int):
        """
        FIX #9: Display cumulative cost after each iteration.
        Helps user track spending in real-time during long runs.
        """
        # Calculate Claude costs
        cache_write_cost = (total_cache_write_tokens / 1_000_000) * 3.75
        cache_read_cost = (total_cache_read_tokens / 1_000_000) * 0.30
        non_cached_input_tokens = total_input_tokens - total_cache_read_tokens
        non_cached_input_cost = (non_cached_input_tokens / 1_000_000) * 3.00
        output_cost = (total_output_tokens / 1_000_000) * 15.00
        claude_total = cache_write_cost + cache_read_cost + non_cached_input_cost + output_cost

        # Calculate ChatGPT costs
        gpt_input_cost = (total_gpt_input_tokens / 1_000_000) * 2.50
        gpt_output_cost = (total_gpt_output_tokens / 1_000_000) * 10.00
        gpt_total = gpt_input_cost + gpt_output_cost

        combined_total = claude_total + gpt_total

        print_info("")
        print_info("═══════════════════════════════════════════════════════════")
        print_info(f"CUMULATIVE COST AFTER ITERATION {iteration}")
        print_info("═══════════════════════════════════════════════════════════")
        print_info(f"Claude API:")
        print_info(f"  → Calls: {total_calls}")
        print_info(f"  → Cache writes: {total_cache_writes}, Cache hits: {total_cache_hits}")
        print_info(f"  → Total cost: ${claude_total:.4f}")
        if total_gpt_calls > 0:
            print_info(f"ChatGPT API:")
            print_info(f"  → Calls: {total_gpt_calls}")
            print_info(f"  → Total cost: ${gpt_total:.4f}")
        print_success(f"TOTAL COST SO FAR: ${combined_total:.4f}")
        print_info("═══════════════════════════════════════════════════════════")
        print_info("")

    def _validate_build_artifacts(self, iteration: int) -> Tuple[bool, list]:
        """
        FIX #8: Pre-QA validation to catch incomplete builds early.

        Validates that critical artifacts are present before sending to QA.
        This prevents wasting QA cycles on obviously incomplete builds.

        Checks:
        1. artifact_manifest.json exists and is valid JSON
        2. build_state.json exists with COMPLETED_CLOSED state
        3. Required files are listed in manifest (README, package.json, etc.)
        4. All files in manifest exist in extracted artifacts

        Returns:
            (passed: bool, errors: list[str])
        """
        errors = []
        artifacts_dir = self.artifacts.build_dir / f'iteration_{iteration:02d}_artifacts'

        # Normalization: promote business/frontend/package.json -> business/package.json
        # when canonical business/package.json is missing. This avoids unnecessary
        # patch loops for common path drift under truncation/recovery.
        canonical_pkg = artifacts_dir / 'business' / 'package.json'
        frontend_pkg = artifacts_dir / 'business' / 'frontend' / 'package.json'
        if not canonical_pkg.exists() and frontend_pkg.exists():
            canonical_pkg.parent.mkdir(parents=True, exist_ok=True)
            canonical_pkg.write_text(frontend_pkg.read_text(encoding='utf-8'), encoding='utf-8')
            print_warning("  → Normalized business/frontend/package.json -> business/package.json")
            self.artifacts.refresh_manifest_for_iteration(iteration)

        # Check 1: artifact_manifest.json exists
        manifest_path = artifacts_dir / 'artifact_manifest.json'
        if not manifest_path.exists():
            errors.append("artifact_manifest.json is missing")
            return False, errors, []

        # Check 2: artifact_manifest.json is valid JSON
        try:
            with open(manifest_path) as f:
                manifest = json.load(f)
        except json.JSONDecodeError as e:
            errors.append(f"artifact_manifest.json is malformed: {e}")
            return False, errors, []

        # Check 3: build_state.json exists and has COMPLETED_CLOSED
        build_state_path = artifacts_dir / 'build_state.json'
        if not build_state_path.exists():
            errors.append("build_state.json is missing")
        else:
            try:
                with open(build_state_path) as f:
                    build_state = json.load(f)
                    if build_state.get('state') != 'COMPLETED_CLOSED':
                        errors.append(f"build_state.json has wrong state: {build_state.get('state')}")
            except json.JSONDecodeError as e:
                errors.append(f"build_state.json is malformed: {e}")

        # Check 4: Required files are in manifest
        # FIX #9: Read from QA override if available, otherwise use defaults
        qa_override = getattr(self, 'qa_override', {})
        validation_config = qa_override.get('pre_qa_validation', {})

        required_files = validation_config.get('required_files', ['package.json', 'README.md'])
        optional_files = validation_config.get('optional_files', [])

        manifest_files = [artifact.get('path', '') for artifact in manifest.get('artifacts', [])]

        for required in required_files:
            # Check if required file exists in manifest (could be in subdirectory)
            found = any(required in path for path in manifest_files)
            if not found:
                errors.append(f"Required file '{required}' not listed in artifact_manifest.json")

        # Warn about optional files but don't fail validation
        for optional in optional_files:
            found = any(optional in path for path in manifest_files)
            if not found:
                print_warning(f"  → {optional} not in manifest (will be flagged by QA as HIGH severity)")

        # Check 5: Files in manifest actually exist
        # Skip optional/polish files — these get generated post-QA
        missing_files = []
        missing_optional = []
        for artifact in manifest.get('artifacts', []):
            file_path = artifact.get('path', '')
            if not file_path:
                continue

            # Check if file exists in extracted artifacts
            full_path = artifacts_dir / file_path
            if not full_path.exists():
                # Is this an optional/polish file? Don't fail validation for these.
                is_optional = any(opt.lower() in file_path.lower() for opt in optional_files)
                if is_optional:
                    missing_optional.append(file_path)
                else:
                    missing_files.append(file_path)

        if missing_optional:
            for f in missing_optional:
                print_warning(f"  → {f} in manifest but not extracted (optional — deferred to post-QA polish)")

        if missing_files:
            errors.append(f"Files in manifest but not extracted: {', '.join(missing_files[:5])}")
            if len(missing_files) > 5:
                errors.append(f"  ... and {len(missing_files) - 5} more")

        # Check 6: Minimum artifact count (sanity check)
        min_count = validation_config.get('min_artifact_count', 3)
        artifact_count = len(manifest.get('artifacts', []))
        if artifact_count < min_count:
            errors.append(f"Only {artifact_count} artifacts in manifest (expected at least {min_count})")

        # Check 7: Boilerplate integration (pre-flight guardrail)
        if getattr(self, 'use_boilerplate', False):
            non_business_paths = [p for p in manifest_files if not p.startswith('business/')]
            if non_business_paths:
                sample = ", ".join(non_business_paths[:5])
                errors.append(f"Boilerplate build contains non-business paths: {sample}")
                if len(non_business_paths) > 5:
                    errors.append(f"  ... and {len(non_business_paths) - 5} more")
            has_integration_readme = any(p == 'business/README-INTEGRATION.md' for p in manifest_files)
            if not has_integration_readme:
                print_warning("  → business/README-INTEGRATION.md not in manifest (deferred to post-QA polish)")

        return len(errors) == 0, errors, missing_files

    def _get_previous_iteration_inventory(self, iteration: int) -> list:
        """
        Load required file inventory from prior iteration manifest.
        Returns business/** file paths only.
        """
        if iteration <= 1:
            return []

        prev_manifest = self.artifacts.build_dir / f'iteration_{iteration-1:02d}_artifacts' / 'artifact_manifest.json'
        if not prev_manifest.exists():
            return []

        try:
            with open(prev_manifest) as f:
                manifest = json.load(f)
        except Exception:
            return []

        files = []
        for artifact in manifest.get('artifacts', []):
            path = artifact.get('path', '')
            if path and path.startswith('business/'):
                files.append(path)
        return sorted(set(files))

    def _read_target_file_contents(self, iteration: int, target_files: list) -> dict:
        """
        Read the current content of defect-target files from the previous iteration's
        artifacts directory. Returns {rel_path: file_text} for files that exist, and
        a NEW FILE placeholder for files that don't exist yet (so Claude knows to create them).
        Used to pass actual file content to surgical patch prompts so Claude doesn't
        reconstruct from memory and introduce collateral errors.
        """
        if iteration <= 1 or not target_files:
            return {}
        prev_artifacts_dir = self.artifacts.build_dir / f'iteration_{iteration - 1:02d}_artifacts'
        contents = {}
        for tf in target_files:
            if not tf.startswith('business/'):
                continue
            tf_path = prev_artifacts_dir / tf
            if tf_path.exists():
                try:
                    contents[tf] = tf_path.read_text(encoding='utf-8')
                except Exception:
                    pass
            else:
                # File doesn't exist yet — signal Claude to create it from scratch
                contents[tf] = '# NEW FILE — does not exist yet. Create this file from scratch using the boilerplate patterns above.'
        return contents

    def _extract_defect_target_files(self, defects_text: Optional[str]) -> list:
        """
        Extract explicit business file paths mentioned in defect text.
        """
        if not defects_text:
            return []

        matches = re.findall(r'(business/[A-Za-z0-9_./-]+\.[A-Za-z0-9_]+)', defects_text)
        return sorted(set(matches))

    def _enrich_defects_with_fix_context(self, qa_report: str) -> str:
        """
        For boilerplate builds: prepend architectural fix context before injecting
        defects into the next iteration's prompt.

        QA correctly identifies problems but doesn't tell Claude HOW to fix them
        in the boilerplate context. This enrichment bridges that gap for the most
        common recurring failure patterns.
        """
        if not self.use_boilerplate:
            return qa_report

        report_lower = qa_report.lower()
        has_mock_storage = any(kw in report_lower for kw in [
            'in-memory', 'in memory', 'mock data', 'hardcoded', 'hard-coded',
            'mock id', 'reports_db', 'clients_db', 'dict storage', 'local dict',
            'sequential id', 'len(', 'in-memory storage', 'demo storage'
        ])
        has_db_note = any(kw in report_lower for kw in [
            'database', 'orm', 'boilerplate', 'persistent', 'persistence'
        ])
        has_frontend_hardcode = any(kw in report_lower for kw in [
            'hardcoded client', 'hardcoded data', 'static data', 'hardcoded array'
        ])

        fixes = []

        if has_mock_storage or has_db_note:
            fixes.append(
                "**ARCHITECTURAL FIX REQUIRED — DATA LAYER:**\n"
                "One or more defects require replacing mock/in-memory storage with real persistence.\n"
                "- Remove ALL `x_db = {}` and `data = []` module-level dicts/lists used as storage.\n"
                "- Remove ALL `len(collection) + 1` ID generation — replace with `str(uuid.uuid4())`.\n"
                "- For every read/write: use the boilerplate database ORM/service. "
                "If you are unsure of the exact import, write `# TODO: use boilerplate DB service` "
                "rather than substituting a dict.\n"
                "- Do NOT add a comment saying 'replace with DB later' and keep the dict — remove the dict."
            )

        if has_frontend_hardcode:
            fixes.append(
                "**ARCHITECTURAL FIX REQUIRED — FRONTEND DATA FETCHING:**\n"
                "One or more defects require replacing hardcoded frontend data with API calls.\n"
                "- Remove ALL hardcoded arrays/objects used as data sources in components.\n"
                "- Replace with `fetch('/api/<resource>')` or equivalent async call in useEffect.\n"
                "- Handle loading and error states explicitly."
            )

        if not fixes:
            return qa_report

        header = "**BOILERPLATE FIX CONTEXT (READ BEFORE APPLYING DEFECT FIXES):**\n" + "\n\n".join(fixes)
        return header + "\n\n" + "=" * 60 + "\n\n" + qa_report

    def _extract_defect_resolutions(self, build_output: str) -> str:
        """
        Extract the ## DEFECT RESOLUTIONS block from Claude's patch output.
        Claude may respond to a defect with EXPLAINED (explanation) instead of FIXED (code change).
        Returns the resolutions text if present, empty string otherwise.
        """
        match = re.search(
            r'##\s*DEFECT RESOLUTIONS\s*\n(.*?)(?=\n##\s|\nPATCH_SET_COMPLETE|\Z)',
            build_output, re.DOTALL | re.IGNORECASE
        )
        if match:
            text = match.group(1).strip()
            if text:
                explained = re.findall(r'DEFECT-\d+:\s*EXPLAINED', text, re.IGNORECASE)
                print_info(
                    f"  [RESOLUTIONS] Found EXPLAINED resolutions: "
                    f"{len(explained)} defect(s) — {', '.join(explained)}"
                )
                return text
        return ''

    @staticmethod
    def _extract_defects_for_tracking(qa_report: str) -> list:
        """
        Parse a QA report into a list of dicts for recurrence tracking.
        Returns: [{'location': str, 'classification': str, 'problem': str, 'fix': str}, ...]
        """
        defects = []
        blocks = re.split(r'(?=DEFECT-\d+:)', qa_report)
        for block in blocks:
            if not re.match(r'DEFECT-\d+:', block.strip()):
                continue
            loc = re.search(r'-\s*Location:\s*(.+?)(?:\n|$)', block)
            cls = re.search(r'DEFECT-\d+:\s*(\S+)', block)
            prob = re.search(r'-\s*Problem:\s*(.*?)(?=\n\s*-\s*(?:Expected|Fix|Severity):|\Z)', block, re.DOTALL)
            fix  = re.search(r'-\s*Fix:\s*(.*?)(?=\n\s*-\s*Severity:|\Z)', block, re.DOTALL)

            location = loc.group(1).strip() if loc else ''
            # Strip **FILE: ...** markers
            fm = re.search(r'\*\*FILE:\s*([^*]+)\*\*', location)
            if fm:
                location = fm.group(1).strip()

            defects.append({
                'location':       location,
                'classification': cls.group(1).strip() if cls else '',
                'problem':        prob.group(1).strip() if prob else '',
                'fix':            fix.group(1).strip() if fix else '',
            })
        return defects

    @staticmethod
    def _build_qa_defect_history(recurring_tracker: dict) -> str:
        """
        Build the {{defect_history_block}} string for the QA prompt.
        Shows all tracked defects with their occurrence counts so QA can
        recognise recurring patterns vs one-time bugs.
        Returns empty string if nothing tracked yet.
        """
        if not recurring_tracker:
            return ''

        lines = [
            '**DEFECT HISTORY (from previous iterations — for pattern recognition):**',
            'Use this to classify root cause types. Same file+issue appearing 2+ times = RECURRING-PATTERN.',
            '',
        ]
        for (location, classification), entry in recurring_tracker.items():
            count = entry['count']
            label = 'RECURRING-PATTERN' if count >= 2 else 'appeared once'
            lines.append(f'- {location} ({classification} — {label}, {count}x)')
            lines.append(f'  Pattern: {entry["last_problem"][:100]}')
        lines.append('')
        return '\n'.join(lines) + '\n---\n'

    @staticmethod
    def _build_prohibitions_block(recurring_tracker: dict) -> str:
        """
        Build the {{prohibitions_block}} string from the recurring defect tracker.
        Only includes entries that have reached the promotion threshold (count >= 2).
        Returns empty string if nothing to prohibit yet.
        """
        promoted = {k: v for k, v in recurring_tracker.items() if v['count'] >= 2}
        if not promoted:
            return ''

        lines = [
            '**PERMANENT PROHIBITIONS — HARD CONSTRAINTS FROM PREVIOUS ITERATIONS:**',
            'These patterns have been flagged in 2+ consecutive iterations.',
            'They are NOT defects to weigh — they are hard product boundary decisions.',
            'You MUST NOT output them in any form, under any name.',
            '',
        ]
        for i, ((location, classification), entry) in enumerate(promoted.items(), 1):
            lines.append(
                f'PROHIBITION-{i}: {location} ({classification} — appeared {entry["count"]}x)'
            )
            lines.append(f'  Problem pattern: {entry["last_problem"][:120]}')
            lines.append(f'  Last fix instruction: {entry["last_fix"][:120]}')
            lines.append(f'  HARD RULE: Do not output this pattern in any form. Not these names, not equivalent names.')
            lines.append('')

        return '\n'.join(lines) + '\n---\n'

    @staticmethod
    def _extract_fixed_from_patch(build_output: str, previous_qa_report: str) -> set:
        """
        Parse Claude's PATCH_PLAN line to find FIXED defect IDs, then map those
        IDs to (location, classification) from the previous QA report.
        Returns a set of (location, classification) tuples pending resolution confirmation.
        """
        # Find PATCH_PLAN line
        patch_match = re.search(r'PATCH_PLAN:\s*(.+?)(?:\n|$)', build_output)
        if not patch_match:
            return set()

        patch_line = patch_match.group(1)
        # Find DEFECT-N: FIXED entries
        fixed_ids = set(re.findall(r'DEFECT-(\d+)[:\s]+FIXED', patch_line, re.IGNORECASE))
        if not fixed_ids:
            return set()

        # Map IDs to (location, classification) from previous QA report
        pending = set()
        for block in re.split(r'(?=DEFECT-\d+:)', previous_qa_report):
            id_match = re.match(r'DEFECT-(\d+):', block.strip())
            if not id_match or id_match.group(1) not in fixed_ids:
                continue
            loc = re.search(r'-\s*Location:\s*(.+?)(?:\n|$)', block)
            cls = re.search(r'DEFECT-\d+:\s*(\S+)', block)
            if loc and cls:
                location = loc.group(1).strip()
                fm = re.search(r'\*\*FILE:\s*([^*]+)\*\*', location)
                if fm:
                    location = fm.group(1).strip()
                fix_match = re.search(
                    r'-\s*Fix:\s*(.*?)(?=\n\s*-\s*Severity:|\Z)', block, re.DOTALL
                )
                fix_text = fix_match.group(1).strip()[:150] if fix_match else ''
                pending.add((location, cls.group(1).strip(), fix_text))
        return pending

    @staticmethod
    def _confirm_resolutions(pending: set, current_qa_report: str,
                             resolved_tracker: dict, iteration: int):
        """
        Compare pending (location, classification) pairs against the current QA report.
        Any that do NOT appear in the current report are confirmed resolved — add to tracker.
        Any that DO reappear are not resolved — leave pending (caller decides next step).
        Returns (newly_confirmed: list, still_pending: set).
        """
        current_defects = FOHarness._extract_defects_for_tracking(current_qa_report)
        current_keys = {(d['location'], d['classification']) for d in current_defects}

        newly_confirmed = []
        still_pending = set()

        for location, classification, fix_text in pending:
            if (location, classification) not in current_keys:
                resolved_tracker[(location, classification)] = {
                    'iteration_resolved': iteration,
                    'fix_summary':        fix_text,
                }
                newly_confirmed.append((location, classification))
            else:
                still_pending.add((location, classification, fix_text))

        return newly_confirmed, still_pending

    @staticmethod
    def _build_resolved_defects_block(resolved_tracker: dict) -> str:
        """
        Build the {{resolved_defects_block}} string for the QA prompt.
        Tells QA: these were fixed and confirmed — only re-flag with verbatim evidence.
        Returns empty string if nothing resolved yet.
        """
        if not resolved_tracker:
            return ''

        lines = [
            '**RESOLVED DEFECTS (fixed and confirmed in previous iterations — senior dev ruling):**',
            'These defects were fixed by Claude and confirmed absent in a subsequent QA pass.',
            'Do NOT re-flag them unless you can quote the EXACT wrong line verbatim from the current build.',
            'If you cannot paste the specific offending line — DELETE the defect. It has already been resolved.',
            '',
        ]
        for i, ((location, classification), entry) in enumerate(resolved_tracker.items(), 1):
            lines.append(
                f'RESOLVED-{i}: {location} ({classification}) — confirmed fixed at iteration {entry["iteration_resolved"]}'
            )
            if entry['fix_summary']:
                lines.append(f'  Fix applied: {entry["fix_summary"]}')
        lines.append('')
        return '\n'.join(lines) + '\n---\n'

    # Phrases banned from Evidence fields per qa_prompt.md ABSOLUTE RULES.
    # Any defect whose Evidence contains one of these is auto-removed.
    _BANNED_EVIDENCE_PHRASES = [
        'n/a',
        'not applicable',
        'content of this file is not present',
        'file not shown',
        'not visible in output',
        'presence of the file is confirmed',
        'the presence of the file',
        'not present in the build output',
        'file is absent',
        'file does not exist in the build',
    ]

    # Structural presence claims: if QA says one of these things is missing,
    # we verify against the actual build output. Key: claim substring → file
    # pattern to look for in qa_build_output.
    _PRESENCE_CLAIMS = [
        # (claim pattern in Problem/Evidence,  file pattern that must exist)
        (r'no\s+\.jsx\s+files',               r'\*\*FILE: business/frontend/pages/\S+\.jsx'),
        (r'no frontend pages',                r'\*\*FILE: business/frontend/pages/\S+\.jsx'),
        (r'missing.*frontend.*pages',         r'\*\*FILE: business/frontend/pages/\S+\.jsx'),
        (r'no \.jsx.*frontend',               r'\*\*FILE: business/frontend/pages/\S+\.jsx'),
        (r'missing.*backend.*route',          r'\*\*FILE: business/backend/routes/\S+\.py'),
        (r'no.*backend.*route',               r'\*\*FILE: business/backend/routes/\S+\.py'),
        (r'missing.*routes.*file',            r'\*\*FILE: business/backend/routes/\S+\.py'),
        (r'at least one.*route.*not.*present',r'\*\*FILE: business/backend/routes/\S+\.py'),
    ]

    def _filter_hallucinated_defects(self, qa_report: str, qa_build_output: str) -> str:
        """
        Post-process QA report to auto-remove defects that are invalid.

        Checks applied per defect (in order):
        1. Location outside business/**               — out-of-scope file
        1b. Location is __init__.py                   — Python plumbing, never a defect
        2. Evidence contains a banned absence phrase  — banned per qa_prompt rules
        3. Backtick-quoted evidence not in build output — fabricated code
        6. All backtick evidence snippets are code comments (# or //) — stub files are intentional
        5a. Auth0 contradiction: evidence shows correct destructuring but problem says wrong call
        5b. Fix == Evidence: fix instructs what evidence already shows — self-invalidating
        4. Presence claim is false — QA says X is missing but X IS in build output

        Returns cleaned report with updated counts. Flips to ACCEPTED if 0 remain.
        """
        # Extract the DEFECTS section
        defects_section_match = re.search(
            r'(### DEFECTS\s*)(.*?)(### VERDICT)',
            qa_report, re.DOTALL
        )
        if not defects_section_match:
            return qa_report  # Can't parse — pass through unchanged

        defects_section = defects_section_match.group(2)

        # Split into individual DEFECT-N blocks
        defect_blocks = re.split(r'(?=DEFECT-\d+:)', defects_section)
        defect_blocks = [b.strip() for b in defect_blocks if re.match(r'DEFECT-\d+:', b.strip())]

        if not defect_blocks:
            return qa_report

        kept = []
        removed = []

        for block in defect_blocks:
            defect_id = re.match(r'(DEFECT-\d+):', block)
            defect_id = defect_id.group(1) if defect_id else 'DEFECT-?'

            # --- Extract Location ---
            loc_match = re.search(r'-\s*Location:\s*(.+?)(?:\n|$)', block)
            location_raw = loc_match.group(1).strip() if loc_match else ''

            # Strip **FILE: ...** markers and extract the path
            path_match = re.search(r'\*\*FILE:\s*([^*]+)\*\*', location_raw)
            if path_match:
                file_path = path_match.group(1).strip()
            else:
                bare = re.search(r'([\w][^\s,;]+\.\w+)', location_raw)
                file_path = bare.group(1).strip() if bare else location_raw

            # --- Check 1: Location must be inside business/** ---
            if file_path and not file_path.startswith('business/'):
                reason = f"Location '{file_path}' is outside business/** — out-of-scope"
                removed.append((defect_id, block, reason))
                print_warning(f"  [FILTER] Removed {defect_id}: {reason}")
                continue

            # --- Check 1b: __init__.py is never a valid defect target ---
            import os as _os
            if _os.path.basename(file_path) == '__init__.py':
                reason = f"Location '{file_path}' is an __init__.py — Python package plumbing, never a defect target"
                removed.append((defect_id, block, reason))
                print_warning(f"  [FILTER] Removed {defect_id}: {reason}")
                continue

            # --- Check 1c: __pycache__ / .pyc files are never valid defect targets ---
            if '__pycache__' in file_path or file_path.endswith('.pyc'):
                reason = f"Location '{file_path}' is a compiled bytecode file — never a defect target"
                removed.append((defect_id, block, reason))
                print_warning(f"  [FILTER] Removed {defect_id}: {reason}")
                continue

            # --- Check 1d: Standard infrastructure columns are never scope violations ---
            # status / created_at / updated_at must always be present on every model.
            # QA routinely ignores the ABSOLUTE RULES instruction and flags these as SCOPE-BOUNDARY.
            # Patterns cover all forms QA may cite:
            #   ORM: status = Column(...)
            #   Dict key / Alembic positional arg: "status": ..., sa.Column('status', ...)
            #   Attribute access in service/route: update.status, horse.status
            _INFRA_COLUMN_PATTERNS = (
                # ORM model column assignment
                r'\b(?:status|created_at|updated_at|processing_status)\s*=\s*Column\b',
                # Dict key or positional column string: "status": ..., 'status', ...
                r"""["'](?:status|created_at|updated_at|processing_status)["']\s*[,:]""",
                # Attribute access: update.status, .created_at etc.
                r"""\.\b(?:status|created_at|updated_at|processing_status)\b""",
            )
            _ev_block_for_1d = re.search(
                r'-\s*Evidence:\s*(.*?)(?=\n\s*-\s*(?:Problem|Expected|Fix|Severity):|\Z)',
                block, re.DOTALL
            )
            _ev_text_1d = _ev_block_for_1d.group(1).strip() if _ev_block_for_1d else ''
            # Extract all backtick-quoted snippets from evidence
            _bt_snippets_1d = re.findall(r'`([^`]{3,})`', _ev_text_1d)
            if _bt_snippets_1d and all(
                any(re.search(pat, snip) for pat in _INFRA_COLUMN_PATTERNS)
                for snip in _bt_snippets_1d
            ):
                reason = (
                    f"Evidence only references standard infrastructure column(s) "
                    f"(status/created_at/updated_at) — these are required on every model and "
                    f"must never be flagged as scope violations"
                )
                removed.append((defect_id, block, reason))
                print_warning(f"  [FILTER] Removed {defect_id}: {reason}")
                continue

            # --- Extract Evidence + Problem + What breaks text for checks 2-7 ---
            ev_match = re.search(
                r'-\s*Evidence:\s*(.*?)(?=\n\s*-\s*(?:What breaks|Problem|Expected|Fix|Severity):|\Z)',
                block, re.DOTALL
            )
            evidence_text = ev_match.group(1).strip() if ev_match else ''

            prob_match = re.search(
                r'-\s*Problem:\s*(.*?)(?=\n\s*-\s*(?:Expected|Fix|Severity):|\Z)',
                block, re.DOTALL
            )
            problem_text = prob_match.group(1).strip() if prob_match else ''

            wb_match = re.search(
                r'-\s*What breaks:\s*(.*?)(?=\n\s*-\s*(?:Problem|Expected|Fix|Severity):|\Z)',
                block, re.DOTALL
            )
            what_breaks_text = wb_match.group(1).strip() if wb_match else ''

            # --- Check 7: Chain-of-evidence enforcement (Steal 3.4) ---
            # a) Evidence must contain at least one backtick-quoted code snippet
            _ev_snippets = re.findall(r'`([^`]+)`', evidence_text)
            _ev_code = [s.strip() for s in _ev_snippets if len(s.strip()) > 4]
            if not _ev_code:
                reason = f"Chain-of-evidence: no backtick-quoted code snippet in Evidence — defect has no proof"
                removed.append((defect_id, block, reason))
                print_warning(f"  [FILTER] Removed {defect_id}: {reason}")
                continue

            # b) "What breaks" must not be vague hedging
            _HEDGE_PHRASES = ('may ', 'could ', 'might ', 'potentially ', 'may cause', 'could lead',
                              'might result', 'could be problematic', 'may cause issues')
            if what_breaks_text:
                _wb_lower = what_breaks_text.lower()
                hedge_hit = next((h for h in _HEDGE_PHRASES if h in _wb_lower), None)
                if hedge_hit:
                    reason = f"Chain-of-evidence: 'What breaks' uses hedge phrase '{hedge_hit}' — defect is speculative"
                    removed.append((defect_id, block, reason))
                    print_warning(f"  [FILTER] Removed {defect_id}: {reason}")
                    continue

            # --- Check 2: Evidence must not contain banned absence phrases ---
            evidence_lower = evidence_text.lower()
            banned_hit = next(
                (p for p in self._BANNED_EVIDENCE_PHRASES if p in evidence_lower), None
            )
            if banned_hit:
                reason = f"Evidence contains banned phrase '{banned_hit}' — invalid per QA rules"
                removed.append((defect_id, block, reason))
                print_warning(f"  [FILTER] Removed {defect_id}: {reason}")
                continue

            # --- Check 3: Backtick-quoted evidence must exist in build output ---
            backtick_snippets = re.findall(r'`([^`]+)`', evidence_text)
            meaningful = [s.strip() for s in backtick_snippets if len(s.strip()) > 8]
            if meaningful:
                found = any(snippet in qa_build_output for snippet in meaningful)
                if not found:
                    reason = f"Evidence {meaningful[:1]} not found in build output — fabricated"
                    removed.append((defect_id, block, reason))
                    print_warning(f"  [FILTER] Removed {defect_id}: {reason}")
                    continue

            # --- Check 6: Comment-only evidence — only suppress explicit scope exclusions ---
            # Narrowed rule: only filter when all snippets are comments AND at least one
            # snippet clearly states a scope-exclusion boundary. This prevents false
            # negatives where comment-only evidence is actually indicating missing code.
            if meaningful:
                all_comments = all(
                    s.lstrip().startswith('#') or s.lstrip().startswith('//')
                    for s in meaningful
                )
                scope_exclusion_phrases = (
                    'not in scope',
                    'out of scope',
                    'outside scope',
                    'per intake requirements',
                    'excluded by intake',
                    'intentionally excluded',
                )
                has_scope_exclusion = any(
                    any(p in s.lower() for p in scope_exclusion_phrases)
                    for s in meaningful
                )
                if all_comments and has_scope_exclusion:
                    reason = (
                        f"Comment-only scope-exclusion evidence ({meaningful[:1]}) — "
                        "intentional boundary note, not executable defect"
                    )
                    removed.append((defect_id, block, reason))
                    print_warning(f"  [FILTER] Removed {defect_id}: {reason}")
                    continue

            # --- Check 5: Evidence contradicts Problem (self-invalidating defect) ---
            # Sub-check A: Auth0 getAccessTokenSilently hallucination.
            # QA sees `getAccessTokenSilently` in a file and generates a defect claiming
            # `user.getAccessTokenSilently()` is called — but if the evidence itself shows
            # it properly destructured from useAuth0(), the code is already correct.
            _ev_has_correct_auth0 = bool(re.search(
                r'getAccessTokenSilently.*useAuth0\(\)|useAuth0\(\).*getAccessTokenSilently',
                evidence_text
            ))
            # Accept paraphrased Auth0 hallucinations (not only exact literal wording).
            _defect_is_auth0_related = bool(re.search(
                r'getAccessTokenSilently|useAuth0|auth0|user object|token.*method|method.*user object',
                problem_text,
                re.IGNORECASE
            ))
            if _ev_has_correct_auth0 and _defect_is_auth0_related:
                reason = (
                    "Auth0 contradiction: Evidence shows correct getAccessTokenSilently "
                    "destructuring from useAuth0(); defect is invalid regardless of problem phrasing"
                )
                removed.append((defect_id, block, reason))
                print_warning(f"  [FILTER] Removed {defect_id}: {reason}")
                continue

            # Sub-check B: Fix == Evidence (defect claims something is wrong
            # but the Fix says to use exactly what the Evidence already shows).
            fix_match = re.search(
                r'-\s*Fix:\s*(.*?)(?=\n\s*-\s*(?:Severity|Root cause):|\Z)',
                block, re.DOTALL
            )
            fix_text = fix_match.group(1).strip() if fix_match else ''
            # Extract backtick snippets from Fix
            fix_snippets = re.findall(r'`([^`]+)`', fix_text)
            fix_meaningful = [s.strip() for s in fix_snippets if len(s.strip()) > 8]
            # If every Fix snippet already appears in the Evidence, the defect is self-contradicting
            if fix_meaningful and all(fs in evidence_text for fs in fix_meaningful):
                reason = (
                    f"Self-contradicting defect: Fix snippet(s) {fix_meaningful[:1]} "
                    "already present in Evidence — code is already correct"
                )
                removed.append((defect_id, block, reason))
                print_warning(f"  [FILTER] Removed {defect_id}: {reason}")
                continue

            # --- Check 4: Presence claims — verify against actual build output ---
            combined_claim = (evidence_text + ' ' + problem_text).lower()
            for claim_pattern, file_pattern in self._PRESENCE_CLAIMS:
                if re.search(claim_pattern, combined_claim, re.IGNORECASE):
                    # QA claims this file/type is missing — check if it actually is
                    if re.search(file_pattern, qa_build_output, re.IGNORECASE):
                        reason = (
                            f"Presence claim '{claim_pattern}' is false — "
                            f"matching file found in build output"
                        )
                        removed.append((defect_id, block, reason))
                        print_warning(f"  [FILTER] Removed {defect_id}: {reason}")
                        break  # Only need one match to disqualify
            else:
                kept.append(block)
                continue

            # If we broke out of the for loop (presence claim removed it), don't kept.append


        if not removed:
            return qa_report  # Nothing changed — return original

        # --- Rebuild SUMMARY counts ---
        kept_text = '\n'.join(kept)
        bug_count  = len(re.findall(r'IMPLEMENTATION_BUG',   kept_text))
        spec_count = len(re.findall(r'SPEC_COMPLIANCE_ISSUE', kept_text))
        scope_count = len(re.findall(r'SCOPE_CHANGE_REQUEST', kept_text))
        total_kept = len(kept)

        summary = (
            f"### SUMMARY\n"
            f"- Total defects found: {total_kept}\n"
            f"- IMPLEMENTATION_BUG: {bug_count}\n"
            f"- SPEC_COMPLIANCE_ISSUE: {spec_count}\n"
            f"- SCOPE_CHANGE_REQUEST: {scope_count}\n"
        )

        filter_note = (
            f"> **[HARNESS FILTER]** Removed {len(removed)} defect(s): "
            + ', '.join(d[0] for d in removed)
            + ' — fabricated evidence or out-of-scope locations.\n'
        )

        # Renumber kept defects sequentially
        counter = [0]
        def _renumber(m):
            counter[0] += 1
            return f'DEFECT-{counter[0]}:'
        renumbered = re.sub(r'DEFECT-\d+:', _renumber, '\n\n'.join(kept))

        if total_kept > 0:
            defects_body = renumbered
            verdict = f"QA STATUS: REJECTED - [{total_kept}] defect{'s' if total_kept != 1 else ''} require fixing"
        else:
            defects_body = (
                f"(All {len(removed)} QA defect(s) removed by harness filter — "
                "fabricated evidence or out-of-scope file locations.)"
            )
            verdict = "QA STATUS: ACCEPTED - Ready for deployment"

        new_report = (
            f"## QA REPORT\n\n"
            f"{filter_note}\n"
            f"{summary}\n"
            f"### DEFECTS\n\n{defects_body}\n\n"
            f"### VERDICT\n{verdict}"
        )

        print_info(f"  [FILTER] QA report filtered: {len(removed)} defect(s) removed, {total_kept} remaining")
        return new_report

    def _build_intake_summary_for_triage(self) -> str:
        """Compact intake summary for the defect triage prompt."""
        if not self.intake_data:
            return '(No intake data available)'
        lines = []
        for key in ('feature_name', 'feature_description', 'core_features',
                    'user_stories', 'data_model', 'success_metrics'):
            val = self.intake_data.get(key)
            if val:
                lines.append(f"{key}: {str(val)[:400]}")
        return '\n'.join(lines) if lines else str(self.intake_data)[:600]

    def _triage_and_sharpen_defects(
        self,
        qa_report: str,
        iteration: int,
        recurring_tracker: dict,
        current_file_contents: dict,
    ) -> tuple:
        """
        After hallucination filter, assess remaining QA defects before triggering a build.

        For each defect:
        - SURGICAL: isolated 1-5 line fix. Sharpens Fix field to exact function+line+change.
        - SYSTEMIC: architectural or 3+ oscillations. Describes flow problem + direction.
        - INVALID: scope creep / not in intake spec → drop.

        Returns:
            sharpened_report (str): qa_report with Fix fields replaced by specific instructions
            strategy (str): 'surgical' | 'systemic' | 'accepted' (all invalid → flip to pass)
            contested (list): dicts with defect number, location, reason for each INVALID
        """
        defects = self._extract_defects_for_tracking(qa_report)
        if not defects:
            return qa_report, 'surgical', []

        # Build recurrence summary
        recurrence_lines = []
        for d in defects:
            key = (d['location'], d['classification'])
            count = recurring_tracker.get(key, {}).get('count', 0)
            last_fix = recurring_tracker.get(key, {}).get('last_fix', '')
            recurrence_lines.append(
                f"- {d['location']} ({d['classification']}): "
                f"appeared {count} time(s) previously"
                + (f" | last attempted fix: {last_fix[:120]}" if last_fix else "")
            )
        recurrence_summary = '\n'.join(recurrence_lines) if recurrence_lines else 'None — first appearance of all defects.'

        # Build file contents section (only files we have)
        if current_file_contents:
            file_parts = []
            for path, content in current_file_contents.items():
                file_parts.append(f"**FILE: {path}**\n```\n{content}\n```")
            file_section = '\n\n'.join(file_parts)
        else:
            file_section = '(No current file contents available for these defects.)'

        # Extract raw defect blocks from qa_report
        blocks = re.split(r'(?=DEFECT-\d+:)', qa_report)
        defect_blocks = [b.strip() for b in blocks if re.match(r'DEFECT-\d+:', b.strip())]
        defects_section = '\n\n'.join(defect_blocks)

        intake_summary = self._build_intake_summary_for_triage()

        prompt = f"""You are a senior engineer triaging QA defects before sending them to a developer.
Your job: classify each defect and sharpen its Fix field into a specific, unambiguous instruction.

**WHAT IS ACTUALLY REQUIRED (intake spec — this is the source of truth):**
{intake_summary}

**RECURRENCE HISTORY (how many times each defect has appeared before):**
{recurrence_summary}

**CURRENT FILE CONTENTS (the actual code being fixed):**
{file_section}

**DEFECTS TO TRIAGE:**
{defects_section}

---

For each defect, respond in EXACTLY this format (no extra text):

TRIAGE-N:
  CLASSIFICATION: SURGICAL | SYSTEMIC | INVALID
  ROOT_CAUSE: <one sentence — WHY this bug exists, not WHAT is wrong. Identify the underlying cause, not the symptom. Example: "Claude used Flask db.session pattern but boilerplate expects FastAPI Depends(get_db)">
  REASON: <one sentence — why this classification>
  SHARPENED_FIX: <see rules below>

CLASSIFICATION rules:
- SURGICAL: isolated bug, 1-5 line change, fix is deterministic. Any developer reads the sharpened fix and makes the same change.
- SYSTEMIC: the fix requires changing how multiple components interact, OR this defect has appeared 3+ times (surgical approach is not working — escalate), OR the current implementation approach is fundamentally wrong.
- INVALID: the intake spec does not require this behavior, or the defect is asking for something beyond what was specified.

SHARPENED_FIX rules:
- SURGICAL: Name the exact function, what the current line says, and what it must change to. Example: "In handleSubmit(), change `axios.post('/api/reports')` to `axios.post('/api/reports/generate')`". No phrases like "update the logic" or "ensure validation".
- SYSTEMIC: Describe what the flow problem is and what architectural change is needed. Be specific about which files and which interaction is wrong.
- INVALID: N/A

Do NOT change the meaning of real bugs — only make the fix instruction more precise.
End your response with: TRIAGE_COMPLETE"""

        try:
            gpt_client = ChatGPTClient()
            result = gpt_client.call(prompt, max_tokens=2048)
            triage_output = result.get('choices', [{}])[0].get('message', {}).get('content', '')
            self.artifacts.save_log(f'iteration_{iteration:02d}_triage_output', triage_output)
        except Exception as e:
            print_warning(f"  [TRIAGE] Triage call failed ({e}) — proceeding with unsharpened defects")
            return qa_report, 'surgical', []

        return self._parse_triage_output(triage_output, qa_report, recurring_tracker, defects, iteration)

    def _parse_triage_output(
        self,
        triage_output: str,
        qa_report: str,
        recurring_tracker: dict,
        defects: list,
        iteration: int,
    ) -> tuple:
        """
        Parse triage output. Replaces Fix fields in qa_report with sharpened versions.
        Returns (sharpened_report, strategy, contested).
        """
        # Parse TRIAGE-N blocks
        triage_blocks = {}
        for match in re.finditer(
            r'TRIAGE-(\d+):\s*\n(.*?)(?=TRIAGE-\d+:|TRIAGE_COMPLETE|\Z)',
            triage_output, re.DOTALL
        ):
            n = int(match.group(1))
            block = match.group(2)
            cls_match    = re.search(r'CLASSIFICATION:\s*(SURGICAL|SYSTEMIC|INVALID)', block)
            root_match   = re.search(r'ROOT_CAUSE:\s*(.+?)(?=\n\s*(?:REASON|SHARPENED_FIX):|\Z)', block, re.DOTALL)
            reason_match = re.search(r'REASON:\s*(.+?)(?=\n\s*SHARPENED_FIX:|\Z)', block, re.DOTALL)
            fix_match    = re.search(r'SHARPENED_FIX:\s*(.*?)(?=\n\s*TRIAGE-|\n\s*TRIAGE_COMPLETE|\Z)', block, re.DOTALL)
            triage_blocks[n] = {
                'classification': cls_match.group(1).strip()   if cls_match   else 'SURGICAL',
                'root_cause':     root_match.group(1).strip()  if root_match  else '',
                'reason':         reason_match.group(1).strip() if reason_match else '',
                'sharpened_fix':  fix_match.group(1).strip()   if fix_match   else '',
            }

        if not triage_blocks:
            print_warning("  [TRIAGE] Could not parse triage output — proceeding with unsharpened defects")
            return qa_report, 'surgical', []

        classifications = [t['classification'] for t in triage_blocks.values()]
        all_invalid  = all(c == 'INVALID'  for c in classifications)
        any_systemic = any(c == 'SYSTEMIC' for c in classifications)
        contested    = []

        # Log each decision (including root cause for audit)
        labels = {'SURGICAL': '[SURGICAL]', 'SYSTEMIC': '[SYSTEMIC]', 'INVALID': '[INVALID ]'}
        for i, (n, t) in enumerate(sorted(triage_blocks.items())):
            loc = defects[i]['location'] if i < len(defects) else f'DEFECT-{n}'
            label = labels.get(t['classification'], '[?]')
            print_info(f"  [TRIAGE] DEFECT-{n} {label} {loc} — {t['reason'][:90]}")
            if t.get('root_cause'):
                print_info(f"           ROOT_CAUSE: {t['root_cause'][:120]}")
            if t['classification'] == 'INVALID':
                contested.append({'defect': n, 'location': loc, 'reason': t['reason']})

        if all_invalid:
            print_success("  [TRIAGE] All defects classified INVALID — accepting build without fix pass")
            return qa_report, 'accepted', contested

        # Replace Fix: fields in qa_report with sharpened versions (SURGICAL and SYSTEMIC only)
        sharpened_report = qa_report
        for n, t in sorted(triage_blocks.items()):
            if t['classification'] == 'INVALID':
                continue
            if not t['sharpened_fix'] or t['sharpened_fix'].upper() == 'N/A':
                continue
            # Match Fix: field inside DEFECT-N block, up to next - Severity: or end of block
            pattern = rf'(DEFECT-{n}:.*?-\s*Fix:\s*)(.*?)(\n\s*-\s*Severity:)'
            replacement = rf'\g<1>{t["sharpened_fix"]}\g<3>'
            new_report = re.sub(pattern, replacement, sharpened_report, flags=re.DOTALL)
            if new_report != sharpened_report:
                print_info(f"  [TRIAGE] DEFECT-{n} Fix field sharpened")
                sharpened_report = new_report

        # Inject ROOT_CAUSE analysis block into the sharpened report (Steal 1.2a — Reflexion).
        # This gives Claude the "why" before the "what", improving fix accuracy.
        root_cause_lines = []
        for n, t in sorted(triage_blocks.items()):
            if t['classification'] == 'INVALID':
                continue
            if t.get('root_cause'):
                loc = defects[n - 1]['location'] if (n - 1) < len(defects) else f'DEFECT-{n}'
                root_cause_lines.append(f"- DEFECT-{n} ({loc}): {t['root_cause']}")

        if root_cause_lines:
            root_cause_block = (
                "\n## ROOT CAUSE ANALYSIS (from triage — fix the cause, not just the symptom)\n"
                + '\n'.join(root_cause_lines)
                + "\n\nFix the root cause FIRST. Individual defects should resolve as a consequence.\n\n"
            )
            # Prepend root cause block before the first DEFECT-
            defect_start = re.search(r'DEFECT-1:', sharpened_report)
            if defect_start:
                sharpened_report = (
                    sharpened_report[:defect_start.start()]
                    + root_cause_block
                    + sharpened_report[defect_start.start():]
                )

        strategy = 'systemic' if any_systemic else 'surgical'
        systemic_count = sum(1 for c in classifications if c == 'SYSTEMIC')
        surgical_count = sum(1 for c in classifications if c == 'SURGICAL')
        print_info(
            f"  [TRIAGE] Strategy: {strategy.upper()} "
            f"({surgical_count} surgical, {systemic_count} systemic, {len(contested)} invalid)"
        )
        return sharpened_report, strategy, contested

    # Patterns that indicate a SYSTEMIC static defect (missing files / empty dirs)
    _SYSTEMIC_STATIC_PATTERNS = [
        r'no frontend pages',
        r'no \.jsx files',
        r'pages.*is empty',
        r'does not resolve',
        r'does not exist in artifacts',
        r'missing file',
        r'no such file',
        r'file not found',
        r'create.*\.py.*or fix the import',
        r'does not match.*arity',
    ]

    def _triage_pre_qa_strategy(
        self,
        defect_source: str,
        defect_target_files: list,
        previous_defects: str,
        consecutive_iters: int,
    ) -> str:
        """
        Rule-based SURGICAL / SYSTEMIC classification for static and consistency defects,
        applied before triggering a build. No AI call — mechanical signals only.

        SYSTEMIC (→ full build with defects as context) when:
        - consecutive_iters >= 2: surgical patch has already failed twice in a row
        - ≥4 distinct target files: too many moving parts for a targeted patch
        - Any "missing file" / "no frontend pages" / "does not resolve" pattern:
          creating a new file from scratch needs the full governance + spec context

        Returns 'surgical' or 'systemic'.
        """
        # Rule 1: surgical has already failed twice consecutively → try full build
        if consecutive_iters >= 2:
            print_info(
                f"  [{defect_source.upper()} TRIAGE] SYSTEMIC — surgical failed "
                f"{consecutive_iters} consecutive time(s)"
            )
            return 'systemic'

        # Rule 2: too many distinct files for targeted patch
        if len(defect_target_files) >= 4:
            print_info(
                f"  [{defect_source.upper()} TRIAGE] SYSTEMIC — {len(defect_target_files)} "
                f"target files (≥4 → full build)"
            )
            return 'systemic'

        # Rule 3: defect text signals missing/non-existent files
        defect_text_lower = (previous_defects or '').lower()
        for pattern in self._SYSTEMIC_STATIC_PATTERNS:
            if re.search(pattern, defect_text_lower):
                print_info(
                    f"  [{defect_source.upper()} TRIAGE] SYSTEMIC — missing-file pattern "
                    f"detected: '{pattern}'"
                )
                return 'systemic'

        print_info(
            f"  [{defect_source.upper()} TRIAGE] SURGICAL — {len(defect_target_files)} "
            f"file(s), no missing-file pattern, first/second consecutive"
        )
        return 'surgical'

    def _sharpen_consistency_issues(self, issues: list, iteration: int) -> list:
        """
        Sharpen Fix fields in consistency issues before passing to Claude.

        For each A <-> B mismatch, specifies:
        - Which file to change (the caller/smaller-change side)
        - Exact function name
        - Exact line change (from X to Y)

        Without sharpening, Claude picks the wrong side of the mismatch or makes
        an ambiguous change that shifts the problem to the other file next iteration.

        Uses gpt-4o-mini (cheap, fast). Falls back silently if call fails.
        """
        if not issues:
            return issues

        # Extract all involved files from issues
        involved_files = []
        for iss in issues:
            files_str = iss.get('files', iss.get('file', ''))
            for f in re.split(r'\s*<->\s*|\s*,\s*|\s+', files_str):
                f = f.strip()
                if f.startswith('business/'):
                    involved_files.append(f)
        involved_files = list(set(involved_files))

        file_contents = self._read_target_file_contents(iteration, involved_files)
        if not file_contents:
            print_warning("  [CONSISTENCY SHARPEN] No file contents available — proceeding unsharpened")
            return issues

        file_section = '\n\n'.join(
            f"**FILE: {path}**\n```python\n{content}\n```"
            for path, content in file_contents.items()
        )

        issues_text = '\n\n'.join(
            f"ISSUE-{iss['id'].replace('ISSUE-', '')}:\n"
            f"  Files: {iss.get('files', iss.get('file', ''))}\n"
            f"  Evidence: {iss.get('evidence', '')}\n"
            f"  Problem: {iss.get('issue', '')}\n"
            f"  Current Fix: {iss.get('fix', '')}"
            for iss in issues
        )

        prompt = f"""You are a senior engineer sharpening fix instructions for cross-file consistency issues.
For each issue, specify EXACTLY which file to change, which function, and what the code changes to.
Pick the side that requires the smaller, safer change (prefer caller changes over callee redesign).

**CURRENT FILE CONTENTS:**
{file_section}

**CONSISTENCY ISSUES TO SHARPEN:**
{issues_text}

---

For each issue respond in EXACTLY this format:

SHARP-N:
  FILE_TO_CHANGE: <exact file path e.g. business/services/ReportService.py>
  FUNCTION: <exact function/method name>
  CHANGE: <current expression or line> → <what it must become>

Rules:
- CHANGE must show concrete code, not a description ("calculate_scores(data)" → "calculate_kpis(assessment.id, db)")
- If the callee needs a new method, add it AND update the caller — list both as separate SHARP-N entries
- Do NOT change __tablename__, Base imports, or Column definitions
- Do NOT restructure files beyond the specific mismatch

End with: SHARPEN_COMPLETE"""

        try:
            gpt_client = ChatGPTClient()
            result = gpt_client.call(prompt, max_tokens=1024)
            sharp_output = result.get('choices', [{}])[0].get('message', {}).get('content', '')
            self.artifacts.save_log(
                f'iteration_{iteration:02d}_consistency_sharpen', sharp_output
            )
            if not sharp_output:
                print_warning("  [CONSISTENCY SHARPEN] Empty response — proceeding unsharpened")
                return issues
        except Exception as e:
            print_warning(f"  [CONSISTENCY SHARPEN] Call failed ({e}) — proceeding unsharpened")
            return issues

        # Parse SHARP-N blocks and update fix fields in a copy of the issues list
        sharpened = [dict(iss) for iss in issues]  # shallow copy each dict
        for match in re.finditer(
            r'SHARP-(\d+):\s*\n(.*?)(?=SHARP-\d+:|SHARPEN_COMPLETE|\Z)',
            sharp_output, re.DOTALL
        ):
            n = int(match.group(1))
            block = match.group(2)
            file_m   = re.search(r'FILE_TO_CHANGE:\s*(.+?)(?=\n|$)', block)
            func_m   = re.search(r'FUNCTION:\s*(.+?)(?=\n|$)', block)
            change_m = re.search(r'CHANGE:\s*(.*?)(?=\n\s*SHARP-|\n\s*SHARPEN_COMPLETE|\Z)', block, re.DOTALL)
            if not (file_m and func_m and change_m):
                continue
            sharpened_fix = (
                f"In `{file_m.group(1).strip()}`, "
                f"function `{func_m.group(1).strip()}`: "
                f"{change_m.group(1).strip()}"
            )
            if 1 <= n <= len(sharpened):
                sharpened[n - 1]['fix'] = sharpened_fix
                print_info(f"  [CONSISTENCY SHARPEN] ISSUE-{n} fix sharpened: {sharpened_fix[:110]}")

        return sharpened

    @staticmethod
    def _find_last_accepted_iteration(run_dir: Path) -> int:
        """
        Scan qa/iteration_*_qa_report.txt in run_dir for the highest iteration
        that contains 'QA STATUS: ACCEPTED'. Returns 0 if none found.
        """
        qa_dir = run_dir / 'qa'
        if not qa_dir.exists():
            return 0
        best = 0
        for qa_file in sorted(qa_dir.glob('iteration_*_qa_report.txt')):
            try:
                if 'QA STATUS: ACCEPTED' in qa_file.read_text(encoding='utf-8', errors='replace'):
                    m = re.search(r'iteration_(\d+)_qa_report', qa_file.name)
                    if m:
                        best = max(best, int(m.group(1)))
            except Exception:
                continue
        return best

    @staticmethod
    def _run_static_check(artifacts_dir: Path, intake_data: dict = None) -> list:
        """
        Run deterministic static checks on extracted artifacts.

        Checks (in order):
        1. AST syntax — parse every .py file; any SyntaxError is HIGH
        2. Duplicate __tablename__ — two models share a DB table name; HIGH
        3. Missing TenantMixin import — class uses TenantMixin but import absent; HIGH
        4. Wrong Base import — uses app.models.base or raw declarative_base(); HIGH
        5. Requirements.txt YAML contamination — docker-compose YAML in pip file; HIGH
        6. Unauthenticated routes — endpoint defined without Depends(get_current_user); MEDIUM
        7. File-role mismatch — router code in models/ or executable route files with no endpoints
        8. Frontend config file mismatch — swapped/invalid next/postcss/tailwind config
        9. Local import integrity — module existence + case-sensitive path + imported symbol existence
        10. Route↔service contract sanity — missing method or constructor arity mismatch
        11. Intake-aware KPI contract (if intake_data is provided)
        12. Intake-aware downloadable-report contract (if intake_data is provided)
        13. Missing frontend pages — backend routes exist but no business/frontend/pages/*.jsx

        Returns list of defect dicts:
            {'id': 'STATIC-N', 'file': path, 'issue': str, 'severity': HIGH|MEDIUM, 'fix': str}
        """
        import ast

        defects = []
        counter = [0]
        parsed_ast = {}

        def add_defect(file_path, issue, severity, fix, related_files=None):
            counter[0] += 1
            d = {
                'id': f'STATIC-{counter[0]}',
                'file': file_path,
                'issue': issue,
                'severity': severity,
                'fix': fix
            }
            if related_files:
                d['related_files'] = [f for f in related_files if f and f != file_path]
            defects.append(d)

        def _read(path: Path) -> str:
            try:
                return path.read_text(encoding='utf-8', errors='replace')
            except Exception:
                return ''

        def _list_children_exact(dir_path: Path) -> set:
            try:
                return {p.name for p in dir_path.iterdir()}
            except Exception:
                return set()

        def _exists_case_sensitive(root: Path, rel_parts: list) -> bool:
            cur = root
            for idx, part in enumerate(rel_parts):
                children = _list_children_exact(cur)
                if part not in children:
                    return False
                cur = cur / part
                if idx < len(rel_parts) - 1 and not cur.is_dir():
                    return False
            return cur.exists()

        def _module_rel_from_business_module(module_name: str) -> str:
            # business.services.foo -> business/services/foo.py
            return str(Path(*module_name.split('.'))).replace('\\', '/') + '.py'

        def _collect_values_for_keys(obj, wanted_keys: set) -> list:
            out = []

            def _walk(v):
                if isinstance(v, dict):
                    for k, vv in v.items():
                        if str(k).lower() in wanted_keys:
                            out.append(vv)
                        _walk(vv)
                elif isinstance(v, list):
                    for item in v:
                        _walk(item)

            _walk(obj)
            return out

        def _gather_exported_symbols(mod_ast: ast.AST) -> set:
            out = set()
            for node in getattr(mod_ast, 'body', []):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    out.add(node.name)
                elif isinstance(node, ast.Assign):
                    for t in node.targets:
                        if isinstance(t, ast.Name):
                            out.add(t.id)
                elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                    out.add(node.target.id)
                elif isinstance(node, ast.ImportFrom):
                    for a in node.names:
                        if a.name != '*':
                            out.add(a.asname or a.name)
            return out

        py_files = sorted(artifacts_dir.rglob('*.py'))

        # ── CHECK 1: AST Syntax ──────────────────────────────────────────────
        for py_file in py_files:
            rel = str(py_file.relative_to(artifacts_dir))
            if rel in ('artifact_manifest.json', 'build_state.json'):
                continue
            try:
                source = py_file.read_text(encoding='utf-8', errors='replace')
                parsed_ast[rel] = ast.parse(source, filename=str(py_file))
            except SyntaxError as e:
                add_defect(
                    rel,
                    f'SyntaxError at line {e.lineno}: {e.msg}',
                    'HIGH',
                    f'Fix syntax error at line {e.lineno} in {rel}: {e.msg}'
                )

        # ── CHECK 2: Duplicate __tablename__ ────────────────────────────────
        tablename_map: dict = {}  # tablename → list of files
        for py_file in py_files:
            rel = str(py_file.relative_to(artifacts_dir))
            try:
                source = py_file.read_text(encoding='utf-8', errors='replace')
                for match in re.finditer(r'__tablename__\s*=\s*["\']([^"\']+)["\']', source):
                    tname = match.group(1)
                    tablename_map.setdefault(tname, []).append(rel)
            except Exception:
                continue
        for tname, files in tablename_map.items():
            if len(files) > 1:
                add_defect(
                    files[0],
                    f'Duplicate __tablename__ = "{tname}" also defined in: {", ".join(files[1:])}',
                    'HIGH',
                    f'Remove the duplicate model class definition. Keep exactly one file with __tablename__ = "{tname}".'
                )

        # ── CHECK 3: Missing TenantMixin import ─────────────────────────────
        for py_file in py_files:
            rel = str(py_file.relative_to(artifacts_dir))
            source = _read(py_file)
            # Class inherits TenantMixin
            if re.search(r'class\s+\w+\s*\([^)]*TenantMixin[^)]*\)', source):
                # But import is absent
                if 'from core.tenancy import' not in source or 'TenantMixin' not in re.findall(
                    r'from core\.tenancy import ([^\n]+)', source, re.IGNORECASE
                ).__str__():
                    # Refined: check that TenantMixin appears in a core.tenancy import
                    tenancy_imports = re.findall(r'from core\.tenancy import ([^\n]+)', source)
                    imported_names = ','.join(tenancy_imports)
                    if 'TenantMixin' not in imported_names:
                        add_defect(
                            rel,
                            'Class inherits TenantMixin but `from core.tenancy import TenantMixin` is absent',
                            'HIGH',
                            'Add `from core.tenancy import TenantMixin, get_tenant_db` at top of file'
                        )

        # ── CHECK 4: Wrong Base import ───────────────────────────────────────
        for py_file in py_files:
            rel = str(py_file.relative_to(artifacts_dir))
            source = _read(py_file)
            if re.search(r'from\s+app\.models\.base\s+import', source):
                add_defect(
                    rel,
                    'Uses `from app.models.base import Base` — wrong path for boilerplate',
                    'HIGH',
                    'Replace with `from core.database import Base, get_db`'
                )
            elif re.search(r'declarative_base\(\)', source) and 'from core.database' not in source:
                add_defect(
                    rel,
                    'Calls `declarative_base()` directly instead of importing Base from boilerplate',
                    'HIGH',
                    'Remove `declarative_base()` call; import `Base` from `core.database` instead'
                )

        # ── CHECK 5: Requirements.txt YAML contamination ─────────────────────
        req_candidates = [
            artifacts_dir / 'business' / 'backend' / 'requirements.txt',
            artifacts_dir / 'business' / 'requirements.txt',
            artifacts_dir / 'requirements.txt',
        ]
        for req_file in req_candidates:
            if not req_file.exists():
                continue
            try:
                req_content = _read(req_file)
                yaml_indicators = ['services:', 'version:', 'image:', 'container_name:', 'networks:', 'volumes:']
                found_yaml = [ind for ind in yaml_indicators if ind in req_content]
                if found_yaml:
                    rel = str(req_file.relative_to(artifacts_dir))
                    add_defect(
                        rel,
                        f'requirements.txt contains docker-compose/YAML content (found: {", ".join(found_yaml)})',
                        'HIGH',
                        'Replace entire file with valid pip requirements only (one package per line, no YAML keys)'
                    )
            except Exception:
                pass

        # ── CHECK 6: Unauthenticated routes ──────────────────────────────────
        routes_dir = artifacts_dir / 'business' / 'backend' / 'routes'
        if routes_dir.exists():
            for py_file in sorted(routes_dir.glob('*.py')):
                rel = str(py_file.relative_to(artifacts_dir))
                try:
                    source = py_file.read_text(encoding='utf-8', errors='replace')
                except Exception:
                    continue
                # Skip files with no route decorators
                if not re.search(r'@router\.(get|post|put|delete|patch)\s*\(', source):
                    continue
                # Skip files that already have auth
                if ('get_current_user' in source or 'require_role' in source):
                    continue
                # Flag: has routes but zero auth references
                add_defect(
                    rel,
                    'Backend route file defines endpoints but contains no `Depends(get_current_user)` — all routes are unauthenticated',
                    'MEDIUM',
                    'Import `from core.rbac import get_current_user` and add `current_user: dict = Depends(get_current_user)` to each endpoint signature'
                )

        # ── CHECK 7: File-role mismatch (models vs routes) ───────────────────
        models_dir = artifacts_dir / 'business' / 'models'
        if models_dir.exists():
            for py_file in sorted(models_dir.glob('*.py')):
                rel = str(py_file.relative_to(artifacts_dir))
                source = _read(py_file)
                if 'APIRouter' in source or re.search(r'@router\.(get|post|put|delete|patch)\s*\(', source):
                    add_defect(
                        rel,
                        'Model file contains route/router code (APIRouter or @router.* decorator)',
                        'HIGH',
                        'Move route handlers to business/backend/routes/*.py and keep models/*.py as SQLAlchemy models only'
                    )

        if routes_dir.exists():
            for py_file in sorted(routes_dir.glob('*.py')):
                rel = str(py_file.relative_to(artifacts_dir))
                source = _read(py_file)
                has_route = bool(re.search(r'@router\.(get|post|put|delete|patch)\s*\(', source))
                if has_route:
                    continue
                # Detect Flask Blueprint pattern — escalate to HIGH with exact fix
                is_flask = bool(re.search(r'from flask import|Blueprint\(|@router\.route\(', source))
                if is_flask:
                    add_defect(
                        rel,
                        'FLASK BLUEPRINT DETECTED — this is a FastAPI project. '
                        'Replace: `from flask import Blueprint` → `from fastapi import APIRouter`. '
                        'Replace: `router = Blueprint(...)` → `router = APIRouter()`. '
                        'Replace: `@router.route(\'/path\', methods=[\'GET\'])` → `@router.get(\'/path\')`. '
                        'All endpoints must use @router.get / @router.post / @router.put / @router.delete.',
                        'HIGH',
                        'Convert entire file to FastAPI APIRouter pattern. '
                        'Import: `from fastapi import APIRouter, Depends, HTTPException`. '
                        'Import: `from sqlalchemy.orm import Session`. '
                        'Import: `from core.database import get_db`. '
                        'Import: `from core.rbac import get_current_user`. '
                        'Declare: `router = APIRouter()`. '
                        'Every endpoint: `@router.get("/path") async def fn(db=Depends(get_db), current_user=Depends(get_current_user)):`'
                    )
                    continue
                # Allow explicit scope-boundary stubs (comment-only route file)
                scope_stub = (
                    'not in scope' in source.lower()
                    or 'per intake requirements' in source.lower()
                    or 'out of scope' in source.lower()
                )
                non_comment_code = [
                    ln for ln in source.splitlines()
                    if ln.strip() and not ln.lstrip().startswith('#')
                ]
                if non_comment_code and not scope_stub:
                    add_defect(
                        rel,
                        'Route file has executable code but defines no @router endpoints',
                        'MEDIUM',
                        'Define route decorators in this file or move non-route code to the correct layer'
                    )

        # ── CHECK 8: Frontend config-file mismatch ───────────────────────────
        frontend_dir = artifacts_dir / 'business' / 'frontend'
        if frontend_dir.exists():
            next_cfg = frontend_dir / 'next.config.js'
            postcss_cfg = frontend_dir / 'postcss.config.js'
            tailwind_cfgs = [frontend_dir / 'tailwind.config.js', frontend_dir / 'tailwind.config.ts']

            if next_cfg.exists() and next_cfg.name not in BOILERPLATE_OWNED_FRONTEND_CONFIGS:
                s = _read(next_cfg)
                if 'compilerOptions' in s:
                    add_defect(
                        str(next_cfg.relative_to(artifacts_dir)),
                        'next.config.js appears to contain tsconfig content (compilerOptions)',
                        'HIGH',
                        'Replace with valid Next.js config object (module.exports = { ... })'
                    )
            if postcss_cfg.exists() and postcss_cfg.name not in BOILERPLATE_OWNED_FRONTEND_CONFIGS:
                s = _read(postcss_cfg)
                if 'rewrites()' in s or 'destination:' in s or 'nextConfig' in s:
                    add_defect(
                        str(postcss_cfg.relative_to(artifacts_dir)),
                        'postcss.config.js appears to contain Next.js config content',
                        'HIGH',
                        'Replace with PostCSS plugin config: module.exports = { plugins: { tailwindcss: {}, autoprefixer: {} } }'
                    )
            for cfg in tailwind_cfgs:
                if not cfg.exists():
                    continue
                if cfg.name in BOILERPLATE_OWNED_FRONTEND_CONFIGS:
                    # Boilerplate owns this file — pruner will delete it; no point flagging content
                    continue
                s = _read(cfg)
                if not re.search(r'\bcontent\s*:', s):
                    add_defect(
                        str(cfg.relative_to(artifacts_dir)),
                        'Tailwind config is missing `content:` paths (likely swapped/invalid config file)',
                        'HIGH',
                        'Add proper Tailwind config with `content` globs and theme/plugins sections'
                    )

        # ── CHECK 9: Local import integrity (module/symbol/case) ────────────
        module_ast = {rel: parsed_ast.get(rel) for rel in parsed_ast.keys()}
        module_exports = {rel: _gather_exported_symbols(tree) for rel, tree in module_ast.items() if tree}

        for rel, tree in module_ast.items():
            if not tree:
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.ImportFrom) or not node.module:
                    continue
                mod = node.module
                if not mod.startswith('business.'):
                    continue
                expected_rel = _module_rel_from_business_module(mod)
                expected_path = artifacts_dir / expected_rel
                if not expected_path.exists():
                    add_defect(
                        rel,
                        f'Local import module `{mod}` does not resolve to `{expected_rel}` in artifacts',
                        'HIGH',
                        f'Create `{expected_rel}` or fix the import path in `{rel}`'
                    )
                    continue
                # case-sensitive enforcement for Linux deploy targets
                if not _exists_case_sensitive(artifacts_dir, expected_rel.split('/')):
                    add_defect(
                        rel,
                        f'Case-sensitive import mismatch for `{mod}` (path casing differs from filesystem)',
                        'HIGH',
                        f'Align import casing exactly with filesystem path `{expected_rel}`'
                    )
                exported = module_exports.get(expected_rel, set())
                for alias in node.names:
                    sym = alias.name
                    if sym == '*':
                        continue
                    if sym not in exported:
                        add_defect(
                            rel,
                            f'Import `{sym}` not defined in `{expected_rel}`',
                            'HIGH',
                            f'Define `{sym}` in `{expected_rel}` or correct the import in `{rel}`'
                        )

        # ── CHECK 10: Route↔service contract sanity ──────────────────────────
        class_meta = {}  # class_name -> (rel, init_min, init_max, methods:set, is_orm_model)
        for rel, tree in module_ast.items():
            if not tree:
                continue
            for node in getattr(tree, 'body', []):
                if not isinstance(node, ast.ClassDef):
                    continue
                init_min = 0
                init_max = 0
                methods = set()
                # SQLAlchemy models have dynamic constructors; static arity/method checks
                # here create false positives, so mark and skip them later.
                has_tablename = any(
                    isinstance(item, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == '__tablename__' for t in item.targets)
                    for item in node.body
                )
                base_names = []
                for base in node.bases:
                    if isinstance(base, ast.Name):
                        base_names.append(base.id)
                    elif isinstance(base, ast.Attribute):
                        base_names.append(base.attr)
                inherits_orm_base = ('Base' in base_names or 'TenantMixin' in base_names)
                is_orm_model = has_tablename or inherits_orm_base
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        methods.add(item.name)
                        if item.name == '__init__':
                            args = item.args.args[1:]  # drop self
                            defaults = item.args.defaults or []
                            init_max = len(args)
                            init_min = len(args) - len(defaults)
                class_meta[node.name] = (rel, init_min, init_max, methods, is_orm_model)

        if routes_dir.exists():
            for py_file in sorted(routes_dir.glob('*.py')):
                rel = str(py_file.relative_to(artifacts_dir))
                source = _read(py_file)
                # var = ClassName(...)
                for m in re.finditer(r'(\w+)\s*=\s*(\w+)\(([^)]*)\)', source):
                    var_name, class_name, args_raw = m.group(1), m.group(2), m.group(3).strip()
                    if class_name not in class_meta:
                        continue
                    _, init_min, init_max, methods, is_orm_model = class_meta[class_name]
                    if is_orm_model:
                        continue
                    arg_count = 0 if not args_raw else len([a for a in args_raw.split(',') if a.strip()])
                    if arg_count < init_min or arg_count > init_max:
                        add_defect(
                            rel,
                            f'Constructor call `{class_name}({args_raw})` does not match `__init__` arity '
                            f'({init_min}..{init_max})',
                            'HIGH',
                            f'Fix constructor call or `__init__` signature for class `{class_name}`'
                        )
                    # var.method(...)
                    service_file = class_meta[class_name][0]  # file that defines this class
                    for mm in re.finditer(rf'{re.escape(var_name)}\.(\w+)\s*\(', source):
                        meth = mm.group(1)
                        if meth not in methods:
                            add_defect(
                                rel,
                                f'Call to missing method `{class_name}.{meth}()`',
                                'HIGH',
                                f'Implement `{meth}()` on `{class_name}` or change route call to an existing method',
                                related_files=[service_file]  # Fix 2: include service file as joint target
                            )

        # ── CHECK 11: Intake-aware KPI contract (optional) ───────────────────
        if intake_data:
            try:
                kpi_keys = {
                    'kpi_definitions', 'kpis', 'key_metrics', 'metrics',
                    'kpi_ids', 'kpi_list'
                }
                raw_kpi_blocks = _collect_values_for_keys(intake_data, kpi_keys)

                kpi_ids = set()
                for block in raw_kpi_blocks:
                    if isinstance(block, str):
                        if block.strip():
                            kpi_ids.add(block.strip())
                    elif isinstance(block, dict):
                        for key_name in ('kpi_id', 'id', 'name', 'metric', 'metric_id', 'code'):
                            val = block.get(key_name)
                            if isinstance(val, str) and val.strip():
                                kpi_ids.add(val.strip())
                    elif isinstance(block, list):
                        for item in block:
                            if isinstance(item, str) and item.strip():
                                kpi_ids.add(item.strip())
                            elif isinstance(item, dict):
                                for key_name in ('kpi_id', 'id', 'name', 'metric', 'metric_id', 'code'):
                                    val = item.get(key_name)
                                    if isinstance(val, str) and val.strip():
                                        kpi_ids.add(val.strip())

                # Keep likely metric IDs/names; drop noisy long free-text entries.
                kpi_ids = {k for k in kpi_ids if 1 <= len(k) <= 64}

                if kpi_ids:
                    service_files = sorted((artifacts_dir / 'business' / 'services').glob('*.py'))
                    service_text_by_file = {
                        str(p.relative_to(artifacts_dir)): _read(p).lower()
                        for p in service_files
                    }
                    for kid in sorted(kpi_ids):
                        kid_l = kid.lower()
                        hit_files = [
                            rel_name for rel_name, txt in service_text_by_file.items()
                            if kid_l in txt
                        ]
                        if not hit_files:
                            add_defect(
                                'business/services',
                                f'Intake KPI `{kid}` is not represented in business/services KPI logic',
                                'HIGH',
                                f'Implement KPI `{kid}` calculation path in the canonical KPI service'
                            )
                        elif len(hit_files) > 1:
                            add_defect(
                                'business/services',
                                f'KPI `{kid}` appears in multiple services: {", ".join(hit_files)}',
                                'MEDIUM',
                                'Consolidate KPI calculation into one canonical service to avoid drift'
                            )
            except Exception:
                pass

        # ── CHECK 12: Intake-aware downloadable-report contract (optional) ───
        if intake_data:
            try:
                intake_blob = json.dumps(intake_data, ensure_ascii=False).lower()
                requires_download = any(sig in intake_blob for sig in (
                    'downloadable', 'download report', 'export report', 'pdf report', 'export', 'download'
                ))
                if requires_download:
                    route_files = sorted((artifacts_dir / 'business' / 'backend' / 'routes').glob('*.py'))
                    has_download = False
                    for rf in route_files:
                        src = _read(rf).lower()
                        has_route = bool(re.search(r'@router\.(get|post|put|delete|patch)\s*\(', src))
                        has_download_marker = any(token in src for token in (
                            'fileresponse', 'streamingresponse', '/download', '/export',
                            'bytesio', '.pdf', 'attachment', 'download', 'export'
                        ))
                        if has_route and has_download_marker:
                            has_download = True
                            break
                    if not has_download:
                        add_defect(
                            'business/backend/routes',
                            'Intake indicates downloadable/exportable output, but no download/export endpoint detected in backend routes',
                            'HIGH',
                            'Add a route that returns FileResponse/StreamingResponse (or equivalent) for report export/download'
                        )
            except Exception:
                pass

        # ── CHECK 13: Missing frontend pages (boilerplate mode) ──────────────
        # If Claude generated backend routes but zero business/frontend/pages/*.jsx
        # files, the dashboard is empty — always a HIGH defect in boilerplate mode.
        routes_dir_bp = artifacts_dir / 'business' / 'backend' / 'routes'
        frontend_pages_dir = artifacts_dir / 'business' / 'frontend' / 'pages'
        has_backend_routes = routes_dir_bp.exists() and bool(list(routes_dir_bp.glob('*.py')))
        jsx_files = list(frontend_pages_dir.glob('*.jsx')) if frontend_pages_dir.exists() else []
        if has_backend_routes and not jsx_files:
            add_defect(
                'business/frontend/pages',
                'No frontend pages found: business/frontend/pages/*.jsx is empty but backend routes exist. '
                'The boilerplate dashboard will be blank.',
                'HIGH',
                'Create at least one business/frontend/pages/<Feature>.jsx React page for each user-facing '
                'feature. Use: const { user, getAccessTokenSilently } = useAuth0() and import api from '
                "'../utils/api'. Every frontend feature MUST have a corresponding .jsx page."
            )

        return defects

    @staticmethod
    def _run_compile_gate(artifacts_dir: Path) -> list:
        """
        Mandatory Gate 0 compile checks (runs before Feature QA).

        - Python compile check for all business/**/*.py via py_compile
        - Frontend build check via npm run build when business/frontend/package.json exists
        """
        import py_compile
        import subprocess

        defects = []
        counter = [0]

        def add_defect(file_path, issue, severity, fix):
            counter[0] += 1
            defects.append({
                'id': f'COMPILE-{counter[0]}',
                'file': file_path,
                'issue': issue,
                'severity': severity,
                'fix': fix
            })

        # Python compile checks
        for py_file in sorted((artifacts_dir / 'business').rglob('*.py')):
            rel = str(py_file.relative_to(artifacts_dir))
            try:
                py_compile.compile(str(py_file), doraise=True)
            except py_compile.PyCompileError as e:
                add_defect(
                    rel,
                    f'Python compile failed: {e.msg}',
                    'HIGH',
                    'Fix Python syntax/indentation/runtime-compile issues in this file'
                )

        # Frontend build check
        frontend_dir = artifacts_dir / 'business' / 'frontend'
        pkg = frontend_dir / 'package.json'
        if pkg.exists():
            npm_check = subprocess.run(
                ['bash', '-lc', 'command -v npm'],
                capture_output=True, text=True
            )
            if npm_check.returncode != 0:
                add_defect(
                    'business/frontend/package.json',
                    'npm is not available in environment; frontend build compile check could not run',
                    'HIGH',
                    'Install Node/npm in runtime environment or disable frontend artifacts for this build profile'
                )
            else:
                # Install deps before building (generated artifacts have no node_modules)
                subprocess.run(
                    ['bash', '-lc', 'npm install --prefer-offline --silent'],
                    cwd=str(frontend_dir),
                    capture_output=True,
                    text=True
                )
                build_cmd = 'npm run build'
                build = subprocess.run(
                    ['bash', '-lc', build_cmd],
                    cwd=str(frontend_dir),
                    capture_output=True,
                    text=True
                )
                if build.returncode != 0:
                    tail = (build.stderr or build.stdout or '').splitlines()[-20:]
                    tail_text = '\n'.join(tail)
                    add_defect(
                        'business/frontend',
                        f'Frontend compile/build failed (npm run build). Last lines:\n{tail_text}',
                        'HIGH',
                        'Fix frontend compile/build errors and ensure configs/dependencies are valid'
                    )

        return defects

    @staticmethod
    def _format_static_defects_for_claude(defects: list) -> str:
        """
        Format static defects list into a structured block for Claude's static fix prompt.
        """
        if not defects:
            return "(no static defects)"
        lines = []
        lines.append(
            "SCOPE LOCK (NON-NEGOTIABLE): Fix ONLY the defects listed below. "
            "Do NOT refactor, rename, or add features beyond these fixes."
        )
        lines.append("")
        for d in defects:
            lines.append(
                f"STATIC-{d['id'].replace('STATIC-', '')}: [{d['severity']}] {d['file']}\n"
                f"  Issue: {d['issue']}\n"
                f"  Fix: {d['fix']}"
            )
        return "\n\n".join(lines)

    @staticmethod
    def _parse_consistency_report(output: str) -> list:
        """
        Parse CONSISTENCY REPORT output from Claude into list of issue dicts.
        Each dict has: id, files, file (first file), evidence, issue, fix, severity.
        """
        issues = []
        blocks = re.split(r'(?=ISSUE-\d+:)', output)
        for block in blocks:
            if not block.strip().startswith('ISSUE-'):
                continue
            issue = {'id': '', 'type': '', 'files': '', 'file': '', 'evidence': '', 'issue': '', 'fix': '', 'severity': 'MEDIUM'}
            m = re.match(r'(ISSUE-\d+):\s*\[([A-Z_]+)\]', block)
            if m:
                issue['id'] = m.group(1)
                issue['type'] = m.group(2)
            else:
                m2 = re.match(r'(ISSUE-\d+):', block)
                if m2:
                    issue['id'] = m2.group(1)
            for field, pattern in [
                ('files',     r'Files:\s*(.+)'),
                ('evidence',  r'Evidence:\s*(.+)'),
                ('issue',     r'Problem:\s*(.+)'),
                ('fix',       r'Fix:\s*(.+)'),
                ('severity',  r'Severity:\s*(HIGH|MEDIUM|LOW)'),
            ]:
                fm = re.search(pattern, block, re.IGNORECASE)
                if fm:
                    issue[field] = fm.group(1).strip()
            # Extract primary file from "files" field
            files_str = issue.get('files', '')
            primary = re.split(r'[<>\-,\s]+', files_str)[0].strip() if files_str else ''
            issue['file'] = primary
            if issue['id']:
                issues.append(issue)
        return issues

    @staticmethod
    def _format_consistency_defects_for_claude(issues: list) -> str:
        """
        Format consistency issue list into a structured block for Claude's static_fix_prompt.
        Reuses the same targeted-patch prompt; the defect text drives what to fix.
        """
        if not issues:
            return "(no consistency issues)"
        lines = []
        lines.append(
            "SCOPE LOCK (NON-NEGOTIABLE): Fix ONLY the defects listed below. "
            "Do NOT refactor, rename, or add features beyond these fixes."
        )
        lines.append("")
        for iss in issues:
            lines.append(
                f"{iss['id']}: [{iss.get('severity', 'MEDIUM')}] {iss.get('files', iss.get('file', 'unknown'))}\n"
                f"  Evidence: {iss.get('evidence', 'N/A')}\n"
                f"  Issue: {iss.get('issue', 'N/A')}\n"
                f"  Fix: {iss.get('fix', 'N/A')}"
            )
        return "\n\n".join(lines)

    @staticmethod
    def _prioritize_and_cap_defects(defects: list, max_defects: int = Config.MAX_DEFECTS_PER_ITERATION) -> list:
        """
        Cap iteration defect load and prioritize highest-impact fixes first.
        Priority: severity (HIGH->MEDIUM->LOW), then runtime/contract/import blockers.
        """
        if not defects or max_defects <= 0:
            return defects or []

        severity_rank = {'HIGH': 0, 'MEDIUM': 1, 'LOW': 2}
        critical_markers = (
            'syntax', 'compile', 'import', 'module', 'does not resolve', 'not defined',
            'constructor', '__init__', 'missing method', 'route', 'schema', 'model',
            'fileresponse', 'streamingresponse'
        )

        def _score(d: dict):
            sev = str(d.get('severity', 'MEDIUM')).upper()
            sev_score = severity_rank.get(sev, 3)
            issue_text = str(d.get('issue', '')).lower()
            fix_text = str(d.get('fix', '')).lower()
            has_critical = any(m in issue_text or m in fix_text for m in critical_markers)
            crit_score = 0 if has_critical else 1
            file_name = str(d.get('file', ''))
            return (sev_score, crit_score, file_name)

        prioritized = sorted(defects, key=_score)
        return prioritized[:max_defects]

    # ── Integration fast gate (Improvement 5) ────────────────────────────────────
    def _run_integration_fast_gate(self, iteration: int) -> list:
        """
        Run integration_check.py --fast (checks 1, 2, 4, 6, 7) on the current iteration's
        artifacts. Returns list of issues dicts (harness-compatible), or [] on PASS.
        Called between STATIC and CONSISTENCY in the main loop to catch structural failures
        before spending AI gate tokens on broken code.
        """
        import subprocess, json as _json, tempfile

        artifacts_dir = self.artifacts.build_dir / f'iteration_{iteration:02d}_artifacts'
        if not artifacts_dir.is_dir():
            print_warning(f"  [INTEGRATION_FAST] Artifacts dir not found: {artifacts_dir}")
            return []

        intake_path = getattr(self, 'intake_file', None)
        if not intake_path or not Path(intake_path).exists():
            print_warning("  [INTEGRATION_FAST] No intake path available — skipping fast check")
            return []

        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as tmp:
            output_path = tmp.name

        try:
            result = subprocess.run(
                [
                    'python3', 'integration_check.py',
                    '--artifacts', str(artifacts_dir),
                    '--intake', str(intake_path),
                    '--output', output_path,
                    '--fast',
                ],
                capture_output=True, text=True, timeout=60,
                cwd=str(Path(__file__).parent)
            )
            try:
                with open(output_path) as f:
                    data = _json.load(f)
            except Exception:
                print_warning("  [INTEGRATION_FAST] Could not parse output JSON — skipping")
                return []

            issues = data.get('issues', [])
            verdict = data.get('verdict', 'INTEGRATION_PASS')
            if verdict == 'INTEGRATION_PASS':
                return []
            high = sum(1 for i in issues if i.get('severity') == 'HIGH')
            print_warning(f"  [INTEGRATION_FAST] {len(issues)} issue(s) found ({high} HIGH)")
            for iss in issues:
                sev_fn = print_error if iss.get('severity') == 'HIGH' else print_warning
                sev_fn(f"    {iss['id']} [{iss['severity']}] {iss.get('file','?')}: {iss.get('evidence','')[:100]}")
            return issues
        except subprocess.TimeoutExpired:
            print_warning("  [INTEGRATION_FAST] Timed out — skipping")
            return []
        except Exception as e:
            print_warning(f"  [INTEGRATION_FAST] Error: {e} — skipping")
            return []
        finally:
            import os
            try:
                os.unlink(output_path)
            except Exception:
                pass

    # ── Artifact filtering per gate ──────────────────────────────────────────────
    # CONSISTENCY only needs backend structural files — frontend/config are noise for this check.
    # QUALITY and FEATURE_QA need all business/ files but not generated doc/env files.
    GATE_FILE_FILTERS = {
        "CONSISTENCY": [
            "business/models/",
            "business/services/",
            "business/routes/",
            "business/schemas/",
        ],
        "QUALITY":     ["business/"],
        "FEATURE_QA":  ["business/"],
    }
    GATE_FILE_EXCLUDES = {
        "CONSISTENCY": [],
        "QUALITY":     ["business/README-INTEGRATION.md", ".env.example", ".gitignore"],
        "FEATURE_QA":  ["business/README-INTEGRATION.md", ".env.example", ".gitignore"],
    }

    @staticmethod
    def filter_artifacts_for_gate(all_artifacts: dict, gate_name: str) -> dict:
        """
        Return only the artifact files relevant to the given gate.
        all_artifacts: {rel_path: content}
        gate_name: "CONSISTENCY" | "QUALITY" | "FEATURE_QA"
        Falls back to full artifact set if filtered set is empty (e.g. no models/ yet).
        """
        includes = FOHarness.GATE_FILE_FILTERS.get(gate_name, [])
        excludes = FOHarness.GATE_FILE_EXCLUDES.get(gate_name, [])
        filtered = {
            path: content
            for path, content in all_artifacts.items()
            if any(path.startswith(inc) for inc in includes)
            and not any(path == exc or path.endswith('/' + exc.lstrip('/')) for exc in excludes)
        }
        if not filtered:
            return all_artifacts  # fallback: pass everything, log handled by caller
        return filtered

    def _run_ai_consistency_check(self, iteration: int, governance_section: str) -> list:
        """
        Call ChatGPT to check cross-file consistency of business/ artifacts.
        Returns list of issue dicts (from _parse_consistency_report), or [] on PASS.
        """
        artifacts_dir = self.artifacts.build_dir / f'iteration_{iteration:02d}_artifacts'
        if not artifacts_dir.is_dir():
            print_warning(f"  [CONSISTENCY] Artifacts dir not found: {artifacts_dir}")
            return []

        # Collect all business/ files
        file_contents = {}
        for path in sorted(artifacts_dir.rglob('*')):
            if not path.is_file():
                continue
            rel_str = str(path.relative_to(artifacts_dir))
            if not rel_str.startswith('business/'):
                continue
            # Skip binary / very large files
            try:
                text = path.read_text(encoding='utf-8', errors='replace')
                file_contents[rel_str] = text
            except Exception:
                pass

        if not file_contents:
            print_warning("  [CONSISTENCY] No business/ files found — skipping check")
            return []

        # Apply gate-specific artifact filter (models/services/routes/schemas only)
        all_count = len(file_contents)
        file_contents = FOHarness.filter_artifacts_for_gate(file_contents, "CONSISTENCY")
        if len(file_contents) == all_count:
            print_info(f"  [CONSISTENCY] Artifact filter fallback — no structural files found, sending all {all_count} file(s)")
        else:
            print_info(f"  [CONSISTENCY] Sending {len(file_contents)} file(s) (filtered from {all_count} total — models/services/routes/schemas only)")
        prompt = PromptTemplates.ai_consistency_prompt(file_contents)
        self.artifacts.save_log(f'iteration_{iteration:02d}_consistency_prompt', prompt)

        try:
            resp = self.chatgpt.call(
                prompt,
                max_tokens=4096,
            )
            output = resp.get('choices', [{}])[0].get('message', {}).get('content', '')
            self.artifacts.save_log(f'iteration_{iteration:02d}_consistency_output', output)

            usage = resp.get('usage', {})
            in_tok  = usage.get('prompt_tokens', 0)
            out_tok = usage.get('completion_tokens', 0)
            cost = (in_tok / 1_000_000) * 2.50 + (out_tok / 1_000_000) * 10.00
            print_info(f"  [CONSISTENCY] ChatGPT responded (${cost:.4f})")
            cached_tokens = usage.get('prompt_tokens_details', {}).get('cached_tokens', 0) or 0
            print_info(f'CACHE CHECK [CONSISTENCY] iteration {iteration}: cached={cached_tokens} / total_prompt={in_tok} ({int(cached_tokens/in_tok*100) if in_tok else 0}% cached)')
        except Exception as e:
            print_error(f"  [CONSISTENCY] ChatGPT call failed: {e}")
            return []

        if 'CONSISTENCY CHECK: PASS' in output:
            return []

        issues = self._parse_consistency_report(output)

        # Filter false-positive consistency issues.
        # The consistency AI hallucinates field-missing defects for fields that ARE present,
        # and flags non-verifiable concerns (duplicate code, vague URL integrity, import style).
        # Strategy: extract the first quoted token from evidence and check it against file content.
        _UNVERIFIABLE_ISSUE_TYPES = {
            'DUPLICATE_SUBSYSTEM', 'DUPLICATE_CODE', 'CODE_DUPLICATION',
            'FRONTEND_URL', 'ROUTE_INTEGRITY', 'URL_INTEGRITY',
        }
        verified = []
        for issue in issues:
            iid = issue.get('id', '?')
            raw_evidence = issue.get('evidence', '').strip()

            # Drop issues with no concrete file targets — "N/A <-> N/A" or empty files field.
            # These are always fabrications: CONSISTENCY cannot identify a cross-file mismatch
            # without naming both files.
            files_val = issue.get('files', '').strip()
            if not files_val or files_val.upper() in ('N/A', 'N/A <-> N/A', 'NONE', 'UNKNOWN'):
                print_info(f"  [CONSISTENCY] Filtered no-file {iid}: no concrete files named — unverifiable")
                continue

            # Drop issue types that are quality opinions, not verifiable cross-file assertions.
            # Check the parsed [TYPE] header first, then fall back to scanning problem + evidence text.
            issue_type = issue.get('type', '').upper()
            issue_text = issue.get('issue', '') + raw_evidence
            if issue_type in _UNVERIFIABLE_ISSUE_TYPES or any(t in issue_text.upper() for t in _UNVERIFIABLE_ISSUE_TYPES):
                print_info(f"  [CONSISTENCY] Filtered non-verifiable {iid} [{issue_type}]: quality opinion, not a runtime assertion")
                continue

            # Extract the first quoted token from evidence (handles "field_name ..." or "field_name")
            quoted_match = re.search(r'"([^"]{1,60})"', raw_evidence)
            if quoted_match:
                evidence_token = quoted_match.group(1).strip()
            else:
                # No quoted token — if it's a known unverifiable type skip, otherwise keep
                verified.append(issue)
                continue

            if not evidence_token:
                verified.append(issue)
                continue

            # The "token found in file → AI hallucinated missing-field" logic ONLY applies to
            # FIELD_MISMATCH issues. For BROKEN_IMPORT, finding the wrong import string confirms
            # the defect is real (opposite direction). All other types: keep as-is.
            _FIELD_MISMATCH_TYPES = {'FIELD_MISMATCH', 'SCHEMA_FIELD_MISMATCH', 'MODEL_FIELD_MISMATCH'}
            if issue_type not in _FIELD_MISMATCH_TYPES:
                verified.append(issue)
                continue

            files_str = issue.get('files', '')
            involved_files = re.findall(r'business/\S+\.py', files_str)
            if not involved_files:
                verified.append(issue)
                continue

            found_in_any = any(evidence_token in file_contents.get(fp, '') for fp in involved_files)
            if found_in_any:
                print_info(f"  [CONSISTENCY] Filtered false positive {iid}: "
                           f"'{evidence_token}' confirmed present in artifact — AI hallucinated missing-field defect")
            else:
                verified.append(issue)
        issues = verified

        return issues

    @staticmethod
    def _run_ai_consistency_check_standalone(artifacts_dir: Path, claude_client) -> list:
        """
        Standalone version for --ai-check CLI mode (no full FOHarness required).
        Reads business/ files directly from artifacts_dir, calls Claude, returns issues.
        """
        file_contents = {}
        for path in sorted(artifacts_dir.rglob('*')):
            if not path.is_file():
                continue
            rel_str = str(path.relative_to(artifacts_dir))
            if not rel_str.startswith('business/'):
                continue
            try:
                file_contents[rel_str] = path.read_text(encoding='utf-8', errors='replace')
            except Exception:
                pass

        if not file_contents:
            return []

        prompt = PromptTemplates.ai_consistency_prompt(file_contents)
        try:
            resp = claude_client.call(prompt, max_tokens=4096)
            output = resp['content'][0]['text']
        except Exception as e:
            print_error(f"  [CONSISTENCY] Claude call failed: {e}")
            return []

        if 'CONSISTENCY CHECK: PASS' in output:
            return []
        return FOHarness._parse_consistency_report(output)

    def _run_quality_gate(self, iteration: int) -> Tuple[list, dict]:
        """
        Optional Gate 4 (OFF by default): quality evaluation via ChatGPT.
        Dimensions:
          - Completeness vs intake
          - Code quality
          - Enhanceability
          - Deployability

        Returns:
          (issues, usage_stats)
          issues: [] when PASS, else parsed ISSUE-* list (same schema as consistency parser).
          usage_stats: {'input_tokens': int, 'output_tokens': int}
        """
        artifacts_dir = self.artifacts.build_dir / f'iteration_{iteration:02d}_artifacts'
        usage_stats = {'input_tokens': 0, 'output_tokens': 0}

        if not artifacts_dir.is_dir():
            print_warning(f"  [QUALITY] Artifacts dir not found: {artifacts_dir}")
            return [], usage_stats

        file_contents = {}
        for path in sorted(artifacts_dir.rglob('*')):
            if not path.is_file():
                continue
            rel_str = str(path.relative_to(artifacts_dir))
            if not rel_str.startswith('business/'):
                continue
            try:
                file_contents[rel_str] = path.read_text(encoding='utf-8', errors='replace')
            except Exception:
                pass

        if not file_contents:
            print_warning("  [QUALITY] No business/ files found — skipping quality gate")
            return [], usage_stats

        # Apply gate-specific artifact filter (all business/ minus generated doc/env files)
        all_count = len(file_contents)
        file_contents = FOHarness.filter_artifacts_for_gate(file_contents, "QUALITY")
        print_info(f"  [QUALITY] Evaluating {len(file_contents)} artifact(s) (filtered from {all_count} total) across 4 quality dimensions...")
        prompt = PromptTemplates.quality_gate_prompt(file_contents, self.intake_data)
        self.artifacts.save_log(f'iteration_{iteration:02d}_quality_prompt', prompt)

        try:
            resp = self.chatgpt.call(prompt, max_tokens=8192)
            output = resp['choices'][0]['message']['content']
            self.artifacts.save_log(f'iteration_{iteration:02d}_quality_output', output)
            usage = resp.get('usage', {})
            usage_stats['input_tokens'] = int(usage.get('prompt_tokens', 0) or 0)
            usage_stats['output_tokens'] = int(usage.get('completion_tokens', 0) or 0)
            cost = (usage_stats['input_tokens'] / 1_000_000) * 2.50 + (usage_stats['output_tokens'] / 1_000_000) * 10.00
            print_info(f"  [QUALITY] ChatGPT responded (${cost:.4f})")
            _quality_cached = usage.get('prompt_tokens_details', {}).get('cached_tokens', 0) or 0
            print_info(f'CACHE CHECK [QUALITY] iteration {iteration}: cached={_quality_cached} / total_prompt={usage_stats["input_tokens"]} ({int(_quality_cached/usage_stats["input_tokens"]*100) if usage_stats["input_tokens"] else 0}% cached)')
        except Exception as e:
            print_error(f"  [QUALITY] ChatGPT call failed: {e}")
            return [], usage_stats

        if 'QUALITY GATE: PASS' in output:
            return [], usage_stats

        # Acceptable-low policy:
        # Gate passes when Completeness, Code Quality, and Deployability are PASS or LOW.
        # (Enhanceability can still be reported for visibility without blocking.)
        dim_map = {}
        for m in re.finditer(
            r'DIMENSION-\d+:\s*([A-Z_]+)\s*=\s*(PASS|LOW|FAIL)',
            output,
            re.IGNORECASE
        ):
            key = m.group(1).strip().upper()
            val = m.group(2).strip().upper()
            dim_map[key] = val

        _c = dim_map.get('COMPLETENESS_VS_INTAKE')
        _q = dim_map.get('CODE_QUALITY')
        _d = dim_map.get('DEPLOYABILITY')
        if self.factory_mode:
            # Factory mode: only DEPLOYABILITY=FAIL blocks the gate
            if _d != 'FAIL':
                print_info("  [QUALITY] Factory mode — DEPLOYABILITY not FAIL, treating gate as PASS")
                return [], usage_stats
            print_warning(f"  [QUALITY] Factory mode — DEPLOYABILITY=FAIL, blocking")
        elif _c in ('PASS', 'LOW') and _q in ('PASS', 'LOW') and _d in ('PASS', 'LOW'):
            print_info("  [QUALITY] LOW accepted for Completeness/Code Quality/Deployability — treating gate as PASS")
            return [], usage_stats

        # Reuse consistency parser/formatter shape: ISSUE-N with Files/Problem/Fix/Severity
        issues = self._parse_consistency_report(output)
        return issues, usage_stats

    def execute_build_qa_loop(self) -> Tuple[bool, str]:
        """
        Execute BUILD → QA loop until QA accepts or max iterations hit.

        Returns (success: bool, final_build_output: str)
        """
        print_header(f"STARTING BUILD → QA LOOP (BLOCK_{self.block})")

        iteration        = 1
        previous_defects = None
        recurring_tracker  = {}   # (location, classification) → {count, last_problem, last_fix}
        prohibitions_block = ''   # accumulated prohibition text, injected into every patch prompt
        resolved_tracker   = {}   # (location, classification) → {iteration_resolved, fix_summary}
        pending_resolution = set() # defects Claude claimed FIXED; awaiting QA confirmation
        build_output     = None

        # Unified QA loop state: tracks which check drove the last rejection
        # 'compile' → mandatory Gate 0 compile check | 'qa' → Feature QA (ChatGPT)
        # 'static' → deterministic checks | 'consistency' → AI cross-file check
        # 'quality' → mandatory quality gate
        defect_source        = 'qa'
        _raw_pending_defects = []   # raw defect list for static/consistency/quality (for file target extraction)
        _qa_accepted_at_iter = None # set when Feature QA first accepts; enables polish even on static/consistency max-iter exit
        _loop_success        = False

        # FIX #1: Track cumulative usage for final cost summary (Claude)
        total_calls = 0
        total_cache_writes = 0
        total_cache_hits = 0
        total_cache_read_tokens = 0
        total_cache_write_tokens = 0
        total_input_tokens = 0
        total_output_tokens = 0

        # Track ChatGPT usage for cost analysis
        total_gpt_calls = 0
        total_gpt_input_tokens = 0
        total_gpt_output_tokens = 0

        # Convergence tracking: detect when defects aren't decreasing
        defect_history = []  # Track defect count per iteration
        convergence_check_after = 10  # Check convergence after this many iterations

        # ── Circuit Breaker (Steal 1.1) ──────────────────────────
        # Three independent detectors; any one triggers a halt.
        # Detector A: No file changes for N consecutive iterations (stagnation)
        # Detector B: Same defect fingerprint appears N consecutive times (oscillation)
        # Detector C: Total artifact bytes drop below threshold (degradation)
        CB_NO_CHANGE_THRESHOLD   = 3   # halt after 3 iterations with identical artifacts
        CB_SAME_DEFECT_THRESHOLD = 5   # halt after same defect fingerprint 5 times
        CB_DEGRADATION_RATIO     = 0.3 # halt if output drops below 30% of previous

        _cb_prev_manifest_hash  = None   # hash of sorted (file, checksum) pairs
        _cb_no_change_count     = 0
        _cb_defect_fingerprints = {}     # fingerprint_str → consecutive_count
        _cb_prev_byte_count     = 0

        def _cb_check(current_manifest: dict, current_defects: list, current_byte_count: int,
                       iter_num: int) -> tuple:
            """
            Run circuit breaker detectors. Returns (tripped: bool, status: str, detail: str).
            Must be called AFTER artifacts are extracted and defects are parsed each iteration.
            Updates nonlocal circuit breaker state.
            """
            nonlocal _cb_prev_manifest_hash, _cb_no_change_count
            nonlocal _cb_defect_fingerprints, _cb_prev_byte_count

            # ── Detector A: Stagnation (no file changes) ──
            manifest_hash = hash(tuple(sorted(current_manifest.items()))) if current_manifest else 0
            if _cb_prev_manifest_hash is not None and manifest_hash == _cb_prev_manifest_hash:
                _cb_no_change_count += 1
            else:
                _cb_no_change_count = 0
            _cb_prev_manifest_hash = manifest_hash

            if _cb_no_change_count >= CB_NO_CHANGE_THRESHOLD:
                return (True, 'CIRCUIT_BREAKER_STAGNATION',
                        f'No file changes for {_cb_no_change_count} consecutive iterations')

            # ── Detector B: Oscillation (same defect repeating) ──
            current_fps = set()
            for d in current_defects:
                # Fingerprint = location + classification (matches recurring_tracker key)
                fp = f"{d.get('location', '')}|{d.get('classification', '')}"
                current_fps.add(fp)

            # Increment count for fingerprints present this iteration
            for fp in current_fps:
                _cb_defect_fingerprints[fp] = _cb_defect_fingerprints.get(fp, 0) + 1

            # Reset count for fingerprints NOT present this iteration
            for fp in list(_cb_defect_fingerprints):
                if fp not in current_fps:
                    _cb_defect_fingerprints[fp] = 0

            stuck = {fp: c for fp, c in _cb_defect_fingerprints.items() if c >= CB_SAME_DEFECT_THRESHOLD}
            if stuck:
                detail_lines = [f'  {fp} ({c}x)' for fp, c in stuck.items()]
                return (True, 'CIRCUIT_BREAKER_OSCILLATION',
                        f'{len(stuck)} defect(s) unfixable after {CB_SAME_DEFECT_THRESHOLD} attempts:\n' +
                        '\n'.join(detail_lines))

            # ── Detector C: Degradation (output size collapsed) ──
            if _cb_prev_byte_count > 0 and current_byte_count > 0:
                ratio = current_byte_count / _cb_prev_byte_count
                if ratio < CB_DEGRADATION_RATIO:
                    return (True, 'CIRCUIT_BREAKER_DEGRADATION',
                            f'Output collapsed to {ratio:.0%} of previous iteration '
                            f'({current_byte_count:,} bytes vs {_cb_prev_byte_count:,} bytes)')
            _cb_prev_byte_count = current_byte_count

            return (False, '', '')

        # FIX #9: Track consecutive validation failures
        consecutive_validation_failures = 0

        # Fix 1/3: Static anti-repetition + hard cap tracking
        _static_consecutive_iters  = 0    # consecutive iterations where static was the only gate failing
        _static_defect_fingerprints = {}  # (file, issue_key) -> consecutive count (Fix 1 escalation)
        _last_static_fingerprints   = set()  # fingerprints from the previous static iteration

        # Consistency hard cap tracking (mirrors Fix 3 for static)
        _consistency_consecutive_iters = 0  # consecutive iterations driven by consistency check alone

        # Defect triage strategy set by _triage_and_sharpen_defects() after Feature QA rejection.
        # 'surgical' → targeted patch (default); 'systemic' → full build with architectural direction
        _triage_strategy = 'surgical'

        # Gate locking — locks persist across iterations; unlock only when relevant files changed.
        # COMPILE and STATIC are never locked (cheap + mandatory).
        gate_locks = {
            "CONSISTENCY": False,
            "QUALITY":     False,
            "FEATURE_QA":  False,
        }
        _prev_artifact_manifest = {}  # checksum dict from prior iteration for files_changed_in_last_fix

        # Repair vs Acceptance mode split.
        # REPAIR MODE  (iterations < acceptance_threshold): skip QUALITY; focused FEATURE_QA via system msg.
        # ACCEPTANCE MODE (iterations >= acceptance_threshold, or early trigger): full QUALITY + full FEATURE_QA.
        # A build cannot be marked accepted unless QUALITY ran explicitly in ACCEPTANCE MODE.
        acceptance_threshold = max(1, self.max_qa_iterations - 2)
        _quality_ran_in_acceptance_mode = False  # must be True before build can be accepted

        REPAIR_MODE_RULES = (
            "REPAIR MODE INSTRUCTIONS:\n"
            "This is a repair iteration, not a final acceptance check.\n"
            "Focus ONLY on:\n"
            "  - IMPLEMENTATION_BUG defects\n"
            "  - SPEC_COMPLIANCE_ISSUE defects for missing required features\n"
            "  - HIGH and MEDIUM severity only\n\n"
            "DO NOT flag in repair mode:\n"
            "  - Enhanceability issues\n"
            "  - Deployability issues (unless they cause a runtime crash)\n"
            "  - Code quality style issues\n"
            "  - LOW severity defects\n"
            "  - SCOPE_CHANGE_REQUEST unless it is causing a CONSISTENCY failure\n"
        )

        def _files_changed_in_last_fix(current_manifest, prev_manifest):
            """Return list of files added, modified, or deleted between two artifact manifests."""
            changed = []
            for path, checksum in current_manifest.items():
                if prev_manifest.get(path) != checksum:
                    changed.append(path)
            for path in prev_manifest:
                if path not in current_manifest:
                    changed.append(path)
            return changed

        def _load_iteration_manifest(iter_num):
            """Load artifact manifest for a given iteration number, return {} on miss."""
            manifest_path = self.artifacts.build_dir / f'iteration_{iter_num:02d}_artifacts' / 'artifact_manifest.json'
            if manifest_path.exists():
                try:
                    import json as _json
                    return _json.loads(manifest_path.read_text())
                except Exception:
                    pass
            return {}

        # Gate telemetry (O): explicit execution trace for QA/STATIC/CONSISTENCY
        gate_trace = []

        def _record_gate(gate: str, status: str, detail: str = '', iter_num: int = None):
            gate_trace.append({
                'iteration': int(iter_num if iter_num is not None else iteration),
                'gate': gate,
                'status': status,
                'detail': detail,
                'ts': datetime.utcnow().isoformat()
            })

        def _flush_gate_trace(tag: str = 'gate_telemetry'):
            try:
                self.artifacts.save_log(tag, json.dumps(gate_trace, indent=2))
            except Exception:
                pass

        # ── Feature-level pass/fail tracking (Steal 4.1) ──────────────────
        # Load feature state from intake if available (phase_planner or slice_planner).
        # Sources: _phase_context.feature_state (phase planner) or _mini_spec.acceptance_checks (slice planner).
        _feature_state = []  # list of {feature, entity, status, allowed_files, acceptance_criteria}

        _phase_ctx = self.intake_data.get('_phase_context', {})
        _mini_spec = self.intake_data.get('_mini_spec', {})

        if _phase_ctx.get('feature_state'):
            _feature_state = copy.deepcopy(_phase_ctx['feature_state'])
            print_info(f"  Feature tracking: {len(_feature_state)} feature(s) from phase planner")
        elif _mini_spec.get('acceptance_checks'):
            # Slice planner: single entity per slice, wrap as one feature entry
            _feature_state = [{
                'feature': _mini_spec.get('entity', 'unknown'),
                'entity': _mini_spec.get('entity', 'unknown'),
                'status': 'pending',
                'allowed_files': [f"business/{f}" for f in
                                  (_mini_spec.get('file_contract', {}).get('allowed_files', []))],
                'acceptance_criteria': _mini_spec.get('acceptance_checks', []),
            }]
            print_info(f"  Feature tracking: 1 feature from slice planner ({_feature_state[0]['entity']})")

        def _update_feature_state(defects: list, iter_num: int):
            """Map defects to features by file path and update pass/fail status."""
            if not _feature_state:
                return
            # Collect defect file paths
            defect_files = set()
            for d in defects:
                loc = d.get('location', '')
                if loc.startswith('business/'):
                    defect_files.add(loc)
                # Also match partial paths (e.g. 'routes/clients.py' → 'business/backend/routes/clients.py')
                elif '/' in loc:
                    defect_files.add(loc)

            for fs in _feature_state:
                # Check if any allowed file for this feature has a defect
                has_defect = False
                for af in fs.get('allowed_files', []):
                    if af in defect_files:
                        has_defect = True
                        break
                    # Partial match: defect at 'routes/clients.py' matches 'business/backend/routes/clients.py'
                    af_short = '/'.join(af.split('/')[-2:])  # e.g. 'routes/clients.py'
                    if af_short in defect_files:
                        has_defect = True
                        break

                if has_defect:
                    fs['status'] = 'failing'
                    fs['last_failed_iter'] = iter_num
                elif fs['status'] == 'pending' or (fs['status'] == 'failing' and not has_defect):
                    fs['status'] = 'passing'
                    fs.setdefault('passed_since_iter', iter_num)

        def _build_feature_preamble() -> str:
            """Build a structured preamble showing feature pass/fail status for fix prompts."""
            if not _feature_state:
                return ''
            passing = [fs for fs in _feature_state if fs['status'] == 'passing']
            failing = [fs for fs in _feature_state if fs['status'] == 'failing']
            pending = [fs for fs in _feature_state if fs['status'] == 'pending']

            lines = [
                "\n## FEATURE STATUS (do NOT touch passing features)",
                f"Passing ({len(passing)}): {', '.join(fs['feature'] for fs in passing) or '(none yet)'}",
                f"Failing ({len(failing)}): {', '.join(fs['feature'] for fs in failing) or '(none)'}",
            ]
            if pending:
                lines.append(f"Pending ({len(pending)}): {', '.join(fs['feature'] for fs in pending)}")

            if failing:
                lines.append("\n**Fix ONLY these failing features:**")
                for fs in failing:
                    lines.append(f"- **{fs['feature']}**: files = {', '.join(fs.get('allowed_files', []))}")
                    for ac in fs.get('acceptance_criteria', []):
                        lines.append(f"  - [ ] {ac}")

            if passing:
                lines.append(f"\n**DO NOT modify files belonging to passing features:**")
                pass_files = []
                for fs in passing:
                    pass_files.extend(fs.get('allowed_files', []))
                if pass_files:
                    lines.append(', '.join(pass_files))

            lines.append("")
            return '\n'.join(lines)

        def _run_final_consistency_if_needed(last_iter: int, governance_section: str = ''):
            """
            Final consistency pass on terminal failures (I).
            Visibility-only: does not mutate loop state.
            """
            if last_iter <= 0:
                return
            _record_gate('CONSISTENCY_FINAL', 'START', 'final consistency on terminal path', last_iter)
            issues = self._run_ai_consistency_check(last_iter, governance_section or '')
            if issues:
                _record_gate('CONSISTENCY_FINAL', 'FAIL', f'{len(issues)} issue(s)', last_iter)
                lines = [self._format_consistency_defects_for_claude(issues)]
                try:
                    self.artifacts.save_log('final_consistency_report', "\n\n".join(lines))
                except Exception:
                    pass
            else:
                _record_gate('CONSISTENCY_FINAL', 'PASS', 'no issues', last_iter)

        # ── Warm-start setup ──────────────────────────────────────────
        _ws_run_dir   = Path(getattr(self.cli_args, 'resume_run', None) or '')
        _ws_iteration = int(getattr(self.cli_args, 'resume_iteration', 1))
        _ws_mode      = (getattr(self.cli_args, 'resume_mode', None) or '').lower()
        # --prior-run: seed prohibition tracker from a prior run's QA reports
        # (used in feature-by-feature builds to carry Phase 1 QA knowledge forward)
        _prior_run_dir = Path(getattr(self.cli_args, 'prior_run', None) or '')

        # ── Integration issues warm-start ──────────────────────────────────────
        # --integration-issues seeds the first Claude fix pass with deterministic
        # integration defects (missing routes, model field gaps, spec mismatches).
        # After the fix pass the full QA loop runs normally.
        _integration_issues_path = Path(getattr(self.cli_args, 'integration_issues', None) or '')
        _integration_loaded = False
        if _integration_issues_path.is_file():
            try:
                _int_data = json.loads(_integration_issues_path.read_text())
            except Exception as e:
                print_error(f"--integration-issues: could not parse JSON: {e}")
                return False, "INTEGRATION_ISSUES_PARSE_ERROR"
            _int_raw = _int_data.get('issues', [])
            if not _int_raw:
                print_info("  [INTEGRATION] No issues in file — skipping integration warm-start")
            else:
                # Convert to harness static defect format
                _int_harness_defects = []
                for _i, _d in enumerate(_int_raw):
                    _int_harness_defects.append({
                        'id':       _d.get('id', f'STATIC-INT-{_i+1}'),
                        'severity': _d.get('severity', 'HIGH'),
                        'file':     _d.get('file', ''),
                        'issue':    _d.get('issue', _d.get('evidence', '')),
                        'fix':      _d.get('fix', ''),
                        'related_files': [f for f in _d.get('files', []) if f != _d.get('file', '')],
                    })
                high_n = sum(1 for d in _int_harness_defects if d['severity'] == 'HIGH')
                print_warning(
                    f"  [INTEGRATION] Loaded {len(_int_harness_defects)} issue(s) "
                    f"({high_n} HIGH) from {_integration_issues_path.name}"
                )
                defect_source        = 'integration'
                _raw_pending_defects = _int_harness_defects
                previous_defects     = self._format_static_defects_for_claude(_int_harness_defects)
                iteration            = _ws_iteration + 1
                _integration_loaded  = True
                print_success(
                    f"  [INTEGRATION] Fix pass at iter {iteration} — "
                    f"other resume-mode warm-starts suppressed"
                )

        if _ws_run_dir.is_dir() and _ws_mode == 'fix' and not _integration_loaded:
            # Load the existing QA report as defects and jump straight to the fix iteration
            # Skipped when --integration-issues is also present (integration block already set defects)
            _qa_report_path = _ws_run_dir / 'qa' / f'iteration_{_ws_iteration:02d}_qa_report.txt'
            if not _qa_report_path.exists():
                print_error(f"Warm-start (fix): QA report not found: {_qa_report_path}")
                self._save_run_status(status='RESUME_FAILED', reason='QA report not found for warm-start fix mode',
                                      detail=str(_qa_report_path))
                return False, "RESUME_MISSING_QA_REPORT"
            previous_defects = _qa_report_path.read_text()
            iteration        = _ws_iteration + 1
            print_success(f"Warm-start (fix): loaded QA report from iter {_ws_iteration} — resuming at iter {iteration}")
        elif _ws_run_dir.is_dir() and _ws_mode == 'qa' and not _integration_loaded:
            # Jump the loop counter to the requested iteration — Claude BUILD will be skipped for it
            iteration = _ws_iteration
            print_success(f"Warm-start (qa): starting loop at iter {iteration} — Claude BUILD will be skipped")
        elif _ws_run_dir.is_dir() and _ws_mode in ('static', 'consistency'):
            # ── Resume at static / consistency check phase ────────────────
            # Find which iteration was QA-accepted (explicit or auto-detect)
            accepted_iter = _ws_iteration if _ws_iteration > 1 else self._find_last_accepted_iteration(_ws_run_dir)
            if not accepted_iter:
                print_error(f"Warm-start ({_ws_mode}): no QA-ACCEPTED iteration found in run dir. "
                            "Pass --resume-iteration N to specify manually.")
                self._save_run_status(status='RESUME_FAILED', reason=f'No QA-ACCEPTED iteration found for warm-start {_ws_mode} mode')
                return False, "RESUME_MISSING_ACCEPTED_ITERATION"

            print_success(f"Warm-start ({_ws_mode}): resuming from iteration {accepted_iter:02d}")

            # Rebuild recurring_tracker from prior QA reports
            _prior_qa_files = sorted(_ws_run_dir.glob('qa/iteration_*_qa_report.txt'))
            for _qf in _prior_qa_files:
                for d in self._extract_defects_for_tracking(_qf.read_text()):
                    key = (d['location'], d['classification'])
                    if key not in recurring_tracker:
                        recurring_tracker[key] = {'count': 0, 'last_problem': '', 'last_fix': ''}
                    recurring_tracker[key]['count'] += 1
                    recurring_tracker[key]['last_problem'] = d['problem']
                    recurring_tracker[key]['last_fix']     = d['fix']
            prohibitions_block = self._build_prohibitions_block(recurring_tracker)

            # Build governance_section for Claude cache in fix calls
            governance_section, _ = PromptTemplates.build_prompt(
                self.block, self.intake_data, self.build_governance,
                accepted_iter, self.max_qa_iterations, None,
                self.tech_stack_override, self.external_integration_override,
                self.startup_id, self.effective_tech_stack, [], []
            )

            _qa_accepted_at_iter = accepted_iter  # QA was already accepted in a previous run

            # Run initial checks; if all pass → polish + return; else fall through to main loop
            _ws_initial_artifacts_dir = self.artifacts.build_dir / f'iteration_{accepted_iter:02d}_artifacts'

            _ws_static_issues = []
            if _ws_mode == 'static':
                _ws_static_issues = self._run_static_check(_ws_initial_artifacts_dir, intake_data=self.intake_data)
                if _ws_static_issues:
                    _ws_static_issues = self._prioritize_and_cap_defects(_ws_static_issues)
                    high = sum(1 for d in _ws_static_issues if d['severity'] == 'HIGH')
                    print_warning(f"  [STATIC] {len(_ws_static_issues)} defect(s) found ({high} HIGH)")
                    defect_source        = 'static'
                    _raw_pending_defects = _ws_static_issues
                    previous_defects     = self._format_static_defects_for_claude(_ws_static_issues)
                    iteration            = accepted_iter + 1
                    # Fall through to main while loop (do NOT return)
                else:
                    print_success(f"  [STATIC] PASS — no static defects")

            if not _ws_static_issues:
                # Static passed (or skipped for consistency mode) — run AI consistency
                _ws_consistency_issues = self._run_ai_consistency_check(accepted_iter, governance_section)
                if _ws_consistency_issues:
                    _ws_consistency_issues = self._prioritize_and_cap_defects(_ws_consistency_issues)
                    print_warning(f"  [CONSISTENCY] {len(_ws_consistency_issues)} issue(s) found")
                    defect_source        = 'consistency'
                    _raw_pending_defects = _ws_consistency_issues
                    previous_defects     = self._format_consistency_defects_for_claude(_ws_consistency_issues)
                    iteration            = accepted_iter + 1
                    # Fall through to main while loop (do NOT return)
                else:
                    print_success("  [CONSISTENCY] PASS — all checks clean")
                    # All checks passed — do polish and return now
                    _ws_final_output = self.artifacts.build_synthetic_qa_output(accepted_iter)
                    if self.skip_polish:
                        print_info("  [POLISH] Skipped (--no-polish)")
                    else:
                        polish_success, polish_cost = self._post_qa_polish(accepted_iter, _ws_final_output, governance_section)
                    self._save_run_status(status='QA_ACCEPTED', iteration=accepted_iter,
                                          accepted_at_iteration=accepted_iter,
                                          reason='All gates passed (warm-start consistency clean)')
                    self._print_cost_summary(
                        accepted_iter, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
                        run_end_reason='QA_ACCEPTED'
                    )
                    return True, _ws_final_output
            # If we reach here, at least one check failed → fall through to main while loop

        # Fix A: On resume, reconstruct recurring_tracker from all previous QA reports so that
        # prohibition knowledge accumulated over prior iterations is NOT lost on restart.
        # Without this, the tracker resets to empty → no prohibitions → Claude re-introduces
        # scope violations it had already been trained out of.
        # Collect QA report files from: resume run dir + optional prior run dir
        _all_seed_qa_files = []
        for _seed_dir in [_ws_run_dir, _prior_run_dir]:
            if _seed_dir.is_dir():
                _all_seed_qa_files += sorted(_seed_dir.glob('qa/iteration_*_qa_report.txt'))
        if _all_seed_qa_files:
            _label = 'prior run(s)' if _prior_run_dir.is_dir() and not _ws_run_dir.is_dir() else 'prior QA report(s)'
            print_info(f"Warm-start: rebuilding prohibition tracker from {len(_all_seed_qa_files)} {_label}...")
            for _qf in _all_seed_qa_files:
                for d in self._extract_defects_for_tracking(_qf.read_text()):
                    key = (d['location'], d['classification'])
                    if key not in recurring_tracker:
                        recurring_tracker[key] = {'count': 0, 'last_problem': '', 'last_fix': ''}
                    recurring_tracker[key]['count'] += 1
                    recurring_tracker[key]['last_problem'] = d['problem']
                    recurring_tracker[key]['last_fix']     = d['fix']
            prohibitions_block = self._build_prohibitions_block(recurring_tracker)
            promoted = sum(1 for v in recurring_tracker.values() if v['count'] >= 2)
            print_success(
                f"Warm-start tracker rebuilt: {len(recurring_tracker)} defect(s) tracked, "
                f"{promoted} prohibition(s) active"
            )

        try:
            while iteration <= self.max_qa_iterations:
                print_header(f"ITERATION {iteration}/{self.max_qa_iterations}")

                # Warm-start QA mode: skip Claude BUILD for this specific iteration,
                # load existing artifacts from the resume run directory.
                _warm_skip_build = (
                    _ws_run_dir.is_dir()
                    and _ws_mode == 'qa'
                    and iteration == _ws_iteration
                )

                # ================================================
                # STEP 1: BUILD (Claude)
                # ================================================

                if _warm_skip_build:
                    # Build governance_section (needed for patch calls later) without calling Claude
                    governance_section, _ = PromptTemplates.build_prompt(
                        self.block, self.intake_data, self.build_governance,
                        iteration, self.max_qa_iterations, None,
                        self.tech_stack_override, self.external_integration_override,
                        self.startup_id, self.effective_tech_stack, [], []
                    )
                    _build_path = self.artifacts.build_dir / f'iteration_{iteration:02d}_build.txt'
                    if not _build_path.exists():
                        print_error(f"Warm-start (qa): build output not found: {_build_path}")
                        self._save_run_status(status='RESUME_FAILED', reason='Build output not found for warm-start qa mode',
                                              detail=str(_build_path))
                        return False, "RESUME_MISSING_BUILD"
                    build_output   = _build_path.read_text()
                    still_truncated = False
                    print_success(f"Warm-start QA: loaded iter {iteration} artifacts — skipping Claude BUILD call")
                if not _warm_skip_build:
                    # For static/consistency/integration fix iterations, extract target files from raw defect list
                    # (more accurate than parsing the formatted text).
                    if defect_source in ('static', 'consistency', 'quality', 'compile', 'integration') and _raw_pending_defects:
                        # static/compile: don't require business/ prefix — files found by the checker are
                        # relative to the artifacts dir and may be at wrong paths (e.g. models/Foo.py).
                        # Without the file content, Claude reconstructs from memory → same wrong path again.
                        _require_biz_prefix = defect_source not in ('static', 'compile')
                        defect_target_files = sorted({
                            d.get('file', '') for d in _raw_pending_defects
                            if d.get('file', '') and (
                                not _require_biz_prefix or d.get('file', '').startswith('business/')
                            )
                        })
                        # Fix 2: For stuck or method-mismatch defects, also include related service files
                        # (route↔service joint rebuild — both sides must agree on method names)
                        _extra_targets = []
                        for _d in _raw_pending_defects:
                            if _d.get('stuck') or _d.get('related_files'):
                                for _rf in _d.get('related_files', []):
                                    if _rf.startswith('business/') and _rf not in defect_target_files:
                                        _extra_targets.append(_rf)
                        if _extra_targets:
                            print_info(
                                f"  [STATIC] Fix 2: adding {len(_extra_targets)} related service file(s) "
                                f"to targets for joint rebuild: {_extra_targets}"
                            )
                            defect_target_files = sorted(set(defect_target_files) | set(_extra_targets))

                        # Fix 3: For consistency issues, include ALL files from the <-> relationship.
                        # Consistency defects have Files: A <-> B — both sides must be fixed together
                        # or the field name oscillates (fix service → model wrong, fix model → service wrong).
                        if defect_source == 'consistency':
                            _consistency_extra = []
                            for _d in _raw_pending_defects:
                                for _cf in re.split(r'\s*<->\s*|\s*,\s*', _d.get('files', '')):
                                    _cf = _cf.strip()
                                    if _cf.startswith('business/') and _cf not in defect_target_files:
                                        _consistency_extra.append(_cf)
                            if _consistency_extra:
                                print_info(
                                    f"  [CONSISTENCY] Fix 3: adding {len(_consistency_extra)} related file(s) "
                                    f"for joint fix (both sides of <->): {_consistency_extra}"
                                )
                                defect_target_files = sorted(set(defect_target_files) | set(_consistency_extra))
                        required_file_inventory = self._get_previous_iteration_inventory(iteration)
                        if not required_file_inventory:
                            # Fallback: read manifest from last accepted artifacts dir
                            _prev_artifacts = self.artifacts.build_dir / f'iteration_{iteration - 1:02d}_artifacts'
                            _manifest = _prev_artifacts / 'artifact_manifest.json'
                            if _manifest.exists():
                                try:
                                    _m = json.load(open(_manifest))
                                    required_file_inventory = sorted({
                                        a['path'] for a in _m.get('artifacts', [])
                                        if a.get('path', '').startswith('business/')
                                    })
                                except Exception:
                                    required_file_inventory = []
                    else:
                        required_file_inventory = self._get_previous_iteration_inventory(iteration) if previous_defects else []
                        defect_target_files = self._extract_defect_target_files(previous_defects) if previous_defects else []

                    # Select prompt:
                    #   all targeted fix sources → surgical patch WITH current file contents
                    #   feature QA → full build prompt
                    # Surgical patch is always strictly better: Claude sees the exact file and
                    # patches only what the defect specifies. Without file contents Claude
                    # reconstructs from memory → drops methods/fields → cascades new defects.
                    _pre_qa_strat = 'surgical'  # default; overridden for static/consistency below
                    if defect_source in ('static', 'consistency', 'quality', 'compile', 'integration') and previous_defects:
                        # Non-QA gate driving this iteration — triage strategy doesn't apply.
                        _triage_strategy = 'surgical'
                        _source_label = defect_source.upper()

                        # Static + consistency: triage before routing to surgical vs full build.
                        # quality/compile/integration always surgical (their defects are narrow).
                        _pre_qa_strat = 'surgical'
                        if defect_source in ('static', 'consistency'):
                            _consec = (
                                _static_consecutive_iters if defect_source == 'static'
                                else _consistency_consecutive_iters
                            )
                            _pre_qa_strat = self._triage_pre_qa_strategy(
                                defect_source, defect_target_files, previous_defects, _consec
                            )

                        if _pre_qa_strat == 'systemic':
                            # Wide surgical patch: surgical patch template but with ALL current
                            # artifact files as context (not just the 2-3 defect targets).
                            # Claude sees every existing file + all defects → can fix missing
                            # methods, add missing files, and preserve correct files in one pass.
                            # Avoids the 89K char cold-start build prompt that includes all
                            # historical prohibitions and confuses Claude on pre-QA fixes.
                            governance_section, _ = PromptTemplates.build_prompt(
                                self.block, self.intake_data, self.build_governance,
                                iteration, self.max_qa_iterations, None,
                                self.tech_stack_override, self.external_integration_override,
                                self.startup_id, self.effective_tech_stack, [], []
                            )
                            # Load ALL current artifacts as context (not just defect targets)
                            _all_current_files = self._get_previous_iteration_inventory(iteration)
                            _current_file_contents = self._read_target_file_contents(
                                iteration, _all_current_files
                            )
                            print_info(
                                f"  [{_source_label}] SYSTEMIC → wide surgical patch "
                                f"({len(_current_file_contents)} current file(s) as context)"
                            )
                            dynamic_section = PromptTemplates.integration_fix_prompt(
                                integration_defects=previous_defects,
                                required_file_inventory=required_file_inventory,
                                defect_target_files=defect_target_files,
                                current_file_contents=_current_file_contents,
                            )
                        else:
                            # Surgical: read current file contents so Claude patches only what
                            # the defect specifies rather than reconstructing from memory.
                            governance_section, _ = PromptTemplates.build_prompt(
                                self.block, self.intake_data, self.build_governance,
                                iteration, self.max_qa_iterations, None,
                                self.tech_stack_override, self.external_integration_override,
                                self.startup_id, self.effective_tech_stack, [], []
                            )
                            _current_file_contents = self._read_target_file_contents(iteration, defect_target_files)
                            if _current_file_contents:
                                print_info(f"  [{_source_label}] Loaded {len(_current_file_contents)} current file(s) for surgical patch")
                            else:
                                print_warning(f"  [{_source_label}] No current file contents found — Claude will reconstruct")
                            dynamic_section = PromptTemplates.integration_fix_prompt(
                                integration_defects=previous_defects,
                                required_file_inventory=required_file_inventory,
                                defect_target_files=defect_target_files,
                                current_file_contents=_current_file_contents,
                            )
                            print_info(f"  [{_source_label}] Using surgical patch prompt for {len(defect_target_files)} target file(s)")
                    elif defect_source == 'qa' and previous_defects and defect_target_files and len(defect_target_files) <= 5 and _triage_strategy != 'systemic':
                        # Targeted QA fix: few defects with clear file locations → surgical patch.
                        # Full build prompt causes Claude to regenerate all files, introducing new
                        # consistency defects for a 1-2 line fix (e.g. Auth0 token pattern).
                        # Exception: triage classified defects as SYSTEMIC → fall through to full
                        # build so Claude gets architectural direction, not a line-level patch.
                        governance_section, _ = PromptTemplates.build_prompt(
                            self.block, self.intake_data, self.build_governance,
                            iteration, self.max_qa_iterations, None,
                            self.tech_stack_override, self.external_integration_override,
                            self.startup_id, self.effective_tech_stack, [], []
                        )
                        _current_file_contents = self._read_target_file_contents(iteration, defect_target_files)
                        if _current_file_contents:
                            print_info(f"  [QA] Loaded {len(_current_file_contents)} current file(s) for surgical QA patch")
                        else:
                            print_warning(f"  [QA] No current file contents found — Claude will reconstruct")
                        dynamic_section = PromptTemplates.integration_fix_prompt(
                            integration_defects=previous_defects,
                            required_file_inventory=required_file_inventory,
                            defect_target_files=defect_target_files,
                            current_file_contents=_current_file_contents,
                        )
                        print_info(f"  [QA] Using surgical patch for {len(defect_target_files)} targeted QA defect file(s)")
                    else:
                        # Broad QA failure or no clear file targets → full build prompt
                        governance_section, dynamic_section = PromptTemplates.build_prompt(
                            self.block,
                            self.intake_data,
                            self.build_governance,
                            iteration,
                            self.max_qa_iterations,
                            previous_defects,
                            self.tech_stack_override,
                            self.external_integration_override,
                            self.startup_id,
                            self.effective_tech_stack,
                            required_file_inventory,
                            defect_target_files,
                            prohibitions_block,
                            ubiquitous_language_block=self.ubiquitous_language_block
                        )

                    # FIX #4: Dynamic max tokens based on iteration + defect_source.
                    # Systemic pre-QA builds (full build prompt) → always 16384.
                    # Patch iterations → 8192 (1 file) or 16384 (≥2 files).
                    if defect_source in ('static', 'consistency') and _pre_qa_strat == 'systemic':
                        max_tokens = Config.CLAUDE_MAX_TOKENS_DEFAULT  # full build needs full room
                    else:
                        max_tokens = Config.get_max_tokens(iteration, defect_source, len(defect_target_files))

                    # FIX #6: Dynamic timeout based on iteration (first call needs more time)
                    request_timeout = Config.get_request_timeout(iteration)

                    # Log the full prompt (combine sections for log)
                    full_prompt_for_log = governance_section + "\n\n" + dynamic_section
                    self.artifacts.save_log(f'iteration_{iteration:02d}_build_prompt', full_prompt_for_log)

                    # FIX #1 & #4 & #6: Detailed logging before Claude call
                    print_info("═══════════════════════════════════════════════════════════")
                    print_info(f"ITERATION {iteration} - CLAUDE BUILD CALL")
                    print_info("═══════════════════════════════════════════════════════════")
                    print_info("Prompt structure:")
                    print_info(f"  → Cacheable section: {len(governance_section):,} chars (governance ZIP)")
                    print_info(f"  → Dynamic section: {len(dynamic_section):,} chars (intake + defects)")
                    print_info(f"  → Total prompt size: {len(governance_section) + len(dynamic_section):,} chars")
                    print_info(f"Token limit: {max_tokens:,} tokens (iteration {iteration})")
                    print_info(f"Request timeout: {request_timeout}s ({request_timeout//60} minutes)")
                    print_info("Cache enabled: YES" if iteration == 1 else "Cache enabled: YES (expecting hit)")
                    print_info("───────────────────────────────────────────────────────────")
                    print_info("Calling Claude API...")

                    start_time = time.time()
                    still_truncated = False  # Track if output remains truncated after continuations
                    try:
                        # FIX #1: Use cacheable_prefix for prompt caching
                        # FIX #4: Use dynamic max_tokens
                        # FIX #6: Use dynamic timeout based on iteration
                        build_response = self.claude.call(
                            dynamic_section,
                            max_tokens=max_tokens,
                            cacheable_prefix=governance_section,
                            timeout=request_timeout
                        )
                        build_output   = build_response['content'][0]['text']
                        build_time     = time.time() - start_time
    
                        # FIX #1: Detailed logging of cache performance
                        print_success(f"Claude responded in {build_time:.1f}s")
                        usage_stats = self._log_claude_usage(build_response, iteration, is_continuation=False)
    
                        # Accumulate usage stats
                        total_calls += 1
                        if usage_stats['cache_creation_tokens'] > 0:
                            total_cache_writes += 1
                            total_cache_write_tokens += usage_stats['cache_creation_tokens']
                        if usage_stats['cache_read_tokens'] > 0:
                            total_cache_hits += 1
                            total_cache_read_tokens += usage_stats['cache_read_tokens']
                        total_input_tokens += usage_stats['input_tokens']
                        total_output_tokens += usage_stats['output_tokens']
    
                        print_success(f"BUILD completed in {build_time:.1f}s")
    
                        # ── TCP-STYLE MULTI-PART ASSEMBLY ──
                        # Check if Claude split the output into numbered parts
                        part_info = detect_multipart(build_output)
                        max_parts = self.max_build_parts
                        max_continuations = self.max_build_continuations
    
                        if part_info['is_multipart'] and not part_info['is_final']:
                            print_warning(
                                f"BIG BUILD DETECTED: multipart assembly active "
                                f"(max parts={max_parts}, current declared parts={part_info.get('total_parts', '?')})"
                            )
                            received_files = extract_file_paths_from_output(build_output)
                            print_info(f"Multi-part build detected: PART {part_info['current_part']}/{part_info['total_parts']}")
                            print_info(f"  → Files received so far: {len(received_files)}")
                            if part_info['remaining_files']:
                                print_info(f"  → Remaining files: {', '.join(part_info['remaining_files'][:10])}")
    
                            next_part = part_info['current_part'] + 1
                            total_parts = part_info['total_parts']
    
                            while next_part <= total_parts and next_part <= max_parts:
                                received_files = extract_file_paths_from_output(build_output)
                                remaining = part_info['remaining_files']
                                remaining_str = ', '.join(remaining) if remaining else '(check your manifest)'
    
                                # Prompt template source: directives/prompts/part_prompt.md
                                part_prompt = DirectiveTemplateLoader.render(
                                    'part_prompt.md',
                                    next_part=next_part,
                                    total_parts=total_parts,
                                    startup_id=self.startup_id,
                                    received_files_bullets=chr(10).join('- ' + f for f in received_files),
                                    remaining_str=remaining_str
                                )
    
                                print_info("───────────────────────────────────────────────────────────")
                                print_info(f"REQUESTING PART {next_part}/{total_parts} - Using cached governance")
                                print_info(f"  → Part prompt: {len(part_prompt):,} chars")
                                print_info(f"  → Token limit: {max_tokens:,} tokens")
                                print_info(f"  → Request timeout: {request_timeout}s")
                                print_info("───────────────────────────────────────────────────────────")
    
                                cont_start = time.time()
                                cont_response = self.claude.call(
                                    part_prompt,
                                    max_tokens=max_tokens,
                                    cacheable_prefix=governance_section,
                                    timeout=request_timeout
                                )
                                part_output = cont_response['content'][0]['text']
                                cont_time = time.time() - cont_start
    
                                print_success(f"PART {next_part}/{total_parts} received in {cont_time:.1f}s")
    
                                # Log and accumulate usage
                                cont_usage_stats = self._log_claude_usage(cont_response, iteration, is_continuation=True, continuation_num=next_part)
                                total_calls += 1
                                if cont_usage_stats['cache_creation_tokens'] > 0:
                                    total_cache_writes += 1
                                    total_cache_write_tokens += cont_usage_stats['cache_creation_tokens']
                                if cont_usage_stats['cache_read_tokens'] > 0:
                                    total_cache_hits += 1
                                    total_cache_read_tokens += cont_usage_stats['cache_read_tokens']
                                total_input_tokens += cont_usage_stats['input_tokens']
                                total_output_tokens += cont_usage_stats['output_tokens']
    
                                # Append part to build output
                                build_output += "\n\n" + part_output
    
                                new_files = extract_file_paths_from_output(part_output)
                                print_info(f"  → New files in part {next_part}: {len(new_files)}")
    
                                # Check if this was the final part
                                part_info = detect_multipart(part_output)
                                if part_info['is_final'] or BUILD_COMPLETE_MARKER in part_output:
                                    all_files = extract_file_paths_from_output(build_output)
                                    print_success(f"All {total_parts} parts assembled — {len(all_files)} total files")
                                    break
    
                                next_part += 1
    
                        # ── FALLBACK: Truncation recovery ──
                        # If output is still truncated after multipart handling (or without multipart),
                        # run continuation recovery. This closes the gap where Claude incorrectly
                        # labels output as PART 1/1 but still truncates before completion.
                        if detect_truncation(build_output):
                            continuation_count = 0
                            recovery_mode = "multipart fallback" if part_info['is_multipart'] else "standard fallback"
                            print_warning(
                                f"BIG BUILD DETECTED: {recovery_mode} continuation mode active "
                                f"(max continuations={max_continuations})"
                            )
    
                            while detect_truncation(build_output) and continuation_count < max_continuations:
                                continuation_count += 1
                                print_warning(
                                    f"Output still truncated - requesting continuation "
                                    f"{continuation_count}/{max_continuations}..."
                                )
    
                                # Prompt template source: directives/prompts/continuation_prompt.md
                                continuation_prompt = DirectiveTemplateLoader.render(
                                    'continuation_prompt.md',
                                    startup_id=self.startup_id,
                                    block=self.block,
                                    iteration=iteration,
                                    max_iterations=self.max_qa_iterations,
                                    last_output_tail=build_output[-1500:]
                                )
    
                                print_info(f"CONTINUATION {continuation_count} - fallback mode")
                                cont_start = time.time()
                                cont_response = self.claude.call(
                                    continuation_prompt,
                                    max_tokens=max_tokens,
                                    cacheable_prefix=governance_section,
                                    timeout=request_timeout
                                )
                                continuation_output = cont_response['content'][0]['text']
                                cont_time = time.time() - cont_start
    
                                print_success(f"Continuation {continuation_count} completed in {cont_time:.1f}s")
                                cont_usage_stats = self._log_claude_usage(cont_response, iteration, is_continuation=True, continuation_num=continuation_count)
                                total_calls += 1
                                if cont_usage_stats['cache_creation_tokens'] > 0:
                                    total_cache_writes += 1
                                    total_cache_write_tokens += cont_usage_stats['cache_creation_tokens']
                                if cont_usage_stats['cache_read_tokens'] > 0:
                                    total_cache_hits += 1
                                    total_cache_read_tokens += cont_usage_stats['cache_read_tokens']
                                total_input_tokens += cont_usage_stats['input_tokens']
                                total_output_tokens += cont_usage_stats['output_tokens']
    
                                build_output += "\n\n<!-- CONTINUATION -->\n\n" + continuation_output
    
                        # Track final truncation status
                        still_truncated = detect_truncation(build_output)
    
                        if still_truncated:
                            print_error(f"Build still incomplete after multi-part/continuation assembly")
                        else:
                            all_files = extract_file_paths_from_output(build_output)
                            print_success(f"Build complete — {len(all_files)} files extracted")
    
                        # Fix B: On patch iterations, truncate build_output at PATCH_SET_COMPLETE
                        # before extraction. Claude sometimes appends continuation files after the
                        # marker — those collateral files cause regressions and must be ignored.
                        # The full raw output is still saved to disk for audit via save_build_output.
                        is_patch_iteration = iteration > 1 and previous_defects
                        if is_patch_iteration and PATCH_SET_COMPLETE_MARKER in build_output:
                            marker_pos = build_output.index(PATCH_SET_COMPLETE_MARKER)
                            build_output_for_extraction = build_output[:marker_pos + len(PATCH_SET_COMPLETE_MARKER)]
                            extra_files = extract_file_paths_from_output(
                                build_output[marker_pos + len(PATCH_SET_COMPLETE_MARKER):]
                            )
                            if extra_files:
                                print_warning(
                                    f"  [PATCH_SET_COMPLETE] Truncated {len(extra_files)} collateral file(s) "
                                    f"Claude output after marker — ignored: {', '.join(extra_files)}"
                                )
                        else:
                            build_output_for_extraction = build_output

                        self.artifacts.save_build_output(
                            iteration, build_output,
                            extract_from=build_output_for_extraction if build_output_for_extraction is not build_output else None
                        )

                        # Track which defects Claude claimed as FIXED in this patch iteration.
                        # We'll confirm resolution after QA (if they don't reappear → resolved).
                        if is_patch_iteration:
                            pending_resolution = self._extract_fixed_from_patch(
                                build_output, previous_defects
                            )
                            if pending_resolution:
                                print_info(
                                    f"  [PENDING RESOLUTION] {len(pending_resolution)} defect(s) claimed FIXED — "
                                    f"awaiting QA confirmation: "
                                    + ", ".join(f"{loc}" for loc, cls, _ in pending_resolution)
                                )
                        else:
                            pending_resolution = set()

                        # Post-build pruning for boilerplate mode: keep business/** only
                        if self.use_boilerplate:
                            self.artifacts.prune_non_business_artifacts(iteration)

                        # Defect iteration: carry forward all non-defect files from previous iteration.
                        # Claude outputs only defect-target files; harness fills in the rest.
                        # Use the extraction-scoped output so merge_forward sees only the files
                        # Claude intentionally output (not collateral past PATCH_SET_COMPLETE).
                        if self.use_boilerplate and is_patch_iteration:
                            claude_output_paths = extract_file_paths_from_output(build_output_for_extraction)
                            self.artifacts.merge_forward_from_previous_iteration(iteration, claude_output_paths)

                        # FIX #6: save defect fix artifact on iterations 2+
                        if is_patch_iteration:
                            self.artifacts.save_defect_fix(iteration, build_output)
    
                    except Exception as e:
                        print_error(f"BUILD failed: {e}")
                        return False, str(e)

                # ================================================
                # TRUNCATION & QUESTION DETECTION
                # ================================================

                # FIX #14: If truncated but we extracted files, proceed to validation + patch call
                # instead of aborting. The patch call can fill in missing files.
                # Only hard-abort if we extracted NOTHING (truly broken output).
                if still_truncated:
                    # Count how many FILE: headers Claude actually output
                    declared_files = extract_file_paths_from_output(build_output)
                    min_artifacts = self.qa_override.get('pre_qa_validation', {}).get('min_artifact_count', 3)

                    if len(declared_files) >= min_artifacts:
                        print_warning(f"Build truncated (no completion marker) but {len(declared_files)} files declared")
                        print_warning(f"  → Proceeding to extraction + validation + patch call")
                        # Save truncated output for debugging but don't abort
                        truncated_path = self.artifacts.logs_dir / 'truncated_build_output.txt'
                        truncated_path.write_text(build_output, encoding='utf-8')
                    else:
                        print_error(f"BUILD OUTPUT TRUNCATED on iteration {iteration}")
                        print_error(f"  → Only {len(declared_files)} file(s) declared (need {min_artifacts}+)")
                        print_error(f"  → Output incomplete even after continuations")
                        print_error(f"  → Solution: Increase CLAUDE_MAX_TOKENS or simplify intake")
                        truncated_path = self.artifacts.logs_dir / 'truncated_build_output.txt'
                        truncated_path.write_text(build_output, encoding='utf-8')
                        print_warning(f"Truncated output saved: logs/truncated_build_output.txt")
                        self._print_cost_summary(
                            iteration, total_calls, total_cache_writes, total_cache_hits,
                            total_cache_write_tokens, total_cache_read_tokens,
                            total_input_tokens, total_output_tokens,
                            total_gpt_calls, total_gpt_input_tokens, total_gpt_output_tokens,
                            run_end_reason='BUILD_TRUNCATED'
                        )
                        self._save_run_status(status='BUILD_TRUNCATED', iteration=iteration,
                                              reason='Build output truncated after max continuations')
                        return False, "BUILD_TRUNCATED"

                # Check for actual questions (CLARIFICATION_NEEDED marker)
                if detect_claude_questions(build_output):
                    print_error(f"Claude asked clarifying questions on iteration {iteration} — stopping pipeline")
                    self.artifacts.save_claude_questions(iteration, build_output)
                    print_warning("Review questions in: logs/claude_questions.txt")
                    print_warning("Answer questions, update intake, and re-run")
                    self._save_run_status(
                        status='QUESTIONS_DETECTED',
                        iteration=iteration,
                        reason='Claude asked clarifying questions instead of building',
                    )
                    self._print_cost_summary(
                        iteration, total_calls, total_cache_writes, total_cache_hits,
                        total_cache_write_tokens, total_cache_read_tokens,
                        total_input_tokens, total_output_tokens,
                        total_gpt_calls, total_gpt_input_tokens, total_gpt_output_tokens,
                        run_end_reason='QUESTIONS_DETECTED'
                    )
                    return False, "QUESTIONS_DETECTED"

                # Warn if build completion marker missing (but don't stop — let QA decide)
                if BUILD_COMPLETE_MARKER not in build_output:
                    print_warning(f"Build did not produce '{BUILD_COMPLETE_MARKER}' marker")

                # ================================================
                # PRE-QA VALIDATION (FIX #8)
                # ================================================
                # WHY: Don't waste QA cycles if build is obviously incomplete.
                # Check for critical artifacts before sending to ChatGPT.

                print_info("═══════════════════════════════════════════════════════════")
                print_info("PRE-QA VALIDATION - Checking build completeness")
                print_info("═══════════════════════════════════════════════════════════")

                validation_passed, validation_errors, missing_files_list = self._validate_build_artifacts(iteration)

                if not validation_passed:
                    consecutive_validation_failures += 1
                    print_error(f"BUILD VALIDATION FAILED on iteration {iteration} ({consecutive_validation_failures} consecutive)")
                    for error in validation_errors:
                        print_error(f"  → {error}")

                    # FIX #11: Try patch recovery for both:
                    # 1) files listed in manifest but not extracted
                    # 2) required files missing from manifest entirely
                    required_missing = []
                    for err in validation_errors:
                        m = re.search(r"Required file '([^']+)' not listed in artifact_manifest\.json", err)
                        if m:
                            required_missing.append(m.group(1))

                    patch_targets = sorted(set((missing_files_list or []) + required_missing))

                    if patch_targets:
                        print_info("")
                        print_info(f"Attempting patch call for {len(patch_targets)} missing file(s)...")
                        patch_success, patch_costs = self._patch_missing_files(
                            iteration, patch_targets, build_output, governance_section
                        )

                        # Accumulate patch costs
                        total_calls += patch_costs['calls']
                        total_input_tokens += patch_costs['input_tokens']
                        total_output_tokens += patch_costs['output_tokens']
                        if patch_costs['cache_read_tokens'] > 0:
                            total_cache_hits += 1
                            total_cache_read_tokens += patch_costs['cache_read_tokens']
                        if patch_costs['cache_creation_tokens'] > 0:
                            total_cache_writes += 1
                            total_cache_write_tokens += patch_costs['cache_creation_tokens']

                        if patch_success:
                            # Re-validate after patch
                            print_info("Re-validating after patch...")
                            validation_passed, validation_errors, missing_files_list = self._validate_build_artifacts(iteration)
                            if validation_passed:
                                consecutive_validation_failures = 0
                                print_success("Patch fixed all issues — proceeding to QA")
                                # Fall through to QA below

                    if not validation_passed:
                        print_error("")
                        print_error("SKIPPING QA - Build is incomplete")
                        print_error("Treating this as a BUILD failure (will retry next iteration)")
                        print_warning("Common causes:")
                        print_warning("  - Output truncated (hit token limit)")
                        print_warning("  - Claude didn't output all required files")
                        print_warning("  - artifact_manifest.json incomplete or malformed")

                        # FIX #9: Warn if validation fails too many times
                        if consecutive_validation_failures >= 5:
                            print_warning("")
                            print_warning(f"⚠️  VALIDATION FAILED {consecutive_validation_failures} TIMES IN A ROW")
                            print_warning("This suggests Claude is struggling to maintain all required files.")
                            print_warning("Consider:")
                            print_warning("  1. Check if token limit is sufficient (currently 16384)")
                            print_warning("  2. Simplify the intake requirements")
                            print_warning("  3. Review validation logs to see which files are missing")
                            print_warning("")

                        # Create synthetic defect report for next iteration
                        synthetic_defects = "## BUILD VALIDATION FAILURES\n\n"
                        synthetic_defects += "The following critical issues were detected:\n\n"
                        for i, error in enumerate(validation_errors, 1):
                            synthetic_defects += f"{i}. {error}\n"
                        synthetic_defects += "\n**FIX ALL OF THESE ISSUES.**\n"

                        # FIX #9: Show cumulative cost after validation failure
                        self._display_cumulative_cost(
                            iteration, total_calls, total_cache_writes, total_cache_hits,
                            total_cache_read_tokens, total_cache_write_tokens,
                            total_input_tokens, total_output_tokens,
                            total_gpt_calls, total_gpt_input_tokens, total_gpt_output_tokens
                        )

                        previous_defects = synthetic_defects
                        iteration += 1
                        continue  # Skip QA, go to next iteration

                consecutive_validation_failures = 0  # Reset counter
                print_success("✓ Build validation passed - all critical artifacts present")
                print_info("───────────────────────────────────────────────────────────")

                # ================================================
                # STEP 1.5: GATE 0 COMPILE (MANDATORY)
                # ================================================
                print_info("")
                print_info("═══════════════════════════════════════════════════════════")
                print_info("GATE 0: COMPILE CHECK — Mandatory pre-QA compile pass")
                print_info("═══════════════════════════════════════════════════════════")
                _record_gate('COMPILE', 'START', 'running mandatory compile checks', iteration)
                _compile_artifacts_dir = self.artifacts.build_dir / f'iteration_{iteration:02d}_artifacts'
                compile_defects = self._run_compile_gate(_compile_artifacts_dir)
                if compile_defects:
                    compile_defects_all = compile_defects
                    compile_defects = self._prioritize_and_cap_defects(compile_defects_all)
                    if len(compile_defects_all) > len(compile_defects):
                        print_warning(
                            f"  [COMPILE] Prioritized {len(compile_defects)} of {len(compile_defects_all)} defects for this iteration"
                        )
                    _record_gate('COMPILE', 'FAIL', f'{len(compile_defects)} defect(s)', iteration)
                    high = sum(1 for d in compile_defects if d['severity'] == 'HIGH')
                    print_warning(f"  [COMPILE] FAIL — {len(compile_defects)} defect(s) ({high} HIGH)")
                    for d in compile_defects:
                        sev_fn = print_error if d['severity'] == 'HIGH' else print_warning
                        sev_fn(f"    {d['id']} [{d['severity']}] {d['file']}: {d['issue']}")
                    defect_source        = 'compile'
                    _raw_pending_defects = compile_defects
                    previous_defects     = self._format_static_defects_for_claude(compile_defects)
                    iteration += 1
                    if iteration > self.max_qa_iterations:
                        print_error(f"Max iterations ({self.max_qa_iterations}) reached during compile gate — halting")
                        self._print_cost_summary(
                            iteration - 1, total_calls, total_cache_writes, total_cache_hits,
                            total_cache_write_tokens, total_cache_read_tokens,
                            total_input_tokens, total_output_tokens,
                            total_gpt_calls, total_gpt_input_tokens, total_gpt_output_tokens,
                            run_end_reason='MAX_ITERATIONS'
                        )
                        _flush_gate_trace()
                        return False, "MAX_ITERATIONS_EXCEEDED"
                    print_info(f"Starting iteration {iteration} with compile-fix defects...")
                    continue
                print_success("  [COMPILE] PASS — compile checks succeeded")
                _record_gate('COMPILE', 'PASS', 'compile checks clean', iteration)

                # ================================================
                # STEP 2: GATE 2 STATIC CHECK (MANDATORY)
                # ================================================
                print_info("")
                print_info("═══════════════════════════════════════════════════════════")
                print_info("GATE 2: STATIC CHECK — Deterministic code quality pass")
                print_info("═══════════════════════════════════════════════════════════")
                _record_gate('STATIC', 'START', 'running deterministic static checks', iteration)
                _static_artifacts_dir = _compile_artifacts_dir
                static_defects = self._run_static_check(_static_artifacts_dir, intake_data=self.intake_data)
                if static_defects:
                    static_defects_all = static_defects
                    static_defects = self._prioritize_and_cap_defects(static_defects_all)
                    if len(static_defects_all) > len(static_defects):
                        print_warning(
                            f"  [STATIC] Prioritized {len(static_defects)} of {len(static_defects_all)} defects for this iteration"
                        )
                    _record_gate('STATIC', 'FAIL', f'{len(static_defects)} defect(s)', iteration)
                    high = sum(1 for d in static_defects if d['severity'] == 'HIGH')
                    print_warning(f"  [STATIC] FAIL — {len(static_defects)} defect(s) ({high} HIGH)")
                    for d in static_defects:
                        sev_fn = print_error if d['severity'] == 'HIGH' else print_warning
                        sev_fn(f"    {d['id']} [{d['severity']}] {d['file']}: {d['issue']}")

                    # Fix 1: Track defect fingerprints to detect stuck defects
                    _static_consecutive_iters += 1
                    _cur_static_fingerprints = set()
                    for d in static_defects:
                        _fp = (d.get('file', ''), d.get('issue', '')[:80])
                        _cur_static_fingerprints.add(_fp)
                        if _fp in _last_static_fingerprints:
                            _static_defect_fingerprints[_fp] = _static_defect_fingerprints.get(_fp, 1) + 1
                        else:
                            _static_defect_fingerprints[_fp] = 1
                    # Clear counts for fingerprints no longer present
                    for _fp in list(_static_defect_fingerprints):
                        if _fp not in _cur_static_fingerprints:
                            del _static_defect_fingerprints[_fp]
                    _last_static_fingerprints = _cur_static_fingerprints

                    _stuck_fps = {_fp for _fp, _cnt in _static_defect_fingerprints.items() if _cnt >= 3}
                    if _stuck_fps:
                        print_warning(
                            f"  [STATIC] Fix 1: {len(_stuck_fps)} defect(s) stuck for 3+ iterations — "
                            "promoting to joint route+service rebuild"
                        )
                        # Mark stuck defects so target calculation includes related files
                        for d in static_defects:
                            _fp = (d.get('file', ''), d.get('issue', '')[:80])
                            if _fp in _stuck_fps:
                                d['stuck'] = True

                    # Fix 3: Hard cap — fall through to Feature QA after MAX_STATIC_CONSECUTIVE iters
                    if _static_consecutive_iters >= Config.MAX_STATIC_CONSECUTIVE:
                        print_warning(
                            f"  [STATIC] Fix 3: Hard cap reached ({_static_consecutive_iters} consecutive static iters) "
                            "— falling through to Feature QA to break deadlock"
                        )
                        _record_gate('STATIC', 'FALLTHROUGH',
                                     f'cap={Config.MAX_STATIC_CONSECUTIVE} reached', iteration)
                        _static_consecutive_iters  = 0
                        _static_defect_fingerprints = {}
                        _last_static_fingerprints   = set()
                        defect_source        = 'qa'
                        previous_defects     = None
                        _raw_pending_defects = []
                        # Fall through — do NOT continue; run GATE 3, GATE 4, Feature QA this iteration
                    else:
                        defect_source        = 'static'
                        _raw_pending_defects = static_defects
                        previous_defects     = self._format_static_defects_for_claude(static_defects)
                        iteration += 1
                        if iteration > self.max_qa_iterations:
                            print_error(f"Max iterations ({self.max_qa_iterations}) reached during static check — halting")
                            self._print_cost_summary(
                                iteration - 1, total_calls, total_cache_writes, total_cache_hits,
                                total_cache_write_tokens, total_cache_read_tokens,
                                total_input_tokens, total_output_tokens,
                                total_gpt_calls, total_gpt_input_tokens, total_gpt_output_tokens,
                                run_end_reason='MAX_ITERATIONS'
                            )
                            _flush_gate_trace()
                            return False, "MAX_ITERATIONS_EXCEEDED"
                        print_info(f"Starting iteration {iteration} with static fix...")
                        continue
                else:
                    _static_consecutive_iters  = 0
                    _static_defect_fingerprints = {}
                    _last_static_fingerprints   = set()

                if not static_defects:
                    print_success("  [STATIC] PASS — no static defects")
                    _record_gate('STATIC', 'PASS', 'no static defects', iteration)

                # Update manifest snapshot for gate locking
                _prev_artifact_manifest = _load_iteration_manifest(iteration - 1) if iteration > 1 else {}
                _cur_artifact_manifest  = _load_iteration_manifest(iteration)

                # Determine repair vs acceptance mode for this iteration.
                # Acceptance mode triggers when iteration reaches the threshold OR when
                # CONSISTENCY + FEATURE_QA are both locked (no HIGH defects remain).
                _early_acceptance = (
                    gate_locks['CONSISTENCY'] and gate_locks['FEATURE_QA']
                )
                build_mode = 'acceptance' if (iteration >= acceptance_threshold or _early_acceptance) else 'repair'
                if _early_acceptance and build_mode == 'acceptance' and iteration < acceptance_threshold:
                    print_info(f"  [MODE] Early acceptance mode triggered — all structural gates locked")
                _record_gate('MODE', build_mode.upper(), f'iter={iteration} threshold={acceptance_threshold}', iteration)

                # ================================================
                # STEP 2.5: GATE 1.5 INTEGRATION_FAST (DETERMINISTIC)
                # ================================================
                print_info("")
                print_info("═══════════════════════════════════════════════════════════")
                print_info("GATE 1.5: INTEGRATION_FAST — Structural pre-check (checks 1,2,4,6,7)")
                print_info("═══════════════════════════════════════════════════════════")
                _record_gate('INTEGRATION_FAST', 'START', 'running fast integration checks', iteration)
                integration_fast_issues = self._run_integration_fast_gate(iteration)
                if integration_fast_issues:
                    _record_gate('INTEGRATION_FAST', 'FAIL',
                                 f'{len(integration_fast_issues)} issue(s) — skipping AI gates', iteration)
                    print_warning(f"  [INTEGRATION_FAST] FAILED — skipping AI gates this iteration, routing to structural fix")
                    # Write issues to a temp file and load as defects via integration fix path
                    import tempfile as _tf, json as _jf
                    _fast_issues_file = self.artifacts.build_dir / f'iteration_{iteration:02d}_integration_fast_issues.json'
                    _fast_output = {
                        'total_issues': len(integration_fast_issues),
                        'high_severity': sum(1 for i in integration_fast_issues if i.get('severity') == 'HIGH'),
                        'medium_severity': sum(1 for i in integration_fast_issues if i.get('severity') == 'MEDIUM'),
                        'issues': integration_fast_issues,
                        'fix_target_files': sorted({
                            i['file'] for i in integration_fast_issues
                            if i.get('file', '').startswith('business/')
                        }),
                        'verdict': 'INTEGRATION_REJECTED',
                    }
                    import json as _json_int
                    _fast_issues_file.write_text(_json_int.dumps(_fast_output, indent=2))
                    # Convert integration issues to harness static defect format (same as --integration-issues warm-start)
                    _fast_harness_defects = []
                    for _i, _d in enumerate(integration_fast_issues):
                        _fast_harness_defects.append({
                            'id':       _d.get('id', f'FAST-INT-{_i+1}'),
                            'severity': _d.get('severity', 'HIGH'),
                            'file':     _d.get('file', ''),
                            'issue':    _d.get('issue', _d.get('evidence', '')),
                            'fix':      _d.get('fix', ''),
                            'related_files': [f for f in _d.get('files', []) if f != _d.get('file', '')],
                        })
                    previous_defects     = self._format_static_defects_for_claude(_fast_harness_defects)
                    defect_source        = 'integration'
                    _raw_pending_defects = _fast_harness_defects
                    iteration += 1
                    if iteration > self.max_qa_iterations:
                        print_error(f"Max iterations ({self.max_qa_iterations}) reached during INTEGRATION_FAST — halting")
                        self._print_cost_summary(
                            iteration - 1, total_calls, total_cache_writes, total_cache_hits,
                            total_cache_write_tokens, total_cache_read_tokens,
                            total_input_tokens, total_output_tokens,
                            total_gpt_calls, total_gpt_input_tokens, total_gpt_output_tokens,
                            run_end_reason='MAX_ITERATIONS'
                        )
                        _flush_gate_trace()
                        return False, "MAX_ITERATIONS_EXCEEDED"
                    print_info(f"Starting iteration {iteration} with structural fix...")
                    continue
                print_success("  [INTEGRATION_FAST] PASS — no structural issues found")
                _record_gate('INTEGRATION_FAST', 'PASS', 'no structural issues', iteration)

                # ================================================
                # STEP 3: GATE 3 AI CONSISTENCY (LOCKABLE)
                # ================================================
                print_info("")
                print_info("═══════════════════════════════════════════════════════════")
                print_info("GATE 3: AI CONSISTENCY CHECK — Cross-file analysis")
                print_info("═══════════════════════════════════════════════════════════")

                _run_consistency = True
                if self.factory_mode:
                    print_info("  [CONSISTENCY] SKIPPED — factory mode")
                    _record_gate('CONSISTENCY', 'SKIPPED', 'factory mode', iteration)
                    _run_consistency = False
                elif gate_locks['CONSISTENCY'] and iteration > 1:
                    _changed = _files_changed_in_last_fix(_cur_artifact_manifest, _prev_artifact_manifest)
                    _relevant = any(
                        'models/' in f or 'services/' in f or 'routes/' in f or 'schemas/' in f
                        for f in _changed
                    )
                    if _relevant:
                        gate_locks['CONSISTENCY'] = False
                        print_info("  [CONSISTENCY] UNLOCKED — relevant files changed, re-running")
                        _record_gate('CONSISTENCY', 'UNLOCK', 'relevant files changed', iteration)
                    else:
                        print_info("  [CONSISTENCY] LOCKED — skipped, no relevant files changed")
                        _record_gate('CONSISTENCY', 'LOCKED', 'no relevant files changed', iteration)
                        _run_consistency = False

                if _run_consistency:
                    _record_gate('CONSISTENCY', 'START', 'running AI consistency check', iteration)
                consistency_issues = self._run_ai_consistency_check(iteration, governance_section) if _run_consistency else []
                if consistency_issues:
                    consistency_all = consistency_issues
                    consistency_issues = self._prioritize_and_cap_defects(consistency_all)
                    if len(consistency_all) > len(consistency_issues):
                        print_warning(
                            f"  [CONSISTENCY] Prioritized {len(consistency_issues)} of {len(consistency_all)} issues for this iteration"
                        )
                    _record_gate('CONSISTENCY', 'FAIL', f'{len(consistency_issues)} issue(s)', iteration)
                    print_warning(f"  [CONSISTENCY] FAIL — {len(consistency_issues)} issue(s)")
                    for iss in consistency_issues:
                        sev_fn = print_error if iss.get('severity') == 'HIGH' else print_warning
                        sev_fn(f"    {iss['id']} [{iss.get('severity', 'MEDIUM')}] "
                               f"{iss.get('files', iss.get('file', '?'))}: {iss.get('issue', '?')}")

                    _consistency_consecutive_iters += 1

                    # Consistency hard cap — always fall through to Feature QA.
                    # Full-build escalation is removed: a full regeneration for 1 stubborn
                    # CONSISTENCY issue causes Claude to invent new wrong-path architectures
                    # (app/, backend/) from scratch, destroying all prior surgical fixes.
                    # QA is the authoritative validator — if a CONSISTENCY issue is a real
                    # AttributeError it will surface as a QA defect with concrete evidence.
                    if _consistency_consecutive_iters >= Config.MAX_CONSISTENCY_CONSECUTIVE:
                        _high_consistency = [i for i in consistency_issues
                                             if i.get('severity', 'HIGH') == 'HIGH']
                        high_note = f" ({len(_high_consistency)} HIGH remain)" if _high_consistency else ""
                        print_warning(
                            f"  [CONSISTENCY] Hard cap reached{high_note} — falling through to Feature QA"
                        )
                        _record_gate('CONSISTENCY', 'FALLTHROUGH',
                                     f'cap={Config.MAX_CONSISTENCY_CONSECUTIVE} reached — falling through to QA',
                                     iteration)
                        _consistency_consecutive_iters = 0
                        defect_source        = 'qa'
                        previous_defects     = None
                        _raw_pending_defects = []
                        # Fall through to GATE 4 + Feature QA this iteration
                    else:
                        defect_source        = 'consistency'
                        _raw_pending_defects = consistency_issues
                        # Sharpen fix fields before formatting: specifies which file changes,
                        # exact function, exact line change. Prevents Claude picking the wrong
                        # side of the A <-> B mismatch or making an ambiguous change.
                        _sharpened_consistency = self._sharpen_consistency_issues(
                            consistency_issues, iteration
                        )
                        previous_defects     = self._format_consistency_defects_for_claude(_sharpened_consistency)
                        iteration += 1
                        if iteration > self.max_qa_iterations:
                            print_error(f"Max iterations ({self.max_qa_iterations}) reached during consistency check — halting")
                            self._print_cost_summary(
                                iteration - 1, total_calls, total_cache_writes, total_cache_hits,
                                total_cache_write_tokens, total_cache_read_tokens,
                                total_input_tokens, total_output_tokens,
                                total_gpt_calls, total_gpt_input_tokens, total_gpt_output_tokens,
                                run_end_reason='MAX_ITERATIONS'
                            )
                            _flush_gate_trace()
                            return False, "MAX_ITERATIONS_EXCEEDED"
                        print_info(f"Starting iteration {iteration} with consistency fix...")
                        continue
                else:
                    _consistency_consecutive_iters = 0

                if not consistency_issues:
                    if _run_consistency:
                        print_success("  [CONSISTENCY] PASS — no cross-file consistency issues")
                        _record_gate('CONSISTENCY', 'PASS', 'no consistency issues', iteration)
                    gate_locks['CONSISTENCY'] = True

                # ================================================
                # STEP 4: GATE 4 QUALITY (LOCKABLE)
                # ================================================
                print_info("")
                print_info("═══════════════════════════════════════════════════════════")
                print_info("GATE 4: QUALITY GATE — Completeness/Quality/Enhanceability/Deployability")
                print_info("═══════════════════════════════════════════════════════════")

                _run_quality = True
                if build_mode == 'repair':
                    print_info(f"  [QUALITY] SKIPPED — repair mode, iteration {iteration} of {self.max_qa_iterations}")
                    _record_gate('QUALITY', 'SKIPPED', f'repair mode iter={iteration}', iteration)
                    _run_quality = False
                elif gate_locks['QUALITY'] and iteration > 1:
                    _changed = _files_changed_in_last_fix(_cur_artifact_manifest, _prev_artifact_manifest)
                    _relevant = any('business/' in f for f in _changed)
                    if _relevant:
                        gate_locks['QUALITY'] = False
                        print_info("  [QUALITY] UNLOCKED — business files changed, re-running")
                        _record_gate('QUALITY', 'UNLOCK', 'business files changed', iteration)
                    else:
                        print_info("  [QUALITY] LOCKED — skipped, no business files changed")
                        _record_gate('QUALITY', 'LOCKED', 'no business files changed', iteration)
                        _run_quality = False

                if _run_quality:
                    _record_gate('QUALITY', 'START', 'running acceptance-mode quality gate', iteration)
                quality_issues, quality_usage = self._run_quality_gate(iteration) if _run_quality else ([], {})
                # account for extra ChatGPT call in cost summary (only when gate actually ran)
                if _run_quality:
                    total_gpt_calls += 1
                    total_gpt_input_tokens += int(quality_usage.get('input_tokens', 0) or 0)
                    total_gpt_output_tokens += int(quality_usage.get('output_tokens', 0) or 0)
                if quality_issues:
                    quality_all = quality_issues
                    quality_issues = self._prioritize_and_cap_defects(quality_all)
                    if len(quality_all) > len(quality_issues):
                        print_warning(
                            f"  [QUALITY] Prioritized {len(quality_issues)} of {len(quality_all)} issues for this iteration"
                        )
                    _record_gate('QUALITY', 'FAIL', f'{len(quality_issues)} issue(s)', iteration)
                    print_warning(f"  [QUALITY] FAIL — {len(quality_issues)} issue(s)")
                    for iss in quality_issues:
                        sev_fn = print_error if iss.get('severity') == 'HIGH' else print_warning
                        sev_fn(f"    {iss['id']} [{iss.get('severity', 'MEDIUM')}] "
                               f"{iss.get('files', iss.get('file', '?'))}: {iss.get('issue', '?')}")
                    defect_source        = 'quality'
                    _raw_pending_defects = quality_issues
                    previous_defects     = self._format_consistency_defects_for_claude(quality_issues)
                    iteration += 1
                    if iteration > self.max_qa_iterations:
                        print_error(f"Max iterations ({self.max_qa_iterations}) reached during quality gate — halting")
                        self._print_cost_summary(
                            iteration - 1, total_calls, total_cache_writes, total_cache_hits,
                            total_cache_write_tokens, total_cache_read_tokens,
                            total_input_tokens, total_output_tokens,
                            total_gpt_calls, total_gpt_input_tokens, total_gpt_output_tokens,
                            run_end_reason='MAX_ITERATIONS'
                        )
                        _flush_gate_trace()
                        return False, "MAX_ITERATIONS_EXCEEDED"
                    print_info(f"Starting iteration {iteration} with quality-gate fixes...")
                    continue
                if _run_quality:
                    print_success("  [QUALITY] PASS — all 4 dimensions acceptable")
                    _record_gate('QUALITY', 'PASS', 'all dimensions pass', iteration)
                    if build_mode == 'acceptance':
                        _quality_ran_in_acceptance_mode = True
                gate_locks['QUALITY'] = True

                # ================================================
                # STEP 5: GATE 5 FEATURE QA (ChatGPT, LOCKABLE)
                # ================================================

                _run_feature_qa = True
                if gate_locks['FEATURE_QA'] and iteration > 1:
                    _changed = _files_changed_in_last_fix(_cur_artifact_manifest, _prev_artifact_manifest)
                    _relevant = any('business/' in f for f in _changed)
                    if _relevant:
                        gate_locks['FEATURE_QA'] = False
                        print_info("  [FEATURE_QA] UNLOCKED — business files changed, re-running")
                        _record_gate('FEATURE_QA', 'UNLOCK', 'business files changed', iteration)
                    else:
                        print_info("  [FEATURE_QA] LOCKED — skipped, no business files changed")
                        _record_gate('FEATURE_QA', 'LOCKED', 'no business files changed', iteration)
                        _run_feature_qa = False

                if not _run_feature_qa:
                    # Treat locked FEATURE_QA as ACCEPTED — gates already passed and no files changed
                    print_success("  [FEATURE_QA] LOCKED — treating as ACCEPTED (no files changed since last pass)")
                    qa_report = "QA STATUS: ACCEPTED - Ready for deployment (gate locked — no changes)"
                else:
                    # On iteration 2+, optionally wait for the OpenAI TPM window to reset.
                    # Use --qa-wait <seconds> if hitting 429s on multi-iteration runs.
                    _qa_wait = int(getattr(self.cli_args, 'qa_wait', 0) or 0)
                    if iteration > 1 and _qa_wait > 0:
                        print_info(f"Waiting {_qa_wait}s for OpenAI TPM window to reset before QA call...")
                        time.sleep(_qa_wait)

                    print_info("Calling ChatGPT for QA...")
                    _record_gate('FEATURE_QA', 'START', 'calling ChatGPT', iteration)

                    # For defect iterations in boilerplate mode, QA receives the full merged
                    # artifact set (not Claude's partial defect-only output) so it evaluates
                    # the complete picture rather than just the 1-3 files Claude patched.
                    if self.use_boilerplate and iteration > 1 and previous_defects:
                        qa_build_output = self.artifacts.build_synthetic_qa_output(iteration)
                    else:
                        qa_build_output = build_output

                    # Prepend any EXPLAINED resolutions from Claude's patch output so QA
                    # can evaluate them before assessing the artifact set (per governance:
                    # fo_build_qa_defect_routing_rules.json > remediate_or_explain).
                    if iteration > 1:
                        defect_resolutions = self._extract_defect_resolutions(build_output)
                        if defect_resolutions:
                            qa_build_output = (
                                "## CLAUDE DEFECT RESOLUTIONS\n\n"
                                "Claude resolved some defects via EXPLAINED (governance citation) "
                                "rather than code changes. Evaluate each before assessing artifacts.\n\n"
                                + defect_resolutions
                                + "\n\n---\n\n"
                                + qa_build_output
                            )

                    qa_prompt = PromptTemplates.qa_prompt(
                        qa_build_output,
                        self.intake_data,
                        self.block,
                        self.effective_tech_stack,
                        self.qa_override,
                        prohibitions_block=prohibitions_block,
                        defect_history_block=self._build_qa_defect_history(recurring_tracker),
                        resolved_defects_block=self._build_resolved_defects_block(resolved_tracker),
                        ubiquitous_language_block=self.ubiquitous_language_block
                    )

                    self.artifacts.save_log(f'iteration_{iteration:02d}_qa_prompt', qa_prompt)

                    start_time = time.time()
                    try:
                        # Repair mode: pass focused rules via system role (not inline — preserves prompt hierarchy)
                        _qa_system_msg = REPAIR_MODE_RULES if build_mode == 'repair' else None
                        qa_response = self.chatgpt.call(qa_prompt, system_message=_qa_system_msg)
                        qa_report   = qa_response['choices'][0]['message']['content']
                        qa_time     = time.time() - start_time
                        print_success(f"QA completed in {qa_time:.1f}s")

                        # Log ChatGPT usage and accumulate stats
                        gpt_usage = self._log_chatgpt_usage(qa_response, iteration)
                        total_gpt_calls += 1
                        total_gpt_input_tokens += gpt_usage['input_tokens']
                        total_gpt_output_tokens += gpt_usage['output_tokens']

                        # Filter fabricated / out-of-scope defects before acting on report
                        raw_qa_report = qa_report
                        qa_report = self._filter_hallucinated_defects(qa_report, qa_build_output)
                        if qa_report != raw_qa_report:
                            self.artifacts.save_log(
                                f'iteration_{iteration:02d}_qa_report_raw', raw_qa_report
                            )

                        # Triage and sharpen surviving defects before triggering a build.
                        # Classifies each defect as SURGICAL (line-level fix) / SYSTEMIC (architectural
                        # rethink) / INVALID (scope creep). Sharpens vague Fix fields into exact
                        # function+line instructions so Claude doesn't have to guess. Stores strategy
                        # in _triage_strategy for prompt routing on the next iteration.
                        if "QA STATUS: REJECTED" in qa_report:
                            _triage_file_contents = self._read_target_file_contents(
                                iteration,
                                [d['location'] for d in self._extract_defects_for_tracking(qa_report)]
                            )
                            qa_report, _triage_strategy, _triage_contested = self._triage_and_sharpen_defects(
                                qa_report, iteration, recurring_tracker, _triage_file_contents
                            )
                            if _triage_contested:
                                self.artifacts.save_log(
                                    f'iteration_{iteration:02d}_triage_contested',
                                    '\n'.join(
                                        f"DEFECT-{c['defect']} @ {c['location']}: {c['reason']}"
                                        for c in _triage_contested
                                    )
                                )
                            if _triage_strategy == 'accepted':
                                # All remaining defects were invalid — flip verdict without another build
                                qa_report = qa_report.replace(
                                    'QA STATUS: REJECTED', 'QA STATUS: ACCEPTED [TRIAGE-CLEARED]'
                                )
                                print_success(
                                    f"  [TRIAGE] Verdict flipped to ACCEPTED — all defects invalid/out-of-scope"
                                )

                        # Confirm pending resolutions: any FIXED defect absent from this QA → resolved
                        if pending_resolution:
                            newly_confirmed, pending_resolution = self._confirm_resolutions(
                                pending_resolution, qa_report, resolved_tracker, iteration
                            )
                            for loc, cls in newly_confirmed:
                                print_success(
                                    f"  [RESOLVED] {loc} ({cls}) confirmed fixed — added to resolved list"
                                )
                            if pending_resolution:
                                reappeared = [loc for loc, cls, _ in pending_resolution]
                                print_warning(
                                    f"  [PING-PONG] {len(pending_resolution)} defect(s) Claude claimed FIXED "
                                    f"but QA re-flagged: {', '.join(reappeared)}"
                                )

                        self.artifacts.save_qa_report(iteration, qa_report)

                    except Exception as e:
                        print_error(f"QA failed: {e}")
                        return False, str(e)

                # ================================================
                # STEP 3: CHECK QA VERDICT
                # ================================================

                if "QA STATUS: ACCEPTED" in qa_report:
                    # ── Steal 1.5: Dual-Condition Exit ──────────────────
                    # QA said ACCEPTED, but verify no CRITICAL/HIGH defects
                    # remain in the structured defect list. Prevents false
                    # acceptance when ChatGPT says "looks good" but lists defects.
                    _residual_defects = self._extract_defects_for_tracking(qa_report)
                    _residual_high = [
                        d for d in _residual_defects
                        if d.get('classification', '').upper() in (
                            'IMPLEMENTATION_BUG', 'SPEC_COMPLIANCE_ISSUE',
                            'MISSING_FEATURE', 'CRITICAL', 'HIGH'
                        )
                    ]
                    if _residual_high:
                        # QA said ACCEPTED but listed critical defects — treat as REJECTED
                        print_warning(
                            f"  [DUAL-EXIT] QA said ACCEPTED but {len(_residual_high)} "
                            f"CRITICAL/HIGH defect(s) found in report — overriding to REJECTED"
                        )
                        for rd in _residual_high:
                            print_warning(f"    → {rd['location']}: {rd['classification']}")
                        _record_gate('FEATURE_QA', 'FAIL',
                                     f'dual-exit override: {len(_residual_high)} residual defects', iteration)
                        # Fall through to the REJECTED branch below
                        qa_report = qa_report.replace(
                            'QA STATUS: ACCEPTED',
                            f'QA STATUS: REJECTED [DUAL-EXIT: {len(_residual_high)} residual defects]'
                        )
                    else:
                        _record_gate('FEATURE_QA', 'PASS', 'QA accepted (dual-exit clean)', iteration)

                    if "QA STATUS: ACCEPTED" in qa_report:
                        print_success(f"GATE 1 PASSED: Feature QA ACCEPTED on iteration {iteration}")
                        # Mark all features as passing on acceptance
                        for fs in _feature_state:
                            if fs['status'] != 'passing':
                                fs['status'] = 'passing'
                                fs['passed_since_iter'] = iteration
                        _qa_accepted_at_iter = iteration
                        gate_locks['FEATURE_QA'] = True

                        # ── Acceptance gate check: QUALITY must have run in acceptance mode ──────
                        if not _quality_ran_in_acceptance_mode:
                            print_warning("  [ACCEPTANCE] QUALITY gate has not run in acceptance mode yet — forcing acceptance mode now")
                            _record_gate('QUALITY', 'FORCE_RUN', 'required before acceptance', iteration)
                            quality_issues_final, quality_usage_final = self._run_quality_gate(iteration)
                            total_gpt_calls += 1
                            total_gpt_input_tokens += int(quality_usage_final.get('input_tokens', 0) or 0)
                            total_gpt_output_tokens += int(quality_usage_final.get('output_tokens', 0) or 0)
                            if quality_issues_final:
                                quality_issues_final = self._prioritize_and_cap_defects(quality_issues_final)
                                print_warning(f"  [QUALITY] Forced run found {len(quality_issues_final)} issue(s) — cannot accept")
                                _record_gate('QUALITY', 'FAIL', f'{len(quality_issues_final)} issue(s) on forced acceptance check', iteration)
                                defect_source        = 'quality'
                                _raw_pending_defects = quality_issues_final
                                previous_defects     = self._format_consistency_defects_for_claude(quality_issues_final)
                                iteration += 1
                                if iteration > self.max_qa_iterations:
                                    self._print_cost_summary(
                                        iteration - 1, total_calls, total_cache_writes, total_cache_hits,
                                        total_cache_write_tokens, total_cache_read_tokens,
                                        total_input_tokens, total_output_tokens,
                                        total_gpt_calls, total_gpt_input_tokens, total_gpt_output_tokens,
                                        run_end_reason='MAX_ITERATIONS'
                                    )
                                    _flush_gate_trace()
                                    return False, "MAX_ITERATIONS_EXCEEDED"
                                continue
                            else:
                                print_success("  [QUALITY] Forced acceptance-mode run: PASS")
                                _record_gate('QUALITY', 'PASS', 'forced acceptance-mode run passed', iteration)
                                _quality_ran_in_acceptance_mode = True

                        # ── All gates passed ──────────────────────────────────────────
                        print_success("")
                        print_success("══════════════════════════════════════════════════════════")
                        print_success("ALL QA GATES PASSED: Compile + Static + AI Consistency + Quality + Feature QA")
                        print_success("══════════════════════════════════════════════════════════")
                        _loop_success = True
                        break

                    # Dual-exit overrode ACCEPTED → treat as REJECTED, fall through
                elif "QA STATUS: REJECTED" in qa_report:
                    _record_gate('FEATURE_QA', 'FAIL', 'QA rejected', iteration)
                    # Feature QA rejected — reset defect source to 'qa' and repair
                    defect_source        = 'qa'
                    _raw_pending_defects = []
                    print_warning("QA REJECTED — defects found")

                    # Brackets in QA verdict e.g. "[4] defects require" — handle both formats
                    defect_match = re.search(r'\[?(\d+)\]? defects? require', qa_report)
                    current_defect_count = 0
                    if defect_match:
                        current_defect_count = int(defect_match.group(1))
                        print_warning(f"  → {current_defect_count} defects to fix")

                    # Print detailed defects to screen
                    self._print_defects_summary(qa_report, iteration)

                    # Track defect count for convergence detection
                    defect_history.append(current_defect_count)

                    # ── Circuit Breaker check (Steal 1.1) ──
                    # Run after defects are known and artifacts are extracted.
                    # Uses the artifact manifest from this iteration + parsed defects.
                    _cb_cur_manifest = _load_iteration_manifest(iteration)
                    _cb_cur_bytes = sum(
                        len((self.artifacts.build_dir / f'iteration_{iteration:02d}_artifacts' / p).read_bytes())
                        for p in _cb_cur_manifest
                        if (self.artifacts.build_dir / f'iteration_{iteration:02d}_artifacts' / p).exists()
                    ) if _cb_cur_manifest else 0
                    _cb_cur_defects = self._extract_defects_for_tracking(qa_report)

                    _cb_tripped, _cb_status, _cb_detail = _cb_check(
                        _cb_cur_manifest, _cb_cur_defects, _cb_cur_bytes, iteration
                    )
                    if _cb_tripped:
                        print_error(f"CIRCUIT BREAKER OPEN: {_cb_status}")
                        print_error(f"  {_cb_detail}")

                        # Write detailed report for post-mortem
                        cb_report = {
                            'status': _cb_status,
                            'detail': _cb_detail,
                            'iteration': iteration,
                            'defect_history': defect_history,
                            'defect_fingerprints': {
                                fp: count for fp, count in _cb_defect_fingerprints.items() if count > 0
                            },
                            'artifact_byte_count': _cb_cur_bytes,
                            'timestamp': datetime.now().isoformat(),
                        }
                        try:
                            cb_report_path = self.run_dir / 'circuit_breaker_report.json'
                            with open(cb_report_path, 'w') as f:
                                json.dump(cb_report, f, indent=2)
                            print_info(f"  → Circuit breaker report: {cb_report_path}")
                        except Exception:
                            pass

                        self._save_run_status(
                            status=_cb_status,
                            iteration=iteration,
                            reason=_cb_detail,
                            defect_count=current_defect_count,
                        )
                        self._print_cost_summary(
                            iteration, total_calls, total_cache_writes, total_cache_hits,
                            total_cache_write_tokens, total_cache_read_tokens,
                            total_input_tokens, total_output_tokens,
                            total_gpt_calls, total_gpt_input_tokens, total_gpt_output_tokens,
                            run_end_reason=_cb_status
                        )
                        _run_final_consistency_if_needed(iteration, governance_section if 'governance_section' in locals() else '')
                        _flush_gate_trace()
                        return False, _cb_status

                    # ── Feature state update (Steal 4.1) ──
                    # Map defects to features by file path; mark features passing/failing.
                    _update_feature_state(_cb_cur_defects, iteration)

                    # Check for convergence after several iterations.
                    # Use len(defect_history) — not the absolute iteration number — so that
                    # resumed runs aren't penalised for iterations from a previous process.
                    if len(defect_history) >= convergence_check_after:
                        # Check if defects are oscillating or not decreasing
                        recent_defects = defect_history[-5:]  # Last 5 iterations
                        avg_recent = sum(recent_defects) / len(recent_defects)

                        # If average defects in last 5 iterations is >= first 5 iterations, not converging
                        if len(defect_history) >= 15:
                            early_defects = defect_history[:5]
                            avg_early = sum(early_defects) / len(early_defects) if early_defects else 0

                            if avg_recent >= avg_early:
                                print_error(f"Loop not converging after {iteration} iterations")
                                print_error(f"  → Early defects (avg): {avg_early:.1f}")
                                print_error(f"  → Recent defects (avg): {avg_recent:.1f}")
                                print_error(f"  → Defect history: {defect_history}")
                                print_warning("Possible causes:")
                                print_warning("  1. Intake requirements too vague (no data model specs)")
                                print_warning("  2. QA flagging reasonable inferences as scope creep")
                                print_warning("  3. Claude fixes introduce new problems (whack-a-mole)")
                                print_warning("Recommendation: Review intake for ambiguity or adjust QA strictness")

                                # Still print cost summary
                                self._save_run_status(
                                    status='NON_CONVERGING',
                                    iteration=iteration,
                                    reason='Defect count not decreasing',
                                    detail=f'Early avg: {avg_early:.1f}, Recent avg: {avg_recent:.1f}, History: {defect_history}',
                                    defect_count=defect_history[-1] if defect_history else None,
                                )
                                self._print_cost_summary(
                                    iteration, total_calls, total_cache_writes, total_cache_hits,
                                    total_cache_write_tokens, total_cache_read_tokens,
                                    total_input_tokens, total_output_tokens,
                                    total_gpt_calls, total_gpt_input_tokens, total_gpt_output_tokens,
                                    run_end_reason='NON_CONVERGING'
                                )
                                _run_final_consistency_if_needed(iteration, governance_section if 'governance_section' in locals() else '')
                                _flush_gate_trace()
                                return False, "NON_CONVERGING_DEFECTS"

                    # FIX #9: Show cumulative cost after each QA iteration
                    self._display_cumulative_cost(
                        iteration, total_calls, total_cache_writes, total_cache_hits,
                        total_cache_read_tokens, total_cache_write_tokens,
                        total_input_tokens, total_output_tokens,
                        total_gpt_calls, total_gpt_input_tokens, total_gpt_output_tokens
                    )

                    previous_defects = self._enrich_defects_with_fix_context(qa_report)

                    # ── Steal 4.1: Feature status preamble ──
                    # Prepend feature pass/fail summary to defects so Claude knows
                    # which features are working and which need fixing.
                    _feat_preamble = _build_feature_preamble()
                    if _feat_preamble:
                        previous_defects = _feat_preamble + "\n" + previous_defects

                    # Track recurrence — promote to prohibition after 2+ appearances
                    for d in self._extract_defects_for_tracking(qa_report):
                        key = (d['location'], d['classification'])
                        if key not in recurring_tracker:
                            recurring_tracker[key] = {'count': 0, 'last_problem': '', 'last_fix': '', 'last_seen': 0}
                        recurring_tracker[key]['count'] += 1
                        recurring_tracker[key]['last_problem'] = d['problem']
                        recurring_tracker[key]['last_fix']     = d['fix']
                        recurring_tracker[key]['last_seen']    = iteration

                    # ── Steal 1.3: Bound reflection memory ──────────────
                    # Prune defects not seen in the last 2 iterations from
                    # recurring_tracker. Keeps prohibitions lean — old defects
                    # that were genuinely fixed don't bloat the prompt forever.
                    # Entries with count >= 3 are kept regardless (true systemic).
                    _RECENCY_WINDOW = 2
                    stale_keys = [
                        k for k, v in recurring_tracker.items()
                        if v.get('last_seen', 0) < iteration - _RECENCY_WINDOW
                        and v['count'] < 3
                    ]
                    for k in stale_keys:
                        del recurring_tracker[k]
                    if stale_keys:
                        print_info(f"  [MEMORY] Pruned {len(stale_keys)} stale defect(s) from tracker (not seen in last {_RECENCY_WINDOW} iterations)")

                    prohibitions_block = self._build_prohibitions_block(recurring_tracker)
                    if prohibitions_block:
                        promoted = sum(1 for v in recurring_tracker.values() if v['count'] >= 2)
                        print_warning(f"  [PROHIBITIONS] {promoted} recurring defect(s) promoted to hard prohibition")

                    iteration       += 1

                    if iteration > self.max_qa_iterations:
                        print_error(f"Max iterations ({self.max_qa_iterations}) reached — loop failed to converge")

                        self._save_run_status(
                            status='MAX_ITERATIONS',
                            iteration=iteration - 1,
                            reason=f'Hit cap of {self.max_qa_iterations} iterations',
                            defect_count=defect_history[-1] if defect_history else None,
                        )
                        # FIX #1: Print cost summary even on failure
                        self._print_cost_summary(
                            iteration - 1, total_calls, total_cache_writes, total_cache_hits,
                            total_cache_write_tokens, total_cache_read_tokens,
                            total_input_tokens, total_output_tokens,
                            total_gpt_calls, total_gpt_input_tokens, total_gpt_output_tokens,
                            run_end_reason='MAX_ITERATIONS'
                        )
                        _run_final_consistency_if_needed(iteration - 1, governance_section if 'governance_section' in locals() else '')
                        _flush_gate_trace()
                        return False, "MAX_ITERATIONS_EXCEEDED"

                    print_info(f"Starting iteration {iteration} with defect fixes...")
                    continue

                else:
                    _record_gate('FEATURE_QA', 'ERROR', 'verdict unclear', iteration)
                    print_error("QA report format invalid — no clear ACCEPTED/REJECTED verdict")
                    self._save_run_status(
                        status='QA_VERDICT_UNCLEAR',
                        iteration=iteration,
                        reason='QA report had no clear ACCEPTED/REJECTED verdict',
                    )
                    self._print_cost_summary(
                        iteration, total_calls, total_cache_writes, total_cache_hits,
                        total_cache_write_tokens, total_cache_read_tokens,
                        total_input_tokens, total_output_tokens,
                        total_gpt_calls, total_gpt_input_tokens, total_gpt_output_tokens,
                        run_end_reason='QA_VERDICT_UNCLEAR'
                    )
                    _run_final_consistency_if_needed(iteration, governance_section if 'governance_section' in locals() else '')
                    _flush_gate_trace()
                    return False, "QA_VERDICT_UNCLEAR"

            # ── Save feature state for post-mortem (Steal 4.1) ──
            if _feature_state:
                try:
                    fs_path = self.run_dir / 'feature_state.json'
                    with open(fs_path, 'w') as f:
                        json.dump(_feature_state, f, indent=2)
                    passing = sum(1 for fs in _feature_state if fs['status'] == 'passing')
                    failing = sum(1 for fs in _feature_state if fs['status'] == 'failing')
                    print_info(f"  Feature state saved: {passing} passing, {failing} failing → {fs_path}")
                except Exception:
                    pass

            # ── Post-loop: called only via break (all gates passed or max-iter during static/consistency) ──
            if _qa_accepted_at_iter is not None:
                # ── Post-QA polish step: generate missing optional files ────────────
                if self.skip_polish:
                    print_info("  [POLISH] Skipped (--no-polish)")
                    polish_success = False
                    polish_cost = {}
                else:
                    polish_success, polish_cost = self._post_qa_polish(
                        iteration, build_output, governance_section
                    )
                if polish_success:
                    total_calls             += polish_cost['calls']
                    total_input_tokens      += polish_cost['input_tokens']
                    total_output_tokens     += polish_cost['output_tokens']
                    if polish_cost['cache_read_tokens'] > 0:
                        total_cache_hits        += 1
                        total_cache_read_tokens += polish_cost['cache_read_tokens']

                end_reason = 'QA_ACCEPTED' if _loop_success else 'MAX_ITERATIONS'
                self._save_run_status(
                    status=end_reason,
                    iteration=iteration,
                    accepted_at_iteration=_qa_accepted_at_iter,
                    reason='All gates passed' if _loop_success else 'QA accepted but max iterations hit during static/consistency',
                )
                self._print_cost_summary(
                    iteration, total_calls, total_cache_writes, total_cache_hits,
                    total_cache_write_tokens, total_cache_read_tokens,
                    total_input_tokens, total_output_tokens,
                    total_gpt_calls, total_gpt_input_tokens, total_gpt_output_tokens,
                    run_end_reason=end_reason
                )
                if not _loop_success:
                    _run_final_consistency_if_needed(iteration, governance_section if 'governance_section' in locals() else '')
                _flush_gate_trace()
                return _loop_success, build_output

        except KeyboardInterrupt:
            _record_gate('HARNESS', 'INTERRUPTED', 'Ctrl+C', iteration)
            print_error("\n\n⚠️  BUILD INTERRUPTED (Ctrl+C)")
            print_info(f"Stopped at iteration {iteration}")
            self._save_run_status(
                status='INTERRUPTED',
                iteration=iteration,
                reason='Ctrl+C',
                defect_count=defect_history[-1] if defect_history else None,
            )
            # Show final cost before exiting
            self._display_cumulative_cost(
                iteration, total_calls, total_cache_writes, total_cache_hits,
                total_cache_read_tokens, total_cache_write_tokens,
                total_input_tokens, total_output_tokens,
                total_gpt_calls, total_gpt_input_tokens, total_gpt_output_tokens
            )
            # Log interrupted run to CSV
            cache_write_cost = (total_cache_write_tokens / 1_000_000) * 3.75
            cache_read_cost = (total_cache_read_tokens / 1_000_000) * 0.30
            non_cached_input_cost = ((total_input_tokens - total_cache_read_tokens) / 1_000_000) * 3.00
            output_cost = (total_output_tokens / 1_000_000) * 15.00
            claude_cost = cache_write_cost + cache_read_cost + non_cached_input_cost + output_cost
            gpt_cost = ((total_gpt_input_tokens / 1_000_000) * 2.50) + ((total_gpt_output_tokens / 1_000_000) * 10.00)
            self._log_run_csv(iteration, claude_cost, gpt_cost, 'CTRL_C')
            _flush_gate_trace('gate_telemetry_interrupt')
            raise  # Re-raise to propagate

        return False, "Should not reach here"

    def execute_deploy(self, build_output: str) -> bool:
        """Execute deployment phase (only called when --deploy is passed)"""

        print_header("STARTING DEPLOYMENT")

        deploy_prompt = PromptTemplates.deploy_prompt(build_output, self.deploy_governance)
        self.artifacts.save_log('deploy_prompt', deploy_prompt)

        print_info("Calling Claude for DEPLOYMENT...")
        start_time = time.time()

        try:
            deploy_response = self.claude.call(deploy_prompt)
            deploy_output   = deploy_response['content'][0]['text']
            deploy_time     = time.time() - start_time
            print_success(f"DEPLOY completed in {deploy_time:.1f}s")
            self.artifacts.save_deploy_output(deploy_output)

            if "DEPLOYMENT STATE: DEPLOYED" in deploy_output:
                print_success("DEPLOYMENT SUCCESSFUL")
                return True
            elif "DEPLOYMENT STATE: DEPLOY_FAILED" in deploy_output:
                print_error("DEPLOYMENT FAILED")
                return False
            else:
                print_warning("Deployment status unclear — no terminal state marker found")
                return False

        except Exception as e:
            print_error(f"DEPLOY failed: {e}")
            return False

    def run(self) -> bool:
        """Run complete BUILD → QA → (ZIP or DEPLOY) pipeline"""

        overall_start = time.time()

        # BUILD → QA loop
        qa_success, build_output = self.execute_build_qa_loop()

        # Questions detected — already logged, exit cleanly
        if not qa_success and build_output == "QUESTIONS_DETECTED":
            self.print_summary(False, time.time() - overall_start, reason="QUESTIONS_DETECTED")
            return False

        if not qa_success:
            print_error("BUILD → QA loop failed")
            self.print_summary(False, time.time() - overall_start, reason=build_output)
            return False

        # Generate artifact manifest
        self.artifacts.generate_manifest()

        if not self.do_deploy:
            # Default path — package ZIP, done
            zip_path = package_output_zip(self.run_dir, self.startup_id, self.block, self.use_boilerplate)
            self.print_summary(True, time.time() - overall_start, zip_path=zip_path)
            return True

        # Deploy path — only if --deploy was passed
        deploy_success = self.execute_deploy(build_output)

        if not deploy_success:
            print_error("DEPLOYMENT failed")
            self.print_summary(False, time.time() - overall_start, reason="DEPLOY_FAILED")
            return False

        self.print_summary(True, time.time() - overall_start, deployed=True)
        return True

    def print_summary(
        self,
        success:  bool,
        elapsed:  float,
        deployed: bool  = False,
        zip_path: Path  = None,
        reason:   str   = None
    ):
        """Print execution summary"""

        print_header("EXECUTION SUMMARY")

        print(f"Startup:        {self.startup_id}")
        print(f"Block:          BLOCK_{self.block}")
        print(f"Status:         {'✓ SUCCESS' if success else '✗ FAILED'}")
        print(f"Total time:     {elapsed:.1f}s ({elapsed/60:.1f} minutes)")
        print(f"Deployed:       {'Yes' if deployed else 'No'}")

        if reason:
            print(f"Reason:         {reason}")

        claude_cost  = getattr(self, '_last_claude_cost',  0.0)
        chatgpt_cost = getattr(self, '_last_chatgpt_cost', 0.0)
        print(f"Claude cost:    ${claude_cost:.2f}")
        print(f"ChatGPT cost:   ${chatgpt_cost:.2f}")
        print(f"Total cost:     ${claude_cost + chatgpt_cost:.2f}")

        if zip_path:
            print(f"ZIP output:     {zip_path}")

        print(f"")
        print(f"Run directory:  {self.run_dir}")
        print(f"")
        print(f"Generated files:")

        build_files  = len(list(self.artifacts.build_dir.rglob('*')))
        qa_files     = len(list(self.artifacts.qa_dir.rglob('*')))
        deploy_files = len(list(self.artifacts.deploy_dir.rglob('*')))
        log_files    = len(list(self.artifacts.logs_dir.rglob('*')))

        print(f"  - BUILD outputs:   {build_files}")
        print(f"  - QA reports:      {qa_files}")
        print(f"  - DEPLOY outputs:  {deploy_files}")
        print(f"  - Logs:            {log_files}")

        if success:
            print(f"\n{Colors.GREEN}{Colors.BOLD}✓ PIPELINE COMPLETED SUCCESSFULLY{Colors.END}")
        else:
            print(f"\n{Colors.RED}{Colors.BOLD}✗ PIPELINE FAILED{Colors.END}")


# ============================================================
# MAIN CLI
# ============================================================

def main():
    """Main entry point"""

    parser = argparse.ArgumentParser(
        description='FO Test Harness v2 — BUILD → QA → ZIP/DEPLOY',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Default: Block B, no deploy, ZIP output
  ./fo_test_harness.py intake.json build_rules.zip deploy_rules.zip

  # Block A (Tier 1), no deploy
  ./fo_test_harness.py intake.json build_rules.zip deploy_rules.zip --block-a

  # Block B, with deployment
  ./fo_test_harness.py intake.json build_rules.zip deploy_rules.zip --deploy

  # Block A, with deployment
  ./fo_test_harness.py intake.json build_rules.zip deploy_rules.zip --block-a --deploy
        """
    )

    # Positional args — optional so --static-check / --ai-check can run without them
    parser.add_argument(
        'intake_file',
        nargs='?',
        type=Path,
        default=None,
        help='Path to combined intake JSON (output of run_intake_v7.sh)'
    )
    parser.add_argument(
        'build_governance_zip',
        nargs='?',
        type=Path,
        default=None,
        help='Path to BUILD governance ZIP (FOBUILFINALLOCKED100.zip). Overridden by --buildzip.'
    )
    parser.add_argument(
        '--buildzip',
        type=Path,
        default=next((Path(p) for p in sorted(Path('.').glob('FOBUILFINALLOCKED*.zip'))), None),
        help='BUILD governance ZIP override (default: auto-detect FOBUILFINALLOCKED*.zip in cwd)'
    )
    # Optional flags
    # FIX #9: --block-a flag, default is Block B
    parser.add_argument(
        '--block-a',
        action='store_true',
        default=False,
        help='Build Block A (Tier 1). Default is Block B (Tier 2).'
    )

    # FIX #8: --deploy flag, default is NO deploy
    parser.add_argument(
        '--deploy',
        action='store_true',
        default=False,
        help='Execute deployment after QA acceptance. Default is ZIP output only.'
    )
    parser.add_argument(
        '--confirm-run-log',
        default='NO',
        help='Require confirmation before writing fo_run_log.csv (YES/NO). Default: NO'
    )
    parser.add_argument(
        '--qa-polish-2-directive',
        type=Path,
        default=None,
        help='Path to external QA_POLISH_2_DOC_RECOVERY directive file. '
             'Precedence: CLI path -> Config default path.'
    )
    parser.add_argument(
        '--qa-testcase-directive',
        type=Path,
        default=None,
        help='Path to external testcase-doc directive template used by post-QA polish. '
             'Precedence: CLI path -> Config default path.'
    )
    parser.add_argument(
        '--platform-boilerplate-dir',
        type=Path,
        default=Config.PLATFORM_BOILERPLATE_DIR,
        help='Path to teebu-saas-platform boilerplate root. '
             'Default: /Users/teebuphilip/Documents/work/teebu-saas-platform'
    )
    parser.add_argument(
        '--max-parts',
        type=int,
        default=Config.MAX_BUILD_PARTS_DEFAULT,
        help='Max multipart chunks to assemble from Claude in one iteration. Default: 10'
    )
    parser.add_argument(
        '--max-continuations',
        type=int,
        default=Config.MAX_BUILD_CONTINUATIONS_DEFAULT,
        help='Max fallback continuation calls when output is truncated. Default: 9'
    )
    parser.add_argument(
        '--max-iterations',
        type=int,
        default=Config.MAX_QA_ITERATIONS,
        help='Max BUILD→QA iterations for this run. Default: 5'
    )
    parser.add_argument(
        '--prior-run',
        type=str,
        default=None,
        dest='prior_run',
        help='Path to a prior run directory whose QA reports seed the prohibition tracker. '
             'Use in feature-by-feature builds to carry Phase 1 QA knowledge into feature runs.'
    )
    parser.add_argument(
        '--resume-run',
        type=str,
        default=None,
        help='Path to an existing run directory to resume (skips new dir creation).'
    )
    parser.add_argument(
        '--resume-iteration',
        type=int,
        default=1,
        help='Which iteration to resume from (used with --resume-run). Default: 1'
    )
    parser.add_argument(
        '--resume-mode',
        choices=['qa', 'fix', 'static', 'consistency'],
        default=None,
        help=(
            'qa          — skip Claude BUILD for --resume-iteration, run fresh QA on existing artifacts. '
            'fix         — load QA report from --resume-iteration as defects, start Claude FIX at iter+1. '
            'static      — find last QA-accepted iter (or use --resume-iteration), run static + AI consistency checks. '
            'consistency — find last QA-accepted iter, skip static check, run AI consistency check only.'
        )
    )
    parser.add_argument(
        '--integration-issues',
        type=str,
        default=None,
        metavar='JSON_FILE',
        help=(
            'Path to integration_issues.json produced by integration_check.py. '
            'Seeds a targeted Claude fix pass with integration defects (missing routes, '
            'model field gaps, spec mismatches) then runs the full QA loop. '
            'Use with --resume-run + --resume-iteration to target the accepted iteration.'
        )
    )
    parser.add_argument(
        '--gpt-model',
        default=None,
        help='Override the ChatGPT model (e.g. gpt-4o, gpt-4o-mini). Default: gpt-4o-mini.'
    )
    parser.add_argument(
        '--qa-wait',
        type=int,
        default=0,
        metavar='SECONDS',
        help='Seconds to wait before each QA call on iteration 2+ (TPM cooldown). Default: 0.'
    )
    parser.add_argument(
        '--static-check',
        type=Path,
        default=None,
        metavar='ARTIFACTS_DIR',
        help='Standalone static check: point at an iteration_NN_artifacts/ dir, '
             'run the 6 checks, print results, exit. No Claude/OpenAI calls. '
             'Does not require intake or governance args.'
    )
    parser.add_argument(
        '--ai-check',
        type=Path,
        default=None,
        metavar='ARTIFACTS_DIR',
        help='Standalone AI consistency check: point at an iteration_NN_artifacts/ dir, '
             'call Claude to check cross-file consistency, print results, exit. '
             'Requires ANTHROPIC_API_KEY. Does not require intake or governance args.'
    )
    parser.add_argument(
        '--quality-gate',
        action='store_true',
        default=False,
        help='Deprecated flag (Gate 4 quality is now mandatory and always ON).'
    )
    parser.add_argument(
        '--factory-mode',
        action='store_true',
        default=False,
        dest='factory_mode',
        help='Factory mode: skip Gate 3 (AI Consistency), Gate 4 fails only on DEPLOYABILITY=FAIL. '
             'Use for high-volume catalog builds where speed > perfection.'
    )
    parser.add_argument(
        '--no-polish',
        action='store_true',
        default=False,
        dest='no_polish',
        help='Skip post-QA polish step (README, .env.example, tests). Use for Phase 1 of a phased build.'
    )

    args = parser.parse_args()
    if args.max_parts < 1:
        parser.error("--max-parts must be >= 1")
    if args.max_continuations < 0:
        parser.error("--max-continuations must be >= 0")
    if args.max_iterations < 1:
        parser.error("--max-iterations must be >= 1")

    # ── Standalone static check mode ─────────────────────────────────────────
    # Run without intake/governance args. Just point at an artifacts dir.
    if args.static_check:
        artifacts_dir = Path(args.static_check)
        if not artifacts_dir.is_dir():
            print_error(f"--static-check path not found or not a directory: {artifacts_dir}")
            sys.exit(1)
        print_info("")
        print_info("═══════════════════════════════════════════════════════════")
        print_info(f"STANDALONE STATIC CHECK: {artifacts_dir}")
        print_info("═══════════════════════════════════════════════════════════")
        defects = FOHarness._run_static_check(artifacts_dir, intake_data=None)
        if not defects:
            print_success("STATIC CHECK: PASS — no defects found")
            sys.exit(0)
        else:
            high = sum(1 for d in defects if d['severity'] == 'HIGH')
            med  = sum(1 for d in defects if d['severity'] == 'MEDIUM')
            print_warning(f"STATIC CHECK: FAIL — {len(defects)} defect(s)  [HIGH: {high}  MEDIUM: {med}]")
            print_info("")
            for d in defects:
                sev_fn = print_error if d['severity'] == 'HIGH' else print_warning
                sev_fn(f"  {d['id']} [{d['severity']}]  {d['file']}")
                print_info(f"    Issue: {d['issue']}")
                print_info(f"    Fix:   {d['fix']}")
                print_info("")
            sys.exit(1)

    # ── Standalone AI consistency check mode ────────────────────────────────
    if args.ai_check:
        artifacts_dir = Path(args.ai_check)
        if not artifacts_dir.is_dir():
            print_error(f"--ai-check path not found or not a directory: {artifacts_dir}")
            sys.exit(1)
        if not Config.ANTHROPIC_API_KEY:
            print_error("ANTHROPIC_API_KEY is required for --ai-check")
            sys.exit(1)
        print_info("")
        print_info("═══════════════════════════════════════════════════════════")
        print_info(f"STANDALONE AI CONSISTENCY CHECK: {artifacts_dir}")
        print_info("═══════════════════════════════════════════════════════════")
        _claude = ClaudeClient(Config.ANTHROPIC_API_KEY, Config.CLAUDE_MODEL)
        issues = FOHarness._run_ai_consistency_check_standalone(artifacts_dir, _claude)
        if not issues:
            print_success("CONSISTENCY CHECK: PASS — no cross-file issues found")
            sys.exit(0)
        else:
            high = sum(1 for iss in issues if iss.get('severity') == 'HIGH')
            med  = sum(1 for iss in issues if iss.get('severity') == 'MEDIUM')
            print_warning(f"CONSISTENCY CHECK: FAIL — {len(issues)} issue(s)  [HIGH: {high}  MEDIUM: {med}]")
            print_info("")
            for iss in issues:
                sev_fn = print_error if iss.get('severity') == 'HIGH' else print_warning
                sev_fn(f"  {iss['id']} [{iss.get('severity', 'MEDIUM')}]  {iss.get('files', iss.get('file', '?'))}")
                print_info(f"    Evidence: {iss.get('evidence', 'N/A')}")
                print_info(f"    Issue:    {iss.get('issue', 'N/A')}")
                print_info(f"    Fix:      {iss.get('fix', 'N/A')}")
                print_info("")
            sys.exit(1)

    # ── Normal run: require intake; resolve governance ZIPs (named flags win over positional) ──
    if not args.intake_file:
        parser.error("intake_file is required (unless using --static-check or --ai-check)")
    # Named flags (--buildzip / --deployzip) override positional args; positional fallback to defaults
    if args.build_governance_zip is None:
        args.build_governance_zip = args.buildzip

    # If --resume-run is given without --resume-mode, default to qa
    if args.resume_run and not args.resume_mode:
        args.resume_mode = 'qa'
        print(f"→ --resume-run set without --resume-mode — defaulting to qa")

    # Apply model overrides
    if args.gpt_model:
        Config.GPT_MODEL = args.gpt_model
        print(f"→ GPT model override: {Config.GPT_MODEL}")

    # Resolve block from flag
    block = 'A' if args.block_a else 'B'

    # Validate API keys
    if not Config.ANTHROPIC_API_KEY:
        print_error("ANTHROPIC_API_KEY environment variable not set")
        print_info("Set it with: export ANTHROPIC_API_KEY='sk-ant-...'")
        sys.exit(1)

    if not Config.OPENAI_API_KEY:
        print_error("OPENAI_API_KEY environment variable not set")
        print_info("Set it with: export OPENAI_API_KEY='sk-...'")
        sys.exit(1)

    # Validate intake file
    if not args.intake_file.exists():
        print_error(f"Intake file not found: {args.intake_file}")
        sys.exit(1)

    # Validate governance ZIPs
    if not args.build_governance_zip.exists():
        print_error(f"BUILD governance ZIP not found: {args.build_governance_zip}")
        sys.exit(1)

    # Inject CLI paths into Config
    Config.BUILD_GOVERNANCE_ZIP  = args.build_governance_zip
    Config.PLATFORM_BOILERPLATE_DIR = args.platform_boilerplate_dir

    # Create base output directory
    Config.OUTPUT_DIR.mkdir(exist_ok=True)

    # Run
    try:
        harness = FOHarness(args.intake_file, block, do_deploy=args.deploy, cli_args=args)
        success = harness.run()
        sys.exit(0 if success else 1)

    except KeyboardInterrupt:
        print_warning("\nExecution interrupted by user")
        sys.exit(130)

    except Exception as e:
        print_error(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
