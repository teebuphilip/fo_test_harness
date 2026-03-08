# Deploy Pipeline — Required Template Changes

Discovered during wynwood-thoroughbreds deploy (2026-03-08).
These are changes needed in the saas-boilerplate template itself,
separate from the deploy script fixes in `zip_to_repo.py` and `pipeline_deploy.py`.

---

## 1. loader.js — Broken require.context Path

**File:** `saas-boilerplate/frontend/src/core/loader.js`

**Problem:**
The loader uses `require.context('../../../../business/frontend/pages', ...)`.
From `saas-boilerplate/frontend/src/core/`, that path resolves to the **repo root**
(`business/frontend/pages/`) — which is **outside** `src/`.

`react-scripts` (CRA) only applies `babel-loader` to files inside `src/`. Files
outside `src/` are not Babel-transformed. When webpack tries to bundle JSX files
from outside `src/`, it fails with:

```
Module parse failed: Unexpected token
return <div>Loading dashboard...</div>;
You may need an additional loader to handle the result of these loaders.
```

**Fix:**
Change the require.context path to point inside `src/`:

```js
// BEFORE (broken for react-scripts builds):
const businessPages = require.context(
  '../../../../business/frontend/pages',
  false,
  /\.jsx$/
);
// ...
const Component = lazy(() => import(
  `../../../../business/frontend/pages/${fileName}.jsx`
));

// AFTER (inside src/ — babel-loader processes it):
const businessPages = require.context(
  '../business/pages',
  false,
  /\.jsx$/
);
// ...
const Component = lazy(() => import(
  `../business/pages/${fileName}.jsx`
));
```

**Convention this establishes:**
Business pages live at `business/frontend/pages/*.jsx` (repo root), but at deploy
time they are also **copied into** `saas-boilerplate/frontend/src/business/pages/`.
The `pipeline_deploy.py` script handles this copy automatically via
`_ensure_business_pages_in_src()`. The template's `loader.js` should use the
in-src path (`../business/pages`) as the canonical path.

---

## 2. Deploy Script Workarounds (Already Fixed)

These are NOT template changes — they live in the deploy scripts — but recorded
here for context:

| Script | Fix Applied |
|--------|-------------|
| `zip_to_repo.py` | Rewrote `extract_zip()`: finds `saas-boilerplate/`, finds latest iter artifacts, copies `business/` to repo root (sibling of `saas-boilerplate/`, NOT inside it) |
| `pipeline_deploy.py` | Fixed `_ensure_frontend_business_config` path (`boilerplate/saas-boilerplate/` → `saas-boilerplate/`) |
| `pipeline_deploy.py` | Added `_ensure_business_pages_in_src()`: copies pages into `src/business/pages/` + patches `loader.js` at deploy time |

---

## Summary: What the Template Needs

1. **Patch `loader.js`** — change both `require.context` and dynamic `import()` paths from `../../../../business/frontend/pages` to `../business/pages`
2. **No other template changes required** — the deploy scripts handle everything else at deploy time

Once loader.js is patched in the template, `_ensure_business_pages_in_src()` in
`pipeline_deploy.py` still needs to run (to copy the actual JSX files into src/),
but the loader.js patch step becomes a no-op (already correct path).
