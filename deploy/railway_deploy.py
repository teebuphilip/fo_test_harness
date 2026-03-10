#!/usr/bin/env python3
"""
railway_deploy.py - Deploy backend to Railway via REST API
===========================================================

NO CLI. NO GUI. Pure Python + requests.

Railway GraphQL API: https://backboard.railway.app/graphql/v2

WHAT IT DOES:
    1. Creates a new Railway project (or links to existing)
    2. Adds PostgreSQL plugin
    3. Sets all environment variables from .env file
    4. Triggers deploy from GitHub repo
    5. Polls until deploy is live
    6. Returns the service URL

CALLED BY: pipeline_deploy.py (do not run directly unless testing)
"""

import json
import time
import sys
import os
import requests
from pathlib import Path

# ============================================================
# RAILWAY GRAPHQL API WRAPPER
# WHY: Railway uses GraphQL. These are the only queries we need.
# ============================================================

RAILWAY_API = "https://backboard.railway.app/graphql/v2"


class RailwayAPI:
    """
    Thin wrapper around Railway's GraphQL API.
    All methods return (success: bool, data: dict).
    """

    def __init__(self, token: str):
        self.token = token
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        })

    def _query(self, query: str, variables: dict = None) -> dict:
        """Run a GraphQL query/mutation. Returns response data or raises."""
        payload = {"query": query}
        if variables:
            payload["variables"] = variables

        resp = self.session.post(RAILWAY_API, json=payload, timeout=30)
        if resp.status_code >= 400:
            # Include body for faster diagnosis of GraphQL shape/auth issues.
            raise Exception(f"Railway HTTP {resp.status_code}: {resp.text}")
        data = resp.json()

        if "errors" in data:
            raise Exception(f"Railway API error: {data['errors']}")

        return data.get("data", {})

    def whoami(self) -> dict:
        """Verify token is valid. Returns user info."""
        q = """
        query {
            me {
                id
                email
                name
                workspaces {
                    id
                    name
                }
            }
        }
        """
        return self._query(q)

    def get_workspace_id(self) -> str:
        """Get the first workspace ID for this account (required for projectCreate)."""
        try:
            me = self.whoami()
            workspaces = me.get("me", {}).get("workspaces", [])
            if workspaces:
                return workspaces[0]["id"]
        except Exception:
            pass
        return None

    def list_projects(self) -> list:
        """List all projects for this account."""
        q = """
        query {
            projects {
                edges {
                    node {
                        id
                        name
                        services {
                            edges {
                                node {
                                    id
                                    name
                                }
                            }
                        }
                    }
                }
            }
        }
        """
        data = self._query(q)
        return [e["node"] for e in data.get("projects", {}).get("edges", [])]

    def create_project(self, name: str, workspace_id: str = None) -> dict:
        """Create a new Railway project. Returns project dict."""
        q = """
        mutation CreateProject($input: ProjectCreateInput!) {
            projectCreate(input: $input) {
                id
                name
            }
        }
        """
        inp = {"name": name}
        if workspace_id:
            inp["workspaceId"] = workspace_id
        data = self._query(q, {"input": inp})
        return data["projectCreate"]

    def create_service(self, project_id: str, name: str, repo_url: str = None) -> dict:
        """Create a service inside a project."""
        q = """
        mutation CreateService($input: ServiceCreateInput!) {
            serviceCreate(input: $input) {
                id
                name
            }
        }
        """
        source = {}
        if repo_url:
            source["repo"] = repo_url

        variables = {
            "input": {
                "name": name,
                "projectId": project_id,
                "source": source if source else None,
            }
        }
        data = self._query(q, variables)
        return data["serviceCreate"]

    def add_plugin(self, project_id: str, plugin_type: str = "postgresql") -> dict:
        """Add a plugin (postgresql, redis, etc.) to a project."""
        q = """
        mutation PluginCreate($input: PluginCreateInput!) {
            pluginCreate(input: $input) {
                id
                name
                status
            }
        }
        """
        variables = {
            "input": {
                "projectId": project_id,
                "name": plugin_type,
            }
        }
        data = self._query(q, variables)
        return data["pluginCreate"]

    def set_variable(self, project_id: str, service_id: str, name: str, value: str, environment_id: str = None) -> bool:
        """Set a single environment variable on a service. Tries bulk upsert first, falls back to single."""
        # Try variableCollectionUpsert (bulk) — avoids GitHub repo validation in some token types
        if environment_id:
            q_bulk = """
            mutation VariableCollectionUpsert($input: VariableCollectionUpsertInput!) {
                variableCollectionUpsert(input: $input)
            }
            """
            try:
                self._query(q_bulk, {
                    "input": {
                        "projectId": project_id,
                        "serviceId": service_id,
                        "environmentId": environment_id,
                        "variables": {name: value},
                    }
                })
                return True
            except Exception:
                pass  # fall through to single upsert

        q = """
        mutation VariableUpsert($input: VariableUpsertInput!) {
            variableUpsert(input: $input)
        }
        """
        self._query(q, {
            "input": {
                "projectId": project_id,
                "serviceId": service_id,
                "environmentId": environment_id,
                "name": name,
                "value": value,
            }
        })
        return True

    def set_root_directory(self, service_id: str, root_directory: str) -> bool:
        """Set the root directory for a service (e.g. 'business/backend')."""
        q = """
        mutation ServiceUpdate($id: String!, $input: ServiceUpdateInput!) {
            serviceUpdate(id: $id, input: $input) {
                id
            }
        }
        """
        self._query(q, {"id": service_id, "input": {"rootDirectory": root_directory}})
        return True

    def get_environment_id(self, project_id: str) -> str:
        """
        Resolve a deployable environment ID for a project.
        Railway schema varies by account/workspace, so try a couple of shapes.
        """
        candidates = [
            (
                """
                query GetProjectEnvironments($id: String!) {
                    project(id: $id) {
                        environments {
                            edges { node { id name } }
                        }
                    }
                }
                """,
                lambda d: [
                    e.get("node", {}) for e in
                    d.get("project", {}).get("environments", {}).get("edges", [])
                ],
            ),
            (
                """
                query GetProjectEnvironmentsAlt($id: String!) {
                    project(id: $id) {
                        environments {
                            id
                            name
                        }
                    }
                }
                """,
                lambda d: d.get("project", {}).get("environments", []),
            ),
        ]

        for query, extractor in candidates:
            try:
                data = self._query(query, {"id": project_id})
                envs = extractor(data) or []
                # Prefer Production, then first available.
                for env in envs:
                    if (env.get("name") or "").lower() == "production":
                        return env.get("id")
                if envs:
                    return envs[0].get("id")
            except Exception:
                continue
        return None

    def trigger_deploy(self, service_id: str, environment_id: str = None, project_id: str = None) -> dict:
        """
        Trigger a redeployment of a service.
        Uses environment-aware mutation and schema fallbacks.
        """
        env_id = environment_id
        if not env_id and project_id:
            env_id = self.get_environment_id(project_id)

        # Attempt 1: explicit environment ID (most common in current schema)
        if env_id:
            q_env = """
            mutation ServiceInstanceRedeploy($serviceId: String!, $environmentId: String!) {
                serviceInstanceRedeploy(serviceId: $serviceId, environmentId: $environmentId)
            }
            """
            self._query(q_env, {"serviceId": service_id, "environmentId": env_id})
            return {"triggered": True, "environment_id": env_id}

        # Attempt 2: service-only fallback (older schema variants)
        q_service_only = """
        mutation ServiceInstanceRedeploy($serviceId: String!) {
            serviceInstanceRedeploy(serviceId: $serviceId)
        }
        """
        self._query(q_service_only, {"serviceId": service_id})
        return {"triggered": True, "environment_id": None}

    def get_service_url(self, project_id: str, service_id: str) -> str:
        """
        Get a reachable public URL for a service.

        Railway GraphQL schema evolves; `service.domains` is not available in some
        versions. Prefer recent deployment URLs, which are available from
        `deployments` and already used elsewhere.
        """
        deployments = self.get_deployments(service_id)
        for dep in deployments:
            url = dep.get("url")
            if url:
                return url
        return None

    def get_deployments(self, service_id: str) -> list:
        """Get recent deployments for a service."""
        q = """
        query GetDeployments($serviceId: String!) {
            deployments(
                first: 5,
                input: { serviceId: $serviceId }
            ) {
                edges {
                    node {
                        id
                        status
                        createdAt
                        url
                    }
                }
            }
        }
        """
        data = self._query(q, {"serviceId": service_id})
        return [e["node"] for e in data.get("deployments", {}).get("edges", [])]


