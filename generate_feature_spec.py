#!/usr/bin/env python3
"""
generate_feature_spec.py — Define a new feature before building it.

Two modes:

  --questions-only
      Print the feature questionnaire to stdout and save a blank template
      file you can fill in. Pass this template to --answers-file when done.

  --answers-file <path>
      Read your filled-in answers (or AI-assisted answers) and use Claude
      to structure them into a precise feature spec that add_feature.sh
      will embed into the build prompt. Claude reads the original intake
      for product context so it can check for conflicts and fill gaps.

Usage:

  # Step 1 — get the questions
  python generate_feature_spec.py \\
    --feature "Competitor benchmarking dashboard" \\
    --questions-only

  # Step 1 output: feature_specs/competitor_benchmarking_dashboard_questions.txt
  # Fill that file in (or have AI help you), then:

  # Step 2 — structure your answers into a spec
  python generate_feature_spec.py \\
    --feature "Competitor benchmarking dashboard" \\
    --intake intake/intake_runs/awi/awi.5.json \\
    --answers-file feature_specs/competitor_benchmarking_dashboard_answers.txt

  # Step 2 output: feature_specs/competitor_benchmarking_dashboard_spec.txt
  # Pass that to add_feature.sh:

  # Step 3 — build
  ./add_feature.sh \\
    --intake intake/intake_runs/awi/awi.5.json \\
    --feature "Competitor benchmarking dashboard" \\
    --spec-file feature_specs/competitor_benchmarking_dashboard_spec.txt \\
    --existing-repo ~/Documents/work/ai_workforce_intelligence
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

SPECS_DIR = Path('feature_specs')

QUESTIONS = [
    (
        'Q1',
        'What does this feature do? (one clear sentence)',
        'Describe the core purpose — what problem it solves for the user.',
    ),
    (
        'Q2',
        'Who uses it and when? (user role + workflow moment)',
        'e.g. "A consultant opens it after completing a client assessment '
        'to prepare an executive presentation."',
    ),
    (
        'Q3',
        'What data does it need? (inputs and where they come from)',
        'List the data fields, models, or external sources it reads. '
        'e.g. "KPI scores from the assessments table, client profile from clients table."',
    ),
    (
        'Q4',
        'What does the UI show? (describe each screen, chart, table, or component)',
        'Be specific — chart type, columns in a table, what a card displays. '
        'e.g. "One bar chart per KPI showing client score vs p25/p50/p75 industry bands."',
    ),
    (
        'Q5',
        'What actions can the user take? (buttons, forms, filters, exports)',
        'e.g. "Filter by date range. Download as PDF. Click a KPI bar to see '
        'the underlying data breakdown."',
    ),
    (
        'Q6',
        'What existing features or data does this connect to?',
        'Which already-built pages, models, or services does this feature '
        'read from or write to? e.g. "Reads from the KPI scoring engine output. '
        'Links back to the executive dashboard."',
    ),
    (
        'Q7',
        'What does this feature explicitly NOT do? (scope boundaries)',
        'Name things that might seem related but are out of scope. '
        'e.g. "Does not allow editing benchmark data. Does not send emails. '
        'Does not integrate with third-party benchmark providers."',
    ),
    (
        'Q8',
        'How do we know it is done? (3-5 acceptance criteria)',
        'Concrete, testable statements. '
        'e.g. "1. Chart renders with real client KPI data. '
        '2. Industry benchmark bands are visible per KPI. '
        '3. PDF download produces a file with the chart and a data table."',
    ),
]


def slugify(text: str) -> str:
    return re.sub(r'[^a-z0-9]+', '_', text.lower()).strip('_')[:50]


def questions_template(feature: str) -> str:
    slug = slugify(feature)
    lines = [
        f'FEATURE SPEC — {feature}',
        '=' * 60,
        '',
        'Fill in each answer below. Be as specific as you can.',
        'Bullet points, sentences, or fragments are all fine.',
        'Save this file and pass it to generate_feature_spec.py --answers-file.',
        '',
    ]
    for q_id, question, hint in QUESTIONS:
        lines += [
            f'{q_id}. {question}',
            f'    ({hint})',
            'A:',
            '',
        ]
    return '\n'.join(lines)


def load_intake_summary(intake_path: str) -> str:
    """Extract a short product summary from the intake JSON for Claude context."""
    try:
        with open(intake_path) as f:
            intake = json.load(f)
        name = intake.get('startup_name', intake.get('startup_idea_id', 'this product'))
        summary = intake.get('summary', '')
        features = []
        try:
            features = intake['block_b']['hero_answers']['Q4_must_have_features']
        except (KeyError, TypeError):
            pass
        parts = [f'Product: {name}']
        if summary:
            parts.append(f'Summary: {summary}')
        if features:
            parts.append('Already-built features: ' + ', '.join(features))
        return '\n'.join(parts)
    except Exception:
        return ''


def structure_answers_with_claude(
    feature: str,
    answers_text: str,
    intake_summary: str,
) -> str:
    """Call Claude to turn raw answers into a structured feature spec."""
    try:
        from anthropic import Anthropic
    except ImportError:
        print('ERROR: anthropic package not installed. Run: pip install anthropic')
        sys.exit(1)

    api_key = os.getenv('ANTHROPIC_API_KEY')
    if not api_key:
        print('ERROR: ANTHROPIC_API_KEY not set.')
        sys.exit(1)

    client = Anthropic(api_key=api_key)

    product_context = (
        f'\n\nPRODUCT CONTEXT:\n{intake_summary}' if intake_summary else ''
    )

    prompt = f"""You are a software product manager writing a precise feature specification.

