# Review Evidence Extension

This stage adds individual review provenance to the existing thesis knowledge
graph without changing the recommendation score.

## New graph model

```text
(Laptop)-[:HAS_REVIEW]->(Review)-[:MENTIONS]->(Aspect)

(Laptop)-[:HAS_ASPECT_SCORE]->(Aspect)
```

`HAS_ASPECT_SCORE` remains the ranking layer.

`Review -> MENTIONS -> Aspect` is the explainability/provenance layer.

## Input integrity found in the supplied data

The uploaded data contains:

- 6,000 original reviews across 30 laptop CSV files
- 15,943 canonical review-aspect records
- 5,198 reviews with at least one canonical experience-aspect record

Every canonical review-aspect record joins to its original review using:

```text
source_file + review_id
```

with zero missing joins.

The source `laptop` value also matches the original review `Product` value
exactly for all joined records.

## Step 1

Copy the three scripts into:

```text
knowledge_graph/scripts/
```

Then prepare review evidence:

```powershell
python knowledge_graph/scripts/prepare_review_evidence.py
```

Expected outputs:

```text
knowledge_graph/review_evidence/
├── review_nodes.csv
├── laptop_review_edges.csv
├── review_aspect_edges.csv
└── review_evidence_manifest.json
```

## Step 2

Import into AuraDB:

```powershell
python knowledge_graph/scripts/import_review_evidence.py
```

The script reads the same `backend/.env` used by FastAPI.

It is idempotent: rerunning it uses `MERGE`.

## Step 3

Verify:

```powershell
python knowledge_graph/scripts/verify_review_evidence.py
```

Expected major counts:

```text
Review nodes             6000
HAS_REVIEW               6000
MENTIONS                 15943
```

## Important

This extension does not change:
- adjusted aspect scores
- Bayesian shrinkage
- evidence confidence
- balanced/custom recommendation ranking

It only adds traceable source review evidence.

After this graph layer passes verification, add an API endpoint such as:

```text
GET /api/laptops/{laptop_id}/aspects/{aspect_id}/evidence
```

and then expose selected review snippets in the frontend.
