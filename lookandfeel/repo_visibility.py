#!/usr/bin/env python3
"""
Toggle GitHub repo visibility (public/private).

Usage:
  python lookandfeel/repo_visibility.py --repo owner/name --visibility public
  python lookandfeel/repo_visibility.py --repo owner/name --visibility private
"""

import argparse
import os
import re
import sys

import requests


def parse_repo(repo: str) -> str:
    repo = repo.strip()
    if repo.startswith("http://") or repo.startswith("https://"):
        m = re.search(r"github\.com/([^/]+/[^/]+)", repo)
        if not m:
            raise ValueError("Invalid GitHub repo URL")
        repo = m.group(1)
    repo = repo.replace(".git", "").strip("/")
    if repo.count("/") != 1:
        raise ValueError("Repo must be owner/name")
    return repo


def main() -> None:
    parser = argparse.ArgumentParser(description="Set GitHub repo visibility")
    parser.add_argument("--repo", required=True, help="owner/name or GitHub URL")
    parser.add_argument(
        "--visibility",
        required=True,
        choices=["public", "private"],
        help="Target visibility",
    )
    args = parser.parse_args()

    token = os.getenv("GITHUB_TOKEN", "").strip()
    if not token:
        print("Error: GITHUB_TOKEN not set")
        sys.exit(2)

    repo = parse_repo(args.repo)
    make_private = args.visibility == "private"
    url = f"https://api.github.com/repos/{repo}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    resp = requests.patch(url, headers=headers, json={"private": make_private}, timeout=30)
    if resp.status_code >= 400:
        print(f"Error: {resp.status_code} {resp.text}")
        sys.exit(1)

    data = resp.json()
    final_visibility = "private" if data.get("private") else "public"
    print(f"Updated: {data.get('full_name')} -> {final_visibility}")


if __name__ == "__main__":
    main()
