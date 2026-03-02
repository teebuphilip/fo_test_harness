# CLAUDE.md — FO_TEST_HARNESS

## Project Overview

End-to-end pipeline for testing the FounderOps BUILD → QA → DEPLOY workflow. Takes a structured intake JSON + governance ZIP and produces a fully-built, QA-validated ZIP of application artifacts.

- **Builder**: Claude (Anthropic) generates full-stack code + docs
- **Validator**: ChatGPT (OpenAI) checks against intake spec
- **Loop**: Defects feed back into Claude until clean or max iterations (default 5)

---

## Three-Stage Pipeline

| Stage | Entry Point | Purpose |
|-------|------------|---------|
| 1. Intake | `intake/generate_intake.sh` | Founder answers → structured intake JSON |
| 2. Build-QA | `fo_test_harness.py` | BUILD + iterative QA loop → output ZIP |
| 3. Deploy | `deploy/zip_to_repo.py` → `deploy/pipeline_deploy.py` | ZIP → GitHub → Railway/Vercel |

---

## Key Files

| File | Purpose |
|------|---------|
| `fo_test_harness.py` | Main orchestrator (~3800 lines); all BUILD-QA logic |
| `check_boilerplate_fit.py` | Checks if intake suits boilerplate (YES/NO + file list) |
| `aggregate_ai_costs.py` | Merges cost CSVs |
| `summarize_harness_runs.py` | Generates run summaries |
| `deploy/pipeline_deploy.py` | Full deploy orchestrator (Railway + Vercel) |
| `deploy/pipeline_prepare.py` | Config-only mode (AI config gen + Git push, no deploy) |
| `deploy/zip_to_repo.py` | ZIP extraction → git init → GitHub push |
| `deploy/railway_deploy.py` | Railway backend deployment |
| `deploy/vercel_deploy.py` | Vercel frontend deployment |
| `munger/munger.py` | Spec quality scorer |
| `munger/munger_ai_fixer.py` | AI-based spec fixing loop |

---

## fo_test_harness.py — Class Structure

| Class | Line | Role |
|-------|------|------|
| `Config` | ~36 | Static config: models, token limits, timeouts |
| `ClaudeClient` | ~452 | Anthropic API wrapper with retry + backoff |
| `ChatGPTClient` | ~564 | OpenAI API wrapper |
| `ArtifactManager` | ~633 | Extracts `**FILE: path**` artifacts from Claude output |
| `DirectiveTemplateLoader` | ~425 | Loads prompt markdown files from `directives/prompts/` |
| `PromptTemplates` | ~1130 | Prompt construction (600+ lines) |
| `FOHarness` | ~1770 | Main orchestrator; `execute_build_qa_loop()` entry |

**Key FOHarness methods:**
- `execute_build_qa_loop()` — main iteration loop
- `run_claude_build()` — calls Claude for BUILD
- `run_chatgpt_qa()` — calls ChatGPT for QA
- `_enrich_defects_with_fix_context()` — adds architectural guidance to defects
- `_apply_patch_recovery()` — recovers missing files
- `_validate_pre_qa()` — pre-QA checks

---

## Running the Harness

### Prerequisites
```bash
export ANTHROPIC_API_KEY=sk-ant-xxxxx
export OPENAI_API_KEY=sk-xxxxx
# Governance ZIP must be unzipped
unzip fobuilgov100.zip -d /tmp/fobuilgov100/
```

### Step 1: Generate Intake
```bash
cd intake
./generate_intake.sh hero_text/twofaced_ai.json
# Output: intake/intake_runs/twofaced_ai/twofaced_ai.json
```

### Step 2: Run Build-QA Loop
```bash
python fo_test_harness.py \
  --intake intake/intake_runs/twofaced_ai/twofaced_ai.json \
  --startup-id twofaced_ai \
  --block B \
  --build-gov /tmp/fobuilgov100 \
  --tech-stack lowcode
```

**Key CLI flags:**
- `--block A|B` — Tier 1 or Tier 2 intake block
- `--tech-stack lowcode` — Skip boilerplate; use Zapier/Shopify stack
- `--deploy` — Run deploy pipeline after build
- `--max-iterations N` — Override default 5-iteration cap
- `--max-parts N` — Multipart output limit (default 10)
- `--max-continuations N` — Continuation limit (default 9)

