#!/usr/bin/env python3
"""
slice_planner.py — Quality-mode vertical slice planner.

Reads an intake JSON and produces a lightweight vertical slice plan that
breaks features into end-to-end slices (schema/service/route/UI).

Uses ChatGPT by default (unless --no-ai or OPENAI_API_KEY missing),
with a rule-based fallback.

Output:
    <stem>_slice_plan.json
"""

import argparse
import csv
import copy
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List


# ---- AI cost logging ---------------------------------------------------------

_PRICING = {
    'gpt-4o':       {'input': 2.50, 'output': 10.00},   # per 1M tokens
    'gpt-4o-mini':  {'input': 0.15, 'output': 0.60},
}

COST_CSV = 'slice_planner_ai_costs.csv'


def _calc_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    p = _PRICING.get(model, {'input': 3.0, 'output': 15.0})
    return (input_tokens * p['input'] + output_tokens * p['output']) / 1_000_000


def _log_ai_cost(csv_path: str, caller: str, model: str, input_tokens: int,
                 output_tokens: int, cost_usd: float, duration_s: float,
                 startup_id: str = '', note: str = '') -> None:
    file_exists = os.path.exists(csv_path)
    with open(csv_path, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow([
                'timestamp', 'caller', 'model', 'input_tokens', 'output_tokens',
                'cost_usd', 'duration_s', 'startup_id', 'note',
            ])
        writer.writerow([
            time.strftime('%Y-%m-%d %H:%M:%S'),
            caller, model, input_tokens, output_tokens,
            f'{cost_usd:.6f}', f'{duration_s:.1f}', startup_id, note,
        ])


# ---- Intake extraction helpers (mirrors phase_planner.py) --------------------

FEATURE_KEYS = {
    'must_have_features', 'q4_must_have_features', 'features',
    'required_features', 'feature_list', 'capabilities', 'requirements',
    'must_haves', 'core_features', 'key_features', 'product_features',
}

TASK_LIST_KEYS = {'combined_task_list', 'task_list', 'tasks'}


def _recursive_get_lists(obj: Any, keys: set) -> list:
    if isinstance(obj, dict):
        out = []
        for k, v in obj.items():
            if k.lower() in keys and isinstance(v, list):
                out.extend(v)
            out.extend(_recursive_get_lists(v, keys))
        return out
    if isinstance(obj, list):
        out = []
        for item in obj:
            out.extend(_recursive_get_lists(item, keys))
        return out
    return []


def _extract_features(intake: dict) -> list:
    raw = _recursive_get_lists(intake, FEATURE_KEYS)
    features = []
    for item in raw:
        if isinstance(item, str) and item.strip():
            features.append(item.strip())
        elif isinstance(item, dict):
            text = (item.get('feature') or item.get('name') or
                    item.get('description') or item.get('title') or '')
            if text:
                features.append(str(text).strip())

    if not features:
        task_raw = _recursive_get_lists(intake, TASK_LIST_KEYS)
        for item in task_raw:
            if isinstance(item, dict) and item.get('classification') == 'build':
                desc = item.get('description', '')
                if desc:
                    features.append(str(desc).strip())

    # Deduplicate, preserve order
    seen = set()
    result = []
    for f in features:
        key = f.lower()
        if key not in seen:
            seen.add(key)
            result.append(f)
    return result


# ---- Slice heuristics --------------------------------------------------------

HITL_KEYWORDS = [
    'brand', 'tone', 'voice', 'copy', 'messaging', 'positioning',
    'pricing', 'legal', 'compliance', 'terms', 'policy',
    'oauth', 'api key', 'integration', 'webhook', 'payment',
    'stripe', 'auth0', 'gmail', 'calendar',
]

ANALYTICS_KEYWORDS = [
    'dashboard', 'analytics', 'kpi', 'metric', 'report', 'export', 'download',
    'chart', 'graph', 'insight', 'analysis', 'trend', 'score',
]

CRUD_KEYWORDS = [
    'create', 'manage', 'list', 'view', 'edit', 'delete', 'update', 'add',
    'remove', 'upload', 'track', 'record', 'notes', 'comments',
]


def _slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r'[^a-z0-9]+', '_', text)
    text = re.sub(r'_+', '_', text).strip('_')
    return text or 'feature'

def _title_from_slug(slug: str) -> str:
    return ''.join(w.capitalize() for w in slug.split('_') if w)


def _infer_http_method(feature: str) -> str:
    f = feature.lower()
    if any(k in f for k in ['list', 'view', 'search', 'filter', 'get']):
        return 'GET'
    if any(k in f for k in ['delete', 'remove']):
        return 'DELETE'
    if any(k in f for k in ['update', 'edit']):
        return 'PUT'
    return 'POST'


