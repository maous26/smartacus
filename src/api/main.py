"""
Smartacus FastAPI Application
=============================

REST API for the Smartacus opportunity detection platform.

Endpoints:
    GET  /api/health          - Health check
    GET  /api/shortlist       - Get current shortlist
    GET  /api/pipeline/status - Get pipeline status
    POST /api/pipeline/run    - Trigger pipeline run

Usage:
    uvicorn src.api.main:app --reload --port 8000

    Or with CLI:
    python -m src.api.main
"""

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from contextlib import asynccontextmanager
import csv
import io
import logging
from datetime import datetime

from .models import (
    ShortlistResponse,
    PipelineStatus,
    HealthResponse,
    RunPipelineRequest,
    RunPipelineResponse,
)
from .services import ShortlistService, PipelineService
from .ai_routes import router as ai_router
from .rag_routes import router as rag_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Services
shortlist_service: ShortlistService = None
pipeline_service: PipelineService = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    global shortlist_service, pipeline_service

    logger.info("Starting Smartacus API...")

    # Initialize services
    shortlist_service = ShortlistService()
    pipeline_service = PipelineService()

    logger.info("Services initialized")

    yield

    # Cleanup
    logger.info("Shutting down Smartacus API...")


# Create FastAPI app
app = FastAPI(
    title="Smartacus API",
    description="Sonde economique Amazon - Detection d'opportunites",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS configuration - allow all localhost ports for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:3002",
        "http://localhost:3003",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
        "http://127.0.0.1:3002",
        "http://127.0.0.1:3003",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include AI routes
app.include_router(ai_router)

# Include RAG routes
app.include_router(rag_router)


# ============================================================================
# HEALTH ENDPOINT
# ============================================================================

@app.get("/api/health", response_model=HealthResponse)
async def health_check():
    """
    Health check endpoint.

    Returns status of all system components.
    """
    # TODO: Add actual health checks for DB, Keepa, etc.
    return HealthResponse(
        status="healthy",
        version="0.1.0",
        database="connected",  # TODO: Check actual connection
        keepa="configured",    # TODO: Check API key validity
        last_pipeline_run=datetime.utcnow(),
    )


# ============================================================================
# SHORTLIST ENDPOINTS
# ============================================================================

@app.get("/api/shortlist", response_model=ShortlistResponse)
async def get_shortlist(
    max_items: int = Query(5, ge=1, le=10, description="Maximum items in shortlist"),
    min_score: int = Query(50, ge=0, le=100, description="Minimum score threshold"),
    min_value: float = Query(5000, ge=0, description="Minimum annual value ($)"),
):
    """
    Get the current opportunity shortlist.

    Returns top opportunities ranked by value x urgency.

    The shortlist is CONSTRAINED by design:
    - Maximum 5 items (concentration over dispersion)
    - Each item has a clear thesis and action recommendation
    - Ranked by risk-adjusted value weighted by urgency

    Response matches frontend ShortlistResponse type.
    """
    try:
        shortlist = shortlist_service.get_shortlist(
            max_items=max_items,
            min_score=min_score,
            min_value=min_value,
        )
        return shortlist
    except Exception as e:
        logger.error(f"Error generating shortlist: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/shortlist/export")
async def export_shortlist_csv(
    max_items: int = Query(5, ge=1, le=10),
    min_score: int = Query(50, ge=0, le=100),
    min_value: float = Query(5000, ge=0),
    urgency: str = Query(None, description="Filter by urgency level (critical,urgent,active,standard,extended)"),
    event_type: str = Query(None, description="Filter by event type (SUPPLY_SHOCK,COMPETITOR_COLLAPSE,QUALITY_DECAY)"),
):
    """
    Export shortlist as CSV file.

    Supports the same filters as the shortlist endpoint plus urgency and event_type filters.
    """
    try:
        shortlist = shortlist_service.get_shortlist(
            max_items=max_items,
            min_score=min_score,
            min_value=min_value,
        )

        opportunities = shortlist.opportunities

        # Apply urgency filter
        if urgency:
            allowed = {u.strip().lower() for u in urgency.split(",")}
            opportunities = [o for o in opportunities if o.urgencyLevel.value in allowed]

        # Apply event type filter
        if event_type:
            allowed_events = {e.strip().upper() for e in event_type.split(",")}
            opportunities = [
                o for o in opportunities
                if any(ev.eventType in allowed_events for ev in o.economicEvents)
            ]

        # Build CSV
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "Rank", "ASIN", "Title", "Brand", "Score", "Base Score",
            "Time Multiplier", "Monthly Profit ($)", "Annual Value ($)",
            "Risk-Adjusted Value ($)", "Window (days)", "Urgency",
            "Thesis", "Action", "Events", "Price ($)", "Reviews", "Rating",
        ])

        for i, opp in enumerate(opportunities, 1):
            events_str = " | ".join(
                f"{ev.eventType}: {ev.thesis}" for ev in opp.economicEvents
            ) if opp.economicEvents else ""

            writer.writerow([
                i,
                opp.asin,
                opp.title or "",
                opp.brand or "",
                opp.finalScore,
                opp.baseScore,
                opp.timeMultiplier,
                f"{opp.estimatedMonthlyProfit:.0f}",
                f"{opp.estimatedAnnualValue:.0f}",
                f"{opp.riskAdjustedValue:.0f}",
                opp.windowDays,
                opp.urgencyLevel.value,
                opp.thesis,
                opp.actionRecommendation,
                events_str,
                opp.amazonPrice or "",
                opp.reviewCount or "",
                opp.rating or "",
            ])

        output.seek(0)
        filename = f"smartacus_shortlist_{datetime.utcnow().strftime('%Y%m%d_%H%M')}.csv"

        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    except Exception as e:
        logger.error(f"Error exporting CSV: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/opportunities/{asin}")
