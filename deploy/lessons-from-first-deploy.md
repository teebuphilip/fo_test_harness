# Lessons From First Deploy
# ===========================
# Every failure we hit deploying AWI (ai-workforce-intelligence) for the first time.
# Ordered roughly by when we hit them. Fix status = what we changed in the pipeline/harness.

---

## 1. Railway token: project UUID token fails everything

**Error:** `Not Authorized` on all Railway API calls (`projectCreate`, `variableUpsert`, `whoami`)

**Root cause:** We were using a project-scoped UUID token. Railway API calls require a
*personal* token for workspace-level operations.

**Fix:**
- Get personal token from `railway.app/account/tokens` — starts with `railway_...`
- Save to `~/Downloads/ACCESSKEYS/RAILWAY_TOKEN`
- `pipeline_deploy.py` now runs `railway logout` before STEP 2 so CLI session doesn't
  override the API token

---

## 2. Railway CLI session conflict

**Error:** API calls still return `Not Authorized` even with correct token in env

**Root cause:** `railway` CLI stores a session token in `~/.railway/` that takes precedence
over the env var token when the API client reads credentials.

**Fix:** `pipeline_deploy.py` runs `railway logout` before any Railway API call.

---

## 3. Railway project name too long

**Error:** `Invalid project name` from Railway API on `projectCreate`

**Root cause:** Railway rejects names over ~30 chars. The ZIP name
`ai-workforce-intelligence-downloadable-executive-report` is 55 chars.

**Fix:** `railway_deploy.py` truncates at last hyphen before 40 chars:
```python
if len(name) > 30:
    truncated = name[:30]
    last_hyphen = truncated.rfind("-")
    name = truncated[:last_hyphen] if last_hyphen > 0 else truncated
```

---

## 4. Railway requires workspaceId on projectCreate

**Error:** `You must specify a workspaceId`

**Root cause:** Railway API added a required `workspaceId` parameter to `projectCreate`.
The pipeline was calling it without this field.

**Fix:** Added `get_workspace_id()` to `RailwayAPI` — reads from `me.workspaces[0].id`
and passes it to `create_project()`.

---

## 5. Nixpacks can't detect Python — "could not determine how to build"

**Error:** Railway build fails: `Railpack: could not determine how to build`

**Root cause:** Railway scans from the repo root. `requirements.txt` and `main.py` are
in `backend/` but Railway was looking at `/`. No Python files at root = no detection.

**Fix:** `pipeline_deploy.py` writes `railway.toml` to **both** repo root AND `backend/`:
- Root: `startCommand = "cd backend && uvicorn main:app --host 0.0.0.0 --port $PORT"`
- `backend/railway.toml`: `startCommand = "uvicorn main:app --host 0.0.0.0 --port $PORT"`

---

## 6. Flat repo layout — all saas-boilerplate/ paths were wrong

**Error:** Various "file not found" errors; Railway couldn't find `main.py`

**Root cause:** `zip_to_repo.py` was updated to extract the ZIP flat
(`backend/` `frontend/` `business/` at root) but `pipeline_deploy.py` and `vercel_deploy.py`
still referenced `saas-boilerplate/backend/` etc.

**Fix:** Updated all paths in `pipeline_deploy.py` and `vercel_deploy.py`:
- `_ensure_railway_toml()` → writes to `backend/` not `saas-boilerplate/backend/`
- `_ensure_frontend_business_config()` → `frontend/src/config/`
- `_ensure_business_pages_in_src()` → `frontend/src/business/pages/`
- `vercel_deploy.py` default root → `frontend/` (was `saas-boilerplate/frontend`)

---

## 7. teebu-shared-libs not found in Railway container

**Error:** `ModuleNotFoundError: No module named 'libs'` (or similar import failure)

**Root cause:** The flat layout extraction didn't copy `teebu-shared-libs` into `backend/`.
`main.py` imports from `libs/` which lives in shared libs.

**Fix:** Fixed in `zip_to_repo.py` — shared libs now copied into `backend/` during extraction.

---

## 8. backend/config/business_config.json missing in Railway container

**Error:** `FileNotFoundError: Missing config: /app/config/business_config.json`

**Root cause:** `backend/config/business_config.json` is in `.gitignore` and wasn't pushed.
Railway container has no config files → app can't start.

**Fix:** `pipeline_deploy.py` `_ensure_frontend_business_config()` now:
1. Copies all `backend/config/*.example.json` → `*.json` if real file doesn't exist
2. Force-adds all `backend/config/*.json` via `git add -f` before push

---

## 9. stripe_config.json wrong key name

**Error:** `ValueError: stripe_secret_key is required in config`

**Root cause:** `saas-boilerplate/backend/config/stripe_config.example.json` had key
`"secret_key"` but `stripe_lib.py` reads `config.get('stripe_secret_key')` → always None.

**Fix:** Fixed `stripe_config.example.json` in boilerplate to use `stripe_secret_key`.
For deployed containers: push a `stripe_config.json` with `"stripe_secret_key": "sk_test_placeholder"`.

---

## 10. mailerlite_config.json wrong key name

**Error:** `ValueError: mailerlite_api_key is required in config`

**Root cause:** Example file had `"api_key"` but lib reads `config.get('mailerlite_api_key')`.

**Fix:** Fixed `mailerlite_config.example.json` to use `mailerlite_api_key`.

---

## 11. auth0_config.json wrong key names

