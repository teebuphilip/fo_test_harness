#!/usr/bin/env python3
"""
check_business_imports.py
-------------------------
Static check for business frontend pages that are copied into frontend/src.

Why: CRA only compiles files inside frontend/src. The deploy pipeline copies
business/frontend/pages -> frontend/src/business/pages. Relative imports must
resolve from the copied location.

Behavior:
- Scans business/frontend/pages/*.jsx for relative imports
- Resolves them as if files were located in frontend/src/business/pages
- If any are unresolved, prints a report and exits non-zero
- If the only issues are "../utils/api", it offers an auto-fix prompt
"""

from __future__ import annotations

import re
import sys
import argparse
from pathlib import Path
import subprocess


IMPORT_PATTERN = re.compile(
    r"""(?:from\s+['"]([^'"]+)['"]|require\(\s*['"]([^'"]+)['"]\s*\)|import\(\s*['"]([^'"]+)['"]\s*\))"""
)

DEFAULT_EXTS = [".js", ".jsx", ".ts", ".tsx", ".json"]
ASSET_EXTS = [
    ".css", ".scss", ".sass", ".less",
    ".svg", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico",
    ".woff", ".woff2", ".ttf", ".eot",
]


def _exists_from(base_file: Path, spec: str, exts: list[str]) -> bool:
    base = (base_file.parent / spec).resolve()
    candidates = []
    if base.suffix:
        candidates.append(base)
    else:
        candidates.append(base)
        candidates.extend(Path(str(base) + ext) for ext in exts)
        candidates.extend(base / f"index{ext}" for ext in exts)
    return any(p.exists() for p in candidates)


def _collect_issues(repo_path: Path, exts: list[str], report_all: bool):
    source_dir = repo_path / "business" / "frontend" / "pages"
    dest_dir = repo_path / "frontend" / "src" / "business" / "pages"
    if not source_dir.exists():
        return [], ["Missing business/frontend/pages"]

    issues = []
    all_rel = []
    for src_file in sorted(source_dir.glob("*.jsx")):
        try:
            content = src_file.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        dest_file = dest_dir / src_file.name
        for match in IMPORT_PATTERN.findall(content):
            spec = next((g for g in match if g), "")
            if not spec.startswith("."):
                continue
            ok = _exists_from(dest_file, spec, exts)
            if report_all:
                all_rel.append((src_file, spec, ok))
            if not ok:
                issues.append((src_file, spec))
    return issues, [], all_rel


def _fix_known_issues(issues: list[tuple[Path, str]]) -> tuple[int, int]:
    """
    Fix known relative import: ../utils/api -> ../../utils/api
    Returns (files_changed, replacements_made).
    """
    files_changed = 0
    replacements = 0
    for src_file, spec in issues:
        if spec != "../utils/api":
            continue
        content = src_file.read_text(encoding="utf-8", errors="ignore")
        new_content = content.replace("from '../utils/api'", "from '../../utils/api'")
        if new_content != content:
            src_file.write_text(new_content, encoding="utf-8")
            files_changed += 1
            replacements += 1
    return files_changed, replacements


def _git_commit(repo_path: Path, files: list[Path]) -> bool:
    rel_paths = [str(p.relative_to(repo_path)) for p in files]
    try:
        subprocess.run(["git", "add", "--", *rel_paths], cwd=repo_path, check=False)
        result = subprocess.run(
            ["git", "commit", "-m", "fix: update business page api import paths"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            print("Committed changes.")
            return True
        if "nothing to commit" in (result.stdout or "") or "nothing to commit" in (result.stderr or ""):
            print("No changes to commit.")
            return False
        print(f"Git commit failed: {result.stderr.strip() or result.stdout.strip()}")
        return False
    except Exception as e:
        print(f"Git commit failed: {e}")
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Check business page imports after copy into frontend/src.")
    parser.add_argument("repo", help="Path to repo")
    parser.add_argument("--report-all", action="store_true", help="Print all relative imports and their resolution.")
    parser.add_argument("--include-assets", action="store_true", help="Include asset extensions (css/images/fonts) in resolution.")
    parser.add_argument("--ext", action="append", default=[], help="Add extra extension(s) to check (e.g. --ext .mjs).")
    args = parser.parse_args()

    repo_path = Path(args.repo).resolve()
    if not repo_path.exists():
        print(f"[ERROR] Repo path not found: {repo_path}")
        return 2

    print("Checking business page imports...")
    print(f"  Repo: {repo_path}")

    exts = list(DEFAULT_EXTS)
    if args.include_assets:
        exts.extend(ASSET_EXTS)
    for ext in args.ext:
        if not ext.startswith("."):
            ext = "." + ext
        if ext not in exts:
            exts.append(ext)

    print(f"  Extensions: {', '.join(exts)}")
    if args.report_all:
        print("  Report all: enabled")
    if args.include_assets:
        print("  Include assets: enabled")
    if args.ext:
        print(f"  Extra extensions: {', '.join(args.ext)}")
    print("  Scanning business/frontend/pages/*.jsx ...")

    issues, errors, all_rel = _collect_issues(repo_path, exts, args.report_all)
    if errors:
        for e in errors:
            print(f"[ERROR] {e}")
        return 2

    if args.report_all and all_rel:
        print("Relative imports (post-copy resolution):")
        for src_file, spec, ok in all_rel:
            rel = src_file.relative_to(repo_path)
            print(f"  {rel}: {spec} -> {'OK' if ok else 'MISSING'}")
        print()

    if not issues:
        print("OK: No unresolved relative imports after copy.")
        return 0

    print("Unresolved relative imports after copy:")
    for src_file, spec in issues:
        rel = src_file.relative_to(repo_path)
        print(f"  - {rel}: {spec}")

    fixable = all(spec == "../utils/api" for _, spec in issues)
    if fixable:
        answer = input("Apply fix (rewrite ../utils/api -> ../../utils/api) in business pages? (yes/no): ").strip().lower()
        if answer in {"y", "yes"}:
            files_changed, replacements = _fix_known_issues(issues)
            print(f"Applied fix: {files_changed} file(s) updated, {replacements} replacement(s).")
            if files_changed:
                files = [src for src, _ in issues]
                _git_commit(repo_path, files)
            return 0
        print("No changes made.")
        return 1

    print("Some issues are not auto-fixable. Please resolve manually.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