A founder wants to add a new feature called "{feature}" to their existing SaaS product.
They have answered 8 questions about what the feature should do.{product_context}

Your job:
1. Read their answers carefully.
2. Write a structured feature spec a software engineer can implement without guessing.
3. Fill obvious gaps using the product context — but do NOT invent functionality the founder did not mention.
4. Flag anything ambiguous at the end under OPEN QUESTIONS (if none, omit the section).

OUTPUT FORMAT (plain text, no JSON):

FEATURE: {feature}

SUMMARY
<One paragraph: what it does, who uses it, why it matters>

DATA REQUIREMENTS
<Bullet list: what data the feature reads/writes, which models/tables, where data comes from>

UI / UX
<Describe each screen, chart, table, or component. Be specific about layout, chart types, columns, labels.>

USER ACTIONS
<Bullet list: every button, form, filter, export, or navigation action>

INTEGRATIONS WITH EXISTING FEATURES
<Which already-built pages, models, or services this feature connects to>

SCOPE — WHAT THIS FEATURE DOES NOT DO
<Explicit exclusions — things that might seem related but are out of scope>

ACCEPTANCE CRITERIA
<Numbered list: 4-6 concrete, testable statements>

OPEN QUESTIONS (omit if none)
<Anything the founder's answers left ambiguous that needs a decision before building>

---

FOUNDER'S ANSWERS:
{answers_text}

Write the spec now. Plain text only — no markdown code fences, no JSON."""

    print('  Calling Claude to structure your answers...')
    response = client.messages.create(
        model='claude-sonnet-4-20250514',
        max_tokens=2048,
        temperature=0.2,
        messages=[{'role': 'user', 'content': prompt}],
    )
    return response.content[0].text.strip()


def validate_spec_with_claude(
    feature: str,
    spec_text: str,
    intake_summary: str,
) -> dict:
    """
    Call Claude to evaluate a spec for build-readiness.

    Returns dict with keys:
      verdict       — 'SUFFICIENT' or 'NEEDS_WORK'
      score         — int 0-100
      gaps          — list of {dimension, problem, question} dicts
      warnings      — list of strings (present but weak coverage)
      ready_to_build — bool
    """
    try:
        from anthropic import Anthropic
    except ImportError:
        print('ERROR: anthropic package not installed. Run: pip install anthropic')
        sys.exit(1)

    api_key = os.getenv('ANTHROPIC_API_KEY')
    if not api_key:
        print('ERROR: ANTHROPIC_API_KEY not set.')
        sys.exit(1)

    client = Anthropic(api_key=api_key)

    product_context = (
        f'\n\nPRODUCT CONTEXT:\n{intake_summary}' if intake_summary else ''
    )

    prompt = f"""You are a senior product manager reviewing a feature spec for build-readiness.

A software team is about to build the feature "{feature}" for an existing SaaS product.{product_context}

Your job: evaluate whether the spec below is detailed enough for a software engineer to implement correctly WITHOUT asking any follow-up questions.

