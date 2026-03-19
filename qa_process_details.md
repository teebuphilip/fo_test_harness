# QA Process Details (Gates + Fix Loop)

This document describes the QA process inside `fo_test_harness.py`, including gate order and how defects trigger the next iteration.

## 1. Gate Order (Current)

The harness runs gates in this order every iteration:
1. GATE 0 — Compile (mandatory)
2. GATE 2 — Static checks (mandatory)
3. GATE 3 — AI consistency (mandatory)
4. GATE 4 — Quality (mandatory)
5. GATE 1 — Feature QA (ChatGPT)

Notes:
- Compile and static gates are deterministic, based on file inspection and rules.
- Consistency and quality gates use ChatGPT.
- Feature QA is the final acceptance gate.

## 2. Defect Capture and Fix Triggering

When any gate fails:
- Defects are collected and normalized into a consistent format.
- A defect cap is applied to avoid over-scoping fixes in a single iteration.
- The next iteration is a targeted fix pass focused only on the reported defects.
- The loop continues until QA accepts or `--max-iterations` is reached.

Defect prioritization:
- Severity and runtime impact are prioritized first.
- A maximum number of defects per iteration is enforced to limit churn.

## 3. Gate-Specific Behavior

Compile (Gate 0):
- Runs first and can short-circuit the iteration if compilation fails.
- Failures trigger a fix pass before proceeding to other gates.

Static (Gate 2):
- Deterministic checks (schema, routes, model consistency, etc.).
- Repeated static-only failures are tracked and may allow fall-through to later gates.

AI Consistency (Gate 3):
- Cross-file consistency checks driven by ChatGPT.
- Repeated consistency-only failures are tracked and may allow fall-through.

Quality (Gate 4):
- Evaluates completeness, code quality, enhanceability, and deployability.
- Mandatory and always ON in the current harness.
- Produces defects that are handled as targeted fixes.

Feature QA (Gate 1):
- Full-feature verification against intake requirements.
- Uses the complete artifact set after merge-forward.
- Accepts only when QA report ends with:
- `QA STATUS: ACCEPTED - Ready for deployment`

## 4. Iteration Control

Key controls:
- `--max-iterations N` limits the total number of build+QA cycles.
- If the max is reached while a gate is failing, the harness stops with a reject state.

Resume integration:
- You can inject external defect lists (from `integration_check.py`) using:
- `--integration-issues integration_issues.json`
- This triggers a targeted fix pass on the supplied defect list.

## 5. Post-QA Polish

If all gates pass:
- The harness runs a polish step (README, `.env.example`, tests), unless `--no-polish` is set.
- A final ZIP is generated (or DEPLOY is executed if `--deploy` is set).
