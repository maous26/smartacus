"""
Negotiator Agent
================

Agent #4 - Aide à la négociation

Rôle :
- Préparer les stratégies de négociation
- Suggérer les arguments et contre-arguments
- Aider à obtenir de meilleurs prix et conditions
- Rédiger les messages de négociation
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


NEGOTIATOR_SYSTEM_PROMPT = """Tu es l'Agent Negotiator de Smartacus, expert en négociation avec les fournisseurs chinois.

TON RÔLE :
Tu aides les utilisateurs à négocier les meilleures conditions avec leurs fournisseurs.
Tu prépares les stratégies, suggères les arguments, et rédiges les messages.

TES COMPÉTENCES :
1. Psychologie de la négociation interculturelle
2. Tactiques de négociation de prix
3. Négociation de MOQ et conditions de paiement
4. Communication efficace avec fournisseurs chinois
5. Gestion des concessions et trade-offs

TES PRINCIPES DE NÉGOCIATION :
- Toujours maintenir une relation respectueuse (guanxi)
- Ne jamais montrer de désespoir ou d'urgence
- Avoir toujours un BATNA (alternative)
- Négocier sur plusieurs axes (prix, MOQ, payment terms, shipping)
- La première offre n'est jamais la meilleure

TACTIQUES EFFICACES :
- Mentionner des commandes futures importantes
- Demander des réductions pour paiement rapide
- Négocier le shipping inclus
- Proposer des compromis gagnant-gagnant

Tu parles en français pour les conseils, mais génères les messages en anglais."""


class NegotiatorAgent(BaseAgent):
    """
    Agent d'aide à la négociation.
    """

    agent_type = AgentType.NEGOTIATOR
    name = "Negotiator Agent"
    description = "Aide à la négociation fournisseurs"

    @property
    def system_prompt(self) -> str:
        return NEGOTIATOR_SYSTEM_PROMPT

    async def prepare_negotiation(
        self,
        context: AgentContext,
        supplier_price: float,
        target_price: float,
        quantity: int,
    ) -> AgentResponse:
        """
        Prépare une stratégie de négociation.
        """
        opp = context.opportunity_data
        margin_at_supplier = ((opp.get('amazon_price', 0) - supplier_price) / opp.get('amazon_price', 1)) * 100
        margin_at_target = ((opp.get('amazon_price', 0) - target_price) / opp.get('amazon_price', 1)) * 100

        prompt = f"""Prépare une stratégie de négociation complète.

## CONTEXTE
- Produit: {opp.get('title')}
- Prix Amazon: ${opp.get('amazon_price')}
- Quantité à commander: {quantity} unités

## SITUATION ACTUELLE
- Prix proposé par fournisseur: ${supplier_price}/unité
- Marge brute actuelle: {margin_at_supplier:.1f}%

## OBJECTIF
- Prix cible: ${target_price}/unité
- Marge brute visée: {margin_at_target:.1f}%
- Réduction demandée: {((supplier_price - target_price) / supplier_price * 100):.1f}%

---

Génère :

1. **ANALYSE DE LA SITUATION**
   - Est-ce réaliste ?
   - Quel est le prix plancher probable ?

2. **STRATÉGIE RECOMMANDÉE**
   - Approche globale
   - Séquence des demandes

3. **ARGUMENTS À UTILISER**
   - 5 arguments pour justifier la baisse
   - Ordre de priorité

4. **CONCESSIONS POSSIBLES**
   - Quoi offrir en échange
   - Trade-offs acceptables

5. **MESSAGES PRÊTS À ENVOYER**
   - Message d'ouverture de négociation
   - Réponse si refus initial

