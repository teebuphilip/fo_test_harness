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
import time
from datetime import datetime

DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
DEFAULT_CLAUDE_MODEL = "claude-3-5-sonnet-20240620"
OPENAI_INPUT_PER_MTOK = float(os.getenv("OPENAI_INPUT_PER_MTOK", "2.50"))
OPENAI_OUTPUT_PER_MTOK = float(os.getenv("OPENAI_OUTPUT_PER_MTOK", "10.00"))
CLAUDE_INPUT_PER_MTOK = float(os.getenv("CLAUDE_INPUT_PER_MTOK", "3.00"))
CLAUDE_OUTPUT_PER_MTOK = float(os.getenv("CLAUDE_OUTPUT_PER_MTOK", "15.00"))
GRILL_ME_COST_CSV = Path(os.getenv("GRILL_ME_COST_CSV", "grill_me_ai_costs.csv"))


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


def _has_non_empty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return len(value) > 0
    return True


def _filter_answered_issues(report: Dict[str, Any], intake_obj: Dict[str, Any]) -> Dict[str, Any]:
    """
    Drop issues that are already answered by authoritative fields.
    """
    block_b = intake_obj.get("block_b", {})
    pass1 = block_b.get("pass_1", {})
    hero = block_b.get("hero_answers", {})

    payment_details = pass1.get("economics_snapshot", {}).get("payment_integration_details")
    roles_permissions = pass1.get("roles_permissions")
    invoice_edge_cases = pass1.get("invoice_edge_cases")
    mvp_features = hero.get("Q4_must_have_features")
    compliance = hero.get("Q6_constraints", {}).get("compliance")
    integrations = hero.get("Q8_integrations") or []
    has_stripe = any(str(i).lower() == "stripe" for i in integrations)
    payment_details_has_stripe = _has_non_empty(payment_details) and "stripe" in str(payment_details).lower()

    filtered = []
    for issue in report.get("issues", []) or []:
        q = f"{issue.get('question','')} {issue.get('suggested_resolution','')}".lower()
        if ("payment" in q or "integration" in q or "paypal" in q or "stripe" in q) and has_stripe and payment_details_has_stripe:
            continue
        if ("role" in q or "permission" in q) and _has_non_empty(roles_permissions):
            continue
        if ("edge case" in q or "edge-case" in q or "edgecase" in q) and _has_non_empty(invoice_edge_cases):
            continue
        if ("mvp" in q or "feature" in q) and _has_non_empty(mvp_features):
            continue
        if ("pci" in q or "compliance" in q) and _has_non_empty(compliance):
            continue
        filtered.append(issue)

    report["issues"] = filtered
    if _acceptance_complete(intake_obj):
        report["issues"] = []
        report["halt"] = False
        report["halt_reason"] = ""
        return report
    if not filtered:
        report["halt"] = False
        report["halt_reason"] = ""
    return report


def _acceptance_complete(intake_obj: Dict[str, Any]) -> bool:
    block_b = intake_obj.get("block_b", {})
    pass1 = block_b.get("pass_1", {})
    hero = block_b.get("hero_answers", {})

    features = hero.get("Q4_must_have_features") or []
    has_features = isinstance(features, list) and len([f for f in features if f]) >= 2
    has_compliance = _has_non_empty(hero.get("Q6_constraints", {}).get("compliance"))
    integrations = hero.get("Q8_integrations") or []
    has_integrations = isinstance(integrations, list) and any(str(i).lower() == "stripe" for i in integrations)
    has_payment_details = _has_non_empty(pass1.get("economics_snapshot", {}).get("payment_integration_details"))
    roles_permissions = pass1.get("roles_permissions")
    has_roles = (
        isinstance(roles_permissions, dict)
        and "admin" in roles_permissions
        and "seller" in roles_permissions
    )
    edge_cases = pass1.get("invoice_edge_cases") or []
    has_edge_cases = isinstance(edge_cases, list) and len([e for e in edge_cases if e]) >= 3

    return all([has_features, has_compliance, has_integrations, has_payment_details, has_roles, has_edge_cases])


