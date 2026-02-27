# FO/AF Munger — HLD v2.0.0 (FINAL)

**Date:** 2026-02-27  
**Goal:** Deterministically transform raw “hero answers” into a canonical, buildable spec input with **no hallucinations**, **auditable changes**, and **business-logic completeness**.

---

## 1. What Munger Does

Munger runs **before** Intake/Build. It:
1. Normalizes input formats (strings/arrays/booleans)
2. Detects missing, ambiguous, and contradictory requirements
3. Applies **safe autopatches** (no guessing)
4. If needed, produces **bounded, deterministic clarification questions** (max 2 loops)
5. Emits a **canonical output object** that downstream steps can consume without inventing missing details

Outputs:
- **PASS**: canonical output is valid and consistent
- **NEEDS_CLARIFICATION**: deterministic questions required
- **REJECTED**: CRITICAL issues remain after 2 clarification loops

---

## 2. Authority Boundary (Non-Negotiable)

- Munger is the authority for:
  - schema validity
  - normalization
  - contradiction detection
  - business-rule completeness
- Any LLM output is **non-authoritative** and must be re-expressed as:
  - structured clarification responses that pass JSON-schema validation
  - patch operations applied by deterministic code

---

## 3. Data Contracts

### 3.1 Input Contract
`MUNGER_INPUT_SCHEMA.json`

### 3.2 Canonical Hero Contract
`HERO_CANONICAL_SCHEMA.json`

Key v2 additions:
- `hero.constraints.economics.pricing` (structured pricing tiers) **supported** (economics may still be a string, but pricing range ambiguity triggers clarification into structured pricing)
- `hero.constraints.quantitative_bounds` (structured min/target/max metrics) **supported**

### 3.3 Output Contract
`MUNGER_OUTPUT_SCHEMA.json`

### 3.4 Patch Contract
All changes are expressed as patches (`PATCH_SCHEMA.json`) and logged in `munger_report.applied_patches`.

---

## 4. Deterministic Pipeline

### Stage 0 — Ingest
Validate against input schema. Invalid input → REJECTED.

### Stage 1 — Normalize (mapping)
Map known keys (Q1..Q11, etc.) into canonical `hero.*` paths.

### Stage 2 — AutoPatch (safe-list only)
Apply `autopatch_rules.v2.0.json` (5 rules):
- AP001 trim strings
- AP002 coerce yes/no booleans
- AP003 split bullets to arrays
- AP004 dedupe arrays
- AP005 normalize integration format

### Stage 3 — Detect
Run `detection_rules.v2.0.json` (includes Claude business logic detection triggers):
- pricing ambiguity (ranges without tiers)
- quantitative ambiguity (ranges without bounds)
- forced-decision ambiguity (OR/AND, conflicting choices)
- architecture contradictions

### Stage 4 — Clarify (max 2 loops)
Use `clarification_templates.v2.0.json`.
- Loop 1: CRITICAL only (max 5)
- Loop 2: remaining CRITICAL + HIGH (max 5)
Each clarification response must validate against the template’s `response_schema`.
Then Munger applies the template’s patch plan.

### Stage 5 — Validate (hard gates)
Run `validation_rules.v2.0.json`:
- canonical JSON schema validity
- pricing tier integrity (sequential, increasing, freemium conversion)
- quantitative bounds integrity (min<=target<=max, range ratio)
- timeline/tier sanity
- architecture consistency

### Stage 6 — Score + Status
Score starts at 100 and subtracts:
- CRITICAL -25
- HIGH -10
- MEDIUM -3
- LOW -1

PASS if `critical_issues==0` and `score>=80`.

---

## 5. Buildability Guarantees

Munger guarantees downstream steps can treat the output as:
- **schema-complete**
- **internally consistent**
- **explicit** where business logic requires exactness (pricing tiers, bounds)

If business logic cannot be made explicit within 2 loops, Munger returns REJECTED rather than letting downstream steps invent details.

---

## 6. Delivered Artifacts (v2.0.0)
- HLD: `HLD_MUNGER_v2.0.0_FINAL.md`
- Schemas: input/output/canonical/patch/clarification envelope
- Control files: autopatch/detection/clarification templates/validation
