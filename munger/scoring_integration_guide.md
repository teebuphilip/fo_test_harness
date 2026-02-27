# Spec Quality Scoring Algorithm - Integration Guide

## Overview

The Spec Quality Scorer evaluates Q1-Q11 startup specs on a **100-point scale** across 5 categories:

| Category | Points | What It Measures |
|----------|--------|------------------|
| **Completeness** | /30 | Are all required fields present and non-empty? |
| **Consistency** | /25 | Do fields align with each other (Q4↔Q11, Q8↔Q11)? |
| **Specificity** | /20 | Are specs concrete or vague? |
| **Business Intelligence** | /15 | Risks, competition, market insights |
| **Technical Depth** | /10 | Architecture, tech stack, deployment plan |
| **TOTAL** | **/100** | Overall spec quality |

---

## Quick Start

### Installation

```bash
# Copy the scorer to your project
cp spec_quality_scorer.py /path/to/your/project/
```

### Basic Usage

```python
from spec_quality_scorer import SpecQualityScorer, compare_specs

# Load your spec
hero_answers = {
    "Q1_problem_customer": "...",
    "Q2_target_user": [...],
    # ... Q3-Q11
}

# Score it
scorer = SpecQualityScorer()
score = scorer.score_spec(hero_answers)

print(f"Total Score: {score.total}/100")
print(f"Completeness: {score.completeness}/30")
print(f"Consistency: {score.consistency}/25")
```

---

## Integration with AI Fixer

### Use Case: Measure AI Fixer Impact

```python
from spec_quality_scorer import compare_specs

# Before AI Fixer
original_spec = load_original_q1_q11()

# After AI Fixer
fixed_spec = ai_fixer.fix(original_spec)

# Compare
comparison = compare_specs(original_spec, fixed_spec)

print(f"Original: {comparison['original_score'].total}/100")
print(f"Fixed: {comparison['fixed_score'].total}/100")
print(f"Delta: {comparison['delta']:+d}")
print(f"Verdict: {comparison['verdict']}")

# Only apply fix if it improves score
if comparison['delta'] > 0:
    save_spec(fixed_spec)
    print("✅ AI fix improved quality - saved")
else:
    save_spec(original_spec)
    print("❌ AI fix degraded quality - reverted to original")
```

---

## Integration with Munger

### Use Case: Pre/Post Munger Quality

```python
from spec_quality_scorer import SpecQualityScorer

scorer = SpecQualityScorer()

# Before Munger
raw_input = load_raw_hero_answers()
pre_score = scorer.score_spec(raw_input)

# Run Munger
munger_output = munger.validate(raw_input)

if munger_output['status'] == 'PASS':
    # After Munger
    canonical = munger_output['canonical_hero']
    post_score = scorer.score_spec(canonical)
    
    print(f"Quality improvement: {post_score.total - pre_score.total:+d} points")
```

---

## Score Interpretation

### Score Ranges

| Score | Grade | Interpretation | Action |
|-------|-------|----------------|--------|
| **90-100** | A | Excellent spec | ✅ Ready for intake |
| **80-89** | B | Good spec with minor gaps | ⚠️ Proceed with caution |
| **70-79** | C | Acceptable but needs work | 🔧 Fix critical issues |
| **60-69** | D | Poor spec with major gaps | ❌ Reject or major rework |
| **<60** | F | Incomplete/unusable | ❌ Reject |

### Example Scores

**Property Manager (Original):** 85/100 (Grade B)
- Completeness: 28/30
- Consistency: 20/25 (missing reporting in Q4)
- Specificity: 15/20
- Business Intel: 15/15 (excellent)
- Technical Depth: 7/10

**Property Manager (AI-Fixed v2):** 92/100 (Grade A)
- Completeness: 30/30 (+2)
- Consistency: 25/25 (+5)
- Specificity: 15/20
- Business Intel: 15/15
- Technical Depth: 7/10

**Delta:** +7 points → AI Fixer improved quality

---

## Detailed Scoring Breakdown

### 1. Completeness (30 points)

