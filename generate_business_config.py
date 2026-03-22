#!/usr/bin/env python3
"""
generate_business_config.py — Standalone post-merge business_config.json generator.

Inspects actual built artifacts to populate nav items, footer links, and dashboard
config from what was really built — not from intake assumptions.

Usage:
  # From a directory (e.g. merged temp dir before zipping)
  python generate_business_config.py --dir /path/to/merged --intake intake.json

  # From a ZIP (extracts to temp dir, generates config, re-zips)
  python generate_business_config.py --zip fo_harness_runs/wynwood_full.zip --intake intake.json

  # Dry run (print config to stdout, don't write)
  python generate_business_config.py --zip wynwood_full.zip --intake intake.json --dry-run
"""

import argparse
import json
import os
import re
import sys
import shutil
import tempfile
import zipfile
from pathlib import Path


# ── PascalCase → kebab-case (mirrors loader.js logic exactly) ────────────────
def pascal_to_kebab(name: str) -> str:
    """Convert PascalCase to kebab-case, matching frontend loader.js."""
    # 'HorseProfiles' -> '-Horse-Profiles' -> 'horse-profiles'
    return re.sub(r'([A-Z])', r'-\1', name).lower().lstrip('-')


def pascal_to_label(name: str) -> str:
    """Convert PascalCase to human label: 'HorseProfiles' -> 'Horse Profiles'."""
    return re.sub(r'([A-Z])', r' \1', name).strip()


# ── Page discovery ────────────────────────────────────────────────────────────
# Pages that are part of boilerplate, not business-specific
BOILERPLATE_PAGES = {
    'Dashboard', 'Home', 'Login', 'Signup', 'Pricing', 'Contact',
    'FAQ', 'Terms', 'Privacy', 'AccountSettings', 'Onboarding',
    'AdminDashboard', 'AdminUsers', 'AdminTenants', 'AdminBilling',
    'AdminExpenses', 'CostDashboard',
}


def discover_pages(root_dir: str) -> list:
    """
    Find all business/frontend/pages/*.jsx files in the directory tree.
    Returns deduplicated list of PascalCase page names (business pages only).

    Handles both flat structure (business/frontend/pages/*.jsx) and
    entity-based structure (entity_name/saas-boilerplate/business/frontend/pages/*.jsx).
    """
    root = Path(root_dir)
    pages = set()

    # Glob for .jsx files in any business/frontend/pages/ directory
    # Skip _harness/build iteration dirs — only look at saas-boilerplate (deployed) copies
    for jsx in root.rglob('business/frontend/pages/*.jsx'):
        # Skip iteration artifact copies — they're intermediate, not final
        if '_harness/build/iteration_' in str(jsx):
            continue
        name = jsx.stem  # e.g. 'HorseProfiles'
        if name not in BOILERPLATE_PAGES:
            pages.add(name)

    return sorted(pages)


def discover_backend_routes(root_dir: str) -> list:
    """Find all business/backend/routes/*.py files (non-iteration, non-__init__)."""
    root = Path(root_dir)
    routes = set()
    for py in root.rglob('business/backend/routes/*.py'):
        if '_harness/build/iteration_' in str(py):
            continue
        name = py.stem
        if name.startswith('__'):
            continue
        routes.add(name)
    return sorted(routes)


