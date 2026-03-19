#!/usr/bin/env python3
"""
ubiquity.py — Ubiquitous Language Extractor

Runs BEFORE phase_planner.py. Parses an intake JSON, extracts canonical domain
terms (entities, features, user roles, KPIs, integrations), resolves synonyms,
and outputs a ubiquitous_language.json that locks terminology for the entire
pipeline: planner → build → QA.

Usage:
    python ubiquity.py --intake path/to/intake.json
    python ubiquity.py --intake path/to/intake.json --output-dir /tmp
    python ubiquity.py --intake path/to/intake.json --no-ai

Outputs:
    <stem>_ubiquitous_language.json   Canonical glossary
"""

import argparse
import csv
import json
import os
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

# ── Cost tracking ────────────────────────────────────────────────────────────

COST_CSV = 'phase_planner_ai_costs.csv'

_PRICING = {
    'claude-haiku-4-5-20251001': {'input': 0.80, 'output': 4.00},
}


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
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            caller, model, input_tokens, output_tokens,
            f'{cost_usd:.6f}', f'{duration_s:.1f}', startup_id, note,
        ])


# ── JSON helpers ─────────────────────────────────────────────────────────────

def recursive_get_lists(obj: Any, keys: set) -> list:
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
    if isinstance(obj, str):
        return obj.lower() + ' '
    if isinstance(obj, dict):
        return ''.join(recursive_text_blob(v) for v in obj.values())
    if isinstance(obj, list):
        return ''.join(recursive_text_blob(v) for v in obj)
    return ''


def recursive_get_strings(obj: Any, keys: set) -> list:
    """Collect all string values at given keys anywhere in nested structure."""
    results = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k.lower() in keys:
                if isinstance(v, str) and v.strip():
                    results.append(v.strip())
                elif isinstance(v, list):
                    for item in v:
                        if isinstance(item, str) and item.strip():
                            results.append(item.strip())
            results.extend(recursive_get_strings(v, keys))
    elif isinstance(obj, list):
        for item in obj:
            results.extend(recursive_get_strings(item, keys))
    return results


# ── Deterministic term extraction ────────────────────────────────────────────

FEATURE_KEYS = {
    'must_have_features', 'q4_must_have_features', 'features',
    'required_features', 'feature_list', 'capabilities', 'requirements',
    'must_haves', 'core_features', 'key_features', 'product_features',
}

TASK_LIST_KEYS = {'combined_task_list', 'task_list', 'tasks'}

KPI_KEYS = {
    'kpi_definitions', 'kpis', 'key_metrics', 'metrics',
    'kpi_ids', 'kpi_list', 'performance_indicators',
}

ROLE_KEYS = {
    'q2_target_user', 'target_user', 'target_users', 'user_roles',
    'user_types', 'personas', 'actors', 'stakeholders',
}

