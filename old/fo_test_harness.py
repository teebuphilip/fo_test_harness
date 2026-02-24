#!/usr/bin/env python3
"""
FO Test Harness - BUILD → QA → DEPLOY Orchestration
Orchestrates Claude (tech) and ChatGPT (QA) to build and deploy businesses
"""

import os
import sys
import json
import time
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import requests
import hashlib

# ============================================================
# CONFIGURATION
# ============================================================

class Config:
    """Configuration for test harness"""
    
    # API Keys (from environment)
    ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY')
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
    
    # API Endpoints
    ANTHROPIC_API = 'https://api.anthropic.com/v1/messages'
    OPENAI_API = 'https://api.openai.com/v1/chat/completions'
    
    # Models
    CLAUDE_MODEL = 'claude-sonnet-4-20250514'  # Tech/Builder
    GPT_MODEL = 'gpt-4o'  # QA/Validator
    
    # Token Limits
    CLAUDE_MAX_TOKENS = 200000  # Prevent truncation
    GPT_MAX_TOKENS = 16000
    
    # Governance Files (update these paths)
    BUILD_GOVERNANCE_ZIP = os.getenv('BUILD_GOVERNANCE_ZIP', '/path/to/FOBUILFINALLOCKED100.zip')
    DEPLOY_GOVERNANCE_ZIP = os.getenv('DEPLOY_GOVERNANCE_ZIP', '/path/to/fo_deploy_governance_v1_2_CLARIFIED.zip')
    
    # Iteration Limits
    MAX_QA_ITERATIONS = 5  # Max BUILD → QA cycles
    
    # Output Directory
    OUTPUT_DIR = Path('./fo_harness_runs')


# ============================================================
# COLOR OUTPUT
# ============================================================

class Colors:
    """ANSI color codes for terminal output"""
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    END = '\033[0m'


def print_header(text: str):
    """Print styled header"""
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*70}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{text}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'='*70}{Colors.END}\n")


def print_success(text: str):
    """Print success message"""
    print(f"{Colors.GREEN}✓ {text}{Colors.END}")


def print_error(text: str):
    """Print error message"""
    print(f"{Colors.RED}✗ {text}{Colors.END}")


def print_warning(text: str):
    """Print warning message"""
    print(f"{Colors.YELLOW}⚠ {text}{Colors.END}")


def print_info(text: str):
    """Print info message"""
    print(f"{Colors.CYAN}→ {text}{Colors.END}")


# ============================================================
# API CLIENTS
# ============================================================

class ClaudeClient:
    """Client for Claude API (Tech/Builder)"""
    
    def __init__(self):
        if not Config.ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY environment variable not set")
    
    def call(self, prompt: str, max_tokens: int = None) -> Dict:
        """Call Claude API"""
        if max_tokens is None:
            max_tokens = Config.CLAUDE_MAX_TOKENS
        
        payload = {
            "model": Config.CLAUDE_MODEL,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "user", "content": prompt}
            ]
        }
        
        headers = {
            "content-type": "application/json",
            "x-api-key": Config.ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01"
        }
        
        response = requests.post(Config.ANTHROPIC_API, json=payload, headers=headers)
        response.raise_for_status()
        
        return response.json()


class ChatGPTClient:
    """Client for ChatGPT API (QA/Validator)"""
    
    def __init__(self):
        if not Config.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY environment variable not set")
    
    def call(self, prompt: str, max_tokens: int = None) -> Dict:
        """Call ChatGPT API"""
        if max_tokens is None:
            max_tokens = Config.GPT_MAX_TOKENS
        
        payload = {
            "model": Config.GPT_MODEL,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "user", "content": prompt}
            ]
        }
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {Config.OPENAI_API_KEY}"
        }
        
        response = requests.post(Config.OPENAI_API, json=payload, headers=headers)
        response.raise_for_status()
        
        return response.json()


# ============================================================
# FILE MANAGEMENT
# ============================================================

