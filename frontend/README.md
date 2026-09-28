# Frontend — Laptop Recommendation Thesis

React + Vite frontend for the FastAPI + Neo4j AuraDB system.

## What it does

- Reads canonical aspects from `GET /api/aspects`
- Reads available filter values from `GET /api/filters`
- Sends hard filters + user aspect weights to `POST /api/recommendations`
- Displays recommendation score separately from evidence confidence
- Displays per-aspect evidence levels
- Shows laptop images from `image_url`
- Provides clickable product links from `product_url`
- Loads detailed specifications and aspect evidence from `GET /api/laptops/{id}`
- Supports Top 5, Top 10, Top 20, or all 30 laptops

## First-time setup

Make sure Node.js is installed:

```powershell
node --version
npm --version
```

Keep FastAPI running in one PowerShell window:

```powershell
cd "C:\Users\USER\Desktop\Program"
uvicorn backend.app.main:app --reload
```

Open a second PowerShell window:

```powershell
cd "C:\Users\USER\Desktop\Program\frontend"
npm install
```

Copy:

```text
frontend/.env.example
```

to:

```text
frontend/.env
```

For local development it should contain:

```env
VITE_API_BASE_URL=http://127.0.0.1:8000
```

This frontend environment value is not secret. AuraDB credentials remain only
inside `backend/.env`.

Start the frontend:

```powershell
npm run dev
```

Then open:

```text
http://localhost:5173
```

## Normal startup after setup

### PowerShell 1 — backend

```powershell
cd "C:\Users\USER\Desktop\Program"
uvicorn backend.app.main:app --reload
```

### PowerShell 2 — frontend

```powershell
cd "C:\Users\USER\Desktop\Program\frontend"
npm run dev
```

Open:

```text
http://localhost:5173
```

## Images and product links

The FastAPI recommendation response already returns:

```json
{
  "image_url": "https://...",
  "product_url": "https://..."
}
```

The UI renders the image on each recommendation card and provides a
"View product" link that opens the original product page in a new tab.

Some retailer/CDN image hosts can block third-party embedding. If a particular
image cannot be displayed, the UI shows a placeholder while the product link
still works.

## Production later

When you eventually deploy:

1. Deploy FastAPI to a cloud host.
2. Add the deployed frontend origin to backend `CORS_ORIGINS`.
3. Change `VITE_API_BASE_URL` to the deployed FastAPI URL.
4. Run:

```powershell
npm run build
```

Vite outputs production files to:

```text
frontend/dist/
```


## Recommendation modes

The frontend now offers two ranking modes:

- **Balanced mode (default):** all canonical experience aspects are passed to
  the backend with equal weight. The user can rank laptops without touching
  any preference sliders.
- **Custom preferences:** the user chooses active aspects and weights manually.
  A Battery Life 50 / Performance 30 / Thermal Performance 20 preset is
  available as an optional example only.

The backend still performs exactly the same evidence-aware scoring. Balanced
mode simply sends equal raw weights for every aspect; the backend normalizes
them automatically.
