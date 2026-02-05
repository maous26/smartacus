"""
Smartacus API Models
====================

Pydantic models for API request/response serialization.
Aligned with frontend TypeScript types.
"""

from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any
from datetime import datetime
from enum import Enum


class UrgencyLevel(str, Enum):
    """Urgency level matching frontend."""
    CRITICAL = "critical"
    URGENT = "urgent"
    ACTIVE = "active"
    STANDARD = "standard"
    EXTENDED = "extended"


class PipelineStatusEnum(str, Enum):
    """Pipeline status."""
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    ERROR = "error"


class ComponentScoreModel(BaseModel):
    """Score component detail."""
    name: str
    score: int
    maxScore: int = Field(alias="max_score")
    percentage: float

    class Config:
        populate_by_name = True


class EconomicEventModel(BaseModel):
    """Economic event/thesis."""
    eventType: str = Field(alias="event_type")
    thesis: str
    confidence: str
    urgency: str

    class Config:
        populate_by_name = True


class OpportunityModel(BaseModel):
    """
    Full opportunity model matching frontend Opportunity type.
    """
    rank: int
    asin: str
    title: Optional[str] = None
    brand: Optional[str] = None

    # Scores
    finalScore: int = Field(alias="final_score")
    baseScore: float = Field(alias="base_score")
    timeMultiplier: float = Field(alias="time_multiplier")

    # Economic values
    estimatedMonthlyProfit: float = Field(alias="estimated_monthly_profit")
    estimatedAnnualValue: float = Field(alias="estimated_annual_value")
    riskAdjustedValue: float = Field(alias="risk_adjusted_value")

    # Window
    windowDays: int = Field(alias="window_days")
    urgencyLevel: UrgencyLevel = Field(alias="urgency_level")
    urgencyLabel: str = Field(alias="urgency_label")

    # Thesis & Action
    thesis: str
    actionRecommendation: str = Field(alias="action_recommendation")

    # Score breakdown
    componentScores: Dict[str, ComponentScoreModel] = Field(
        default_factory=dict, alias="component_scores"
    )

    # Events
    economicEvents: List[EconomicEventModel] = Field(
        default_factory=list, alias="economic_events"
    )

    # Product metrics
    amazonPrice: Optional[float] = Field(None, alias="amazon_price")
    reviewCount: Optional[int] = Field(None, alias="review_count")
    rating: Optional[float] = None

    # Timestamps
    detectedAt: datetime = Field(alias="detected_at")

    class Config:
        populate_by_name = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class ShortlistCriteria(BaseModel):
    """Criteria used to generate shortlist."""
    minScore: int = Field(alias="min_score")
    minValue: float = Field(alias="min_value")
    maxItems: int = Field(alias="max_items")

    class Config:
        populate_by_name = True


class ShortlistSummary(BaseModel):
    """Summary of generated shortlist."""
    generatedAt: datetime = Field(alias="generated_at")
    count: int
    totalPotentialValue: float = Field(alias="total_potential_value")
    criteria: ShortlistCriteria

    class Config:
        populate_by_name = True


class ShortlistResponse(BaseModel):
    """
    Complete shortlist response matching frontend ShortlistResponse type.
    """
    summary: ShortlistSummary
    opportunities: List[OpportunityModel]


class PipelineStatus(BaseModel):
    """
    Pipeline status for header display.
    """
    lastRunAt: Optional[datetime] = Field(None, alias="last_run_at")
    status: PipelineStatusEnum
    asinsTracked: int = Field(alias="asins_tracked")
    opportunitiesFound: int = Field(alias="opportunities_found")
    nextRunAt: Optional[datetime] = Field(None, alias="next_run_at")

    class Config:
        populate_by_name = True


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    version: str
    database: str
    keepa: str
    lastPipelineRun: Optional[datetime] = Field(None, alias="last_pipeline_run")

    class Config:
        populate_by_name = True


class RunPipelineRequest(BaseModel):
    """Request to run the pipeline."""
    maxAsins: Optional[int] = Field(None, alias="max_asins")
    forceRefresh: bool = Field(False, alias="force_refresh")

    class Config:
        populate_by_name = True


class RunPipelineResponse(BaseModel):
    """Response after starting pipeline."""
    status: str
    message: str
    runId: Optional[str] = Field(None, alias="run_id")

    class Config:
        populate_by_name = True
