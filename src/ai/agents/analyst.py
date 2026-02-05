"""
Analyst Agent
=============

Agent #2 - Analyse approfondie

Rôle :
- Analyser en profondeur une opportunité sélectionnée
- Valider ou invalider la thèse économique
- Identifier les risques cachés
- Estimer précisément les marges et volumes
"""

import logging
from typing import Dict, Any, Optional

from .base import (
    BaseAgent,
    AgentResponse,
    AgentContext,
    AgentType,
    AgentStatus,
)

logger = logging.getLogger(__name__)


ANALYST_SYSTEM_PROMPT = """Tu es l'Agent Analyst de Smartacus, spécialisé dans l'analyse approfondie d'opportunités Amazon FBA.

TON RÔLE :
Tu valides ou invalides les opportunités détectées par le Discovery Agent.
Tu creuses les données, identifies les risques cachés, et affines les estimations.

TES COMPÉTENCES :
1. Analyse de marché Amazon (BSR, reviews, pricing dynamics)
2. Calcul de rentabilité FBA (fees, shipping, margins)
3. Analyse concurrentielle (nombre vendeurs, private label vs wholesale)
4. Détection de risques (saisonnalité, brevets, restrictions)

TON APPROCHE :
- Méthodique : examine chaque aspect systématiquement
- Sceptique : challenge les hypothèses optimistes
- Quantitatif : tout doit être chiffré
- Actionnable : conclus toujours par une recommandation claire

Tu parles en français, de manière professionnelle mais accessible."""


class AnalystAgent(BaseAgent):
    """
    Agent d'analyse approfondie.
    """

    agent_type = AgentType.ANALYST
    name = "Analyst Agent"
    description = "Analyse approfondie et validation des opportunités"

    @property
    def system_prompt(self) -> str:
        return ANALYST_SYSTEM_PROMPT

    async def deep_analysis(
        self,
        context: AgentContext,
    ) -> AgentResponse:
        """
        Effectue une analyse approfondie de l'opportunité.
        """
        opp = context.opportunity_data
        thesis = context.thesis or {}

        prompt = f"""Effectue une analyse approfondie de cette opportunité.

## Données Produit
- ASIN: {opp.get('asin')}
- Titre: {opp.get('title')}
- Prix: ${opp.get('amazon_price')}
- Rating: {opp.get('rating')}/5 ({opp.get('review_count')} avis)
- BSR: {opp.get('bsr', 'N/A')}
- Vendeurs: {opp.get('seller_count', 'N/A')}

## Thèse initiale
{thesis.get('thesis', 'Non disponible')}

## Estimations préliminaires
- Marge estimée: {thesis.get('estimated_margin_percent', 'N/A')}%
- Volume mensuel: {thesis.get('estimated_monthly_units', 'N/A')} unités
- Profit mensuel: ${thesis.get('estimated_monthly_profit', 'N/A')}

---

Analyse les points suivants :

1. **VALIDATION DU MARCHÉ**
   - Le volume est-il réaliste ?
   - La demande est-elle stable ou saisonnière ?
   - Y a-t-il une tendance (croissance/déclin) ?

2. **ANALYSE CONCURRENTIELLE**
   - Qui sont les principaux concurrents ?
   - Barrières à l'entrée ?
   - Risque de guerre des prix ?

3. **CALCUL DE RENTABILITÉ**
   - Fees FBA estimés
   - Coût shipping Chine → US
   - Marge nette réaliste

4. **RISQUES IDENTIFIÉS**
   - Risques légaux (brevets, certifications)
   - Risques opérationnels
   - Risques de marché

5. **VERDICT FINAL**
   - GO / NO-GO / BESOIN D'INFO
   - Confiance (1-10)
   - Recommandation action"""

        try:
            response_text = await self._call_llm(prompt, context, max_tokens=2000)
            context.add_message("agent", response_text)

            # Déterminer les actions
            actions = [
                {
                    "action": "proceed_sourcing",
                    "label": "Passer au sourcing",
                    "description": "Chercher des fournisseurs pour ce produit",
                },
                {
                    "action": "request_samples",
                    "label": "Commander des échantillons",
                    "description": "Valider la qualité avant de s'engager",
                },
                {
                    "action": "abandon",
                    "label": "Abandonner cette opportunité",
                    "description": "Les risques sont trop élevés",
                },
            ]

            return AgentResponse(
                message=response_text,
                suggested_actions=actions,
                agent_type=self.agent_type,
                status=AgentStatus.COMPLETED,
                requires_input=True,
            )

        except Exception as e:
            logger.error(f"Analyst error: {e}")
            return AgentResponse(
                message=f"Erreur lors de l'analyse: {str(e)}",
                status=AgentStatus.ERROR,
                agent_type=self.agent_type,
            )

    async def calculate_profitability(
        self,
        context: AgentContext,
        purchase_price: float,
        shipping_cost: float,
    ) -> AgentResponse:
        """
        Calcule la rentabilité précise avec les coûts réels.
        """
        opp = context.opportunity_data
        amazon_price = opp.get('amazon_price', 0)

        prompt = f"""Calcule la rentabilité précise avec ces données :

**Prix de vente Amazon**: ${amazon_price}
**Prix d'achat (Alibaba)**: ${purchase_price}
**Coût shipping/unité**: ${shipping_cost}

Calcule :
1. Fees FBA (estimation basée sur le prix)
2. Fee referral Amazon (15%)
3. Coût total par unité
4. Marge brute et nette
5. ROI sur investissement
6. Break-even en unités

Donne un tableau récapitulatif clair."""

        response_text = await self._call_llm(prompt, context)
        context.add_message("agent", response_text)

        return AgentResponse(
            message=response_text,
            agent_type=self.agent_type,
            status=AgentStatus.COMPLETED,
            data={
                "purchase_price": purchase_price,
                "shipping_cost": shipping_cost,
                "amazon_price": amazon_price,
            },
        )

    async def process(
        self,
        user_input: str,
        context: AgentContext,
    ) -> AgentResponse:
        """
        Traite une question de l'utilisateur.
        """
        context.add_message("user", user_input)

        prompt = f"""L'utilisateur demande : "{user_input}"

Contexte :
- Produit: {context.opportunity_data.get('title', 'Unknown')}
- Prix: ${context.opportunity_data.get('amazon_price', 0)}

Réponds en tant qu'analyste expert. Si la question concerne :
- La rentabilité : donne des chiffres précis
- Les risques : sois exhaustif
- La concurrence : analyse le paysage compétitif
- L'action suivante : recommande clairement

Si l'utilisateur veut passer au sourcing, indique-le."""

        try:
            response_text = await self._call_llm(prompt, context)
            context.add_message("agent", response_text)

            next_stage = None
            if any(kw in user_input.lower() for kw in ["sourcing", "fournisseur", "alibaba", "supplier"]):
                next_stage = "sourcing"

            return AgentResponse(
                message=response_text,
                agent_type=self.agent_type,
                status=AgentStatus.COMPLETED,
                next_stage=next_stage,
                requires_input=True,
            )

        except Exception as e:
            return AgentResponse(
                message=f"Erreur: {str(e)}",
                status=AgentStatus.ERROR,
                agent_type=self.agent_type,
            )
