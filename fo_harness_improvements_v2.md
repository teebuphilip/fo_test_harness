# FO TEST HARNESS — IMPROVEMENT INSTRUCTIONS
## FOR CLAUDE CODE — DO NOT DEVIATE FROM THESE INSTRUCTIONS

**Five targeted improvements: Prompt Caching | Gate Locking (fixed) | Repair vs Acceptance Mode Split | Artifact Filtering | Integration Checks Before AI Gates**

---

## MANDATORY RULES FOR THIS SESSION

> **STOP. Read these before touching anything.**

- Show diff before applying any change. Wait for confirmation before proceeding to the next change.
- Do NOT refactor, rename, or restructure anything outside the explicit scope below.
- Do NOT modify fo_test_harness.py unless explicitly told to in a specific improvement section.
- Do NOT touch intake/, deploy/, munger/, or any prompt .md files unless explicitly listed.
- After each improvement is implemented and confirmed, update changelog.md with what changed.
- If you are uncertain about scope, STOP and ask. Do not assume.

---

## NOTE (2026-03-28)
Pre-intake gap analysis now lives in `gap-analysis/` and is documented in `gap-analysis/README_DETAILED.md`. It is separate from the harness improvements tracked here.

## NOTE (2026-03-31)
Intake QA tooling was hardened outside this doc: `intake/grill_me.py` now auto-resumes, targets block B only, and enforces Stripe-only + minimal roles/edge cases. `check_boilerplate_fit.py` now uses a slim manifest and logs prompt size with a scoring rubric.

## NOTE (2026-04-01)
Pre-build feature spec generation is now live. `generate_feature_spec.py` runs GPT→Claude spec negotiation before each feature/slice build. Both shell pipelines (`run_integration_and_feature_build.sh`, `run_slicer_and_feature_build.sh`) auto-generate and inject specs. `fo_test_harness.py` `build_prompt()` reads `_phase_context['feature_spec']` and injects it as a non-negotiable build constraint. New file: `inject_spec.py` (standalone injector for slicer pipeline). This reduces ambiguity-driven QA churn by pre-agreeing feature structure before the build loop.

## NOTE (2026-04-02)
Run analysis tooling is now available: `analyze_runs.py` mines `fo_harness_runs/` and QA reports
into summary outputs, and `analyze_by_prefix.sh` runs per-startup summaries under
`analysis_output/by_startup/<startup_id>/`. Gate breakdown falls back to QA + integration signals
when `riaf-logs/` are missing.

## NOTE (2026-03-31)
Munger now runs via `munger/run_munger_full.sh` (deterministic + AI fixer loop) and converges to a PASSed munged hero JSON (`munger/<slug>.munged.json`). This lives outside the harness improvements tracked here.

## CONTEXT — WHY THESE CHANGES

The harness currently runs three AI QA gates on every build iteration regardless of build state. This causes two problems:

- **Cost:** every iteration pays full token cost for CONSISTENCY + QUALITY + FEATURE_QA even on early broken builds
- **Convergence:** Claude receives overlapping defect reports from three AI voices simultaneously, slowing fixes

These five improvements address both problems without changing QA correctness on final acceptance.

---

---

# IMPROVEMENT 1 — PROMPT CACHING ON AI GATE PROMPTS

**Estimated cost reduction: 30-50% on Gates 3, 4, 5. Estimated time: 2-3 hours.**

## What this does

The static rule portions of `build_ai_consistency.md`, `build_quality_gate.md`, and `qa_prompt.md` never change between iterations. Anthropic prompt caching charges 10% of normal cost on cache hits. On a 20-iteration build that is 19 cache hits on ~2000 tokens of static rules per gate. This is the single highest ROI change.

## Where the code lives

File: `fo_test_harness.py`

Look for the functions that construct the API call payload for Gates 3, 4, and 5. They will be building a `messages` array with a user message containing the full prompt text loaded from `.md` files in `directives/prompts/`.

