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
import json
import logging
import hashlib
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Literal, Tuple, Any
from enum import Enum

logger = logging.getLogger(__name__)


# =============================================================================
# LLM CONFIGURATION (normalized)
# =============================================================================

@dataclass
class LLMConfig:
    """Normalized LLM configuration."""
    provider: str = "openai"      # openai, anthropic
    model: str = "gpt-4o-mini"    # Model to use
    api_key: Optional[str] = None
    max_tokens: int = 500
    temperature: float = 0.1
    cache_ttl_hours: int = 24     # Cache TTL for responses

    @classmethod
    def from_env(cls) -> "LLMConfig":
        """Load LLM config from environment variables."""
        provider = os.getenv("LLM_PROVIDER", "openai").lower()
        model = os.getenv("LLM_MODEL", "gpt-4o-mini")

        # Find API key based on provider or fallback
        api_key = None
        if provider == "openai":
            api_key = os.getenv("GPT_API_KEY") or os.getenv("OPENAI_API_KEY")
        elif provider == "anthropic":
            api_key = os.getenv("ANTHROPIC_API_KEY")

        # Fallback: try all keys
        if not api_key:
            api_key = os.getenv("GPT_API_KEY") or os.getenv("OPENAI_API_KEY") or os.getenv("ANTHROPIC_API_KEY")

        return cls(
            provider=provider,
            model=model,
            api_key=api_key,
            max_tokens=int(os.getenv("LLM_MAX_TOKENS", "500")),
            temperature=float(os.getenv("LLM_TEMPERATURE", "0.1")),
            cache_ttl_hours=int(os.getenv("LLM_CACHE_TTL_HOURS", "24")),
        )


# =============================================================================
# LLM RESPONSE SCHEMA (strict)
# =============================================================================

LLM_RESPONSE_SCHEMA = {
    "type": "object",
    "required": ["should_override", "recommended_order", "rationale", "confidence"],
    "properties": {
        "should_override": {"type": "boolean"},
        "recommended_order": {
            "type": "array",
            "items": {"type": "integer"},
            "description": "Niche IDs in recommended priority order"
        },
        "rationale": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["niche_id", "reason_codes"],
                "properties": {
                    "niche_id": {"type": "integer"},
                    "new_status": {"type": "string", "enum": ["EXPLOIT", "EXPLORE", "PAUSE"]},
                    "reason_codes": {
                        "type": "array",
                        "items": {"type": "string", "enum": [
                            "HIGH_VALUE", "LOW_VALUE",
                            "HIGH_DENSITY", "LOW_DENSITY",
                            "STALE_DATA", "FRESH_DATA",
                            "CRITICAL_EVENT", "NO_DATA",
                            "COLD_START", "MATURE_NICHE"
                        ]}
                    },
                    "notes": {"type": "string"}
                }
            }
        },
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "disagreements": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Where LLM disagrees with deterministic algo"
        }
    }
}


# =============================================================================
# LLM RESPONSE CACHE (Redis-backed with in-memory fallback)
# =============================================================================

