# STEAL REPORT: What to Take, Mapped to Your 3 Problems

## Problem 0: GARBAGE IN → GARBAGE OUT (Upstream)

### Steal 0.1 — Grill-Me Pass on Intake Before Build (from mattpocock/skills + TODO.md)

**What:** Stress-test the intake PRD before spending $5-10 on a build run. A "grill-me" pass asks adversarial questions about the intake spec — vague features, contradictory requirements, missing data model details, unclear integrations — and patches the intake with frozen decisions before build starts.

**Reference:** `mattpocock/skills` (write-a-prd, grill-me, prd-to-plan). Already in TODO.md lines 5-9.

**The flow:**
```
Intake → PRD structuring → Grill-me pass → Patch intake + freeze decisions → Pre-planner → Build
```

**How to apply:** Add a pre-build step (ChatGPT — cheap) that receives the intake JSON and asks:
1. Which features are vague enough that Claude will hallucinate implementation details?
2. Are there contradictions between features (e.g., "simple dashboard" + "real-time analytics")?
3. Are data model relationships explicit or will Claude have to guess?
4. Are external integration requirements (Stripe, auth, email) specific enough?

Output: a list of ambiguities + suggested patches. Auto-apply patches to intake, log originals for audit. If critical ambiguities remain (>3 unresolvable), halt and ask the founder.

**Why this matters:** This is Steal 3.1 (reference-first judging) applied UPSTREAM to the intake. If the intake is vague, no amount of QA gates will produce a good build. Catch it before you burn tokens.

---

## Problem 1: BUILDS NOT CONVERGING

Your builds spiral because: (a) Claude regenerates non-defect files from memory, (b) QA flags the same issue under different labels each iteration, (c) context degrades over long runs, (d) no stagnation detection — you just hit max iterations.

### Steal 1.1 — Circuit Breaker Pattern (from Ralph/UndeadList)

**What:** Formal stagnation detection with three thresholds instead of just a max-iteration cap.

| Threshold | Value | Action |
|-----------|-------|--------|
| No file changes | 3 iterations | Open circuit → stop loop |
| Same error repeating | 5 iterations | Open circuit → stop loop |
| Output size declining >70% | Any iteration | Open circuit → stop loop |

**How to apply:** Add to `execute_build_qa_loop()`. Track per-iteration: files changed set, defect signatures (hash of location+type), total artifact byte count. If any threshold triggers, exit early with diagnostic instead of burning remaining iterations.

### Steal 1.2 — Separate Reflection from Fix (from Reflexion)

**What:** Before Claude generates fix code, force a **separate reflection step** where it explains WHY the previous attempt failed. This reflection becomes a hint for the fix, not the fix itself.

**The prompt pattern:**
```
You will be given your previous implementation and test results.
Write a few sentences explaining WHY your implementation is wrong.
You will need this as a hint when you try again.
Only provide the diagnosis, not the implementation.
```

Then in the fix prompt, inject the reflection as context:

```
[reflection on previous attempt]: {reflection_text}
[improved implementation]:
```

**Impact:** +11 percentage points on HumanEval (80.1→91.0). The key insight: when you skip diagnosis, the LLM pattern-matches on surface symptoms. When forced to diagnose first, it finds root causes.

**How to apply:** Add a `_generate_reflection()` method between QA and BUILD in the fix loop. Call Claude (Haiku — cheap) with the defect report and ask only for diagnosis. Inject that diagnosis into `build_previous_defects.md` before the fix prompt.

### Steal 1.2a — ROOT_CAUSE in Triage (fast-path Reflexion, from TODO.md)

**What:** Instead of adding a separate Haiku reflection call (Steal 1.2), extend the existing `_triage_and_sharpen_defects()` to emit `ROOT_CAUSE: <one sentence>` per defect alongside the existing `CLASSIFICATION` and `SHARPENED_FIX`. Zero additional API calls — just extend the triage prompt output format.

**From TODO.md lines 10-15:**
> Update triage prompt to include `ROOT_CAUSE: <one sentence>` per defect. Trigger: only when QA rejects (current behavior). No new calls; just extend triage output format.

**How to apply:** Update the triage prompt in `fo_test_harness.py` (`_triage_and_sharpen_defects()`) to require:
```
DEFECT-N:
  CLASSIFICATION: <scope|hallucination|real>
  ROOT_CAUSE: <one sentence causal hypothesis — WHY this happened, not WHAT is wrong>
  SHARPENED_FIX: <exact code change>
```

