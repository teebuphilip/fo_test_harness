"""
Spec Quality Scoring Algorithm
Used to measure original vs AI-fixed spec quality

Version: 1.0
Date: 2026-02-27
"""

import json
from typing import Dict, List, Tuple, Any
from dataclasses import dataclass


@dataclass
class ScoreBreakdown:
    """Detailed score breakdown by category"""
    completeness: int  # /30 points
    consistency: int   # /25 points
    specificity: int   # /20 points
    business_intel: int  # /15 points
    technical_depth: int  # /10 points
    total: int  # /100 points
    penalties: List[str]  # List of deductions
    bonuses: List[str]  # List of additions


class SpecQualityScorer:
    """
    Scores a startup spec (Q1-Q11) on a 100-point scale
    
    Categories:
    - Completeness (30 pts): Are all required fields present and non-empty?
    - Consistency (25 pts): Do fields align with each other?
    - Specificity (20 pts): Are specs concrete or vague?
    - Business Intelligence (15 pts): Risks, competition, market insights
    - Technical Depth (10 pts): Architecture, constraints, tech requirements
    
    Usage:
        scorer = SpecQualityScorer()
        score = scorer.score_spec(hero_answers)
        print(f"Score: {score.total}/100")
    """
    
    def __init__(self):
        self.max_completeness = 30
        self.max_consistency = 25
        self.max_specificity = 20
        self.max_business_intel = 15
        self.max_technical_depth = 10
    
    def score_spec(self, hero_answers: Dict) -> ScoreBreakdown:
        """Main scoring entry point"""
        
        completeness, comp_details = self._score_completeness(hero_answers)
        consistency, cons_details = self._score_consistency(hero_answers)
        specificity, spec_details = self._score_specificity(hero_answers)
        business_intel, biz_details = self._score_business_intelligence(hero_answers)
        technical_depth, tech_details = self._score_technical_depth(hero_answers)
        
        total = completeness + consistency + specificity + business_intel + technical_depth
        
        all_penalties = comp_details['penalties'] + cons_details['penalties'] + \
                       spec_details['penalties'] + biz_details['penalties'] + \
                       tech_details['penalties']
        
        all_bonuses = comp_details['bonuses'] + cons_details['bonuses'] + \
                     spec_details['bonuses'] + biz_details['bonuses'] + \
                     tech_details['bonuses']
        
        return ScoreBreakdown(
            completeness=completeness,
            consistency=consistency,
            specificity=specificity,
            business_intel=business_intel,
            technical_depth=technical_depth,
            total=total,
            penalties=all_penalties,
            bonuses=all_bonuses
        )
    
    # ========== COMPLETENESS SCORING (30 points) ==========
    
    def _score_completeness(self, hero: Dict) -> Tuple[int, Dict]:
        """
        Score completeness of required fields
        
        Breakdown:
        - Q1 problem_customer (5 pts): Min 20 chars
        - Q2 target_user (3 pts): At least 1 user segment
        - Q3 success_metric (3 pts): Present and non-empty
        - Q4 must_have_features (5 pts): 3-20 features
        - Q5 non_goals (2 pts): At least 1 non-goal
        - Q6 constraints (4 pts): All sub-fields present
        - Q7 data_sources (2 pts): At least 1 source
        - Q8 integrations (1 pt): Can be empty for some products
        - Q9 risks (3 pts): At least 1 risk
        - Q10 shipping_preference (1 pt): Present and non-empty
        - Q11 architecture (6 pts): All required flags + timeline
        """
        score = 0
        penalties = []
        bonuses = []
        
        # Q1 (5 pts)
        q1 = hero.get('Q1_problem_customer', '')
        if len(q1) >= 100:
            score += 5
        elif len(q1) >= 50:
            score += 3
            penalties.append("Q1 too short (50-99 chars)")
        elif len(q1) >= 20:
            score += 1
            penalties.append("Q1 too short (20-49 chars)")
        else:
            penalties.append("Q1 missing or <20 chars")
        
        # Q2 (3 pts)
        q2 = hero.get('Q2_target_user', [])
        if isinstance(q2, list):
            if len(q2) >= 3:
                score += 3
            elif len(q2) >= 1:
                score += 2
                penalties.append("Q2 has only 1-2 user segments (need 3+)")
            else:
                penalties.append("Q2 empty")
        else:
            penalties.append("Q2 not a list")
        
        # Q3 (3 pts)
        q3 = hero.get('Q3_success_metric', '')
        if len(q3) >= 50:
            score += 3
        elif len(q3) >= 10:
            score += 1
            penalties.append("Q3 too vague (<50 chars)")
        else:
            penalties.append("Q3 missing or <10 chars")
        
        # Q4 (5 pts)
        q4 = hero.get('Q4_must_have_features', [])
        if isinstance(q4, list):
            if 3 <= len(q4) <= 20:
                score += 5
                if len(q4) >= 10:
                    bonuses.append("Q4 has comprehensive feature list (10+)")
            elif len(q4) > 20:
                score += 3
                penalties.append("Q4 has too many features (>20)")
            elif len(q4) >= 1:
                score += 2
                penalties.append("Q4 has too few features (<3)")
            else:
                penalties.append("Q4 empty")
        else:
            penalties.append("Q4 not a list")
        
        # Q5 (2 pts)
        q5 = hero.get('Q5_non_goals', [])
        if isinstance(q5, list) and len(q5) >= 3:
            score += 2
        elif isinstance(q5, list) and len(q5) >= 1:
            score += 1
            penalties.append("Q5 has only 1-2 non-goals (need 3+)")
        else:
            penalties.append("Q5 missing or not a list")
        
        # Q6 (4 pts)
        q6 = hero.get('Q6_constraints', {})
        if isinstance(q6, dict):
            required_fields = ['brand_positioning', 'scope', 'economics', 'build_time']
            present_fields = sum(1 for f in required_fields if q6.get(f))
            score += present_fields  # 1 pt per field
            missing = [f for f in required_fields if not q6.get(f)]
            if missing:
                penalties.append(f"Q6 missing: {', '.join(missing)}")
        else:
            penalties.append("Q6 not a dict")
        
        # Q7 (2 pts)
        q7 = hero.get('Q7_data_sources', [])
        if isinstance(q7, list) and len(q7) >= 2:
            score += 2
        elif isinstance(q7, list) and len(q7) >= 1:
            score += 1
            penalties.append("Q7 has only 1 data source")
        else:
            penalties.append("Q7 missing or not a list")
        
        # Q8 (1 pt)
        q8 = hero.get('Q8_integrations', [])
        if isinstance(q8, list):
            score += 1
        else:
            penalties.append("Q8 not a list")
        
        # Q9 (3 pts)
        q9 = hero.get('Q9_risks', [])
        if isinstance(q9, list):
            if len(q9) >= 5:
                score += 3
            elif len(q9) >= 3:
                score += 2
                penalties.append("Q9 has only 3-4 risks (need 5+)")
            elif len(q9) >= 1:
                score += 1
                penalties.append("Q9 has only 1-2 risks (need 5+)")
            else:
                penalties.append("Q9 empty")
        else:
            penalties.append("Q9 not a list")
        
        # Q10 (1 pt)
        q10 = hero.get('Q10_shipping_preference', '')
        if len(q10) >= 20:
            score += 1
        else:
            penalties.append("Q10 missing or too short")
        
        # Q11 (6 pts)
        q11 = hero.get('Q11_architecture', {})
        if isinstance(q11, dict):
            required_flags = [
                'authentication_required', 'role_based_access', 'multi_tenant',
                'persistent_database', 'payments_required', 'subscription_billing',
                'dashboard_reporting', 'pdf_generation', 'background_jobs',
                'admin_panel', 'expected_timeline_days', 'minimum_tier'
            ]
            present_flags = sum(1 for f in required_flags if f in q11)
            score += min(6, int(present_flags / 2))  # 2 flags = 1 pt
            missing = [f for f in required_flags if f not in q11]
            if missing:
                penalties.append(f"Q11 missing: {len(missing)} flags")
        else:
            penalties.append("Q11 not a dict")
        
        return score, {'penalties': penalties, 'bonuses': bonuses}
    
    # ========== CONSISTENCY SCORING (25 points) ==========
    
    def _score_consistency(self, hero: Dict) -> Tuple[int, Dict]:
        """
        Score internal consistency between fields
        
        Checks:
        - Q4 features ↔ Q11 architecture flags (10 pts)
        - Q8 integrations ↔ Q11 external_apis (5 pts)
        - Q4 must-haves ↔ Q5 non-goals (no overlap) (5 pts)
        - Q6 economics ↔ Q11 payments_required (3 pts)
        - Q3 timeline ↔ Q11 expected_timeline_days (2 pts)
        """
        score = 0
        penalties = []
        bonuses = []
        
        q4 = hero.get('Q4_must_have_features', [])
        q5 = hero.get('Q5_non_goals', [])
        q8 = hero.get('Q8_integrations', [])
        q11 = hero.get('Q11_architecture', {})
        
        # Check Q4 features → Q11 flags (10 pts)
        consistency_checks = [
            ('auth', ['login', 'registration', 'auth'], 'authentication_required'),
            ('roles', ['role', 'permission', 'access control'], 'role_based_access'),
            ('payment', ['payment', 'billing', 'stripe'], 'payments_required'),
            ('dashboard', ['dashboard', 'report', 'analytics'], 'dashboard_reporting'),
            ('pdf', ['pdf', 'document', 'invoice'], 'pdf_generation'),
        ]
        
        for name, keywords, flag in consistency_checks:
            has_feature = any(any(kw in f.lower() for kw in keywords) for f in q4)
            flag_value = q11.get(flag, False)
            
            if has_feature and flag_value:
                score += 2  # Perfect consistency
            elif has_feature and not flag_value:
                penalties.append(f"Q4 mentions {name} but Q11.{flag}=false")
            elif not has_feature and flag_value:
                penalties.append(f"Q11.{flag}=true but Q4 doesn't mention {name}")
            else:
                score += 2  # Both agree it's not needed
        
        # Check Q8 integrations → Q11 external_apis (5 pts)
        q11_apis = q11.get('external_apis', [])
        if isinstance(q8, list) and isinstance(q11_apis, list):
            mvp_integrations = [i for i in q8 if 'MVP' in i or 'required' in i.lower()]
            mvp_in_q11 = all(any(api_name in q11_api for api_name in [i.split('-')[0].split('(')[0].strip() for i in mvp_integrations]) for q11_api in q11_apis)
            
            if len(mvp_integrations) == 0:
                score += 5  # No MVP integrations, consistent
            elif mvp_in_q11 or len(q11_apis) >= len(mvp_integrations):
                score += 5  # APIs align
                bonuses.append("Q8 MVP integrations present in Q11")
            else:
                score += 2
                penalties.append("Q8 MVP integrations missing from Q11 external_apis")
        
        # Check Q4 ↔ Q5 overlap (5 pts)
        if isinstance(q4, list) and isinstance(q5, list):
            q4_lower = [f.lower() for f in q4]
            q5_lower = [ng.lower() for ng in q5]
            
            overlaps = []
            for ng in q5_lower:
                for f in q4_lower:
                    # Check for keyword overlap
                    ng_words = set(ng.split())
                    f_words = set(f.split())
                    if len(ng_words & f_words) >= 2:  # At least 2 common words
                        overlaps.append((ng[:50], f[:50]))
            
            if len(overlaps) == 0:
                score += 5  # No contradictions
            else:
                score += max(0, 5 - len(overlaps))
                for ng, f in overlaps:
                    penalties.append(f"Contradiction: '{ng}...' in non-goals but similar feature in must-haves")
        
        # Check Q6 economics → Q11 payments (3 pts)
        q6 = hero.get('Q6_constraints', {})
        economics = str(q6.get('economics', '')).lower()
        payments_required = q11.get('payments_required', False)
        
        has_pricing = any(word in economics for word in ['$', 'price', 'subscription', 'billing', 'payment'])
        
        if has_pricing and payments_required:
            score += 3
        elif has_pricing and not payments_required:
            penalties.append("Q6 mentions pricing but Q11.payments_required=false")
        elif not has_pricing and payments_required:
            score += 1
            penalties.append("Q11.payments_required=true but Q6 doesn't mention pricing")
        else:
            score += 3  # Both agree no payments
        
        # Check Q3 timeline → Q11 timeline (2 pts)
        # This is harder to parse automatically, so just check both exist
        q3 = hero.get('Q3_success_metric', '')
        timeline_days = q11.get('expected_timeline_days', 0)
        
        if timeline_days > 0:
            score += 2
        else:
            penalties.append("Q11 missing expected_timeline_days")
        
        return score, {'penalties': penalties, 'bonuses': bonuses}
    
    # ========== SPECIFICITY SCORING (20 points) ==========
    
    def _score_specificity(self, hero: Dict) -> Tuple[int, Dict]:
        """
        Score how specific vs vague the specs are
        
        Checks:
        - Pricing model specific (5 pts)
        - Quantitative requirements (5 pts)
        - Technical requirements (5 pts)
        - Success metrics measurable (5 pts)
        """
        score = 0
        penalties = []
        bonuses = []
        
        # Pricing specificity (5 pts)
        q6 = hero.get('Q6_constraints', {})
        economics = str(q6.get('economics', ''))
        
        if 'tier' in economics.lower() and '$' in economics:
            score += 5
            bonuses.append("Pricing has specific tier structure")
        elif '$' in economics and any(word in economics.lower() for word in ['month', 'annual', 'per']):
            score += 3
        elif '$' in economics:
            score += 1
            penalties.append("Pricing vague (has $ but no clear model)")
        else:
            penalties.append("Pricing not specified")
        
        # Quantitative requirements (5 pts)
        q7 = hero.get('Q7_data_sources', [])
        quantitative_patterns = [
            r'\d+',  # Any number
            r'minimum.*\d+',
            r'maximum.*\d+',
            r'target.*\d+'
        ]
        
        import re
        quant_count = 0
        for source in q7:
            for pattern in quantitative_patterns:
                if re.search(pattern, source.lower()):
                    quant_count += 1
                    break
        
        if quant_count >= 2:
            score += 5
        elif quant_count >= 1:
            score += 3
            penalties.append("Few quantitative requirements")
        else:
            penalties.append("No quantitative requirements")
        
        # Technical requirements (5 pts)
        tech_reqs = q6.get('tech_requirements', '')
        if isinstance(tech_reqs, dict):
            score += 5
            bonuses.append("Tech requirements structured")
        elif isinstance(tech_reqs, str) and len(tech_reqs) >= 50:
            score += 3
        elif isinstance(tech_reqs, str) and len(tech_reqs) > 0:
            score += 1
            penalties.append("Tech requirements too vague")
        else:
            penalties.append("Tech requirements missing")
        
        # Success metrics measurable (5 pts)
        q3 = hero.get('Q3_success_metric', '')
        
        # Check for specific numbers
        import re
        numbers = re.findall(r'\d+', q3)
        
        if len(numbers) >= 3:
            score += 5
            bonuses.append("Success metrics highly specific (3+ numbers)")
        elif len(numbers) >= 1:
            score += 3
        else:
            penalties.append("Success metrics not measurable (no numbers)")
        
        return score, {'penalties': penalties, 'bonuses': bonuses}
    
    # ========== BUSINESS INTELLIGENCE SCORING (15 points) ==========
    
    def _score_business_intelligence(self, hero: Dict) -> Tuple[int, Dict]:
        """
        Score depth of business intelligence
        
        Checks:
        - Risk identification (6 pts)
        - Competitive awareness (4 pts)
        - Market insights (3 pts)
        - Go-to-market considerations (2 pts)
        """
        score = 0
        penalties = []
        bonuses = []
        
        q9 = hero.get('Q9_risks', [])
        
        # Risk identification (6 pts)
        if len(q9) >= 5:
            score += 6
            bonuses.append("Comprehensive risk analysis (5+ risks)")
        elif len(q9) >= 3:
            score += 4
        elif len(q9) >= 1:
            score += 2
            penalties.append("Insufficient risk analysis (<3 risks)")
        else:
            penalties.append("No risk analysis")
        
        # Competitive awareness (4 pts)
        risks_text = ' '.join(q9).lower()
        has_competition = any(word in risks_text for word in ['competitor', 'competition', 'compete', 'vs', 'alternative'])
        
        if has_competition:
            score += 4
            bonuses.append("Competitive awareness present in risks")
        else:
            penalties.append("No competitive analysis")
        
        # Market insights (3 pts)
        q1 = hero.get('Q1_problem_customer', '')
        has_market_size = any(word in q1.lower() for word in ['market', 'users', 'customers', 'segment'])
        has_pain_point = any(word in q1.lower() for word in ['struggle', 'problem', 'pain', 'frustration', 'difficult'])
        
        if has_market_size and has_pain_point:
            score += 3
        elif has_pain_point:
            score += 2
        else:
            score += 1
            penalties.append("Weak problem statement")
        
        # GTM considerations (2 pts)
        has_gtm = any(word in risks_text for word in ['adopt', 'onboard', 'education', 'behavior', 'sales cycle'])
        
        if has_gtm:
            score += 2
            bonuses.append("GTM considerations in risk analysis")
        else:
            penalties.append("No GTM considerations")
        
        return score, {'penalties': penalties, 'bonuses': bonuses}
    
    # ========== TECHNICAL DEPTH SCORING (10 points) ==========
    
    def _score_technical_depth(self, hero: Dict) -> Tuple[int, Dict]:
        """
        Score technical depth and architecture clarity
        
        Checks:
        - Architecture flags completeness (4 pts)
        - Tech stack specified (3 pts)
        - External APIs documented (2 pts)
        - Deployment plan (1 pt)
        """
        score = 0
        penalties = []
        bonuses = []
        
        q11 = hero.get('Q11_architecture', {})
        
        # Architecture flags (4 pts)
        required_flags = [
            'authentication_required', 'persistent_database',
            'payments_required', 'background_jobs'
        ]
        present_flags = sum(1 for f in required_flags if f in q11)
        score += present_flags  # 1 pt per key flag
        
        if present_flags == 4:
            bonuses.append("All key architecture flags present")
        elif present_flags < 2:
            penalties.append("Missing critical architecture flags")
        
        # Tech stack (3 pts)
        tech_stack = q11.get('tech_stack', '')
        if isinstance(tech_stack, str) and len(tech_stack) >= 20:
            score += 3
            bonuses.append("Tech stack clearly specified")
        elif isinstance(tech_stack, str) and len(tech_stack) > 0:
            score += 1
            penalties.append("Tech stack vague")
        else:
            penalties.append("Tech stack not specified")
        
        # External APIs (2 pts)
        external_apis = q11.get('external_apis', [])
        if isinstance(external_apis, list) and len(external_apis) >= 2:
            score += 2
        elif isinstance(external_apis, list) and len(external_apis) >= 1:
            score += 1
        else:
            penalties.append("External APIs not documented")
        
        # Deployment (1 pt)
        deployment = q11.get('deployment', '')
        if isinstance(deployment, str) and len(deployment) > 0:
            score += 1
        else:
            penalties.append("Deployment plan missing")
        
        return score, {'penalties': penalties, 'bonuses': bonuses}


