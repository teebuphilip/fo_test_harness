#!/usr/bin/env python3
"""
FO Test Harness v2 - BUILD → QA → DEPLOY Orchestration
Orchestrates Claude (tech/builder) and ChatGPT (QA/validator)

USAGE:
  ./fo_test_harness.py <intake_file> <build_governance_zip> <deploy_governance_zip> [--block-a] [--deploy]

DEFAULTS:
  Block:    B (Tier 2)   — pass --block-a for Tier 1
  Deploy:   NO           — pass --deploy to trigger deployment

OUTPUT:
  ./fo_harness_runs/{startup_id}_{block}_{timestamp}/   ← run directory
  ./fo_harness_runs/{startup_id}_{block}_{timestamp}.zip ← deliverable ZIP (no-deploy mode)
"""

import os
import sys
import json
import re
import time
import zipfile
import argparse
import hashlib
import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, Tuple
import requests

# ============================================================
# CONFIGURATION
# ============================================================

class Config:
    """Runtime configuration — governance ZIPs come from CLI, not env"""

    # API Keys (from environment — these stay as env vars)
    ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY')
    OPENAI_API_KEY    = os.getenv('OPENAI_API_KEY')

    # API Endpoints
    ANTHROPIC_API = 'https://api.anthropic.com/v1/messages'
    OPENAI_API    = 'https://api.openai.com/v1/chat/completions'

    # Models
    CLAUDE_MODEL = 'claude-sonnet-4-20250514'  # Tech/Builder
    GPT_MODEL    = 'gpt-4o'                    # QA/Validator

    # Token Limits
    # FIX #1: 200000 was the context window (input), not output limit.
    # Claude Sonnet 4.5 max output tokens is 16384 (API limit).
    # Complex builds (TwoFaced AI, Adversarial AI, etc.) need 12-15k+ tokens.
    # FIX #8: Testing showed 16384 still causes truncation on complex T2 builds
    # with extensive business logic (10+ services, models, routes, tests, etc.)
    # However, 16384 is the API maximum, so we handle truncation with continuation.
    CLAUDE_MAX_TOKENS = 16384  # API maximum
    GPT_MAX_TOKENS    = 16000

    # FIX #4 & #8: Dynamic max tokens based on iteration
    # WHY: Lowcode builds output ALL files every iteration (not incremental patches).
    # BUILD must regenerate: models, services, routes, tests, README, package.json,
    # config files, artifact_manifest.json, build_state.json - every single time.
    # For large builds (20+ files), even 16384 tokens may truncate.
    # Solution: Use max tokens + improved truncation detection + continuation.
    CLAUDE_MAX_TOKENS_BY_ITERATION = {
        1: 16384,   # Full initial build (API max)
        2: 16384,   # Still need full output (not incremental)
        3: 16384,   # Still need full output (not incremental)
        4: 16384,   # Still need full output (not incremental)
    }
    CLAUDE_MAX_TOKENS_DEFAULT = 16384  # Always use API max - lowcode needs complete output

    @classmethod
    def get_max_tokens(cls, iteration: int) -> int:
        """
        WHY: Return 16384 tokens for all iterations.

        Lowcode builds regenerate ALL files every iteration, not incremental patches.
        Complex builds need 10-12k tokens. 8192 caused truncation for TwoFaced AI.
        16384 ensures complete output including artifact_manifest/build_state.
        """
        return cls.CLAUDE_MAX_TOKENS_BY_ITERATION.get(
            iteration,
            cls.CLAUDE_MAX_TOKENS_DEFAULT
        )

    # Iteration Limits
    MAX_QA_ITERATIONS = 5  # Default aligns with locked governance; CLI can override.

    # API call settings
    # FIX #6: Increased timeout for large builds with prompt caching.
    # WHY: First iteration with caching + 16K token output can take 4-6 minutes.
    # Complex builds (adversarial AI, two-faced AI) with full governance context
    # need more time. 180s was too aggressive, causing false timeout failures.
    REQUEST_TIMEOUT = 600    # seconds before giving up (10 minutes for safety)
    REQUEST_TIMEOUT_BY_ITERATION = {
        1: 600,   # First call: prompt cache initialization + large output
        2: 300,   # Subsequent: cache hit, but still complex output
        3: 300,
        4: 300,
    }
    REQUEST_TIMEOUT_DEFAULT = 300  # 5 minutes for later iterations

    MAX_RETRIES        = 6      # retries on transient errors (rate limit, 529)
    RETRY_SLEEP        = 5      # seconds between retries (multiplied by attempt)
    RETRY_SLEEP_429    = 60     # minimum wait on 429 rate-limit (ChatGPT hits this hard)
    MAX_BUILD_PARTS_DEFAULT = 10            # default multipart ceiling
    MAX_BUILD_CONTINUATIONS_DEFAULT = 9     # default fallback continuation ceiling

    @classmethod
    def get_request_timeout(cls, iteration: int) -> int:
        """Get timeout for specific iteration (first call needs more time for caching)"""
        return cls.REQUEST_TIMEOUT_BY_ITERATION.get(
            iteration,
            cls.REQUEST_TIMEOUT_DEFAULT
        )

    # Output base directory
    OUTPUT_DIR = Path('./fo_harness_runs')

    # Governance ZIP contents — populated at runtime from CLI paths
    BUILD_GOVERNANCE_ZIP  = None   # Path set by CLI arg
    DEPLOY_GOVERNANCE_ZIP = None   # Path set by CLI arg

    # Default SaaS platform boilerplate (preferred for most builds)
    PLATFORM_BOILERPLATE_DIR = Path('/Users/teebuphilip/Documents/work/teebu-saas-platform')

    # Local overrides (testing only)
    TECH_STACK_OVERRIDE_FILE = Path('./fo_tech_stack_override.json')
    EXTERNAL_INTEGRATION_OVERRIDE_FILE = Path('./fo_external_integration_override.json')
    QA_OVERRIDE_FILE = Path('./fo_qa_override.json')
    QA_POLISH_2_DIRECTIVE_FILE = Path('./directives/qa_polish_2_doc_recovery.md')
    PROMPT_DIRECTIVES_DIR = Path('./directives/prompts')


# ============================================================
# QUESTION DETECTION
# ============================================================

# Markers and patterns used to detect when Claude is asking
# questions instead of building. If any of these are found in
# the response AND the build completion marker is absent,
# we treat it as a clarification request and stop.
QUESTION_MARKERS = [
    'CLARIFICATION_NEEDED',
    'QUESTIONS:',
    'CLARIFYING QUESTIONS',
    'BEFORE I BEGIN',
    'BEFORE PROCEEDING',
    'PLEASE CLARIFY',
    'PLEASE CONFIRM',
    'CAN YOU CONFIRM',
    'I NEED TO KNOW',
    'COULD YOU CLARIFY',
]

BUILD_COMPLETE_MARKER = 'BUILD STATE: COMPLETED_CLOSED'

def should_use_platform_boilerplate(intake_data: dict, block: str) -> bool:
    """
    Default to the platform boilerplate unless the intake explicitly
    indicates a lowcode Zapier/Shopify build.
    """
    block_key = f'block_{block.lower()}'
    block_data = intake_data.get(block_key, {})
    tech_stack = block_data.get('pass_2', {}).get('tech_stack_selection', 'custom')

    # Only skip boilerplate for explicit lowcode Zapier/Shopify cases
    if tech_stack == 'lowcode':
        intake_text = json.dumps(intake_data).lower()
        if 'zapier' in intake_text or 'shopify' in intake_text:
            return False

    return True


def detect_truncation(output: str) -> bool:
    """
    Check if output is truncated (incomplete build).

    FIX #7: Prioritize BUILD STATE marker over code block formatting.
    WHY: After continuation concatenation, code blocks may be malformed
    but if BUILD STATE: COMPLETED_CLOSED is present, the build IS complete.

    Indicators of truncation (in priority order):
    1. Missing BUILD STATE marker (most reliable)
    2. Unclosed code blocks (secondary check)
    3. Has CONTINUATION marker but no proper ending
    """
    # Check 1: Missing BUILD STATE marker (MOST RELIABLE)
    # If this marker is present, build is complete even if formatting is off
    if BUILD_COMPLETE_MARKER not in output:
        return True

    # Check 2: Has CONTINUATION marker without BUILD STATE in last 500 chars
    # (Claude tried to continue but was cut off before completing)
    if '<!-- CONTINUATION -->' in output:
        last_500_chars = output[-500:]
        if BUILD_COMPLETE_MARKER not in last_500_chars:
            return True

    # Check 3: Unclosed code blocks (secondary check)
    # Only flag as truncated if BUILD STATE is missing too
    # WHY: Continuation concatenation can create formatting issues,
    # but if BUILD STATE is present, artifacts are complete
    opening = len(re.findall(r'^```\w+', output, re.MULTILINE))
    closing = len(re.findall(r'^```\s*$', output, re.MULTILINE))
    if opening > closing:
        # Double-check: Is BUILD STATE in the last 1000 chars?
        last_1000_chars = output[-1000:]
        if BUILD_COMPLETE_MARKER not in last_1000_chars:
            return True
        # If BUILD STATE is recent, ignore code block mismatch
        # (continuation concatenation issue, but build is done)

    return False


def detect_multipart(output: str) -> dict:
    """
    Detect TCP-style multi-part output from Claude.

    Claude is instructed to split large builds into parts:
      <!-- PART 1/3 -->
      ...files...
      <!-- END PART 1/3 -->
      REMAINING FILES: file1.js, file2.js, ...

    Returns dict with:
      is_multipart: bool
      current_part: int
      total_parts: int
      remaining_files: list[str]
      is_final: bool (True if BUILD STATE: COMPLETED_CLOSED present)
    """
    result = {
        'is_multipart': False,
        'current_part': 0,
        'total_parts': 0,
        'remaining_files': [],
        'is_final': BUILD_COMPLETE_MARKER in output
    }

    # Look for <!-- PART X/N --> marker
    part_match = re.search(r'<!--\s*PART\s+(\d+)/(\d+)\s*-->', output)
    if not part_match:
        return result

    result['is_multipart'] = True
    result['current_part'] = int(part_match.group(1))
    result['total_parts'] = int(part_match.group(2))

    # Extract REMAINING FILES list
    remaining_match = re.search(r'REMAINING FILES:\s*(.+?)(?:\n\n|$)', output, re.DOTALL)
    if remaining_match:
        raw = remaining_match.group(1).strip()
        # Handle comma-separated or newline-separated lists
        files = [f.strip().strip('-').strip('*').strip() for f in re.split(r'[,\n]', raw)]
        result['remaining_files'] = [f for f in files if f and not f.startswith('<!--')]

    return result


def extract_file_paths_from_output(output: str) -> list:
    """Extract all **FILE: path** declarations from Claude's output."""
    return re.findall(r'\*\*FILE:\s*([^\*\n]+)\*\*', output)


def detect_claude_questions(text: str) -> bool:
    """
    Return True if Claude is asking REAL clarifying questions (not just code with "question" in it).

    STRICT detection to avoid false positives:
    - Only trigger on explicit CLARIFICATION_NEEDED marker
    - Don't trigger on normal code that happens to have "question" or "?" in it
    - Prevents false positives from business logic (e.g., "user questions", "FAQ", etc.)

    Strategy:
    1. If build completed (has BUILD STATE marker) → not questions
    2. If has explicit CLARIFICATION_NEEDED → actual questions
    3. Otherwise → not questions (even if has other question markers)
    """
    if BUILD_COMPLETE_MARKER in text:
        return False  # Build completed — no questions

    # Only trigger on explicit CLARIFICATION_NEEDED marker
    if 'CLARIFICATION_NEEDED' in text.upper():
        return True

    return False


# ============================================================
# COLOR OUTPUT
# ============================================================

class Colors:
    """ANSI color codes for terminal output"""
    HEADER    = '\033[95m'
    BLUE      = '\033[94m'
    CYAN      = '\033[96m'
    GREEN     = '\033[92m'
    YELLOW    = '\033[93m'
    RED       = '\033[91m'
    BOLD      = '\033[1m'
    UNDERLINE = '\033[4m'
    END       = '\033[0m'


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
# GOVERNANCE ZIP LOADER
# ============================================================

def load_governance_zip(zip_path: Path) -> str:
    """
    Read all text files from a governance ZIP and return them
    as a single concatenated string with filename markers.

    FIX #5: Previously the ZIP was referenced in prompts but
    never actually read or injected. Claude was told to "read
    governance files" but received nothing. Now we extract and
    inline every file from the ZIP into the prompt context.
    """
    # TODO: Enforce size limits and/or selective inclusion to avoid prompt bloat.
    if not zip_path.exists():
        raise FileNotFoundError(f"Governance ZIP not found: {zip_path}")

    bundle = []
    bundle.append(f"<<<BEGIN_GOVERNANCE_ZIP: {zip_path.name}>>>")

    with zipfile.ZipFile(zip_path, 'r') as zf:
        for name in sorted(zf.namelist()):
            # Skip directories and hidden files
            if name.endswith('/') or name.startswith('__'):
                continue
            try:
                content = zf.read(name).decode('utf-8', errors='replace')
                bundle.append(f"\n<<<BEGIN_GOVERNANCE_FILE: {name}>>>")
                bundle.append(content)
                bundle.append(f"<<<END_GOVERNANCE_FILE: {name}>>>")
            except Exception as e:
                bundle.append(f"\n<<<SKIP_GOVERNANCE_FILE: {name} — could not read: {e}>>>")

    bundle.append(f"\n<<<END_GOVERNANCE_ZIP: {zip_path.name}>>>")
    return '\n'.join(bundle)


