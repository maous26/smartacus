"""
Smartacus Shortlist Generator
=============================

Génère une shortlist CONTRAINTE et ORDONNÉE d'opportunités.

PARADIGME:
- Pas "voici 200 produits intéressants, choisis"
- Mais "voici LES 5 opportunités à exécuter, dans CET ORDRE"

FORMAT DE SORTIE:
    1. B09XXXXX → Score 82 → Fenêtre 30j → $31,000/an
       Thèse: Supply shock détecté, 3 ruptures/mois, marge 42%

    2. B08YYYYY → Score 75 → Fenêtre 60j → $18,500/an
       Thèse: Concurrent effondré, part de marché à prendre

CLASSEMENT:
    rank_score = risk_adjusted_value × urgency_multiplier

L'utilisateur ne choisit pas. La machine recommande.
"""

from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from datetime import datetime
from decimal import Decimal

from ..scoring.economic_scorer import EconomicScorer, EconomicOpportunity


@dataclass
class ShortlistItem:
    """
    Item de la shortlist avec toutes les informations décisionnelles.
    """
    rank: int
    asin: str
    score: int
    window_days: int
    urgency_label: str
    annual_value: Decimal
    risk_adjusted_value: Decimal
    thesis: str
    economic_events: List[str]
    action_recommendation: str

    def to_display_string(self) -> str:
        """Format d'affichage console."""
        return (
            f"{self.rank}. {self.asin} → "
            f"Score {self.score} → "
            f"Fenêtre {self.window_days}j → "
            f"${self.risk_adjusted_value:,.0f}/an\n"
            f"   {self.urgency_label}\n"
            f"   Thèse: {self.thesis}\n"
            f"   Action: {self.action_recommendation}"
        )

    def to_dict(self) -> Dict[str, Any]:
        """Format JSON."""
        return {
            "rank": self.rank,
            "asin": self.asin,
            "score": self.score,
            "window_days": self.window_days,
            "urgency_label": self.urgency_label,
            "annual_value": float(self.annual_value),
            "risk_adjusted_value": float(self.risk_adjusted_value),
            "thesis": self.thesis,
            "economic_events": self.economic_events,
            "action_recommendation": self.action_recommendation,
        }


class ShortlistGenerator:
    """
    Générateur de shortlist contrainte.

    RÈGLES:
    1. Maximum 5 items (concentration > dispersion)
    2. Classés par valeur × urgence
    3. Chaque item a une thèse explicable
    4. Chaque item a une recommandation d'action
    """

    MAX_ITEMS = 5
    MIN_SCORE = 50
    MIN_VALUE = 5000  # $5,000/an minimum

    def __init__(self):
        self.scorer = EconomicScorer()

    def generate(
        self,
        opportunities: List[EconomicOpportunity],
        max_items: Optional[int] = None,
    ) -> List[ShortlistItem]:
        """
        Génère la shortlist contrainte.

        Args:
            opportunities: Liste d'opportunités économiques
            max_items: Nombre max (défaut: 5)

        Returns:
            Shortlist ordonnée et contrainte
        """
        max_items = max_items or self.MAX_ITEMS

        # Filtrer les opportunités non viables
        viable = [
            o for o in opportunities
            if o.final_score >= self.MIN_SCORE
            and float(o.risk_adjusted_value) >= self.MIN_VALUE
        ]

        # Classer par rank_score (valeur × urgence)
        ranked = sorted(viable, key=lambda x: x.rank_score, reverse=True)

        # Construire la shortlist
        shortlist = []
        for i, opp in enumerate(ranked[:max_items], 1):
            item = ShortlistItem(
                rank=i,
                asin=opp.asin,
                score=opp.final_score,
                window_days=opp.window_days,
                urgency_label=opp.urgency_label,
                annual_value=opp.estimated_annual_value,
                risk_adjusted_value=opp.risk_adjusted_value,
                thesis=opp.thesis,
                economic_events=opp.economic_events,
                action_recommendation=self._generate_action(opp),
            )
            shortlist.append(item)

        return shortlist

    def _generate_action(self, opp: EconomicOpportunity) -> str:
        """Génère une recommandation d'action."""
        if opp.window_days <= 14:
            return "ACTION IMMÉDIATE: Sourcer fournisseur cette semaine"
        elif opp.window_days <= 30:
            return "PRIORITAIRE: Lancer analyse fournisseurs sous 7 jours"
        elif opp.window_days <= 60:
            return "ACTIF: Planifier sourcing dans les 2 semaines"
        else:
            return "SURVEILLER: Ajouter au backlog, réévaluer dans 30 jours"

    def print_shortlist(
        self,
        shortlist: List[ShortlistItem],
        show_details: bool = True,
    ) -> str:
        """
        Formate la shortlist pour affichage console.

        Returns:
            String formaté pour print()
        """
        if not shortlist:
            return "Aucune opportunité viable détectée."

        lines = [
            "=" * 70,
            "SHORTLIST SMARTACUS - OPPORTUNITÉS À EXÉCUTER",
            "=" * 70,
            f"Généré le: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
            f"Critères: Score >= {self.MIN_SCORE}, Valeur >= ${self.MIN_VALUE:,}/an",
            "",
        ]

        for item in shortlist:
            lines.append("-" * 70)
            lines.append(item.to_display_string())
            lines.append("")

        lines.append("-" * 70)
        lines.append(f"Total: {len(shortlist)} opportunité(s) recommandée(s)")

        # Résumé valeur totale
        total_value = sum(float(item.risk_adjusted_value) for item in shortlist)
        lines.append(f"Valeur totale potentielle: ${total_value:,.0f}/an")

        return "\n".join(lines)

    def to_json(self, shortlist: List[ShortlistItem]) -> Dict[str, Any]:
        """
        Exporte la shortlist en JSON.
        """
        return {
            "generated_at": datetime.utcnow().isoformat(),
            "criteria": {
                "min_score": self.MIN_SCORE,
                "min_value": self.MIN_VALUE,
                "max_items": self.MAX_ITEMS,
            },
            "count": len(shortlist),
            "total_potential_value": sum(
                float(item.risk_adjusted_value) for item in shortlist
            ),
            "items": [item.to_dict() for item in shortlist],
        }