class ArtifactManager:
    """Manages saving artifacts, QA reports, and build outputs"""
    
    def __init__(self, run_dir: Path):
        self.run_dir = run_dir
        self.iteration = 0
        
        # Create subdirectories
        self.build_dir = run_dir / 'build'
        self.qa_dir = run_dir / 'qa'
        self.deploy_dir = run_dir / 'deploy'
        self.logs_dir = run_dir / 'logs'
        
        for d in [self.build_dir, self.qa_dir, self.deploy_dir, self.logs_dir]:
            d.mkdir(parents=True, exist_ok=True)
    
    def save_build_output(self, iteration: int, output: str):
        """Save BUILD output from Claude"""
        path = self.build_dir / f'iteration_{iteration:02d}_build.txt'
        path.write_text(output)
        print_success(f"Saved BUILD output: {path}")
        return path
    
    def save_qa_report(self, iteration: int, report: str):
        """Save QA report from ChatGPT"""
        path = self.qa_dir / f'iteration_{iteration:02d}_qa_report.txt'
        path.write_text(report)
        print_success(f"Saved QA report: {path}")
        return path
    
    def save_defect_fix(self, iteration: int, fix: str):
        """Save defect fix from Claude"""
        path = self.build_dir / f'iteration_{iteration:02d}_fix.txt'
        path.write_text(fix)
        print_success(f"Saved defect fix: {path}")
        return path
    
    def save_deploy_output(self, output: str):
        """Save DEPLOY output"""
        path = self.deploy_dir / 'deploy_output.txt'
        path.write_text(output)
        print_success(f"Saved DEPLOY output: {path}")
        return path
    
    def save_artifact(self, name: str, content: str, artifact_type: str = 'code'):
        """Save build artifact (code, docs, etc)"""
        subdir = self.build_dir / artifact_type
        subdir.mkdir(exist_ok=True)
        
        path = subdir / name
        path.write_text(content)
        return path
    
    def save_log(self, log_name: str, content: str):
        """Save execution log"""
        path = self.logs_dir / f'{log_name}.log'
        
        # Append with timestamp
        timestamp = datetime.now().isoformat()
        with open(path, 'a') as f:
            f.write(f"\n[{timestamp}]\n{content}\n")
        
        return path
    
    def generate_manifest(self):
        """Generate artifact manifest with checksums"""
        manifest = {
            "generated_at": datetime.now().isoformat(),
            "artifacts": []
        }
        
        for artifact_file in self.build_dir.rglob('*'):
            if artifact_file.is_file():
                with open(artifact_file, 'rb') as f:
                    content = f.read()
                    checksum = hashlib.sha256(content).hexdigest()
                
                manifest["artifacts"].append({
                    "path": str(artifact_file.relative_to(self.run_dir)),
                    "sha256": checksum,
                    "size": len(content)
                })
        
        manifest_path = self.run_dir / 'artifact_manifest.json'
        manifest_path.write_text(json.dumps(manifest, indent=2))
        print_success(f"Generated artifact manifest: {manifest_path}")
        
        return manifest_path


# ============================================================
# PROMPT TEMPLATES
# ============================================================

