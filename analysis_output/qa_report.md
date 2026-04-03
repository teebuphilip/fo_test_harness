# Harness Run QA Report
Generated: 2026-04-03T20:46:20.474535Z
Runs analyzed: 153

---

## Executive Summary
- Total iterations across all runs: 1146
- Average iterations per idea: 34.73
- Most expensive idea: ai_workforce_intelligence
- Most common failure gate: G2 (98.6%)
- Most common failure reason: Intake KPI 'MVP' has no implementation in any service or route. (seen 6 runs)
- Estimated wasted iterations (false positives): 0 (0.0% of checked)

---

## Top 10 Failure Reasons
1. Intake KPI 'MVP' has no implementation in any service or route. — 6 occurrences
   Gate: G6
   Ideas: invoicetool_s05_make_payments_wire_stripe_payment_processing_using_boi, invoicetool_s08_email_notifications_for_invoice_status, invoicetool_s08_email_notifications_for_invoice_status_wire_mailerlite_email_notifications_usin, wynwood_thoroughbreds_p1, wynwood_thoroughbreds_p1_contentpage
2. The method `getAccessTokenSilently` is not destructured correctly in the incorrect location. However, note that the problem is actually elsewhere, see next defect. — 41 occurrences
   Gate: G2
   Ideas: ai_workforce_intelligence, invoicetool_s05_make_payments, wynwood_thoroughbreds_p1, wynwood_thoroughbreds_p1_member
3. The presence of this compiled file is indicative of unnecessary artifacts in the deployment. — 8 occurrences
   Gate: G2
   Ideas: adversarial_ai_validator_integrate_anthropic_sdk_for_advocate_rol, ai_workforce_intelligence_downloadable_executive_report, wynwood_thoroughbreds_p1
4. Intake KPI 'HLD' has no implementation in any service or route. — 3 occurrences
   Gate: G6
   Ideas: invoicetool_s05_make_payments_wire_stripe_payment_processing_using_boi, invoicetool_s08_email_notifications_for_invoice_status, invoicetool_s08_email_notifications_for_invoice_status_wire_mailerlite_email_notifications_usin
5. The `owner_id` field is incorrectly included in the Assessment model. — 2 occurrences
   Gate: G2
   Ideas: ai_workforce_intelligence_kpi_scoring_engine, ai_workforce_intelligence_narrative_summary_generator
6. `.tsx` or `.ts` frontend files are present instead of .jsx. — 16 occurrences
   Gate: G2
   Ideas: ai_workforce_intelligence
7. The code attempts to use a method that doesn't exist on the user object. — 5 occurrences
   Gate: G2
   Ideas: ai_workforce_intelligence
8. The description is too generic and does not provide a specific overview of the service. — 4 occurrences
   Gate: G2
   Ideas: adversarial_ai_validator_implement_stripe_pay_per_analysis_checko
9. The inclusion of the `status` column implies new functionality not stated in the intake. — 4 occurrences
   Gate: G2
   Ideas: ai_workforce_intelligence
10. The token is retrieved using the wrong method on the user object. — 4 occurrences
   Gate: G2
   Ideas: wynwood_thoroughbreds_p1

## False Positive Analysis
Rate: 0.0% of checked transitions

## Per-Idea Breakdown
### adversarial_ai_validator
- Phase 1: 0 iterations
- Features: 0 (avg 0)
- Total iterations: 78

### adversarial_ai_validator_build_synthesis_engine_for_structured_ve
- Phase 1: 0 iterations
- Features: 0 (avg 0)
- Total iterations: 2

### adversarial_ai_validator_implement_stripe_pay_per_analysis_checko
- Phase 1: 0 iterations
- Features: 0 (avg 0)
- Total iterations: 35

### adversarial_ai_validator_integrate_anthropic_sdk_for_advocate_rol
- Phase 1: 0 iterations
- Features: 0 (avg 0)
- Total iterations: 31

### adversarial_ai_validator_integrate_openai_sdk_for_adversary_role_
- Phase 1: 0 iterations
- Features: 0 (avg 0)
- Total iterations: 23

