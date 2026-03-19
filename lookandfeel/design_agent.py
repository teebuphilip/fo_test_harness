#!/usr/bin/env python3
"""
Design Agent
============

Analyzes and improves look-and-feel (not UI flow/logic) for a GitHub repo
using a Base44-compatible AI API.

Usage:
  python lookandfeel/design_agent.py https://github.com/<owner>/<repo>
"""

import base64
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

import requests


DEFAULT_FALLBACK_TARGET_FILES = [
    "src/components/DashboardLayout.jsx",
    "src/components/Navbar.jsx",
    "src/components/FeatureCard.jsx",
    "src/components/PricingCard.jsx",
    "src/index.css",
    "src/globals.css",
    "tailwind.config.js",
]

SKIP_PATH_PARTS = {
    "node_modules",
    "__tests__",
    "dist",
    "build",
    ".next",
    "coverage",
}

FRONTEND_EXTENSIONS = (".jsx", ".tsx", ".js", ".ts", ".css")


def env_required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        print(f"Error: {name} is required")
        sys.exit(2)
    return value


def parse_repo(url: str) -> Tuple[str, str]:
    parsed = urlparse(url)
    if "github.com" not in parsed.netloc:
        raise ValueError("Only GitHub repo URLs are supported")
    parts = parsed.path.strip("/").split("/")
    if len(parts) < 2:
        raise ValueError("Invalid GitHub repo URL")
    owner = parts[0]
    repo = parts[1].replace(".git", "")
    return owner, repo


def github_headers(token: str) -> Dict[str, str]:
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def fetch_file(owner: str, repo: str, path: str, branch: str, gh_token: str) -> Optional[str]:
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
    resp = requests.get(url, headers=github_headers(gh_token), params={"ref": branch}, timeout=30)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, list):
        return None
    content = data.get("content", "")
    if not content:
        return None
    return base64.b64decode(content).decode("utf-8", errors="replace")


def fetch_tree(owner: str, repo: str, branch: str, gh_token: str) -> List[str]:
    url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/{branch}"
    resp = requests.get(
        url,
        headers=github_headers(gh_token),
        params={"recursive": 1},
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    return [item["path"] for item in data.get("tree", []) if item.get("type") == "blob"]


def strip_fences(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[len("```json"):].strip()
    elif cleaned.startswith("```"):
        cleaned = cleaned[len("```"):].strip()
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3].strip()
    return cleaned


def parse_json_text(text: str) -> dict:
    cleaned = strip_fences(text)
    return json.loads(cleaned)


def call_base44_ai(system_prompt: str, user_prompt: str) -> str:
    api_key = env_required("BASE44_API_KEY")
    api_url = os.getenv("BASE44_API_URL", "https://api.anthropic.com/v1/messages")
    model = os.getenv("BASE44_MODEL", "claude-sonnet-4-20250514")
    max_tokens = int(os.getenv("BASE44_MAX_TOKENS", "8192"))
    api_version = os.getenv("BASE44_API_VERSION", "2023-06-01")

    headers = {
        "x-api-key": api_key,
        "anthropic-version": api_version,
        "content-type": "application/json",
    }
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_prompt}],
        "temperature": 0.0,
    }
    resp = requests.post(api_url, headers=headers, json=payload, timeout=120)
    resp.raise_for_status()
    data = resp.json()
    content = data.get("content", [])
    if not content:
        raise RuntimeError("AI response missing content")
    return content[0].get("text", "")


def parse_target_files_from_directive(directive: str) -> List[str]:
    files: List[str] = []
    in_section = False
    for raw in directive.splitlines():
        line = raw.strip()
        upper = line.upper()
        if upper.startswith("## TARGET FILES"):
            in_section = True
            continue
        if in_section and line.startswith("## "):
            break
        if in_section and line.startswith("-"):
            files.append(line.lstrip("- ").strip())
    return [f for f in files if f]


DISCOVERY_SYSTEM = """
You are a senior frontend engineer.
Given a repo file tree, choose files that control look-and-feel only:
layout shells, nav/shared UI components, global CSS, Tailwind/theme config.
Ignore tests, backend, API, business logic, routing, data layers.
Return JSON only: {"target_files":["path1","path2",...]}
"""