def _is_hitl(feature: str, intake_blob: str) -> bool:
    f = feature.lower()
    if any(k in f for k in HITL_KEYWORDS):
        return True
    if any(k in intake_blob for k in HITL_KEYWORDS):
        return True
    return False


def _build_slice(feature: str, intake_blob: str, idx: int) -> Dict[str, Any]:
    slug = _slugify(feature)
    method = _infer_http_method(feature)
    route = f"/api/{slug}"
    data_model = f"{slug}_model"
    page = f"{slug}_page"

    hitl = _is_hitl(feature, intake_blob)
    mode = 'HITL' if hitl else 'AFK'
    mode_reason = "requires human taste/decision or external setup" if hitl else "deterministic from intake"

    needs_data = any(k in feature.lower() for k in CRUD_KEYWORDS) or True
    data_changes = [f"new model: {data_model}"] if needs_data else []

    acceptance = [
        f"API {method} {route} responds successfully",
        f"UI can complete: {feature}",
    ]
    if any(k in feature.lower() for k in ANALYTICS_KEYWORDS):
        acceptance.append("Computed output matches defined KPI/metric logic")

    return {
        "id": f"S{idx:02d}",
        "title": feature,
        "feature": feature,
        "api": {"method": method, "route": route},
        "data_changes": data_changes,
        "ui": {"page": page, "actions": ["create", "view"]},
        "acceptance_criteria": acceptance,
        "mode": mode,
        "mode_reason": mode_reason,
        "dependencies": [],
        "notes": "",
    }


def _intake_blob(intake: dict) -> str:
    def _flatten(obj: Any) -> str:
        if isinstance(obj, str):
            return obj.lower() + ' '
        if isinstance(obj, dict):
            return ''.join(_flatten(v) for v in obj.values())
        if isinstance(obj, list):
            return ''.join(_flatten(v) for v in obj)
        return ''
    return _flatten(intake)


def _strip_tier1_from_intake(intake: dict) -> dict:
    # Remove Tier 1 / POC references (Airtable, Softr, etc.) from intake before AI planning.
    tier1_markers = [
        'tier 1', 'poc', 'proof slice', 'proof-of-concept', 'prototype',
        'airtable', 'softr', 'no-code', 'nocode', 'rapid prototyping',
    ]

    def _filter(obj):
        if isinstance(obj, str):
            s = obj.lower()
            if any(m in s for m in tier1_markers):
                return ''
            return obj
        if isinstance(obj, list):
            return [_filter(v) for v in obj if _filter(v) != '']
        if isinstance(obj, dict):
            return {k: _filter(v) for k, v in obj.items() if _filter(v) != ''}
        return obj

    return _filter(intake)


def build_slice_plan(intake: dict) -> Dict[str, Any]:
    features = _extract_features(intake)
    blob = _intake_blob(intake)
    slices = [_build_slice(f, blob, i + 1) for i, f in enumerate(features)]
    return {
        "planner": "slice_planner",
        "feature_count": len(features),
        "slices": slices,
    }

def _ensure_unique_slug(base: str, used: set) -> str:
    slug = base
    n = 2
    while slug in used:
        slug = f"{base}_{n}"
        n += 1
    used.add(slug)
    return slug


def _normalize_slices(plan: dict) -> dict:
    slices = plan.get('slices', [])
    if not isinstance(slices, list):
        slices = []

    used_slugs = set()
    normalized = []
    for i, s in enumerate(slices, start=1):
        feature = (s.get('feature') or s.get('title') or f"Slice {i}")
        title = s.get('title') or feature

        base_slug = _slugify(feature)
        slug = _ensure_unique_slug(base_slug, used_slugs)

        # Normalize API route and method
        api = s.get('api') or {}
        method = (api.get('method') or _infer_http_method(feature)).upper()
        route = api.get('route') or f"/api/{slug}"
        route = route.replace('-', '_')

        # Normalize UI/page
        ui = s.get('ui') or {}
        page = ui.get('page') or f"{slug}_page"

        # Normalize mode
        mode = s.get('mode') or ('HITL' if _is_hitl(feature, '') else 'AFK')
        mode_reason = s.get('mode_reason') or ("requires human taste/decision or external setup" if mode == 'HITL' else "deterministic from intake")

        acceptance = s.get('acceptance_criteria') or [
            f"API {method} {route} responds successfully",
            f"UI can complete: {feature}",
        ]

        normalized.append({
            "id": s.get('id') or f"S{i:02d}",
            "title": title,
            "feature": feature,
            "slug": slug,
            "api": {"method": method, "route": route},
            "data_changes": s.get('data_changes') or [],
            "ui": {"page": page, "actions": ui.get('actions', ["create", "view"])},
            "acceptance_criteria": acceptance,
            "mode": mode,
            "mode_reason": mode_reason,
            "dependencies": s.get('dependencies') or [],
            "notes": s.get('notes', ""),
        })

    plan['slices'] = normalized
    plan['feature_count'] = len(normalized)
    return plan