## The change

For each of the three AI gate API calls, split the prompt into two parts:

- **Part 1 — Static rules:** everything from the top of the `.md` file down to the `{{artifact_contents}}` or `{{build_output}}` placeholder. This never changes between iterations.
- **Part 2 — Dynamic content:** the artifact contents, build output, and intake JSON. This changes every iteration.

Apply Anthropic `cache_control` to Part 1.

**BEFORE:**
```python
messages=[{
    "role": "user",
    "content": full_prompt_string
}]
```

**AFTER:**
```python
messages=[{
    "role": "user",
    "content": [
        {
            "type": "text",
            "text": static_rules,
            "cache_control": {"type": "ephemeral"}
        },
        {
            "type": "text",
            "text": dynamic_content
        }
    ]
}]
```

## Exact implementation steps

1. Find the function that calls the Anthropic API for Gate 3 (CONSISTENCY). It will be passing `build_ai_consistency.md` content as the prompt.
2. Extract the static portion — everything above the `artifact_contents` placeholder — into a variable called `static_rules`.
3. Extract the dynamic portion — artifact contents — into a variable called `dynamic_content`.
4. Change the messages content from a plain string to a list with two dicts as shown above.
5. Repeat for Gate 4 (QUALITY) using `build_quality_gate.md`.
6. Repeat for Gate 5 (FEATURE_QA) using `qa_prompt.md`. Note: `qa_prompt.md` has multiple placeholders. The static portion ends at the `INTAKE REQUIREMENTS` section header.
7. Add a comment above each change: `# PROMPT CACHE: static rules cached, dynamic content uncached`

## Verification

After implementing, run one build iteration and check the API response for `cache_read_input_tokens` in the usage field. A non-zero value confirms caching is working.

```python
# Expected in API response usage object:
# cache_creation_input_tokens: N  (first call builds cache)
# cache_read_input_tokens: N      (subsequent calls hit cache)
```

> **WARNING: Do NOT cache the dynamic content sections. Only cache the static rule text.**

> **WARNING: Do NOT apply cache_control to OpenAI (ChatGPT) calls. This change is Anthropic API calls only.**

---

---

# IMPROVEMENT 2 — GATE LOCKING AFTER PASS

**Estimated iteration reduction: 30-40%. Estimated time: 3-4 hours.**

## What this does

Currently all 5 gates re-run on every iteration even if some passed cleanly. Gate 3 CONSISTENCY may pass on iteration 5, then a Gate 4 fix is applied, and Gate 3 runs again on iteration 6 even though nothing it checks was touched. This wastes tokens and can introduce new Gate 3 failures from unrelated code.

Gate locking means: once a gate passes, it stays locked unless the fix for the current iteration explicitly touched files that gate is responsible for.

## Gate file responsibility map

| Gate | Name | Re-run only if fix touched... |
|------|------|-------------------------------|
| Gate 0 | COMPILE | Any .py or .jsx file |
| Gate 1 | STATIC | Any .py file |
| Gate 2 | CONSISTENCY | models/, services/, routes/, schemas/ files |
| Gate 3 | QUALITY | Any business/ file (always re-run in repair mode — see Improvement 3) |
| Gate 4 | FEATURE_QA | Any business/ file |

## Where the code lives

File: `fo_test_harness.py`

Find the main iteration loop. It will have a sequence of gate function calls like `run_compile_gate()`, `run_static_gate()`, `run_consistency_gate()`, `run_quality_gate()`, `run_feature_qa_gate()`. The gate locking logic goes in this loop.

## Data structure to add

Add a `gate_locks` dict to the run state at the start of the iteration loop:

```python
gate_locks = {
    "CONSISTENCY": False,
    "QUALITY": False,
    "FEATURE_QA": False
}
```

## Lock logic

After each gate passes, set its lock to `True`. Before running each gate, check the lock. If locked, check whether the previous fix touched files that gate cares about. If not, skip the gate and log: `GATE [name] LOCKED — skipped, no relevant files changed`.

