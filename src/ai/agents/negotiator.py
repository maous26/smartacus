"""
Negotiator Agent
================

Agent #4 - Aide a la negociation

Role :
- Preparer les strategies de negociation
- Suggerer les arguments et contre-arguments
- Aider a obtenir de meilleurs prix et conditions
- Rediger les messages de negociation
- Exploiter les donnees economiques et review intelligence comme leviers
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


NEGOTIATOR_SYSTEM_PROMPT = """Tu es l'Agent Negotiator de Smartacus, expert en negociation avec les fournisseurs chinois, specialise dans la niche **Car Phone Mounts / Supports Telephone Voiture**.

TON ROLE :
Tu aides les utilisateurs a negocier les meilleures conditions avec leurs fournisseurs.
Tu prepares les strategies, suggeres les arguments, et rediges les messages.
Tu utilises les donnees economiques reelles comme leviers de negociation.

## STRUCTURE DE COUTS REELLE — Car Phone Mounts (Amazon FBA FR, prix en EUR)

### Couts incompressibles par unite
- **Referral fee** : 15% du prix de vente
- **FBA fulfillment FR** : 3.00-4.50 EUR (petit/leger)
- **Shipping Chine→EU** : 2-4 EUR/unite (sea freight 40-55j via port EU)
- **Emballage/etiquetage** : 0.30-0.80 EUR/unite
- **Inspection QC** : 0.10-0.20 EUR/unite (amortie sur le lot)
- **TVA import** : 20% sur valeur en douane

### Regle du quart
Prix HT / 4 = COGS maximum pour atteindre ~25% marge nette
Ex: 19.99 EUR TTC → 16.66 EUR HT → COGS max 4.17 EUR

### Prix typiques fournisseurs (2024-2025, en EUR)
- Ventouse/grille simple : 1.50-3.00 EUR
- MagSafe / aimant N52 : 3.00-6.00 EUR
- Wireless charging Qi : 5.00-9.00 EUR
- Motorise/auto-clamp : 6.00-12.00 EUR

### Leviers de negociation
- Volume : -10 a -20% entre 500 et 2000 unites
- Paiement rapide : -3 a -5% pour 100% upfront (vs 30/70)
- Relation long terme : -5 a -10% a partir de la 3e commande
- Shipping inclus FOB→CIF : economise 1-2 EUR/unite
- Commande reguliere : planifier 3 commandes/an = meilleur prix

## PRINCIPES DE NEGOCIATION :
- Respecter la relation (guanxi) — toujours courtois
- Ne jamais montrer de desperation ou d'urgence
- Avoir un BATNA (autre fournisseur en backup)
- Negocier sur plusieurs axes (prix, MOQ, payment, shipping, QC)
- La premiere offre n'est JAMAIS la meilleure
- Utiliser le improvement_score et les defauts comme levier ("je suis pret a payer plus si vous corrigez X")