def _slice_to_mini_spec(slice_obj: dict) -> dict:
    slug = slice_obj['slug']
    group_key = slice_obj.get('group_key') or slug
    owner = slice_obj.get('group_owner', True)
    plural = slug + 's' if not slug.endswith('s') else slug
    page_name = _title_from_slug(slug)
    api = slice_obj.get('api', {})
    route = api.get('route', f"/api/{slug}")
    method = api.get('method', 'POST').upper()
    public_route = route.replace('/api', '')

    allowed_files = [
        f"business/backend/routes/{plural}.py",
        f"business/frontend/pages/{page_name}.jsx",
    ]
    if owner:
        allowed_files = [
            f"business/models/{group_key}.py",
            f"business/schemas/{group_key}.py",
            f"business/services/{group_key}_service.py",
        ] + allowed_files

    # Extract required integrations from mode_reason
    mode = slice_obj.get('mode', 'AFK')
    mode_reason = slice_obj.get('mode_reason', '')
    required_integrations = []
    integration_map = {
        'stripe': {
            'name': 'Stripe',
            'import': 'from lib.stripe_lib import load_stripe_lib',
            'init': 'stripe = load_stripe_lib("config/stripe_config.json")',
        },
        'mailerlite': {
            'name': 'MailerLite',
            'import': 'from lib.mailerlite_lib import load_mailerlite_lib',
            'init': 'mailer = load_mailerlite_lib("config/mailerlite_config.json")',
        },
        'auth0': {
            'name': 'Auth0',
            'import': 'from lib.auth0_lib import load_auth0_lib',
            'init': 'auth0 = load_auth0_lib("config/auth0_config.json")',
        },
        'meilisearch': {
            'name': 'Meilisearch',
            'import': 'from lib.meilisearch_lib import load_meilisearch_lib',
            'init': 'search = load_meilisearch_lib("config/meilisearch_config.json")',
        },
    }
    mode_reason_lower = mode_reason.lower()
    for key, info in integration_map.items():
        if key in mode_reason_lower:
            required_integrations.append(info)

    mini_spec = {
        "entity": slice_obj.get('title', slice_obj['feature']),
        "build_order": int(slice_obj['id'].lstrip('S')) if str(slice_obj['id']).lstrip('S').isdigit() else 99,
        "evidence": [slice_obj['feature']],
        "inclusion_reason": f"Slice derived from intake: {slice_obj['feature']}",
        "fields": [],
        "crud_operations": [f"{method} {public_route}"],
        "dependencies": slice_obj.get('dependencies', []),
        "relationship_cardinality": [],
        "frontend_page": {
            "route": f"/{slug.replace('_', '-')}",
            "list_view": [],
            "detail_view": [],
        },
        "out_of_scope": [],
        "deferred_related_capabilities": [],
        "acceptance_checks": slice_obj.get('acceptance_criteria', []),
        "file_contract": {
            "allowed_files": allowed_files
        },
        "forbidden_expansions": [
            "Do not create any file outside the allowed_files list.",
        ],
        "open_questions": [],
        "mode": mode,
        "mode_reason": mode_reason,
        "required_integrations": required_integrations,
    }
    return mini_spec


def build_slice_intakes(intake: dict, plan: dict, output_dir: Path, stem: str) -> list:
    intakes = []
    # Clean prior slice intakes for this stem to avoid duplicate artifacts
    for old in output_dir.glob(f"{stem}_s*.json"):
        if "_slice_" in old.name:
            continue
        try:
            old.unlink()
        except Exception:
            pass
    for i, s in enumerate(plan.get('slices', []), start=1):
        mini_spec = _slice_to_mini_spec(s)

        slice_intake = copy.deepcopy(intake)
        base_id = intake.get('startup_idea_id', stem).rstrip('_')
        slice_intake['startup_idea_id'] = f"{base_id}_s{i:02d}_{s['slug']}"
        slice_intake['must_have_features'] = [s['feature']]
        slice_intake['_mini_spec'] = mini_spec

        slice_intake['_phase_context'] = {
            'phase': 1,
            'of_phases': plan.get('feature_count', len(plan.get('slices', []))),
            'scope': f"SLICE — {s['title']} ONLY",
            'current_entity': s['title'],
            'all_phase1_entities': [x.get('title', x['feature']) for x in plan.get('slices', [])],
            'deferred_to_phase2': [],
            'note': (
                f"Build ONLY this slice. "
                f"Allowed files: {', '.join(mini_spec.get('file_contract', {}).get('allowed_files', []))}. "
                f"Do NOT create any other files."
            ),
        }

        slice_path = output_dir / f"{stem}_s{i:02d}_{s['slug']}.json"
        with slice_path.open("w", encoding="utf-8") as f:
            json.dump(slice_intake, f, indent=2)

        intakes.append({
            "id": s['id'],
            "title": s['title'],
            "feature": s['feature'],
            "intake_path": str(slice_path),
        })
        print(f"  Slice intake: {slice_path.name} ({s['id']})")
    return intakes