**What it checks:**
- Q1 problem_customer length (5 pts)
- Q2 target_user count (3 pts)
- Q3 success_metric present (3 pts)
- Q4 must_have_features count (5 pts)
- Q5 non_goals count (2 pts)
- Q6 constraints completeness (4 pts)
- Q7 data_sources (2 pts)
- Q8 integrations (1 pt)
- Q9 risks count (3 pts)
- Q10 shipping_preference (1 pt)
- Q11 architecture flags (6 pts)

**Scoring logic:**
```python
# Q1 example
if len(q1) >= 100:
    score += 5  # Comprehensive
elif len(q1) >= 50:
    score += 3  # Adequate
elif len(q1) >= 20:
    score += 1  # Minimal
else:
    score += 0  # Missing
```

---

### 2. Consistency (25 points)

**What it checks:**
- Q4 features ↔ Q11 architecture flags (10 pts)
  - Auth mentioned in Q4 → authentication_required=true in Q11
  - Payments mentioned → payments_required=true
  - Dashboard mentioned → dashboard_reporting=true
- Q8 integrations ↔ Q11 external_apis (5 pts)
  - MVP integrations in Q8 should be in Q11 external_apis
- Q4 must-haves ↔ Q5 non-goals (5 pts)
  - No overlap between what you're building and what you're not
- Q6 economics ↔ Q11 payments_required (3 pts)
- Q3 timeline ↔ Q11 expected_timeline_days (2 pts)

**Example penalty:**
```
Q4: "User login with email verification"
Q11: {"authentication_required": false}
→ Penalty: "Q4 mentions auth but Q11.authentication_required=false"
→ Deduction: -2 points
```

---

### 3. Specificity (20 points)

**What it checks:**
- Pricing model specific (5 pts)
  - Tier structure with exact prices = 5 pts
  - Price with frequency ($X/month) = 3 pts
  - Just has $ symbol = 1 pt
- Quantitative requirements (5 pts)
  - Numbers in Q7 data sources (templates count, user limits, etc.)
- Technical requirements (5 pts)
  - Structured dict = 5 pts
  - String with >50 chars = 3 pts
- Success metrics measurable (5 pts)
  - 3+ numbers in Q3 = 5 pts (e.g., "50 signups, 20 active users, $5K revenue")

**Example:**
```
Q6 economics: "Monthly subscription $39-79/month based on property count"
→ Has $ and frequency but no tier structure
→ Score: 3/5
→ Penalty: "Pricing vague (has $ but no clear model)"

After Munger fix:
Q6 economics: "Tier 1: $39 (1-15 props), Tier 2: $79 (16-50 props)"
→ Has tier structure with exact prices
→ Score: 5/5
→ Bonus: "Pricing has specific tier structure"
```

---

### 4. Business Intelligence (15 points)

**What it checks:**
- Risk identification (6 pts)
  - 5+ risks = 6 pts
  - 3-4 risks = 4 pts
  - 1-2 risks = 2 pts
- Competitive awareness (4 pts)
  - Mentions competitors in Q9 = 4 pts
- Market insights (3 pts)
  - Q1 has market size + pain point = 3 pts
- GTM considerations (2 pts)
  - Q9 mentions adoption/onboarding challenges = 2 pts

**Example:**
```
Q9 risks (original with 5 risks):
- "Late adopters of technology"
- "Email marked as spam"
- "Photo storage costs - cap at 5 photos, 2MB"
- "Recurring logic bugs (Feb 29, DST)"
- "Competition from Buildium ($200-400/mo vs our $39-79)"
→ Score: 6 + 4 + 2 = 12/15

Q9 risks (AI-fixed v1 with 1 risk):
- "Background job failures"
→ Score: 2 + 0 + 0 = 2/15
→ Lost 10 points!
```

---

### 5. Technical Depth (10 points)

**What it checks:**
- Architecture flags completeness (4 pts)
  - 4 key flags present = 4 pts
- Tech stack specified (3 pts)
  - "FastAPI + React + PostgreSQL" = 3 pts
- External APIs documented (2 pts)
  - 2+ APIs = 2 pts
- Deployment plan (1 pt)
  - "Railway + Vercel" = 1 pt

---

## Penalties & Bonuses

### Common Penalties