A spec is SUFFICIENT if it answers all of these dimensions clearly:
  1. WHAT — what the feature does (not vague — a specific description)
  2. WHO — who uses it and in what workflow context
  3. DATA — what data it reads/writes, which models or tables, where data comes from
  4. UI — what each screen/component shows (chart type, table columns, labels — not just "a dashboard")
  5. ACTIONS — every user action (buttons, forms, filters, exports) and what each does
  6. INTEGRATIONS — which existing features/models/services it connects to
  7. SCOPE — explicit exclusions (what it does NOT do)
  8. ACCEPTANCE CRITERIA — at least 3 concrete, testable statements

A spec NEEDS WORK if any dimension is: missing entirely, too vague to implement, or contradicts the product context.

OUTPUT FORMAT (strict JSON — nothing else):
{{
  "verdict": "SUFFICIENT" | "NEEDS_WORK",
  "score": <int 0-100, where 100 = fully ready>,
  "gaps": [
    {{
      "dimension": "<one of: WHAT, WHO, DATA, UI, ACTIONS, INTEGRATIONS, SCOPE, ACCEPTANCE_CRITERIA>",
      "problem": "<what is missing or too vague>",
      "question": "<the specific question the engineer would have to guess at>"
    }}
  ],
  "warnings": [
    "<dimension covered but weakly — e.g. 'UI described but no chart type specified'>"
  ],
  "ready_to_build": <true if score >= 75 and no critical gaps in DATA, UI, or ACCEPTANCE_CRITERIA>
}}

If verdict is SUFFICIENT, gaps may be empty. Always include warnings for weak-but-present coverage.
Output ONLY the JSON. No explanation, no markdown fences.