AI_SLICE_PROMPT = """You are generating a vertical slice plan for a build harness.

ARCHITECTURE + GOVERNANCE CONTEXT (must respect):
{governance_context}

QA EXCERPT (use to shape acceptance criteria):
- Criteria must be verifiable from the artifacts (routes/models/services/pages).
- Use concrete file/route/field references, not vague phrases like "works" or "should".
- If a criterion cannot be evidenced in code or UI, do not include it.

INTEGRATION RULES (boilerplate-first):
- Prefer boilerplate integrations: Auth0, Stripe, MailerLite, Sentry, OpenAI, Anthropic.
- Replace SendGrid/SES/Mailgun/Postmark with MailerLite.
- Use non-boilerplate integrations only if there is no boilerplate alternative (e.g., S3 for file storage).

IMPORTANT: You MUST produce EXACTLY ONE slice per feature listed below. Do NOT collapse
multiple features into a single slice. Do NOT skip features. Do NOT invent features
not in the list.

Each slice is a thin end-to-end tracer bullet that spans ALL layers:
- SQLAlchemy model (data layer)
- Pydantic schema (validation)
- Service method (business logic)
- FastAPI route (API endpoint)
- React JSX page (frontend UI)

FEATURES TO SLICE (one slice per feature, in this order):
{feature_list}

For each feature, generate:
1. A clear short title
2. The primary API endpoint (method + route)
3. Data model changes (new models, new fields, foreign keys)
4. UI page and user actions
5. 4-6 SPECIFIC acceptance criteria — concrete, testable, not generic
   BAD: "API responds successfully"
   GOOD: "POST /api/clients creates a Client with name, email, organization fields and returns 201"
   GOOD: "ClientPage.jsx renders a searchable list with columns: name, email, status"
   GOOD: "GET /api/clients/{{id}} returns 404 for non-existent client"
6. Mode: AFK (can be built and verified without human input) or HITL (needs human
   taste/approval, external API keys, brand decisions, legal review, pricing)
7. Dependencies: which earlier slices (by ID) must be built first

OUTPUT CONTRACT — return ONLY valid JSON with this structure:
{{
  "planner": "slice_planner",
  "feature_count": {feature_count},
  "slices": [
    {{
      "id": "S01",
      "title": "<short feature name>",
      "feature": "<feature description from the list above>",
      "api": {{"method": "GET|POST|PUT|DELETE", "route": "/api/slug"}},
      "data_changes": ["new model: foo", "new field: bar on foo"],
      "ui": {{"page": "foo_page", "actions": ["create", "view", "edit"]}},
      "acceptance_criteria": ["specific testable criterion 1", "...", "..."],
      "mode": "HITL|AFK",
      "mode_reason": "one sentence reason",
      "dependencies": ["S01"],
      "notes": ""
    }}
  ]
}}

Rules:
- feature_count MUST equal {feature_count}
- One slice per feature — no merging, no skipping
- Routes use underscores, NEVER hyphens
- Acceptance criteria must be SPECIFIC to this feature, not generic boilerplate
- HITL only when external setup, human taste, or third-party credentials are needed
- Dependencies reference earlier slice IDs (e.g. S01) — NOT feature names
- No markdown, no explanation. Return ONLY the JSON object.

INTAKE (for context — domain details, KPIs, user roles):
"""


def _format_feature_list(features: list) -> str:
    return '\n'.join(f'{i+1}. {f}' for i, f in enumerate(features))


def _extract_py_triple_quote_block(path: str, var_name: str) -> str:
    try:
        with open(path, 'r', encoding='utf-8') as f:
            text = f.read()
        m = re.search(rf'{re.escape(var_name)}\\s*=\\s*\"\"\"(.*?)\"\"\"', text, re.DOTALL)
        return m.group(1).strip() if m else ''
    except Exception:
        return ''


def _read_text_file(path: str) -> str:
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return f.read().strip()
    except Exception:
        return ''


def _build_governance_context() -> str:
    parts = []
    # Pull core architecture + golden examples from fo_test_harness.py
    frozen = _extract_py_triple_quote_block('fo_test_harness.py', 'FROZEN_ARCHITECTURAL_DECISIONS')
    golden = _extract_py_triple_quote_block('fo_test_harness.py', 'GOLDEN_EXAMPLES')
    if frozen:
        parts.append("## FROZEN ARCHITECTURAL DECISIONS\n" + frozen)
    if golden:
        parts.append("## GOLDEN EXAMPLES\n" + golden)

    # Add boilerplate/integration rules if present
    artifact_rules = _read_text_file('FO_ARTIFACT_FORMAT_RULES.txt')
    boilerplate_rules = _read_text_file('FO_BOILERPLATE_INTEGRATION_RULES.txt')
    if artifact_rules:
        parts.append("## ARTIFACT FORMAT RULES\n" + artifact_rules)
    if boilerplate_rules:
        parts.append("## BOILERPLATE INTEGRATION RULES\n" + boilerplate_rules)

    # Fallback minimal constraints if nothing found
    if not parts:
        parts.append(
            "Backend: FastAPI + SQLAlchemy (Python). No Node/Express. "
            "Frontend: React JSX pages only (no .tsx, no app/ router). "
            "Routes use underscores; auth via Depends(get_current_user)."
        )

    return '\n\n'.join(parts)


