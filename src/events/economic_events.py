"""
Smartacus Economic Events
=========================

Events à sens économique - thèses primitives, pas symptômes numériques.

Ces événements représentent des DÉSÉQUILIBRES DE MARCHÉ exploitables,
pas de simples changements de métriques.

PHILOSOPHIE:
- Un "price_change" est un symptôme
- Un "SUPPLY_SHOCK" est une thèse économique

Le scoring consomme des thèses, pas des chiffres.

Types d'événements économiques:
    - SUPPLY_SHOCK: Rupture d'approvisionnement (demande > offre)
    - DEMAND_SURGE: Accélération soudaine de la demande
    - COMPETITOR_COLLAPSE: Effondrement d'un concurrent significatif
    - QUALITY_DECAY: Dégradation qualité perçue (opportunité d'amélioration)
    - PRICE_ELASTICITY_SIGNAL: Le marché accepte des prix plus élevés
    - MARKET_FATIGUE: Vendeurs qui abandonnent (place qui se libère)
    - MARGIN_COMPRESSION: Guerre des prix (danger ou opportunité)
    - SEASONAL_WINDOW: Fenêtre saisonnière qui s'ouvre
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional, List, Dict, Any


class EconomicEventType(Enum):
    """
    Types d'événements économiques.

    Chaque type représente une THÈSE sur l'état du marché,
    pas une observation brute.
    """
    # Déséquilibres Offre/Demande
    SUPPLY_SHOCK = "supply_shock"
    """
    La demande dépasse l'offre de manière significative.
    Signaux: stockouts répétés, BSR qui s'améliore malgré prix stable/hausse
    Opportunité: Entrer avec stock fiable
    """

    DEMAND_SURGE = "demand_surge"
    """
    Accélération soudaine de la demande.
    Signaux: BSR qui chute rapidement, reviews qui accélèrent
    Opportunité: Capter la vague avant saturation
    """

    # Dynamique Concurrentielle
    COMPETITOR_COLLAPSE = "competitor_collapse"
    """
    Un vendeur significatif quitte ou s'effondre.
    Signaux: seller_count baisse, buybox rotation change, top seller disparaît
    Opportunité: Capturer ses parts de marché
    """

    MARKET_FATIGUE = "market_fatigue"
    """
    Les vendeurs abandonnent progressivement.
    Signaux: churn élevé, moins de nouveaux entrants, prix instables
    Opportunité: Persévérance = victoire
    """

    # Signaux de Prix
    PRICE_ELASTICITY_SIGNAL = "price_elasticity_signal"
    """
    Le marché accepte des prix plus élevés.
    Signaux: prix monte ET ventes se maintiennent/augmentent
    Opportunité: Marge plus élevée possible
    """

    MARGIN_COMPRESSION = "margin_compression"
    """
    Guerre des prix en cours.
    Signaux: prix baisse généralisée, marges qui se réduisent
    Risque: Éviter ou différencier
    """

    # Qualité Produit
    QUALITY_DECAY = "quality_decay"
    """
    La qualité perçue se dégrade sur le marché.
    Signaux: reviews négatifs en hausse, "I wish...", plaintes récurrentes
    Opportunité: Entrer avec qualité supérieure
    """

    # Timing
    SEASONAL_WINDOW = "seasonal_window"
    """
    Fenêtre saisonnière qui s'ouvre.
    Signaux: patterns historiques, événements à venir (Prime Day, etc.)
    Opportunité: Timing d'entrée optimal
    """


class EventConfidence(Enum):
    """Niveau de confiance dans la thèse."""
    WEAK = "weak"           # 1-2 signaux concordants
    MODERATE = "moderate"   # 3-4 signaux concordants
    STRONG = "strong"       # 5+ signaux concordants
    CONFIRMED = "confirmed" # Pattern répété dans le temps


class EventUrgency(Enum):
    """Urgence d'action."""
    LOW = "low"             # Fenêtre > 90 jours
    MEDIUM = "medium"       # Fenêtre 30-90 jours
    HIGH = "high"           # Fenêtre 14-30 jours
    CRITICAL = "critical"   # Fenêtre < 14 jours


