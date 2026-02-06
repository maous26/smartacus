"""
Smartacus Economic Scorer
=========================

Scoring économique avec intégration du COÛT DU TEMPS.

DIFFÉRENCE AVEC opportunity_scorer.py:
- opportunity_scorer: score = composantes additives (margin + velocity + ...)
- economic_scorer: score = base_score × time_multiplier × value_estimate

PHILOSOPHIE:
Le temps n'est pas une composante parmi d'autres.
Le temps est le MULTIPLICATEUR de toute opportunité.

Un produit à 80/100 avec fenêtre de 14 jours > produit à 90/100 avec fenêtre de 180 jours.

FORMULE FINALE:
    economic_value = base_score × time_multiplier × estimated_monthly_profit

Où:
    - base_score = (margin + velocity + competition + gap) / 90  [0-1]
    - time_multiplier = f(urgency, window_days, erosion_rate)   [0.5-2.0]
    - estimated_monthly_profit = (amazon_price - total_cost) × estimated_units

OUTPUT:
    - Score final [0-100]
    - Valeur économique estimée [$]
    - Classement par value × time
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum
from decimal import Decimal
import math

from .opportunity_scorer import OpportunityScorer, ScoringResult, ComponentScore


class TimeWindow(Enum):
    """Classification de la fenêtre temporelle."""
    CRITICAL = "critical"     # < 14 jours - AGIR MAINTENANT
    URGENT = "urgent"         # 14-30 jours - Action prioritaire
    ACTIVE = "active"         # 30-60 jours - Fenêtre viable
    STANDARD = "standard"     # 60-90 jours - Temps confortable
    EXTENDED = "extended"     # > 90 jours - Pas d'urgence


@dataclass
class TimeMultiplierResult:
    """
    Résultat du calcul du multiplicateur temporel.
    """
    multiplier: float           # [0.5 - 2.0]
    window: TimeWindow
    window_days: int
    erosion_rate: float         # Vitesse d'érosion de l'opportunité [0-1]
    confidence: float           # Confiance dans l'estimation [0-1]
    factors: Dict[str, float] = field(default_factory=dict)

    @property
    def urgency_label(self) -> str:
        """Label humain pour l'urgence."""
        labels = {
            TimeWindow.CRITICAL: "🔴 CRITIQUE - Agir immédiatement",
            TimeWindow.URGENT: "🟠 URGENT - Action prioritaire",
            TimeWindow.ACTIVE: "🟡 ACTIF - Fenêtre viable",
            TimeWindow.STANDARD: "🟢 STANDARD - Temps disponible",
            TimeWindow.EXTENDED: "⚪ ÉTENDU - Pas d'urgence",
        }
        return labels.get(self.window, "Inconnu")


@dataclass
class EconomicOpportunity:
    """
    Opportunité économique avec valeur et ranking.
    """
    asin: str
    # Scores
    base_score: float           # Score de base [0-1]
    time_multiplier: float      # Multiplicateur temporel [0.5-2.0]
    final_score: int            # Score final [0-100]
    # Valeur économique
    estimated_monthly_profit: Decimal
    estimated_annual_value: Decimal
    risk_adjusted_value: Decimal
    # Fenêtre
    window: TimeWindow
    window_days: int
    urgency_label: str
    # Détails
    thesis: str                 # Thèse économique
    component_scores: Dict[str, ComponentScore] = field(default_factory=dict)
    economic_events: List[str] = field(default_factory=list)
    # Ranking
    rank_score: float = 0.0     # Score de ranking = value × urgency

    def to_dict(self) -> Dict[str, Any]:
        """Convertir en dictionnaire."""
        return {
            "asin": self.asin,
            "final_score": self.final_score,
            "base_score": round(self.base_score, 3),
            "time_multiplier": round(self.time_multiplier, 2),
            "estimated_monthly_profit": float(self.estimated_monthly_profit),
            "estimated_annual_value": float(self.estimated_annual_value),
            "risk_adjusted_value": float(self.risk_adjusted_value),
            "window": self.window.value,
            "window_days": self.window_days,
            "urgency_label": self.urgency_label,
            "thesis": self.thesis,
            "rank_score": round(self.rank_score, 2),
            "economic_events": self.economic_events,
        }


