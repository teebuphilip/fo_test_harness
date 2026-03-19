#!/usr/bin/env python3
"""
trigger_qa.py
Called from your build pipeline AFTER deploying to Vercel + Railway.
Triggers the QA container on Railway as a one-shot job and polls for results.

Usage:
  python trigger_qa.py \
    --target-url https://myapp.vercel.app \
    --project-id <railway-qa-project-id> \
    --service-id <railway-qa-service-id>

Or via env vars:
  TARGET_URL, RAILWAY_QA_PROJECT_ID, RAILWAY_QA_SERVICE_ID, RAILWAY_API_TOKEN
"""

import argparse
import json
import os
import sys
import time
import requests

# ── Config ────────────────────────────────────────────────────────────────────

RAILWAY_API       = "https://backboard.railway.app/graphql/v2"
POLL_INTERVAL_SEC = 10
MAX_WAIT_SEC      = 600  # 10 min timeout

# ── Args ──────────────────────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(description="Trigger QA container on Railway")
    parser.add_argument("--target-url",   default=os.environ.get("TARGET_URL"))
    parser.add_argument("--service-id",   default=os.environ.get("RAILWAY_QA_SERVICE_ID"))
    parser.add_argument("--api-token",    default=os.environ.get("RAILWAY_API_TOKEN"))
    parser.add_argument("--results-file", default="qa_report.json",
                        help="Local file to write final QA report to")
    return parser.parse_args()

# ── Railway API helpers ───────────────────────────────────────────────────────

def gql(token, query, variables=None):
    resp = requests.post(
        RAILWAY_API,
        json={"query": query, "variables": variables or {}},
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if "errors" in data:
        raise RuntimeError(f"Railway GQL error: {data['errors']}")
    return data["data"]

def trigger_deployment(token, service_id, target_url):
    """Redeploy the QA service with TARGET_URL injected as an env var override."""
    query = """
    mutation ServiceInstanceRedeploy($serviceId: String!) {
      serviceInstanceRedeploy(serviceId: $serviceId)
    }
    """
    # First update the TARGET_URL variable on the service
    set_var_query = """
    mutation VariableUpsert($input: VariableUpsertInput!) {
      variableUpsert(input: $input)
    }
    """
    gql(token, set_var_query, {
        "input": {
            "serviceId": service_id,
            "name": "TARGET_URL",
            "value": target_url,
        }
    })
    print(f"[trigger_qa] Set TARGET_URL={target_url} on service {service_id}")

    # Trigger redeploy
    result = gql(token, query, {"serviceId": service_id})
    print(f"[trigger_qa] Deployment triggered: {result}")
    return result

def get_latest_deployment(token, service_id):
    query = """
    query ServiceDeployments($serviceId: String!) {
      deployments(first: 1, input: { serviceId: $serviceId }) {
        edges {
          node {
            id
            status
            createdAt
          }
        }
      }
    }
    """
    data = gql(token, query, {"serviceId": service_id})
    edges = data.get("deployments", {}).get("edges", [])
    if not edges:
        return None
    return edges[0]["node"]

def get_deployment_logs(token, deployment_id):
    query = """
    query DeploymentLogs($deploymentId: String!) {
      deploymentLogs(deploymentId: $deploymentId) {
        message
        timestamp
      }
    }
    """
    data = gql(token, query, {"deploymentId": deployment_id})
    return data.get("deploymentLogs", [])

# ── Poll for completion ───────────────────────────────────────────────────────

TERMINAL_STATUSES = {"SUCCESS", "FAILED", "CRASHED", "REMOVED"}

def poll_deployment(token, service_id, deployment_id):
    print(f"[trigger_qa] Polling deployment {deployment_id}...")
    elapsed = 0

    while elapsed < MAX_WAIT_SEC:
        deployment = get_latest_deployment(token, service_id)
        if not deployment:
            print("[trigger_qa] WARNING: Could not fetch deployment status")
        else:
            status = deployment.get("status", "UNKNOWN")
            print(f"[trigger_qa] Status: {status} ({elapsed}s elapsed)")

            if status in TERMINAL_STATUSES:
                return status

        time.sleep(POLL_INTERVAL_SEC)
        elapsed += POLL_INTERVAL_SEC

    print(f"[trigger_qa] TIMEOUT after {MAX_WAIT_SEC}s")
    return "TIMEOUT"

# ── Extract QA report from logs ───────────────────────────────────────────────

def extract_report_from_logs(token, deployment_id):
    """
    The entrypoint.py writes qa_report.json inside the container.
    We can't directly read container files from Railway, so the entrypoint
    also prints the JSON report to stdout — we extract it from logs here.
    """
    logs = get_deployment_logs(token, deployment_id)
    full_log = "\n".join(entry.get("message", "") for entry in logs)

    # Look for the JSON report marker printed by entrypoint.py
    marker = "QA_REPORT_JSON:"
    for line in full_log.splitlines():
        if line.startswith(marker):
            try:
                return json.loads(line[len(marker):].strip())
            except json.JSONDecodeError:
                pass

    return {"raw_logs": full_log, "parse_error": "Could not extract structured report"}

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    args = parse_args()

    missing = [k for k, v in {
        "target-url":  args.target_url,
        "service-id":  args.service_id,
        "api-token":   args.api_token,
    }.items() if not v]

    if missing:
        print(f"[trigger_qa] ERROR: Missing required args/env vars: {missing}")
        sys.exit(1)

    print(f"[trigger_qa] Triggering QA for: {args.target_url}")

    # 1. Trigger the QA container
    trigger_deployment(args.api_token, args.service_id, args.target_url)

    # Small wait for Railway to register the new deployment
    time.sleep(5)

    # 2. Get deployment ID
    deployment = get_latest_deployment(args.api_token, args.service_id)
    if not deployment:
        print("[trigger_qa] ERROR: Could not get deployment info")
        sys.exit(1)

    deployment_id = deployment["id"]
    print(f"[trigger_qa] Deployment ID: {deployment_id}")

    # 3. Poll until terminal status
    final_status = poll_deployment(args.api_token, args.service_id, deployment_id)
    print(f"[trigger_qa] Final status: {final_status}")

    # 4. Extract report from logs
    report = extract_report_from_logs(args.api_token, deployment_id)

    # 5. Write local results file
    with open(args.results_file, "w") as f:
        json.dump(report, f, indent=2)
    print(f"[trigger_qa] Report written to: {args.results_file}")

    # 6. Exit code mirrors QA pass/fail
    overall = report.get("meta", {}).get("overall_passed", False)
    if final_status != "SUCCESS" or not overall:
        print("[trigger_qa] QA FAILED")
        sys.exit(1)

    print("[trigger_qa] QA PASSED")
    sys.exit(0)

if __name__ == "__main__":
    main()
