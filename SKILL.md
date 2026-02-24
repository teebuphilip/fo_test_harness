# Skill: FO Test Harness Operator

## Purpose
Operate the FO Test Harness pipeline end to end: intake generation, build/QA loop,
artifact review, and boilerplate fit checks.

## When To Use
- Running or debugging the BUILD → QA loop.
- Generating intake JSON from founder answers.
- Producing or reviewing run outputs and logs.
- Checking boilerplate fit for a given intake.

## Prerequisites
- Python 3.8+
- Environment variables:
  - `ANTHROPIC_API_KEY`
  - `OPENAI_API_KEY`
- Governance ZIPs available locally for `--build-gov` (and optional deploy).
- Boilerplate available at `~/Downloads/teebu-saas-platform` if using `--tech-stack lowcode`.

## Inputs
- Hero JSON: `intake/hero_text/<startup>.json`
- Intake JSON: `intake/intake_runs/<startup>/<startup>.json`
- Governance ZIP: e.g. `/tmp/fobuilgov100` (unzipped or zip path as required)

## Outputs
- Run directory: `fo_harness_runs/<startup>_BLOCK_<X>_<timestamp>/`
- Run ZIP: `fo_harness_runs/<startup>_BLOCK_<X>_<timestamp>.zip`
- QA reports: `fo_harness_runs/.../qa/`
- Build artifacts: `fo_harness_runs/.../build/iteration_*_artifacts/`

## Procedure
1. Generate intake (if needed):
```bash
cd intake
./generate_intake.sh hero_text/<startup>.json
```

2. Run the harness:
```bash
python fo_test_harness.py \
  --intake intake/intake_runs/<startup>/<startup>.json \
  --startup-id <startup> \
  --block B \
  --build-gov /tmp/fobuilgov100 \
  --tech-stack lowcode
```

3. Review outputs:
```bash
ls fo_harness_runs/<startup>_BLOCK_B_*/
cat fo_harness_runs/<startup>_BLOCK_B_*/qa/iteration_*_qa_report.txt
```

4. Optional boilerplate fit check:
```bash
./check_boilerplate_fit.py intake/intake_runs/<startup>/<startup>.json /path/to/teebu-saas-platform.zip
```

## Guardrails
- Do not edit or delete existing run artifacts unless explicitly requested.
- Do not commit or display API keys.
- If BUILD output is truncated, check `build_state.json` and rerun with fixes.
