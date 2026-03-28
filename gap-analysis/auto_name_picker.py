#!/usr/bin/env python3
"""Generate name suggestions and pick the cheapest domain among top-5 scored candidates."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

NAME_GENERATOR = Path(__file__).resolve().parent.parent / "agent-make" / "name_generator.py"

VOWELS = set("aeiou")


def _read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: Path, data: Dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def _slugify(name: str) -> str:
    name = name.strip().lower()
    name = re.sub(r"[^a-z0-9]+", "-", name)
    name = re.sub(r"-+", "-", name).strip("-")
    return name


def _rename_intake(intake: Dict[str, Any], new_name: str) -> Dict[str, Any]:
    updated = deepcopy(intake)
    slug = _slugify(new_name)

    old_name = updated.get("startup_name", "")
    updated["startup_name"] = new_name
    updated["run_id"] = slug
    updated["startup_idea_id"] = slug

    if "summary" in updated and isinstance(updated["summary"], str) and old_name:
        updated["summary"] = updated["summary"].replace(old_name, new_name, 1)

    for block_key in ["block_a", "block_b"]:
        block = updated.get(block_key, {})
        if isinstance(block, dict):
            block["startup_idea_id"] = slug
            pass_1 = block.get("pass_1", {})
            if isinstance(pass_1, dict):
                pass_1["startup_name"] = new_name

    return updated


def _keyword_tokens(brief: Dict[str, Any]) -> List[str]:
    parts = []
    for key in ["name", "description", "target_audience", "problem_solved"]:
        val = brief.get(key, "")
        if isinstance(val, str):
            parts.append(val.lower())
    for feat in brief.get("features", []) or []:
        if isinstance(feat, str):
            parts.append(feat.lower())
    text = " ".join(parts)
    tokens = re.findall(r"[a-z]{3,}", text)
    return list(dict.fromkeys(tokens))


def _score_candidate(name: str, slug: str, tokens: List[str]) -> int:
    base = 100
    length_penalty = len(slug) * 2
    vowel_bonus = sum(1 for ch in slug if ch in VOWELS) * 2
    token_bonus = 0
    for tok in tokens:
        if tok in slug:
            token_bonus += 3
    repeat_penalty = 5 if re.search(r"(.)\1\1", slug) else 0
    score = base - length_penalty + vowel_bonus + token_bonus - repeat_penalty
    return max(score, 0)


def _parse_price(price: Optional[str]) -> Optional[float]:
    if price is None:
        return None
    try:
        return float(price)
    except ValueError:
        return None


def _run_name_generator(args: List[str]) -> None:
    cmd = ["python", str(NAME_GENERATOR)] + args
    result = subprocess.run(cmd, check=False)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def main() -> None:
    parser = argparse.ArgumentParser(description="Auto name picker (cheapest among top-5 scored)")
    parser.add_argument("--intake", required=True, help="Path to original intake JSON")
    parser.add_argument("--brief", required=True, help="Path to business brief JSON")
    parser.add_argument("--out-dir", help="Output directory")
    parser.add_argument("--provider", choices=["chatgpt", "claude"], default="chatgpt")
    parser.add_argument("--model", default=None)
    parser.add_argument("--candidates", type=int, default=60)
    parser.add_argument("--max-len", type=int, default=14)
    parser.add_argument("--tlds", default="com,co,io,app,ai,dev,xyz,site,online,live")
    parser.add_argument("--price-max", type=float, default=30.0)
    parser.add_argument("--require-domain-check", action="store_true", default=True)
    args = parser.parse_args()

    intake_path = Path(args.intake).expanduser().resolve()
    brief_path = Path(args.brief).expanduser().resolve()
    repo_root = Path(__file__).resolve().parent.parent
    out_dir = Path(args.out_dir).expanduser().resolve() if args.out_dir else repo_root / "gap-analysis" / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)

    if not intake_path.exists():
        raise SystemExit(f"Intake not found: {intake_path}")
    if not brief_path.exists():
        raise SystemExit(f"Brief not found: {brief_path}")

    base = intake_path.stem
    report_path = out_dir / f"{base}_name_report.json"
    suggestions_path = out_dir / f"{base}_name_suggestions.json"
    renamed_path = out_dir / f"{base}_named.json"

    ng_args = [
        "--intake", str(intake_path),
        "--provider", args.provider,
        "--candidates", str(args.candidates),
        "--max-len", str(args.max_len),
        "--tlds", args.tlds,
        "--price-max", str(args.price_max),
        "--report", str(report_path),
        "--no-apply",
    ]
    if args.model:
        ng_args += ["--model", args.model]
    if args.require_domain_check:
        ng_args += ["--require-domain-check"]

    _run_name_generator(ng_args)

    report = _read_json(report_path)
    candidates = report.get("candidates", []) or []
    checked = report.get("checked_domains", []) or []

    tokens = _keyword_tokens(_read_json(brief_path))

    scored = []
    for c in candidates:
        name = c.get("name", "")
        slug = c.get("slug", "")
        if not name or not slug:
            continue
        score = _score_candidate(name, slug, tokens)
        scored.append({"name": name, "slug": slug, "tagline": c.get("tagline", ""), "score": score})

    scored.sort(key=lambda x: (-x["score"], x["name"]))
    top5 = scored[:5]

    available_prices: Dict[str, float] = {}
    for entry in checked:
        domain = entry.get("domain")
        if not domain or not entry.get("available"):
            continue
        price = _parse_price(entry.get("price"))
        if price is None:
            continue
        slug = domain.split(".")[0]
        if slug not in available_prices or price < available_prices[slug]:
            available_prices[slug] = price

    chosen = None
    chosen_price = None
    for c in top5:
        slug = c["slug"]
        if slug in available_prices:
            if chosen is None or available_prices[slug] < (chosen_price or 9999):
                chosen = c
                chosen_price = available_prices[slug]

    if chosen is None and available_prices:
        # fallback: cheapest available among all scored
        for c in scored:
            slug = c["slug"]
            if slug in available_prices:
                chosen = c
                chosen_price = available_prices[slug]
                break

    if chosen is None:
        # Fallback: pick best scored even without an available domain
        if not scored:
            raise SystemExit("No candidates generated.")
        chosen = scored[0]
        chosen_price = None

    intake = _read_json(intake_path)
    renamed = _rename_intake(intake, chosen["name"])
    _write_json(renamed_path, renamed)

    suggestions = {
        "picked": {
            "name": chosen["name"],
            "slug": chosen["slug"],
            "score": chosen["score"],
            "price_usd": chosen_price,
        },
        "top5": top5,
        "available_prices": available_prices,
        "report": str(report_path),
    }
    _write_json(suggestions_path, suggestions)

    if chosen_price is None:
        print(f"Picked (no domain available): {chosen['name']}")
    else:
        print(f"Picked: {chosen['name']} (${chosen_price:.2f})")
    print(f"Renamed intake: {renamed_path}")
    print(f"Suggestions: {suggestions_path}")


if __name__ == "__main__":
    main()
