#!/usr/bin/env python3
"""
pipeline_prepare.py
===================

Runs only the PREP stages from pipeline_deploy.py:
  1) AI config generation/update (railway.deploy.json + vercel.deploy.json)
  2) GitHub push

This does NOT run Railway or Vercel deploy.
"""

import argparse
import os
import sys
from pathlib import Path

# Reuse existing deploy pipeline logic (single source of truth).
sys.path.insert(0, str(Path(__file__).parent))
from pipeline_deploy import (
    DEFAULT_CLAUDE_MODEL,
    DEFAULT_OPENAI_MODEL,
    RAILWAY_STATE_FILE,
    VERCEL_STATE_FILE,
    _base_project_name,
    generate_deploy_configs,
    load_config,
    push_to_github,
    read_railway_config,
    read_vercel_config,
    sanitize_vercel_runtime_config,
    write_config_back,
)


def main():
    parser = argparse.ArgumentParser(
        description="Run AI config generation + Git push only (no deploy)."
    )
    parser.add_argument("--repo", required=True, help="Path to repo")
    parser.add_argument(
        "--new-project",
        action="store_true",
        help="Treat as new project (create GitHub repo, generate fresh deploy state).",
    )
    parser.add_argument(
        "--provider",
        choices=["chatgpt", "claude"],
        default="chatgpt",
        help="AI provider for config generation (default: chatgpt)",
    )
    parser.add_argument(
        "--openai-model",
        default=DEFAULT_OPENAI_MODEL,
        help="OpenAI model for config generation",
    )
    parser.add_argument(
        "--claude-model",
        default=DEFAULT_CLAUDE_MODEL,
        help="Claude model for config generation",
    )
    parser.add_argument(
        "--branch",
        default="main",
        help="Branch to push (default: main)",
    )
    parser.add_argument(
        "--repo-name",
        default=None,
        help="Optional GitHub repo name override (default: derived from local repo dir).",
    )
    parser.add_argument(
        "--regenerate-configs",
        action="store_true",
        help="Force AI regeneration even if deploy state files already exist.",
    )
    parser.add_argument(
        "--configs-only",
        action="store_true",
        help="Only generate/update railway.deploy.json and vercel.deploy.json; skip Git push.",
    )
    target_group = parser.add_mutually_exclusive_group()
    target_group.add_argument(
        "--railway-only",
        action="store_true",
        help="Generate/update only railway.deploy.json.",
    )
    target_group.add_argument(
        "--vercel-only",
        action="store_true",
        help="Generate/update only vercel.deploy.json.",
    )
    args = parser.parse_args()

    repo_path = Path(args.repo).expanduser().resolve()
    if not repo_path.exists():
        print(f"[ERROR] Repo path does not exist: {repo_path}")
        sys.exit(1)

    # Provider-specific API key checks for AI config generation
    if args.provider == "chatgpt" and not os.getenv("OPENAI_API_KEY"):
        print("[ERROR] OPENAI_API_KEY not set")
        sys.exit(1)
    if args.provider == "claude" and not os.getenv("ANTHROPIC_API_KEY"):
        print("[ERROR] ANTHROPIC_API_KEY not set")
        sys.exit(1)

    github_token = ""
    github_username = ""
    if not args.configs_only:
        print("\nLoading credentials from environment variables")
        config = load_config()
        github_token = config["github"]["token"]
        github_username = config["github"]["username"]

    # Keep runtime vercel.json schema-safe
    sanitize_vercel_runtime_config(repo_path)

    # Read deploy-state files
    railway_cfg = {} if args.new_project else read_railway_config(repo_path)
    vercel_cfg = {} if args.new_project else read_vercel_config(repo_path)

    # Canonical naming
    project_base_name = _base_project_name(repo_path, railway_cfg)
    railway_cfg["project"] = project_base_name
    vercel_cfg["project"] = f"{project_base_name}-frontend"
    print(f"  [prepare] {RAILWAY_STATE_FILE}: project={railway_cfg.get('project', 'unnamed')}")
    print(f"  [prepare] {VERCEL_STATE_FILE}: project={vercel_cfg.get('project', 'unnamed')}")

    update_railway = not args.vercel_only
    update_vercel = not args.railway_only
    target_label = "railway only" if args.railway_only else ("vercel only" if args.vercel_only else "railway + vercel")

    # STEP 0: AI generation/update
    railway_cfg_path = repo_path / RAILWAY_STATE_FILE
    vercel_cfg_path = repo_path / VERCEL_STATE_FILE
    has_existing = railway_cfg_path.exists() and vercel_cfg_path.exists()

    print(f"\n{'='*60}")
    print(f"STEP 0/2: Generate deploy config(s) via AI ({target_label})")
    print(f"{'='*60}")
    if has_existing and not args.regenerate_configs:
        print("  [prepare] Existing config files found - skipping AI regeneration")
    else:
        railway_ai_cfg, vercel_ai_cfg = generate_deploy_configs(
            repo_path=repo_path,
            project_name=project_base_name,
            provider=args.provider,
            openai_model=args.openai_model,
            claude_model=args.claude_model,
        )

        if update_railway and railway_ai_cfg:
            railway_cfg.update(railway_ai_cfg)
        if update_vercel and vercel_ai_cfg:
            vercel_cfg.update(vercel_ai_cfg)

        # Enforce canonical names even if AI output differs
        if update_railway:
            railway_cfg["project"] = project_base_name
        if update_vercel:
            vercel_cfg["project"] = f"{project_base_name}-frontend"

        if update_railway:
            write_config_back(repo_path, RAILWAY_STATE_FILE, railway_cfg)
        if update_vercel:
            write_config_back(repo_path, VERCEL_STATE_FILE, vercel_cfg)

    github_url = ""
    github_repo = ""
    if not args.configs_only:
        # STEP 1: Git push
        github_repo_name = args.repo_name or project_base_name
        github_url, github_repo = push_to_github(
            repo_path=repo_path,
            github_token=github_token,
            github_username=github_username,
            repo_name=github_repo_name,
            branch=args.branch,
            new_repo=args.new_project,
        )

    print(f"\n{'='*60}")
    print("PREP COMPLETE (NO DEPLOY)")
    print(f"{'='*60}")
    print(f"  Repo path: {repo_path}")
    if args.configs_only:
        updated = []
        if update_railway:
            updated.append(RAILWAY_STATE_FILE)
        if update_vercel:
            updated.append(VERCEL_STATE_FILE)
        print(f"  Configs:   {', '.join(updated)} updated")
        print("  Git push:  skipped (--configs-only)")
    else:
        print(f"  GitHub:    {github_url}")
        print(f"  Repo:      {github_repo}")
        print(f"  Next:      python deploy/pipeline_deploy.py --repo {repo_path}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
