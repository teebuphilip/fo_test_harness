#!/usr/bin/env python3
"""
check_boilerplate_fit.py - Boilerplate Compatibility Analyzer

Analyzes an intake JSON from run_intake_v7.sh against the Teebu SaaS
boilerplate and produces a YES/NO verdict with a full technical decomposition.

If YES: outputs the exact file list Claude should build in business/
If NO:  outputs why it does not fit and what custom approach is needed

USAGE:
    ./check_boilerplate_fit.py <intake_json> <boilerplate_zip_or_dir>

EXAMPLES:
    ./check_boilerplate_fit.py \\
        intake_hero_runs/wynwood_thoroughbreds/wynwood_thoroughbreds.json \\
        /path/to/teebu-saas-platform.zip

    ./check_boilerplate_fit.py \\
        intake_hero_runs/wynwood_thoroughbreds/wynwood_thoroughbreds.json \\
        /path/to/teebu-saas-platform

OUTPUT:
    Terminal: colored verdict summary
    File:     boilerplate_checks/{startup_id}_boilerplate_check.json
"""

import os
import sys
import json
import re
import time
import zipfile
import argparse
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, Tuple
import requests


# ============================================================
# CONFIGURATION
# ============================================================

class Config:
    OPENAI_API_KEY    = os.getenv('OPENAI_API_KEY')
    ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY')
    ANTHROPIC_API     = 'https://api.anthropic.com/v1/messages'
    CLAUDE_MODEL      = 'claude-sonnet-4-20250514'
    OPENAI_API        = 'https://api.openai.com/v1/chat/completions'
    OPENAI_MODEL      = os.getenv('OPENAI_MODEL', 'gpt-4o-mini')
    CLAUDE_MAX_TOKENS = 8192
    REQUEST_TIMEOUT   = 180
    MAX_RETRIES       = 3
    RETRY_SLEEP       = 5
    MAX_MANIFEST_CHARS = int(os.getenv("MAX_MANIFEST_CHARS", "300000"))
    OUTPUT_DIR        = Path('./boilerplate_checks')
    COST_CSV          = Path('./boilerplate_checks/boilerplate_fit_ai_costs.csv')
    OPENAI_INPUT_PER_MTOK = float(os.getenv("OPENAI_INPUT_PER_MTOK", "2.50"))
    OPENAI_OUTPUT_PER_MTOK = float(os.getenv("OPENAI_OUTPUT_PER_MTOK", "10.00"))
    CLAUDE_INPUT_PER_MTOK = float(os.getenv("CLAUDE_INPUT_PER_MTOK", "3.00"))
    CLAUDE_OUTPUT_PER_MTOK = float(os.getenv("CLAUDE_OUTPUT_PER_MTOK", "15.00"))


# ============================================================
# COLOR OUTPUT
# ============================================================

class Colors:
    GREEN  = '\033[92m'
    YELLOW = '\033[93m'
    RED    = '\033[91m'
    CYAN   = '\033[96m'
    BLUE   = '\033[94m'
    BOLD   = '\033[1m'
    END    = '\033[0m'

def print_header(text: str):
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*70}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{text}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'='*70}{Colors.END}\n")

def print_success(text: str):
    print(f"{Colors.GREEN}✓ {text}{Colors.END}")

def print_error(text: str):
    print(f"{Colors.RED}✗ {text}{Colors.END}")

def print_warning(text: str):
    print(f"{Colors.YELLOW}⚠ {text}{Colors.END}")

def print_info(text: str):
    print(f"{Colors.CYAN}→ {text}{Colors.END}")


# ============================================================
# COST TRACKING
# ============================================================

def _append_cost_row(startup_id: str, provider: str, model: str, in_tokens: int, out_tokens: int, cost: float) -> None:
    Config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    exists = Config.COST_CSV.exists()
    with open(Config.COST_CSV, "a", encoding="utf-8") as f:
        if not exists:
            f.write("date,time,startup,provider,model,in_tokens,out_tokens,cost\n")
        now = datetime.now()
        f.write(
            f"{now.date().isoformat()},{now.time().strftime('%H:%M:%S')},"
            f"{startup_id},{provider},{model},{in_tokens},{out_tokens},{cost:.6f}\n"
        )