GENERIC_CRITERIA_PATTERNS = [
    r'\bworks\b',
    r'\bfunctions\b',
    r'\bresponds successfully\b',
    r'\bno errors\b',
    r'\bcorrectly\b',
    r'\bproperly\b',
    r'\bconfigured\b',
]

STACK_VIOLATION_PATTERNS = [
    r'\bnode\b',
    r'\bexpress\b',
    r'\bflask\b',
    r'\bdjango\b',
    r'next\.js',
    r'nextjs',
    r'\.tsx\b',
    r'\bapp router\b',
]

BOILERPLATE_INTEGRATIONS = {
    'auth0', 'stripe', 'mailerlite', 'sentry', 'openai', 'anthropic'
}

NON_BOILERPLATE_REPLACEMENTS = {
    # Auth
    'clerk': 'auth0',
    'okta': 'auth0',
    'firebase auth': 'auth0',
    'cognito': 'auth0',
    # Email
    'send grid': 'mailerlite',
    'send-grid': 'mailerlite',
    'amazon ses': 'mailerlite',
    'aws ses': 'mailerlite',
    'sendgrid': 'mailerlite',
    'ses': 'mailerlite',
    'mailgun': 'mailerlite',
    'postmark': 'mailerlite',
    # Payments
    'braintree': 'stripe',
    'chargebee': 'stripe',
    'paddle': 'stripe',
    # Monitoring
    'dynatrace': 'sentry',
    'datadog apm': 'sentry',
    'new relic': 'sentry',
    'rollbar': 'sentry',
    # AI providers
    'openrouter': 'openai',
    'google gemini': 'openai',
    'gemini': 'openai',
}


def _slice_has_issues(slice_obj: dict) -> list:
    issues = []
    title = (slice_obj.get('title') or '')
    feature = (slice_obj.get('feature') or '')
    acc = slice_obj.get('acceptance_criteria') or []
    blob = f"{title} {feature} " + ' '.join(acc)
    bl = blob.lower()

    if any(re.search(p, bl) for p in STACK_VIOLATION_PATTERNS):
        issues.append('stack_violation')

    for c in acc:
        cl = c.lower()
        if any(re.search(p, cl) for p in GENERIC_CRITERIA_PATTERNS):
            issues.append('generic_acceptance')
            break

    for k in NON_BOILERPLATE_REPLACEMENTS.keys():
        if re.search(rf'(?i)\b{re.escape(k)}\b', bl):
            issues.append('non_boilerplate_integration')
            break

    if not acc or len(acc) < 3:
        issues.append('acceptance_too_short')

    return issues


def _sanitize_stack_terms(text: str) -> str:
    replacements = {
        'node.js': 'fastapi',
        'node': 'fastapi',
        'express': 'fastapi',
        'flask': 'fastapi',
        'django': 'fastapi',
        'next.js': 'react',
        'nextjs': 'react',
        '.tsx': '.jsx',
        'app router': 'pages router',
    }
    out = text
    for k, v in replacements.items():
        out = re.sub(rf'(?i){re.escape(k)}', v, out)
    return out


def _sanitize_integrations(text: str) -> str:
    out = text
    # Phrase-level replacements first
    for k, v in NON_BOILERPLATE_REPLACEMENTS.items():
        if ' ' in k or '-' in k:
            out = re.sub(rf'(?i){re.escape(k)}', v, out)
    # Token-level replacements
    for k, v in NON_BOILERPLATE_REPLACEMENTS.items():
        if ' ' in k or '-' in k:
            continue
        out = re.sub(rf'(?i)\b{re.escape(k)}\b', v, out)
    return out


def _enforce_boilerplate_integrations(obj):
    if isinstance(obj, str):
        return _sanitize_integrations(obj)
    if isinstance(obj, list):
        return [_enforce_boilerplate_integrations(v) for v in obj]
    if isinstance(obj, dict):
        return {k: _enforce_boilerplate_integrations(v) for k, v in obj.items()}
    return obj


def _intake_mentions(intake: dict, keyword: str) -> bool:
    blob = _intake_blob(intake)
    return keyword.lower() in blob


