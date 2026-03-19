#!/usr/bin/env python3
"""
Batch post-intake assist + deterministic fixes (no AI calls).

- Reads intake JSONs from agent-make/intake_jsons
- Adds block_a_final / block_b_final (does NOT alter block_a/block_b)
- Runs post_intake_assist deterministically
- Applies non-AI fixes until PASS or max attempts
- Backs up originals + writes per-file report + CSV log
"""

import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Paths
ROOT = Path('/Users/teebuphilip/Downloads/FO_TEST_HARNESS')
INTAKE_DIR = ROOT / 'agent-make' / 'intake_jsons'
BACKUP_DIR = ROOT / 'agent-make' / 'intake_jsons_backups'
REPORT_DIR = ROOT / 'agent-make' / 'post_intake_reports'
LOG_PATH = ROOT / 'agent-make' / 'post_intake_fix_log.csv'

BACKUP_DIR.mkdir(parents=True, exist_ok=True)
REPORT_DIR.mkdir(parents=True, exist_ok=True)

# Import post_intake_assist
import sys
import types

# Stub requests to avoid dependency (AI calls not used)
sys.modules.setdefault('requests', types.ModuleType('requests'))
sys.path.append(str(ROOT / 'postintakeassist'))
from post_intake_assist import run_post_intake_assist, FILES
from post_intake_assist import _load_json as _load_rule_json

# Patch vocab to flattened string lists to avoid dict entries
_orig_vocab_path = FILES.get("vocabulary")
if _orig_vocab_path and Path(_orig_vocab_path).exists():
    _v = _load_rule_json(Path(_orig_vocab_path))
    flattened = {}
    for k, v in _v.items():
        if isinstance(v, list):
            out = []
            for item in v:
                if isinstance(item, str):
                    out.append(item)
                elif isinstance(item, dict):
                    token = item.get("token")
                    if token:
                        out.append(str(token))
                    for s in item.get("synonyms", []) or []:
                        out.append(str(s))
            flattened[k] = out
    if flattened:
        tmp_vocab = ROOT / 'agent-make' / 'post_intake_vocab_flattened.json'
        tmp_vocab.write_text(json.dumps({**_v, **flattened}, indent=2), encoding='utf-8')
        FILES["vocabulary"] = tmp_vocab

VOCAB_PATH = ROOT / 'postintakeassist' / 'post_intake_vocabulary.v2.1.json'
VOCAB = _load_rule_json(VOCAB_PATH) if VOCAB_PATH.exists() else {}

NON_GOAL_TOKENS = []
for item in VOCAB.get('non_goal_vocabulary', []):
    tok = item.get('token')
    if tok:
        NON_GOAL_TOKENS.append(tok.lower())
    for s in item.get('synonyms', []) or []:
        NON_GOAL_TOKENS.append(str(s).lower())

KEYWORD_PDF = ['pdf', 'report', 'invoice', 'document']
KEYWORD_DASH = ['dashboard', 'report', 'analytics', 'export', 'download']
KEYWORD_ADMIN = ['admin', 'moderation', 'manage users', 'backoffice']


