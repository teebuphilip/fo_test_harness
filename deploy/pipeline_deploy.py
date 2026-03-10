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
    ├── railway.deploy.json   ← backend deploy state (project/service IDs)
    ├── vercel.deploy.json    ← frontend deploy state (project ID)
    ├── vercel.json           ← OPTIONAL Vercel runtime config (must follow Vercel schema)
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
import shutil
import re
from datetime import datetime
from pathlib import Path

# ─── Import our API modules ───────────────────────────────────────────────────
# These live in the same directory as this script
sys.path.insert(0, str(Path(__file__).parent))
from railway_deploy import deploy_backend, RailwayAPI, parse_env_file as railway_parse_env
from vercel_deploy import deploy_frontend, VercelAPI
from auth0_setup import update_spa_urls


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
RAILWAY_STATE_FILE = "railway.deploy.json"
VERCEL_STATE_FILE = "vercel.deploy.json"
LEGACY_RAILWAY_FILE = "railway.json"
LEGACY_VERCEL_FILE = "vercel.json"


def load_config() -> dict:
    """
    Load deployment tokens from environment variables.
    """
    railway_token = os.getenv("RAILWAY_TOKEN")
    vercel_token = os.getenv("VERCEL_TOKEN")
    vercel_team_id = os.getenv("VERCEL_TEAM_ID", "")
    github_token = os.getenv("GITHUB_TOKEN")
    github_username = os.getenv("GITHUB_USERNAME")

    errors = []
    if not railway_token:
        errors.append("RAILWAY_TOKEN not set")
    if not vercel_token:
        errors.append("VERCEL_TOKEN not set")
    if not github_token:
        errors.append("GITHUB_TOKEN not set")
    if not github_username:
        errors.append("GITHUB_USERNAME not set")

    if errors:
        print("[ERROR] Missing required environment variables:")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)

    return {
        "railway": {"token": railway_token},
        "vercel": {"token": vercel_token, "team_id": vercel_team_id},
        "github": {"token": github_token, "username": github_username},
    }


def _safe_project_name(value: str) -> str:
    if not value:
        return ""
    cleaned = value.strip().lower().replace("_", "-").replace(" ", "-")
    if cleaned in {"unnamed", "unknown", "none", "null"}:
        return ""
    return cleaned


def _base_project_name(repo_path: Path, railway_cfg: dict) -> str:
    repo_name = _safe_project_name(repo_path.name)
    # Always use repo name as the canonical project base name.
    return repo_name


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
    Use AI to generate deploy state JSON for Railway + Vercel.
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
        "- railway_config should include project name and optional IDs/placeholders.",
        "- vercel_config should include project name and optional IDs/placeholders.",
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
# DEPLOY STATE READER
# WHY: Deploy pipeline state is stored in dedicated files to avoid
#      collisions with Vercel's runtime config schema in vercel.json.
# ============================================================

def read_railway_config(repo_path: Path) -> dict:
    """Read Railway deploy state. Prefer railway.deploy.json, fallback legacy railway.json."""
    cfg_path = repo_path / RAILWAY_STATE_FILE
    if not cfg_path.exists():
        legacy_path = repo_path / LEGACY_RAILWAY_FILE
        if legacy_path.exists():
            cfg_path = legacy_path
            print(f"  [pipeline] Using legacy {LEGACY_RAILWAY_FILE} (consider migrating to {RAILWAY_STATE_FILE})")
        else:
            print(f"  [pipeline] No {RAILWAY_STATE_FILE} found - will create new Railway project")
            return {}
    with open(cfg_path) as f:
        cfg = json.load(f)
    print(f"  [pipeline] {cfg_path.name}: project={cfg.get('project', 'unnamed')}")
    return cfg


def read_vercel_config(repo_path: Path) -> dict:
    """Read Vercel deploy state. Prefer vercel.deploy.json, fallback legacy vercel.json."""
    cfg_path = repo_path / VERCEL_STATE_FILE
    if not cfg_path.exists():
        legacy_path = repo_path / LEGACY_VERCEL_FILE
        if legacy_path.exists():
            cfg_path = legacy_path
            print(f"  [pipeline] Using legacy {LEGACY_VERCEL_FILE} for deploy state")
        else:
            print(f"  [pipeline] No {VERCEL_STATE_FILE} found - will create new Vercel project")
            return {}
    with open(cfg_path) as f:
        cfg = json.load(f)
    print(f"  [pipeline] {cfg_path.name}: project={cfg.get('project', 'unnamed')}")
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