### Step 3: Deploy
```bash
# Extract ZIP → git repo → GitHub
python deploy/zip_to_repo.py fo_harness_runs/twofaced_ai_BLOCK_B_*.zip

# Full deploy (Railway + Vercel)
python deploy/pipeline_deploy.py --repo ~/Documents/work/twofaced_ai

# Configs only (no deploy)
python deploy/pipeline_prepare.py --repo ~/Documents/work/twofaced_ai
python deploy/pipeline_prepare.py --repo . --configs-only  # skip git push too
```

---

## Output Structure

```
fo_harness_runs/<startup>_BLOCK_<X>_<timestamp>/
├── build/
│   ├── iteration_01_build.txt        # Raw Claude output
│   ├── iteration_01_artifacts/       # Extracted files
│   └── iteration_02_fix.txt          # Defect-fix iteration
├── qa/
│   └── iteration_01_qa_report.txt    # ChatGPT QA report
├── logs/
│   ├── iteration_01_build_prompt.log
│   ├── iteration_01_qa_prompt.log
│   └── claude_questions.txt
├── artifact_manifest.json            # File checksums
└── build_state.json                  # Run metadata
```

---

## Critical Patterns

### Artifact Extraction
- Pattern: `**FILE: path/to/file.ext**` header + code fence
- Handled by `ArtifactManager.extract_artifacts()`
- Boilerplate files: `business/frontend/pages/*.jsx`, `business/backend/routes/*.py`

### Multipart Output
- Claude may split large builds: `<!-- PART 1/3 -->...<!-- END PART 1/3 -->`
- Harness concatenates parts; falls back to continuation prompts on truncation
- Detection: `detect_truncation()`, `detect_multipart()`

### Defect Injection
- QA report → `PREVIOUS_DEFECTS` block in next BUILD prompt
- QA defects must include `Fix:` field (exact code change, not just description)
- Enrichment: `_enrich_defects_with_fix_context()` prepends architectural guidance for boilerplate patterns

### Boilerplate Decision
- Default: `/Users/teebuphilip/Documents/work/teebu-saas-platform`
- Skipped when `--tech-stack lowcode` (Zapier/Shopify intake)
- Hard-prohibited: dict storage, sequential IDs, hardcoded data

### Token / Timeout Strategy
- Max tokens: 16384 (full regeneration each iteration)
- Timeout: 600s first call (caching overhead), 300s subsequent

---

## Config Override Files

| File | Controls |
|------|---------|
| `fo_tech_stack_override.json` | Tech stack defaults (Next.js, Prisma, etc.) |
| `fo_external_integration_override.json` | Rules for Stripe, auth, etc. |
| `fo_qa_override.json` | QA behavior adjustments |

---

## Prompt Templates

Modular prompts live in `directives/prompts/` (17 markdown files):
- `build_*.md` — Build iteration prompts
- `qa_prompt.md` — QA validation prompt
- `build_patch_first_file_lock.md` — Defect fix iteration (locks first file)

Loaded by `DirectiveTemplateLoader`; hardcoded fallbacks in `PromptTemplates`.

---

## Cost Tracking

| File | Contains |
|------|---------|
| `fo_run_log.csv` | Claude + ChatGPT costs per build run |
| `deploy/deploy_ai_costs.csv` | Deploy pipeline AI costs |
| `munger/munger_ai_costs.csv` | Munger AI costs |
| `ai_costs_aggregated.csv` | Merged all costs |

Run `python aggregate_ai_costs.py` to refresh aggregates.

---

## Dependencies

No `requirements.txt`. Install manually:
```bash
pip install anthropic openai requests
```

Required env vars: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`
For deploy: `GITHUB_TOKEN`, `GITHUB_USERNAME`, `RAILWAY_TOKEN`, `VERCEL_TOKEN`

---

## Important Docs

| File | Read for |
|------|---------|
| `README.md` | Quick start + troubleshooting |
| `AGENTS.md` | Agent operating instructions |
| `changelog.md` | Recent changes (QA convergence, multipart, deploy) |
| `learnings-from-af-to-fo.md` | Reliability lessons |
| `intake/README.md` | Intake generation details |
| `FO_ARTIFACT_FORMAT_RULES.txt` | File formatting standards Claude must follow |
| `FO_BOILERPLATE_INTEGRATION_RULES.txt` | Boilerplate constraints |
