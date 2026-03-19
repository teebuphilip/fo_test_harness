# LookAndFeel Agent

`design_agent.py` analyzes and improves only visual look-and-feel for a GitHub repo.

It performs two AI passes:
- Pass 1: assess visual quality
- Pass 2: apply visual updates to target files

It does **not** change UI flow, business logic, routing, or data behavior.

## Required Env Vars

- `BASE44_API_KEY`

## Optional Env Vars

- `BASE44_API_URL` (default: `https://api.anthropic.com/v1/messages`)
- `BASE44_MODEL` (default: `claude-sonnet-4-20250514`)
- `BASE44_API_VERSION` (default: `2023-06-01`)
- `BASE44_MAX_TOKENS` (default: `8192`)
- `GITHUB_TOKEN` (needed for private repos, optional for public repos)
- `GITHUB_BRANCH` (default: `HEAD`)
- `OUTPUT_DIR` (default: `./lookandfeel_output`)
- `DRY_RUN` (`true` or `false`, default `false`)
- `TARGET_FILES` (comma-separated fallback list)

## Target File Resolution Order

1. `DESIGN_DIRECTIVE.md` target list in repo root
2. AI discovery from repo file tree
3. `TARGET_FILES` env override
4. Hardcoded fallback list

## Usage

```bash
python lookandfeel/design_agent.py https://github.com/<owner>/<repo>
python lookandfeel/design_agent.py https://github.com/<owner>/<repo> main
```

Dry run:

```bash
DRY_RUN=true python lookandfeel/design_agent.py https://github.com/<owner>/<repo>
```

## Output

Under `OUTPUT_DIR`:
- `assessment.json`
- `DESIGN_DIRECTIVE.generated.md`
- `files/<path>` updated file contents

## Repo Visibility Helper

Use one script with a flag to flip public/private:

```bash
python lookandfeel/repo_visibility.py --repo owner/repo --visibility public
python lookandfeel/repo_visibility.py --repo owner/repo --visibility private
```

Requires:
- `GITHUB_TOKEN`
