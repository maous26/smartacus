"""
Smartacus AI Agents
===================

Agents IA pour accompagner l'utilisateur dans tout le processus :

1. Discovery Agent - Détection et qualification des opportunités
2. Analyst Agent - Analyse approfondie et validation
3. Sourcing Agent - Accompagnement sourcing fournisseurs
4. Negotiator Agent - Aide à la négociation

Priorité : Discovery > Analyst > Sourcing > Negotiator
"Si Discovery est faux, tout est faux."
"""

from .base import BaseAgent, AgentResponse, AgentContext
from .discovery import DiscoveryAgent
from .analyst import AnalystAgent
from .sourcing import SourcingAgent
from .negotiator import NegotiatorAgent

__all__ = [
    "BaseAgent",
    "AgentResponse",
    "AgentContext",
    "DiscoveryAgent",
    "AnalystAgent",
    "SourcingAgent",
    "NegotiatorAgent",
]