# ── Config generation ─────────────────────────────────────────────────────────
def generate_config(intake_path: str, root_dir: str) -> dict:
    """Generate business_config.json from intake + actual built artifacts."""

    with open(intake_path) as f:
        intake = json.load(f)

    # ── Extract intake metadata ──────────────────────────────────────────
    block_b = intake.get('block_b', {})
    hero = block_b.get('hero_answers', {})
    econ = intake.get('block_a', {}).get('pass_1', {}).get('economics_snapshot', {})

    startup_name = intake.get('startup_name', 'My Startup')
    startup_id = intake.get('startup_idea_id', 'my_startup')
    tagline = hero.get('Q3_success_metric', econ.get('target_customer', ''))[:120]
    price_raw = econ.get('starter_price', '$99/month')

    price_match = re.search(r'[\d,]+', price_raw.replace(',', ''))
    price_monthly = int(price_match.group(0)) if price_match else 99
    price_annual = round(price_monthly * 10)

    slug = startup_name.lower().replace(' ', '')

    must_haves = hero.get('Q4_must_have_features', [])
    entitlements = []
    for f in must_haves:
        key = re.sub(r'[^a-z0-9]+', '_', f.lower()).strip('_')[:30]
        entitlements.append(key)
    if not entitlements:
        entitlements = ['dashboard']

    features_block = {}
    for i, (key, label) in enumerate(zip(entitlements, must_haves)):
        features_block[key] = {
            "tier": 1 if i < 5 else 2,
            "label": label[:50],
            "description": label,
        }

    # ── Discover actual built pages ──────────────────────────────────────
    pages = discover_pages(root_dir)
    backend_routes = discover_backend_routes(root_dir)

    print(f"  Discovered {len(pages)} business page(s):")
    for p in pages:
        route = pascal_to_kebab(p)
        print(f"    {p}.jsx → /dashboard/{route}")

    print(f"  Discovered {len(backend_routes)} backend route(s):")
    for r in backend_routes:
        print(f"    {r}.py → /api/{r}")

    # ── Build nav_items from actual pages ────────────────────────────────
    nav_items = [
        {"label": "Dashboard", "path": "/dashboard", "icon": "grid"},
    ]
    for page_name in pages:
        nav_items.append({
            "label": pascal_to_label(page_name),
            "path": f"/dashboard/{pascal_to_kebab(page_name)}",
            "icon": "file",
        })
    nav_items.append({"label": "Settings", "path": "/settings", "icon": "cog"})

    # ── Build footer product links from actual pages ─────────────────────
    product_links = []
    for page_name in pages[:6]:  # cap at 6 for footer
        product_links.append({
            "label": pascal_to_label(page_name),
            "url": f"/dashboard/{pascal_to_kebab(page_name)}",
        })
    if not product_links:
        product_links = [{"label": "Dashboard", "url": "/dashboard"}]

    # ── Build home features from intake + actual pages ───────────────────
    home_features = []
    # Use must_haves if available, else fall back to page names
    feature_sources = must_haves[:6] if must_haves else [pascal_to_label(p) for p in pages[:6]]
    for feat in feature_sources:
        label = feat[:50] if isinstance(feat, str) else feat.get("label", "Feature")
        home_features.append({
            "icon": "star",
            "title": label,
            "description": "",
        })
    if not home_features:
        home_features = [{"icon": "star", "title": "Core features", "description": ""}]

    # ── Assemble config ──────────────────────────────────────────────────
    config = {
        "_comment": "business_config.json — auto-generated by generate_business_config.py from intake + built artifacts.",
        "business": {
            "name": startup_name,
            "tagline": tagline,
            "description": tagline,
            "url": f"https://{slug}.com",
            "support_email": f"support@{slug}.com",
        },
        "stripe": {
            "publishable_key": "pk_live_YOUR_KEY_HERE",
            "secret_key": "sk_live_YOUR_KEY_HERE",
            "webhook_secret": "whsec_YOUR_WEBHOOK_SECRET_HERE",
        },
        "stripe_products": {
            "prod_REPLACE_WITH_STARTER_ID": {
                "name": "Starter",
                "description": f"Get started with {startup_name}",
                "price_monthly": price_monthly,
                "price_annual": price_annual,
                "annual_savings": f"Save ${price_monthly * 2}/year",
                "popular": True,
                "cta_text": "Start Free Trial",
                "stripe_price_id_monthly": "price_REPLACE_WITH_MONTHLY_PRICE_ID",
                "stripe_price_id_annual": "price_REPLACE_WITH_ANNUAL_PRICE_ID",
                "features": must_haves[:6] if must_haves else ["Full access"],
                "limitations": [],
                "entitlements": entitlements,
            }
        },
        "features": features_block,
        "auth0": {
            "domain": "YOUR_AUTH0_DOMAIN.auth0.com",
            "client_id": "YOUR_CLIENT_ID",
            "client_secret": "YOUR_CLIENT_SECRET",
            "audience": "https://YOUR_AUTH0_DOMAIN.auth0.com/api/v2/",
        },
        "mailerlite": {
            "api_key": "YOUR_MAILERLITE_API_KEY",
            "group_id": "YOUR_GROUP_ID",
        },
        "branding": {
            "primary_color": "#1E3A5F",
            "logo_url": "",
            "favicon_url": "",
            "company_name": startup_name,
        },
        "dashboard": {
            "theme": "light",
            "show_upgrade_banner": True,
            "nav_items": nav_items,
            "hero_support_url": "",
            "hero_docs_url": "",
        },
        "metadata": {
            "analytics": {"google_analytics_id": ""},
            "seo": {
                "title": startup_name,
                "description": tagline,
            },
        },
        "home": {
            "hero": {
                "headline": startup_name,
                "subheadline": tagline,
                "cta_primary": "Get Started",
                "cta_secondary": "Learn More",
            },
            "features_heading": "Everything you need",
            "features": home_features,
            "social_proof": {
                "stats": [
                    {"value": "500+", "label": "Customers"},
                    {"value": "99%", "label": "Uptime"},
                    {"value": "24/7", "label": "Support"},
                ],
                "testimonials": [
                    {
                        "quote": f"{startup_name} has transformed how we work.",
                        "author": "Early Customer",
                        "title": "Founder",
                    }
                ],
            },
            "final_cta": {
                "headline": f"Ready to get started with {startup_name}?",
                "subheadline": tagline,
                "button_text": "Start Free Trial",
            },
        },
        "pricing": {
            "headline": f"{startup_name} Pricing",
            "subheadline": "Simple, transparent pricing",
            "faq": [
                {"question": "Can I cancel anytime?", "answer": "Yes, cancel anytime with no penalties."},
                {"question": "Is there a free trial?", "answer": "Yes, 14-day free trial on all plans."},
                {"question": "Do you offer refunds?", "answer": "Yes, 30-day money-back guarantee."},
                {"question": "What payment methods?", "answer": "All major credit cards via Stripe."},
            ],
        },
        "contact": {
            "headline": "Get in touch",
            "subheadline": "We'd love to hear from you.",
            "methods": [
                {"label": "Email", "description": "Send us an email", "value": f"support@{slug}.com"},
            ],
            "form": {
                "title": "Send a message",
                "submit_text": "Send Message",
                "success_message": "Thanks! We'll be in touch shortly.",
                "fields": [
                    {"label": "Name", "name": "name", "type": "text", "required": True},
                    {"label": "Email", "name": "email", "type": "email", "required": True},
                    {"label": "Message", "name": "message", "type": "textarea", "required": True},
                ],
            },
        },
        "faq": {
            "headline": "Frequently Asked Questions",
            "categories": [
                {
                    "name": "General",
                    "questions": [
                        {"question": f"What is {startup_name}?", "answer": tagline},
                        {"question": "How do I get started?", "answer": "Sign up for a free trial — no credit card required."},
                        {"question": "Is my data secure?", "answer": "Yes, all data is encrypted in transit and at rest."},
                    ],
                },
                {
                    "name": "Billing",
                    "questions": [
                        {"question": "Can I cancel anytime?", "answer": "Yes, cancel anytime with no penalties."},
                        {"question": "Do you offer refunds?", "answer": "Yes, 30-day money-back guarantee."},
                    ],
                },
            ],
        },
        "terms_of_service": {
            "last_updated": "2025-01-01",
            "sections": [
                {"title": "Acceptance of Terms", "content": f"By using {startup_name}, you agree to these terms."},
                {"title": "Use of Service", "content": "You may use the service for lawful purposes only."},
                {"title": "Intellectual Property", "content": f"All content and software is owned by {startup_name}."},
                {"title": "Limitation of Liability", "content": "We are not liable for indirect or consequential damages."},
                {"title": "Contact", "content": f"Questions? Email support@{slug}.com"},
            ],
        },
        "privacy_policy": {
            "last_updated": "2025-01-01",
            "sections": [
                {"title": "Information We Collect", "content": "We collect information you provide when creating an account."},
                {"title": "How We Use It", "content": "We use your information to provide and improve the service."},
                {"title": "Data Sharing", "content": "We do not sell your personal data to third parties."},
                {"title": "Security", "content": "We use industry-standard encryption to protect your data."},
                {"title": "Contact", "content": f"Questions? Email support@{slug}.com"},
            ],
        },
        "marketing": {"enabled": False},
        "footer": {
            "tagline": tagline,
            "columns": [
                {
                    "title": startup_name,
                    "links": [
                        {"label": "Home", "url": "/"},
                        {"label": "Dashboard", "url": "/dashboard"},
                        {"label": "Pricing", "url": "/pricing"},
                    ],
                },
                {
                    "title": "Product",
                    "links": product_links,
                },
                {
                    "title": "Company",
                    "links": [
                        {"label": "About", "url": "/about"},
                        {"label": "Contact", "url": "/contact"},
                        {"label": "Privacy", "url": "/privacy"},
                        {"label": "Terms", "url": "/terms"},
                    ],
                },
            ],
            "copyright": f"\u00a9 2025 {startup_name}. All rights reserved.",
        },
    }

    return config


