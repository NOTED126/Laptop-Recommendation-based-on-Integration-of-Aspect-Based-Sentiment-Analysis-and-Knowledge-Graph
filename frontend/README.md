# React/Vite Frontend

User interface for the **[Evidence-Aware Laptop Recommendation System](../README.md)**. It calls the Neo4j-backed FastAPI backend; the browser does **not** connect directly to Neo4j and never handles database credentials.

## Current features

- **Balanced:** equal weights across the 23 selectable experience aspects.
- **Custom Preferences:** user-selected aspects and weights.
- **Guided Two-Stage Refinement:** verified initial shortlist of up to 10 laptops, with the second stage reranking only its original members after adding preferences.
- Hardware filters, ranked results, image/product links, aspect evidence information, and evidence-supported strengths/weaknesses summaries.
- Two-/three-laptop comparison with specification extremes, coverage highlighting, sorted aspect scores, and top/bottom sentiment radar charts.
- Inline evidence details with source review snippets; missing direct aspect evidence appears as N/A.
- Client-only highlighting of key phrases in previously approved summaries; no online AI generation.

## Run locally

The backend requires an **already populated Neo4j database**. Run from the repository root in the first PowerShell terminal:

```powershell
python -m pip install -r backend/requirements.txt
Copy-Item backend/.env.example backend/.env
# Enter your own Neo4j credentials in backend/.env.
uvicorn backend.app.main:app --reload
```

In another terminal:

```powershell
cd frontend
npm ci
Copy-Item .env.example .env.local
# For local development, VITE_API_BASE_URL=http://127.0.0.1:8000
npm run dev
```

Open http://localhost:5173. Do not place secrets in `VITE_` variables; those values are visible in bundled browser code.

## Build and regression tests

```powershell
cd frontend
node test_display_all.mjs
node test_supervisor_comparison.mjs
node test_supervisor_four_refinements.mjs
node test_summary_coverage.mjs
npm run build
```

The production output is written to `frontend/dist/` and is not committed to Git. Production uses the `VITE_API_BASE_URL` set at build time (`frontend/.env.production` currently contains the deployed API endpoint). Set the Render frontend service's root directory to `frontend` and publish directory to `dist` if deploying as a Static Site.

See the [root README](../README.md) and [environment guide](../docs/ENVIRONMENT_SETUP.md) for ML data dependencies and full deployment context.
