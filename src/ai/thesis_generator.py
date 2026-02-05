"""
Smartacus Thesis Generator
==========================

Génère des thèses économiques argumentées pour chaque opportunité.

Le LLM ne fait PAS le scoring (déterministe).
Le LLM GÉNÈRE LA THÈSE : pourquoi cette opportunité existe,
quel est le raisonnement économique, et quelle est la recommandation d'action.

Architecture :
    Data → Events → Scoring déterministe → [LLM] Thèse → Agents

La thèse est le "jugement économique" qui manque à Jungle Scout / Helium 10.
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from datetime import datetime
from enum import Enum

from .llm_client import get_llm_client, LLMClient, LLMResponse

logger = logging.getLogger(__name__)


class ThesisConfidence(Enum):
    """Niveau de confiance de la thèse."""
    STRONG = "strong"
    MODERATE = "moderate"
    WEAK = "weak"
    SPECULATIVE = "speculative"


class ActionUrgency(Enum):
    """Urgence de l'action recommandée."""
    IMMEDIATE = "immediate"      # < 7 jours
    PRIORITY = "priority"        # 7-14 jours
    ACTIVE = "active"            # 14-30 jours
    MONITOR = "monitor"          # 30-60 jours
    BACKLOG = "backlog"          # > 60 jours


@dataclass
class EconomicThesis:
    """
    Thèse économique générée par le LLM.

    C'est le cœur de la valeur ajoutée de Smartacus :
    pas juste des stats, mais un JUGEMENT ÉCONOMIQUE ARGUMENTÉ.
    """
    # Identification
    asin: str
    generated_at: datetime = field(default_factory=datetime.utcnow)

    # La thèse elle-même
    headline: str = ""  # Titre accrocheur (1 ligne)
    thesis: str = ""    # Thèse complète argumentée (2-3 paragraphes)
    reasoning: List[str] = field(default_factory=list)  # Points clés du raisonnement

    # Qualification
    confidence: ThesisConfidence = ThesisConfidence.MODERATE
    confidence_factors: List[str] = field(default_factory=list)

    # Recommandation
    action: str = ""    # Action recommandée
    urgency: ActionUrgency = ActionUrgency.MONITOR
    next_steps: List[str] = field(default_factory=list)

    # Risques identifiés
    risks: List[str] = field(default_factory=list)
    mitigations: List[str] = field(default_factory=list)

    # Estimation économique (validée par LLM)
    estimated_margin_percent: Optional[float] = None
    estimated_monthly_units: Optional[int] = None
    estimated_monthly_profit: Optional[float] = None
    breakeven_units: Optional[int] = None

    # Metadata
    model_used: str = ""
    tokens_used: int = 0
    cost_usd: float = 0.0


THESIS_SYSTEM_PROMPT = """Tu es un analyste économique spécialisé dans l'arbitrage Amazon FBA.
Tu génères des thèses d'investissement pour des opportunités de produits.

Ton rôle :
1. Analyser les données de marché fournies
2. Identifier les dynamiques économiques sous-jacentes
3. Formuler une thèse d'investissement claire et argumentée
4. Recommander une action concrète avec niveau d'urgence

Tu dois être :
- Analytique : chaque affirmation doit être justifiée par les données
- Pragmatique : focus sur l'actionnable, pas la théorie
- Honnête : explicite sur les incertitudes et risques
- Concis : va droit au but, pas de fluff

Tu analyses des opportunités de vente sur Amazon pour des micro-entrepreneurs.
Budget moyen : 5-20k$ de stock initial.
Objectif : 20-40% de marge nette après tous frais."""


