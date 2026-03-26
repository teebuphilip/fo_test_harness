#!/usr/bin/env python3
"""
generate_tests.py — FO Test Scaffolder

Scans FO build artifacts (business/backend/routes/*.py + business/frontend/pages/*.jsx)
and generates Playwright E2E tests + Newman (Postman) collections for post-deploy QA.

Adapted from alirezarezvani/claude-skills playwright-pro + senior-qa patterns,
rewritten for FO's FastAPI + React boilerplate artifact structure.

Usage:
    # From an artifacts directory
    python generate_tests.py --artifacts fo_harness_runs/my_startup_BLOCK_B_*/build/iteration_19_artifacts

    # From a ZIP
    python generate_tests.py --zip fo_harness_runs/my_startup_BLOCK_B_*.zip

    # With intake JSON for richer test generation
    python generate_tests.py --artifacts <dir> --intake intake/intake_runs/my_startup/my_startup.json

    # Specify output directory
    python generate_tests.py --artifacts <dir> --output tests/

Output:
    tests/
      postman/
        api_collection.json       # Newman-ready Postman collection
        environment.json          # Postman environment with BASE_URL
      playwright/
        package.json              # Playwright project
        playwright.config.ts      # Config with TARGET_URL from env
        tests/
          auth.spec.ts            # Auth flow tests
          <entity>.spec.ts        # Per-entity CRUD tests
          dashboard.spec.ts       # Dashboard/page tests
          smoke.spec.ts           # Basic smoke tests

Stdlib-only — no external dependencies.
"""

import os
import sys
import json
import re
import ast
import argparse
import zipfile
import tempfile
import shutil
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# ── Data Classes ─────────────────────────────────────────────────────────────

@dataclass
class RouteEndpoint:
    """A FastAPI route endpoint extracted from a .py file"""
    method: str          # GET, POST, PUT, DELETE
    path: str            # e.g. /api/clients, /api/clients/{id}
    function_name: str   # e.g. get_clients, create_client
    has_auth: bool       # Uses Depends(get_current_user)
    has_body: bool       # Has a Pydantic body param
    body_schema: str     # e.g. ClientCreate
    route_file: str      # e.g. business/backend/routes/clients.py
    entity: str          # e.g. clients (derived from filename)


@dataclass
class PageInfo:
    """A React page extracted from a .jsx file"""
    name: str            # e.g. ClientsPage
    file_path: str       # e.g. business/frontend/pages/ClientsPage.jsx
    entity: str          # e.g. clients (derived from filename)
    has_form: bool       # Contains form elements
    has_table: bool      # Contains table/list rendering
    has_modal: bool      # Contains modal/dialog
    api_calls: List[str] # API paths called via fetch/axios
    has_auth: bool       # Uses useAuth0 or similar


@dataclass
class IntakeContext:
    """Extracted context from intake JSON"""
    startup_name: str
    entities: List[str]
    features: List[str]
    has_auth: bool
    has_stripe: bool


# ── Route Scanner ────────────────────────────────────────────────────────────

