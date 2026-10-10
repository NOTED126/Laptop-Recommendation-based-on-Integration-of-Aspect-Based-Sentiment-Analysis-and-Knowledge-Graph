from contextlib import asynccontextmanager

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .db import db
from .models import (
    AspectEvidenceResponse,
    AspectInfo,
    FilterOptionsResponse,
    LaptopDetail,
    RecommendationRequest,
    RecommendationResponse,
    TwoStageRefinementRequest,
)
from .services import (
    get_aspect_evidence,
    get_aspects,
    get_filter_options,
    get_laptop_detail,
    get_recommendations,
    get_refined_recommendations,
)


settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.verify_connectivity()
    yield
    db.close()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "FastAPI backend for the evidence-aware "
        "knowledge-graph laptop recommendation system."
    ),
    lifespan=lifespan,
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {
        "message": "Laptop Recommendation API",
        "docs": "/docs",
    }


@app.get("/api/health")
def health():
    rows = db.execute_read(
        """
        RETURN
            'ok' AS status,
            1 AS database_test
        """
    )

    return {
        "status": "ok",
        "database_connected": bool(rows),
    }


@app.get(
    "/api/aspects",
    response_model=list[AspectInfo],
)
def aspects():
    return get_aspects()


@app.get(
    "/api/filters",
    response_model=FilterOptionsResponse,
)
def filters():
    return get_filter_options()


@app.get(
    "/api/laptops/{laptop_id}",
    response_model=LaptopDetail,
)
def laptop_detail(laptop_id: str):
    return get_laptop_detail(laptop_id)


@app.get(
    "/api/laptops/{laptop_id}/aspects/{aspect_id}/evidence",
    response_model=AspectEvidenceResponse,
)
def aspect_evidence(
    laptop_id: str,
    aspect_id: str,
    limit: int = Query(
        default=6,
        ge=1,
        le=20,
        description=(
            "Maximum number of sentiment-diverse review snippets "
            "to return."
        ),
    ),
):
    return get_aspect_evidence(
        laptop_id=laptop_id,
        aspect_id=aspect_id,
        limit=limit,
    )


@app.post(
    "/api/recommendations",
    response_model=RecommendationResponse,
)
def recommendations(request: RecommendationRequest):
    return get_recommendations(request)


@app.post(
    "/api/recommendations/refine",
    response_model=RecommendationResponse,
)
def recommendations_refine(request: TwoStageRefinementRequest):
    """Rerank the verified Stage 1 shortlist with refined user weights."""
    return get_refined_recommendations(request)
