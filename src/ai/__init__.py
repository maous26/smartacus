"""
Smartacus AI Module
===================

Intelligence artificielle au cœur de Smartacus :
- LLM pour génération de thèses économiques
- Agents IA pour accompagnement utilisateur
- Analyse de reviews et sentiments
"""

from .thesis_generator import ThesisGenerator
from .agents import DiscoveryAgent, AnalystAgent, SourcingAgent, NegotiatorAgent

__all__ = [
    "ThesisGenerator",
    "DiscoveryAgent",
    "AnalystAgent",
    "SourcingAgent",
    "NegotiatorAgent",
]