def sanitize_vercel_runtime_config(repo_path: Path):
    """
    Ensure repo vercel.json is valid Vercel runtime config.
    If legacy pipeline keys are present, back up and remove them.
    """
    vercel_path = repo_path / LEGACY_VERCEL_FILE
    if not vercel_path.exists():
        return
    try:
        with open(vercel_path) as f:
            data = json.load(f)
    except Exception:
        return

    if not isinstance(data, dict):
        return

    original_data = dict(data)

    removed_fields = []
    for key in ("project", "project_id", "service_id"):
        if key in data:
            data.pop(key, None)
            removed_fields.append(key)

    # Some legacy/generated vercel.json files contain invalid schema under `build`.
    # Example failure:
    #   Invalid request: `build` should NOT have additional property `outputDirectory`
    build_cfg = data.get("build")
    if isinstance(build_cfg, dict) and "outputDirectory" in build_cfg:
        build_cfg.pop("outputDirectory", None)
        removed_fields.append("build.outputDirectory")

    if not removed_fields:
        return

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = repo_path / f"vercel.json.pipeline-backup.{ts}"
    with open(backup, "w") as f:
        json.dump(original_data, f, indent=2)

    with open(vercel_path, "w") as f:
        json.dump(data, f, indent=2)

    print(f"  [pipeline] Sanitized vercel.json (removed {', '.join(removed_fields)}; backup: {backup.name})")


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
    _ensure_frontend_business_config(repo_path)
    _ensure_business_pages_in_src(repo_path)

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


def _ensure_frontend_business_config(repo_path: Path):
    """
    Ensure frontend business_config.json is present and staged for deploy.

    Vercel build expects this file. It is often gitignored in frontend repos.
    """
    cfg_rel = Path("frontend/src/config/business_config.json")
    example_rel = Path("frontend/src/config/business_config.example.json")
    cfg_path = repo_path / cfg_rel
    example_path = repo_path / example_rel

    if not cfg_path.exists():
        if example_path.exists():
            cfg_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(example_path, cfg_path)
            print("  [pipeline] Created frontend business_config.json from example")
        else:
            print("  [pipeline] WARNING: frontend business_config.json missing and no example found")
            return

    # Force-add in case frontend/.gitignore excludes it.
    _git(repo_path, f"add -f -- {cfg_rel.as_posix()}", required=False)
    print("  [pipeline] Ensured frontend business_config.json is staged for push")


def _ensure_railway_toml(repo_path: Path):
    """
    Write railway.toml inside backend/ (flat layout: zip_to_repo puts main.py there).
    Railway root directory = backend/, so start command is just uvicorn main:app.
    """
    content = (
        '[build]\n'
        'builder = "nixpacks"\n'
        '\n'
        '[deploy]\n'
        'startCommand = "uvicorn main:app --host 0.0.0.0 --port $PORT"\n'
        'restartPolicyType = "ON_FAILURE"\n'
        'restartPolicyMaxRetries = 10\n'
    )
    backend_dir = repo_path / "backend"
    if backend_dir.exists():
        (backend_dir / "railway.toml").write_text(content)
        print("  [pipeline] railway.toml written (backend/)")
    else:
        print("  [pipeline] WARNING: backend/ dir not found — railway.toml not written")


