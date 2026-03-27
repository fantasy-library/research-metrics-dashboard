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

- `VITE_USE_DIRECT_API` — `true` for direct Elsevier API, `false` to use the Supabase edge function proxy
- `VITE_SUPABASE_URL` / `VITE_SUPABASE_ANON_KEY` — required when using the proxy
- `VITE_SCIVAL_API_KEY` or `SCIVAL_API_KEY` — SciVal API key (direct API and ORCID lookup)

## Run

From the repository root:

```bash
streamlit run streamlit_app/app.py
```

## Supabase

The `supabase/` folder holds Edge Functions (e.g. `scival-proxy`) if you deploy the proxy backend. The Streamlit app does not require Node.js.

If you still see a `node_modules` folder from the old React/Vite app, delete it manually after closing any process that locks files inside it (terminals, dev servers, antivirus scans).