def _auto_fill_criteria(slice_obj: dict) -> list:
    api = slice_obj.get('api') or {}
    method = api.get('method', 'POST')
    route = api.get('route', '/api/endpoint')
    page = (slice_obj.get('ui') or {}).get('page', 'Page')
    title = slice_obj.get('title', 'Feature')
    return [
        f"{method} {route} returns a structured JSON response for {title}",
        f"{method} {route} validates required fields and returns 400 on missing data",
        f"{page}.jsx renders the primary UI for {title} with required inputs and actions",
        f"{page}.jsx displays API results from {route} in a visible section or list",
    ]


def _group_entity_key(feature: str) -> str:
    f = feature.lower()
    if 'auth' in f or 'login' in f or 'signup' in f or 'registration' in f:
        return 'user_auth'
    if 'property' in f:
        return 'property'
    if 'template' in f:
        return 'task_template'
    if 'task' in f or 'maintenance' in f or 'recurring' in f or 'schedule' in f:
        return 'task'
    if 'billing' in f or 'stripe' in f or 'subscription' in f:
        return 'billing'
    if 'email' in f or 'reminder' in f:
        return 'email'
    if 'upload' in f or 'photo' in f or 's3' in f:
        return 'file_upload'
    if 'dashboard' in f or 'calendar' in f:
        return 'dashboard'
    return _slugify(feature)


def _assign_groups(plan: dict) -> dict:
    seen = set()
    for s in plan.get('slices', []):
        key = _group_entity_key(s.get('feature', '') or s.get('title', ''))
        s['group_key'] = key
        if key not in seen:
            s['group_owner'] = True
            seen.add(key)
        else:
            s['group_owner'] = False
    return plan


def _rebuild_slug_fields(plan: dict) -> dict:
    used = set()
    for s in plan.get('slices', []):
        base = _slugify(s.get('feature') or s.get('title') or 'feature')
        s['slug'] = _ensure_unique_slug(base, used)
        api = s.get('api') or {}
        route = api.get('route') or f"/api/{s['slug']}"
        route = route.replace('-', '_')
        s['api'] = {'method': api.get('method', 'POST'), 'route': route}
        ui = s.get('ui') or {}
        s['ui'] = {
            'page': ui.get('page') or f"{s['slug']}_page",
            'actions': ui.get('actions', ['create', 'view']),
        }
    return plan


SLICE_REPAIR_PROMPT = """You are repairing a vertical slice definition to comply with governance.

Return ONLY valid JSON:
{{
  \"title\": \"...\",
  \"feature\": \"...\",
  \"acceptance_criteria\": [\"...\", \"...\", \"...\", \"...\"]
}}

Rules:
- Must respect the architecture: FastAPI + SQLAlchemy backend, React JSX frontend.
- No Node/Express/Flask/Django/Next.js, no .tsx, no app router.
- Acceptance criteria must be SPECIFIC and verifiable in code/UI.
- Use concrete file/route/field references (e.g., \"POST /api/clients creates ...\").
- 4-6 acceptance criteria per slice.
- Keep the same intent as the original feature; if it mentions Node/Express, translate to FastAPI instead.
- Do NOT change the API method/route.
- Remove any mention of Node/Express/Flask/Django/Next.js/.tsx/app router from title/feature/criteria.
- Replace generic statements (e.g., \"configured correctly\", \"works\") with concrete, testable checks.
- Use boilerplate integrations only: Auth0, Stripe, MailerLite, Sentry, OpenAI, Anthropic.
- If SendGrid/SES/Mailgun/Postmark appear, replace with MailerLite (boilerplate email).
- Only use non-boilerplate integrations if there is no boilerplate option (e.g., S3 for file storage).

GOVERNANCE:
{governance_context}

SLICE:
ID: {sid}
Title: {title}
Feature: {feature}
API: {method} {route}
UI Page: {page}
Existing criteria:
{criteria}
"""


