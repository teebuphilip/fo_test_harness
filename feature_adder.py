#!/usr/bin/env python3
"""
feature_adder.py — Add a single new feature to an existing built project.

Takes the original intake JSON + a prior run ZIP and produces a tightly-scoped
intake for ONE feature only, with the full do-not-regenerate file list from the
prior ZIP pre-populated so Claude never touches existing files.

Usage:
  python feature_adder.py \\
    --intake intake/intake_runs/awi/awi.json \\
    --manifest fo_harness_runs/awi_p1_BLOCK_B_20260307_070205.zip \\
    --feature "KPI scoring engine"

  # After that run produces a ZIP, chain to next feature:
  python feature_adder.py \\
    --intake intake/intake_runs/awi/awi.json \\
    --manifest fo_harness_runs/awi_feature_kpi_scoring_engine_BLOCK_B_*.zip \\
    --feature "Narrative summary generator"

Output:
  <intake_dir>/<stem>_feature_<slug>.json
"""

import argparse
import copy
import json
import os
import re
import sys
import zipfile
from pathlib import Path
from typing import Optional

# ── Classification keywords (mirrors phase_planner.py) ───────────────────────

DATA_KEYWORDS = [
    'crud', 'profile', 'management', 'form', 'input', 'entry', 'auth',
    'authentication', 'login', 'register', 'user', 'client', 'entity',
    'record', 'create', 'read', 'update', 'delete', 'list', 'search',
    'filter', 'upload', 'storage', 'basic', 'simple', 'view',
]

INTEL_KEYWORDS = [
    'kpi', 'scoring', 'score', 'engine', 'dashboard', 'analytics',
    'report', 'reporting', 'executive', 'narrative', 'summary', 'generator',
    'insight', 'metric', 'trend', 'forecast', 'analysis', 'intelligence',
    'recommendation', 'calculation', 'compute', 'export', 'download',
    'pdf', 'chart', 'graph', 'visualization', 'benchmark',
]


def slugify(text: str) -> str:
    return re.sub(r'[^a-z0-9]+', '_', text.lower()).strip('_')[:40]


def classify_feature(feature: str) -> str:
    """Returns 'INTELLIGENCE_LAYER' or 'DATA_LAYER'."""
    fl = feature.lower()
    intel_hits = sum(1 for k in INTEL_KEYWORDS if k in fl)
    data_hits  = sum(1 for k in DATA_KEYWORDS  if k in fl)
    return 'INTELLIGENCE_LAYER' if intel_hits >= data_hits else 'DATA_LAYER'


def extract_existing_files(zip_path: str) -> list:
    """
    Reads the final iteration artifact_manifest.json from a harness run ZIP
    and returns all business/** file paths (no .pyc, no __pycache__).
    """
    existing = []
    try:
        with zipfile.ZipFile(zip_path) as z:
            names = z.namelist()
            # Find all iteration manifests, take the last one (highest iter number)
            iter_manifests = sorted([
                n for n in names
                if re.search(r'/build/iteration_\d+_artifacts/artifact_manifest\.json$', n)
            ])
            if not iter_manifests:
                # Fallback: root manifest
                root = [n for n in names if n.endswith('artifact_manifest.json')
                        and '/build/' not in n]
                if root:
                    iter_manifests = root

            if not iter_manifests:
                print(f"WARNING: No artifact_manifest.json found in {zip_path}")
                return []

            target = iter_manifests[-1]
            with z.open(target) as f:
                manifest = json.load(f)

            for entry in manifest.get('artifacts', []):
                path = entry.get('path', '')
                if (path.startswith('business/')
                        and not path.endswith('.pyc')
                        and '__pycache__' not in path):
                    existing.append(path)

    except Exception as e:
        print(f"ERROR reading manifest from ZIP: {e}")
        sys.exit(1)

    return sorted(existing)


