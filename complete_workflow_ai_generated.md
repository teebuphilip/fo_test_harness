**Definitive Guide: Idea → Deploy (AI-Generated Ideas)**

This is the single source of truth for the full pipeline from idea to deploy.

**Step 0 — Source of AI Ideas**
Ideas come from AFH:
- Repo: `https://www.github.com/teebuphilip/AFH`
- Local: `~/Documents/work/AFH` (see its README)

These are AI-generated ideas that still need enrichment and a market gap check.

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
4. Outputs:
```text
intake/intake_runs/<picked_name>/<picked_name>.grill_report.json
intake/intake_runs/<picked_name>/<picked_name>.grilled.json
boilerplate_checks/<picked_name>_boilerplate_check.json
```

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
5. Example output (grill-me, from `invoicetool`):
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
