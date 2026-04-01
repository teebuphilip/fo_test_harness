#!/usr/bin/env python3
"""
phase_planner.py — Intake phase analyzer and splitter.

Reads an intake JSON, determines whether the project can be built in one pass
or needs to be split into two phases (data layer first, intelligence layer second),
and produces the derived intake files ready to pass to fo_test_harness.py.

Usage:
    python phase_planner.py --intake path/to/intake.json
    python phase_planner.py --intake path/to/intake.json --output-dir /tmp/phases
    python phase_planner.py --intake path/to/intake.json --no-ai
    python phase_planner.py --intake path/to/intake.json --threshold 6

Outputs (if 2-phase):
    <stem>_phase1.json          Phase 1 intake (data layer)
    <stem>_phase2.json          Phase 2 intake (intelligence layer, references Phase 1)
    <stem>_phase_assessment.json  Full classification detail

Outputs (if 1-phase):
    <stem>_phase_assessment.json  Assessment confirming single phase
"""

import argparse
import copy
import csv
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

# ── Thresholds ────────────────────────────────────────────────────────────────

FEATURE_COUNT_THRESHOLD = 3  # features at or below this → candidate for 1-phase

# ── Classification keyword tables ─────────────────────────────────────────────

DATA_LAYER_KEYWORDS = [
    'create', 'manage', 'list', 'view', 'edit', 'delete', 'upload', 'store',
    'track', 'profile', 'crud', 'form', 'record', 'search', 'filter',
    'add', 'update', 'remove', 'input', 'entry', 'registration', 'onboarding',
    'invite', 'user management', 'client management', 'contact', 'account',
    'settings', 'notes', 'comments', 'tags', 'status management', 'basic',
    'directory', 'roster', 'schedule', 'calendar', 'booking', 'log',
]

INTELLIGENCE_LAYER_KEYWORDS = [
    'calculat', 'scor', 'kpi', 'metric', 'analytic', 'trend', 'report',
    'generat', 'recommend', 'export', 'download', 'pdf', 'chart', 'graph',
    'insight', 'forecast', 'analysis', 'ai-powered', 'machine learning',
    'dashboard analytic', 'intelligence', 'prediction', 'algorithm',
    'benchmark', 'index', 'ratio', 'performance indicator', 'visualization',
    'executive summary', 'aggregat', 'compute', 'infer', 'classify',
    'detect', 'rank', 'priorit', 'assess score', 'evaluate', 'model output',
    'sentiment', 'nlp', 'embedding', 'cluster',
]

# Signals in the intake JSON that force 2-phase regardless of feature count
FORCE_2_PHASE_CONTENT_SIGNALS = [
    'downloadable executive report',
    'trend analysis',
    'predictive',
    'scoring engine',
    'analytics dashboard',
    'ai-powered',
    'machine learning',
    'executive report',
]

# Keys whose presence at ≥3 entries forces 2-phase
FORCE_2_PHASE_KEY_SIGNALS = {
    'kpi_definitions', 'kpis', 'key_metrics', 'metrics',
}


# ── JSON helpers ──────────────────────────────────────────────────────────────

def recursive_get_lists(obj: Any, keys: set) -> list:
    """Collect all list values anywhere in nested structure matching given keys."""
    results = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k.lower() in keys and isinstance(v, list):
                results.extend(v)
            results.extend(recursive_get_lists(v, keys))
    elif isinstance(obj, list):
        for item in obj:
            results.extend(recursive_get_lists(item, keys))
    return results


def recursive_text_blob(obj: Any) -> str:
    """Flatten all string values in nested structure into one lowercase blob."""
    if isinstance(obj, str):
        return obj.lower() + ' '
    if isinstance(obj, dict):
        return ''.join(recursive_text_blob(v) for v in obj.values())
    if isinstance(obj, list):
        return ''.join(recursive_text_blob(v) for v in obj)
    return ''


def has_key_anywhere(obj: Any, key: str) -> bool:
    """Check if a key exists anywhere in nested dict."""
    if isinstance(obj, dict):
        if key.lower() in {k.lower() for k in obj}:
            return True
        return any(has_key_anywhere(v, key) for v in obj.values())
    if isinstance(obj, list):
        return any(has_key_anywhere(v, key) for v in obj)
    return False


# ── Feature extraction ────────────────────────────────────────────────────────

FEATURE_KEYS = {
    'must_have_features', 'q4_must_have_features', 'features',
    'required_features', 'feature_list', 'capabilities', 'requirements',
    'must_haves', 'core_features', 'key_features', 'product_features',
}

# Task-list format intakes (e.g. wynwood): extract build tasks from combined_task_list
TASK_LIST_KEYS = {'combined_task_list', 'task_list', 'tasks'}

KPI_KEYS = {
    'kpi_definitions', 'kpis', 'key_metrics', 'metrics',
    'kpi_ids', 'kpi_list', 'performance_indicators',
}


def extract_features(intake: dict) -> list:
    raw = recursive_get_lists(intake, FEATURE_KEYS)
    features = []
    for item in raw:
        if isinstance(item, str) and item.strip():
            features.append(item.strip())
        elif isinstance(item, dict):
            text = (item.get('feature') or item.get('name') or
                    item.get('description') or item.get('title') or '')
            if text:
                features.append(str(text).strip())

    # Fallback: task-list format intakes (combined_task_list with classification=build)
    if not features:
        task_raw = recursive_get_lists(intake, TASK_LIST_KEYS)
        for item in task_raw:
            if isinstance(item, dict) and item.get('classification') == 'build':
                desc = item.get('description', '')
                if desc:
                    features.append(str(desc).strip())

    # deduplicate preserving order
    seen = set()
    result = []
    for f in features:
        if f.lower() not in seen:
            seen.add(f.lower())
            result.append(f)
    return result


def extract_kpis(intake: dict) -> list:
    raw = recursive_get_lists(intake, KPI_KEYS)
    kpis = []
    for item in raw:
        if isinstance(item, dict):
            kid = (item.get('kpi_id') or item.get('id') or
                   item.get('name') or item.get('kpi_name') or '')
            if kid:
                kpis.append(str(kid).strip())
        elif isinstance(item, str) and item.strip():
            kpis.append(item.strip())
    return kpis


# ── Feature classification ────────────────────────────────────────────────────

def classify_rule_based(feature: str) -> str:
    """Returns 'DATA_LAYER', 'INTELLIGENCE_LAYER', or 'AMBIGUOUS'."""
    fl = feature.lower()
    intel = sum(1 for kw in INTELLIGENCE_LAYER_KEYWORDS if kw in fl)
    data  = sum(1 for kw in DATA_LAYER_KEYWORDS if kw in fl)
    if intel > 0 and data == 0:
        return 'INTELLIGENCE_LAYER'
    if data > 0 and intel == 0:
        return 'DATA_LAYER'
    if intel > data:
        return 'INTELLIGENCE_LAYER'
    if data > intel:
        return 'DATA_LAYER'
    return 'AMBIGUOUS'


