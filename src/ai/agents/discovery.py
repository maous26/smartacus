"""
Discovery Agent
===============

Agent #1 - PRIORITÉ MAXIMALE
"Si Discovery est faux, tout est faux."

Rôle :
- Présenter les opportunités détectées à l'utilisateur
- Expliquer pourquoi chaque opportunité existe
- Aider à qualifier et prioriser
- Répondre aux questions sur les opportunités

L'agent Discovery est le premier contact de l'utilisateur avec une opportunité.
Il doit être clair, convaincant, et honnête sur les risques.
"""

import logging
from typing import Dict, Any, Optional, List

from .base import (
    BaseAgent,
    AgentResponse,
    AgentContext,
    AgentType,
    AgentStatus,
)

logger = logging.getLogger(__name__)


DISCOVERY_SYSTEM_PROMPT = """Tu es l'Agent Discovery de Smartacus, un système de détection d'opportunités Amazon.

TON RÔLE :
Tu présentes des opportunités de produits à vendre sur Amazon FBA.
Tu expliques POURQUOI chaque opportunité existe et si elle vaut la peine d'être poursuivie.

TES PRINCIPES :
1. CLARTÉ : Explique simplement, même les concepts complexes
2. HONNÊTETÉ : Sois transparent sur les risques et incertitudes
3. PRAGMATISME : Focus sur l'actionnable, pas la théorie
4. CONVICTION : Si tu crois en l'opportunité, montre-le. Sinon, dis-le aussi.

FORMAT DE RÉPONSE :
- Sois conversationnel mais professionnel
- Utilise des chiffres concrets quand disponibles
- Structure tes réponses avec des points clés
- Propose toujours une prochaine action

CONTEXTE UTILISATEUR :
- Budget typique : 5-20k$ de stock initial
- Objectif : 20-40% de marge nette
- Niveau : débutant à intermédiaire en FBA

Tu parles en français."""


