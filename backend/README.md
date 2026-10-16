# FastAPI Backend

The API serving the **[Evidence-Aware Laptop Recommendation System](../README.md)**. It connects to a **previously populated Neo4j/AuraDB** instance, applies hard specification filters, performs weighted recommendation ranking from precomputed `HAS_ASPECT_SCORE` relationships, and retrieves supporting review evidence.

> DistilBERT inference, ontology aggregation, and aspect-score preparation happen offline, **not** inside API requests.

## Local setup (PowerShell)

Run from the repository root:

```powershell
python -m pip install -r backend/requirements.txt
Copy-Item backend/.env.example backend/.env
# Set YOUR database URI, username, password, database name, and allowed CORS origins.
uvicorn backend.app.main:app --reload
```

Required values in `backend/.env`: `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, `NEO4J_DATABASE`. `CORS_ORIGINS` is a comma-separated list of permitted frontend origins. Use the actual database name for your Neo4j instance, which is not always `neo4j`.

- Local API: http://127.0.0.1:8000
- Interactive API docs: http://127.0.0.1:8000/docs
- Health check: http://127.0.0.1:8000/api/health

## Implemented endpoints

| Method | Route | Function |
|---|---|---|
| GET | `/api/health` | Checks graph connectivity |
| GET | `/api/aspects` | Returns selectable canonical experience aspects |
| GET | `/api/filters` | Reads available specification filter values |
| GET | `/api/laptops/{laptop_id}` | Returns specifications, scores and explanatory metadata |
| GET | `/api/laptops/{laptop_id}/aspects/{aspect_id}/evidence` | Returns sentiment-diverse source review snippets |
| POST | `/api/recommendations` | Filters and ranks laptop candidates using normalized weights |
| POST | `/api/recommendations/refine` | Independently verifies the initial shortlist and reranks only its members |

Example recommendation request:

```json
{
  "filters": {"min_ram": 16, "min_storage": 512, "max_price": 1500},
  "weights": {"BATTERY_LIFE": 50, "PERFORMANCE": 30, "THERMAL_PERFORMANCE": 20},
  "top_n": 5
}
```

Recommendation score and evidence confidence are distinct outputs. The backend rejects unknown/retired aspects as active preferences and prevents guided Stage 2 from introducing out-of-shortlist laptops.

## Operational precautions

- `backend/.env` is secret and excluded from Git. Do **not** place credentials in frontend variables.
- Confirm the database contains the current corrected research artifacts before interpreting its results.
- Never run graph-import scripts against a production database without confirming the intended target and backup.
- Deploy the backend with `backend` as the root directory and an appropriate Uvicorn startup command for your Render configuration; see the actual deployment service settings before changing them.
