**Definitive Guide: Idea → Deploy**

This is the single source of truth for the full pipeline from idea to deploy.

**A) Raw Idea → Pre-Intake (Pass0)**
1. Run the gap analysis pipeline on a raw idea JSON:
```bash
./gap-analysis/run_full_pipeline.sh /path/to/preintake.json --verbose
```
Example (AFH raw idea):
```bash
./gap-analysis/run_full_pipeline.sh \
  /Users/teebuphilip/Documents/work/AFH/data/runs/2026-03-06/verdicts/hold/idea_0050.json__0001.json \
  --verbose
```
2. Output you care about:
```text
gap-analysis/outputs/*_business_brief.json
gap-analysis/outputs/*_one_liner.txt
intake/ai_text/<picked_name>.json  (hero JSON)
```

**B) Hero JSON → Intake**
1. If you already have a hero JSON:
```bash
cd intake
./generate_intake.sh ai_text/<picked_name>.json
```
2. Output:
```text
intake/intake_runs/<picked_name>/<picked_name>.json
```

**C) Intake QA + Fit**
1. Boilerplate fit check:
```bash
python check_boilerplate_fit.py --intake intake/intake_runs/<picked_name>/<picked_name>.json
```
2. Optional grill-me pass:
```bash
cd intake
./grill_me.sh intake_runs/<picked_name>/<picked_name>.json
```

**D) Build + QA**
1. Full greenfield pipeline:
```bash
./run_integration_and_feature_build.sh \
  --intake intake/intake_runs/<picked_name>/<picked_name>.json \
  --startup-id <picked_name>
```
2. Output ZIP:
```text
fo_harness_runs/<picked_name>_BLOCK_B_full_<timestamp>.zip
```

**E) Deploy**
1. Convert ZIP to repo:
```bash
python deploy/zip_to_repo.py fo_harness_runs/<picked_name>_BLOCK_B_full_<timestamp>.zip
```
2. Deploy:
```bash
python deploy/pipeline_deploy.py --repo ~/Documents/work/<picked_name>
```

**Alternate Entry: Hero JSON → Pre-Intake Outputs**
Use this when you already have Q1–Q11:
```bash
./gap-analysis/run_full_pipeline_from_hero.sh intake/ai_text/<picked_name>.json --verbose
```

**Notes**
1. `--no-ai` disables AI stages (use for deterministic runs).
2. `--force` continues even if Pass0 is HOLD.
3. Outputs are tracked in `gap-analysis/outputs/` and `seo/`.
