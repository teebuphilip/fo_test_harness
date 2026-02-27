#!/usr/bin/env python3
"""
Post-Intake Assist v2.1
Deterministic validation + issue detection for Intake outputs (Block A + Block B).
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, List, Tuple


ROOT = Path(__file__).resolve().parent

FILES = {
    "detection": ROOT / "post_intake_detection_rules.v2.1.json",
    "validation": ROOT / "post_intake_validation_rules.v2.1.json",
    "build_contract_schema": ROOT / "BUILD_CONTRACT_SCHEMA.json",
    "revision_templates": ROOT / "post_intake_revision_templates.v2.1.json",
    "vocabulary": ROOT / "post_intake_vocabulary.v2.1.json",
    "block_a_schema": ROOT / "BLOCK_A_SCHEMA.json",
    "block_b_schema": ROOT / "BLOCK_B_SCHEMA.json",
    "approval_schema": ROOT / "HERO_APPROVAL_TOKEN_SCHEMA.json",
    "output_schema": ROOT / "POST_INTAKE_ASSIST_OUTPUT_SCHEMA.json",
}


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _get_path(data: dict, path: str) -> Any:
    cur = data
    for part in path.split("."):
        if "[" in part and part.endswith("]"):
            name, idx = part[:-1].split("[", 1)
            if name:
                if not isinstance(cur, dict) or name not in cur:
                    return None
                cur = cur[name]
            try:
                i = int(idx)
                cur = cur[i]
            except Exception:
                return None
        else:
            if not isinstance(cur, dict) or part not in cur:
                return None
            cur = cur[part]
    return cur


def _resolve_values(data: dict, path: str) -> List[Any]:
    if "[*]" not in path:
        val = _get_path(data, path)
        return [] if val is None else [val]
    base, rest = path.split("[*]", 1)
    base = base.rstrip(".")
    arr = _get_path(data, base)
    if not isinstance(arr, list):
        return []
    values = []
    for item in arr:
        if rest.startswith("."):
            values.extend(_resolve_values(item, rest[1:]))
        elif rest == "":
            values.append(item)
        else:
            values.extend(_resolve_values(item, rest))
    return values


def _textify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return " ".join(_textify(v) for v in value)
    if isinstance(value, dict):
        return " ".join(_textify(v) for v in value.values())
    return str(value)


def _contains_any(text: str, items: List[str]) -> bool:
    t = text.lower()
    return any(i.lower() in t for i in items)


def _issue(rule: dict, message: str) -> dict:
    return {
        "rule_id": rule.get("rule_id"),
        "severity": rule.get("severity", "MEDIUM"),
        "mode": rule.get("mode"),
        "message": message,
        "revision_template_id": rule.get("revision_template_id"),
    }


def _basic_schema_validate(target: Any, schema: dict, rule: dict) -> List[dict]:
    issues = []
    if target is None:
        issues.append(_issue(rule, "Schema target missing"))
        return issues
    if not isinstance(target, dict):
        issues.append(_issue(rule, "Schema target is not an object"))
        return issues
    required = schema.get("required", [])
    for k in required:
        if k not in target:
            issues.append(_issue(rule, f"Missing required field: {k}"))
    return issues


def _detect_issues(data: dict, rules: dict, vocab: dict) -> List[dict]:
    issues = []
    for rule in rules.get("rules", []):
        mode = rule.get("mode")

        if mode == "pricing_drift":
            baseline = _get_path(data, rule["paths"]["baseline"])
            current = _get_path(data, rule["paths"]["current"])
            if baseline is not None and current is not None and baseline != current:
                issues.append(_issue(rule, "Pricing drift from baseline"))

        elif mode == "path_missing":
            if _get_path(data, rule["target_path"]) is None:
                issues.append(_issue(rule, f"Missing path: {rule['target_path']}"))

        elif mode == "pricing_tier_gap":
            tiers = _get_path(data, rule["path"]) or []
            if isinstance(tiers, list):
                ids = []
                for t in tiers:
                    if isinstance(t, dict):
                        m = re.match(r"^T(\\d+)$", t.get("tier_id", ""))
                        if m:
                            ids.append(int(m.group(1)))
                if ids:
                    ids_sorted = sorted(ids)
                    if ids_sorted != list(range(1, max(ids_sorted) + 1)):
                        issues.append(_issue(rule, "Tier IDs not sequential"))

        elif mode == "pricing_limits_invalid":
            tiers = _get_path(data, rule["path"]) or []
            for t in tiers if isinstance(tiers, list) else []:
                if not isinstance(t, dict):
                    continue
                unit_limit = t.get("unit_limit", {})
                if not unit_limit or unit_limit.get("max", 0) <= 0:
                    issues.append(_issue(rule, "Invalid unit_limit"))
                    break

        elif mode == "freemium_requires_conversion":
            pricing = _get_path(data, rule["path"]) or {}
            tiers = pricing.get("tiers") if isinstance(pricing, dict) else None
            freemium = pricing.get("freemium") if isinstance(pricing, dict) else None
            has_free = False
            if isinstance(tiers, list):
                has_free = any(isinstance(t, dict) and float(t.get("price_usd", 1)) == 0 for t in tiers)
            if isinstance(freemium, dict) and freemium.get("has_free") is True:
                has_free = True
            if has_free and not (isinstance(freemium, dict) and freemium.get("conversion_mechanism")):
                issues.append(_issue(rule, "Freemium missing conversion mechanism"))

        elif mode == "regex":
            paths = rule.get("target_paths", [])
            for p in paths:
                for val in _resolve_values(data, p):
                    if re.search(rule.get("regex", ""), _textify(val), re.IGNORECASE):
                        issues.append(_issue(rule, f"Regex matched at {p}"))
                        break

        elif mode == "equals":
            val = _get_path(data, rule["path"])
            if val == rule.get("equals"):
                issues.append(_issue(rule, f"Equals disallowed value at {rule['path']}"))

        elif mode == "pricing_unit_unknown":
            tiers = _get_path(data, rule["path"]) or []
            for t in tiers if isinstance(tiers, list) else []:
                unit = (t.get("unit_limit") or {}).get("unit")
                if unit == "unknown":
                    issues.append(_issue(rule, "Pricing unit is unknown"))
                    break

        elif mode == "bounds_missing_when_referenced":
            bounds = _get_path(data, rule["paths"]["bounds"])
            texts = []
            for p in rule["paths"]["texts"]:
                texts.extend(_resolve_values(data, p))
            if texts and not bounds:
                issues.append(_issue(rule, "Quant bounds referenced but missing"))

        elif mode == "bounds_logical":
            metrics = _get_path(data, rule["path"]) or []
            for m in metrics if isinstance(metrics, list) else []:
                if not isinstance(m, dict):
                    continue
                if m.get("min") is None or m.get("target") is None or m.get("max") is None:
                    continue
                if not (m["min"] <= m["target"] <= m["max"]):
                    issues.append(_issue(rule, "Bounds not logical"))
                    break

        elif mode == "bounds_missing_units":
            metrics = _get_path(data, rule["path"]) or []
            for m in metrics if isinstance(metrics, list) else []:
                if not m.get("unit"):
                    issues.append(_issue(rule, "Metric missing unit"))
                    break

        elif mode == "bounds_range_ratio":
            metrics = _get_path(data, rule["path"]) or []
            max_ratio = rule.get("max_ratio", 2.0)
            for m in metrics if isinstance(metrics, list) else []:
                min_v = m.get("min")
                max_v = m.get("max")
                if min_v in (None, 0) or max_v is None:
                    continue
                if max_v > min_v * max_ratio:
                    issues.append(_issue(rule, "Bounds range too wide"))
                    break

        elif mode == "keyword":
            keywords = vocab.get(rule.get("keywords_ref", ""), [])
            for p in rule.get("target_paths", []):
                for val in _resolve_values(data, p):
                    if _contains_any(_textify(val), keywords):
                        issues.append(_issue(rule, f"Keyword match at {p}"))
                        break

        elif mode == "array_items_missing_field":
            arr = _get_path(data, rule["path"]) or []
            field = rule["field"]
            for item in arr if isinstance(arr, list) else []:
                if not isinstance(item, dict) or field not in item:
                    issues.append(_issue(rule, f"Missing {field} in {rule['path']}"))
                    break

        elif mode == "feature_count_vs_tier":
            tier = _get_path(data, rule["paths"]["tier"])
            deliverables = _get_path(data, rule["paths"]["deliverables"]) or []
            if tier and isinstance(deliverables, list):
                for t in rule.get("thresholds", []):
                    if t["tier"] == tier and len(deliverables) > t["max_deliverables"]:
                        issues.append(_issue(rule, "Deliverable count exceeds tier"))
                        break

        elif mode == "phase_label_missing":
            tasks = _get_path(data, rule["path"]) or []
            if isinstance(tasks, list):
                unlabeled = [t for t in tasks if isinstance(t, dict) and "phase" not in t]
                if unlabeled:
                    issues.append(_issue(rule, "Tasks missing phase labels"))

        elif mode == "consistency":
            for check in rule.get("checks", []):
                cond = check.get("if", {})
                then = check.get("then", {})
                cond_val = _get_path(data, cond.get("path"))
                if "equals" in cond and cond_val != cond["equals"]:
                    continue
                val = _get_path(data, then.get("path"))
                if then.get("must_contain_any") and not _contains_any(_textify(val), then["must_contain_any"]):
                    issues.append(_issue(rule, "Consistency missing required item"))
                if "equals" in then and val != then["equals"]:
                    issues.append(_issue(rule, "Consistency equality failed"))

        elif mode == "auth_provider_presence":
            flag = _get_path(data, rule["paths"]["flag"])
            integrations = _get_path(data, rule["paths"]["integrations"])
            if flag is True and not _contains_any(_textify(integrations), rule.get("acceptable", [])):
                issues.append(_issue(rule, "Auth provider missing"))

        elif mode == "background_provider_presence":
            flag = _get_path(data, rule["paths"]["flag"])
            integrations = _get_path(data, rule["paths"]["integrations"])
            if flag is True and not _contains_any(_textify(integrations), rule.get("acceptable", [])):
                issues.append(_issue(rule, "Background provider missing"))

        elif mode == "set_subset":
            subset = _get_path(data, rule["paths"]["subset"]) or []
            superset = _get_path(data, rule["paths"]["superset"]) or []
            if isinstance(subset, list) and isinstance(superset, list):
                sset = {x.casefold() for x in subset if isinstance(x, str)}
                tset = {x.casefold() for x in superset if isinstance(x, str)}
                if not sset.issubset(tset):
                    issues.append(_issue(rule, "External APIs not in integrations"))

        elif mode == "flag_requires_feature_keyword":
            flag = _get_path(data, rule["paths"]["flag"])
            if flag is True:
                features = []
                for p in [rule["paths"]["features"]]:
                    features.extend(_resolve_values(data, p))
                if not _contains_any(_textify(features), rule.get("keywords", [])):
                    issues.append(_issue(rule, "Flag missing matching deliverable keyword"))

        elif mode == "timeline_vs_hours":
            timeline = _get_path(data, rule["paths"]["timeline_days"]) or 0
            tasks = _get_path(data, rule["paths"]["tasks"]) or []
            hours_per_day = rule.get("hours_per_day", 6)
            total_hours = 0
            for t in tasks if isinstance(tasks, list) else []:
                if isinstance(t, dict):
                    total_hours += float(t.get("estimated_hours", 0) or 0)
            if timeline and total_hours > timeline * hours_per_day:
                issues.append(_issue(rule, "Task hours exceed timeline capacity"))

        elif mode == "tier_time_sanity":
            tier = _get_path(data, rule["paths"]["tier"])
            days = _get_path(data, rule["paths"]["timeline_days"])
            if tier and days:
                for r in rule.get("rules", []):
                    if r.get("tier") == tier and days > r.get("max_days", 10**9):
                        issues.append(_issue(rule, "Timeline too long for tier"))

        elif mode == "acceptance_mapping":
            criteria = _get_path(data, rule["paths"]["criteria"]) or []
            deliverables = _get_path(data, rule["paths"]["deliverables"]) or []
            deliverable_ids = {d.get("deliverable_id") for d in deliverables if isinstance(d, dict)}
            for c in criteria if isinstance(criteria, list) else []:
                if isinstance(c, dict):
                    if c.get("deliverable_id") not in deliverable_ids:
                        issues.append(_issue(rule, "Acceptance criteria unmapped"))
                        break

    return issues


def _validate_rules(data: dict, rules: dict) -> List[dict]:
    issues = []
    for rule in rules.get("rules", []):
        mode = rule.get("mode")
        if mode == "json_schema":
            schema_ref = rule.get("schema_ref")
            if schema_ref == "BLOCK_A_SCHEMA":
                schema = _load_json(FILES["block_a_schema"])
                target = _get_path(data, rule.get("target_path", "block_a_final"))
                issues.extend(_basic_schema_validate(target, schema, rule))
            elif schema_ref == "BLOCK_B_SCHEMA":
                schema = _load_json(FILES["block_b_schema"])
                target = _get_path(data, rule.get("target_path", "block_b_final"))
                issues.extend(_basic_schema_validate(target, schema, rule))
            elif schema_ref == "BUILD_CONTRACT_SCHEMA":
                schema = _load_json(FILES["build_contract_schema"])
                target = _get_path(data, rule.get("target_path", "build_contract"))
                issues.extend(_basic_schema_validate(target, schema, rule))
            continue
    return issues


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


def _build_contract(data: dict) -> dict:
    block_a = data.get("block_a_final", {})
    block_b = data.get("block_b_final", {})
    return {
        "contract_version": "2.1.0",
        "pricing": block_a.get("pricing"),
        "architecture": block_a.get("architecture"),
        "integrations": block_a.get("integrations"),
        "deliverables": block_b.get("deliverables"),
        "acceptance_criteria": block_a.get("acceptance_criteria"),
        "quantitative_bounds": block_a.get("quantitative_bounds"),
    }


def run_post_intake_assist(input_data: dict) -> dict:
    detection_rules = _load_json(FILES["detection"])
    validation_rules = _load_json(FILES["validation"])
    vocab = _load_json(FILES["vocabulary"]) if FILES["vocabulary"].exists() else {}

    issues = _detect_issues(input_data, detection_rules, vocab)
    issues += _validate_rules(input_data, validation_rules)

    score, critical = _score_issues(issues)
    status = "PASS" if critical == 0 and score >= 80 else "NEEDS_REVISION"

    report = {
        "status": status,
        "score": score,
        "critical_issues": critical,
        "issues": issues,
        "versions": {
            "post_intake_assist_version": "2.1.0",
            "ruleset_version": detection_rules.get("ruleset_version", "2.1.0"),
        },
    }
    if status != "PASS":
        report["revision_requests"] = [
            {
                "template_id": i.get("revision_template_id"),
                "issue": i,
            }
            for i in issues if i.get("revision_template_id")
        ][:5]

    return {
        "build_contract": _build_contract(input_data),
        "post_intake_report": report,
    }


def main():
    parser = argparse.ArgumentParser(description="Post-Intake Assist v2.1")
    parser.add_argument("input_json", help="Input JSON containing block_a_final and block_b_final")
    parser.add_argument("--out", help="Write output JSON to path")
    args = parser.parse_args()

    path = Path(args.input_json)
    if not path.exists():
        print(f"Error: {path} not found")
        sys.exit(1)

    data = _load_json(path)
    output = run_post_intake_assist(data)
    output_json = json.dumps(output, indent=2)

    if args.out:
        Path(args.out).write_text(output_json, encoding="utf-8")
        print(f"Wrote: {args.out}")
    else:
        print(output_json)


if __name__ == "__main__":
    main()