```python
# Completeness penalties
"Q1 too short (50-99 chars)"  # -2 pts
"Q4 has too few features (<3)"  # -3 pts
"Q9 has only 1-2 risks (need 5+)"  # -2 pts

# Consistency penalties
"Q4 mentions auth but Q11.authentication_required=false"  # -2 pts
"Contradiction: mobile app in both must-have and non-goals"  # -5 pts

# Specificity penalties
"Pricing vague (has $ but no clear model)"  # -2 pts
"No quantitative requirements"  # -5 pts

# Business intel penalties
"Insufficient risk analysis (<3 risks)"  # -2 pts
"No competitive analysis"  # -4 pts

# Technical penalties
"Tech stack vague"  # -2 pts
"Deployment plan missing"  # -1 pt
```

### Common Bonuses

```python
# Completeness bonuses
"Q4 has comprehensive feature list (10+)"  # +0 (already at max)

# Consistency bonuses
"Q8 MVP integrations present in Q11"  # +0 (already at max)

# Specificity bonuses
"Pricing has specific tier structure"  # +0 (already at max)
"Success metrics highly specific (3+ numbers)"  # +0 (already at max)

# Business intel bonuses
"Comprehensive risk analysis (5+ risks)"  # +0 (already at max)
"Competitive awareness present in risks"  # +0 (already at max)
"GTM considerations in risk analysis"  # +0 (already at max)

# Technical bonuses
"Tech stack clearly specified"  # +0 (already at max)
"All key architecture flags present"  # +0 (already at max)
```

**Note:** Bonuses don't add extra points beyond the category maximum. They're informational only.

---

## AI Fixer Integration Pattern

### Pattern 1: Score-Gated Application

Only apply AI fixes if they improve the score:

```python
def apply_ai_fixer_with_scoring(original_spec):
    """Apply AI fixer only if it improves quality"""
    
    # Score original
    scorer = SpecQualityScorer()
    original_score = scorer.score_spec(original_spec)
    
    # Generate fix
    fixed_spec = ai_fixer.fix(original_spec)
    
    # Score fixed
    fixed_score = scorer.score_spec(fixed_spec)
    
    # Compare
    if fixed_score.total > original_score.total:
        print(f"✅ AI improved: {original_score.total} → {fixed_score.total}")
        return fixed_spec
    else:
        print(f"❌ AI degraded: {original_score.total} → {fixed_score.total}")
        return original_spec  # Revert to original
```

---

### Pattern 2: Category-Specific Gating

Apply fixes only if they improve specific categories:

```python
def apply_ai_fixer_selective(original_spec, target_categories=['consistency']):
    """Apply AI fixer only if target categories improve"""
    
    scorer = SpecQualityScorer()
    original_score = scorer.score_spec(original_spec)
    fixed_spec = ai_fixer.fix(original_spec)
    fixed_score = scorer.score_spec(fixed_spec)
    
    # Check target categories
    improved = True
    for category in target_categories:
        orig_val = getattr(original_score, category)
        fixed_val = getattr(fixed_score, category)
        
        if fixed_val < orig_val:
            print(f"❌ {category}: {orig_val} → {fixed_val} (degraded)")
            improved = False
    
    if improved:
        return fixed_spec
    else:
        return original_spec
```

---

### Pattern 3: Confidence-Adjusted Threshold

Lower score threshold for high-confidence fixes:

```python
def apply_with_confidence_threshold(original_spec, ai_confidence):
    """Apply fix based on confidence-adjusted threshold"""
    
    scorer = SpecQualityScorer()
    original_score = scorer.score_spec(original_spec)
    fixed_spec = ai_fixer.fix(original_spec)
    fixed_score = scorer.score_spec(fixed_spec)
    
    delta = fixed_score.total - original_score.total
    
    # High confidence = tolerate small degradation
    if ai_confidence >= 0.9:
        threshold = -3  # Allow up to 3 point loss
    elif ai_confidence >= 0.7:
        threshold = 0  # No degradation allowed
    else:
        threshold = +3  # Must improve by 3+ points
    
    if delta >= threshold:
        return fixed_spec
    else:
        return original_spec
```

---

## Testing & Validation