# ========== COMPARISON & DELTA SCORING ==========

def compare_specs(original: Dict, fixed: Dict) -> Dict:
    """
    Compare original vs fixed specs and calculate delta
    
    Returns:
        {
            "original_score": ScoreBreakdown,
            "fixed_score": ScoreBreakdown,
            "delta": int,
            "verdict": str,
            "changes": [...]
        }
    """
    scorer = SpecQualityScorer()
    
    orig_score = scorer.score_spec(original)
    fixed_score = scorer.score_spec(fixed)
    
    delta = fixed_score.total - orig_score.total
    
    if delta > 0:
        verdict = f"IMPROVED by {delta} points"
    elif delta < 0:
        verdict = f"DEGRADED by {abs(delta)} points"
    else:
        verdict = "UNCHANGED"
    
    # Identify specific changes
    changes = []
    
    # Completeness changes
    if fixed_score.completeness != orig_score.completeness:
        changes.append({
            "category": "Completeness",
            "original": orig_score.completeness,
            "fixed": fixed_score.completeness,
            "delta": fixed_score.completeness - orig_score.completeness
        })
    
    # Consistency changes
    if fixed_score.consistency != orig_score.consistency:
        changes.append({
            "category": "Consistency",
            "original": orig_score.consistency,
            "fixed": fixed_score.consistency,
            "delta": fixed_score.consistency - orig_score.consistency
        })
    
    # Specificity changes
    if fixed_score.specificity != orig_score.specificity:
        changes.append({
            "category": "Specificity",
            "original": orig_score.specificity,
            "fixed": fixed_score.specificity,
            "delta": fixed_score.specificity - orig_score.specificity
        })
    
    # Business intel changes
    if fixed_score.business_intel != orig_score.business_intel:
        changes.append({
            "category": "Business Intelligence",
            "original": orig_score.business_intel,
            "fixed": fixed_score.business_intel,
            "delta": fixed_score.business_intel - orig_score.business_intel
        })
    
    # Technical depth changes
    if fixed_score.technical_depth != orig_score.technical_depth:
        changes.append({
            "category": "Technical Depth",
            "original": orig_score.technical_depth,
            "fixed": fixed_score.technical_depth,
            "delta": fixed_score.technical_depth - orig_score.technical_depth
        })
    
    return {
        "original_score": orig_score,
        "fixed_score": fixed_score,
        "delta": delta,
        "verdict": verdict,
        "changes": changes
    }