```python
# Pseudo-logic for CONSISTENCY gate:
if gate_locks['CONSISTENCY']:
    changed = files_changed_in_last_fix()
    relevant = any(f for f in changed if
        'models/' in f or 'services/' in f or
        'routes/' in f or 'schemas/' in f)
    if not relevant:
        log('GATE CONSISTENCY LOCKED — skipped')
        continue  # skip to next gate
```

## files_changed_in_last_fix() function

Implement this helper. It compares the artifact manifest from the current iteration against the previous iteration and returns the list of files that changed OR were deleted. The `artifact_manifest.json` in each iteration directory already contains file checksums — use those.

```python
def files_changed_in_last_fix(current_manifest, prev_manifest):
    changed = []
    # Files modified or added
    for path, checksum in current_manifest.items():
        if prev_manifest.get(path) != checksum:
            changed.append(path)
    # Files deleted — present in prev but missing from current
    for path in prev_manifest:
        if path not in current_manifest:
            changed.append(path)
    return changed
```

> **NOTE: If `files_changed_in_last_fix()` returns an empty list (first iteration, no prior manifest), treat all gates as unlocked.**

## Lock reset rules

**CORRECTED — the original version had a logic bug. Read carefully.**

Locks persist across iterations within the same feature build. They do NOT reset every iteration — if they did, nothing would ever stay locked.

Locks reset ONLY when:
- A new feature starts in `run_integration_and_feature_build.sh`
- Repair mode restarts from the beginning
- Acceptance mode begins

Lock unlock triggers (mid-build):
- If relevant files changed since the gate last passed → unlock that gate so it re-runs
- If relevant files did NOT change → gate stays locked, skip it

```python
# CORRECT lock logic — locks persist, only unlock when relevant files changed
# Initialize once at feature build start, NOT at iteration start
gate_locks = {
    "CONSISTENCY": False,
    "QUALITY": False,
    "FEATURE_QA": False
}

# Each iteration: check lock, unlock if relevant files changed, run or skip
if gate_locks['CONSISTENCY']:
    changed = files_changed_in_last_fix(current_manifest, prev_manifest)
    relevant = any(f for f in changed if
        'models/' in f or 'services/' in f or
        'routes/' in f or 'schemas/' in f)
    if relevant:
        gate_locks['CONSISTENCY'] = False  # unlock — needs re-run
        log('GATE CONSISTENCY UNLOCKED — relevant files changed')
    else:
        log('GATE CONSISTENCY LOCKED — skipped, no relevant files changed')
        # treat as PASS, continue to next gate

# After gate passes: lock it
if consistency_result == 'PASS':
    gate_locks['CONSISTENCY'] = True
```

- Never lock Gate 0 COMPILE or Gate 1 STATIC — these are cheap deterministic checks and must always run
- QUALITY gate locking is controlled by Improvement 3 (repair mode) not by this mechanism

---

---

# IMPROVEMENT 3 — REPAIR MODE vs ACCEPTANCE MODE SPLIT

**Estimated cost reduction: 40-60% on QUALITY gate. Estimated convergence improvement: significant. Estimated time: 3-4 hours.**

## What this does

The QUALITY gate currently runs on every iteration checking completeness, code quality, enhanceability, and deployability. Most dimensions are irrelevant during repair cycles when the build is structurally broken. Enhanceability and deployability are useless to check when code has not yet passed CONSISTENCY or FEATURE_QA.

The split: during repair iterations the harness runs REPAIR MODE which skips QUALITY entirely and uses a stripped FEATURE_QA gate. Only on the final candidate does it run ACCEPTANCE MODE with full QUALITY.

## The two modes