# ============================================================
# PLACEHOLDER DETECTION
# WHY: Don't push unfilled placeholder values to Railway
# ============================================================

PLACEHOLDER_VALUES = {
    "your_token", "your_key", "your_secret", "xxxx", "your_client_id",
    "your_client_secret", "your_username", "your_password", "your_zone_id",
    "your_id", "your_mgmt_client_id", "your_mgmt_client_secret",
    "your_bot_token", "your_master_key", "your_mailerlite_token",
    "123456789", "987654321", "your_project_name", "",
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


# ============================================================
# MAIN DEPLOY FUNCTION
# ============================================================

def deploy_backend(
    token: str,
    repo_path: Path,
    github_repo_url: str,
    project_name: str = None,
    add_postgres: bool = True,
    env_file: Path = None,
    railway_config: dict = None,
) -> dict:
    """
    Deploy backend repo to Railway via API.

    Args:
        token: Railway API token
        repo_path: Local path to the repo (for reading .env)
        github_repo_url: GitHub repo URL (Railway pulls from here)
        project_name: Railway project name (defaults to repo dir name)
        add_postgres: Whether to add PostgreSQL plugin
        env_file: Path to .env file (defaults to repo_path/.env)
        railway_config: Existing railway.json config (to reuse project)

    Returns:
        {
            "success": True,
            "project_id": "...",
            "service_id": "...",
            "url": "https://...",
        }
    """
    api = RailwayAPI(token)
    project_name = project_name or repo_path.name.lower().replace("_", "-")
    # Railway rejects long names — truncate at word boundary before 40 chars
    if len(project_name) > 40:
        truncated = project_name[:40]
        last_hyphen = truncated.rfind("-")
        project_name = truncated[:last_hyphen] if last_hyphen > 0 else truncated
    env_file = env_file or (repo_path / ".env")

    # ── Step 1: Verify token (non-blocking) ─────────────────
    # Some Railway token types cannot access `me` but can still deploy.
    print("  [Railway] Verifying token...")
    try:
        me = api.whoami()
        user = me.get("me", {})
        print(f"  [Railway] Authenticated as: {user.get('email', 'unknown')}")
    except Exception as e:
        print(f"  [Railway] whoami check skipped: {e}")
        print("  [Railway] Continuing with deploy operations...")

    # ── Step 2: Create or reuse project ────────────────────
    project_id = railway_config.get("project_id") if railway_config else None
    service_id = railway_config.get("service_id") if railway_config else None

    if not project_id:
        print(f"  [Railway] Creating project: {project_name}")
        workspace_id = api.get_workspace_id()
        if workspace_id:
            print(f"  [Railway] Using workspace: {workspace_id}")
        project = api.create_project(project_name, workspace_id=workspace_id)
        project_id = project["id"]
        print(f"  [Railway] Project created: {project_id}")
    else:
        print(f"  [Railway] Reusing project: {project_id}")

    # ── Step 3: Create or reuse service ────────────────────
    if not service_id:
        print(f"  [Railway] Creating service: backend")
        service = api.create_service(
            project_id=project_id,
            name="backend",
            repo_url=github_repo_url,
        )
        service_id = service["id"]
        print(f"  [Railway] Service created: {service_id}")
    else:
        print(f"  [Railway] Reusing service: {service_id}")

    # ── Step 4: Add PostgreSQL ──────────────────────────────
    if add_postgres and not (railway_config or {}).get("postgres_added"):
        print("  [Railway] Adding PostgreSQL...")
        try:
            plugin = api.add_plugin(project_id, "postgresql")
            print(f"  [Railway] PostgreSQL added: {plugin.get('id')}")
            print("  [Railway] DATABASE_URL will be auto-injected")
        except Exception as e:
            print(f"  [Railway] PostgreSQL note: {e} (may already exist)")

    # ── Step 5: Push environment variables ─────────────────
    env_vars = parse_env_file(env_file)
    if env_vars:
        print(f"  [Railway] Pushing {len(env_vars)} environment variables...")
        env_id = (railway_config or {}).get("environment_id") or api.get_environment_id(project_id)
        if not env_id:
            print("  [Railway] WARNING: could not resolve environment_id — vars may not be set")
        failed_vars = {}
        for key, value in env_vars.items():
            try:
                api.set_variable(project_id, service_id, key, value, environment_id=env_id)
            except Exception:
                failed_vars[key] = value

        # Fallback: try Railway CLI for any vars that failed via API
        if failed_vars:
            import subprocess, shutil
            cli = shutil.which("railway")
            if cli:
                print(f"  [Railway] API failed — trying Railway CLI for {len(failed_vars)} var(s)...")
                cli_failed = {}
                for key, value in failed_vars.items():
                    try:
                        result = subprocess.run(
                            [cli, "variables", "--set", f"{key}={value}",
                             "--project", project_id, "--service", service_id],
                            capture_output=True, text=True, timeout=30,
                            env={**__import__("os").environ, "RAILWAY_TOKEN": api.token}
                        )
                        if result.returncode != 0:
                            cli_failed[key] = value
                        else:
                            print(f"  [Railway] CLI set: {key}")
                    except Exception:
                        cli_failed[key] = value
                failed_vars = cli_failed

        if failed_vars:
            dashboard_url = f"https://railway.app/project/{project_id}"
            print(f"\n  [Railway] Could not set {len(failed_vars)} var(s) — paste into Railway dashboard:")
            print(f"  [Railway] {dashboard_url}")
            print(f"  {'─'*56}")
            for k, v in failed_vars.items():
                print(f"  {k}={v}")
            print(f"  {'─'*56}\n")
        else:
            print(f"  [Railway] Variables set.")
    else:
        print("  [Railway] No .env file or no filled variables - skipping")

    # ── Step 6: Trigger deploy ──────────────────────────────
    print("  [Railway] Triggering deploy...")
    try:
        redeploy = api.trigger_deploy(service_id, project_id=project_id)
        if redeploy.get("environment_id"):
            print(f"  [Railway] Deploy triggered in environment: {redeploy.get('environment_id')}")
    except Exception as e:
        # Some Railway accounts/workspaces reject explicit redeploy mutation
        # even when service creation/linking succeeds. Continue and poll URL.
        print(f"  [Railway] trigger_deploy skipped: {e}")
        print("  [Railway] Continuing to poll service URL...")

    # ── Step 7: Poll for URL ────────────────────────────────
    print("  [Railway] Waiting for deploy to come up", end="", flush=True)
    url = None
    for _ in range(24):  # 2 minutes max
        time.sleep(5)
        print(".", end="", flush=True)
        try:
            url = api.get_service_url(project_id, service_id)
            if url:
                break
        except Exception:
            pass
    print()

    if not url:
        print("  [Railway] Deploy triggered but URL not available yet.")
        print("  [Railway] Check Railway dashboard for status.")

    return {
        "success": True,
        "project_id": project_id,
        "service_id": service_id,
        "url": f"https://{url}" if url else None,
        "postgres_added": True,
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Deploy backend to Railway")
    parser.add_argument("--repo", required=True, help="Path to repo (for .env)")
    parser.add_argument("--github-url", required=True, help="GitHub repo URL")
    parser.add_argument("--project-name", default=None, help="Railway project name")
    parser.add_argument("--env-file", default=None, help="Path to .env (optional)")
    parser.add_argument("--add-postgres", action="store_true", help="Add PostgreSQL plugin")
    args = parser.parse_args()

    token = os.getenv("RAILWAY_TOKEN")
    if not token:
        print("Error: RAILWAY_TOKEN not set")
        sys.exit(1)

    repo_path = Path(args.repo).resolve()
    env_file = Path(args.env_file).resolve() if args.env_file else None

    result = deploy_backend(
        token=token,
        repo_path=repo_path,
        github_repo_url=args.github_url,
        project_name=args.project_name,
        add_postgres=args.add_postgres,
        env_file=env_file,
        railway_config=None,
    )
    print(json.dumps(result, indent=2))
