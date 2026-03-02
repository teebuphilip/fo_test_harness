Generate exactly one markdown file for boilerplate integration.

Output format must be:
**FILE: business/README-INTEGRATION.md**
```markdown
...content...
```

Requirements:
- Describe how business artifacts integrate with the boilerplate auto-loaders.
- Include frontend page mapping (`business/frontend/pages/*.jsx` -> `/dashboard/...`).
- Include backend route mapping (`business/backend/routes/*.py` -> `/api/...`).
- Include required environment/config notes only if they are grounded in manifest/build output.
- Do not invent external systems not present in the artifact list.
- Keep it concise and implementation-oriented.

Context:
- Startup: {{startup_id}}
- Block: {{block}}

Manifest sample:
{{manifest_sample}}

Build output sample:
{{build_output_sample}}
