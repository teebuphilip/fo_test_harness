#!/usr/bin/env python3
"""
auth0_update_urls.py
--------------------
Update Auth0 SPA callback/logout/origin URLs for a given app and base URL.

Usage:
  python deploy/auth0_update_urls.py \
    --app-name ai-workforce-intelligence-downloadable-executive-report \
    --base-url https://ai-workforce-intelligence-downloadable-executive-report-frontend.vercel.app

Reads AUTH0_MGMT_TOKEN from env. Auth0 app credentials are loaded from:
  ~/Downloads/ACCESSKEYS/auth0_<app-name>.env
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import List

import requests


def _load_auth0_env(app_name: str) -> dict:
    keys_file = Path.home() / "Downloads" / "ACCESSKEYS" / f"auth0_{app_name}.env"
    if not keys_file.exists():
        raise FileNotFoundError(f"Auth0 credentials file not found: {keys_file}")
    values = {}
    for line in keys_file.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, _, v = line.partition("=")
            values[k.strip()] = v.strip()
    return values


def _normalize_url(url: str) -> str:
    return url.strip().rstrip("/")


def _merge_urls(existing: List[str], add: List[str]) -> List[str]:
    merged = {u for u in (existing or [])}
    for u in add:
        if u:
            merged.add(u)
    return sorted(merged)


def main() -> int:
    parser = argparse.ArgumentParser(description="Update Auth0 SPA URLs.")
    parser.add_argument("--app-name", required=True, help="App name (used to load auth0_<app>.env)")
    parser.add_argument("--base-url", required=True, help="Production base URL (https://...)")
    args = parser.parse_args()

    mgmt_token = os.getenv("AUTH0_MGMT_TOKEN")
    if not mgmt_token:
        print("[ERROR] AUTH0_MGMT_TOKEN not set")
        return 2

    vals = _load_auth0_env(args.app_name)
    domain = vals.get("AUTH0_DOMAIN")
    client_id = vals.get("AUTH0_CLIENT_ID")
    if not domain or not client_id:
        print("[ERROR] Missing AUTH0_DOMAIN or AUTH0_CLIENT_ID in auth0_<app>.env")
        return 2

    base = _normalize_url(args.base_url)
    callbacks = [f"{base}/callback", base]
    logout_urls = [base]
    web_origins = [base]

    url = f"https://{domain}/api/v2/clients/{client_id}"
    headers = {"Authorization": f"Bearer {mgmt_token}", "Content-Type": "application/json"}

    # Fetch current settings
    resp = requests.get(url, headers=headers, timeout=20)
    if resp.status_code >= 400:
        print(f"[ERROR] Auth0 GET failed: {resp.status_code} {resp.text}")
        return 1
    current = resp.json()

    payload = {
        "callbacks": _merge_urls(current.get("callbacks", []), callbacks),
        "allowed_logout_urls": _merge_urls(current.get("allowed_logout_urls", []), logout_urls),
        "web_origins": _merge_urls(current.get("web_origins", []), web_origins),
        "allowed_origins": _merge_urls(current.get("allowed_origins", []), web_origins),
    }

    patch = requests.patch(url, headers=headers, data=json.dumps(payload), timeout=20)
    if patch.status_code >= 400:
        print(f"[ERROR] Auth0 PATCH failed: {patch.status_code} {patch.text}")
        return 1

    print("Auth0 URLs updated for:", base)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