def _log_ai_cost(csv_path: str, caller: str, model: str, input_tokens: int,
                  output_tokens: int, cost_usd: float, duration_s: float,
                  startup_id: str = '', note: str = '') -> None:
    """Append a row to the phase_planner AI cost CSV."""
    file_exists = os.path.exists(csv_path)
    with open(csv_path, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow([
                'timestamp', 'caller', 'model', 'input_tokens', 'output_tokens',
                'cost_usd', 'duration_s', 'startup_id', 'note',
            ])
        writer.writerow([
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            caller, model, input_tokens, output_tokens,
            f'{cost_usd:.6f}', f'{duration_s:.1f}', startup_id, note,
        ])


# Pricing per 1M tokens (as of 2026-03)
_PRICING = {
    'claude-haiku-4-5-20251001': {'input': 0.80, 'output': 4.00},
    'gpt-4o':                    {'input': 2.50, 'output': 10.00},
}

COST_CSV = 'phase_planner_ai_costs.csv'


def _calc_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    p = _PRICING.get(model, {'input': 3.0, 'output': 15.0})
    return (input_tokens * p['input'] + output_tokens * p['output']) / 1_000_000


def classify_with_ai(features: list, api_key: str, startup_id: str = '') -> dict:
    """
    Use Claude Haiku to classify ambiguous features.
    Returns {feature_text: 'DATA_LAYER' | 'INTELLIGENCE_LAYER'}.
    """
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        numbered = '\n'.join(f'{i+1}. {f}' for i, f in enumerate(features))
        prompt = f"""You are classifying app features for a build-phase planner.

DATA_LAYER: CRUD operations, data input and storage, user/entity management,
basic lists and views, forms, scheduling, booking, file upload, settings.

INTELLIGENCE_LAYER: KPI calculation, scoring engines, analytics, report generation,
trend analysis, AI/ML features, dashboard charts, PDF/export of computed data,
recommendations, forecasting, performance indicators, data visualization.

Features to classify:
{numbered}

Reply with exactly one line per feature:
<number>: DATA_LAYER
or
<number>: INTELLIGENCE_LAYER

No explanations. No other text."""

        print(f'  [CLASSIFIER] Calling Claude Haiku — {len(features)} features, '
              f'~{len(prompt)} chars prompt')
        t0 = time.time()
        resp = client.messages.create(
            model='claude-haiku-4-5-20251001',
            max_tokens=512,
            messages=[{'role': 'user', 'content': prompt}]
        )
        elapsed = time.time() - t0
        text = resp.content[0].text

        in_tok = resp.usage.input_tokens
        out_tok = resp.usage.output_tokens
        cost = _calc_cost('claude-haiku-4-5-20251001', in_tok, out_tok)
        print(f'  [CLASSIFIER] Done in {elapsed:.1f}s — '
              f'{in_tok} in / {out_tok} out — ${cost:.4f}')

        _log_ai_cost(COST_CSV, 'classify_with_ai', 'claude-haiku-4-5-20251001',
                     in_tok, out_tok, cost, elapsed, startup_id,
                     f'{len(features)} ambiguous features')

        result = {}
        for line in text.strip().splitlines():
            m = re.match(r'(\d+):\s*(DATA_LAYER|INTELLIGENCE_LAYER)', line.strip())
            if m:
                idx = int(m.group(1)) - 1
                if 0 <= idx < len(features):
                    result[features[idx]] = m.group(2)
        return result
    except Exception as e:
        print(f'  [AI classifier] Failed: {e} — treating ambiguous features as DATA_LAYER')
        return {}


# ── Phase assessment ──────────────────────────────────────────────────────────

def assess(intake: dict, use_ai: bool = True, api_key: str = '',
           threshold: int = FEATURE_COUNT_THRESHOLD,
           startup_id: str = '') -> dict:
    """
    Returns:
    {
        'phases': 1 | 2,
        'reason': str,
        'force_signal': str | None,
        'features': {feature_text: 'DATA_LAYER' | 'INTELLIGENCE_LAYER'},
        'data_features': [str],
        'intelligence_features': [str],
        'kpis': [str],
    }
    """
    features = extract_features(intake)
    kpis = extract_kpis(intake)
    blob = recursive_text_blob(intake)

    print(f'  Extracted {len(features)} feature(s), {len(kpis)} KPI(s)')

    # Step 1 — rule-based classification
    classifications = {}
    ambiguous = []
    for f in features:
        cls = classify_rule_based(f)
        if cls == 'AMBIGUOUS':
            ambiguous.append(f)
        else:
            classifications[f] = cls

    # Step 2 — AI for ambiguous
    if ambiguous:
        if use_ai and api_key:
            print(f'  Sending {len(ambiguous)} ambiguous feature(s) to AI classifier...')
            ai_result = classify_with_ai(ambiguous, api_key, startup_id=startup_id)
            for f in ambiguous:
                classifications[f] = ai_result.get(f, 'DATA_LAYER')
        else:
            for f in ambiguous:
                classifications[f] = 'DATA_LAYER'  # safe default

    data_features  = [f for f in features if classifications.get(f) == 'DATA_LAYER']
    intel_features = [f for f in features if classifications.get(f) == 'INTELLIGENCE_LAYER']

    # Step 3 — force signals
    force_signal = None

    if len(kpis) >= 3:
        force_signal = f'{len(kpis)} KPIs defined in intake'
    else:
        for sig in FORCE_2_PHASE_CONTENT_SIGNALS:
            if sig in blob:
                force_signal = f'intake contains \'{sig}\''
                break
        if not force_signal:
            for key in FORCE_2_PHASE_KEY_SIGNALS:
                if has_key_anywhere(intake, key):
                    raw = recursive_get_lists(intake, {key})
                    if len(raw) >= 3:
                        force_signal = f'intake has {len(raw)} entries under \'{key}\''
                        break

    # Decision
    if force_signal:
        phases = 2
        reason = f'Force signal: {force_signal}'
    elif intel_features:
        phases = 2
        reason = (f'{len(intel_features)} intelligence-layer feature(s) detected: '
                  f'{", ".join(intel_features[:3])}'
                  f'{"..." if len(intel_features) > 3 else ""}')
    elif len(features) > threshold:
        phases = 2
        reason = f'Feature count {len(features)} exceeds threshold {threshold}'
    else:
        phases = 1
        reason = (f'All {len(features)} feature(s) are data-layer and within '
                  f'threshold ({threshold}) — single phase sufficient')

    return {
        'phases':               phases,
        'reason':               reason,
        'force_signal':         force_signal,
        'features':             classifications,
        'data_features':        data_features,
        'intelligence_features': intel_features,
        'kpis':                 kpis,
    }


# ── Intake splitter ───────────────────────────────────────────────────────────

def _prune_intel_features(obj: Any, intel_set: set) -> Any:
    """Remove intelligence-layer entries from any feature list."""
    if isinstance(obj, list):
        return [
            item for item in obj
            if not (isinstance(item, str) and
                    any(kw in item.lower() for kw in intel_set))
        ]
    return obj


# Keywords that signal external integrations or intelligence features in text fields.
# Used to strip sentences from HLD, engineering questions, QA docs, and task lists.
PHASE2_STRIP_KEYWORDS = [
    # External integrations
    'equineline', 'truenicks', 'shopify', 'stripe', 'twilio', 'sendgrid',
    'mailchimp', 'zapier', 'plaid', 'airtable', 'salesforce',
    'third-party', 'third party', 'external api', 'external integration',
    'webhook', 'oauth', 'api integration',
    # Intelligence features
    'breeding data', 'pedigree', 'lineage', 'bloodline',
    'analytics', 'report generation', 'scoring', 'kpi',
    'trend analysis', 'forecast', 'prediction', 'recommendation',
    'ai-powered', 'machine learning', 'intelligence',
    'executive report', 'executive summary', 'pdf export',
    'visualization', 'chart', 'graph', 'benchmark',
    # Merchandising (external commerce)
    'merchandise', 'merch', 'shopify store', 'e-commerce', 'ecommerce',
    'fulfillment', 'inventory management',
    # Payment / billing (requires Stripe or similar)
    'payment processing', 'configure payment', 'billing',
]


def _strip_phase2_from_text(text: str) -> str:
    """Remove sentences containing Phase 2 / external integration keywords from text."""
    if not text or not isinstance(text, str):
        return text
    # Split on sentence boundaries (period, comma in lists, semicolons)
    sentences = re.split(r'(?<=[.;])\s+', text)
    kept = []
    for sent in sentences:
        sl = sent.lower()
        if any(kw in sl for kw in PHASE2_STRIP_KEYWORDS):
            continue
        kept.append(sent)
    result = ' '.join(kept).strip()
    return result if result else text  # fallback to original if everything got stripped


def _strip_phase2_from_list(items: list) -> list:
    """Remove list items (strings or dicts) that reference Phase 2 features."""
    result = []
    for item in items:
        if isinstance(item, str):
            if not any(kw in item.lower() for kw in PHASE2_STRIP_KEYWORDS):
                result.append(item)
        elif isinstance(item, dict):
            desc = str(item.get('description', '') or item.get('name', '') or
                       item.get('title', '') or item.get('feature', '') or '').lower()
            if not any(kw in desc for kw in PHASE2_STRIP_KEYWORDS):
                result.append(item)
        else:
            result.append(item)
    return result


def _extract_entity_names(data_features: list, intake: dict) -> list:
    """
    Derive entity names from data-layer features for explicit Phase 1 entity list.
    E.g. 'Manage horse profiles' → 'Horse', 'Track member onboarding' → 'Member'
    """
    # Common entity-suggesting words in feature descriptions
    entity_patterns = [
        r'\b(horse|horses)\b', r'\b(member|members)\b', r'\b(stable|stables)\b',
        r'\b(update|updates)\b', r'\b(content|contents)\b', r'\b(client|clients)\b',
        r'\b(user|users)\b', r'\b(project|projects)\b', r'\b(event|events)\b',
        r'\b(booking|bookings)\b', r'\b(order|orders)\b', r'\b(team|teams)\b',
        r'\b(report|reports)\b', r'\b(task|tasks)\b', r'\b(asset|assets)\b',
        r'\b(property|properties)\b', r'\b(listing|listings)\b',
        r'\b(contact|contacts)\b', r'\b(lead|leads)\b', r'\b(campaign|campaigns)\b',
        r'\b(subscription|subscriptions)\b', r'\b(payment|payments)\b',
        r'\b(invoice|invoices)\b', r'\b(compliance|compliance records)\b',
    ]
    entities = set()
    all_text = ' '.join(data_features).lower()
    # Also scan HLD and task descriptions — but NOT the entire blob (too noisy)
    bb = intake.get('block_b', {})
    if isinstance(bb, str):
        try:
            bb = json.loads(bb)
        except Exception:
            bb = {}
    hld = str(bb.get('pass_2', {}).get('hld_document', '')).lower()
    task_descs = ' '.join(
        str(t.get('description', '')) for t in
        recursive_get_lists(intake, TASK_LIST_KEYS) if isinstance(t, dict)
    ).lower()
    combined = all_text + ' ' + hld + ' ' + task_descs
    for pat in entity_patterns:
        if re.search(pat, combined):
            # Capitalize the first match group
            m = re.search(pat, combined)
            if m:
                entities.add(m.group(1).capitalize().rstrip('s'))  # Normalize: horses → Horse
    return sorted(entities)


def build_phase1_intake(intake: dict, assessment: dict) -> dict:
    """
    Phase 1 intake: data layer only — aggressively stripped.
    - Intelligence-layer must-haves removed from all feature list fields
    - KPI definition fields emptied (deferred to Phase 2)
    - External integration tasks stripped from combined_task_list
    - HLD, engineering questions, QA docs sanitized of Phase 2 references
    - _phase_context block with explicit entity list and hard prohibitions
    """
    p1 = copy.deepcopy(intake)
    intel_set = {f.lower() for f in assessment['intelligence_features']}

    # Keys whose text content should be sanitized of Phase 2 references
    TEXT_SANITIZE_KEYS = {
        'hld_document', 'qa_hlt_document', 'approved_bdr', 'bdr_summary',
    }
    # Keys whose list content should have Phase 2 items removed
    LIST_SANITIZE_KEYS = {
        'engineering_questions', 'qa_questions_for_engineering',
        'questions_for_hero', 'test_vectors',
    }

    def walk(obj: Any) -> Any:
        if isinstance(obj, dict):
            result = {}
            for k, v in obj.items():
                kl = k.lower()
                if kl in KPI_KEYS and isinstance(v, list):
                    result[k] = []  # defer KPIs to Phase 2
                elif kl in FEATURE_KEYS:
                    result[k] = _prune_intel_features(v, intel_set)
                elif kl in TASK_LIST_KEYS and isinstance(v, list):
                    # Strip external integration and intelligence tasks
                    result[k] = _strip_phase2_from_list(v)
                elif kl in TEXT_SANITIZE_KEYS and isinstance(v, str):
                    result[k] = _strip_phase2_from_text(v)
                elif kl in LIST_SANITIZE_KEYS and isinstance(v, list):
                    result[k] = _strip_phase2_from_list(v)
                else:
                    result[k] = walk(v)
            return result
        if isinstance(obj, list):
            return [walk(item) for item in obj]
        return obj

    p1 = walk(p1)

    # Extract entity names for explicit Phase 1 scope
    entities = _extract_entity_names(assessment['data_features'], intake)

    # Build deferred items list (for the note)
    deferred_items = list(assessment['intelligence_features'])
    # Also note any stripped tasks
    orig_tasks = recursive_get_lists(intake, TASK_LIST_KEYS)
    stripped_tasks = recursive_get_lists(p1, TASK_LIST_KEYS)
    stripped_count = len(orig_tasks) - len(stripped_tasks)

    # ── Feature-level state: acceptance criteria + allowed files per entity ──
    # Mirrors slice_planner's per-slice structure so the harness can track
    # pass/fail per feature and scope fix prompts to failing features only.
    feature_state = []
    for entity in entities:
        slug = entity.lower().rstrip('s')
        plural = slug + 's' if not slug.endswith('s') else slug
        page_name = entity.rstrip('s') + 'Page'  # e.g. Horse → HorsePage
        allowed = [
            f"business/models/{plural}.py",
            f"business/schemas/{plural}.py",
            f"business/services/{plural}_service.py",
            f"business/backend/routes/{plural}.py",
            f"business/frontend/pages/{page_name}.jsx",
        ]
        criteria = [
            f"SQLAlchemy model class exists in business/models/{plural}.py with appropriate Columns",
            f"CRUD service in business/services/{plural}_service.py has create/get/list/update/delete methods",
            f"FastAPI routes in business/backend/routes/{plural}.py expose GET/POST/PUT/DELETE endpoints",
            f"{page_name}.jsx renders a list view and supports create/edit actions",
            f"All imports between model/schema/service/route resolve correctly",
        ]
        # Find the original feature description that maps to this entity
        feature_desc = next(
            (f for f in assessment['data_features']
             if entity.lower() in f.lower() or slug in f.lower()),
            entity
        )
        feature_state.append({
            'feature': feature_desc,
            'entity': entity,
            'status': 'pending',
            'allowed_files': allowed,
            'acceptance_criteria': criteria,
        })

    # Suffix startup_idea_id so Phase 1 and Phase 2 run dirs/ZIPs are distinct
    if 'startup_idea_id' in p1:
        p1['startup_idea_id'] = p1['startup_idea_id'].rstrip('_') + '_p1'
    p1['_phase_context'] = {
        'phase': 1,
        'of_phases': 2,
        'scope': 'DATA_LAYER — CRUD, entities, basic views only',
        'entities_to_build': entities,
        'feature_state': feature_state,
        'deferred_to_phase2': deferred_items,
        'kpis_deferred': assessment['kpis'],
        'tasks_stripped': stripped_count,
        'note': (
            'Build ONLY the data-collection layer: SQLAlchemy models, Pydantic schemas, '
            'CRUD services (create/get/list/update/delete), FastAPI routes, and basic '
            'frontend list/detail pages for each entity. '
            'HARD PROHIBITIONS for Phase 1: '
            '(1) No external API integrations (Equineline, TrueNicks, Shopify, Stripe API calls, etc.) '
            '(2) No KPI calculation, scoring, analytics, report generation, or dashboard charts '
            '(3) No AI/ML features, recommendations, or predictions '
            '(4) No PDF/export generation '
            '(5) No email automation or webhook handlers '
            '(6) No merchandise/e-commerce features '
            'If the intake mentions any of these, IGNORE THEM — they are Phase 2 scope. '
            'Phase 1 entities: ' + ', '.join(entities) + '. '
            'For each entity build exactly: 1 model, 1 schema, 1 service (sync CRUD), '
            '1 route file, 1 frontend page.'
        ),
    }
    return p1


def build_phase2_intake(intake: dict, assessment: dict) -> dict:
    """
    Phase 2 intake: full picture with phase context.
    - All original features retained
    - _phase_context tells Claude what Phase 1 already built
    - Includes explicit do-not-regenerate file list
    """
    p2 = copy.deepcopy(intake)

    # Build a plausible Phase 1 file list from data features
    # (harness will override this with the real Phase 1 manifest at runtime)
    p1_route_files = []
    p1_model_files = []
    p1_page_files  = []
    for f in assessment['data_features']:
        slug = re.sub(r'[^a-z0-9]+', '_', f.lower()).strip('_')
        if slug:
            p1_route_files.append(f'business/backend/routes/{slug}.py')
            p1_model_files.append(f'business/models/{slug.capitalize()}.py')
            p1_page_files.append(f'business/frontend/pages/{slug.capitalize()}.jsx')

    # ── Feature-level state for Phase 2 intelligence features ──
    p2_feature_state = []
    for feat in assessment['intelligence_features']:
        slug = re.sub(r'[^a-z0-9]+', '_', feat.lower()).strip('_')
        # Intelligence features typically need a service + route + possibly a page
        allowed = [
            f"business/services/{slug}_service.py",
            f"business/backend/routes/{slug}.py",
        ]
        criteria = [
            f"Service in business/services/{slug}_service.py implements the core logic for: {feat}",
            f"Route in business/backend/routes/{slug}.py exposes API endpoint(s) for: {feat}",
            f"All imports from Phase 1 models resolve correctly",
        ]
        # Add KPI-specific criteria if this feature involves scoring/KPIs
        feat_lower = feat.lower()
        if any(kw in feat_lower for kw in ('kpi', 'scor', 'metric', 'analytic')):
            criteria.append("KPI calculations produce numeric results, not stubs or placeholders")
        if any(kw in feat_lower for kw in ('report', 'export', 'download', 'pdf')):
            criteria.append("Export/download endpoint returns a file response, not just JSON")
            allowed.append(f"business/frontend/pages/{slug.title().replace('_', '')}Page.jsx")
        if any(kw in feat_lower for kw in ('dashboard', 'chart', 'visual')):
            allowed.append(f"business/frontend/pages/{slug.title().replace('_', '')}Page.jsx")
            criteria.append("Dashboard page renders data from API, not hardcoded values")

        p2_feature_state.append({
            'feature': feat,
            'entity': slug,
            'status': 'pending',
            'allowed_files': allowed,
            'acceptance_criteria': criteria,
        })

    # Suffix startup_idea_id so Phase 1 and Phase 2 run dirs/ZIPs are distinct
    if 'startup_idea_id' in p2:
        p2['startup_idea_id'] = p2['startup_idea_id'].rstrip('_') + '_p2'
    # Extract required integrations from intake for Phase 2
    _integration_map = {
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
    _intake_blob = json.dumps(intake, ensure_ascii=False).lower()
    p2_required_integrations = []
    for key, info in _integration_map.items():
        if key in _intake_blob:
            p2_required_integrations.append(info)

    p2['_phase_context'] = {
        'phase': 2,
        'of_phases': 2,
        'scope': 'INTELLIGENCE_LAYER — KPIs, scoring, reports, analytics',
        'phase1_completed_features': assessment['data_features'],
        'phase1_do_not_regenerate': p1_route_files + p1_model_files + p1_page_files,
        'kpis_to_implement': assessment['kpis'],
        'required_integrations': p2_required_integrations,
        'phase2_new_features': assessment['intelligence_features'],
        'feature_state': p2_feature_state,
        'note': (
            'Phase 1 (data layer) is already built and QA-accepted. '
            'DO NOT regenerate Phase 1 files. '
            'Output ONLY the new intelligence-layer files: '
            'KPI calculation, scoring service, report generation, '
            'analytics routes, dashboard upgrades, and export endpoints. '
            'You may import from Phase 1 models and routes freely.'
        ),
    }
    return p2


# ── Reporting ─────────────────────────────────────────────────────────────────

# ── AI Decomposer ────────────────────────────────────────────────────────────

DECOMPOSER_PROMPT = """You are a software architect decomposing a startup intake spec into buildable mini specs for Phase 1 (data layer only).

Read the full intake below. Your job:
1. Identify ONLY entities that are explicitly named or strictly necessary to satisfy a named Phase 1 user-visible capability in the intake
2. For each entity, specify exact fields with SQLAlchemy types
3. Define CRUD operations as FastAPI endpoints
4. Map dependencies (foreign keys between entities)
5. Describe the frontend page (React, list + detail views)
6. Explicitly list what is OUT OF SCOPE for this entity in Phase 1

RULES — ABSOLUTE:
- Phase 1 is DATA LAYER ONLY: models, schemas, services (sync CRUD), routes, basic pages
- "Data layer only" means ALL entities that store and manage user data — NOT "absolute minimum"
- If a feature says "create X", "manage X", "build X system", "setup X framework" → that IS a data entity
- Content management systems, member portals, educational content pages — these are ALL data layer entities that need models + CRUD
- External API integrations (Shopify, Equineline, TrueNicks, Stripe API calls, any third-party) are Phase 2 — do NOT include as entities or fields
- Computed features (analytics, reports, scoring, recommendations, PDF export) are Phase 2
- Email automation, webhook handlers, background tasks are Phase 2
- Every entity gets exactly: 1 model, 1 schema, 1 service, 1 route file, 1 frontend page
- Standard fields on EVERY model (do NOT list these in fields — they are automatic): id (UUID, primary key), owner_id (String, from auth), status (String, default "active"), created_at (DateTime), updated_at (DateTime)
- All services are synchronous (no async def)
- All routes use Depends(get_current_user) for auth
- Route file names use underscores, NEVER hyphens: membership_plans.py NOT membership-plans.py
- Frontend page file extension is .jsx NOT .tsx
- Every entity MUST include at least 1 evidence phrase copied verbatim from the intake
- Do NOT create an entity only because it is common in similar systems — but DO create entities for every explicit feature in the intake that involves storing/managing data
- Do NOT create fields for external integration IDs, analytics outputs, webhook states, automation schedules, or future-phase computations
- Do NOT add fields like sire_name, dam_name, breeding_score, auction_value unless the intake EXPLICITLY mentions them
- IMPORTANT: Be thorough with fields. Each entity should have 5-10 meaningful fields based on what the intake describes. A horse profile for a thoroughbred site needs more than just name/bio/image. Read the intake carefully for domain-specific attributes.
- IMPORTANT: Do NOT under-extract. If the intake lists 10 features and 6 are data-layer CRUD, you should produce ~6 entities, not 2. Rejecting an entity that has an explicit "create X" or "build X" feature in the intake is WRONG.
- CRITICAL DISTINCTION: "Set up X signup" or "collect X" = Phase 1 data entity (store the data). "Automate X" or "send X sequences" = Phase 2 automation. Example: "Set up email list signup" → Phase 1 EmailSubscriber entity (name, email, signup_date). "Setup email automation" → Phase 2 (sending drip campaigns). These are DIFFERENT features — do not conflate them.
- CRITICAL DISTINCTION: "Setup member portal framework" = Phase 1 Member entity (profiles, basic access, tier assignment). "Configure payment processing" = Phase 2 Stripe integration. A portal framework needs a data model for members even without payments. Do NOT reject Member just because payments exist elsewhere in the intake.
- CRITICAL DISTINCTION: "Build content management system" = Phase 1 CMS entity with CRUD for managing content pages. This is a core data-layer feature, NOT Phase 2.

OUTPUT CONTRACT — return ONLY valid JSON with this exact structure:
{
  "phase": 1,
  "scope": "data_layer_only",
  "entities": [
    {
      "entity": "EntityName",
      "build_order": 1,
      "evidence": ["exact phrase from intake supporting this entity"],
      "inclusion_reason": "one sentence explaining why this entity is needed",
      "fields": [
        {"name": "field_name", "type": "String|Text|Integer|Boolean|DateTime|JSON|Numeric|Float", "constraints": ["nullable=False"], "default": null}
      ],
      "crud_operations": ["GET /entity_name", "GET /entity_name/{id}", "POST /entity_name", "PUT /entity_name/{id}", "DELETE /entity_name/{id}"],
      "dependencies": [],
      "relationship_cardinality": [{"related_entity": "Other", "type": "many_to_one", "fk_field": "other_id"}],
      "frontend_page": {
        "route": "/entity-name",
        "list_view": ["field1", "field2"],
        "detail_view": ["field1", "field2", "field3"]
      },
      "out_of_scope": ["specific things NOT to build"],
      "deferred_related_capabilities": ["Phase 2 features related to this entity"],
      "acceptance_checks": ["model compiles", "CRUD works synchronously", "routes require auth", "page renders list and detail"],
      "file_contract": {
        "allowed_files": ["models/entity_name.py", "schemas/entity_name.py", "services/entity_name_service.py", "routes/entity_name.py", "pages/EntityName.jsx"]
      },
      "forbidden_expansions": ["Do not add X", "Do not add Y"],
      "open_questions": ["anything ambiguous in the intake"]
    }
  ],
  "deferred_items": ["list of capabilities explicitly deferred to Phase 2"],
  "rejected_candidates": [{"name": "EntityName", "reason": "why it was rejected"}]
}

No markdown. No explanation. No code fences. ONLY the JSON object.

INTAKE:
"""


def decompose_intake(intake: dict, api_key: str = '', startup_id: str = '') -> dict:
    """
    Use ChatGPT to decompose the full intake into mini specs for Phase 1 entities.
    Returns the structured decomposition JSON, or None on failure.
    """
    if not api_key:
        api_key = os.environ.get('OPENAI_API_KEY', '')
    if not api_key:
        print('  [DECOMPOSER] No OPENAI_API_KEY — cannot run AI decomposer')
        return None

    try:
        import openai
        client = openai.OpenAI(api_key=api_key)

        intake_json = json.dumps(intake, indent=2, default=str)
        prompt = DECOMPOSER_PROMPT + intake_json

        prompt_len = len(prompt)
        print(f'  [DECOMPOSER] Sending intake to ChatGPT (gpt-4o)')
        print(f'  [DECOMPOSER] Prompt: ~{prompt_len:,} chars, '
              f'~{prompt_len // 4:,} est. tokens')
        print(f'  [DECOMPOSER] Waiting for response...')

        t0 = time.time()
        resp = client.chat.completions.create(
            model='gpt-4o',
            temperature=0.2,
            max_tokens=8192,
            messages=[{'role': 'user', 'content': prompt}],
        )
        elapsed = time.time() - t0

        raw = resp.choices[0].message.content.strip()
        in_tok = resp.usage.prompt_tokens
        out_tok = resp.usage.completion_tokens
        cost = _calc_cost('gpt-4o', in_tok, out_tok)

        print(f'  [DECOMPOSER] Response in {elapsed:.1f}s — '
              f'{in_tok:,} in / {out_tok:,} out — ${cost:.4f}')

        _log_ai_cost(COST_CSV, 'decompose_intake', 'gpt-4o',
                     in_tok, out_tok, cost, elapsed, startup_id,
                     f'prompt {prompt_len} chars')

        # Strip code fences if present
        if raw.startswith('```'):
            raw = re.sub(r'^```\w*\n?', '', raw)
            raw = re.sub(r'\n?```$', '', raw)

        result = json.loads(raw)
        n_entities = len(result.get('entities', []))
        n_deferred = len(result.get('deferred_items', []))
        n_rejected = len(result.get('rejected_candidates', []))
        print(f'  [DECOMPOSER] Parsed: {n_entities} entities, '
              f'{n_deferred} deferred, {n_rejected} rejected')

        # Print entity summary
        for ent in result.get('entities', []):
            n_fields = len(ent.get('fields', []))
            n_crud = len(ent.get('crud_operations', []))
            deps = ', '.join(ent.get('dependencies', [])) or 'none'
            print(f'    [{ent.get("build_order", "?")}] {ent["entity"]}: '
                  f'{n_fields} fields, {n_crud} CRUD ops, deps={deps}')

        if result.get('deferred_items'):
            print(f'  [DECOMPOSER] Deferred to Phase 2:')
            for d in result['deferred_items']:
                print(f'    → {d}')

        if result.get('rejected_candidates'):
            print(f'  [DECOMPOSER] Rejected candidates:')
            for r in result['rejected_candidates']:
                if isinstance(r, dict):
                    print(f'    ✗ {r.get("name", "?")}: {r.get("reason", "")}')
                else:
                    print(f'    ✗ {r}')

        return result

    except json.JSONDecodeError as e:
        print(f'  [DECOMPOSER] Failed to parse JSON: {e}')
        print(f'  [DECOMPOSER] Raw output (first 500 chars): {raw[:500]}')
        return None
    except Exception as e:
        print(f'  [DECOMPOSER] API call failed: {e}')
        return None


def check_coverage(decomposition: dict, data_features: list) -> list:
    """
    Cross-check: every DATA_LAYER feature from the classifier should be
    covered by at least one entity's evidence or inclusion_reason.
    Returns list of uncovered features (excluding legitimately Phase 2 items).
    """
    if not decomposition or not data_features:
        return []

    # Collect all evidence, inclusion reasons, and out_of_scope from entities
    covered_text = ''
    for ent in decomposition.get('entities', []):
        for ev in ent.get('evidence', []):
            covered_text += ' ' + ev.lower()
        covered_text += ' ' + ent.get('inclusion_reason', '').lower()
        covered_text += ' ' + ent.get('entity', '').lower()
        # Also count out_of_scope and forbidden_expansions as "covered by this entity"
        for oos in ent.get('out_of_scope', []):
            covered_text += ' ' + oos.lower()
        for fe in ent.get('forbidden_expansions', []):
            covered_text += ' ' + fe.lower()
        # File contract file names contribute coverage (e.g. "content_page" covers "content")
        for af in ent.get('file_contract', {}).get('allowed_files', []):
            covered_text += ' ' + af.replace('_', ' ').replace('/', ' ').lower()

    # Also check deferred items (legitimately deferred = covered)
    for d in decomposition.get('deferred_items', []):
        covered_text += ' ' + d.lower()

    uncovered = []
    for feat in data_features:
        fl = feat.lower()

        # Skip features that are legitimately Phase 2 (external integrations)
        if any(kw in fl for kw in PHASE2_STRIP_KEYWORDS):
            continue

        # Skip features that don't imply a database entity
        NON_ENTITY_PHRASES = [
            'static website structure', 'website layout', 'page layout',
            'css', 'html structure', 'navigation', 'landing page design',
        ]
        if any(p in fl for p in NON_ENTITY_PHRASES):
            continue

        # Extract key nouns from feature (skip generic verbs)
        key_words = [w for w in re.findall(r'[a-z]+', fl)
                     if w not in {'create', 'set', 'up', 'build', 'setup', 'manage',
                                  'configure', 'write', 'add', 'make', 'the', 'and',
                                  'for', 'with', 'a', 'an', 'of', 'to', 'static'}]
        # If at least half the key words appear in covered text, it's covered
        if key_words:
            hits = sum(1 for w in key_words if w in covered_text)
            if hits < len(key_words) * 0.5:
                uncovered.append(feat)

    return uncovered


RETRY_PROMPT = """You previously decomposed a startup intake into Phase 1 entities but MISSED these data-layer features:

{uncovered_features}

These features were classified as DATA_LAYER by the system. They involve storing and managing data — NOT external integrations, NOT analytics, NOT automation.

Your previous entities were: {existing_entities}

For EACH uncovered feature above, produce an entity mini spec. Use the SAME JSON structure as before.
Return ONLY a JSON array of entity objects (same structure as before). No markdown, no explanation.

Remember:
- "member portal framework" = Member entity (name, email, tier, join_date etc.) — NOT payment processing
- "content management system" = CMS/ContentPage entity (title, body, slug, published etc.) — basic CRUD
- Standard fields (id, owner_id, status, created_at, updated_at) are automatic — do NOT list them
- Route files use underscores, pages use .jsx
- 5-10 meaningful fields per entity

INTAKE (for reference):
{intake_json}
"""


def _retry_coverage_gaps(intake: dict, uncovered: list, decomposition: dict,
                         api_key: str, startup_id: str = '') -> list:
    """
    Second ChatGPT call to fill coverage gaps.
    Returns list of new entity specs, or empty list on failure.
    """
    try:
        import openai
        client = openai.OpenAI(api_key=api_key)

        existing = ', '.join(e['entity'] for e in decomposition.get('entities', []))
        intake_json = json.dumps(intake, indent=2, default=str)
        prompt = RETRY_PROMPT.format(
            uncovered_features='\n'.join(f'- {f}' for f in uncovered),
            existing_entities=existing,
            intake_json=intake_json,
        )

        prompt_len = len(prompt)
        print(f'  [RETRY] Sending {len(uncovered)} gap(s) to ChatGPT (gpt-4o)')
        print(f'  [RETRY] Prompt: ~{prompt_len:,} chars')

        t0 = time.time()
        resp = client.chat.completions.create(
            model='gpt-4o',
            temperature=0.2,
            max_tokens=4096,
            messages=[{'role': 'user', 'content': prompt}],
        )
        elapsed = time.time() - t0

        raw = resp.choices[0].message.content.strip()
        in_tok = resp.usage.prompt_tokens
        out_tok = resp.usage.completion_tokens
        cost = _calc_cost('gpt-4o', in_tok, out_tok)

        print(f'  [RETRY] Response in {elapsed:.1f}s — '
              f'{in_tok:,} in / {out_tok:,} out — ${cost:.4f}')

        _log_ai_cost(COST_CSV, 'retry_coverage_gaps', 'gpt-4o',
                     in_tok, out_tok, cost, elapsed, startup_id,
                     f'{len(uncovered)} gaps')

        # Strip code fences if present
        if raw.startswith('```'):
            raw = re.sub(r'^```\w*\n?', '', raw)
            raw = re.sub(r'\n?```$', '', raw)

        parsed = json.loads(raw)
        if isinstance(parsed, dict) and 'entities' in parsed:
            entities = parsed['entities']
        elif isinstance(parsed, list):
            entities = parsed
        elif isinstance(parsed, dict) and 'entity' in parsed:
            entities = [parsed]
        else:
            print(f'  [RETRY] Unexpected response shape: {type(parsed)}')
            print(f'  [RETRY] Keys: {list(parsed.keys()) if isinstance(parsed, dict) else "N/A"}')
            return []

        # Filter out entities without required 'entity' key
        valid = []
        for ent in entities:
            if not isinstance(ent, dict):
                continue
            # Handle common alternate keys for entity name
            if 'entity' not in ent:
                for alt_key in ('entity_name', 'name', 'entityName'):
                    if alt_key in ent:
                        ent['entity'] = ent[alt_key]
                        break
            if 'entity' not in ent:
                print(f'  [RETRY] Skipping entity without name: {list(ent.keys())}')
                continue
            valid.append(ent)

        for ent in valid:
            n_fields = len(ent.get('fields', []))
            print(f'    + {ent["entity"]}: {n_fields} fields')

        return valid

    except Exception as e:
        print(f'  [RETRY] Failed: {e}')
        return []


def _normalize_entity_schema(entity: dict) -> dict:
    """
    Normalize retry entities that come back in a different schema.
    Converts field_name/field_type → name/type, adds missing file_contract, etc.
    """
    ename = entity.get('entity', 'Unknown')
    slug = re.sub(r'[^a-z0-9]+', '_', ename.lower()).strip('_')

    # Normalize fields: field_name/field_type → name/type with SQLAlchemy types
    TYPE_MAP = {
        'string': 'String', 'str': 'String', 'text': 'Text',
        'integer': 'Integer', 'int': 'Integer', 'number': 'Integer',
        'boolean': 'Boolean', 'bool': 'Boolean',
        'date': 'DateTime', 'datetime': 'DateTime',
        'json': 'JSON', 'array': 'JSON', 'object': 'JSON',
        'float': 'Float', 'decimal': 'Numeric', 'numeric': 'Numeric',
    }
    if entity.get('fields') and isinstance(entity['fields'][0], dict):
        if 'field_name' in entity['fields'][0]:
            new_fields = []
            for f in entity['fields']:
                raw_type = str(f.get('field_type', f.get('type', 'String'))).lower()
                new_fields.append({
                    'name': f.get('field_name', f.get('name', '')),
                    'type': TYPE_MAP.get(raw_type, 'String'),
                    'constraints': f.get('constraints', ['nullable=True']),
                    'default': f.get('default', None),
                })
            entity['fields'] = new_fields

    # Ensure file_contract exists with standard structure
    if 'file_contract' not in entity or not entity['file_contract'].get('allowed_files'):
        plural = slug + 's' if not slug.endswith('s') else slug
        entity['file_contract'] = {
            'allowed_files': [
                f'models/{slug}.py',
                f'schemas/{slug}.py',
                f'services/{slug}_service.py',
                f'routes/{plural}.py',
                f'pages/{ename}.jsx',
            ]
        }

    # Ensure crud_operations exists
    if 'crud_operations' not in entity:
        plural = slug + 's' if not slug.endswith('s') else slug
        entity['crud_operations'] = [
            f'GET /{plural}',
            f'GET /{plural}/{{id}}',
            f'POST /{plural}',
            f'PUT /{plural}/{{id}}',
            f'DELETE /{plural}/{{id}}',
        ]

    # Ensure other required fields
    entity.setdefault('evidence', [])
    entity.setdefault('inclusion_reason', '')
    entity.setdefault('dependencies', [])
    entity.setdefault('relationship_cardinality', [])
    entity.setdefault('frontend_page', {
        'route': f'/{slug.replace("_", "-")}',
        'list_view': [f['name'] for f in entity.get('fields', [])[:3]],
        'detail_view': [f['name'] for f in entity.get('fields', [])],
    })
    entity.setdefault('out_of_scope', [])
    entity.setdefault('deferred_related_capabilities', [])
    entity.setdefault('acceptance_checks', [
        'model compiles', 'CRUD works synchronously',
        'routes require auth', 'page renders list and detail',
    ])
    entity.setdefault('forbidden_expansions', [])
    entity.setdefault('open_questions', [])

    # Remove non-standard keys from retry response
    for junk_key in ('routes', 'pages', 'entity_name'):
        entity.pop(junk_key, None)

    return entity


def validate_mini_specs(decomposition: dict) -> dict:
    """
    Deterministic validation of AI-produced mini specs.
    Enforces harness rules: underscore filenames, .jsx extension, standard fields,
    no external integration IDs, no Phase 2 leakage.
    Returns cleaned decomposition with any fixes applied.
    """
    if not decomposition or 'entities' not in decomposition:
        return decomposition

    fixes = []

    for i, entity in enumerate(decomposition['entities']):
        # Normalize schema first (handles retry entities with different format)
        decomposition['entities'][i] = _normalize_entity_schema(entity)
        entity = decomposition['entities'][i]

        ename = entity.get('entity', 'Unknown')

        # Fix 1: Ensure file_contract uses underscores and .jsx
        fc = entity.get('file_contract', {})
        if 'allowed_files' in fc:
            fixed_files = []
            for f in fc['allowed_files']:
                # Hyphens → underscores in Python files
                if f.endswith('.py'):
                    old = f
                    f = f.replace('-', '_')
                    if f != old:
                        fixes.append(f'{ename}: fixed hyphen in {old} → {f}')
                # .tsx → .jsx
                if f.endswith('.tsx'):
                    old = f
                    f = f[:-4] + '.jsx'
                    fixes.append(f'{ename}: fixed .tsx → .jsx in {old}')
                fixed_files.append(f)
            fc['allowed_files'] = fixed_files

        # Fix 2: Strip external integration ID fields
        EXTERNAL_ID_PATTERNS = [
            'shopify_', 'stripe_', 'equineline_', 'truenicks_',
            'external_', 'webhook_', 'sync_', 'integration_',
        ]
        if 'fields' in entity:
            clean_fields = []
            for field in entity['fields']:
                fname = field.get('name', '').lower()
                if any(fname.startswith(p) for p in EXTERNAL_ID_PATTERNS):
                    fixes.append(f'{ename}: stripped external field {fname}')
                    continue
                clean_fields.append(field)
            entity['fields'] = clean_fields

        # Fix 3: Strip standard fields if AI included them (they're automatic)
        STANDARD_FIELDS = {'id', 'owner_id', 'status', 'created_at', 'updated_at'}
        if 'fields' in entity:
            entity['fields'] = [
                f for f in entity['fields']
                if f.get('name', '').lower() not in STANDARD_FIELDS
            ]

        # Fix 4: Ensure CRUD operations use underscores in URLs
        if 'crud_operations' in entity:
            entity['crud_operations'] = [
                op.replace('-', '_') for op in entity['crud_operations']
            ]

        # Fix 5: Ensure frontend route uses hyphens (URL convention)
        # (URLs use hyphens, filenames use underscores — this is correct)

    if fixes:
        print(f'  [VALIDATOR] Applied {len(fixes)} fix(es):')
        for f in fixes:
            print(f'    → {f}')

    return decomposition


def build_entity_intakes(intake: dict, decomposition: dict, assessment: dict,
                         output_dir: Path, stem: str) -> list:
    """
    Produce one intake JSON per entity from the decomposition.
    Each intake JSON contains the original intake data PLUS a _mini_spec key
    with the entity's full mini spec. The harness detects _mini_spec and uses it
    to constrain the build.

    Returns list of (entity_name, intake_path, build_order) tuples sorted by build_order.
    """
    entity_intakes = []

    for entity_spec in decomposition.get('entities', []):
        ename = entity_spec['entity']
        build_order = entity_spec.get('build_order', 99)

        # Create entity-specific intake
        entity_intake = copy.deepcopy(intake)

        # Suffix startup_idea_id for unique run dirs/ZIPs
        slug = re.sub(r'[^a-z0-9]+', '_', ename.lower()).strip('_')
        base_id = intake.get('startup_idea_id', stem).rstrip('_')
        entity_intake['startup_idea_id'] = f'{base_id}_p1_{slug}'

        # Inject mini spec — the harness will detect this and use it
        entity_intake['_mini_spec'] = entity_spec

        # Inject phase context
        all_entities = [e['entity'] for e in decomposition.get('entities', [])]
        entity_intake['_phase_context'] = {
            'phase': 1,
            'of_phases': 2,
            'scope': f'DATA_LAYER — {ename} entity ONLY',
            'current_entity': ename,
            'all_phase1_entities': all_entities,
            'deferred_to_phase2': decomposition.get('deferred_items', []),
            'note': (
                f'Build ONLY the {ename} entity. '
                f'Allowed files: {", ".join(entity_spec.get("file_contract", {}).get("allowed_files", []))}. '
                f'Do NOT create any other files. '
                f'Do NOT build any other entities. '
                + (' '.join(entity_spec.get('forbidden_expansions', [])))
            ),
        }

        # Write entity intake
        entity_path = output_dir / f'{stem}_p1_{slug}.json'
        with open(entity_path, 'w', encoding='utf-8') as f:
            json.dump(entity_intake, f, indent=2)

        entity_intakes.append((ename, entity_path, build_order))
        print(f'  Entity intake: {entity_path.name} (order {build_order})')

    # Sort by build_order
    entity_intakes.sort(key=lambda x: x[2])
    return entity_intakes


def print_assessment(assessment: dict) -> None:
    phases = assessment['phases']
    print(f'\nRESULT: {phases}-PHASE BUILD')
    print(f'Reason: {assessment["reason"]}')

    if assessment['kpis']:
        print(f'\nKPIs ({len(assessment["kpis"])}): {", ".join(assessment["kpis"])}')

    print('\nFeature classification:')
    for feature, cls in assessment['features'].items():
        tag = '[INTELLIGENCE]' if cls == 'INTELLIGENCE_LAYER' else '[DATA      ]'
        print(f'  {tag}  {feature}')

    if assessment['intelligence_features']:
        print(f'\nPhase 1 (data):        {len(assessment["data_features"])} feature(s)')
        print(f'Phase 2 (intelligence): {len(assessment["intelligence_features"])} feature(s)')


def print_next_steps(p1_path: Path, p2_path: Path, stem: str) -> None:
    print(f"""
Next steps:
  1. Run Phase 1 (data layer):
       python fo_test_harness.py \\
         --intake {p1_path} \\
         --startup-id {stem}_p1 \\
         --block B \\
         --build-gov <path/to/gov.zip>

  2. After Phase 1 QA_ACCEPTED, run Phase 2 (intelligence layer):
       python fo_test_harness.py \\
         --intake {p2_path} \\
         --startup-id {stem}_p2 \\
         --block B \\
         --build-gov <path/to/gov.zip>

  Note: Phase 2 build prompt will include _phase_context so Claude
        scopes output to intelligence-layer files only.
""")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description='Analyze intake JSON and split into 1 or 2 build phases.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('--intake',     required=True,
                        help='Path to intake JSON file')
    parser.add_argument('--output-dir', default=None,
                        help='Output directory (default: same directory as intake)')
    parser.add_argument('--no-ai',      action='store_true',
                        help='Disable AI classification (rule-based only)')
    parser.add_argument('--threshold',  type=int, default=FEATURE_COUNT_THRESHOLD,
                        help=f'Feature count threshold for 2-phase '
                             f'(default: {FEATURE_COUNT_THRESHOLD})')
    args = parser.parse_args()

    intake_path = Path(args.intake)
    if not intake_path.exists():
        print(f'ERROR: Intake file not found: {intake_path}')
        sys.exit(1)

    # Early-exit if a final ZIP already exists for this intake — no point re-planning.
    _stem = intake_path.stem
    _existing_zips = sorted(Path('fo_harness_runs').glob(f'{_stem}_BLOCK_B_full_*.zip')) if Path('fo_harness_runs').exists() else []
    if _existing_zips:
        print(f'✓ Already complete — final ZIP exists: {_existing_zips[-1]}')
        print('  Delete it and rerun to rebuild from scratch.')
        sys.exit(0)

    try:
        with open(intake_path, 'r', encoding='utf-8') as f:
            intake = json.load(f)
    except json.JSONDecodeError as e:
        print(f'ERROR: Invalid JSON in {intake_path}: {e}')
        sys.exit(1)

    output_dir = Path(args.output_dir) if args.output_dir else intake_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    api_key = os.environ.get('ANTHROPIC_API_KEY', '')
    use_ai  = (not args.no_ai) and bool(api_key)

    stem = intake_path.stem

    print(f'\nPhase Planner')
    print('=' * 60)
    print(f'Intake:  {intake_path}')
    print(f'Output:  {output_dir}')
    print(f'AI:      {"enabled (Claude Haiku)" if use_ai else "disabled (rule-based only)"}')
    print(f'Threshold: {args.threshold} features')
    print()

    print('Analyzing intake...')
    result = assess(intake, use_ai=use_ai, api_key=api_key, threshold=args.threshold,
                    startup_id=stem)

    print_assessment(result)

    assessment_path = output_dir / f'{stem}_phase_assessment.json'
    with open(assessment_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2)
    print(f'\nAssessment saved: {assessment_path}')

    if result['phases'] == 1:
        print('\nSingle phase — proceed with standard harness run.')
        print(f'  python fo_test_harness.py --intake {intake_path} ...')
        return

    # 2-phase split
    print('\nGenerating split intakes...')

    # ── AI Decomposer: break Phase 1 into entity-level mini specs ────────────
    openai_key = os.environ.get('OPENAI_API_KEY', '')
    decomposition = None
    if not args.no_ai and openai_key:
        print('\n▶ AI DECOMPOSER — Breaking Phase 1 into entity mini specs')
        print('─' * 60)
        decomposition = decompose_intake(intake, api_key=openai_key, startup_id=stem)
        if decomposition:
            decomposition = validate_mini_specs(decomposition)

            # Coverage check: are all data features accounted for?
            uncovered = check_coverage(decomposition, result['data_features'])
            if uncovered:
                print(f'\n  ⚠ COVERAGE GAP — {len(uncovered)} data feature(s) not covered:')
                for uf in uncovered:
                    print(f'    ✗ {uf}')

                # Targeted retry: ask ChatGPT to reconsider only the uncovered features
                print(f'\n  [DECOMPOSER] Retry: asking ChatGPT to produce entities for gaps...')
                gap_entities = _retry_coverage_gaps(
                    intake, uncovered, decomposition, openai_key, stem
                )
                if gap_entities:
                    # Merge new entities into decomposition
                    max_order = max(
                        (e.get('build_order', 0) for e in decomposition['entities']),
                        default=0
                    )
                    for ge in gap_entities:
                        ge['build_order'] = max_order + ge.get('build_order', 1)
                        max_order = ge['build_order']
                    decomposition['entities'].extend(gap_entities)
                    decomposition = validate_mini_specs(decomposition)
                    print(f'  [DECOMPOSER] Total entities after gap fill: '
                          f'{len(decomposition["entities"])}')

                    # Re-check coverage
                    still_uncovered = check_coverage(decomposition, result['data_features'])
                    if still_uncovered:
                        print(f'  ⚠ Still uncovered after retry: {still_uncovered}')
                    else:
                        print(f'  ✓ All data features now covered')

            # Save decomposition for debugging
            decomp_path = output_dir / f'{stem}_decomposition.json'
            with open(decomp_path, 'w', encoding='utf-8') as f:
                json.dump(decomposition, f, indent=2)
            print(f'  Decomposition saved: {decomp_path}')

            # Generate per-entity intake files
            print('\n▶ ENTITY INTAKES')
            print('─' * 60)
            entity_intakes = build_entity_intakes(
                intake, decomposition, result, output_dir, stem
            )

            # Save entity order to assessment for run_integration_and_feature_build.sh
            result['entity_intakes'] = [
                {'entity': name, 'intake_file': str(path), 'build_order': order}
                for name, path, order in entity_intakes
            ]
            result['decomposition_mode'] = 'ai_mini_specs'
        else:
            print('  [DECOMPOSER] Failed — falling back to monolithic Phase 1 intake')

    # Always generate the legacy monolithic intakes (Phase 1 + Phase 2)
    # Phase 1 monolithic is used as fallback if decomposer fails
    p1 = build_phase1_intake(intake, result)
    p2 = build_phase2_intake(intake, result)

    p1_path = output_dir / f'{stem}_phase1.json'
    p2_path = output_dir / f'{stem}_phase2.json'

    with open(p1_path, 'w', encoding='utf-8') as f:
        json.dump(p1, f, indent=2)
    with open(p2_path, 'w', encoding='utf-8') as f:
        json.dump(p2, f, indent=2)

    print(f'\nPhase 1 intake (fallback): {p1_path}')
    print(f'Phase 2 intake: {p2_path}')

    # Re-save assessment with entity_intakes info
    with open(assessment_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2)

    if decomposition and result.get('entity_intakes'):
        print(f'\n▶ ENTITY BUILD ORDER')
        print('─' * 60)
        for ei in result['entity_intakes']:
            print(f"  {ei['build_order']}. {ei['entity']} → {Path(ei['intake_file']).name}")
        print(f'\n  Total: {len(result["entity_intakes"])} entities')
        print(f'  Mode:  AI mini specs (entity-by-entity build)')
    else:
        print_next_steps(p1_path, p2_path, stem)


if __name__ == '__main__':
    main()
