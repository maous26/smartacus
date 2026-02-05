"""
Smartacus Review Analyzer
=========================

Analyse des reviews Amazon pour détecter :
- Pain points des clients (opportunités d'amélioration)
- Fonctionnalités souhaitées ("I wish it had...")
- Problèmes de qualité récurrents
- Avantages concurrentiels potentiels

Les reviews sont une mine d'or d'insights économiques.
Un produit avec beaucoup de "I wish..." = opportunité de différenciation.
"""

import logging
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from enum import Enum

from .llm_client import get_llm_client, LLMClient

logger = logging.getLogger(__name__)


class InsightType(Enum):
    """Types d'insights extraits des reviews."""
    PAIN_POINT = "pain_point"           # Problème récurrent
    WISH = "wish"                        # Fonctionnalité souhaitée
    QUALITY_ISSUE = "quality_issue"      # Problème de qualité
    PRAISE = "praise"                    # Point fort apprécié
    COMPARISON = "comparison"            # Comparaison avec concurrent
    USE_CASE = "use_case"                # Cas d'usage mentionné


class SentimentLevel(Enum):
    """Niveau de sentiment."""
    VERY_NEGATIVE = "very_negative"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    POSITIVE = "positive"
    VERY_POSITIVE = "very_positive"


@dataclass
class ReviewInsight:
    """Un insight extrait d'une review."""
    type: InsightType
    content: str
    frequency: int = 1  # Nombre de mentions
    importance: float = 0.5  # 0-1, importance économique
    actionable: bool = True
    source_quotes: List[str] = field(default_factory=list)


@dataclass
class ReviewAnalysis:
    """Analyse complète des reviews d'un produit."""
    asin: str
    total_reviews_analyzed: int
    average_sentiment: SentimentLevel

    # Insights catégorisés
    pain_points: List[ReviewInsight] = field(default_factory=list)
    wishes: List[ReviewInsight] = field(default_factory=list)
    quality_issues: List[ReviewInsight] = field(default_factory=list)
    praises: List[ReviewInsight] = field(default_factory=list)

    # Métriques
    negative_rate: float = 0.0  # % de reviews négatives
    mention_competitors: List[str] = field(default_factory=list)

    # Opportunité
    differentiation_score: float = 0.0  # 0-1, potentiel de différenciation
    opportunity_summary: str = ""

    # Coût LLM
    tokens_used: int = 0
    cost_usd: float = 0.0


REVIEW_ANALYSIS_SYSTEM = """Tu es un analyste spécialisé dans l'extraction d'insights business depuis les reviews Amazon.

TON OBJECTIF :
Identifier les opportunités économiques cachées dans les reviews :
- Pain points = produit améliorable = opportunité
- "I wish" = demande non satisfaite = opportunité
- Problèmes qualité récurrents = différenciation possible
- Comparaisons négatives = avantage compétitif potentiel

TU DOIS :
1. Extraire les thèmes récurrents (pas les cas isolés)
2. Quantifier la fréquence relative
3. Évaluer l'importance économique (impact sur achat)
4. Identifier ce qui est actionnable

FORMAT : JSON structuré avec insights catégorisés."""


REVIEW_ANALYSIS_PROMPT = """Analyse ces reviews Amazon et extrais les insights business.

## Produit
ASIN: {asin}
Titre: {title}

## Reviews à analyser
{reviews_text}

---

Extrais les insights au format JSON :

{{
  "sentiment_distribution": {{
    "very_negative": 0.05,
    "negative": 0.15,
    "neutral": 0.20,
    "positive": 0.40,
    "very_positive": 0.20
  }},
  "pain_points": [
    {{
      "issue": "Description du problème",
      "frequency": "high|medium|low",
      "importance": 0.8,
      "quotes": ["Citation 1", "Citation 2"],
      "actionable": true
    }}
  ],
  "wishes": [
    {{
      "feature": "Fonctionnalité souhaitée",
      "frequency": "high|medium|low",
      "importance": 0.7,
      "quotes": ["I wish it had..."],
      "market_gap": true
    }}
  ],
  "quality_issues": [
    {{
      "issue": "Problème de qualité",
      "frequency": "high|medium|low",
      "severity": "critical|major|minor"
    }}
  ],
  "praises": [
    {{
      "feature": "Point fort",
      "frequency": "high|medium|low"
    }}
  ],
  "competitors_mentioned": ["Concurrent 1", "Concurrent 2"],
  "differentiation_opportunity": {{
    "score": 0.75,
    "summary": "Résumé de l'opportunité de différenciation",
    "key_improvements": ["Amélioration 1", "Amélioration 2"]
  }}
}}"""