def cmd_shortlist(args):
    """
    Commande CLI pour afficher la shortlist.

    Usage:
        python -m src.orchestrator.cli shortlist
        python -m src.orchestrator.cli shortlist --json
        python -m src.orchestrator.cli shortlist --max 3
    """
    from ..orchestrator.daily_pipeline import DailyPipeline

    print("=" * 70)
    print("GÉNÉRATION DE LA SHORTLIST SMARTACUS")
    print("=" * 70)

    try:
        with DailyPipeline() as pipeline:
            # Récupérer les opportunités récentes
            raw_opportunities = pipeline.get_active_opportunities(
                min_score=40,
                limit=100,
            )

        if not raw_opportunities:
            print("\nAucune opportunité trouvée dans la base.")
            print("Lancez d'abord: python -m src.orchestrator.cli run")
            return 1

        # Convertir en EconomicOpportunity
        # (Dans une vraie implémentation, les données time seraient aussi chargées)
        scorer = EconomicScorer()
        economic_opps = []

        for raw in raw_opportunities:
            # Simuler les données temporelles (à remplacer par vraies données)
            product_data = {
                "product_id": raw["asin"],
                "amazon_price": 25.0,  # À charger depuis DB
                "alibaba_price": 5.0,
                "bsr_current": 50000,
                "bsr_delta_7d": -0.15,
                "bsr_delta_30d": -0.25,
                "reviews_per_month": 50,
                "seller_count": 8,
                "buybox_rotation": 0.20,
                "review_gap_vs_top10": 0.40,
                "negative_review_percent": 0.12,
                "wish_mentions_per_100": 4,
                "unanswered_questions": 3,
                "stockout_count_90d": 2,
                "price_trend_30d": 0.05,
                "seller_churn_90d": 0.15,
                "bsr_acceleration": 0.05,
            }

            time_data = {
                "stockout_frequency": 0.7,
                "seller_churn_90d": 0.15,
                "price_volatility": 0.08,
                "bsr_acceleration": 0.05,
                "estimated_monthly_units": 150,
            }

            opp = scorer.score_economic(product_data, time_data)
            economic_opps.append(opp)

        # Générer la shortlist
        generator = ShortlistGenerator()
        max_items = getattr(args, 'max', 5)
        shortlist = generator.generate(economic_opps, max_items=max_items)

        # Affichage
        if getattr(args, 'json', False):
            import json
            print(json.dumps(generator.to_json(shortlist), indent=2))
        else:
            print(generator.print_shortlist(shortlist))

        return 0

    except Exception as e:
        print(f"\nERREUR: {e}")
        import traceback
        traceback.print_exc()
        return 1
