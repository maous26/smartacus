"""
Smartacus AI API Routes
=======================

Endpoints pour les fonctionnalités IA :
- Génération de thèses économiques
- Agents conversationnels (Discovery, Analyst, Sourcing, Negotiator)
- Analyse de reviews
"""

import logging
from fastapi import APIRouter, HTTPException, Body
from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ai", tags=["AI"])


# =============================================================================
# MODELS
# =============================================================================

class ThesisRequest(BaseModel):
    """Requête de génération de thèse."""
    asin: str
    opportunity_data: Dict[str, Any]
    score_data: Dict[str, Any]
    events: Optional[List[Dict[str, Any]]] = None


class ThesisResponse(BaseModel):
    """Réponse avec la thèse générée."""
    asin: str
    headline: str
    thesis: str
    reasoning: List[str]
    confidence: str
    action: str
    urgency: str
    risks: List[str]
    next_steps: List[str]
    estimated_monthly_profit: Optional[float] = None
    cost_usd: float


class AgentMessageRequest(BaseModel):
    """Message envoyé à un agent."""
    agent_type: str = Field(..., description="discovery|analyst|sourcing|negotiator")
    message: str
    context: Optional[Dict[str, Any]] = None
    session_id: Optional[str] = None


class AgentMessageResponse(BaseModel):
    """Réponse d'un agent."""
    agent_type: str
    message: str
    suggested_actions: List[Dict[str, str]] = []
    questions: List[str] = []
    next_stage: Optional[str] = None
    requires_input: bool = True
    session_id: str


class ReviewAnalysisRequest(BaseModel):
    """Requête d'analyse de reviews."""
    asin: str
    reviews: List[Dict[str, Any]]
    product_title: Optional[str] = None


class ReviewAnalysisResponse(BaseModel):
    """Résultat de l'analyse de reviews."""
    asin: str
    reviews_analyzed: int
    sentiment: str
    negative_rate: str
    differentiation_score: float
    opportunity_signals: List[Dict[str, Any]]
    summary: str
    top_pain_points: List[str]
    top_wishes: List[str]


# =============================================================================
# SESSION MANAGEMENT
# =============================================================================

# Simple in-memory session storage (en prod: Redis)
_agent_sessions: Dict[str, Dict[str, Any]] = {}


def get_or_create_session(session_id: Optional[str]) -> tuple:
    """Récupère ou crée une session agent."""
    import uuid

    if session_id and session_id in _agent_sessions:
        return session_id, _agent_sessions[session_id]

    new_id = str(uuid.uuid4())[:8]
    _agent_sessions[new_id] = {
        "created_at": datetime.utcnow().isoformat(),
        "messages": [],
        "context": {},
    }
    return new_id, _agent_sessions[new_id]


# =============================================================================
# CONTEXT ENRICHMENT
# =============================================================================

def _enrich_context(context):
    """Auto-inject review_profile and spec_bundle from DB into agent context."""
    asin = context.asin
    if not asin:
        return

    try:
        from . import db
        from .shared import load_profile

        pool = db.get_pool()
        if not pool:
            return

        conn = pool.getconn()
        try:
            # Review intelligence profile
            profile = load_profile(conn, asin)
            if profile:
                context.review_profile = {
                    "improvement_score": profile.improvement_score,
                    "dominant_pain": profile.dominant_pain,
                    "reviews_analyzed": profile.reviews_analyzed,
                    "negative_reviews_analyzed": profile.negative_reviews_analyzed,
                    "has_actionable_insights": profile.has_actionable_insights,
                    "thesis_fragment": profile.to_thesis_fragment(),
                    "top_defects": [
                        {"type": d.defect_type, "freq": d.frequency,
                         "severity": d.severity_score, "rate": d.frequency_rate}
                        for d in profile.top_defects
                    ],
                    "missing_features": [
                        {"feature": f.feature, "mentions": f.mentions,
                         "wish_strength": f.wish_strength}
                        for f in profile.missing_features
                    ],
                }

            # Product spec bundle
            try:
                from ..specs import SpecGenerator
                generator = SpecGenerator()
                cached = generator.load_bundle_from_db(conn, asin)
                if cached:
                    context.spec_bundle = {
                        "oem_spec_text": cached.get("oem_spec_text", ""),
                        "qc_checklist_text": cached.get("qc_checklist_text", ""),
                        "rfq_message_text": cached.get("rfq_message_text", ""),
                        "total_requirements": cached.get("total_requirements", 0),
                        "total_qc_tests": cached.get("total_qc_tests", 0),
                    }
            except Exception:
                pass  # Spec module optional
        finally:
            pool.putconn(conn)
    except Exception as e:
        logger.warning(f"Context enrichment failed for {asin}: {e}")


