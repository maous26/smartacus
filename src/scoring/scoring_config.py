"""
Configuration des seuils et pondérations pour le scoring Smartacus.

Ce fichier centralise TOUS les paramètres de calibration du modèle économique.
Calibré spécifiquement pour la niche "Car Phone Mounts" sur Amazon.

PHILOSOPHIE:
- Tous les seuils sont explicites et documentés
- Aucun "magic number" dans le code principal
- Facilement ajustable sans modifier la logique de scoring

NICHE CAR PHONE MOUNTS - CARACTÉRISTIQUES:
- Prix moyen: $15-35
- Marge typique: 25-40% (produit léger, shipping économique)
- BSR Electronics: 1,000-50,000 pour un bon vendeur
- Cycle de vie: 12-18 mois avant obsolescence
- Saisonnalité: pic Q4 (cadeaux), pic été (voyages)
"""

from dataclasses import dataclass, field
from typing import Dict, List, Tuple


@dataclass(frozen=True)
class MarginConfig:
    """
    Configuration du scoring MARGIN (30 points max).

    LOGIQUE ÉCONOMIQUE:
    La marge nette est le fondement de toute opportunité viable.
    Pour car phone mounts, les marges sont généralement bonnes grâce à:
    - Poids léger (shipping Alibaba ~$2-4/unité)
    - Prix Alibaba bas ($2-8/unité)
    - Prix Amazon soutenu ($15-35)

    SEUILS CALIBRÉS:
    - <15%: Non viable après frais cachés (retours, PPC, stockage)
    - 15-25%: Viable mais fragile
    - 25-35%: Sweet spot pour cette catégorie
    - >35%: Excellente opportunité (rare, à valider)
    """
    max_points: int = 30

    # Seuils de marge nette (après tous frais)
    thresholds: Tuple[Tuple[float, int], ...] = (
        (0.35, 30),  # >35% = 30 points (exceptionnel)
        (0.25, 20),  # 25-35% = 20 points (très bon)
        (0.15, 10),  # 15-25% = 10 points (acceptable)
        (0.00, 0),   # <15% = 0 points (non viable)
    )

    # Estimations de coûts pour car phone mounts
    fba_fee_percent: float = 0.15  # ~15% du prix de vente (référentiel)
    fba_fee_minimum: float = 3.00  # Minimum FBA fee
    amazon_referral_percent: float = 0.15  # 15% referral fee Electronics

    # Shipping Alibaba → Amazon FBA (par unité, estimé)
    shipping_per_unit_low: float = 2.50   # Sea freight, gros volume
    shipping_per_unit_mid: float = 4.00   # Sea freight, volume moyen
    shipping_per_unit_high: float = 6.00  # Air freight ou petit volume

    # Coûts cachés à provisionner
    return_rate: float = 0.03  # 3% taux de retour typique
    ppc_percent_of_revenue: float = 0.10  # 10% du CA en PPC estimé
    storage_monthly_per_unit: float = 0.15  # Stockage mensuel moyen