**Error:** Auth0Lib silently initializes with `None` values (no hard crash, but auth fails)

**Root cause:** Example file had `"domain"`, `"client_id"`, `"client_secret"`, `"audience"`.
Lib reads `config.get('auth0_domain')`, `config.get('auth0_client_id')` etc. — prefixed.

**Fix:** Fixed `auth0_config.example.json` to use `auth0_`-prefixed keys.

---

## 12. business_config.json missing `description` field

**Error:** `KeyError: 'description'` in `main.py` line 157

**Root cause:** `main.py` does `BUSINESS_CONFIG["business"]["description"]` — hard dict access,
no `.get()`. The boilerplate example and harness-generated config both lacked this field.

Two layers of fix:
1. **Harness** (`fo_test_harness.py`): `_generate_business_config()` now includes
   `"description": tagline` in the `business` block.
2. **Pipeline** (`pipeline_deploy.py`): when copying from example, the example now has the field.

AWI was deployed before the harness fix existed — pushed `description` manually to repo.

---

## 13. GitHub App installation — can't be done via API

**Error:** `403 Forbidden` on `GET /user/installations`

**Root cause:** GitHub requires a special OAuth scope (`read:org` + app install scope) to
list/modify App installations. PATs and `gh` CLI tokens don't have it.

**Fix:** `repo_setup.py` falls back to opening `github.com/settings/installations` in browser.
User must manually grant access for Railway and Vercel GitHub Apps to the new repo.
**This is a required manual step — no automation possible.**

---

## 14. Vercel build fails with ESLint errors (CI=true)

**Error:** Vercel build fails on ESLint warnings treated as errors

**Root cause:** Vercel sets `CI=true` in the build environment. React treats any ESLint
warning as a build error under `CI=true`.

**Fix:** `vercel_deploy.py` injects `CI=false` as an env var on the Vercel project
before triggering the build.

---

## 15. business_config.json is InboxTamer-branded in boilerplate

**Root cause:** The boilerplate developer's local working copy of `business_config.json`
is their own test project (InboxTamer). This file is gitignored, so `zip_to_repo.py`
picks it up from the local filesystem — every deployed repo gets InboxTamer branding.

**Fix:** Harness now generates `business_config.json` from intake data in
`_generate_business_config()`. This writes the correct startup-specific config into the
ZIP before it's ever extracted.

**For any ZIP built before this fix:** push a corrected `business_config.json` manually.

---

## 16. email-validator missing from requirements.txt

**Error:** `ImportError: email-validator is not installed, run pip install 'pydantic[email]'`

**Root cause:** `main.py` defines `class SignupRequest(BaseModel)` with an `EmailStr` field (line 184).
Pydantic's `EmailStr` type requires the separate `email-validator` package — it is NOT included
when you install `pydantic` alone. The boilerplate `requirements.txt` only listed `pydantic>=2.5.0`.

**Fix:** Added `email-validator>=2.0.0` to `saas-boilerplate/backend/requirements.txt`.
Also pushed directly to deployed AWI repo.

---

## 17. require_ajax_header defined after first use — NameError at startup

**Error:** `NameError: name 'require_ajax_header' is not defined` at `main.py` line 268

**Root cause:** `require_ajax_header` is a local function defined at line ~628 in `main.py`,
but Python evaluates `Depends(require_ajax_header)` as a default argument at module load time
(line 268) — before the function exists in the namespace.

**Fix:** Moved `require_ajax_header` definition to just above the `# AUTH ENDPOINTS` section.
Removed the duplicate definition at the old location.
Applied to both AWI repo and boilerplate `saas-boilerplate/backend/main.py`.

---

## Summary: Required manual steps (can't be automated)

1. **Railway personal token** — get from `railway.app/account/tokens`, save to ACCESSKEYS
2. **GitHub App access** — must be granted in browser at `github.com/settings/installations`
   for both Railway and Vercel apps on every new repo
3. **Railway env vars** — if API token is wrong/expired, set manually in Railway dashboard:
   `AUTH0_DOMAIN`, `AUTH0_AUDIENCE`, `AUTH0_ISSUER_BASE_URL`, `CORS_ORIGINS`, `ENVIRONMENT`

---

## Files changed as a result of all the above

| File | Change |
|------|--------|
| `deploy/railway_deploy.py` | `get_workspace_id()`, `create_project(workspaceId)`, name truncation |
| `deploy/pipeline_deploy.py` | `railway logout`, flat layout paths, force-add all `backend/config/*.json`, dual `railway.toml` |
| `deploy/vercel_deploy.py` | `root_directory=frontend/`, `CI=false` env var |
| `deploy/zip_to_repo.py` | flat layout extraction, shared libs copy |
| `deploy/repo_setup.py` | new — GitHub repo + App install helper |
| `deploy/auth0_setup.py` | new — Auth0 SPA + API creation per project |
| `fo_test_harness.py` | `_generate_business_config()` — generates startup-specific config from intake |
| `saas-boilerplate/backend/config/stripe_config.example.json` | fixed key names |
| `saas-boilerplate/backend/config/mailerlite_config.example.json` | fixed key names |
| `saas-boilerplate/backend/config/auth0_config.example.json` | fixed key names |
| `saas-boilerplate/backend/requirements.txt` | added `email-validator>=2.0.0` |
| `saas-boilerplate/backend/main.py` | moved `require_ajax_header` above AUTH ENDPOINTS |
