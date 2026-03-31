# Research Metrics Dashboard

Streamlit app for SciVal author metrics (HKUST Library). Configure API access with environment variables (see `.env.example`).

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate   # Windows
# source .venv/bin/activate   # macOS/Linux

pip install -r requirements.txt
```

Copy `.env.example` to `.env` and set:

- SciVal / Elsevier API key (any one): `VITE_SCIVAL_API_KEY`, `SCIVAL_API_KEY`, `ELSEVIER_API_KEY`, or `ELS_API_KEY` (direct API and ORCID lookup). On Railway, add one of these in **Variables** for the service.
- **No Supabase URL:** the app uses **direct** Elsevier SciVal API automatically (good for simple hosting).
- **Using the Supabase proxy:** set `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY`, and leave `VITE_USE_DIRECT_API` unset or `false` unless you want to force direct API anyway.
- `VITE_USE_DIRECT_API` — optional override when both direct and proxy are configured

## Run

From the repository root:

```bash
streamlit run streamlit_app/app.py
```

## Supabase

The `supabase/` folder holds Edge Functions (e.g. `scival-proxy`) if you deploy the proxy backend. The Streamlit app does not require Node.js.

For the **`scival-proxy`** function, set the Elsevier key as a Supabase secret (Dashboard → **Edge Functions** → **Manage secrets**), e.g. `SCIVAL_API_KEY` (or `ELSEVIER_API_KEY`). From the CLI: `supabase secrets set SCIVAL_API_KEY=your_key`. Do not commit keys in the repo.

If you still see a `node_modules` folder from the old React/Vite app, delete it manually after closing any process that locks files inside it (terminals, dev servers, antivirus scans).