def discover_target_files_by_ai(paths: List[str]) -> List[str]:
    if not paths:
        return []
    prompt = "Repo file tree:\n" + "\n".join(paths)
    raw = call_base44_ai(DISCOVERY_SYSTEM, prompt)
    data = parse_json_text(raw)
    files = data.get("target_files", [])
    if not isinstance(files, list):
        return []
    return [str(p).strip() for p in files if str(p).strip()]


def build_candidate_paths(repo_paths: List[str]) -> List[str]:
    out: List[str] = []
    for p in repo_paths:
        lower = p.lower()
        if not lower.endswith(FRONTEND_EXTENSIONS):
            continue
        if any(part in p.split("/") for part in SKIP_PATH_PARTS):
            continue
        if ".test." in lower or ".spec." in lower:
            continue
        out.append(p)
    return out


def resolve_target_paths(owner: str, repo: str, branch: str, gh_token: str) -> Tuple[List[str], Optional[str], List[str]]:
    # Priority 1: DESIGN_DIRECTIVE.md target list
    directive = fetch_file(owner, repo, "DESIGN_DIRECTIVE.md", branch, gh_token)
    if directive:
        from_directive = parse_target_files_from_directive(directive)
        if from_directive:
            return from_directive, directive, ["DESIGN_DIRECTIVE.md"]

    # Priority 2: AI discovery from file tree
    tree = fetch_tree(owner, repo, branch, gh_token)
    candidates = build_candidate_paths(tree)
    discovered = discover_target_files_by_ai(candidates)
    if discovered:
        return discovered, directive, ["AI_DISCOVERY"]

    # Priority 3: TARGET_FILES env var
    env_targets = os.getenv("TARGET_FILES", "").strip()
    if env_targets:
        files = [x.strip() for x in env_targets.split(",") if x.strip()]
        if files:
            return files, directive, ["TARGET_FILES"]

    # Priority 4: hardcoded fallback list
    return DEFAULT_FALLBACK_TARGET_FILES[:], directive, ["DEFAULT_FALLBACK"]


def fetch_target_files(owner: str, repo: str, branch: str, gh_token: str, paths: List[str]) -> Dict[str, str]:
    files: Dict[str, str] = {}
    for path in paths:
        content = fetch_file(owner, repo, path, branch, gh_token)
        if content is None:
            print(f"  - missing: {path}")
            continue
        files[path] = content
        print(f"  - fetched: {path}")
    return files


def build_file_block(files: Dict[str, str]) -> str:
    blocks = []
    for path, content in files.items():
        blocks.append(f"### FILE: {path}\n```\n{content}\n```")
    return "\n\n".join(blocks)


ASSESS_SYSTEM = """
You are a senior UI engineer specializing in modern SaaS visual design systems.
Assess look-and-feel only.
Do not change UI flow, component behavior, data flow, imports, routing, or business logic.
Focus on colors, typography, spacing rhythm, borders, shadows, backgrounds, hover/focus states, motion.
Return JSON only.
"""

ASSESS_PROMPT = """
Assess these files for visual quality and suggest improvements.

{directive_block}

{file_block}

Return JSON exactly:
{{
  "summary": "brief summary",
  "issues": [
    {{"file":"path","issue":"what is weak","suggestion":"exact class/token-level fix"}}
  ],
  "design_tokens": {{
    "theme": "light|dark|hybrid",
    "primary_color": "token/class",
    "background": "token/class",
    "surface": "token/class",
    "text_primary": "token/class",
    "text_muted": "token/class",
    "border": "token/class",
    "accent": "token/class"
  }},
  "directives": [
    "short actionable directive line"
  ],
  "priority_files": ["path1","path2"]
}}
"""

APPLY_SYSTEM = """
You are a senior frontend engineer.
Apply only look-and-feel improvements.
Keep component structure, props, logic, imports, routing, API and state behavior unchanged.
Only edit CSS variables/classes/theme tokens and visual utility classes.
Return JSON only in shape: {"path":"full file content", ...}
"""

APPLY_PROMPT = """
Apply the assessment improvements to these files.

ASSESSMENT:
{assessment_json}

{directive_block}

FILES:
{file_block}

Return JSON only:
{{"path/to/file":"updated file text"}}
"""


