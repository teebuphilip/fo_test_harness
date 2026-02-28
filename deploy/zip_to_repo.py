#!/usr/bin/env python3
"""
zip_to_repo.py
==============
1) Take a zip file from fo_test_harness.py
2) Extract into ~/Documents/work/<startup_name>
3) Init/commit git repo (or commit updates if already exists)
4) Create/push to GitHub (if repo exists, just push)

Usage:
  python deploy/zip_to_repo.py /path/to/run.zip
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


CONFIG_FILE = Path(__file__).parent / "deploy_config.json"
WORK_ROOT = Path("~/Documents/work").expanduser()


def load_config() -> dict:
    if not CONFIG_FILE.exists():
        print(f"[ERROR] deploy_config.json not found at {CONFIG_FILE}")
        sys.exit(1)
    with open(CONFIG_FILE) as f:
        config = json.load(f)
    errors = []
    if not config.get("github", {}).get("token") or \
       config["github"]["token"] == "YOUR_GITHUB_PAT_HERE":
        errors.append("github.token not set in deploy_config.json")
    if not config.get("github", {}).get("username") or \
       config["github"]["username"] == "YOUR_GITHUB_USERNAME":
        errors.append("github.username not set in deploy_config.json")
    if errors:
        print("[ERROR] deploy_config.json has unfilled values:")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)
    return config


def _run(cmd: str, cwd: Path = None, capture: bool = False):
    result = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=capture, text=True)
    if result.returncode != 0:
        print(f"[ERROR] Command failed: {cmd}")
        if capture:
            print(result.stderr)
        sys.exit(1)
    return result.stdout.strip() if capture else ""


def _zip_top_level_dir(zip_path: Path) -> str:
    with zipfile.ZipFile(zip_path, "r") as z:
        names = [n for n in z.namelist() if n and not n.startswith("__MACOSX")]
    top_levels = {n.split("/")[0] for n in names if "/" in n}
    if len(top_levels) == 1:
        return list(top_levels)[0]
    return ""


def _safe_name(name: str) -> str:
    return name.strip().lower().replace(" ", "-").replace("_", "-")


def extract_zip(zip_path: Path, dest_root: Path) -> Path:
    dest_root.mkdir(parents=True, exist_ok=True)
    top = _zip_top_level_dir(zip_path)
    if top:
        dest = dest_root / _safe_name(top)
    else:
        dest = dest_root / _safe_name(zip_path.stem)

    if dest.exists():
        print(f"[INFO] Destination exists: {dest}")
        return dest

    with tempfile.TemporaryDirectory() as tmpdir:
        with zipfile.ZipFile(zip_path, "r") as z:
            z.extractall(tmpdir)
        tmp = Path(tmpdir)
        if top and (tmp / top).exists():
            shutil.move(str(tmp / top), dest)
        else:
            dest.mkdir(parents=True, exist_ok=True)
            for child in tmp.iterdir():
                shutil.move(str(child), dest / child.name)

    return dest


def ensure_git_repo(repo_path: Path):
    git_dir = repo_path / ".git"
    if not git_dir.exists():
        _run("git init", cwd=repo_path)
        _run('git config user.email "deploy@teebu.io"', cwd=repo_path)
        _run('git config user.name "Teebu Deploy"', cwd=repo_path)


def commit_all(repo_path: Path, message: str = "deploy: initial commit"):
    _run("git add -A", cwd=repo_path)
    status = _run("git status --porcelain", cwd=repo_path, capture=True)
    if status:
        _run(f'git commit -m "{message}"', cwd=repo_path)
    else:
        print("[INFO] No changes to commit")


def github_repo_exists(token: str, owner: str, repo: str) -> bool:
    import requests
    resp = requests.get(
        f"https://api.github.com/repos/{owner}/{repo}",
        headers={"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"},
    )
    return resp.status_code == 200


def create_github_repo(token: str, repo: str) -> None:
    import requests
    resp = requests.post(
        "https://api.github.com/user/repos",
        headers={"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"},
        json={"name": repo, "private": True, "auto_init": False},
    )
    if resp.status_code not in (200, 201, 422):
        print(f"[ERROR] GitHub repo create failed: {resp.status_code} {resp.text}")
        sys.exit(1)


def push_to_github(repo_path: Path, token: str, owner: str, repo: str):
    remote_url = f"https://{token}@github.com/{owner}/{repo}.git"
    _run("git remote remove origin", cwd=repo_path, capture=False)
    _run(f"git remote add origin {remote_url}", cwd=repo_path)
    _run("git branch -M main", cwd=repo_path)
    _run("git push -u origin main --force", cwd=repo_path)


def main():
    parser = argparse.ArgumentParser(description="Extract zip to ~/Documents/work and push to GitHub")
    parser.add_argument("zip_path", help="Path to build zip")
    args = parser.parse_args()

    zip_path = Path(args.zip_path).expanduser().resolve()
    if not zip_path.exists():
        print(f"[ERROR] Zip not found: {zip_path}")
        sys.exit(1)

    config = load_config()
    github_token = config["github"]["token"]
    github_username = config["github"]["username"]

    repo_path = extract_zip(zip_path, WORK_ROOT)
    print(f"[INFO] Repo path: {repo_path}")

    ensure_git_repo(repo_path)
    commit_all(repo_path)

    repo_name = _safe_name(repo_path.name)
    exists = github_repo_exists(github_token, github_username, repo_name)
    if not exists:
        print(f"[INFO] Creating GitHub repo: {repo_name}")
        create_github_repo(github_token, repo_name)
    else:
        print(f"[INFO] GitHub repo exists: {repo_name}")

    push_to_github(repo_path, github_token, github_username, repo_name)
    print(f"[INFO] Pushed: https://github.com/{github_username}/{repo_name}")


if __name__ == "__main__":
    main()