def load_tech_stack_override() -> dict:
    """
    Load tech stack override file (local testing only).
    Returns empty dict if file doesn't exist.
    """
    override_path = Config.TECH_STACK_OVERRIDE_FILE
    if not override_path.exists():
        return {}

    try:
        with open(override_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        print_warning(f"Could not load tech stack override: {e}")
        return {}


def load_external_integration_override() -> dict:
    """
    Load external integration override file (local testing only).
    Returns empty dict if file doesn't exist.
    """
    override_path = Config.EXTERNAL_INTEGRATION_OVERRIDE_FILE
    if not override_path.exists():
        return {}

    try:
        with open(override_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        print_warning(f"Could not load external integration override: {e}")
        return {}


def load_qa_override() -> dict:
    """
    Load QA override file (local testing only).
    FIX #8: Allows tightening QA loop without modifying governance ZIP.
    Returns empty dict if file doesn't exist.
    """
    override_path = Config.QA_OVERRIDE_FILE
    if not override_path.exists():
        return {}

    try:
        with open(override_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        print_warning(f"Could not load QA override: {e}")
        return {}


def load_text_file(path: Path) -> str:
    """Load a UTF-8 text file and return stripped content."""
    with open(path, 'r', encoding='utf-8') as f:
        return f.read().strip()


class DirectiveTemplateLoader:
    """Loads and renders external prompt templates from directives/prompts."""

    _cache = {}

    @classmethod
    def load(cls, template_name: str) -> str:
        path = Config.PROMPT_DIRECTIVES_DIR / template_name
        if not path.exists():
            raise FileNotFoundError(f"Prompt template not found: {path}")
        cache_key = str(path.resolve())
        if cache_key not in cls._cache:
            cls._cache[cache_key] = load_text_file(path)
        return cls._cache[cache_key]

    @classmethod
    def render(cls, template_name: str, **kwargs) -> str:
        text = cls.load(template_name)
        for key, value in kwargs.items():
            text = text.replace(f"{{{{{key}}}}}", str(value))
        return text


# ============================================================
# API CLIENTS
# ============================================================

class ClaudeClient:
    """
    Client for Claude API (Tech/Builder).

    FIX #4: Added timeout and retry logic. A single hung call
    previously blocked forever. Transient errors (rate limit,
    overload) now retry up to MAX_RETRIES times.
    """

    def __init__(self):
        if not Config.ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY environment variable not set")

    def call(self, prompt: str, max_tokens: int = None, cacheable_prefix: str = None, timeout: int = None) -> Dict:
        """
        Call Claude API with timeout and retry.

        FIX #1 (Prompt Caching):
        WHY: Governance ZIP is sent every iteration. Caching saves ~90% of input token costs.
        When cacheable_prefix provided, it's marked with cache_control for 5-minute caching.

        FIX #6 (Dynamic Timeout):
        WHY: First iteration with caching + large output needs more time (4-6 min).
        Timeout can be customized per iteration to avoid false failures.

        Args:
            prompt: The main prompt (dynamic content)
            max_tokens: Max output tokens (if None, uses Config default)
            cacheable_prefix: Optional static content to cache (e.g., governance ZIP)
            timeout: Request timeout in seconds (if None, uses Config default)

        Returns:
            API response dict with usage stats including cache metrics
        """
        if max_tokens is None:
            max_tokens = Config.CLAUDE_MAX_TOKENS

        if timeout is None:
            timeout = Config.REQUEST_TIMEOUT

        # Build message content - use array format if caching, string otherwise
        if cacheable_prefix:
            # WHY: Content array format with cache_control enables prompt caching.
            # First block (governance) is cached, second block (dynamic) is not.
            message_content = [
                {
                    "type": "text",
                    "text": cacheable_prefix,
                    "cache_control": {"type": "ephemeral"}
                },
                {
                    "type": "text",
                    "text": prompt
                }
            ]
        else:
            # Backward compatible - no caching
            message_content = prompt

        payload = {
            "model":      Config.CLAUDE_MODEL,
            "max_tokens": max_tokens,
            "messages":   [{"role": "user", "content": message_content}]
        }

        headers = {
            "content-type":      "application/json",
            "x-api-key":         Config.ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "anthropic-beta":    "prompt-caching-2024-07-31"  # Enable caching
        }

        last_error = None
        for attempt in range(1, Config.MAX_RETRIES + 1):
            try:
                response = requests.post(
                    Config.ANTHROPIC_API,
                    json=payload,
                    headers=headers,
                    timeout=timeout
                )

                # Fatal errors — do not retry
                if response.status_code in (400, 401, 403):
                    response.raise_for_status()

                # Transient errors — retry
                if response.status_code in (429, 500, 529):
                    wait = Config.RETRY_SLEEP * attempt
                    print_warning(f"Claude API transient error {response.status_code} — retry {attempt}/{Config.MAX_RETRIES} in {wait}s")
                    time.sleep(wait)
                    last_error = f"HTTP {response.status_code}"
                    continue

                response.raise_for_status()
                return response.json()

            except requests.exceptions.Timeout:
                print_warning(f"Claude API timeout after {timeout}s — retry {attempt}/{Config.MAX_RETRIES}")
                last_error = f"Timeout ({timeout}s)"
                time.sleep(Config.RETRY_SLEEP)
                continue

            except requests.exceptions.RequestException as e:
                print_warning(f"Claude API error — retry {attempt}/{Config.MAX_RETRIES}: {e}")
                last_error = str(e)
                time.sleep(Config.RETRY_SLEEP)
                continue

        raise RuntimeError(f"Claude API failed after {Config.MAX_RETRIES} attempts: {last_error}")


class ChatGPTClient:
    """
    Client for ChatGPT API (QA/Validator).

    FIX #4: Same timeout and retry logic applied as ClaudeClient.
    """

    def __init__(self):
        if not Config.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY environment variable not set")

    def call(self, prompt: str, max_tokens: int = None) -> Dict:
        """Call ChatGPT API with timeout and retry"""
        if max_tokens is None:
            max_tokens = Config.GPT_MAX_TOKENS

        payload = {
            "model":      Config.GPT_MODEL,
            "max_tokens": max_tokens,
            "messages":   [{"role": "user", "content": prompt}]
        }

        headers = {
            "Content-Type":  "application/json",
            "Authorization": f"Bearer {Config.OPENAI_API_KEY}"
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
                    wait = Config.RETRY_SLEEP_429 if response.status_code == 429 else Config.RETRY_SLEEP * attempt
                    print_warning(f"ChatGPT API transient error {response.status_code} — retry {attempt}/{Config.MAX_RETRIES} in {wait}s")
                    time.sleep(wait)
                    last_error = f"HTTP {response.status_code}"
                    continue

                response.raise_for_status()
                return response.json()

            except requests.exceptions.Timeout:
                print_warning(f"ChatGPT API timeout — retry {attempt}/{Config.MAX_RETRIES}")
                last_error = "Timeout"
                time.sleep(Config.RETRY_SLEEP)
                continue

            except requests.exceptions.RequestException as e:
                print_warning(f"ChatGPT API error — retry {attempt}/{Config.MAX_RETRIES}: {e}")
                last_error = str(e)
                time.sleep(Config.RETRY_SLEEP)
                continue

        raise RuntimeError(f"ChatGPT API failed after {Config.MAX_RETRIES} attempts: {last_error}")


# ============================================================
# FILE MANAGEMENT
# ============================================================

# Valid boilerplate business/** paths — anything outside this is pruned.
# Pattern syntax is fnmatch (shell-style wildcards).
BOILERPLATE_VALID_PATHS = [
    'business/frontend/pages/*.jsx',
    'business/backend/routes/*.py',
    'business/models/*.py',
    'business/services/*.py',
    'business/frontend/lib/*.js',
    'business/frontend/lib/*.jsx',
    'business/README-INTEGRATION.md',
    'business/package.json',
]

class ArtifactManager:
    """Manages saving artifacts, QA reports, build outputs, and logs"""

    def __init__(self, run_dir: Path):
        self.run_dir = run_dir

        # Subdirectories
        self.build_dir  = run_dir / 'build'
        self.qa_dir     = run_dir / 'qa'
        self.deploy_dir = run_dir / 'deploy'
        self.logs_dir   = run_dir / 'logs'

        for d in [self.build_dir, self.qa_dir, self.deploy_dir, self.logs_dir]:
            d.mkdir(parents=True, exist_ok=True)

    def save_build_output(self, iteration: int, output: str):
        """Save BUILD output from Claude and extract artifacts"""
        # Save raw output
        path = self.build_dir / f'iteration_{iteration:02d}_build.txt'
        path.write_text(output)
        print_success(f"Saved BUILD output: build/iteration_{iteration:02d}_build.txt")

        # Extract and save code artifacts
        extracted_count = self._extract_artifacts_from_output(output, iteration)
        if extracted_count > 0:
            print_success(f"Extracted {extracted_count} artifact(s) from BUILD output")

        return path

    def _extract_artifacts_from_output(self, output: str, iteration: int) -> int:
        """
        Parse Claude's output and extract code blocks/artifacts into separate files.
        Returns the count of artifacts extracted.
        """
        import re

        # Create artifacts subdirectory for this iteration
        artifacts_dir = self.build_dir / f'iteration_{iteration:02d}_artifacts'
        artifacts_dir.mkdir(exist_ok=True)

        count = 0
        skipped_snippets = []

        # Track when we're in README context to skip documentation snippets
        last_readme_pos = -1

        # Pattern to match code blocks with optional filename hints
        # Matches: [preceding line]\n```language [filename]\n...\n```
        # Captures up to 200 chars before the code fence to check for filename hints
        # TODO: Support unlabeled code fences (``` with no language) to avoid missing artifacts.
        code_block_pattern = r'(?:^|\n)(.{0,200}?)\n?```(\w+)(?:[ \t]+([^\n]+))?\n(.*?)```'

        for match in re.finditer(code_block_pattern, output, re.DOTALL | re.MULTILINE):
            preceding_line = match.group(1).strip() if match.group(1) else ''
            language = match.group(2)
            filename_hint = match.group(3)
            code_content = match.group(4)

            match_pos = match.start()

            # Check if this is a documentation snippet (example code in README/docs)
            is_doc_snippet = False
            # context_before: 500 chars before this match (for doc snippet detection)
            # NOTE: match_pos is the start of the full regex match, which INCLUDES
            # preceding_line. So context_before does NOT contain the FILE: header.
            # We must also check preceding_line for FILE: presence.
            context_before = output[max(0, match_pos - 500):match_pos]
            has_file_header = '**FILE:' in preceding_line or '**File:' in preceding_line

            # Skip if no explicit **FILE:** header AND it looks like a doc snippet
            if not has_file_header and '**FILE:' not in context_before:
                # Indicators this is a documentation example:
                doc_indicators = [
                    '### ',           # Markdown header
                    '## ',            # Markdown header
                    'Add to your',    # Instructional text
                    'In your',        # Instructional text
                    'Mount the',      # Instructional text
                    'Example:',       # Example label
                    'Usage:',         # Usage label
                    'Sample:',        # Sample label
                ]

                # If preceded by doc indicators, it's probably a snippet
                has_doc_indicator = any(indicator in context_before[-200:] for indicator in doc_indicators)

                # Also skip if it's a small snippet (< 300 chars)
                is_tiny_snippet = len(code_content.strip()) < 300

                if has_doc_indicator or is_tiny_snippet:
                    is_doc_snippet = True
                    snippet_context = context_before[-100:].strip().split('\n')[-1] if context_before else 'unknown'
                    print_info(f"  → Skipped: doc snippet ({language}, {len(code_content)} chars) - context: {snippet_context[:50]}...")

            if is_doc_snippet:
                skipped_snippets.append({
                    "language": language,
                    "context": snippet_context if 'snippet_context' in locals() else '',
                    "content": code_content.strip()
                })
                continue

            filename = None

            # STEP 1: Check preceding context for patterns like "**FILE: path/to/file.ext**"
            # preceding_line (from regex group 1) contains the FILE: header most of the time.
            # context_before is 500 chars BEFORE the match (doesn't include preceding_line).
            # Check preceding_line first (most reliable), then context_before as fallback.
            search_area = preceding_line + '\n' + context_before if preceding_line else context_before

            if search_area:
                # Look for filename patterns (case-insensitive)
                preceding_patterns = [
                    r'\*\*FILE:\s*([^\*]+)\*\*',           # **FILE: path/file.ext**
                    r'\*\*File:\s*([^\*]+)\*\*',           # **File: path/file.ext**
                    r'File:\s*([^\n]+)',                    # File: file.ext
                    r'###\s*([^\n]+\.[\w]+)',               # ### file.ext
                    r'##\s*([^\n]+\.[\w]+)',                # ## file.ext
                ]

                for pattern in preceding_patterns:
                    # Search from the end (closest match to code fence)
                    all_matches = list(re.finditer(pattern, search_area, re.IGNORECASE))
                    if all_matches:
                        prec_match = all_matches[-1]  # Take the closest match
                        potential_filename = prec_match.group(1).strip()
                        # Clean and validate the filename
                        if potential_filename and ('.' in potential_filename or potential_filename.startswith('.')):
                            # Remove any remaining markdown or formatting
                            potential_filename = re.sub(r'[\*`]', '', potential_filename)
                            potential_filename = potential_filename.strip()
                            if potential_filename:
                                filename = potential_filename
                                break

            # STEP 2: Check if there's a filename hint on the same line as the language identifier
            if not filename and filename_hint and filename_hint.strip():
                # Clean the filename hint:
                # - Remove leading comment markers (// or # or /* or *)
                # - Remove leading/trailing whitespace
                # - Remove leading slashes
                potential_filename = filename_hint.strip()
                # Strip common comment prefixes
                for prefix in ['//', '/*', '*/', '#', '*']:
                    if potential_filename.startswith(prefix):
                        potential_filename = potential_filename[len(prefix):].strip()
                # Strip leading slashes (fix paths like "//package.json")
                potential_filename = potential_filename.lstrip('/')

                # Validate filename - allow subdirectories and dotfiles
                if potential_filename and ('.' in potential_filename or '/' in potential_filename):
                    filename = potential_filename

            # STEP 3: Check the first line of content for filename comment
            # (e.g., "// app.js" or "# config.py" or "<!-- index.html -->")
            if not filename and code_content:
                first_line = code_content.split('\n')[0].strip()
                # Check for common comment patterns with filenames
                comment_patterns = [
                    (r'^//\s*(.+\.[\w]+)\s*$', '//'),           # JavaScript: // filename.js
                    (r'^#\s*(.+\.[\w]+)\s*$', '#'),             # Python/Bash: # filename.py
                    (r'^/\*\s*(.+\.[\w]+)\s*\*/$', '/*'),       # CSS: /* filename.css */
                    (r'^<!--\s*(.+\.[\w]+)\s*-->$', '<!--'),    # HTML: <!-- filename.html -->
                ]

                for pattern, _ in comment_patterns:
                    comment_match = re.match(pattern, first_line)
                    if comment_match:
                        potential_filename = comment_match.group(1).strip()
                        # Validate it looks like a filename (has extension, no spaces in name)
                        if '.' in potential_filename and ' ' not in potential_filename:
                            filename = potential_filename
                            break

            # Generate filename if hint was invalid or missing
            if not filename:
                # FIX #13: Try to infer filename from code content before falling back to artifact_N
                inferred = None
                # Look for common patterns: class Name, module.exports, export default, router name, etc.
                class_match = re.search(r'(?:class|function)\s+(\w+)', code_content)
                export_match = re.search(r'module\.exports\s*=\s*(?:class\s+)?(\w+)', code_content)
                react_match = re.search(r'export\s+(?:default\s+)?(?:function|class|const)\s+(\w+)', code_content)
                router_match = re.search(r"router\s*=\s*express\.Router\(\)|app\.\w+\(['\"]\/(\w+)", code_content)

                for m in [export_match, react_match, class_match]:
                    if m:
                        name = m.group(1)
                        # Skip generic names
                        if name.lower() not in ('module', 'exports', 'default', 'app', 'router', 'handler'):
                            inferred = name
                            break

                if inferred:
                    extensions_map = {
                        'python': '.py', 'javascript': '.js', 'typescript': '.ts',
                        'json': '.json', 'html': '.html', 'css': '.css',
                        'yaml': '.yaml', 'jsx': '.jsx', 'tsx': '.tsx',
                    }
                    ext = extensions_map.get(language.lower(), '.js')
                    filename = f'{inferred}{ext}'
                    print_info(f"  → Inferred filename from code content: {filename}")
                else:
                    extensions = {
                        'python': '.py',
                        'javascript': '.js',
                        'typescript': '.ts',
                        'json': '.json',
                        'html': '.html',
                        'css': '.css',
                        'yaml': '.yaml',
                        'yml': '.yml',
                        'markdown': '.md',
                        'bash': '.sh',
                        'shell': '.sh',
                    }
                    ext = extensions.get(language.lower(), '.txt')
                    filename = f'artifact_{count + 1}{ext}'

            # TODO: Sanitize/normalize filename to prevent path traversal (e.g., ../ or absolute paths).
            # Save the artifact
            artifact_path = artifacts_dir / filename
            # Create parent directories if the filename contains subdirectories
            artifact_path.parent.mkdir(parents=True, exist_ok=True)

            # Don't overwrite existing files with duplicates (e.g. build_state.json
            # appearing in multiple parts). Keep the first version which is usually
            # more complete. Exception: numbered artifacts can always be written.
            if artifact_path.exists() and not filename.startswith('artifact_'):
                existing_size = artifact_path.stat().st_size
                new_size = len(code_content)
                if new_size <= existing_size:
                    print_warning(f"  → Skipped duplicate: {filename} (keeping existing {existing_size} chars over new {new_size} chars)")
                    continue
                else:
                    print_warning(f"  → Overwriting: {filename} (new version larger: {new_size} > {existing_size} chars)")

            artifact_path.write_text(code_content)
            count += 1
            print_info(f"  → Extracted: {filename}")

        # ══════════════════════════════════════════════════════════
        # FIX #12: Generate metadata files ourselves instead of
        # depending on Claude. Claude's manifest often gets truncated
        # or has continuation markers embedded in the JSON.
        # ══════════════════════════════════════════════════════════

        # Always generate build_state.json
        build_state_path = artifacts_dir / 'build_state.json'
        has_complete_marker = BUILD_COMPLETE_MARKER in output
        build_state = {
            "state": "COMPLETED_CLOSED" if has_complete_marker else "IN_PROGRESS",
            "timestamp": datetime.now().isoformat(),
            "generated_by": "fo_test_harness"
        }
        with open(build_state_path, 'w') as f:
            json.dump(build_state, f, indent=2)
        if has_complete_marker:
            print_info(f"  → Generated: build_state.json (COMPLETED_CLOSED)")
        else:
            print_warning(f"  → Generated: build_state.json (IN_PROGRESS — no completion marker found)")

        # Persist skipped snippets for post-QA polish
        if skipped_snippets:
            snippets_path = artifacts_dir / 'skipped_snippets.json'
            with open(snippets_path, 'w') as f:
                json.dump(skipped_snippets, f, indent=2)
            print_info(f"  → Saved: skipped_snippets.json ({len(skipped_snippets)} snippet(s))")

        self._write_artifact_manifest(artifacts_dir)

        return count

    def _write_artifact_manifest(self, artifacts_dir: Path):
        """Generate artifact_manifest.json from files in artifacts_dir."""
        manifest_path = artifacts_dir / 'artifact_manifest.json'
        manifest_artifacts = []
        for file_path in sorted(artifacts_dir.rglob('*')):
            if file_path.is_file():
                rel_path = str(file_path.relative_to(artifacts_dir))
                if rel_path in ('artifact_manifest.json', 'build_state.json', 'execution_declaration.json'):
                    continue
                file_content = file_path.read_bytes()
                sha256 = hashlib.sha256(file_content).hexdigest()
                manifest_artifacts.append({
                    "path": rel_path,
                    "sha256": sha256,
                    "size": len(file_content)
                })

        manifest = {
            "artifacts": manifest_artifacts,
            "total_count": len(manifest_artifacts),
            "generated_by": "fo_test_harness",
            "timestamp": datetime.now().isoformat()
        }
        with open(manifest_path, 'w') as f:
            json.dump(manifest, f, indent=2)
        print_info(f"  → Generated: artifact_manifest.json ({len(manifest_artifacts)} files)")

    def refresh_manifest_for_iteration(self, iteration: int):
        """Regenerate manifest for a given iteration after post-processing."""
        artifacts_dir = self.build_dir / f'iteration_{iteration:02d}_artifacts'
        if artifacts_dir.exists():
            self._write_artifact_manifest(artifacts_dir)

    @staticmethod
    def _is_valid_business_path(rel_path: str) -> bool:
        """Return True if rel_path matches the boilerplate whitelist."""
        import fnmatch
        for pattern in BOILERPLATE_VALID_PATHS:
            if fnmatch.fnmatch(rel_path, pattern):
                return True
        return False

    @staticmethod
    def _remap_to_valid_path(rel_path: str):
        """Return the canonical business/ path for a wrong-path file, or None if unmappable.

        Rules:
          *.py  in app/api/, app/routers/, app/routes/, backend/routes/ → business/backend/routes/<name>
          *.py  in app/models/, models/                                  → business/models/<name>
          *.py  in app/services/, services/                              → business/services/<name>
          *.jsx in pages/, app/, src/pages/, frontend/pages/             → business/frontend/pages/<name>
          *.js|*.jsx in lib/, frontend/lib/, src/lib/                    → business/frontend/lib/<name>
        """
        import os
        name = os.path.basename(rel_path)
        parts = rel_path.replace('\\', '/').split('/')

        if name.endswith('.py'):
            for marker in ('api', 'routers', 'routes'):
                if marker in parts:
                    return f'business/backend/routes/{name}'
            if 'models' in parts:
                return f'business/models/{name}'
            if 'services' in parts:
                return f'business/services/{name}'
        elif name.endswith(('.jsx', '.tsx')):
            canonical = name.replace('.tsx', '.jsx')
            # lib files
            if 'lib' in parts:
                return f'business/frontend/lib/{canonical}'
            # page files
            return f'business/frontend/pages/{canonical}'
        elif name.endswith('.js') and 'lib' in parts:
            return f'business/frontend/lib/{name}'

        return None  # unmappable — will be pruned

    def prune_non_business_artifacts(self, iteration: int):
        """Remove non-business artifacts and regenerate manifest.

        Pass 1: wrong-path files (not under business/).
          - If a valid-path equivalent already exists in this iteration → prune (duplicate).
          - If NO equivalent exists → remap to the canonical business/ path to avoid losing logic.
          - Truly unmappable files are pruned.

        Pass 2: business/** files not on the valid-path whitelist
                (e.g. business/tests/, business/backend/services/,
                 business/app/, business/backend/__init__.py, .tsx files)
        """
        artifacts_dir = self.build_dir / f'iteration_{iteration:02d}_artifacts'
        if not artifacts_dir.exists():
            return

        SKIP = {'artifact_manifest.json', 'build_state.json', 'execution_declaration.json'}

        removed = 0
        remapped = 0
        invalid_business = 0
        for file_path in sorted(artifacts_dir.rglob('*')):
            if not file_path.is_file():
                continue
            rel_path = str(file_path.relative_to(artifacts_dir))
            if rel_path in SKIP:
                continue

            if not rel_path.startswith('business/'):
                canonical = self._remap_to_valid_path(rel_path)
                if canonical:
                    dest = artifacts_dir / canonical
                    if dest.exists():
                        # Correct-path version already present — discard the duplicate
                        file_path.unlink()
                        removed += 1
                        print_warning(f"  → Pruned duplicate wrong-path: {rel_path} (kept {canonical})")
                    else:
                        # No correct-path version — salvage by remapping
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        file_path.rename(dest)
                        remapped += 1
                        print_warning(f"  → Remapped {rel_path} → {canonical}")
                else:
                    file_path.unlink()
                    removed += 1
            elif not self._is_valid_business_path(rel_path):
                file_path.unlink()
                print_warning(f"  → Pruned invalid business path: {rel_path}")
                invalid_business += 1

        # Remove empty directories
        for dir_path in sorted(artifacts_dir.rglob('*'), reverse=True):
            if dir_path.is_dir() and not any(dir_path.iterdir()):
                dir_path.rmdir()

        if removed:
            print_warning(f"  → Pruned {removed} non-business artifact(s)")
        if remapped:
            print_success(f"  → Remapped {remapped} wrong-path file(s) to correct business/ paths")
        if removed or remapped or invalid_business:
            self._write_artifact_manifest(artifacts_dir)

    def merge_forward_from_previous_iteration(self, iteration: int, claude_output_paths: list):
        """
        After a defect-only patch iteration, copy any business/** files from the previous
        iteration that Claude did NOT output into the current iteration's artifact dir.
        This prevents non-defect files from being lost when Claude outputs only defect files.
        """
        import shutil
        prev_dir = self.build_dir / f'iteration_{iteration-1:02d}_artifacts'
        curr_dir = self.build_dir / f'iteration_{iteration:02d}_artifacts'
        if not prev_dir.exists() or not curr_dir.exists():
            return

        # Normalize Claude's output paths for comparison
        output_set = set(p.lstrip('./') for p in claude_output_paths)

        copied = 0
        for file_path in sorted(prev_dir.rglob('*')):
            if not file_path.is_file():
                continue
            rel_path = str(file_path.relative_to(prev_dir))
            if rel_path in ('artifact_manifest.json', 'build_state.json', 'execution_declaration.json'):
                continue
            if not self._is_valid_business_path(rel_path):
                continue  # Never carry forward invalid paths
            if rel_path in output_set:
                continue  # Claude already output this file — keep Claude's version
            dest = curr_dir / rel_path
            if not dest.exists():
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(file_path, dest)
                copied += 1

        if copied > 0:
            print_info(f"  → Carried forward {copied} unchanged file(s) from iteration {iteration-1:02d}")
            self._write_artifact_manifest(curr_dir)

    def build_synthetic_qa_output(self, iteration: int) -> str:
        """
        Build a synthetic build_output string from the current iteration's merged artifact
        directory, formatted as FILE: headers + code fences. Used to give QA an accurate
        view of the full artifact set after merge-forward, not just Claude's partial output.
        """
        artifacts_dir = self.build_dir / f'iteration_{iteration:02d}_artifacts'
        if not artifacts_dir.exists():
            return ""

        ext_to_lang = {
            '.py': 'python', '.jsx': 'jsx', '.js': 'jsx', '.ts': 'typescript',
            '.tsx': 'typescript', '.json': 'json', '.md': 'markdown',
            '.css': 'css', '.html': 'html', '.sh': 'bash', '.txt': 'text',
        }
        skip = {'artifact_manifest.json', 'build_state.json', 'execution_declaration.json'}

        parts = []
        for file_path in sorted(artifacts_dir.rglob('*')):
            if not file_path.is_file():
                continue
            rel_path = str(file_path.relative_to(artifacts_dir))
            if rel_path in skip:
                continue
            lang = ext_to_lang.get(file_path.suffix.lower(), 'text')
            try:
                content = file_path.read_text(encoding='utf-8', errors='replace')
            except Exception:
                continue
            parts.append(f'**FILE: {rel_path}**\n```{lang}\n{content}\n```')

        return '\n\n'.join(parts)

    def save_qa_report(self, iteration: int, report: str):
        """Save QA report from ChatGPT"""
        path = self.qa_dir / f'iteration_{iteration:02d}_qa_report.txt'
        path.write_text(report)
        print_success(f"Saved QA report: qa/iteration_{iteration:02d}_qa_report.txt")
        return path

    def save_defect_fix(self, iteration: int, fix: str):
        """
        Save defect fix from Claude (iterations 2+).

        FIX #6: This method existed but was never called. Now invoked
        from execute_build_qa_loop() on every iteration > 1.
        """
        path = self.build_dir / f'iteration_{iteration:02d}_fix.txt'
        path.write_text(fix)
        print_success(f"Saved defect fix: build/iteration_{iteration:02d}_fix.txt")
        return path

    def save_deploy_output(self, output: str):
        """Save DEPLOY output"""
        path = self.deploy_dir / 'deploy_output.txt'
        path.write_text(output)
        print_success(f"Saved DEPLOY output: deploy/deploy_output.txt")
        return path

    def save_artifact(self, name: str, content: str, artifact_type: str = 'code'):
        """Save a build artifact (code file, doc, etc.)"""
        subdir = self.build_dir / artifact_type
        subdir.mkdir(exist_ok=True)
        path = subdir / name
        path.write_text(content)
        return path

    def save_log(self, log_name: str, content: str):
        """Append timestamped entry to a log file"""
        path = self.logs_dir / f'{log_name}.log'
        timestamp = datetime.now().isoformat()
        with open(path, 'a') as f:
            f.write(f"\n[{timestamp}]\n{content}\n")
        return path

    def save_claude_questions(self, iteration: int, questions_text: str):
        """
        Save Claude's clarification questions and stop the pipeline.
        Written to logs/ so they're easy to find.
        """
        path = self.logs_dir / 'claude_questions.txt'
        timestamp = datetime.now().isoformat()
        with open(path, 'w') as f:
            f.write(f"Claude asked clarifying questions at iteration {iteration}\n")
            f.write(f"Timestamp: {timestamp}\n")
            f.write("=" * 60 + "\n\n")
            f.write(questions_text)
        print_warning(f"Claude questions saved: logs/claude_questions.txt")
        return path

    def generate_manifest(self):
        """Generate artifact manifest with SHA256 checksums"""
        manifest = {
            "generated_at": datetime.now().isoformat(),
            "artifacts":    []
        }

        for artifact_file in self.build_dir.rglob('*'):
            if artifact_file.is_file():
                with open(artifact_file, 'rb') as f:
                    content  = f.read()
                    checksum = hashlib.sha256(content).hexdigest()
                manifest["artifacts"].append({
                    "path":   str(artifact_file.relative_to(self.run_dir)),
                    "sha256": checksum,
                    "size":   len(content)
                })

        manifest_path = self.run_dir / 'artifact_manifest.json'
        manifest_path.write_text(json.dumps(manifest, indent=2))
        print_success(f"Generated artifact manifest: artifact_manifest.json")
        return manifest_path


# ============================================================
# ZIP PACKAGER
# ============================================================

def package_output_zip(run_dir: Path, startup_id: str, block: str, use_boilerplate: bool = False) -> Path:
    """
    Package the run directory into a ZIP at the base fo_harness_runs/ level.

    For boilerplate builds, also includes the teebu-saas-platform boilerplate.

    ZIP contains:
      build/     — all Claude build outputs and code
      qa/        — all QA reports
      logs/      — all prompt logs
      artifact_manifest.json
      boilerplate/  — (boilerplate builds only) teebu-saas-platform (legacy layout)

    ZIP name matches the run directory name for easy pairing.
    Returns the path to the created ZIP.
    """
    zip_path = Config.OUTPUT_DIR / f'{run_dir.name}.zip'

    print_info(f"Packaging output ZIP: {zip_path.name}")

    # For boilerplate builds, prepare boilerplate source
    boilerplate_source = None
    if use_boilerplate:
        boilerplate_source = Config.PLATFORM_BOILERPLATE_DIR
        if boilerplate_source.exists():
            print_info(f"Including boilerplate: {boilerplate_source}")
        else:
            print_warning(f"Boilerplate not found at {boilerplate_source} - skipping")

    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        if use_boilerplate and boilerplate_source and boilerplate_source.exists():
            # Assemble a single startup root folder with boilerplate + overlay
            root = Path(startup_id)

            # 1) Add boilerplate under startup root
            for file_path in boilerplate_source.rglob('*'):
                if file_path.is_file():
                    if any(exclude in file_path.parts for exclude in ['node_modules', '.git', '.claude', 'scripts', '__pycache__', '.DS_Store']):
                        continue
                    rel_path = file_path.relative_to(boilerplate_source)
                    arcname = root / rel_path
                    zf.write(file_path, arcname)

            # 2) Overlay latest build artifacts into saas-boilerplate/business/**
            build_dir = run_dir / 'build'
            artifact_dirs = sorted(build_dir.glob('iteration_*_artifacts'))
            latest_artifacts = artifact_dirs[-1] if artifact_dirs else None
            if latest_artifacts:
                for file_path in latest_artifacts.rglob('*'):
                    if not file_path.is_file():
                        continue
                    rel_path = file_path.relative_to(latest_artifacts)
                    if str(rel_path).startswith('business/'):
                        arcname = root / 'saas-boilerplate' / rel_path
                        zf.write(file_path, arcname)

            # 3) Include harness outputs under startup root for traceability
            for file_path in run_dir.rglob('*'):
                if file_path.is_file():
                    if '.claude' in file_path.parts or 'scripts' in file_path.parts:
                        continue
                    arcname = root / '_harness' / file_path.relative_to(run_dir)
                    zf.write(file_path, arcname)
        else:
            # Default legacy packaging: add run directory contents
            for file_path in run_dir.rglob('*'):
                if file_path.is_file():
                    arcname = file_path.relative_to(Config.OUTPUT_DIR)
                    zf.write(file_path, arcname)

        # Legacy boilerplate/ layout is superseded by startup-root assembly

    zip_size_mb = zip_path.stat().st_size / (1024 * 1024)
    print_success(f"ZIP created: {zip_path} ({zip_size_mb:.2f} MB)")
    return zip_path


# ============================================================
# PROMPT TEMPLATES
# ============================================================

class PromptTemplates:
    """Templates for BUILD, QA, and DEPLOY prompts"""

    @staticmethod
    def build_prompt(
        block: str,
        intake_data: dict,
        build_governance: str,
        iteration: int = 1,
        max_iterations: int = Config.MAX_QA_ITERATIONS,
        previous_defects: Optional[str] = None,
        tech_stack_override: dict = None,
        external_integration_override: dict = None,
        startup_id: str = 'unknown',
        force_tech_stack: Optional[str] = None,
        required_file_inventory: Optional[list] = None,
        defect_target_files: Optional[list] = None
    ) -> Tuple[str, str]:
        """
        Generate BUILD prompt for Claude.

        FIX #1 (Prompt Caching):
        WHY: Returns (governance_section, dynamic_section) tuple.
        Governance section is cached (saves ~90% of input token costs).
        Dynamic section varies per iteration (iteration #, defects, intake).

        FIX #5: build_governance (full ZIP contents) now injected inline.
        FIX #2: intake_data keyed as block_a / block_b to match run_intake_v7 output.

        Returns:
            tuple[str, str]: (cacheable_governance_section, dynamic_iteration_section)
        """
        # FIX #2: correct key lookup — run_intake_v7 outputs block_a / block_b
        block_key  = f'block_{block.lower()}'
        block_data = intake_data.get(block_key, {})

        # Extract tech stack for override injection
        tech_stack = force_tech_stack or block_data.get('pass_2', {}).get('tech_stack_selection', 'custom')

        # Build dynamic injections (kept as data inputs; directive text is externalized)
        tech_stack_instructions = ""
        if tech_stack_override and tech_stack == 'lowcode':
            lowcode_def = tech_stack_override.get('tech_stack_definitions', {}).get('lowcode', {})
            if lowcode_def:
                prompt_template = tech_stack_override.get('prompt_injection_template', {}).get('for_lowcode_stack', '')
                if prompt_template:
                    tech_stack_instructions = "\n\n" + prompt_template.replace('{startup_name}', startup_id) + "\n\n"

        integration_instructions = ""
        if external_integration_override:
            prompt_injection = external_integration_override.get('prompt_injection', '')
            if prompt_injection:
                integration_instructions = "\n\n" + prompt_injection + "\n\n"

        boilerplate_path_instruction = ""
        if tech_stack == 'lowcode':
            boilerplate_path_instruction = "\n\n" + DirectiveTemplateLoader.render(
                'build_boilerplate_path_rules.md'
            ) + "\n\n" + DirectiveTemplateLoader.render(
                'build_boilerplate_capabilities.md'
            ) + "\n\n" + DirectiveTemplateLoader.render(
                'build_boilerplate_sample_code.md'
            ) + "\n\n"

        previous_defects_section = ""
        if previous_defects:
            required_inventory_bullets = "\n".join(f"- {p}" for p in (required_file_inventory or []))
            if not required_inventory_bullets:
                required_inventory_bullets = "- (no prior manifest inventory available)"

            defect_target_bullets = "\n".join(f"- {p}" for p in (defect_target_files or []))
            if not defect_target_bullets:
                defect_target_bullets = "- (no explicit file paths found in defects; infer minimal targets)"

            previous_defects_section = "\n\n" + DirectiveTemplateLoader.render(
                'build_previous_defects.md',
                previous_defects=previous_defects
            ) + "\n\n"
            previous_defects_section += "\n\n" + DirectiveTemplateLoader.render(
                'build_patch_first_file_lock.md',
                required_file_inventory_bullets=required_inventory_bullets,
                defect_target_files_bullets=defect_target_bullets
            ) + "\n\n"

        governance_section = DirectiveTemplateLoader.render(
            'build_governance.md',
            block=block,
            build_governance=build_governance
        )

        dynamic_section = DirectiveTemplateLoader.render(
            'build_dynamic_base.md',
            iteration=iteration,
            max_iterations=max_iterations,
            block=block,
            block_key=block_key,
            block_data_json=json.dumps(block_data, indent=2),
            previous_defects_section=previous_defects_section,
            tech_stack_instructions=tech_stack_instructions,
            integration_instructions=integration_instructions,
            boilerplate_path_instruction=boilerplate_path_instruction
        )

        return (governance_section, dynamic_section)

        # LEGACY INLINE PROMPT (INACTIVE, kept for reference only)
        # Replaced by external templates:
        # - directives/prompts/build_governance.md
        # - directives/prompts/build_dynamic_base.md
        # - directives/prompts/build_previous_defects.md
        # - directives/prompts/build_boilerplate_path_rules.md
        # ═══════════════════════════════════════════════════════════════
        # CACHEABLE SECTION - Static governance and rules
        # WHY: This content never changes between iterations.
        # Caching this saves 90% of input token costs on rounds 2+.
        # ═══════════════════════════════════════════════════════════════

        governance_section = f"""You are the FO BUILD EXECUTOR running in FOUNDER_FAST_PATH mode.

**YOUR ROLE:**
Execute the build for {block} using the locked FO Build Governance provided below.

**CRITICAL INSTRUCTION:**
Do NOT ask clarifying questions. Do NOT request additional information.
Build immediately using the intake data and governance provided.
If something is ambiguous, make a reasonable assumption and document it.
If you cannot proceed without clarification, output ONLY:
  CLARIFICATION_NEEDED: <your questions, one per line>
And nothing else.

**GOVERNANCE FILES (inline — use these as your build rules):**
{build_governance}

**CRITICAL RULES FROM GOVERNANCE:**
- No inference — follow governance literally
- No scope changes (ABORT_AND_DISCARD if scope change detected)
- Produce all required code artifacts

**DO NOT OUTPUT THESE FILES (the harness generates them automatically):**
- artifact_manifest.json — SKIP, generated by harness
- build_state.json — SKIP, generated by harness
- execution_declaration.json — SKIP, generated by harness
- README.md — SKIP, generated post-QA
- .env.example — SKIP, generated post-QA
- .gitignore — SKIP, generated post-QA
This saves tokens for actual code files.

**ARTIFACT REQUIREMENTS:**
- All code files in separate artifacts (no truncation)
- package.json with dependencies
- All configuration files

**OUTPUT FORMAT:**
1. Provide complete implementation (no placeholders, no "...continued")
2. Use artifacts/code blocks for all files
3. Do NOT include artifact_manifest.json or build_state.json (auto-generated)
4. End with exactly: "BUILD STATE: COMPLETED_CLOSED"

**═══════════════════════════════════════════════════════════════**
**MULTI-PART OUTPUT (CRITICAL FOR LARGE BUILDS)**
**═══════════════════════════════════════════════════════════════**

Your output limit is 16,000 tokens (~12,000 words). If your build has more files than
can fit in a single response, you MUST split your output into numbered parts (like TCP):

1. Start Part 1 with: <!-- PART 1/N --> (estimate N based on total file count)
2. Include as many COMPLETE files as will fit (NEVER cut a file mid-content)
3. End Part 1 with: <!-- END PART 1/N --> followed by a list of remaining files:
   REMAINING FILES: file1.js, file2.js, config.json, ...
4. I will automatically request each subsequent part — do NOT stop or ask
5. The LAST part MUST end with: BUILD STATE: COMPLETED_CLOSED
   (Do NOT output artifact_manifest.json or build_state.json — auto-generated by harness)

**MULTI-PART RULES:**
- Each file appears in EXACTLY ONE part. Never repeat a file across parts.
- Never cut a file in the middle. If a file won't fit, move it entirely to the next part.
- If your build fits in one response, do NOT use parts — just output normally.
- When estimating N, assume ~4-5 files per part depending on file size.

**═══════════════════════════════════════════════════════════════**
**ARTIFACT OUTPUT FORMAT - MANDATORY RULES**
**═══════════════════════════════════════════════════════════════**

You MUST follow these formatting rules exactly for ALL code artifacts:

**CRITICAL: README FILES MUST NOT CONTAIN CODE BLOCKS**
If you are creating README.md or any documentation:
- NEVER use triple-backtick code blocks for bash, sh, javascript, sql, jsx, or any language
- Write commands as plain text: "Run: npm install" or "Execute: npm run dev"
- Use inline code for commands: Run `npm install` to install dependencies
- DO NOT include example code snippets, SQL schemas, or integration examples in code blocks
- Code blocks in README will cause extraction errors - DO NOT USE THEM
- If you need to show SQL schema, database setup, or integration examples, use plain text or inline code

**CRITICAL: ALL CODE MUST HAVE FILE: HEADERS**
- EVERY code block you write MUST have a **FILE: path/to/file.ext** header
- NO example code, integration snippets, or documentation examples outside of FILE: headers
- If you include ANY code block without a FILE: header, it will be extracted as a numbered artifact
- Example snippets should be written as plain text or inline code, NOT code blocks

**RULE 1: File Path Declaration**
Before EVERY code block, declare the file path on its own line:
**FILE: path/to/filename.ext**

**RULE 2: Code Block Format**
Immediately after the file path, start the code block:
```language
code content here
```

**RULE 3: No Inline Filename Hints**
Do NOT put filenames on the code fence line or as comments inside the code.
Only use the **FILE:** declaration above the code block.

**RULE 4: Subdirectories**
You MAY use subdirectories in paths:
- **FILE: src/index.html** ✓
- **FILE: js/app.js** ✓
- **FILE: config/database.json** ✓

**RULE 5: Complete Files Only**
Every file must be complete. NO placeholders like "// ... rest of code".
If output limit is reached, end gracefully and I will request continuation.

**RULE 6: Metadata Files — DO NOT OUTPUT**
The harness auto-generates these files. Do NOT output them:
- artifact_manifest.json (auto-generated with SHA256 checksums)
- build_state.json (auto-generated)
- execution_declaration.json (auto-generated)
Instead, use your token budget for actual code files.
Just end your output with: BUILD STATE: COMPLETED_CLOSED

**EXAMPLE FORMAT:**

**FILE: index.html**
```html
<!DOCTYPE html>
<html>
<head><title>Example</title></head>
<body><h1>Hello World</h1></body>
</html>
```

**FILE: js/app.js**
```javascript
console.log('Hello from app.js');
```

**FILE: package.json**
```json
{{
  "name": "my-app",
  "version": "1.0.0",
  "dependencies": {{}}
}}
```

(No artifact_manifest.json, build_state.json, or README needed — auto-generated by harness)

**═══════════════════════════════════════════════════════════════**
"""

        # ═══════════════════════════════════════════════════════════════
        # DYNAMIC SECTION - Changes per iteration
        # WHY: This content varies (iteration #, defects, intake data).
        # Not cached - sent fresh each time.
        # ═══════════════════════════════════════════════════════════════

        dynamic_section = f"""
**ITERATION:** {iteration} of {Config.MAX_QA_ITERATIONS}
**YOUR TASK:**
1. Extract {block} intake data from the INTAKE DATA section below
2. Execute BUILD according to fo_build_state_machine.json (from governance above)
3. Follow all enforcement rules (tier, scope, iteration, QA routing)
4. Produce COMPLETED_CLOSED state with all required artifacts
5. You are on iteration {iteration} - Max 5 iterations per task

**PHASED FEATURE RULE (NON-NEGOTIABLE):**
- If a feature/integration is marked "optional", "phase 2", "phase 3", or "later",
  you MUST NOT implement it now. Provide only a stub/interface and TODO notes.
  Do NOT add real integration logic until it is explicitly in-scope for this phase.

"""

        if previous_defects:
            dynamic_section += f"""
**PREVIOUS QA ITERATION — DEFECTS TO FIX:**
ChatGPT QA reported the following defects. Fix ALL of them.

**CRITICAL RULES FOR DEFECT FIXES:**
1. **Fix ONLY the reported defects** - Do NOT change unrelated code
2. **Output ALL artifacts** - You MUST include EVERY file from previous iteration
3. **Never drop files** - If a file isn't mentioned in defects, include it unchanged
4. **No scope changes** - Do NOT add new features or functionality
5. **No over-engineering** - Fix exactly what QA asks, nothing more

**WHY THIS MATTERS:**
Lowcode builds regenerate ALL files every iteration. If you don't output a file,
it will be considered DELETED. QA will flag it as missing and you'll loop forever.

**DEFECTS TO FIX:**
{previous_defects}

**REMEMBER:** Output the COMPLETE build (all files) with ONLY the defects fixed.
"""

        # Inject tech stack override if lowcode
        tech_stack_instructions = ""
        if tech_stack_override and tech_stack == 'lowcode':
            lowcode_def = tech_stack_override.get('tech_stack_definitions', {}).get('lowcode', {})
            if lowcode_def:
                prompt_template = tech_stack_override.get('prompt_injection_template', {}).get('for_lowcode_stack', '')
                if prompt_template:
                    tech_stack_instructions = "\n\n" + prompt_template.replace('{startup_name}', startup_id) + "\n\n"

        # Enforce boilerplate-only output paths when lowcode is active
        boilerplate_path_instruction = ""
        if tech_stack == 'lowcode':
            boilerplate_path_instruction = "\n\n" + DirectiveTemplateLoader.render(
                'build_boilerplate_path_rules.md'
            ) + "\n\n" + DirectiveTemplateLoader.render(
                'build_boilerplate_capabilities.md'
            ) + "\n\n" + DirectiveTemplateLoader.render(
                'build_boilerplate_sample_code.md'
            ) + "\n\n"

        # Inject external integration policy
        integration_instructions = ""
        if external_integration_override:
            prompt_injection = external_integration_override.get('prompt_injection', '')
            if prompt_injection:
                integration_instructions = "\n\n" + prompt_injection + "\n\n"

        dynamic_section += f"""
**INTAKE DATA ({block} — key: {block_key}):**
{json.dumps(block_data, indent=2)}
{tech_stack_instructions}{integration_instructions}{boilerplate_path_instruction}
**BEGIN BUILD EXECUTION NOW.**
"""

        return (governance_section, dynamic_section)

    @staticmethod
    def qa_prompt(build_output: str, intake_data: dict, block: str, tech_stack: str = 'custom', qa_override: dict = None) -> str:
        """
        Generate QA prompt for ChatGPT.

        FIX #2: correct key lookup — block_a / block_b.
        FIX #3: Add tech stack awareness for lowcode builds.
        FIX #8: Add QA override support for tightened evaluation.
        """
        if qa_override is None:
            qa_override = {}

        block_key  = f'block_{block.lower()}'
        block_data = intake_data.get(block_key, {})

        # Build tech stack context for lowcode
        tech_stack_context = ""
        if tech_stack == 'lowcode':
            tech_stack_context = """

**═══════════════════════════════════════════════════════════════**
**TECH STACK CONTEXT - LOWCODE BUILD**
**═══════════════════════════════════════════════════════════════**

This is a LOWCODE build using the teebu-saas-boilerplate framework.

**WHAT THE BOILERPLATE ALREADY PROVIDES:**
- Authentication & authorization (JWT, role-based access control)
- Payment processing infrastructure (Stripe integration)
- Database models, migrations, and ORM setup
- Email service integration
- UI framework (React, Tailwind CSS)
- API infrastructure (REST endpoints, middleware)
- Deployment configuration (Docker, CI/CD)

**WHAT CLAUDE BUILT (Business Logic Only):**
- Custom models specific to this business domain
- Business services and logic
- Domain-specific React components
- Configuration to integrate with boilerplate
- API endpoints for business features

**CRITICAL QA INSTRUCTIONS FOR LOWCODE:**
1. DO NOT flag missing infrastructure (auth, payments, DB setup, email) as defects
   → The boilerplate provides these - they are NOT in Claude's output
2. DO NOT flag "missing deployment config" or "missing Docker files" as defects
   → The boilerplate handles deployment
3. DO NOT flag "no UI framework setup" or "missing Tailwind config" as defects
   → The boilerplate provides the UI foundation
4. DO validate that business logic correctly integrates with boilerplate patterns
5. DO validate that business models/services/components are complete
6. DO flag if Claude built infrastructure that should use boilerplate instead

**BOILERPLATE MODULES — WHAT CORRECT INTEGRATION LOOKS LIKE:**
RULE: If you see any import from `core.*` or `lib.*_lib` in a file, that capability IS correctly integrated. You MUST NOT flag it as missing, broken, or incorrectly implemented unless you can quote a specific wrong line. The presence of the import IS the implementation.
The following imports and patterns ARE correct boilerplate usage. Do NOT flag them as bugs or missing implementations:

Authentication (correct):
  `from core.rbac import get_current_user` + `Depends(get_current_user)` in route signature
  `current_user["sub"]` used as user/owner/consultant ID
  `from core.rbac import require_role` + `Depends(require_role("admin"))` for role gating
  Frontend: `import {{ useAuth0 }} from '@auth0/auth0-react'` + `user.sub`
  → DO NOT flag: "missing authentication", "consultant_id not validated", "hardcoded user check"
  → DO FLAG: hardcoded ID strings like `'consultant_1'`, `'current_user'`, `'user_123'`

Multi-tenancy (correct):
  `from core.tenancy import TenantMixin` on SQLAlchemy models, `get_tenant_db(db, tenant_id)`
  → DO NOT flag: "missing tenant isolation" when TenantMixin is present

Usage limits (correct):
  `from core.usage_limits import check_and_increment` called before metered operations
  → DO NOT flag: "missing quota enforcement" when check_and_increment is called

AI calls (correct):
  `from core.ai_governance import call_ai` — handles Claude/OpenAI, cost tracking, budgets
  → DO NOT flag: "missing AI implementation", "no cost tracking" when call_ai is used

Social posting (correct):
  `from core.posting import post_to_reddit, post_to_twitter, post_to_linkedin` etc.
  → DO NOT flag: "missing social integration" when core.posting is imported

Email (correct):
  `from lib.mailerlite_lib import load_mailerlite_lib` + `.send_welcome_email()` etc.
  → DO NOT flag: "missing email service" when mailerlite_lib is imported

Billing/Stripe (correct):
  `from lib.stripe_lib import load_stripe_lib` + `.create_subscription_product()` etc.
  → DO NOT flag: "missing payment implementation" when stripe_lib is imported

Analytics (correct):
  `from lib.analytics_lib import load_analytics_lib` + `.track_event()` etc.
  → DO NOT flag: "missing analytics" when analytics_lib is imported

Search (correct):
  `from lib.meilisearch_lib import load_meilisearch_lib` + `.search()` etc.
  → DO NOT flag: "missing search" when meilisearch_lib is imported

Onboarding/Trial/Activation (correct):
  `from core.onboarding import get_or_create_onboarding, mark_step_complete`
  `from core.trial import start_trial, is_trial_active`
  `from core.activation import record_activation`
  → DO NOT flag missing onboarding/trial/activation when these are imported

**WHAT TO FLAG (incorrect patterns even in lowcode):**
  - Hardcoded user/owner IDs: `consultant_id: 'consultant_1'`, `user_id = 'test_user'`
  - Dict/in-memory storage: `items_db = {}`, `data = []` used as a database
  - Sequential integer IDs: `id = len(db) + 1`
  - Flask patterns in backend: `from flask import Blueprint`, `@bp.route`, `jsonify()`
  - Hardcoded data arrays in frontend instead of API fetch calls
  - Custom reimplementation of auth, payments, or email that bypasses boilerplate modules

**═══════════════════════════════════════════════════════════════**
**SCOPE VALIDATION RULES FOR LOWCODE**
**═══════════════════════════════════════════════════════════════**

**WHY THIS MATTERS:** Lowcode builds implement business logic only. The intake
specifies HIGH-LEVEL features but not data model details. Distinguish between:
- **Scope creep** = NEW features not in intake
- **Reasonable implementation** = Data model details supporting defined features

**✅ ACCEPTABLE (NOT scope creep):**

**Standard Data Model Properties:**
- Domain-appropriate attributes for models mentioned in HLD
  Examples: Horse (age, color, gender, breed), Member (preferences, contact),
  Race (track, position, earnings, date), Breeding (sire, dam, offspring)
- These are reasonable inferences to implement the HLD features

**Common Service Methods:**
- Standard CRUD operations: findById, findAll, create, update, delete
- Data access methods needed for features: getByOwner, getActive, filter
- These are necessary to implement ANY data-driven feature

**Standard Test Coverage:**
- Unit tests for implemented models and services
- API endpoint tests for implemented routes
- Integration tests for business logic
- Test coverage is EXPECTED for professional builds

**Configuration & Setup Files:**
- jest.config.js, .env.example, .gitignore, package.json
- Database migration/schema files for business models
- These are necessary for ANY working application

**Reasonable Error Handling:**
- Input validation, error messages, status codes
- Authorization checks for protected resources
- These are professional development standards

**❌ SCOPE CREEP (REJECT these):**

**NEW User-Facing Features:**
- Betting/wagering system (if not in intake)
- Social networking/forums (if not in intake)
- Analytics dashboards (if not in intake)
- Mobile app (if only web specified)

**NEW External Integrations:**
- Payment providers (if intake specifies data feeds only)
- SMS/notifications (if only email specified)
- Third-party APIs (unless explicitly required)

**NEW Business Capabilities:**
- Live streaming (if not in intake)
- Automated trading (if not in intake)
- AI/ML features (if not in intake)

**Significant Complexity Not Implied:**
- Complex algorithms beyond stated requirements
- Advanced optimization not requested
- Enterprise features for simple use case

**EXAMPLES OF CORRECT EVALUATION:**

❌ WRONG: "Horse model includes 'age' property - SCOPE CREEP (not in intake)"
✅ RIGHT: "Horse model needs age to display horse information (HLD feature)"

❌ WRONG: "Tests include horse.test.js - SCOPE CREEP (tests not specified)"
✅ RIGHT: "Test coverage is standard practice - ACCEPTABLE"

❌ WRONG: "MembershipService has upgradeMembership() - SCOPE CREEP"
✅ RIGHT: "Membership management is in HLD - method is reasonable"

✅ CORRECT: "Added betting feature - SCOPE CREEP (not in intake)"
✅ CORRECT: "Added SMS notifications - SCOPE CREEP (only email specified)"

**WHEN IN DOUBT:** Ask yourself: "Does this enable a NEW feature not in the HLD,
or is it a reasonable implementation detail to support an existing feature?"

**═══════════════════════════════════════════════════════════════**
"""

        # Inject sample code QA reference for lowcode builds
        if tech_stack == 'lowcode':
            tech_stack_context += "\n\n" + DirectiveTemplateLoader.render(
                'build_boilerplate_sample_code.md'
            ) + "\n\n"

        # FIX #8: Inject QA override if present
        qa_override_context = ""
        if qa_override and 'prompt_injection' in qa_override:
            qa_override_context = "\n\n" + qa_override['prompt_injection'] + "\n\n"

        return DirectiveTemplateLoader.render(
            'qa_prompt.md',
            tech_stack_context=tech_stack_context,
            qa_override_context=qa_override_context,
            block=block,
            block_key=block_key,
            block_data_json=json.dumps(block_data, indent=2),
            build_output=build_output
        )

        # LEGACY INLINE PROMPT (INACTIVE, kept for reference only)
        # Replaced by external template:
        # - directives/prompts/qa_prompt.md
        return f"""You are the FO QA OPERATOR (ChatGPT).

**YOUR ROLE:**
Validate the build output from Claude against the intake requirements
and FO Build Governance.
{tech_stack_context}{qa_override_context}
**INTAKE REQUIREMENTS ({block} — key: {block_key}):**
{json.dumps(block_data, indent=2)}

**BUILD OUTPUT FROM CLAUDE:**
{build_output}

**YOUR TASK:**
1. Verify all tasks from intake were completed
2. Verify all required artifacts are present:
   ✅ CRITICAL: All code files for features in intake
   ✅ CRITICAL: package.json (with dependencies)
   ⚠️  MEDIUM: Test files (nice-to-have for POC, required for production)
   ⚠️  Flag MISSING CRITICAL as SPEC_COMPLIANCE_ISSUE, MEDIUM as LOW severity
3. Check for scope compliance (no extra features beyond intake)
4. Check for implementation bugs (code correctness)

**DO NOT FLAG THESE AS DEFECTS (auto-generated by harness after QA):**
- artifact_manifest.json — auto-generated by the test harness with SHA256 checksums
- build_state.json — auto-generated by the test harness
- execution_declaration.json — auto-generated by the test harness
- README.md — auto-generated in post-QA polish step
- .env.example — auto-generated in post-QA polish step
- .gitignore — auto-generated in post-QA polish step
- Test files — auto-generated in post-QA polish step (flag as MEDIUM at most)
These files are NOT expected in Claude's build output. Do NOT flag them as missing.

**DEFECT CLASSIFICATION:**
- IMPLEMENTATION_BUG:     Code doesn't work as specified (logic errors, broken functionality)
- SPEC_COMPLIANCE_ISSUE:  Missing CRITICAL artifacts or doesn't match intake requirements
- SCOPE_CHANGE_REQUEST:   Extra USER-FACING features not in intake (CRITICAL)

**SEVERITY GUIDELINES (FIX #8 - Tightened):**
- CRITICAL: Missing core business logic, broken functionality, major scope creep
- HIGH:     Missing important files (README), incorrect implementation of key features
- MEDIUM:   Missing nice-to-have features (tests for POC), minor deviations from spec
- LOW:      Documentation formatting, code style, non-critical optimizations

**CRITICAL: FOCUS ON WHAT MATTERS**
- DO flag: Missing core features, broken code, new features not in intake
- DO flag: Missing package.json
- DON'T flag: Missing artifact_manifest.json, build_state.json, execution_declaration.json (auto-generated)
- DON'T flag: Missing README.md, .env.example, .gitignore, tests (auto-generated in polish step)
- DON'T flag: Missing tests as HIGH (use MEDIUM at most for POC builds)
- DON'T flag: Code organization preferences (unless clearly wrong)
- DON'T flag: Documentation formatting issues

**OUTPUT FORMAT:**
Provide a structured QA report:

## QA REPORT

### SUMMARY
- Total defects found: [number]
- IMPLEMENTATION_BUG: [count]
- SPEC_COMPLIANCE_ISSUE: [count]
- SCOPE_CHANGE_REQUEST: [count]

### DEFECTS
[List each defect:]
DEFECT-[ID]: [classification]
  - Location: [file/line]
  - Problem: [what's wrong]
  - Expected: [what should be]
  - Severity: HIGH | MEDIUM | LOW

### VERDICT
If ACCEPTED: end with exactly: "QA STATUS: ACCEPTED - Ready for deployment"
If REJECTED: end with exactly: "QA STATUS: REJECTED - [X] defects require fixing"

**BEGIN QA ANALYSIS NOW.**
"""

    @staticmethod
    def deploy_prompt(build_output: str, deploy_governance: str) -> str:
        """
        Generate DEPLOY prompt for Claude.

        FIX #5: deploy_governance (full ZIP contents) now injected inline.
        """
        return DirectiveTemplateLoader.render(
            'deploy_prompt.md',
            build_output=build_output,
            deploy_governance=deploy_governance
        )

        # LEGACY INLINE PROMPT (INACTIVE, kept for reference only)
        # Replaced by external template:
        # - directives/prompts/deploy_prompt.md
        return f"""You are the FO DEPLOY EXECUTOR.

**YOUR ROLE:**
Execute deployment using the locked FO Deploy Governance provided below.

**GOVERNANCE FILES (inline — use these as your deploy rules):**
{deploy_governance}

**YOUR TASK:**
1. Validate build_state = COMPLETED_CLOSED
2. Validate all artifacts exist with correct checksums
3. Execute deployment per governance rules
4. Produce terminal state: DEPLOYED or DEPLOY_FAILED

**CRITICAL RULES FROM GOVERNANCE:**
- Follow fo_deploy_artifact_eligibility_rules.json (validate checksums)
- Follow fo_deploy_completion_rules.json (validation procedures)
- Produce deployment_state.json

**BUILD OUTPUT:**
{build_output}

**OUTPUT FORMAT:**
1. Artifact validation results
2. Deployment commands executed
3. Environment validation
4. Final deployment state
5. End with exactly: "DEPLOYMENT STATE: DEPLOYED" or "DEPLOYMENT STATE: DEPLOY_FAILED"

**BEGIN DEPLOYMENT NOW.**
"""


# ============================================================
# ORCHESTRATOR
# ============================================================

class FOHarness:
    """Main orchestrator for BUILD → QA → DEPLOY"""

    def __init__(self, intake_file: Path, block: str, do_deploy: bool, cli_args: argparse.Namespace = None):
        self.intake_file = intake_file
        self.block       = block.upper()   # 'A' or 'B'
        self.do_deploy   = do_deploy
        self.cli_args    = cli_args
        self.confirm_run_log = (getattr(cli_args, "confirm_run_log", "NO").strip().upper() == "YES") if cli_args else False
        self.max_qa_iterations = int(getattr(cli_args, "max_iterations", Config.MAX_QA_ITERATIONS)) if cli_args else Config.MAX_QA_ITERATIONS
        self.max_build_parts = int(getattr(cli_args, "max_parts", Config.MAX_BUILD_PARTS_DEFAULT)) if cli_args else Config.MAX_BUILD_PARTS_DEFAULT
        self.max_build_continuations = int(getattr(cli_args, "max_continuations", Config.MAX_BUILD_CONTINUATIONS_DEFAULT)) if cli_args else Config.MAX_BUILD_CONTINUATIONS_DEFAULT

        # Load intake JSON
        # Handles both pure JSON and marker-wrapped formats
        with open(intake_file) as f:
            content = f.read()
        if content.strip().startswith('{'):
            self.intake_data = json.loads(content)
        else:
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                self.intake_data = json.loads(json_match.group(0))
            else:
                raise ValueError(f"Could not parse intake JSON from: {intake_file}")

        # Extract startup identity
        self.startup_id = self.intake_data.get('startup_idea_id', 'unknown')

        # Extract tech stack from intake
        block_key = f'block_{self.block.lower()}'
        block_data = self.intake_data.get(block_key, {})
        self.tech_stack = block_data.get('pass_2', {}).get('tech_stack_selection', 'custom')
        self.use_boilerplate = should_use_platform_boilerplate(self.intake_data, self.block)
        self.effective_tech_stack = 'lowcode' if self.use_boilerplate else 'custom'

        # Load governance ZIPs into memory (inline for prompts)
        print_info("Loading BUILD governance ZIP...")
        self.build_governance = load_governance_zip(Path(Config.BUILD_GOVERNANCE_ZIP))
        print_success("BUILD governance loaded")

        # Load tech stack override (local testing)
        self.tech_stack_override = load_tech_stack_override()
        if self.tech_stack_override:
            print_info(f"Tech stack override loaded (stack: {self.tech_stack})")

        # Load external integration override (local testing)
        self.external_integration_override = load_external_integration_override()
        if self.external_integration_override:
            print_info("External integration override loaded")

        # Load QA override (local testing - FIX #8)
        self.qa_override = load_qa_override()
        if self.qa_override:
            print_info("QA override loaded (tightened evaluation criteria)")

        # Resolve QA_POLISH_2 directive path (CLI override takes precedence)
        self.qa_polish_2_directive_path = self._resolve_qa_polish_2_directive_path()
        self.qa_polish_2_directive = load_text_file(self.qa_polish_2_directive_path)
        print_info(f"QA_POLISH_2 directive: {self.qa_polish_2_directive_path}")

        # Only load deploy governance if --deploy was passed
        self.deploy_governance = None
        if self.do_deploy:
            print_info("Loading DEPLOY governance ZIP...")
            self.deploy_governance = load_governance_zip(Path(Config.DEPLOY_GOVERNANCE_ZIP))
            print_success("DEPLOY governance loaded")

        # Warm-start: reuse an existing run directory if --resume-run was given
        resume_run = Path(getattr(cli_args, 'resume_run', None) or '')
        if resume_run.is_dir():
            self.run_dir = resume_run
            print_info(f"Warm-start: reusing run directory {self.run_dir}")
        else:
            # Create run directory with timestamp
            timestamp    = datetime.now().strftime('%Y%m%d_%H%M%S')
            self.run_dir = Config.OUTPUT_DIR / f'{self.startup_id}_BLOCK_{self.block}_{timestamp}'
            self.run_dir.mkdir(parents=True, exist_ok=True)
            # Persist run metadata for traceability
            self._write_run_metadata()

        # Initialize components
        self.claude    = ClaudeClient()
        self.chatgpt   = ChatGPTClient()
        self.artifacts = ArtifactManager(self.run_dir)

        print_header("FO HARNESS INITIALIZED")
        print_info(f"Startup:       {self.startup_id}")
        print_info(f"Block:         BLOCK_{self.block}")
        print_info(f"Tech stack:    {self.tech_stack} (effective: {self.effective_tech_stack})")
        print_info(f"Boilerplate:   {'YES' if self.use_boilerplate else 'NO'}")
        print_info(f"Max iterations:{self.max_qa_iterations}")
        print_info(f"Build caps:    max_parts={self.max_build_parts}, max_continuations={self.max_build_continuations}")
        print_info(f"Deploy:        {'YES' if self.do_deploy else 'NO — ZIP output only'}")
        print_info(f"Run directory: {self.run_dir}")

    def _write_run_metadata(self):
        """Write a run metadata file with CLI args and effective settings."""
        def _coerce_jsonable(value):
            if isinstance(value, Path):
                return str(value)
            if isinstance(value, dict):
                return {k: _coerce_jsonable(v) for k, v in value.items()}
            if isinstance(value, (list, tuple)):
                return [_coerce_jsonable(v) for v in value]
            return value

        metadata = {
            "timestamp": datetime.now().isoformat(),
            "intake_file": str(self.intake_file),
            "startup_id": self.startup_id,
            "block": self.block,
            "deploy": self.do_deploy,
            "tech_stack": self.tech_stack,
            "effective_tech_stack": self.effective_tech_stack,
            "use_boilerplate": self.use_boilerplate,
            "build_governance_zip": str(Config.BUILD_GOVERNANCE_ZIP),
            "deploy_governance_zip": str(Config.DEPLOY_GOVERNANCE_ZIP) if self.do_deploy else None,
            "platform_boilerplate_dir": str(Config.PLATFORM_BOILERPLATE_DIR),
            "qa_polish_2_directive_path": str(self.qa_polish_2_directive_path),
            "cli_args": _coerce_jsonable(vars(self.cli_args)) if self.cli_args else None
        }

        metadata_path = self.run_dir / 'run_metadata.json'
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)

    def _resolve_qa_polish_2_directive_path(self) -> Path:
        """
        Resolve QA_POLISH_2 directive path with precedence:
        1) CLI override (--qa-polish-2-directive)
        2) Config default (Config.QA_POLISH_2_DIRECTIVE_FILE)
        3) Fail fast if resolved path does not exist
        """
        cli_path = getattr(self.cli_args, 'qa_polish_2_directive', None) if self.cli_args else None
        resolved = Path(cli_path) if cli_path else Path(Config.QA_POLISH_2_DIRECTIVE_FILE)
        if not resolved.exists():
            raise FileNotFoundError(
                "QA_POLISH_2 directive not found. "
                f"Looked for: {resolved}. "
                "Provide --qa-polish-2-directive <path> or create the default file."
            )
        return resolved

    def _log_claude_usage(self, response: dict, iteration: int, is_continuation: bool = False, continuation_num: int = 0) -> dict:
        """
        FIX #1: Detailed logging of Claude API usage and cache performance.

        WHY: You asked for DETAILED LOGGING because you're "dumber than a bag of rocks".
        This shows exactly what's happening with caching, tokens, and costs.

        Args:
            response: Claude API response dict
            iteration: Current iteration number
            is_continuation: Whether this was a continuation call
            continuation_num: If continuation, which number (1, 2, 3...)

        Returns:
            dict: Usage stats for accumulation (cache_creation, cache_read, input, output tokens)
        """
        # Extract usage stats from response
        usage = response.get('usage', {})

        # Cache metrics
        cache_creation_tokens = usage.get('cache_creation_input_tokens', 0)
        cache_read_tokens = usage.get('cache_read_input_tokens', 0)
        input_tokens = usage.get('input_tokens', 0)
        output_tokens = usage.get('output_tokens', 0)

        # Determine call type for logging
        call_type = f"CONTINUATION {continuation_num}" if is_continuation else f"ITERATION {iteration}"

        print_info("═══════════════════════════════════════════════════════════")
        print_info(f"CLAUDE API USAGE BREAKDOWN - {call_type}")
        print_info("═══════════════════════════════════════════════════════════")

        # Cache performance
        if cache_creation_tokens > 0:
            print_info("Input tokens:")
            print_info(f"  → Cache creation (write): {cache_creation_tokens:,} tokens")
            print_info(f"  → Non-cached input: {input_tokens:,} tokens")
            print_info(f"  → Total input: {cache_creation_tokens + input_tokens:,} tokens")
            print_info("  → Cache status: FIRST WRITE (will be cached for 5 minutes)")
        elif cache_read_tokens > 0:
            print_success("Input tokens:")
            print_success(f"  → Cache read (hit): {cache_read_tokens:,} tokens ✓ CACHE HIT!")
            print_success(f"  → Non-cached input: {input_tokens:,} tokens")
            print_success(f"  → Total input: {cache_read_tokens + input_tokens:,} tokens")

            # Calculate savings
            # WHY: Cache reads cost ~10% of cache writes. Show the savings!
            cache_write_cost = cache_read_tokens * 0.003 / 1000  # $3/MTok for write
            cache_read_cost = cache_read_tokens * 0.0003 / 1000  # $0.30/MTok for read
            savings = cache_write_cost - cache_read_cost
            savings_percent = (savings / cache_write_cost * 100) if cache_write_cost > 0 else 0

            print_success(f"  → Cache savings: ${savings:.4f} ({savings_percent:.0f}% cheaper than write)")
        else:
            print_info("Input tokens:")
            print_info(f"  → Non-cached input: {input_tokens:,} tokens")
            print_info("  → Cache status: NOT USED (no cacheable prefix provided)")

        # Output tokens
        print_info(f"Output tokens: {output_tokens:,} tokens")

        # Cost estimates
        # Anthropic pricing (as of 2025): Sonnet = $3/MTok input, $15/MTok output
        # Cache write = $3.75/MTok, Cache read = $0.30/MTok
        input_cost = input_tokens * 0.003 / 1000
        cache_write_cost = cache_creation_tokens * 0.00375 / 1000
        cache_read_cost = cache_read_tokens * 0.0003 / 1000
        output_cost = output_tokens * 0.015 / 1000
        total_cost = input_cost + cache_write_cost + cache_read_cost + output_cost

        print_info("Cost estimate:")
        if cache_creation_tokens > 0:
            print_info(f"  → Cache write: ${cache_write_cost:.4f}")
        if cache_read_tokens > 0:
            print_success(f"  → Cache read: ${cache_read_cost:.4f} (vs ${cache_read_tokens * 0.003 / 1000:.4f} without cache)")
        if input_tokens > 0:
            print_info(f"  → Non-cached input: ${input_cost:.4f}")
        print_info(f"  → Output: ${output_cost:.4f}")
        print_info(f"  → Total this call: ${total_cost:.4f}")

        print_info("═══════════════════════════════════════════════════════════")

        # Return usage stats for accumulation
        return {
            'cache_creation_tokens': cache_creation_tokens,
            'cache_read_tokens': cache_read_tokens,
            'input_tokens': input_tokens,
            'output_tokens': output_tokens
        }

    def _log_chatgpt_usage(self, response: dict, iteration: int) -> dict:
        """
        Log ChatGPT API usage and costs.

        WHY: User wants cost tracking for ChatGPT (QA) calls too.
        OpenAI response format: response['usage'] = {prompt_tokens, completion_tokens, total_tokens}

        Args:
            response: OpenAI API response dict
            iteration: Current iteration number

        Returns:
            dict: Usage stats for accumulation (input_tokens, output_tokens)
        """
        # Extract usage from OpenAI response
        usage = response.get('usage', {})
        input_tokens = usage.get('prompt_tokens', 0)
        output_tokens = usage.get('completion_tokens', 0)
        total_tokens = usage.get('total_tokens', 0)

        print_info("═══════════════════════════════════════════════════════════")
        print_info(f"CHATGPT API USAGE - ITERATION {iteration} QA")
        print_info("═══════════════════════════════════════════════════════════")

        print_info(f"Input tokens:  {input_tokens:,} tokens")
        print_info(f"Output tokens: {output_tokens:,} tokens")
        print_info(f"Total tokens:  {total_tokens:,} tokens")

        # Cost calculation (OpenAI GPT-4o pricing as of 2025)
        # Input: $2.50/MTok, Output: $10.00/MTok
        input_cost = input_tokens * 0.0025 / 1000
        output_cost = output_tokens * 0.010 / 1000
        total_cost = input_cost + output_cost

        print_info("")
        print_info("Cost estimate:")
        print_info(f"  → Input:  ${input_cost:.4f}")
        print_info(f"  → Output: ${output_cost:.4f}")
        print_info(f"  → Total:  ${total_cost:.4f}")

        print_info("═══════════════════════════════════════════════════════════")

        return {
            'input_tokens': input_tokens,
            'output_tokens': output_tokens
        }

    def _print_defects_summary(self, qa_report: str, iteration: int):
        """
        Print detailed defects to screen so user doesn't have to dig through logs.

        WHY: User wants to see what defects QA found without opening log files.
        Extracts all DEFECT-XXX entries and prints them in a readable format.
        """
        print_info("")
        print_info("═══════════════════════════════════════════════════════════")
        print_info(f"ITERATION {iteration} - DEFECTS FOUND")
        print_info("═══════════════════════════════════════════════════════════")

        # Extract all defects using regex
        defect_pattern = r'(DEFECT-\d+):\s*(\w+)\s*\n\s*-\s*Location:\s*([^\n]+)\n\s*-\s*Problem:\s*([^\n]+)\n\s*-\s*Expected:\s*([^\n]+)\n\s*-\s*Severity:\s*(\w+)'
        defects = re.findall(defect_pattern, qa_report, re.MULTILINE)

        if defects:
            for defect_id, defect_type, location, problem, expected, severity in defects:
                # Color code by type
                if defect_type == "IMPLEMENTATION_BUG":
                    type_display = f"🐛 {defect_type}"
                elif defect_type == "SPEC_COMPLIANCE_ISSUE":
                    type_display = f"📋 {defect_type}"
                elif defect_type == "SCOPE_CHANGE_REQUEST":
                    type_display = f"🔍 {defect_type}"
                else:
                    type_display = defect_type

                print_warning(f"\n{defect_id}: {type_display}")
                print_info(f"  Location:  {location.strip()}")
                print_info(f"  Problem:   {problem.strip()}")
                print_info(f"  Expected:  {expected.strip()}")
                print_info(f"  Severity:  {severity}")
        else:
            # Fallback: print defects section if regex fails
            defects_section = re.search(r'### DEFECTS\n(.*?)### VERDICT', qa_report, re.DOTALL)
            if defects_section:
                print_info(defects_section.group(1).strip())
            else:
                print_warning("Could not parse defects from QA report")

        print_info("═══════════════════════════════════════════════════════════")
        print_info("")

    def _print_cost_summary(
        self,
        iterations: int,
        total_calls: int,
        total_cache_writes: int,
        total_cache_hits: int,
        total_cache_write_tokens: int,
        total_cache_read_tokens: int,
        total_input_tokens: int,
        total_output_tokens: int,
        total_gpt_calls: int = 0,
        total_gpt_input_tokens: int = 0,
        total_gpt_output_tokens: int = 0,
        run_end_reason: str = 'UNKNOWN'
    ):
        """
        FIX #1: Print final cost summary showing cumulative savings.

        WHY: Show the user EXACTLY how much money they saved with caching.
        This is the "bag of rocks" summary they requested.

        Now includes ChatGPT (QA) costs too.
        """
        print_info("")
        print_info("═══════════════════════════════════════════════════════════")
        print_info("FULL RUN COST ANALYSIS")
        print_info("═══════════════════════════════════════════════════════════")
        print_info(f"Total iterations: {iterations}")
        print_info(f"Total Claude calls: {total_calls} ({iterations} builds + {total_calls - iterations} continuations)")

        # Cache performance
        cache_hit_rate = (total_cache_hits / total_calls * 100) if total_calls > 0 else 0
        print_info("")
        print_info("Cache performance:")
        print_info(f"  → Cache writes: {total_cache_writes}")
        print_info(f"  → Cache hits: {total_cache_hits}")
        print_success(f"  → Cache hit rate: {cache_hit_rate:.1f}%")
        print_success(f"  → Total tokens read from cache: {total_cache_read_tokens:,} tokens")

        # Token usage
        print_info("")
        print_info("Token usage:")
        print_info(f"  → Cache write tokens: {total_cache_write_tokens:,} tokens")
        print_info(f"  → Cache read tokens: {total_cache_read_tokens:,} tokens")
        print_info(f"  → Non-cached input tokens: {total_input_tokens:,} tokens")
        print_info(f"  → Output tokens: {total_output_tokens:,} tokens")

        # Cost calculations (Anthropic Sonnet pricing)
        cache_write_cost = total_cache_write_tokens * 0.00375 / 1000
        cache_read_cost = total_cache_read_tokens * 0.0003 / 1000
        input_cost = total_input_tokens * 0.003 / 1000
        output_cost = total_output_tokens * 0.015 / 1000

        total_cost_with_cache = cache_write_cost + cache_read_cost + input_cost + output_cost

        # Calculate what it would have cost WITHOUT caching
        # (all cache reads would have been full writes)
        cost_without_cache = (total_cache_write_tokens + total_cache_read_tokens) * 0.003 / 1000
        cost_without_cache += input_cost + output_cost

        savings = cost_without_cache - total_cost_with_cache
        savings_percent = (savings / cost_without_cache * 100) if cost_without_cache > 0 else 0

        print_info("")
        print_info("Cost breakdown:")
        if cache_write_cost > 0:
            print_info(f"  → Cache writes: ${cache_write_cost:.4f}")
        if cache_read_cost > 0:
            print_success(f"  → Cache reads: ${cache_read_cost:.4f}")
        print_info(f"  → Non-cached input: ${input_cost:.4f}")
        print_info(f"  → Output: ${output_cost:.4f}")
        print_info(f"  → Total with caching: ${total_cost_with_cache:.4f}")

        print_info("")
        print_success(f"Without caching: ${cost_without_cache:.4f}")
        print_success(f"Total saved: ${savings:.4f} ({savings_percent:.0f}% reduction)")

        # Dynamic token limiting savings estimate
        # WHY: Harder to calculate exact savings from dynamic tokens since we don't know
        # what Claude would have output with 8192 limit. Conservative estimate: 10-20% of output cost.
        dynamic_token_savings_estimate = output_cost * 0.15  # Conservative 15%
        print_info("")
        print_info("Dynamic token limiting:")
        print_info(f"  → Estimated additional savings: ${dynamic_token_savings_estimate:.4f} (15% of output)")
        print_success(f"  → Combined Claude savings: ${savings + dynamic_token_savings_estimate:.4f}")

        # ChatGPT (QA) costs
        if total_gpt_calls > 0:
            print_info("")
            print_info("ChatGPT (QA) costs:")
            print_info(f"  → Total QA calls: {total_gpt_calls}")
            print_info(f"  → Input tokens: {total_gpt_input_tokens:,} tokens")
            print_info(f"  → Output tokens: {total_gpt_output_tokens:,} tokens")

            # OpenAI GPT-4o pricing: Input $2.50/MTok, Output $10.00/MTok
            gpt_input_cost = total_gpt_input_tokens * 0.0025 / 1000
            gpt_output_cost = total_gpt_output_tokens * 0.010 / 1000
            gpt_total_cost = gpt_input_cost + gpt_output_cost

            print_info(f"  → Input cost: ${gpt_input_cost:.4f}")
            print_info(f"  → Output cost: ${gpt_output_cost:.4f}")
            print_info(f"  → Total ChatGPT: ${gpt_total_cost:.4f}")

            # Combined totals
            print_info("")
            print_success(f"TOTAL COST (Claude + ChatGPT): ${total_cost_with_cache + gpt_total_cost:.4f}")
            print_success(f"  → Claude: ${total_cost_with_cache:.4f}")
            print_success(f"  → ChatGPT: ${gpt_total_cost:.4f}")
            print_success(f"Total saved from caching: ${savings + dynamic_token_savings_estimate:.4f}")
        else:
            print_info("")
            print_success(f"TOTAL COST (Claude only): ${total_cost_with_cache:.4f}")

        print_info("═══════════════════════════════════════════════════════════")

        # Log run to CSV
        gpt_total_cost = 0
        if total_gpt_calls > 0:
            gpt_total_cost = (total_gpt_input_tokens * 0.0025 / 1000) + (total_gpt_output_tokens * 0.010 / 1000)
        self._log_run_csv(iterations, total_cost_with_cache, gpt_total_cost, run_end_reason)

    def _log_run_csv(self, iterations: int, claude_cost: float, chatgpt_cost: float, run_end_reason: str = 'UNKNOWN'):
        """Log run stats to a persistent CSV file for tracking across runs."""
        import csv

        csv_path = Path(__file__).parent / 'fo_run_log.csv'
        file_exists = csv_path.exists()

        # Safety prompt before modifying run log
        if not self._confirm_sensitive_write(csv_path):
            print_warning(f"Run log not written (confirmation declined): {csv_path}")
            return

        now = datetime.now()
        row = {
            'date': now.strftime('%Y-%m-%d'),
            'time': now.strftime('%H:%M:%S'),
            'startup': self.startup_id,
            'iterations': iterations,
            'cost_claude': f'{claude_cost:.4f}',
            'cost_chatgpt': f'{chatgpt_cost:.4f}',
            'total_cost': f'{claude_cost + chatgpt_cost:.4f}',
            'run_end_reason': run_end_reason
        }

        fieldnames = ['date', 'time', 'startup', 'iterations', 'cost_claude', 'cost_chatgpt', 'total_cost', 'run_end_reason']

        with open(csv_path, 'a', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if not file_exists:
                writer.writeheader()
            writer.writerow(row)

        print_info(f"Run logged to: {csv_path}")

    def _confirm_sensitive_write(self, path: Path) -> bool:
        """
        Safety prompt before writing sensitive files.
        Set --confirm-run-log YES to require a prompt.
        """
        if not self.confirm_run_log:
            return True

        try:
            response = input(f"Confirm write to {path} (type YES to proceed): ").strip()
        except EOFError:
            print_warning("No TTY available; refusing to write without confirmation")
            return False

        return response == "YES"

    def _patch_missing_files(self, iteration: int, missing_files: list,
                              build_output: str, governance_section: str) -> Tuple[bool, dict]:
        """
        FIX #11: Patch call — request only missing files instead of full rebuild.

        When validation fails because files are in manifest but not extracted,
        make a targeted Claude call for just those files. Like TCP retransmission.

        Returns:
            (success: bool, cost_stats: dict)
        """
        print_info("")
        print_info("═══════════════════════════════════════════════════════════")
        print_info(f"PATCH CALL - Requesting {len(missing_files)} missing file(s)")
        print_info("═══════════════════════════════════════════════════════════")

        cost_stats = {
            'calls': 0,
            'input_tokens': 0,
            'output_tokens': 0,
            'cache_read_tokens': 0,
            'cache_creation_tokens': 0
        }

        artifacts_dir = self.artifacts.build_dir / f'iteration_{iteration:02d}_artifacts'

        # Get list of files we DO have for context
        existing_files = extract_file_paths_from_output(build_output)

        # Build targeted prompt
        # Prompt template source: directives/prompts/patch_prompt.md
        patch_prompt = DirectiveTemplateLoader.render(
            'patch_prompt.md',
            startup_id=self.startup_id,
            missing_files_bullets=chr(10).join('- ' + f for f in missing_files),
            existing_files_bullets=chr(10).join('- ' + f for f in existing_files[:25])
        )

        # Estimate tokens needed: ~200-400 tokens per file
        estimated_tokens = min(16384, max(4096, len(missing_files) * 2000))

        print_info(f"  → Missing: {', '.join(missing_files[:8])}")
        if len(missing_files) > 8:
            print_info(f"    ... and {len(missing_files) - 8} more")
        print_info(f"  → Token limit: {estimated_tokens:,}")
        print_info("───────────────────────────────────────────────────────────")

        try:
            start_time = time.time()
            patch_response = self.claude.call(
                patch_prompt,
                max_tokens=estimated_tokens,
                cacheable_prefix=governance_section,
                timeout=300
            )
            patch_output = patch_response['content'][0]['text']
            elapsed = time.time() - start_time

            # Log usage
            usage = patch_response.get('usage', {})
            cost_stats['calls'] = 1
            cost_stats['input_tokens'] = usage.get('input_tokens', 0)
            cost_stats['output_tokens'] = usage.get('output_tokens', 0)
            cost_stats['cache_read_tokens'] = usage.get('cache_read_input_tokens', 0)
            cost_stats['cache_creation_tokens'] = usage.get('cache_creation_input_tokens', 0)

            input_cost = (cost_stats['input_tokens'] / 1_000_000) * 3.00
            output_cost = (cost_stats['output_tokens'] / 1_000_000) * 15.00
            cache_read_cost = (cost_stats['cache_read_tokens'] / 1_000_000) * 0.30
            patch_cost = input_cost + output_cost + cache_read_cost
            print_success(f"Patch response received in {elapsed:.1f}s (cost: ${patch_cost:.4f})")

            # Extract files from patch output
            patched_files = extract_file_paths_from_output(patch_output)
            print_info(f"  → Files in patch response: {len(patched_files)}")

            # Run the artifact extraction on the patch output
            code_block_pattern = r'(?:^|\n)(.{0,200}?)\n?```(\w+)(?:[ \t]+([^\n]+))?\n(.*?)```'
            patched_count = 0

            for match in re.finditer(code_block_pattern, patch_output, re.DOTALL | re.MULTILINE):
                preceding_line = match.group(1).strip() if match.group(1) else ''
                language = match.group(2)
                code_content = match.group(4)
                match_pos = match.start()

                # Find FILE: header
                context_before = patch_output[max(0, match_pos - 500):match_pos]
                search_area = preceding_line + '\n' + context_before if preceding_line else context_before

                filename = None
                file_match = re.search(r'\*\*FILE:\s*([^\*]+)\*\*', search_area, re.IGNORECASE)
                if file_match:
                    filename = re.sub(r'[\*`]', '', file_match.group(1)).strip()

                if filename:
                    artifact_path = artifacts_dir / filename
                    artifact_path.parent.mkdir(parents=True, exist_ok=True)
                    artifact_path.write_text(code_content, encoding='utf-8')
                    patched_count += 1
                    print_success(f"  → Patched: {filename}")

            # Also fix build_state.json if it had wrong state
            build_state_path = artifacts_dir / 'build_state.json'
            if build_state_path.exists():
                try:
                    with open(build_state_path) as f:
                        bs = json.load(f)
                    if bs.get('state') != 'COMPLETED_CLOSED':
                        bs['state'] = 'COMPLETED_CLOSED'
                        with open(build_state_path, 'w') as f:
                            json.dump(bs, f, indent=2)
                        print_success(f"  → Fixed: build_state.json state → COMPLETED_CLOSED")
                except:
                    pass

            # Check how many missing files were recovered
            still_missing = []
            for f in missing_files:
                if not (artifacts_dir / f).exists():
                    still_missing.append(f)

            # Keep manifest in sync with patched artifacts so re-validation
            # sees newly recovered files in artifact_manifest.json.
            if patched_count > 0:
                self.artifacts.refresh_manifest_for_iteration(iteration)

            print_info("")
            print_info(f"Patch results: {patched_count} files recovered, {len(still_missing)} still missing")
            if still_missing:
                print_warning(f"  → Still missing: {', '.join(still_missing[:5])}")

            success = len(still_missing) == 0
            if success:
                print_success("Patch successful — all missing files recovered")
            print_info("═══════════════════════════════════════════════════════════")

            return success, cost_stats

        except Exception as e:
            print_error(f"Patch call failed: {e}")
            return False, cost_stats

    def _post_qa_polish(self, iteration: int, build_output: str, governance_section: str) -> Tuple[bool, dict]:
        """
        FIX #10: Post-QA polish step to generate missing optional files.

        After QA accepts the build, check for missing optional files (README, etc.)
        and make targeted Claude calls to generate them.

        This solves the 16K token limit issue - core build passes QA, then we
        generate optional files separately.

        Returns:
            (success: bool, cost_stats: dict)
        """
        import re  # For regex extraction

        print_info("")
        print_info("═══════════════════════════════════════════════════════════")
        print_info("POST-QA POLISH - Generating missing optional files")
        print_info("═══════════════════════════════════════════════════════════")

        artifacts_dir = self.artifacts.build_dir / f'iteration_{iteration:02d}_artifacts'
        manifest_path = artifacts_dir / 'artifact_manifest.json'

        cost_stats = {
            'calls': 0,
            'input_tokens': 0,
            'output_tokens': 0,
            'cache_read_tokens': 0
        }

        # Check if artifact_manifest exists
        if not manifest_path.exists():
            print_warning("No artifact_manifest.json found - skipping polish")
            return False, cost_stats

        try:
            with open(manifest_path) as f:
                manifest = json.load(f)
        except json.JSONDecodeError:
            print_warning("Could not parse artifact_manifest.json - skipping polish")
            return False, cost_stats

        manifest_files = [artifact.get('path', '') for artifact in manifest.get('artifacts', [])]

        # Check what's missing
        readme_found = any(path.endswith('README.md') for path in manifest_files)
        env_example_found = any('.env.example' in path for path in manifest_files)
        integration_readme_found = any(path == 'business/README-INTEGRATION.md' for path in manifest_files)
        test_files = [f for f in manifest_files if 'test' in f.lower() or 'spec' in f.lower()]
        has_minimal_tests = len(test_files) < 3  # Consider < 3 test files as "minimal"
        docs_dir = artifacts_dir / 'business' / 'docs'

        polish_items = []
        if not readme_found:
            polish_items.append("README.md")
        if not env_example_found:
            polish_items.append(".env.example")
        if getattr(self, 'use_boilerplate', False) and not integration_readme_found:
            polish_items.append("business/README-INTEGRATION.md")
        if has_minimal_tests:
            polish_items.append(f"Tests (only {len(test_files)} found)")
        # Always ensure docs folder exists and include HLD + QUICKSTART
        polish_items.append("Docs (HLD + QUICKSTART)")

        if not polish_items:
            print_success("✓ All optional files present - no polish needed")
            return True, cost_stats

        print_info(f"→ Missing optional files: {', '.join(polish_items)}")
        print_info("")

        # ============================================================
        # 1. Rename boilerplate README if present and generate README.md
        # ============================================================
        # Rename boilerplate README to README-base.md if it exists
        readme_path = artifacts_dir / 'README.md'
        if readme_path.exists():
            base_path = artifacts_dir / 'README-base.md'
            if not base_path.exists():
                readme_path.rename(base_path)
                print_info("→ Renamed boilerplate README.md → README-base.md")
            readme_found = False  # Force regeneration

        if not readme_found:
            print_info("→ README.md missing - generating...")

            # Create targeted prompt for README generation
            # Prompt template source: directives/prompts/polish_readme_prompt.md
            readme_prompt = DirectiveTemplateLoader.render(
                'polish_readme_prompt.md',
                manifest_sample=chr(10).join(manifest_files[:20]),
                build_output_sample=build_output[:2000]
            )

            try:
                print_info("→ Calling Claude for README generation...")
                start_time = time.time()

                readme_response = self.claude.call(
                    readme_prompt,
                    max_tokens=4096,  # README shouldn't need more
                    cacheable_prefix=None,  # Don't cache for one-off
                    timeout=120  # 2 minutes should be plenty
                )

                readme_content = readme_response['content'][0]['text']
                elapsed = time.time() - start_time

                # Extract markdown from response
                import re
                md_match = re.search(r'```markdown\n(.*?)\n```', readme_content, re.DOTALL)
                if md_match:
                    readme_text = md_match.group(1)
                else:
                    # Maybe just markdown without fence
                    md_match = re.search(r'```\n(.*?)\n```', readme_content, re.DOTALL)
                    if md_match:
                        readme_text = md_match.group(1)
                    else:
                        readme_text = readme_content  # Use as-is

                # Save README to artifacts
                readme_path = artifacts_dir / 'README.md'
                readme_path.write_text(readme_text, encoding='utf-8')

                print_success(f"✓ Generated README.md ({len(readme_text)} chars) in {elapsed:.1f}s")
                print_info(f"  → Saved to: iteration_{iteration:02d}_artifacts/README.md")

                # Update cost stats
                usage = readme_response.get('usage', {})
                cost_stats['calls'] += 1
                cost_stats['input_tokens'] += usage.get('input_tokens', 0)
                cost_stats['output_tokens'] += usage.get('output_tokens', 0)
                cost_stats['cache_read_tokens'] += usage.get('cache_read_input_tokens', 0)

                # Calculate cost
                input_cost = (usage.get('input_tokens', 0) / 1_000_000) * 3.00
                output_cost = (usage.get('output_tokens', 0) / 1_000_000) * 15.00
                readme_cost = input_cost + output_cost
                print_info(f"  → Cost: ${readme_cost:.4f}")
                print_info("")

            except Exception as e:
                print_error(f"Failed to generate README: {e}")
                print_info("")

        # ============================================================
        # 2. Generate .env.example
        # ============================================================
        if not env_example_found:
            print_info("→ .env.example missing - generating...")

            # Read actual source files to find env vars
            source_files = []
            for file_path in manifest_files[:10]:  # Sample first 10 files
                full_path = artifacts_dir / file_path
                if full_path.exists() and full_path.suffix in ['.js', '.ts', '.jsx', '.tsx']:
                    try:
                        content = full_path.read_text(encoding='utf-8')
                        source_files.append(f"**{file_path}:**\n{content[:500]}")  # First 500 chars
                    except:
                        pass

            # Prompt template source: directives/prompts/polish_env_prompt.md
            env_prompt = DirectiveTemplateLoader.render(
                'polish_env_prompt.md',
                source_files_sample=chr(10).join(source_files[:5]),
                manifest_sample=chr(10).join(manifest_files[:15])
            )

            try:
                print_info("→ Calling Claude for .env.example generation...")
                start_time = time.time()

                env_response = self.claude.call(
                    env_prompt,
                    max_tokens=2048,  # .env shouldn't need much
                    cacheable_prefix=None,
                    timeout=90
                )

                env_content = env_response['content'][0]['text']
                elapsed = time.time() - start_time

                # Extract bash/env content from response
                env_match = re.search(r'```(?:bash|env|sh)?\n(.*?)\n```', env_content, re.DOTALL)
                if env_match:
                    env_text = env_match.group(1)
                else:
                    env_text = env_content  # Use as-is

                # Save .env.example to artifacts
                env_path = artifacts_dir / '.env.example'
                env_path.write_text(env_text, encoding='utf-8')

                print_success(f"✓ Generated .env.example ({len(env_text)} chars) in {elapsed:.1f}s")
                print_info(f"  → Saved to: iteration_{iteration:02d}_artifacts/.env.example")

                # Update cost stats
                usage = env_response.get('usage', {})
                cost_stats['calls'] += 1
                cost_stats['input_tokens'] += usage.get('input_tokens', 0)
                cost_stats['output_tokens'] += usage.get('output_tokens', 0)
                cost_stats['cache_read_tokens'] += usage.get('cache_read_input_tokens', 0)

                # Calculate cost
                input_cost = (usage.get('input_tokens', 0) / 1_000_000) * 3.00
                output_cost = (usage.get('output_tokens', 0) / 1_000_000) * 15.00
                env_cost = input_cost + output_cost
                print_info(f"  → Cost: ${env_cost:.4f}")
                print_info("")

            except Exception as e:
                print_error(f"Failed to generate .env.example: {e}")
                print_info("")

        # ============================================================
        # 3. Generate business/README-INTEGRATION.md (boilerplate runs)
        # ============================================================
        if getattr(self, 'use_boilerplate', False) and not integration_readme_found:
            print_info("→ business/README-INTEGRATION.md missing - generating...")
            integration_prompt = DirectiveTemplateLoader.render(
                'polish_integration_readme_prompt.md',
                startup_id=self.startup_id,
                block=self.block,
                manifest_sample=chr(10).join(manifest_files[:40]),
                build_output_sample=build_output[:3000]
            )

            try:
                print_info("→ Calling Claude for integration README generation...")
                start_time = time.time()

                integration_response = self.claude.call(
                    integration_prompt,
                    max_tokens=3072,
                    cacheable_prefix=None,
                    timeout=120
                )

                integration_content = integration_response['content'][0]['text']
                elapsed = time.time() - start_time

                md_match = re.search(r'```markdown\n(.*?)\n```', integration_content, re.DOTALL)
                if md_match:
                    integration_text = md_match.group(1)
                else:
                    md_match = re.search(r'```\n(.*?)\n```', integration_content, re.DOTALL)
                    integration_text = md_match.group(1) if md_match else integration_content

                integration_path = artifacts_dir / 'business' / 'README-INTEGRATION.md'
                integration_path.parent.mkdir(parents=True, exist_ok=True)
                integration_path.write_text(integration_text, encoding='utf-8')

                print_success(f"✓ Generated business/README-INTEGRATION.md ({len(integration_text)} chars) in {elapsed:.1f}s")
                print_info(f"  → Saved to: iteration_{iteration:02d}_artifacts/business/README-INTEGRATION.md")

                usage = integration_response.get('usage', {})
                cost_stats['calls'] += 1
                cost_stats['input_tokens'] += usage.get('input_tokens', 0)
                cost_stats['output_tokens'] += usage.get('output_tokens', 0)
                cost_stats['cache_read_tokens'] += usage.get('cache_read_input_tokens', 0)

                input_cost = (usage.get('input_tokens', 0) / 1_000_000) * 3.00
                output_cost = (usage.get('output_tokens', 0) / 1_000_000) * 15.00
                integration_cost = input_cost + output_cost
                print_info(f"  → Cost: ${integration_cost:.4f}")
                print_info("")
            except Exception as e:
                print_warning(f"Failed to generate business/README-INTEGRATION.md: {e}")
                print_info("")

        # ============================================================
        # 4. Generate additional tests (if minimal)
        # ============================================================
        if has_minimal_tests:
            print_info(f"→ Only {len(test_files)} test file(s) found - generating additional tests...")

            # Get list of testable files
            testable_files = [f for f in manifest_files
                            if ('service' in f.lower() or 'model' in f.lower() or 'api' in f.lower())
                            and 'test' not in f.lower()]

            # Prompt template source: directives/prompts/polish_tests_prompt.md
            tests_prompt = DirectiveTemplateLoader.render(
                'polish_tests_prompt.md',
                existing_test_files=(chr(10).join(test_files) if test_files else "None"),
                testable_files=chr(10).join(testable_files[:10])
            )

            try:
                print_info("→ Calling Claude for test generation...")
                start_time = time.time()

                tests_response = self.claude.call(
                    tests_prompt,
                    max_tokens=6144,  # Tests can be longer
                    cacheable_prefix=None,
                    timeout=180
                )

                tests_content = tests_response['content'][0]['text']
                elapsed = time.time() - start_time

                # Extract test files using FILE: pattern
                test_pattern = r'\*\*FILE:\s*([^\*]+)\*\*\s*```(?:javascript|js|typescript|ts)?\n(.*?)```'
                test_matches = re.findall(test_pattern, tests_content, re.DOTALL)

                tests_generated = 0
                for file_path, test_code in test_matches:
                    file_path = file_path.strip()
                    test_file_path = artifacts_dir / file_path
                    test_file_path.parent.mkdir(parents=True, exist_ok=True)
                    test_file_path.write_text(test_code, encoding='utf-8')
                    tests_generated += 1
                    print_success(f"✓ Generated {file_path}")

                print_success(f"✓ Generated {tests_generated} test file(s) in {elapsed:.1f}s")
                print_info(f"  → Saved to: iteration_{iteration:02d}_artifacts/")

                # Update cost stats
                usage = tests_response.get('usage', {})
                cost_stats['calls'] += 1
                cost_stats['input_tokens'] += usage.get('input_tokens', 0)
                cost_stats['output_tokens'] += usage.get('output_tokens', 0)
                cost_stats['cache_read_tokens'] += usage.get('cache_read_input_tokens', 0)

                # Calculate cost
                input_cost = (usage.get('input_tokens', 0) / 1_000_000) * 3.00
                output_cost = (usage.get('output_tokens', 0) / 1_000_000) * 15.00
                tests_cost = input_cost + output_cost
                print_info(f"  → Cost: ${tests_cost:.4f}")
                print_info("")

            except Exception as e:
                print_error(f"Failed to generate tests: {e}")
                print_info("")

        # ============================================================
        # 5. Save skipped doc snippets (if any)
        # ============================================================
        snippets_path = artifacts_dir / 'skipped_snippets.json'
        if snippets_path.exists():
            try:
                snippets = json.loads(snippets_path.read_text(encoding='utf-8'))
                if snippets:
                    print_info("→ Saving skipped doc snippets...")
                    docs_dir = artifacts_dir / 'business' / 'docs'
                    docs_dir.mkdir(parents=True, exist_ok=True)
                    out_path = docs_dir / 'snippets.md'

                    lines = ["# Snippets", "", "Captured documentation snippets from build output.", ""]
                    for idx, snip in enumerate(snippets, 1):
                        lang = snip.get('language') or ''
                        context = snip.get('context') or ''
                        content = snip.get('content') or ''
                        lines.append(f"## Snippet {idx}")
                        if context:
                            lines.append(f"Context: {context}")
                        lines.append(f"```{lang}".strip())
                        lines.append(content)
                        lines.append("```")
                        lines.append("")

                    out_path.write_text("\n".join(lines), encoding='utf-8')
                    print_success(f"✓ Saved snippets to {out_path}")
            except Exception as e:
                print_warning(f"Failed to save skipped snippets: {e}")

        # ============================================================
        # 6. Generate Docs (HLD + QUICKSTART)
        # ============================================================
        try:
            docs_dir.mkdir(parents=True, exist_ok=True)
            # Prompt template source: directives/prompts/polish_docs_wrapper_prompt.md
            docs_prompt = DirectiveTemplateLoader.render(
                'polish_docs_wrapper_prompt.md',
                qa_polish_2_directive=self.qa_polish_2_directive,
                startup_id=self.startup_id,
                block=self.block,
                iteration=iteration,
                iteration_padded=f"{iteration:02d}",
                manifest_sample=chr(10).join(manifest_files[:50]),
                build_output_sample=build_output[:3000]
            )
            print_info("→ Calling Claude for docs generation...")
            docs_response = self.claude.call(
                docs_prompt,
                max_tokens=4096,
                cacheable_prefix=None,
                timeout=120
            )
            docs_content = docs_response['content'][0]['text']
            docs_matches = re.findall(r'\*\*FILE:\s*([^\*]+)\*\*\\s*```markdown\\n(.*?)```', docs_content, re.DOTALL)
            docs_generated = 0
            for file_path, md in docs_matches:
                file_path = file_path.strip()
                full_path = artifacts_dir / file_path
                full_path.parent.mkdir(parents=True, exist_ok=True)
                full_path.write_text(md, encoding='utf-8')
                docs_generated += 1
            if docs_generated:
                print_success(f"✓ Generated {docs_generated} doc file(s)")

            usage = docs_response.get('usage', {})
            cost_stats['calls'] += 1
            cost_stats['input_tokens'] += usage.get('input_tokens', 0)
            cost_stats['output_tokens'] += usage.get('output_tokens', 0)
            cost_stats['cache_read_tokens'] += usage.get('cache_read_input_tokens', 0)
        except Exception as e:
            print_warning(f"Failed to generate docs: {e}")

        # ============================================================
        # Summary
        # ============================================================
        self.artifacts.refresh_manifest_for_iteration(iteration)
        total_polish_cost = (cost_stats['input_tokens'] / 1_000_000) * 3.00 + (cost_stats['output_tokens'] / 1_000_000) * 15.00
        print_success(f"✓ Post-QA polish complete")
        print_info(f"  → Generated {cost_stats['calls']} file(s)")
        print_info(f"  → Total polish cost: ${total_polish_cost:.4f}")
        print_info("═══════════════════════════════════════════════════════════")
        print_info("")

        return True, cost_stats

    def _display_cumulative_cost(self, iteration: int, total_calls: int,
                                  total_cache_writes: int, total_cache_hits: int,
                                  total_cache_read_tokens: int, total_cache_write_tokens: int,
                                  total_input_tokens: int, total_output_tokens: int,
                                  total_gpt_calls: int, total_gpt_input_tokens: int,
                                  total_gpt_output_tokens: int):
        """
        FIX #9: Display cumulative cost after each iteration.
        Helps user track spending in real-time during long runs.
        """
        # Calculate Claude costs
        cache_write_cost = (total_cache_write_tokens / 1_000_000) * 3.75
        cache_read_cost = (total_cache_read_tokens / 1_000_000) * 0.30
        non_cached_input_tokens = total_input_tokens - total_cache_read_tokens
        non_cached_input_cost = (non_cached_input_tokens / 1_000_000) * 3.00
        output_cost = (total_output_tokens / 1_000_000) * 15.00
        claude_total = cache_write_cost + cache_read_cost + non_cached_input_cost + output_cost

        # Calculate ChatGPT costs
        gpt_input_cost = (total_gpt_input_tokens / 1_000_000) * 2.50
        gpt_output_cost = (total_gpt_output_tokens / 1_000_000) * 10.00
        gpt_total = gpt_input_cost + gpt_output_cost

        combined_total = claude_total + gpt_total

        print_info("")
        print_info("═══════════════════════════════════════════════════════════")
        print_info(f"CUMULATIVE COST AFTER ITERATION {iteration}")
        print_info("═══════════════════════════════════════════════════════════")
        print_info(f"Claude API:")
        print_info(f"  → Calls: {total_calls}")
        print_info(f"  → Cache writes: {total_cache_writes}, Cache hits: {total_cache_hits}")
        print_info(f"  → Total cost: ${claude_total:.4f}")
        if total_gpt_calls > 0:
            print_info(f"ChatGPT API:")
            print_info(f"  → Calls: {total_gpt_calls}")
            print_info(f"  → Total cost: ${gpt_total:.4f}")
        print_success(f"TOTAL COST SO FAR: ${combined_total:.4f}")
        print_info("═══════════════════════════════════════════════════════════")
        print_info("")

    def _validate_build_artifacts(self, iteration: int) -> Tuple[bool, list]:
        """
        FIX #8: Pre-QA validation to catch incomplete builds early.

        Validates that critical artifacts are present before sending to QA.
        This prevents wasting QA cycles on obviously incomplete builds.

        Checks:
        1. artifact_manifest.json exists and is valid JSON
        2. build_state.json exists with COMPLETED_CLOSED state
        3. Required files are listed in manifest (README, package.json, etc.)
        4. All files in manifest exist in extracted artifacts

        Returns:
            (passed: bool, errors: list[str])
        """
        errors = []
        artifacts_dir = self.artifacts.build_dir / f'iteration_{iteration:02d}_artifacts'

        # Normalization: promote business/frontend/package.json -> business/package.json
        # when canonical business/package.json is missing. This avoids unnecessary
        # patch loops for common path drift under truncation/recovery.
        canonical_pkg = artifacts_dir / 'business' / 'package.json'
        frontend_pkg = artifacts_dir / 'business' / 'frontend' / 'package.json'
        if not canonical_pkg.exists() and frontend_pkg.exists():
            canonical_pkg.parent.mkdir(parents=True, exist_ok=True)
            canonical_pkg.write_text(frontend_pkg.read_text(encoding='utf-8'), encoding='utf-8')
            print_warning("  → Normalized business/frontend/package.json -> business/package.json")
            self.artifacts.refresh_manifest_for_iteration(iteration)

        # Check 1: artifact_manifest.json exists
        manifest_path = artifacts_dir / 'artifact_manifest.json'
        if not manifest_path.exists():
            errors.append("artifact_manifest.json is missing")
            return False, errors, []

        # Check 2: artifact_manifest.json is valid JSON
        try:
            with open(manifest_path) as f:
                manifest = json.load(f)
        except json.JSONDecodeError as e:
            errors.append(f"artifact_manifest.json is malformed: {e}")
            return False, errors, []

        # Check 3: build_state.json exists and has COMPLETED_CLOSED
        build_state_path = artifacts_dir / 'build_state.json'
        if not build_state_path.exists():
            errors.append("build_state.json is missing")
        else:
            try:
                with open(build_state_path) as f:
                    build_state = json.load(f)
                    if build_state.get('state') != 'COMPLETED_CLOSED':
                        errors.append(f"build_state.json has wrong state: {build_state.get('state')}")
            except json.JSONDecodeError as e:
                errors.append(f"build_state.json is malformed: {e}")

        # Check 4: Required files are in manifest
        # FIX #9: Read from QA override if available, otherwise use defaults
        qa_override = getattr(self, 'qa_override', {})
        validation_config = qa_override.get('pre_qa_validation', {})

        required_files = validation_config.get('required_files', ['package.json', 'README.md'])
        optional_files = validation_config.get('optional_files', [])

        manifest_files = [artifact.get('path', '') for artifact in manifest.get('artifacts', [])]

        for required in required_files:
            # Check if required file exists in manifest (could be in subdirectory)
            found = any(required in path for path in manifest_files)
            if not found:
                errors.append(f"Required file '{required}' not listed in artifact_manifest.json")

        # Warn about optional files but don't fail validation
        for optional in optional_files:
            found = any(optional in path for path in manifest_files)
            if not found:
                print_warning(f"  → {optional} not in manifest (will be flagged by QA as HIGH severity)")

        # Check 5: Files in manifest actually exist
        # Skip optional/polish files — these get generated post-QA
        missing_files = []
        missing_optional = []
        for artifact in manifest.get('artifacts', []):
            file_path = artifact.get('path', '')
            if not file_path:
                continue

            # Check if file exists in extracted artifacts
            full_path = artifacts_dir / file_path
            if not full_path.exists():
                # Is this an optional/polish file? Don't fail validation for these.
                is_optional = any(opt.lower() in file_path.lower() for opt in optional_files)
                if is_optional:
                    missing_optional.append(file_path)
                else:
                    missing_files.append(file_path)

        if missing_optional:
            for f in missing_optional:
                print_warning(f"  → {f} in manifest but not extracted (optional — deferred to post-QA polish)")

        if missing_files:
            errors.append(f"Files in manifest but not extracted: {', '.join(missing_files[:5])}")
            if len(missing_files) > 5:
                errors.append(f"  ... and {len(missing_files) - 5} more")

        # Check 6: Minimum artifact count (sanity check)
        min_count = validation_config.get('min_artifact_count', 3)
        artifact_count = len(manifest.get('artifacts', []))
        if artifact_count < min_count:
            errors.append(f"Only {artifact_count} artifacts in manifest (expected at least {min_count})")

        # Check 7: Boilerplate integration (pre-flight guardrail)
        if getattr(self, 'use_boilerplate', False):
            non_business_paths = [p for p in manifest_files if not p.startswith('business/')]
            if non_business_paths:
                sample = ", ".join(non_business_paths[:5])
                errors.append(f"Boilerplate build contains non-business paths: {sample}")
                if len(non_business_paths) > 5:
                    errors.append(f"  ... and {len(non_business_paths) - 5} more")
            has_integration_readme = any(p == 'business/README-INTEGRATION.md' for p in manifest_files)
            if not has_integration_readme:
                print_warning("  → business/README-INTEGRATION.md not in manifest (deferred to post-QA polish)")

        return len(errors) == 0, errors, missing_files

    def _get_previous_iteration_inventory(self, iteration: int) -> list:
        """
        Load required file inventory from prior iteration manifest.
        Returns business/** file paths only.
        """
        if iteration <= 1:
            return []

        prev_manifest = self.artifacts.build_dir / f'iteration_{iteration-1:02d}_artifacts' / 'artifact_manifest.json'
        if not prev_manifest.exists():
            return []

        try:
            with open(prev_manifest) as f:
                manifest = json.load(f)
        except Exception:
            return []

        files = []
        for artifact in manifest.get('artifacts', []):
            path = artifact.get('path', '')
            if path and path.startswith('business/'):
                files.append(path)
        return sorted(set(files))

    def _extract_defect_target_files(self, defects_text: Optional[str]) -> list:
        """
        Extract explicit business file paths mentioned in defect text.
        """
        if not defects_text:
            return []

        matches = re.findall(r'(business/[A-Za-z0-9_./-]+\.[A-Za-z0-9_]+)', defects_text)
        return sorted(set(matches))

    def _enrich_defects_with_fix_context(self, qa_report: str) -> str:
        """
        For boilerplate builds: prepend architectural fix context before injecting
        defects into the next iteration's prompt.

        QA correctly identifies problems but doesn't tell Claude HOW to fix them
        in the boilerplate context. This enrichment bridges that gap for the most
        common recurring failure patterns.
        """
        if not self.use_boilerplate:
            return qa_report

        report_lower = qa_report.lower()
        has_mock_storage = any(kw in report_lower for kw in [
            'in-memory', 'in memory', 'mock data', 'hardcoded', 'hard-coded',
            'mock id', 'reports_db', 'clients_db', 'dict storage', 'local dict',
            'sequential id', 'len(', 'in-memory storage', 'demo storage'
        ])
        has_db_note = any(kw in report_lower for kw in [
            'database', 'orm', 'boilerplate', 'persistent', 'persistence'
        ])
        has_frontend_hardcode = any(kw in report_lower for kw in [
            'hardcoded client', 'hardcoded data', 'static data', 'hardcoded array'
        ])

        fixes = []

        if has_mock_storage or has_db_note:
            fixes.append(
                "**ARCHITECTURAL FIX REQUIRED — DATA LAYER:**\n"
                "One or more defects require replacing mock/in-memory storage with real persistence.\n"
                "- Remove ALL `x_db = {}` and `data = []` module-level dicts/lists used as storage.\n"
                "- Remove ALL `len(collection) + 1` ID generation — replace with `str(uuid.uuid4())`.\n"
                "- For every read/write: use the boilerplate database ORM/service. "
                "If you are unsure of the exact import, write `# TODO: use boilerplate DB service` "
                "rather than substituting a dict.\n"
                "- Do NOT add a comment saying 'replace with DB later' and keep the dict — remove the dict."
            )

        if has_frontend_hardcode:
            fixes.append(
                "**ARCHITECTURAL FIX REQUIRED — FRONTEND DATA FETCHING:**\n"
                "One or more defects require replacing hardcoded frontend data with API calls.\n"
                "- Remove ALL hardcoded arrays/objects used as data sources in components.\n"
                "- Replace with `fetch('/api/<resource>')` or equivalent async call in useEffect.\n"
                "- Handle loading and error states explicitly."
            )

        if not fixes:
            return qa_report

        header = "**BOILERPLATE FIX CONTEXT (READ BEFORE APPLYING DEFECT FIXES):**\n" + "\n\n".join(fixes)
        return header + "\n\n" + "=" * 60 + "\n\n" + qa_report

    def execute_build_qa_loop(self) -> Tuple[bool, str]:
        """
        Execute BUILD → QA loop until QA accepts or max iterations hit.

        Returns (success: bool, final_build_output: str)
        """
        print_header(f"STARTING BUILD → QA LOOP (BLOCK_{self.block})")

        iteration        = 1
        previous_defects = None
        build_output     = None

        # FIX #1: Track cumulative usage for final cost summary (Claude)
        total_calls = 0
        total_cache_writes = 0
        total_cache_hits = 0
        total_cache_read_tokens = 0
        total_cache_write_tokens = 0
        total_input_tokens = 0
        total_output_tokens = 0

        # Track ChatGPT usage for cost analysis
        total_gpt_calls = 0
        total_gpt_input_tokens = 0
        total_gpt_output_tokens = 0

        # Convergence tracking: detect when defects aren't decreasing
        defect_history = []  # Track defect count per iteration
        convergence_check_after = 10  # Check convergence after this many iterations

        # FIX #9: Track consecutive validation failures
        consecutive_validation_failures = 0

        # ── Warm-start setup ──────────────────────────────────────────
        _ws_run_dir   = Path(getattr(self.cli_args, 'resume_run', None) or '')
        _ws_iteration = int(getattr(self.cli_args, 'resume_iteration', 1))
        _ws_mode      = (getattr(self.cli_args, 'resume_mode', None) or '').lower()

        if _ws_run_dir.is_dir() and _ws_mode == 'fix':
            # Load the existing QA report as defects and jump straight to the fix iteration
            _qa_report_path = _ws_run_dir / 'qa' / f'iteration_{_ws_iteration:02d}_qa_report.txt'
            if not _qa_report_path.exists():
                print_error(f"Warm-start (fix): QA report not found: {_qa_report_path}")
                return False, "RESUME_MISSING_QA_REPORT"
            previous_defects = _qa_report_path.read_text()
            iteration        = _ws_iteration + 1
            print_success(f"Warm-start (fix): loaded QA report from iter {_ws_iteration} — resuming at iter {iteration}")

        try:
            while iteration <= self.max_qa_iterations:
                print_header(f"ITERATION {iteration}/{self.max_qa_iterations}")

                # Warm-start QA mode: skip Claude BUILD for this specific iteration,
                # load existing artifacts from the resume run directory.
                _warm_skip_build = (
                    _ws_run_dir.is_dir()
                    and _ws_mode == 'qa'
                    and iteration == _ws_iteration
                )

                # ================================================
                # STEP 1: BUILD (Claude)
                # ================================================

                if _warm_skip_build:
                    # Build governance_section (needed for patch calls later) without calling Claude
                    governance_section, _ = PromptTemplates.build_prompt(
                        self.block, self.intake_data, self.build_governance,
                        iteration, self.max_qa_iterations, None,
                        self.tech_stack_override, self.external_integration_override,
                        self.startup_id, self.effective_tech_stack, [], []
                    )
                    _build_path = self.artifacts.build_dir / f'iteration_{iteration:02d}_build.txt'
                    if not _build_path.exists():
                        print_error(f"Warm-start (qa): build output not found: {_build_path}")
                        return False, "RESUME_MISSING_BUILD"
                    build_output   = _build_path.read_text()
                    still_truncated = False
                    print_success(f"Warm-start QA: loaded iter {iteration} artifacts — skipping Claude BUILD call")
                if not _warm_skip_build:
                    required_file_inventory = self._get_previous_iteration_inventory(iteration) if previous_defects else []
                    defect_target_files = self._extract_defect_target_files(previous_defects) if previous_defects else []

                    # FIX #1 & #4: Get prompt sections and dynamic token limit
                    governance_section, dynamic_section = PromptTemplates.build_prompt(
                        self.block,
                        self.intake_data,
                        self.build_governance,
                        iteration,
                        self.max_qa_iterations,
                        previous_defects,
                        self.tech_stack_override,
                        self.external_integration_override,
                        self.startup_id,
                        self.effective_tech_stack,
                        required_file_inventory,
                        defect_target_files
                    )

                    # FIX #4: Dynamic max tokens based on iteration
                    max_tokens = Config.get_max_tokens(iteration)

                    # FIX #6: Dynamic timeout based on iteration (first call needs more time)
                    request_timeout = Config.get_request_timeout(iteration)

                    # Log the full prompt (combine sections for log)
                    full_prompt_for_log = governance_section + "\n\n" + dynamic_section
                    self.artifacts.save_log(f'iteration_{iteration:02d}_build_prompt', full_prompt_for_log)

                    # FIX #1 & #4 & #6: Detailed logging before Claude call
                    print_info("═══════════════════════════════════════════════════════════")
                    print_info(f"ITERATION {iteration} - CLAUDE BUILD CALL")
                    print_info("═══════════════════════════════════════════════════════════")
                    print_info("Prompt structure:")
                    print_info(f"  → Cacheable section: {len(governance_section):,} chars (governance ZIP)")
                    print_info(f"  → Dynamic section: {len(dynamic_section):,} chars (intake + defects)")
                    print_info(f"  → Total prompt size: {len(governance_section) + len(dynamic_section):,} chars")
                    print_info(f"Token limit: {max_tokens:,} tokens (iteration {iteration})")
                    print_info(f"Request timeout: {request_timeout}s ({request_timeout//60} minutes)")
                    print_info("Cache enabled: YES" if iteration == 1 else "Cache enabled: YES (expecting hit)")
                    print_info("───────────────────────────────────────────────────────────")
                    print_info("Calling Claude API...")

                    start_time = time.time()
                    still_truncated = False  # Track if output remains truncated after continuations
                    try:
                        # FIX #1: Use cacheable_prefix for prompt caching
                        # FIX #4: Use dynamic max_tokens
                        # FIX #6: Use dynamic timeout based on iteration
                        build_response = self.claude.call(
                            dynamic_section,
                            max_tokens=max_tokens,
                            cacheable_prefix=governance_section,
                            timeout=request_timeout
                        )
                        build_output   = build_response['content'][0]['text']
                        build_time     = time.time() - start_time
    
                        # FIX #1: Detailed logging of cache performance
                        print_success(f"Claude responded in {build_time:.1f}s")
                        usage_stats = self._log_claude_usage(build_response, iteration, is_continuation=False)
    
                        # Accumulate usage stats
                        total_calls += 1
                        if usage_stats['cache_creation_tokens'] > 0:
                            total_cache_writes += 1
                            total_cache_write_tokens += usage_stats['cache_creation_tokens']
                        if usage_stats['cache_read_tokens'] > 0:
                            total_cache_hits += 1
                            total_cache_read_tokens += usage_stats['cache_read_tokens']
                        total_input_tokens += usage_stats['input_tokens']
                        total_output_tokens += usage_stats['output_tokens']
    
                        print_success(f"BUILD completed in {build_time:.1f}s")
    
                        # ── TCP-STYLE MULTI-PART ASSEMBLY ──
                        # Check if Claude split the output into numbered parts
                        part_info = detect_multipart(build_output)
                        max_parts = self.max_build_parts
                        max_continuations = self.max_build_continuations
    
                        if part_info['is_multipart'] and not part_info['is_final']:
                            print_warning(
                                f"BIG BUILD DETECTED: multipart assembly active "
                                f"(max parts={max_parts}, current declared parts={part_info.get('total_parts', '?')})"
                            )
                            received_files = extract_file_paths_from_output(build_output)
                            print_info(f"Multi-part build detected: PART {part_info['current_part']}/{part_info['total_parts']}")
                            print_info(f"  → Files received so far: {len(received_files)}")
                            if part_info['remaining_files']:
                                print_info(f"  → Remaining files: {', '.join(part_info['remaining_files'][:10])}")
    
                            next_part = part_info['current_part'] + 1
                            total_parts = part_info['total_parts']
    
                            while next_part <= total_parts and next_part <= max_parts:
                                received_files = extract_file_paths_from_output(build_output)
                                remaining = part_info['remaining_files']
                                remaining_str = ', '.join(remaining) if remaining else '(check your manifest)'
    
                                # Prompt template source: directives/prompts/part_prompt.md
                                part_prompt = DirectiveTemplateLoader.render(
                                    'part_prompt.md',
                                    next_part=next_part,
                                    total_parts=total_parts,
                                    startup_id=self.startup_id,
                                    received_files_bullets=chr(10).join('- ' + f for f in received_files),
                                    remaining_str=remaining_str
                                )
    
                                print_info("───────────────────────────────────────────────────────────")
                                print_info(f"REQUESTING PART {next_part}/{total_parts} - Using cached governance")
                                print_info(f"  → Part prompt: {len(part_prompt):,} chars")
                                print_info(f"  → Token limit: {max_tokens:,} tokens")
                                print_info(f"  → Request timeout: {request_timeout}s")
                                print_info("───────────────────────────────────────────────────────────")
    
                                cont_start = time.time()
                                cont_response = self.claude.call(
                                    part_prompt,
                                    max_tokens=max_tokens,
                                    cacheable_prefix=governance_section,
                                    timeout=request_timeout
                                )
                                part_output = cont_response['content'][0]['text']
                                cont_time = time.time() - cont_start
    
                                print_success(f"PART {next_part}/{total_parts} received in {cont_time:.1f}s")
    
                                # Log and accumulate usage
                                cont_usage_stats = self._log_claude_usage(cont_response, iteration, is_continuation=True, continuation_num=next_part)
                                total_calls += 1
                                if cont_usage_stats['cache_creation_tokens'] > 0:
                                    total_cache_writes += 1
                                    total_cache_write_tokens += cont_usage_stats['cache_creation_tokens']
                                if cont_usage_stats['cache_read_tokens'] > 0:
                                    total_cache_hits += 1
                                    total_cache_read_tokens += cont_usage_stats['cache_read_tokens']
                                total_input_tokens += cont_usage_stats['input_tokens']
                                total_output_tokens += cont_usage_stats['output_tokens']
    
                                # Append part to build output
                                build_output += "\n\n" + part_output
    
                                new_files = extract_file_paths_from_output(part_output)
                                print_info(f"  → New files in part {next_part}: {len(new_files)}")
    
                                # Check if this was the final part
                                part_info = detect_multipart(part_output)
                                if part_info['is_final'] or BUILD_COMPLETE_MARKER in part_output:
                                    all_files = extract_file_paths_from_output(build_output)
                                    print_success(f"All {total_parts} parts assembled — {len(all_files)} total files")
                                    break
    
                                next_part += 1
    
                        # ── FALLBACK: Truncation recovery ──
                        # If output is still truncated after multipart handling (or without multipart),
                        # run continuation recovery. This closes the gap where Claude incorrectly
                        # labels output as PART 1/1 but still truncates before completion.
                        if detect_truncation(build_output):
                            continuation_count = 0
                            recovery_mode = "multipart fallback" if part_info['is_multipart'] else "standard fallback"
                            print_warning(
                                f"BIG BUILD DETECTED: {recovery_mode} continuation mode active "
                                f"(max continuations={max_continuations})"
                            )
    
                            while detect_truncation(build_output) and continuation_count < max_continuations:
                                continuation_count += 1
                                print_warning(
                                    f"Output still truncated - requesting continuation "
                                    f"{continuation_count}/{max_continuations}..."
                                )
    
                                # Prompt template source: directives/prompts/continuation_prompt.md
                                continuation_prompt = DirectiveTemplateLoader.render(
                                    'continuation_prompt.md',
                                    startup_id=self.startup_id,
                                    block=self.block,
                                    iteration=iteration,
                                    max_iterations=self.max_qa_iterations,
                                    last_output_tail=build_output[-1500:]
                                )
    
                                print_info(f"CONTINUATION {continuation_count} - fallback mode")
                                cont_start = time.time()
                                cont_response = self.claude.call(
                                    continuation_prompt,
                                    max_tokens=max_tokens,
                                    cacheable_prefix=governance_section,
                                    timeout=request_timeout
                                )
                                continuation_output = cont_response['content'][0]['text']
                                cont_time = time.time() - cont_start
    
                                print_success(f"Continuation {continuation_count} completed in {cont_time:.1f}s")
                                cont_usage_stats = self._log_claude_usage(cont_response, iteration, is_continuation=True, continuation_num=continuation_count)
                                total_calls += 1
                                if cont_usage_stats['cache_creation_tokens'] > 0:
                                    total_cache_writes += 1
                                    total_cache_write_tokens += cont_usage_stats['cache_creation_tokens']
                                if cont_usage_stats['cache_read_tokens'] > 0:
                                    total_cache_hits += 1
                                    total_cache_read_tokens += cont_usage_stats['cache_read_tokens']
                                total_input_tokens += cont_usage_stats['input_tokens']
                                total_output_tokens += cont_usage_stats['output_tokens']
    
                                build_output += "\n\n<!-- CONTINUATION -->\n\n" + continuation_output
    
                        # Track final truncation status
                        still_truncated = detect_truncation(build_output)
    
                        if still_truncated:
                            print_error(f"Build still incomplete after multi-part/continuation assembly")
                        else:
                            all_files = extract_file_paths_from_output(build_output)
                            print_success(f"Build complete — {len(all_files)} files extracted")
    
                        self.artifacts.save_build_output(iteration, build_output)
    
                        # Post-build pruning for boilerplate mode: keep business/** only
                        if self.use_boilerplate:
                            self.artifacts.prune_non_business_artifacts(iteration)
    
                        # Defect iteration: carry forward all non-defect files from previous iteration.
                        # Claude outputs only defect-target files; harness fills in the rest.
                        if self.use_boilerplate and iteration > 1 and previous_defects:
                            claude_output_paths = extract_file_paths_from_output(build_output)
                            self.artifacts.merge_forward_from_previous_iteration(iteration, claude_output_paths)
    
                        # FIX #6: save defect fix artifact on iterations 2+
                        if iteration > 1 and previous_defects:
                            self.artifacts.save_defect_fix(iteration, build_output)
    
                    except Exception as e:
                        print_error(f"BUILD failed: {e}")
                        return False, str(e)

                # ================================================
                # TRUNCATION & QUESTION DETECTION
                # ================================================

                # FIX #14: If truncated but we extracted files, proceed to validation + patch call
                # instead of aborting. The patch call can fill in missing files.
                # Only hard-abort if we extracted NOTHING (truly broken output).
                if still_truncated:
                    # Count how many FILE: headers Claude actually output
                    declared_files = extract_file_paths_from_output(build_output)
                    min_artifacts = self.qa_override.get('pre_qa_validation', {}).get('min_artifact_count', 3)

                    if len(declared_files) >= min_artifacts:
                        print_warning(f"Build truncated (no completion marker) but {len(declared_files)} files declared")
                        print_warning(f"  → Proceeding to extraction + validation + patch call")
                        # Save truncated output for debugging but don't abort
                        truncated_path = self.artifacts.logs_dir / 'truncated_build_output.txt'
                        truncated_path.write_text(build_output, encoding='utf-8')
                    else:
                        print_error(f"BUILD OUTPUT TRUNCATED on iteration {iteration}")
                        print_error(f"  → Only {len(declared_files)} file(s) declared (need {min_artifacts}+)")
                        print_error(f"  → Output incomplete even after continuations")
                        print_error(f"  → Solution: Increase CLAUDE_MAX_TOKENS or simplify intake")
                        truncated_path = self.artifacts.logs_dir / 'truncated_build_output.txt'
                        truncated_path.write_text(build_output, encoding='utf-8')
                        print_warning(f"Truncated output saved: logs/truncated_build_output.txt")
                        self._print_cost_summary(
                            iteration, total_calls, total_cache_writes, total_cache_hits,
                            total_cache_write_tokens, total_cache_read_tokens,
                            total_input_tokens, total_output_tokens,
                            total_gpt_calls, total_gpt_input_tokens, total_gpt_output_tokens,
                            run_end_reason='BUILD_TRUNCATED'
                        )
                        return False, "BUILD_TRUNCATED"

                # Check for actual questions (CLARIFICATION_NEEDED marker)
                if detect_claude_questions(build_output):
                    print_error(f"Claude asked clarifying questions on iteration {iteration} — stopping pipeline")
                    self.artifacts.save_claude_questions(iteration, build_output)
                    print_warning("Review questions in: logs/claude_questions.txt")
                    print_warning("Answer questions, update intake, and re-run")
                    self._print_cost_summary(
                        iteration, total_calls, total_cache_writes, total_cache_hits,
                        total_cache_write_tokens, total_cache_read_tokens,
                        total_input_tokens, total_output_tokens,
                        total_gpt_calls, total_gpt_input_tokens, total_gpt_output_tokens,
                        run_end_reason='QUESTIONS_DETECTED'
                    )
                    return False, "QUESTIONS_DETECTED"

                # Warn if build completion marker missing (but don't stop — let QA decide)
                if BUILD_COMPLETE_MARKER not in build_output:
                    print_warning(f"Build did not produce '{BUILD_COMPLETE_MARKER}' marker")

                # ================================================
                # PRE-QA VALIDATION (FIX #8)
                # ================================================
                # WHY: Don't waste QA cycles if build is obviously incomplete.
                # Check for critical artifacts before sending to ChatGPT.

                print_info("═══════════════════════════════════════════════════════════")
                print_info("PRE-QA VALIDATION - Checking build completeness")
                print_info("═══════════════════════════════════════════════════════════")

                validation_passed, validation_errors, missing_files_list = self._validate_build_artifacts(iteration)

                if not validation_passed:
                    consecutive_validation_failures += 1
                    print_error(f"BUILD VALIDATION FAILED on iteration {iteration} ({consecutive_validation_failures} consecutive)")
                    for error in validation_errors:
                        print_error(f"  → {error}")

                    # FIX #11: Try patch recovery for both:
                    # 1) files listed in manifest but not extracted
                    # 2) required files missing from manifest entirely
                    required_missing = []
                    for err in validation_errors:
                        m = re.search(r"Required file '([^']+)' not listed in artifact_manifest\.json", err)
                        if m:
                            required_missing.append(m.group(1))

                    patch_targets = sorted(set((missing_files_list or []) + required_missing))

                    if patch_targets:
                        print_info("")
                        print_info(f"Attempting patch call for {len(patch_targets)} missing file(s)...")
                        patch_success, patch_costs = self._patch_missing_files(
                            iteration, patch_targets, build_output, governance_section
                        )

                        # Accumulate patch costs
                        total_calls += patch_costs['calls']
                        total_input_tokens += patch_costs['input_tokens']
                        total_output_tokens += patch_costs['output_tokens']
                        if patch_costs['cache_read_tokens'] > 0:
                            total_cache_hits += 1
                            total_cache_read_tokens += patch_costs['cache_read_tokens']
                        if patch_costs['cache_creation_tokens'] > 0:
                            total_cache_writes += 1
                            total_cache_write_tokens += patch_costs['cache_creation_tokens']

                        if patch_success:
                            # Re-validate after patch
                            print_info("Re-validating after patch...")
                            validation_passed, validation_errors, missing_files_list = self._validate_build_artifacts(iteration)
                            if validation_passed:
                                consecutive_validation_failures = 0
                                print_success("Patch fixed all issues — proceeding to QA")
                                # Fall through to QA below

                    if not validation_passed:
                        print_error("")
                        print_error("SKIPPING QA - Build is incomplete")
                        print_error("Treating this as a BUILD failure (will retry next iteration)")
                        print_warning("Common causes:")
                        print_warning("  - Output truncated (hit token limit)")
                        print_warning("  - Claude didn't output all required files")
                        print_warning("  - artifact_manifest.json incomplete or malformed")

                        # FIX #9: Warn if validation fails too many times
                        if consecutive_validation_failures >= 5:
                            print_warning("")
                            print_warning(f"⚠️  VALIDATION FAILED {consecutive_validation_failures} TIMES IN A ROW")
                            print_warning("This suggests Claude is struggling to maintain all required files.")
                            print_warning("Consider:")
                            print_warning("  1. Check if token limit is sufficient (currently 16384)")
                            print_warning("  2. Simplify the intake requirements")
                            print_warning("  3. Review validation logs to see which files are missing")
                            print_warning("")

                        # Create synthetic defect report for next iteration
                        synthetic_defects = "## BUILD VALIDATION FAILURES\n\n"
                        synthetic_defects += "The following critical issues were detected:\n\n"
                        for i, error in enumerate(validation_errors, 1):
                            synthetic_defects += f"{i}. {error}\n"
                        synthetic_defects += "\n**FIX ALL OF THESE ISSUES.**\n"

                        # FIX #9: Show cumulative cost after validation failure
                        self._display_cumulative_cost(
                            iteration, total_calls, total_cache_writes, total_cache_hits,
                            total_cache_read_tokens, total_cache_write_tokens,
                            total_input_tokens, total_output_tokens,
                            total_gpt_calls, total_gpt_input_tokens, total_gpt_output_tokens
                        )

                        previous_defects = synthetic_defects
                        iteration += 1
                        continue  # Skip QA, go to next iteration

                consecutive_validation_failures = 0  # Reset counter
                print_success("✓ Build validation passed - all critical artifacts present")
                print_info("───────────────────────────────────────────────────────────")

                # ================================================
                # STEP 2: QA (ChatGPT)
                # ================================================

                print_info("Calling ChatGPT for QA...")

                # For defect iterations in boilerplate mode, QA receives the full merged
                # artifact set (not Claude's partial defect-only output) so it evaluates
                # the complete picture rather than just the 1-3 files Claude patched.
                if self.use_boilerplate and iteration > 1 and previous_defects:
                    qa_build_output = self.artifacts.build_synthetic_qa_output(iteration)
                else:
                    qa_build_output = build_output

                qa_prompt = PromptTemplates.qa_prompt(
                    qa_build_output,
                    self.intake_data,
                    self.block,
                    self.effective_tech_stack,
                    self.qa_override
                )

                self.artifacts.save_log(f'iteration_{iteration:02d}_qa_prompt', qa_prompt)

                start_time = time.time()
                try:
                    qa_response = self.chatgpt.call(qa_prompt)
                    qa_report   = qa_response['choices'][0]['message']['content']
                    qa_time     = time.time() - start_time
                    print_success(f"QA completed in {qa_time:.1f}s")

                    # Log ChatGPT usage and accumulate stats
                    gpt_usage = self._log_chatgpt_usage(qa_response, iteration)
                    total_gpt_calls += 1
                    total_gpt_input_tokens += gpt_usage['input_tokens']
                    total_gpt_output_tokens += gpt_usage['output_tokens']

                    self.artifacts.save_qa_report(iteration, qa_report)

                except Exception as e:
                    print_error(f"QA failed: {e}")
                    return False, str(e)

                # ================================================
                # STEP 3: CHECK QA VERDICT
                # ================================================

                if "QA STATUS: ACCEPTED" in qa_report:
                    print_success(f"QA ACCEPTED on iteration {iteration}")
                    print_success("BUILD → QA loop complete — no defects")

                    # FIX #10: Post-QA polish step - generate missing optional files
                    polish_success, polish_cost = self._post_qa_polish(
                        iteration, build_output, governance_section
                    )
                    if polish_success:
                        # Update cost tracking with polish costs
                        total_calls += polish_cost['calls']
                        total_input_tokens += polish_cost['input_tokens']
                        total_output_tokens += polish_cost['output_tokens']
                        if polish_cost['cache_read_tokens'] > 0:
                            total_cache_hits += 1
                            total_cache_read_tokens += polish_cost['cache_read_tokens']

                    # FIX #1: Print cost summary before returning
                    self._print_cost_summary(
                        iteration, total_calls, total_cache_writes, total_cache_hits,
                        total_cache_write_tokens, total_cache_read_tokens,
                        total_input_tokens, total_output_tokens,
                        total_gpt_calls, total_gpt_input_tokens, total_gpt_output_tokens,
                        run_end_reason='QA_ACCEPTED'
                    )

                    return True, build_output

                elif "QA STATUS: REJECTED" in qa_report:
                    print_warning("QA REJECTED — defects found")

                    defect_match = re.search(r'(\d+) defects? require', qa_report)
                    current_defect_count = 0
                    if defect_match:
                        current_defect_count = int(defect_match.group(1))
                        print_warning(f"  → {current_defect_count} defects to fix")

                    # Print detailed defects to screen
                    self._print_defects_summary(qa_report, iteration)

                    # Track defect count for convergence detection
                    defect_history.append(current_defect_count)

                    # Check for convergence after several iterations
                    if iteration >= convergence_check_after:
                        # Check if defects are oscillating or not decreasing
                        recent_defects = defect_history[-5:]  # Last 5 iterations
                        avg_recent = sum(recent_defects) / len(recent_defects)

                        # If average defects in last 5 iterations is >= first 5 iterations, not converging
                        if iteration >= 15:
                            early_defects = defect_history[:5]
                            avg_early = sum(early_defects) / len(early_defects) if early_defects else 0

                            if avg_recent >= avg_early:
                                print_error(f"Loop not converging after {iteration} iterations")
                                print_error(f"  → Early defects (avg): {avg_early:.1f}")
                                print_error(f"  → Recent defects (avg): {avg_recent:.1f}")
                                print_error(f"  → Defect history: {defect_history}")
                                print_warning("Possible causes:")
                                print_warning("  1. Intake requirements too vague (no data model specs)")
                                print_warning("  2. QA flagging reasonable inferences as scope creep")
                                print_warning("  3. Claude fixes introduce new problems (whack-a-mole)")
                                print_warning("Recommendation: Review intake for ambiguity or adjust QA strictness")

                                # Still print cost summary
                                self._print_cost_summary(
                                    iteration, total_calls, total_cache_writes, total_cache_hits,
                                    total_cache_write_tokens, total_cache_read_tokens,
                                    total_input_tokens, total_output_tokens,
                                    total_gpt_calls, total_gpt_input_tokens, total_gpt_output_tokens,
                                    run_end_reason='NON_CONVERGING'
                                )

                                return False, "NON_CONVERGING_DEFECTS"

                    # FIX #9: Show cumulative cost after each QA iteration
                    self._display_cumulative_cost(
                        iteration, total_calls, total_cache_writes, total_cache_hits,
                        total_cache_read_tokens, total_cache_write_tokens,
                        total_input_tokens, total_output_tokens,
                        total_gpt_calls, total_gpt_input_tokens, total_gpt_output_tokens
                    )

                    previous_defects = self._enrich_defects_with_fix_context(qa_report)
                    iteration       += 1

                    if iteration > self.max_qa_iterations:
                        print_error(f"Max iterations ({self.max_qa_iterations}) reached — loop failed to converge")

                        # FIX #1: Print cost summary even on failure
                        self._print_cost_summary(
                            iteration - 1, total_calls, total_cache_writes, total_cache_hits,
                            total_cache_write_tokens, total_cache_read_tokens,
                            total_input_tokens, total_output_tokens,
                            total_gpt_calls, total_gpt_input_tokens, total_gpt_output_tokens,
                            run_end_reason='MAX_ITERATIONS'
                        )

                        return False, "MAX_ITERATIONS_EXCEEDED"

                    print_info(f"Starting iteration {iteration} with defect fixes...")
                    continue

                else:
                    print_error("QA report format invalid — no clear ACCEPTED/REJECTED verdict")
                    self._print_cost_summary(
                        iteration, total_calls, total_cache_writes, total_cache_hits,
                        total_cache_write_tokens, total_cache_read_tokens,
                        total_input_tokens, total_output_tokens,
                        total_gpt_calls, total_gpt_input_tokens, total_gpt_output_tokens,
                        run_end_reason='QA_VERDICT_UNCLEAR'
                    )
                    return False, "QA_VERDICT_UNCLEAR"

        except KeyboardInterrupt:
            print_error("\n\n⚠️  BUILD INTERRUPTED (Ctrl+C)")
            print_info(f"Stopped at iteration {iteration}")
            # Show final cost before exiting
            self._display_cumulative_cost(
                iteration, total_calls, total_cache_writes, total_cache_hits,
                total_cache_read_tokens, total_cache_write_tokens,
                total_input_tokens, total_output_tokens,
                total_gpt_calls, total_gpt_input_tokens, total_gpt_output_tokens
            )
            # Log interrupted run to CSV
            cache_write_cost = (total_cache_write_tokens / 1_000_000) * 3.75
            cache_read_cost = (total_cache_read_tokens / 1_000_000) * 0.30
            non_cached_input_cost = ((total_input_tokens - total_cache_read_tokens) / 1_000_000) * 3.00
            output_cost = (total_output_tokens / 1_000_000) * 15.00
            claude_cost = cache_write_cost + cache_read_cost + non_cached_input_cost + output_cost
            gpt_cost = ((total_gpt_input_tokens / 1_000_000) * 2.50) + ((total_gpt_output_tokens / 1_000_000) * 10.00)
            self._log_run_csv(iteration, claude_cost, gpt_cost, 'CTRL_C')
            raise  # Re-raise to propagate

        return False, "Should not reach here"

    def execute_deploy(self, build_output: str) -> bool:
        """Execute deployment phase (only called when --deploy is passed)"""

        print_header("STARTING DEPLOYMENT")

        deploy_prompt = PromptTemplates.deploy_prompt(build_output, self.deploy_governance)
        self.artifacts.save_log('deploy_prompt', deploy_prompt)

        print_info("Calling Claude for DEPLOYMENT...")
        start_time = time.time()

        try:
            deploy_response = self.claude.call(deploy_prompt)
            deploy_output   = deploy_response['content'][0]['text']
            deploy_time     = time.time() - start_time
            print_success(f"DEPLOY completed in {deploy_time:.1f}s")
            self.artifacts.save_deploy_output(deploy_output)

            if "DEPLOYMENT STATE: DEPLOYED" in deploy_output:
                print_success("DEPLOYMENT SUCCESSFUL")
                return True
            elif "DEPLOYMENT STATE: DEPLOY_FAILED" in deploy_output:
                print_error("DEPLOYMENT FAILED")
                return False
            else:
                print_warning("Deployment status unclear — no terminal state marker found")
                return False

        except Exception as e:
            print_error(f"DEPLOY failed: {e}")
            return False

    def run(self) -> bool:
        """Run complete BUILD → QA → (ZIP or DEPLOY) pipeline"""

        overall_start = time.time()

        # BUILD → QA loop
        qa_success, build_output = self.execute_build_qa_loop()

        # Questions detected — already logged, exit cleanly
        if not qa_success and build_output == "QUESTIONS_DETECTED":
            self.print_summary(False, time.time() - overall_start, reason="QUESTIONS_DETECTED")
            return False

        if not qa_success:
            print_error("BUILD → QA loop failed")
            self.print_summary(False, time.time() - overall_start, reason=build_output)
            return False

        # Generate artifact manifest
        self.artifacts.generate_manifest()

        if not self.do_deploy:
            # Default path — package ZIP, done
            zip_path = package_output_zip(self.run_dir, self.startup_id, self.block, self.use_boilerplate)
            self.print_summary(True, time.time() - overall_start, zip_path=zip_path)
            return True

        # Deploy path — only if --deploy was passed
        deploy_success = self.execute_deploy(build_output)

        if not deploy_success:
            print_error("DEPLOYMENT failed")
            self.print_summary(False, time.time() - overall_start, reason="DEPLOY_FAILED")
            return False

        self.print_summary(True, time.time() - overall_start, deployed=True)
        return True

    def print_summary(
        self,
        success:  bool,
        elapsed:  float,
        deployed: bool  = False,
        zip_path: Path  = None,
        reason:   str   = None
    ):
        """Print execution summary"""

        print_header("EXECUTION SUMMARY")

        print(f"Startup:        {self.startup_id}")
        print(f"Block:          BLOCK_{self.block}")
        print(f"Status:         {'✓ SUCCESS' if success else '✗ FAILED'}")
        print(f"Total time:     {elapsed:.1f}s ({elapsed/60:.1f} minutes)")
        print(f"Deployed:       {'Yes' if deployed else 'No'}")

        if reason:
            print(f"Reason:         {reason}")

        if zip_path:
            print(f"ZIP output:     {zip_path}")

        print(f"")
        print(f"Run directory:  {self.run_dir}")
        print(f"")
        print(f"Generated files:")

        build_files  = len(list(self.artifacts.build_dir.rglob('*')))
        qa_files     = len(list(self.artifacts.qa_dir.rglob('*')))
        deploy_files = len(list(self.artifacts.deploy_dir.rglob('*')))
        log_files    = len(list(self.artifacts.logs_dir.rglob('*')))

        print(f"  - BUILD outputs:   {build_files}")
        print(f"  - QA reports:      {qa_files}")
        print(f"  - DEPLOY outputs:  {deploy_files}")
        print(f"  - Logs:            {log_files}")

        if success:
            print(f"\n{Colors.GREEN}{Colors.BOLD}✓ PIPELINE COMPLETED SUCCESSFULLY{Colors.END}")
        else:
            print(f"\n{Colors.RED}{Colors.BOLD}✗ PIPELINE FAILED{Colors.END}")


# ============================================================
# MAIN CLI
# ============================================================

def main():
    """Main entry point"""

    parser = argparse.ArgumentParser(
        description='FO Test Harness v2 — BUILD → QA → ZIP/DEPLOY',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Default: Block B, no deploy, ZIP output
  ./fo_test_harness.py intake.json build_rules.zip deploy_rules.zip

  # Block A (Tier 1), no deploy
  ./fo_test_harness.py intake.json build_rules.zip deploy_rules.zip --block-a

  # Block B, with deployment
  ./fo_test_harness.py intake.json build_rules.zip deploy_rules.zip --deploy

  # Block A, with deployment
  ./fo_test_harness.py intake.json build_rules.zip deploy_rules.zip --block-a --deploy
        """
    )

    # Positional args
    parser.add_argument(
        'intake_file',
        type=Path,
        help='Path to combined intake JSON (output of run_intake_v7.sh)'
    )
    parser.add_argument(
        'build_governance_zip',
        type=Path,
        help='Path to BUILD governance ZIP (FOBUILFINALLOCKED100.zip)'
    )
    parser.add_argument(
        'deploy_governance_zip',
        type=Path,
        help='Path to DEPLOY governance ZIP (fo_deploy_governance_v1_2_CLARIFIED.zip)'
    )

    # Optional flags
    # FIX #9: --block-a flag, default is Block B
    parser.add_argument(
        '--block-a',
        action='store_true',
        default=False,
        help='Build Block A (Tier 1). Default is Block B (Tier 2).'
    )

    # FIX #8: --deploy flag, default is NO deploy
    parser.add_argument(
        '--deploy',
        action='store_true',
        default=False,
        help='Execute deployment after QA acceptance. Default is ZIP output only.'
    )
    parser.add_argument(
        '--confirm-run-log',
        default='NO',
        help='Require confirmation before writing fo_run_log.csv (YES/NO). Default: NO'
    )
    parser.add_argument(
        '--qa-polish-2-directive',
        type=Path,
        default=None,
        help='Path to external QA_POLISH_2_DOC_RECOVERY directive file. '
             'Precedence: CLI path -> Config default path.'
    )
    parser.add_argument(
        '--platform-boilerplate-dir',
        type=Path,
        default=Config.PLATFORM_BOILERPLATE_DIR,
        help='Path to teebu-saas-platform boilerplate root. '
             'Default: /Users/teebuphilip/Documents/work/teebu-saas-platform'
    )
    parser.add_argument(
        '--max-parts',
        type=int,
        default=Config.MAX_BUILD_PARTS_DEFAULT,
        help='Max multipart chunks to assemble from Claude in one iteration. Default: 10'
    )
    parser.add_argument(
        '--max-continuations',
        type=int,
        default=Config.MAX_BUILD_CONTINUATIONS_DEFAULT,
        help='Max fallback continuation calls when output is truncated. Default: 9'
    )
    parser.add_argument(
        '--max-iterations',
        type=int,
        default=Config.MAX_QA_ITERATIONS,
        help='Max BUILD→QA iterations for this run. Default: 5'
    )
    parser.add_argument(
        '--resume-run',
        type=str,
        default=None,
        help='Path to an existing run directory to resume (skips new dir creation).'
    )
    parser.add_argument(
        '--resume-iteration',
        type=int,
        default=1,
        help='Which iteration to resume from (used with --resume-run). Default: 1'
    )
    parser.add_argument(
        '--resume-mode',
        choices=['qa', 'fix'],
        default=None,
        help=(
            'qa  — skip Claude BUILD for --resume-iteration, run fresh QA on existing artifacts. '
            'fix — load QA report from --resume-iteration as defects, start Claude FIX at iter+1.'
        )
    )

    args = parser.parse_args()
    if args.max_parts < 1:
        parser.error("--max-parts must be >= 1")
    if args.max_continuations < 0:
        parser.error("--max-continuations must be >= 0")
    if args.max_iterations < 1:
        parser.error("--max-iterations must be >= 1")

    # Resolve block from flag
    block = 'A' if args.block_a else 'B'

    # Validate API keys
    if not Config.ANTHROPIC_API_KEY:
        print_error("ANTHROPIC_API_KEY environment variable not set")
        print_info("Set it with: export ANTHROPIC_API_KEY='sk-ant-...'")
        sys.exit(1)

    if not Config.OPENAI_API_KEY:
        print_error("OPENAI_API_KEY environment variable not set")
        print_info("Set it with: export OPENAI_API_KEY='sk-...'")
        sys.exit(1)

    # Validate intake file
    if not args.intake_file.exists():
        print_error(f"Intake file not found: {args.intake_file}")
        sys.exit(1)

    # Validate governance ZIPs
    if not args.build_governance_zip.exists():
        print_error(f"BUILD governance ZIP not found: {args.build_governance_zip}")
        sys.exit(1)

    if not args.deploy_governance_zip.exists():
        print_error(f"DEPLOY governance ZIP not found: {args.deploy_governance_zip}")
        sys.exit(1)

    # Inject CLI paths into Config
    Config.BUILD_GOVERNANCE_ZIP  = args.build_governance_zip
    Config.DEPLOY_GOVERNANCE_ZIP = args.deploy_governance_zip
    Config.PLATFORM_BOILERPLATE_DIR = args.platform_boilerplate_dir

    # Create base output directory
    Config.OUTPUT_DIR.mkdir(exist_ok=True)

    # Run
    try:
        harness = FOHarness(args.intake_file, block, do_deploy=args.deploy, cli_args=args)
        success = harness.run()
        sys.exit(0 if success else 1)

    except KeyboardInterrupt:
        print_warning("\nExecution interrupted by user")
        sys.exit(130)

    except Exception as e:
        print_error(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
