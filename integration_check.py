#!/usr/bin/env python3
"""
integration_check.py — Post-build integration validator

Takes a harness ZIP (or artifacts dir) + original intake JSON.
Runs deterministic cross-file checks — NO AI calls, NO Claude, NO ChatGPT.

Checks:
  1. Route inventory  — frontend fetch()/api calls vs backend @router decorators
  2. Model field refs — service model.field accesses vs model Column definitions
  3. Spec compliance  — intake keywords (PDF, email, KPI names) vs artifacts
  4. Import chains    — from business.X import Y vs actual files in artifact set

Output:
  integration_issues.json  (harness-compatible defect format)

Usage:
  python integration_check.py \\
    --zip fo_harness_runs/foo_BLOCK_B_<ts>.zip \\
    --intake intake/intake_runs/foo/foo.json

  python integration_check.py \\
    --artifacts fo_harness_runs/foo_BLOCK_B_<ts>/build/iteration_19_artifacts \\
    --intake intake/intake_runs/foo/foo.json \\
    --output my_integration_issues.json

Then feed back into the harness:
  python fo_test_harness.py <intake> \\
    --resume-run <run_dir> \\
    --resume-iteration 19 \\
    --integration-issues integration_issues.json
"""

import argparse
import ast
import json
import re
import sys
import zipfile
from pathlib import Path


# ── Artifact loading ──────────────────────────────────────────────────────────

def load_artifacts_from_zip(zip_path: Path) -> dict:
    """
    Extract the highest-numbered iteration_XX_artifacts/business/** text files
    from a harness ZIP. Returns {relative_path: content}.
    """
    artifacts = {}
    with zipfile.ZipFile(zip_path) as z:
        names = z.namelist()

        # Find all iteration artifact dirs (under _harness/build/ or build/), pick the highest
        iter_dirs = sorted({
            m.group(1)
            for n in names
            for m in [re.search(r'((?:_harness/)?build/iteration_(\d+)_artifacts)/business/', n)]
            if m
        }, key=lambda d: int(re.search(r'(\d+)', d).group(1)))

        if not iter_dirs:
            print("[ERROR] No iteration_XX_artifacts/business/ found in ZIP")
            sys.exit(1)

        best_dir = iter_dirs[-1]
        print(f"  Using: {best_dir}")

        # Find the ZIP prefix (top-level run dir)
        prefix = re.match(r'(.+?/)', names[0]).group(1) if names else ''

        for name in names:
            # Match: prefix/<best_dir>/business/**
            rel = name[len(prefix):] if name.startswith(prefix) else name
            if not rel.startswith(f'{best_dir}/business/'):
                continue
            business_rel = rel[len(f'{best_dir}/'):]  # business/...
            if (business_rel.endswith('.pyc')
                    or '__pycache__' in business_rel
                    or business_rel.endswith('/')):
                continue
            try:
                content = z.read(name).decode('utf-8', errors='replace')
                artifacts[business_rel] = content
            except Exception:
                pass

    return artifacts


def load_artifacts_from_dir(artifacts_dir: Path) -> dict:
    """Load all business/** files from an iteration_XX_artifacts/ directory."""
    artifacts = {}
    biz_dir = artifacts_dir / 'business'
    if not biz_dir.exists():
        print(f"[ERROR] No business/ dir found at: {biz_dir}")
        sys.exit(1)
    for f in biz_dir.rglob('*'):
        if not f.is_file():
            continue
        if f.suffix == '.pyc' or '__pycache__' in str(f):
            continue
        rel = str(f.relative_to(artifacts_dir))
        try:
            artifacts[rel] = f.read_text(errors='replace')
        except Exception:
            pass
    return artifacts


# ── Parsing helpers ───────────────────────────────────────────────────────────

def parse_model_columns(content: str) -> set:
    """
    Parse a SQLAlchemy model file and return set of Column field names.
    Looks for:  field_name = Column(...)
    """
    columns = set()
    for m in re.finditer(r'^\s{4}(\w+)\s*=\s*Column\(', content, re.MULTILINE):
        columns.add(m.group(1))
    # Also pick up relationship names
    for m in re.finditer(r'^\s{4}(\w+)\s*=\s*relationship\(', content, re.MULTILINE):
        columns.add(m.group(1))
    return columns


def parse_route_endpoints(content: str) -> set:
    """
    Parse a FastAPI route file and return set of URL paths from @router decorators.
    e.g.  @router.get("/reports/{report_id}/download") → /reports/{report_id}/download
    """
    endpoints = set()
    for m in re.finditer(r'@router\.\w+\(["\']([^"\']+)["\']', content):
        endpoints.add(m.group(1))
    return endpoints


