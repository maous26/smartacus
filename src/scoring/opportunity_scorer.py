"""
Smartacus Opportunity Scorer - Module de scoring déterministe.

Ce module implémente un système de scoring 100% déterministe et explicable
pour évaluer les opportunités Amazon sur la niche "Car Phone Mounts".

PHILOSOPHIE:
- Pas de ML, pas de fine-tuning
- Chaque score est REPRODUCTIBLE avec les mêmes inputs
- Chaque score est EXPLICABLE avec une trace de calcul

ARCHITECTURE:
- OpportunityScorer: classe principale orchestrant le scoring
- Méthodes dédiées par composante (margin, velocity, competition, gap, time_pressure)
- ScoringResult: dataclass contenant le détail complet du scoring

UTILISATION:
    from scoring import OpportunityScorer

    scorer = OpportunityScorer()
    result = scorer.score(product_data)

    print(result.total_score)
    print(result.is_valid)  # False si time_pressure < 3
    print(result.explanation)  # Trace complète du calcul
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
from enum import Enum

from .scoring_config import ScoringConfig, DEFAULT_CONFIG


class OpportunityStatus(Enum):
    """Statut de l'opportunité après scoring."""
    EXCEPTIONAL = "exceptional"
    STRONG = "strong"
    MODERATE = "moderate"
    WEAK = "weak"
    REJECTED = "rejected"
    INVALID_NO_WINDOW = "invalid_no_window"  # time_pressure < 3


@dataclass
class ComponentScore:
    """
    Score détaillé d'une composante.

    Contient:
    - Le score final de la composante
    - Le détail par sous-composante
    - L'explication textuelle
    """
    name: str
    score: int
    max_score: int
    details: Dict[str, Any] = field(default_factory=dict)
    explanation: str = ""

    @property
    def percentage(self) -> float:
        """Pourcentage du score max obtenu."""
        if self.max_score == 0:
            return 0.0
        return round(self.score / self.max_score * 100, 1)


@dataclass
class ScoringResult:
    """
    Résultat complet du scoring d'une opportunité.

    Contient tous les détails nécessaires pour:
    1. Prendre une décision (is_valid, total_score, status)
    2. Comprendre le scoring (component_scores, explanation)
    3. Estimer la fenêtre d'action (window_estimate)
    """
    product_id: str
    total_score: int
    max_score: int
    status: OpportunityStatus
    is_valid: bool  # False si time_pressure < 3
    window_estimate: str
    window_days: int
    component_scores: Dict[str, ComponentScore] = field(default_factory=dict)
    rejection_reason: Optional[str] = None

    @property
    def percentage(self) -> float:
        """Score total en pourcentage."""
        return round(self.total_score / self.max_score * 100, 1)

    def get_explanation(self) -> str:
        """Génère l'explication complète du scoring."""
        lines = [
            f"=== SCORING SMARTACUS ===",
            f"Produit: {self.product_id}",
            f"Score Total: {self.total_score}/{self.max_score} ({self.percentage}%)",
            f"Statut: {self.status.value.upper()}",
            f"Valide: {'OUI' if self.is_valid else 'NON'}",
            f"Fenêtre: {self.window_estimate}",
            "",
            "--- DÉTAIL PAR COMPOSANTE ---",
        ]

        for name, comp in self.component_scores.items():
            lines.append(f"\n{name.upper()} ({comp.score}/{comp.max_score} - {comp.percentage}%):")
            lines.append(comp.explanation)

        if self.rejection_reason:
            lines.append(f"\n!!! REJET: {self.rejection_reason} !!!")

        return "\n".join(lines)