class ReviewAnalyzer:
    """
    Analyseur de reviews Amazon.

    Utilise le LLM pour extraire des insights économiques
    depuis les reviews clients.
    """

    def __init__(self, llm_client: Optional[LLMClient] = None):
        self._llm_client = llm_client
        self._total_cost = 0.0

    @property
    def llm_client(self) -> LLMClient:
        if self._llm_client is None:
            self._llm_client = get_llm_client()
        return self._llm_client

    def _format_reviews(self, reviews: List[Dict[str, Any]], max_reviews: int = 50) -> str:
        """Formate les reviews pour le prompt."""
        formatted = []
        for i, review in enumerate(reviews[:max_reviews], 1):
            rating = review.get('rating', 'N/A')
            title = review.get('title', '')
            body = review.get('body', review.get('text', ''))[:500]  # Limite la longueur
            formatted.append(f"[{i}] ★{rating} - {title}\n{body}")
        return "\n\n".join(formatted)

    async def analyze_reviews(
        self,
        asin: str,
        reviews: List[Dict[str, Any]],
        product_title: str = "",
    ) -> ReviewAnalysis:
        """
        Analyse un ensemble de reviews.

        Args:
            asin: ASIN du produit
            reviews: Liste de reviews (avec rating, title, body/text)
            product_title: Titre du produit

        Returns:
            ReviewAnalysis avec tous les insights
        """
        if not reviews:
            return ReviewAnalysis(
                asin=asin,
                total_reviews_analyzed=0,
                average_sentiment=SentimentLevel.NEUTRAL,
                opportunity_summary="Pas de reviews à analyser",
            )

        reviews_text = self._format_reviews(reviews)

        prompt = REVIEW_ANALYSIS_PROMPT.format(
            asin=asin,
            title=product_title,
            reviews_text=reviews_text,
        )

        try:
            result = await self.llm_client.generate_json(
                prompt=prompt,
                system=REVIEW_ANALYSIS_SYSTEM,
            )

            # Parser les résultats
            sentiment_dist = result.get('sentiment_distribution', {})

            # Calculer le sentiment moyen
            sentiment_weights = {
                'very_negative': -2,
                'negative': -1,
                'neutral': 0,
                'positive': 1,
                'very_positive': 2,
            }
            weighted_sum = sum(
                sentiment_dist.get(k, 0) * v
                for k, v in sentiment_weights.items()
            )

            if weighted_sum < -0.5:
                avg_sentiment = SentimentLevel.NEGATIVE
            elif weighted_sum < 0.5:
                avg_sentiment = SentimentLevel.NEUTRAL
            else:
                avg_sentiment = SentimentLevel.POSITIVE

            # Construire les insights
            pain_points = [
                ReviewInsight(
                    type=InsightType.PAIN_POINT,
                    content=pp.get('issue', ''),
                    frequency=self._freq_to_int(pp.get('frequency', 'low')),
                    importance=pp.get('importance', 0.5),
                    actionable=pp.get('actionable', True),
                    source_quotes=pp.get('quotes', []),
                )
                for pp in result.get('pain_points', [])
            ]

            wishes = [
                ReviewInsight(
                    type=InsightType.WISH,
                    content=w.get('feature', ''),
                    frequency=self._freq_to_int(w.get('frequency', 'low')),
                    importance=w.get('importance', 0.5),
                    actionable=w.get('market_gap', True),
                    source_quotes=w.get('quotes', []),
                )
                for w in result.get('wishes', [])
            ]

            quality_issues = [
                ReviewInsight(
                    type=InsightType.QUALITY_ISSUE,
                    content=qi.get('issue', ''),
                    frequency=self._freq_to_int(qi.get('frequency', 'low')),
                    importance=0.9 if qi.get('severity') == 'critical' else 0.6,
                )
                for qi in result.get('quality_issues', [])
            ]

            praises = [
                ReviewInsight(
                    type=InsightType.PRAISE,
                    content=p.get('feature', ''),
                    frequency=self._freq_to_int(p.get('frequency', 'low')),
                )
                for p in result.get('praises', [])
            ]

            diff_opp = result.get('differentiation_opportunity', {})

            # Estimer le coût
            estimated_cost = 0.003  # ~$0.003 par analyse

            analysis = ReviewAnalysis(
                asin=asin,
                total_reviews_analyzed=len(reviews),
                average_sentiment=avg_sentiment,
                pain_points=pain_points,
                wishes=wishes,
                quality_issues=quality_issues,
                praises=praises,
                negative_rate=sentiment_dist.get('negative', 0) + sentiment_dist.get('very_negative', 0),
                mention_competitors=result.get('competitors_mentioned', []),
                differentiation_score=diff_opp.get('score', 0),
                opportunity_summary=diff_opp.get('summary', ''),
                cost_usd=estimated_cost,
            )

            self._total_cost += estimated_cost
            logger.info(f"Analyzed {len(reviews)} reviews for {asin}")

            return analysis

        except Exception as e:
            logger.error(f"Review analysis failed for {asin}: {e}")
            return ReviewAnalysis(
                asin=asin,
                total_reviews_analyzed=len(reviews),
                average_sentiment=SentimentLevel.NEUTRAL,
                opportunity_summary=f"Erreur d'analyse: {str(e)}",
            )

    def _freq_to_int(self, freq: str) -> int:
        """Convertit la fréquence textuelle en nombre."""
        mapping = {'high': 10, 'medium': 5, 'low': 2}
        return mapping.get(freq.lower(), 1)

    async def find_opportunities_in_reviews(
        self,
        asin: str,
        reviews: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Identifie directement les opportunités depuis les reviews.

        Retourne un résumé actionnable.
        """
        analysis = await self.analyze_reviews(asin, reviews)

        # Calculer un score d'opportunité
        opportunity_signals = []

        # Pain points fréquents = forte opportunité
        high_freq_pains = [p for p in analysis.pain_points if p.frequency >= 5]
        if high_freq_pains:
            opportunity_signals.append({
                "signal": "Problèmes récurrents identifiés",
                "count": len(high_freq_pains),
                "examples": [p.content for p in high_freq_pains[:3]],
                "action": "Résoudre ces problèmes = différenciation forte",
            })

        # Wishes = demande explicite
        if analysis.wishes:
            opportunity_signals.append({
                "signal": "Fonctionnalités demandées par clients",
                "count": len(analysis.wishes),
                "examples": [w.content for w in analysis.wishes[:3]],
                "action": "Ajouter ces features = USP claire",
            })

        # Problèmes qualité = facile à battre
        if analysis.quality_issues:
            opportunity_signals.append({
                "signal": "Problèmes de qualité signalés",
                "count": len(analysis.quality_issues),
                "action": "Garantir meilleure qualité = confiance client",
            })

        return {
            "asin": asin,
            "reviews_analyzed": analysis.total_reviews_analyzed,
            "sentiment": analysis.average_sentiment.value,
            "negative_rate": f"{analysis.negative_rate * 100:.1f}%",
            "differentiation_score": analysis.differentiation_score,
            "opportunity_signals": opportunity_signals,
            "summary": analysis.opportunity_summary,
            "top_pain_points": [p.content for p in analysis.pain_points[:5]],
            "top_wishes": [w.content for w in analysis.wishes[:5]],
            "competitors": analysis.mention_competitors,
        }

    @property
    def total_cost(self) -> float:
        return self._total_cost