class LLMResponseCache:
    """
    Redis-backed cache for LLM responses with in-memory fallback.

    Uses Redis if available, otherwise falls back to in-memory cache.
    Cache keys are prefixed with 'llm:strategy:' for namespace isolation.
    """

    CACHE_PREFIX = "llm:strategy"

    def __init__(self):
        self._redis_cache = None
        self._memory_cache: Dict[str, Tuple[datetime, Dict]] = {}
        self._init_redis()

    def _init_redis(self) -> None:
        """Initialize Redis cache if available."""
        try:
            from src.cache import get_cache
            self._redis_cache = get_cache()
            logger.debug(f"LLM cache using backend: {self._redis_cache.get_stats()['backend']}")
        except ImportError:
            logger.debug("Redis cache module not available, using in-memory cache")
        except Exception as e:
            logger.warning(f"Failed to initialize Redis cache: {e}")

    def _compute_cache_key(
        self,
        niches: List["NicheMetrics"],
        budget: int,
        thresholds: Tuple[float, float],
    ) -> str:
        """Compute cache key from inputs."""
        # Sort niches by ID for deterministic hash
        niche_data = sorted([
            (n.niche_id, round(n.density, 4), round(n.value_per_1k_tokens, 2), n.total_runs)
            for n in niches
        ])
        key_input = json.dumps({
            "niches": niche_data,
            "budget": budget,
            "thresholds": thresholds,
            "version": "v1.0",  # Bump when algo changes
        }, sort_keys=True)
        return hashlib.sha256(key_input.encode()).hexdigest()[:16]

    def get(self, key: str, ttl_hours: int) -> Optional[Dict]:
        """Get cached response if valid."""
        full_key = f"{self.CACHE_PREFIX}:{key}"

        # Try Redis first
        if self._redis_cache:
            try:
                result = self._redis_cache.get(full_key)
                if result is not None:
                    logger.debug(f"Redis cache hit for {key}")
                    return result
            except Exception as e:
                logger.warning(f"Redis get failed: {e}")

        # Fallback to memory cache
        if key not in self._memory_cache:
            return None
        cached_at, response = self._memory_cache[key]
        if datetime.utcnow() - cached_at > timedelta(hours=ttl_hours):
            del self._memory_cache[key]
            return None
        return response

    def set(self, key: str, response: Dict, ttl_hours: int = 24) -> None:
        """Cache a response."""
        full_key = f"{self.CACHE_PREFIX}:{key}"

        # Try Redis first
        if self._redis_cache:
            try:
                self._redis_cache.set(full_key, response, ttl_hours=ttl_hours)
                logger.debug(f"Redis cache set for {key} (TTL: {ttl_hours}h)")
                return
            except Exception as e:
                logger.warning(f"Redis set failed: {e}")

        # Fallback to memory cache
        self._memory_cache[key] = (datetime.utcnow(), response)

    def clear(self) -> None:
        """Clear all cached responses."""
        # Clear Redis
        if self._redis_cache:
            try:
                self._redis_cache.clear_prefix(self.CACHE_PREFIX)
            except Exception as e:
                logger.warning(f"Redis clear failed: {e}")

        # Clear memory
        self._memory_cache.clear()

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        stats = {
            "memory_keys": len(self._memory_cache),
            "redis_available": self._redis_cache is not None,
        }
        if self._redis_cache:
            try:
                redis_stats = self._redis_cache.get_stats()
                stats["redis_backend"] = redis_stats.get("backend", "unknown")
                stats["redis_connected"] = redis_stats.get("connected", False)
            except Exception:
                pass
        return stats