def _ensure_business_pages_in_src(repo_path: Path):
    """
    Copy business/frontend/pages/*.jsx into saas-boilerplate/frontend/src/business/pages/
    and patch loader.js to use the inside-src path.

    WHY: react-scripts (CRA) only applies babel-loader to files inside src/.
    The boilerplate loader.js uses require.context('../../../../business/frontend/pages')
    which resolves to repo_root/business/frontend/pages — outside src/ — so webpack
    can't parse JSX there. Fix: copy pages into src/ and update the loader path.
    """
    biz_pages_src = repo_path / "business" / "frontend" / "pages"
    if not biz_pages_src.exists():
        print("  [pipeline] No business/frontend/pages/ found — skipping src copy")
        return

    # Destination: inside src/ so babel-loader processes it
    biz_pages_dest = repo_path / "frontend" / "src" / "business" / "pages"
    if biz_pages_dest.exists():
        shutil.rmtree(biz_pages_dest)
    shutil.copytree(biz_pages_src, biz_pages_dest)
    print(f"  [pipeline] Copied business pages into frontend/src/business/pages/ ({len(list(biz_pages_dest.glob('*.jsx')))} .jsx files)")

    # Patch loader.js: update require.context path to in-src location
    loader_path = repo_path / "frontend" / "src" / "core" / "loader.js"
    if loader_path.exists():
        content = loader_path.read_text()
        NEW_PATH = "../business/pages"
        # Support both old (saas-boilerplate layout) and new (flat layout) paths
        OLD_PATHS = [
            "../../../../business/frontend/pages",  # old: saas-boilerplate/frontend/src/core/
            "../../../business/frontend/pages",      # new: frontend/src/core/
        ]
        old_found = next((p for p in OLD_PATHS if p in content), None)
        OLD_PATH = old_found
        if OLD_PATH and OLD_PATH in content:
            patched = content.replace(OLD_PATH, NEW_PATH)
            loader_path.write_text(patched)
            print("  [pipeline] Patched loader.js: require.context path → ../business/pages")
        elif NEW_PATH in content:
            print("  [pipeline] loader.js already patched")
        else:
            print("  [pipeline] WARNING: loader.js path not recognized — skipping patch")
    else:
        print("  [pipeline] WARNING: loader.js not found — skipping patch")


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


def _import_target_exists(importer_file: Path, import_spec: str) -> bool:
    """Resolve a relative import and check if a matching file/directory exists."""
    base = (importer_file.parent / import_spec).resolve()
    exts = [".js", ".jsx", ".ts", ".tsx", ".json"]
    candidates = []

    if base.suffix:
        candidates.append(base)
    else:
        candidates.append(base)
        for ext in exts:
            candidates.append(Path(str(base) + ext))
        for ext in exts:
            candidates.append(base / f"index{ext}")

    return any(p.exists() for p in candidates)


def preflight_frontend_business_imports(repo_path: Path) -> list:
    """
    Validate frontend relative imports that reference business frontend modules.
    Returns a list of unresolved import diagnostics.
    """
    frontend_src = repo_path / "boilerplate" / "saas-boilerplate" / "frontend" / "src"
    if not frontend_src.exists():
        return []

    issues = []
    pattern = re.compile(r"""(?:from\s+['"]([^'"]+)['"]|require\(\s*['"]([^'"]+)['"]\s*\)|import\(\s*['"]([^'"]+)['"]\s*\))""")

    for file_path in frontend_src.rglob("*"):
        if file_path.suffix not in {".js", ".jsx", ".ts", ".tsx"}:
            continue
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        for match in pattern.findall(content):
            import_spec = next((g for g in match if g), "")
            if not import_spec.startswith("."):
                continue
            if "business/frontend" not in import_spec:
                continue
            if _import_target_exists(file_path, import_spec):
                continue

            suggestion = ""
            if import_spec.startswith("../../../../business/frontend/"):
                suggestion = import_spec.replace("../../../../", "../../../", 1)

            rel_file = file_path.relative_to(repo_path)
            msg = f"{rel_file}: unresolved import '{import_spec}'"
            if suggestion:
                msg += f" (try '{suggestion}')"
            issues.append(msg)

    return issues


