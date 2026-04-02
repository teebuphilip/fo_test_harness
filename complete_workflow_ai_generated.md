**Definitive Guide: Idea → Deploy (AI-Generated Ideas)**

This is the single source of truth for the full pipeline from idea to deploy.

**Step 0 — Source of AI Ideas**
Ideas come from AFH:
- Repo: `https://www.github.com/teebuphilip/AFH`
- Local: `~/Documents/work/AFH` (see its README)

These are AI-generated ideas that still need enrichment and a market gap check.

**Step 0 — API Health Check (Required)**
```bash
python check_openai.py
```
Example output:
```text
(cd39) Teebus-MacBook-Pro:FO_TEST_HARNESS teebuphilip$ python check_openai.py
✓ Claude  — UP  (reply: 'UP')
✓ OpenAI  — UP  (reply: 'DOWN')
   Requests: 499/500 remaining
   Tokens  : 29992/30000 remaining  (resets in 16ms)
(cd39) Teebus-MacBook-Pro:FO_TEST_HARNESS teebuphilip$ echo $?
0
```

**Step 1 — Raw Idea → Pre-Intake (Pass0)**
Run the gap analysis pipeline on a raw AFH idea JSON:
```bash
./gap-analysis/run_full_pipeline.sh \
  /Users/teebuphilip/Documents/work/AFH/data/runs/2026-03-06/verdicts/hold/idea_0050.json__0001.json \
  --verbose
```

**Gap-analysis execution chain (run_full_pipeline.sh)**
- `run_full_pipeline.sh`
  - `run_pass0.sh` → `pass0_gap_check.py` (writes pass0 + brief + one‑liner)
  - `run_pricing_modeler.sh` → `pricing_modeler.py` (updates business brief)
  - `run_name_picker.sh` → `auto_name_picker.py` (writes named + suggestions)
  - `run_ai_hero_answers.sh` → `generate_ai_hero_answers.py` → `intake/convert_hero_answers.py`
  - `run_seo_generator.sh` → `seo_generator.py` (writes `seo/*_seo.json`)
  - `run_marketing_copy.sh` → `base_marketing_copy.py`
  - `run_gtm_plan.sh` → `base_gtm_plan.py`

Sample (key outputs from the above run):
```text
gap-analysis/outputs/*_business_brief.json
gap-analysis/outputs/*_one_liner.txt
intake/ai_text/<picked_name>.json  (hero JSON)
seo/<picked_name>_business_brief_seo.json
gap-analysis/outputs/*_business_brief_marketing_copy.json
gap-analysis/outputs/*_business_brief_gtm.json
```

**Step 2 — Munger (Hero Answers QA)**
Run the full munger loop (deterministic + AI fixer) on the hero JSON before intake:
```bash
./munger/run_munger_full.sh intake/ai_text/<picked_name>.json
```
Outputs:
```text
munger/<picked_name>.munged.json
munger/<picked_name>_munger_out.json
munger/<picked_name>_munger_ai_fixed.json
```
Example output (from `invoicetool`, with low-issue cleanup):
```text
(cd39) Teebus-MacBook-Pro:munger teebuphilip$ ./run_munger_full.sh ../intake/ai_text/invoicetool.json --resume
[MungerFull] Input: ../intake/ai_text/invoicetool.json
[MungerFull] Munged output: /Users/teebuphilip/Downloads/FO_TEST_HARNESS/munger/invoicetool.munged.json
[MungerFull] Fixer output: /Users/teebuphilip/Downloads/FO_TEST_HARNESS/munger/invoicetool_munger_ai_fixed.json
[MungerFull] Report output: /Users/teebuphilip/Downloads/FO_TEST_HARNESS/munger/invoicetool_munger_out.json
[MungerFull] Python: /Users/teebuphilip/venvs/cd39/bin/python
[MungerFull] Max loops: 5
[MungerFull] Resume: enabled
[MungerFull] Resume enabled and munged output exists — starting from munged file
[MungerFull] Loop 1/5
[Munger] Input: /Users/teebuphilip/Downloads/FO_TEST_HARNESS/munger/invoicetool.munged.json
[Munger] Output: /Users/teebuphilip/Downloads/FO_TEST_HARNESS/munger/invoicetool_munger_out.json
[Munger] Loop: 1
Wrote: /Users/teebuphilip/Downloads/FO_TEST_HARNESS/munger/invoicetool_munger_out.json
[Munger] Status: PASS
[Munger] Score: 99
[Munger] Issues: 1 (critical: 0)
[Munger] Issues detail:
  - ISSUE_01 [LOW] None missing recommended pattern
[Munger] Applied patches: 0
[Munger] Duration: 0.01s
[Munger] Cost: $0.0000 (deterministic)
[Munger] Cost CSV: /Users/teebuphilip/Downloads/FO_TEST_HARNESS/munger/munger_ai_costs.csv
[MungerFull] Status PASS with 1 LOW issues — attempting low-issue cleanup
[MungerFixer] Calling AI for template CT036_pdf_library_choice (provider=chatgpt)
[MungerFixer] Tokens: in=771 out=60
[MungerFixer] Cost: $0.0025
[MungerFixer] AI response for CT036_pdf_library_choice: {"pdf_library_choice": "WeasyPrint"}
[MungerFixer] Status: SUCCESS
[MungerFull] Loop 2/5
[Munger] Status: PASS
[Munger] Score: 100
[Munger] Issues: 0 (critical: 0)
[MungerFull] Status PASS — writing munged file from clean_hero_answers
Wrote: /Users/teebuphilip/Downloads/FO_TEST_HARNESS/munger/invoicetool.munged.json
=======================
=======================
```

**Step 3 — Hero JSON → Intake**
1. Use the munged hero JSON:
```bash
cd intake
./generate_intake.sh ../munger/<picked_name>.munged.json
```
2. Output:
```text
intake/intake_runs/<picked_name>/<picked_name>.json
```
3. Example output (from `invoicetool`):
```text
🚀 Generating intake for hero file: /Users/teebuphilip/Downloads/FO_TEST_HARNESS/munger/invoicetool.munged.json
============================================================
🚀 FOUNDEROPS INTAKE RUNNER v7
Mode: hero
Hero file: /Users/teebuphilip/Downloads/FO_TEST_HARNESS/munger/invoicetool.munged.json
Output dir: /Users/teebuphilip/Downloads/FO_TEST_HARNESS/intake/intake_runs
Pass directive: /Users/teebuphilip/Downloads/FO_TEST_HARNESS/intake/inputs/chatgpt_block_directive.txt
============================================================

============================================================
🦸 HERO MODE
ID:        invoicetool
Name:      Invoicetool
Run ID:    invoicetool
Directory: /Users/teebuphilip/Downloads/FO_TEST_HARNESS/intake/intake_runs/invoicetool
============================================================

⚙️  Running Block A (Tier 1)...
  ▶ Attempt 1/5 for block A
🔎 OPENAI_API_KEY: prefix=sk-proj len=164
💰 ChatGPT cost estimate: $0.0156 (in: 3157, out: 767)
🔍 Token usage: 767 / 4096
  ✅ Valid block A
⚙️  Running Block B (Tier 2)...
  ▶ Attempt 1/5 for block B
🔎 OPENAI_API_KEY: prefix=sk-proj len=164
💰 ChatGPT cost estimate: $0.0169 (in: 3158, out: 902)
🔍 Token usage: 902 / 4096
  ✅ Valid block B
📄 Created: invoicetool.txt
📦 Created: invoicetool.json

============================================
✅ HERO RUN COMPLETE
Output: /Users/teebuphilip/Downloads/FO_TEST_HARNESS/intake/intake_runs/invoicetool/
  block_a.json           → Tier 1 passes
  block_b.json           → Tier 2 passes
  invoicetool.txt      → Summary
  invoicetool.json     → Combined blocks
Total Costs: $0.04
============================================
```

**Step 4 — Intake QA + Fit**
1. Boilerplate fit check (original intake):
```bash
python check_boilerplate_fit.py intake/intake_runs/<picked_name>/<picked_name>.json
```
2. Grill-me pass (auto-resume, block B only, auto-answer):
```bash
cd intake
./grill_me.sh intake_runs/<picked_name>/<picked_name>.json
```
3. Boilerplate fit check (grilled intake):
```bash
python check_boilerplate_fit.py intake/intake_runs/<picked_name>/<picked_name>.grilled.json
```
4. Block B quality check (deterministic, no AI):
```bash
python check_block_b.py intake/intake_runs/<picked_name>/<picked_name>.grilled.json
```
5. Auto-route build pipeline (slice vs phase):
```bash
./run_auto_build.sh --intake intake/intake_runs/<picked_name>/<picked_name>.grilled.json
```
This uses `planner_router.py` to choose between:
- `run_slicer_and_feature_build.sh` (slice pipeline)
- `run_integration_and_feature_build.sh` (phase pipeline)

**What `run_auto_build.sh` does**
- Reads `planner_router.py` recommendation and routes accordingly.
- `slice` route runs `run_slicer_and_feature_build.sh` (vertical slices).
- `phase` route runs `run_integration_and_feature_build.sh` (phase + feature loop).
- You can override routing with `--force slice|phase`.
- Exit codes: `0` = success; non‑zero = build failed or aborted (no deliverable produced).

**What `planner_router.py` looks for**
- Feature count, integration signals, analytics/reporting signals, multi-role signals, and subjective-polish signals.
- Score ≥ 2 → `slice`, otherwise → `phase`.

**Phase vs Slice execution chains**
- **Phase chain:** `run_auto_build.sh` → `planner_router.py` → `run_integration_and_feature_build.sh` → `ubiquity.py` → `phase_planner.py` → `generate_feature_spec.py` → `feature_adder.py --spec-file` → `fo_test_harness.py` → `integration_check.py` → merge ZIPs → `check_final_zip.py` (optional)
- **Slice chain:** `run_auto_build.sh` → `planner_router.py` → `run_slicer_and_feature_build.sh` → `ubiquity.py` → `slice_planner.py` → `generate_feature_spec.py` → `inject_spec.py` → `fo_test_harness.py` → `integration_check.py` → merge ZIPs → `check_final_zip.py` (optional)

**Where `ubiquity.py` runs**
- Called inside `run_slicer_and_feature_build.sh` and `run_integration_and_feature_build.sh`.
- Extracts canonical domain terms from intake and writes a ubiquitous language glossary used by planner → build → QA.