# Global cache instance (singleton)
_llm_cache = LLMResponseCache()


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
class LLMMetrics:
    """Metrics for LLM consultation (for cost/impact tracking)."""
    provider: str = ""
    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_estimate_usd: float = 0.0
    latency_ms: int = 0
    cache_hit: bool = False
    changed_decision: bool = False


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
    llm_metrics: Optional[LLMMetrics] = None

    def to_dict(self) -> Dict:
        """Convert to dictionary for logging/storage."""
        result = {
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

        # Add LLM metrics if available
        if self.llm_metrics:
            result["llm_metrics"] = {
                "provider": self.llm_metrics.provider,
                "model": self.llm_metrics.model,
                "prompt_tokens": self.llm_metrics.prompt_tokens,
                "completion_tokens": self.llm_metrics.completion_tokens,
                "total_tokens": self.llm_metrics.total_tokens,
                "cost_estimate_usd": round(self.llm_metrics.cost_estimate_usd, 6),
                "latency_ms": self.llm_metrics.latency_ms,
                "cache_hit": self.llm_metrics.cache_hit,
                "changed_decision": self.llm_metrics.changed_decision,
            }

        return result


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

    def __init__(self, enable_llm: bool = False, llm_config: Optional[LLMConfig] = None):
        """
        Initialize Strategy Agent.

        Args:
            enable_llm: If True, may consult LLM for ambiguous decisions
            llm_config: Optional LLM configuration (loads from env if None)
        """
        self.enable_llm = enable_llm
        self.llm_config = llm_config or LLMConfig.from_env()
        self._cycle_counter = 0
        self._last_llm_metrics: Optional[LLMMetrics] = None

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
            llm_metrics=self._last_llm_metrics,
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

        Features:
        - Response caching by input hash
        - Strict JSON schema enforcement
        - Veto policy for hard limits
        - Cost/impact tracking

        Returns:
            Tuple of (new_exploits, new_explores, override_reason) or None
        """
        if not self.enable_llm:
            return None

        # Reset metrics
        self._last_llm_metrics = None

        # Check API key
        if not self.llm_config.api_key:
            logger.debug("LLM consultation skipped: no API key configured")
            return None

        # Check cache first
        all_niches = [n for n, _ in exploits + explores]
        cache_key = _llm_cache._compute_cache_key(
            all_niches, budget, (self.EXPLOIT_THRESHOLD, self.EXPLORE_THRESHOLD)
        )
        cached = _llm_cache.get(cache_key, self.llm_config.cache_ttl_hours)
        if cached:
            logger.info(f"LLM cache hit for key {cache_key}")
            self._last_llm_metrics = LLMMetrics(
                provider=self.llm_config.provider,
                model=self.llm_config.model,
                cache_hit=True,
                changed_decision=cached.get("should_override", False),
            )
            if cached.get("should_override"):
                return self._apply_llm_response(cached, exploits, explores, budget)
            return None

        try:
            return self._call_llm_for_decision(exploits, explores, budget, cache_key)
        except Exception as e:
            logger.warning(f"LLM consultation failed: {e}")
            return None

    def _call_llm_for_decision(
        self,
        exploits: List[Tuple[NicheMetrics, float]],
        explores: List[Tuple[NicheMetrics, float]],
        budget: int,
        cache_key: str,
    ) -> Optional[Tuple[List, List, str]]:
        """
        Call LLM API to resolve ambiguous allocation decisions.

        Features:
        - Strict JSON schema with reason_codes
        - Cost tracking
        - Veto policy enforcement
        - Response caching

        Returns:
            Tuple of (new_exploits, new_explores, override_reason) or None
        """
        import time
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

        # Build prompt with strict schema
        prompt = f"""Tu es Strategy Agent pour Smartacus, un système de détection d'opportunités e-commerce.

CONTEXTE:
- Budget disponible: {budget} tokens
- Seuil EXPLOIT: score > {self.EXPLOIT_THRESHOLD}
- Seuil EXPLORE: score > {self.EXPLORE_THRESHOLD}

NICHES À ÉVALUER:
{json.dumps(niche_data, indent=2, ensure_ascii=False)}

RÈGLES DE VETO (tu ne peux PAS violer):
- Tu ne peux PAS mettre en EXPLOIT une niche avec score < {self.EXPLORE_THRESHOLD} (hard floor)
- Tu ne peux PAS changer les quotas 70/20/10 exploit/explore/reserve
- Tu peux seulement RÉORDONNER ou RECLASSIFIER entre EXPLOIT et EXPLORE

QUESTION:
Dois-je ajuster le classement déterministe? Réponds UNIQUEMENT si tu identifies un problème clair.

RÉPONDS EN JSON STRICT (schéma obligatoire):
{{
  "should_override": false,
  "recommended_order": [niche_id1, niche_id2, ...],
  "rationale": [
    {{
      "niche_id": 123,
      "new_status": "EXPLOIT",
      "reason_codes": ["HIGH_VALUE", "CRITICAL_EVENT"],
      "notes": "Justification courte"
    }}
  ],
  "confidence": 0.8,
  "disagreements": ["Point de désaccord avec l'algo déterministe"]
}}

reason_codes valides: HIGH_VALUE, LOW_VALUE, HIGH_DENSITY, LOW_DENSITY, STALE_DATA, FRESH_DATA, CRITICAL_EVENT, NO_DATA, COLD_START, MATURE_NICHE

Si le classement déterministe est correct:
{{"should_override": false, "recommended_order": [], "rationale": [], "confidence": 1.0, "disagreements": []}}
"""

        client = OpenAI(api_key=self.llm_config.api_key)

        logger.info(f"Consulting LLM ({self.llm_config.model}) for ambiguous allocation...")
        start_time = time.time()

        response = client.chat.completions.create(
            model=self.llm_config.model,
            messages=[
                {"role": "system", "content": "Tu es un assistant d'allocation de ressources. Réponds UNIQUEMENT en JSON valide suivant le schéma demandé."},
                {"role": "user", "content": prompt}
            ],
            temperature=self.llm_config.temperature,
            max_tokens=self.llm_config.max_tokens,
        )

        latency_ms = int((time.time() - start_time) * 1000)

        # Extract usage and compute cost
        usage = response.usage
        prompt_tokens = usage.prompt_tokens if usage else 0
        completion_tokens = usage.completion_tokens if usage else 0
        total_tokens = prompt_tokens + completion_tokens

        # Cost estimation (gpt-4o-mini pricing as of 2024)
        # Input: $0.15/1M tokens, Output: $0.60/1M tokens
        cost_estimate = (prompt_tokens * 0.15 + completion_tokens * 0.60) / 1_000_000

        result_text = response.choices[0].message.content.strip()

        # Parse JSON response (handle markdown code blocks)
        if result_text.startswith("```"):
            result_text = result_text.split("```")[1]
            if result_text.startswith("json"):
                result_text = result_text[4:]
            result_text = result_text.strip()

        result = json.loads(result_text)

        # Cache the response (use configured TTL)
        _llm_cache.set(cache_key, result, ttl_hours=self.llm_config.cache_ttl_hours)

        # Track metrics
        changed_decision = result.get("should_override", False)
        self._last_llm_metrics = LLMMetrics(
            provider=self.llm_config.provider,
            model=self.llm_config.model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cost_estimate_usd=cost_estimate,
            latency_ms=latency_ms,
            cache_hit=False,
            changed_decision=changed_decision,
        )

        logger.info(f"LLM response: {total_tokens} tokens, ${cost_estimate:.6f}, {latency_ms}ms")

        if not changed_decision:
            logger.info(f"LLM decision: No override needed (confidence: {result.get('confidence', 'N/A')})")
            if result.get("disagreements"):
                for d in result["disagreements"]:
                    logger.debug(f"  LLM disagreement: {d}")
            return None

        # Apply with veto policy
        return self._apply_llm_response(result, exploits, explores, budget)

    def _apply_llm_response(
        self,
        result: Dict,
        exploits: List[Tuple[NicheMetrics, float]],
        explores: List[Tuple[NicheMetrics, float]],
        budget: int,
    ) -> Optional[Tuple[List, List, str]]:
        """
        Apply LLM response with veto policy enforcement.

        Veto rules:
        - Cannot promote to EXPLOIT if score < EXPLORE_THRESHOLD
        - Cannot change budget allocation ratios
        - Can only reorder/reclassify between EXPLOIT and EXPLORE
        """
        new_exploits = list(exploits)
        new_explores = list(explores)
        vetoed_count = 0

        for change in result.get("rationale", []):
            niche_id = change.get("niche_id")
            new_status = change.get("new_status")
            reason_codes = change.get("reason_codes", [])

            if not niche_id or not new_status:
                continue

            # Find the niche
            found_niche = None
            found_score = 0
            for niche, score in exploits + explores:
                if niche.niche_id == niche_id:
                    found_niche = niche
                    found_score = score
                    break

            if not found_niche:
                logger.warning(f"LLM referenced unknown niche_id: {niche_id}")
                continue

            # VETO CHECK: Cannot promote to EXPLOIT if score too low
            if new_status == "EXPLOIT" and found_score < self.EXPLORE_THRESHOLD:
                logger.warning(f"VETO: Cannot promote {found_niche.name} to EXPLOIT (score {found_score:.2f} < {self.EXPLORE_THRESHOLD})")
                vetoed_count += 1
                continue

            # Apply change
            if new_status == "EXPLOIT" and (found_niche, found_score) in new_explores:
                new_explores.remove((found_niche, found_score))
                new_exploits.append((found_niche, found_score))
                logger.info(f"LLM override: {found_niche.name} EXPLORE -> EXPLOIT ({reason_codes})")
            elif new_status == "EXPLORE" and (found_niche, found_score) in new_exploits:
                new_exploits.remove((found_niche, found_score))
                new_explores.append((found_niche, found_score))
                logger.info(f"LLM override: {found_niche.name} EXPLOIT -> EXPLORE ({reason_codes})")

        if vetoed_count > 0:
            logger.warning(f"Vetoed {vetoed_count} LLM recommendations")

        # Build overall reason
        overall_reason = f"LLM override (confidence: {result.get('confidence', 'N/A')})"
        if result.get("disagreements"):
            overall_reason += f" - Disagreements: {', '.join(result['disagreements'][:2])}"

        return (new_exploits, new_explores, overall_reason)

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