class RouteScanner:
    """Scans business/backend/routes/*.py for FastAPI endpoints"""

    # @router.get("/path") pattern
    ROUTE_PATTERN = re.compile(
        r'@router\.(get|post|put|delete|patch)\(\s*["\']([^"\']+)["\']',
        re.IGNORECASE
    )

    # Depends(get_current_user) pattern
    AUTH_PATTERN = re.compile(r'Depends\s*\(\s*get_current_user\s*\)')

    # Body parameter pattern: param: SchemaName
    BODY_PATTERN = re.compile(r'(\w+)\s*:\s*(\w+(?:Create|Update|Schema|Input|Request))')

    def __init__(self, artifacts_dir: Path):
        self.artifacts_dir = artifacts_dir
        self.routes_dir = artifacts_dir / 'business' / 'backend' / 'routes'

    def scan(self) -> List[RouteEndpoint]:
        endpoints = []
        if not self.routes_dir.exists():
            print(f"  [routes] Directory not found: {self.routes_dir}")
            return endpoints

        for py_file in sorted(self.routes_dir.glob('*.py')):
            if py_file.name.startswith('__'):
                continue
            file_endpoints = self._scan_file(py_file)
            endpoints.extend(file_endpoints)

        print(f"  [routes] Found {len(endpoints)} endpoints across {len(list(self.routes_dir.glob('*.py')))} route files")
        return endpoints

    def _scan_file(self, py_file: Path) -> List[RouteEndpoint]:
        endpoints = []
        entity = py_file.stem  # e.g. "clients" from clients.py
        route_prefix = f"/api/{entity}"

        try:
            content = py_file.read_text(encoding='utf-8')
        except Exception:
            return endpoints

        file_has_auth = bool(self.AUTH_PATTERN.search(content))

        for match in self.ROUTE_PATTERN.finditer(content):
            method = match.group(1).upper()
            path_suffix = match.group(2)

            # Build full path
            if path_suffix == '/' or path_suffix == '':
                full_path = route_prefix
            elif path_suffix.startswith('/'):
                full_path = route_prefix + path_suffix
            else:
                full_path = route_prefix + '/' + path_suffix

            # Find the function definition after this decorator
            func_match = re.search(
                r'(?:async\s+)?def\s+(\w+)\s*\(',
                content[match.end():]
            )
            func_name = func_match.group(1) if func_match else 'unknown'

            # Check for body parameter in function signature
            func_block = content[match.end():match.end() + 500]
            body_match = self.BODY_PATTERN.search(func_block)
            has_body = method in ('POST', 'PUT', 'PATCH') and body_match is not None
            body_schema = body_match.group(2) if body_match else ''

            # Check auth on this specific route
            route_block = content[max(0, match.start() - 200):match.end() + 500]
            has_auth = bool(self.AUTH_PATTERN.search(route_block)) or file_has_auth

            endpoints.append(RouteEndpoint(
                method=method,
                path=full_path,
                function_name=func_name,
                has_auth=has_auth,
                has_body=has_body,
                body_schema=body_schema,
                route_file=str(py_file.relative_to(self.artifacts_dir)),
                entity=entity,
            ))

        return endpoints


# ── Page Scanner ─────────────────────────────────────────────────────────────

class PageScanner:
    """Scans business/frontend/pages/*.jsx for React page components"""

    FORM_PATTERNS = [r'<form', r'handleSubmit', r'onSubmit', r'<input', r'<textarea', r'<select']
    TABLE_PATTERNS = [r'<table', r'<Table', r'\.map\(', r'<DataGrid', r'<List']
    MODAL_PATTERNS = [r'Modal', r'Dialog', r'isOpen', r'setIsOpen', r'showModal']
    AUTH_PATTERNS = [r'useAuth0', r'getAccessTokenSilently', r'isAuthenticated']
    API_CALL_PATTERN = re.compile(r'''(?:api|fetch|axios)\s*\.\s*(?:get|post|put|delete|patch)\s*\(\s*[`'"]([^`'"]+)[`'"]''')

    def __init__(self, artifacts_dir: Path):
        self.artifacts_dir = artifacts_dir
        self.pages_dir = artifacts_dir / 'business' / 'frontend' / 'pages'

    def scan(self) -> List[PageInfo]:
        pages = []
        if not self.pages_dir.exists():
            print(f"  [pages] Directory not found: {self.pages_dir}")
            return pages

        for jsx_file in sorted(self.pages_dir.glob('*.jsx')):
            if jsx_file.name.startswith('__'):
                continue
            page = self._scan_file(jsx_file)
            if page:
                pages.append(page)

        print(f"  [pages] Found {len(pages)} pages")
        return pages

    def _scan_file(self, jsx_file: Path) -> Optional[PageInfo]:
        try:
            content = jsx_file.read_text(encoding='utf-8')
        except Exception:
            return None

        name = jsx_file.stem  # e.g. ClientsPage
        # Derive entity: ClientsPage -> clients, DashboardPage -> dashboard
        entity = re.sub(r'Page$', '', name)
        entity = re.sub(r'([a-z])([A-Z])', r'\1_\2', entity).lower()

        has_form = any(re.search(p, content) for p in self.FORM_PATTERNS)
        has_table = any(re.search(p, content) for p in self.TABLE_PATTERNS)
        has_modal = any(re.search(p, content) for p in self.MODAL_PATTERNS)
        has_auth = any(re.search(p, content) for p in self.AUTH_PATTERNS)

        api_calls = self.API_CALL_PATTERN.findall(content)

        return PageInfo(
            name=name,
            file_path=str(jsx_file.relative_to(self.artifacts_dir)),
            entity=entity,
            has_form=has_form,
            has_table=has_table,
            has_modal=has_modal,
            api_calls=api_calls,
            has_auth=has_auth,
        )


