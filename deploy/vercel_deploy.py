#!/usr/bin/env python3
"""
vercel_deploy.py - Deploy frontend to Vercel via REST API
==========================================================

NO CLI. NO GUI. Pure Python + requests.

Vercel REST API: https://api.vercel.com

WHAT IT DOES:
    1. Creates a new Vercel project (or links to existing)
    2. Sets environment variables from .env file
    3. Triggers deploy from GitHub repo
    4. Polls until deploy is live
    5. Returns the deployment URL

CALLED BY: pipeline_deploy.py (do not run directly unless testing)
"""

import json
import time
import sys
import requests
from pathlib import Path

# ============================================================
# VERCEL REST API WRAPPER
# WHY: Vercel has a proper REST API. No CLI needed.
# ============================================================

VERCEL_API = "https://api.vercel.com"


class VercelAPI:
    """
    Thin wrapper around Vercel's REST API.
    Docs: https://vercel.com/docs/rest-api
    """

    def __init__(self, token: str, team_id: str = None):
        self.token = token
        self.team_id = team_id
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        })

    def _params(self, extra: dict = None) -> dict:
        """Add teamId to params if set."""
        params = {}
        if self.team_id:
            params["teamId"] = self.team_id
        if extra:
            params.update(extra)
        return params

    def whoami(self) -> dict:
        """Verify token. Returns user/team info."""
        resp = self.session.get(f"{VERCEL_API}/v2/user", params=self._params())
        resp.raise_for_status()
        return resp.json()

    def list_projects(self) -> list:
        """List existing projects."""
        resp = self.session.get(f"{VERCEL_API}/v9/projects", params=self._params())
        resp.raise_for_status()
        return resp.json().get("projects", [])

    def get_project(self, name_or_id: str) -> dict:
        """Get a project by name or ID. Returns None if not found."""
        resp = self.session.get(
            f"{VERCEL_API}/v9/projects/{name_or_id}",
            params=self._params()
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()

    def create_project(
        self,
        name: str,
        github_repo: str,
        framework: str = "create-react-app",
        root_directory: str = None,
        build_command: str = None,
        output_directory: str = None,
    ) -> dict:
        """
        Create a new Vercel project linked to a GitHub repo.

        Args:
            name: Project name (slug, lowercase, hyphens ok)
            github_repo: GitHub repo in format "username/repo-name"
            framework: Vercel framework preset
                       Options: create-react-app, vite, nextjs, gatsby, vue, nuxt, etc.
            root_directory: Subdirectory with frontend code (e.g. "saas-boilerplate/frontend")
            build_command: Override default (e.g. "npm run build")
            output_directory: Override default (e.g. "dist" for Vite, "build" for CRA)
        """
        payload = {
            "name": name,
            "framework": framework,
            "gitRepository": {
                "type": "github",
                "repo": github_repo,
            },
        }
        if root_directory:
            payload["rootDirectory"] = root_directory
        if build_command:
            payload["buildCommand"] = build_command
        if output_directory:
            payload["outputDirectory"] = output_directory

        resp = self.session.post(
            f"{VERCEL_API}/v9/projects",
            json=payload,
            params=self._params()
        )
        resp.raise_for_status()
        return resp.json()

    def update_project(
        self,
        project_id: str,
        framework: str = None,
        root_directory: str = None,
        build_command: str = None,
        output_directory: str = None,
    ) -> dict:
        """
        Update an existing Vercel project (e.g., rootDirectory/outputDirectory).
        """
        payload = {}
        if framework:
            payload["framework"] = framework
        if root_directory is not None:
            payload["rootDirectory"] = root_directory
        if build_command:
            payload["buildCommand"] = build_command
        if output_directory:
            payload["outputDirectory"] = output_directory

        if not payload:
            return {"skipped": True}

        resp = self.session.patch(
            f"{VERCEL_API}/v9/projects/{project_id}",
            json=payload,
            params=self._params()
        )
        resp.raise_for_status()
        return resp.json()

    def set_env_var(
        self,
        project_id: str,
        key: str,
        value: str,
        target: list = None,
    ) -> dict:
        """
        Upsert an environment variable on a Vercel project.
        Creates if new, patches existing if already present (handles 400/409).

        Args:
            target: List of environments: ["production", "preview", "development"]
                    Defaults to all three.
        """
        target = target or ["production", "preview", "development"]
        payload = {
            "key": key,
            "value": value,
            "type": "plain",
            "target": target,
        }
        resp = self.session.post(
            f"{VERCEL_API}/v10/projects/{project_id}/env",
            json=payload,
            params=self._params()
        )
        if resp.status_code in (200, 201):
            return resp.json()
        # 400 or 409 = already exists — fetch the env var ID and PATCH it
        if resp.status_code in (400, 409):
            existing = self.session.get(
                f"{VERCEL_API}/v9/projects/{project_id}/env",
                params=self._params()
            )
            if existing.ok:
                for env in existing.json().get("envs", []):
                    if env.get("key") == key:
                        env_id = env["id"]
                        patch = self.session.patch(
                            f"{VERCEL_API}/v9/projects/{project_id}/env/{env_id}",
                            json=payload,
                            params=self._params()
                        )
                        return patch.json() if patch.ok else {"skipped": True}
            return {"skipped": True}
        resp.raise_for_status()

    def trigger_deploy(self, project_name: str, github_repo: str, branch: str = "main") -> dict:
        """
        Trigger a new deployment.

        Args:
            project_name: Vercel project name
            github_repo: GitHub repo "username/repo"
            branch: Branch to deploy (default: main)
        """
        owner, repo = github_repo.split("/", 1)
        payload = {
            "name": project_name,
            "gitSource": {
                "type": "github",
                "repoId": None,      # Vercel resolves this from org/repo
                "ref": branch,
                "repo": repo,
                "org": owner,
            },
        }
        resp = self.session.post(
            f"{VERCEL_API}/v13/deployments",
            json=payload,
            params=self._params()
        )
        if resp.status_code >= 400:
            raise Exception(f"Vercel deploy API {resp.status_code}: {resp.text}")
        return resp.json()

    def get_deployment(self, deployment_id: str) -> dict:
        """Get deployment status."""
        resp = self.session.get(
            f"{VERCEL_API}/v13/deployments/{deployment_id}",
            params=self._params()
        )
        resp.raise_for_status()
        return resp.json()

    def get_deployment_events(self, deployment_id: str, limit: int = 50) -> list:
        """Fetch deployment events/log chunks when available."""
        resp = self.session.get(
            f"{VERCEL_API}/v3/deployments/{deployment_id}/events",
            params=self._params({"limit": limit})
        )
        if resp.status_code >= 400:
            return []
        data = resp.json()
        return data if isinstance(data, list) else data.get("events", [])

    def get_latest_deployment(self, project_id: str) -> dict:
        """Get the most recent deployment for a project."""
        resp = self.session.get(
            f"{VERCEL_API}/v6/deployments",
            params=self._params({"projectId": project_id, "limit": 1})
        )
        resp.raise_for_status()
        deployments = resp.json().get("deployments", [])
        return deployments[0] if deployments else None


# ============================================================
# PLACEHOLDER DETECTION (same as railway_deploy.py)
# ============================================================

PLACEHOLDER_VALUES = {
    "your_token", "your_key", "your_secret", "xxxx", "your_client_id",
    "your_client_secret", "your_username", "your_password", "your_zone_id",
    "your_id", "your_mgmt_client_id", "your_mgmt_client_secret",
    "your_bot_token", "your_master_key", "your_mailerlite_token",
    "123456789", "987654321", "",
}


def is_placeholder(value: str) -> bool:
    return value.strip().lower() in PLACEHOLDER_VALUES


def parse_env_file(env_path: Path) -> dict:
    """Parse .env file into dict, skipping comments and placeholders."""
    vars = {}
    if not env_path.exists():
        return vars

    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if not is_placeholder(value):
                vars[key] = value

    return vars


def load_auth0_frontend_env(repo_path: Path) -> dict:
    """
    Load Auth0 frontend env vars from ~/Downloads/ACCESSKEYS/auth0_<app>.env.
    Returns a dict with REACT_APP_AUTH0_DOMAIN and REACT_APP_AUTH0_CLIENT_ID if present.
    """
    app_name = repo_path.name
    keys_file = Path.home() / "Downloads" / "ACCESSKEYS" / f"auth0_{app_name}.env"
    if not keys_file.exists():
        return {}

    raw = {}
    for line in keys_file.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, _, v = line.partition("=")
            raw[k.strip()] = v.strip()

    env = {}
    if raw.get("AUTH0_DOMAIN"):
        env["REACT_APP_AUTH0_DOMAIN"] = raw["AUTH0_DOMAIN"]
    if raw.get("AUTH0_CLIENT_ID"):
        env["REACT_APP_AUTH0_CLIENT_ID"] = raw["AUTH0_CLIENT_ID"]
    return env


# ============================================================
# MAIN DEPLOY FUNCTION
# ============================================================

def deploy_frontend(
    token: str,
    repo_path: Path,
    github_repo: str,
    project_name: str = None,
    framework: str = "create-react-app",
    root_directory: str = "frontend",
    output_directory: str = "build",
    branch: str = "main",
    env_file: Path = None,
    vercel_config: dict = None,
    team_id: str = None,
    backend_url: str = None,
) -> dict:
    """
    Deploy frontend to Vercel via REST API.

    Args:
        token: Vercel API token
        repo_path: Local repo path (for reading .env)
        github_repo: GitHub repo "username/repo-name"
        project_name: Vercel project name
        framework: Framework preset (create-react-app, vite, nextjs, etc.)
        root_directory: Where frontend code lives in the repo
        output_directory: Build output dir ("build" for CRA, "dist" for Vite)
        branch: Git branch to deploy
        env_file: Path to frontend .env file
        vercel_config: Existing vercel.json config (to reuse project)
        team_id: Vercel team ID (blank for personal accounts)
        backend_url: Railway backend URL - injected as REACT_APP_API_URL

    Returns:
        {
            "success": True,
            "project_id": "...",
            "deployment_id": "...",
            "url": "https://...",
        }
    """
    api = VercelAPI(token, team_id=team_id or None)
    project_name = project_name or (repo_path.name.lower().replace("_", "-") + "-frontend")
    env_file = env_file or (repo_path / "frontend" / ".env")

    # ── Step 1: Verify token ────────────────────────────────
    print("  [Vercel] Verifying token...")
    me = api.whoami()
    user = me.get("user", {})
    print(f"  [Vercel] Authenticated as: {user.get('email', 'unknown')}")

    # ── Step 2: Create or reuse project ────────────────────
    project_id = (vercel_config or {}).get("project_id")

    if not project_id:
        # Check if project already exists
        print(f"  [Vercel] Checking for existing project: {project_name}")
        existing = api.get_project(project_name)

        if existing:
            project_id = existing["id"]
            print(f"  [Vercel] Reusing existing project: {project_id}")
        else:
            print(f"  [Vercel] Creating project: {project_name}")
            project = api.create_project(
                name=project_name,
                github_repo=github_repo,
                framework=framework,
                root_directory=root_directory,
                output_directory=output_directory,
            )
            project_id = project["id"]
            print(f"  [Vercel] Project created: {project_id}")
    else:
        print(f"  [Vercel] Reusing project from config: {project_id}")

    # ── Step 2b: Ensure project settings match desired config ─────────
    try:
        api.update_project(
            project_id=project_id,
            framework=framework,
            root_directory=root_directory,
            output_directory=output_directory,
        )
        print(f"  [Vercel] Project settings updated (rootDirectory={root_directory})")
    except Exception as e:
        print(f"  [Vercel] WARNING: could not update project settings: {e}")

    # ── Step 3: Set environment variables ──────────────────
    env_vars = parse_env_file(env_file)

    # Disable CI=true so ESLint warnings don't fail the build
    env_vars["CI"] = "false"

    # Inject Auth0 frontend env vars if not provided in .env
    if "REACT_APP_AUTH0_DOMAIN" not in env_vars or "REACT_APP_AUTH0_CLIENT_ID" not in env_vars:
        auth0_env = load_auth0_frontend_env(repo_path)
        for k, v in auth0_env.items():
            env_vars.setdefault(k, v)

    # Inject backend URL so frontend knows where the API is
    if backend_url:
        env_vars["REACT_APP_API_URL"] = backend_url
        env_vars["VITE_API_URL"] = backend_url  # For Vite projects
        print(f"  [Vercel] Injecting backend URL: {backend_url}")

    if env_vars:
        print(f"  [Vercel] Setting {len(env_vars)} environment variables...")
        for key, value in env_vars.items():
            api.set_env_var(project_id, key, value)
        print("  [Vercel] Variables set.")
    else:
        print("  [Vercel] No env vars to set - skipping")

    # ── Step 4: Trigger deploy ──────────────────────────────
    print(f"  [Vercel] Triggering deploy from branch: {branch}")
    deployment_id = None
    try:
        deployment = api.trigger_deploy(project_name, github_repo, branch)
        deployment_id = deployment.get("id")
        print(f"  [Vercel] Deploy triggered: {deployment_id}")
    except Exception as e:
        print(f"  [Vercel] trigger_deploy skipped: {e}")
        print("  [Vercel] Falling back to latest deployment polling...")

    # ── Step 5: Poll for completion ─────────────────────────
    print("  [Vercel] Waiting for build to complete", end="", flush=True)
    url = None
    final_status = None

    for _ in range(36):  # 3 minutes max (5s intervals)
        time.sleep(5)
        print(".", end="", flush=True)

        try:
            if deployment_id:
                status = api.get_deployment(deployment_id)
            else:
                status = api.get_latest_deployment(project_id) or {}
            state = status.get("readyState") or status.get("status")
            final_status = state

            if state == "READY":
                url = status.get("url")
                break
            elif state in ("ERROR", "CANCELED"):
                print(f"\n  [Vercel] Deploy failed: {state}")
                reason = (
                    status.get("errorMessage")
                    or status.get("readyStateReason")
                    or status.get("errorCode")
                )
                if reason:
                    print(f"  [Vercel] Reason: {reason}")
                if deployment_id:
                    events = api.get_deployment_events(deployment_id, limit=80)
                    if events:
                        print("  [Vercel] Last deployment events:")
                        for ev in events[-30:]:
                            text = ev.get("text") or ev.get("payload", {}).get("text") or ev.get("type")
                            if text:
                                print(f"    - {str(text)[:300]}")
                print(f"  [Vercel] Check: https://vercel.com/dashboard")
                return {
                    "success": False,
                    "status": state,
                    "deployment_id": deployment_id,
                    "reason": reason,
                }
        except Exception:
            pass
    print()

    if not url:
        print(f"  [Vercel] Deploy status: {final_status}")
        print("  [Vercel] URL not available yet - check Vercel dashboard")

    return {
        "success": True,
        "project_id": project_id,
        "deployment_id": deployment_id,
        "url": f"https://{url}" if url and not url.startswith("http") else url,
    }


if __name__ == "__main__":
    import argparse
    import os

    parser = argparse.ArgumentParser(description="Deploy frontend to Vercel")
    parser.add_argument("--repo", required=True, help="Path to repo (for .env)")
    parser.add_argument("--github-repo", required=True, help="GitHub repo name (owner/repo)")
    parser.add_argument("--project-name", default=None, help="Vercel project name")
    parser.add_argument("--framework", default="create-react-app")
    parser.add_argument("--root-dir", default="saas-boilerplate/frontend")
    parser.add_argument("--output-dir", default="build")
    parser.add_argument("--branch", default="main")
    parser.add_argument("--env-file", default=None)
    parser.add_argument("--backend-url", default=None)
    args = parser.parse_args()

    token = os.getenv("VERCEL_TOKEN")
    if not token:
        print("Error: VERCEL_TOKEN not set")
        sys.exit(1)

    repo_path = Path(args.repo).resolve()
    env_file = Path(args.env_file).resolve() if args.env_file else None

    result = deploy_frontend(
        token=token,
        repo_path=repo_path,
        github_repo=args.github_repo,
        project_name=args.project_name,
        framework=args.framework,
        root_directory=args.root_dir,
        output_directory=args.output_dir,
        branch=args.branch,
        env_file=env_file,
        vercel_config=None,
        team_id=os.getenv("VERCEL_TEAM_ID"),
        backend_url=args.backend_url,
    )
    print(json.dumps(result, indent=2))