| | REPAIR MODE (iterations 1 to N-1) | ACCEPTANCE MODE (final candidate only) |
|---|---|---|
| Gate 0 | COMPILE — always run | COMPILE — always run |
| Gate 1 | STATIC — always run | STATIC — always run |
| Gate 2 | CONSISTENCY — run (lockable) | CONSISTENCY — always run |
| Gate 3 | QUALITY — **SKIP** | QUALITY — always run (full 4 dimensions) |
| Gate 4 | FEATURE_QA — run with repair rules (lockable) | FEATURE_QA — run with full rules |

Note: `slice_planner.py` supports `--extra-repair` to allow one bounded additional AI repair pass before strict validation (no infinite loops).

## How to determine mode

Add an `acceptance_threshold` parameter that defaults to `max_iterations - 2`. Any iteration below the threshold is REPAIR MODE. The last 2 iterations are ACCEPTANCE MODE.

```python
# In fo_test_harness.py run() method:
acceptance_threshold = self.max_iterations - 2
mode = 'acceptance' if iteration >= acceptance_threshold else 'repair'
```

Also trigger ACCEPTANCE MODE early if ALL of these are true:
- Gate 0 COMPILE passed
- Gate 1 STATIC passed
- Gate 2 CONSISTENCY passed
- Gate 4 FEATURE_QA passed with zero HIGH defects

```python
def should_run_acceptance_mode(gate_results):
    return (
        gate_results['COMPILE'] == 'PASS' and
        gate_results['STATIC'] == 'PASS' and
        gate_results['CONSISTENCY'] == 'PASS' and
        gate_results['FEATURE_QA_HIGH_COUNT'] == 0
    )
```

## QUALITY gate in REPAIR MODE

Do not call the QUALITY gate API at all in REPAIR MODE. Log: `QUALITY GATE SKIPPED — repair mode, iteration N of M`.

This is not a pass — it is a deliberate skip. The build cannot be accepted without QUALITY passing in ACCEPTANCE MODE.

> **WARNING: Do NOT mark a build as accepted if QUALITY was only ever skipped. The acceptance check must verify QUALITY was explicitly run and passed.**

## FEATURE_QA prompt in REPAIR MODE

In REPAIR MODE, pass the repair rules as a system message, NOT as inline text prepended to the user prompt. Prepending inline can break the prompt's instruction hierarchy and cause the LLM to ignore it.

**CORRECT approach — system message:**
```python
if mode == 'repair':
    messages = [
        {
            "role": "system",
            "content": REPAIR_MODE_RULES  # see block below
        },
        {
            "role": "user",
            "content": qa_prompt  # full qa_prompt.md with dynamic content
        }
    ]
else:  # acceptance mode
    messages = [
        {
            "role": "user",
            "content": qa_prompt  # full qa_prompt.md, no system override
        }
    ]
```

**REPAIR_MODE_RULES constant to add to fo_test_harness.py:**
```
REPAIR MODE INSTRUCTIONS:
This is a repair iteration, not a final acceptance check.
Focus ONLY on:
  - IMPLEMENTATION_BUG defects
  - SPEC_COMPLIANCE_ISSUE defects for missing required features
  - HIGH and MEDIUM severity only

DO NOT flag in repair mode:
  - Enhanceability issues
  - Deployability issues (unless they cause a runtime crash)
  - Code quality style issues
  - LOW severity defects
  - SCOPE_CHANGE_REQUEST unless it is causing a CONSISTENCY failure
```

In ACCEPTANCE MODE use no system message and run the full `qa_prompt.md` as-is.

> **WARNING: Do NOT prepend repair rules inline into the user content. Always use the system role for repair mode instructions.**

## Updated acceptance check

A build is only eligible for acceptance when ALL of the following are true:

- COMPILE: PASS
- STATIC: PASS
- CONSISTENCY: PASS
- QUALITY: PASS — **must have run in ACCEPTANCE MODE, skips do not count**
- FEATURE_QA: `QA STATUS: ACCEPTED`

Update the acceptance check in `fo_test_harness.py` to enforce the QUALITY-was-run requirement explicitly.

