"""
Smartacus Scheduler V3.0
========================

Intelligent scheduling system for automated pipeline runs with:
- Monthly token budget management
- Category auto-discovery and prioritization
- Performance-based category selection
- **V3.0**: Strategy Agent for intelligent resource allocation
  - EXPLOIT/EXPLORE/PAUSE classification
  - Value-per-token optimization
  - Optional LLM consultation for ambiguous cases
"""

from .scheduler import SmartScheduler
from .category_discovery import CategoryDiscovery
from .token_budget import TokenBudgetManager
from .strategy_agent import StrategyAgent, NicheMetrics, NicheStatus, StrategyDecision

__all__ = [
    "SmartScheduler",
    "CategoryDiscovery",
    "TokenBudgetManager",
    "StrategyAgent",
    "NicheMetrics",
    "NicheStatus",
    "StrategyDecision",
]
