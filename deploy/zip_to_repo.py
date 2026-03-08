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
import zipfile
from datetime import datetime
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


def _repo_path_from_zip(zip_path: Path, dest_root: Path) -> Path:
    top = _zip_top_level_dir(zip_path)
    repo_name = _safe_name(top) if top else _safe_name(zip_path.stem)
    if "-block-b" in repo_name:
        repo_name = repo_name.split("-block-b", 1)[0]
    return dest_root / repo_name


def _confirm_destructive_action() -> bool:
    response = input("ARE YOU SURE??? (Y/N) ").strip().upper()
    return response == "Y"


def _preclean_repo_path(repo_path: Path, clean_existing: bool, hard_delete_existing: bool):
    if not repo_path.exists():
        return
    if clean_existing:
        if not _confirm_destructive_action():
            print("[INFO] Aborted by user.")
            sys.exit(1)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = repo_path.parent / f"{repo_path.name}_backup_{timestamp}"
        shutil.move(str(repo_path), str(backup_path))
        print(f"[INFO] Archived existing repo to: {backup_path}")
    elif hard_delete_existing:
        if not _confirm_destructive_action():
            print("[INFO] Aborted by user.")
            sys.exit(1)
        shutil.rmtree(repo_path)
        print(f"[INFO] Deleted existing repo: {repo_path}")


def _find_latest_business_artifacts(run_root: Path) -> Path:
    """Find the highest-numbered iteration_XX_artifacts/business/ dir under _harness/build/."""
    import re
    harness_build = run_root / "_harness" / "build"
    if not harness_build.exists():
        return None
    best_iter = -1
    best_path = None
    for d in harness_build.iterdir():
        m = re.match(r'iteration_(\d+)_artifacts$', d.name)
        if m:
            n = int(m.group(1))
            candidate = d / "business"
            if candidate.exists() and n > best_iter:
                best_iter = n
                best_path = candidate
    if best_path:
        print(f"[INFO] Using final artifacts: iteration_{best_iter:02d}_artifacts/business")
    return best_path


def extract_zip(zip_path: Path, dest_root: Path) -> Path:
    """
    1) Extract ZIP into a temp folder inside dest_root
    2) Locate saas-boilerplate/ and latest _harness/build/iterXX_artifacts/business/
    3) Copy saas-boilerplate/ → repo_path/saas-boilerplate/
    4) Copy business/ → repo_path/business/  (repo root, sibling of saas-boilerplate/)
    5) Copy top-level docs (README etc.) to repo root
    6) Clean up temp extraction folder
    """
    import tempfile
    dest_root.mkdir(parents=True, exist_ok=True)
    repo_path = _repo_path_from_zip(zip_path, dest_root)
    repo_path.mkdir(parents=True, exist_ok=True)

    # Extract into a temp dir so we don't pollute the repo folder
    with tempfile.TemporaryDirectory(dir=dest_root) as tmp:
        tmp_path = Path(tmp)
        with zipfile.ZipFile(zip_path, "r") as z:
            z.extractall(tmp_path)

        # Find the top-level run dir inside the temp extraction
        top = _zip_top_level_dir(zip_path)
        if top:
            run_root = tmp_path / top
        else:
            candidates = [p for p in tmp_path.iterdir() if p.is_dir()]
            run_root = candidates[0] if len(candidates) == 1 else tmp_path

        # --- Copy saas-boilerplate/ → repo_path/saas-boilerplate/ ---
        bp_src = run_root / "saas-boilerplate"
        bp_dest = repo_path / "saas-boilerplate"
        if bp_src.exists():
            if bp_dest.exists():
                shutil.rmtree(bp_dest)
            shutil.copytree(bp_src, bp_dest)
            print(f"[INFO] Copied saas-boilerplate/ to repo")
        else:
            print(f"[WARN] saas-boilerplate/ not found in ZIP at: {bp_src}")

        # --- Copy final business/ artifacts → repo_path/business/ (sibling of saas-boilerplate/) ---
        # The boilerplate's frontend/src/core/loader.js resolves ../../../../business/frontend/pages
        # from saas-boilerplate/frontend/src/core → repo root → business/
        # So business/ must sit at the repo root, NOT inside saas-boilerplate/.
        biz_src = _find_latest_business_artifacts(run_root)
        if biz_src and biz_src.exists():
            biz_dest = repo_path / "business"
            if biz_dest.exists():
                shutil.rmtree(biz_dest)
            shutil.copytree(biz_src, biz_dest)
            print(f"[INFO] Copied business/ artifacts to repo root (sibling of saas-boilerplate/)")
        else:
            print(f"[WARN] No business/ artifacts found in ZIP")

        # --- Copy top-level docs to repo root (README, .gitignore, etc.) ---
        for item in run_root.iterdir():
            if item.is_file() and item.name not in ('saas-boilerplate',):
                dest_file = repo_path / item.name
                if not dest_file.exists():
                    shutil.copy2(item, dest_file)

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
    cleanup_group = parser.add_mutually_exclusive_group()
    cleanup_group.add_argument(
        "--clean-existing",
        action="store_true",
        help="Archive existing target repo folder before extraction (asks for confirmation).",
    )
    cleanup_group.add_argument(
        "--hard-delete-existing",
        action="store_true",
        help="Delete existing target repo folder before extraction (asks for confirmation).",
    )
    args = parser.parse_args()

    zip_path = Path(args.zip_path).expanduser().resolve()
    if not zip_path.exists():
        print(f"[ERROR] Zip not found: {zip_path}")
        sys.exit(1)

    config = load_config()
    github_token = config["github"]["token"]
    github_username = config["github"]["username"]

    target_repo_path = _repo_path_from_zip(zip_path, WORK_ROOT)
    _preclean_repo_path(
        target_repo_path,
        clean_existing=args.clean_existing,
        hard_delete_existing=args.hard_delete_existing,
    )

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