async def get_opportunity(asin: str):
    """
    Get details for a specific opportunity.

    Args:
        asin: Amazon Standard Identification Number

    Returns:
        Full opportunity details including:
        - Score breakdown
        - Economic thesis
        - Historical data
        - Action recommendation
    """
    # TODO: Implement single opportunity lookup
    raise HTTPException(status_code=501, detail="Not implemented yet")


# ============================================================================
# PIPELINE ENDPOINTS
# ============================================================================

@app.get("/api/pipeline/status", response_model=PipelineStatus)
async def get_pipeline_status():
    """
    Get current pipeline status.

    Returns:
        - Last run timestamp
        - Current status (idle/running/completed/error)
        - Number of ASINs tracked
        - Number of opportunities found
        - Next scheduled run
    """
    try:
        status = pipeline_service.get_status()
        return status
    except Exception as e:
        logger.error(f"Error getting pipeline status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/pipeline/run", response_model=RunPipelineResponse)
async def run_pipeline(request: RunPipelineRequest = None):
    """
    Trigger a pipeline run.

    Args:
        max_asins: Optional limit on ASINs to process (for testing)
        force_refresh: If true, refresh all data regardless of age

    Returns:
        Run ID for tracking progress
    """
    try:
        if request is None:
            request = RunPipelineRequest()

        result = await pipeline_service.run_pipeline(
            max_asins=request.maxAsins,
            force_refresh=request.forceRefresh,
        )
        return RunPipelineResponse(**result)
    except Exception as e:
        logger.error(f"Error starting pipeline: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    import uvicorn

    print("=" * 60)
    print("SMARTACUS API SERVER")
    print("=" * 60)
    print()
    print("Starting server at http://localhost:8000")
    print()
    print("API Documentation:")
    print("  - Swagger UI: http://localhost:8000/docs")
    print("  - ReDoc:      http://localhost:8000/redoc")
    print()
    print("Endpoints:")
    print("  GET  /api/health          - Health check")
    print("  GET  /api/shortlist       - Get opportunity shortlist")
    print("  GET  /api/pipeline/status - Pipeline status")
    print("  POST /api/pipeline/run    - Trigger pipeline run")
    print()
    print("AI Endpoints:")
    print("  GET  /api/ai/status       - AI services status")
    print("  POST /api/ai/thesis       - Generate economic thesis")
    print("  POST /api/ai/agent/*      - Agent interactions")
    print()
    print("RAG Endpoints:")
    print("  GET  /api/rag/status      - RAG system status")
    print("  POST /api/rag/search      - Search knowledge base")
    print("  POST /api/rag/ingest      - Ingest document")
    print("  GET  /api/rag/stats       - RAG statistics")
    print()
    print("=" * 60)

    uvicorn.run(
        "src.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