def parse_jsx_api_calls(content: str) -> set:
    """
    Parse a JSX file and return set of API path stems called via fetch() or api.*.
    Returns paths relative to /api/ prefix.
    e.g. fetch('/api/assessments') → 'assessments'
         api.get('/reports')      → 'reports'
    """
    paths = set()
    # fetch('/api/X') and fetch(`/api/X`)
    for m in re.finditer(r"""fetch\([`'"]/api/([^`'"?\s]+)""", content):
        paths.add(m.group(1).split('/')[0])  # top-level segment
    # api.get/post/put/delete('/X') or api.get('/api/X')
    for m in re.finditer(r"""api\.\w+\([`'"]/(?:api/)?([^`'"?\s]+)""", content):
        paths.add(m.group(1).split('/')[0])
    return paths


def parse_python_imports(content: str) -> list:
    """
    Parse Python imports of the form: from business.X.Y import Z
    Returns list of (module_path, symbol) tuples.
    """
    imports = []
    for m in re.finditer(r'from\s+(business\.[.\w]+)\s+import\s+(\w+)', content):
        imports.append((m.group(1), m.group(2)))
    return imports


def module_to_file_path(module: str) -> str:
    """Convert 'business.models.Report' → 'business/models/Report.py'"""
    return module.replace('.', '/') + '.py'


# ── Check 1: Route inventory ──────────────────────────────────────────────────

def check_route_inventory(artifacts: dict) -> list:
    """
    Find API paths called from frontend .jsx files.
    Check that a backend route file exists that handles each path.
    """
    issues = []

    # Collect all route file names (stem → endpoints defined)
    route_stems = {}  # 'assessments' → {'/assessments', '/assessments/{id}', ...}
    for path, content in artifacts.items():
        if re.match(r'business/backend/routes/\w+\.py$', path):
            stem = Path(path).stem  # 'assessments'
            route_stems[stem] = parse_route_endpoints(content)

    # Collect all frontend API calls
    frontend_calls = {}  # jsx_path → {stem1, stem2, ...}
    for path, content in artifacts.items():
        if path.endswith('.jsx') and 'pages/' in path:
            calls = parse_jsx_api_calls(content)
            if calls:
                frontend_calls[path] = calls

    # Cross-check
    all_route_stems = set(route_stems.keys())
    for jsx_path, called_stems in frontend_calls.items():
        for stem in called_stems:
            if stem not in all_route_stems:
                route_file = f'business/backend/routes/{stem}.py'
                issues.append({
                    'id': f'INT-ROUTE-{stem}',
                    'severity': 'HIGH',
                    'category': 'MISSING_ROUTE',
                    'file': route_file,
                    'files': [jsx_path, 'business/backend/routes/'],
                    'evidence': (
                        f"fetch('/api/{stem}') called in {Path(jsx_path).name} "
                        f"but no {stem}.py route file found in business/backend/routes/"
                    ),
                    'issue': (
                        f"Frontend calls /api/{stem} but no matching backend route file exists. "
                        f"Will 404 in production."
                    ),
                    'fix': (
                        f"Create business/backend/routes/{stem}.py with FastAPI APIRouter. "
                        f"Include authenticated GET /{stem} and POST /{stem} endpoints. "
                        f"Use: from core.rbac import get_current_user; from core.database import get_db"
                    ),
                })

    return issues


# ── Check 2: Model field refs ─────────────────────────────────────────────────