# ── Intake Parser ────────────────────────────────────────────────────────────

class IntakeParser:
    """Extracts test-relevant context from intake JSON"""

    def parse(self, intake_path: Path) -> Optional[IntakeContext]:
        if not intake_path.exists():
            return None

        try:
            with open(intake_path) as f:
                data = json.load(f)
        except Exception:
            return None

        entities = []
        features = []

        # Extract entities from various intake shapes
        for key in ('entities', 'data_entities', 'models'):
            if key in data and isinstance(data[key], list):
                entities.extend(data[key])

        # Phase context entities
        phase_ctx = data.get('_phase_context', {})
        if 'entities' in phase_ctx:
            entities.extend(phase_ctx['entities'])

        # Features
        for key in ('features', 'intelligence_features', 'feature_list'):
            if key in data and isinstance(data[key], list):
                features.extend(data[key])

        # Detect integrations
        raw = json.dumps(data).lower()
        has_auth = 'auth0' in raw or 'authentication' in raw or 'login' in raw
        has_stripe = 'stripe' in raw or 'payment' in raw or 'subscription' in raw

        return IntakeContext(
            startup_name=data.get('startup_name', data.get('app_name', 'app')),
            entities=[e if isinstance(e, str) else str(e) for e in entities],
            features=[f if isinstance(f, str) else str(f) for f in features],
            has_auth=has_auth,
            has_stripe=has_stripe,
        )


# ── Postman Collection Generator ─────────────────────────────────────────────

