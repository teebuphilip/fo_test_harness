#!/usr/bin/env python3
"""
write_deploy_state.py
---------------------
Helper to write deploy state JSON files (railway.deploy.json / vercel.deploy.json)
and optionally set simple env entries for documentation.

Usage:
  python deploy/write_deploy_state.py --repo /path/to/repo --target railway \
    --project <name> --project-id <id> --service-id <id> --postgres-added true

  python deploy/write_deploy_state.py --repo /path/to/repo --target railway \
    --service-domain backend-production-xxx.up.railway.app

  python deploy/write_deploy_state.py --repo /path/to/repo --target vercel \
    --project <name> --project-id <id>
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


TARGET_FILES = {
    "railway": "railway.deploy.json",
    "vercel": "vercel.deploy.json",
}


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def _write_json(path: Path, data: dict):
    path.write_text(json.dumps(data, indent=2) + "\n")


def _parse_bool(value: str | None) -> bool | None:
    if value is None:
        return None
    v = value.strip().lower()
    if v in {"true", "1", "yes", "y"}:
        return True
    if v in {"false", "0", "no", "n"}:
        return False
    raise ValueError(f"Invalid boolean value: {value}")


def _merge_updates(data: dict, updates: dict[str, Any]) -> dict:
    for k, v in updates.items():
        if v is None:
            continue
        data[k] = v
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description="Write deploy state JSON files.")
    parser.add_argument("--repo", required=True, help="Path to repo")
    parser.add_argument("--target", required=True, choices=["railway", "vercel"])
    parser.add_argument("--project", help="Project name")
    parser.add_argument("--project-id", help="Project ID")
    parser.add_argument("--service-id", help="Service ID (Railway only)")
    parser.add_argument("--service-domain", help="Service domain (Railway only)")
    parser.add_argument("--postgres-added", help="true/false (Railway only)")
    parser.add_argument("--env", action="append", default=[], help="KEY=VALUE (stored under env)")
    args = parser.parse_args()

    repo_path = Path(args.repo).resolve()
    if not repo_path.exists():
        print(f"[ERROR] Repo path not found: {repo_path}")
        return 2

    target_file = repo_path / TARGET_FILES[args.target]
    data = _load_json(target_file)

    updates: dict[str, Any] = {
        "project": args.project,
        "project_id": args.project_id,
        "service_id": args.service_id if args.target == "railway" else None,
        "service_domain": args.service_domain if args.target == "railway" else None,
        "postgres_added": _parse_bool(args.postgres_added) if args.target == "railway" else None,
    }

    data = _merge_updates(data, updates)

    if args.env:
        env_obj = data.get("env") if isinstance(data.get("env"), dict) else {}
        for kv in args.env:
            if "=" not in kv:
                print(f"[WARN] Skipping invalid --env (no '='): {kv}")
                continue
            k, _, v = kv.partition("=")
            env_obj[k.strip()] = v
        data["env"] = env_obj

    _write_json(target_file, data)
    print(f"Wrote {target_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