def check_model_field_refs(artifacts: dict) -> list:
    """
    Build a map of model_name → set of columns.
    Scan services/*.py for model_instance.field accesses.
    Flag if field doesn't exist on the model.
    """
    issues = []

    # Build model column map: {'Client': {'id','name','industry',...}, ...}
    model_columns = {}
    for path, content in artifacts.items():
        if re.match(r'business/models/\w+\.py$', path):
            model_name = Path(path).stem  # 'Client'
            model_columns[model_name] = parse_model_columns(content)

    if not model_columns:
        return issues

    # For each service, scan for model_instance.field_name patterns
    # Strategy: find variable assignments like `client = db.query(Client).filter(...).first()`
    # then track `client.X` accesses.
    for path, content in artifacts.items():
        if not (path.startswith('business/services/') and path.endswith('.py')):
            continue

        for model_name, columns in model_columns.items():
            varname = model_name.lower()  # Client → client
            # Find attribute accesses: varname.something
            for m in re.finditer(rf'\b{re.escape(varname)}\.(\w+)\b', content):
                field = m.group(1)
                # Skip method calls (followed by '('), dunder, sqlalchemy query methods
                ctx_end = m.end()
                next_char = content[ctx_end:ctx_end+1]
                if next_char == '(':
                    continue  # it's a method call
                if field.startswith('_'):
                    continue
                if field in ('id', 'query', 'filter', 'all', 'first', 'commit',
                             'add', 'delete', 'refresh', 'flush', 'close',
                             'update', 'get', 'scalar', 'execute'):
                    continue  # SQLAlchemy/session methods
                if field not in columns and columns:  # columns empty = parse failed
                    line_no = content[:m.start()].count('\n') + 1
                    issues.append({
                        'id': f'INT-FIELD-{model_name}-{field}',
                        'severity': 'HIGH',
                        'category': 'MISSING_MODEL_FIELD',
                        'file': f'business/models/{model_name}.py',
                        'files': [path, f'business/models/{model_name}.py'],
                        'evidence': (
                            f"`{varname}.{field}` accessed in {Path(path).name} line ~{line_no} "
                            f"but {model_name} model has no `{field}` Column. "
                            f"Defined columns: {sorted(columns)}"
                        ),
                        'issue': (
                            f"Service {Path(path).name} accesses {model_name}.{field} "
                            f"which does not exist on the model — will raise AttributeError at runtime."
                        ),
                        'fix': (
                            f"Add `{field} = Column(String, nullable=True)` to business/models/{model_name}.py, "
                            f"OR remove the reference to `{varname}.{field}` in {Path(path).name} "
                            f"and use an existing field instead."
                        ),
                    })

    # Deduplicate (same id may appear from multiple accesses)
    seen = set()
    deduped = []
    for issue in issues:
        if issue['id'] not in seen:
            seen.add(issue['id'])
            deduped.append(issue)
    return deduped


# ── Check 3: Spec compliance ──────────────────────────────────────────────────

def check_spec_compliance(artifacts: dict, intake: dict) -> list:
    """
    Check intake-specified requirements against actual artifacts.
    - PDF requirement: if intake mentions PDF, check for PDF library in requirements
    - KPI names: check each KPI is referenced in at least one service
    - Email field: if intake mentions email, check Client model has email column
    """
    issues = []
    all_content = '\n'.join(artifacts.values()).lower()

    # ── PDF check ─────────────────────────────────────────────────────────────
    intake_text = json.dumps(intake).lower()
    PDF_LIBS = ('reportlab', 'fpdf', 'weasyprint', 'pdfkit', 'pypdf', 'xhtml2pdf')
    if 'pdf' in intake_text:
        # Check if any PDF library appears in requirements or any Python file
        has_pdf_lib = any(lib in all_content for lib in PDF_LIBS)
        # Check if download endpoint exists with pdf content type
        has_pdf_endpoint = 'application/pdf' in all_content or 'pdf' in all_content
        if not has_pdf_lib:
            # Find requirements file
            req_file = next(
                (p for p in artifacts if 'requirements' in p.lower() and p.endswith('.txt')),
                'business/requirements.txt'
            )
            issues.append({
                'id': 'INT-SPEC-PDF',
                'severity': 'HIGH',
                'category': 'SPEC_COMPLIANCE',
                'file': req_file,
                'files': [req_file, 'business/backend/routes/reports.py'],
                'evidence': (
                    f"Intake specifies PDF output but no PDF generation library found. "
                    f"Checked: {', '.join(PDF_LIBS)}"
                ),
                'issue': (
                    "Intake requires downloadable PDF reports but no PDF library is present. "
                    "Download endpoint returns CSV/JSON only."
                ),
                'fix': (
                    "Add `reportlab` to requirements.txt. "
                    "In reports.py download endpoint, add a 'pdf' format branch: "
                    "use reportlab to generate PDF from report_data and return as "
                    "StreamingResponse with media_type='application/pdf'."
                ),
            })

    # ── KPI names check ───────────────────────────────────────────────────────
    kpis = []
    try:
        kpis = intake.get('block_b', {}).get('kpi_definitions', [])
        if not kpis:
            # Try phase_context
            kpis = intake.get('_phase_context', {}).get('kpi_definitions', [])
    except Exception:
        pass

    # Also check phase assessment sibling (if we can infer)
    kpi_names = []
    for kpi in kpis:
        if isinstance(kpi, dict):
            kpi_names.append(kpi.get('name', kpi.get('id', '')))
        elif isinstance(kpi, str):
            kpi_names.append(kpi)

    # Check from intake text: look for KPI acronyms in block_b
    intake_b_text = json.dumps(intake.get('block_b', {}))
    for acronym in re.findall(r'\b([A-Z]{2,5})\b', intake_b_text):
        if acronym not in kpi_names and len(acronym) >= 2:
            kpi_names.append(acronym)

    kpi_names = list(set(kpi_names))
    for kpi in kpi_names:
        if kpi and len(kpi) >= 2:
            if kpi.lower() not in all_content:
                issues.append({
                    'id': f'INT-SPEC-KPI-{kpi}',
                    'severity': 'MEDIUM',
                    'category': 'SPEC_COMPLIANCE',
                    'file': 'business/services/ScoringService.py',
                    'files': ['business/services/ScoringService.py', 'business/services/ReportService.py'],
                    'evidence': (
                        f"KPI '{kpi}' defined in intake but not referenced anywhere in artifacts"
                    ),
                    'issue': (
                        f"Intake KPI '{kpi}' has no implementation in any service or route."
                    ),
                    'fix': (
                        f"Add `_calculate_{kpi.lower()}()` method to ScoringService.py or ReportService.py "
                        f"and include '{kpi}' in the KPI output dict."
                    ),
                })

    # ── Email field check ─────────────────────────────────────────────────────
    if 'email' in intake_text:
        client_content = artifacts.get('business/models/Client.py', '')
        if client_content and 'email' not in client_content.lower():
            issues.append({
                'id': 'INT-SPEC-EMAIL',
                'severity': 'HIGH',
                'category': 'SPEC_COMPLIANCE',
                'file': 'business/models/Client.py',
                'files': ['business/models/Client.py'],
                'evidence': (
                    "Intake references email for clients but Client model has no email Column"
                ),
                'issue': (
                    "Client model is missing email field. Services that reference client.email "
                    "will raise AttributeError at runtime."
                ),
                'fix': (
                    "Add `email = Column(String(255), nullable=True)` to business/models/Client.py "
                    "and add `email: Optional[str]` to ClientCreate/ClientResponse Pydantic schemas."
                ),
            })

    return issues