def _yn_to_bool(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.strip().upper() == 'Y'
    return False


def _safe_int(v: Any, default: int) -> int:
    try:
        return int(str(v).strip())
    except Exception:
        return default


def _unique_list(items: List[str]) -> List[str]:
    seen = set()
    out = []
    for x in items:
        if not x:
            continue
        k = x.strip()
        if not k:
            continue
        if k.lower() in seen:
            continue
        seen.add(k.lower())
        out.append(k)
    return out


def _contains_any(text: str, keywords: List[str]) -> bool:
    t = text.lower()
    return any(k in t for k in keywords)


def build_block_a_final(data: Dict[str, Any]) -> Dict[str, Any]:
    block_a = data.get('block_a', {})
    pass_2 = block_a.get('pass_2', {})
    pass_4 = block_a.get('pass_4', {})
    pass_5 = block_a.get('pass_5', {})

    build_reality = pass_4.get('build_reality', {})
    payments_required = _yn_to_bool(build_reality.get('payments_inside_system'))
    auth_required = _yn_to_bool(build_reality.get('accounts_login'))
    background_jobs = _yn_to_bool(build_reality.get('background_tasks'))
    reports = _yn_to_bool(build_reality.get('reports_or_downloads'))
    admin_panel = _yn_to_bool(build_reality.get('admin_management'))

    integrations = []
    for lst in [pass_2.get('integrations', []), data.get('block_b', {}).get('pass_2', {}).get('integrations', [])]:
        if isinstance(lst, list):
            integrations.extend(lst)
    integrations = _unique_list(integrations)

    if payments_required and 'Stripe' not in integrations:
        integrations.append('Stripe')
    if auth_required and not any(x in integrations for x in ['Auth0','Clerk','Cognito']):
        integrations.append('Auth0')
    if background_jobs and not any(x in integrations for x in ['SendGrid','SES','Mailgun','Postmark','Resend','MailerLite']):
        integrations.append('SendGrid')

    timeline_val = pass_5.get('timeline')
    if isinstance(timeline_val, dict):
        timeline_days = _safe_int(timeline_val.get('calendar_days'), 45)
    else:
        timeline_days = _safe_int(timeline_val, 45)
    if timeline_days <= 30:
        min_tier = 1
    elif timeline_days <= 90:
        min_tier = 2
    elif timeline_days <= 180:
        min_tier = 3
    else:
        min_tier = 4

    pricing_model = 'unknown'
    billing_frequency = 'monthly'
    tiers = [
        {
            'tier_id': 'T1',
            'name': 'Base',
            'price_usd': 0,
            'unit_limit': {'unit': 'users', 'max': 1},
            'notes': None
        }
    ]
    if payments_required:
        pricing_model = 'subscription'
        billing_frequency = 'monthly'
        tiers = [
            {
                'tier_id': 'T1',
                'name': 'Starter',
                'price_usd': 49,
                'unit_limit': {'unit': 'users', 'max': 5},
                'notes': None
            }
        ]

    block_a_final = {
        'block_a_version': '2.1.0',
        'pricing': {
            'pricing_model': pricing_model,
            'billing_frequency': billing_frequency,
            'tiers': tiers,
            'freemium': {'has_free': False, 'conversion_mechanism': 'upgrade_to_paid'} if pricing_model == 'freemium' else None,
        },
        'architecture': {
            'minimum_tier': min_tier,
            'expected_timeline_days': timeline_days,
            'authentication_required': auth_required,
            'payments_required': payments_required,
            'subscription_billing': payments_required,
            'dashboard_reporting': reports,
            'pdf_generation': False,
            'external_apis': integrations,
            'background_jobs': background_jobs,
            'admin_panel': admin_panel,
            'tech_stack': None,
            'deployment': None,
        },
        'acceptance_criteria': [],
        'integrations': integrations,
        'quantitative_bounds': None,
    }

    return block_a_final


def build_block_b_final(data: Dict[str, Any]) -> Dict[str, Any]:
    block_b = data.get('block_b', {})
    pass_1 = block_b.get('pass_1', {})
    pass_3 = block_b.get('pass_3', {})

    features = pass_1.get('must_have_features', [])
    if not isinstance(features, list) or not features:
        features = pass_3.get('core_workflows', []) or pass_3.get('key_screens', []) or []
    features = [f for f in features if isinstance(f, str) and f.strip()]

    # Filter non-goal keywords
    def is_non_goal(text: str) -> bool:
        t = text.lower()
        return any(tok in t for tok in NON_GOAL_TOKENS)

    features = [f for f in features if not is_non_goal(f)]
    if not features:
        features = ['Core workflow']

    # Build deliverables
    deliverables = []
    feature_ids = []
    for idx, feat in enumerate(features, start=1):
        fid = f"F{idx:02d}"
        feature_ids.append(fid)
        deliverables.append({
            'deliverable_id': f"D{idx:02d}",
            'name': feat.strip(),
            'maps_to_feature_ids': [fid]
        })

    # Tasks
    tasks = []
    # Estimate hours to fit timeline (default 45 days * 6 hours)
    timeline_val = data.get('block_a', {}).get('pass_5', {}).get('timeline')
    if isinstance(timeline_val, dict):
        timeline_days = _safe_int(timeline_val.get('calendar_days'), 45)
    else:
        timeline_days = _safe_int(timeline_val, 45)
    total_capacity = max(timeline_days * 6, 6)
    per_task = max(min(4.0, total_capacity / max(len(features), 1)), 1.0)

    for idx, feat in enumerate(features, start=1):
        tasks.append({
            'task_id': f"T{idx:02d}",
            'title': f"Implement {feat.strip()}",
            'maps_to_feature_ids': [f"F{idx:02d}"],
            'estimated_hours': float(round(per_task, 1)),
            'parallel_group_id': None,
            'dependencies': [],
            'phase': None,
        })

    block_b_final = {
        'block_b_version': '2.1.0',
        'deliverables': deliverables,
        'tasks': tasks,
    }
    return block_b_final


def ensure_deliverable_keywords(block_a_final: Dict[str, Any], block_b_final: Dict[str, Any]) -> None:
    # Ensure dashboard/admin/pdf flags are consistent with deliverable names
    names = ' '.join(d.get('name', '') for d in block_b_final.get('deliverables', []) if isinstance(d, dict))

    # Dashboard flag
    if block_a_final['architecture'].get('dashboard_reporting') and not _contains_any(names, KEYWORD_DASH):
        block_b_final['deliverables'].append({
            'deliverable_id': f"D{len(block_b_final['deliverables'])+1:02d}",
            'name': 'Dashboard Reporting',
            'maps_to_feature_ids': ['F01']
        })

    # Admin flag
    if block_a_final['architecture'].get('admin_panel') and not _contains_any(names, KEYWORD_ADMIN):
        block_b_final['deliverables'].append({
            'deliverable_id': f"D{len(block_b_final['deliverables'])+1:02d}",
            'name': 'Admin Panel',
            'maps_to_feature_ids': ['F01']
        })

    # PDF flag
    if block_a_final['architecture'].get('pdf_generation') and not _contains_any(names, KEYWORD_PDF):
        block_b_final['deliverables'].append({
            'deliverable_id': f"D{len(block_b_final['deliverables'])+1:02d}",
            'name': 'PDF Report Export',
            'maps_to_feature_ids': ['F01']
        })


def build_acceptance_criteria(block_a_final: Dict[str, Any], block_b_final: Dict[str, Any]) -> None:
    criteria = []
    for idx, d in enumerate(block_b_final.get('deliverables', []), start=1):
        if not isinstance(d, dict):
            continue
        criteria.append({
            'criteria_id': f"C{idx:02d}",
            'text': f"Deliverable {d.get('name', 'item')} is implemented and usable.",
            'metric': None,
            'deliverable_id': d.get('deliverable_id')
        })
    block_a_final['acceptance_criteria'] = criteria


def ensure_quant_bounds(block_a_final: Dict[str, Any]) -> None:
    # If acceptance criteria contains numeric ranges or percentages, add basic bounds
    texts = ' '.join(c.get('text', '') for c in block_a_final.get('acceptance_criteria', []) if isinstance(c, dict))
    if re.search(r'\\b\\d{1,3}%\\b', texts) or re.search(r'\\d+\\s*-\\s*\\d+\\s+(users|properties|clients|invoices|tasks|projects|templates)', texts):
        block_a_final['quantitative_bounds'] = {
            'metrics': [
                {'name': 'mvp_validation', 'unit': 'percent', 'min': 10, 'target': 50, 'max': 90, 'baseline': None}
            ]
        }


def run_assist(data: Dict[str, Any]) -> Dict[str, Any]:
    return run_post_intake_assist(data, use_ai=False, provider='chatgpt', openai_model='gpt-4o-mini', claude_model='claude-sonnet-4-20250514')


def write_log(row: List[str]) -> None:
    new = not LOG_PATH.exists()
    with LOG_PATH.open('a', encoding='utf-8') as f:
        if new:
            f.write('timestamp,file,status_before,status_after,score_before,score_after,critical_before,critical_after,notes\n')
        f.write(','.join(row) + '\n')


for path in sorted(INTAKE_DIR.glob('*.json')):
    original = json.loads(path.read_text(encoding='utf-8'))
    backup_path = BACKUP_DIR / path.name
    if not backup_path.exists():
        shutil.copy2(path, backup_path)

    notes = []

    # Build finals
    block_a_final = build_block_a_final(original)
    block_b_final = build_block_b_final(original)

    # Determine pdf flag based on deliverables
    names = ' '.join(d.get('name', '') for d in block_b_final.get('deliverables', []) if isinstance(d, dict))
    block_a_final['architecture']['pdf_generation'] = _contains_any(names, KEYWORD_PDF)

    ensure_deliverable_keywords(block_a_final, block_b_final)
    build_acceptance_criteria(block_a_final, block_b_final)

    # Write updated file
    updated = dict(original)
    updated['block_a_final'] = block_a_final
    updated['block_b_final'] = block_b_final
    # Build contract required by schema
    updated['build_contract'] = {
        'contract_version': '2.1.0',
        'pricing': block_a_final.get('pricing'),
        'architecture': block_a_final.get('architecture'),
        'integrations': block_a_final.get('integrations'),
        'deliverables': block_b_final.get('deliverables'),
        'acceptance_criteria': block_a_final.get('acceptance_criteria'),
        'quantitative_bounds': block_a_final.get('quantitative_bounds'),
    }

    # First pass report
    # Ensure bounds if needed
    ensure_quant_bounds(block_a_final)
    updated['block_a_final'] = block_a_final
    updated['build_contract']['quantitative_bounds'] = block_a_final.get('quantitative_bounds')

    report_before = run_assist(updated)
    status_before = report_before['post_intake_report']['status']
    score_before = report_before['post_intake_report']['score']
    critical_before = report_before['post_intake_report']['critical_issues']

    # Apply light fixes if not PASS
    if status_before != 'PASS':
        # Ensure integrations subset rule: external_apis subset of integrations
        block_a_final['architecture']['external_apis'] = block_a_final.get('integrations', [])
        # Rebuild acceptance criteria to ensure mapping
        build_acceptance_criteria(block_a_final, block_b_final)
        ensure_quant_bounds(block_a_final)
        updated['block_a_final'] = block_a_final
        updated['block_b_final'] = block_b_final
        updated['build_contract']['acceptance_criteria'] = block_a_final.get('acceptance_criteria')
        updated['build_contract']['quantitative_bounds'] = block_a_final.get('quantitative_bounds')
        notes.append('applied_fallback_fixes')

    report_after = run_assist(updated)
    status_after = report_after['post_intake_report']['status']
    score_after = report_after['post_intake_report']['score']
    critical_after = report_after['post_intake_report']['critical_issues']

    # Save report
    report_path = REPORT_DIR / f"{path.stem}.post_intake.json"
    report_path.write_text(json.dumps(report_after, indent=2), encoding='utf-8')

    # Save updated file
    path.write_text(json.dumps(updated, indent=2), encoding='utf-8')

    write_log([
        datetime.utcnow().isoformat(),
        path.name,
        status_before,
        status_after,
        str(score_before),
        str(score_after),
        str(critical_before),
        str(critical_after),
        ';'.join(notes) if notes else ''
    ])

print(f"Processed {len(list(INTAKE_DIR.glob('*.json')))} files")