class PostmanGenerator:
    """Generates a Newman-ready Postman collection from route endpoints"""

    def generate(self, endpoints: List[RouteEndpoint], startup_name: str = 'app') -> dict:
        """Generate a Postman collection JSON"""
        items_by_entity = {}

        for ep in endpoints:
            if ep.entity not in items_by_entity:
                items_by_entity[ep.entity] = []

            request = {
                'method': ep.method,
                'header': [],
                'url': {
                    'raw': '{{baseUrl}}' + ep.path,
                    'host': ['{{baseUrl}}'],
                    'path': [p for p in ep.path.strip('/').split('/') if p],
                },
            }

            # Add auth header
            if ep.has_auth:
                request['header'].append({
                    'key': 'Authorization',
                    'value': 'Bearer {{authToken}}',
                    'type': 'text',
                })

            # Add content-type + body for write operations
            if ep.has_body:
                request['header'].append({
                    'key': 'Content-Type',
                    'value': 'application/json',
                    'type': 'text',
                })
                request['body'] = {
                    'mode': 'raw',
                    'raw': json.dumps(self._generate_sample_body(ep), indent=2),
                }

            # Build test script
            tests = self._generate_tests(ep)

            item = {
                'name': f"{ep.method} {ep.path}",
                'request': request,
                'event': [{
                    'listen': 'test',
                    'script': {
                        'type': 'text/javascript',
                        'exec': tests,
                    },
                }],
            }

            items_by_entity[ep.entity].append(item)

        # Build folder structure
        folders = []
        for entity, items in items_by_entity.items():
            folders.append({
                'name': entity.title(),
                'item': items,
            })

        # Add smoke test folder
        smoke_items = self._generate_smoke_items(endpoints)
        if smoke_items:
            folders.insert(0, {'name': 'Smoke', 'item': smoke_items})

        collection = {
            'info': {
                'name': f"{startup_name} — API Tests",
                '_postman_id': f"{startup_name}-api-tests",
                'schema': 'https://schema.getpostman.com/json/collection/v2.1.0/collection.json',
            },
            'item': folders,
        }

        return collection

    def generate_environment(self, startup_name: str = 'app') -> dict:
        return {
            'id': f"{startup_name}-env",
            'name': f"{startup_name} Environment",
            'values': [
                {'key': 'baseUrl', 'value': '{{TARGET_URL}}', 'enabled': True},
                {'key': 'authToken', 'value': '', 'enabled': True},
            ],
        }

    def _generate_sample_body(self, ep: RouteEndpoint) -> dict:
        """Generate a placeholder request body"""
        body = {}
        entity_singular = ep.entity.rstrip('s')

        if 'Create' in ep.body_schema or ep.method == 'POST':
            body = {
                'name': f'Test {entity_singular}',
                'description': f'Auto-generated test {entity_singular}',
            }
        elif 'Update' in ep.body_schema or ep.method == 'PUT':
            body = {
                'name': f'Updated {entity_singular}',
            }

        return body

    def _generate_tests(self, ep: RouteEndpoint) -> List[str]:
        """Generate Postman test scripts for an endpoint"""
        tests = []

        if ep.method == 'GET':
            tests.extend([
                f'pm.test("{ep.method} {ep.path} returns 200", function () {{',
                '    pm.response.to.have.status(200);',
                '});',
                '',
                f'pm.test("{ep.method} {ep.path} returns JSON", function () {{',
                '    pm.response.to.be.json;',
                '});',
            ])
        elif ep.method == 'POST':
            tests.extend([
                f'pm.test("{ep.method} {ep.path} returns 201 or 200", function () {{',
                '    pm.expect(pm.response.code).to.be.oneOf([200, 201]);',
                '});',
                '',
                f'pm.test("{ep.method} {ep.path} returns JSON", function () {{',
                '    pm.response.to.be.json;',
                '});',
            ])
        elif ep.method == 'PUT' or ep.method == 'PATCH':
            tests.extend([
                f'pm.test("{ep.method} {ep.path} returns 200", function () {{',
                '    pm.response.to.have.status(200);',
                '});',
            ])
        elif ep.method == 'DELETE':
            tests.extend([
                f'pm.test("{ep.method} {ep.path} returns 200 or 204", function () {{',
                '    pm.expect(pm.response.code).to.be.oneOf([200, 204]);',
                '});',
            ])

        # Auth test
        if ep.has_auth:
            tests.extend([
                '',
                f'pm.test("{ep.method} {ep.path} rejects without auth", function () {{',
                '    // Run this request without Authorization header to verify 401',
                '});',
            ])

        # Response time
        tests.extend([
            '',
            f'pm.test("{ep.method} {ep.path} responds within 5s", function () {{',
            '    pm.expect(pm.response.responseTime).to.be.below(5000);',
            '});',
        ])

        return tests

    def _generate_smoke_items(self, endpoints: List[RouteEndpoint]) -> list:
        """Generate basic smoke test items — one GET per entity"""
        seen = set()
        items = []

        for ep in endpoints:
            if ep.method == 'GET' and ep.entity not in seen and '{' not in ep.path:
                seen.add(ep.entity)
                items.append({
                    'name': f"Smoke: GET {ep.path}",
                    'request': {
                        'method': 'GET',
                        'header': [{'key': 'Authorization', 'value': 'Bearer {{authToken}}', 'type': 'text'}] if ep.has_auth else [],
                        'url': {
                            'raw': '{{baseUrl}}' + ep.path,
                            'host': ['{{baseUrl}}'],
                            'path': [p for p in ep.path.strip('/').split('/') if p],
                        },
                    },
                    'event': [{
                        'listen': 'test',
                        'script': {
                            'type': 'text/javascript',
                            'exec': [
                                f'pm.test("Smoke: {ep.path} is reachable", function () {{',
                                '    pm.expect(pm.response.code).to.be.oneOf([200, 401, 403]);',
                                '});',
                            ],
                        },
                    }],
                })

        return items


# ── Playwright Generator ─────────────────────────────────────────────────────