def write_config(config: dict, root_dir: str) -> list:
    """Write business_config.json to all config locations.

    Writes to:
      1. business/frontend/config/ + business/backend/config/  (harness convention)
      2. frontend/src/config/  + backend/config/               (deployed app reads these)
      3. */saas-boilerplate/business/frontend/config/ etc.      (entity-based ZIP structure)
      4. */saas-boilerplate/frontend/src/config/ etc.           (entity-based deployed paths)

    Returns list of paths written.
    """
    root = Path(root_dir)
    config_json = json.dumps(config, indent=2)
    targets_written = set()
    written = []

    def _write_target(target: Path):
        resolved = str(target.resolve())
        if resolved in targets_written:
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(config_json)
        targets_written.add(resolved)
        written.append(str(target))
        print(f"  ✓ {target.relative_to(root)}")

    # ── Harness paths: business/frontend/config + business/backend/config ─────
    # Flat structure
    flat_biz = root / 'business'
    if flat_biz.is_dir():
        _write_target(flat_biz / 'frontend' / 'config' / 'business_config.json')
        _write_target(flat_biz / 'backend' / 'config' / 'business_config.json')

    # Entity-based structure: */saas-boilerplate/business/
    for bp_biz in root.glob('*/saas-boilerplate/business'):
        _write_target(bp_biz / 'frontend' / 'config' / 'business_config.json')
        _write_target(bp_biz / 'backend' / 'config' / 'business_config.json')

    # ── Deployed app paths: frontend/src/config + backend/config ──────────────
    # Flat structure (deployed repo layout)
    fe_src_config = root / 'frontend' / 'src' / 'config' / 'business_config.json'
    be_config = root / 'backend' / 'config' / 'business_config.json'
    if (root / 'frontend' / 'src').is_dir():
        _write_target(fe_src_config)
    if (root / 'backend').is_dir():
        _write_target(be_config)

    # Entity-based: */saas-boilerplate/frontend/src/config/
    for bp_fe in root.glob('*/saas-boilerplate/frontend/src/config'):
        _write_target(bp_fe / 'business_config.json')
    for bp_be in root.glob('*/saas-boilerplate/backend/config'):
        _write_target(bp_be / 'business_config.json')

    return written