# =============================================================================
# THESIS ENDPOINT
# =============================================================================

@router.post("/thesis", response_model=ThesisResponse)
async def generate_thesis(request: ThesisRequest):
    """
    Génère une thèse économique pour une opportunité.

    La thèse est le "jugement économique" que les outils comme
    Jungle Scout ne fournissent pas.

    Requires: ANTHROPIC_API_KEY ou OPENAI_API_KEY
    """
    try:
        from ..ai.thesis_generator import ThesisGenerator

        generator = ThesisGenerator()

        # Enrich opportunity_data with review_profile from DB
        enriched_data = dict(request.opportunity_data)
        if "review_profile" not in enriched_data:
            asin = enriched_data.get("asin", "")
            if asin:
                try:
                    from .shared import load_profile
                    from .db import get_connection
                    with get_connection() as conn:
                        profile = load_profile(conn, asin)
                        if profile:
                            enriched_data["review_profile"] = {
                                "improvement_score": profile.improvement_score,
                                "dominant_pain": profile.dominant_pain,
                                "reviews_analyzed": profile.reviews_analyzed,
                                "negative_reviews_analyzed": profile.negative_reviews_analyzed,
                                "top_defects": [
                                    {"defect_type": d.defect_type, "frequency": d.frequency,
                                     "frequency_rate": d.frequency / max(profile.negative_reviews_analyzed, 1),
                                     "severity_score": d.severity_score}
                                    for d in profile.top_defects
                                ],
                                "missing_features": [
                                    {"feature": f.feature, "mentions": f.mentions}
                                    for f in profile.missing_features
                                ],
                                "thesis_fragment": profile.to_thesis_fragment() if hasattr(profile, 'to_thesis_fragment') else "",
                            }
                except Exception:
                    pass  # Non-blocking: thesis works without review data

        thesis = await generator.generate_thesis(
            opportunity_data=enriched_data,
            score_data=request.score_data,
            events=request.events,
        )

        return ThesisResponse(
            asin=thesis.asin,
            headline=thesis.headline,
            thesis=thesis.thesis,
            reasoning=thesis.reasoning,
            confidence=thesis.confidence.value,
            action=thesis.action,
            urgency=thesis.urgency.value,
            risks=thesis.risks,
            next_steps=thesis.next_steps,
            estimated_monthly_profit=thesis.estimated_monthly_profit,
            cost_usd=thesis.cost_usd,
        )

    except ValueError as e:
        raise HTTPException(
            status_code=503,
            detail=f"LLM not configured: {str(e)}. Set ANTHROPIC_API_KEY or OPENAI_API_KEY"
        )
    except Exception as e:
        logger.error(f"Thesis generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# AGENT ENDPOINTS
# =============================================================================

@router.post("/agent/message", response_model=AgentMessageResponse)
async def agent_message(request: AgentMessageRequest):
    """
    Envoie un message à un agent IA.

    Agents disponibles :
    - discovery : Présentation et qualification des opportunités
    - analyst : Analyse approfondie
    - sourcing : Accompagnement fournisseurs
    - negotiator : Aide à la négociation
    """
    try:
        from ..ai.agents import (
            DiscoveryAgent,
            AnalystAgent,
            SourcingAgent,
            NegotiatorAgent,
            AgentContext,
        )

        # Récupérer/créer la session
        session_id, session = get_or_create_session(request.session_id)

        # Mettre à jour le contexte
        if request.context:
            session["context"].update(request.context)

        # Créer le contexte agent
        context = AgentContext(
            asin=session["context"].get("asin"),
            opportunity_data=session["context"].get("opportunity_data", {}),
            thesis=session["context"].get("thesis"),
            messages=session["messages"],
        )

        # Enrich context with review intelligence + spec bundle
        _enrich_context(context)

        # Sélectionner l'agent
        agents = {
            "discovery": DiscoveryAgent,
            "analyst": AnalystAgent,
            "sourcing": SourcingAgent,
            "negotiator": NegotiatorAgent,
        }

        agent_class = agents.get(request.agent_type.lower())
        if not agent_class:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown agent type: {request.agent_type}"
            )

        agent = agent_class()

        # Traiter le message
        response = await agent.process(request.message, context)

        # Sauvegarder la session
        session["messages"] = context.messages

        return AgentMessageResponse(
            agent_type=request.agent_type,
            message=response.message,
            suggested_actions=response.suggested_actions,
            questions=response.questions,
            next_stage=response.next_stage,
            requires_input=response.requires_input,
            session_id=session_id,
        )

    except ValueError as e:
        raise HTTPException(
            status_code=503,
            detail=f"LLM not configured: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Agent error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/agent/present-opportunity")
