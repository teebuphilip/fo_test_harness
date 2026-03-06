# Plan P: Config-Driven Static Check Engine

## Goal
Move static-check policy from hardcoded paths/markers into a rules file while keeping current behavior stable.

## Implementation Steps

1. Create `fo_static_check_rules.json` at repo root.
2. Add rule-loader in `fo_test_harness.py` with fallback:
   - requested profile -> `default_profile` -> current hardcoded defaults.
3. Refactor existing static checks to consume rules:
   - requirements path check
   - model/route role checks
   - frontend config sanity checks
   - local import prefix/case checks
   - route/service directory discovery for contract checks
4. Keep intake-aware checks (KPI/download) as Python logic in phase 1.
5. Validate on known-good + known-bad artifact sets for regression.
6. Update docs/changelog.

## Proposed Rules File Shape

```json
{
  "$schema_version": "1.0",
  "default_profile": "fastapi_nextjs",
  "profiles": {
    "fastapi_nextjs": {
      "description": "FounderOps FastAPI backend + React/Next-style frontend layout",
      "local_import_prefixes": ["business."],
      "requirements_files": [
        "business/backend/requirements.txt",
        "business/requirements.txt",
        "requirements.txt"
      ],
      "directories": {
        "models": ["business/models"],
        "routes": ["business/backend/routes"],
        "services": ["business/services"],
        "frontend": ["business/frontend"]
      },
      "markers": {
        "route_decorators_regex": "@router\\.(get|post|put|delete|patch)\\s*\\(",
        "route_symbols_any": ["APIRouter", "@router."],
        "model_symbols_any": ["__tablename__", "class "],
        "auth_symbols_any": ["Depends(get_current_user)", "require_role", "get_current_user"]
      },
      "config_rules": [
        {
          "path": "business/frontend/next.config.js",
          "must_contain_any": [],
          "must_not_contain_any": ["compilerOptions"],
          "severity": "HIGH",
          "issue": "next.config.js appears to contain tsconfig content",
          "fix": "Replace with valid Next.js config object"
        },
        {
          "path": "business/frontend/postcss.config.js",
          "must_contain_any": ["plugins"],
          "must_not_contain_any": ["rewrites()", "destination:", "nextConfig", "reactStrictMode"],
          "severity": "HIGH",
          "issue": "postcss.config.js appears to contain non-PostCSS config",
          "fix": "Replace with PostCSS plugin config"
        },
        {
          "path_glob": "business/frontend/tailwind.config.*",
          "must_contain_any": ["content:"],
          "must_not_contain_any": [],
          "severity": "HIGH",
          "issue": "Tailwind config missing content paths",
          "fix": "Add content globs and valid Tailwind config structure"
        }
      ],
      "checks": {
        "check_requirements_yaml_contamination": true,
        "check_role_mismatch_models_vs_routes": true,
        "check_frontend_config_sanity": true,
        "check_local_import_integrity": true,
        "check_case_sensitive_import_paths": true,
        "check_route_service_contract": true,
        "check_unauthenticated_routes": true
      },
      "thresholds": {
        "route_file_without_endpoints_severity": "MEDIUM",
        "duplicate_kpi_service_severity": "MEDIUM",
        "missing_kpi_severity": "HIGH"
      }
    }
  }
}
```

## Minimal Validation Rules

1. `default_profile` exists in `profiles`.
2. Each profile has `directories`, `markers`, and `checks`.
3. `severity` values restricted to `HIGH|MEDIUM|LOW`.
4. `requirements_files` is non-empty.
5. `local_import_prefixes` is non-empty.