### adversarial_ai_validator_p1
- Phase 1: 20 iterations
- Features: 0 (avg 0)
- Total iterations: 30

### ai_workforce_intelligence
- Phase 1: 0 iterations
- Features: 0 (avg 0)
- Total iterations: 318

### ai_workforce_intelligence_downloadable_executive_report
- Phase 1: 0 iterations
- Features: 0 (avg 0)
- Total iterations: 117

### ai_workforce_intelligence_kpi_scoring_engine
- Phase 1: 0 iterations
- Features: 0 (avg 0)
- Total iterations: 40

### ai_workforce_intelligence_kpi_scoring_engine_executive_dashboard
- Phase 1: 0 iterations
- Features: 0 (avg 0)
- Total iterations: 48

### ai_workforce_intelligence_narrative_summary_generator
- Phase 1: 0 iterations
- Features: 0 (avg 0)
- Total iterations: 30

### ai_workforce_intelligence_p1
- Phase 1: 17 iterations
- Features: 0 (avg 0)
- Total iterations: 17

### ai_workforce_intelligence_p2
- Phase 1: 0 iterations
- Features: 0 (avg 0)
- Total iterations: 30

### freelance_invoice_tracker
- Phase 1: 0 iterations
- Features: 0 (avg 0)
- Total iterations: 15

### invoicetool_s01_manage_users
- Phase 1: 0 iterations
- Features: 0 (avg 0)
- Total iterations: 4

### invoicetool_s02_configure_settings
- Phase 1: 0 iterations
- Features: 0 (avg 0)
- Total iterations: 4

### invoicetool_s03_view_all_invoices
- Phase 1: 0 iterations
- Features: 0 (avg 0)
- Total iterations: 4

### invoicetool_s04_view_invoices
- Phase 1: 0 iterations
- Features: 0 (avg 0)
- Total iterations: 8

### invoicetool_s05_make_payments
- Phase 1: 0 iterations
- Features: 0 (avg 0)
- Total iterations: 3

### invoicetool_s05_make_payments_wire_stripe_payment_processing_using_boi
- Phase 1: 0 iterations
- Features: 0 (avg 0)
- Total iterations: 2

### invoicetool_s06_submit_invoices
- Phase 1: 0 iterations
- Features: 0 (avg 0)
- Total iterations: 2

### invoicetool_s07_manual_invoice_entry_form
- Phase 1: 0 iterations
- Features: 0 (avg 0)
- Total iterations: 5

### invoicetool_s08_email_notifications_for_invoice_status
- Phase 1: 0 iterations
- Features: 0 (avg 0)
- Total iterations: 3

### invoicetool_s08_email_notifications_for_invoice_status_wire_mailerlite_email_notifications_usin
- Phase 1: 0 iterations
- Features: 0 (avg 0)
- Total iterations: 1

### property_manager_maintenance_scheduler
- Phase 1: 0 iterations
- Features: 0 (avg 0)
- Total iterations: 2

### wynwood_thoroughbreds
- Phase 1: 0 iterations
- Features: 0 (avg 0)
- Total iterations: 173

### wynwood_thoroughbreds_p1
- Phase 1: 20 iterations
- Features: 0 (avg 0)
- Total iterations: 101

### wynwood_thoroughbreds_p1_contactformsubmission
- Phase 1: 1 iterations
- Features: 0 (avg 0)
- Total iterations: 1

### wynwood_thoroughbreds_p1_contentpage
- Phase 1: 3 iterations
- Features: 0 (avg 0)
- Total iterations: 3

### wynwood_thoroughbreds_p1_educationalcontent
- Phase 1: 3 iterations
- Features: 0 (avg 0)
- Total iterations: 3

### wynwood_thoroughbreds_p1_emailsubscriber
- Phase 1: 3 iterations
- Features: 0 (avg 0)
- Total iterations: 3

### wynwood_thoroughbreds_p1_horseprofile
- Phase 1: 4 iterations
- Features: 0 (avg 0)
- Total iterations: 4

### wynwood_thoroughbreds_p1_member
- Phase 1: 6 iterations
- Features: 0 (avg 0)
- Total iterations: 6

