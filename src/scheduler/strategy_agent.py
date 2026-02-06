"""
Strategy Agent V3.0
====================

Intelligent resource allocation for Smartacus pipeline.
Maximizes economic value detected per token consumed.

Principle: "Smartacus ne cherche pas à tout voir.
            Il cherche à voir juste assez pour décider mieux que les autres."

Features:
- Tri-partition: EXPLOIT / EXPLORE / PAUSE
- Token allocation: 70% exploit, 20% explore, 10% reserve
- Deterministic scoring with optional LLM override
- Cold start protection (min 2 runs before PAUSE)
- Event boost for critical signals
"""

import os
import logging
import hashlib
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Literal, Tuple
from enum import Enum

logger = logging.getLogger(__name__)


# =============================================================================
# DATA MODELS
# =============================================================================

class NicheStatus(str, Enum):
    """Niche classification for resource allocation."""
    EXPLOIT = "EXPLOIT"  # High priority, proven value
    EXPLORE = "EXPLORE"  # Testing hypothesis
    PAUSE = "PAUSE"      # Low yield, skip this cycle


@dataclass
class NicheMetrics:
    """
    Performance metrics for a niche (category + domain).

    Populated from category_performance + category_registry tables.
    """
    niche_id: int                    # category_id
    name: str
    domain: str                      # 'com', 'fr', etc.

    # Performance metrics (from historical runs)
    total_runs: int = 0
    total_asins_scanned: int = 0
    total_opportunities: int = 0     # score >= 40
    high_value_opps: int = 0         # score >= 60
    total_tokens_used: int = 0
    total_value_detected: float = 0  # sum of risk_adjusted_value

    # Computed metrics
    density: float = 0.0             # opportunities / asins_scanned
    value_per_1k_tokens: float = 0.0
    avg_score: float = 0.0

    # Freshness
    last_scanned_at: Optional[datetime] = None
    days_since_scan: int = 999

    # Events
    recent_critical_events: int = 0  # CRITICAL/HIGH events in last 7 days

    # Status
    is_active: bool = False
    priority: int = 5                # 1=highest, 10=lowest

    def __post_init__(self):
        """Compute derived metrics."""
        if self.total_asins_scanned > 0:
            self.density = self.total_opportunities / self.total_asins_scanned
        if self.total_tokens_used > 0:
            self.value_per_1k_tokens = (self.total_value_detected / self.total_tokens_used) * 1000
        if self.last_scanned_at:
            self.days_since_scan = (datetime.utcnow() - self.last_scanned_at).days


@dataclass
class NicheAssessment:
    """Assessment result for a single niche."""
    niche_id: int
    name: str
    domain: str
    status: NicheStatus
    score: float                     # 0-1 composite score
    tokens_allocated: int
    max_asins: int
    justification: str
    confidence: float = 1.0          # 0-1, lower if LLM override used


@dataclass
class StrategyDecision:
    """Complete strategy decision for a cycle."""
    cycle_id: str
    decided_at: datetime
    budget_total: int
    budget_exploit: int
    budget_explore: int
    budget_reserve: int

    assessments: List[NicheAssessment]
    risk_notes: List[str]

    # LLM consultation (if used)
    llm_consulted: bool = False
    llm_override_reason: Optional[str] = None

    def to_dict(self) -> Dict:
        """Convert to dictionary for logging/storage."""
        return {
            "cycle_id": self.cycle_id,
            "decided_at": self.decided_at.isoformat(),
            "budget": {
                "total": self.budget_total,
                "exploit": self.budget_exploit,
                "explore": self.budget_explore,
                "reserve": self.budget_reserve,
            },
            "assessments": [
                {
                    "niche_id": a.niche_id,
                    "name": a.name,
                    "domain": a.domain,
                    "status": a.status.value,
                    "score": round(a.score, 3),
                    "tokens": a.tokens_allocated,
                    "max_asins": a.max_asins,
                    "justification": a.justification,
                    "confidence": a.confidence,
                }
                for a in self.assessments
            ],
            "risk_notes": self.risk_notes,
            "llm_consulted": self.llm_consulted,
            "llm_override_reason": self.llm_override_reason,
        }


# =============================================================================
# STRATEGY AGENT
# =============================================================================

