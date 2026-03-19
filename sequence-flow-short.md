# Sequence Flow (Short)

Purpose: take the intake JSON (output of the intake step) and decide whether the build runs in one phase or two, with a quick API readiness check first.

1. Confirm intake output exists (from `intake/`). This is the working input JSON you build from.
2. Check API readiness:
- Run `python check_openai.py` to verify OpenAI and Claude endpoints respond and to see rate-limit headroom.
  - Example: `python check_openai.py`
3. Plan phases:
- Run `python phase_planner.py --intake <path/to/intake.json>` to classify features and decide 1-phase vs 2-phase.
4. Use the planner outputs:
- If 1-phase: proceed directly with the harness using the original intake JSON.
- If 2-phase: use the generated `_phase1.json` and `_phase2.json` intakes for separate harness runs.

Notes on scripts:
- `run_integration_and_feature_build.sh` is the preferred end-to-end pipeline wrapper (feature-by-feature + integration check loop).
- `run_feature_build.sh` is no longer used (legacy wrapper without integration loop).
- `run_phased_build.sh` is no longer used (legacy 2-phase runner).
- `feature_adder.py` generates a feature-scoped intake JSON based on an existing intake and a prior ZIP/manifest.
- Example: `python feature_adder.py --intake intake/intake_runs/ai_workforce_intelligence/ai_workforce_intelligence.5.json --manifest fo_harness_runs/ai_workforce_intelligence_narrative_summary_generator_BLOCK_B_20260308_050012.zip --feature "Downloadable executive report" --output intake/intake_runs/ai_workforce_intelligence/ai_workforce_intelligence.5_feature_downloadable_executive_report.json`
- `integration_check.py` runs deterministic post-build checks and writes `integration_issues.json` for fix passes.
- Example: `python integration_check.py --zip fo_harness_runs/ai_workforce_intelligence_downloadable_executive_report_BLOCK_B_20260308_070302.zip --intake intake/intake_runs/ai_workforce_intelligence/ai_workforce_intelligence.5.json`

Key outputs from `phase_planner.py`:
- `<stem>_phase_assessment.json` (always)
- `<stem>_phase1.json` and `<stem>_phase2.json` (only if 2-phase)