Then inject the `ROOT_CAUSE` into `build_previous_defects.md` alongside the fix. This gives Claude the "why" (Reflexion's key insight) without the cost of a separate call.

**Log output:** Write root-cause notes to `iteration_##_triage_output` for post-run analysis. Over time, recurring root causes become candidates for contrastive rules (Steal 3.7).

**Why this is better than Steal 1.2 for now:** Steal 1.2 (separate Haiku reflection call) is the theoretically cleaner approach, but 1.2a is free — you're already making the triage call. Start with 1.2a in Week 1, evaluate whether it's sufficient. Add 1.2 later only if root-cause quality from triage is too shallow.

### Steal 1.3 — Bound Reflection Memory to 1-3 Past Attempts (from Reflexion)

**What:** Only keep the last 1-3 reflections/defect reports in the fix prompt. More causes context bloat without benefit.

**How to apply:** Your `PREVIOUS_DEFECTS` block currently accumulates. Cap it: keep only the last 2 iterations of defect history. Older defects that keep recurring get a one-line summary, not full evidence blocks.

### Steal 1.4 — Targeted Re-Audit on Modified Files Only (from UndeadList)

**What:** After a fix iteration, re-run QA ONLY on the files Claude actually changed, not the full artifact set. This prevents "new findings on untouched code" that cause oscillation.

**How to apply:** After `ArtifactManager.extract_artifacts()`, compute the diff (which files changed vs previous iteration). Pass only changed files + their direct dependents to QA. Unchanged files get a pass-through.

### Steal 1.5 — Dual-Condition Exit (from Ralph)

**What:** Require BOTH a heuristic signal AND an explicit structured signal to accept a build. Prevents false "ACCEPTED" when ChatGPT says "looks good" but means "I'm tired of reviewing this."

**How to apply:** QA verdict requires: (1) ChatGPT says ACCEPTED, AND (2) zero CRITICAL/HIGH defects in the structured defect list. If ChatGPT says ACCEPTED but lists defects → treat as REJECTED.

### Steal 1.6 — Context Clearing Between Phases (from SDD)

**What:** Clear context between planning and implementation. Planning fills context with analysis artifacts; implementation needs clean context.

**How to apply:** Your phase pipeline already does fresh harness invocations per feature. But within `execute_build_qa_loop()`, the prompt accumulates governance + intake + boilerplate + defects + reflections. Track total prompt token count. If approaching 70% of model context, compact: summarize previous defects instead of including raw reports.

---

## Problem 2: BUILDS ARE POOR QUALITY

Builds are mediocre because: (a) Claude generates "looks like code" not "works as code", (b) no pre-build plan to validate against, (c) build prompt is a wall of text with no priority signal.

### Steal 2.1 — Pre-Execution Planning Injection (from CrewAI + SDD)

**What:** Before calling Claude BUILD, run a planning step that produces a concrete **file manifest + route inventory + model schema**. Then BUILD validates against the plan, and QA validates against the plan (not vague intake).

**SDD's version:** 7-phase planning with specialist agents (researcher, architect, tech lead, QA engineer) each producing structured output, each gated by a judge.

**Minimum viable version for FO:** Before the first BUILD iteration, call Claude (Sonnet — cheaper) with the intake to produce:
```json
{
  "files_to_generate": ["business/backend/routes/clients.py", ...],
  "models": {"Client": ["id", "name", "email", "tenant_id"]},
  "routes": {"/api/clients": ["GET", "POST"], "/api/clients/{id}": ["GET", "PUT"]},
  "frontend_pages": ["ClientDashboard.jsx", "ClientForm.jsx"],
  "external_integrations": ["stripe", "mailerlite"]
}
```

This becomes the **contract**. BUILD must produce these files. QA validates against this contract, not the raw intake.

### Steal 2.2 — De-Sloppify as Separate Pass (from everything-claude-code)

**What:** Rather than adding negative instructions ("don't use hardcoded data", "don't forget auth") which degrade build quality, run a **separate cleanup pass** after the initial build.

**How to apply:** After BUILD iteration 1 produces artifacts, run a lightweight "de-sloppify" pass (Sonnet) that:
- Checks every route has auth
- Checks every model uses proper Base import
- Checks no hardcoded data
- Fixes issues in-place

This is cheaper and more reliable than stuffing anti-patterns into the build prompt.

### Steal 2.3 — Pydantic Output Contracts (from CrewAI)

**What:** Define a schema for what acceptable build output looks like. If output doesn't conform structurally, it fails before QA even runs.

**How to apply:** Define `BuildOutputContract`:
- Every `.py` file must `ast.parse()` successfully
- Every route file must contain `router = APIRouter()`
- Every model file must contain `class X(Base)` or `class X(TenantMixin, Base)`
- Every `.jsx` file must contain `export default`
- `business_config.json` must be valid JSON

You already do some of this in COMPILE/STATIC gates. Formalize it as a hard contract checked before any AI QA runs.

### Steal 2.4 — Model Routing by Task Complexity (from everything-claude-code)

**What:** Use expensive models (Opus) only for hard reasoning tasks. Use cheap models (Haiku/Sonnet) for everything else.

| Task | Model | Why |
|------|-------|-----|
| Initial BUILD | Opus or Sonnet | Full code generation |
| Reflection/diagnosis | Haiku | Just text analysis |
| Fix iteration | Sonnet | Targeted patches |
| QA | GPT-4o (current) | Validation |
| Consistency check | Sonnet (current) | Cross-file analysis |
| De-sloppify pass | Haiku | Mechanical fixes |

### Steal 2.5 — Per-Step Isolation (from SDD)

**What:** "Execute ONLY Step [N]" — each build step dispatched independently. The orchestrator never reads code, only structured reports.

**How to apply:** Your phase pipeline already does this at the feature level. But within a feature build, Claude generates ALL files at once. Consider splitting: (1) generate models first, validate, (2) generate routes, validate against models, (3) generate frontend, validate against routes. Each step has a smaller scope → higher quality per step.

---

## Problem 3: QA MISSING THINGS COMPLETELY

QA misses real bugs because: (a) ChatGPT anchors on whatever Claude produced and rationalizes it, (b) QA prompt is monolithic — one pass for everything, (c) no ground truth to compare against, (d) sycophancy — QA says "ACCEPTED" too easily.

### Steal 3.1 — Reference-First Judging (from SDD) — HIGHEST IMPACT

**What:** Before QA reads Claude's build output, have it independently generate what the **correct output SHOULD look like** based on the intake spec. THEN compare against actual output. This eliminates anchoring bias.

**SDD's exact approach (Stage 2 of Judge):**
> "Generate your own correct solution BEFORE examining the artifact. Identify what the artifact MUST contain, SHOULD contain, and MUST NOT contain."

**How to apply:** Add a pre-QA step. Call ChatGPT with ONLY the intake (not the build output) and ask:
```
Based on this intake spec, list:
1. MUST HAVE: Files, routes, models, and features that MUST exist
2. SHOULD HAVE: Quality attributes (auth on all routes, proper error handling)
3. MUST NOT HAVE: Anti-patterns (hardcoded data, missing auth, Flask patterns)
```

Save this as `reference_spec.json`. Then QA compares build output against this reference, not against vibes.

### Steal 3.2 — Deflationary Scoring + Anti-Sycophancy (from SDD)

**What:** Default QA score = 2/5 ("adequate"). Score of 5.0 = auto-reject as hallucination. The judge prompt includes explicit anti-rationalization instructions:

> "When in doubt, score DOWN. Never give benefit of the doubt."
> "Lenient judges get replaced. Critical judges get trusted."

**Anti-rationalization table in the prompt:**

| Rationalization | Counter |
|----------------|---------|
| "It's mostly good" | "Partially bad = fails" |
| "Minor issues only" | "Issues compound" |
| "It works for the basic case" | "Edge cases are requirements" |

**How to apply:** Add to `qa_prompt.md`:
- Explicit instruction: "Your default verdict is REJECTED. You must find sufficient evidence to UPGRADE to ACCEPTED."
- Flip the burden of proof from "find bugs" to "prove correctness"
- Add the anti-rationalization table

### Steal 3.3 — Non-Overlapping QA Scopes (from UndeadList)

**What:** Instead of one monolithic QA pass, split into focused auditors with explicit scope boundaries. Each auditor declares what it checks and what it does NOT check.

**UndeadList's 11 parallel auditors with scope declarations:**
```
bug-auditor checks: Runtime bugs, error handling gaps
Does NOT check (use security-auditor): SQL injection, XSS, auth

security-auditor checks: SQL injection, XSS, auth
Does NOT check (use bug-auditor): null refs, type errors
```

**How to apply:** Your 5 gates already split by type (COMPILE, STATIC, CONSISTENCY, QUALITY, FEATURE_QA). But FEATURE_QA is still monolithic. Consider splitting it into:
- **Route completeness auditor**: Does every intake feature have a backend route + frontend page?
- **Data integrity auditor**: Do model fields match what routes/services reference?
- **Integration auditor**: Do frontend API calls match backend endpoints?

Each gets a focused prompt instead of one giant QA prompt trying to check everything.

### Steal 3.4 — Mandatory Chain-of-Evidence Before Verdict (from SDD)

**What:** Judge must provide file:line evidence BEFORE the score. Never score first, evidence second.

**SDD's exact sequence:**
1. Find evidence FIRST (quote exact locations)
2. Search actively for what's WRONG (not validating what's right)
3. Explain mapping to rubric level definitions
4. THEN assign score

