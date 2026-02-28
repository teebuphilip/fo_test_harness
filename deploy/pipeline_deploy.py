#!/usr/bin/env python3
"""
pipeline_deploy.py - Master deploy orchestrator
=================================================

NO CLI. NO GUI. Pure Python + requests.

SEQUENCE:
    1. Read deploy_config.json (your tokens)
    2. Push repo to GitHub
    3. Deploy backend to Railway via REST API
    4. If Railway succeeds → deploy frontend to Vercel via REST API
    5. Print both URLs

USAGE:
    python pipeline_deploy.py --repo /path/to/your/repo
    python pipeline_deploy.py --repo /path/to/your/repo --new-project
    python pipeline_deploy.py --repo /path/to/your/repo --backend-only
    python pipeline_deploy.py --repo /path/to/your/repo --frontend-only

CONFIG:
    Put deploy_config.json in the same directory as this script.
    See deploy_config.json for format.
    NEVER commit deploy_config.json to git.

REPO STRUCTURE EXPECTED:
    your-repo/
    ├── railway.json          ← backend deploy config (created by AI post-build)
    ├── vercel.json           ← frontend deploy config (created by AI post-build)
    ├── .env                  ← backend env vars
    ├── saas-boilerplate/
    │   ├── backend/          ← Railway deploys this
    │   └── frontend/         ← Vercel deploys this
    │       └── .env          ← frontend env vars (optional)
    └── requirements.txt      ← Railway detects Python from this
"""

import json
import sys
import argparse
import subprocess
import time
import requests
import os
from datetime import datetime
from pathlib import Path

# ─── Import our API modules ───────────────────────────────────────────────────
# These live in the same directory as this script
sys.path.insert(0, str(Path(__file__).parent))
from railway_deploy import deploy_backend, parse_env_file as railway_parse_env
from vercel_deploy import deploy_frontend


# ============================================================
# CONFIG LOADER
# WHY: All tokens in one place. Never hardcoded.
# ============================================================

CONFIG_FILE = Path(__file__).parent / "deploy_config.json"
AI_COST_LOG = Path(__file__).parent / "deploy_ai_costs.csv"
OPENAI_API = "https://api.openai.com/v1/chat/completions"
CLAUDE_API = "https://api.anthropic.com/v1/messages"
DEFAULT_OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
DEFAULT_CLAUDE_MODEL = "claude-sonnet-4-20250514"


def load_config() -> dict:
    """
    Load deploy_config.json.
    Dies with a clear message if it's missing or malformed.
    """
    if not CONFIG_FILE.exists():
        print(f"""
[ERROR] deploy_config.json not found at:
        {CONFIG_FILE}

Create it with this structure:
{{
  "railway": {{
    "token": "YOUR_RAILWAY_TOKEN"
  }},
  "vercel": {{
    "token": "YOUR_VERCEL_TOKEN",
    "team_id": ""
  }},
  "github": {{
    "token": "YOUR_GITHUB_PAT",
    "username": "YOUR_GITHUB_USERNAME"
  }}
}}

Get tokens:
  Railway → dashboard → Account Settings → Tokens → Create Token
  Vercel  → dashboard → Settings → Tokens → Create Token
  GitHub  → Settings → Developer Settings → Personal Access Tokens → Generate
""")
        sys.exit(1)

    with open(CONFIG_FILE) as f:
        config = json.load(f)

    # Validate required fields
    errors = []
    if not config.get("railway", {}).get("token") or \
       config["railway"]["token"] == "YOUR_RAILWAY_TOKEN_HERE":
        errors.append("railway.token not set in deploy_config.json")
    if not config.get("vercel", {}).get("token") or \
       config["vercel"]["token"] == "YOUR_VERCEL_TOKEN_HERE":
        errors.append("vercel.token not set in deploy_config.json")
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


def _append_ai_cost(provider: str, model: str, input_tokens: int, output_tokens: int):
    in_rate = float(os.getenv("OPENAI_INPUT_PER_MTOK", "2.50"))
    out_rate = float(os.getenv("OPENAI_OUTPUT_PER_MTOK", "10.00"))
    if provider == "claude":
        in_rate = float(os.getenv("ANTHROPIC_INPUT_PER_MTOK", "3.00"))
        out_rate = float(os.getenv("ANTHROPIC_OUTPUT_PER_MTOK", "15.00"))

    in_cost = input_tokens * in_rate / 1_000_000
    out_cost = output_tokens * out_rate / 1_000_000
    total = in_cost + out_cost

    new_file = not AI_COST_LOG.exists()
    with AI_COST_LOG.open("a", newline="") as f:
        if new_file:
            f.write("date,time,provider,model,input_tokens,output_tokens,cost\n")
        now = datetime.now()
        f.write(",".join([
            now.strftime("%Y-%m-%d"),
            now.strftime("%H:%M:%S"),
            provider,
            model,
            str(input_tokens),
            str(output_tokens),
            f"{total:.6f}",
        ]) + "\n")


