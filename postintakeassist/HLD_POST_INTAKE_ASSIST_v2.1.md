# Post-Intake Assist — HLD v2.1 (FINAL)
**Date:** 2026-02-27

## Goal
Deterministically validate and correct Intake outputs (Block A + Block B) before Build.

## Contracts
- Block A schema: `BLOCK_A_SCHEMA.json`
- Block B schema: `BLOCK_B_SCHEMA.json`
- Approval token: `HERO_APPROVAL_TOKEN_SCHEMA.json`
- Build contract: `BUILD_CONTRACT_SCHEMA.json`
- Output envelope: `POST_INTAKE_ASSIST_OUTPUT_SCHEMA.json`

## Control Files
- Detection rules (31): `post_intake_detection_rules.v2.1.json`
- Validation rules (20): `post_intake_validation_rules.v2.1.json`
- Revision templates (7): `post_intake_revision_templates.v2.1.json`
- Vocabulary: `post_intake_vocabulary.v2.1.json`

## Pipeline
1) Validate Block A/B  
2) Detect issues (30 rules)  
3) Revision loop (max 2) using deterministic templates  
4) Validate gates (20 rules)  
5) Emit `build_contract` for Build/QA consumption  

## Status policy
- REJECTED: pricing drift w/o token, non-goals remaining, or CRITICAL failures after 2 loops
- NEEDS_REVISION: HIGH/MEDIUM issues and loops remain
- PASS: critical_issues==0 and score>=80