## New stop conditions to add

These do not exist yet. Add them to the iteration loop.

| Condition | Action | Log message |
|-----------|--------|-------------|
| Same defect ID in same file for 2 consecutive iterations | Switch to surgical patch mode — send only offending file(s) + exact defect(s) | `CONVERGENCE: recurring defect detected — switching to surgical patch` |
| Same root cause type repeats 3 times across any iterations | Stop loop, output NON_CONVERGING status with root cause classification | `CONVERGENCE FAILURE: root cause [type] repeated 3 times — manual intervention required` |
| All remaining defects are LOW severity only in REPAIR MODE | Force switch to ACCEPTANCE MODE early | `REPAIR COMPLETE: only LOW defects remain — switching to acceptance mode` |

> **WARNING: The NON_CONVERGING outcome must be written to build_state.json with the repeated defect pattern details so the operator can diagnose the root cause.**

---

---

# IMPROVEMENT 4 — ARTIFACT FILTERING PER GATE

**Estimated cost reduction: 40-60% on Gates 3 and 4. Estimated time: 2-3 hours.**

## What this does

Currently all AI gates receive `{{artifact_contents}}` — the full codebase. Gate 3 CONSISTENCY only needs backend files to check model/service/route/schema alignment. It does not need frontend pages, READMEs, or config. Sending the full artifact set to every gate wastes tokens on content that gate cannot act on.

## File sets per gate

| Gate | Needs | Does NOT need |
|------|-------|---------------|
| Gate 2 CONSISTENCY | `models/`, `services/`, `routes/`, `schemas/` | frontend/, README, config, package.json |
| Gate 3 QUALITY | All `business/` files | README-INTEGRATION.md, .env.example, .gitignore |
| Gate 4 FEATURE_QA | All `business/` files | README-INTEGRATION.md, .env.example, .gitignore |

## Where the code lives

File: `fo_test_harness.py`

Find where `artifact_contents` is assembled before being injected into the gate prompts. It will be building a string by reading files from the artifacts directory.

## The change

Add a filter function that takes the full artifact list and returns only the files relevant for a given gate:

```python
GATE_FILE_FILTERS = {
    "CONSISTENCY": [
        "business/models/",
        "business/services/",
        "business/routes/",
        "business/schemas/"
    ],
    "QUALITY": ["business/"],
    "FEATURE_QA": ["business/"],
}

GATE_FILE_EXCLUDES = {
    "CONSISTENCY": [],
    "QUALITY": [
        "business/README-INTEGRATION.md",
        ".env.example",
        ".gitignore"
    ],
    "FEATURE_QA": [
        "business/README-INTEGRATION.md",
        ".env.example",
        ".gitignore"
    ]
}

def filter_artifacts_for_gate(all_artifacts, gate_name):
    """
    Returns only the artifact files relevant to the given gate.
    all_artifacts: dict of {filepath: content}
    gate_name: "CONSISTENCY" | "QUALITY" | "FEATURE_QA"
    """
    includes = GATE_FILE_FILTERS.get(gate_name, [])
    excludes = GATE_FILE_EXCLUDES.get(gate_name, [])
    filtered = {}
    for path, content in all_artifacts.items():
        if any(path.startswith(inc) for inc in includes):
            if not any(path == exc or path.endswith(exc) for exc in excludes):
                filtered[path] = content
    return filtered
```

## Implementation steps

1. Find the artifact assembly code — where `artifact_contents` string is built from the artifacts directory.
2. Add the `GATE_FILE_FILTERS` and `GATE_FILE_EXCLUDES` constants to `fo_test_harness.py`.
3. Add the `filter_artifacts_for_gate()` function.
4. Before each AI gate call, call `filter_artifacts_for_gate()` with the appropriate gate name.
5. Pass the filtered artifact set to that gate's prompt instead of the full set.
6. Log the token reduction: `GATE [name]: sending N files (filtered from M total)`