@dataclass(frozen=True)
class VelocityConfig:
    """
    Configuration du scoring VELOCITY (25 points max).

    LOGIQUE ÉCONOMIQUE:
    La vélocité mesure la DEMANDE RÉELLE et son évolution.
    Un bon BSR seul ne suffit pas - on veut voir du MOMENTUM.

    COMPOSANTES:
    1. BSR absolu (volume actuel) - 10 pts max
    2. BSR delta 7j (momentum court terme) - 8 pts max
    3. BSR delta 30j (tendance moyen terme) - 4 pts max
    4. Reviews/mois (proxy vélocité visible) - 3 pts max

    BSR ELECTRONICS (calibration car phone mounts):
    - BSR < 5,000: Très fort volume (~100+ ventes/jour)
    - BSR 5,000-20,000: Bon volume (~20-100 ventes/jour)
    - BSR 20,000-50,000: Volume correct (~5-20 ventes/jour)
    - BSR > 50,000: Volume faible (<5 ventes/jour)
    """
    max_points: int = 25

    # Points par composante
    bsr_absolute_max: int = 10
    bsr_delta_7d_max: int = 8
    bsr_delta_30d_max: int = 4
    reviews_velocity_max: int = 3

    # Seuils BSR absolu (catégorie Electronics)
    bsr_thresholds: Tuple[Tuple[int, int], ...] = (
        (5_000, 10),    # BSR < 5k = 10 pts (excellent)
        (20_000, 7),    # BSR 5k-20k = 7 pts (très bon)
        (50_000, 4),    # BSR 20k-50k = 4 pts (correct)
        (100_000, 2),   # BSR 50k-100k = 2 pts (faible)
        (999_999, 0),   # BSR > 100k = 0 pts (trop faible)
    )

    # Seuils BSR delta 7j (variation en %)
    # Négatif = amélioration du BSR (plus de ventes)
    bsr_delta_7d_thresholds: Tuple[Tuple[float, int], ...] = (
        (-0.30, 8),   # Baisse >30% = 8 pts (forte accélération)
        (-0.15, 6),   # Baisse 15-30% = 6 pts (bonne accélération)
        (-0.05, 4),   # Baisse 5-15% = 4 pts (légère accélération)
        (0.05, 2),    # Stable ±5% = 2 pts (maintien)
        (0.15, 1),    # Hausse 5-15% = 1 pt (léger déclin)
        (1.00, 0),    # Hausse >15% = 0 pts (déclin marqué)
    )

    # Seuils BSR delta 30j (tendance)
    bsr_delta_30d_thresholds: Tuple[Tuple[float, int], ...] = (
        (-0.20, 4),   # Baisse >20% = 4 pts (tendance haussière forte)
        (-0.05, 3),   # Baisse 5-20% = 3 pts (tendance positive)
        (0.10, 2),    # Stable ou légère hausse = 2 pts
        (0.30, 1),    # Hausse 10-30% = 1 pt
        (1.00, 0),    # Hausse >30% = 0 pts (tendance baissière)
    )

    # Seuils reviews par mois
    reviews_per_month_thresholds: Tuple[Tuple[int, int], ...] = (
        (50, 3),   # >50 reviews/mois = 3 pts (très actif)
        (20, 2),   # 20-50 reviews/mois = 2 pts (actif)
        (5, 1),    # 5-20 reviews/mois = 1 pt (modéré)
        (0, 0),    # <5 reviews/mois = 0 pts (faible activité)
    )

    # Pénalité produit stagnant
    stagnant_penalty: int = -3  # Si BSR stable ET reviews faibles


@dataclass(frozen=True)
class CompetitionConfig:
    """
    Configuration du scoring COMPETITION (20 points max).

    LOGIQUE ÉCONOMIQUE:
    On cherche des marchés "ouverts" où on peut s'insérer.
    Signaux positifs:
    - Peu de vendeurs établis (moins de 5 vendeurs FBA)
    - Buy box qui tourne (pas de dominance absolue)
    - Gap de reviews rattrapable vs top 10

    ATTENTION: Trop peu de concurrence peut signifier un marché mort.
    On veut de la concurrence MODÉRÉE avec des failles.
    """
    max_points: int = 20

    # Points par composante
    seller_count_max: int = 8
    buybox_rotation_max: int = 6
    review_gap_max: int = 6

    # Seuils nombre de vendeurs FBA
    seller_count_thresholds: Tuple[Tuple[int, int], ...] = (
        (3, 8),    # 1-3 vendeurs = 8 pts (très ouvert)
        (5, 6),    # 4-5 vendeurs = 6 pts (ouvert)
        (10, 4),   # 6-10 vendeurs = 4 pts (modéré)
        (20, 2),   # 11-20 vendeurs = 2 pts (compétitif)
        (999, 0),  # >20 vendeurs = 0 pts (saturé)
    )

    # Seuils rotation buy box (% de temps hors leader)
    # Plus la buy box tourne, plus il y a d'opportunité
    buybox_rotation_thresholds: Tuple[Tuple[float, int], ...] = (
        (0.40, 6),  # >40% rotation = 6 pts (très instable, opportunité)
        (0.25, 4),  # 25-40% rotation = 4 pts (instable)
        (0.10, 2),  # 10-25% rotation = 2 pts (légère rotation)
        (0.00, 0),  # <10% rotation = 0 pts (dominance)
    )

    # Seuils gap reviews vs moyenne top 10
    # Gap = (moyenne top 10 - nos reviews) / moyenne top 10
    # Plus le gap est faible, plus c'est rattrapable
    review_gap_thresholds: Tuple[Tuple[float, int], ...] = (
        (0.30, 6),  # Gap <30% = 6 pts (très rattrapable)
        (0.50, 4),  # Gap 30-50% = 4 pts (rattrapable)
        (0.70, 2),  # Gap 50-70% = 2 pts (difficile)
        (1.00, 0),  # Gap >70% = 0 pts (quasi impossible)
    )

    # Bonus/malus
    no_brand_dominance_bonus: int = 2  # Pas de marque > 50% du marché
    amazon_basics_penalty: int = -4    # Amazon Basics présent


