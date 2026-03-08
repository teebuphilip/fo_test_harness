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
    parser.add_argument("--repo",     required=True, help="Repo name e.g. wynwood-thoroughbreds")
    parser.add_argument("--username", default=None,  help="GitHub username (or set GITHUB_USERNAME)")
    parser.add_argument("--token",    default=None,  help="GitHub token (or set GITHUB_TOKEN)")
    args = parser.parse_args()

    token    = args.token    or load_credential("GITHUB_TOKEN",    "TEEBUGITHUBPERSONALACCESSTOKEN")
    username = args.username or load_credential("GITHUB_USERNAME", "GITHUB_USERNAME")

    if not token:
        print("ERROR: set GITHUB_TOKEN or put token in ~/Downloads/ACCESSKEYS/TEEBUGITHUBPERSONALACCESSTOKEN")
        sys.exit(1)
    if not username:
        print("ERROR: set GITHUB_USERNAME or provide --username")
        sys.exit(1)

    repo = args.repo.strip()
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

    # List installed GitHub Apps
    print(f"  [GitHub] Fetching GitHub App installations...")
    try:
        installations = get_installations(token)
    except Exception as e:
        print(f"  [GitHub] ERROR: could not list installations — {e}")
        sys.exit(1)

    if not installations:
        print("  [GitHub] No GitHub App installations found on your account.")
        sys.exit(1)

    found = {i["app_slug"]: i for i in installations}
    print(f"  [GitHub] Found {len(installations)} installation(s): {', '.join(found.keys())}")

    # Grant access for each target app
    for app in APPS_TO_GRANT:
        if app not in found:
            print(f"  [GitHub] {app}: not installed on your account — skipping")
            continue
        installation_id = found[app]["id"]
        print(f"  [GitHub] Granting {app} (installation {installation_id}) access to {repo}...")
        try:
            ok = grant_repo_to_installation(token, installation_id, repo_id)
            if ok:
                print(f"  [GitHub] {app}: access granted ✓")
            else:
                print(f"  [GitHub] {app}: already has access or no change needed")
        except Exception as e:
            print(f"  [GitHub] {app}: ERROR — {e}")

    print(f"\n{'='*60}")
    print(f"Done. Railway and Vercel can now access {username}/{repo}.")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