class PromptTemplates:
    """Templates for BUILD, QA, and DEPLOY prompts"""
    
    @staticmethod
    def build_prompt(block: str, intake_data: dict, iteration: int = 1, 
                     previous_defects: Optional[str] = None) -> str:
        """Generate BUILD prompt for Claude"""
        
        base_prompt = f"""You are the FO BUILD EXECUTOR running in FOUNDER_FAST_PATH mode.

**YOUR ROLE:**
Execute the build for {block} using the locked FO Build Governance.

**ITERATION:** {iteration}

**INPUTS PROVIDED:**
1. Intake output (MCv6-SCHEMA v21.4) - below
2. FO Build Governance (22 files) - in governance ZIP

**YOUR TASK:**
1. Read BUILD governance files
2. Extract {block} intake data
3. Execute BUILD according to fo_build_state_machine.json
4. Follow all enforcement rules (tier, scope, iteration, QA routing)
5. Produce COMPLETED_CLOSED state with all required artifacts

**CRITICAL RULES FROM GOVERNANCE:**
- No inference - follow governance literally
- Max 5 iterations per task (you are on iteration {iteration})
- No scope changes (ABORT_AND_DISCARD if scope change detected)
- Produce all required artifacts with checksums
- Generate artifact_manifest.json with SHA256 checksums
- Generate build_state.json with state = COMPLETED_CLOSED
- Generate execution_declaration.json with all commands executed

**ARTIFACT REQUIREMENTS:**
- All code files in separate artifacts (no truncation)
- README.md with setup instructions
- package.json with dependencies
- All configuration files
- Test files (if applicable)

**OUTPUT FORMAT:**
1. Provide complete implementation (no placeholders, no "...continued")
2. Use artifacts/code blocks for all files
3. Include artifact_manifest.json at the end
4. Include build_state.json at the end
5. End with: "BUILD STATE: COMPLETED_CLOSED"

"""
        
        if previous_defects:
            base_prompt += f"""
**PREVIOUS QA ITERATION:**
The previous build had defects. ChatGPT reported:

{previous_defects}

**YOUR TASK NOW:**
Fix ALL reported defects while maintaining scope.
Do NOT introduce new functionality (scope change).
Follow QA feedback precisely.

"""
        
        base_prompt += f"""
**INTAKE DATA ({block}):**
{json.dumps(intake_data.get(block.lower(), {}), indent=2)}

**BEGIN BUILD EXECUTION NOW.**
"""
        
        return base_prompt
    
    @staticmethod
    def qa_prompt(build_output: str, intake_data: dict, block: str) -> str:
        """Generate QA prompt for ChatGPT"""
        
        return f"""You are the FO QA OPERATOR (ChatGPT).

**YOUR ROLE:**
Validate the build output from Claude against the intake requirements and FO Build Governance.

**INTAKE REQUIREMENTS ({block}):**
{json.dumps(intake_data.get(block.lower(), {}), indent=2)}

**BUILD OUTPUT FROM CLAUDE:**
{build_output}

**YOUR TASK:**
1. Verify all tasks from intake were completed
2. Verify all deliverables are present
3. Check for scope compliance (no extra features)
4. Check for implementation bugs
5. Validate artifact_manifest.json exists with checksums
6. Validate build_state.json shows COMPLETED_CLOSED

**DEFECT CLASSIFICATION (from fo_build_qa_defect_routing_rules.json):**
- IMPLEMENTATION_BUG: Code doesn't work as specified
- SPEC_COMPLIANCE_ISSUE: Doesn't match intake requirements
- SCOPE_CHANGE_REQUEST: Extra features not in intake (CRITICAL)

**OUTPUT FORMAT:**
Provide a structured QA report with:

## QA REPORT

### SUMMARY
- Total defects found: [number]
- IMPLEMENTATION_BUG: [count]
- SPEC_COMPLIANCE_ISSUE: [count]
- SCOPE_CHANGE_REQUEST: [count]

### DEFECTS
[List each defect with:]
- DEFECT-[ID]: [classification]
  - Location: [file/line]
  - Problem: [what's wrong]
  - Expected: [what should be]
  - Severity: HIGH | MEDIUM | LOW

### VERDICT
- ACCEPTED (no defects) OR
- REJECTED (defects found - requires fix)

**If ACCEPTED:**
End with: "QA STATUS: ACCEPTED - Ready for deployment"

**If REJECTED:**
End with: "QA STATUS: REJECTED - [X] defects require fixing"

**BEGIN QA ANALYSIS NOW.**
"""
    
    @staticmethod
    def deploy_prompt(build_output: str, environment: str = 'POC') -> str:
        """Generate DEPLOY prompt for Claude"""
        
        return f"""You are the FO DEPLOY EXECUTOR.

**YOUR ROLE:**
Execute deployment using the locked FO Deploy Governance.

**INPUTS PROVIDED:**
1. Build artifacts from BUILD phase (below)
2. FO Deploy Governance (5 files) - in governance ZIP
3. Target environment: {environment}

**YOUR TASK:**
1. Read DEPLOY governance files
2. Validate build_state = COMPLETED_CLOSED
3. Validate all artifacts exist with correct checksums
4. Execute deployment to {environment} environment
5. Produce terminal state: DEPLOYED or DEPLOY_FAILED

**CRITICAL RULES FROM GOVERNANCE:**
- Follow fo_deploy_artifact_eligibility_rules.json (validate checksums)
- Follow fo_deploy_environment_definitions.json ({environment} environment)
- Follow fo_deploy_completion_rules.json (validation procedures)
- Check forbidden capabilities for {environment}
- Produce deployment_state.json

**BUILD OUTPUT:**
{build_output}

**OUTPUT FORMAT:**
1. Artifact validation results
2. Deployment commands executed
3. Environment validation
4. Final deployment state
5. End with: "DEPLOYMENT STATE: DEPLOYED" or "DEPLOYMENT STATE: DEPLOY_FAILED"

**BEGIN DEPLOYMENT NOW.**
"""


# ============================================================
# ORCHESTRATOR
# ============================================================