# ── Check 4: Import chains ────────────────────────────────────────────────────

def check_import_chains(artifacts: dict) -> list:
    """
    Verify that all 'from business.X.Y import Z' statements resolve to
    files that actually exist in the artifact set.
    """
    issues = []
    artifact_files = set(artifacts.keys())

    for path, content in artifacts.items():
        if not path.endswith('.py'):
            continue
        for module, symbol in parse_python_imports(content):
            expected_file = module_to_file_path(module)
            if expected_file not in artifact_files:
                # Only flag if it looks like a real business file
                if not any(skip in module for skip in ('core.', 'lib.', '__init__')):
                    issues.append({
                        'id': f'INT-IMPORT-{module.replace(".", "-")}',
                        'severity': 'HIGH',
                        'category': 'BROKEN_IMPORT',
                        'file': expected_file,
                        'files': [path, expected_file],
                        'evidence': (
                            f"`from {module} import {symbol}` in {Path(path).name} "
                            f"but {expected_file} does not exist in the artifact set"
                        ),
                        'issue': (
                            f"Import `from {module} import {symbol}` will raise ImportError — "
                            f"the file {expected_file} was never generated."
                        ),
                        'fix': (
                            f"Create {expected_file} with the {symbol} class/function, "
                            f"OR remove the import and inline the logic in {Path(path).name}."
                        ),
                    })

    # Deduplicate
    seen = set()
    deduped = []
    for issue in issues:
        if issue['id'] not in seen:
            seen.add(issue['id'])
            deduped.append(issue)
    return deduped


# ── Runner ────────────────────────────────────────────────────────────────────

def run_all_checks(artifacts: dict, intake: dict) -> list:
    print(f"\n  Running Check 1: Route inventory...")
    route_issues = check_route_inventory(artifacts)
    print(f"    → {len(route_issues)} issue(s)")

    print(f"  Running Check 2: Model field refs...")
    field_issues = check_model_field_refs(artifacts)
    print(f"    → {len(field_issues)} issue(s)")

    print(f"  Running Check 3: Spec compliance...")
    spec_issues = check_spec_compliance(artifacts, intake)
    print(f"    → {len(spec_issues)} issue(s)")

    print(f"  Running Check 4: Import chains...")
    import_issues = check_import_chains(artifacts)
    print(f"    → {len(import_issues)} issue(s)")

    return route_issues + field_issues + spec_issues + import_issues