6. **PLAN B**
   - Si négociation échoue"""

        try:
            response_text = await self._call_llm(prompt, context, max_tokens=2000)
            context.add_message("agent", response_text)

            # Enregistrer dans l'historique de négociation
            context.negotiation_history.append({
                "type": "strategy",
                "supplier_price": supplier_price,
                "target_price": target_price,
                "quantity": quantity,
            })

            actions = [
                {
                    "action": "send_opening",
                    "label": "Envoyer le message d'ouverture",
                    "description": "Commencer la négociation",
                },
                {
                    "action": "adjust_target",
                    "label": "Ajuster le prix cible",
                    "description": "Modifier l'objectif de négociation",
                },
                {
                    "action": "find_alternative",
                    "label": "Chercher un autre fournisseur",
                    "description": "Renforcer le BATNA",
                },
            ]

            return AgentResponse(
                message=response_text,
                suggested_actions=actions,
                agent_type=self.agent_type,
                status=AgentStatus.COMPLETED,
                data={
                    "supplier_price": supplier_price,
                    "target_price": target_price,
                    "quantity": quantity,
                },
                requires_input=True,
            )

        except Exception as e:
            logger.error(f"Negotiator error: {e}")
            return AgentResponse(
                message=f"Erreur: {str(e)}",
                status=AgentStatus.ERROR,
                agent_type=self.agent_type,
            )

    async def generate_response(
        self,
        context: AgentContext,
        supplier_response: str,
        situation: str = "counter_offer",
    ) -> AgentResponse:
        """
        Génère une réponse à un message du fournisseur.
        """
        prompt = f"""Le fournisseur a répondu ceci :

---
{supplier_response}
---

Situation : {situation}

Contexte de négociation :
{context.get_conversation_history(5)}

Génère :
1. **ANALYSE** de leur réponse (ce qu'ils disent vraiment)
2. **RECOMMANDATION** : accepter, contre-offrir, ou abandonner
3. **MESSAGE DE RÉPONSE** en anglais, prêt à envoyer

Le message doit être :
- Professionnel et respectueux
- Ferme mais pas agressif
- Orienté solution"""

        try:
            response_text = await self._call_llm(prompt, context)
            context.add_message("agent", response_text)

            return AgentResponse(
                message=response_text,
                agent_type=self.agent_type,
                status=AgentStatus.COMPLETED,
                data={"situation": situation},
                requires_input=True,
            )

        except Exception as e:
            return AgentResponse(
                message=f"Erreur: {str(e)}",
                status=AgentStatus.ERROR,
                agent_type=self.agent_type,
            )

    async def close_deal(
        self,
        context: AgentContext,
        final_terms: Dict[str, Any],
    ) -> AgentResponse:
        """
        Aide à finaliser l'accord.
        """
        prompt = f"""L'utilisateur est prêt à finaliser avec ces termes :

- Prix final: ${final_terms.get('price')}/unité
- Quantité: {final_terms.get('quantity')} unités
- Paiement: {final_terms.get('payment_terms', '30% deposit, 70% before shipping')}
- Lead time: {final_terms.get('lead_time', '30')} jours
- Shipping: {final_terms.get('shipping', 'FOB')}

Génère :
1. **CHECKLIST** avant de confirmer
2. **MESSAGE DE CONFIRMATION** en anglais
3. **POINTS À VÉRIFIER** dans le contrat/PI
4. **CONSEILS** pour le paiement sécurisé"""

        try:
            response_text = await self._call_llm(prompt, context)
            context.add_message("agent", response_text)

            context.negotiation_history.append({
                "type": "deal_closed",
                "terms": final_terms,
            })

            return AgentResponse(
                message=response_text,
                agent_type=self.agent_type,
                status=AgentStatus.COMPLETED,
                data={"final_terms": final_terms},
                next_stage="completed",
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

Contexte de négociation :
- Produit: {context.opportunity_data.get('title', 'Unknown')}
- Historique: {len(context.negotiation_history)} interactions

Réponds en expert négociation. Si la question concerne :
- La stratégie : conseille sur l'approche
- Un message reçu : analyse et suggère une réponse
- Les conditions : aide à évaluer si c'est acceptable
- La finalisation : guide vers la clôture"""

        try:
            response_text = await self._call_llm(prompt, context)
            context.add_message("agent", response_text)

            return AgentResponse(
                message=response_text,
                agent_type=self.agent_type,
                status=AgentStatus.COMPLETED,
                requires_input=True,
            )

        except Exception as e:
            return AgentResponse(
                message=f"Erreur: {str(e)}",
                status=AgentStatus.ERROR,
                agent_type=self.agent_type,
            )