THESIS_PROMPT_TEMPLATE = """Analyse cette opportunité Amazon et génère une thèse économique.

## Données Produit

**ASIN**: {asin}
**Titre**: {title}
**Marque**: {brand}
**Catégorie**: {category}

## Métriques Actuelles

- Prix Amazon: ${amazon_price}
- BSR (Best Seller Rank): {bsr}
- Rating: {rating}/5 ({review_count} avis)
- Nombre de vendeurs: {seller_count}

## Signaux Détectés

{signals}

## Score Déterministe

- Score final: {final_score}/100
- Fenêtre temporelle: {window_days} jours
- Niveau d'urgence: {urgency_level}

## Événements Économiques Identifiés

{economic_events}

## Estimations Préliminaires

- Prix d'achat estimé (Alibaba): ${alibaba_price}
- Marge brute estimée: {gross_margin}%
- Volume mensuel estimé: {monthly_units} unités

---

Génère une thèse économique complète au format JSON suivant :

{{
  "headline": "Titre accrocheur de la thèse (max 100 caractères)",
  "thesis": "Thèse argumentée en 2-3 paragraphes. Explique POURQUOI cette opportunité existe économiquement.",
  "reasoning": ["Point clé 1", "Point clé 2", "Point clé 3"],
  "confidence": "strong|moderate|weak|speculative",
  "confidence_factors": ["Facteur positif 1", "Facteur négatif 1"],
  "action": "Action recommandée concrète",
  "urgency": "immediate|priority|active|monitor|backlog",
  "next_steps": ["Étape 1", "Étape 2", "Étape 3"],
  "risks": ["Risque 1", "Risque 2"],
  "mitigations": ["Mitigation 1", "Mitigation 2"],
  "estimated_margin_percent": 25.0,
  "estimated_monthly_units": 150,
  "estimated_monthly_profit": 1500.0,
  "breakeven_units": 50
}}"""