**Key options for both pipelines**
- `--mode quality|factory` (default: quality)
- `--max-iterations N`
- `--clean` (remove final ZIP only)
- `--fullclean` (remove all ZIPs for this startup)
- `--start-from-feature N` (resume partial run)

**Internal helpers used by the pipelines (not called directly)**
- `generate_feature_spec.py` — Generates a scoped feature spec from intake/plan context to guide feature builds.
- `inject_spec.py` — Injects/merges a generated spec into artifacts/build context before build/QA.

6. Outputs:
```text
intake/intake_runs/<picked_name>/<picked_name>.grill_report.json
intake/intake_runs/<picked_name>/<picked_name>.grilled.json
boilerplate_checks/<picked_name>_boilerplate_check.json
```

**Step 5 — Final ZIP Quality Check (Required for deploy)**
```bash
python check_final_zip.py \
  --zip fo_harness_runs/<startup>_BLOCK_B_full_<timestamp>.zip \
  --intake intake/intake_runs/<startup>/<startup>_phase_assessment.json
```
What it does:
- Extracts the final ZIP
- Merges entity `business/**` artifacts
- Runs static + integration checks
- Exits `0` on pass, `1` on failure

Example output:
```text
(cd39) Teebus-MacBook-Pro:FO_TEST_HARNESS teebuphilip$ python check_final_zip.py --zip fo_harness_runs/invoicetool.grilled_BLOCK_B_full_20260401_110213.zip --intake intake/intake_runs/invoicetool/invoicetool.grilled_slice_assessment.json 

══════════════════════════════════════════════════════════════
  CHECK FINAL ZIP
  invoicetool.grilled_BLOCK_B_full_20260401_110213.zip
══════════════════════════════════════════════════════════════

Merging entity artifacts...
  Extracting: invoicetool.grilled_BLOCK_B_full_20260401_110213.zip
  [iteration_04_artifacts] invoicetool_s01_manage_users  →  10 file(s)
  [iteration_04_artifacts] invoicetool_s02_configure_settings  →  10 file(s)
  [iteration_02_artifacts] invoicetool_s03_view_all_invoices  →  10 file(s)
  [iteration_04_artifacts] invoicetool_s04_view_invoices  →  10 file(s)
  [iteration_03_artifacts] invoicetool_s05_make_payments  →  10 file(s)
  [iteration_02_artifacts] invoicetool_s06_submit_invoices  →  10 file(s)
  [iteration_05_artifacts] invoicetool_s07_manual_invoice_entry_form  →  10 file(s)
  [iteration_03_artifacts] invoicetool_s08_email_notifications_for_invoice_status  →  10 file(s)

  Total merged files: 45

──────────────────────────────────────────────────────────────
GATE 1 — STATIC CHECK
──────────────────────────────────────────────────────────────
  RESULT: PASS

──────────────────────────────────────────────────────────────
GATE 2 — INTEGRATION CHECK
──────────────────────────────────────────────────────────────

  Running Check 1: Route inventory...
    → 0 issue(s)
  Running Check 2: Model field refs...
    → 0 issue(s)
  Running Check 3: Spec compliance...
    → 0 issue(s)
  Running Check 4: Import chains...
    → 0 issue(s)
  Running Check 5: Route decorator double-path...
    → 0 issue(s)
  Running Check 6: Auth contract (route auth vs frontend headers)...
    → 0 issue(s)
  Running Check 7: Async misuse (await on non-async functions)...
    → 0 issue(s)
  Running Check 8: asyncio.gather with sync function args...
    → 0 issue(s)
  Running Check 9: npm package integrity (imports vs package.json)...
    → 0 issue(s)
  Running Check 10: Bare except / silent error swallow in services...
    → 0 issue(s)
  Running Check 11: Unbounded polling loops in frontend...
    → 0 issue(s)
  Running Check 12: Background task timeout vs intake SLA...
    → 0 issue(s)
  Running Check 13: Config object rendered as text in JSX...
    → 0 issue(s)
  Running Check 14: Dead buttons (no onClick / placeholder href)...
    → 0 issue(s)
  Running Check 15: Form state fields not in config form definition...
    → 0 issue(s)
  Running Check 16: Hollow service methods (no DB interaction)...
    → 0 issue(s)
  Running Check 17: Orphaned pages (UI with no backend coverage)...
    → 0 issue(s)
  Output written: fo_harness_runs/invoicetool.grilled_BLOCK_B_full_20260401_110213_check.json


============================================================
INTEGRATION CHECK COMPLETE
============================================================
  Total issues: 0  (HIGH: 0  MEDIUM: 0)
  Verdict: INTEGRATION_PASS
============================================================


══════════════════════════════════════════════════════════════
  COMBINED RESULT
══════════════════════════════════════════════════════════════

  Entities merged: 8
    invoicetool_s01_manage_users  (iteration_04_artifacts, 10 files)
    invoicetool_s02_configure_settings  (iteration_04_artifacts, 10 files)
    invoicetool_s03_view_all_invoices  (iteration_02_artifacts, 10 files)
    invoicetool_s04_view_invoices  (iteration_04_artifacts, 10 files)
    invoicetool_s05_make_payments  (iteration_03_artifacts, 10 files)
    invoicetool_s06_submit_invoices  (iteration_02_artifacts, 10 files)
    invoicetool_s07_manual_invoice_entry_form  (iteration_05_artifacts, 10 files)
    invoicetool_s08_email_notifications_for_invoice_status  (iteration_03_artifacts, 10 files)

  Static check     : PASS  (0 defect(s))
  Integration check: INTEGRATION_PASS  (HIGH:0  MED:0  Total:0)

  ✓ ALL CHECKS PASSED
```

**Step 6 — Generate business_config.json (Post-build)**
```bash
python generate_business_config.py \
  --zip fo_harness_runs/<startup>_BLOCK_B_full_<timestamp>.zip \
  --intake intake/intake_runs/<startup>/<startup>_phase_assessment.json \
  --seo seo/<startup>_business_brief_seo.json \
  --marketing gap-analysis/outputs/<startup>_business_brief_marketing_copy.json \
  --gtm gap-analysis/outputs/<startup>_business_brief_gtm.json \
  --include-harness-build
```
Notes:
- `--seo`, `--marketing`, `--gtm` are optional; if omitted they are skipped.
- `--include-harness-build` also writes into `_harness/build` iteration artifacts (optional).

**Step 7 — ZIP → Repo (GitHub)**
```bash
python deploy/zip_to_repo.py fo_harness_runs/<startup>_BLOCK_B_full_<timestamp>.zip
```
Example output (invoicetool):
```text
(cd39) Teebus-MacBook-Pro:FO_TEST_HARNESS teebuphilip$ python deploy/zip_to_repo.py fo_harness_runs/invoicetool.grilled_BLOCK_B_full_20260401_110213.zip
[ERROR] Missing required environment variables:
  - GITHUB_TOKEN not set
  - GITHUB_USERNAME not set
(cd39) Teebus-MacBook-Pro:FO_TEST_HARNESS teebuphilip$ export GITHUB_USERNAME=teebuphilip
(cd39) Teebus-MacBook-Pro:FO_TEST_HARNESS teebuphilip$ export GITHUB_TOKEN=`cat ~/Downloads/ACCESSKEYS/TEEBUGITHUBPERSONALACCESSTOKEN `
(cd39) Teebus-MacBook-Pro:FO_TEST_HARNESS teebuphilip$ python deploy/zip_to_repo.py fo_harness_runs/invoicetool.grilled_BLOCK_B_full_20260401_110213.zip
[INFO] Copied saas-boilerplate/backend/ → repo/backend/
[INFO] Copied saas-boilerplate/frontend/ → repo/frontend/
[INFO] Copied teebu-shared-libs/lib/ → repo/backend/libs/
[INFO] Merged business/ artifacts → repo/business/ (45 files)
[INFO]   invoicetool_s01_manage_users (iteration_04_artifacts) → 10 file(s)
[INFO]   invoicetool_s02_configure_settings (iteration_04_artifacts) → 10 file(s)
[INFO]   invoicetool_s03_view_all_invoices (iteration_02_artifacts) → 10 file(s)
[INFO]   invoicetool_s04_view_invoices (iteration_04_artifacts) → 10 file(s)
[INFO]   invoicetool_s05_make_payments (iteration_03_artifacts) → 10 file(s)
[INFO]   invoicetool_s06_submit_invoices (iteration_02_artifacts) → 10 file(s)
[INFO]   invoicetool_s07_manual_invoice_entry_form (iteration_05_artifacts) → 10 file(s)
[INFO]   invoicetool_s08_email_notifications_for_invoice_status (iteration_03_artifacts) → 10 file(s)
[INFO] Repo path: /Users/teebuphilip/Documents/work/invoicetool.grilled
Initialized empty Git repository in /Users/teebuphilip/Documents/work/invoicetool.grilled/.git/
[master (root-commit) f526c6c] Initial Invoicetool.Grilled integration from harness zip
 149 files changed, 48315 insertions(+)
...
[INFO] Creating GitHub repo: invoicetool.grilled
Enumerating objects: 178, done.
Counting objects: 100% (178/178), done.
Delta compression using up to 8 threads
Compressing objects: 100% (172/172), done.
Writing objects: 100% (178/178), 412.25 KiB | 6.87 MiB/s, done.
Total 178 (delta 16), reused 0 (delta 0)
remote: Resolving deltas: 100% (16/16), done.
To https://github.com/teebuphilip/invoicetool.grilled.git
 * [new branch]      main -> main
Branch 'main' set up to track remote branch 'main' from 'origin'.
[INFO] Pushed: https://github.com/teebuphilip/invoicetool.grilled
```

**Step 8 — Check Business Imports**
```bash
python deploy/check_business_imports.py --repo ~/Documents/work/<startup>
```
Example output:
```text
(cd39) Teebus-MacBook-Pro:FO_TEST_HARNESS teebuphilip$   python deploy/check_business_imports.py --repo ~/Documents/work/invoicetool.grilled
Checking business page imports...
  Repo: /Users/teebuphilip/Documents/work/invoicetool.grilled
  Extensions: .js, .jsx, .ts, .tsx, .json
  Report all: enabled
  Scanning business/frontend/pages/*.jsx ...
OK: No unresolved relative imports after copy.
```