class PlaywrightGenerator:
    """Generates Playwright E2E test files from page and route info"""

    def generate_config(self) -> str:
        return '''import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: [['json', { outputFile: '/app/results/playwright_results.json' }], ['list']],
  use: {
    baseURL: process.env.TARGET_URL || process.env.BASE_URL || 'http://localhost:3000',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  ],
});
'''

    def generate_package_json(self, startup_name: str = 'app') -> dict:
        return {
            'name': f'{startup_name}-e2e-tests',
            'version': '1.0.0',
            'private': True,
            'scripts': {
                'test': 'npx playwright test',
                'test:headed': 'npx playwright test --headed',
            },
            'devDependencies': {
                '@playwright/test': '^1.40.0',
            },
        }

    def generate_smoke_test(self, pages: List[PageInfo], endpoints: List[RouteEndpoint]) -> str:
        """Generate a basic smoke test that hits the landing page and checks API health"""
        lines = [
            "import { test, expect } from '@playwright/test';",
            "",
            "test.describe('Smoke Tests', () => {",
            "",
            "  test('landing page loads', async ({ page }) => {",
            "    const response = await page.goto('/');",
            "    expect(response?.status()).toBeLessThan(400);",
            "    await expect(page.locator('body')).toBeVisible();",
            "  });",
            "",
            "  test('dashboard loads for authenticated user', async ({ page }) => {",
            "    // TODO: Add auth setup (storageState or API login)",
            "    const response = await page.goto('/dashboard');",
            "    expect(response?.status()).toBeLessThan(500);",
            "  });",
        ]

        # Add one API health check per entity (GET list endpoint)
        seen = set()
        for ep in endpoints:
            if ep.method == 'GET' and ep.entity not in seen and '{' not in ep.path:
                seen.add(ep.entity)
                lines.extend([
                    "",
                    f"  test('API: {ep.path} responds', async ({{ request }}) => {{",
                    f"    const response = await request.get('{ep.path}');",
                    f"    expect(response.status()).toBeLessThan(500);",
                    "  });",
                ])

        lines.extend(["", "});", ""])
        return '\n'.join(lines)

    def generate_auth_test(self) -> str:
        """Generate Auth0 login/logout tests"""
        return '''import { test, expect } from '@playwright/test';

test.describe('Authentication', () => {

  test('unauthenticated user is redirected to login', async ({ page }) => {
    await page.goto('/dashboard');
    // Auth0 should redirect to login page or Auth0 universal login
    await expect(page).toHaveURL(/login|auth0/);
  });

  test('login page renders correctly', async ({ page }) => {
    await page.goto('/login');
    // Should show login form or Auth0 universal login
    await expect(page.locator('body')).toBeVisible();
  });

  // NOTE: Full login test requires test credentials in env vars.
  // Set TEST_EMAIL and TEST_PASSWORD to enable.
  test('login with valid credentials', async ({ page }) => {
    const email = process.env.TEST_EMAIL;
    const password = process.env.TEST_PASSWORD;
    test.skip(!email || !password, 'TEST_EMAIL and TEST_PASSWORD not set');

    await page.goto('/login');

    // Auth0 Universal Login
    await page.getByLabel(/email/i).fill(email!);
    await page.getByLabel(/password/i).fill(password!);
    await page.getByRole('button', { name: /continue|log in|sign in/i }).click();

    // Should redirect to dashboard after login
    await expect(page).toHaveURL(/dashboard/, { timeout: 10000 });
  });

  test('logout redirects to landing', async ({ page }) => {
    // TODO: Set up authenticated state first
    await page.goto('/');
    // Find and click logout if visible
    const logoutBtn = page.getByRole('button', { name: /log out|sign out/i });
    if (await logoutBtn.isVisible()) {
      await logoutBtn.click();
      await expect(page).toHaveURL(/login|\\//);
    }
  });
});
'''

    def generate_entity_test(self, entity: str, endpoints: List[RouteEndpoint],
                              page_info: Optional[PageInfo] = None) -> str:
        """Generate CRUD + page tests for a single entity"""
        entity_title = entity.replace('_', ' ').title()
        entity_singular = entity.rstrip('s')
        lines = [
            "import { test, expect } from '@playwright/test';",
            "",
            f"test.describe('{entity_title}', () => {{",
        ]

        # ── API tests ────────────────────────────────────────────────────
        api_endpoints = [ep for ep in endpoints if ep.entity == entity]

        if api_endpoints:
            lines.extend(["", f"  test.describe('API: /api/{entity}', () => {{"])

            for ep in api_endpoints:
                test_name = f"{ep.method} {ep.path}"

                if ep.method == 'GET' and '{' not in ep.path:
                    lines.extend([
                        "",
                        f"    test('{test_name} returns list', async ({{ request }}) => {{",
                        f"      const response = await request.get('{ep.path}');",
                        f"      expect(response.status()).toBe(200);",
                        f"      const body = await response.json();",
                        f"      expect(Array.isArray(body) || body.items || body.data).toBeTruthy();",
                        "    });",
                    ])
                elif ep.method == 'GET' and '{' in ep.path:
                    lines.extend([
                        "",
                        f"    test('{test_name} returns item or 404', async ({{ request }}) => {{",
                        f"      const response = await request.get('{ep.path.replace('{id}', '1').replace('{' + entity_singular + '_id}', '1')}');",
                        f"      expect([200, 404]).toContain(response.status());",
                        "    });",
                    ])
                elif ep.method == 'POST':
                    lines.extend([
                        "",
                        f"    test('{test_name} creates item', async ({{ request }}) => {{",
                        f"      const response = await request.post('{ep.path}', {{",
                        f"        data: {{ name: 'Test {entity_singular}', description: 'Auto-generated' }},",
                        "      });",
                        f"      expect([200, 201, 422]).toContain(response.status());",
                        "    });",
                    ])
                elif ep.method in ('PUT', 'PATCH'):
                    lines.extend([
                        "",
                        f"    test('{test_name} updates item', async ({{ request }}) => {{",
                        f"      const response = await request.{ep.method.lower()}('{ep.path.replace('{id}', '1').replace('{' + entity_singular + '_id}', '1')}', {{",
                        f"        data: {{ name: 'Updated {entity_singular}' }},",
                        "      });",
                        f"      expect([200, 404, 422]).toContain(response.status());",
                        "    });",
                    ])
                elif ep.method == 'DELETE':
                    lines.extend([
                        "",
                        f"    test('{test_name} deletes item', async ({{ request }}) => {{",
                        f"      const response = await request.delete('{ep.path.replace('{id}', '99999').replace('{' + entity_singular + '_id}', '99999')}');",
                        f"      expect([200, 204, 404]).toContain(response.status());",
                        "    });",
                    ])

            lines.extend(["", "  });"])

        # ── Page tests ───────────────────────────────────────────────────
        if page_info:
            kebab = page_info.entity.replace('_', '-')
            page_url = f"/dashboard/{kebab}"

            lines.extend([
                "",
                f"  test.describe('Page: {page_info.name}', () => {{",
                "",
                f"    test('page loads', async ({{ page }}) => {{",
                f"      // TODO: Add auth setup",
                f"      const response = await page.goto('{page_url}');",
                f"      expect(response?.status()).toBeLessThan(500);",
                "    });",
            ])

            if page_info.has_table:
                lines.extend([
                    "",
                    f"    test('displays {entity} list', async ({{ page }}) => {{",
                    f"      await page.goto('{page_url}');",
                    f"      // Should show a table or list of {entity}",
                    f"      const list = page.getByRole('table').or(page.getByRole('list'));",
                    f"      await expect(list.first()).toBeVisible({{ timeout: 10000 }});",
                    "    });",
                ])

            if page_info.has_form:
                lines.extend([
                    "",
                    f"    test('form submits successfully', async ({{ page }}) => {{",
                    f"      await page.goto('{page_url}');",
                    "",
                    f"      // Open create form (button or link)",
                    f"      const createBtn = page.getByRole('button', {{ name: /create|add|new/i }});",
                    f"      if (await createBtn.isVisible()) {{",
                    f"        await createBtn.click();",
                    f"      }}",
                    "",
                    f"      // TODO: Fill form fields from business_config.json",
                    f"      // await page.getByLabel(/name/i).fill('Test {entity_singular}');",
                    "",
                    f"      // Submit",
                    f"      // await page.getByRole('button', {{ name: /save|submit|create/i }}).click();",
                    f"      // await expect(page.getByText(/success|created/i)).toBeVisible();",
                    "    });",
                ])

            if page_info.has_modal:
                lines.extend([
                    "",
                    f"    test('modal opens and closes', async ({{ page }}) => {{",
                    f"      await page.goto('{page_url}');",
                    f"      // TODO: Trigger modal open",
                    f"      // await expect(page.getByRole('dialog')).toBeVisible();",
                    f"      // await page.keyboard.press('Escape');",
                    f"      // await expect(page.getByRole('dialog')).not.toBeVisible();",
                    "    });",
                ])

            lines.extend(["", "  });"])

        lines.extend(["", "});", ""])
        return '\n'.join(lines)

    def generate_dashboard_test(self, pages: List[PageInfo]) -> str:
        """Generate a test that visits each dashboard page"""
        lines = [
            "import { test, expect } from '@playwright/test';",
            "",
            "test.describe('Dashboard Pages', () => {",
        ]

        for page_info in pages:
            kebab = page_info.entity.replace('_', '-')
            page_url = f"/dashboard/{kebab}"
            lines.extend([
                "",
                f"  test('{page_info.name} loads without error', async ({{ page }}) => {{",
                f"    // TODO: Add auth setup",
                f"    const response = await page.goto('{page_url}');",
                f"    expect(response?.status()).toBeLessThan(500);",
                f"    await expect(page.locator('body')).toBeVisible();",
                "  });",
            ])

        lines.extend(["", "});", ""])
        return '\n'.join(lines)


