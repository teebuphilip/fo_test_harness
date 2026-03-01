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
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


WORK_ROOT = Path("~/Documents/work").expanduser()


def load_config() -> dict:
    github_token = os.getenv("GITHUB_TOKEN")
    github_username = os.getenv("GITHUB_USERNAME")
    errors = []
    if not github_token:
        errors.append("GITHUB_TOKEN not set")
    if not github_username:
        errors.append("GITHUB_USERNAME not set")
    if errors:
        print("[ERROR] Missing required environment variables:")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)
    return {"github": {"token": github_token, "username": github_username}}


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
    """
    1) Create empty repo folder in ~/Documents/work
    2) Copy ZIP there
    3) Unzip inside repo folder
    4) Copy build/iteration_04_artifacts/business -> ./business
    """
    dest_root.mkdir(parents=True, exist_ok=True)
    top = _zip_top_level_dir(zip_path)
    repo_name = _safe_name(top) if top else _safe_name(zip_path.stem)
    repo_path = dest_root / repo_name

    repo_path.mkdir(parents=True, exist_ok=True)
    local_zip = repo_path / zip_path.name
    if not local_zip.exists():
        shutil.copy2(zip_path, local_zip)

    # unzip inside repo folder
    with zipfile.ZipFile(local_zip, "r") as z:
        z.extractall(repo_path)

    # copy boilerplate into repo root
    if top:
        run_root = repo_path / top
    else:
        # best-effort: find a single extracted folder
        candidates = [p for p in repo_path.iterdir() if p.is_dir() and p.name != ".git"]
        run_root = candidates[0] if len(candidates) == 1 else repo_path

    boilerplate_src = run_root / "boilerplate"
    boilerplate_dest = repo_path / "boilerplate"
    if boilerplate_src.exists():
        if boilerplate_dest.exists():
            shutil.rmtree(boilerplate_dest)
        shutil.copytree(boilerplate_src, boilerplate_dest)
    else:
        print(f"[WARN] Boilerplate not found at: {boilerplate_src}")

    # copy final artifacts into boilerplate business directory
    src = run_root / "build" / "iteration_04_artifacts" / "business"
    dest = repo_path / "boilerplate" / "saas-boilerplate" / "business"
    if src.exists():
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(src, dest)
    else:
        print(f"[WARN] Expected artifacts not found at: {src}")

    return repo_path


def ensure_git_repo(repo_path: Path):
    git_dir = repo_path / ".git"
    if not git_dir.exists():
        _run("git init", cwd=repo_path)
        _run('git config user.email "deploy@teebu.io"', cwd=repo_path)
        _run('git config user.name "Teebu Deploy"', cwd=repo_path)


def commit_all(repo_path: Path, message: str):
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
    # Remove existing origin if present
    subprocess.run("git remote remove origin", shell=True, cwd=repo_path, capture_output=True, text=True)
    _run(f"git remote add origin {remote_url}", cwd=repo_path)
    _run("git branch -M main", cwd=repo_path)
    _run("git push -u origin main --force", cwd=repo_path)


def _derive_repo_name(repo_path: Path) -> str:
    name = _safe_name(repo_path.name)
    if "-block-b" in name:
        return name.split("-block-b", 1)[0]
    return name


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
    repo_name = _derive_repo_name(repo_path)
    commit_all(repo_path, f"Initial {repo_name.replace('-', ' ').title()} integration from harness zip")
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
