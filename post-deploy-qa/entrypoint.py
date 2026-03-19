#!/usr/bin/env python3
"""
entrypoint.py
QA container entrypoint. Runs Newman (Postman) and Playwright tests
against deployed TARGET_URL, writes combined JSON results to /app/results/qa_report.json

Required env vars:
  TARGET_URL          - Base URL of deployed app (e.g. https://myapp.vercel.app)
  TEST_REPO_URL       - Git repo URL containing tests (optional if baked in at build)
  TEST_REPO_BRANCH    - Branch to clone (default: main)

Optional env vars:
  POSTMAN_FOLDER      - Subfolder within repo for collections (default: postman)
  PLAYWRIGHT_FOLDER   - Subfolder within repo for playwright specs (default: playwright)
  POSTMAN_ENV_FILE    - Filename of Postman environment JSON (default: environment.json)
  RESULTS_DIR         - Where to write results (default: /app/results)
"""

import os
import json
import subprocess
import sys
import glob
from datetime import datetime, timezone

# ── Config ────────────────────────────────────────────────────────────────────

TARGET_URL        = os.environ.get("TARGET_URL", "").strip()
TESTS_BASE        = "/app/tests"
POSTMAN_FOLDER    = os.environ.get("POSTMAN_FOLDER", "postman")
PLAYWRIGHT_FOLDER = os.environ.get("PLAYWRIGHT_FOLDER", "playwright")
POSTMAN_ENV_FILE  = os.environ.get("POSTMAN_ENV_FILE", "environment.json")
RESULTS_DIR       = os.environ.get("RESULTS_DIR", "/app/results")

POSTMAN_DIR       = os.path.join(TESTS_BASE, POSTMAN_FOLDER)
PLAYWRIGHT_DIR    = os.path.join(TESTS_BASE, PLAYWRIGHT_FOLDER)
NEWMAN_RESULTS    = os.path.join(RESULTS_DIR, "newman_results.json")
PLAYWRIGHT_RESULTS= os.path.join(RESULTS_DIR, "playwright_results.json")
FINAL_REPORT      = os.path.join(RESULTS_DIR, "qa_report.json")

# ── Helpers ───────────────────────────────────────────────────────────────────

def log(msg):
    print(f"[qa-runner] {msg}", flush=True)

def run(cmd, cwd=None, capture=False):
    """Run a shell command. Returns (returncode, stdout, stderr)."""
    log(f"Running: {' '.join(cmd)}")
    result = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=capture,
        text=True
    )
    return result.returncode, result.stdout, result.stderr

def ensure_dirs():
    os.makedirs(RESULTS_DIR, exist_ok=True)

# ── Clone test repo ───────────────────────────────────────────────────────────

def clone_repo():
    log("Cloning test repo...")
    rc, _, err = run(["bash", "/app/clone_tests.sh"])
    if rc != 0:
        log(f"WARNING: clone_tests.sh exited {rc}: {err}")

# ── Newman (Postman) ──────────────────────────────────────────────────────────

def run_newman():
    log("=== Running Newman (Postman) tests ===")

    if not os.path.isdir(POSTMAN_DIR):
        log(f"WARNING: Postman dir not found at {POSTMAN_DIR} — skipping")
        return {"skipped": True, "reason": f"directory not found: {POSTMAN_DIR}"}

    # Find all collection files
    collections = glob.glob(os.path.join(POSTMAN_DIR, "*.json"))
    collections = [c for c in collections if "environment" not in os.path.basename(c).lower()]

    if not collections:
        log("WARNING: No Postman collection JSON files found — skipping")
        return {"skipped": True, "reason": "no collection files found"}

    env_file = os.path.join(POSTMAN_DIR, POSTMAN_ENV_FILE)
    all_results = []

    for collection in collections:
        collection_name = os.path.basename(collection)
        out_file = os.path.join(RESULTS_DIR, f"newman_{collection_name}")

        cmd = [
            "newman", "run", collection,
            "--reporters", "json",
            "--reporter-json-export", out_file,
            "--env-var", f"baseUrl={TARGET_URL}",
        ]

        if os.path.isfile(env_file):
            cmd += ["--environment", env_file]
            log(f"Using environment file: {env_file}")

        rc, stdout, stderr = run(cmd, capture=True)

        result_data = {}
        if os.path.isfile(out_file):
            with open(out_file) as f:
                try:
                    result_data = json.load(f)
                except json.JSONDecodeError:
                    result_data = {"raw": stdout}

        summary = result_data.get("run", {}).get("stats", {})
        failures = result_data.get("run", {}).get("failures", [])

        all_results.append({
            "collection": collection_name,
            "exit_code": rc,
            "passed": rc == 0,
            "stats": summary,
            "failures": failures,
        })

        log(f"Newman [{collection_name}]: {'PASS' if rc == 0 else 'FAIL'} (exit {rc})")

    return {
        "skipped": False,
        "collections": all_results,
        "overall_passed": all(r["passed"] for r in all_results),
    }