async def present_opportunity(
    asin: str = Body(...),
    opportunity_data: Dict[str, Any] = Body(...),
    thesis: Optional[Dict[str, Any]] = Body(None),
    session_id: Optional[str] = Body(None),
):
    """
    Présente une opportunité via l'agent Discovery.

    Point d'entrée principal pour commencer l'accompagnement.
    """
    try:
        from ..ai.agents import DiscoveryAgent, AgentContext

        session_id, session = get_or_create_session(session_id)

        # Stocker le contexte
        session["context"]["asin"] = asin
        session["context"]["opportunity_data"] = opportunity_data
        session["context"]["thesis"] = thesis

        context = AgentContext(
            asin=asin,
            opportunity_data=opportunity_data,
            thesis=thesis,
            messages=session["messages"],
        )

        # Enrich context with review intelligence + spec bundle
        _enrich_context(context)

        agent = DiscoveryAgent()
        response = await agent.present_opportunity(
            opportunity=opportunity_data,
            thesis=thesis,
            context=context,
        )

        session["messages"] = context.messages

        return {
            "message": response.message,
            "suggested_actions": response.suggested_actions,
            "session_id": session_id,
        }

    except Exception as e:
        logger.error(f"Present opportunity error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# REVIEW ANALYSIS ENDPOINT
# =============================================================================

@router.post("/analyze-reviews", response_model=ReviewAnalysisResponse)
async def analyze_reviews(request: ReviewAnalysisRequest):
    """
    Analyse les reviews Amazon pour détecter les opportunités.

    Extrait :
    - Pain points (problèmes récurrents)
    - Wishes (fonctionnalités demandées)
    - Problèmes de qualité
    - Potentiel de différenciation
    """
    try:
        from ..ai.review_analyzer import ReviewAnalyzer

        analyzer = ReviewAnalyzer()

        result = await analyzer.find_opportunities_in_reviews(
            asin=request.asin,
            reviews=request.reviews,
        )

        return ReviewAnalysisResponse(
            asin=result["asin"],
            reviews_analyzed=result["reviews_analyzed"],
            sentiment=result["sentiment"],
            negative_rate=result["negative_rate"],
            differentiation_score=result["differentiation_score"],
            opportunity_signals=result["opportunity_signals"],
            summary=result["summary"],
            top_pain_points=result["top_pain_points"],
            top_wishes=result["top_wishes"],
        )

    except ValueError as e:
        raise HTTPException(
            status_code=503,
            detail=f"LLM not configured: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Review analysis error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# STATUS ENDPOINT
# =============================================================================

@router.get("/status")
async def ai_status():
    """
    Vérifie le statut des services IA.
    """
    import os
    from dotenv import load_dotenv

    # Charger le .env si pas encore fait
    load_dotenv()

    anthropic_configured = bool(os.getenv("ANTHROPIC_API_KEY"))
    openai_configured = bool(os.getenv("OPENAI_API_KEY") or os.getenv("GPT_API_KEY"))

    return {
        "ai_available": anthropic_configured or openai_configured,
        "providers": {
            "anthropic": "configured" if anthropic_configured else "not_configured",
            "openai": "configured" if openai_configured else "not_configured",
        },
        "active_sessions": len(_agent_sessions),
        "features": {
            "thesis_generation": anthropic_configured or openai_configured,
            "agents": anthropic_configured or openai_configured,
            "review_analysis": anthropic_configured or openai_configured,
        },
    }