def _sum_total_cost() -> float:
    if not Config.COST_CSV.exists():
        return 0.0
    total = 0.0
    with open(Config.COST_CSV, "r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            if i == 0:
                continue
            parts = line.strip().split(",")
            if len(parts) < 8:
                continue
            try:
                total += float(parts[7])
            except ValueError:
                continue
    return total


# ============================================================
# BOILERPLATE ZIP READER
# ============================================================

def read_boilerplate_manifest(path: Path) -> str:
    """
    Extract a structured manifest of what the boilerplate provides.

    Accepts either a ZIP file or a directory path.
    """
    if not path.exists():
        raise FileNotFoundError(f"Boilerplate not found: {path}")

    # Files we want to read in full (exact paths only)
    FULL_READ_FILES = {
        'README.md',
        'PLATFORM_CAPABILITIES.md',
        'CLAUDE_BUILD_DIRECTIVE.md',
        'P0_KERNEL_BUILD_DIRECTIVE.md',
        'saas-boilerplate/README.md',
        'saas-boilerplate/QUICKSTART.md',
        'saas-boilerplate/PLUGIN_ARCHITECTURE.md',
        'saas-boilerplate/DELIVERY_MANIFEST.md',
        'saas-boilerplate/directives/BUILD_DIRECTIVE.md',
        'saas-boilerplate/directives/backend_directive.md',
        'saas-boilerplate/directives/frontend_directive.md',
        'saas-boilerplate/directives/testing_directive.md',
        'teebu-shared-libs/README.md',
        'teebu-shared-libs/README_STRIPE_LIB.md',
        'teebu-shared-libs/GA4_SETUP_GUIDE.md',
    }


    def normalize(p: str) -> str:
        return p.replace('\\', '/').lstrip('./')

    bundle = []
    bundle.append("<<<BEGIN_BOILERPLATE_MANIFEST>>>")
    bundle.append("")

    if path.is_dir():
        # Directory mode
        all_names = []
        for root, _, files in os.walk(path):
            for file in files:
                file_path = Path(root) / file
                rel = normalize(str(file_path.relative_to(path)))
                all_names.append(rel)

        # Read full content for key files
        bundle.append("## FULL CONTENT: KEY DIRECTIVE AND README FILES")
        bundle.append("")
        for name in sorted(all_names):
            if name in FULL_READ_FILES:
                try:
                    content = (path / name).read_text(encoding='utf-8', errors='replace')
                    bundle.append(f"<<<BEGIN_FILE: {name}>>>")
                    bundle.append(content)
                    bundle.append(f"<<<END_FILE: {name}>>>")
                    bundle.append("")
                except Exception as e:
                    bundle.append(f"<<<SKIP: {name} — {e}>>>")

        # Intentionally omit file listings and full file tree to keep prompt size small

    else:
        # ZIP mode
        with zipfile.ZipFile(path, 'r') as zf:
            all_names = [normalize(n) for n in zf.namelist()]

            # Read full content for key files
            bundle.append("## FULL CONTENT: KEY DIRECTIVE AND README FILES")
            bundle.append("")
            for name in sorted(all_names):
                if name in FULL_READ_FILES:
                    try:
                        content = zf.read(name).decode('utf-8', errors='replace')
                        bundle.append(f"<<<BEGIN_FILE: {name}>>>")
                        bundle.append(content)
                        bundle.append(f"<<<END_FILE: {name}>>>")
                        bundle.append("")
                    except Exception as e:
                        bundle.append(f"<<<SKIP: {name} — {e}>>>")

            # Intentionally omit file listings and full file tree to keep prompt size small

    bundle.append("")
    bundle.append("<<<END_BOILERPLATE_MANIFEST>>>")
    manifest = '\n'.join(bundle)
    if len(manifest) > Config.MAX_MANIFEST_CHARS:
        truncated = manifest[:Config.MAX_MANIFEST_CHARS]
        truncated += "\n\n<<<TRUNCATED: BOILERPLATE MANIFEST EXCEEDED MAX SIZE>>>\n"
        return truncated
    return manifest


# ============================================================
# CLAUDE API CLIENT
# ============================================================

def call_claude(prompt: str) -> Tuple[str, Dict[str, int]]:
    """
    Call Claude API with retry logic.
    Returns extracted text content or raises on failure.
    """
    if not Config.ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY environment variable not set")

    payload = {
        "model":      Config.CLAUDE_MODEL,
        "max_tokens": Config.CLAUDE_MAX_TOKENS,
        "messages":   [{"role": "user", "content": prompt}]
    }

    headers = {
        "content-type":      "application/json",
        "x-api-key":         Config.ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01"
    }

    last_error = None
    for attempt in range(1, Config.MAX_RETRIES + 1):
        try:
            response = requests.post(
                Config.ANTHROPIC_API,
                json=payload,
                headers=headers,
                timeout=Config.REQUEST_TIMEOUT
            )

            if response.status_code in (400, 401, 403):
                response.raise_for_status()

            if response.status_code in (429, 500, 529):
                wait = Config.RETRY_SLEEP * attempt
                print_warning(f"API transient error {response.status_code} — retry {attempt}/{Config.MAX_RETRIES} in {wait}s")
                time.sleep(wait)
                last_error = f"HTTP {response.status_code}"
                continue

            response.raise_for_status()
            data = response.json()
            text = data['content'][0]['text']
            usage = data.get("usage", {}) or {}
            return text, usage

        except requests.exceptions.Timeout:
            print_warning(f"API timeout — retry {attempt}/{Config.MAX_RETRIES}")
            last_error = "Timeout"
            time.sleep(Config.RETRY_SLEEP)
            continue

        except requests.exceptions.RequestException as e:
            print_warning(f"API error — retry {attempt}/{Config.MAX_RETRIES}: {e}")
            last_error = str(e)
            time.sleep(Config.RETRY_SLEEP)
            continue

    raise RuntimeError(f"Claude API failed after {Config.MAX_RETRIES} attempts: {last_error}")


# ============================================================
# ANALYSIS PROMPT
# ============================================================

def call_openai(prompt: str) -> Tuple[str, Dict[str, int]]:
    """
    Call OpenAI Chat Completions with retry logic.
    Returns (text, usage dict).
    """
    if not Config.OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY environment variable not set")

    payload = {
        "model": Config.OPENAI_MODEL,
        "messages": [
            {"role": "system", "content": "You are a precise JSON-only assistant."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
    }

    headers = {
        "content-type": "application/json",
        "authorization": f"Bearer {Config.OPENAI_API_KEY}",
    }

    last_error = None
    for attempt in range(1, Config.MAX_RETRIES + 1):
        try:
            response = requests.post(
                Config.OPENAI_API,
                json=payload,
                headers=headers,
                timeout=Config.REQUEST_TIMEOUT
            )

            if response.status_code in (400, 401, 403):
                response.raise_for_status()

            if response.status_code in (429, 500, 529):
                wait = Config.RETRY_SLEEP * attempt
                print_warning(f"API transient error {response.status_code} — retry {attempt}/{Config.MAX_RETRIES} in {wait}s")
                time.sleep(wait)
                last_error = f"HTTP {response.status_code}"
                continue

            response.raise_for_status()
            data = response.json()
            text = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {}) or {}
            return text, usage

        except requests.exceptions.Timeout:
            print_warning(f"API timeout — retry {attempt}/{Config.MAX_RETRIES}")
            last_error = "Timeout"
            time.sleep(Config.RETRY_SLEEP)
            continue

        except requests.exceptions.RequestException as e:
            print_warning(f"API error — retry {attempt}/{Config.MAX_RETRIES}: {e}")
            last_error = str(e)
            time.sleep(Config.RETRY_SLEEP)
            continue

    raise RuntimeError(f"OpenAI API failed after {Config.MAX_RETRIES} attempts: {last_error}")

def build_analysis_prompt(intake_data: dict, boilerplate_manifest: str) -> str:
    """
    Build the prompt that asks Claude to evaluate boilerplate fit
    and produce a structured JSON verdict.
    """

    startup_id   = intake_data.get('startup_idea_id', 'unknown')
    startup_name = intake_data.get('startup_name', 'unknown')

    # Pull both blocks if available, fall back to hero_answers
    block_a = intake_data.get('block_a', {})
    block_b = intake_data.get('block_b', {})
    hero    = intake_data.get('hero_answers', {})

    return f"""You are a senior software architect evaluating whether a SaaS boilerplate
is a good fit for a specific business idea.

Your job is to:
1. Analyze the business intake data carefully
2. Review what the boilerplate already provides
3. Determine if this business fits the boilerplate architecture
4. If YES: produce a precise technical decomposition of what needs to be built
5. Output a structured JSON verdict

---

## BUSINESS INTAKE DATA

Startup ID:   {startup_id}
Startup Name: {startup_name}

### Block A (Tier 1 analysis):
{json.dumps(block_a, indent=2) if block_a else "Not present"}

### Block B (Tier 2 analysis):
{json.dumps(block_b, indent=2) if block_b else "Not present"}

### Hero Answers (founder Q&A):
{json.dumps(hero, indent=2) if hero else "Not present"}

---

## BOILERPLATE MANIFEST

The following is what the Teebu SaaS boilerplate already provides.
Read it carefully before making your verdict.

{boilerplate_manifest}

---

## YOUR ANALYSIS TASK

Answer these questions:

**FIT ASSESSMENT:**
1. Is this a web-based SaaS product? (boilerplate is FastAPI + React)
2. Does it need standard auth (login/signup)? (already built)
3. Does it need payments/subscriptions? (Stripe already built)
4. Does it need email marketing? (MailerLite already built)
5. Does it need analytics? (GA4 already built)
6. Is the core value in business logic, not infrastructure?
7. Are there any hard blockers? (native mobile, blockchain, real-time video, etc.)

**TECHNICAL DECOMPOSITION (only if YES):**
For each feature in the intake, identify:
- Exact filename for backend route (snake_case.py)
- Exact filename for frontend page (PascalCase.jsx)
- Key data models needed
- Any external APIs or integrations needed beyond what boilerplate provides
- Confidence level: HIGH (clear from intake) / MEDIUM (reasonable assumption) / LOW (ambiguous)

**AMBIGUITIES:**
List any features where the intake does not have enough detail for
deterministic implementation. Be specific about what is missing.

---

## FIT SCORE RUBRIC
Start at 10. Subtract:
-1 if auth is NOT needed
-1 if payments/subscriptions are NOT needed
-1 if email marketing is NOT needed
-1 if analytics are NOT needed
-1 if there are any ambiguities
-1 if any external dependencies are required beyond what the boilerplate provides
-2 if the core value is NOT standard CRUD/workflow (e.g., heavy realtime, mobile-only, video, blockchain)

You MUST show a brief score breakdown and compute the final fit_score.

## OUTPUT FORMAT

You MUST respond with ONLY a JSON object. No preamble. No explanation outside the JSON.
The JSON must parse cleanly.

{{
  "startup_id": "{startup_id}",
  "startup_name": "{startup_name}",
  "analyzed_at": "ISO_TIMESTAMP",
  "verdict": "YES" or "NO",
  "fit_score": 0-10,
  "fit_score_breakdown": ["Start 10", "-1 no auth", "...", "Final = X"],
  "fit_summary": "One sentence explaining the verdict",

  "boilerplate_covers": [
    "List of features the boilerplate already handles for this business"
  ],

  "business_layer": {{
    "backend_routes": [
      {{
        "filename": "snake_case.py",
        "route_prefix": "/api/filename",
        "purpose": "What this route does",
        "key_endpoints": ["GET /", "POST /", "DELETE /{{id}}"],
        "data_models": ["ModelName: field1 (type), field2 (type)"],
        "external_deps": ["Any external API or service needed"],
        "confidence": "HIGH | MEDIUM | LOW",
        "confidence_reason": "Why this confidence level"
      }}
    ],
    "frontend_pages": [
      {{
        "filename": "PascalCase.jsx",
        "route_path": "/dashboard/kebab-case",
        "purpose": "What this page shows/does",
        "key_components": ["List of UI elements needed"],
        "api_calls": ["Which backend routes it calls"],
        "confidence": "HIGH | MEDIUM | LOW",
        "confidence_reason": "Why this confidence level"
      }}
    ],
    "config_updates": {{
      "business_name": "Name for business_config.json",
      "tagline": "Tagline",
      "primary_color": "#hexcode or 'unknown'",
      "pricing_plans": ["Plan names and rough prices if known"],
      "notes": "Any other config changes needed"
    }}
  }},

  "ambiguities": [
    {{
      "feature": "Which feature is ambiguous",
      "missing": "What specific information is missing",
      "impact": "HIGH | MEDIUM | LOW",
      "suggestion": "What question to ask the founder to resolve this"
    }}
  ],

  "blockers": [
    "Only populated if verdict is NO — list hard architectural blockers"
  ],

  "recommendation": "2-3 sentences of concrete next-step advice"
}}

Respond with ONLY the JSON. No markdown fences. No explanation. Pure JSON.
"""


# ============================================================
# RESPONSE PARSER
# ============================================================

def parse_verdict(raw_text: str) -> dict:
    """
    Parse Claude's JSON response. Handles minor formatting issues.
    """
    # Strip markdown fences if Claude included them despite instructions
    text = raw_text.strip()
    if text.startswith('```'):
        text = re.sub(r'^```[a-z]*\n?', '', text)
        text = re.sub(r'\n?```$', '', text)
        text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        # Try to extract JSON block if there's preamble
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass
        raise ValueError(f"Could not parse Claude response as JSON: {e}\n\nRaw response:\n{text[:500]}")


# ============================================================
# RESULT PRINTER
# ============================================================

def print_verdict(result: dict):
    """Print a human-readable summary of the verdict to terminal."""

    verdict    = result.get('verdict', 'UNKNOWN')
    fit_score  = result.get('fit_score', 0)
    summary    = result.get('fit_summary', '')
    startup    = result.get('startup_name', '')
    rec        = result.get('recommendation', '')

    print_header(f"BOILERPLATE FIT CHECK — {startup}")

    # Big verdict line
    if verdict == 'YES':
        print(f"{Colors.BOLD}{Colors.GREEN}VERDICT: YES — USE BOILERPLATE{Colors.END}")
    else:
        print(f"{Colors.BOLD}{Colors.RED}VERDICT: NO — CUSTOM BUILD REQUIRED{Colors.END}")

    print(f"Fit Score: {fit_score}/10")
    print(f"Summary:   {summary}")
    print()

    # What boilerplate covers
    covers = result.get('boilerplate_covers', [])
    if covers:
        print(f"{Colors.BOLD}Boilerplate Already Handles:{Colors.END}")
        for item in covers:
            print_success(item)
        print()

    if verdict == 'YES':
        # Backend routes
        bl = result.get('business_layer', {})
        routes = bl.get('backend_routes', [])
        if routes:
            print(f"{Colors.BOLD}Backend Routes to Build ({len(routes)} files):{Colors.END}")
            for r in routes:
                conf_color = Colors.GREEN if r.get('confidence') == 'HIGH' else \
                             Colors.YELLOW if r.get('confidence') == 'MEDIUM' else Colors.RED
                print(f"  {conf_color}[{r.get('confidence','?')}]{Colors.END} "
                      f"business/backend/routes/{r.get('filename','?')} "
                      f"→ {r.get('route_prefix','')}")
                print(f"         {r.get('purpose','')}")
            print()

        # Frontend pages
        pages = bl.get('frontend_pages', [])
        if pages:
            print(f"{Colors.BOLD}Frontend Pages to Build ({len(pages)} files):{Colors.END}")
            for p in pages:
                conf_color = Colors.GREEN if p.get('confidence') == 'HIGH' else \
                             Colors.YELLOW if p.get('confidence') == 'MEDIUM' else Colors.RED
                print(f"  {conf_color}[{p.get('confidence','?')}]{Colors.END} "
                      f"business/frontend/pages/{p.get('filename','?')} "
                      f"→ {p.get('route_path','')}")
                print(f"         {p.get('purpose','')}")
            print()

    # Ambiguities
    ambiguities = result.get('ambiguities', [])
    if ambiguities:
        print(f"{Colors.BOLD}Ambiguities ({len(ambiguities)} items):{Colors.END}")
        for a in ambiguities:
            impact_color = Colors.RED if a.get('impact') == 'HIGH' else \
                           Colors.YELLOW if a.get('impact') == 'MEDIUM' else Colors.CYAN
            print(f"  {impact_color}[{a.get('impact','?')}]{Colors.END} "
                  f"{a.get('feature','?')}")
            print(f"         Missing: {a.get('missing','?')}")
            print(f"         Ask: {a.get('suggestion','?')}")
        print()

    # Blockers (NO verdict only)
    blockers = result.get('blockers', [])
    if blockers:
        print(f"{Colors.BOLD}Hard Blockers:{Colors.END}")
        for b in blockers:
            print_error(b)
        print()

    # Recommendation
    if rec:
        print(f"{Colors.BOLD}Recommendation:{Colors.END}")
        print(f"  {rec}")
        print()


# ============================================================
# MAIN
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description='Check if a business intake fits the Teebu SaaS boilerplate',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  ./check_boilerplate_fit.py \\
      intake_hero_runs/wynwood_thoroughbreds/wynwood_thoroughbreds.json \\
      /path/to/teebu-saas-platform.zip

  ./check_boilerplate_fit.py \\
      intake_hero_runs/wynwood_thoroughbreds/wynwood_thoroughbreds.json \\
      /path/to/teebu-saas-platform
        """
    )

    parser.add_argument(
        'intake_file',
        type=Path,
        help='Path to combined intake JSON (output of run_intake_v7.sh)'
    )
    parser.add_argument(
        'boilerplate_path',
        nargs='?',
        type=Path,
        default=Path('~/Documents/work/teebu-saas-platform').expanduser(),
        help='Path to teebu-saas-platform.zip or teebu-saas-platform/ directory'
    )
    parser.add_argument(
        '--boilerplate-path',
        dest='boilerplate_path_override',
        type=Path,
        default=None,
        help='Override boilerplate path (defaults to ~/Documents/work/teebu-saas-platform)'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Print raw model response to stdout'
    )

    args = parser.parse_args()

    # Validate API keys (ChatGPT default, Claude fallback)
    if not Config.OPENAI_API_KEY:
        print_error("OPENAI_API_KEY environment variable not set")
        print_info("Set it with: export OPENAI_API_KEY='sk-...'")
        sys.exit(1)
    if not Config.ANTHROPIC_API_KEY:
        print_error("ANTHROPIC_API_KEY environment variable not set")
        print_info("Set it with: export ANTHROPIC_API_KEY='sk-ant-...'")
        sys.exit(1)

    # Validate inputs
    if not args.intake_file.exists():
        print_error(f"Intake file not found: {args.intake_file}")
        sys.exit(1)

    boilerplate_path = args.boilerplate_path_override or args.boilerplate_path

    if not boilerplate_path.exists():
        print_error(f"Boilerplate not found: {boilerplate_path}")
        sys.exit(1)

    # Create output directory
    Config.OUTPUT_DIR.mkdir(exist_ok=True)

    print_header("BOILERPLATE FIT CHECKER")
    print_info(f"Intake:     {args.intake_file}")
    print_info(f"Boilerplate: {boilerplate_path}")

    # Load intake JSON
    print_info("Loading intake JSON...")
    with open(args.intake_file) as f:
        content = f.read()
    if content.strip().startswith('{'):
        intake_data = json.loads(content)
    else:
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            intake_data = json.loads(json_match.group(0))
        else:
            print_error(f"Could not parse intake JSON from: {args.intake_file}")
            sys.exit(1)

    startup_id = intake_data.get('startup_idea_id', 'unknown')
    print_success(f"Loaded intake: {startup_id}")

    # Read boilerplate manifest
    print_info("Reading boilerplate (ZIP or directory)...")
    try:
        boilerplate_manifest = read_boilerplate_manifest(boilerplate_path)
        print_success("Boilerplate manifest built")
        print_info(f"Boilerplate manifest size: {len(boilerplate_manifest):,} chars")
    except Exception as e:
        print_error(f"Failed to read boilerplate: {e}")
        sys.exit(1)

    # Build prompt
    prompt = build_analysis_prompt(intake_data, boilerplate_manifest)
    prompt_bytes = len(prompt.encode("utf-8"))
    print_info(f"Prompt size: {prompt_bytes:,} bytes")

    # Log prompt for debugging
    prompt_log = Config.OUTPUT_DIR / f'{startup_id}_analysis_prompt.log'
    with open(prompt_log, 'w') as f:
        f.write(f"[{datetime.now().isoformat()}]\n{prompt}\n")
    print_success(f"Prompt logged: {prompt_log.name}")

    # Call ChatGPT (fallback to Claude)
    print_info("Calling ChatGPT for analysis...")
    start_time = time.time()
    try:
        raw_response, usage = call_openai(prompt)
        provider = "chatgpt"
        model = Config.OPENAI_MODEL
    except Exception as e:
        print_warning(f"ChatGPT API call failed: {e}")
        print_info("Falling back to Claude for analysis...")
        try:
            raw_response, usage = call_claude(prompt)
            provider = "claude"
            model = Config.CLAUDE_MODEL
        except Exception as e2:
            print_error(f"Claude API call failed: {e2}")
            sys.exit(1)

    elapsed = time.time() - start_time
    print_success(f"Analysis complete in {elapsed:.1f}s")

    if provider == "chatgpt":
        in_tokens = int(usage.get("prompt_tokens", 0) or 0)
        out_tokens = int(usage.get("completion_tokens", 0) or 0)
        cost = (in_tokens * Config.OPENAI_INPUT_PER_MTOK + out_tokens * Config.OPENAI_OUTPUT_PER_MTOK) / 1_000_000
    else:
        in_tokens = int(usage.get("input_tokens", 0) or 0)
        out_tokens = int(usage.get("output_tokens", 0) or 0)
        cost = (in_tokens * Config.CLAUDE_INPUT_PER_MTOK + out_tokens * Config.CLAUDE_OUTPUT_PER_MTOK) / 1_000_000

    _append_cost_row(startup_id, provider, model, in_tokens, out_tokens, cost)
    total_cost = _sum_total_cost()
    print_info(f"AI cost: ${cost:.4f} (cumulative: ${total_cost:.4f})")
    print_info(f"Cost CSV: {Config.COST_CSV.resolve()}")

    # Log raw response
    raw_log = Config.OUTPUT_DIR / f'{startup_id}_raw_response.log'
    with open(raw_log, 'w') as f:
        f.write(f"[{datetime.now().isoformat()}]\n{raw_response}\n")
    if args.verbose:
        print_info("RAW OUTPUT BEGIN")
        print(raw_response)
        print_info("RAW OUTPUT END")

    # Parse verdict
    print_info("Parsing verdict...")
    try:
        result = parse_verdict(raw_response)
    except ValueError as e:
        print_error(f"Failed to parse Claude response: {e}")
        print_warning(f"Raw response saved to: {raw_log}")
        sys.exit(1)

    # Inject timestamp if Claude didn't include one
    if not result.get('analyzed_at'):
        result['analyzed_at'] = datetime.now().isoformat()

    # Save result JSON
    output_file = Config.OUTPUT_DIR / f'{startup_id}_boilerplate_check.json'
    with open(output_file, 'w') as f:
        json.dump(result, f, indent=2)

    # Print human-readable verdict
    print_verdict(result)

    # Final file pointer
    verdict = result.get('verdict', 'UNKNOWN')
    print(f"{Colors.BOLD}Output saved:{Colors.END} {output_file}")
    print()

    score = result.get('fit_score', 0)
    if verdict == 'YES' and score >= 7:
        print(f"{Colors.BOLD}{Colors.GREEN}Next step:{Colors.END} Run the test harness with --use-boilerplate")
        print(f"  Pass this file to the harness: {output_file}")
        print()
        sys.exit(0)
    if verdict == 'YES' and score < 7:
        print(f"{Colors.BOLD}{Colors.YELLOW}Next step:{Colors.END} Fit score below 7 — treat as NO for automation")
        print()
        sys.exit(1)
    else:
        print(f"{Colors.BOLD}{Colors.YELLOW}Next step:{Colors.END} Review blockers above and plan custom build")
        print()
        sys.exit(1)


if __name__ == '__main__':
    main()