# ── Main Scaffolder ──────────────────────────────────────────────────────────

class FO_TestScaffolder:
    """Main orchestrator: scan artifacts → generate tests"""

    def __init__(self, artifacts_dir: Path, output_dir: Path,
                 intake_path: Optional[Path] = None):
        self.artifacts_dir = artifacts_dir
        self.output_dir = output_dir
        self.intake_path = intake_path

    def run(self) -> dict:
        print(f"Scanning artifacts: {self.artifacts_dir}")

        # Parse intake if available
        intake_ctx = None
        if self.intake_path:
            intake_ctx = IntakeParser().parse(self.intake_path)
            if intake_ctx:
                print(f"  [intake] {intake_ctx.startup_name}: {len(intake_ctx.entities)} entities, {len(intake_ctx.features)} features")

        startup_name = intake_ctx.startup_name if intake_ctx else 'app'

        # Scan artifacts
        route_scanner = RouteScanner(self.artifacts_dir)
        page_scanner = PageScanner(self.artifacts_dir)

        endpoints = route_scanner.scan()
        pages = page_scanner.scan()

        if not endpoints and not pages:
            print("WARNING: No routes or pages found in artifacts. Generating minimal smoke tests only.")

        # Create output directories
        postman_dir = self.output_dir / 'postman'
        pw_dir = self.output_dir / 'playwright'
        pw_tests_dir = pw_dir / 'tests'

        postman_dir.mkdir(parents=True, exist_ok=True)
        pw_tests_dir.mkdir(parents=True, exist_ok=True)

        generated = []

        # ── Generate Postman collection ──────────────────────────────────
        if endpoints:
            postman_gen = PostmanGenerator()
            collection = postman_gen.generate(endpoints, startup_name)
            env = postman_gen.generate_environment(startup_name)

            col_path = postman_dir / 'api_collection.json'
            env_path = postman_dir / 'environment.json'

            with open(col_path, 'w') as f:
                json.dump(collection, f, indent=2)
            with open(env_path, 'w') as f:
                json.dump(env, f, indent=2)

            generated.extend([str(col_path), str(env_path)])
            print(f"  [postman] {col_path}")
            print(f"  [postman] {env_path}")

        # ── Generate Playwright tests ────────────────────────────────────
        pw_gen = PlaywrightGenerator()

        # Config + package.json
        config_path = pw_dir / 'playwright.config.ts'
        config_path.write_text(pw_gen.generate_config(), encoding='utf-8')
        generated.append(str(config_path))

        pkg_path = pw_dir / 'package.json'
        with open(pkg_path, 'w') as f:
            json.dump(pw_gen.generate_package_json(startup_name), f, indent=2)
        generated.append(str(pkg_path))

        # Smoke test
        smoke_path = pw_tests_dir / 'smoke.spec.ts'
        smoke_path.write_text(pw_gen.generate_smoke_test(pages, endpoints), encoding='utf-8')
        generated.append(str(smoke_path))
        print(f"  [playwright] {smoke_path}")

        # Auth test
        if intake_ctx and intake_ctx.has_auth or any(p.has_auth for p in pages):
            auth_path = pw_tests_dir / 'auth.spec.ts'
            auth_path.write_text(pw_gen.generate_auth_test(), encoding='utf-8')
            generated.append(str(auth_path))
            print(f"  [playwright] {auth_path}")

        # Per-entity tests
        entities_seen = set()
        for ep in endpoints:
            entities_seen.add(ep.entity)
        for p in pages:
            entities_seen.add(p.entity)

        for entity in sorted(entities_seen):
            entity_endpoints = [ep for ep in endpoints if ep.entity == entity]
            entity_page = next((p for p in pages if p.entity == entity), None)

            if entity_endpoints or entity_page:
                test_path = pw_tests_dir / f'{entity}.spec.ts'
                test_path.write_text(
                    pw_gen.generate_entity_test(entity, endpoints, entity_page),
                    encoding='utf-8'
                )
                generated.append(str(test_path))
                print(f"  [playwright] {test_path}")

        # Dashboard overview test
        if pages:
            dash_path = pw_tests_dir / 'dashboard.spec.ts'
            dash_path.write_text(pw_gen.generate_dashboard_test(pages), encoding='utf-8')
            generated.append(str(dash_path))
            print(f"  [playwright] {dash_path}")

        # ── Summary ──────────────────────────────────────────────────────
        result = {
            'status': 'success',
            'startup_name': startup_name,
            'artifacts_dir': str(self.artifacts_dir),
            'output_dir': str(self.output_dir),
            'endpoints_found': len(endpoints),
            'pages_found': len(pages),
            'files_generated': len(generated),
            'generated': generated,
        }

        print(f"\nDone: {len(generated)} files generated in {self.output_dir}")
        return result


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='Generate post-deploy tests from FO build artifacts',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # From artifacts directory
  python generate_tests.py --artifacts fo_harness_runs/my_startup_BLOCK_B_*/build/iteration_19_artifacts

  # From ZIP
  python generate_tests.py --zip fo_harness_runs/my_startup_BLOCK_B_*.zip

  # With intake for richer tests
  python generate_tests.py --artifacts <dir> --intake intake/intake_runs/my_startup/my_startup.json

  # Custom output
  python generate_tests.py --artifacts <dir> --output my_tests/
        """
    )
    parser.add_argument('--artifacts', help='Path to artifacts directory')
    parser.add_argument('--zip', help='Path to build ZIP (extracts to temp dir)')
    parser.add_argument('--intake', help='Path to intake JSON for richer test generation')
    parser.add_argument('--output', '-o', default='tests', help='Output directory (default: tests/)')
    parser.add_argument('--json', action='store_true', help='Print results as JSON')

    args = parser.parse_args()

    if not args.artifacts and not args.zip:
        parser.error('Provide --artifacts or --zip')

    temp_dir = None
    artifacts_dir = None

    try:
        if args.zip:
            if not os.path.isfile(args.zip):
                print(f"ERROR: ZIP not found: {args.zip}")
                sys.exit(1)
            temp_dir = tempfile.mkdtemp(prefix='fo_test_scaffold_')
            print(f"Extracting ZIP to {temp_dir}...")
            with zipfile.ZipFile(args.zip, 'r') as zf:
                zf.extractall(temp_dir)
            # Find the business/ directory inside
            for root, dirs, files in os.walk(temp_dir):
                if 'business' in dirs:
                    artifacts_dir = Path(root)
                    break
            if not artifacts_dir:
                artifacts_dir = Path(temp_dir)
        else:
            artifacts_dir = Path(args.artifacts)
            if not artifacts_dir.exists():
                print(f"ERROR: Artifacts dir not found: {artifacts_dir}")
                sys.exit(1)

        intake_path = Path(args.intake) if args.intake else None
        output_dir = Path(args.output)

        scaffolder = FO_TestScaffolder(artifacts_dir, output_dir, intake_path)
        result = scaffolder.run()

        if args.json:
            print(json.dumps(result, indent=2))

    finally:
        if temp_dir and os.path.isdir(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == '__main__':
    main()
