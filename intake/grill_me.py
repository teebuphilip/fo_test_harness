#!/usr/bin/env python3
"""
Grill‑Me pass: adversarial intake review + patch suggestions.

Default provider: ChatGPT. Override with --provider claude.
Outputs a report and (optionally) a patched intake JSON.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Tuple

import requests

DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
DEFAULT_CLAUDE_MODEL = "claude-3-5-sonnet-20240620"


def _read_json(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: Path, data: Dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def _path_tokens(path: str) -> List[str]:
    # Supports: a.b[0].c or a.b.c
    tokens: List[str] = []
    buf = ""
    i = 0
    while i < len(path):
        c = path[i]
        if c == ".":
            if buf:
                tokens.append(buf)
                buf = ""
            i += 1
            continue
        if c == "[":
            if buf:
                tokens.append(buf)
                buf = ""
            j = path.find("]", i)
            if j == -1:
                raise ValueError(f"Invalid path (missing ]): {path}")
            tokens.append(path[i:j+1])
            i = j + 1
            continue
        buf += c
        i += 1
    if buf:
        tokens.append(buf)
    return tokens


def _set_by_path(data: Any, path: str, new_value: Any) -> Tuple[bool, str, Any]:
    """
    Set value by dot/bracket path. Returns (ok, resolved_path, old_value).
    """
    tokens = _path_tokens(path)
    cur = data
    for idx, tok in enumerate(tokens):
        is_last = idx == len(tokens) - 1
        if tok.startswith("[") and tok.endswith("]"):
            # list index
            if not isinstance(cur, list):
                return False, path, None
            try:
                i = int(tok[1:-1])
            except ValueError:
                return False, path, None
            if i < 0 or i >= len(cur):
                return False, path, None
            if is_last:
                old = cur[i]
                cur[i] = new_value
                return True, path, old
            cur = cur[i]
        else:
            # dict key
            if not isinstance(cur, dict) or tok not in cur:
                return False, path, None
            if is_last:
                old = cur[tok]
                cur[tok] = new_value
                return True, path, old
            cur = cur[tok]
    return False, path, None


def _build_prompt(intake: Dict[str, Any]) -> str:
    intake_str = json.dumps(intake, indent=2)
    return (
        "You are an adversarial reviewer. Stress-test the intake spec before build. "
        "Find vagueness, contradictions, missing data model details, unclear integrations, "
        "or ambiguous workflows that could cause hallucinations. "
        "Then propose concrete patches to the intake to freeze decisions.\n\n"
        "Return STRICT JSON only, with this schema:\n"
        "{\n"
        "  \"issues\": [\n"
        "    {\"severity\": \"low|medium|high\", \"area\": \"feature|data_model|integration|workflow|scope\", "
        "\"question\": \"...\", \"risk\": \"...\", \"suggested_resolution\": \"...\"}\n"
        "  ],\n"
        "  \"patches\": [\n"
        "    {\"json_path\": \"a.b[0].c\", \"new_value\": <JSON>, \"rationale\": \"...\"}\n"
        "  ],\n"
        "  \"halt\": true|false,\n"
        "  \"halt_reason\": \"...\"\n"
        "}\n\n"
        "Rules:\n"
        "- Only include patches you are confident about.\n"
        "- If more than 3 critical ambiguities remain, set halt=true.\n"
        "- Do not include commentary outside JSON.\n\n"
        f"INTAKE JSON:\n{intake_str}\n"
    )


def _call_openai(prompt: str, model: str) -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set")
    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a precise JSON-only assistant."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=60)
    if resp.status_code >= 400:
        raise RuntimeError(f"OpenAI error {resp.status_code}: {resp.text}")
    data = resp.json()
    return data["choices"][0]["message"]["content"]


def _call_claude(prompt: str, model: str) -> str:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    payload = {
        "model": model,
        "max_tokens": 2000,
        "temperature": 0.2,
        "messages": [
            {"role": "user", "content": prompt},
        ],
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=60)
    if resp.status_code >= 400:
        raise RuntimeError(f"Anthropic error {resp.status_code}: {resp.text}")
    data = resp.json()
    # Claude returns list of content blocks
    parts = data.get("content", [])
    text = "".join(p.get("text", "") for p in parts)
    return text


def _extract_json(text: str) -> Dict[str, Any]:
    # Expect JSON only, but be defensive
    text = text.strip()
    if text.startswith("{") and text.endswith("}"):
        return json.loads(text)
    # Fallback: extract first JSON object
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        raise ValueError("No JSON object found in model output")
    return json.loads(m.group(0))


def main() -> int:
    parser = argparse.ArgumentParser(description="Grill‑Me intake pass")
    parser.add_argument("--intake", required=True, help="Path to intake JSON")
    parser.add_argument("--provider", choices=["chatgpt", "claude"], default="chatgpt")
    parser.add_argument("--model", default=None, help="Model override")
    parser.add_argument("--out", default=None, help="Path for patched intake JSON")
    parser.add_argument("--report", default=None, help="Path for grill-me report JSON")
    parser.add_argument("--in-place", action="store_true", help="Overwrite intake JSON in place")
    parser.add_argument("--no-apply", action="store_true", help="Do not apply patches, only report")
    args = parser.parse_args()

    intake_path = Path(args.intake).expanduser().resolve()
    if not intake_path.exists():
        print(f"[ERROR] Intake not found: {intake_path}")
        return 1

    intake = _read_json(intake_path)
    prompt = _build_prompt(intake)

    model = args.model
    if args.provider == "chatgpt":
        model = model or DEFAULT_OPENAI_MODEL
        raw = _call_openai(prompt, model)
    else:
        model = model or DEFAULT_CLAUDE_MODEL
        raw = _call_claude(prompt, model)

    report = _extract_json(raw)

    # Apply patches
    patched = deepcopy(intake)
    applied: List[Dict[str, Any]] = []
    failed: List[Dict[str, Any]] = []

    for p in report.get("patches", []) or []:
        path = p.get("json_path")
        if not path:
            failed.append({"json_path": path, "error": "missing json_path"})
            continue
        ok, _, old = _set_by_path(patched, path, p.get("new_value"))
        if ok:
            applied.append({"json_path": path, "old_value": old, "new_value": p.get("new_value"), "rationale": p.get("rationale", "")})
        else:
            failed.append({"json_path": path, "error": "path not found"})

    report["patches_applied"] = applied
    report["patches_failed"] = failed
    report["provider"] = args.provider
    report["model"] = model

    if args.report:
        report_path = Path(args.report).expanduser().resolve()
    else:
        report_path = intake_path.parent / f"{intake_path.stem}.grill_report.json"
    _write_json(report_path, report)
    print(f"[Grill‑Me] Report saved: {report_path}")

    if not args.no_apply:
        if args.in_place:
            out_path = intake_path
        else:
            if args.out:
                out_path = Path(args.out).expanduser().resolve()
            else:
                out_path = intake_path.parent / f"{intake_path.stem}.grilled.json"
        _write_json(out_path, patched)
        print(f"[Grill‑Me] Patched intake saved: {out_path}")

    if report.get("halt"):
        print(f"[Grill‑Me] HALT: {report.get('halt_reason', 'unspecified')}")
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