def persist_deploy_state_if_changed(repo_path: Path, branch: str):
    """
    Auto-commit deploy state files if they changed.
    Runs only after successful deploy flow.
    """
    tracked = [RAILWAY_STATE_FILE, VERCEL_STATE_FILE, LEGACY_VERCEL_FILE]
    status = _git(repo_path, "status --porcelain", capture=True, required=False) or ""
    changed_paths = []
    for line in status.splitlines():
        if len(line) < 4:
            continue
        path = line[3:].strip()
        # Handle rename lines like: "R  old -> new"
        if " -> " in path:
            path = path.split(" -> ", 1)[1].strip()
        changed_paths.append(path)

    to_commit = [p for p in tracked if p in changed_paths]
    if not to_commit:
        print("  [pipeline] No deploy state changes to commit")
        return

    print(f"  [pipeline] Persisting deploy state changes: {', '.join(to_commit)}")
    for rel_path in to_commit:
        _git(repo_path, f"add -- {rel_path}", required=False)

    staged = _git(repo_path, "diff --cached --name-only", capture=True, required=False) or ""
    if not staged.strip():
        print("  [pipeline] No staged deploy state changes")
        return

    _git(repo_path, 'commit -m "deploy: persist deploy state"', required=False)
    _git(repo_path, f"push origin {branch}", required=False)
    print("  [pipeline] Deploy state committed and pushed")


# ============================================================
# DEPLOY SUMMARY PRINTER
# ============================================================

def print_summary(
    github_url,
    railway_result,
    vercel_result,
    backend_skipped=False,
    railway_cfg=None,
    vercel_cfg=None,
    backend_url=None,
    frontend_url=None,
):
    print(f"\n{'='*60}")
    print("DEPLOY COMPLETE")
    print(f"{'='*60}")

    print(f"\n  GitHub:   {github_url}")

    resolved_backend_url = backend_url or (railway_result or {}).get("url")
    resolved_frontend_url = frontend_url or (vercel_result or {}).get("url")

    if backend_skipped and not resolved_backend_url:
        print(f"  Backend:  skipped (--frontend-only)")
    elif railway_result and railway_result.get("success") or resolved_backend_url:
        show_backend = resolved_backend_url or "check Railway dashboard"
        print(f"  Backend:  {show_backend}")
        print(f"  Health:   {show_backend}/health" if show_backend and str(show_backend).startswith("http") else "")
        print(f"  API Docs: {show_backend}/docs" if show_backend and str(show_backend).startswith("http") else "")
    else:
        print(f"  Backend:  FAILED - check Railway dashboard")

    if vercel_result and vercel_result.get("success") or resolved_frontend_url:
        show_frontend = resolved_frontend_url or "check Vercel dashboard"
        print(f"  Frontend: {show_frontend}")
    elif vercel_result is None:
        print(f"  Frontend: skipped (--backend-only)")
    else:
        print(f"  Frontend: FAILED - check Vercel dashboard")

    railway_project_id = (railway_result or {}).get("project_id") or (railway_cfg or {}).get("project_id")
    if railway_project_id:
        print(f"  Railway:  https://railway.app/project/{railway_project_id}")
    else:
        print(f"  Railway:  https://railway.app/dashboard")

    vercel_project = (vercel_cfg or {}).get("project")
    if vercel_project:
        print(f"  Vercel:   https://vercel.com/dashboard/projects/{vercel_project}")
    else:
        print(f"  Vercel:   https://vercel.com/dashboard")

    print(f"\n  Railway logs: railway logs (or dashboard)")
    print(f"  Vercel  logs: vercel.com/dashboard")
    print(f"{'='*60}\n")


def get_existing_backend_url(railway_token: str, railway_cfg: dict) -> str:
    project_id = (railway_cfg or {}).get("project_id")
    service_id = (railway_cfg or {}).get("service_id")
    if not project_id or not service_id:
        return None
    try:
        api = RailwayAPI(railway_token)
        domain = api.get_service_url(project_id, service_id)
        if not domain:
            return None
        return domain if domain.startswith("http") else f"https://{domain}"
    except Exception as e:
        print(f"  [pipeline] Could not fetch backend URL from Railway IDs: {e}")
        return None