@dataclass(frozen=True)
class GapConfig:
    """
    Configuration du scoring GAP (15 points max).

    LOGIQUE ÉCONOMIQUE:
    Le gap analyse les PROBLÈMES NON RÉSOLUS du marché.
    C'est un AMPLIFICATEUR, pas un moteur:
    - Un gap seul ne fait pas une opportunité
    - Un gap + bonne marge + vélocité = vraie opportunité

    SOURCES DE GAP:
    1. Reviews négatifs (problèmes exprimés)
    2. Mentions "I wish" (besoins non satisfaits)
    3. Questions sans réponse (confusion/manque d'info)

    CALIBRATION CAR PHONE MOUNTS:
    Problèmes typiques: stabilité, compatibilité téléphone,
    qualité plastique, instructions, ventouse qui tient pas
    """
    max_points: int = 15

    # Points par composante
    negative_reviews_max: int = 6
    wish_mentions_max: int = 5
    unanswered_questions_max: int = 4

    # Seuils % reviews négatifs (1-2 étoiles)
    # Plus il y en a, plus il y a de problèmes à résoudre
    negative_reviews_thresholds: Tuple[Tuple[float, int], ...] = (
        (0.25, 6),  # >25% négatifs = 6 pts (gros problèmes)
        (0.15, 4),  # 15-25% négatifs = 4 pts (problèmes notables)
        (0.08, 2),  # 8-15% négatifs = 2 pts (problèmes mineurs)
        (0.00, 0),  # <8% négatifs = 0 pts (peu d'amélioration possible)
    )

    # Seuils mentions "I wish" / "would be better if" pour 100 reviews
    wish_mentions_per_100_thresholds: Tuple[Tuple[int, int], ...] = (
        (10, 5),  # >10 mentions/100 = 5 pts (besoins clairs)
        (5, 3),   # 5-10 mentions/100 = 3 pts (besoins identifiables)
        (2, 1),   # 2-5 mentions/100 = 1 pt (quelques besoins)
        (0, 0),   # <2 mentions/100 = 0 pts (satisfaits)
    )

    # Seuils questions sans réponse
    unanswered_questions_thresholds: Tuple[Tuple[int, int], ...] = (
        (20, 4),  # >20 questions sans réponse = 4 pts
        (10, 3),  # 10-20 questions = 3 pts
        (5, 2),   # 5-10 questions = 2 pts
        (2, 1),   # 2-5 questions = 1 pt
        (0, 0),   # <2 questions = 0 pts
    )

    # Pondération si les problèmes sont RÉCURRENTS (même thème)
    recurring_problem_multiplier: float = 1.3