def _repair_slices(plan: dict, intake: dict, api_key: str, model: str) -> tuple:
    try:
        import openai
        client = openai.OpenAI(api_key=api_key)
    except Exception:
        return plan, []

    governance_context = _build_governance_context()
    total_costs = []

    max_attempts = 2
    repaired_count = 0
    for attempt in range(1, max_attempts + 1):
        for i, s in enumerate(plan.get('slices', [])):
            issues = _slice_has_issues(s)
            if not issues:
                continue

            criteria = '\\n'.join(f'- {c}' for c in (s.get('acceptance_criteria') or [])) or '- (none)'
            prompt = SLICE_REPAIR_PROMPT.format(
                governance_context=governance_context,
                sid=s.get('id', f'S{i+1:02d}'),
                title=s.get('title', ''),
                feature=s.get('feature', ''),
                method=(s.get('api') or {}).get('method', ''),
                route=(s.get('api') or {}).get('route', ''),
                page=(s.get('ui') or {}).get('page', ''),
                criteria=criteria,
            )

            prompt_len = len(prompt)
            t0 = time.time()
            resp = client.chat.completions.create(
                model=model,
                temperature=0.2,
                max_tokens=1200,
                messages=[{'role': 'user', 'content': prompt}],
            )
            elapsed = time.time() - t0

            raw = resp.choices[0].message.content.strip()
            in_tok = resp.usage.prompt_tokens
            out_tok = resp.usage.completion_tokens
            cost = _calc_cost(model, in_tok, out_tok)

            issue_str = ", ".join(issues)
            _log_ai_cost(COST_CSV, 'slice_plan_repair', model,
                         in_tok, out_tok, cost, elapsed, intake.get('startup_idea_id', ''),
                         f"{s.get('id', '?')} issues: {issue_str} (attempt {attempt})")

            total_costs.append({
                'model': model,
                'input_tokens': in_tok,
                'output_tokens': out_tok,
                'cost_usd': cost,
                'elapsed_s': elapsed,
            })

            if raw.startswith('```'):
                raw = re.sub(r'^```\\w*\\n?', '', raw)
                raw = re.sub(r'\\n?```$', '', raw)

            try:
                repaired = json.loads(raw)
            except Exception:
                continue

            if isinstance(repaired, dict):
                if repaired.get('title'):
                    s['title'] = repaired['title']
                if repaired.get('feature'):
                    s['feature'] = repaired['feature']
                if repaired.get('acceptance_criteria'):
                    s['acceptance_criteria'] = repaired['acceptance_criteria']
                repaired_count += 1

    # Final deterministic cleanup for stubborn slices
    for s in plan.get('slices', []):
        issues = _slice_has_issues(s)
        if not issues:
            continue
        if 'stack_violation' in issues:
            s['title'] = _sanitize_stack_terms(s.get('title', ''))
            s['feature'] = _sanitize_stack_terms(s.get('feature', ''))
            s['acceptance_criteria'] = [_sanitize_stack_terms(c) for c in (s.get('acceptance_criteria') or [])]
        if 'non_boilerplate_integration' in issues:
            s['title'] = _sanitize_integrations(s.get('title', ''))
            s['feature'] = _sanitize_integrations(s.get('feature', ''))
            s['acceptance_criteria'] = [_sanitize_integrations(c) for c in (s.get('acceptance_criteria') or [])]
        # If acceptance criteria still weak, fill with deterministic criteria
        if _slice_has_issues(s):
            s['acceptance_criteria'] = _auto_fill_criteria(s)

    return plan, total_costs