> **WARNING: Do NOT filter artifact contents for Gate 0 COMPILE or Gate 1 STATIC — those are deterministic and use their own file access logic.**

> **WARNING: If the filtered set for CONSISTENCY is empty (no models/services/routes/schemas files exist yet), pass the full artifact set and log a warning.**

## Verification

After implementing, compare token counts per gate before and after. CONSISTENCY should show the largest reduction — typically 50-70% fewer tokens if the build has significant frontend code.

---

---

# IMPROVEMENT 5 — MOVE INTEGRATION CHECKS BEFORE AI GATES

**Estimated cost reduction: variable but high on builds with structural failures. Estimated time: 2-3 hours.**

## What this does

Currently `integration_check.py` runs POST-BUILD — after the full iteration loop exits. This means AI gates run on structurally broken code for multiple iterations before the deterministic integration check catches the failure.

Integration check catches 15 classes of structural bugs cheaply and deterministically:
- Route/endpoint mismatches
- Model field reference errors
- Auth contract violations
- Async misuse
- Dead buttons
- Form state mismatches

These are cheap to catch deterministically. Letting AI gates run on code with these failures wastes tokens generating defect reports for problems a script could have caught for free.

## The change

Move a lightweight integration pre-check to run BEFORE Gate 2 CONSISTENCY on every iteration inside the build loop. This is distinct from the full post-build integration check which remains in place.

## Where the code lives

Files: `fo_test_harness.py`, `integration_check.py`

Find the main iteration loop gate sequence. Add a new gate before CONSISTENCY.

## New gate sequence

```
Gate 0: COMPILE          (deterministic — existing)
Gate 1: STATIC           (deterministic — existing)
Gate 1.5: INTEGRATION_FAST  (deterministic — NEW, runs subset of integration_check.py)
Gate 2: CONSISTENCY      (AI — existing, lockable)
Gate 3: QUALITY          (AI — existing, repair/acceptance split)
Gate 4: FEATURE_QA       (AI — existing, repair/acceptance split)
```

## What INTEGRATION_FAST checks

Do NOT run all 15 checks — that is expensive and slow. Run only the checks that produce AI-wasted iterations when missed:

| Check # | Check name | Why run early |
|---------|-----------|---------------|
| 1 | Route inventory | Frontend fetch() vs backend routes — if mismatched AI gates produce useless defects |
| 2 | Model field refs | Service model.field vs Column definitions — breaks every AI gate that reads services |
| 4 | Import chains | Broken imports fail at runtime — AI gates can't catch these reliably |
| 6 | Auth contract | Unauthenticated routes vs frontend auth headers — structural, not code quality |
| 7 | Async misuse | await on sync functions — deterministic, AI often misses these |

Checks 3, 5, 8-15 remain in the post-build full integration check only.

## Implementation steps

1. Add a new function `run_integration_fast_gate()` in `fo_test_harness.py`.
2. This function calls `integration_check.py` with a `--fast` flag (add this flag to `integration_check.py`) that runs only checks 1, 2, 4, 6, 7.
3. Add `--fast` mode to `integration_check.py` that accepts a subset check list parameter.
4. Insert `run_integration_fast_gate()` call in the iteration loop between STATIC and CONSISTENCY.
5. If INTEGRATION_FAST fails: route directly to Claude fix with the integration issues file, skip AI gates entirely for this iteration. Log: `INTEGRATION_FAST FAILED — skipping AI gates, routing to structural fix`.
6. If INTEGRATION_FAST passes: continue to Gate 2 CONSISTENCY as normal.

```python
# In iteration loop, between STATIC and CONSISTENCY:
integration_fast_result = run_integration_fast_gate(artifacts_dir, intake_json)
if integration_fast_result.has_issues:
    log('INTEGRATION_FAST FAILED — skipping AI gates this iteration')
    # Route to targeted structural fix — do not run CONSISTENCY, QUALITY, FEATURE_QA
    apply_integration_fix(integration_fast_result.issues_file)
    continue  # next iteration
```