# ── CLI ───────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description='Generate business_config.json from intake + actual built artifacts.'
    )
    parser.add_argument('--dir', help='Root directory containing built artifacts')
    parser.add_argument('--zip', help='ZIP file to process (extracts, generates, re-zips)')
    parser.add_argument('--intake', required=True, help='Path to intake JSON')
    parser.add_argument('--dry-run', action='store_true', help='Print config to stdout, do not write')
    args = parser.parse_args()

    if not args.dir and not args.zip:
        print("ERROR: Must provide --dir or --zip")
        sys.exit(1)

    if args.dir and args.zip:
        print("ERROR: Provide --dir or --zip, not both")
        sys.exit(1)

    if not os.path.isfile(args.intake):
        print(f"ERROR: Intake not found: {args.intake}")
        sys.exit(1)

    print("=" * 60)
    print("  GENERATE BUSINESS CONFIG")
    print(f"  Intake: {args.intake}")
    print("=" * 60)
    print()

    if args.dir:
        root_dir = args.dir
        if not os.path.isdir(root_dir):
            print(f"ERROR: Directory not found: {root_dir}")
            sys.exit(1)

        config = generate_config(args.intake, root_dir)

        if args.dry_run:
            print()
            print(json.dumps(config, indent=2))
        else:
            print()
            print("  Writing config files:")
            written = write_config(config, root_dir)
            print(f"\n  Done — wrote {len(written)} file(s)")

    elif args.zip:
        zip_path = args.zip
        if not os.path.isfile(zip_path):
            print(f"ERROR: ZIP not found: {zip_path}")
            sys.exit(1)

        # Extract to temp dir
        tmp = tempfile.mkdtemp()
        try:
            print(f"  Extracting: {zip_path}")
            with zipfile.ZipFile(zip_path, 'r') as zf:
                zf.extractall(tmp)

            config = generate_config(args.intake, tmp)

            if args.dry_run:
                print()
                print(json.dumps(config, indent=2))
            else:
                print()
                print("  Writing config files:")
                written = write_config(config, tmp)
                print(f"\n  Re-packing ZIP: {zip_path}")

                # Re-create ZIP with updated config
                new_zip = zip_path + '.tmp'
                with zipfile.ZipFile(new_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
                    for dirpath, dirnames, filenames in os.walk(tmp):
                        for fn in filenames:
                            full = os.path.join(dirpath, fn)
                            arcname = os.path.relpath(full, tmp)
                            zf.write(full, arcname)
                os.replace(new_zip, zip_path)
                print(f"  Done — updated {zip_path} ({len(written)} config file(s))")

        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    main()
