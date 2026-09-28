# FastAPI Backend — Laptop Recommendation Thesis

This backend connects the future website to the AuraDB knowledge graph.

## Architecture

```text
Frontend
   |
   | HTTP / JSON
   v
FastAPI
   |
   | Neo4j Python driver
   v
AuraDB
```

The frontend never receives Neo4j credentials.

## 1. Install dependencies

From the project root:

```powershell
python -m pip install -r backend/requirements.txt
```

## 2. Create backend/.env

Copy:

```text
backend/.env.example
```

to:

```text
backend/.env
```

Fill it with the exact working Aura values.

Important: for this project, the Aura database name may be the Aura instance/database ID,
rather than `neo4j`. Use the same database name that already worked with the importer.

## 3. Run the API

From the thesis project root:

```powershell
uvicorn backend.app.main:app --reload
```

Expected local URL:

```text
http://127.0.0.1:8000
```

Swagger UI:

```text
http://127.0.0.1:8000/docs
```

## 4. Test endpoints

### Health

```text
GET /api/health
```

Expected:

```json
{
  "status": "ok",
  "database_connected": true
}
```

### Canonical aspects

```text
GET /api/aspects
```

Returns the ontology aspects that the frontend can offer as user preferences.

### Filter options

```text
GET /api/filters
```

Returns:
- brands
- CPU brands
- GPU brands
- available RAM capacities
- available storage capacities
- available screen sizes
- minimum/maximum laptop prices

### Laptop details

```text
GET /api/laptops/{laptop_id}
```

Includes:
- laptop specifications
- image_url
- product_url
- every aspect score and its evidence information

### Recommendations

```text
POST /api/recommendations
```

Example request:

```json
{
  "filters": {
    "min_ram": 16,
    "min_storage": 512,
    "max_price": 1500
  },
  "weights": {
    "BATTERY_LIFE": 50,
    "PERFORMANCE": 30,
    "THERMAL_PERFORMANCE": 20
  },
  "top_n": 5
}
```

Weights are normalized automatically.

The endpoint:
1. applies hard specification filters
2. retrieves eligible laptops
3. calculates weighted recommendation scores from `adjusted_score`
4. calculates evidence confidence separately
5. sorts by score, then confidence
6. returns top-N laptops
7. includes per-aspect explanation data

## Laptop images and product links

The API returns both:

```json
{
  "image_url": "https://...",
  "product_url": "https://..."
}
```

The future frontend can render:

```html
<img src="{image_url}" alt="Laptop image">
<a href="{product_url}" target="_blank" rel="noopener noreferrer">
  View product
</a>
```

The image and link are therefore already supported by the backend design.

## CORS

During frontend development, the defaults allow:

```text
http://localhost:5173
http://localhost:3000
```

When the final frontend is deployed, add its real domain to `CORS_ORIGINS`.