def match_intake_feature(feature_str: str, intake_features: list) -> Optional[str]:
    """
    Try to match feature_str against the intake feature list.
    Returns the matched intake feature string, or None if no match.
    """
    fl = feature_str.lower()
    # Exact match first
    for f in intake_features:
        if f.lower() == fl:
            return f
    # Substring match
    for f in intake_features:
        if fl in f.lower() or f.lower() in fl:
            return f
    # Word overlap match (>=50% of words in common)
    query_words = set(fl.split())
    for f in intake_features:
        candidate_words = set(f.lower().split())
        overlap = len(query_words & candidate_words)
        if overlap >= max(1, len(query_words) // 2):
            return f
    return None


def get_intake_features(intake: dict) -> list:
    """Extract must_have_features from block_b hero_answers."""
    try:
        return intake['block_b']['hero_answers']['Q4_must_have_features']
    except (KeyError, TypeError):
        return []


def get_kpi_definitions(intake: dict) -> list:
    """Extract KPI definitions from block_b."""
    try:
        return intake['block_b'].get('kpi_definitions', [])
    except (KeyError, TypeError):
        return []


def get_normalization_rules(intake: dict) -> dict:
    """Extract normalization rules from block_b."""
    try:
        return intake['block_b'].get('normalization_rules', {})
    except (KeyError, TypeError):
        return {}


def build_feature_intake(
    intake: dict,
    feature: str,
    matched_intake_feature: Optional[str],
    existing_files: list,
    classification: str,
    all_intake_features: list,
) -> dict:
    """
    Build a scoped intake with only the target feature.
    """
    scoped = copy.deepcopy(intake)
    slug = slugify(feature)
    base_id = intake.get('startup_idea_id', 'unknown').rstrip('_')
    scoped['startup_idea_id'] = f'{base_id}_{slug}'

    # Scope must_have_features to just this one feature
    display_name = matched_intake_feature or feature
    try:
        scoped['block_b']['hero_answers']['Q4_must_have_features'] = [display_name]
    except (KeyError, TypeError):
        pass

    # Include KPIs only for intelligence-layer features
    kpis = get_kpi_definitions(intake)
    norms = get_normalization_rules(intake)
    if classification == 'INTELLIGENCE_LAYER' and kpis:
        scoped['block_b']['kpi_definitions'] = kpis
        scoped['block_b']['normalization_rules'] = norms
    else:
        scoped['block_b'].pop('kpi_definitions', None)
        scoped['block_b'].pop('normalization_rules', None)

    # Already-built features (everything except this one)
    already_built = [f for f in all_intake_features
                     if f.lower() != display_name.lower()]

    # _phase_context block
    scoped['_phase_context'] = {
        'feature_add_mode': True,
        'feature': display_name,
        'classification': classification,
        'already_built_features': already_built,
        'do_not_regenerate': existing_files,
        'note': (
            f'You are adding ONE new feature to an existing codebase: "{display_name}". '
            f'The files listed in do_not_regenerate are ALREADY BUILT AND QA-ACCEPTED — '
            f'do NOT output them. Output ONLY the new files required for "{display_name}". '
            f'You may import from existing files freely.'
        ),
    }

    return scoped


def main():
    parser = argparse.ArgumentParser(
        description='feature_adder.py — Scope a single-feature intake from an existing build.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Add KPI scoring engine on top of Phase 1 data layer:
  python feature_adder.py \\
    --intake intake/intake_runs/awi/awi.5.json \\
    --manifest fo_harness_runs/awi_p1_BLOCK_B_20260307_070205.zip \\
    --feature "KPI scoring engine"

  # Chain: add next feature on top of prior feature build:
  python feature_adder.py \\
    --intake intake/intake_runs/awi/awi.5.json \\
    --manifest fo_harness_runs/awi_kpi_scoring_engine_BLOCK_B_*.zip \\
    --feature "Narrative summary generator"
        """
    )
    parser.add_argument('--intake',   required=True, help='Original full intake JSON path')
    parser.add_argument('--manifest', required=True, help='Prior run ZIP (any phase or feature build)')
    parser.add_argument('--feature',  required=True, help='Feature name or description to add')
    parser.add_argument('--output-dir', default=None,
                        help='Output directory (default: same dir as intake)')
    parser.add_argument('--output', default=None,
                        help='Full output file path (overrides --output-dir + auto-name)')
    args = parser.parse_args()

    intake_path = Path(args.intake)
    if not intake_path.exists():
        print(f"ERROR: Intake not found: {intake_path}")
        sys.exit(1)

    # Resolve glob in manifest path (user may pass a *.zip pattern)
    manifest_path = args.manifest
    if '*' in manifest_path:
        import glob as _glob
        matches = sorted(_glob.glob(manifest_path))
        if not matches:
            print(f"ERROR: No ZIP found matching: {manifest_path}")
            sys.exit(1)
        manifest_path = matches[-1]  # most recent
        print(f"  Manifest: {manifest_path}")

    if not os.path.exists(manifest_path):
        print(f"ERROR: Manifest ZIP not found: {manifest_path}")
        sys.exit(1)

    # Load intake
    with open(intake_path) as f:
        intake = json.load(f)

    # Extract existing files from prior ZIP
    print(f"\nReading existing files from: {manifest_path}")
    existing_files = extract_existing_files(manifest_path)
    print(f"  {len(existing_files)} existing business/ file(s) found")

    # Get all intake features
    all_features = get_intake_features(intake)
    print(f"  {len(all_features)} feature(s) in intake: {', '.join(all_features)}")

    # Match feature against intake
    matched = match_intake_feature(args.feature, all_features)
    if matched:
        print(f"  Matched intake feature: '{matched}'")
    else:
        print(f"  No intake match — treating as new feature: '{args.feature}'")

    # Classify
    classification = classify_feature(args.feature)
    print(f"  Classification: {classification}")

    # Build scoped intake
    scoped = build_feature_intake(
        intake=intake,
        feature=args.feature,
        matched_intake_feature=matched,
        existing_files=existing_files,
        classification=classification,
        all_intake_features=all_features,
    )

    # Write output
    if args.output:
        out_path = Path(args.output)
    else:
        output_dir = Path(args.output_dir) if args.output_dir else intake_path.parent
        stem = intake_path.stem
        slug = slugify(args.feature)
        out_path = output_dir / f'{stem}_feature_{slug}.json'
    with open(out_path, 'w') as f:
        json.dump(scoped, f, indent=2)

    startup_id = scoped['startup_idea_id']
    manifest_zip = f"fo_harness_runs/{startup_id}_BLOCK_B_<timestamp>.zip"
    print(f"\nOutput: {out_path}")
    print(f"startup_idea_id: {startup_id}")
    print(f"\nRun harness:")
    print(f"  python fo_test_harness.py {out_path} --prior-run {Path(manifest_path).with_suffix('')} --max-iterations 30 --no-polish")
    print(f"\nAfter this run succeeds, chain the next feature:")
    print(f"  python feature_adder.py --intake {intake_path} --manifest {manifest_zip} --feature \"<next feature name>\"")


if __name__ == '__main__':
    main()
