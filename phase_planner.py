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
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

# ── Thresholds ────────────────────────────────────────────────────────────────

FEATURE_COUNT_THRESHOLD = 5  # features at or below this → candidate for 1-phase

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


def classify_with_ai(features: list, api_key: str) -> dict:
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

        resp = client.messages.create(
            model='claude-haiku-4-5-20251001',
            max_tokens=512,
            messages=[{'role': 'user', 'content': prompt}]
        )
        text = resp.content[0].text
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
           threshold: int = FEATURE_COUNT_THRESHOLD) -> dict:
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
            ai_result = classify_with_ai(ambiguous, api_key)
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


def build_phase1_intake(intake: dict, assessment: dict) -> dict:
    """
    Phase 1 intake: data layer only.
    - Intelligence-layer must-haves removed from all feature list fields
    - KPI definition fields emptied (deferred to Phase 2)
    - _phase_context block added for harness awareness
    """
    p1 = copy.deepcopy(intake)
    intel_set = {f.lower() for f in assessment['intelligence_features']}

    def walk(obj: Any) -> Any:
        if isinstance(obj, dict):
            result = {}
            for k, v in obj.items():
                kl = k.lower()
                if kl in KPI_KEYS and isinstance(v, list):
                    result[k] = []  # defer KPIs to Phase 2
                elif kl in FEATURE_KEYS:
                    result[k] = _prune_intel_features(v, intel_set)
                else:
                    result[k] = walk(v)
            return result
        if isinstance(obj, list):
            return [walk(item) for item in obj]
        return obj

    p1 = walk(p1)
    p1['_phase_context'] = {
        'phase': 1,
        'of_phases': 2,
        'scope': 'DATA_LAYER — CRUD, entities, basic views only',
        'deferred_to_phase2': assessment['intelligence_features'],
        'kpis_deferred': assessment['kpis'],
        'note': (
            'Build ONLY the data-collection layer. '
            'Do not implement KPI calculation, scoring, report generation, '
            'analytics charts, or any computed intelligence features. '
            'Those are Phase 2 scope.'
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

    p2['_phase_context'] = {
        'phase': 2,
        'of_phases': 2,
        'scope': 'INTELLIGENCE_LAYER — KPIs, scoring, reports, analytics',
        'phase1_completed_features': assessment['data_features'],
        'phase1_do_not_regenerate': p1_route_files + p1_model_files + p1_page_files,
        'kpis_to_implement': assessment['kpis'],
        'phase2_new_features': assessment['intelligence_features'],
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
    result = assess(intake, use_ai=use_ai, api_key=api_key, threshold=args.threshold)

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
    p1 = build_phase1_intake(intake, result)
    p2 = build_phase2_intake(intake, result)

    p1_path = output_dir / f'{stem}_phase1.json'
    p2_path = output_dir / f'{stem}_phase2.json'

    with open(p1_path, 'w', encoding='utf-8') as f:
        json.dump(p1, f, indent=2)
    with open(p2_path, 'w', encoding='utf-8') as f:
        json.dump(p2, f, indent=2)

    print(f'Phase 1 intake: {p1_path}')
    print(f'Phase 2 intake: {p2_path}')

    print_next_steps(p1_path, p2_path, stem)


if __name__ == '__main__':
    main()
