#!/usr/bin/env python3
"""
cleanup_fo_harness_runs.py
--------------------------
Targeted cleanup for fo_harness_runs:
- Keep all top-level .zip files
- Keep latest N run directories per prefix (default N=3)
- For older run dirs, delete heavy subfolders (build/, qa/, logs/, tmp/)
  while retaining metadata/cost files for summarize_harness_runs.py

Usage:
  python cleanup_fo_harness_runs.py --runs-dir fo_harness_runs --keep 3 --apply
  python cleanup_fo_harness_runs.py --runs-dir fo_harness_runs --keep 3 --dry-run
"""

from __future__ import annotations

import argparse
import re
import shutil
from pathlib import Path


RUN_DIR_RE = re.compile(r"^(?P<prefix>.+)_BLOCK_[A-Z]_(?P<ts>\d{8}_\d{6})$")

HEAVY_DIRS = {"build", "qa", "logs", "tmp"}


def parse_run_dir(name: str):
    m = RUN_DIR_RE.match(name)
    if not m:
        return None, None
    return m.group("prefix"), m.group("ts")


def main() -> int:
    parser = argparse.ArgumentParser(description="Targeted cleanup for fo_harness_runs.")
    parser.add_argument("--runs-dir", default="fo_harness_runs", help="Runs directory")
    parser.add_argument("--keep", type=int, default=5, help="Latest N run dirs to keep per prefix (default: 5)")
    parser.add_argument("--apply", action="store_true", help="Apply changes")
    parser.add_argument("--dry-run", action="store_true", help="Print actions only (default)")
    args = parser.parse_args()

    if not args.apply and not args.dry_run:
        args.dry_run = True

    runs_dir = Path(args.runs_dir).resolve()
    if not runs_dir.exists():
        print(f"[ERROR] Runs dir not found: {runs_dir}")
        return 2

    # Collect run dirs by prefix
    groups = {}
    for p in runs_dir.iterdir():
        if not p.is_dir():
            continue
        prefix, ts = parse_run_dir(p.name)
        if not prefix:
            continue
        groups.setdefault(prefix, []).append((ts, p))

    # Determine keepers
    keep_dirs = set()
    for prefix, items in groups.items():
        items.sort(key=lambda x: x[0], reverse=True)
        for _, path in items[: args.keep]:
            keep_dirs.add(path)

    # Actions
    for prefix, items in groups.items():
        for ts, path in sorted(items, key=lambda x: x[0], reverse=True):
            if path in keep_dirs:
                continue
            for child in path.iterdir():
                if child.is_dir() and child.name in HEAVY_DIRS:
                    action = f"DELETE DIR {child}"
                    if args.dry_run:
                        print(action)
                    else:
                        shutil.rmtree(child, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