**Step 9 — Prepare Deploy Configs (No Deploy)**
```bash
python deploy/pipeline_prepare.py --repo ~/Documents/work/<startup>
```
Example output:
```text
(cd39) Teebus-MacBook-Pro:FO_TEST_HARNESS teebuphilip$   python deploy/pipeline_prepare.py --repo ~/Documents/work/invoicetool.grilled

Loading credentials from environment variables
[ERROR] Missing required environment variables:
  - RAILWAY_TOKEN not set
  - VERCEL_TOKEN not set
(cd39) Teebus-MacBook-Pro:FO_TEST_HARNESS teebuphilip$ export RAILWAY_TOKEN=`cat ~/Downloads/ACCESSKEYS/RAILWAYKEY `
(cd39) Teebus-MacBook-Pro:FO_TEST_HARNESS teebuphilip$ export VERCEL_TOKEN=`cat ~/Downloads/ACCESSKEYS/VERCELKEY `
(cd39) Teebus-MacBook-Pro:FO_TEST_HARNESS teebuphilip$   python deploy/pipeline_prepare.py --repo ~/Documents/work/invoicetool.grilled

Loading credentials from environment variables
  [pipeline] No railway.deploy.json found - will create new Railway project
  [pipeline] No vercel.deploy.json found - will create new Vercel project
  [prepare] railway.deploy.json: project=invoicetool.grilled
  [prepare] vercel.deploy.json: project=invoicetool.grilled-frontend

============================================================
STEP 0/2: Generate deploy config(s) via AI (railway + vercel)
============================================================
  [pipeline] Updated railway.deploy.json with project IDs
  [pipeline] Updated vercel.deploy.json with project IDs

============================================================
STEP 1/3: Push to GitHub
============================================================
  Repo: teebuphilip/invoicetool.grilled
  Updated .gitignore with 2 entries
  [pipeline] Ensured frontend business_config.json is staged for push
  [pipeline] Created analytics_config.json from example
  [pipeline] Created auth0_config.json from example
  [pipeline] Created mailerlite_config.json from example
  [pipeline] Created stripe_config.json from example
  [pipeline] Force-staged all backend/config/*.json for push
  [pipeline] Copied business pages into frontend/src/business/pages/ (8 .jsx files)
  [pipeline] Patched loader.js: require.context path → ../business/pages
[main cae8a31] deploy: automated build commit
 19 files changed, 3400 insertions(+), 3 deletions(-)
 create mode 100644 backend/config/analytics_config.json
 create mode 100644 backend/config/auth0_config.json
 create mode 100644 backend/config/business_config.json
 create mode 100644 backend/config/capabilities.json
 create mode 100644 backend/config/mailerlite_config.json
 create mode 100644 backend/config/stripe_config.json
 create mode 100644 frontend/src/business/pages/ConfigureSettings.jsx
 create mode 100644 frontend/src/business/pages/EmailNotificationsForInvoiceStatus.jsx
 create mode 100644 frontend/src/business/pages/MakePayments.jsx
 create mode 100644 frontend/src/business/pages/ManageUsers.jsx
 create mode 100644 frontend/src/business/pages/ManualInvoiceEntryForm.jsx
 create mode 100644 frontend/src/business/pages/SubmitInvoices.jsx
 create mode 100644 frontend/src/business/pages/ViewAllInvoices.jsx
 create mode 100644 frontend/src/business/pages/ViewInvoices.jsx
 create mode 100644 frontend/src/config/business_config.json
 create mode 100644 railway.deploy.json
 create mode 100644 vercel.deploy.json
Enumerating objects: 24, done.
Counting objects: 100% (24/24), done.
Delta compression using up to 8 threads
Compressing objects: 100% (14/14), done.
Writing objects: 100% (15/15), 11.38 KiB | 5.69 MiB/s, done.
Total 15 (delta 6), reused 0 (delta 0)
remote: Resolving deltas: 100% (6/6), completed with 6 local objects.
To https://github.com/teebuphilip/invoicetool.grilled.git
   f526c6c..cae8a31  main -> main
Branch 'main' set up to track remote branch 'main' from 'origin'.
  Pushed to: https://github.com/teebuphilip/invoicetool.grilled

============================================================
PREP COMPLETE (NO DEPLOY)
============================================================
  Repo path: /Users/teebuphilip/Documents/work/invoicetool.grilled
  GitHub:    https://github.com/teebuphilip/invoicetool.grilled
  Repo:      teebuphilip/invoicetool.grilled
  Next:      python deploy/pipeline_deploy.py --repo /Users/teebuphilip/Documents/work/invoicetool.grilled
============================================================
```

---