> **WARNING: Only add `--fast` flag to `integration_check.py`. Do NOT modify any existing check logic in that file. The full 15-check run must remain unchanged.**

> **WARNING: The post-build full integration check in `run_integration_and_feature_build.sh` must remain in place. INTEGRATION_FAST is an early-exit optimization, not a replacement.**

## Verification

After implementing, run a build that you know has integration issues and confirm:
- INTEGRATION_FAST fires and logs correctly
- AI gates are skipped for that iteration
- The structural fix is applied
- Next iteration INTEGRATION_FAST passes and AI gates run normally

---

---

# IMPLEMENTATION ORDER

Implement in this exact order. Do not combine steps. Confirm each before starting the next.

1. Implement Improvement 1 (prompt caching) — Gates 3, 4, 5 Anthropic calls only
2. Verify caching is working via `cache_read_input_tokens` in API response
3. Implement Improvement 2 (gate locking) — add `gate_locks` dict, `files_changed_in_last_fix()` with deleted file detection, correct persist-across-iterations logic
4. Test gate locking with a dry run — confirm LOCKED and UNLOCKED log messages appear correctly
5. Implement Improvement 3 part A — repair vs acceptance mode split, QUALITY gate skip in repair mode
6. Implement Improvement 3 part B — repair mode system message for FEATURE_QA (NOT inline prepend)
7. Implement Improvement 3 part C — new stop conditions and convergence breakers
8. Update acceptance check to require QUALITY was explicitly run in ACCEPTANCE MODE
9. Implement Improvement 4 (artifact filtering) — add filter function and apply per gate
10. Implement Improvement 5 part A — add `--fast` flag to `integration_check.py` for checks 1, 2, 4, 6, 7 only
11. Implement Improvement 5 part B — add `run_integration_fast_gate()` to `fo_test_harness.py` and insert in iteration loop
12. Run one full build end to end and confirm all verification items below
13. Update changelog.md with all changes

---

# FILES PERMITTED TO MODIFY

Only these files. Nothing else.

- `fo_test_harness.py` — all five improvements
- `integration_check.py` — Improvement 5 only: add `--fast` flag and subset check mode. Do NOT modify any existing check logic.
- `changelog.md` — update after implementation

**Explicitly off limits for this session:**

- `run_integration_and_feature_build.sh`
- `add_feature.sh`
- `phase_planner.py`
- `feature_adder.py`
- `deploy/` — any file
- `intake/` — any file
- `munger/` — any file
- `directives/prompts/*.md` — do NOT modify prompt files

---

# VERIFICATION CHECKLIST

Before closing this session confirm all of the following:

- [ ] `cache_read_input_tokens` appears in API response after first iteration
- [ ] `GATE [name] LOCKED` log message appears when gate is skipped
- [ ] `GATE [name] UNLOCKED` log message appears when relevant files changed
- [ ] Gate locks persist across iterations — they do NOT reset every iteration
- [ ] `QUALITY GATE SKIPPED — repair mode` log appears on iterations below acceptance threshold
- [ ] REPAIR MODE system message appears in FEATURE_QA API call during repair iterations (NOT inline prepend)
- [ ] NON_CONVERGING outcome writes correctly to `build_state.json`
- [ ] A build cannot be marked accepted without QUALITY having explicitly run and passed
- [ ] Gate 2 CONSISTENCY receives filtered artifacts (models/services/routes/schemas only)
- [ ] `GATE CONSISTENCY: sending N files (filtered from M total)` log appears
- [ ] `INTEGRATION_FAST FAILED — skipping AI gates` log appears when fast checks fail
- [ ] AI gates are skipped when INTEGRATION_FAST fails
- [ ] Post-build full integration check still runs unchanged via `run_integration_and_feature_build.sh`
- [ ] `changelog.md` updated

> **If any verification item fails, fix it before closing the session. Do not defer.**
