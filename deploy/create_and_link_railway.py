#!/usr/bin/env python3
"""
create_and_link_railway.py
==========================
Create a Railway project/service, persist IDs to railway.deploy.json,
attempt to link the GitHub repo, and rename the project when linked.

Usage:
  python deploy/create_and_link_railway.py --repo ~/Documents/work/my_repo
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

# Allow running from repo root or deploy/ dir
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from deploy.railway_deploy import RailwayAPI  # noqa: E402
from deploy.pipeline_deploy import (  # noqa: E402
    read_railway_config,
    write_config_back,
    _base_project_name,
    RAILWAY_STATE_FILE,
)


def _git_remote_url(repo_path: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return None
        return result.stdout.strip() or None
    except Exception:
        return None


def _normalize_github_url(url: str) -> str | None:
    if not url:
        return None
    url = url.strip()
    if url.startswith("git@github.com:"):
        # git@github.com:owner/repo.git
        path = url.split(":", 1)[1]
        if path.endswith(".git"):
            path = path[:-4]
        return f"https://github.com/{path}"
    if url.startswith("https://github.com/"):
        if url.endswith(".git"):
            return url[:-4]
        return url
    return None


def _fallback_github_url(repo_path: Path) -> str | None:
    username = os.getenv("GITHUB_USERNAME")
    if not username:
        return None
    return f"https://github.com/{username}/{repo_path.name}"


def _service_has_repo_link(api: RailwayAPI, service_id: str) -> bool:
    candidates = [
        (
            """
            query Service($id: String!) {
                service(id: $id) {
                    id
                    source { repo }
                }
            }
            """,
            lambda d: d.get("service", {}).get("source", {}).get("repo"),
        ),
        (
            """
            query Service($id: String!) {
                service(id: $id) {
                    id
                    repo
                }
            }
            """,
            lambda d: d.get("service", {}).get("repo"),
        ),
    ]
    for q, extractor in candidates:
        try:
            data = api._query(q, {"id": service_id})
            repo = extractor(data)
            if repo:
                return True
        except Exception:
            continue
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Create Railway project/service and link repo")
    parser.add_argument("--repo", required=True, help="Path to local repo")
    parser.add_argument("--debug", action="store_true", help="Log Railway GraphQL to /tmp/railway_debug.log")
    args = parser.parse_args()

    repo_path = Path(args.repo).expanduser().resolve()
    if not repo_path.exists():
        print(f"[ERROR] Repo path not found: {repo_path}")
        return 1

    token = os.getenv("RAILWAY_TOKEN")
    if not token:
        print("[ERROR] RAILWAY_TOKEN not set")
        return 1

    github_url = _normalize_github_url(_git_remote_url(repo_path) or "") or _fallback_github_url(repo_path)
    if not github_url:
        print("[ERROR] Could not resolve GitHub repo URL. Set GITHUB_USERNAME or add git remote origin.")
        return 1

    api = RailwayAPI(token, debug_log="/tmp/railway_debug.log" if args.debug else None)
    project_name = _base_project_name(repo_path, read_railway_config(repo_path))
    cfg = read_railway_config(repo_path)

    project_id = cfg.get("project_id")
    service_id = cfg.get("service_id")

    if not project_id:
        print(f"[Railway] Creating project: {project_name}-tmp")
        workspace_id = api.get_workspace_id()
        project = api.create_project(f"{project_name}-tmp", workspace_id=workspace_id)
        project_id = project["id"]
        print(f"[Railway] Project created: {project_id}")
    else:
        print(f"[Railway] Reusing project: {project_id}")

    if not service_id:
        print("[Railway] Creating service: backend (no repo)")
        service = api.create_service(project_id=project_id, name="backend", repo_url=None)
        service_id = service["id"]
        print(f"[Railway] Service created: {service_id}")
    else:
        print(f"[Railway] Reusing service: {service_id}")

    # Persist IDs immediately
    cfg.update({
        "project": project_name,
        "project_id": project_id,
        "service_id": service_id,
    })
    write_config_back(repo_path, RAILWAY_STATE_FILE, cfg)
    print(f"[Railway] Updated {RAILWAY_STATE_FILE} with IDs")

    # Attempt link
    print("[Railway] Linking GitHub repo to service...")
    try:
        api.link_repo_to_service(service_id, github_url)
    except Exception as e:
        print(f"[Railway] Repo link failed: {e}")

    linked = _service_has_repo_link(api, service_id)
    if linked:
        print("[Railway] Repo linked. Renaming project...")
        try:
            api.update_project_name(project_id, project_name)
        except Exception as e:
            print(f"[Railway] Project rename skipped: {e}")
        print("[Railway] OK")
        return 0

    print("[Railway] Repo not linked — manual link required in Railway UI.")
    print(f"[Railway] Project: https://railway.app/project/{project_id}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