**Addendum — Rerun a Slice / Feature (use add_feature.sh)**
```bash
./add_feature.sh \
  --intake intake/intake_runs/<startup>/<startup>_sXX_<feature>.json \
  --feature "<feature description>" \
  --existing-repo ~/Documents/work/<startup> \
  --spec-file intake/intake_runs/<startup>/<startup>_sXX_<feature>_spec.txt
```
Example output:
```text
(cd39) Teebus-MacBook-Pro:FO_TEST_HARNESS teebuphilip$ ./add_feature.sh --intake intake/intake_runs/invoicetool/invoicetool.grilled_s05_make_payments.json --feature "Wire Stripe payment processing using boilerplate stripe_lib for invoice payments"  --existing-repo ~/Documents/work/invoicetool.grilled  --spec-file intake/intake_runs/invoicetool/invoicetool.grilled_s05_make_payments_spec.txt 
========================================================
  ADD FEATURE PIPELINE
  Intake        : intake/intake_runs/invoicetool/invoicetool.grilled_s05_make_payments.json
  Feature       : Wire Stripe payment processing using boilerplate stripe_lib for invoice payments
  Feature slug  : wire_stripe_payment_processing_using_boi
  Base (repo)   : /Users/teebuphilip/Documents/work/invoicetool.grilled
  Max iter      : 20
  Build GOV     : FOBUILFINALLOCKED100.zip
========================================================

▶ STEP 1 — Generate Feature Intake
────────────────────────────────────────────────────────
  ↩ Feature intake already exists — skipping:
    intake/intake_runs/invoicetool/invoicetool.grilled_s05_make_payments_feature_wire_stripe_payment_processing_using_boi.json


▶ STEP 2 — Build Feature: Wire Stripe payment processing using boilerplate stripe_lib for invoice payments
────────────────────────────────────────────────────────
→ Loading BUILD governance ZIP...
✓ BUILD governance loaded
→ Tech stack override loaded (stack: lowcode)
→ External integration override loaded
→ QA override loaded (tightened evaluation criteria)
→ QA_POLISH_2 directive: directives/qa_polish_2_doc_recovery.md
→ QA_TESTCASE directive: directives/qa_testcase_doc_directive.md

======================================================================
FO HARNESS INITIALIZED
======================================================================

→ Startup:       invoicetool_s05_make_payments_wire_stripe_payment_processing_using_boi
→ Block:         BLOCK_B
→ Tech stack:    lowcode (effective: lowcode)
→ Boilerplate:   YES
→ Max iterations:20
→ Build caps:    max_parts=10, max_continuations=9
→ Quality gate:  ON
→ Factory mode:  OFF
→ Polish:        ON
→ Deploy:        NO — ZIP output only
→ Run directory: fo_harness_runs/invoicetool_s05_make_payments_wire_stripe_payment_processing_using_boi_BLOCK_B_20260402_061746

======================================================================
STARTING BUILD → QA LOOP (BLOCK_B)
======================================================================

→   Feature tracking: 1 feature from slice planner (Make Payments)
→ Warm-start: rebuilding prohibition tracker from 12 prior QA report(s)...
✓ Warm-start tracker rebuilt: 14 defect(s) tracked, 14 prohibition(s) active

======================================================================
ITERATION 1/20
======================================================================

→ Intake: intake/intake_runs/invoicetool/invoicetool.grilled_s05_make_payments_feature_wire_stripe_payment_processing_using_boi.json
→ ═══════════════════════════════════════════════════════════
→ ITERATION 1 - CLAUDE BUILD CALL
→ ═══════════════════════════════════════════════════════════
→ Prompt structure:
→   → Cacheable section: 22,596 chars (governance ZIP)
→   → Dynamic section: 94,590 chars (intake + defects)
→   → Total prompt size: 117,186 chars
→ Token limit: 16,384 tokens (iteration 1)
→ Request timeout: 600s (10 minutes)
→ Cache enabled: YES
→ ───────────────────────────────────────────────────────────
→ Calling Claude API...
→ [2026-04-02 06:17:46] → Claude API request sent
→ [2026-04-02 06:18:20] ← Claude API response received (34.0s)
✓ Claude responded in 34.0s
→ ═══════════════════════════════════════════════════════════
→ CLAUDE API USAGE BREAKDOWN - ITERATION 1
→ ═══════════════════════════════════════════════════════════
→ Input tokens:
→   → Cache creation (write): 7,246 tokens
→   → Non-cached input: 28,173 tokens
→   → Total input: 35,419 tokens
→   → Cache status: FIRST WRITE (will be cached for 5 minutes)
→ Output tokens: 2,854 tokens
→ Cost estimate:
→   → Cache write: $0.0272
→   → Non-cached input: $0.0845
→   → Output: $0.0428
→   → Total this call: $0.1545
→ ═══════════════════════════════════════════════════════════
✓ BUILD completed in 34.0s
✓ Build complete — 7 files extracted
✓ Saved BUILD output: build/iteration_01_build.txt
→   → Extracted: business/models/make_payments.py
→   → Extracted: business/schemas/make_payments.py
→   → Extracted: business/services/make_payments_service.py
→   → Extracted: business/backend/routes/make_payments.py
→   → Extracted: business/frontend/pages/MakePayments.jsx
→   → Extracted: business/README-INTEGRATION.md
→   → Extracted: business/package.json
→   → Generated: build_state.json (COMPLETED_CLOSED)
→   → Generated: artifact_manifest.json (7 files)
✓ Extracted 7 artifact(s) from BUILD output
→ ═══════════════════════════════════════════════════════════
→ PRE-QA VALIDATION - Checking build completeness
→ ═══════════════════════════════════════════════════════════
⚠   → README.md not in manifest (will be flagged by QA as HIGH severity)
⚠   → .env.example not in manifest (will be flagged by QA as HIGH severity)
⚠   → .gitignore not in manifest (will be flagged by QA as HIGH severity)
⚠   → test not in manifest (will be flagged by QA as HIGH severity)
⚠   → spec not in manifest (will be flagged by QA as HIGH severity)
✓ ✓ Build validation passed - all critical artifacts present
→ ───────────────────────────────────────────────────────────
→ 
→ ═══════════════════════════════════════════════════════════
→ GATE 0: COMPILE CHECK — Mandatory pre-QA compile pass
→ ═══════════════════════════════════════════════════════════
✓   [COMPILE] PASS — compile checks succeeded
→ 
→ ═══════════════════════════════════════════════════════════
→ GATE 2: STATIC CHECK — Deterministic code quality pass
→ ═══════════════════════════════════════════════════════════
✓   [STATIC] PASS — no static defects
→ 
→ ═══════════════════════════════════════════════════════════
→ GATE 1.5: INTEGRATION_FAST — Structural pre-check (checks 1,2,4,6,7)
→ ═══════════════════════════════════════════════════════════
✓   [INTEGRATION_FAST] PASS — no structural issues found
→ 
→ ═══════════════════════════════════════════════════════════
→ GATE 3: AI CONSISTENCY CHECK — Cross-file analysis
→ ═══════════════════════════════════════════════════════════
→   [CONSISTENCY] Sending 6 file(s) (filtered from 11 total — models/services/routes/schemas only)
→ [2026-04-02 06:18:20] → ChatGPT API request sent
→ [2026-04-02 06:18:23] ← ChatGPT API response received (2.2s)
→   [CONSISTENCY] ChatGPT responded ($0.0112)
→ CACHE CHECK [CONSISTENCY] iteration 1: cached=0 / total_prompt=4409 (0% cached)
✓   [CONSISTENCY] PASS — no cross-file consistency issues
→ 
→ ═══════════════════════════════════════════════════════════
→ GATE 4: QUALITY GATE — Completeness/Quality/Enhanceability/Deployability
→ ═══════════════════════════════════════════════════════════
→   [QUALITY] SKIPPED — repair mode, iteration 1 of 20
→ Calling ChatGPT for QA...
→ [2026-04-02 06:18:23] → ChatGPT API request sent
→ [2026-04-02 06:18:42] ← ChatGPT API response received (19.4s)
✓ QA completed in 19.4s
→ ═══════════════════════════════════════════════════════════
→ CHATGPT API USAGE - ITERATION 1 QA
→ ═══════════════════════════════════════════════════════════
→ Input tokens:  22,604 tokens
→ Output tokens: 646 tokens
→ Total tokens:  23,250 tokens
→ 
→ Cost estimate:
→   → Input:  $0.0565
→   → Output: $0.0065
→   → Total:  $0.0630
→ CACHE CHECK [FEATURE_QA] iteration 1: cached=0 / total_prompt=22604 (0% cached)
→ ═══════════════════════════════════════════════════════════
⚠   [FILTER] Removed DEFECT-1: Evidence only references standard infrastructure column(s) (status/created_at/updated_at) — these are required on every model and must never be flagged as scope violations
⚠   [FILTER] Removed DEFECT-2: Evidence ['javascript\n    const token = await user.getAccessTokenSilently();'] not found in build output — fabricated
⚠   [FILTER] Removed DEFECT-3: Chain-of-evidence: no backtick-quoted code snippet in Evidence — defect has no proof
→   [FILTER] QA report filtered: 3 defect(s) removed, 1 remaining
→ [2026-04-02 06:18:42] → ChatGPT API request sent
→ [2026-04-02 06:18:45] ← ChatGPT API response received (3.2s)
→   [TRIAGE] DEFECT-1 [SURGICAL] business/models/make_payments.py — This issue results from unnecessary reimplementation of core database utilities that shoul
→            ROOT_CAUSE: The code imports `Base` from `core.database` which is not needed, leading to redundancy.
→   [TRIAGE] DEFECT-1 Fix field sharpened
→   [TRIAGE] Strategy: SURGICAL (1 surgical, 0 systemic, 0 invalid)
✓ Saved QA report: qa/iteration_01_qa_report.txt
⚠ QA REJECTED — defects found
⚠   → 1 defects to fix
→ 
→ ═══════════════════════════════════════════════════════════
→ ITERATION 1 - DEFECTS FOUND
→ ═══════════════════════════════════════════════════════════
→ ## ROOT CAUSE ANALYSIS (from triage — fix the cause, not just the symptom)
- DEFECT-1 (business/models/make_payments.py): The code imports `Base` from `core.database` which is not needed, leading to redundancy.

Fix the root cause FIRST. Individual defects should resolve as a consequence.

DEFECT-1: SPEC_COMPLIANCE_ISSUE
  - Location: business/models/make_payments.py
  - Evidence: `from core.database import Base` appears but not needed.
  - What breaks: This implies redundancy in model definition.
  - Problem: The model should not reimplement any core base expectations provided by the framework.
  - Expected: Stick to definitions relying on the base framework utilities already available.
  - Fix: In business/models/make_payments.py, remove the line `from core.database import Base`.
  - Severity: MEDIUM
  - Root cause type: ONE-TIME-BUG
→ ═══════════════════════════════════════════════════════════
→ 
→ 
→ ═══════════════════════════════════════════════════════════
→ CUMULATIVE COST AFTER ITERATION 1
→ ═══════════════════════════════════════════════════════════
→ Claude API:
→   → Calls: 1
→   → Cache writes: 1, Cache hits: 0
→   → Total cost: $0.1545
→ ChatGPT API:
→   → Calls: 1
→   → Total cost: $0.0630
✓ TOTAL COST SO FAR: $0.2175
→ ═══════════════════════════════════════════════════════════
→ 
⚠   [PROHIBITIONS] 14 recurring defect(s) promoted to hard prohibition
→ Starting iteration 2 with defect fixes...

======================================================================
ITERATION 2/20
======================================================================

→ Intake: intake/intake_runs/invoicetool/invoicetool.grilled_s05_make_payments_feature_wire_stripe_payment_processing_using_boi.json
→   [QA] Loaded 5 current file(s) for surgical QA patch
→   [QA] Using surgical patch for 5 targeted QA defect file(s)
→ ═══════════════════════════════════════════════════════════
→ ITERATION 2 - CLAUDE BUILD CALL
→ ═══════════════════════════════════════════════════════════
→ Prompt structure:
→   → Cacheable section: 22,596 chars (governance ZIP)
→   → Dynamic section: 14,046 chars (intake + defects)
→   → Total prompt size: 36,642 chars
→ Token limit: 16,384 tokens (iteration 2)
→ Request timeout: 300s (5 minutes)
→ Cache enabled: YES (expecting hit)
→ ───────────────────────────────────────────────────────────
→ Calling Claude API...
→ [2026-04-02 06:18:45] → Claude API request sent
→ [2026-04-02 06:19:08] ← Claude API response received (22.9s)
✓ Claude responded in 22.9s
→ ═══════════════════════════════════════════════════════════
→ CLAUDE API USAGE BREAKDOWN - ITERATION 2
→ ═══════════════════════════════════════════════════════════
✓ Input tokens:
✓   → Cache read (hit): 7,246 tokens ✓ CACHE HIT!
✓   → Non-cached input: 4,000 tokens
✓   → Total input: 11,246 tokens
✓   → Cache savings: $0.0196 (90% cheaper than write)
→ Output tokens: 2,372 tokens
→ Cost estimate:
✓   → Cache read: $0.0022 (vs $0.0217 without cache)
→   → Non-cached input: $0.0120
→   → Output: $0.0356
→   → Total this call: $0.0498
→ ═══════════════════════════════════════════════════════════
✓ BUILD completed in 22.9s
⚠ BIG BUILD DETECTED: standard fallback continuation mode active (max continuations=9)
⚠ Output still truncated - requesting continuation 1/9...
→ CONTINUATION 1 - fallback mode
→ [2026-04-02 06:19:08] → Claude API request sent
→ [2026-04-02 06:20:00] ← Claude API response received (52.1s)
✓ Continuation 1 completed in 52.1s
→ ═══════════════════════════════════════════════════════════
→ CLAUDE API USAGE BREAKDOWN - CONTINUATION 1
→ ═══════════════════════════════════════════════════════════
✓ Input tokens:
✓   → Cache read (hit): 7,246 tokens ✓ CACHE HIT!
✓   → Non-cached input: 624 tokens
✓   → Total input: 7,870 tokens
✓   → Cache savings: $0.0196 (90% cheaper than write)
→ Output tokens: 5,859 tokens
→ Cost estimate:
✓   → Cache read: $0.0022 (vs $0.0217 without cache)
→   → Non-cached input: $0.0019
→   → Output: $0.0879
→   → Total this call: $0.0919
→ ═══════════════════════════════════════════════════════════
✓ Build complete — 10 files extracted
⚠   [PATCH_SET_COMPLETE] Truncated 5 collateral file(s) Claude output after marker — ignored: business/frontend/pages/InvoicesPage.jsx, business/frontend/pages/PaymentsPage.jsx, business/frontend/pages/CreateInvoicePage.jsx, core/main.py, alembic/versions/001_initial_schema.py
✓ Saved BUILD output: build/iteration_02_build.txt
→   → Extracted: business/models/make_payments.py
→   → Extracted: business/schemas/make_payments.py
→   → Extracted: business/services/make_payments_service.py
→   → Extracted: business/backend/routes/make_payments.py
→   → Extracted: business/frontend/pages/MakePayments.jsx
→   → Generated: build_state.json (COMPLETED_CLOSED)
→   → Generated: artifact_manifest.json (5 files)
✓ Extracted 5 artifact(s) from BUILD output
→   → Carried forward: business/README-INTEGRATION.md
→   → Carried forward: business/package.json
→   → Carried forward 2 unchanged file(s) from iteration 01 (listed above)
→   → Generated: artifact_manifest.json (7 files)
✓ Saved defect fix: build/iteration_02_fix.txt
→ ═══════════════════════════════════════════════════════════
→ PRE-QA VALIDATION - Checking build completeness
→ ═══════════════════════════════════════════════════════════
⚠   → README.md not in manifest (will be flagged by QA as HIGH severity)
⚠   → .env.example not in manifest (will be flagged by QA as HIGH severity)
⚠   → .gitignore not in manifest (will be flagged by QA as HIGH severity)
⚠   → test not in manifest (will be flagged by QA as HIGH severity)
⚠   → spec not in manifest (will be flagged by QA as HIGH severity)
✓ ✓ Build validation passed - all critical artifacts present
→ ───────────────────────────────────────────────────────────
→ 
→ ═══════════════════════════════════════════════════════════
→ GATE 0: COMPILE CHECK — Mandatory pre-QA compile pass
→ ═══════════════════════════════════════════════════════════
✓   [COMPILE] PASS — compile checks succeeded
→ 
→ ═══════════════════════════════════════════════════════════
→ GATE 2: STATIC CHECK — Deterministic code quality pass
→ ═══════════════════════════════════════════════════════════
✓   [STATIC] PASS — no static defects
→ 
→ ═══════════════════════════════════════════════════════════
→ GATE 1.5: INTEGRATION_FAST — Structural pre-check (checks 1,2,4,6,7)
→ ═══════════════════════════════════════════════════════════
✓   [INTEGRATION_FAST] PASS — no structural issues found
→ 
→ ═══════════════════════════════════════════════════════════
→ GATE 3: AI CONSISTENCY CHECK — Cross-file analysis
→ ═══════════════════════════════════════════════════════════
→   [CONSISTENCY] LOCKED — skipped, no relevant files changed
→ 
→ ═══════════════════════════════════════════════════════════
→ GATE 4: QUALITY GATE — Completeness/Quality/Enhanceability/Deployability
→ ═══════════════════════════════════════════════════════════
→   [QUALITY] SKIPPED — repair mode, iteration 2 of 20
→ Calling ChatGPT for QA...
→ [2026-04-02 06:20:01] → ChatGPT API request sent
→ [2026-04-02 06:20:23] ← ChatGPT API response received (22.5s)
✓ QA completed in 22.5s
→ ═══════════════════════════════════════════════════════════
→ CHATGPT API USAGE - ITERATION 2 QA
→ ═══════════════════════════════════════════════════════════
→ Input tokens:  25,847 tokens
→ Output tokens: 935 tokens
→ Total tokens:  26,782 tokens
→ 
→ Cost estimate:
→   → Input:  $0.0646
→   → Output: $0.0093
→   → Total:  $0.0740
→ CACHE CHECK [FEATURE_QA] iteration 2: cached=18560 / total_prompt=25847 (71% cached)
→ ═══════════════════════════════════════════════════════════
⚠   [FILTER] Removed DEFECT-1: Chain-of-evidence: 'What breaks' uses hedge phrase 'could ' — defect is speculative
⚠   [FILTER] Removed DEFECT-2: Chain-of-evidence: 'What breaks' uses hedge phrase 'may ' — defect is speculative
⚠   [FILTER] Removed DEFECT-3: Chain-of-evidence: 'What breaks' uses hedge phrase 'may ' — defect is speculative
⚠   [FILTER] Removed DEFECT-4: Evidence ['jsx\n    const [formData, setFormData] = useState({\n      amount: "",\n      payment_method: "card"\n    });'] not found in build output — fabricated
⚠   [FILTER] Removed DEFECT-5: Evidence ['python\n    class MakePaymentsResponse(BaseModel):\n        status: str'] not found in build output — fabricated
→   [FILTER] QA report filtered: 5 defect(s) removed, 0 remaining
✓ Saved QA report: qa/iteration_02_qa_report.txt
✓ GATE 1 PASSED: Feature QA ACCEPTED on iteration 2
⚠   [ACCEPTANCE] QUALITY gate has not run in acceptance mode yet — forcing acceptance mode now
→   [QUALITY] Evaluating 10 artifact(s) (filtered from 11 total) across 4 quality dimensions...
→ [2026-04-02 06:20:23] → ChatGPT API request sent
→ [2026-04-02 06:20:30] ← ChatGPT API response received (6.6s)
→   [QUALITY] ChatGPT responded ($0.0280)
→ CACHE CHECK [QUALITY] iteration 2: cached=0 / total_prompt=9958 (0% cached)
→   [QUALITY] LOW accepted for Completeness/Code Quality/Deployability — treating gate as PASS
✓   [QUALITY] Forced acceptance-mode run: PASS
✓ 
✓ ══════════════════════════════════════════════════════════
✓ ALL QA GATES PASSED: Compile + Static + AI Consistency + Quality + Feature QA
✓ ══════════════════════════════════════════════════════════
→   Feature state saved: 1 passing, 0 failing → fo_harness_runs/invoicetool_s05_make_payments_wire_stripe_payment_processing_using_boi_BLOCK_B_20260402_061746/feature_state.json
→ 
→ ═══════════════════════════════════════════════════════════
→ POST-QA POLISH - Generating missing optional files
→ ═══════════════════════════════════════════════════════════
→ → Generating business_config.json from intake...
✓   ✓ business_config.json → business/frontend/config/business_config.json
✓   ✓ business_config.json → business/backend/config/business_config.json
→ → Missing optional files: README.md, .env.example, Tests (only 0 found), Docs (HLD + QUICKSTART)
→ 
→ → README.md missing - generating...
→ → Calling Claude for README generation...
→ [2026-04-02 06:20:30] → Claude API request sent
→ [2026-04-02 06:20:49] ← Claude API response received (19.0s)
✓ ✓ Generated README.md (1192 chars) in 19.0s
→   → Saved to: iteration_02_artifacts/README.md
→   → Cost: $0.0216
→ 
→ → .env.example missing - generating...
→ → Calling Claude for .env.example generation...
→ [2026-04-02 06:20:49] → Claude API request sent
→ [2026-04-02 06:20:54] ← Claude API response received (5.3s)
✓ ✓ Generated .env.example (1151 chars) in 5.4s
→   → Saved to: iteration_02_artifacts/.env.example
→   → Cost: $0.0069
→ 
→ → Only 0 test file(s) found - generating additional tests...
→ → Calling Claude for test generation...
→ [2026-04-02 06:20:54] → Claude API request sent
→ [2026-04-02 06:21:55] ← Claude API response received (60.7s)
✓ ✓ Generated 0 test file(s) in 60.7s
→   → Saved to: iteration_02_artifacts/
→   → Cost: $0.0924
→ 
→ → Calling Claude for docs generation...
→ [2026-04-02 06:21:55] → Claude API request sent
→ [2026-04-02 06:22:41] ← Claude API response received (46.6s)
→ → Calling ChatGPT for testcase doc generation...
→ [2026-04-02 06:22:41] → ChatGPT API request sent
→ [2026-04-02 06:23:10] ← ChatGPT API response received (29.1s)
✓ ✓ Generated testcase doc: fo_harness_runs/invoicetool_s05_make_payments_wire_stripe_payment_processing_using_boi_BLOCK_B_20260402_061746/build/iteration_02_artifacts/business/docs/TEST_CASES.md
→   → Generated: artifact_manifest.json (16 files)
✓ ✓ Post-QA polish complete
→   → Generated 5 file(s)
→   → Total polish cost: $0.2001
→ ═══════════════════════════════════════════════════════════
→ 
→ 
→ ═══════════════════════════════════════════════════════════
→ FULL RUN COST ANALYSIS
→ ═══════════════════════════════════════════════════════════
→ Total iterations: 2
→ Total Claude calls: 8 (2 builds + 6 continuations)
→ 
→ Cache performance:
→   → Cache writes: 1
→   → Cache hits: 2
✓   → Cache hit rate: 25.0%
✓   → Total tokens read from cache: 14,492 tokens
→ 
→ Token usage:
→   → Cache write tokens: 7,246 tokens
→   → Cache read tokens: 14,492 tokens
→   → Non-cached input tokens: 41,435 tokens
→   → Output tokens: 22,699 tokens
→ 
→ Cost breakdown:
→   → Cache writes: $0.0272
✓   → Cache reads: $0.0043
→   → Non-cached input: $0.1243
→   → Output: $0.3405
→   → Total with caching: $0.4963
→ 
✓ Without caching: $0.5300
✓ Total saved: $0.0337 (6% reduction)
→ 
→ Dynamic token limiting:
→   → Estimated additional savings: $0.0511 (15% of output)
✓   → Combined Claude savings: $0.0848
→ 
→ ChatGPT (QA) costs:
→   → Total QA calls: 3
→   → Input tokens: 58,409 tokens
→   → Output tokens: 1,894 tokens
→   → Input cost: $0.1460
→   → Output cost: $0.0189
→   → Total ChatGPT: $0.1650
→ 
✓ TOTAL COST (Claude + ChatGPT): $0.6613
✓   → Claude: $0.4963
✓   → ChatGPT: $0.1650
✓ Total saved from caching: $0.0848
→ ═══════════════════════════════════════════════════════════
→ Run logged to: /Users/teebuphilip/Downloads/FO_TEST_HARNESS/fo_run_log.csv
✓ Generated artifact manifest: artifact_manifest.json
→ Packaging output ZIP: invoicetool_s05_make_payments_wire_stripe_payment_processing_using_boi_BLOCK_B_20260402_061746.zip
→ Including boilerplate: /Users/teebuphilip/Documents/work/teebu-saas-platform
✓ ZIP created: fo_harness_runs/invoicetool_s05_make_payments_wire_stripe_payment_processing_using_boi_BLOCK_B_20260402_061746.zip (0.74 MB)

======================================================================
EXECUTION SUMMARY
======================================================================

Startup:        invoicetool_s05_make_payments_wire_stripe_payment_processing_using_boi
Block:          BLOCK_B
Status:         ✓ SUCCESS
Total time:     327.5s (5.5 minutes)
Deployed:       No
Claude cost:    $0.50
ChatGPT cost:   $0.16
Total cost:     $0.66
ZIP output:     fo_harness_runs/invoicetool_s05_make_payments_wire_stripe_payment_processing_using_boi_BLOCK_B_20260402_061746.zip

Run directory:  fo_harness_runs/invoicetool_s05_make_payments_wire_stripe_payment_processing_using_boi_BLOCK_B_20260402_061746

Generated files:
  - BUILD outputs:   63
  - QA reports:      2
  - DEPLOY outputs:  0
  - Logs:            12

✓ PIPELINE COMPLETED SUCCESSFULLY
✓ Feature ZIP: fo_harness_runs/invoicetool_s05_make_payments_wire_stripe_payment_processing_using_boi_BLOCK_B_20260402_061746.zip

▶ STEP 3 — Integration Check
────────────────────────────────────────────────────────
  Using artifacts dir: fo_harness_runs/invoicetool_s05_make_payments_wire_stripe_payment_processing_using_boi_BLOCK_B_20260402_061746/build/iteration_02_artifacts

Loading artifacts...
  10 file(s) loaded

  Running Check 1: Route inventory...
    → 0 issue(s)
  Running Check 2: Model field refs...
    → 0 issue(s)
  Running Check 3: Spec compliance...
    → 2 issue(s)
  Running Check 4: Import chains...
    → 0 issue(s)
  Running Check 5: Route decorator double-path...
    → 0 issue(s)
  Running Check 6: Auth contract (route auth vs frontend headers)...
    → 0 issue(s)
  Running Check 7: Async misuse (await on non-async functions)...
    → 0 issue(s)
  Running Check 8: asyncio.gather with sync function args...
    → 0 issue(s)
  Running Check 9: npm package integrity (imports vs package.json)...
    → 0 issue(s)
  Running Check 10: Bare except / silent error swallow in services...
    → 0 issue(s)
  Running Check 11: Unbounded polling loops in frontend...
    → 0 issue(s)
  Running Check 12: Background task timeout vs intake SLA...
    → 0 issue(s)
  Running Check 13: Config object rendered as text in JSX...
    → 0 issue(s)
  Running Check 14: Dead buttons (no onClick / placeholder href)...
    → 0 issue(s)
  Running Check 15: Form state fields not in config form definition...
    → 0 issue(s)
  Running Check 16: Hollow service methods (no DB interaction)...
    → 0 issue(s)
  Running Check 17: Orphaned pages (UI with no backend coverage)...
    → 0 issue(s)

  Output written: fo_harness_runs/invoicetool_s05_make_payments_wire_stripe_payment_processing_using_boi_BLOCK_B_20260402_061746/integration_issues.json

============================================================
INTEGRATION CHECK COMPLETE
============================================================
  Total issues: 2  (HIGH: 0  MEDIUM: 2)
  Verdict: INTEGRATION_REJECTED

  Issues found:
    [MEDIUM] INT-SPEC-KPI-MVP (SPEC_COMPLIANCE)
           KPI 'MVP' defined in intake but not referenced anywhere in artifacts
    [MEDIUM] INT-SPEC-KPI-HLD (SPEC_COMPLIANCE)
           KPI 'HLD' defined in intake but not referenced anywhere in artifacts

  Fix target files:
    - business/services/ScoringService.py

  Run harness fix pass:
    python fo_test_harness.py <intake> --resume-run <run_dir> --resume-iteration <N> --integration-issues integration_issues.json
============================================================

ℹ Integration issues are MEDIUM-only — skipping fix pass
✓ Integration check clean.

▶ STEP 4 — Merge into new final ZIP
────────────────────────────────────────────────────────
  Layering (later source wins on conflict):
    Base (repo) : /Users/teebuphilip/Documents/work/invoicetool.grilled
    Feature     : fo_harness_runs/invoicetool_s05_make_payments_wire_stripe_payment_processing_using_boi_BLOCK_B_20260402_061746.zip
========================================================
  FEATURE ADD COMPLETE

  Feature       : Wire Stripe payment processing using boilerplate stripe_lib for invoice payments
  Base          : /Users/teebuphilip/Documents/work/invoicetool.grilled
  Feature ZIP   : fo_harness_runs/invoicetool_s05_make_payments_wire_stripe_payment_processing_using_boi_BLOCK_B_20260402_061746.zip
  FINAL ZIP     : fo_harness_runs/invoicetool_grilled_s05_make_payments_wire_stripe_payment_processing_using_boi_FINAL_20260402_062314.zip  (844K)
========================================================

Next step — deploy:
  python deploy/zip_to_repo.py fo_harness_runs/invoicetool_grilled_s05_make_payments_wire_stripe_payment_processing_using_boi_FINAL_20260402_062314.zip
```