class OpportunityScorer:
    """
    Scorer d'opportunités Amazon - 100% déterministe.

    Évalue une opportunité produit selon 5 composantes:
    - MARGIN (30 pts): Viabilité économique
    - VELOCITY (25 pts): Demande et momentum
    - COMPETITION (20 pts): Accessibilité du marché
    - GAP (15 pts): Potentiel d'amélioration
    - TIME_PRESSURE (10 pts): Urgence de l'action

    RÈGLE CRITIQUE:
    Si time_pressure < 3 → opportunité INVALIDE (rejet automatique)
    """

    def __init__(self, config: Optional[ScoringConfig] = None):
        """
        Initialise le scorer avec une configuration.

        Args:
            config: Configuration de scoring. Si None, utilise DEFAULT_CONFIG.
        """
        self.config = config or DEFAULT_CONFIG
        self.config.validate()

    # =========================================================================
    # MÉTHODE PRINCIPALE
    # =========================================================================

    def score(self, product_data: Dict[str, Any]) -> ScoringResult:
        """
        Calcule le score complet d'une opportunité.

        Args:
            product_data: Dictionnaire contenant toutes les données produit.
                Clés attendues:
                - product_id: str
                - amazon_price: float
                - alibaba_price: float (estimé)
                - fba_fees: float (optionnel, sera estimé)
                - shipping_per_unit: float (optionnel)
                - bsr_current: int
                - bsr_delta_7d: float (variation en %)
                - bsr_delta_30d: float (variation en %)
                - reviews_per_month: int
                - seller_count: int
                - buybox_rotation: float (% temps hors leader)
                - review_gap_vs_top10: float (ratio)
                - negative_review_percent: float
                - wish_mentions_per_100: int
                - unanswered_questions: int
                - stockout_count_90d: int
                - price_trend_30d: float (variation en %)
                - seller_churn_90d: int
                - bsr_acceleration: float

        Returns:
            ScoringResult avec le détail complet du scoring.
        """
        product_id = product_data.get("product_id", "UNKNOWN")

        # Calculer chaque composante
        margin_score = self.score_margin(product_data)
        velocity_score = self.score_velocity(product_data)
        competition_score = self.score_competition(product_data)
        gap_score = self.score_gap(product_data)
        time_pressure_score = self.score_time_pressure(product_data)

        # Agréger les scores
        component_scores = {
            "margin": margin_score,
            "velocity": velocity_score,
            "competition": competition_score,
            "gap": gap_score,
            "time_pressure": time_pressure_score,
        }

        total_score = sum(c.score for c in component_scores.values())

        # RÈGLE CRITIQUE: Vérifier time_pressure
        is_valid = time_pressure_score.score >= self.config.time_pressure.minimum_valid
        rejection_reason = None

        if not is_valid:
            rejection_reason = (
                f"Time Pressure ({time_pressure_score.score}) < seuil minimum "
                f"({self.config.time_pressure.minimum_valid}). "
                f"Pas de fenêtre d'action identifiée."
            )

        # Déterminer le statut
        status = self._determine_status(total_score, is_valid)

        # Estimer la fenêtre
        window_estimate, window_days = self.estimate_window(time_pressure_score.score)

        return ScoringResult(
            product_id=product_id,
            total_score=total_score,
            max_score=self.config.max_total_score,
            status=status,
            is_valid=is_valid,
            window_estimate=window_estimate,
            window_days=window_days,
            component_scores=component_scores,
            rejection_reason=rejection_reason,
        )

    # =========================================================================
    # SCORING MARGIN (30 points max)
    # =========================================================================

    def score_margin(self, product_data: Dict[str, Any]) -> ComponentScore:
        """
        Calcule le score MARGIN.

        FORMULE:
        1. Calculer le coût total (Alibaba + shipping + FBA + referral + provisions)
        2. Calculer la marge nette = (prix Amazon - coût total) / prix Amazon
        3. Appliquer les seuils de scoring

        LOGIQUE ÉCONOMIQUE:
        La marge est le FONDEMENT. Sans marge suffisante, rien d'autre ne compte.
        On provisionne les coûts cachés (retours, PPC, stockage) pour être conservateur.
        """
        cfg = self.config.margin

        # Extraire les données
        amazon_price = product_data.get("amazon_price", 0)
        alibaba_price = product_data.get("alibaba_price", 0)
        shipping = product_data.get("shipping_per_unit", cfg.shipping_per_unit_mid)
        fba_fees = product_data.get("fba_fees")

        # Estimer FBA fees si non fourni
        if fba_fees is None:
            fba_fees = max(
                amazon_price * cfg.fba_fee_percent,
                cfg.fba_fee_minimum
            )

        # Calculer les coûts
        referral_fee = amazon_price * cfg.amazon_referral_percent
        product_cost = alibaba_price + shipping

        # Provisions pour coûts cachés
        return_provision = amazon_price * cfg.return_rate
        ppc_provision = amazon_price * cfg.ppc_percent_of_revenue
        storage_provision = cfg.storage_monthly_per_unit * 2  # 2 mois de stock moyen

        total_cost = (
            product_cost +
            fba_fees +
            referral_fee +
            return_provision +
            ppc_provision +
            storage_provision
        )

        # Calculer la marge nette
        if amazon_price <= 0:
            net_margin = 0
        else:
            net_margin = (amazon_price - total_cost) / amazon_price

        # Appliquer les seuils
        score = 0
        for threshold, points in cfg.thresholds:
            if net_margin >= threshold:
                score = points
                break

        # Construire l'explication
        explanation = (
            f"  Prix Amazon: ${amazon_price:.2f}\n"
            f"  Prix Alibaba: ${alibaba_price:.2f}\n"
            f"  Shipping/unité: ${shipping:.2f}\n"
            f"  FBA fees: ${fba_fees:.2f}\n"
            f"  Referral (15%): ${referral_fee:.2f}\n"
            f"  Provisions (retours, PPC, stock): ${return_provision + ppc_provision + storage_provision:.2f}\n"
            f"  ---\n"
            f"  Coût total: ${total_cost:.2f}\n"
            f"  Marge nette: {net_margin*100:.1f}%\n"
            f"  → Score: {score}/{cfg.max_points}"
        )

        return ComponentScore(
            name="margin",
            score=score,
            max_score=cfg.max_points,
            details={
                "amazon_price": amazon_price,
                "total_cost": total_cost,
                "net_margin": net_margin,
                "net_margin_percent": round(net_margin * 100, 1),
            },
            explanation=explanation,
        )

    # =========================================================================
    # SCORING VELOCITY (25 points max)
    # =========================================================================

    def score_velocity(self, product_data: Dict[str, Any]) -> ComponentScore:
        """
        Calcule le score VELOCITY.

        FORMULE:
        velocity_score = bsr_absolute + bsr_delta_7d + bsr_delta_30d + reviews_velocity
                       + (pénalité si stagnant)

        COMPOSANTES:
        1. BSR absolu (10 pts): Volume de ventes actuel
        2. BSR delta 7j (8 pts): Momentum court terme
        3. BSR delta 30j (4 pts): Tendance moyen terme
        4. Reviews/mois (3 pts): Proxy de vélocité visible

        LOGIQUE ÉCONOMIQUE:
        On veut des produits qui BOUGENT, pas des produits stagnants.
        Le momentum est crucial: mieux vaut un BSR moyen en amélioration
        qu'un bon BSR en déclin.
        """
        cfg = self.config.velocity

        # Extraire les données
        bsr_current = product_data.get("bsr_current", 999999)
        bsr_delta_7d = product_data.get("bsr_delta_7d", 0)  # % variation
        bsr_delta_30d = product_data.get("bsr_delta_30d", 0)  # % variation
        reviews_per_month = product_data.get("reviews_per_month", 0)

        # Score BSR absolu
        bsr_score = 0
        for threshold, points in cfg.bsr_thresholds:
            if bsr_current <= threshold:
                bsr_score = points
                break

        # Score BSR delta 7j
        delta_7d_score = 0
        for threshold, points in cfg.bsr_delta_7d_thresholds:
            if bsr_delta_7d <= threshold:
                delta_7d_score = points
                break

        # Score BSR delta 30j
        delta_30d_score = 0
        for threshold, points in cfg.bsr_delta_30d_thresholds:
            if bsr_delta_30d <= threshold:
                delta_30d_score = points
                break

        # Score reviews velocity
        reviews_score = 0
        for threshold, points in cfg.reviews_per_month_thresholds:
            if reviews_per_month >= threshold:
                reviews_score = points
                break

        # Pénalité produit stagnant
        # Stagnant = BSR stable (±5%) ET reviews faibles (<5/mois)
        stagnant_penalty = 0
        is_stagnant = (
            abs(bsr_delta_7d) < 0.05 and
            abs(bsr_delta_30d) < 0.10 and
            reviews_per_month < 5
        )
        if is_stagnant:
            stagnant_penalty = cfg.stagnant_penalty

        # Score total
        raw_score = bsr_score + delta_7d_score + delta_30d_score + reviews_score + stagnant_penalty
        score = max(0, min(raw_score, cfg.max_points))

        # Explication
        explanation = (
            f"  BSR actuel: {bsr_current:,} → {bsr_score} pts\n"
            f"  BSR delta 7j: {bsr_delta_7d*100:+.1f}% → {delta_7d_score} pts\n"
            f"  BSR delta 30j: {bsr_delta_30d*100:+.1f}% → {delta_30d_score} pts\n"
            f"  Reviews/mois: {reviews_per_month} → {reviews_score} pts\n"
            f"  Stagnant: {'OUI' if is_stagnant else 'NON'} → {stagnant_penalty} pts\n"
            f"  → Score: {score}/{cfg.max_points}"
        )

        return ComponentScore(
            name="velocity",
            score=score,
            max_score=cfg.max_points,
            details={
                "bsr_current": bsr_current,
                "bsr_delta_7d": bsr_delta_7d,
                "bsr_delta_30d": bsr_delta_30d,
                "reviews_per_month": reviews_per_month,
                "is_stagnant": is_stagnant,
                "sub_scores": {
                    "bsr_absolute": bsr_score,
                    "bsr_delta_7d": delta_7d_score,
                    "bsr_delta_30d": delta_30d_score,
                    "reviews_velocity": reviews_score,
                    "stagnant_penalty": stagnant_penalty,
                }
            },
            explanation=explanation,
        )

    # =========================================================================
    # SCORING COMPETITION (20 points max)
    # =========================================================================

    def score_competition(self, product_data: Dict[str, Any]) -> ComponentScore:
        """
        Calcule le score COMPETITION.

        FORMULE:
        competition_score = seller_count_score + buybox_rotation_score + review_gap_score
                          + bonus/malus

        COMPOSANTES:
        1. Nombre de vendeurs (8 pts): Moins = plus ouvert
        2. Rotation buy box (6 pts): Plus de rotation = plus d'opportunité
        3. Gap reviews vs top 10 (6 pts): Plus rattrapable = mieux

        LOGIQUE ÉCONOMIQUE:
        On cherche des marchés "ouverts" où on peut s'insérer.
        Un marché avec peu de vendeurs, une buy box instable et un gap
        de reviews rattrapable est idéal.
        """
        cfg = self.config.competition

        # Extraire les données
        seller_count = product_data.get("seller_count", 50)
        buybox_rotation = product_data.get("buybox_rotation", 0)  # % temps hors leader
        review_gap = product_data.get("review_gap_vs_top10", 1.0)  # ratio
        has_amazon_basics = product_data.get("has_amazon_basics", False)
        has_brand_dominance = product_data.get("has_brand_dominance", False)

        # Score nombre de vendeurs
        seller_score = 0
        for threshold, points in cfg.seller_count_thresholds:
            if seller_count <= threshold:
                seller_score = points
                break

        # Score rotation buy box
        buybox_score = 0
        for threshold, points in cfg.buybox_rotation_thresholds:
            if buybox_rotation >= threshold:
                buybox_score = points
                break

        # Score gap reviews
        gap_score = 0
        for threshold, points in cfg.review_gap_thresholds:
            if review_gap <= threshold:
                gap_score = points
                break

        # Bonus/malus
        bonus = 0
        if not has_brand_dominance:
            bonus += cfg.no_brand_dominance_bonus
        if has_amazon_basics:
            bonus += cfg.amazon_basics_penalty

        # Score total
        raw_score = seller_score + buybox_score + gap_score + bonus
        score = max(0, min(raw_score, cfg.max_points))

        # Explication
        explanation = (
            f"  Vendeurs FBA: {seller_count} → {seller_score} pts\n"
            f"  Rotation buy box: {buybox_rotation*100:.0f}% → {buybox_score} pts\n"
            f"  Gap reviews vs top 10: {review_gap*100:.0f}% → {gap_score} pts\n"
            f"  Amazon Basics: {'OUI (-4)' if has_amazon_basics else 'NON'}\n"
            f"  Dominance marque: {'OUI' if has_brand_dominance else 'NON (+2)'}\n"
            f"  Bonus/malus: {bonus:+d}\n"
            f"  → Score: {score}/{cfg.max_points}"
        )

        return ComponentScore(
            name="competition",
            score=score,
            max_score=cfg.max_points,
            details={
                "seller_count": seller_count,
                "buybox_rotation": buybox_rotation,
                "review_gap_vs_top10": review_gap,
                "has_amazon_basics": has_amazon_basics,
                "has_brand_dominance": has_brand_dominance,
                "sub_scores": {
                    "seller_count": seller_score,
                    "buybox_rotation": buybox_score,
                    "review_gap": gap_score,
                    "bonus": bonus,
                }
            },
            explanation=explanation,
        )

    # =========================================================================
    # SCORING GAP (15 points max)
    # =========================================================================

    def score_gap(self, product_data: Dict[str, Any]) -> ComponentScore:
        """
        Calcule le score GAP.

        FORMULE:
        gap_score = negative_reviews_score + wish_mentions_score + unanswered_questions_score
                  * (multiplicateur si problèmes récurrents)

        COMPOSANTES:
        1. % reviews négatifs (6 pts): Problèmes exprimés
        2. Mentions "I wish" (5 pts): Besoins non satisfaits
        3. Questions sans réponse (4 pts): Confusion/manque d'info

        LOGIQUE ÉCONOMIQUE:
        Le gap est un AMPLIFICATEUR, pas un moteur.
        On identifie des problèmes qu'on pourrait résoudre avec un meilleur produit.
        Seul, un gap ne fait pas une opportunité.
        """
        cfg = self.config.gap

        # Extraire les données
        negative_percent = product_data.get("negative_review_percent", 0)
        wish_mentions = product_data.get("wish_mentions_per_100", 0)
        unanswered = product_data.get("unanswered_questions", 0)
        has_recurring_problems = product_data.get("has_recurring_problems", False)

        # Score reviews négatifs
        negative_score = 0
        for threshold, points in cfg.negative_reviews_thresholds:
            if negative_percent >= threshold:
                negative_score = points
                break

        # Score mentions "I wish"
        wish_score = 0
        for threshold, points in cfg.wish_mentions_per_100_thresholds:
            if wish_mentions >= threshold:
                wish_score = points
                break

        # Score questions sans réponse
        questions_score = 0
        for threshold, points in cfg.unanswered_questions_thresholds:
            if unanswered >= threshold:
                questions_score = points
                break

        # Multiplicateur si problèmes récurrents
        raw_score = negative_score + wish_score + questions_score
        if has_recurring_problems:
            raw_score = int(raw_score * cfg.recurring_problem_multiplier)

        score = max(0, min(raw_score, cfg.max_points))

        # Explication
        explanation = (
            f"  Reviews négatifs: {negative_percent*100:.0f}% → {negative_score} pts\n"
            f"  Mentions 'I wish'/100: {wish_mentions} → {wish_score} pts\n"
            f"  Questions sans réponse: {unanswered} → {questions_score} pts\n"
            f"  Problèmes récurrents: {'OUI (x1.3)' if has_recurring_problems else 'NON'}\n"
            f"  → Score: {score}/{cfg.max_points}"
        )

        return ComponentScore(
            name="gap",
            score=score,
            max_score=cfg.max_points,
            details={
                "negative_review_percent": negative_percent,
                "wish_mentions_per_100": wish_mentions,
                "unanswered_questions": unanswered,
                "has_recurring_problems": has_recurring_problems,
                "sub_scores": {
                    "negative_reviews": negative_score,
                    "wish_mentions": wish_score,
                    "unanswered_questions": questions_score,
                }
            },
            explanation=explanation,
        )

    # =========================================================================
    # SCORING TIME_PRESSURE (10 points max) - CRITIQUE
    # =========================================================================

    def score_time_pressure(self, product_data: Dict[str, Any]) -> ComponentScore:
        """
        Calcule le score TIME_PRESSURE.

        FORMULE:
        time_pressure = stockout_score + price_trend_score + seller_churn_score + bsr_acceleration_score

        COMPOSANTES:
        1. Fréquence ruptures 90j (3 pts): Demande > offre
        2. Tendance prix 30j (3 pts): Marge qui s'améliore
        3. Churn vendeurs 90j (2 pts): Place qui se libère
        4. Accélération BSR (2 pts): Momentum qui s'accélère

        RÈGLE CRITIQUE:
        Si time_pressure < 3 → opportunité INVALIDE
        Cette règle est absolue et ne peut être contournée.

        LOGIQUE ÉCONOMIQUE:
        Sans urgence, pas d'action. On veut des signaux clairs que
        la fenêtre d'opportunité est ouverte MAINTENANT.
        """
        cfg = self.config.time_pressure

        # Extraire les données
        stockout_count = product_data.get("stockout_count_90d", 0)
        price_trend = product_data.get("price_trend_30d", 0)  # % variation
        seller_churn = product_data.get("seller_churn_90d", 0)
        bsr_acceleration = product_data.get("bsr_acceleration", 0)

        # Score ruptures
        stockout_score = 0
        for threshold, points in cfg.stockout_frequency_thresholds:
            if stockout_count >= threshold:
                stockout_score = points
                break

        # Score tendance prix
        price_score = 0
        for threshold, points in cfg.price_trend_thresholds:
            if price_trend >= threshold:
                price_score = points
                break

        # Score churn vendeurs
        churn_score = 0
        for threshold, points in cfg.seller_churn_thresholds:
            if seller_churn >= threshold:
                churn_score = points
                break

        # Score accélération BSR
        acceleration_score = 0
        for threshold, points in cfg.bsr_acceleration_thresholds:
            if bsr_acceleration >= threshold:
                acceleration_score = points
                break

        # Score total
        raw_score = stockout_score + price_score + churn_score + acceleration_score
        score = max(0, min(raw_score, cfg.max_points))

        # Vérification seuil critique
        is_valid = score >= cfg.minimum_valid

        # Explication
        explanation = (
            f"  Ruptures 90j: {stockout_count} → {stockout_score} pts\n"
            f"  Tendance prix 30j: {price_trend*100:+.1f}% → {price_score} pts\n"
            f"  Churn vendeurs 90j: {seller_churn} → {churn_score} pts\n"
            f"  Accélération BSR: {bsr_acceleration*100:+.1f}% → {acceleration_score} pts\n"
            f"  ---\n"
            f"  SEUIL CRITIQUE: {cfg.minimum_valid} pts minimum\n"
            f"  STATUT: {'VALIDE' if is_valid else '*** INVALIDE - REJET ***'}\n"
            f"  → Score: {score}/{cfg.max_points}"
        )

        return ComponentScore(
            name="time_pressure",
            score=score,
            max_score=cfg.max_points,
            details={
                "stockout_count_90d": stockout_count,
                "price_trend_30d": price_trend,
                "seller_churn_90d": seller_churn,
                "bsr_acceleration": bsr_acceleration,
                "is_valid": is_valid,
                "minimum_required": cfg.minimum_valid,
                "sub_scores": {
                    "stockout_frequency": stockout_score,
                    "price_trend": price_score,
                    "seller_churn": churn_score,
                    "bsr_acceleration": acceleration_score,
                }
            },
            explanation=explanation,
        )

    # =========================================================================
    # MÉTHODES UTILITAIRES
    # =========================================================================

    def estimate_window(self, time_pressure_score: int) -> Tuple[str, int]:
        """
        Estime la fenêtre temporelle d'opportunité.

        Args:
            time_pressure_score: Score time_pressure (0-10)

        Returns:
            Tuple (label textuel, nombre de jours estimés)

        LOGIQUE:
        Plus le time_pressure est élevé, plus la fenêtre est courte
        (l'opportunité va se refermer vite si on n'agit pas).
        """
        for score_min, score_max, label, days in self.config.window_estimation.windows:
            if score_min <= time_pressure_score <= score_max:
                return label, days

        return "INCONNU", 0

    def _determine_status(self, total_score: int, is_valid: bool) -> OpportunityStatus:
        """Détermine le statut de l'opportunité basé sur le score total."""
        if not is_valid:
            return OpportunityStatus.INVALID_NO_WINDOW

        thresholds = self.config.score_thresholds
        if total_score >= thresholds["exceptional"][0]:
            return OpportunityStatus.EXCEPTIONAL
        elif total_score >= thresholds["strong"][0]:
            return OpportunityStatus.STRONG
        elif total_score >= thresholds["moderate"][0]:
            return OpportunityStatus.MODERATE
        elif total_score >= thresholds["weak"][0]:
            return OpportunityStatus.WEAK
        else:
            return OpportunityStatus.REJECTED

    def score_batch(self, products: List[Dict[str, Any]]) -> List[ScoringResult]:
        """
        Score un batch de produits.

        Args:
            products: Liste de dictionnaires product_data

        Returns:
            Liste de ScoringResult triée par score décroissant
        """
        results = [self.score(p) for p in products]
        # Trier par: valide d'abord, puis score décroissant
        return sorted(
            results,
            key=lambda r: (r.is_valid, r.total_score),
            reverse=True
        )

    def get_top_opportunities(
        self,
        products: List[Dict[str, Any]],
        n: int = 10,
        min_score: int = 55
    ) -> List[ScoringResult]:
        """
        Retourne les N meilleures opportunités valides.

        Args:
            products: Liste de dictionnaires product_data
            n: Nombre max d'opportunités à retourner
            min_score: Score minimum requis

        Returns:
            Liste des meilleures opportunités (max n)
        """
        all_results = self.score_batch(products)
        valid_above_threshold = [
            r for r in all_results
            if r.is_valid and r.total_score >= min_score
        ]
        return valid_above_threshold[:n]