**How to apply:** Restructure `qa_prompt.md` output format:
```
For each check:
1. EVIDENCE: Quote exact line from build output
2. ANALYSIS: What is wrong and why
3. VERDICT: PASS or FAIL for this specific check
4. [only after all checks] OVERALL VERDICT
```

### Steal 3.5 — Self-Verification Gate on QA Itself (from SDD)

**What:** After QA produces its report, make it answer 5 self-check questions:
1. Did I verify every claim against actual file contents?
2. Did I flag anything not in the artifacts (hallucinated finding)?
3. Did I miss any intake requirement?
4. Are my evidence quotes actually from the build output?
5. Would a different reviewer reach the same conclusion?

If any answer reveals a problem, QA must revise its report.

**How to apply:** Add a second ChatGPT call after QA. Pass the QA report + build output and ask the 5 self-check questions. If inconsistencies found, re-run QA with the self-check as guidance.

### Steal 3.6 — Checklist Penalty Caps (from SDD)

**What:** Essential checklist item fails → cap total score at minimum regardless of other scores. Prevents "95% good" from masking "auth is completely broken."

**How to apply:** Define essential items (auth present, DB layer works, all intake features addressed). If ANY essential item fails, verdict is REJECTED regardless of everything else.

### Steal 3.7 — Contrastive Rule Generation from Failures (from SDD)