def _extract_json(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    import re
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("No JSON object found in model response")
    return json.loads(match.group(0))


def _call_chatgpt(prompt: str, model: str) -> dict:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set")
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "Return only JSON. No extra text."},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": 900,
        "temperature": 0.0,
    }
    resp = requests.post(
        OPENAI_API,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    usage = data.get("usage", {})
    _append_ai_cost(
        "chatgpt",
        model,
        int(usage.get("prompt_tokens", 0) or 0),
        int(usage.get("completion_tokens", 0) or 0),
    )
    text = data["choices"][0]["message"]["content"].strip()
    return _extract_json(text)


def _call_claude(prompt: str, model: str) -> dict:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    payload = {
        "model": model,
        "max_tokens": 900,
        "messages": [{"role": "user", "content": prompt}],
    }
    resp = requests.post(
        CLAUDE_API,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json=payload,
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    usage = data.get("usage", {})
    _append_ai_cost(
        "claude",
        model,
        int(usage.get("input_tokens", 0) or 0),
        int(usage.get("output_tokens", 0) or 0),
    )
    text = data["content"][0]["text"].strip()
    return _extract_json(text)


def _repo_tree(repo_path: Path, max_files: int = 300) -> str:
    lines = []
    count = 0
    for path in repo_path.rglob("*"):
        if count >= max_files:
            lines.append("... truncated ...")
            break
        if path.is_dir():
            continue
        rel = path.relative_to(repo_path)
        if any(part in {".git", "node_modules", "__pycache__"} for part in rel.parts):
            continue
        lines.append(str(rel))
        count += 1
    return "\n".join(lines)


def generate_deploy_configs(repo_path: Path, project_name: str, provider: str, openai_model: str, claude_model: str) -> tuple:
    """
    Use AI to generate railway.json + vercel.json based on repo structure.
    """
    tree = _repo_tree(repo_path)
    prompt = "\n".join([
        "You are generating deployment configs for Railway (backend) and Vercel (frontend).",
        "Return JSON with keys: railway_config and vercel_config.",
        "Do not include any text outside JSON.",
        "",
        f"Project name: {project_name}",
        "",
        "Repo tree:",
        tree,
        "",
        "Requirements:",
        "- railway_config should be a railway.json structure with project name.",
        "- vercel_config should be a vercel.json structure with project name.",
        "- Assume backend is saas-boilerplate/backend and frontend is saas-boilerplate/frontend unless evidence suggests otherwise.",
        "- Keep fields minimal and safe.",
        "",
        "Output JSON format:",
        "{",
        '  "railway_config": { ... },',
        '  "vercel_config": { ... }',
        "}",
    ])

    if provider == "chatgpt":
        data = _call_chatgpt(prompt, openai_model)
    else:
        data = _call_claude(prompt, claude_model)

    railway_cfg = data.get("railway_config", {})
    vercel_cfg = data.get("vercel_config", {})
    return railway_cfg, vercel_cfg


# ============================================================
# RAILWAY.JSON / VERCEL.JSON READER
# WHY: AI post-build job writes these into the repo.
#      We read them to know project names and IDs.
# ============================================================

def read_railway_config(repo_path: Path) -> dict:
    """Read railway.json from repo root. Returns {} if not found."""
    cfg_path = repo_path / "railway.json"
    if not cfg_path.exists():
        print("  [pipeline] No railway.json found - will create new Railway project")
        return {}
    with open(cfg_path) as f:
        cfg = json.load(f)
    print(f"  [pipeline] railway.json: project={cfg.get('project', 'unnamed')}")
    return cfg


def read_vercel_config(repo_path: Path) -> dict:
    """Read vercel.json from repo root. Returns {} if not found."""
    cfg_path = repo_path / "vercel.json"
    if not cfg_path.exists():
        print("  [pipeline] No vercel.json found - will create new Vercel project")
        return {}
    with open(cfg_path) as f:
        cfg = json.load(f)
    print(f"  [pipeline] vercel.json: project={cfg.get('project', 'unnamed')}")
    return cfg


def write_config_back(repo_path: Path, filename: str, config: dict):
    """
    Write updated config back to repo.
    WHY: Saves project_id and service_id so next deploy reuses same project.
    """
    cfg_path = repo_path / filename
    with open(cfg_path, "w") as f:
        json.dump(config, f, indent=2)
    print(f"  [pipeline] Updated {filename} with project IDs")


# ============================================================
# GITHUB PUSH
# WHY: Railway and Vercel both pull from GitHub.
#      We push the repo first, then trigger deploys.
# ============================================================

def push_to_github(
    repo_path: Path,
    github_token: str,
    github_username: str,
    repo_name: str = None,
    branch: str = "main",
    new_repo: bool = False,
) -> str:
    """
    Push repo to GitHub via git CLI + GitHub REST API.

    Returns the GitHub repo URL (https://github.com/username/repo).
    """
    repo_name = repo_name or repo_path.name.lower().replace("_", "-").replace(" ", "-")
    github_repo = f"{github_username}/{repo_name}"

    print(f"\n{'='*60}")
    print(f"STEP 1/3: Push to GitHub")
    print(f"{'='*60}")
    print(f"  Repo: {github_repo}")

    # ── Create GitHub repo if needed ─────────────────────────
    if new_repo:
        print(f"  Creating GitHub repo: {repo_name}")
        resp = requests.post(
            "https://api.github.com/user/repos",
            headers={
                "Authorization": f"token {github_token}",
                "Accept": "application/vnd.github.v3+json",
            },
            json={
                "name": repo_name,
                "private": True,
                "auto_init": False,
            }
        )
        if resp.status_code == 422:
            print(f"  Repo already exists on GitHub - continuing")
        elif resp.status_code not in (200, 201):
            print(f"  [WARNING] Could not create repo: {resp.status_code} {resp.text}")
        else:
            print(f"  GitHub repo created: {github_repo}")

    # ── Git init if needed ───────────────────────────────────
    git_dir = repo_path / ".git"
    if not git_dir.exists():
        print("  Initializing git repo...")
        _git(repo_path, "init")
        _git(repo_path, f'config user.email "deploy@teebu.io"')
        _git(repo_path, f'config user.name "Teebu Deploy"')

    # ── Set remote ───────────────────────────────────────────
    remote_url = f"https://{github_token}@github.com/{github_repo}.git"

    # Remove existing origin if any
    _git(repo_path, "remote remove origin", required=False)
    _git(repo_path, f"remote add origin {remote_url}")

    # ── Ensure .gitignore has the right entries ──────────────
    _ensure_gitignore(repo_path)

    # ── Commit and push ──────────────────────────────────────
    _git(repo_path, "add -A")

    # Check if there's anything to commit
    status = _git(repo_path, "status --porcelain", capture=True, required=False)
    if status:
        _git(repo_path, f'commit -m "deploy: automated build commit"')
    else:
        print("  Nothing new to commit - pushing existing HEAD")

    _git(repo_path, f"branch -M {branch}")
    _git(repo_path, f"push -u origin {branch} --force")

    print(f"  Pushed to: https://github.com/{github_repo}")
    return f"https://github.com/{github_repo}", github_repo


def _ensure_gitignore(repo_path: Path):
    """Make sure sensitive files are in .gitignore."""
    gitignore_path = repo_path / ".gitignore"
    must_ignore = [
        ".env",
        "deploy_config.json",
        "__pycache__/",
        "*.pyc",
        "node_modules/",
        ".DS_Store",
        "dist/",
        "build/",
    ]

    existing = ""
    if gitignore_path.exists():
        existing = gitignore_path.read_text()

    additions = []
    for entry in must_ignore:
        if entry not in existing:
            additions.append(entry)

    if additions:
        with open(gitignore_path, "a") as f:
            f.write("\n# Added by pipeline_deploy.py\n")
            for entry in additions:
                f.write(f"{entry}\n")
        print(f"  Updated .gitignore with {len(additions)} entries")


def _git(repo_path: Path, cmd: str, capture: bool = False, required: bool = True):
    """Run a git command in the repo directory."""
    import subprocess
    result = subprocess.run(
        f"git {cmd}",
        shell=True,
        cwd=repo_path,
        capture_output=capture,
        text=True
    )
    if required and result.returncode != 0:
        stderr = result.stderr if capture else ""
        print(f"[ERROR] git {cmd} failed: {stderr}")
        sys.exit(1)
    if capture:
        return result.stdout.strip()
    return result.returncode == 0


# ============================================================
# DEPLOY SUMMARY PRINTER
# ============================================================

def print_summary(github_url, railway_result, vercel_result):
    print(f"\n{'='*60}")
    print("DEPLOY COMPLETE")
    print(f"{'='*60}")

    print(f"\n  GitHub:   {github_url}")

    if railway_result and railway_result.get("success"):
        url = railway_result.get("url", "check Railway dashboard")
        print(f"  Backend:  {url}")
        print(f"  Health:   {url}/health" if url and url.startswith("http") else "")
        print(f"  API Docs: {url}/docs" if url and url.startswith("http") else "")
    else:
        print(f"  Backend:  FAILED - check Railway dashboard")

    if vercel_result and vercel_result.get("success"):
        url = vercel_result.get("url", "check Vercel dashboard")
        print(f"  Frontend: {url}")
    elif vercel_result is None:
        print(f"  Frontend: skipped (--backend-only)")
    else:
        print(f"  Frontend: FAILED - check Vercel dashboard")

    print(f"\n  Railway logs: railway logs (or dashboard)")
    print(f"  Vercel  logs: vercel.com/dashboard")
    print(f"{'='*60}\n")


# ============================================================
# MAIN PIPELINE
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="Deploy backend to Railway + frontend to Vercel. No CLI. No GUI."
    )
    parser.add_argument(
        "--repo",
        required=True,
        help="Path to the repo to deploy"
    )
    parser.add_argument(
        "--new-project",
        action="store_true",
        help="Force create new Railway/Vercel projects (ignore existing IDs in railway.json/vercel.json)"
    )
    parser.add_argument(
        "--backend-only",
        action="store_true",
        help="Only deploy backend to Railway, skip Vercel"
    )
    parser.add_argument(
        "--frontend-only",
        action="store_true",
        help="Only deploy frontend to Vercel, skip Railway"
    )
    parser.add_argument(
        "--branch",
        default="main",
        help="Git branch to deploy (default: main)"
    )
    parser.add_argument(
        "--framework",
        default="create-react-app",
        help="Vercel framework preset (default: create-react-app). Use 'vite' for Vite projects."
    )
    parser.add_argument(
        "--frontend-dir",
        default="saas-boilerplate/frontend",
        help="Frontend subdirectory in repo (default: saas-boilerplate/frontend)"
    )
    parser.add_argument(
        "--output-dir",
        default="build",
        help="Frontend build output dir (default: build). Use 'dist' for Vite."
    )
    parser.add_argument(
        "--provider",
        choices=["chatgpt", "claude"],
        default="chatgpt",
        help="AI provider for config generation (default: chatgpt)"
    )
    parser.add_argument(
        "--openai-model",
        default=DEFAULT_OPENAI_MODEL,
        help="OpenAI model for config generation"
    )
    parser.add_argument(
        "--claude-model",
        default=DEFAULT_CLAUDE_MODEL,
        help="Claude model for config generation"
    )

    args = parser.parse_args()
    repo_path = Path(args.repo).resolve()

    if not repo_path.exists():
        print(f"[ERROR] Repo path not found: {repo_path}")
        sys.exit(1)

    if args.provider == "chatgpt" and not os.getenv("OPENAI_API_KEY"):
        print("[ERROR] OPENAI_API_KEY not set")
        sys.exit(2)
    if args.provider == "claude" and not os.getenv("ANTHROPIC_API_KEY"):
        print("[ERROR] ANTHROPIC_API_KEY not set")
        sys.exit(3)

    # ── Load credentials ─────────────────────────────────────
    print(f"\nLoading credentials from: {CONFIG_FILE}")
    config = load_config()

    railway_token  = config["railway"]["token"]
    vercel_token   = config["vercel"]["token"]
    vercel_team_id = config["vercel"].get("team_id", "")
    github_token   = config["github"]["token"]
    github_username = config["github"]["username"]

    # ── Read repo configs ────────────────────────────────────
    railway_cfg = {} if args.new_project else read_railway_config(repo_path)
    vercel_cfg  = {} if args.new_project else read_vercel_config(repo_path)

    project_name = (
        railway_cfg.get("project")
        or vercel_cfg.get("project")
        or repo_path.name.lower().replace("_", "-")
    )

    # ── Generate configs via AI before push ─────────────────
    print(f"\n{'='*60}")
    print("STEP 0/3: Generate railway.json + vercel.json via AI")
    print(f"{'='*60}")
    try:
        railway_ai_cfg, vercel_ai_cfg = generate_deploy_configs(
            repo_path, project_name, args.provider, args.openai_model, args.claude_model
        )
        if railway_ai_cfg:
            write_config_back(repo_path, "railway.json", railway_ai_cfg)
        if vercel_ai_cfg:
            write_config_back(repo_path, "vercel.json", vercel_ai_cfg)
    except Exception as e:
        print(f"[ERROR] Failed to generate deploy configs: {e}")
        sys.exit(1)

    # ── STEP 1: Push to GitHub ───────────────────────────────
    github_url, github_repo = push_to_github(
        repo_path=repo_path,
        github_token=github_token,
        github_username=github_username,
        repo_name=project_name,
        branch=args.branch,
        new_repo=args.new_project,
    )

    # Small pause - let GitHub settle before Railway/Vercel pull
    time.sleep(3)

    railway_result = None
    vercel_result  = None

    # ── STEP 2: Deploy backend to Railway ────────────────────
    if not args.frontend_only:
        print(f"\n{'='*60}")
        print(f"STEP 2/3: Deploy Backend → Railway")
        print(f"{'='*60}")

        try:
            railway_result = deploy_backend(
                token=railway_token,
                repo_path=repo_path,
                github_repo_url=github_url,
                project_name=project_name,
                add_postgres=not railway_cfg.get("postgres_added"),
                railway_config=railway_cfg,
            )

            if railway_result["success"]:
                print(f"  [Railway] SUCCESS: {railway_result.get('url', 'no URL yet')}")

                # Save project/service IDs back to railway.json for next deploy
                railway_cfg.update({
                    "project": project_name,
                    "project_id": railway_result["project_id"],
                    "service_id": railway_result["service_id"],
                    "postgres_added": True,
                })
                write_config_back(repo_path, "railway.json", railway_cfg)
            else:
                print("  [Railway] FAILED")

        except Exception as e:
            print(f"  [Railway] ERROR: {e}")
            railway_result = {"success": False, "error": str(e)}

    # ── STEP 3: Deploy frontend to Vercel ────────────────────
    # Only runs if Railway succeeded (or --frontend-only)
    railway_ok = args.frontend_only or (railway_result and railway_result.get("success"))

    if not args.backend_only and railway_ok:
        print(f"\n{'='*60}")
        print(f"STEP 3/3: Deploy Frontend → Vercel")
        print(f"{'='*60}")

        backend_url = railway_result.get("url") if railway_result else None

        try:
            vercel_result = deploy_frontend(
                token=vercel_token,
                repo_path=repo_path,
                github_repo=github_repo,
                project_name=f"{project_name}-frontend",
                framework=args.framework,
                root_directory=args.frontend_dir,
                output_directory=args.output_dir,
                branch=args.branch,
                vercel_config=vercel_cfg,
                team_id=vercel_team_id or None,
                backend_url=backend_url,
            )

            if vercel_result["success"]:
                print(f"  [Vercel] SUCCESS: {vercel_result.get('url', 'no URL yet')}")

                # Save project ID back to vercel.json for next deploy
                vercel_cfg.update({
                    "project": f"{project_name}-frontend",
                    "project_id": vercel_result["project_id"],
                })
                write_config_back(repo_path, "vercel.json", vercel_cfg)
            else:
                print("  [Vercel] FAILED")

        except Exception as e:
            print(f"  [Vercel] ERROR: {e}")
            vercel_result = {"success": False, "error": str(e)}

    elif not args.backend_only and not railway_ok:
        print(f"\n[SKIPPED] Vercel deploy skipped because Railway failed.")
        print(f"  Fix Railway first, then run with --frontend-only")

    # ── Print summary ────────────────────────────────────────
    print_summary(github_url, railway_result, vercel_result)

    # Exit code: 0 = success, 1 = at least one failure
    if railway_result and not railway_result.get("success"):
        sys.exit(1)
    if vercel_result and not vercel_result.get("success"):
        sys.exit(1)


if __name__ == "__main__":
    main()