def build_output(issues: list, zip_path: str = None, artifacts_dir: str = None,
                 intake_path: str = None) -> dict:
    from datetime import datetime

    # Deduplicate by id
    seen = set()
    deduped = []
    for issue in issues:
        if issue['id'] not in seen:
            seen.add(issue['id'])
            deduped.append(issue)

    # Collect unique fix target files
    fix_targets = sorted({
        issue['file'] for issue in deduped
        if issue.get('file', '').startswith('business/')
    })

    return {
        'check_date': datetime.now().isoformat(),
        'source_zip': str(zip_path) if zip_path else None,
        'source_artifacts_dir': str(artifacts_dir) if artifacts_dir else None,
        'intake_path': str(intake_path) if intake_path else None,
        'total_issues': len(deduped),
        'high_severity': sum(1 for i in deduped if i['severity'] == 'HIGH'),
        'medium_severity': sum(1 for i in deduped if i['severity'] == 'MEDIUM'),
        'issues': deduped,
        'fix_target_files': fix_targets,
        'verdict': 'INTEGRATION_PASS' if not deduped else 'INTEGRATION_REJECTED',
    }


def print_summary(output: dict):
    verdict = output['verdict']
    total   = output['total_issues']
    high    = output['high_severity']
    medium  = output['medium_severity']

    print(f"\n{'='*60}")
    print(f"INTEGRATION CHECK COMPLETE")
    print(f"{'='*60}")
    print(f"  Total issues: {total}  (HIGH: {high}  MEDIUM: {medium})")
    print(f"  Verdict: {verdict}")

    if output['issues']:
        print(f"\n  Issues found:")
        for issue in output['issues']:
            sev = issue['severity']
            cat = issue['category']
            fid = issue['id']
            print(f"    [{sev}] {fid} ({cat})")
            print(f"           {issue['evidence'][:120]}")

    if output['fix_target_files']:
        print(f"\n  Fix target files:")
        for f in output['fix_target_files']:
            print(f"    - {f}")

    if verdict == 'INTEGRATION_REJECTED':
        print(f"\n  Run harness fix pass:")
        print(f"    python fo_test_harness.py <intake> --resume-run <run_dir> --resume-iteration <N> --integration-issues integration_issues.json")
    print(f"{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(
        description='integration_check.py — Post-build integration validator',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python integration_check.py --zip fo_harness_runs/awi_BLOCK_B_<ts>.zip --intake intake/intake_runs/awi/awi.5.json
  python integration_check.py --artifacts fo_harness_runs/awi_BLOCK_B_<ts>/build/iteration_19_artifacts --intake intake/intake_runs/awi/awi.5.json
        """
    )
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument('--zip',       type=Path, help='Path to harness output ZIP')
    src.add_argument('--artifacts', type=Path, help='Path to iteration_NN_artifacts/ directory')
    parser.add_argument('--intake', type=Path, required=True, help='Original full intake JSON')
    parser.add_argument('--output', type=Path, default=Path('integration_issues.json'),
                        help='Output JSON file (default: integration_issues.json)')
    args = parser.parse_args()

    # Validate inputs
    if args.zip and not args.zip.exists():
        print(f"[ERROR] ZIP not found: {args.zip}")
        sys.exit(1)
    if args.artifacts and not args.artifacts.exists():
        print(f"[ERROR] Artifacts dir not found: {args.artifacts}")
        sys.exit(1)
    if not args.intake.exists():
        print(f"[ERROR] Intake not found: {args.intake}")
        sys.exit(1)

    # Load intake
    with open(args.intake) as f:
        intake = json.load(f)

    # Load artifacts
    print(f"\nLoading artifacts...")
    if args.zip:
        artifacts = load_artifacts_from_zip(args.zip)
    else:
        artifacts = load_artifacts_from_dir(args.artifacts)
    print(f"  {len(artifacts)} file(s) loaded")

    if not artifacts:
        print("[ERROR] No artifacts found")
        sys.exit(1)

    # Run checks
    issues = run_all_checks(artifacts, intake)

    # Build output
    output = build_output(
        issues,
        zip_path=args.zip,
        artifacts_dir=args.artifacts,
        intake_path=args.intake,
    )

    # Write JSON
    with open(args.output, 'w') as f:
        json.dump(output, f, indent=2)
    print(f"\n  Output written: {args.output}")

    # Print summary
    print_summary(output)

    sys.exit(0 if output['verdict'] == 'INTEGRATION_PASS' else 1)


if __name__ == '__main__':
    main()
