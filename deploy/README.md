# Deploy Pipeline

Converts a harness output ZIP into a live Railway (backend) + Vercel (frontend) deployment.

---

## Where You Are in the Pipeline

```
run_integration_and_feature_build.sh
        ↓
  fo_harness_runs/<startup>_BLOCK_B_full_<ts>.zip   ← you have this
        ↓
  check_final_zip.py                                ← auto-ran at end of build
        ↓
  YOU ARE HERE
        ↓
  zip_to_repo.py  →  repo_setup.py  →  pipeline_deploy.py
        ↓
  Live app on Railway + Vercel
```

If you're starting from scratch (new client), see `NON_AI_CLIENT_PIPELINE.md` in the project root.

---

## Prerequisites

```bash
export GITHUB_TOKEN=ghp_xxxxx
export GITHUB_USERNAME=yourname
export RAILWAY_TOKEN=xxxxx
export VERCEL_TOKEN=xxxxx
export ANTHROPIC_API_KEY=sk-ant-xxxxx   # used by pipeline_deploy for AI config generation
export OPENAI_API_KEY=sk-xxxxx          # used by pipeline_deploy for AI config generation
```

---

## Deploy Sequence

### Step 1 — ZIP → GitHub repo

Extracts the harness ZIP into `~/Documents/work/<startup_name>/`, initialises a git repo (or commits updates if the repo already exists), and pushes to GitHub.

```bash
python deploy/zip_to_repo.py fo_harness_runs/my_startup_BLOCK_B_full_<timestamp>.zip
```

Output: `~/Documents/work/my_startup/` with git history + GitHub remote set.

---

### Step 2 — Grant GitHub App access (first deploy only)

Railway and Vercel need access to the new GitHub repo before they can deploy it.

```bash
python deploy/repo_setup.py --repo my-startup
```

This grants both the Railway and Vercel GitHub Apps access to the repo. Only needed once per repo.

---

### Step 3 — Full deploy (Railway + Vercel)

Runs AI config generation, pushes to GitHub, deploys backend to Railway, deploys frontend to Vercel, then updates Auth0 callback URLs to match the live endpoints.

```bash
python deploy/pipeline_deploy.py --repo ~/Documents/work/my_startup
```

During the run:
- all console output is also written to `deploy/pipeline-deploy-logs/`
- each log file is timestamped per run
- each log line in the file gets a date/time prefix
- Railway now reuses an existing public domain if one already exists for the service; otherwise it generates one automatically
- the resolved Railway backend URL is injected into the Vercel deploy as the frontend API base URL

**Flags:**

| Flag | Purpose |
|------|---------|
| `--repo <path>` | Path to the local repo (required) |
| `--new-project` | Force create a new Railway/Vercel project (vs update existing) |
| `--backend-only` | Deploy Railway only, skip Vercel |
| `--frontend-only` | Deploy Vercel only, skip Railway |

**Output:** Prints live Railway URL + Vercel URL.

Example backend result:
- `https://backend-production-xxxx.up.railway.app`

Note:
- Railway-managed public domains are generated `*.up.railway.app`
- if you want a human-chosen hostname, add a custom domain you control after deploy

---

## Configs Only (no deploy)

Use `pipeline_prepare.py` when you want to generate `railway.deploy.json` / `vercel.deploy.json` and push to GitHub without actually triggering a Railway or Vercel deploy. Useful for reviewing AI-generated configs before deploying.

```bash
# Generate configs + push to GitHub
python deploy/pipeline_prepare.py --repo ~/Documents/work/my_startup

# Generate configs only, skip git push
python deploy/pipeline_prepare.py --repo ~/Documents/work/my_startup --configs-only
```

---

## Scripts Reference

| Script | Purpose |
|--------|---------|
| `zip_to_repo.py` | Extract harness ZIP → `~/Documents/work/<name>/` → git init → GitHub push |
| `pipeline_deploy.py` | Full orchestrator: AI config gen → GitHub push → Railway → Vercel → Auth0 |
| `pipeline_prepare.py` | Prep only: AI config gen + GitHub push, no Railway/Vercel deploy |
| `railway_deploy.py` | Railway backend deploy (called by pipeline_deploy.py) |
| `vercel_deploy.py` | Vercel frontend deploy (called by pipeline_deploy.py) |
| `auth0_setup.py` | Auth0 SPA application setup and URL configuration |
| `auth0_update_urls.py` | Update Auth0 callback/logout URLs after deploy URLs are known |
| `repo_setup.py` | Grant Railway + Vercel GitHub App access to a repo (first deploy only) |
| `check_business_imports.py` | Static check: business/frontend/pages relative imports resolve correctly after copy to frontend/src |
| `write_deploy_state.py` | Write railway.deploy.json / vercel.deploy.json state files |

---

## Repo Structure Expected by Deployer

After `zip_to_repo.py` runs, the repo at `~/Documents/work/<startup_name>/` should look like:

```
my_startup/
├── saas-boilerplate/
│   ├── backend/          ← Railway deploys this (FastAPI)
│   │   ├── main.py
│   │   ├── requirements.txt
│   │   └── business/
│   └── frontend/         ← Vercel deploys this (Next.js)
│       ├── package.json
│       └── business/
├── .env                  ← backend env vars (Railway injects these)
├── railway.deploy.json   ← written by pipeline_deploy (project/service IDs)
├── vercel.deploy.json    ← written by pipeline_deploy (project ID)
└── requirements.txt      ← Railway detects Python from this
```

---

## Cost Tracking

AI calls made during config generation are logged to `deploy/deploy_ai_costs.csv`.

Run from the project root to merge into the aggregated cost log:

```bash
python aggregate_ai_costs.py
```

---

## Troubleshooting

**Railway deploy fails on first run**

Check that `repo_setup.py` has been run — Railway needs GitHub App access before it can pull the repo.

**Railway deploy succeeds but no URL is printed**

The deploy worker now treats this as a partial success, not a failure. It will:
- reuse an existing service domain if present
- otherwise generate a Railway-managed domain automatically

If `url_pending` is still returned, check the Railway dashboard and rerun once the service domain exists.

**Auth0 URLs not updating**

`auth0_update_urls.py` runs automatically at the end of `pipeline_deploy.py`. If it fails, run it manually after deploy URLs are known:

```bash
python deploy/auth0_update_urls.py
```

**Frontend import errors after deploy**

Run the static import checker before deploying:

```bash
python deploy/check_business_imports.py --repo ~/Documents/work/my_startup
```

This catches relative imports in `business/frontend/pages/*.jsx` that break when files are copied into `frontend/src/business/pages/` during the Vercel build.

**Vercel CRA build fails on ESLint / CI**

`vercel_deploy.py` now forces:
- `CI=false`
- `DISABLE_ESLINT_PLUGIN=true` for `create-react-app`

So CRA lint warnings should no longer fail the Vercel build.

**Reference:** `deploy/lessons-from-first-deploy.md` — 17 documented deploy failures and their fixes.