class StrategyAgent:
    """
    Intelligent resource allocator for Smartacus.

    Decides which niches to scan, how many tokens to allocate,
    and when to pause or explore new territories.
    """

    # Allocation ratios
    EXPLOIT_RATIO = 0.70
    EXPLORE_RATIO = 0.20
    RESERVE_RATIO = 0.10

    # Classification thresholds
    EXPLOIT_THRESHOLD = 0.55   # score > this → EXPLOIT
    EXPLORE_THRESHOLD = 0.25   # score > this → EXPLORE, else PAUSE

    # Density thresholds
    DENSITY_GOOD = 0.05        # 5% = good conversion
    DENSITY_BAD = 0.01         # 1% = poor conversion

    # Freshness
    STALE_DAYS = 14            # Niche not scanned in 14 days needs refresh

    # Cold start protection
    MIN_RUNS_BEFORE_PAUSE = 2  # Don't pause before 2 runs
    COLD_START_TOKENS = 200    # Fixed allocation for new niches

    # Event boost
    EVENT_BOOST_MULTIPLIER = 1.5  # Boost score if critical events

    def __init__(self, enable_llm: bool = False):
        """
        Initialize Strategy Agent.

        Args:
            enable_llm: If True, may consult LLM for ambiguous decisions
        """
        self.enable_llm = enable_llm
        self._cycle_counter = 0

    def decide(
        self,
        budget: int,
        niches: List[NicheMetrics],
        force_include: Optional[List[int]] = None,
    ) -> StrategyDecision:
        """
        Make strategic allocation decision.

        Args:
            budget: Total tokens available for this cycle
            niches: List of niche metrics to evaluate
            force_include: Niche IDs that must be scanned (user override)

        Returns:
            StrategyDecision with allocations and justifications
        """
        self._cycle_counter += 1
        cycle_id = self._generate_cycle_id()

        logger.info(f"Strategy cycle {cycle_id}: {len(niches)} niches, {budget} tokens")

        # Score and classify each niche
        scored_niches: List[Tuple[NicheMetrics, float]] = []
        for niche in niches:
            score = self._score_niche(niche)
            scored_niches.append((niche, score))

        # Sort by score descending
        scored_niches.sort(key=lambda x: x[1], reverse=True)

        # Classify into EXPLOIT / EXPLORE / PAUSE
        exploits: List[Tuple[NicheMetrics, float]] = []
        explores: List[Tuple[NicheMetrics, float]] = []
        pauses: List[Tuple[NicheMetrics, float]] = []

        for niche, score in scored_niches:
            # Force include override
            if force_include and niche.niche_id in force_include:
                exploits.append((niche, score))
                continue

            # Cold start protection
            if niche.total_runs < self.MIN_RUNS_BEFORE_PAUSE:
                explores.append((niche, score))
                continue

            # Classification by score
            if score > self.EXPLOIT_THRESHOLD:
                exploits.append((niche, score))
            elif score > self.EXPLORE_THRESHOLD:
                explores.append((niche, score))
            else:
                pauses.append((niche, score))

        # Maybe consult LLM for ambiguous cases
        llm_consulted = False
        llm_override_reason = None

        if self.enable_llm and self._has_ambiguous_cases(exploits, explores):
            llm_result = self._maybe_consult_llm(exploits, explores, budget)
            if llm_result:
                exploits, explores, llm_override_reason = llm_result
                llm_consulted = True

        # Calculate budget allocation
        budget_exploit = int(budget * self.EXPLOIT_RATIO)
        budget_explore = int(budget * self.EXPLORE_RATIO)
        budget_reserve = budget - budget_exploit - budget_explore

        # Allocate tokens to niches
        assessments = []
        risk_notes = []

        # Allocate EXPLOIT niches
        exploit_allocations = self._allocate_tokens(
            exploits, budget_exploit, status=NicheStatus.EXPLOIT
        )
        assessments.extend(exploit_allocations)

        # Allocate EXPLORE niches
        explore_allocations = self._allocate_tokens(
            explores, budget_explore, status=NicheStatus.EXPLORE
        )
        assessments.extend(explore_allocations)

        # Mark PAUSE niches (0 tokens)
        for niche, score in pauses:
            assessments.append(NicheAssessment(
                niche_id=niche.niche_id,
                name=niche.name,
                domain=niche.domain,
                status=NicheStatus.PAUSE,
                score=score,
                tokens_allocated=0,
                max_asins=0,
                justification=self._justify_pause(niche, score),
                confidence=1.0,
            ))

        # Generate risk notes
        risk_notes = self._generate_risk_notes(exploits, explores, pauses, budget)

        return StrategyDecision(
            cycle_id=cycle_id,
            decided_at=datetime.utcnow(),
            budget_total=budget,
            budget_exploit=budget_exploit,
            budget_explore=budget_explore,
            budget_reserve=budget_reserve,
            assessments=assessments,
            risk_notes=risk_notes,
            llm_consulted=llm_consulted,
            llm_override_reason=llm_override_reason,
        )

    def _score_niche(self, niche: NicheMetrics) -> float:
        """
        Compute composite score for a niche.

        Score components (weights sum to 1.0):
        - value_per_token: 40% — economic efficiency
        - density: 30% — opportunity conversion rate
        - freshness: 20% — staleness penalty/bonus
        - event_boost: 10% — recent critical events

        Returns:
            Score between 0 and 1
        """
        # Value per token (normalize to 0-1, assuming 100 EUR/1k tokens is excellent)
        value_score = min(1.0, niche.value_per_1k_tokens / 100)

        # Density (5% or higher is excellent)
        density_score = min(1.0, niche.density / self.DENSITY_GOOD)

        # Freshness (bonus for stale, penalty for very recent)
        if niche.days_since_scan >= self.STALE_DAYS:
            freshness_score = 0.8  # Needs refresh
        elif niche.days_since_scan >= 7:
            freshness_score = 0.5  # Normal
        else:
            freshness_score = 0.3  # Recently scanned, lower priority

        # Event boost
        if niche.recent_critical_events > 0:
            event_score = 1.0
        else:
            event_score = 0.0

        # Cold start bonus (new niches get exploration boost)
        if niche.total_runs == 0:
            cold_start_bonus = 0.3
        elif niche.total_runs < self.MIN_RUNS_BEFORE_PAUSE:
            cold_start_bonus = 0.15
        else:
            cold_start_bonus = 0.0

        # Weighted composite
        base_score = (
            value_score * 0.40 +
            density_score * 0.30 +
            freshness_score * 0.20 +
            event_score * 0.10
        )

        # Apply cold start bonus (additive, capped at 1.0)
        final_score = min(1.0, base_score + cold_start_bonus)

        # Apply event boost multiplier if critical events
        if niche.recent_critical_events > 0:
            final_score = min(1.0, final_score * self.EVENT_BOOST_MULTIPLIER)

        return final_score

    def _allocate_tokens(
        self,
        niches: List[Tuple[NicheMetrics, float]],
        budget: int,
        status: NicheStatus,
    ) -> List[NicheAssessment]:
        """
        Allocate tokens proportionally to niche scores.

        Args:
            niches: List of (niche, score) tuples
            budget: Total tokens to allocate
            status: EXPLOIT or EXPLORE

        Returns:
            List of NicheAssessment with allocations
        """
        if not niches or budget <= 0:
            return []

        assessments = []
        total_score = sum(score for _, score in niches)

        if total_score == 0:
            # Equal allocation if all scores are 0
            per_niche = budget // len(niches)
            for niche, score in niches:
                tokens = per_niche
                max_asins = self._tokens_to_asins(tokens)
                assessments.append(NicheAssessment(
                    niche_id=niche.niche_id,
                    name=niche.name,
                    domain=niche.domain,
                    status=status,
                    score=score,
                    tokens_allocated=tokens,
                    max_asins=max_asins,
                    justification=self._justify(niche, score, status),
                    confidence=1.0,
                ))
            return assessments

        # Proportional allocation
        for niche, score in niches:
            proportion = score / total_score
            tokens = int(budget * proportion)

            # Minimum allocation for cold start
            if niche.total_runs < self.MIN_RUNS_BEFORE_PAUSE:
                tokens = max(tokens, self.COLD_START_TOKENS)

            # Ensure at least some allocation if included
            tokens = max(tokens, 50)  # Minimum 50 tokens

            max_asins = self._tokens_to_asins(tokens)

            assessments.append(NicheAssessment(
                niche_id=niche.niche_id,
                name=niche.name,
                domain=niche.domain,
                status=status,
                score=score,
                tokens_allocated=tokens,
                max_asins=max_asins,
                justification=self._justify(niche, score, status),
                confidence=1.0,
            ))

        return assessments

    def _tokens_to_asins(self, tokens: int) -> int:
        """
        Convert token budget to max ASINs.

        Estimate: discovery ~5 tokens + ~2 tokens per ASIN
        """
        if tokens < 10:
            return 0
        return max(1, (tokens - 5) // 2)

    def _justify(self, niche: NicheMetrics, score: float, status: NicheStatus) -> str:
        """Generate human-readable justification."""
        parts = []

        if status == NicheStatus.EXPLOIT:
            parts.append(f"High score ({score:.2f})")
            if niche.density >= self.DENSITY_GOOD:
                parts.append(f"excellent density ({niche.density:.1%})")
            if niche.value_per_1k_tokens > 50:
                parts.append(f"good value ({niche.value_per_1k_tokens:.0f} EUR/1k tokens)")

        elif status == NicheStatus.EXPLORE:
            if niche.total_runs < self.MIN_RUNS_BEFORE_PAUSE:
                parts.append(f"cold start ({niche.total_runs} runs)")
            else:
                parts.append(f"testing hypothesis (score {score:.2f})")
            if niche.days_since_scan >= self.STALE_DAYS:
                parts.append("needs refresh")

        if niche.recent_critical_events > 0:
            parts.append(f"{niche.recent_critical_events} critical events")

        return "; ".join(parts) if parts else f"score {score:.2f}"

    def _justify_pause(self, niche: NicheMetrics, score: float) -> str:
        """Generate justification for PAUSE status."""
        parts = []

        if niche.density < self.DENSITY_BAD:
            parts.append(f"low density ({niche.density:.1%})")
        if niche.value_per_1k_tokens < 10:
            parts.append(f"low value ({niche.value_per_1k_tokens:.0f} EUR/1k tokens)")
        if score < self.EXPLORE_THRESHOLD:
            parts.append(f"score below threshold ({score:.2f})")

        return "; ".join(parts) if parts else "low priority"

    def _has_ambiguous_cases(
        self,
        exploits: List[Tuple[NicheMetrics, float]],
        explores: List[Tuple[NicheMetrics, float]],
    ) -> bool:
        """
        Check if there are ambiguous cases worth LLM consultation.

        Ambiguous = two niches with very close scores near threshold.
        """
        all_scored = exploits + explores
        if len(all_scored) < 2:
            return False

        # Check for score ties near threshold
        for i, (n1, s1) in enumerate(all_scored):
            for n2, s2 in all_scored[i+1:]:
                score_diff = abs(s1 - s2)
                near_threshold = (
                    abs(s1 - self.EXPLOIT_THRESHOLD) < 0.1 or
                    abs(s2 - self.EXPLOIT_THRESHOLD) < 0.1
                )
                if score_diff < 0.05 and near_threshold:
                    return True

        return False

    def _maybe_consult_llm(
        self,
        exploits: List[Tuple[NicheMetrics, float]],
        explores: List[Tuple[NicheMetrics, float]],
        budget: int,
    ) -> Optional[Tuple[List, List, str]]:
        """
        Optionally consult LLM for ambiguous allocation decisions.

        Returns:
            Tuple of (new_exploits, new_explores, override_reason) or None
        """
        if not self.enable_llm:
            return None

        # Check if LLM consultation is enabled via env
        # Support multiple key names: GPT_API_KEY, OPENAI_API_KEY, ANTHROPIC_API_KEY
        llm_api_key = os.getenv("GPT_API_KEY") or os.getenv("OPENAI_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
        if not llm_api_key:
            logger.debug("LLM consultation skipped: no API key configured (GPT_API_KEY, OPENAI_API_KEY, or ANTHROPIC_API_KEY)")
            return None

        try:
            return self._call_openai_for_decision(exploits, explores, budget, llm_api_key)
        except Exception as e:
            logger.warning(f"LLM consultation failed: {e}")
            return None

    def _call_openai_for_decision(
        self,
        exploits: List[Tuple[NicheMetrics, float]],
        explores: List[Tuple[NicheMetrics, float]],
        budget: int,
        api_key: str,
    ) -> Optional[Tuple[List, List, str]]:
        """
        Call OpenAI API to resolve ambiguous allocation decisions.

        Returns:
            Tuple of (new_exploits, new_explores, override_reason) or None
        """
        import json
        try:
            from openai import OpenAI
        except ImportError:
            logger.warning("OpenAI package not installed. Run: pip install openai")
            return None

        # Build context for LLM
        all_niches = exploits + explores
        niche_data = []
        for niche, score in all_niches:
            niche_data.append({
                "id": niche.niche_id,
                "name": niche.name,
                "domain": niche.domain,
                "score": round(score, 3),
                "current_status": "EXPLOIT" if (niche, score) in exploits else "EXPLORE",
                "metrics": {
                    "runs": niche.total_runs,
                    "density": f"{niche.density:.1%}",
                    "value_per_1k_tokens": round(niche.value_per_1k_tokens, 1),
                    "days_since_scan": niche.days_since_scan,
                    "critical_events": niche.recent_critical_events,
                }
            })

        prompt = f"""Tu es Strategy Agent pour Smartacus, un système de détection d'opportunités e-commerce.

CONTEXTE:
- Budget disponible: {budget} tokens
- Seuil EXPLOIT: score > 0.55
- Seuil EXPLORE: score > 0.25

NICHES À ÉVALUER (scores proches du seuil):
{json.dumps(niche_data, indent=2, ensure_ascii=False)}

QUESTION:
Certaines niches ont des scores très proches. Dois-je reclassifier certaines niches?
- Promouvoir un EXPLORE en EXPLOIT si les métriques justifient un investissement plus fort
- Rétrograder un EXPLOIT en EXPLORE si les risques sont trop élevés

RÉPONDS EN JSON STRICT:
{{
  "should_override": true/false,
  "changes": [
    {{"niche_id": 123, "new_status": "EXPLOIT", "reason": "..."}}
  ],
  "overall_reason": "Explication courte de la décision"
}}

Si aucun changement n'est nécessaire, réponds: {{"should_override": false, "changes": [], "overall_reason": "Classement déterministe correct"}}
"""

        client = OpenAI(api_key=api_key)

        logger.info("Consulting LLM for ambiguous allocation decision...")

        response = client.chat.completions.create(
            model="gpt-4o-mini",  # Cost-effective for simple decisions
            messages=[
                {"role": "system", "content": "Tu es un assistant d'allocation de ressources. Réponds uniquement en JSON valide."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,  # Low temperature for consistent decisions
            max_tokens=500,
        )

        result_text = response.choices[0].message.content.strip()

        # Parse JSON response
        # Handle markdown code blocks if present
        if result_text.startswith("```"):
            result_text = result_text.split("```")[1]
            if result_text.startswith("json"):
                result_text = result_text[4:]
            result_text = result_text.strip()

        result = json.loads(result_text)

        if not result.get("should_override", False):
            logger.info(f"LLM decision: No override needed - {result.get('overall_reason', 'N/A')}")
            return None

        # Apply changes
        new_exploits = list(exploits)
        new_explores = list(explores)

        for change in result.get("changes", []):
            niche_id = change["niche_id"]
            new_status = change["new_status"]

            # Find the niche in current lists
            for niche, score in exploits + explores:
                if niche.niche_id == niche_id:
                    if new_status == "EXPLOIT" and (niche, score) in new_explores:
                        new_explores.remove((niche, score))
                        new_exploits.append((niche, score))
                        logger.info(f"LLM override: {niche.name} EXPLORE -> EXPLOIT ({change.get('reason', 'N/A')})")
                    elif new_status == "EXPLORE" and (niche, score) in new_exploits:
                        new_exploits.remove((niche, score))
                        new_explores.append((niche, score))
                        logger.info(f"LLM override: {niche.name} EXPLOIT -> EXPLORE ({change.get('reason', 'N/A')})")
                    break

        return (new_exploits, new_explores, result.get("overall_reason", "LLM override"))

    def _generate_risk_notes(
        self,
        exploits: List[Tuple[NicheMetrics, float]],
        explores: List[Tuple[NicheMetrics, float]],
        pauses: List[Tuple[NicheMetrics, float]],
        budget: int,
    ) -> List[str]:
        """Generate risk notes for the decision."""
        notes = []

        # Risk: No exploit niches
        if not exploits:
            notes.append("WARNING: No high-confidence niches to exploit. Consider activating more categories.")

        # Risk: All niches paused
        if pauses and not exploits and not explores:
            notes.append("CRITICAL: All niches paused. System may miss opportunities.")

        # Risk: Budget too low
        if budget < 100:
            notes.append(f"LOW BUDGET: Only {budget} tokens available. Limited scanning possible.")

        # Risk: Stale data
        stale_count = sum(1 for n, _ in exploits + explores if n.days_since_scan >= self.STALE_DAYS)
        if stale_count > 0:
            notes.append(f"STALE DATA: {stale_count} niches haven't been scanned in {self.STALE_DAYS}+ days.")

        # Risk: Over-concentration
        if len(exploits) == 1 and not explores:
            notes.append("CONCENTRATION RISK: All tokens allocated to single niche.")

        # Hypothesis to invalidate
        for niche, score in explores:
            if niche.total_runs == 1:
                notes.append(f"HYPOTHESIS: {niche.name} ({niche.domain}) needs validation (1 run)")

        return notes

    def _generate_cycle_id(self) -> str:
        """Generate unique cycle ID."""
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        hash_input = f"{timestamp}_{self._cycle_counter}"
        short_hash = hashlib.md5(hash_input.encode()).hexdigest()[:6]
        return f"cycle_{timestamp}_{short_hash}"


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def load_niche_metrics_from_db(conn) -> List[NicheMetrics]:
    """
    Load niche metrics from database.

    Joins category_registry with category_performance and economic_events.
    """
    query = """
    WITH perf_agg AS (
        SELECT
            category_id,
            COUNT(*) as total_runs,
            COALESCE(SUM(asins_scored), 0) as total_asins_scanned,
            COALESCE(SUM(opportunities_found), 0) as total_opportunities,
            COALESCE(SUM(high_value_opps), 0) as high_value_opps,
            COALESCE(SUM(tokens_used), 0) as total_tokens_used,
            COALESCE(SUM(total_potential_value), 0) as total_value_detected,
            COALESCE(AVG(avg_score), 0) as avg_score
        FROM category_performance
        GROUP BY category_id
    ),
    recent_events AS (
        SELECT
            a.category_id,
            COUNT(*) as critical_events
        FROM economic_events e
        JOIN asins a ON e.asin = a.asin
        WHERE e.detected_at > NOW() - INTERVAL '7 days'
        AND e.urgency IN ('CRITICAL', 'HIGH')
        GROUP BY a.category_id
    )
    SELECT
        cr.category_id,
        cr.name,
        cr.amazon_domain,
        cr.is_active,
        cr.priority,
        cr.last_scanned_at,
        COALESCE(pa.total_runs, 0) as total_runs,
        COALESCE(pa.total_asins_scanned, 0) as total_asins_scanned,
        COALESCE(pa.total_opportunities, 0) as total_opportunities,
        COALESCE(pa.high_value_opps, 0) as high_value_opps,
        COALESCE(pa.total_tokens_used, 0) as total_tokens_used,
        COALESCE(pa.total_value_detected, 0) as total_value_detected,
        COALESCE(pa.avg_score, 0) as avg_score,
        COALESCE(re.critical_events, 0) as recent_critical_events
    FROM category_registry cr
    LEFT JOIN perf_agg pa ON cr.category_id = pa.category_id
    LEFT JOIN recent_events re ON cr.category_id = re.category_id
    WHERE cr.is_active = true
    ORDER BY cr.priority ASC, cr.last_scanned_at ASC NULLS FIRST;
    """

    with conn.cursor() as cur:
        cur.execute(query)
        rows = cur.fetchall()

    metrics = []
    for row in rows:
        metrics.append(NicheMetrics(
            niche_id=row[0],
            name=row[1],
            domain=row[2],
            is_active=row[3],
            priority=row[4],
            last_scanned_at=row[5],
            total_runs=row[6],
            total_asins_scanned=row[7],
            total_opportunities=row[8],
            high_value_opps=row[9],
            total_tokens_used=row[10],
            total_value_detected=float(row[11]) if row[11] else 0.0,
            avg_score=float(row[12]) if row[12] else 0.0,
            recent_critical_events=row[13],
        ))

    return metrics


def save_strategy_decision(conn, decision: StrategyDecision) -> None:
    """Save strategy decision to database for audit."""
    import json

    query = """
    INSERT INTO strategy_decisions (
        cycle_id, decided_at, budget_total, budget_exploit, budget_explore, budget_reserve,
        assessments, risk_notes, llm_consulted, llm_override_reason
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (cycle_id) DO NOTHING;
    """

    with conn.cursor() as cur:
        cur.execute(query, (
            decision.cycle_id,
            decision.decided_at,
            decision.budget_total,
            decision.budget_exploit,
            decision.budget_explore,
            decision.budget_reserve,
            json.dumps([a.__dict__ for a in decision.assessments], default=str),
            json.dumps(decision.risk_notes),
            decision.llm_consulted,
            decision.llm_override_reason,
        ))
    conn.commit()
