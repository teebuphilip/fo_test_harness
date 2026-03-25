# FO Test Harness Details

This document expands how `fo_test_harness.py` works internally and how to operate advanced flows.

## 1. AI Call Flow (Send + Retrieve)

High-level flow:
- Build calls go to Claude (builder).
- QA calls go to ChatGPT (validator).
- Responses are parsed for completeness, truncation, and markers before moving to the next step.

Key behaviors:
- Claude build calls use the governance ZIPs + intake JSON as the main prompt context.
- Output is expected to include explicit build state markers (e.g., `BUILD STATE: COMPLETED_CLOSED`).
- Truncation detection is applied; if output is incomplete, continuation calls are triggered up to the configured limits.
- QA calls use ChatGPT to review the artifacts against the intake and produce structured defects.
- Integration issues can be injected into the fix loop with `--integration-issues`.

Relevant CLI options:
- `--buildzip` / `--deployzip` to override governance ZIPs.
- `--max-parts`, `--max-continuations` to control continuation behavior.
- `--qa-wait` to add delay between QA calls.

## 2. QA Cycle (5 Gates + Fix Triggering)

The QA pipeline runs multiple gates in a fixed order. Current order:
1. `GATE 0` — compile
2. `GATE 2` — static
3. `GATE 3` — AI consistency
4. `GATE 4` — quality (mandatory)
5. `GATE 1` — feature QA

Fix triggering:
- When QA reports defects, the harness prepares a targeted fix pass.
- Each fix iteration is scope-limited (defect cap) to reduce churn.
- The next iteration is a fix build that applies only the listed defects.
- The loop continues until QA accepts or max iterations are hit.

Key flags:
- `--max-iterations N` controls the QA loop cap.
- `--resume-mode fix` loads a specific iteration’s QA defects and starts a fix pass.

## 3. Resuming Builds at a Specific Iteration

Resume flows use an existing run directory and iteration number:

- `--resume-run <run_dir>`: reuse an existing run dir (no new run created)
- `--resume-iteration N`: pick which iteration to resume from
- `--resume-mode`:
  - `qa` — run QA on existing artifacts (no new build for that iteration)
  - `fix` — load QA defects from `--resume-iteration` and start fixes at iter+1
  - `static` — run static + AI consistency checks (skip full build)
  - `consistency` — run AI consistency only

Default behavior:
- If `--resume-run` is set without `--resume-mode`, the harness defaults to `qa`.

Example (resume QA at iteration 15):

```bash
python fo_test_harness.py \
  intake/intake_runs/ai_workforce_intelligence/ai_workforce_intelligence.5_phase2.json \
  /Users/teebuphilip/Documents/work/FounderOps/docs/architecture/BUILD/build_rules/FOBUILFINALLOCKED100.zip \
  /Users/teebuphilip/Documents/work/FounderOps/docs/architecture/BUILD/deployment_rules/fo_deploy_governance_v1_2_CLARIFIED.zip \
  --resume-run fo_harness_runs/ai_workforce_intelligence_p2_BLOCK_B_20260307_072650 \
  --resume-iteration 15 \
  --resume-mode qa
```

## 4. Layering Features on Top of a Working ZIP

Recommended flow:
1. Start with a QA‑accepted Phase 1 (data layer) ZIP/run.
2. For each intelligence feature:
   - Generate a scoped intake with `feature_adder.py` using the latest ZIP as the manifest.
   - Run `fo_test_harness.py` with `--prior-run` pointing to the last accepted run.
   - Skip polish on intermediate features with `--no-polish` and enable polish on the last feature.
3. Merge all ZIPs after the final feature pass.

Example (from history):

## 5. Slice Pipeline (Quality Mode)

The slice pipeline breaks the build into end-to-end vertical slices and chains them via `--prior-run`.

Entry points:
- `run_slicer_and_feature_build.sh` — runs `slice_planner.py`, builds each slice intake in order, then runs integration check + ZIP merge.
- `run_auto_build.sh` — auto-routes to slice vs phase pipeline using `planner_router.py` (`--force slice|phase` override).
- `slice_planner.py` supports `--extra-repair` for one bounded additional repair pass before strict validation.


```bash
python feature_adder.py \
  --intake intake/intake_runs/ai_workforce_intelligence/ai_workforce_intelligence.5.json \
  --manifest fo_harness_runs/ai_workforce_intelligence_narrative_summary_generator_BLOCK_B_20260308_050012.zip \
  --feature "Downloadable executive report" \
  --output intake/intake_runs/ai_workforce_intelligence/ai_workforce_intelligence.5_feature_downloadable_executive_report.json
```

```bash
python fo_test_harness.py \
  intake/intake_runs/ai_workforce_intelligence/ai_workforce_intelligence.5_feature_downloadable_executive_report.json \
  /Users/teebuphilip/Documents/work/FounderOps/docs/architecture/BUILD/build_rules/FOBUILFINALLOCKED100.zip \
  /Users/teebuphilip/Documents/work/FounderOps/docs/architecture/BUILD/deployment_rules/fo_deploy_governance_v1_2_CLARIFIED.zip \
  --prior-run fo_harness_runs/ai_workforce_intelligence_narrative_summary_generator_BLOCK_B_20260308_050012 \
  --max-iterations 30 \
  --no-polish
```

Optional integration fix loop:
- Run `integration_check.py` on the latest ZIP.
- Pass `--integration-issues integration_issues.json` into a resume fix pass.
- Re-run `integration_check.py` to confirm clean.