@dataclass
class EconomicEvent:
    """
    Événement économique exploitable.

    Représente une THÈSE sur un déséquilibre de marché,
    avec les preuves qui la soutiennent.
    """
    # Identification
    event_id: str
    asin: str
    event_type: EconomicEventType
    detected_at: datetime

    # Thèse
    thesis: str  # Description humaine de la thèse
    """Ex: "Demande dépasse l'offre: 3 stockouts en 30j, BSR -40%"""

    # Confiance et Urgence
    confidence: EventConfidence
    urgency: EventUrgency
    window_days: int  # Fenêtre estimée d'action

    # Preuves (signaux qui soutiennent la thèse)
    supporting_signals: List[Dict[str, Any]] = field(default_factory=list)
    """
    Liste des signaux bruts qui soutiennent cette thèse.
    Ex: [
        {"type": "stockout", "count": 3, "period": "30d"},
        {"type": "bsr_improvement", "delta": -0.40},
        {"type": "price_stable", "variance": 0.02}
    ]
    """

    # Contre-signaux (pourquoi la thèse pourrait être fausse)
    contradicting_signals: List[Dict[str, Any]] = field(default_factory=list)

    # Impact économique estimé
    estimated_opportunity_value: Optional[Decimal] = None
    """Valeur estimée de l'opportunité en USD"""

    # Métadonnées
    category: Optional[str] = None
    related_asins: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convertir en dictionnaire pour stockage/API."""
        return {
            "event_id": self.event_id,
            "asin": self.asin,
            "event_type": self.event_type.value,
            "detected_at": self.detected_at.isoformat(),
            "thesis": self.thesis,
            "confidence": self.confidence.value,
            "urgency": self.urgency.value,
            "window_days": self.window_days,
            "supporting_signals": self.supporting_signals,
            "contradicting_signals": self.contradicting_signals,
            "estimated_opportunity_value": (
                float(self.estimated_opportunity_value)
                if self.estimated_opportunity_value else None
            ),
            "category": self.category,
            "related_asins": self.related_asins,
        }

    @property
    def signal_strength(self) -> float:
        """
        Force du signal (ratio signaux positifs / négatifs).

        Returns:
            Ratio entre 0 et 1. >0.7 = signal fort.
        """
        total = len(self.supporting_signals) + len(self.contradicting_signals)
        if total == 0:
            return 0.0
        return len(self.supporting_signals) / total

    @property
    def is_actionable(self) -> bool:
        """
        Détermine si l'événement est actionnable.

        Critères:
        - Confiance >= MODERATE
        - Au moins 2 signaux de support
        - Ratio signal > 0.6
        """
        return (
            self.confidence in (EventConfidence.MODERATE, EventConfidence.STRONG, EventConfidence.CONFIRMED)
            and len(self.supporting_signals) >= 2
            and self.signal_strength >= 0.6
        )


@dataclass
class SupplyShockEvent(EconomicEvent):
    """
    Événement SUPPLY_SHOCK spécialisé.

    La demande dépasse l'offre de manière significative.
    """
    # Métriques spécifiques
    stockout_count: int = 0
    stockout_frequency_per_month: float = 0.0
    days_out_of_stock: int = 0
    bsr_during_stockout: Optional[int] = None
    competitors_also_stocked_out: int = 0

    def __post_init__(self):
        self.event_type = EconomicEventType.SUPPLY_SHOCK

    @classmethod
    def from_signals(
        cls,
        asin: str,
        stockouts_90d: int,
        bsr_change: float,
        price_change: float,
        competitors_stockout: int = 0,
    ) -> Optional["SupplyShockEvent"]:
        """
        Créer un SupplyShockEvent si les conditions sont remplies.

        Conditions pour SUPPLY_SHOCK:
        - 2+ stockouts en 90 jours
        - OU 1 stockout + BSR amélioration > 20%
        - Prix stable ou en hausse (pas de liquidation)
        """
        import uuid

        # Vérifier les conditions
        signals = []
        contra_signals = []

        # Signal: Stockouts fréquents
        if stockouts_90d >= 2:
            signals.append({
                "type": "frequent_stockouts",
                "count": stockouts_90d,
                "period": "90d",
                "interpretation": "Demande récurrente non satisfaite"
            })
        elif stockouts_90d == 1:
            signals.append({
                "type": "single_stockout",
                "count": 1,
                "interpretation": "Signal faible mais présent"
            })

        # Signal: BSR s'améliore (demande forte)
        if bsr_change < -0.20:  # Amélioration > 20%
            signals.append({
                "type": "bsr_improvement",
                "delta": bsr_change,
                "interpretation": "Demande en accélération"
            })
        elif bsr_change > 0.20:  # Dégradation
            contra_signals.append({
                "type": "bsr_degradation",
                "delta": bsr_change,
                "interpretation": "Demande en baisse"
            })

        # Signal: Prix stable ou hausse (pas liquidation)
        if price_change >= 0:
            signals.append({
                "type": "price_stable_or_up",
                "delta": price_change,
                "interpretation": "Pas de liquidation, demande réelle"
            })
        elif price_change < -0.15:
            contra_signals.append({
                "type": "price_dropping",
                "delta": price_change,
                "interpretation": "Possible liquidation"
            })

        # Signal: Concurrents aussi en rupture
        if competitors_stockout > 0:
            signals.append({
                "type": "market_wide_shortage",
                "count": competitors_stockout,
                "interpretation": "Problème d'offre généralisé"
            })

        # Décider si on crée l'événement
        if len(signals) < 2:
            return None

        # Calculer confiance
        if len(signals) >= 4 and len(contra_signals) == 0:
            confidence = EventConfidence.STRONG
        elif len(signals) >= 3:
            confidence = EventConfidence.MODERATE
        else:
            confidence = EventConfidence.WEAK

        # Calculer urgence basée sur fréquence stockouts
        if stockouts_90d >= 3:
            urgency = EventUrgency.HIGH
            window = 30
        elif stockouts_90d >= 2:
            urgency = EventUrgency.MEDIUM
            window = 60
        else:
            urgency = EventUrgency.LOW
            window = 90

        # Construire la thèse
        thesis = f"Supply shock détecté: {stockouts_90d} ruptures en 90j"
        if bsr_change < -0.20:
            thesis += f", BSR +{abs(bsr_change)*100:.0f}%"
        if competitors_stockout > 0:
            thesis += f", {competitors_stockout} concurrents aussi en rupture"

        return cls(
            event_id=f"ss_{asin}_{datetime.utcnow().strftime('%Y%m%d')}_{uuid.uuid4().hex[:6]}",
            asin=asin,
            event_type=EconomicEventType.SUPPLY_SHOCK,
            detected_at=datetime.utcnow(),
            thesis=thesis,
            confidence=confidence,
            urgency=urgency,
            window_days=window,
            supporting_signals=signals,
            contradicting_signals=contra_signals,
            stockout_count=stockouts_90d,
            stockout_frequency_per_month=stockouts_90d / 3,
            competitors_also_stocked_out=competitors_stockout,
        )


@dataclass
class CompetitorCollapseEvent(EconomicEvent):
    """
    Événement COMPETITOR_COLLAPSE spécialisé.

    Un vendeur significatif quitte ou s'effondre.
    """
    # Métriques spécifiques
    seller_exited_id: Optional[str] = None
    seller_exited_name: Optional[str] = None
    seller_market_share: float = 0.0  # Part de marché estimée
    seller_review_count: int = 0
    buybox_share_lost: float = 0.0

    def __post_init__(self):
        self.event_type = EconomicEventType.COMPETITOR_COLLAPSE

    @classmethod
    def from_signals(
        cls,
        asin: str,
        seller_churn_90d: float,
        top_seller_gone: bool,
        buybox_rotation_change: float,
        new_entrants: int,
    ) -> Optional["CompetitorCollapseEvent"]:
        """
        Créer un CompetitorCollapseEvent si les conditions sont remplies.

        Conditions:
        - Seller churn > 20% OU top seller disparu
        - Peu de nouveaux entrants (marché qui se vide)
        """
        import uuid

        signals = []
        contra_signals = []

        # Signal: Churn élevé
        if seller_churn_90d > 0.30:
            signals.append({
                "type": "high_seller_churn",
                "rate": seller_churn_90d,
                "interpretation": "Vendeurs abandonnent en masse"
            })
        elif seller_churn_90d > 0.20:
            signals.append({
                "type": "moderate_seller_churn",
                "rate": seller_churn_90d,
                "interpretation": "Turnover significatif"
            })

        # Signal: Top seller parti
        if top_seller_gone:
            signals.append({
                "type": "top_seller_exit",
                "interpretation": "Leader du marché parti"
            })

        # Signal: Buybox plus instable
        if buybox_rotation_change > 0.20:
            signals.append({
                "type": "buybox_destabilized",
                "delta": buybox_rotation_change,
                "interpretation": "Place à prendre"
            })

        # Contre-signal: Nouveaux entrants (remplacement)
        if new_entrants > 3:
            contra_signals.append({
                "type": "new_entrants",
                "count": new_entrants,
                "interpretation": "Marché se reconstitue"
            })
        elif new_entrants == 0:
            signals.append({
                "type": "no_new_entrants",
                "interpretation": "Marché qui se vide"
            })

        if len(signals) < 2:
            return None

        # Confiance
        if top_seller_gone and seller_churn_90d > 0.30:
            confidence = EventConfidence.STRONG
            urgency = EventUrgency.HIGH
            window = 30
        elif len(signals) >= 3:
            confidence = EventConfidence.MODERATE
            urgency = EventUrgency.MEDIUM
            window = 60
        else:
            confidence = EventConfidence.WEAK
            urgency = EventUrgency.LOW
            window = 90

        thesis = f"Effondrement concurrent: churn {seller_churn_90d*100:.0f}%"
        if top_seller_gone:
            thesis += ", leader parti"

        return cls(
            event_id=f"cc_{asin}_{datetime.utcnow().strftime('%Y%m%d')}_{uuid.uuid4().hex[:6]}",
            asin=asin,
            event_type=EconomicEventType.COMPETITOR_COLLAPSE,
            detected_at=datetime.utcnow(),
            thesis=thesis,
            confidence=confidence,
            urgency=urgency,
            window_days=window,
            supporting_signals=signals,
            contradicting_signals=contra_signals,
            seller_market_share=seller_churn_90d,
        )


@dataclass
class QualityDecayEvent(EconomicEvent):
    """
    Événement QUALITY_DECAY spécialisé.

    La qualité perçue se dégrade = opportunité d'amélioration.
    """
    # Métriques spécifiques
    negative_review_trend: float = 0.0  # Évolution % reviews négatifs
    common_complaints: List[str] = field(default_factory=list)
    wish_mentions_count: int = 0
    rating_decline: float = 0.0

    def __post_init__(self):
        self.event_type = EconomicEventType.QUALITY_DECAY

    @classmethod
    def from_signals(
        cls,
        asin: str,
        negative_pct: float,
        negative_pct_trend: float,
        wish_mentions: int,
        common_complaints: List[str],
        rating_30d_ago: float,
        rating_now: float,
    ) -> Optional["QualityDecayEvent"]:
        """
        Créer un QualityDecayEvent si les conditions sont remplies.

        Conditions:
        - Reviews négatifs > 15% ET en hausse
        - OU "I wish" mentions > 5
        - OU Rating en baisse > 0.3
        """
        import uuid

        signals = []
        contra_signals = []

        # Signal: Beaucoup de reviews négatifs
        if negative_pct > 0.20:
            signals.append({
                "type": "high_negative_reviews",
                "rate": negative_pct,
                "interpretation": "Insatisfaction élevée"
            })
        elif negative_pct > 0.15:
            signals.append({
                "type": "moderate_negative_reviews",
                "rate": negative_pct,
                "interpretation": "Problèmes de qualité"
            })

        # Signal: Trend négatif
        if negative_pct_trend > 0.05:  # +5% de négatifs
            signals.append({
                "type": "negative_trend_worsening",
                "delta": negative_pct_trend,
                "interpretation": "Qualité en dégradation"
            })

        # Signal: "I wish..."
        if wish_mentions >= 5:
            signals.append({
                "type": "wish_mentions",
                "count": wish_mentions,
                "interpretation": "Features manquantes identifiées"
            })

        # Signal: Rating en baisse
        rating_decline = rating_30d_ago - rating_now
        if rating_decline > 0.3:
            signals.append({
                "type": "rating_decline",
                "delta": rating_decline,
                "interpretation": "Réputation en chute"
            })

        # Signal: Plaintes récurrentes
        if len(common_complaints) >= 3:
            signals.append({
                "type": "recurring_complaints",
                "complaints": common_complaints[:5],
                "interpretation": "Problèmes systémiques identifiés"
            })

        # Contre-signal: Peu de reviews (pas assez de data)
        # (à ajouter selon contexte)

        if len(signals) < 2:
            return None

        # Confiance et urgence
        if len(signals) >= 4:
            confidence = EventConfidence.STRONG
        elif len(signals) >= 3:
            confidence = EventConfidence.MODERATE
        else:
            confidence = EventConfidence.WEAK

        # Quality decay = fenêtre longue (produit reste sur le marché)
        urgency = EventUrgency.MEDIUM
        window = 90

        thesis = f"Qualité en déclin: {negative_pct*100:.0f}% reviews négatifs"
        if wish_mentions >= 5:
            thesis += f", {wish_mentions} demandes d'amélioration"
        if common_complaints:
            thesis += f", plaintes: {', '.join(common_complaints[:2])}"

        return cls(
            event_id=f"qd_{asin}_{datetime.utcnow().strftime('%Y%m%d')}_{uuid.uuid4().hex[:6]}",
            asin=asin,
            event_type=EconomicEventType.QUALITY_DECAY,
            detected_at=datetime.utcnow(),
            thesis=thesis,
            confidence=confidence,
            urgency=urgency,
            window_days=window,
            supporting_signals=signals,
            contradicting_signals=contra_signals,
            negative_review_trend=negative_pct_trend,
            common_complaints=common_complaints,
            wish_mentions_count=wish_mentions,
            rating_decline=rating_decline,
        )


@dataclass
class PriceElasticityEvent(EconomicEvent):
    """
    Événement PRICE_ELASTICITY_SIGNAL spécialisé.

    Le marché accepte des prix plus élevés.
    """
    price_increase: float = 0.0
    sales_maintained: bool = False
    bsr_stable: bool = False
    competitors_followed: bool = False

    def __post_init__(self):
        self.event_type = EconomicEventType.PRICE_ELASTICITY_SIGNAL


@dataclass
class DemandSurgeEvent(EconomicEvent):
    """
    Événement DEMAND_SURGE spécialisé.

    Accélération soudaine de la demande.
    """
    bsr_acceleration: float = 0.0
    review_velocity_increase: float = 0.0
    search_volume_increase: float = 0.0

    def __post_init__(self):
        self.event_type = EconomicEventType.DEMAND_SURGE


# =============================================================================
# Event Detector
# =============================================================================

class EconomicEventDetector:
    """
    Détecte les événements économiques à partir des données brutes.

    Transforme les symptômes (price_change, bsr_change) en thèses économiques.
    """

    def detect_all_events(
        self,
        asin: str,
        metrics: Dict[str, Any],
    ) -> List[EconomicEvent]:
        """
        Détecter tous les événements économiques pour un ASIN.

        Args:
            asin: ASIN à analyser
            metrics: Dictionnaire de métriques brutes
                - stockouts_90d
                - bsr_change_30d
                - price_change_30d
                - seller_churn_90d
                - negative_review_pct
                - wish_mentions
                - etc.

        Returns:
            Liste d'événements économiques détectés
        """
        events = []

        # Tenter de détecter chaque type d'événement
        supply_shock = SupplyShockEvent.from_signals(
            asin=asin,
            stockouts_90d=metrics.get("stockouts_90d", 0),
            bsr_change=metrics.get("bsr_change_30d", 0),
            price_change=metrics.get("price_change_30d", 0),
            competitors_stockout=metrics.get("competitors_stockout", 0),
        )
        if supply_shock:
            events.append(supply_shock)

        competitor_collapse = CompetitorCollapseEvent.from_signals(
            asin=asin,
            seller_churn_90d=metrics.get("seller_churn_90d", 0),
            top_seller_gone=metrics.get("top_seller_gone", False),
            buybox_rotation_change=metrics.get("buybox_rotation_change", 0),
            new_entrants=metrics.get("new_entrants", 0),
        )
        if competitor_collapse:
            events.append(competitor_collapse)

        quality_decay = QualityDecayEvent.from_signals(
            asin=asin,
            negative_pct=metrics.get("negative_review_pct", 0),
            negative_pct_trend=metrics.get("negative_review_trend", 0),
            wish_mentions=metrics.get("wish_mentions", 0),
            common_complaints=metrics.get("common_complaints", []),
            rating_30d_ago=metrics.get("rating_30d_ago", 4.0),
            rating_now=metrics.get("rating_now", 4.0),
        )
        if quality_decay:
            events.append(quality_decay)

        return events

    def get_primary_event(
        self,
        events: List[EconomicEvent],
    ) -> Optional[EconomicEvent]:
        """
        Retourne l'événement principal (plus haute confiance + urgence).
        """
        if not events:
            return None

        # Trier par confiance puis urgence
        confidence_order = {
            EventConfidence.CONFIRMED: 4,
            EventConfidence.STRONG: 3,
            EventConfidence.MODERATE: 2,
            EventConfidence.WEAK: 1,
        }
        urgency_order = {
            EventUrgency.CRITICAL: 4,
            EventUrgency.HIGH: 3,
            EventUrgency.MEDIUM: 2,
            EventUrgency.LOW: 1,
        }

        return max(
            events,
            key=lambda e: (
                confidence_order.get(e.confidence, 0),
                urgency_order.get(e.urgency, 0),
            )
        )
