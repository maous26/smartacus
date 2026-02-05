"""
Sourcing Agent
==============

Agent #3 - Accompagnement sourcing fournisseurs

Rôle :
- Identifier des fournisseurs potentiels (Alibaba, 1688, etc.)
- Évaluer la fiabilité des fournisseurs
- Guider la demande d'échantillons
- Préparer les questions pour les fournisseurs
"""

import logging
from typing import Dict, Any, List, Optional

from .base import (
    BaseAgent,
    AgentResponse,
    AgentContext,
    AgentType,
    AgentStatus,
)

logger = logging.getLogger(__name__)


SOURCING_SYSTEM_PROMPT = """Tu es l'Agent Sourcing de Smartacus, expert en approvisionnement depuis la Chine pour Amazon FBA.

TON RÔLE :
Tu aides les utilisateurs à trouver et évaluer des fournisseurs pour leurs produits.
Tu guides tout le processus de sourcing, de la recherche à la commande.

TES COMPÉTENCES :
1. Recherche de fournisseurs (Alibaba, 1688, Global Sources)
2. Évaluation de fiabilité (Trade Assurance, certifications, historique)
3. Communication avec fournisseurs chinois
4. Négociation de prix et MOQ
5. Contrôle qualité et échantillons

TES CONSEILS CLÉS :
- Toujours demander des échantillons avant une grosse commande
- Vérifier Trade Assurance et années d'activité
- Comparer au moins 3-5 fournisseurs
- Attention aux prix trop bas (qualité douteuse)
- Prévoir 30-45 jours de lead time

Tu parles en français, de manière pratique et directe."""


class SourcingAgent(BaseAgent):
    """
    Agent de sourcing et accompagnement fournisseurs.
    """

    agent_type = AgentType.SOURCING
    name = "Sourcing Agent"
    description = "Accompagnement sourcing fournisseurs"

    @property
    def system_prompt(self) -> str:
        return SOURCING_SYSTEM_PROMPT

    async def find_suppliers(
        self,
        context: AgentContext,
    ) -> AgentResponse:
        """
        Guide la recherche de fournisseurs pour le produit.
        """
        opp = context.opportunity_data
        product_title = opp.get('title', 'Unknown Product')

        prompt = f"""L'utilisateur cherche des fournisseurs pour ce produit :

**Produit**: {product_title}
**ASIN**: {opp.get('asin')}
**Prix Amazon**: ${opp.get('amazon_price')}

Guide l'utilisateur pour trouver des fournisseurs :

1. **MOTS-CLÉS DE RECHERCHE**
   - Suggère 3-5 termes de recherche en anglais pour Alibaba
   - Inclus des variantes (OEM, wholesale, manufacturer)

2. **CRITÈRES DE SÉLECTION**
   - Trade Assurance : obligatoire ou non ?
   - Années minimum d'activité
   - Certifications requises (CE, FCC, etc.)
   - MOQ acceptable

3. **QUESTIONS À POSER**
   - Liste 5 questions essentielles pour les fournisseurs

4. **RED FLAGS**
   - Signaux d'alerte à surveiller

5. **ESTIMATION PRIX**
   - Fourchette de prix attendue
   - Coût shipping estimé

Termine par une action concrète (ex: "Commence par chercher sur Alibaba avec...")"""

        try:
            response_text = await self._call_llm(prompt, context, max_tokens=1500)
            context.add_message("agent", response_text)

            actions = [
                {
                    "action": "search_alibaba",
                    "label": "Ouvrir Alibaba",
                    "description": "Lancer la recherche sur Alibaba",
                    "url": f"https://www.alibaba.com/trade/search?SearchText={product_title.replace(' ', '+')}",
                },
                {
                    "action": "generate_message",
                    "label": "Générer un message fournisseur",
                    "description": "Créer un template de premier contact",
                },
                {
                    "action": "compare_suppliers",
                    "label": "Comparer des fournisseurs",
                    "description": "Évaluer plusieurs fournisseurs",
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
            logger.error(f"Sourcing error: {e}")
            return AgentResponse(
                message=f"Erreur: {str(e)}",
                status=AgentStatus.ERROR,
                agent_type=self.agent_type,
            )

    async def generate_supplier_message(
        self,
        context: AgentContext,
        quantity: int = 500,
    ) -> AgentResponse:
        """
        Génère un template de message pour contacter un fournisseur.
        """
        opp = context.opportunity_data

        prompt = f"""Génère un message professionnel pour contacter un fournisseur Alibaba.

**Produit recherché**: {opp.get('title')}
**Quantité initiale**: {quantity} unités
**Destination**: USA (Amazon FBA)

Le message doit :
1. Être professionnel mais amical
2. Montrer qu'on est un acheteur sérieux
3. Demander les informations clés (prix, MOQ, lead time)
4. Mentionner qu'on veut des échantillons
5. Être en anglais (pour les fournisseurs chinois)

Format : prêt à copier-coller."""

        try:
            response_text = await self._call_llm(prompt, context)
            context.add_message("agent", response_text)

            return AgentResponse(
                message=response_text,
                agent_type=self.agent_type,
                status=AgentStatus.COMPLETED,
                data={"template_type": "supplier_contact", "quantity": quantity},
            )

        except Exception as e:
            return AgentResponse(
                message=f"Erreur: {str(e)}",
                status=AgentStatus.ERROR,
                agent_type=self.agent_type,
            )

    async def evaluate_supplier(
        self,
        context: AgentContext,
        supplier_info: Dict[str, Any],
    ) -> AgentResponse:
        """
        Évalue un fournisseur spécifique.
        """
        prompt = f"""Évalue ce fournisseur Alibaba :

**Nom**: {supplier_info.get('name', 'Unknown')}
**Années d'activité**: {supplier_info.get('years', 'Unknown')}
**Trade Assurance**: {supplier_info.get('trade_assurance', 'Unknown')}
**Certifications**: {supplier_info.get('certifications', 'Unknown')}
**Prix proposé**: ${supplier_info.get('price', 'Unknown')}/unité
**MOQ**: {supplier_info.get('moq', 'Unknown')} unités
**Lead time**: {supplier_info.get('lead_time', 'Unknown')} jours

Analyse :
1. Score de fiabilité (1-10)
2. Points forts
3. Points faibles / red flags
4. Questions à poser avant de commander
5. Recommandation : GO / PRUDENCE / NO-GO"""

        try:
            response_text = await self._call_llm(prompt, context)
            context.add_message("agent", response_text)

            # Stocker l'évaluation
            context.sourcing_options.append({
                "supplier": supplier_info,
                "evaluation": response_text,
            })

            return AgentResponse(
                message=response_text,
                agent_type=self.agent_type,
                status=AgentStatus.COMPLETED,
                data={"supplier_evaluated": supplier_info.get('name')},
            )

        except Exception as e:
            return AgentResponse(
                message=f"Erreur: {str(e)}",
                status=AgentStatus.ERROR,
                agent_type=self.agent_type,
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
- Étape: Sourcing fournisseurs

Réponds en expert sourcing. Si la question concerne :
- La recherche de fournisseurs : guide précisément
- L'évaluation d'un fournisseur : analyse les critères
- Les prix/négociation : donne des conseils tactiques
- Les échantillons : explique le processus

Si l'utilisateur est prêt à négocier, suggère de passer à l'Agent Negotiator."""

        try:
            response_text = await self._call_llm(prompt, context)
            context.add_message("agent", response_text)

            next_stage = None
            if any(kw in user_input.lower() for kw in ["négocier", "négociation", "prix final", "negotiate"]):
                next_stage = "negotiator"

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