class ThesisGenerator:
    """
    Générateur de thèses économiques.

    Utilise le LLM pour transformer les données brutes et le score
    déterministe en une thèse économique argumentée.
    """

    def __init__(self, llm_client: Optional[LLMClient] = None):
        """
        Args:
            llm_client: Client LLM (auto-détecté si non fourni)
        """
        self._llm_client = llm_client
        self._total_cost = 0.0
        self._total_tokens = 0

    @property
    def llm_client(self) -> LLMClient:
        """Lazy init du client LLM."""
        if self._llm_client is None:
            self._llm_client = get_llm_client()
        return self._llm_client

    def _format_signals(self, signals: List[Dict[str, Any]]) -> str:
        """Formate les signaux pour le prompt."""
        if not signals:
            return "Aucun signal particulier détecté."

        lines = []
        for sig in signals:
            lines.append(f"- **{sig.get('type', 'Unknown')}**: {sig.get('description', '')}")
            if sig.get('value'):
                lines.append(f"  Valeur: {sig['value']}")
        return "\n".join(lines)

    def _format_events(self, events: List[Dict[str, Any]]) -> str:
        """Formate les événements économiques pour le prompt."""
        if not events:
            return "Aucun événement économique majeur."

        lines = []
        for event in events:
            event_type = event.get('event_type', 'UNKNOWN')
            thesis = event.get('thesis', '')
            confidence = event.get('confidence', 'moderate')
            lines.append(f"- **{event_type}** [{confidence}]: {thesis}")
        return "\n".join(lines)

    async def generate_thesis(
        self,
        opportunity_data: Dict[str, Any],
        score_data: Dict[str, Any],
        events: Optional[List[Dict[str, Any]]] = None,
        signals: Optional[List[Dict[str, Any]]] = None,
    ) -> EconomicThesis:
        """
        Génère une thèse économique pour une opportunité.

        Args:
            opportunity_data: Données du produit (asin, title, price, etc.)
            score_data: Résultat du scoring déterministe
            events: Événements économiques détectés
            signals: Signaux de marché

        Returns:
            EconomicThesis avec la thèse complète
        """
        asin = opportunity_data.get("asin", "UNKNOWN")

        # Construire le prompt
        prompt = THESIS_PROMPT_TEMPLATE.format(
            asin=asin,
            title=opportunity_data.get("title", "Unknown Product"),
            brand=opportunity_data.get("brand", "Unknown"),
            category=opportunity_data.get("category", "Unknown"),
            amazon_price=opportunity_data.get("amazon_price", 0),
            bsr=opportunity_data.get("bsr", "N/A"),
            rating=opportunity_data.get("rating", "N/A"),
            review_count=opportunity_data.get("review_count", 0),
            seller_count=opportunity_data.get("seller_count", "N/A"),
            signals=self._format_signals(signals or []),
            final_score=score_data.get("final_score", 0),
            window_days=score_data.get("window_days", 90),
            urgency_level=score_data.get("urgency_level", "standard"),
            economic_events=self._format_events(events or []),
            alibaba_price=opportunity_data.get("alibaba_price", opportunity_data.get("amazon_price", 0) / 5),
            gross_margin=score_data.get("gross_margin_percent", 30),
            monthly_units=score_data.get("estimated_monthly_units", 100),
        )

        try:
            # Appeler le LLM
            result = await self.llm_client.generate_json(
                prompt=prompt,
                system=THESIS_SYSTEM_PROMPT,
            )

            # Tracker les coûts
            # Note: generate_json ne retourne pas directement les tokens
            # On estime ~500 tokens input, ~800 output pour ce type de prompt
            estimated_cost = 0.005  # ~$0.005 par thèse avec Claude Sonnet

            # Construire la thèse
            thesis = EconomicThesis(
                asin=asin,
                headline=result.get("headline", ""),
                thesis=result.get("thesis", ""),
                reasoning=result.get("reasoning", []),
                confidence=ThesisConfidence(result.get("confidence", "moderate")),
                confidence_factors=result.get("confidence_factors", []),
                action=result.get("action", ""),
                urgency=ActionUrgency(result.get("urgency", "monitor")),
                next_steps=result.get("next_steps", []),
                risks=result.get("risks", []),
                mitigations=result.get("mitigations", []),
                estimated_margin_percent=result.get("estimated_margin_percent"),
                estimated_monthly_units=result.get("estimated_monthly_units"),
                estimated_monthly_profit=result.get("estimated_monthly_profit"),
                breakeven_units=result.get("breakeven_units"),
                model_used=self.llm_client.model if hasattr(self.llm_client, 'model') else "unknown",
                cost_usd=estimated_cost,
            )

            self._total_cost += estimated_cost
            logger.info(f"Thesis generated for {asin}: {thesis.headline}")

            return thesis

        except Exception as e:
            logger.error(f"Failed to generate thesis for {asin}: {e}")
            # Retourner une thèse par défaut
            return EconomicThesis(
                asin=asin,
                headline="Analyse non disponible",
                thesis=f"Erreur lors de la génération de la thèse: {str(e)}",
                confidence=ThesisConfidence.SPECULATIVE,
            )

    async def generate_batch(
        self,
        opportunities: List[Dict[str, Any]],
        max_concurrent: int = 3,
    ) -> List[EconomicThesis]:
        """
        Génère des thèses pour plusieurs opportunités.

        Args:
            opportunities: Liste de {opportunity_data, score_data, events, signals}
            max_concurrent: Nombre max d'appels LLM simultanés

        Returns:
            Liste de EconomicThesis
        """
        import asyncio

        semaphore = asyncio.Semaphore(max_concurrent)

        async def generate_with_limit(opp):
            async with semaphore:
                return await self.generate_thesis(
                    opportunity_data=opp.get("opportunity_data", {}),
                    score_data=opp.get("score_data", {}),
                    events=opp.get("events"),
                    signals=opp.get("signals"),
                )

        tasks = [generate_with_limit(opp) for opp in opportunities]
        return await asyncio.gather(*tasks)

    @property
    def total_cost(self) -> float:
        """Coût total des appels LLM."""
        return self._total_cost

    @property
    def total_tokens(self) -> int:
        """Tokens totaux utilisés."""
        return self._total_tokens