SPEC TO EVALUATE:
{spec_text}"""

    print('  Calling Claude to validate spec...')
    response = client.messages.create(
        model='claude-sonnet-4-20250514',
        max_tokens=1024,
        temperature=0.1,
        messages=[{'role': 'user', 'content': prompt}],
    )

    raw = response.content[0].text.strip()
    # Strip markdown fences if present
    raw = re.sub(r'^```(?:json)?\n?', '', raw)
    raw = re.sub(r'\n?```$', '', raw)

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Fallback: return a structured error so the caller can still print something useful
        return {
            'verdict': 'UNKNOWN',
            'score': 0,
            'gaps': [],
            'warnings': [f'Could not parse Claude response: {raw[:200]}'],
            'ready_to_build': False,
        }


def print_validation_report(result: dict, feature: str, spec_file: str):
    verdict = result.get('verdict', 'UNKNOWN')
    score = result.get('score', 0)
    gaps = result.get('gaps', [])
    warnings = result.get('warnings', [])
    ready = result.get('ready_to_build', False)

    print()
    print('=' * 60)
    print(f'SPEC VALIDATION — {feature}')
    print('=' * 60)
    print(f'  Spec file : {spec_file}')
    print(f'  Score     : {score}/100')
    print(f'  Verdict   : {verdict}')
    print(f'  Build-ready: {"YES" if ready else "NO"}')

    if gaps:
        print()
        print(f'  GAPS ({len(gaps)} — must fix before building):')
        for g in gaps:
            print(f'    [{g["dimension"]}] {g["problem"]}')
            print(f'            → {g["question"]}')

    if warnings:
        print()
        print(f'  WARNINGS ({len(warnings)} — weak coverage, consider improving):')
        for w in warnings:
            print(f'    ⚠  {w}')

    print()
    if ready:
        print('  ✓ Spec is sufficient — proceed to build:')
        print(f'    ./add_feature.sh \\')
        print(f'      --intake <your_intake.json> \\')
        print(f'      --feature "{feature}" \\')
        print(f'      --spec-file {spec_file} \\')
        print(f'      --existing-repo <path_or_url>')
    else:
        print('  ✗ Spec needs work before building.')
        print('    Address the gaps above, then revalidate:')
        print(f'    python generate_feature_spec.py \\')
        print(f'      --feature "{feature}" \\')
        print(f'      --validate-spec {spec_file}')

    print()
    return ready


def main():
    parser = argparse.ArgumentParser(
        description='Generate a feature spec before building with add_feature.sh.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Get the questions
  python generate_feature_spec.py --feature "Competitor benchmarking" --questions-only

  # Structure your answers into a spec
  python generate_feature_spec.py \\
    --feature "Competitor benchmarking" \\
    --intake intake/intake_runs/awi/awi.5.json \\
    --answers-file feature_specs/competitor_benchmarking_answers.txt

  # Validate any spec (yours, AI-written, freeform) before building
  python generate_feature_spec.py \\
    --feature "Competitor benchmarking" \\
    --intake intake/intake_runs/awi/awi.5.json \\
    --validate-spec feature_specs/competitor_benchmarking_spec.txt
        """,
    )
    parser.add_argument('--feature', required=True,
                        help='Name of the feature to spec out or validate')
    parser.add_argument('--questions-only', action='store_true',
                        help='Print questions template and exit (no Claude call)')
    parser.add_argument('--answers-file',
                        help='Path to filled-in answers file → structured spec')
    parser.add_argument('--validate-spec',
                        help='Path to any existing spec file to validate for build-readiness')
    parser.add_argument('--intake', default=None,
                        help='Original intake JSON (provides product context to Claude)')
    parser.add_argument('--output-dir', default=None,
                        help='Where to write output files (default: feature_specs/)')
    args = parser.parse_args()

    if not args.questions_only and not args.answers_file and not args.validate_spec:
        parser.error('Provide --questions-only, --answers-file <path>, or --validate-spec <path>')

    slug = slugify(args.feature)
    out_dir = Path(args.output_dir) if args.output_dir else SPECS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    # ── Mode 1: questions only ────────────────────────────────────────────────
    if args.questions_only:
        template = questions_template(args.feature)
        questions_file = out_dir / f'{slug}_questions.txt'
        questions_file.write_text(template)

        print(template)
        print()
        print('=' * 60)
        print(f'Template saved to: {questions_file}')
        print()
        print('Next steps:')
        print(f'  1. Fill in your answers in: {questions_file}')
        print(f'     (rename it to {slug}_answers.txt when done)')
        print(f'  2. Run:')
        print(f'     python generate_feature_spec.py \\')
        print(f'       --feature "{args.feature}" \\')
        if args.intake:
            print(f'       --intake {args.intake} \\')
        print(f'       --answers-file {out_dir}/{slug}_answers.txt')
        return

    # ── Mode 2: structure answers into spec ───────────────────────────────────
    if args.answers_file:
        answers_path = Path(args.answers_file)
        if not answers_path.exists():
            print(f'ERROR: Answers file not found: {answers_path}')
            sys.exit(1)

        answers_text = answers_path.read_text(encoding='utf-8').strip()
        if not answers_text:
            print(f'ERROR: Answers file is empty: {answers_path}')
            sys.exit(1)

        intake_summary = ''
        if args.intake:
            if not Path(args.intake).exists():
                print(f'ERROR: Intake file not found: {args.intake}')
                sys.exit(1)
            print(f'  Loading product context from: {args.intake}')
            intake_summary = load_intake_summary(args.intake)

        print(f'  Feature       : {args.feature}')
        print(f'  Answers file  : {answers_path}')
        print()

        spec_text = structure_answers_with_claude(args.feature, answers_text, intake_summary)

        spec_file = out_dir / f'{slug}_spec.txt'
        spec_file.write_text(spec_text, encoding='utf-8')

        print()
        print('=' * 60)
        print(f'Feature spec written to: {spec_file}')
        print()
        print('Review it, then validate before building:')
        print(f'  python generate_feature_spec.py \\')
        print(f'    --feature "{args.feature}" \\')
        if args.intake:
            print(f'    --intake {args.intake} \\')
        print(f'    --validate-spec {spec_file}')
        return

    # ── Mode 3: validate an existing spec ─────────────────────────────────────
    if args.validate_spec:
        validate_path = Path(args.validate_spec)
        if not validate_path.exists():
            print(f'ERROR: Spec file not found: {validate_path}')
            sys.exit(1)

        spec_text = validate_path.read_text(encoding='utf-8').strip()
        if not spec_text:
            print(f'ERROR: Spec file is empty: {validate_path}')
            sys.exit(1)

        intake_summary = ''
        if args.intake:
            if not Path(args.intake).exists():
                print(f'ERROR: Intake file not found: {args.intake}')
                sys.exit(1)
            print(f'  Loading product context from: {args.intake}')
            intake_summary = load_intake_summary(args.intake)

        print(f'  Feature   : {args.feature}')
        print(f'  Spec file : {validate_path}')
        print()

        result = validate_spec_with_claude(args.feature, spec_text, intake_summary)
        ready = print_validation_report(result, args.feature, str(validate_path))
        sys.exit(0 if ready else 1)


if __name__ == '__main__':
    main()
