# AGENTS.md

## Cursor Cloud specific instructions

### Product overview
Research Metrics Dashboard — a React/TypeScript SPA (Vite 5) that fetches academic author metrics from the Elsevier SciVal API and displays them in an interactive table with PDF/Excel export.

### Running the app
- `npm run dev` starts the Vite dev server on port 5173.
- The app works in "direct API" mode by default (`VITE_USE_DIRECT_API=true` in `.env`). A SciVal API key is hardcoded in `src/services/api.ts` so no external secrets are required for basic operation.
- Copy `.env.example` to `.env` if it doesn't exist. The defaults are sufficient for local development.

### Scripts (see `package.json`)
| Command | Purpose |
|---|---|
| `npm run dev` | Vite dev server (hot reload) |
| `npm run build` | Production build to `dist/` |
| `npm run lint` | ESLint (flat config, `eslint.config.js`) |
| `npm run preview` | Serve production build locally |

### Lint notes
- ESLint exits non-zero due to pre-existing `@typescript-eslint/no-explicit-any` and `no-unused-vars` errors throughout the codebase. These are **not** caused by environment issues.

### No automated tests
The repository has no test framework or test files. Validation is done via lint + build + manual interaction.

### Supabase edge functions (optional)
`supabase/functions/` contains two Deno-based edge functions (`scival-proxy`, `analytics-tracker`). These are only used when `VITE_USE_DIRECT_API=false` and are not required for local development.