Tu parles en francais pour les conseils, mais generes les messages en anglais."""


class NegotiatorAgent(BaseAgent):
    """
    Agent d'aide a la negociation.
    """

    agent_type = AgentType.NEGOTIATOR
    name = "Negotiator Agent"
    description = "Aide a la negociation fournisseurs"

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
        Prepare une strategie de negociation.
        """
        opp = context.opportunity_data
        rp = context.review_profile or {}
        sb = context.spec_bundle or {}
        amazon_price = opp.get('amazon_price', 0) or 1

        # Real cost breakdown
        referral = amazon_price * 0.15
        fba_fee = 4.25  # average for car phone mounts
        shipping = 3.0  # average sea freight
        ppc = amazon_price * 0.10

        margin_at_supplier = amazon_price - supplier_price - referral - fba_fee - shipping - ppc
        margin_pct_supplier = (margin_at_supplier / amazon_price) * 100
        margin_at_target = amazon_price - target_price - referral - fba_fee - shipping - ppc
        margin_pct_target = (margin_at_target / amazon_price) * 100
        quarter_rule = amazon_price / 4

        # Review intelligence levers
        improvement_score = rp.get("improvement_score", 0)
        defects = rp.get("top_defects", [])
        defect_text = "\n".join(f"  - {d.get('defect_type')}: {d.get('frequency')} plaintes" for d in defects[:3]) if defects else "  Aucun identifie"
        risk_adj = opp.get("risk_adjusted_value", 0)

        prompt = f"""Prepare une strategie de negociation complete et realiste.

## CONTEXTE PRODUIT
- Produit: {opp.get('title')}
- Prix Amazon: ${amazon_price:.2f}
- Score opportunite: {opp.get('final_score', 0)}/100
- Valeur ajustee risque: ${risk_adj:,.0f}/an
- Quantite: {quantity} unites

## COUTS REELS (par unite)
- Referral fee (15%): ${referral:.2f}
- FBA fee: ${fba_fee:.2f}
- Shipping: ${shipping:.2f}
- PPC (~10%): ${ppc:.2f}
- **Regle du quart**: COGS max ${quarter_rule:.2f}

## SITUATION
- Prix fournisseur actuel: ${supplier_price:.2f}/unite
- Marge nette actuelle: ${margin_at_supplier:.2f} ({margin_pct_supplier:.1f}%) {'— BON' if margin_pct_supplier >= 25 else '— INSUFFISANT' if margin_pct_supplier < 15 else '— CORRECT'}
- Prix cible: ${target_price:.2f}/unite
- Marge nette visee: ${margin_at_target:.2f} ({margin_pct_target:.1f}%)
- Reduction demandee: {((supplier_price - target_price) / supplier_price * 100):.1f}%
- vs regle du quart: {'CONFORME' if target_price <= quarter_rule else f'DEPASSEMENT +${target_price - quarter_rule:.2f}'}

## LEVIERS REVIEW INTELLIGENCE
- Avis Amazon: {opp.get('review_count', 0)} avis, note {opp.get('rating', 'N/A')}/5
- Improvement score: {f"{improvement_score:.0%}" if rp else "non analysé (backfill requis)"}{'— FORT levier qualite' if improvement_score > 0.6 else ' — levier modere' if improvement_score > 0 else ''}
- Defauts a corriger (levier "je paie plus si vous corrigez"):
{defect_text}

---

Genere :

1. **ANALYSE REALISTE**
   - La reduction est-elle realiste vu les prix benchmark niche ?
   - Quel est le prix plancher probable du fournisseur ?

2. **STRATEGIE EN 3 PHASES**
   - Phase 1: Ouverture (demander plus que voulu)
   - Phase 2: Echange de concessions
   - Phase 3: Cloture

3. **ARGUMENTS CLES** (5, par ordre de force)
   - Utilise les donnees reelles : volume, engagement long terme, defauts a corriger

4. **CONCESSIONS A OFFRIR**
   - Paiement plus rapide
   - Volume garanti
   - Commandes regulieres
   - Exclusivite regionale

5. **MESSAGE D'OUVERTURE** (en anglais, pret a envoyer)
   - Professionnel, cite les specs/corrections attendues

6. **PLAN B** si echec"""

        try:
            response_text = await self._call_llm(prompt, context, max_tokens=2000)
            context.add_message("agent", response_text)

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
                    "description": "Commencer la negociation",
                },
                {
                    "action": "adjust_target",
                    "label": "Ajuster le prix cible",
                    "description": "Modifier l'objectif de negociation",
                },
            ]
            if margin_pct_supplier < 15:
                actions.append({
                    "action": "find_alternative",
                    "label": "Chercher un autre fournisseur",
                    "description": "Marge trop faible — renforcer le BATNA",
                })
            actions.append({
                "action": "simulate_profitability",
                "label": "Simuler la rentabilite",
                "description": "Retour a l'Analyst pour calcul detaille",
            })

            return AgentResponse(
                message=response_text,
                suggested_actions=actions,
                agent_type=self.agent_type,
                status=AgentStatus.COMPLETED,
                data={
                    "supplier_price": supplier_price,
                    "target_price": target_price,
                    "quantity": quantity,
                    "margin_current": margin_pct_supplier,
                    "margin_target": margin_pct_target,
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
        Genere une reponse a un message du fournisseur.
        """
        opp = context.opportunity_data
        amazon_price = opp.get("amazon_price", 0) or 1
        quarter_rule = amazon_price / 4

        prompt = f"""Le fournisseur a repondu ceci :

---
{supplier_response}
---

Situation : {situation}
Regle du quart : COGS max ${quarter_rule:.2f}

Contexte de negociation :
{context.get_conversation_history(5)}

Genere :
1. **ANALYSE** de leur reponse (ce qu'ils disent vraiment, les signaux)
2. **RECOMMANDATION** : accepter, contre-offrir, ou abandonner — avec justification chiffree
3. **MESSAGE DE REPONSE** en anglais, pret a envoyer

Le message doit etre professionnel, ferme mais pas agressif, oriente solution."""

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
        Aide a finaliser l'accord.
        """
        opp = context.opportunity_data
        amazon_price = opp.get("amazon_price", 0) or 1
        final_price = final_terms.get("price", 0)
        referral = amazon_price * 0.15
        fba = 4.25
        shipping = 3.0
        ppc = amazon_price * 0.10
        final_margin = amazon_price - final_price - referral - fba - shipping - ppc
        final_margin_pct = (final_margin / amazon_price) * 100

        prompt = f"""L'utilisateur est pret a finaliser avec ces termes :

- Prix final: ${final_terms.get('price')}/unite
- Quantite: {final_terms.get('quantity')} unites
- Paiement: {final_terms.get('payment_terms', '30% deposit, 70% before shipping')}
- Lead time: {final_terms.get('lead_time', '30')} jours
- Shipping: {final_terms.get('shipping', 'FOB')}

## Marge nette finale
- Referral: ${referral:.2f} + FBA: ${fba:.2f} + Ship: ${shipping:.2f} + PPC: ${ppc:.2f} + COGS: ${final_price:.2f}
- **Marge nette: ${final_margin:.2f}/unite ({final_margin_pct:.1f}%)**
- {'DANS LA CIBLE (20-35%)' if 20 <= final_margin_pct <= 35 else 'SOUS LA CIBLE' if final_margin_pct < 20 else 'EXCELLENTE MARGE'}

Genere :
1. **VERDICT** sur le deal (bon / acceptable / risque)
2. **CHECKLIST** avant confirmation (8-10 points)
3. **MESSAGE DE CONFIRMATION** en anglais
4. **POINTS A VERIFIER** dans le contrat/PI
5. **CONSEILS PAIEMENT** securise (Trade Assurance, Escrow, etc.)"""

        try:
            response_text = await self._call_llm(prompt, context)
            context.add_message("agent", response_text)

            context.negotiation_history.append({
                "type": "deal_closed",
                "terms": final_terms,
                "margin_pct": final_margin_pct,
            })

            return AgentResponse(
                message=response_text,
                agent_type=self.agent_type,
                status=AgentStatus.COMPLETED,
                data={"final_terms": final_terms, "margin_pct": final_margin_pct},
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

        opp = context.opportunity_data
        rp = context.review_profile or {}
        amazon_price = opp.get("amazon_price", 0) or 1

        prompt = f"""L'utilisateur demande : "{user_input}"

## Contexte negociation
- Produit: {opp.get('title', 'Unknown')}
- Prix Amazon: ${amazon_price:.2f}
- Regle du quart: COGS max ${amazon_price / 4:.2f}
- Avis Amazon: {opp.get('review_count', 0)} avis, note {opp.get('rating', 'N/A')}/5
- Improvement score: {f"{rp.get('improvement_score', 0):.0%}" if rp else "non analysé"}
- Historique: {len(context.negotiation_history)} interactions
- Valeur ajustee risque: ${opp.get('risk_adjusted_value', 0):,.0f}/an

## Structure de couts
- Referral 15% = ${amazon_price * 0.15:.2f}
- FBA ~$4.25
- Shipping ~$3.00
- PPC ~10% = ${amazon_price * 0.10:.2f}

Reponds en expert negociation niche Car Phone Mounts.
Cite toujours les chiffres concrets.
Si la question concerne un message recu du fournisseur, analyse et suggere une reponse."""

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
