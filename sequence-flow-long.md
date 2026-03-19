# Sequence Flow (Detailed)

This documents the intake-to-build staging that uses `check_openai.py` and `phase_planner.py`. The intake JSON coming out of `intake/` is the working input for all subsequent steps.

## Stage 0: Intake Output (Starting Point)

Input: a single intake JSON file generated under `intake/` (your working original file).

Requirements:
- JSON must be valid and readable.
- The file path will be passed into the planner as `--intake`.

## Stage 1: API Readiness Check (`check_openai.py`)

Purpose: confirm OpenAI and/or Claude are reachable and return a minimal reply before running a full build/QA cycle.

Command:
- `python check_openai.py`
  - Example: `python check_openai.py`

Variants:
- `python check_openai.py --openai`
- `python check_openai.py --claude`

Behavior:
- Reads `OPENAI_API_KEY` and `ANTHROPIC_API_KEY` from environment.
- Sends a small “Reply with one word: UP” ping.
- Retries on rate limits or timeouts.
- Prints remaining OpenAI request and token quota headers when available.

Exit status:
- `0` if all requested checks pass.
- `1` if any requested check fails.

Notes:
- A successful ping does not guarantee a large QA call will succeed. Token-per-minute limits can still trigger 429s later.

## Stage 2: Phase Planning (`phase_planner.py`)

Purpose: analyze the intake JSON and decide if the build should run in a single phase or split into two phases.

Command:
- `python phase_planner.py --intake <path/to/intake.json>`

Optional flags:
- `--output-dir <dir>` to control where derived files are written.
- `--no-ai` to disable AI classification and use rule-based classification only.
- `--threshold <n>` to adjust the feature count threshold for 2-phase.

What it does:
- Extracts features and KPI definitions from the intake JSON.
- Classifies features into data-layer vs intelligence-layer using keywords.
- Optionally uses Claude to classify ambiguous features if `ANTHROPIC_API_KEY` is present and `--no-ai` is not set.
- Forces 2-phase if certain KPI or analytics signals are present.

Decision rules (summary):
- Force 2-phase if KPI count is high or analytics/scoring signals appear in the intake.
- Otherwise choose 2-phase if intelligence-layer features exist.
- Otherwise choose 2-phase if feature count exceeds the threshold.
- Else run 1-phase.

Outputs:
- Always writes `<stem>_phase_assessment.json` containing:
- `phases` (1 or 2)
- `reason`
- `features` (classification map)
- `data_features`, `intelligence_features`
- `kpis`
- If 2-phase:
- `<stem>_phase1.json` for Phase 1 (data layer only)
- `<stem>_phase2.json` for Phase 2 (intelligence layer)

Phase 1 intake changes:
- Removes intelligence-layer feature entries from feature lists.
- Empties KPI definitions so analytics are deferred.
- Adds `_phase_context` describing scope and what to defer.
- Suffixes `startup_idea_id` with `_p1` when present.

Phase 2 intake changes:
- Retains the full original intake content.
- Adds `_phase_context` describing Phase 1 completion and do-not-regenerate files.
- Suffixes `startup_idea_id` with `_p2` when present.

## Stage 3: Run the Harness (Follow-On)

If 1-phase:
- Use the original intake JSON with the harness.
  - Example: `python ./fo_test_harness.py ./intake/intake_runs/ai_workforce_intelligence/ai_workforce_intelligence.5.json ~/Documents/work/FounderOps/docs/architecture/BUILD/build_rules/FOBUILFINALLOCKED100.zip ~/Documents/work/FounderOps/docs/architecture/BUILD/deployment_rules/fo_deploy_governance_v1_2_CLARIFIED.zip --max-iterations 12`

If 2-phase:
- Run Phase 1 using `<stem>_phase1.json`.
- After Phase 1 is QA-accepted, run Phase 2 using `<stem>_phase2.json`.

The harness run itself is out of scope here, but `phase_planner.py` prints the exact next-step commands after generation.

## Wrapper Scripts (High-Level Guidance)

Preferred wrapper:
- `run_integration_and_feature_build.sh` — end-to-end feature-by-feature pipeline with an integration check → fix → re-check loop before final merge.

No longer used (kept in repo for reference):
- `run_feature_build.sh` — legacy feature-by-feature pipeline without integration loop.
- `run_phased_build.sh` — legacy 2-phase runner and merge.

## Supporting Scripts (Behavior Summary)

- `feature_adder.py`: builds a scoped intake JSON for a single intelligence feature, using the original intake plus a prior manifest/ZIP to constrain scope.
- Example: `python feature_adder.py --intake intake/intake_runs/ai_workforce_intelligence/ai_workforce_intelligence.5.json --manifest fo_harness_runs/ai_workforce_intelligence_narrative_summary_generator_BLOCK_B_20260308_050012.zip --feature "Downloadable executive report" --output intake/intake_runs/ai_workforce_intelligence/ai_workforce_intelligence.5_feature_downloadable_executive_report.json`
- `integration_check.py`: runs deterministic post-build validation across artifacts (routes, model fields, spec compliance, imports), writes `integration_issues.json`, and returns pass/fail.
- Example (ZIP): `python integration_check.py --zip fo_harness_runs/ai_workforce_intelligence_downloadable_executive_report_BLOCK_B_20260308_070302.zip --intake intake/intake_runs/ai_workforce_intelligence/ai_workforce_intelligence.5.json`
