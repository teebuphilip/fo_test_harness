# Deploy Clean ZIP (First Time)

This is the minimal, deterministic sequence for first-time deploys from a clean ZIP.

## 1) Create Railway project + service (UI)
- Create the Railway project and backend service.
- Copy **project_id** and **service_id**.

## 2) Write `railway.deploy.json`
Use the helper:
```bash
python deploy/write_deploy_state.py \
  --repo /Users/teebuphilip/Documents/work/ai-workforce-intelligence-downloadable-executive-report \
  --target railway \
  --project ai-workforce-intelligence-downloadable-executive-report \
  --project-id YOUR_PROJECT_ID \
  --service-id YOUR_SERVICE_ID \
  --postgres-added true
```

## 3) Run deploy pipeline (no Git push if unchanged)
```bash
python /Users/teebuphilip/Downloads/FO_TEST_HARNESS/deploy/pipeline_deploy.py \
  --repo /Users/teebuphilip/Documents/work/ai-workforce-intelligence-downloadable-executive-report \
  --skip-git-push
```

## 4) Get Railway domain (CLI)
Railway does not reliably expose a domain via API unless it already exists.
```bash
railway login
railway link
railway domain
```
Copy the domain (e.g. `backend-production-f61e.up.railway.app`).

## 5) Save Railway domain to deploy state
```bash
python deploy/write_deploy_state.py \
  --repo /Users/teebuphilip/Documents/work/ai-workforce-intelligence-downloadable-executive-report \
  --target railway \
  --service-domain backend-production-f61e.up.railway.app
```

## 6) Set Vercel backend URL
Set `REACT_APP_API_URL` in Vercel project env vars:
```
REACT_APP_API_URL=https://backend-production-f61e.up.railway.app
```
Redeploy the frontend.

## 7) Verify health
```bash
curl -i https://backend-production-f61e.up.railway.app/health
```