**What `check_block_b.py` does**
- Deterministic Block B quality checker (no AI).
- Validates passes 1–6, core fields, and basic coverage.
- Outputs a score and PASS/WARN/FAIL status.
- Exit codes: `0=PASS`, `1=WARN`, `2=FAIL`, `3=ERROR`.

Example output (boilerplate fit after intake, from `invoicetool`):
```text
======================================================================
BOILERPLATE FIT CHECKER
======================================================================

→ Intake:     /Users/teebuphilip/Downloads/FO_TEST_HARNESS/intake/intake_runs/invoicetool/invoicetool.json
→ Boilerplate: /Users/teebuphilip/Documents/work/teebu-saas-platform
→ Loading intake JSON...
✓ Loaded intake: invoicetool
→ Reading boilerplate (ZIP or directory)...
✓ Boilerplate manifest built
→ Boilerplate manifest size: 232,307 chars
→ Prompt size: 246,995 bytes
✓ Prompt logged: invoicetool_analysis_prompt.log
→ Calling ChatGPT for analysis...
✓ Analysis complete in 18.4s
→ AI cost: $0.1593 (cumulative: $0.1593)
→ Cost CSV: /Users/teebuphilip/Downloads/FO_TEST_HARNESS/intake/boilerplate_checks/boilerplate_fit_ai_costs.csv
→ Parsing verdict...

======================================================================
BOILERPLATE FIT CHECK — Invoicetool
======================================================================

VERDICT: YES — USE BOILERPLATE
Fit Score: 10/10
Summary:   The business idea fits perfectly with the capabilities of the boilerplate, requiring no additional dependencies or features outside its scope.

Boilerplate Already Handles:
✓ User authentication via Auth0
✓ Payment processing via Stripe
✓ Email marketing via MailerLite
✓ Analytics tracking via GA4

Backend Routes to Build (1 files):
  [HIGH] business/backend/routes/vendor_invoices.py → /api/vendor_invoices
         Manage vendor invoices for Etsy sellers

Frontend Pages to Build (1 files):
  [HIGH] business/frontend/pages/VendorInvoices.jsx → /dashboard/vendor-invoices
         Display and manage vendor invoices for Etsy sellers

Recommendation:
  Proceed with building the backend routes and frontend pages as outlined. Ensure to set up the necessary Stripe products and test the integration thoroughly.

Output saved: boilerplate_checks/invoicetool_boilerplate_check.json

Next step: Run the test harness with --use-boilerplate
  Pass this file to the harness: boilerplate_checks/invoicetool_boilerplate_check.json
```
6. Example output (boilerplate fit before grill-me, from `invoicetool`): see above.
7. Example output (check_block_b, from `invoicetool`):
```text
(cd39) Teebus-MacBook-Pro:FO_TEST_HARNESS teebuphilip$ python check_block_b.py /Users/teebuphilip/Downloads/FO_TEST_HARNESS/intake/intake_runs/invoicetool/invoicetool.grilled.json

Block B Quality Check — invoicetool
====================================================
Score  : 86 / 100
Status : PASS
Issues : 2

  [MEDIUM  ] pass_3 / test_vectors
             Only 1 test vector(s) — at least 2 recommended
  [HIGH    ] pass_4 / combined_task_list
             Only 2 task(s) — suspiciously sparse for a real product
```
9. Example output (run_auto_build / slice pipeline success + integration check + final ZIP):
```text
→   → Generated 5 file(s)
→   → Total polish cost: $0.2107
→ ═══════════════════════════════════════════════════════════
→ 
→ 
→ ═══════════════════════════════════════════════════════════
→ FULL RUN COST ANALYSIS
→ ═══════════════════════════════════════════════════════════
→ Total iterations: 3
→ Total Claude calls: 10 (3 builds + 7 continuations)
→ 
→ Cache performance:
→   → Cache writes: 0
→   → Cache hits: 5
✓   → Cache hit rate: 50.0%
✓   → Total tokens read from cache: 36,230 tokens
→ 
→ Token usage:
→   → Cache write tokens: 0 tokens
→   → Cache read tokens: 36,230 tokens
→   → Non-cached input tokens: 43,192 tokens
→   → Output tokens: 24,539 tokens
→ 
→ Cost breakdown:
✓   → Cache reads: $0.0109
→   → Non-cached input: $0.1296
→   → Output: $0.3681
→   → Total with caching: $0.5085
→ 
✓ Without caching: $0.6064
✓ Total saved: $0.0978 (16% reduction)
→ 
→ Dynamic token limiting:
→   → Estimated additional savings: $0.0552 (15% of output)
✓   → Combined Claude savings: $0.1530
→ 
→ ChatGPT (QA) costs:
→   → Total QA calls: 2
→   → Input tokens: 35,208 tokens
→   → Output tokens: 1,342 tokens
→   → Input cost: $0.0880
→   → Output cost: $0.0134
→   → Total ChatGPT: $0.1014
→ 
✓ TOTAL COST (Claude + ChatGPT): $0.6100
✓   → Claude: $0.5085
✓   → ChatGPT: $0.1014
✓ Total saved from caching: $0.1530
→ ═══════════════════════════════════════════════════════════
→ Run logged to: /Users/teebuphilip/Downloads/FO_TEST_HARNESS/fo_run_log.csv
✓ Generated artifact manifest: artifact_manifest.json
→ Packaging output ZIP: invoicetool_s08_email_notifications_for_invoice_status_BLOCK_B_20260401_105556.zip
→ Including boilerplate: /Users/teebuphilip/Documents/work/teebu-saas-platform
✓ ZIP created: fo_harness_runs/invoicetool_s08_email_notifications_for_invoice_status_BLOCK_B_20260401_105556.zip (0.74 MB)

======================================================================
EXECUTION SUMMARY
======================================================================

Startup:        invoicetool_s08_email_notifications_for_invoice_status
Block:          BLOCK_B
Status:         ✓ SUCCESS
Total time:     377.4s (6.3 minutes)
Deployed:       No
Claude cost:    $0.51
ChatGPT cost:   $0.10
Total cost:     $0.61
ZIP output:     fo_harness_runs/invoicetool_s08_email_notifications_for_invoice_status_BLOCK_B_20260401_105556.zip

Run directory:  fo_harness_runs/invoicetool_s08_email_notifications_for_invoice_status_BLOCK_B_20260401_105556

Generated files:
  - BUILD outputs:   94
  - QA reports:      1
  - DEPLOY outputs:  0
  - Logs:            15

✓ PIPELINE COMPLETED SUCCESSFULLY
✓ Slice ZIP: fo_harness_runs/invoicetool_s08_email_notifications_for_invoice_status_BLOCK_B_20260401_105556.zip

════════════════════════════════════════════════════════
  ✓ SLICE 8/8 COMPLETE: Email Notifications for Invoice Status
════════════════════════════════════════════════════════

▶ STEP 10 — Integration Check
────────────────────────────────────────────────────────
  Using artifacts dir: fo_harness_runs/invoicetool_s08_email_notifications_for_invoice_status_BLOCK_B_20260401_105556/build/iteration_03_artifacts

Loading artifacts...
  10 file(s) loaded

  Running Check 1: Route inventory...
    → 0 issue(s)
  Running Check 2: Model field refs...
    → 0 issue(s)
  Running Check 3: Spec compliance...
    → 3 issue(s)
  Running Check 4: Import chains...
    → 0 issue(s)
  Running Check 5: Route decorator double-path...
    → 0 issue(s)
  Running Check 6: Auth contract (route auth vs frontend headers)...
    → 0 issue(s)
  Running Check 7: Async misuse (await on non-async functions)...
    → 0 issue(s)
  Running Check 8: asyncio.gather with sync function args...
    → 0 issue(s)
  Running Check 9: npm package integrity (imports vs package.json)...
    → 0 issue(s)
  Running Check 10: Bare except / silent error swallow in services...
    → 0 issue(s)
  Running Check 11: Unbounded polling loops in frontend...
    → 0 issue(s)
  Running Check 12: Background task timeout vs intake SLA...
    → 0 issue(s)
  Running Check 13: Config object rendered as text in JSX...
    → 0 issue(s)
  Running Check 14: Dead buttons (no onClick / placeholder href)...
    → 0 issue(s)
  Running Check 15: Form state fields not in config form definition...
    → 0 issue(s)
  Running Check 16: Hollow service methods (no DB interaction)...
    → 0 issue(s)
  Running Check 17: Orphaned pages (UI with no backend coverage)...
    → 0 issue(s)

  Output written: fo_harness_runs/invoicetool_s08_email_notifications_for_invoice_status_BLOCK_B_20260401_105556/integration_issues.json

============================================================
INTEGRATION CHECK COMPLETE
============================================================
  Total issues: 3  (HIGH: 0  MEDIUM: 3)
  Verdict: INTEGRATION_REJECTED

  Issues found:
    [MEDIUM] INT-SPEC-KPI-MVP (SPEC_COMPLIANCE)
           KPI 'MVP' defined in intake but not referenced anywhere in artifacts
    [MEDIUM] INT-SPEC-KPI-HLD (SPEC_COMPLIANCE)
           KPI 'HLD' defined in intake but not referenced anywhere in artifacts
    [MEDIUM] INT-SPEC-KPI-QA (SPEC_COMPLIANCE)
           KPI 'QA' defined in intake but not referenced anywhere in artifacts

  Fix target files:
    - business/services/ScoringService.py

  Run harness fix pass:
    python fo_test_harness.py <intake> --resume-run <run_dir> --resume-iteration <N> --integration-issues integration_issues.json
============================================================

ℹ Integration issues are MEDIUM-only — skipping fix pass (not worth burning iterations)
✓ Integration check clean.

▶ FINAL STEP — Merging 8 ZIP(s) into final deliverable
────────────────────────────────────────────────────────
  ZIPs to merge (in order):
    fo_harness_runs/invoicetool_s01_manage_users_BLOCK_B_20260401_093633.zip
    fo_harness_runs/invoicetool_s02_configure_settings_BLOCK_B_20260401_094449.zip
    fo_harness_runs/invoicetool_s03_view_all_invoices_BLOCK_B_20260401_101823.zip
    fo_harness_runs/invoicetool_s04_view_invoices_BLOCK_B_20260401_102749.zip
    fo_harness_runs/invoicetool_s05_make_payments_BLOCK_B_20260401_103502.zip
    fo_harness_runs/invoicetool_s06_submit_invoices_BLOCK_B_20260401_104124.zip
    fo_harness_runs/invoicetool_s07_manual_invoice_entry_form_BLOCK_B_20260401_104736.zip
    fo_harness_runs/invoicetool_s08_email_notifications_for_invoice_status_BLOCK_B_20260401_105556.zip

========================================================
  SLICE BUILD COMPLETE

  Slice 1: fo_harness_runs/invoicetool_s01_manage_users_BLOCK_B_20260401_093633.zip
  Slice 2: fo_harness_runs/invoicetool_s02_configure_settings_BLOCK_B_20260401_094449.zip
  Slice 3: fo_harness_runs/invoicetool_s03_view_all_invoices_BLOCK_B_20260401_101823.zip
  Slice 4: fo_harness_runs/invoicetool_s04_view_invoices_BLOCK_B_20260401_102749.zip
  Slice 5: fo_harness_runs/invoicetool_s05_make_payments_BLOCK_B_20260401_103502.zip
  Slice 6: fo_harness_runs/invoicetool_s06_submit_invoices_BLOCK_B_20260401_104124.zip
  Slice 7: fo_harness_runs/invoicetool_s07_manual_invoice_entry_form_BLOCK_B_20260401_104736.zip
  Slice 8: fo_harness_runs/invoicetool_s08_email_notifications_for_invoice_status_BLOCK_B_20260401_105556.zip

  FINAL ZIP : fo_harness_runs/invoicetool.grilled_BLOCK_B_full_20260401_110213.zip  (6.3M)
========================================================

Running final quality check...


══════════════════════════════════════════════════════════════
  CHECK FINAL ZIP
  invoicetool.grilled_BLOCK_B_full_20260401_110213.zip
══════════════════════════════════════════════════════════════

Merging entity artifacts...
  Extracting: invoicetool.grilled_BLOCK_B_full_20260401_110213.zip
  [iteration_04_artifacts] invoicetool_s01_manage_users  →  10 file(s)
  [iteration_04_artifacts] invoicetool_s02_configure_settings  →  10 file(s)
  [iteration_02_artifacts] invoicetool_s03_view_all_invoices  →  10 file(s)
  [iteration_04_artifacts] invoicetool_s04_view_invoices  →  10 file(s)
  [iteration_03_artifacts] invoicetool_s05_make_payments  →  10 file(s)
  [iteration_02_artifacts] invoicetool_s06_submit_invoices  →  10 file(s)
  [iteration_05_artifacts] invoicetool_s07_manual_invoice_entry_form  →  10 file(s)
  [iteration_03_artifacts] invoicetool_s08_email_notifications_for_invoice_status  →  10 file(s)

  Total merged files: 45

──────────────────────────────────────────────────────────────
GATE 1 — STATIC CHECK
──────────────────────────────────────────────────────────────
  RESULT: PASS

──────────────────────────────────────────────────────────────
GATE 2 — INTEGRATION CHECK
──────────────────────────────────────────────────────────────

  Running Check 1: Route inventory...
    → 0 issue(s)
  Running Check 2: Model field refs...
    → 0 issue(s)
  Running Check 3: Spec compliance...
    → 3 issue(s)
  Running Check 4: Import chains...
    → 0 issue(s)
  Running Check 5: Route decorator double-path...
    → 0 issue(s)
  Running Check 6: Auth contract (route auth vs frontend headers)...
    → 0 issue(s)
  Running Check 7: Async misuse (await on non-async functions)...
    → 0 issue(s)
  Running Check 8: asyncio.gather with sync function args...
    → 0 issue(s)
  Running Check 9: npm package integrity (imports vs package.json)...
    → 0 issue(s)
  Running Check 10: Bare except / silent error swallow in services...
    → 0 issue(s)
  Running Check 11: Unbounded polling loops in frontend...
    → 0 issue(s)
  Running Check 12: Background task timeout vs intake SLA...
    → 0 issue(s)
  Running Check 13: Config object rendered as text in JSX...
    → 0 issue(s)
  Running Check 14: Dead buttons (no onClick / placeholder href)...
    → 0 issue(s)
  Running Check 15: Form state fields not in config form definition...
    → 0 issue(s)
  Running Check 16: Hollow service methods (no DB interaction)...
    → 0 issue(s)
  Running Check 17: Orphaned pages (UI with no backend coverage)...
    → 0 issue(s)
  Output written: fo_harness_runs/invoicetool.grilled_BLOCK_B_full_20260401_110213_check.json


============================================================
INTEGRATION CHECK COMPLETE
============================================================
  Total issues: 3  (HIGH: 0  MEDIUM: 3)
  Verdict: INTEGRATION_REJECTED

  Issues found:
    [MEDIUM] INT-SPEC-KPI-MVP (SPEC_COMPLIANCE)
           KPI 'MVP' defined in intake but not referenced anywhere in artifacts
    [MEDIUM] INT-SPEC-KPI-HLD (SPEC_COMPLIANCE)
           KPI 'HLD' defined in intake but not referenced anywhere in artifacts
    [MEDIUM] INT-SPEC-KPI-QA (SPEC_COMPLIANCE)
           KPI 'QA' defined in intake but not referenced anywhere in artifacts

  Fix target files:
    - business/services/ScoringService.py

  Run harness fix pass:
    python fo_test_harness.py <intake> --resume-run <run_dir> --resume-iteration <N> --integration-issues integration_issues.json
============================================================


══════════════════════════════════════════════════════════════
  COMBINED RESULT
══════════════════════════════════════════════════════════════

  Entities merged: 8
    invoicetool_s01_manage_users  (iteration_04_artifacts, 10 files)
    invoicetool_s02_configure_settings  (iteration_04_artifacts, 10 files)
    invoicetool_s03_view_all_invoices  (iteration_02_artifacts, 10 files)
    invoicetool_s04_view_invoices  (iteration_04_artifacts, 10 files)
    invoicetool_s05_make_payments  (iteration_03_artifacts, 10 files)
    invoicetool_s06_submit_invoices  (iteration_02_artifacts, 10 files)
    invoicetool_s07_manual_invoice_entry_form  (iteration_05_artifacts, 10 files)
    invoicetool_s08_email_notifications_for_invoice_status  (iteration_03_artifacts, 10 files)

  Static check     : PASS  (0 defect(s))
  Integration check: INTEGRATION_REJECTED  (HIGH:0  MED:3  Total:3)

  ✗ CHECKS FAILED — review issues above


Next step — deploy:
  python deploy/zip_to_repo.py fo_harness_runs/invoicetool.grilled_BLOCK_B_full_20260401_110213.zip
```
8. Example output (grill-me, from `invoicetool`):
```text
(cd39) Teebus-MacBook-Pro:intake teebuphilip$   ./grill_me.sh intake_runs/invoicetool/invoicetool.json
[Grill‑Me] Iteration 1/5
[Grill‑Me] Provider: chatgpt
[Grill‑Me] Model: gpt-4o-mini
[Grill‑Me] Intake: /Users/teebuphilip/Downloads/FO_TEST_HARNESS/intake/intake_runs/invoicetool/invoicetool.json
[Grill‑Me] Prompt bytes: 8975
[Grill‑Me] Calling AI (review)...
[Grill‑Me] AI call complete in 4.98s
[Grill‑Me] Tokens: in=2229 out=276
[Grill‑Me] Cost: $0.0083 (cumulative: $1.0863)
[Grill‑Me] Cost CSV: /Users/teebuphilip/Downloads/FO_TEST_HARNESS/intake/grill_me_ai_costs.csv
[Grill‑Me] RAW OUTPUT BEGIN
{
  "issues": [
    {
      "severity": "high",
      "area": "feature",
      "question": "What are the two must-have features for the MVP?",
      "risk": "Without clear identification of must-have features, the MVP may lack essential functionality.",
      "suggested_resolution": "Define at least two must-have features for the MVP in block_b.pass_1."
    },
    {
      "severity": "high",
      "area": "roles",
      "question": "Is there a structured roles_permissions object with at least admin and seller roles?",
      "risk": "Lack of defined roles may lead to permission issues during implementation.",
      "suggested_resolution": "Add a structured roles_permissions object in block_b.pass_1."
    },
    {
      "severity": "high",
      "area": "invoice_edge_cases",
      "question": "What are the three invoice edge cases that need to be considered?",
      "risk": "Insufficient edge case coverage may lead to unexpected behavior during invoice processing.",
      "suggested_resolution": "Define at least three invoice edge cases in block_b.pass_1."
    }
  ],
  "patches": [],
  "halt": true,
  "halt_reason": "Critical ambiguities remain regarding must-have features, roles_permissions, and invoice edge cases."
}
[Grill‑Me] RAW OUTPUT END
[Grill‑Me] Report saved: /Users/teebuphilip/Downloads/FO_TEST_HARNESS/intake/intake_runs/invoicetool/invoicetool.grill_report.json
[Grill‑Me] Patched intake saved: /Users/teebuphilip/Downloads/FO_TEST_HARNESS/intake/intake_runs/invoicetool/invoicetool.grilled.json
[Grill‑Me] provide-answers enabled — attempting to auto-fill ambiguities
[Grill‑Me] Provider: chatgpt
[Grill‑Me] Model: gpt-4o-mini
[Grill‑Me] Intake: /Users/teebuphilip/Downloads/FO_TEST_HARNESS/intake/intake_runs/invoicetool/invoicetool.json
[Grill‑Me] Prompt bytes: 9798
[Grill‑Me] Calling AI (answer-fill)...
[Grill‑Me] AI call complete in 7.98s
[Grill‑Me] Tokens: in=2459 out=358
[Grill‑Me] Cost: $0.0097 (cumulative: $1.0960)
[Grill‑Me] Cost CSV: /Users/teebuphilip/Downloads/FO_TEST_HARNESS/intake/grill_me_ai_costs.csv
[Grill‑Me] RAW OUTPUT BEGIN
```json
{
  "hero_answers": {
    "Q1_problem_customer": "Etsy sellers struggle with timely processing of vendor invoices.",
    "Q2_target_user": ["Etsy sellers"],
    "Q3_success_metric": "Reduction in invoice processing time by 50%.",
    "Q4_must_have_features": ["Manual invoice entry form", "Email notifications for invoice status"],
    "Q5_non_goals": ["Automated invoice processing", "Advanced reporting features"],
    "Q6_constraints": {
      "brand_positioning": "Affordable and user-friendly solution for small business owners.",
      "compliance": "none",
      "promise_limits": "Limited to manual processing capabilities.",
      "scale_limits": "Designed for small-scale operations."
    },
    "Q7_data_sources": ["User input for invoices", "Vendor list management"],
    "Q8_integrations": ["Stripe"],
    "Q9_risks": ["Potential delays in invoice processing", "User error in manual entry", "Payment processing failures"],
    "Q10_shipping_preference": "none"
  },
  "supplemental": {
    "payment_integration_details": "Stripe integration for payment processing.",
    "roles_permissions": {
      "admin": {
        "access": "full",
        "capabilities": [
          "manage_users",
          "configure_settings"
        ]
      },
      "seller": {
        "access": "limited",
        "capabilities": [
          "view_invoices",
          "make_payments"
        ]
      }
    },
    "invoice_edge_cases": [
      "Handling duplicate invoices",
      "Processing invoices with missing vendor information",
      "Managing invoices that exceed payment limits"
    ]
  }
}
```
[Grill‑Me] RAW OUTPUT END
[Grill‑Me] Applied hero_answers to block_b
{
  "Q1_problem_customer": "Etsy sellers struggle with timely processing of vendor invoices.",
  "Q2_target_user": [
    "Etsy sellers"
  ],
  "Q3_success_metric": "Reduction in invoice processing time by 50%.",
  "Q4_must_have_features": [
    "Manual invoice entry form",
    "Email notifications for invoice status"
  ],
  "Q5_non_goals": [
    "Automated invoice processing",
    "Advanced reporting features"
  ],
  "Q6_constraints": {
    "brand_positioning": "Affordable and user-friendly solution for small business owners.",
    "compliance": "none",
    "promise_limits": "Limited to manual processing capabilities.",
    "scale_limits": "Designed for small-scale operations."
  },
  "Q7_data_sources": [
    "User input for invoices",
    "Vendor list management"
  ],
  "Q8_integrations": [
    "Stripe"
  ],
  "Q9_risks": [
    "Potential delays in invoice processing",
    "User error in manual entry",
    "Payment processing failures"
  ],
  "Q10_shipping_preference": "none"
}
[Grill‑Me] Patched intake saved: /Users/teebuphilip/Downloads/FO_TEST_HARNESS/intake/intake_runs/invoicetool/invoicetool.grilled.json
[Grill‑Me] Acceptance criteria met — stopping early
============================================================
```
6. Example output (boilerplate fit after grilled intake, from `invoicetool`):
```text
(cd39) Teebus-MacBook-Pro:FO_TEST_HARNESS teebuphilip$ python check_boilerplate_fit.py  /Users/teebuphilip/Downloads/FO_TEST_HARNESS/intake/intake_runs/invoicetool/invoicetool.grilled.json 

======================================================================
BOILERPLATE FIT CHECKER
======================================================================

→ Intake:     /Users/teebuphilip/Downloads/FO_TEST_HARNESS/intake/intake_runs/invoicetool/invoicetool.grilled.json
→ Boilerplate: /Users/teebuphilip/Documents/work/teebu-saas-platform
→ Loading intake JSON...
✓ Loaded intake: invoicetool
→ Reading boilerplate (ZIP or directory)...
✓ Boilerplate manifest built
→ Boilerplate manifest size: 232,307 chars
→ Prompt size: 247,979 bytes
✓ Prompt logged: invoicetool_analysis_prompt.log
→ Calling ChatGPT for analysis...
✓ Analysis complete in 31.0s
→ AI cost: $0.1608 (cumulative: $0.3208)
→ Cost CSV: /Users/teebuphilip/Downloads/FO_TEST_HARNESS/boilerplate_checks/boilerplate_fit_ai_costs.csv
→ Parsing verdict...

======================================================================
BOILERPLATE FIT CHECK — Invoicetool
======================================================================

VERDICT: YES — USE BOILERPLATE
Fit Score: 9/10
Summary:   The business idea fits well with the boilerplate capabilities, with minor adjustments needed for email marketing and analytics integration.

Boilerplate Already Handles:
✓ User authentication via Auth0
✓ Payment processing via Stripe
✓ Basic CRUD operations for invoices
✓ User onboarding flow

Backend Routes to Build (1 files):
  [HIGH] business/backend/routes/vendor_invoices.py → /api/vendor_invoices
         Manage vendor invoices for Etsy sellers

Frontend Pages to Build (1 files):
  [HIGH] business/frontend/pages/VendorInvoices.jsx → /dashboard/vendor-invoices
         Display and manage vendor invoices for Etsy sellers

Ambiguities (1 items):
  [MEDIUM] Email notifications for invoice status
         Missing: Details on what triggers notifications and the content of the emails.
         Ask: Ask the founder what specific events should trigger email notifications and what the email content should include.

Recommendation:
  Proceed with building the backend routes for invoice management and the corresponding frontend pages. Clarify the email notification requirements with the founder to ensure complete functionality.

Output saved: boilerplate_checks/invoicetool_boilerplate_check.json

Next step: Run the test harness with --use-boilerplate
  Pass this file to the harness: boilerplate_checks/invoicetool_boilerplate_check.json
```

**Step 5 — Build + QA**
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

**Step 6 — Deploy**
1. Convert ZIP to repo:
```bash
python deploy/zip_to_repo.py fo_harness_runs/<picked_name>_BLOCK_B_full_<timestamp>.zip
```
2. Deploy:
```bash
python deploy/pipeline_deploy.py --repo ~/Documents/work/<picked_name>
```

**Alternate Entry — Hero JSON → Pre-Intake Outputs**
Use this when you already have Q1–Q11:
```bash
./gap-analysis/run_full_pipeline_from_hero.sh intake/ai_text/<picked_name>.json --verbose
```

**Notes**
1. `--no-ai` disables AI stages (use for deterministic runs).
2. `--force` continues even if Pass0 is HOLD.
3. Outputs are tracked in `gap-analysis/outputs/` and `seo/`.
