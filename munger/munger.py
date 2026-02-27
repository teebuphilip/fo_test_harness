#!/usr/bin/env python3
"""
FO/AF Munger v2.0.0 - Deterministic hero answer normalization + validation.

Usage:
  python munger/munger.py <hero_input.json> [--out output.json]
                           [--clarifications clarifications.json] [--loop 1|2]

Clarifications file format: list of envelopes:
[
  {"template_id": "CT011_architecture", "answers": {...}},
  {"template_id": "CT030_pricing_tiers", "answers": {...}}
]
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


ROOT = Path(__file__).resolve().parent

MUNGER_VERSION = "2.0.0"

FILES = {
    "autopatch": ROOT / "autopatch_rules.v2.0.json",
    "detection": ROOT / "detection_rules.v2.0.json",
    "validation": ROOT / "validation_rules.v2.0.json",
    "templates": ROOT / "clarification_templates.v2.0.json",
    "input_schema": ROOT / "MUNGER_INPUT_SCHEMA.json",
    "output_schema": ROOT / "MUNGER_OUTPUT_SCHEMA.json",
    "canonical_schema": ROOT / "HERO_CANONICAL_SCHEMA.json",
}


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _get_path(data: dict, path: str) -> Any:
    cur = data
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _set_path(data: dict, path: str, value: Any):
    parts = path.split(".")
    cur = data
    for p in parts[:-1]:
        if p not in cur or not isinstance(cur[p], dict):
            cur[p] = {}
        cur = cur[p]
    cur[parts[-1]] = value


def _ensure_list(value: Any) -> Optional[List[str]]:
    if value is None:
        return None
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        parts = re.split(r"[\\n\\r;]+", value)
        out = []
        for p in parts:
            p = p.strip()
            if not p:
                continue
            p = re.sub(r"^[-*•]+\\s*", "", p)
            out.append(p)
        return out
    return None


def _casefold_dedupe(items: List[str]) -> List[str]:
    seen = set()
    out = []
    for item in items:
        key = item.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _normalize_dash_parenthetical(text: str) -> str:
    if "(" in text or ")" in text:
        return text.strip()
    if " - " in text:
        left, right = text.split(" - ", 1)
        return f"{left.strip()} ({right.strip()})"
    if " – " in text:
        left, right = text.split(" – ", 1)
        return f"{left.strip()} ({right.strip()})"
    if " — " in text:
        left, right = text.split(" — ", 1)
        return f"{left.strip()} ({right.strip()})"
    return text.strip()


def _tokens(s: str) -> set:
    return set(re.findall(r"[a-z0-9]+", s.lower()))


def _jaccard(a: str, b: str) -> float:
    ta = _tokens(a)
    tb = _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _map_hero_answers(hero_answers: dict) -> dict:
    mapping = {
        "Q1_problem_customer": "problem_customer",
        "Q2_target_user": "target_user",
        "Q3_success_metric": "success_metric",
        "Q4_must_have_features": "must_have_features",
        "Q5_non_goals": "non_goals",
        "Q6_constraints": "constraints",
        "Q7_data_sources": "data_sources",
        "Q8_integrations": "integrations",
        "Q9_risks": "risks",
        "Q10_shipping_preference": "shipping_preference",
        "Q11_architecture": "architecture",
    }
    hero = {}
    for src, dst in mapping.items():
        if src in hero_answers:
            hero[dst] = hero_answers[src]
        elif dst in hero_answers:
            hero[dst] = hero_answers[dst]
    return hero


def _trim_strings(obj: Any) -> Any:
    if isinstance(obj, str):
        return obj.strip()
    if isinstance(obj, list):
        return [_trim_strings(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _trim_strings(v) for k, v in obj.items()}
    return obj


def _apply_autopatch(hero: dict, rules: dict) -> List[dict]:
    patches = []
    patch_idx = 1

    for rule in rules.get("rules", []):
        rule_id = rule.get("rule_id")
        op = rule.get("operation", {})
        op_type = op.get("type")
        target_paths = rule.get("target_paths", [])

        def record(path: str, before: Any, after: Any):
            nonlocal patch_idx
            if before == after:
                return
            patches.append({
                "patch_id": f"AP{patch_idx:03d}",
                "rule_id": rule_id,
                "op": "replace",
                "path": path,
                "from": None,
                "before": before,
                "after": after,
                "reason": f"autopatch:{rule_id}",
                "confidence": rule.get("confidence", 1.0),
            })
            patch_idx += 1

        if op_type == "trim":
            if "hero.*" in target_paths:
                before = json.loads(json.dumps(hero))
                hero.update(_trim_strings(hero))
                record("hero.*", before, hero)
            continue

        for path in target_paths:
            value = _get_path({"hero": hero}, path)
            if value is None:
                continue

            if op_type == "coerce_boolean" and isinstance(value, str):
                v = value.strip().lower()
                if v in op.get("true_values", []):
                    before = value
                    after = True
                    _set_path({"hero": hero}, path, after)
                    record(path, before, after)
                elif v in op.get("false_values", []):
                    before = value
                    after = False
                    _set_path({"hero": hero}, path, after)
                    record(path, before, after)

            elif op_type == "split_lines_to_array":
                if isinstance(value, str):
                    arr = _ensure_list(value) or []
                    before = value
                    after = arr
                    _set_path({"hero": hero}, path, after)
                    record(path, before, after)

            elif op_type == "dedupe_array_casefold":
                if isinstance(value, list) and all(isinstance(x, str) for x in value):
                    before = value
                    after = _casefold_dedupe(value)
                    _set_path({"hero": hero}, path, after)
                    record(path, before, after)

            elif op_type == "normalize_dash_parenthetical":
                if isinstance(value, list) and all(isinstance(x, str) for x in value):
                    before = value
                    after = [_normalize_dash_parenthetical(x) for x in value]
                    _set_path({"hero": hero}, path, after)
                    record(path, before, after)
    return patches


def _value_as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return " ".join([_value_as_text(v) for v in value])
    if isinstance(value, dict):
        return " ".join([_value_as_text(v) for v in value.values()])
    return str(value)


def _contains_any(value: Any, needles: List[str]) -> bool:
    hay = _value_as_text(value).lower()
    return any(n.lower() in hay for n in needles)


def _matches_regex(value: Any, pattern: str) -> bool:
    if not pattern:
        return False
    return re.search(pattern, _value_as_text(value), re.IGNORECASE) is not None


def _extract_numbers(text: str, pattern: str) -> List[int]:
    nums = []
    for m in re.findall(pattern, text, re.IGNORECASE):
        if isinstance(m, tuple):
            m = [x for x in m if x]
            if not m:
                continue
            m = m[-1]
        try:
            nums.append(int(m))
        except ValueError:
            continue
    return nums


def _detect_issues(hero: dict, rules: dict) -> List[dict]:
    issues = []
    for rule in rules.get("rules", []):
        rule_id = rule.get("rule_id")
        mode = rule.get("mode")
        severity = rule.get("severity", "MEDIUM")
        template_id = rule.get("clarification_template_id")
        description = rule.get("description") or rule.get("category")

        def add_issue(message: str):
            issues.append({
                "rule_id": rule_id,
                "severity": severity,
                "category": rule.get("category"),
                "description": description,
                "message": message,
                "clarification_template_id": template_id,
            })

        if mode == "missing_or_empty":
            for path in rule.get("target_paths", []):
                val = _get_path({"hero": hero}, path)
                if val is None or val == "" or val == [] or val == {}:
                    add_issue(f"Missing or empty: {path}")

        elif mode == "regex":
            for path in rule.get("target_paths", []):
                if path == "all":
                    val = hero
                else:
                    val = _get_path({"hero": hero}, path)
                if val is None:
                    continue
                if _matches_regex(val, rule.get("regex", "")):
                    unless = rule.get("unless_regex")
                    if unless and _matches_regex(val, unless):
                        continue
                    add_issue(f"Regex matched at {path}")

        elif mode == "cross_field":
            primary_path = rule.get("primary_path")
            check_path = rule.get("check_path")
            check_paths = rule.get("check_paths", [])
            primary = _get_path({"hero": hero}, primary_path) if primary_path else None

            pred = rule.get("predicate")
            if pred and "equals" in pred and primary != pred["equals"]:
                continue

            # build check value
            if check_path:
                check_value = _get_path({"hero": hero}, check_path)
            elif check_paths:
                check_value = " ".join(_value_as_text(_get_path({"hero": hero}, p)) for p in check_paths)
            else:
                check_value = None

            if rule.get("must_contain_any"):
                if not _contains_any(check_value, rule["must_contain_any"]):
                    add_issue(f"{check_path} missing required items")
            if rule.get("must_contain_regex"):
                if not _matches_regex(check_value, rule["must_contain_regex"]):
                    add_issue(f"{check_path} missing required pattern")
            if rule.get("should_contain_regex"):
                if not _matches_regex(check_value, rule["should_contain_regex"]):
                    add_issue(f"{check_path} missing recommended pattern")
            if rule.get("must_not_contain_regex"):
                if _matches_regex(check_value, rule["must_not_contain_regex"]):
                    add_issue(f"{check_path} contains forbidden pattern")
            if rule.get("must_be_subset"):
                a = _get_path({"hero": hero}, primary_path) or []
                b = _get_path({"hero": hero}, check_path) or []
                if isinstance(a, list) and isinstance(b, list):
                    aset = {x.casefold() for x in a if isinstance(x, str)}
                    bset = {x.casefold() for x in b if isinstance(x, str)}
                    if not aset.issubset(bset):
                        add_issue("external_apis must be subset of integrations")
            if rule.get("must_equal") is not None:
                if check_value != rule["must_equal"]:
                    add_issue("Cross-field equality check failed")
            if rule.get("must_match_array"):
                primary_arr = _get_path({"hero": hero}, primary_path) or []
                check_arr = _get_path({"hero": hero}, rule.get("check_path")) or []
                filter_primary = rule.get("filter_primary")
                if filter_primary:
                    if re.search(r"[()|?]", filter_primary):
                        primary_arr = [x for x in primary_arr if re.search(filter_primary, x, re.IGNORECASE)]
                    else:
                        primary_arr = [x for x in primary_arr if filter_primary.lower() in x.lower()]
                pa = {x.casefold() for x in primary_arr if isinstance(x, str)}
                ca = {x.casefold() for x in check_arr if isinstance(x, str)}
                if pa != ca and pa:
                    add_issue("Integration list does not match external API list")

        elif mode == "compatibility_check":
            tech_stack = _get_path({"hero": hero}, "hero.architecture.tech_stack") or ""
            integrations = _get_path({"hero": hero}, "hero.integrations") or []
            integrations_text = _value_as_text(integrations)
            for combo in rule.get("incompatible_combinations", []):
                if re.search(combo["tech_stack_pattern"], tech_stack, re.IGNORECASE) and \
                   re.search(combo["integration_pattern"], integrations_text, re.IGNORECASE):
                    add_issue(combo.get("reason", "Incompatible tech/integration"))

        elif mode == "cross_field_numeric":
            q2_text = _value_as_text(_get_path({"hero": hero}, "hero.target_user"))
            econ_text = _value_as_text(_get_path({"hero": hero}, "hero.constraints.economics"))
            q2_nums = _extract_numbers(q2_text, rule.get("extract_from_Q2", ""))
            econ_nums = _extract_numbers(econ_text, rule.get("extract_from_economics", ""))

            q2_max = max(q2_nums) if q2_nums else None

            pricing = _get_path({"hero": hero}, "hero.constraints.economics.pricing.tiers")
            tier_max = None
            if isinstance(pricing, list):
                tier_max = max((t.get("unit_limit", {}).get("max", 0) for t in pricing if isinstance(t, dict)), default=0)
            if tier_max:
                econ_max = tier_max
            else:
                econ_max = max(econ_nums) if econ_nums else None

            if q2_max and econ_max and econ_max < q2_max:
                add_issue("Pricing tier limits do not cover target market upper bound")

        elif mode == "temporal_check":
            q3 = _value_as_text(_get_path({"hero": hero}, "hero.success_metric"))
            q11_days = _get_path({"hero": hero}, "hero.architecture.expected_timeline_days")
            nums = _extract_numbers(q3, rule.get("extract_from_Q3", ""))
            q3_days = nums[0] if nums else None
            if q3_days and q11_days and q3_days < q11_days:
                add_issue("Success metrics timeline precedes build completion timeline")

        elif mode == "business_logic_check":
            tier = _get_path({"hero": hero}, "hero.architecture.minimum_tier")
            days = _get_path({"hero": hero}, "hero.architecture.expected_timeline_days")
            ruleset = rule.get("rules", {})
            if tier and days:
                key = f"tier_{tier}"
                min_days = ruleset.get(key, {}).get("min_days")
                if min_days and days < min_days:
                    add_issue("Timeline too short for minimum tier complexity")

        elif mode == "feature_to_flag_mapping":
            features = _get_path({"hero": hero}, "hero.must_have_features") or []
            if not isinstance(features, list):
                continue
            for pattern, flag in rule.get("mappings", {}).items():
                match = any(re.search(pattern, f, re.IGNORECASE) for f in features if isinstance(f, str))
                if match:
                    flag_val = _get_path({"hero": hero}, f"hero.architecture.{flag}")
                    if flag_val is not True:
                        add_issue(f"Feature implies architecture flag '{flag}'")

        elif mode == "cross_field":
            continue

        elif mode == "keyword_overlap":
            continue

        if mode == "cross_field" and rule.get("comparison") == "keyword_overlap":
            a = _get_path({"hero": hero}, rule.get("primary_path")) or []
            b = _get_path({"hero": hero}, rule.get("check_path")) or []
            if isinstance(a, list) and isinstance(b, list):
                for x in a:
                    for y in b:
                        if isinstance(x, str) and isinstance(y, str) and _jaccard(x, y) >= rule.get("similarity_threshold", 0.7):
                            add_issue("Feature appears in both must-haves and non-goals")
                            break

    return issues


def _basic_schema_validate(hero: dict, canonical_schema: dict) -> List[dict]:
    issues = []
    required = canonical_schema.get("required", [])
    for field in required:
        if field not in hero or hero[field] in (None, "", [], {}):
            issues.append({
                "rule_id": "VR001_schema_valid",
                "severity": "CRITICAL",
                "category": "schema",
                "description": "Missing required field",
                "message": f"Missing required field: {field}",
            })
    arch = hero.get("architecture", {})
    arch_required = canonical_schema.get("properties", {}).get("architecture", {}).get("required", [])
    for field in arch_required:
        if field not in arch:
            issues.append({
                "rule_id": "VR001_schema_valid",
                "severity": "CRITICAL",
                "category": "schema",
                "description": "Missing required architecture field",
                "message": f"Missing architecture field: {field}",
            })
    return issues


def _validate_rules(hero: dict, rules: dict, canonical_schema: dict) -> List[dict]:
    issues = []
    for rule in rules.get("rules", []):
        rule_id = rule.get("rule_id")
        mode = rule.get("mode")
        severity = rule.get("severity", "MEDIUM")
        error = rule.get("error_message", "Validation failed")

        def add_issue(msg: str):
            issues.append({
                "rule_id": rule_id,
                "severity": severity,
                "category": "validation",
                "description": error,
                "message": msg,
            })

        if mode == "json_schema":
            issues.extend(_basic_schema_validate(hero, canonical_schema))

        elif mode == "pricing_sequential":
            tiers = _get_path({"hero": hero}, rule.get("path", "")) or []
            if isinstance(tiers, list) and tiers:
                ids = []
                for t in tiers:
                    if isinstance(t, dict):
                        tid = t.get("tier_id", "")
                        m = re.match(r"^T(\\d+)$", tid)
                        if m:
                            ids.append(int(m.group(1)))
                if ids:
                    ids_sorted = sorted(ids)
                    if ids_sorted != list(range(1, max(ids_sorted) + 1)):
                        add_issue("Tier IDs must be sequential T1..Tn")

        elif mode == "pricing_prices_increasing":
            tiers = _get_path({"hero": hero}, rule.get("path", "")) or []
            if isinstance(tiers, list) and tiers:
                prices = []
                for t in tiers:
                    if isinstance(t, dict) and "price_usd" in t:
                        prices.append(float(t["price_usd"]))
                if prices and prices != sorted(prices):
                    add_issue("Tier prices must be non-decreasing")

        elif mode == "freemium_requires_conversion":
            pricing = _get_path({"hero": hero}, rule.get("path", "")) or {}
            tiers = pricing.get("tiers") if isinstance(pricing, dict) else None
            freemium = pricing.get("freemium") if isinstance(pricing, dict) else None
            has_free = False
            if isinstance(tiers, list):
                for t in tiers:
                    if isinstance(t, dict) and float(t.get("price_usd", 1)) == 0:
                        has_free = True
                        break
            if isinstance(freemium, dict) and freemium.get("has_free") is True:
                has_free = True
            if has_free:
                if not (isinstance(freemium, dict) and freemium.get("conversion_mechanism")):
                    add_issue("Freemium requires conversion mechanism")

        elif mode == "bounds_logical":
            metrics = _get_path({"hero": hero}, rule.get("path", "")) or []
            if isinstance(metrics, list):
                for m in metrics:
                    if not isinstance(m, dict):
                        continue
                    if m.get("min") is None or m.get("target") is None or m.get("max") is None:
                        continue
                    if not (m["min"] <= m["target"] <= m["max"]):
                        add_issue(f"Bounds invalid for {m.get('name', 'metric')}")

        elif mode == "bounds_range_ratio":
            metrics = _get_path({"hero": hero}, rule.get("path", "")) or []
            max_ratio = rule.get("max_ratio", 1.5)
            if isinstance(metrics, list):
                for m in metrics:
                    if not isinstance(m, dict):
                        continue
                    min_v = m.get("min")
                    max_v = m.get("max")
                    if min_v in (None, 0) or max_v is None:
                        continue
                    if max_v > min_v * max_ratio:
                        add_issue(f"Range too wide for {m.get('name', 'metric')}")

        elif mode == "timeline_consistency":
            arch_days = _get_path({"hero": hero}, rule.get("paths", {}).get("arch_days", ""))
            build_time = _get_path({"hero": hero}, rule.get("paths", {}).get("build_time", ""))
            build_days = None
            if isinstance(build_time, int):
                build_days = build_time
            elif isinstance(build_time, str):
                m = re.search(r"(\\d+)\\s*(day|days|week|weeks)", build_time, re.IGNORECASE)
                if m:
                    num = int(m.group(1))
                    unit = m.group(2).lower()
                    build_days = num * 7 if "week" in unit else num
            if arch_days and build_days and arch_days != build_days:
                add_issue("expected_timeline_days contradicts constraints.build_time")

        elif mode == "tier_time_sanity":
            tier = _get_path({"hero": hero}, rule.get("paths", {}).get("tier", ""))
            days = _get_path({"hero": hero}, rule.get("paths", {}).get("arch_days", ""))
            if tier and days:
                for r in rule.get("rules", []):
                    if r.get("tier") == tier and days > r.get("max_days", 10**9):
                        add_issue("Timeline too long for minimum_tier")

        elif mode == "consistency":
            for check in rule.get("checks", []):
                cond = check.get("if", {})
                then = check.get("then", {})
                cond_path = cond.get("path")
                cond_val = _get_path({"hero": hero}, cond_path)
                if "equals" in cond and cond_val != cond["equals"]:
                    continue
                if then.get("must_contain_any"):
                    val = _get_path({"hero": hero}, then.get("path"))
                    if not _contains_any(val, then["must_contain_any"]):
                        add_issue(error)
                if "equals" in then:
                    val = _get_path({"hero": hero}, then.get("path"))
                    if val != then["equals"]:
                        add_issue(error)
                if then.get("must_superset_of_path"):
                    a = _get_path({"hero": hero}, then.get("path")) or []
                    b = _get_path({"hero": hero}, then.get("must_superset_of_path")) or []
                    if isinstance(a, list) and isinstance(b, list):
                        aset = {x.casefold() for x in a if isinstance(x, str)}
                        bset = {x.casefold() for x in b if isinstance(x, str)}
                        if not bset.issubset(aset):
                            add_issue(error)

    return issues


def _validate_response_schema(schema: dict, answers: dict) -> Tuple[bool, str]:
    required = schema.get("required", [])
    for key in required:
        if key not in answers:
            return False, f"Missing required key: {key}"
    for key, spec in schema.get("properties", {}).items():
        if key not in answers:
            continue
        val = answers[key]
        if spec.get("type") == "string" and not isinstance(val, str):
            return False, f"{key} must be string"
        if spec.get("type") == "boolean" and not isinstance(val, bool):
            return False, f"{key} must be boolean"
        if spec.get("type") == "integer" and not isinstance(val, int):
            return False, f"{key} must be integer"
        if spec.get("type") == "array" and not isinstance(val, list):
            return False, f"{key} must be array"
    return True, "ok"


def _apply_template_patch(hero: dict, template: dict, answers: dict, patches: List[dict], patch_idx_start: int) -> int:
    patch_idx = patch_idx_start
    for ap in template.get("apply_patch", []):
        op = ap.get("op")
        if op == "replace":
            from_key = ap.get("from_answer")
            value = answers.get(from_key)
            if ap.get("wrap"):
                wrapped = ap["wrap"].replace("<pricing>", json.dumps(value))
                value = json.loads(wrapped)
            path = ap.get("path")
            before = _get_path({"hero": hero}, path)
            _set_path({"hero": hero}, path, value)
            patches.append({
                "patch_id": f"CP{patch_idx:03d}",
                "rule_id": template.get("template_id"),
                "op": "replace",
                "path": path,
                "from": None,
                "before": before,
                "after": value,
                "reason": "clarification_patch",
                "confidence": 1.0,
            })
            patch_idx += 1
        elif op == "add":
            path = ap.get("path")
            from_key = ap.get("from_answer")
            value = answers.get(from_key)
            before = _get_path({"hero": hero}, path)
            _set_path({"hero": hero}, path, value)
            patches.append({
                "patch_id": f"CP{patch_idx:03d}",
                "rule_id": template.get("template_id"),
                "op": "add",
                "path": path,
                "from": None,
                "before": before,
                "after": value,
                "reason": "clarification_patch",
                "confidence": 1.0,
            })
            patch_idx += 1
        elif op == "merge":
            path = ap.get("path")
            from_key = ap.get("from_answer")
            value = answers.get(from_key, {})
            before = _get_path({"hero": hero}, path) or {}
            after = dict(before)
            if isinstance(value, dict):
                after.update(value)
            _set_path({"hero": hero}, path, after)
            patches.append({
                "patch_id": f"CP{patch_idx:03d}",
                "rule_id": template.get("template_id"),
                "op": "replace",
                "path": path,
                "from": None,
                "before": before,
                "after": after,
                "reason": "clarification_patch",
                "confidence": 1.0,
            })
            patch_idx += 1
        elif op == "replace_many":
            array_key = ap.get("paths_from_array")
            for entry in answers.get(array_key, []):
                path = entry.get("path")
                value = entry.get("value")
                before = _get_path({"hero": hero}, path)
                _set_path({"hero": hero}, path, value)
                patches.append({
                    "patch_id": f"CP{patch_idx:03d}",
                    "rule_id": template.get("template_id"),
                    "op": "replace",
                    "path": path,
                    "from": None,
                    "before": before,
                    "after": value,
                    "reason": "clarification_patch",
                    "confidence": 1.0,
                })
                patch_idx += 1
        elif op == "replace_dynamic":
            path = answers.get(ap.get("path_from_answer"))
            value = answers.get(ap.get("value_from_answer"))
            before = _get_path({"hero": hero}, path)
            _set_path({"hero": hero}, path, value)
            patches.append({
                "patch_id": f"CP{patch_idx:03d}",
                "rule_id": template.get("template_id"),
                "op": "replace",
                "path": path,
                "from": None,
                "before": before,
                "after": value,
                "reason": "clarification_patch",
                "confidence": 1.0,
            })
            patch_idx += 1
        elif op == "replace_map":
            map_key = ap.get("paths_from_object")
            patch_map = answers.get(map_key, {})
            if isinstance(patch_map, dict):
                for path, value in patch_map.items():
                    before = _get_path({"hero": hero}, path)
                    _set_path({"hero": hero}, path, value)
                    patches.append({
                        "patch_id": f"CP{patch_idx:03d}",
                        "rule_id": template.get("template_id"),
                        "op": "replace",
                        "path": path,
                        "from": None,
                        "before": before,
                        "after": value,
                        "reason": "clarification_patch",
                        "confidence": 1.0,
                    })
                    patch_idx += 1
    return patch_idx


def _score_issues(issues: List[dict]) -> Tuple[int, int]:
    score = 100
    critical = 0
    for i in issues:
        sev = i.get("severity", "MEDIUM")
        if sev == "CRITICAL":
            score -= 25
            critical += 1
        elif sev == "HIGH":
            score -= 10
        elif sev == "MEDIUM":
            score -= 3
        elif sev == "LOW":
            score -= 1
    return max(score, 0), critical


def _build_clarifications(issues: List[dict], templates: dict, loop: int) -> List[dict]:
    template_map = {t["template_id"]: t for t in templates.get("templates", [])}
    max_items = 5
    if loop == 1:
        sev_allowed = {"CRITICAL"}
    else:
        sev_allowed = {"CRITICAL", "HIGH", "MEDIUM"}

    clarifications = []
    for issue in issues:
        if issue.get("severity") not in sev_allowed:
            continue
        tid = issue.get("clarification_template_id")
        if not tid or tid not in template_map:
            continue
        tmpl = template_map[tid]
        clarifications.append({
            "template_id": tid,
            "title": tmpl.get("title"),
            "question": tmpl.get("question"),
            "response_schema": tmpl.get("response_schema"),
            "issue": issue,
        })
        if len(clarifications) >= max_items:
            break
    return clarifications


def run_munger(input_data: dict, clarifications: Optional[List[dict]], loop: int) -> dict:
    rules_autopatch = _load_json(FILES["autopatch"])
    rules_detection = _load_json(FILES["detection"])
    rules_validation = _load_json(FILES["validation"])
    templates = _load_json(FILES["templates"])
    canonical_schema = _load_json(FILES["canonical_schema"])

    hero = _map_hero_answers(input_data.get("hero_answers", {}))

    applied_patches = []
    applied_patches.extend(_apply_autopatch(hero, rules_autopatch))

    if clarifications:
        template_map = {t["template_id"]: t for t in templates.get("templates", [])}
        patch_idx = 1 + len(applied_patches)
        for env in clarifications:
            tid = env.get("template_id")
            answers = env.get("answers", {})
            tmpl = template_map.get(tid)
            if not tmpl:
                continue
            ok, msg = _validate_response_schema(tmpl.get("response_schema", {}), answers)
            if not ok:
                continue
            patch_idx = _apply_template_patch(hero, tmpl, answers, applied_patches, patch_idx)

    detection_issues = _detect_issues(hero, rules_detection)
    validation_issues = _validate_rules(hero, rules_validation, canonical_schema)
    issues = detection_issues + validation_issues

    score, critical = _score_issues(issues)

    status = "PASS"
    if critical == 0 and score >= 80:
        status = "PASS"
    else:
        if loop >= 2 and critical > 0:
            status = "REJECTED"
        else:
            status = "NEEDS_CLARIFICATION"

    report = {
        "status": status,
        "score": score,
        "critical_issues": critical,
        "issues": issues,
        "applied_patches": applied_patches,
        "versions": {
            "munger_version": MUNGER_VERSION,
            "ruleset_version": rules_autopatch.get("ruleset_version", "2.0.0"),
            "input_schema_version": "2.0",
            "output_schema_version": "2.0",
        },
    }

    if status == "NEEDS_CLARIFICATION":
        report["clarifications"] = _build_clarifications(issues, templates, loop)

    return {
        "startup_idea_id": input_data.get("startup_idea_id", ""),
        "startup_name": input_data.get("startup_name", ""),
        "startup_description": input_data.get("startup_description", ""),
        "clean_hero_answers": hero,
        "munger_report": report,
    }


def main():
    parser = argparse.ArgumentParser(description="FO/AF Munger v2.0.0")
    parser.add_argument("input_json", help="Hero input JSON (MUNGER_INPUT_SCHEMA)")
    parser.add_argument("--out", help="Write output JSON to path")
    parser.add_argument("--clarifications", help="Clarification responses JSON file")
    parser.add_argument("--loop", type=int, default=1, choices=[1, 2], help="Clarification loop number")
    args = parser.parse_args()

    input_path = Path(args.input_json)
    if not input_path.exists():
        print(f"Error: {input_path} not found")
        sys.exit(1)

    input_data = _load_json(input_path)
    missing = [k for k in ("startup_idea_id", "startup_name", "startup_description", "hero_answers") if k not in input_data]
    if missing:
        print(f"Error: missing required fields: {', '.join(missing)}")
        sys.exit(2)

    clarifications = None
    if args.clarifications:
        clarifications = _load_json(Path(args.clarifications))
        if not isinstance(clarifications, list):
            print("Error: clarifications file must be a list of envelopes")
            sys.exit(3)

    output = run_munger(input_data, clarifications, args.loop)

    output_json = json.dumps(output, indent=2, ensure_ascii=False)
    if args.out:
        Path(args.out).write_text(output_json, encoding="utf-8")
        print(f"Wrote: {args.out}")
    else:
        print(output_json)


if __name__ == "__main__":
    main()
