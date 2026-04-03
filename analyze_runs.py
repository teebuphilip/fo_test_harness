#!/usr/bin/env python3
"""
analyze_runs.py - Run Analysis Tool

Mines harness run logs to identify failure patterns, iteration waste,
and prompt improvement signals. Produces console tables + output files.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent


# ----------------------------- Helpers --------------------------------------


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _safe_int(val: str) -> Optional[int]:
    try:
        return int(val)
    except Exception:
        return None


def _normalize_reason(text: str) -> str:
    t = text.strip().lower()
    # Canonical buckets for common noisy QA defects
    if "getaccesstokensilently" in t or "get access token silently" in t:
        return "auth0 getaccesstokensilently misuse"
    if ".tsx" in t or "tsx" in t:
        return "frontend uses tsx instead of jsx"
    if "compiled file" in t or "compiled" in t:
        return "compiled artifacts included"
    if "roles_permissions" in t:
        return "missing roles_permissions object"
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _parse_iteration_num(path_str: str) -> Optional[int]:
    m = re.search(r"iteration_(\d+)_artifacts", path_str)
    if not m:
        return None
    return _safe_int(m.group(1))


def _startup_id_from_run_dir(name: str) -> str:
    m = re.match(r"(.+?)_BLOCK_[AB]_", name)
    if m:
        return m.group(1)
    # fallback: strip trailing timestamp block
    m2 = re.match(r"(.+?)_20\d{6}_\d{6}$", name)
    if m2:
        return m2.group(1)
    return name


def _classify_run(intake_path: Optional[str], run_dir_name: str) -> Tuple[str, Optional[str]]:
    """
    Returns (run_type, feature_slug)
    run_type: phase1 | feature | main
    """
    if "_p1_" in run_dir_name or (intake_path and intake_path.endswith("_phase1.json")):
        return "phase1", None
    if intake_path and "_feature_" in intake_path:
        slug = Path(intake_path).stem.split("_feature_", 1)[-1]
        return "feature", slug
    if "_feature_" in run_dir_name:
        slug = run_dir_name.split("_feature_", 1)[-1]
        return "feature", slug
    return "main", None


def _list_iteration_dirs(run_dir: Path) -> List[Path]:
    build_dir = run_dir / "build"
    if not build_dir.exists():
        # sometimes nested under _harness
        build_dir = run_dir / "_harness" / "build"
    if not build_dir.exists():
        return []
    return sorted(build_dir.glob("iteration_*_artifacts"))


def _latest_iteration_num(run_dir: Path) -> int:
    iters = [_parse_iteration_num(p.name) for p in _list_iteration_dirs(run_dir)]
    iters = [i for i in iters if i is not None]
    return max(iters) if iters else 0


def _qa_reports(run_dir: Path) -> List[Path]:
    qa_dir = run_dir / "qa"
    if not qa_dir.exists():
        return []
    return sorted(qa_dir.glob("iteration_*_qa_report.txt"))


def _latest_build_state(run_dir: Path) -> Optional[Dict[str, Any]]:
    build_dir = run_dir / "build"
    if not build_dir.exists():
        build_dir = run_dir / "_harness" / "build"
    if not build_dir.exists():
        return None
    # Find highest iteration build_state.json
    best_path = None
    best_iter = -1
    for p in build_dir.glob("iteration_*_artifacts/build_state.json"):
        it = _parse_iteration_num(str(p.parent))
        if it is None:
            continue
        if it > best_iter:
            best_iter = it
            best_path = p
    if not best_path:
        return None
    return _read_json(best_path)


def _status_from_build_state(state: Optional[Dict[str, Any]]) -> str:
    if not state or not isinstance(state, dict):
        return "UNKNOWN"
    if state.get("state") == "COMPLETED_CLOSED":
        return "COMPLETE"
    if state.get("state") == "FAILED" or state.get("terminal") is True:
        return "FAILED"
    return "UNKNOWN"

def _parse_qa_report(path: Path) -> Dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    defects = []
    total_defects = None
    m = re.search(r"Total defects found:\s*(\d+)", text)
    if m:
        total_defects = _safe_int(m.group(1))

    # Parse DEFECT blocks
    blocks = re.split(r"\n(?=DEFECT-\d+:)", text)
    for block in blocks:
        if not block.strip().startswith("DEFECT-"):
            continue
        problem = None
        severity = None
        location = None
        for line in block.splitlines():
            line = line.strip()
            if re.search(r"(?:^|[-\s])Problem:\s*", line):
                problem = re.split(r"Problem:\s*", line, maxsplit=1)[-1].strip()
            elif re.search(r"(?:^|[-\s])Severity:\s*", line):
                severity = re.split(r"Severity:\s*", line, maxsplit=1)[-1].strip()
            elif re.search(r"(?:^|[-\s])Location:\s*", line):
                location = re.split(r"Location:\s*", line, maxsplit=1)[-1].strip()
        if problem:
            defects.append({
                "problem": problem,
                "severity": severity or "",
                "location": location or "",
            })

    # Verdict
    verdict = None
    vm = re.search(r"QA STATUS:\s*([A-Z_]+)", text)
    if vm:
        verdict = vm.group(1)

    return {
        "total_defects": total_defects if total_defects is not None else len(defects),
        "defects": defects,
        "verdict": verdict or "",
    }


def _artifact_manifest(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    data = _read_json(path)
    if not isinstance(data, dict):
        return None
    return data


def _manifests_equal(m1: Optional[Dict[str, Any]], m2: Optional[Dict[str, Any]]) -> bool:
    if m1 is None or m2 is None:
        return False
    return m1 == m2


# ----------------------------- Log parsing ----------------------------------


def parse_riaf_logs(log_paths: List[Path]) -> Dict[str, Any]:
    """
    Returns dict keyed by startup_id with:
      - mode
      - integration_fix_passes
      - gate_failures (G2/G3/G4)
      - feature_iters {feature_name: max_iter}
      - phase1_iters
      - status (COMPLETE/FAILED) if present
    """
    result: Dict[str, Any] = {}

    for log_path in log_paths:
        text = log_path.read_text(encoding="utf-8", errors="ignore")
        lines = text.splitlines()

        startup_id = None
        mode = None
        status = None

        # Track sections
        current_section = "unknown"
        section_iters = defaultdict(int)  # section -> max iter
        feature_iters = {}
        integration_fix_passes = 0
        gate_failures = Counter()

        for line in lines:
            if "Startup ID" in line:
                m = re.search(r"Startup ID\s*:\s*(.+)", line)
                if m:
                    startup_id = m.group(1).strip()
            if "Mode" in line:
                m = re.search(r"Mode\s*:\s*(\w+)", line)
                if m:
                    mode = m.group(1).strip().lower()

            # Section markers
            if "STEP 2" in line and "Phase 1" in line:
                current_section = "phase1"
            m = re.search(r"Feature \d+/\d+:\s*(.+)$", line)
            if m:
                feature_name = m.group(1).strip()
                current_section = f"feature::{feature_name}"
            m = re.search(r"ENTITY \d+/\d+ COMPLETE", line)
            if m:
                current_section = "phase1"

            # Iteration artifacts
            if "iteration_" in line and "_artifacts" in line:
                it = _parse_iteration_num(line)
                if it:
                    section_iters[current_section] = max(section_iters[current_section], it)

            # Integration fix passes
            if "Integration issues found" in line and "fix pass" in line:
                integration_fix_passes += 1

            # Gate failures
            gm = re.search(r"Gate\s*([234]).*FAIL", line, re.IGNORECASE)
            if gm:
                gate_failures[f"G{gm.group(1)}"] += 1

            # Status
            if "✓ Already complete" in line or "COMPLETE" in line:
                status = "COMPLETE"
            if "FAILED" in line and "FAILED" in line:
                if status != "COMPLETE":
                    status = "FAILED"

        # Map section_iters to phase/feature
        for k, v in section_iters.items():
            if k == "phase1":
                pass
            elif k.startswith("feature::"):
                feature_iters[k.split("feature::", 1)[-1]] = v

        if startup_id:
            result[startup_id] = {
                "mode": mode,
                "integration_fix_passes": integration_fix_passes,
                "gate_failures": gate_failures,
                "feature_iters": feature_iters,
                "phase1_iters": section_iters.get("phase1", 0),
                "status": status or "UNKNOWN",
                "log_path": str(log_path),
            }

    return result


# ----------------------------- Run dir parsing -------------------------------


def parse_run_dirs(run_dirs: List[Path]) -> Dict[str, Any]:
    """
    Returns dict keyed by run_dir with per-run data.
    """
    runs: Dict[str, Any] = {}

    for run_dir in run_dirs:
        run_name = run_dir.name
        startup_id = _startup_id_from_run_dir(run_name)
        iters = _latest_iteration_num(run_dir)
        build_state = _latest_build_state(run_dir)
        status = _status_from_build_state(build_state)

        # Intake path (from integration_issues.json if present)
        intake_path = None
        integration_issues_path = run_dir / "integration_issues.json"
        integration_issues = None
        if integration_issues_path.exists():
            integration_issues = _read_json(integration_issues_path)
            if integration_issues and isinstance(integration_issues, dict):
                intake_path = integration_issues.get("intake_path")

        run_type, feature_slug = _classify_run(intake_path, run_name)

        # QA reports
        qa_reports = _qa_reports(run_dir)
        qa_summary = []
        qa_fail_iterations = []
        qa_defect_reasons = []
        for rpt in qa_reports:
            data = _parse_qa_report(rpt)
            qa_summary.append((rpt.name, data))
            if data["total_defects"] and data["total_defects"] > 0:
                iter_num = _parse_iteration_num(rpt.name.replace("_qa_report.txt", "_artifacts"))
                if iter_num:
                    qa_fail_iterations.append(iter_num)
                for d in data["defects"]:
                    qa_defect_reasons.append(d["problem"])

        # Integration issues
        integ_counts = {"HIGH": 0, "MEDIUM": 0}
        integ_reasons = []
        if integration_issues and isinstance(integration_issues, dict):
            integ_counts["HIGH"] = integration_issues.get("high_severity", 0) or 0
            integ_counts["MEDIUM"] = integration_issues.get("medium_severity", 0) or 0
            for issue in integration_issues.get("issues", []) or []:
                if isinstance(issue, dict) and issue.get("issue"):
                    integ_reasons.append(issue.get("issue"))

        # Fix pass detection
        fix_pass = False
        build_dir = run_dir / "build"
        if build_dir.exists():
            if list(build_dir.glob("iteration_*_fix.txt")):
                fix_pass = True

        # False positive heuristic
        false_pos = 0
        false_pos_total = 0
        false_pos_defects = []
        # Compare iteration N and N+1 if QA defects drop to 0
        qa_by_iter = {}
        for rpt_name, data in qa_summary:
            iter_num = _parse_iteration_num(rpt_name.replace("_qa_report.txt", "_artifacts"))
            if iter_num:
                qa_by_iter[iter_num] = data
        for n in sorted(qa_by_iter.keys()):
            if n + 1 not in qa_by_iter:
                continue
            if qa_by_iter[n]["total_defects"] > 0 and qa_by_iter[n + 1]["total_defects"] == 0:
                m1 = _artifact_manifest(run_dir / "build" / f"iteration_{n:02d}_artifacts" / "artifact_manifest.json")
                m2 = _artifact_manifest(run_dir / "build" / f"iteration_{n+1:02d}_artifacts" / "artifact_manifest.json")
                false_pos_total += 1
                if _manifests_equal(m1, m2):
                    false_pos += 1
                    for d in qa_by_iter[n].get("defects", []):
                        if d.get("problem"):
                            false_pos_defects.append({
                                "startup_id": startup_id,
                                "iteration": n,
                                "problem": d.get("problem")
                            })

        runs[run_name] = {
            "startup_id": startup_id,
            "run_dir": str(run_dir),
            "run_type": run_type,
            "feature_slug": feature_slug,
            "iterations": iters,
            "status": status,
            "qa_fail_iterations": qa_fail_iterations,
            "qa_defect_reasons": qa_defect_reasons,
            "integration_counts": integ_counts,
            "integration_reasons": integ_reasons,
            "fix_pass": fix_pass,
            "false_pos_est": false_pos,
            "false_pos_total": false_pos_total,
            "false_pos_defects": false_pos_defects,
            "intake_path": intake_path,
        }

    return runs


# ----------------------------- Spec injection -------------------------------


def detect_spec_injection(intake_root: Path) -> Dict[str, bool]:
    """
    Return map startup_id -> has_spec
    """
    has_spec = {}
    for p in intake_root.rglob("*_feature_*.json"):
        data = _read_json(p)
        if not data or not isinstance(data, dict):
            continue
        startup_id = data.get("startup_idea_id") or _startup_id_from_run_dir(p.stem)
        feature_spec = None
        phase_ctx = data.get("_phase_context") if isinstance(data.get("_phase_context"), dict) else None
        if phase_ctx:
            feature_spec = phase_ctx.get("feature_spec")
        has_spec[startup_id] = bool(feature_spec)
    return has_spec


# ----------------------------- Output builders -------------------------------


def build_failure_patterns(runs: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Counter]:
    """
    Returns (patterns, gate_failures_counter).
    Gate breakdown is inferred from QA defects when riaf logs are missing.
    """
    reason_counter = Counter()
    reason_examples: Dict[str, Dict[str, Any]] = {}
    gate_failures = Counter()

    for run_name, r in runs.items():
        startup_id = r["startup_id"]
        # Gate 2 failures: QA defects (heuristic when riaf logs are missing)
        if r["qa_defect_reasons"]:
            gate_failures["G2"] += len(r["qa_defect_reasons"])
        for reason in r["qa_defect_reasons"]:
            key = _normalize_reason(reason)
            reason_counter[key] += 1
            if key not in reason_examples:
                reason_examples[key] = {
                    "reason": reason,
                    "gate": "G2",
                    "ideas": set([startup_id]),
                }
            else:
                reason_examples[key]["ideas"].add(startup_id)

        # Integration issues
        for reason in r["integration_reasons"]:
            key = _normalize_reason(reason)
            reason_counter[key] += 1
            if key not in reason_examples:
                reason_examples[key] = {
                    "reason": reason,
                    "gate": "G6",
                    "ideas": set([startup_id]),
                }
            else:
                reason_examples[key]["ideas"].add(startup_id)

        if r["integration_reasons"]:
            gate_failures["G6"] += len(r["integration_reasons"])

    patterns = []
    for key, count in reason_counter.most_common():
        ex = reason_examples[key]
        patterns.append({
            "reason": ex["reason"],
            "count": count,
            "gate": ex["gate"],
            "ideas": sorted(ex["ideas"]),
            "idea_count": len(ex["ideas"]),
        })

    # Prefer sorting by idea_count, then count
    patterns.sort(key=lambda p: (p["idea_count"], p["count"]), reverse=True)

    return patterns, gate_failures


def print_iteration_table(summary_rows: List[Dict[str, Any]]) -> None:
    headers = ["startup_id", "phase1_iters", "features", "avg_feat_iters", "total_iters", "status"]
    widths = {h: max(len(h), 12) for h in headers}
    for row in summary_rows:
        for h in headers:
            widths[h] = max(widths[h], len(str(row.get(h, ""))))

    line = " | ".join(h.ljust(widths[h]) for h in headers)
    sep = "-+-".join("-" * widths[h] for h in headers)
    print(line)
    print(sep)
    for row in summary_rows:
        print(" | ".join(str(row.get(h, "")).ljust(widths[h]) for h in headers))


# ----------------------------- Main ------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze FO harness runs")
    parser.add_argument("--startup-id", help="Filter to a single startup id")
    parser.add_argument("--failures-only", action="store_true", help="Only output failure patterns")
    parser.add_argument("--qa-report-only", action="store_true", help="Only output QA report")
    parser.add_argument("--compare-spec", action="store_true", help="Include pre/post spec comparison")
    parser.add_argument("--output-dir", default="analysis_output", help="Output directory")
    args = parser.parse_args()

    output_dir = (ROOT / args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    # Inputs
    riaf_logs = sorted((ROOT / "riaf-logs").glob("riaf_*.log"))
    run_dirs = [p for p in (ROOT / "fo_harness_runs").iterdir() if p.is_dir()]

    # Filter startup-id if provided
    if args.startup_id:
        run_dirs = [p for p in run_dirs if _startup_id_from_run_dir(p.name) == args.startup_id]

    riaf_data = parse_riaf_logs(riaf_logs) if riaf_logs else {}
    runs = parse_run_dirs(run_dirs)
    spec_map = detect_spec_injection(ROOT / "intake" / "intake_runs")

    # Build per-idea summary
    per_idea = defaultdict(lambda: {
        "phase1_iters": 0,
        "feature_iters": [],
        "total_iters": 0,
        "status": "UNKNOWN",
        "mode": None,
    })

    for run_name, r in runs.items():
        sid = r["startup_id"]
        if args.startup_id and sid != args.startup_id:
            continue
        per_idea[sid]["total_iters"] += r["iterations"]
        if r["run_type"] == "phase1":
            per_idea[sid]["phase1_iters"] = max(per_idea[sid]["phase1_iters"], r["iterations"])
        elif r["run_type"] == "feature":
            per_idea[sid]["feature_iters"].append(r["iterations"])

        # status/mode from riaf logs when available; fallback to build_state
        if sid in riaf_data:
            per_idea[sid]["status"] = riaf_data[sid].get("status", "UNKNOWN")
            per_idea[sid]["mode"] = riaf_data[sid].get("mode")
        else:
            if per_idea[sid]["status"] == "UNKNOWN":
                per_idea[sid]["status"] = r.get("status", "UNKNOWN")

    summary_rows = []
    for sid, data in sorted(per_idea.items()):
        feature_iters = data["feature_iters"]
        avg_feat = round(sum(feature_iters) / len(feature_iters), 2) if feature_iters else 0
        summary_rows.append({
            "startup_id": sid,
            "phase1_iters": data["phase1_iters"],
            "features": len(feature_iters),
            "avg_feat_iters": avg_feat,
            "total_iters": data["total_iters"],
            "status": data["status"],
        })

    # Failure patterns
    patterns, gate_failures = build_failure_patterns(runs)

    # Not-a-bug candidates (from false-positive heuristic)
    cand_map: Dict[str, Dict[str, Any]] = {}
    for r in runs.values():
        for d in r.get("false_pos_defects", []):
            problem = d.get("problem", "")
            key = _normalize_reason(problem)
            if key not in cand_map:
                cand_map[key] = {
                    "pattern": key,
                    "count": 0,
                    "ideas": set(),
                    "examples": []
                }
            cand_map[key]["count"] += 1
            cand_map[key]["ideas"].add(d.get("startup_id"))
            if len(cand_map[key]["examples"]) < 5:
                cand_map[key]["examples"].append({
                    "startup_id": d.get("startup_id"),
                    "iteration": d.get("iteration"),
                    "problem": problem
                })

    not_a_bug_candidates = sorted(
        [
            {
                "pattern": v["pattern"],
                "count": v["count"],
                "ideas": sorted(list(v["ideas"])),
                "examples": v["examples"]
            }
            for v in cand_map.values()
        ],
        key=lambda x: (len(x["ideas"]), x["count"]),
        reverse=True
    )

    # Gate breakdown (include riaf data if any)
    for sid, d in riaf_data.items():
        gate_failures.update(d.get("gate_failures", {}))

    total_gate_failures = sum(gate_failures.values()) or 1

    # False positive analysis
    fp_total = 0
    fp_est = 0
    for r in runs.values():
        fp_total += r["false_pos_total"]
        fp_est += r["false_pos_est"]

    # Pre/post spec comparison
    pre_post_rows = []
    if args.compare_spec:
        # aggregate total iters by spec status
        per_spec = defaultdict(lambda: {"pre": [], "post": []})
        for sid, data in per_idea.items():
            if spec_map.get(sid):
                per_spec[sid]["post"].append(data["total_iters"])
            else:
                per_spec[sid]["pre"].append(data["total_iters"])
        for sid, d in per_spec.items():
            if d["pre"] and d["post"]:
                pre = sum(d["pre"]) / len(d["pre"])
                post = sum(d["post"]) / len(d["post"])
                delta = post - pre
                pct = round((pre - post) / pre * 100, 2) if pre else 0
                pre_post_rows.append({
                    "startup_id": sid,
                    "pre_spec_iters": round(pre, 2),
                    "post_spec_iters": round(post, 2),
                    "delta": round(delta, 2),
                    "pct_improvement": pct,
                })

    # Console output
    if not args.failures_only and not args.qa_report_only:
        print("\nTable 1 — Iteration summary per idea")
        print_iteration_table(summary_rows)

        print("\nTable 2 — Gate failure frequency")
        print("gate | failures | % of total iterations")
        for gate, cnt in gate_failures.most_common():
            pct = round(cnt / total_gate_failures * 100, 2)
            print(f"{gate} | {cnt} | {pct}%")

        print("\nTable 3 — Top recurring failure reasons")
        for p in patterns[:10]:
            ideas = ", ".join(p["ideas"][:5]) + ("..." if len(p["ideas"]) > 5 else "")
            print(f"{p['reason']} | {p['count']} | {p['gate']} | {ideas}")

        if pre_post_rows:
            print("\nTable 4 — Pre/post spec comparison")
            print("startup_id | pre_spec_iters | post_spec_iters | delta | % improvement")
            for r in pre_post_rows:
                print(f"{r['startup_id']} | {r['pre_spec_iters']} | {r['post_spec_iters']} | {r['delta']} | {r['pct_improvement']}%")

    # Write outputs
    runs_summary = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "runs": runs,
        "per_idea": per_idea,
        "patterns": patterns,
        "gate_failures": dict(gate_failures),
        "false_positive": {"estimated": fp_est, "checked": fp_total},
        "not_a_bug_candidates": not_a_bug_candidates,
    }
    (output_dir / "runs_summary.json").write_text(json.dumps(runs_summary, indent=2), encoding="utf-8")

    # failure_patterns.txt
    with (output_dir / "failure_patterns.txt").open("w", encoding="utf-8") as f:
        for p in patterns:
            ideas = ", ".join(p["ideas"])
            f.write(f"{p['reason']} | {p['count']} | {p['gate']} | {ideas}\n")

    # not_a_bug_candidates.json
    (output_dir / "not_a_bug_candidates.json").write_text(
        json.dumps(
            {
                "generated_at": datetime.utcnow().isoformat() + "Z",
                "candidates": not_a_bug_candidates,
            },
            indent=2
        ),
        encoding="utf-8"
    )

    # gate_breakdown.csv
    with (output_dir / "gate_breakdown.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["gate", "failures", "pct_of_total"])
        for gate, cnt in gate_failures.most_common():
            pct = round(cnt / total_gate_failures * 100, 2)
            writer.writerow([gate, cnt, pct])

    # iteration_heatmap.csv
    with (output_dir / "iteration_heatmap.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["startup_id", "feature", "iterations"])
        for run_name, r in runs.items():
            if r["run_type"] == "feature":
                writer.writerow([r["startup_id"], r["feature_slug"] or "", r["iterations"]])

    # qa_report.md
    qa_report_path = output_dir / "qa_report.md"
    with qa_report_path.open("w", encoding="utf-8") as f:
        f.write("# Harness Run QA Report\n")
        f.write(f"Generated: {datetime.utcnow().isoformat()}Z\n")
        f.write(f"Runs analyzed: {len(runs)}\n")
        f.write("\n---\n\n")
        total_iters = sum(d["total_iters"] for d in per_idea.values()) if per_idea else 0
        avg_iters = round(total_iters / len(per_idea), 2) if per_idea else 0
        most_exp = max(per_idea.items(), key=lambda x: x[1]["total_iters"])[0] if per_idea else "n/a"
        f.write("## Executive Summary\n")
        f.write(f"- Total iterations across all runs: {total_iters}\n")
        f.write(f"- Average iterations per idea: {avg_iters}\n")
        f.write(f"- Most expensive idea: {most_exp}\n")
        if gate_failures:
            top_gate = gate_failures.most_common(1)[0]
            f.write(f"- Most common failure gate: {top_gate[0]} ({round(top_gate[1]/total_gate_failures*100,2)}%)\n")
        if patterns:
            f.write(f"- Most common failure reason: {patterns[0]['reason']} (seen {patterns[0]['count']} runs)\n")
        if fp_total:
            fp_rate = round(fp_est / fp_total * 100, 2) if fp_total else 0
            f.write(f"- Estimated wasted iterations (false positives): {fp_est} ({fp_rate}% of checked)\n")
        if pre_post_rows:
            avg_imp = round(sum(r["pct_improvement"] for r in pre_post_rows) / len(pre_post_rows), 2) if pre_post_rows else 0
            f.write(f"- Pre/post spec delta: {len(pre_post_rows)} runs compared, avg {avg_imp}% improvement\n")

        f.write("\n---\n\n")
        f.write("## Top 10 Failure Reasons\n")
        for idx, p in enumerate(patterns[:10], start=1):
            ideas = ", ".join(p["ideas"][:5]) + ("..." if len(p["ideas"]) > 5 else "")
            f.write(f"{idx}. {p['reason']} — {p['count']} occurrences\n")
            f.write(f"   Gate: {p['gate']}\n")
            f.write(f"   Ideas: {ideas}\n")

        f.write("\n## False Positive Analysis\n")
        fp_rate = round(fp_est / fp_total * 100, 2) if fp_total else 0
        f.write(f"Rate: {fp_rate}% of checked transitions\n")

        f.write("\n## Per-Idea Breakdown\n")
        for sid, data in sorted(per_idea.items()):
            f.write(f"### {sid}\n")
            f.write(f"- Phase 1: {data['phase1_iters']} iterations\n")
            f.write(f"- Features: {len(data['feature_iters'])} (avg {round((sum(data['feature_iters'])/len(data['feature_iters'])),2) if data['feature_iters'] else 0})\n")
            f.write(f"- Total iterations: {data['total_iters']}\n")
            f.write("\n")

        if not_a_bug_candidates:
            f.write("\n## Not-a-bug Candidates (Review Required)\n")
            for idx, c in enumerate(not_a_bug_candidates[:10], start=1):
                ideas = ", ".join(c["ideas"][:5]) + ("..." if len(c["ideas"]) > 5 else "")
                f.write(f"{idx}. {c['pattern']} — {c['count']} occurrences\n")
                f.write(f"   Ideas: {ideas}\n")
                if c["examples"]:
                    ex = c["examples"][0]
                    f.write(f"   Example: {ex['startup_id']} iter {ex['iteration']}: {ex['problem']}\n")

    if args.failures_only:
        print("\nFailure patterns written to:", output_dir / "failure_patterns.txt")
    elif args.qa_report_only:
        print("\nQA report written to:", qa_report_path)
    else:
        print("\nOutputs written to:", output_dir)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