def make_directive_markdown(target_paths: List[str], assessment: dict) -> str:
    tokens = assessment.get("design_tokens", {}) if isinstance(assessment, dict) else {}
    directives = assessment.get("directives", []) if isinstance(assessment, dict) else []
    lines = [
        "# DESIGN_DIRECTIVE.generated.md",
        "version: 1.0",
        "",
        "## SCOPE",
        "- CHANGE: colors, typography, spacing, shadows, borders, hover/focus states, transitions",
        "- DO NOT CHANGE: props, business logic, routing, data flow, imports, component structure",
        "",
        "## TARGET FILES",
    ]
    for p in target_paths:
        lines.append(f"- {p}")
    lines.extend(["", "## DESIGN TOKENS"])
    for key in [
        "theme",
        "primary_color",
        "background",
        "surface",
        "text_primary",
        "text_muted",
        "border",
        "accent",
    ]:
        lines.append(f"{key}: {tokens.get(key, '')}")
    lines.extend(["", "## DIRECTIVES"])
    for d in directives:
        lines.append(f"- {d}")
    return "\n".join(lines) + "\n"


def write_outputs(output_dir: Path, assessment: dict, updated_files: Dict[str, str], directive_md: str) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    (output_dir / "assessment.json").write_text(json.dumps(assessment, indent=2) + "\n")
    (output_dir / "DESIGN_DIRECTIVE.generated.md").write_text(directive_md)

    files_root = output_dir / "files"
    for rel_path, content in updated_files.items():
        dest = files_root / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content)


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python lookandfeel/design_agent.py <github-repo-url> [branch]")
        sys.exit(1)

    repo_url = sys.argv[1]
    branch = sys.argv[2] if len(sys.argv) > 2 else os.getenv("GITHUB_BRANCH", "HEAD")
    gh_token = os.getenv("GITHUB_TOKEN", "").strip()
    output_dir = Path(os.getenv("OUTPUT_DIR", "./lookandfeel_output")).resolve()
    dry_run = os.getenv("DRY_RUN", "false").strip().lower() == "true"

    owner, repo = parse_repo(repo_url)
    print(f"Repo: {owner}/{repo} (branch/ref: {branch})")

    target_paths, directive, source = resolve_target_paths(owner, repo, branch, gh_token)
    print(f"Target selection source: {', '.join(source)}")
    print(f"Target path count: {len(target_paths)}")

    files = fetch_target_files(owner, repo, branch, gh_token, target_paths)
    if not files:
        print("Error: no target files fetched")
        sys.exit(3)

    file_block = build_file_block(files)
    directive_block = ""
    if directive:
        directive_block = f"DESIGN_DIRECTIVE.md:\n```\n{directive}\n```"

    print("Step 1: Assess look and feel...")
    assess_raw = call_base44_ai(
        ASSESS_SYSTEM,
        ASSESS_PROMPT.format(
            directive_block=directive_block or "No DESIGN_DIRECTIVE.md provided.",
            file_block=file_block,
        ),
    )
    assessment = parse_json_text(assess_raw)

    print("Assessment summary:")
    print(f"  {assessment.get('summary', 'No summary returned')}")
    for issue in assessment.get("issues", [])[:10]:
        if not isinstance(issue, dict):
            continue
        print(f"  - {issue.get('file', 'unknown')}: {issue.get('issue', '')}")

    if dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "assessment.json").write_text(json.dumps(assessment, indent=2) + "\n")
        directive_md = make_directive_markdown(list(files.keys()), assessment)
        (output_dir / "DESIGN_DIRECTIVE.generated.md").write_text(directive_md)
        print(f"DRY_RUN=true. Wrote: {output_dir / 'assessment.json'}")
        print(f"DRY_RUN=true. Wrote: {output_dir / 'DESIGN_DIRECTIVE.generated.md'}")
        return

    print("Step 2: Apply visual improvements...")
    apply_raw = call_base44_ai(
        APPLY_SYSTEM,
        APPLY_PROMPT.format(
            assessment_json=json.dumps(assessment, indent=2),
            directive_block=directive_block or "No DESIGN_DIRECTIVE.md provided.",
            file_block=file_block,
        ),
    )
    updated_files = parse_json_text(apply_raw)
    if not isinstance(updated_files, dict):
        print("Error: apply response is not a JSON object")
        sys.exit(4)

    directive_md = make_directive_markdown(list(files.keys()), assessment)
    write_outputs(output_dir, assessment, updated_files, directive_md)
    print(f"Wrote updated files under: {output_dir / 'files'}")
    print(f"Wrote directive: {output_dir / 'DESIGN_DIRECTIVE.generated.md'}")


if __name__ == "__main__":
    main()
