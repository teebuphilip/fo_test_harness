# Munger v2.0 (Standalone)

Deterministic munger that normalizes and validates hero answers **before** intake/build.

## What It Does
- Maps Q1–Q11 into canonical `hero.*`
- Applies safe autopatches (trim, coerce booleans, split bullets, dedupe)
- Detects missing/ambiguous/contradictory inputs
- Validates canonical constraints
- Produces a structured report and optional clarification requests

## Usage
```bash
python munger/munger.py <hero_input.json> --out munger_out.json
```

## AI Fixer (Auto-clarify)
Generates clarification responses automatically and re-runs Munger (max 2 loops).
```bash
python munger/munger_ai_fixer.py <hero_input.json> --out fixer_out.json
```

### AI Fixer Output (Sample)
```json
{
  "fixer_session_id": "fixer_20260227_153012",
  "status": "SUCCESS",
  "loops": 1,
  "clarifications_generated": 2,
  "confidence_avg": 0.95,
  "updated_q1_q11": {
    "Q1_problem_customer": "Property managers waste time tracking maintenance...",
    "Q2_target_user": ["Property managers with 10-50 residential units"],
    "Q3_success_metric": "Within 30 days of launch: 100 user signups",
    "Q4_must_have_features": ["Maintenance task templates", "Owner portal"],
    "Q5_non_goals": ["Tenant screening"],
    "Q6_constraints": {
      "economics": {
        "pricing": {
          "pricing_model": "subscription",
          "billing_frequency": "monthly",
          "tiers": [
            {
              "tier_id": "T1",
              "price_usd": 39,
              "unit_limit": { "unit": "properties", "max": 15 }
            },
            {
              "tier_id": "T2",
              "price_usd": 79,
              "unit_limit": { "unit": "properties", "max": 50 }
            }
          ]
        }
      }
    },
    "Q7_data_sources": ["Pre-built task templates (min 20, target 25, max 30)"],
    "Q8_integrations": ["Stripe"],
    "Q9_risks": ["Job failures causing missed reminders"],
    "Q10_shipping_preference": "Ship v1 as a simple web app first",
    "Q11_architecture": {
      "authentication_required": true,
      "role_based_access": false,
      "multi_tenant": false,
      "persistent_database": true,
      "payments_required": true,
      "subscription_billing": true,
      "dashboard_reporting": true,
      "pdf_generation": false,
      "external_apis": ["Stripe"],
      "background_jobs": true,
      "admin_panel": false,
      "expected_timeline_days": 60,
      "minimum_tier": 3
    }
  },
  "munger_output": {
    "clean_hero_answers": { "..." : "..." },
    "munger_report": { "status": "PASS", "score": 100, "issues": [] }
  }
}
```

### With Clarifications (loop 1 or 2)
```bash
python munger/munger.py <hero_input.json> \
  --clarifications clarifications.json \
  --loop 1 \
  --out munger_out.json
```

## Input Format
Must match `munger/MUNGER_INPUT_SCHEMA.json`:
```json
{
  "startup_idea_id": "example_id",
  "startup_name": "Example Name",
  "startup_description": "One-line description",
  "hero_answers": {
    "Q1_problem_customer": "...",
    "Q2_target_user": ["..."],
    "Q3_success_metric": "...",
    "Q4_must_have_features": ["..."],
    "Q5_non_goals": ["..."],
    "Q6_constraints": { "brand_positioning": "...", "scope": "...", "economics": "...", "build_time": "...", "tech_requirements": "..." },
    "Q7_data_sources": ["..."],
    "Q8_integrations": ["..."],
    "Q9_risks": ["..."],
    "Q10_shipping_preference": "...",
    "Q11_architecture": {
      "authentication_required": true,
      "role_based_access": false,
      "multi_tenant": false,
      "persistent_database": true,
      "payments_required": true,
      "subscription_billing": true,
      "dashboard_reporting": true,
      "pdf_generation": false,
      "external_apis": ["Stripe"],
      "background_jobs": true,
      "admin_panel": false,
      "expected_timeline_days": 60,
      "minimum_tier": 3
    }
  }
}
```

## Clarifications File
List of envelopes (matches `CLARIFICATION_ENVELOPE_SCHEMA.json`):
```json
[
  {
    "template_id": "CT011_architecture",
    "answers": {
      "architecture": {
        "authentication_required": true,
        "role_based_access": false,
        "multi_tenant": false,
        "persistent_database": true,
        "payments_required": true,
        "subscription_billing": true,
        "dashboard_reporting": true,
        "pdf_generation": false,
        "external_apis": ["Stripe"],
        "background_jobs": true,
        "admin_panel": false,
        "expected_timeline_days": 60,
        "minimum_tier": 3
      }
    }
  }
]
```

## Output
Munger output matches `munger/MUNGER_OUTPUT_SCHEMA.json`:
- `clean_hero_answers`: canonical hero object
- `munger_report`: issues, score, status, applied patches, and optional clarifications

## Files
- `munger/munger.py` — executable
- `munger/*_SCHEMA.json` — input/output/canonical/patch/clarification schemas
- `munger/*_rules.v2.0.json` — autopatch, detection, validation rules
- `munger/clarification_templates.v2.0.json` — clarification templates
