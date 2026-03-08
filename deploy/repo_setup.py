#!/usr/bin/env python3
"""
repo_setup.py — Grant Railway + Vercel GitHub App access to a repo.

Reads GITHUB_TOKEN and GITHUB_USERNAME from env vars or ACCESSKEYS directory.

Usage:
    python repo_setup.py --repo wynwood-thoroughbreds
"""

import argparse
import os
import sys
from pathlib import Path

import requests

ACCESSKEYS_DIR = Path.home() / "Downloads" / "ACCESSKEYS"
GITHUB_API = "https://api.github.com"
APPS_TO_GRANT = ["railway", "vercel"]


def load_credential(env_var: str, filename: str) -> str:
    val = os.getenv(env_var, "").strip()
    if val:
        return val
    path = ACCESSKEYS_DIR / filename
    if path.exists():
        return "".join(path.read_text().split())
    return ""


def gh(token: str, method: str, path: str, **kwargs) -> requests.Response:
    resp = requests.request(
        method,
        f"{GITHUB_API}{path}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        timeout=30,
        **kwargs,
    )
    return resp


def get_repo_id(token: str, owner: str, repo: str) -> int:
    resp = gh(token, "GET", f"/repos/{owner}/{repo}")
    resp.raise_for_status()
    return resp.json()["id"]


def get_installations(token: str) -> list:
    resp = gh(token, "GET", "/user/installations?per_page=100")
    resp.raise_for_status()
    return resp.json().get("installations", [])


def grant_repo_to_installation(token: str, installation_id: int, repo_id: int) -> bool:
    resp = gh(token, "PUT", f"/user/installations/{installation_id}/repositories/{repo_id}")
    return resp.status_code in (204, 304)


def main():
    parser = argparse.ArgumentParser(description="Grant Railway + Vercel GitHub App access to a repo")
    parser.add_argument("--repo",  required=True, help="Repo name or full local path e.g. ~/Documents/work/wynwood-thoroughbreds")
    parser.add_argument("--token", default=None,  help="GitHub token (or set GITHUB_TOKEN)")
    args = parser.parse_args()

    token    = args.token or load_credential("GITHUB_TOKEN", "TEEBUGITHUBPERSONALACCESSTOKEN")
    username = load_credential("GITHUB_USERNAME", "GITHUB_USERNAME")

    if not token:
        print("ERROR: set GITHUB_TOKEN or put token in ~/Downloads/ACCESSKEYS/TEEBUGITHUBPERSONALACCESSTOKEN")
        sys.exit(1)
    if not username:
        print("ERROR: set GITHUB_USERNAME env var or add GITHUB_USERNAME file to ACCESSKEYS")
        sys.exit(1)

    # Accept full local path or bare repo name
    repo = Path(args.repo.strip()).expanduser().resolve().name
    print(f"\n{'='*60}")
    print(f"Repo Setup: {username}/{repo}")
    print(f"{'='*60}\n")

    # Get repo ID
    print(f"  [GitHub] Looking up repo ID for {username}/{repo}...")
    try:
        repo_id = get_repo_id(token, username, repo)
        print(f"  [GitHub] Repo ID: {repo_id}")
    except Exception as e:
        print(f"  [GitHub] ERROR: could not find repo — {e}")
        sys.exit(1)

    # GitHub API can't list installations with a PAT — open browser instead
    import subprocess, platform
    print(f"\n  [GitHub] Opening Railway + Vercel settings in your browser...")
    print(f"  [GitHub] For each app — click Configure → add '{repo}' → Save\n")

    urls = [
        f"https://github.com/settings/installations",
    ]
    for url in urls:
        if platform.system() == "Darwin":
            subprocess.run(["open", url])
        else:
            print(f"  Open this URL: {url}")

    print(f"{'='*60}")
    print(f"Steps:")
    print(f"  1. Find 'Railway App' → click Configure → add '{repo}'")
    print(f"  2. Find 'Vercel'      → click Configure → add '{repo}'")
    print(f"  3. Save both, then re-run pipeline_deploy.py")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