def get_existing_frontend_url(vercel_token: str, vercel_cfg: dict, team_id: str = None) -> str:
    project_id = (vercel_cfg or {}).get("project_id")
    if not project_id:
        return None
    try:
        api = VercelAPI(vercel_token, team_id=team_id or None)
        latest = api.get_latest_deployment(project_id)
        if not latest:
            return None
        url = latest.get("url")
        if not url:
            return None
        return url if url.startswith("http") else f"https://{url}"
    except Exception as e:
        print(f"  [pipeline] Could not fetch frontend URL from Vercel project ID: {e}")
        return None


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
        help="Force create new Railway/Vercel projects (ignore existing IDs in deploy state files)"
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

    # ── Step 0: Check Auth0 credentials exist + merge into .env ─────────────
    app_name   = repo_path.name
    keys_file  = Path.home() / "Downloads" / "ACCESSKEYS" / f"auth0_{app_name}.env"
    if not keys_file.exists():
        print(f"\n[ERROR] Auth0 credentials not found for '{app_name}'")
        print(f"  Expected: {keys_file}")
        print(f"\n  Run this first:")
        print(f"    python deploy/auth0_setup.py --app-name {app_name}")
        print()
        sys.exit(1)

    # Merge Auth0 creds into repo .env so Railway picks them up
    repo_env   = repo_path / ".env"
    auth0_vars = {}
    for line in keys_file.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, _, v = line.partition("=")
            auth0_vars[k.strip()] = v.strip()

    existing_env = repo_env.read_text() if repo_env.exists() else ""
    additions = []
    for k, v in auth0_vars.items():
        if k not in existing_env:
            additions.append(f"{k}={v}")
    if additions:
        with open(repo_env, "a") as f:
            f.write("\n# Auth0 (injected by pipeline_deploy)\n")
            f.write("\n".join(additions) + "\n")
        print(f"  [pipeline] Injected {len(additions)} Auth0 vars into .env")
    else:
        print(f"  [pipeline] Auth0 vars already in .env — skipping")

    if args.provider == "chatgpt" and not os.getenv("OPENAI_API_KEY"):
        print("[ERROR] OPENAI_API_KEY not set")
        sys.exit(2)
    if args.provider == "claude" and not os.getenv("ANTHROPIC_API_KEY"):
        print("[ERROR] ANTHROPIC_API_KEY not set")
        sys.exit(3)

    # ── Load credentials ─────────────────────────────────────
    print(f"\nLoading credentials from environment variables")
    config = load_config()

    railway_token  = config["railway"]["token"]
    vercel_token   = config["vercel"]["token"]
    vercel_team_id = config["vercel"].get("team_id", "")
    github_token   = config["github"]["token"]
    github_username = config["github"]["username"]

    # ── Sanitize runtime vercel.json if it contains legacy pipeline fields ──
    sanitize_vercel_runtime_config(repo_path)

    # ── Read deploy state configs ────────────────────────────
    railway_cfg = {} if args.new_project else read_railway_config(repo_path)
    vercel_cfg  = {} if args.new_project else read_vercel_config(repo_path)

    # Base project/repo name must map to the backend repo, not the Vercel frontend project.
    project_name = _base_project_name(repo_path, railway_cfg)

    # ── Generate configs via AI before push ─────────────────
    railway_cfg_path = repo_path / RAILWAY_STATE_FILE
    vercel_cfg_path = repo_path / VERCEL_STATE_FILE
    if railway_cfg_path.exists() and vercel_cfg_path.exists():
        print(f"\n{'='*60}")
        print(f"STEP 0/3: Generate {RAILWAY_STATE_FILE} + {VERCEL_STATE_FILE} via AI")
        print(f"{'='*60}")
        print("  [pipeline] Existing config files found - skipping AI regeneration")
    else:
        print(f"\n{'='*60}")
        print(f"STEP 0/3: Generate {RAILWAY_STATE_FILE} + {VERCEL_STATE_FILE} via AI")
        print(f"{'='*60}")
        try:
            railway_ai_cfg, vercel_ai_cfg = generate_deploy_configs(
                repo_path, project_name, args.provider, args.openai_model, args.claude_model
            )
            if railway_ai_cfg:
                write_config_back(repo_path, RAILWAY_STATE_FILE, railway_ai_cfg)
            if vercel_ai_cfg:
                write_config_back(repo_path, VERCEL_STATE_FILE, vercel_ai_cfg)
        except Exception as e:
            print(f"[ERROR] Failed to generate deploy configs: {e}")
            sys.exit(1)

    # ── STEP 0b: Write railway.toml ─────────────────────────
    _ensure_railway_toml(repo_path)

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

                # Save project/service IDs back to Railway deploy state for next deploy
                railway_cfg.update({
                    "project": project_name,
                    "project_id": railway_result["project_id"],
                    "service_id": railway_result["service_id"],
                    "postgres_added": True,
                })
                write_config_back(repo_path, RAILWAY_STATE_FILE, railway_cfg)
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

        # Give Railway additional time to publish service URL after a trigger.
        # This improves chances of injecting backend URL into Vercel env vars.
        if not args.frontend_only:
            print("  [pipeline] Waiting 60s for Railway URL readiness before Vercel deploy...")
            time.sleep(60)

        import_issues = preflight_frontend_business_imports(repo_path)
        if import_issues:
            print("  [pipeline] Frontend preflight failed: unresolved business imports")
            for issue in import_issues[:20]:
                print(f"    - {issue}")
            if len(import_issues) > 20:
                print(f"    - ... and {len(import_issues) - 20} more")
            vercel_result = {
                "success": False,
                "status": "ERROR",
                "error": "FRONTEND_PREFLIGHT_FAILED",
                "reason": "Unresolved frontend imports into business modules",
            }
            print("  [Vercel] FAILED (preflight)")
        else:
            backend_url = railway_result.get("url") if railway_result else None
            if not backend_url:
                merged_for_backend = dict(railway_cfg or {})
                if railway_result:
                    if railway_result.get("project_id"):
                        merged_for_backend["project_id"] = railway_result.get("project_id")
                    if railway_result.get("service_id"):
                        merged_for_backend["service_id"] = railway_result.get("service_id")
                backend_url = get_existing_backend_url(railway_token, merged_for_backend)
                if backend_url:
                    print(f"  [pipeline] Resolved backend URL for Vercel env injection: {backend_url}")

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

                    # Save project ID back to Vercel deploy state for next deploy
                    vercel_cfg.update({
                        "project": f"{project_name}-frontend",
                        "project_id": vercel_result["project_id"],
                    })
                    write_config_back(repo_path, VERCEL_STATE_FILE, vercel_cfg)
                else:
                    print("  [Vercel] FAILED")

            except Exception as e:
                print(f"  [Vercel] ERROR: {e}")
                vercel_result = {"success": False, "error": str(e)}

    elif not args.backend_only and not railway_ok:
        print(f"\n[SKIPPED] Vercel deploy skipped because Railway failed.")
        print(f"  Fix Railway first, then run with --frontend-only")

    if args.frontend_only and (not railway_result or not railway_result.get("url")):
        existing_backend_url = get_existing_backend_url(railway_token, railway_cfg)
        if existing_backend_url:
            railway_result = railway_result or {"success": True}
            railway_result["url"] = existing_backend_url

    if (vercel_result is None or not vercel_result.get("url")) and not args.backend_only:
        existing_frontend_url = get_existing_frontend_url(vercel_token, vercel_cfg, team_id=vercel_team_id or None)
        if existing_frontend_url:
            vercel_result = vercel_result or {"success": True}
            vercel_result["url"] = existing_frontend_url

    final_backend_url = None
    if railway_result and railway_result.get("url"):
        final_backend_url = railway_result.get("url")
    if not final_backend_url:
        merged_railway_cfg = dict(railway_cfg or {})
        if railway_result:
            if railway_result.get("project_id"):
                merged_railway_cfg["project_id"] = railway_result.get("project_id")
            if railway_result.get("service_id"):
                merged_railway_cfg["service_id"] = railway_result.get("service_id")
        final_backend_url = get_existing_backend_url(railway_token, merged_railway_cfg)

    final_frontend_url = None
    if vercel_result and vercel_result.get("url"):
        final_frontend_url = vercel_result.get("url")
    if not final_frontend_url:
        merged_vercel_cfg = dict(vercel_cfg or {})
        if vercel_result and vercel_result.get("project_id"):
            merged_vercel_cfg["project_id"] = vercel_result.get("project_id")
        final_frontend_url = get_existing_frontend_url(vercel_token, merged_vercel_cfg, team_id=vercel_team_id or None)

    # ── Step 4a: Push CORS_ORIGINS + ENVIRONMENT to Railway once Vercel URL known ──
    vercel_succeeded = args.backend_only or (vercel_result and vercel_result.get("success"))
    railway_succeeded = args.frontend_only or (railway_result and railway_result.get("success"))
    if final_frontend_url and vercel_succeeded and railway_succeeded and not args.frontend_only:
        try:
            r_api      = RailwayAPI(railway_token)
            r_proj_id  = railway_cfg.get("project_id")
            r_svc_id   = railway_cfg.get("service_id")
            r_env_id   = railway_cfg.get("environment_id") or r_api.get_environment_id(r_proj_id)
            if r_proj_id and r_svc_id:
                print("\n  [Railway] Setting CORS_ORIGINS + ENVIRONMENT=production...")
                post_vars = {"CORS_ORIGINS": final_frontend_url, "ENVIRONMENT": "production"}
                failed = {}
                for k, v in post_vars.items():
                    try:
                        r_api.set_variable(r_proj_id, r_svc_id, k, v, environment_id=r_env_id)
                    except Exception:
                        failed[k] = v
                if failed:
                    import subprocess as _sp, shutil as _sh
                    cli = _sh.which("railway")
                    if cli:
                        still_failed = {}
                        for k, v in failed.items():
                            res = _sp.run(
                                [cli, "variables", "--set", f"{k}={v}",
                                 "--project", r_proj_id, "--service", r_svc_id],
                                capture_output=True, text=True, timeout=30,
                                env={**os.environ, "RAILWAY_TOKEN": railway_token}
                            )
                            if res.returncode == 0:
                                print(f"  [Railway] CLI set: {k}")
                            else:
                                still_failed[k] = v
                        failed = still_failed
                if failed:
                    print(f"  [Railway] Could not set via API or CLI — paste into Railway dashboard:")
                    print(f"  [Railway] https://railway.app/project/{r_proj_id}")
                    for k, v in failed.items():
                        print(f"  {k}={v}")
                else:
                    print("  [Railway] CORS + ENVIRONMENT set.")
        except Exception as e:
            print(f"  [Railway] WARNING: could not set CORS/ENVIRONMENT: {e}")

    # ── Step 4b: Update Auth0 callback URLs with Vercel frontend URL ──────────
    if final_frontend_url and vercel_succeeded:
        app_name    = repo_path.name
        mgmt_token  = os.getenv("AUTH0_MGMT_TOKEN")
        keys_file   = Path.home() / "Downloads" / "ACCESSKEYS" / f"auth0_{app_name}.env"
        if mgmt_token and keys_file.exists():
            auth0_vars = {}
            for line in keys_file.read_text().splitlines():
                if "=" in line and not line.startswith("#"):
                    k, _, v = line.partition("=")
                    auth0_vars[k.strip()] = v.strip()
            auth0_domain    = auth0_vars.get("AUTH0_DOMAIN")
            auth0_client_id = auth0_vars.get("AUTH0_CLIENT_ID")
            if auth0_domain and auth0_client_id:
                print("\n  [Auth0] Updating callback URLs with Vercel frontend URL...")
                try:
                    update_spa_urls(auth0_domain, mgmt_token, auth0_client_id, final_frontend_url)
                except Exception as e:
                    print(f"  [Auth0] WARNING: URL update failed — {e}")
                    print(f"  [Auth0] Run manually: python deploy/auth0_setup.py --update-urls ...")
        elif keys_file.exists() and not mgmt_token:
            print(f"\n  [Auth0] Skipping URL update — set AUTH0_MGMT_TOKEN env var to enable")

    # ── Print summary ────────────────────────────────────────
    print_summary(
        github_url,
        railway_result,
        vercel_result,
        backend_skipped=args.frontend_only,
        railway_cfg=railway_cfg,
        vercel_cfg=vercel_cfg,
        backend_url=final_backend_url,
        frontend_url=final_frontend_url,
    )

    # Persist state files only when deploy flow succeeds
    railway_success = args.frontend_only or (railway_result and railway_result.get("success"))
    vercel_success = args.backend_only or (vercel_result and vercel_result.get("success"))
    overall_success = railway_success and vercel_success
    if overall_success:
        persist_deploy_state_if_changed(repo_path, args.branch)

    # Exit code: 0 = success, 1 = at least one failure
    if railway_result and not railway_result.get("success"):
        sys.exit(1)
    if vercel_result and not vercel_result.get("success"):
        sys.exit(1)


if __name__ == "__main__":
    main()