@dataclass(frozen=True)
class TimePressureConfig:
    """
    Configuration du scoring TIME_PRESSURE (10 points max).

    LOGIQUE ÉCONOMIQUE:
    Le time pressure mesure l'URGENCE de saisir l'opportunité.
    C'est le GARDE-FOU du scoring: sans urgence, pas d'action.

    RÈGLE CRITIQUE:
    Si time_pressure < 3 → opportunité INVALIDE
    Pas de fenêtre = pas d'opportunité, même si score total élevé.

    SIGNAUX D'URGENCE:
    1. Ruptures de stock fréquentes (demande > offre)
    2. Tendance prix haussière (marge qui s'améliore)
    3. Churn vendeurs (concurrents qui partent)
    4. Accélération BSR (momentum qui s'accélère)
    """
    max_points: int = 10
    minimum_valid: int = 3  # SEUIL CRITIQUE - en dessous = rejet

    # Points par composante
    stockout_frequency_max: int = 3
    price_trend_max: int = 3
    seller_churn_max: int = 2
    bsr_acceleration_max: int = 2

    # Seuils fréquence ruptures sur 90 jours
    stockout_frequency_thresholds: Tuple[Tuple[int, int], ...] = (
        (5, 3),   # >5 ruptures/90j = 3 pts (forte demande)
        (3, 2),   # 3-5 ruptures = 2 pts (demande soutenue)
        (1, 1),   # 1-2 ruptures = 1 pt (demande correcte)
        (0, 0),   # 0 ruptures = 0 pts (offre suffisante)
    )

    # Seuils tendance prix 30 jours (variation %)
    # Prix qui monte = marge qui s'améliore potentiellement
    price_trend_thresholds: Tuple[Tuple[float, int], ...] = (
        (0.15, 3),   # >+15% = 3 pts (forte hausse)
        (0.05, 2),   # +5-15% = 2 pts (hausse modérée)
        (0.00, 1),   # 0-5% = 1 pt (stable/légère hausse)
        (-0.10, 0),  # Baisse <10% = 0 pts
        (-1.00, -1), # Forte baisse = -1 pt (pression prix)
    )

    # Seuils churn vendeurs sur 90 jours
    # Vendeurs qui partent = place qui se libère
    seller_churn_thresholds: Tuple[Tuple[int, int], ...] = (
        (3, 2),   # >3 départs = 2 pts (marché qui se vide)
        (1, 1),   # 1-3 départs = 1 pt (mouvement)
        (0, 0),   # 0 départs = 0 pts (stable)
    )

    # Seuils accélération BSR (dérivée seconde)
    # Accélération = momentum qui S'ACCÉLÈRE (pas juste amélioration)
    bsr_acceleration_thresholds: Tuple[Tuple[float, int], ...] = (
        (0.20, 2),   # Accélération >20% = 2 pts
        (0.05, 1),   # Accélération 5-20% = 1 pt
        (0.00, 0),   # Pas d'accélération = 0 pts
    )


@dataclass(frozen=True)
class WindowEstimation:
    """
    Conversion time_pressure → estimation de fenêtre temporelle.

    LOGIQUE:
    Le score time_pressure nous indique COMBIEN DE TEMPS
    l'opportunité restera viable.
    """
    # (score_min, score_max, label, jours_estimés)
    windows: Tuple[Tuple[int, int, str, int], ...] = (
        (9, 10, "CRITIQUE - 2 semaines max", 14),
        (7, 8, "URGENT - 1 mois", 30),
        (5, 6, "COURT TERME - 2 mois", 60),
        (3, 4, "MOYEN TERME - 3-6 mois", 120),
        (0, 2, "PAS DE FENÊTRE - Opportunité invalide", 0),
    )


@dataclass
class ScoringConfig:
    """
    Configuration globale du scoring Smartacus.

    Agrège toutes les configurations de composantes.
    Point d'entrée unique pour la calibration.
    """
    # Pondérations globales (somme = 100)
    margin: MarginConfig = field(default_factory=MarginConfig)
    velocity: VelocityConfig = field(default_factory=VelocityConfig)
    competition: CompetitionConfig = field(default_factory=CompetitionConfig)
    gap: GapConfig = field(default_factory=GapConfig)
    time_pressure: TimePressureConfig = field(default_factory=TimePressureConfig)
    window_estimation: WindowEstimation = field(default_factory=WindowEstimation)

    # Score total maximum
    max_total_score: int = 100

    # Seuils de décision sur le score total
    score_thresholds: Dict[str, Tuple[int, str]] = field(default_factory=lambda: {
        "exceptional": (85, "OPPORTUNITÉ EXCEPTIONNELLE - Action immédiate"),
        "strong": (70, "FORTE OPPORTUNITÉ - À investiguer rapidement"),
        "moderate": (55, "OPPORTUNITÉ MODÉRÉE - Analyse approfondie requise"),
        "weak": (40, "OPPORTUNITÉ FAIBLE - Probablement à éviter"),
        "reject": (0, "REJET - Ne pas poursuivre"),
    })

    def validate(self) -> bool:
        """Vérifie la cohérence de la configuration."""
        total_max = (
            self.margin.max_points +
            self.velocity.max_points +
            self.competition.max_points +
            self.gap.max_points +
            self.time_pressure.max_points
        )
        assert total_max == self.max_total_score, \
            f"Somme des max ({total_max}) != max_total_score ({self.max_total_score})"
        return True


# Instance par défaut pour car phone mounts
DEFAULT_CONFIG = ScoringConfig()