INTEGRATION_KEYS = {
    'q8_integrations', 'integrations', 'external_integrations',
    'third_party_services', 'apis',
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
    # Fallback: task-list format
    if not features:
        task_raw = recursive_get_lists(intake, TASK_LIST_KEYS)
        for item in task_raw:
            if isinstance(item, dict) and item.get('classification') == 'build':
                desc = item.get('description', '')
                if desc:
                    features.append(str(desc).strip())
    return _dedup(features)


def extract_kpis(intake: dict) -> list:
    raw = recursive_get_lists(intake, KPI_KEYS)
    kpis = []
    for item in raw:
        if isinstance(item, dict):
            kid = item.get('kpi_id') or item.get('id') or ''
            kname = item.get('kpi_name') or item.get('name') or ''
            definition = item.get('definition', '')
            kpis.append({
                'id': str(kid).strip(),
                'name': str(kname).strip(),
                'definition': str(definition).strip(),
            })
        elif isinstance(item, str) and item.strip():
            kpis.append({'id': item.strip(), 'name': item.strip(), 'definition': ''})
    return kpis


def extract_roles(intake: dict) -> list:
    raw = recursive_get_strings(intake, ROLE_KEYS)
    # Also scan hero_answers Q2
    bb = intake.get('block_b', {})
    if isinstance(bb, str):
        try:
            bb = json.loads(bb)
        except Exception:
            bb = {}
    ha = bb.get('hero_answers', {})
    q2 = ha.get('Q2_target_user', '')
    if isinstance(q2, list):
        raw.extend(str(item).strip() for item in q2 if item)
    elif q2:
        raw.append(str(q2).strip())
    return _dedup(raw)


def extract_integrations(intake: dict) -> list:
    raw = recursive_get_strings(intake, INTEGRATION_KEYS)
    bb = intake.get('block_b', {})
    if isinstance(bb, str):
        try:
            bb = json.loads(bb)
        except Exception:
            bb = {}
    ha = bb.get('hero_answers', {})
    q8 = ha.get('Q8_integrations', '')
    if isinstance(q8, list):
        raw.extend(str(item).strip() for item in q8 if item)
    elif q8:
        raw.append(str(q8).strip())
    return _dedup(raw)


def extract_entity_candidates(intake: dict, features: list) -> list:
    """Pull entity-like nouns from features + HLD + task descriptions."""
    ENTITY_PATTERNS = [
        r'\b(horse|horses)\b', r'\b(member|members)\b', r'\b(client|clients)\b',
        r'\b(user|users)\b', r'\b(project|projects)\b', r'\b(event|events)\b',
        r'\b(booking|bookings)\b', r'\b(order|orders)\b', r'\b(team|teams)\b',
        r'\b(report|reports)\b', r'\b(task|tasks)\b', r'\b(asset|assets)\b',
        r'\b(property|properties)\b', r'\b(listing|listings)\b',
        r'\b(contact|contacts)\b', r'\b(lead|leads)\b', r'\b(campaign|campaigns)\b',
        r'\b(subscription|subscriptions)\b', r'\b(payment|payments)\b',
        r'\b(invoice|invoices)\b', r'\b(profile|profiles)\b',
        r'\b(employee|employees)\b', r'\b(worker|workers)\b',
        r'\b(candidate|candidates)\b', r'\b(department|departments)\b',
        r'\b(program|programs)\b', r'\b(training|trainings)\b',
        r'\b(assessment|assessments)\b', r'\b(vendor|vendors)\b',
        r'\b(customer|customers)\b', r'\b(product|products)\b',
        r'\b(service|services)\b', r'\b(ticket|tickets)\b',
        r'\b(document|documents)\b', r'\b(content|contents)\b',
        r'\b(subscriber|subscribers)\b', r'\b(notification|notifications)\b',
        r'\b(metric|metrics)\b', r'\b(dashboard|dashboards)\b',
        r'\b(form|forms)\b', r'\b(workflow|workflows)\b',
        r'\b(organization|organizations)\b', r'\b(company|companies)\b',
    ]

    # Build text blob from features + HLD + tasks
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
    feat_text = ' '.join(features).lower()
    combined = feat_text + ' ' + hld + ' ' + task_descs

    entities = set()
    for pat in ENTITY_PATTERNS:
        if re.search(pat, combined):
            m = re.search(pat, combined)
            if m:
                # Normalize: horses → Horse (singular, capitalized)
                word = m.group(1).rstrip('s')
                if word:
                    entities.add(word.capitalize())
    return sorted(entities)


def _dedup(items: list) -> list:
    seen = set()
    result = []
    for item in items:
        key = item.lower() if isinstance(item, str) else str(item)
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


# ── Deterministic synonym detection ──────────────────────────────────────────

# Known synonym groups — if multiple appear in the same intake, pick the first as canonical
SYNONYM_GROUPS = [
    ['client', 'customer', 'account', 'buyer'],
    ['user', 'login', 'auth identity'],
    ['employee', 'worker', 'staff', 'team member', 'personnel'],
    ['member', 'subscriber', 'enrollee'],
    ['report', 'summary report'],
    ['dashboard', 'analytics dashboard'],
    ['kpi', 'metric', 'performance indicator', 'key metric'],
    ['training', 'learning program', 'course'],
    ['assessment', 'evaluation', 'review', 'appraisal'],
    ['vendor', 'supplier', 'provider', 'partner'],
    ['document', 'file', 'attachment', 'artifact'],
    ['notification', 'alert', 'message'],
    ['booking', 'reservation', 'appointment'],
    ['listing', 'property', 'real estate'],
    ['horse', 'thoroughbred', 'stallion', 'mare'],
    ['invoice', 'bill', 'payment request'],
    ['campaign', 'outreach', 'marketing campaign'],
    ['lead', 'prospect', 'opportunity'],
]


def detect_synonyms_deterministic(blob: str) -> list:
    """
    Scan the full text blob for synonym conflicts.
    Returns list of {canonical, aliases_found, aliases_to_avoid}.
    """
    conflicts = []
    for group in SYNONYM_GROUPS:
        found = [term for term in group if term in blob]
        if len(found) >= 2:
            canonical = found[0]  # first in our preferred order
            conflicts.append({
                'canonical': canonical,
                'aliases_found': found[1:],
                'aliases_to_avoid': found[1:],
            })
    return conflicts


# ── AI synonym resolution (optional) ────────────────────────────────────────

AI_PROMPT = """You are resolving domain terminology for a software build pipeline.

Given this startup intake, identify:
1. Terms that refer to the same concept (synonyms) — pick the BEST canonical term
2. Ambiguous terms that could mean different things in this domain
3. Relationships between key entities (e.g. "A Member belongs to one Organization")

INTAKE SUMMARY:
Startup: {startup_name}
Summary: {summary}
Features: {features}
KPIs: {kpis}
Roles: {roles}
Entity candidates: {entities}
Detected synonym conflicts: {conflicts}

For each synonym conflict, either CONFIRM the canonical term or OVERRIDE with a better one.
Also add any NEW synonym conflicts I missed.
Also add entity relationships you can infer.

OUTPUT FORMAT — valid JSON only, no markdown, no explanation:
{{
  "resolved_synonyms": [
    {{"canonical": "Client", "aliases_to_avoid": ["customer", "account"], "reason": "intake uses 'client' consistently"}}
  ],
  "ambiguities": [
    {{"term": "report", "meanings": ["executive PDF report", "analytics dashboard view"], "recommendation": "Use 'Executive Report' for PDF, 'Dashboard' for live view"}}
  ],
  "entity_relationships": [
    {{"from": "Client", "to": "Assessment", "type": "one_to_many", "description": "A Client has many Assessments"}}
  ]
}}
"""


def resolve_with_ai(intake: dict, features: list, kpis: list, roles: list,
                    entities: list, conflicts: list, api_key: str,
                    startup_id: str = '') -> dict:
    """Use Claude Haiku to refine synonym resolution and add relationships."""
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)

        prompt = AI_PROMPT.format(
            startup_name=intake.get('startup_name', startup_id),
            summary=intake.get('summary', '')[:500],
            features=', '.join(features[:10]),
            kpis=', '.join(k['name'] if isinstance(k, dict) else k for k in kpis[:10]),
            roles=', '.join(roles[:5]),
            entities=', '.join(entities[:15]),
            conflicts=json.dumps(conflicts, indent=2) if conflicts else 'None detected',
        )

        print(f'  [UBIQUITY AI] Calling Claude Haiku — ~{len(prompt)} chars')
        t0 = time.time()
        resp = client.messages.create(
            model='claude-haiku-4-5-20251001',
            max_tokens=1024,
            messages=[{'role': 'user', 'content': prompt}],
        )
        elapsed = time.time() - t0
        text = resp.content[0].text.strip()

        in_tok = resp.usage.input_tokens
        out_tok = resp.usage.output_tokens
        cost = _calc_cost('claude-haiku-4-5-20251001', in_tok, out_tok)
        print(f'  [UBIQUITY AI] Done in {elapsed:.1f}s — '
              f'{in_tok} in / {out_tok} out — ${cost:.4f}')

        _log_ai_cost(COST_CSV, 'ubiquity_resolve', 'claude-haiku-4-5-20251001',
                     in_tok, out_tok, cost, elapsed, startup_id,
                     f'{len(conflicts)} conflicts, {len(entities)} entities')

        # Strip code fences if present
        if text.startswith('```'):
            text = re.sub(r'^```\w*\n?', '', text)
            text = re.sub(r'\n?```$', '', text)

        return json.loads(text)

    except Exception as e:
        print(f'  [UBIQUITY AI] Failed: {e} — using deterministic results only')
        return {}


