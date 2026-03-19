# QA Container

One-shot Railway container that runs Newman (Postman) + Playwright tests
against a deployed app, then writes a combined JSON report.

## Files

```
qa-container/
  Dockerfile          # Container definition
  entrypoint.py       # Runs Newman + Playwright, writes qa_report.json
  clone_tests.sh      # Clones your test repo at container startup
  trigger_qa.py       # Run from your build pipeline to trigger + poll the container
  requirements.txt    # Python deps (requests only)
```

## Expected test repo structure

```
your-test-repo/
  postman/
    my_collection.json      # One or more Postman collection files
    environment.json        # Postman environment (optional)
  playwright/
    package.json            # Playwright project
    playwright.config.ts
    tests/
      smoke.spec.ts
      ...
```

## Playwright test setup

Tests must read `TARGET_URL` or `BASE_URL` from env:

```typescript
// playwright.config.ts
const baseURL = process.env.TARGET_URL || process.env.BASE_URL || 'http://localhost:3000';

export default defineConfig({
  use: { baseURL },
});
```

## Railway setup

1. Create a new Railway project for the QA container
2. Deploy this directory as a Railway service
3. Set these env vars on the Railway service:
   - `TEST_REPO_URL`     — your test repo git URL
   - `TEST_REPO_BRANCH`  — branch to use (default: main)
   - `TARGET_URL`        — set dynamically per run by trigger_qa.py

## Running from your build pipeline

```bash
# After deploying to Vercel + Railway:
python trigger_qa.py \
  --target-url https://myapp.vercel.app \
  --service-id <railway-qa-service-id>

# Or via env vars:
export TARGET_URL=https://myapp.vercel.app
export RAILWAY_QA_SERVICE_ID=xxx
export RAILWAY_API_TOKEN=xxx
python trigger_qa.py
```

## One-line wrapper

```bash
export TARGET_URL=https://myapp.vercel.app
export RAILWAY_QA_SERVICE_ID=xxx
export RAILWAY_API_TOKEN=xxx
./run_post_deploy_qa.sh
```

## Output

`qa_report.json` written locally by `trigger_qa.py`:

```json
{
  "meta": {
    "timestamp": "2026-03-06T12:00:00Z",
    "target_url": "https://myapp.vercel.app",
    "overall_passed": true
  },
  "newman": {
    "skipped": false,
    "overall_passed": true,
    "collections": [...]
  },
  "playwright": {
    "skipped": false,
    "passed": true,
    "stats": { "expected": 10, "unexpected": 0 }
  }
}
```

## Exit codes

- `0` — all tests passed
- `1` — one or more tests failed, timeout, or missing config

This means you can use `trigger_qa.py` as a pipeline gate:
```bash
python trigger_qa.py || { echo "QA failed — aborting deploy"; exit 1; }
```
