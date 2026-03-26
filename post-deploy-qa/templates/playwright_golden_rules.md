# Playwright Golden Rules for FO Builds

Reference for generate_tests.py and any future AI-driven test generation.
Adapted from alirezarezvani/claude-skills playwright-pro.

## 10 Rules

1. **`getByRole()` over CSS/XPath** — resilient to markup changes
2. **Never `page.waitForTimeout()`** — use web-first assertions
3. **`expect(locator)` auto-retries; `expect(await locator.textContent())` does not**
4. **Isolate every test** — no shared state between tests
5. **`baseURL` in config** — zero hardcoded URLs; read from `TARGET_URL` env var
6. **Retries: 2 in CI, 0 locally**
7. **Traces: `'on-first-retry'`** — rich debugging without slowdown
8. **Fixtures over globals** — `test.extend()` for shared state
9. **One behavior per test** — multiple related assertions are fine
10. **Mock external services only** — never mock your own app

## Locator Priority

```
1. getByRole()        — buttons, links, headings, form elements
2. getByLabel()       — form fields with labels
3. getByText()        — non-interactive text
4. getByPlaceholder() — inputs with placeholder
5. getByTestId()      — when no semantic option exists
6. page.locator()     — CSS/XPath as last resort
```

## FO-Specific Patterns

### Auth0 Login Test
```typescript
// Auth0 Universal Login — use getByLabel, not CSS selectors
await page.getByLabel(/email/i).fill(email);
await page.getByLabel(/password/i).fill(password);
await page.getByRole('button', { name: /continue|log in|sign in/i }).click();
await expect(page).toHaveURL(/dashboard/, { timeout: 10000 });
```

### Authenticated API Request
```typescript
// Use Playwright's request context with auth header
const response = await request.get('/api/clients', {
  headers: { Authorization: `Bearer ${token}` },
});
expect(response.status()).toBe(200);
```

### Dashboard Page Navigation
```typescript
// FO pages mount at /dashboard/<kebab-case>
await page.goto('/dashboard/client-profiles');
await expect(page.getByRole('heading')).toBeVisible();
```

## Common Anti-Patterns to Avoid

| Anti-Pattern | Fix |
|---|---|
| `page.waitForTimeout(2000)` | `await expect(locator).toBeVisible()` |
| `page.locator('.btn-primary')` | `page.getByRole('button', { name: /submit/i })` |
| `page.$$('.list-item')` | `page.getByRole('listitem')` |
| Hardcoded `http://localhost:3000` | Use `baseURL` from config |
| `await page.click('#submit')` | `await page.getByRole('button').click()` |
| Shared state between tests | Use `test.beforeEach` for setup |
