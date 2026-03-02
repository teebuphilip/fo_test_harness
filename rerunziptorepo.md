# Re-Run zip-to-repo (Clean Repo Flow)

Use this when you have a new harness ZIP and want a clean `~/Documents/work/ai-workforce-intelligence` repo before deploy.

## 1) Go to FO_TEST_HARNESS

```bash
cd ~/Downloads/FO_TEST_HARNESS
```

## 2) Find the latest AI Workforce ZIP

```bash
LATEST_ZIP=$(ls -t ~/Downloads/FO_TEST_HARNESS/fo_harness_runs/ai_workforce_intelligence_BLOCK_B_*.zip | head -n 1)
echo "$LATEST_ZIP"
```

## 3) Archive old repo (recommended)

```bash
if [ -d ~/Documents/work/ai-workforce-intelligence ]; then
  mv ~/Documents/work/ai-workforce-intelligence \
     ~/Documents/work/ai-workforce-intelligence_backup_$(date +%Y%m%d_%H%M%S)
fi
```

## 4) Run zip-to-repo

```bash
python deploy/zip_to_repo.py "$LATEST_ZIP"
```

What this script does:
- Creates/extracts into `~/Documents/work/<repo-name>`
- Copies boilerplate + overlays final business artifacts
- Commits git changes
- Creates GitHub repo if needed
- Pushes `main`

## 5) Verify output

```bash
cd ~/Documents/work/ai-workforce-intelligence
git remote -v
git log --oneline -n 3
```

## Optional: hard delete instead of archive

Use only if you are sure you do not need the old repo copy.

```bash
rm -rf ~/Documents/work/ai-workforce-intelligence
```
