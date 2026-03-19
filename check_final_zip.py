#!/usr/bin/env python3
"""
check_final_zip.py — Quality check on a final multi-entity ZIP.

Usage:
    python check_final_zip.py \\
        --zip fo_harness_runs/wynwood_thoroughbreds_BLOCK_B_full_20260318_103929.zip \\
        --intake intake/intake_runs/wynwood_thoroughbreds/wynwood_thoroughbreds_phase_assessment.json

What it does:
    1. Extracts the full ZIP to a temp dir.
    2. For each entity subdir, finds the last iteration_NN_artifacts/ (in build/ or _harness/build/).
    3. Merges all entity business/** trees — later entities overwrite earlier on conflict.
    4. Runs:
         a. Static check  (fo_test_harness.py _run_static_check)
         b. Integration check (integration_check.py run_all_checks)
    5. Prints a combined report and exits 0 (all pass) or 1 (any failures).
"""

import argparse
import json
import os
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Optional

# ── Locate repo root ──────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).parent.resolve()
sys.path.insert(0, str(REPO_ROOT))

from integration_check import run_all_checks, build_output, print_summary
from fo_test_harness import FOHarness
from deploy.zip_layout import merge_business_artifacts, find_entity_dirs


# ── Helpers ───────────────────────────────────────────────────────────────────

def merge_artifacts_from_zip(zip_path: Path, extract_root: Path) -> dict:
    """
    Extract full ZIP and merge business/** from every entity's last iteration.
    Returns {relative_path: content} where relative_path starts with 'business/'.
    """
    print(f"  Extracting: {zip_path.name}")
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(extract_root)

    entity_dirs = find_entity_dirs(extract_root)
    if not entity_dirs:
        print("[ERROR] ZIP contains no top-level directories")
        sys.exit(1)
    merged, entity_report = merge_business_artifacts(extract_root)
    for name, iter_dir, n in entity_report:
        print(f"  [{iter_dir}] {name}  →  {n} file(s)")
    return merged, entity_report


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='check_final_zip.py — Quality check on a final multi-entity ZIP',
    )
    parser.add_argument(
        '--zip', type=Path, required=True,
        help='Path to the final full ZIP (e.g. fo_harness_runs/<startup>_BLOCK_B_full_<ts>.zip)',
    )
    parser.add_argument(
        '--intake', type=Path, required=True,
        help='Path to the phase-assessment intake JSON for this startup',
    )
    parser.add_argument(
        '--output', type=Path, default=None,
        help='Write integration issues JSON to this path (default: <zip_stem>_check.json)',
    )
    parser.add_argument(
        '--no-static', action='store_true',
        help='Skip static check (run integration check only)',
    )
    parser.add_argument(
        '--no-integration', action='store_true',
        help='Skip integration check (run static check only)',
    )
    args = parser.parse_args()

    if not args.zip.exists():
        print(f"[ERROR] ZIP not found: {args.zip}")
        sys.exit(1)
    if not args.intake.exists():
        print(f"[ERROR] Intake not found: {args.intake}")
        sys.exit(1)

    output_path = args.output or args.zip.with_name(args.zip.stem + '_check.json')

    with open(args.intake) as f:
        intake = json.load(f)

    # ── Extract + merge ───────────────────────────────────────────────────────
    extract_root = Path(tempfile.mkdtemp(prefix='cfz_'))
    try:
        print()
        print('═' * 62)
        print('  CHECK FINAL ZIP')
        print(f'  {args.zip.name}')
        print('═' * 62)
        print()
        print('Merging entity artifacts...')
        artifacts, entity_report = merge_artifacts_from_zip(args.zip, extract_root)
        print(f'\n  Total merged files: {len(artifacts)}')

        # Write merged tree to disk so static check can use it (needs a real dir)
        merged_dir = extract_root / '_merged'
        for rel, content in artifacts.items():
            dest = merged_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content, encoding='utf-8')

        # ── Static check ─────────────────────────────────────────────────────
        static_pass = True
        static_defects = []
        if not args.no_static:
            print()
            print('─' * 62)
            print('GATE 1 — STATIC CHECK')
            print('─' * 62)
            # _run_static_check expects the parent of business/ (i.e. merged_dir)
            static_defects = FOHarness._run_static_check(merged_dir, intake_data=intake)
            if not static_defects:
                print('  RESULT: PASS')
            else:
                static_pass = False
                high = sum(1 for d in static_defects if d['severity'] == 'HIGH')
                med  = sum(1 for d in static_defects if d['severity'] == 'MEDIUM')
                print(f'  RESULT: FAIL — {len(static_defects)} defect(s)  [HIGH: {high}  MEDIUM: {med}]')
                print()
                for d in static_defects:
                    sev = d.get('severity', '?')
                    chk = d.get('check', '')
                    loc = d.get('location', d.get('file', ''))
                    msg = d.get('message', d.get('issue', ''))
                    print(f'  [{sev}] {chk}  {loc}')
                    print(f'         {msg}')

        # ── Integration check ─────────────────────────────────────────────────
        integration_pass = True
        output_json = None
        if not args.no_integration:
            print()
            print('─' * 62)
            print('GATE 2 — INTEGRATION CHECK')
            print('─' * 62)
            issues = run_all_checks(artifacts, intake)
            output_json = build_output(
                issues,
                zip_path=args.zip,
                artifacts_dir=None,
                intake_path=args.intake,
            )
            with open(output_path, 'w') as f:
                json.dump(output_json, f, indent=2)
            print(f'  Output written: {output_path}')
            print()
            print_summary(output_json)
            integration_pass = (output_json['verdict'] == 'INTEGRATION_PASS')

        # ── Combined summary ──────────────────────────────────────────────────
        print()
        print('═' * 62)
        print('  COMBINED RESULT')
        print('═' * 62)
        print()
        print(f'  Entities merged: {len(entity_report)}')
        for name, iter_dir, n in entity_report:
            print(f'    {name}  ({iter_dir}, {n} files)')
        print()
        if not args.no_static:
            status = 'PASS' if static_pass else 'FAIL'
            print(f'  Static check     : {status}  ({len(static_defects)} defect(s))')
        if not args.no_integration and output_json:
            hi  = output_json['high_severity']
            med = output_json['medium_severity']
            total = output_json['total_issues']
            verdict = output_json['verdict']
            print(f'  Integration check: {verdict}  (HIGH:{hi}  MED:{med}  Total:{total})')
        print()

        all_pass = static_pass and integration_pass
        if all_pass:
            print('  ✓ ALL CHECKS PASSED')
        else:
            print('  ✗ CHECKS FAILED — review issues above')
        print()

        sys.exit(0 if all_pass else 1)

    finally:
        shutil.rmtree(extract_root, ignore_errors=True)


if __name__ == '__main__':
    main()
