# Gap Analysis Pipeline — Detailed Guide

This document explains the full pipeline in `gap-analysis/` from pre‑intake idea → Pass0 → pricing → naming → AI hero answers → SEO → marketing copy → GTM plan.

## What This Pipeline Does
The pipeline is designed to take a raw idea (pre‑intake), decide if it’s worth building, then generate:
- a build‑ready business brief,
- a pricing model,
- a candidate name + domain check,
- AI‑generated hero answers + hero JSON,
- structured SEO config,
- marketing copy seed JSON,
- a structured GTM plan.

The flow is deterministic where it must be (SEO), and AI‑assisted where it adds value (Pass0 + marketing copy).

## Inputs and Outputs

### Input 1: Pre‑intake idea JSON
Example:
```
/Users/teebuphilip/Documents/work/AFH/data/runs/2026-03-06/verdicts/hold/idea_0050.json__0001.json
```
Key field used:
- `idea_text`

### Output Directory
All generated artifacts live under:
```
/Users/teebuphilip/Downloads/FO_TEST_HARNESS/gap-analysis/outputs/
```

## Pipeline Steps (What Runs)

### Step 1 — Pass0 Gap Check
Command (via full pipeline):
```
./run_pass0.sh <preintake_idea.json>
```
Outputs:
- `*_pass0.json` — decision, scores, warnings
- `*_brief.json` — locked builder brief
- `*_one_liner.txt`
- `*_business_brief.json` — normalized brief for SEO + marketing

Key rules enforced:
- Persona must be specific + numeric
- Wedge must follow strict template and include consequence
- Must have 3 manual‑first features (auto‑filled if AI fails)
- Distribution must include ≥2 free channels (Reddit, IH, etc.)

If decision is not `BUILD_APPROVED`, the pipeline halts unless `--force` is used.

### Step 2 — Pricing Modeler (AI)
Command:
```
./run_pricing_modeler.sh <business_brief.json> <one_liner.txt>
```
Outputs:
- Updates `*_business_brief.json` with `pricing_model`

### Step 3 — Name Picker (Porkbun)
Command (via full pipeline):
```
./run_name_picker.sh <intake_stub.json> <business_brief.json>
```
Outputs:
- `*_name_report.json` — domain availability
- `*_name_suggestions.json` — picked name, top 5
- `*_named.json` — renamed intake stub

Selection rule:
- pick cheapest available domain among top‑5 scored names
- if none available, pick best scored name anyway

### Step 4 — AI Hero Answers (Q1–Q11)
Command:
```
./run_ai_hero_answers.sh <business_brief.json> <one_liner.txt> <name_suggestions.json>
```
Outputs:
- `intake/ai_text/<picked_slug>_hero_answers.txt`
- `intake/ai_text/<picked_slug>.json`

### Step 5 — SEO Generator (Deterministic)
Command:
```
./run_seo_generator.sh
```
Inputs:
- uses latest `*_business_brief.json`

Outputs:
- `seo/<brief_basename>_seo.json`

SEO rules:
- deterministic only (no AI)
- keywords 2–4 words max
- excludes “saas”, “platform”, etc.

### Step 6 — Marketing Copy Generator (AI)
Command:
```
./run_marketing_copy.sh <business_brief.json> <seo.json>
```
Outputs:
- `*_marketing_copy.json`

Schema:
- `taglines`
- `hero_headlines`
- `hero_subheads`
- `value_props`
- `feature_bullets`
- `cta_variants`

### Step 7 — GTM Plan Generator (AI + Template)
Command:
```
./run_gtm_plan.sh <business_brief.json> <one_liner.txt>
```
Outputs:
- `*_gtm.json`

Schema:
- `who`
- `offer`
- `problem`
- `channels_free`
- `try_it`
- `pay`
- `cheap_execution_checklist`
- `automation_simplification_ideas`

## Full Unattended Run

```
./run_full_pipeline.sh <preintake_idea.json>
```

Flags:
- `--verbose` — prints internal details
- `--no-ai` — disables research (Pass0 likely HOLD)
- `--force` — continue even if Pass0 not approved

## Cost Tracking
AI calls log to:
- `gap-analysis/pass0_ai_costs.csv`
- `gap-analysis/pricing_model_ai_costs.csv`
- `gap-analysis/marketing_copy_ai_costs.csv`
- `gap-analysis/gtm_plan_ai_costs.csv`
- `agent-make/name_generator_ai_costs.csv`
- `intake/name_generator_ai_costs.csv`
 - `intake/hero_answers_ai_costs.csv`

## Why This Split Exists
- Pass0 ensures you don’t waste time on weak ideas.
- Naming and SEO are only worth doing after BUILD_APPROVED.
- SEO is deterministic to keep consistency.
- Marketing copy is AI‑assisted for speed.
- GTM plan is template‑driven with AI fill for specificity.
- Pricing model is AI‑assisted with a fallback for reliability.

## Quick Troubleshooting
- If Pass0 returns HOLD: refine wedge or allowlist.
- If name picker fails: increase TLDs or price cap.
- If SEO keywords look odd: check business brief input.