def build_slice_plan_ai(intake: dict, api_key: str, model: str, startup_id: str = '') -> tuple:
    try:
        import openai
        client = openai.OpenAI(api_key=api_key)

        intake_for_ai = _strip_tier1_from_intake(intake)
        features = _extract_features(intake_for_ai)
        feature_list = _format_feature_list(features)
        feature_count = len(features)
        governance_context = _build_governance_context()

        intake_json = json.dumps(intake_for_ai, indent=2, default=str)
        prompt = AI_SLICE_PROMPT.format(
            feature_list=feature_list,
            feature_count=feature_count,
            governance_context=governance_context,
        ) + intake_json

        prompt_len = len(prompt)
        print(f'  [SLICE-AI] Sending intake to ChatGPT ({model})')
        print(f'  [SLICE-AI] Prompt: ~{prompt_len:,} chars, '
              f'~{prompt_len // 4:,} est. tokens')
        print('  [SLICE-AI] Waiting for response...')

        t0 = time.time()
        resp = client.chat.completions.create(
            model=model,
            temperature=0.2,
            max_tokens=4096,
            messages=[{'role': 'user', 'content': prompt}],
        )
        elapsed = time.time() - t0

        raw = resp.choices[0].message.content.strip()
        in_tok = resp.usage.prompt_tokens
        out_tok = resp.usage.completion_tokens
        cost = _calc_cost(model, in_tok, out_tok)

        print(f'  [SLICE-AI] Response in {elapsed:.1f}s — '
              f'{in_tok:,} in / {out_tok:,} out — ${cost:.4f}')

        _log_ai_cost(COST_CSV, 'slice_plan', model,
                     in_tok, out_tok, cost, elapsed, startup_id,
                     f'prompt {prompt_len} chars')

        if raw.startswith('```'):
            raw = re.sub(r'^```\w*\n?', '', raw)
            raw = re.sub(r'\n?```$', '', raw)

        result = json.loads(raw)
        if not isinstance(result, dict) or 'slices' not in result:
            print('  [SLICE-AI] Unexpected response shape — falling back to heuristics')
            return None

        return result, {
            "model": model,
            "input_tokens": in_tok,
            "output_tokens": out_tok,
            "cost_usd": cost,
            "elapsed_s": elapsed,
        }
    except Exception as e:
        print(f'  [SLICE-AI] API call failed: {e}')
        return None, None


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate vertical slice plan from intake JSON.")
    parser.add_argument("--intake", required=True, help="Path to intake JSON")
    parser.add_argument("--output-dir", default="", help="Output directory (defaults to intake dir)")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON")
    parser.add_argument("--no-ai", action="store_true", help="Disable AI and use heuristics only")
    parser.add_argument("--loose", action="store_true", help="Allow imperfect slices (skip strict validation)")
    parser.add_argument("--openai-model", default="gpt-4o", help="OpenAI model for slice planning")
    parser.add_argument("--extra-repair", action="store_true",
                        help="Allow one additional AI repair pass before failing strict validation")
    args = parser.parse_args()

    intake_path = Path(args.intake)
    if not intake_path.exists():
        raise SystemExit(f"Intake file not found: {intake_path}")

    with intake_path.open("r", encoding="utf-8") as f:
        intake = json.load(f)

    plan = None
    cost_info = None
    openai_key = os.environ.get('OPENAI_API_KEY', '')
    if not args.no_ai and openai_key:
        plan, cost_info = build_slice_plan_ai(intake, openai_key, args.openai_model, startup_id=intake_path.stem)
        if plan is None:
            print('  [SLICE-AI] Falling back to heuristic slice planner')

    if plan is None:
        print('  [SLICE-AI] AI disabled or unavailable — using heuristic slice planner')
        plan = build_slice_plan(intake)

    plan = _normalize_slices(plan)

    # Repair acceptance criteria / stack violations if needed (AI only)
    repair_costs = []
    if not args.no_ai and openai_key:
        plan, repair_costs = _repair_slices(plan, intake, openai_key, args.openai_model)
        if args.extra_repair:
            # One additional bounded repair pass to avoid infinite loops
            plan, extra_costs = _repair_slices(plan, intake, openai_key, args.openai_model)
            if extra_costs:
                repair_costs.extend(extra_costs)

    # Enforce boilerplate integrations regardless of intake preferences
    plan = _enforce_boilerplate_integrations(plan)
    plan = _rebuild_slug_fields(plan)
    plan = _assign_groups(plan)

    # Print repair costs early (even if strict validation fails)
    if repair_costs:
        total = sum(c['cost_usd'] for c in repair_costs)
        in_tok = sum(c['input_tokens'] for c in repair_costs)
        out_tok = sum(c['output_tokens'] for c in repair_costs)
        print(
            f"AI repair cost: ${total:.4f} "
            f"({in_tok:,} in / {out_tok:,} out, {args.openai_model})"
        )

    # Strict validation: fail if issues remain (unless --loose)
    remaining_issues = []
    for s in plan.get('slices', []):
        issues = _slice_has_issues(s)
        if issues:
            remaining_issues.append((s.get('id'), s.get('title'), issues))

    if remaining_issues and not args.loose:
        print("ERROR: Slice validation failed after repair (use --loose to continue).")
        for sid, title, issues in remaining_issues:
            print(f"  - {sid} {title}: {', '.join(issues)}")
        raise SystemExit(1)
    elif remaining_issues:
        print("WARNING: Slice validation issues remain (continuing due to --loose):")
        for sid, title, issues in remaining_issues:
            print(f"  - {sid} {title}: {', '.join(issues)}")

    out_dir = Path(args.output_dir) if args.output_dir else intake_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = intake_path.stem
    out_path = out_dir / f"{stem}_slice_plan.json"

    with out_path.open("w", encoding="utf-8") as f:
        if args.pretty:
            json.dump(plan, f, indent=2)
        else:
            json.dump(plan, f)

    print(f"Slice plan written: {out_path}")
    print(f"Slices: {plan['feature_count']}")
    if cost_info:
        print(
            f"AI cost: ${cost_info['cost_usd']:.4f} "
            f"({cost_info['input_tokens']:,} in / {cost_info['output_tokens']:,} out, "
            f"{cost_info['model']}, {cost_info['elapsed_s']:.1f}s)"
        )
    total_cost = 0.0
    if cost_info:
        total_cost += cost_info['cost_usd']
    if repair_costs:
        total_cost += sum(c['cost_usd'] for c in repair_costs)
    if total_cost > 0:
        print(f"TOTAL AI COST: ${total_cost:.2f}")
    # Emit runnable slice intakes + assessment
    intakes = build_slice_intakes(intake, plan, out_dir, stem)
    assessment = {
        "planner": "slice_planner",
        "slice_count": plan['feature_count'],
        "slices": plan.get('slices', []),
        "slice_intakes": intakes,
    }
    assessment_path = out_dir / f"{stem}_slice_assessment.json"
    with assessment_path.open("w", encoding="utf-8") as f:
        json.dump(assessment, f, indent=2)
    print(f"Slice assessment written: {assessment_path}")


if __name__ == "__main__":
    main()
