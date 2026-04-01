#!/usr/bin/env python3
"""
inject_spec.py — Embed a feature spec into an existing intake JSON.

Mirrors feature_adder.py's apply_spec_file() logic but works standalone.
Used by run_slicer_and_feature_build.sh to inject specs into slice intakes
before they enter fo_test_harness.py.

Usage:
  python inject_spec.py \
    --intake <path/to/slice_intake.json> \
    --spec-file <path/to/spec.txt> \
    --output <path/to/output.json>   # can be same as --intake to overwrite in place
"""

import argparse
import json
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(
        description='inject_spec.py — Embed spec text into intake _phase_context'
    )
    parser.add_argument('--intake',    required=True, help='Intake JSON to inject into')
    parser.add_argument('--spec-file', required=True, help='Spec text file from generate_feature_spec.py')
    parser.add_argument('--output',    required=True, help='Output path (can be same as --intake)')
    args = parser.parse_args()

    intake_path = Path(args.intake)
    spec_path   = Path(args.spec_file)
    output_path = Path(args.output)

    if not intake_path.exists():
        print(f"ERROR: intake not found: {intake_path}")
        sys.exit(1)
    if not spec_path.exists():
        print(f"ERROR: spec file not found: {spec_path}")
        sys.exit(1)

    with open(intake_path) as f:
        intake = json.load(f)

    spec_text = spec_path.read_text(encoding='utf-8').strip()

    # Ensure _phase_context exists
    if '_phase_context' not in intake:
        intake['_phase_context'] = {}

    # Inject spec — mirrors feature_adder.py apply_spec_file()
    intake['_phase_context']['feature_spec'] = spec_text
    existing_note = intake['_phase_context'].get('note', '')
    intake['_phase_context']['note'] = (
        existing_note
        + '\n\nFEATURE SPEC (implement this exactly — do not deviate):\n'
        + spec_text
    ).strip()

    with open(output_path, 'w') as f:
        json.dump(intake, f, indent=2)

    print(f"✓ Spec injected: {output_path}")
    print(f"  Spec length: {len(spec_text)} chars")


if __name__ == '__main__':
    main()
