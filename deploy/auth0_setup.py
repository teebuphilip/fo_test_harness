#!/usr/bin/env python3
"""
auth0_setup.py — Create an Auth0 Application + API for a given app.

Usage:
    python auth0_setup.py \
        --domain dev-xxxxxxxx.us.auth0.com \
        --mgmt-token <Management API token> \
        --app-name wynwood-thoroughbreds \
        --frontend-url https://wynwood-thoroughbreds-xxx.vercel.app  # optional

Output:
    ~/Downloads/ACCESSKEYS/auth0_wynwood-thoroughbreds.env
    (also printed to stdout)

Getting your Management API token (one-time GUI step):
    Auth0 Dashboard -> Applications -> APIs -> Auth0 Management API -> Test tab -> Copy Token

To update callback URLs after Vercel deploy:
    python auth0_setup.py --domain <domain> --mgmt-token <token> \
        --app-name wynwood-thoroughbreds \
        --update-urls --client-id <client_id> \
        --frontend-url https://your-vercel-url.vercel.app
"""

import argparse
import os
import sys
from pathlib import Path

import requests

ACCESSKEYS_DIR = Path.home() / "Downloads" / "ACCESSKEYS"


def auth0_post(domain, token, path, payload):
    resp = requests.post(
        f"https://{domain}/api/v2/{path}",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=payload,
        timeout=30,
    )
    if not resp.ok:
        print(f"  [Auth0] ERROR {resp.status_code}: {resp.text}")
        resp.raise_for_status()
    return resp.json()


def auth0_get(domain, token, path):
    resp = requests.get(
        f"https://{domain}/api/v2/{path}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def auth0_patch(domain, token, path, payload):
    resp = requests.patch(
        f"https://{domain}/api/v2/{path}",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def create_spa_application(domain, token, app_name, frontend_url=None):
    callbacks    = ["http://localhost:3000"]
    logout_urls  = ["http://localhost:3000"]
    web_origins  = ["http://localhost:3000"]
    if frontend_url:
        callbacks.append(frontend_url)
        logout_urls.append(frontend_url)
        web_origins.append(frontend_url)

    print(f"  [Auth0] Creating SPA application: {app_name}...")
    result = auth0_post(domain, token, "clients", {
        "name": app_name,
        "app_type": "spa",
        "callbacks": callbacks,
        "allowed_logout_urls": logout_urls,
        "web_origins": web_origins,
        "allowed_origins": web_origins,
        "grant_types": ["authorization_code", "implicit", "refresh_token"],
        "token_endpoint_auth_method": "none",
        "oidc_conformant": True,
        "jwt_configuration": {"alg": "RS256"},
    })
    print(f"  [Auth0] Application created: {result['client_id']}")
    return result


def create_api(domain, token, app_name):
    identifier = f"https://{app_name}.api"
    print(f"  [Auth0] Creating API: {app_name}-api (audience: {identifier})...")
    result = auth0_post(domain, token, "resource-servers", {
        "name": f"{app_name}-api",
        "identifier": identifier,
        "signing_alg": "RS256",
        "token_lifetime": 86400,
        "allow_offline_access": False,
    })
    print(f"  [Auth0] API created: {result['id']}")
    return result


def update_spa_urls(domain, token, client_id, frontend_url):
    print(f"  [Auth0] Updating callback URLs with: {frontend_url}")
    existing = auth0_get(domain, token, f"clients/{client_id}")
    callbacks   = list(set(existing.get("callbacks", [])           + [frontend_url]))
    logout_urls = list(set(existing.get("allowed_logout_urls", []) + [frontend_url]))
    web_origins = list(set(existing.get("web_origins", [])         + [frontend_url]))
    auth0_patch(domain, token, f"clients/{client_id}", {
        "callbacks": callbacks,
        "allowed_logout_urls": logout_urls,
        "web_origins": web_origins,
        "allowed_origins": web_origins,
    })
    print("  [Auth0] URLs updated.")


def save_credentials(app_name, domain, client, api):
    ACCESSKEYS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = ACCESSKEYS_DIR / f"auth0_{app_name}.env"
    out_path.write_text(
        f"# Auth0 credentials for {app_name}\n"
        f"AUTH0_DOMAIN={domain}\n"
        f"AUTH0_CLIENT_ID={client['client_id']}\n"
        f"AUTH0_CLIENT_SECRET={client['client_secret']}\n"
        f"AUTH0_AUDIENCE={api['identifier']}\n"
    )
    return out_path


def main():
    parser = argparse.ArgumentParser(description="Auth0 app + API setup")
    parser.add_argument("--domain",       default=None, help="Auth0 domain (or set AUTH0_DOMAIN env var)")
    parser.add_argument("--mgmt-token",   default=None, help="Auth0 Management API token (or set AUTH0_KEY env var)")
    parser.add_argument("--app-name",     required=True, help="App slug e.g. wynwood-thoroughbreds")
    parser.add_argument("--frontend-url", default=None,  help="Vercel URL (optional, add later)")
    parser.add_argument("--update-urls",  action="store_true", help="Only patch callback URLs on existing app")
    parser.add_argument("--client-id",    default=None,  help="Existing client ID (required with --update-urls)")
    args = parser.parse_args()

    domain = "".join((args.domain or os.getenv("AUTH0_DOMAIN", "")).split())
    token  = "".join((args.mgmt_token or os.getenv("AUTH0_KEY", "")).split())
    app_name = args.app_name.strip()

    if not domain:
        print("ERROR: provide --domain or export AUTH0_DOMAIN")
        sys.exit(1)
    if not token:
        print("ERROR: provide --mgmt-token or export AUTH0_KEY")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"Auth0 Setup: {app_name}")
    print(f"Domain:      {domain}")
    print(f"{'='*60}\n")

    if args.update_urls:
        if not args.client_id or not args.frontend_url:
            print("ERROR: --update-urls requires --client-id and --frontend-url")
            sys.exit(1)
        update_spa_urls(domain, token, args.client_id, args.frontend_url)
        print("\nDone — URLs updated.")
        return

    client = create_spa_application(domain, token, app_name, args.frontend_url)
    api    = create_api(domain, token, app_name)
    out    = save_credentials(app_name, domain, client, api)

    print(f"\n{'='*60}")
    print(f"SAVED: {out}")
    print(f"{'='*60}")
    print(f"AUTH0_DOMAIN={domain}")
    print(f"AUTH0_CLIENT_ID={client['client_id']}")
    print(f"AUTH0_CLIENT_SECRET={client['client_secret']}")
    print(f"AUTH0_AUDIENCE={api['identifier']}")
    print(f"\nTo update callback URLs after Vercel deploy:")
    print(f"  python auth0_setup.py --domain {domain} --mgmt-token <token> \\")
    print(f"    --app-name {app_name} --update-urls \\")
    print(f"    --client-id {client['client_id']} \\")
    print(f"    --frontend-url https://your-vercel-url.vercel.app")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
