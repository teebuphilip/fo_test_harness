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
- **Phase chain:** `run_auto_build.sh` → `planner_router.py` → `run_integration_and_feature_build.sh` → `phase_planner.py` → `generate_feature_spec.py` → `feature_adder.py --spec-file` → `fo_test_harness.py` → `integration_check.py` → merge ZIPs → `check_final_zip.py` (optional)
- **Slice chain:** `run_auto_build.sh` → `planner_router.py` → `run_slicer_and_feature_build.sh` → `slice_planner.py` → `generate_feature_spec.py` → `inject_spec.py` → `fo_test_harness.py` → `integration_check.py` → merge ZIPs → `check_final_zip.py` (optional)

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
