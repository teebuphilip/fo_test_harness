# Agent Guide (Unified)

This document is a unified operating guide for both Codex and Claude. It synthesizes `AGENTS.md`, `README.md`, `why-we-are-here.md`, `FO_TEST_HARNESS_README.md`, and recent `changelog.md` highlights.

## Purpose
- This repo is the FounderOps BUILD → QA → DEPLOY harness plus intake tooling.
- It converts founder answers into structured intake JSON.
- It runs a Claude build + ChatGPT QA loop to produce artifacts.
- It packages results into a ZIP under `fo_harness_runs/`.
- It supports full BUILD → QA → DEPLOY with auto-resume behavior.

## Why This Exists (Context)
This harness started as a validation tool for `~/Documents/work/FounderOps`, specifically the rules and specs in `docs/architecture/INTAKE` and `docs/architecture/BUILD`. It is now the primary near‑term revenue engine while AI accelerates.

AutoFounderHub (`~/Documents/work/AFH`) produces small, practical SaaS ideas for small businesses. Ideas are scored; the best are built here. Builds from personal networks also route through this harness. AFH will sell ideas, scores, full codebases, and turnkey deploys at planned tiers ($2.99, $5.99, $2,500, $10,000), with feature work priced separately.

Target launch is May 15 (post‑tax filing window). Before then: **60 builds** deployed to personal Vercel/Railway. The `agent-make/` directory lists the 60 planned builds. Active higher‑complexity builds: **wynwood**, **awi**, **aav**. Basketball projects in `~/Documents/work/courtdominion` will also be run through this engine.

Primary near‑term goals:
- stronger intake requirements,
- fewer hallucinations,
- higher‑quality QA.

## Core Pipeline (Three Stages)
| Stage | Script | Purpose |
|-------|--------|---------|
| 1. Intake | `intake/generate_intake.sh` | Founder answers → structured intake JSON |
| 2. Build-QA | `run_integration_and_feature_build.sh` | Phase-by-phase BUILD + QA + integration check |
| 3. Deploy | `deploy/zip_to_repo.py` → `deploy/pipeline_deploy.py` | ZIP → GitHub → Railway / Vercel |

## Pre-Intake Gap Analysis (Pass0)
Use the gap-analysis pipeline to turn a raw idea into a build-ready brief + hero JSON.

```
./gap-analysis/run_full_pipeline.sh /path/to/preintake.json --verbose
```

Outputs:
- `gap-analysis/outputs/*_business_brief.json`
- `intake/ai_text/<picked_name>.json` (hero JSON for `generate_intake.sh`)

## Primary Workflows
Greenfield full pipeline (recommended):
```
./run_integration_and_feature_build.sh \
  --intake intake/intake_runs/<startup>/<startup>.json \
  --startup-id <startup>
```

Add a feature to an existing build:
```
./add_feature.sh \
  --intake <intake.json> \
  --feature "<feature name>" \
  --existing-zip <zip>
```

Pre-intake gap analysis:
```
./gap-analysis/run_full_pipeline.sh /path/to/preintake.json --verbose
```

Direct harness run (manual control or resume):
```
python fo_test_harness.py \
  intake/intake_runs/<startup>/<startup>.json \
  FOBUILFINALLOCKED100.zip \
  --max-iterations 20
```

Integration check (deterministic, post-build):
```
python integration_check.py \
  --zip fo_harness_runs/<startup>_BLOCK_B_<ts>.zip \
  --intake intake/intake_runs/<startup>/<startup>.json
```

## QA Gates (Summary)
Five sequential gates inside `fo_test_harness.py`, then a post-build integration gate:
1. COMPILE (deterministic AST parse)
2. STATIC (deterministic structural checks)
3. CONSISTENCY (AI, pre‑filter only)
4. QUALITY (AI)
5. FEATURE_QA (AI)
6. INTEGRATION (deterministic `integration_check.py`, post‑build)

**Rule:** CONSISTENCY is a pre‑filter, not the authority. After 4 consecutive CONSISTENCY failures, fall through to QA; do not trigger a full rebuild based solely on CONSISTENCY.

## Factory Mode
High‑volume AFH catalog builds use `--mode factory` on `run_integration_and_feature_build.sh`:
- caps iterations and fix passes,
- skips CONSISTENCY gate,
- allows QUALITY gate to pass unless deployability fails.

## Safety & Repo Hygiene (Non‑Negotiable)
- Never commit or expose API keys. Keys only in environment variables.
- Treat `.claude/settings.local.json` as sensitive; never copy keys from it.
- Avoid modifying `fo_harness_runs/` and `boilerplate_checks/` unless explicitly asked.
- Preserve build artifacts and QA logs when changing the harness.
- Do not write or modify code unless the user explicitly says “YES”.
- Always commit `fo_run_log.csv` when it changes.
- Outside of actual builds, default to ChatGPT instead of Claude to control costs.
- Safety prompt required before modifying `fo_run_log.csv` or `fo_test_harness.py`.

## Output Structure (Run Directory)
```
fo_harness_runs/<startup>_BLOCK_B_<timestamp>/
├── build/
├── qa/
├── logs/
├── integration_issues.json
├── artifact_manifest.json
└── build_state.json
```

## Cost Tracking
- `fo_run_log.csv` (Claude + ChatGPT costs per build run)
- `deploy/deploy_ai_costs.csv`
- `munger/munger_ai_costs.csv`
- `ai_costs_aggregated.csv` (run `python aggregate_ai_costs.py`)

## Config Overrides
- `fo_tech_stack_override.json`
- `fo_external_integration_override.json`
- `fo_qa_override.json`

## Deploy Prereqs (Env Vars)
- `GITHUB_TOKEN`, `GITHUB_USERNAME`
- `RAILWAY_TOKEN`, `VERCEL_TOKEN`

## Key Docs
- `CLAUDE.md` (full Claude Code instructions)
- `README.md` (main repo guide)
- `FO_TEST_HARNESS_README.md` (legacy v2 guide and flags)
- `why-we-are-here.md` (origin + business context)
- `changelog.md` (every change made)
- `FO_ARTIFACT_FORMAT_RULES.txt` (artifact formatting)
- `FO_BOILERPLATE_INTEGRATION_RULES.txt` (boilerplate constraints)
- `intake/README.md` (intake generation)
- `learnings-from-af-to-fo.md` (recurring patterns)
- `must-port-to-fo.md` (not yet in FO production)

## Recent Changelog Highlights (Condensed)
2026‑03‑18:
- `integration_check.py` false positives fixed for snake_case route/model stems.
- `check_final_zip.py` added: runs static + integration checks on final merged ZIP.
- `run_integration_and_feature_build.sh` cleanup flags (`--clean`, `--fullclean`).
- ZIP selection and run‑dir scoping bugs fixed.
- Factory mode added (see above).

2026‑03‑17:
- AI decomposer + mini‑spec entity builds in `phase_planner.py`.
- CONSISTENCY failures no longer trigger full rebuilds; fall through to QA after cap.
- Consistency cross‑file fix targeting improved (both sides patched).
- Schema naming convention locked; `__pycache__`/`.pyc` filtered from defects.
- QA prompt hardened: cross‑file contracts, evidence rules, hallucination bans.

2026‑03‑06 (FO Test Harness v2 hardening):
- Gate ordering clarified; static KPI and export checks made schema‑agnostic.
- Per‑iteration defect scope capped and prioritized.

## Source‑of‑Truth Notes
If defaults or flags conflict between docs, defer to `README.md` and the code in `fo_test_harness.py`. `FO_TEST_HARNESS_README.md` is a legacy guide and may describe older defaults.