class EconomicScorer:
    """
    Scorer économique intégrant le coût du temps.

    DIFFÉRENCE CLÉ:
    - Le temps n'est pas une composante additive
    - Le temps est un MULTIPLICATEUR qui amplifie ou réduit la valeur

    FORMULE:
        final_score = base_score × time_multiplier × 100

    Où:
        base_score = (margin + velocity + competition + gap) / 90
        time_multiplier = f(stockout_freq, seller_churn, price_volatility, bsr_accel)
    """

    # Multiplicateurs temporels par fenêtre
    TIME_MULTIPLIERS = {
        TimeWindow.CRITICAL: 2.0,    # Double la valeur perçue
        TimeWindow.URGENT: 1.5,      # +50%
        TimeWindow.ACTIVE: 1.2,      # +20%
        TimeWindow.STANDARD: 1.0,    # Base
        TimeWindow.EXTENDED: 0.7,    # -30%
    }

    def __init__(self):
        """Initialise le scorer économique."""
        self.base_scorer = OpportunityScorer()

    def calculate_time_multiplier(
        self,
        stockout_frequency: float,      # Ruptures par mois
        seller_churn: float,            # Taux de churn 90j [0-1]
        price_volatility: float,        # Coefficient de variation prix
        bsr_acceleration: float,        # Accélération BSR (2nd dérivée)
    ) -> TimeMultiplierResult:
        """
        Calcule le multiplicateur temporel basé sur les dynamiques de marché.

        Le multiplicateur capture:
        - Vitesse d'érosion de l'opportunité
        - Urgence d'action
        - Risque de fenêtre qui se ferme

        Returns:
            TimeMultiplierResult avec le multiplicateur [0.5-2.0]
        """
        factors = {}

        # === FACTEUR 1: Fréquence des ruptures ===
        # Plus de ruptures = demande forte = fenêtre courte
        if stockout_frequency >= 3:  # 3+ ruptures/mois
            stockout_factor = 1.5
            factors["stockouts"] = "Très fréquentes (+50%)"
        elif stockout_frequency >= 1:
            stockout_factor = 1.2
            factors["stockouts"] = "Fréquentes (+20%)"
        elif stockout_frequency >= 0.5:
            stockout_factor = 1.0
            factors["stockouts"] = "Occasionnelles (neutre)"
        else:
            stockout_factor = 0.8
            factors["stockouts"] = "Rares (-20%)"

        # === FACTEUR 2: Churn des vendeurs ===
        # Churn élevé = place qui se libère = fenêtre qui s'ouvre
        if seller_churn > 0.30:
            churn_factor = 1.4
            factors["seller_churn"] = "Élevé (+40%)"
        elif seller_churn > 0.20:
            churn_factor = 1.2
            factors["seller_churn"] = "Modéré (+20%)"
        elif seller_churn > 0.10:
            churn_factor = 1.0
            factors["seller_churn"] = "Normal (neutre)"
        else:
            churn_factor = 0.8
            factors["seller_churn"] = "Faible (-20%)"

        # === FACTEUR 3: Volatilité des prix ===
        # Prix volatils = marché instable = agir vite
        if price_volatility > 0.20:
            volatility_factor = 1.3
            factors["price_volatility"] = "Haute (+30%)"
        elif price_volatility > 0.10:
            volatility_factor = 1.1
            factors["price_volatility"] = "Modérée (+10%)"
        else:
            volatility_factor = 1.0
            factors["price_volatility"] = "Stable (neutre)"

        # === FACTEUR 4: Accélération BSR ===
        # BSR qui accélère = momentum = fenêtre qui rétrécit
        if bsr_acceleration > 0.10:  # Amélioration qui s'accélère
            bsr_factor = 1.4
            factors["bsr_acceleration"] = "Forte accélération (+40%)"
        elif bsr_acceleration > 0:
            bsr_factor = 1.2
            factors["bsr_acceleration"] = "Accélération (+20%)"
        elif bsr_acceleration > -0.05:
            bsr_factor = 1.0
            factors["bsr_acceleration"] = "Stable (neutre)"
        else:
            bsr_factor = 0.8
            factors["bsr_acceleration"] = "Décélération (-20%)"

        # === CALCUL DU MULTIPLICATEUR COMPOSITE ===
        # Moyenne géométrique pour éviter les extrêmes
        raw_multiplier = (
            stockout_factor *
            churn_factor *
            volatility_factor *
            bsr_factor
        ) ** 0.25  # Racine 4ème = moyenne géométrique

        # Clamp entre 0.5 et 2.0
        multiplier = max(0.5, min(2.0, raw_multiplier))

        # === DÉTERMINER LA FENÊTRE ===
        if multiplier >= 1.8:
            window = TimeWindow.CRITICAL
            window_days = 14
        elif multiplier >= 1.4:
            window = TimeWindow.URGENT
            window_days = 30
        elif multiplier >= 1.1:
            window = TimeWindow.ACTIVE
            window_days = 60
        elif multiplier >= 0.9:
            window = TimeWindow.STANDARD
            window_days = 90
        else:
            window = TimeWindow.EXTENDED
            window_days = 180

        # Calculer le taux d'érosion
        erosion_rate = (multiplier - 0.5) / 1.5  # Normaliser [0-1]

        # Confiance basée sur le nombre de signaux forts
        strong_signals = sum(1 for f in [
            stockout_factor, churn_factor, volatility_factor, bsr_factor
        ] if f >= 1.2)
        confidence = 0.5 + (strong_signals * 0.125)  # 0.5 - 1.0

        return TimeMultiplierResult(
            multiplier=multiplier,
            window=window,
            window_days=window_days,
            erosion_rate=erosion_rate,
            confidence=confidence,
            factors=factors,
        )

    def get_best_quote_cogs(self, asin: str) -> Optional[Tuple[float, float]]:
        """
        Get best COGS from sourcing_quotes table if available.

        Returns:
            (unit_price_usd, shipping_cost_usd) or None if no valid quote
        """
        try:
            import os
            import psycopg2

            conn = psycopg2.connect(
                host=os.getenv("DATABASE_HOST", "localhost"),
                port=int(os.getenv("DATABASE_PORT", "5432")),
                dbname=os.getenv("DATABASE_NAME", "smartacus"),
                user=os.getenv("DATABASE_USER", "postgres"),
                password=os.getenv("DATABASE_PASSWORD", ""),
                sslmode=os.getenv("DATABASE_SSL_MODE", "prefer"),
                connect_timeout=5,
            )
            try:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT unit_price_usd, shipping_cost_usd
                        FROM sourcing_quotes
                        WHERE asin = %s
                          AND is_active = true
                          AND (valid_until IS NULL OR valid_until > NOW())
                          AND unit_price_usd IS NOT NULL
                        ORDER BY unit_price_usd ASC
                        LIMIT 1
                    """, (asin,))
                    row = cur.fetchone()
                    if row:
                        unit_price = float(row[0]) if row[0] else None
                        shipping = float(row[1]) if row[1] else 0.0
                        if unit_price:
                            return (unit_price, shipping)
            finally:
                conn.close()
        except Exception:
            pass  # Silently fallback to heuristic
        return None

    def estimate_economic_value(
        self,
        amazon_price: float,
        estimated_cogs: float,
        estimated_monthly_units: int,
        risk_factor: float = 0.3,  # 30% de réduction pour risque
        asin: Optional[str] = None,  # V2.0: optional ASIN to lookup real quotes
    ) -> Tuple[Decimal, Decimal, Decimal]:
        """
        Estime la valeur économique de l'opportunité.

        V2.0 Enhancement: If asin is provided, attempts to use real sourcing quotes
        from the database instead of the heuristic estimated_cogs.

        Returns:
            (monthly_profit, annual_value, risk_adjusted_value)
        """
        # V2.0: Try to get real COGS from sourcing_quotes
        actual_cogs = estimated_cogs
        if asin:
            quote_data = self.get_best_quote_cogs(asin)
            if quote_data:
                actual_cogs = quote_data[0] + quote_data[1]  # unit_price + shipping

        # Coûts complets
        fba_fees = max(amazon_price * 0.15, 3.0)
        referral = amazon_price * 0.15
        ppc_provision = amazon_price * 0.10
        return_provision = amazon_price * 0.05

        total_cost_per_unit = (
            actual_cogs +
            fba_fees +
            referral +
            ppc_provision +
            return_provision
        )

        profit_per_unit = amazon_price - total_cost_per_unit
        monthly_profit = Decimal(str(max(0, profit_per_unit * estimated_monthly_units)))
        annual_value = monthly_profit * 12

        # Ajustement risque
        risk_adjusted = annual_value * Decimal(str(1 - risk_factor))

        return monthly_profit, annual_value, risk_adjusted

    def score_economic(
        self,
        product_data: Dict[str, Any],
        time_data: Dict[str, Any],
        economic_events: List[str] = None,
    ) -> EconomicOpportunity:
        """
        Score économique complet avec coût du temps.

        Args:
            product_data: Données produit pour le scoring de base
            time_data: Données temporelles:
                - stockout_frequency: float (ruptures/mois)
                - seller_churn_90d: float [0-1]
                - price_volatility: float
                - bsr_acceleration: float
                - estimated_monthly_units: int
            economic_events: Liste d'événements économiques détectés

        Returns:
            EconomicOpportunity avec score, valeur et ranking
        """
        asin = product_data.get("product_id", "UNKNOWN")

        # === 1. SCORE DE BASE ===
        base_result = self.base_scorer.score(product_data)

        # Extraire les composantes principales (sans time_pressure, géré différemment)
        base_components_score = (
            base_result.component_scores.get("margin", ComponentScore("margin", 0, 30)).score +
            base_result.component_scores.get("velocity", ComponentScore("velocity", 0, 25)).score +
            base_result.component_scores.get("competition", ComponentScore("competition", 0, 20)).score +
            base_result.component_scores.get("gap", ComponentScore("gap", 0, 15)).score
        )
        base_score = base_components_score / 90  # Normaliser [0-1]

        # === 2. MULTIPLICATEUR TEMPOREL ===
        time_result = self.calculate_time_multiplier(
            stockout_frequency=time_data.get("stockout_frequency", 0),
            seller_churn=time_data.get("seller_churn_90d", 0),
            price_volatility=time_data.get("price_volatility", 0),
            bsr_acceleration=time_data.get("bsr_acceleration", 0),
        )

        # === 3. SCORE FINAL ===
        # Score = base × multiplier, plafonné à 100
        final_score = int(min(100, base_score * time_result.multiplier * 100))

        # === 4. VALEUR ÉCONOMIQUE ===
        amazon_price = product_data.get("amazon_price", 0)
        alibaba_price = product_data.get("alibaba_price", amazon_price / 5)
        estimated_units = time_data.get("estimated_monthly_units", 100)

        monthly_profit, annual_value, risk_adjusted = self.estimate_economic_value(
            amazon_price=amazon_price,
            estimated_cogs=alibaba_price + 3,  # +3$ shipping (fallback heuristic)
            estimated_monthly_units=estimated_units,
            asin=asin,  # V2.0: pass ASIN to lookup real quotes
        )

        # === 5. SCORE DE RANKING ===
        # Ranking = valeur ajustée × urgence
        urgency_weight = self.TIME_MULTIPLIERS.get(time_result.window, 1.0)
        rank_score = float(risk_adjusted) * urgency_weight

        # === 6. CONSTRUIRE LA THÈSE ===
        thesis = self._build_thesis(
            base_score=base_score,
            time_result=time_result,
            monthly_profit=monthly_profit,
            base_result=base_result,
        )

        return EconomicOpportunity(
            asin=asin,
            base_score=base_score,
            time_multiplier=time_result.multiplier,
            final_score=final_score,
            estimated_monthly_profit=monthly_profit,
            estimated_annual_value=annual_value,
            risk_adjusted_value=risk_adjusted,
            window=time_result.window,
            window_days=time_result.window_days,
            urgency_label=time_result.urgency_label,
            thesis=thesis,
            component_scores=base_result.component_scores,
            economic_events=economic_events or [],
            rank_score=rank_score,
        )

    def _build_thesis(
        self,
        base_score: float,
        time_result: TimeMultiplierResult,
        monthly_profit: Decimal,
        base_result: ScoringResult,
    ) -> str:
        """Construit une thèse économique lisible."""
        parts = []

        # Force du produit
        if base_score >= 0.8:
            parts.append("Produit à fort potentiel")
        elif base_score >= 0.6:
            parts.append("Produit viable")
        else:
            parts.append("Produit à risque modéré")

        # Fenêtre temporelle
        if time_result.window in (TimeWindow.CRITICAL, TimeWindow.URGENT):
            parts.append(f"fenêtre courte ({time_result.window_days}j)")
        else:
            parts.append(f"fenêtre {time_result.window_days}j")

        # Profit estimé
        parts.append(f"~${monthly_profit:.0f}/mois estimé")

        # Facteurs clés
        strong_factors = [
            k for k, v in time_result.factors.items()
            if "+" in v
        ]
        if strong_factors:
            parts.append(f"drivers: {', '.join(strong_factors)}")

        return " | ".join(parts)

    def rank_opportunities(
        self,
        opportunities: List[EconomicOpportunity],
        top_n: int = 10,
    ) -> List[EconomicOpportunity]:
        """
        Classe les opportunités par valeur × temps.

        Args:
            opportunities: Liste d'opportunités à classer
            top_n: Nombre maximum à retourner

        Returns:
            Liste ordonnée par rank_score décroissant
        """
        # Filtrer les opportunités non viables
        viable = [o for o in opportunities if o.final_score >= 40]

        # Trier par rank_score
        ranked = sorted(viable, key=lambda x: x.rank_score, reverse=True)

        return ranked[:top_n]

    def generate_shortlist(
        self,
        opportunities: List[EconomicOpportunity],
        max_items: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Génère une shortlist contrainte et ordonnée.

        Format:
            1. ASIN B0... → score 82 → fenêtre 45 jours → $31k/an
            2. ASIN B0... → score 75 → fenêtre 120 jours → $18k/an

        Args:
            opportunities: Opportunités à filtrer
            max_items: Nombre max dans la shortlist

        Returns:
            Liste de dictionnaires formatés pour affichage
        """
        ranked = self.rank_opportunities(opportunities, top_n=max_items)

        shortlist = []
        for i, opp in enumerate(ranked, 1):
            shortlist.append({
                "rank": i,
                "asin": opp.asin,
                "score": opp.final_score,
                "window_days": opp.window_days,
                "urgency": opp.urgency_label,
                "annual_value": f"${opp.estimated_annual_value:,.0f}",
                "risk_adjusted_value": f"${opp.risk_adjusted_value:,.0f}",
                "thesis": opp.thesis,
                "summary": (
                    f"Score {opp.final_score} | "
                    f"Fenêtre {opp.window_days}j | "
                    f"${opp.risk_adjusted_value:,.0f}/an"
                ),
            })

        return shortlist