class DiscoveryAgent(BaseAgent):
    """
    Agent de découverte et qualification des opportunités.
    """

    agent_type = AgentType.DISCOVERY
    name = "Discovery Agent"
    description = "Détection et qualification des opportunités Amazon"

    @property
    def system_prompt(self) -> str:
        return DISCOVERY_SYSTEM_PROMPT

    async def present_opportunity(
        self,
        opportunity: Dict[str, Any],
        thesis: Optional[Dict[str, Any]],
        context: AgentContext,
    ) -> AgentResponse:
        """
        Présente une nouvelle opportunité à l'utilisateur.

        Args:
            opportunity: Données de l'opportunité
            thesis: Thèse économique générée
            context: Contexte de conversation

        Returns:
            AgentResponse avec la présentation
        """
        # Mettre à jour le contexte
        context.asin = opportunity.get("asin")
        context.opportunity_data = opportunity
        context.thesis = thesis
        context.current_stage = "discovery"

        # Construire le prompt de présentation
        prompt = f"""Présente cette opportunité à l'utilisateur de manière engageante et informative.

## Données Opportunité
- ASIN: {opportunity.get('asin')}
- Titre: {opportunity.get('title')}
- Prix Amazon: ${opportunity.get('amazon_price')}
- Score: {opportunity.get('final_score')}/100
- Fenêtre: {opportunity.get('window_days')} jours
- Urgence: {opportunity.get('urgency_level')}

## Thèse Économique
{thesis.get('headline') if thesis else 'Non disponible'}

{thesis.get('thesis') if thesis else ''}

## Points clés
{', '.join(thesis.get('reasoning', [])) if thesis else 'N/A'}

## Risques identifiés
{', '.join(thesis.get('risks', [])) if thesis else 'N/A'}

---

Génère une présentation conversationnelle qui :
1. Accroche l'attention avec le point le plus intéressant
2. Explique pourquoi cette opportunité existe
3. Donne les chiffres clés (prix, marge estimée, volume)
4. Mentionne les risques principaux
5. Propose une action (ex: "Veux-tu que je cherche des fournisseurs ?")"""

        try:
            response_text = await self._call_llm(prompt, context)

            # Déterminer les actions suggérées
            actions = [
                {
                    "action": "analyze_deeper",
                    "label": "Analyser en profondeur",
                    "description": "Obtenir plus de détails sur cette opportunité",
                },
                {
                    "action": "find_suppliers",
                    "label": "Chercher des fournisseurs",
                    "description": "Passer à l'étape sourcing",
                },
                {
                    "action": "skip",
                    "label": "Passer à la suivante",
                    "description": "Voir une autre opportunité",
                },
            ]

            # Ajouter le message à l'historique
            context.add_message("agent", response_text)

            return AgentResponse(
                message=response_text,
                suggested_actions=actions,
                data={"opportunity": opportunity, "thesis": thesis},
                agent_type=self.agent_type,
                status=AgentStatus.WAITING,
                requires_input=True,
            )

        except Exception as e:
            logger.error(f"Discovery agent error: {e}")
            return AgentResponse(
                message=f"Désolé, j'ai rencontré une erreur en analysant cette opportunité: {str(e)}",
                status=AgentStatus.ERROR,
                agent_type=self.agent_type,
            )

    async def process(
        self,
        user_input: str,
        context: AgentContext,
    ) -> AgentResponse:
        """
        Traite une question/réponse de l'utilisateur.
        """
        context.add_message("user", user_input)

        # Construire le prompt
        prompt = f"""L'utilisateur a dit : "{user_input}"

Contexte de l'opportunité actuelle :
- ASIN: {context.asin}
- Produit: {context.opportunity_data.get('title', 'Unknown')}
- Score: {context.opportunity_data.get('final_score', 'N/A')}/100

Thèse: {context.thesis.get('headline') if context.thesis else 'Non disponible'}

Réponds à l'utilisateur. Si sa question concerne :
- L'opportunité : fournis les détails demandés
- Les risques : sois honnête et complet
- L'action suivante : guide-le vers l'étape appropriée
- Autre chose : réponds au mieux

Si l'utilisateur veut avancer (sourcing, fournisseurs), indique qu'il peut passer à l'Agent Sourcing."""

        try:
            response_text = await self._call_llm(prompt, context)
            context.add_message("agent", response_text)

            # Détecter si l'utilisateur veut passer à l'étape suivante
            next_stage = None
            if any(kw in user_input.lower() for kw in ["fournisseur", "sourcing", "supplier", "alibaba", "commander"]):
                next_stage = "sourcing"

            return AgentResponse(
                message=response_text,
                agent_type=self.agent_type,
                status=AgentStatus.COMPLETED,
                next_stage=next_stage,
                requires_input=True,
            )

        except Exception as e:
            logger.error(f"Discovery process error: {e}")
            return AgentResponse(
                message=f"Erreur: {str(e)}",
                status=AgentStatus.ERROR,
                agent_type=self.agent_type,
            )

    async def compare_opportunities(
        self,
        opportunities: List[Dict[str, Any]],
        context: AgentContext,
    ) -> AgentResponse:
        """
        Compare plusieurs opportunités pour aider l'utilisateur à choisir.
        """
        if len(opportunities) < 2:
            return AgentResponse(
                message="Il faut au moins 2 opportunités pour comparer.",
                status=AgentStatus.ERROR,
                agent_type=self.agent_type,
            )

        # Formater les opportunités pour le prompt
        opps_text = "\n\n".join([
            f"""### Opportunité {i+1}: {opp.get('title', 'Unknown')[:50]}
- ASIN: {opp.get('asin')}
- Score: {opp.get('final_score')}/100
- Prix: ${opp.get('amazon_price')}
- Urgence: {opp.get('urgency_level')}
- Valeur estimée: ${opp.get('risk_adjusted_value', 0):,.0f}/an"""
            for i, opp in enumerate(opportunities[:5])
        ])

        prompt = f"""Compare ces opportunités et aide l'utilisateur à choisir.

{opps_text}

Donne :
1. Un classement avec justification
2. Le meilleur choix pour un débutant
3. Le meilleur choix pour maximiser le profit
4. Ta recommandation personnelle"""

        response_text = await self._call_llm(prompt, context)
        context.add_message("agent", response_text)

        return AgentResponse(
            message=response_text,
            agent_type=self.agent_type,
            status=AgentStatus.COMPLETED,
            data={"compared_opportunities": [o.get("asin") for o in opportunities]},
        )