# ── Glossary builder ─────────────────────────────────────────────────────────

def build_glossary(intake: dict, use_ai: bool = True, api_key: str = '',
                   startup_id: str = '') -> dict:
    """
    Main entry point. Returns the ubiquitous language glossary dict.
    """
    startup_name = intake.get('startup_name', startup_id)
    summary = intake.get('summary', '')

    print(f'  Extracting terms from intake...')

    features = extract_features(intake)
    kpis = extract_kpis(intake)
    roles = extract_roles(intake)
    integrations = extract_integrations(intake)
    entities = extract_entity_candidates(intake, features)

    print(f'    Features:     {len(features)}')
    print(f'    KPIs:         {len(kpis)}')
    print(f'    Roles:        {len(roles)}')
    print(f'    Integrations: {len(integrations)}')
    print(f'    Entities:     {len(entities)}')

    # Deterministic synonym detection
    blob = recursive_text_blob(intake)
    conflicts = detect_synonyms_deterministic(blob)
    if conflicts:
        print(f'    Synonym conflicts: {len(conflicts)}')
        for c in conflicts:
            print(f'      {c["canonical"]} vs {c["aliases_found"]}')

    # AI refinement (optional)
    ai_result = {}
    if use_ai and api_key and (entities or conflicts):
        ai_result = resolve_with_ai(
            intake, features, kpis, roles, entities, conflicts, api_key, startup_id
        )

    # Merge deterministic + AI results
    resolved_synonyms = ai_result.get('resolved_synonyms', [])
    if not resolved_synonyms:
        # Use deterministic conflicts as-is
        resolved_synonyms = [
            {'canonical': c['canonical'], 'aliases_to_avoid': c['aliases_to_avoid'],
             'reason': 'deterministic detection'}
            for c in conflicts
        ]

    # Build the alias lookup: alias → canonical
    alias_map = {}
    for syn in resolved_synonyms:
        canonical = syn['canonical']
        for alias in syn.get('aliases_to_avoid', []):
            alias_map[alias.lower()] = canonical

    # Build entity glossary
    entity_glossary = []
    for ent in entities:
        entry = {
            'term': ent,
            'type': 'entity',
        }
        # Check if this entity has a canonical override
        if ent.lower() in alias_map:
            entry['canonical'] = alias_map[ent.lower()]
            entry['note'] = f'Use "{alias_map[ent.lower()]}" instead'
        entity_glossary.append(entry)

    # Build KPI glossary
    kpi_glossary = []
    for kpi in kpis:
        entry = {
            'term': kpi['id'] if isinstance(kpi, dict) else kpi,
            'type': 'kpi',
        }
        if isinstance(kpi, dict):
            entry['full_name'] = kpi.get('name', '')
            entry['definition'] = kpi.get('definition', '')
        kpi_glossary.append(entry)

    # Build the prompt injection block (compact, for BUILD + QA prompts)
    lock_block_lines = [
        f'## UBIQUITOUS LANGUAGE — {startup_name}',
        f'These are the CANONICAL terms for this project. Use these EXACTLY — do not invent synonyms.',
        '',
    ]

    if entity_glossary:
        lock_block_lines.append('### Entities')
        for e in entity_glossary:
            if 'canonical' in e:
                lock_block_lines.append(f'- ~~{e["term"]}~~ → use **{e["canonical"]}**')
            else:
                lock_block_lines.append(f'- **{e["term"]}**')

    if kpi_glossary:
        lock_block_lines.append('')
        lock_block_lines.append('### KPIs')
        for k in kpi_glossary:
            name = k.get('full_name', '')
            if name and name != k['term']:
                lock_block_lines.append(f'- **{k["term"]}** ({name})')
            else:
                lock_block_lines.append(f'- **{k["term"]}**')

    if roles:
        lock_block_lines.append('')
        lock_block_lines.append('### User Roles')
        for r in roles:
            lock_block_lines.append(f'- **{r}**')

    if integrations:
        lock_block_lines.append('')
        lock_block_lines.append('### Integrations')
        for i in integrations:
            lock_block_lines.append(f'- **{i}**')

    if resolved_synonyms:
        lock_block_lines.append('')
        lock_block_lines.append('### Terminology Rules')
        for syn in resolved_synonyms:
            avoid = ', '.join(syn['aliases_to_avoid'])
            lock_block_lines.append(
                f'- Use **{syn["canonical"]}** — do NOT use: {avoid}'
            )

    # Entity relationships (from AI)
    relationships = ai_result.get('entity_relationships', [])

    # Ambiguities (from AI)
    ambiguities = ai_result.get('ambiguities', [])
    if ambiguities:
        lock_block_lines.append('')
        lock_block_lines.append('### Disambiguation')
        for amb in ambiguities:
            lock_block_lines.append(
                f'- **{amb["term"]}**: {amb.get("recommendation", "")}'
            )

    glossary = {
        'startup_name': startup_name,
        'startup_id': startup_id,
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'entities': entity_glossary,
        'kpis': kpi_glossary,
        'roles': roles,
        'integrations': integrations,
        'synonym_resolutions': resolved_synonyms,
        'ambiguities': ambiguities,
        'entity_relationships': relationships,
        'alias_map': alias_map,
        'prompt_lock_block': '\n'.join(lock_block_lines),
    }

    return glossary


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description='Extract ubiquitous language glossary from intake JSON.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('--intake', required=True,
                        help='Path to intake JSON file')
    parser.add_argument('--output-dir', default=None,
                        help='Output directory (default: same as intake)')
    parser.add_argument('--no-ai', action='store_true',
                        help='Skip AI synonym resolution (deterministic only)')
    args = parser.parse_args()

    intake_path = Path(args.intake)
    if not intake_path.exists():
        print(f'ERROR: Intake file not found: {intake_path}')
        sys.exit(1)

    try:
        with open(intake_path, 'r', encoding='utf-8') as f:
            intake = json.load(f)
    except json.JSONDecodeError as e:
        print(f'ERROR: Invalid JSON in {intake_path}: {e}')
        sys.exit(1)

    output_dir = Path(args.output_dir) if args.output_dir else intake_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    api_key = os.environ.get('ANTHROPIC_API_KEY', '')
    use_ai = (not args.no_ai) and bool(api_key)
    stem = intake_path.stem
    startup_id = intake.get('startup_idea_id', stem)

    print(f'\nUbiquitous Language Extractor')
    print('=' * 60)
    print(f'Intake:  {intake_path}')
    print(f'Output:  {output_dir}')
    print(f'AI:      {"enabled (Claude Haiku)" if use_ai else "disabled (deterministic only)"}')
    print()

    glossary = build_glossary(intake, use_ai=use_ai, api_key=api_key,
                              startup_id=startup_id)

    # Save glossary JSON
    glossary_path = output_dir / f'{stem}_ubiquitous_language.json'
    with open(glossary_path, 'w', encoding='utf-8') as f:
        json.dump(glossary, f, indent=2)
    print(f'\nGlossary saved: {glossary_path}')

    # Print summary
    print(f'\n  Entities:      {len(glossary["entities"])}')
    print(f'  KPIs:          {len(glossary["kpis"])}')
    print(f'  Roles:         {len(glossary["roles"])}')
    print(f'  Integrations:  {len(glossary["integrations"])}')
    print(f'  Synonyms:      {len(glossary["synonym_resolutions"])}')
    print(f'  Ambiguities:   {len(glossary["ambiguities"])}')
    print(f'  Relationships: {len(glossary["entity_relationships"])}')

    # Print the lock block preview
    print(f'\n── Prompt Lock Block ──')
    print(glossary['prompt_lock_block'])
    print()


if __name__ == '__main__':
    main()
