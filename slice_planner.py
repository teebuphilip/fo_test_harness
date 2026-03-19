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
    plural = slug + 's' if not slug.endswith('s') else slug
    page_name = _title_from_slug(slug)
    api = slice_obj.get('api', {})
    route = api.get('route', f"/api/{slug}")
    method = api.get('method', 'POST').upper()
    public_route = route.replace('/api', '')

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
            "allowed_files": [
                f"models/{slug}.py",
                f"schemas/{slug}.py",
                f"services/{slug}_service.py",
                f"routes/{plural}.py",
                f"pages/{page_name}.jsx",
            ]
        },
        "forbidden_expansions": [
            "Do not create any file outside the allowed_files list.",
        ],
        "open_questions": [],
    }
    return mini_spec


def build_slice_intakes(intake: dict, plan: dict, output_dir: Path, stem: str) -> list:
    intakes = []
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
Each slice is a thin end-to-end tracer bullet that spans:
- schema/model
- service method
- route
- frontend UI

OUTPUT CONTRACT — return ONLY valid JSON with this structure:
{
  "planner": "slice_planner",
  "feature_count": <int>,
  "slices": [
    {
      "id": "S01",
      "title": "<short feature name>",
      "feature": "<feature description>",
      "api": {"method": "GET|POST|PUT|DELETE", "route": "/api/slug"},
      "data_changes": ["new model: foo_model", "new field: bar"],
      "ui": {"page": "foo_page", "actions": ["create", "view"]},
      "acceptance_criteria": ["..."],
      "mode": "HITL|AFK",
      "mode_reason": "one sentence reason",
      "dependencies": [],
      "notes": ""
    }
  ]
}

Rules:
- Keep slices minimal and testable.
- Use HITL only when human taste/approval or external setup is required.
- Routes must use underscores, no hyphens.
- Do NOT add extra sections. Return ONLY the JSON object.

INTAKE:
"""


def build_slice_plan_ai(intake: dict, api_key: str, model: str, startup_id: str = '') -> tuple:
    try:
        import openai
        client = openai.OpenAI(api_key=api_key)

        intake_json = json.dumps(intake, indent=2, default=str)
        prompt = AI_SLICE_PROMPT + intake_json

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
    parser.add_argument("--openai-model", default="gpt-4o", help="OpenAI model for slice planning")
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