**What:** When a systemic bug is found across multiple builds, auto-generate an Incorrect/Correct rule file. Load into every future build prompt.

**How to apply:** You already do this manually (`learnings-from-af-to-fo.md`). Automate it: after a build converges, scan the defect history. Any defect that appeared 3+ times across builds → generate a rule file in `directives/prompts/rules/`. These get auto-loaded into build prompts.

---

## IMPLEMENTATION STATUS (39 days to May 1)

**✅ DONE — Session 17 (2026-03-24):**
1. ✅ run_status.json hardening (precursor — all 11 exit paths)
2. ✅ Circuit breaker (Steal 1.1) — stagnation/oscillation/degradation
3. ✅ ROOT_CAUSE in triage (Steal 1.2a) — zero-cost Reflexion
4. ✅ Bound defect memory to last 2 iterations (Steal 1.3)
5. ✅ Dual-condition exit (Steal 1.5)
6. ✅ Deflationary scoring (Steal 3.2) — three-question gate + severity calibration
7. ✅ Chain-of-evidence (Steal 3.4) — "What breaks" field + harness Check 7
8. ✅ Self-verification gate (Steal 3.5) — QA self-review before output
9. ✅ Contrastive rules (Steal 3.7) — 7 VALID/INVALID example pairs
10. ✅ Grill-me pass (Steal 0.1) — done separately via Codex

**🔲 IN PROGRESS — Session 17 continued (2026-03-25):**
11. 4.1 Feature-level pass/fail state tracking (from Karpathy GAN article)
    - phase_planner.py: emit `acceptance_criteria` + `allowed_files` per feature (slice_planner already does this)
    - fo_test_harness.py: read feature state, map defects to features by file path, track pass/fail across iterations
    - Fix preamble: "Features passing: [X]. Features failing: [Y with reasons]. Fix ONLY failing feature files."
    - Pairs with existing `build_patch_first_file_lock.md` but scopes at feature level, not file level

**🔲 NEXT — after validation builds:**
12. 1.4/3.1 Targeted Re-Audit + Reference-First (collapsed — big change, validate current fixes first)
13. 2.3 Pydantic Output Contracts (big rewrite — hold)

**🔲 LATER (Week 5+):**
14. 2.1 Pre-Build File Manifest Contract (low priority — existing reactive fixes cover it)
15. 2.2 De-Sloppify Pass (needed for AFH production, not harness)
16. 3.3 Non-Overlapping QA Scopes (skipped — overlap is tolerable, dedup at filter level)
17. 1.2 Separate Reflexion call (evaluate after ROOT_CAUSE in triage proves out)

**AFTER 4.1: Run 10+ builds to validate all changes.**

---

## SOURCE REPOS RESEARCHED

| Repo | Status | Value |
|------|--------|-------|
| `hesreallyhim/awesome-claude-code` + UndeadList + Ralph | Excellent | Circuit breaker, parallel auditors, micro-checkpoints, context management |
| `NeoLabHQ/context-engineering-kit` (SDD) | Excellent | Reference-first judging, deflationary scoring, meta-judge/judge separation, per-step isolation |
| `noahshinn/reflexion` | Excellent | Separate reflection from fix, bounded memory, +11pp on HumanEval |
| `affaan-m/everything-claude-code` | Good | De-sloppify pass, model routing, 50% auto-compact, tool budget |
| `crewAIInc/crewAI` | Good | Pydantic contracts, guardrail functions, pre-execution planning, scoped memory |
| `EleutherAI/lm-evaluation-harness` | Good | YAML test specs, pass_at_k code validation, metric registry, seeded reproducibility |
| `appdotbuild/agent` | Dead end | Namespace squatting POC, not a real framework |