### Unit Test Example

```python
import pytest
from spec_quality_scorer import SpecQualityScorer

def test_perfect_spec():
    """Test a perfect 100-point spec"""
    perfect_spec = {
        "Q1_problem_customer": "Property managers with 10-50 units...",  # 100+ chars
        "Q2_target_user": ["User 1", "User 2", "User 3"],  # 3+ users
        "Q3_success_metric": "Within 90 days: 50 signups, 20 active, 300 tasks",  # 3+ numbers
        "Q4_must_have_features": ["Feature " + str(i) for i in range(1, 11)],  # 10 features
        "Q5_non_goals": ["Non-goal " + str(i) for i in range(1, 6)],  # 5 non-goals
        "Q6_constraints": {
            "brand_positioning": "Simple tool",
            "scope": "Maintenance only",
            "economics": "Tier 1: $39 (1-15), Tier 2: $79 (16-50)",
            "build_time": "60 days",
            "tech_requirements": {"requirement": "Test"}
        },
        "Q7_data_sources": ["Source with 20-30 items", "Another source"],
        "Q8_integrations": ["Stripe", "SendGrid"],
        "Q9_risks": [
            "Late adopters",
            "Email spam",
            "Storage costs",
            "Logic bugs",
            "Competition from Buildium"
        ],
        "Q10_shipping_preference": "Ship fast, iterate",
        "Q11_architecture": {
            "authentication_required": True,
            "role_based_access": False,
            "multi_tenant": False,
            "persistent_database": True,
            "payments_required": True,
            "subscription_billing": True,
            "dashboard_reporting": True,
            "pdf_generation": False,
            "background_jobs": True,
            "admin_panel": False,
            "expected_timeline_days": 60,
            "minimum_tier": 2,
            "tech_stack": "FastAPI + React + PostgreSQL",
            "deployment": "Railway + Vercel",
            "external_apis": ["Stripe", "SendGrid"]
        }
    }
    
    scorer = SpecQualityScorer()
    score = scorer.score_spec(perfect_spec)
    
    assert score.total >= 90, f"Perfect spec should score 90+, got {score.total}"
```

---

## Command Line Usage

```bash
# Score a single spec
python spec_quality_scorer.py property_manager.json

# Compare two specs
python spec_quality_scorer.py --compare original.json fixed.json

# Output:
# === ORIGINAL SPEC ===
# Total: 85/100
#   Completeness: 28/30
#   Consistency: 20/25
#   ...
#
# === AI-FIXED SPEC ===
# Total: 92/100
#   ...
#
# === VERDICT: IMPROVED by 7 points ===
```

---

## Calibration

The scorer is calibrated against these reference specs:

| Spec | Total | Comp | Cons | Spec | Biz | Tech | Notes |
|------|-------|------|------|------|-----|------|-------|
| **Perfect** | 100 | 30 | 25 | 20 | 15 | 10 | All fields complete, consistent, specific |
| **Property Mgr (Orig)** | 85 | 28 | 20 | 15 | 15 | 7 | Missing Q4 reporting |
| **Property Mgr (Fixed v2)** | 92 | 30 | 25 | 15 | 15 | 7 | All consistency issues fixed |
| **TwoFaced (Clean)** | 95 | 30 | 25 | 20 | 12 | 8 | Excellent spec from start |
| **Invoice Tracker** | 90 | 30 | 23 | 18 | 12 | 7 | Minor consistency issues |
| **Minimal MVP** | 70 | 25 | 18 | 12 | 8 | 7 | Bare minimum acceptable |

---

## Next Steps

1. **Copy scorer to your project:**
   ```bash
   cp spec_quality_scorer.py /path/to/munger/
   ```

2. **Integrate with AI Fixer:**
   - Add score comparison before/after AI fixes
   - Only apply fixes that improve scores

3. **Add to Munger pipeline:**
   - Score input before Munger
   - Score output after Munger
   - Track quality improvement

4. **Monitor in production:**
   - Track average scores over time
   - Identify common penalty patterns
   - Tune rules based on data

---

**Questions? Check the inline docstrings in `spec_quality_scorer.py` for detailed implementation notes.**