# ========== USAGE EXAMPLE ==========

if __name__ == "__main__":
    # Example usage
    import json
    
    # Load specs
    with open('property_manager_maintenance_scheduler.json') as f:
        original_spec = json.load(f)['hero_answers']
    
    with open('aifixed_property_manager_maintenance_scheduler.json') as f:
        fixed_spec = json.load(f)['hero_answers']
    
    # Score both
    scorer = SpecQualityScorer()
    
    print("=== ORIGINAL SPEC ===")
    orig_score = scorer.score_spec(original_spec)
    print(f"Total: {orig_score.total}/100")
    print(f"  Completeness: {orig_score.completeness}/30")
    print(f"  Consistency: {orig_score.consistency}/25")
    print(f"  Specificity: {orig_score.specificity}/20")
    print(f"  Business Intel: {orig_score.business_intel}/15")
    print(f"  Technical Depth: {orig_score.technical_depth}/10")
    print()
    
    print("=== AI-FIXED SPEC ===")
    fixed_score = scorer.score_spec(fixed_spec)
    print(f"Total: {fixed_score.total}/100")
    print(f"  Completeness: {fixed_score.completeness}/30")
    print(f"  Consistency: {fixed_score.consistency}/25")
    print(f"  Specificity: {fixed_score.specificity}/20")
    print(f"  Business Intel: {fixed_score.business_intel}/15")
    print(f"  Technical Depth: {fixed_score.technical_depth}/10")
    print()
    
    # Compare
    comparison = compare_specs(original_spec, fixed_spec)
    print(f"=== VERDICT: {comparison['verdict']} ===")
    print()
    
    if comparison['changes']:
        print("Changes:")
        for change in comparison['changes']:
            print(f"  {change['category']}: {change['original']} → {change['fixed']} ({change['delta']:+d})")
    
    print()
    print("Penalties (Fixed):")
    for penalty in fixed_score.penalties[:5]:  # Show first 5
        print(f"  - {penalty}")
    
    print()
    print("Bonuses (Fixed):")
    for bonus in fixed_score.bonuses[:5]:  # Show first 5
        print(f"  + {bonus}")