def _dedup_list(values: Any) -> Any:
    if not isinstance(values, list):
        return values
    seen = set()
    deduped = []
    for item in values:
        key = item if isinstance(item, str) else json.dumps(item, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _normalize_block_b(intake_obj: Dict[str, Any]) -> None:
    block_b = intake_obj.get("block_b", {})
    pass1 = block_b.get("pass_1", {})
    pass2 = block_b.get("pass_2", {})
    pass3 = block_b.get("pass_3", {})
    pass6 = block_b.get("pass_6", {})

    # 1) Dedup questions_for_hero
    if "questions_for_hero" in pass1:
        pass1["questions_for_hero"] = _dedup_list(pass1.get("questions_for_hero"))

    # Enforce Stripe-only integration
    hero = block_b.get("hero_answers", {})
    integrations = hero.get("Q8_integrations")
    if isinstance(integrations, list):
        hero["Q8_integrations"] = ["Stripe"]
    elif integrations is not None:
        hero["Q8_integrations"] = ["Stripe"]
    econ = pass1.get("economics_snapshot", {})
    payment_details = econ.get("payment_integration_details")
    if payment_details:
        lower = str(payment_details).lower()
        if "stripe" not in lower or "paypal" in lower:
            econ["payment_integration_details"] = (
                "Stripe only. Use Stripe Checkout or Payment Intents. "
                "Handle failures with user notification and retry."
            )

    # 2) integration_count at least 1 when payments are needed
    arch = pass1.get("architecture_flags", {})
    if arch.get("needs_payments"):
        metrics = pass1.setdefault("tier_enforcement_metrics", {})
        metrics["integration_count"] = max(1, int(metrics.get("integration_count", 0) or 0))

    # 3) Dedup engineering and QA questions
    if "engineering_questions" in pass2:
        pass2["engineering_questions"] = _dedup_list(pass2.get("engineering_questions"))
    if "qa_questions_for_engineering" in pass3:
        pass3["qa_questions_for_engineering"] = _dedup_list(pass3.get("qa_questions_for_engineering"))

    # 4) needs_auth should be true when roles/permissions exist
    roles_permissions = pass1.get("roles_permissions")
    if isinstance(roles_permissions, str) or roles_permissions is None:
        pass1["roles_permissions"] = {
            "admin": {
                "access": "full",
                "capabilities": ["manage_users", "configure_settings"],
            },
            "seller": {
                "access": "limited",
                "capabilities": ["view_invoices", "make_payments"],
            },
        }
    if pass1.get("roles_permissions"):
        pass1.setdefault("architecture_flags", {})["needs_auth"] = True

    # 5) Clear hero_questions when hero_answers already define features
    hero_answers = block_b.get("hero_answers", {})
    if hero_answers.get("Q4_must_have_features"):
        pass6["hero_questions"] = []


def _build_prompt(intake: Dict[str, Any], arch_context: str = "", block_b_only: bool = False) -> str:
    intake_str = json.dumps(intake, indent=2)
    base = (
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
        "- Treat block_b.hero_answers and block_b.pass_1.economics_snapshot.payment_integration_details as authoritative.\n"
        "- If roles/permissions or edge cases are already defined in block_b.pass_1.roles_permissions or block_b.pass_1.invoice_edge_cases, do not raise them.\n"
        "- questions_for_hero is legacy; do not treat unanswered questions there as missing if answers exist elsewhere.\n\n"
        "- Intake-level sufficiency only. Do NOT ask for implementation-level details like exact API endpoints, full data schemas, or validation rules.\n"
        "- If payment integrations and compliance are described at a high level, treat them as resolved.\n"
        "- If the intake explicitly defers specifics to build (e.g., 'to be finalized during build'), treat that as resolved.\n"
        "- If block_b.hero_answers and block_b.pass_1 (payment_integration_details, roles_permissions, invoice_edge_cases) are populated, return no issues and halt=false.\n\n"
        "- Payment integration must be Stripe only. Do not require or suggest PayPal.\n"
        "- Require at least 2 must-have features in hero_answers.\n"
        "- Require roles_permissions as a structured object with at least admin and seller roles.\n"
        "- Require at least 3 invoice_edge_cases (intake-level, short list).\n\n"
        f"INTAKE JSON:\n{intake_str}\n"
    )
    if block_b_only:
        base += "\nConstraints:\n- Only consider and patch block_b. Ignore block_a entirely.\n"
    if arch_context:
        return base + "\nARCHITECTURE CONTEXT:\n" + arch_context + "\n"
    return base


def _call_openai(prompt: str, model: str) -> Tuple[str, Dict[str, Any]]:
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
    usage = data.get("usage", {})
    return data["choices"][0]["message"]["content"], usage


def _call_claude(prompt: str, model: str) -> Tuple[str, Dict[str, Any]]:
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
    usage = data.get("usage", {})
    return text, usage


def _compute_cost(provider: str, usage: Dict[str, Any]) -> Tuple[int, int, float]:
    if provider == "chatgpt":
        in_tokens = int(usage.get("prompt_tokens", 0) or 0)
        out_tokens = int(usage.get("completion_tokens", 0) or 0)
        cost = (in_tokens * OPENAI_INPUT_PER_MTOK + out_tokens * OPENAI_OUTPUT_PER_MTOK) / 1_000_000
        return in_tokens, out_tokens, cost
    in_tokens = int(usage.get("input_tokens", 0) or 0)
    out_tokens = int(usage.get("output_tokens", 0) or 0)
    cost = (in_tokens * CLAUDE_INPUT_PER_MTOK + out_tokens * CLAUDE_OUTPUT_PER_MTOK) / 1_000_000
    return in_tokens, out_tokens, cost


def _append_cost_row(intake_path: Path, provider: str, model: str, in_tokens: int, out_tokens: int, cost: float) -> None:
    exists = GRILL_ME_COST_CSV.exists()
    with open(GRILL_ME_COST_CSV, "a", encoding="utf-8") as f:
        if not exists:
            f.write("date,time,intake,provider,model,in_tokens,out_tokens,cost\n")
        now = datetime.now()
        f.write(
            f"{now.date().isoformat()},{now.time().strftime('%H:%M:%S')},"
            f"{intake_path.name},{provider},{model},{in_tokens},{out_tokens},{cost:.6f}\n"
        )


def _sum_total_cost() -> float:
    if not GRILL_ME_COST_CSV.exists():
        return 0.0
    total = 0.0
    with open(GRILL_ME_COST_CSV, "r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            if i == 0:
                continue
            parts = line.strip().split(",")
            if len(parts) < 8:
                continue
            try:
                total += float(parts[7])
            except ValueError:
                continue
    return total


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
    parser.add_argument("--provide-answers", action="store_true", help="Auto-fill answers and re-run grill-me until max iterations (default: on)")
    parser.add_argument("--architecture-context", default=None, help="Path to architecture context file to append")
    parser.add_argument("--max-iterations", type=int, default=5, help="Max iterations before halting (default: 5)")
    parser.add_argument("--block-b-only", action="store_true", help="Ignore block_a and only patch block_b (default: on)")
    parser.add_argument("--resume", action="store_true", help="Resume from existing *.grilled.json if present (default: on if file exists)")
    args = parser.parse_args()

    intake_path = Path(args.intake).expanduser().resolve()
    if not intake_path.exists():
        print(f"[ERROR] Intake not found: {intake_path}")
        return 1

    def _run_ai(prompt: str, label: str) -> Tuple[str, str]:
        print(f"[Grill‑Me] Provider: {args.provider}")
        print(f"[Grill‑Me] Model: {args.model or (DEFAULT_OPENAI_MODEL if args.provider == 'chatgpt' else DEFAULT_CLAUDE_MODEL)}")
        print(f"[Grill‑Me] Intake: {intake_path}")
        print(f"[Grill‑Me] Prompt bytes: {len(prompt.encode('utf-8'))}")
        print(f"[Grill‑Me] Calling AI ({label})...")
        start = time.time()

        model = args.model
        if args.provider == "chatgpt":
            model = model or DEFAULT_OPENAI_MODEL
            raw, usage = _call_openai(prompt, model)
        else:
            model = model or DEFAULT_CLAUDE_MODEL
            raw, usage = _call_claude(prompt, model)
        elapsed = time.time() - start
        in_tokens, out_tokens, cost = _compute_cost(args.provider, usage)
        _append_cost_row(intake_path, args.provider, model, in_tokens, out_tokens, cost)
        cumulative = _sum_total_cost()

        print(f"[Grill‑Me] AI call complete in {elapsed:.2f}s")
        print(f"[Grill‑Me] Tokens: in={in_tokens} out={out_tokens}")
        print(f"[Grill‑Me] Cost: ${cost:.4f} (cumulative: ${cumulative:.4f})")
        print(f"[Grill‑Me] Cost CSV: {GRILL_ME_COST_CSV.resolve()}")
        print("[Grill‑Me] RAW OUTPUT BEGIN")
        print(raw)
        print("[Grill‑Me] RAW OUTPUT END")
        return raw, model

    def _build_answer_prompt(intake_obj: Dict[str, Any], report_obj: Dict[str, Any], block_b_only: bool = False) -> str:
        intake_str = json.dumps(intake_obj, indent=2)
        report_str = json.dumps(report_obj, indent=2)
        base = (
            "You are fixing intake ambiguities. Provide concrete answers.\n"
            "Return STRICT JSON only with this schema:\n"
            "{\n"
            "  \"hero_answers\": {\n"
            "    \"Q1_problem_customer\": \"...\",\n"
            "    \"Q2_target_user\": [\"...\"],\n"
            "    \"Q3_success_metric\": \"...\",\n"
            "    \"Q4_must_have_features\": [\"...\"],\n"
            "    \"Q5_non_goals\": [\"...\"],\n"
            "    \"Q6_constraints\": {\n"
            "      \"brand_positioning\": \"...\",\n"
            "      \"compliance\": \"...\",\n"
            "      \"promise_limits\": \"...\",\n"
            "      \"scale_limits\": \"...\"\n"
            "    },\n"
            "    \"Q7_data_sources\": [\"...\"],\n"
            "    \"Q8_integrations\": [\"...\"],\n"
            "    \"Q9_risks\": [\"...\"],\n"
            "    \"Q10_shipping_preference\": \"...\"\n"
            "  },\n"
            "  \"supplemental\": {\n"
            "    \"payment_integration_details\": \"...\",\n"
            "    \"roles_permissions\": \"...\",\n"
            "    \"invoice_edge_cases\": [\"...\"]\n"
            "  }\n"
            "}\n\n"
            "Rules:\n"
            "- Use only information implied by the intake and the grill report.\n"
            "- Prefer small, buildable, manual-first answers.\n"
            "- Keep compliance realistic; if unknown, state 'none' or 'tbd'.\n\n"
            "- Payment integration must be Stripe only.\n"
            "- Provide at least 2 must-have features.\n"
            "- Provide roles_permissions as a structured object with at least admin and seller roles.\n"
            "- Provide at least 3 invoice_edge_cases.\n\n"
            f"INTAKE JSON:\n{intake_str}\n\n"
            f"GRILL REPORT:\n{report_str}\n"
        )
        if block_b_only:
            base += "\nConstraints:\n- Only update block_b fields. Do not modify block_a.\n"
        return base

    intake = _read_json(intake_path)
    # Default provide-answers to True unless explicitly disabled in future
    if not args.provide_answers:
        args.provide_answers = True
    arch_context = ""
    if args.architecture_context:
        arch_path = Path(args.architecture_context).expanduser().resolve()
        if not arch_path.exists():
            print(f"[ERROR] Architecture context not found: {arch_path}")
            return 1
        arch_context = arch_path.read_text(encoding="utf-8", errors="replace")
        print(f"[Grill‑Me] Architecture context: {arch_path}")

    if args.report:
        report_path = Path(args.report).expanduser().resolve()
    else:
        report_path = intake_path.parent / f"{intake_path.stem}.grill_report.json"

    if args.in_place:
        out_path = intake_path
    else:
        out_path = Path(args.out).expanduser().resolve() if args.out else intake_path.parent / f"{intake_path.stem}.grilled.json"

    max_iters = max(1, args.max_iterations)
    # Default block-b-only to True unless explicitly disabled in future
    if not args.block_b_only:
        args.block_b_only = True
    current = deepcopy(intake)
    if (args.resume or out_path.exists()) and out_path.exists():
        current = _read_json(out_path)
        print(f"[Grill‑Me] Resuming from: {out_path}")

    for iteration in range(1, max_iters + 1):
        print(f"[Grill‑Me] Iteration {iteration}/{max_iters}")
        raw, model = _run_ai(_build_prompt(current, arch_context, args.block_b_only), "review")
        report = _extract_json(raw)
        report = _filter_answered_issues(report, current)

        # Apply patches
        patched = deepcopy(current)
        applied: List[Dict[str, Any]] = []
        failed: List[Dict[str, Any]] = []

        for p in report.get("patches", []) or []:
            path = p.get("json_path")
            if not path:
                failed.append({"json_path": path, "error": "missing json_path"})
                continue
            if "questions_for_hero" in str(path):
                failed.append({"json_path": path, "error": "legacy questions_for_hero ignored"})
                continue
            if args.block_b_only and not str(path).startswith("block_b."):
                failed.append({"json_path": path, "error": "block_a skipped (block-b-only)"})
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

        _normalize_block_b(patched)

        _write_json(report_path, report)
        print(f"[Grill‑Me] Report saved: {report_path}")

        if not args.no_apply:
            _write_json(out_path, patched)
            print(f"[Grill‑Me] Patched intake saved: {out_path}")

        if not report.get("halt") and not report.get("issues"):
            print("[Grill‑Me] No issues remain — stopping")
            print("============================================================")
            break

        if report.get("halt"):
            if args.provide_answers and not args.no_apply and iteration < max_iters:
                print("[Grill‑Me] provide-answers enabled — attempting to auto-fill ambiguities")
                answer_raw, _ = _run_ai(_build_answer_prompt(patched, report, args.block_b_only), "answer-fill")
                answer_report = _extract_json(answer_raw)
                hero_answers = answer_report.get("hero_answers")
                if isinstance(hero_answers, dict):
                    patched.setdefault("block_b", {})["hero_answers"] = hero_answers
                    print("[Grill‑Me] Applied hero_answers to block_b")
                    print(json.dumps(hero_answers, indent=2))
                supplemental = answer_report.get("supplemental") or {}
                if isinstance(supplemental, dict):
                    pass1 = patched.setdefault("block_b", {}).setdefault("pass_1", {})
                    econ = pass1.setdefault("economics_snapshot", {})
                    payment_details = supplemental.get("payment_integration_details")
                    if payment_details:
                        econ["payment_integration_details"] = payment_details
                    roles_permissions = supplemental.get("roles_permissions")
                    if roles_permissions:
                        pass1["roles_permissions"] = roles_permissions
                    invoice_edge_cases = supplemental.get("invoice_edge_cases")
                    if invoice_edge_cases:
                        pass1["invoice_edge_cases"] = invoice_edge_cases
                _normalize_block_b(patched)
                _write_json(out_path, patched)
                print(f"[Grill‑Me] Patched intake saved: {out_path}")
                if _acceptance_complete(patched):
                    print("[Grill‑Me] Acceptance criteria met — stopping early")
                    print("============================================================")
                    return 0
                current = deepcopy(patched)
                print("============================================================")
                continue
            if iteration >= max_iters:
                print(f"[Grill‑Me] HALT: {report.get('halt_reason', 'unspecified')}")
                print("============================================================")
                return 2
        current = deepcopy(patched)
        print("============================================================")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