# ── Playwright ────────────────────────────────────────────────────────────────

def run_playwright():
    log("=== Running Playwright tests ===")

    if not os.path.isdir(PLAYWRIGHT_DIR):
        log(f"WARNING: Playwright dir not found at {PLAYWRIGHT_DIR} — skipping")
        return {"skipped": True, "reason": f"directory not found: {PLAYWRIGHT_DIR}"}

    # Install dependencies if package.json present
    pkg = os.path.join(PLAYWRIGHT_DIR, "package.json")
    if os.path.isfile(pkg):
        log("Installing Playwright test dependencies...")
        run(["npm", "install"], cwd=PLAYWRIGHT_DIR)

    cmd = [
        "npx", "playwright", "test",
        "--reporter=json",
        f"--output={RESULTS_DIR}/playwright-artifacts",
    ]

    # Pass target URL as env var — tests should read process.env.TARGET_URL
    env = os.environ.copy()
    env["TARGET_URL"] = TARGET_URL
    env["BASE_URL"]   = TARGET_URL  # common alias

    result = subprocess.run(
        cmd,
        cwd=PLAYWRIGHT_DIR,
        capture_output=True,
        text=True,
        env=env
    )

    rc = result.returncode
    raw_output = result.stdout + result.stderr

    # Playwright JSON reporter writes to stdout
    pw_data = {}
    try:
        pw_data = json.loads(result.stdout)
    except json.JSONDecodeError:
        pw_data = {"raw_output": raw_output}

    # Write playwright results separately
    with open(PLAYWRIGHT_RESULTS, "w") as f:
        json.dump(pw_data, f, indent=2)

    # Summarize
    suites  = pw_data.get("suites", [])
    stats   = pw_data.get("stats", {})
    passed  = rc == 0

    log(f"Playwright: {'PASS' if passed else 'FAIL'} (exit {rc})")
    log(f"  Stats: {stats}")

    return {
        "skipped": False,
        "exit_code": rc,
        "passed": passed,
        "stats": stats,
        "suites": suites,
    }

# ── Final report ──────────────────────────────────────────────────────────────

def write_report(newman_results, playwright_results):
    overall_passed = (
        newman_results.get("skipped") or newman_results.get("overall_passed", False)
    ) and (
        playwright_results.get("skipped") or playwright_results.get("passed", False)
    )

    report = {
        "meta": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "target_url": TARGET_URL,
            "overall_passed": overall_passed,
        },
        "newman": newman_results,
        "playwright": playwright_results,
    }

    with open(FINAL_REPORT, "w") as f:
        json.dump(report, f, indent=2)

    log(f"=== QA REPORT WRITTEN: {FINAL_REPORT} ===")
    log(f"=== OVERALL: {'PASS ✓' if overall_passed else 'FAIL ✗'} ===")

    return report

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if not TARGET_URL:
        log("ERROR: TARGET_URL env var is required")
        sys.exit(1)

    log(f"Target URL: {TARGET_URL}")

    ensure_dirs()
    clone_repo()

    newman_results     = run_newman()
    playwright_results = run_playwright()
    report             = write_report(newman_results, playwright_results)

    # Exit non-zero if any tests failed (so Railway marks the job as failed)
    if not report["meta"]["overall_passed"]:
        log("One or more test suites FAILED.")
        sys.exit(1)

    log("All tests PASSED.")
    sys.exit(0)

if __name__ == "__main__":
    main()