class FOHarness:
    """Main orchestrator for BUILD → QA → DEPLOY"""
    
    def __init__(self, intake_file: Path, block: str):
        self.intake_file = intake_file
        self.block = block.upper()
        
        # Load intake data
        with open(intake_file) as f:
            content = f.read()
            # Handle both pure JSON and wrapped formats
            if content.strip().startswith('{'):
                self.intake_data = json.loads(content)
            else:
                # Extract JSON from wrapped format
                import re
                json_match = re.search(r'\{.*\}', content, re.DOTALL)
                if json_match:
                    self.intake_data = json.loads(json_match.group(0))
                else:
                    raise ValueError("Could not parse intake JSON")
        
        # Extract startup_idea_id
        self.startup_id = self.intake_data.get('startup_idea_id', 'unknown')
        
        # Create run directory
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.run_dir = Config.OUTPUT_DIR / f'{self.startup_id}_{self.block}_{timestamp}'
        self.run_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize components
        self.claude = ClaudeClient()
        self.chatgpt = ChatGPTClient()
        self.artifacts = ArtifactManager(self.run_dir)
        
        print_header(f"FO HARNESS INITIALIZED")
        print_info(f"Startup: {self.startup_id}")
        print_info(f"Block: {self.block}")
        print_info(f"Run directory: {self.run_dir}")
    
    def execute_build_qa_loop(self) -> Tuple[bool, str]:
        """Execute BUILD → QA loop until no defects"""
        
        print_header(f"STARTING BUILD → QA LOOP ({self.block})")
        
        iteration = 1
        previous_defects = None
        build_output = None
        
        while iteration <= Config.MAX_QA_ITERATIONS:
            print_header(f"ITERATION {iteration}/{Config.MAX_QA_ITERATIONS}")
            
            # =====================================
            # STEP 1: BUILD (Claude)
            # =====================================
            
            print_info("Calling Claude for BUILD...")
            
            build_prompt = PromptTemplates.build_prompt(
                self.block, 
                self.intake_data, 
                iteration,
                previous_defects
            )
            
            # Save prompt
            self.artifacts.save_log(f'iteration_{iteration:02d}_build_prompt', build_prompt)
            
            # Call Claude
            start_time = time.time()
            try:
                build_response = self.claude.call(build_prompt)
                build_output = build_response['content'][0]['text']
                build_time = time.time() - start_time
                
                print_success(f"BUILD completed in {build_time:.1f}s")
                
                # Save output
                self.artifacts.save_build_output(iteration, build_output)
                
            except Exception as e:
                print_error(f"BUILD failed: {e}")
                return False, str(e)
            
            # Check if build completed
            if "BUILD STATE: COMPLETED_CLOSED" not in build_output:
                print_warning("Build did not reach COMPLETED_CLOSED state")
            
            # =====================================
            # STEP 2: QA (ChatGPT)
            # =====================================
            
            print_info("Calling ChatGPT for QA...")
            
            qa_prompt = PromptTemplates.qa_prompt(
                build_output,
                self.intake_data,
                self.block
            )
            
            # Save prompt
            self.artifacts.save_log(f'iteration_{iteration:02d}_qa_prompt', qa_prompt)
            
            # Call ChatGPT
            start_time = time.time()
            try:
                qa_response = self.chatgpt.call(qa_prompt)
                qa_report = qa_response['choices'][0]['message']['content']
                qa_time = time.time() - start_time
                
                print_success(f"QA completed in {qa_time:.1f}s")
                
                # Save report
                self.artifacts.save_qa_report(iteration, qa_report)
                
            except Exception as e:
                print_error(f"QA failed: {e}")
                return False, str(e)
            
            # =====================================
            # STEP 3: CHECK QA VERDICT
            # =====================================
            
            if "QA STATUS: ACCEPTED" in qa_report:
                print_success(f"QA ACCEPTED on iteration {iteration}")
                print_success("BUILD → QA loop complete - no defects")
                return True, build_output
            
            elif "QA STATUS: REJECTED" in qa_report:
                print_warning(f"QA REJECTED - defects found")
                
                # Extract defect count
                import re
                defect_match = re.search(r'(\d+) defects? require', qa_report)
                if defect_match:
                    defect_count = defect_match.group(1)
                    print_warning(f"  → {defect_count} defects to fix")
                
                # Prepare for next iteration
                previous_defects = qa_report
                iteration += 1
                
                if iteration > Config.MAX_QA_ITERATIONS:
                    print_error(f"Max iterations ({Config.MAX_QA_ITERATIONS}) reached")
                    print_error("BUILD → QA loop failed to converge")
                    return False, "Max QA iterations exceeded"
                
                print_info(f"Starting iteration {iteration} with defect fixes...")
                continue
            
            else:
                print_error("QA report format invalid - no clear verdict")
                return False, "QA verdict unclear"
        
        return False, "Should not reach here"
    
    def execute_deploy(self, build_output: str, environment: str = 'POC') -> bool:
        """Execute deployment"""
        
        print_header(f"STARTING DEPLOYMENT ({environment})")
        
        deploy_prompt = PromptTemplates.deploy_prompt(build_output, environment)
        
        # Save prompt
        self.artifacts.save_log('deploy_prompt', deploy_prompt)
        
        # Call Claude
        print_info("Calling Claude for DEPLOYMENT...")
        start_time = time.time()
        
        try:
            deploy_response = self.claude.call(deploy_prompt)
            deploy_output = deploy_response['content'][0]['text']
            deploy_time = time.time() - start_time
            
            print_success(f"DEPLOY completed in {deploy_time:.1f}s")
            
            # Save output
            self.artifacts.save_deploy_output(deploy_output)
            
            # Check deployment status
            if "DEPLOYMENT STATE: DEPLOYED" in deploy_output:
                print_success("DEPLOYMENT SUCCESSFUL")
                return True
            
            elif "DEPLOYMENT STATE: DEPLOY_FAILED" in deploy_output:
                print_error("DEPLOYMENT FAILED")
                return False
            
            else:
                print_warning("Deployment status unclear")
                return False
        
        except Exception as e:
            print_error(f"DEPLOY failed: {e}")
            return False
    
    def run(self, skip_deploy: bool = False) -> bool:
        """Run complete BUILD → QA → DEPLOY pipeline"""
        
        overall_start = time.time()
        
        # Execute BUILD → QA loop
        qa_success, build_output = self.execute_build_qa_loop()
        
        if not qa_success:
            print_error("BUILD → QA loop failed")
            self.print_summary(False, time.time() - overall_start)
            return False
        
        # Generate artifact manifest
        self.artifacts.generate_manifest()
        
        if skip_deploy:
            print_warning("Skipping DEPLOY (--skip-deploy flag)")
            self.print_summary(True, time.time() - overall_start, deployed=False)
            return True
        
        # Execute deployment
        deploy_success = self.execute_deploy(build_output)
        
        if not deploy_success:
            print_error("DEPLOYMENT failed")
            self.print_summary(False, time.time() - overall_start)
            return False
        
        # Success!
        self.print_summary(True, time.time() - overall_start, deployed=True)
        return True
    
    def print_summary(self, success: bool, elapsed: float, deployed: bool = False):
        """Print execution summary"""
        
        print_header("EXECUTION SUMMARY")
        
        print(f"Startup:        {self.startup_id}")
        print(f"Block:          {self.block}")
        print(f"Status:         {'✓ SUCCESS' if success else '✗ FAILED'}")
        print(f"Total time:     {elapsed:.1f}s ({elapsed/60:.1f} minutes)")
        print(f"Deployed:       {'Yes' if deployed else 'No'}")
        print(f"")
        print(f"Output directory: {self.run_dir}")
        print(f"")
        print(f"Generated files:")
        
        # Count files
        build_files = len(list(self.artifacts.build_dir.rglob('*')))
        qa_files = len(list(self.artifacts.qa_dir.rglob('*')))
        deploy_files = len(list(self.artifacts.deploy_dir.rglob('*')))
        log_files = len(list(self.artifacts.logs_dir.rglob('*')))
        
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
        description='FO Test Harness - BUILD → QA → DEPLOY Orchestration'
    )
    
    parser.add_argument(
        'intake_file',
        type=Path,
        help='Path to intake JSON file (MCv6-SCHEMA v21.4 format)'
    )
    
    parser.add_argument(
        'block',
        choices=['A', 'B', 'a', 'b'],
        help='Block to build (A or B)'
    )
    
    parser.add_argument(
        '--skip-deploy',
        action='store_true',
        help='Skip deployment phase (BUILD + QA only)'
    )
    
    parser.add_argument(
        '--environment',
        choices=['POC', 'PRODUCTION'],
        default='POC',
        help='Deployment environment (default: POC)'
    )
    
    args = parser.parse_args()
    
    # Validate environment variables
    if not Config.ANTHROPIC_API_KEY:
        print_error("ANTHROPIC_API_KEY environment variable not set")
        print_info("Set it with: export ANTHROPIC_API_KEY='your-key'")
        sys.exit(1)
    
    if not Config.OPENAI_API_KEY:
        print_error("OPENAI_API_KEY environment variable not set")
        print_info("Set it with: export OPENAI_API_KEY='your-key'")
        sys.exit(1)
    
    # Validate intake file
    if not args.intake_file.exists():
        print_error(f"Intake file not found: {args.intake_file}")
        sys.exit(1)
    
    # Create output directory
    Config.OUTPUT_DIR.mkdir(exist_ok=True)
    
    # Run harness
    try:
        harness = FOHarness(args.intake_file, args.block)
        success = harness.run(skip_deploy=args.skip_deploy)
        
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