# =============================================================================
# EXEMPLES DE CALCUL
# =============================================================================

def example_calculations():
    """
    Exemples de calcul pour illustrer le fonctionnement du scorer.

    Ces exemples montrent des cas typiques de la niche car phone mounts.
    """
    scorer = OpportunityScorer()

    # -------------------------------------------------------------------------
    # EXEMPLE 1: Opportunité exceptionnelle
    # -------------------------------------------------------------------------
    print("=" * 70)
    print("EXEMPLE 1: Opportunité exceptionnelle")
    print("=" * 70)

    exceptional_product = {
        "product_id": "B09EXAMPLE1",
        # Margin inputs
        "amazon_price": 29.99,
        "alibaba_price": 4.50,
        "shipping_per_unit": 3.00,
        # Velocity inputs
        "bsr_current": 8_500,
        "bsr_delta_7d": -0.20,  # BSR baisse de 20% = plus de ventes
        "bsr_delta_30d": -0.10,
        "reviews_per_month": 35,
        # Competition inputs
        "seller_count": 4,
        "buybox_rotation": 0.35,
        "review_gap_vs_top10": 0.40,
        "has_amazon_basics": False,
        "has_brand_dominance": False,
        # Gap inputs
        "negative_review_percent": 0.18,
        "wish_mentions_per_100": 7,
        "unanswered_questions": 12,
        "has_recurring_problems": True,
        # Time pressure inputs
        "stockout_count_90d": 4,
        "price_trend_30d": 0.08,
        "seller_churn_90d": 2,
        "bsr_acceleration": 0.15,
    }

    result = scorer.score(exceptional_product)
    print(result.get_explanation())

    # -------------------------------------------------------------------------
    # EXEMPLE 2: Opportunité rejetée (time_pressure insuffisant)
    # -------------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("EXEMPLE 2: Opportunité rejetée (pas de fenêtre)")
    print("=" * 70)

    no_window_product = {
        "product_id": "B09EXAMPLE2",
        # Bonne marge
        "amazon_price": 24.99,
        "alibaba_price": 3.50,
        "shipping_per_unit": 2.50,
        # Bonne vélocité
        "bsr_current": 12_000,
        "bsr_delta_7d": -0.10,
        "bsr_delta_30d": -0.05,
        "reviews_per_month": 25,
        # Bonne compétition
        "seller_count": 6,
        "buybox_rotation": 0.25,
        "review_gap_vs_top10": 0.35,
        "has_amazon_basics": False,
        "has_brand_dominance": False,
        # Gap correct
        "negative_review_percent": 0.12,
        "wish_mentions_per_100": 4,
        "unanswered_questions": 8,
        "has_recurring_problems": False,
        # MAIS: Pas d'urgence (time_pressure < 3)
        "stockout_count_90d": 0,
        "price_trend_30d": -0.05,  # Prix en légère baisse
        "seller_churn_90d": 0,
        "bsr_acceleration": 0.0,
    }

    result = scorer.score(no_window_product)
    print(result.get_explanation())

    # -------------------------------------------------------------------------
    # EXEMPLE 3: Opportunité modérée
    # -------------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("EXEMPLE 3: Opportunité modérée")
    print("=" * 70)

    moderate_product = {
        "product_id": "B09EXAMPLE3",
        # Marge acceptable
        "amazon_price": 19.99,
        "alibaba_price": 4.00,
        "shipping_per_unit": 3.50,
        # Vélocité moyenne
        "bsr_current": 35_000,
        "bsr_delta_7d": -0.05,
        "bsr_delta_30d": 0.02,
        "reviews_per_month": 12,
        # Compétition modérée
        "seller_count": 8,
        "buybox_rotation": 0.15,
        "review_gap_vs_top10": 0.55,
        "has_amazon_basics": False,
        "has_brand_dominance": False,
        # Gap limité
        "negative_review_percent": 0.10,
        "wish_mentions_per_100": 3,
        "unanswered_questions": 5,
        "has_recurring_problems": False,
        # Time pressure suffisant
        "stockout_count_90d": 2,
        "price_trend_30d": 0.03,
        "seller_churn_90d": 1,
        "bsr_acceleration": 0.08,
    }

    result = scorer.score(moderate_product)
    print(result.get_explanation())


if __name__ == "__main__":
    example_calculations()
