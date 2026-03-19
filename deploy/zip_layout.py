#!/usr/bin/env python3
"""
zip_layout.py
==============
Shared helpers for understanding multi-entity harness ZIP structure.
Used by:
  - check_final_zip.py
  - deploy/zip_to_repo.py
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path
from typing import Optional, Iterable


def zip_top_level_dir(zip_path: Path) -> str:
    """Return the single top-level dir name if ZIP has exactly one; else ''."""
    with zipfile.ZipFile(zip_path, "r") as z:
        names = [n for n in z.namelist() if n and not n.startswith("__MACOSX")]
    top_levels = {n.split("/")[0] for n in names if "/" in n}
    if len(top_levels) == 1:
        return list(top_levels)[0]
    return ""


def iter_num(iter_dir_name: str) -> int:
    m = re.search(r'(\d+)', iter_dir_name)
    return int(m.group(1)) if m else 0


def best_iter_dir(entity_root: Path) -> Optional[Path]:
    """
    Return the highest-numbered iteration_NN_artifacts/ directory inside an
    entity dir. Checks both `build/` and `_harness/build/`.
    """
    for sub in ("build", "_harness/build"):
        build_dir = entity_root / sub
        if not build_dir.is_dir():
            continue
        candidates = [
            d for d in build_dir.iterdir()
            if d.is_dir() and re.match(r'iteration_\d+_artifacts$', d.name)
        ]
        if candidates:
            return max(candidates, key=lambda d: iter_num(d.name))
    return None


def find_entity_dirs(extract_root: Path) -> list[Path]:
    """
    Return sorted list of entity dirs inside an extracted ZIP root.
    """
    entity_dirs = [d for d in extract_root.iterdir() if d.is_dir()]
    entity_dirs.sort(key=lambda d: d.name)
    return entity_dirs


def _maybe_descend_single_root(root: Path, max_depth: int = 3) -> Path:
    """
    If the extracted ZIP has a single top-level directory, descend into it.
    Repeats up to max_depth to handle wrapper folders.
    """
    current = root
    for _ in range(max_depth):
        try:
            dirs = [d for d in current.iterdir() if d.is_dir()]
        except Exception:
            return current
        if len(dirs) == 1:
            current = dirs[0]
            continue
        break
    return current


def merge_business_artifacts(
    extract_root: Path,
    ignore_paths: Iterable[str] = ("__pycache__",),
    ignore_suffixes: Iterable[str] = (".pyc",),
) -> tuple[dict[str, str], list[tuple[str, str, int]]]:
    """
    Merge business/** from each entity's latest iteration.
    Returns:
      merged: { 'business/relative/path': content }
      report: [ (entity_dir_name, iter_dir_name, file_count) ]
    """
    extract_root = _maybe_descend_single_root(extract_root)
    merged: dict[str, str] = {}
    report: list[tuple[str, str, int]] = []
    entity_dirs = find_entity_dirs(extract_root)
    # If still empty, try one more descend and re-scan.
    if not entity_dirs:
        extract_root = _maybe_descend_single_root(extract_root, max_depth=1)
        entity_dirs = find_entity_dirs(extract_root)
    # If entity dirs are empty but the root itself looks like an entity, treat it as one.
    if not entity_dirs and extract_root.is_dir():
        entity_dirs = [extract_root]
    for entity_dir in entity_dirs:
        best = best_iter_dir(entity_dir)
        if best is None:
            continue
        biz_dir = best / "business"
        if not biz_dir.is_dir():
            continue
        files_added = 0
        for f in biz_dir.rglob("*"):
            if not f.is_file():
                continue
            if f.suffix in ignore_suffixes:
                continue
            path_str = str(f)
            if any(p in path_str for p in ignore_paths):
                continue
            rel = "business/" + str(f.relative_to(biz_dir))
            try:
                merged[rel] = f.read_text(errors="replace")
                files_added += 1
            except Exception:
                pass
        report.append((entity_dir.name, best.name, files_added))
    return merged, report
