"""
Sourcing Agent
==============

Agent #3 - Accompagnement sourcing fournisseurs

Role :
- Identifier des fournisseurs potentiels (Alibaba, 1688, etc.)
- Evaluer la fiabilite des fournisseurs
- Guider la demande d'echantillons
- Preparer les questions pour les fournisseurs
- Exploiter les specs OEM et defauts reviews pour un sourcing cible
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


SOURCING_SYSTEM_PROMPT = """Tu es l'Agent Sourcing de Smartacus, expert en approvisionnement depuis la Chine pour Amazon FBA, specialise dans la niche **Car Phone Mounts / Supports Telephone Voiture**.

TON ROLE :
Tu aides les utilisateurs a trouver et evaluer des fournisseurs pour leurs produits.
Tu exploites les specs OEM et les defauts identifies par la Review Intelligence pour un sourcing ultra-cible.

## EXPERTISE NICHE — Materiaux & Fabrication

### Materiaux typiques
- **Corps** : PC+ABS (polycarbonate + ABS), parfois ABS seul pour entree de gamme
- **Pads/ventouses** : Silicone (Shore A 30-50), gel PU pour les pads anti-glisse
- **Aimants** : Neodyme N52 (les plus puissants), N48 pour budget, anneau MagSafe compatible
- **Bras** : Alliage aluminium 6061 ou acier inox 304 pour les bras telescopiques
- **Finition** : Soft-touch coating, UV coating pour anti-jaunissement

### Certifications necessaires
- **FCC** : obligatoire si electronique (chargeur wireless)
- **CE** : optionnel mais rassure (marche EU)
- **RoHS** : obligatoire pour tous les produits electroniques
- **Qi** : certification Wireless Power Consortium si wireless charging

### Termes Alibaba specifiques
- "car phone holder manufacturer" (pas "seller")
- "OEM ODM car mount"
- "custom car phone bracket factory"
- MOQ typique : 500-1000 unites premiere commande, 200-500 apres relation
- Lead time : 15-25 jours production + 30-45 jours sea freight

### Structure de prix (en EUR, marche Amazon FR)
- Entree de gamme (ventouse/grille simple) : 1.50-3.00 EUR
- Milieu (MagSafe, bras articule) : 3.00-6.00 EUR
- Haut de gamme (wireless charging, motorise) : 6.00-12.00 EUR
- Shipping : 2-4 EUR/unite sea freight (vers port EU), 5-8 EUR air freight
- TVA import EU : 20% (a inclure dans le calcul total)

## TES PRINCIPES :
- Toujours demander des echantillons avant grosse commande
- Verifier Trade Assurance et annees d'activite (>3 ans minimum)
- Comparer 3-5 fournisseurs minimum
- Prix trop bas = qualite douteuse
- Exiger des rapports de test (drop test, force retention, UV aging)

Tu parles en francais, de maniere pratique et directe."""


def _format_spec_for_sourcing(sb: Dict[str, Any]) -> str:
    """Format spec bundle for sourcing context."""
    if not sb:
        return "Pas de spec OEM disponible — sourcing generique."
    lines = [
        f"Spec OEM disponible: {sb.get('total_requirements', 0)} exigences, {sb.get('total_qc_tests', 0)} tests QC",
    ]
    oem = sb.get("oem_spec_text", "")
    if oem:
        # Show first 500 chars of spec
        lines.append("--- Extrait spec OEM ---")
        lines.append(oem[:500] + ("..." if len(oem) > 500 else ""))
    qc = sb.get("qc_checklist_text", "")
    if qc:
        lines.append("--- Extrait QC ---")
        lines.append(qc[:300] + ("..." if len(qc) > 300 else ""))
    return "\n".join(lines)


def _format_defects_for_sourcing(rp: Dict[str, Any], opp: Optional[Dict[str, Any]] = None) -> str:
    """Format review defects as sourcing requirements."""
    if not rp:
        rc = (opp or {}).get("review_count", 0) or 0
        rt = (opp or {}).get("rating", 0) or 0
        if rc > 0:
            return (f"Analyse detaillee non disponible (backfill requis). "
                    f"Le produit a {rc:,} avis Amazon (note {rt}/5). "
                    f"Sourcing generique — demander au fournisseur les rapports de test standard.")
        return "Pas de donnees avis — sourcing generique."
    defects = rp.get("top_defects", [])
    wishes = rp.get("missing_features", [])
    lines = []
    if defects:
        lines.append("DEFAUTS A CORRIGER (exiger du fournisseur) :")
        for d in defects[:5]:
            lines.append(f"  - {d.get('defect_type', '?')}: {d.get('frequency', 0)} plaintes (severite {d.get('severity_score', 0):.2f})")
    if wishes:
        lines.append("FEATURES A AJOUTER (differenciateur) :")
        for w in wishes[:3]:
            lines.append(f"  - \"{w.get('feature', '?')}\" ({w.get('mentions', 0)} demandes)")
    return "\n".join(lines) if lines else "Aucun defaut ni wish identifie."


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
        rp = context.review_profile or {}
        sb = context.spec_bundle or {}
        product_title = opp.get('title', 'Unknown Product')

        prompt = f"""L'utilisateur cherche des fournisseurs pour ce Car Phone Mount :

## Produit
- **Titre**: {product_title}
- **ASIN**: {opp.get('asin')}
- **Prix Amazon**: ${opp.get('amazon_price', 0)}
- **Score**: {opp.get('final_score', 0)}/100
- **Rating concurrent**: {opp.get('rating', 'N/A')}/5

## Intelligence Review — Ce que les clients veulent
{_format_defects_for_sourcing(rp, opp)}

## Spec OEM (si disponible)
{_format_spec_for_sourcing(sb)}

---

Guide l'utilisateur pour trouver les BONS fournisseurs :

1. **MOTS-CLES DE RECHERCHE ALIBABA**
   - 5 termes precis en anglais adaptes a CE produit specifique
   - Inclure les variantes OEM/ODM et les termes techniques niche

2. **CRITERES DE SELECTION SPECIFIQUES**
   - Trade Assurance : montant minimum selon la commande
   - Annees minimum (3+ pour la niche)
   - Certifications requises selon le produit (FCC si wireless, etc.)
   - MOQ acceptable pour premiere commande
   - Capacite a gerer les corrections de defauts identifies

3. **QUESTIONS CLES A POSER**
   - 5 questions specifiques a CE produit (pas generiques)
   - Inclure les defauts a corriger et les features a ajouter

4. **RED FLAGS SPECIFIQUES NICHE**
   - Signaux d'alerte pour les supports telephone

5. **ESTIMATION PRIX & TIMELINE**
   - Fourchette prix attendue pour CE type de produit
   - Timeline realiste (production + shipping)

6. **SPEC A ENVOYER**
   - Resume des exigences OEM a inclure dans la demande"""

        try:
            response_text = await self._call_llm(prompt, context, max_tokens=1500)
            context.add_message("agent", response_text)

            actions = [
                {
                    "action": "search_alibaba",
                    "label": "Ouvrir Alibaba",
                    "description": "Lancer la recherche",
                    "url": f"https://www.alibaba.com/trade/search?SearchText=car+phone+mount+OEM+manufacturer",
                },
                {
                    "action": "generate_message",
                    "label": "Generer un message fournisseur",
                    "description": "Template avec spec OEM integree",
                },
            ]

            if sb.get("rfq_message_text"):
                actions.append({
                    "action": "send_rfq",
                    "label": "Envoyer le RFQ pret",
                    "description": "Message RFQ avec specs detaillees",
                })

            actions.extend([
                {
                    "action": "compare_suppliers",
                    "label": "Comparer des fournisseurs",
                    "description": "Evaluer plusieurs fournisseurs",
                },
                {
                    "action": "negotiate",
                    "label": "Passer a la negociation",
                    "description": "J'ai trouve un fournisseur",
                },
            ])

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
        Genere un template de message pour contacter un fournisseur.
        """
        opp = context.opportunity_data
        rp = context.review_profile or {}
        sb = context.spec_bundle or {}

        # If we have a RFQ message ready, use it as a base
        rfq_base = sb.get("rfq_message_text", "")

        prompt = f"""Genere un message professionnel pour contacter un fournisseur Alibaba de Car Phone Mounts.

**Produit recherche**: {opp.get('title')}
**Quantite initiale**: {quantity} unites
**Destination**: USA (Amazon FBA)
**Prix cible**: ${opp.get('amazon_price', 0) / 4:.2f}/unite max (regle du quart)

## Defauts a corriger absolument
{_format_defects_for_sourcing(rp, opp)}

## Spec OEM a inclure
{rfq_base[:800] if rfq_base else 'Pas de spec RFQ — generer un message generique mais precis'}

Le message doit :
1. Etre professionnel, montrer qu'on est un acheteur serieux avec des specs precises
2. Mentionner les defauts specifiques a corriger (pas generique)
3. Demander : prix unitaire pour {quantity} et 2000 unites, MOQ, lead time, certifications
4. Demander des echantillons (2-3 pieces)
5. Etre en anglais (pour les fournisseurs chinois)

Format : pret a copier-coller."""

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
        Evalue un fournisseur specifique.
        """
        rp = context.review_profile or {}
        defects = rp.get("top_defects", [])
        defect_text = ", ".join(d.get("defect_type", "") for d in defects[:3]) if defects else "aucun defaut identifie"

        prompt = f"""Evalue ce fournisseur Alibaba de Car Phone Mounts :

**Nom**: {supplier_info.get('name', 'Unknown')}
**Annees d'activite**: {supplier_info.get('years', 'Unknown')}
**Trade Assurance**: {supplier_info.get('trade_assurance', 'Unknown')}
**Certifications**: {supplier_info.get('certifications', 'Unknown')}
**Prix propose**: ${supplier_info.get('price', 'Unknown')}/unite
**MOQ**: {supplier_info.get('moq', 'Unknown')} unites
**Lead time**: {supplier_info.get('lead_time', 'Unknown')} jours

## Contexte
- Prix Amazon du produit concurrent : ${context.opportunity_data.get('amazon_price', 0)}
- Regle du quart : COGS max ${context.opportunity_data.get('amazon_price', 0) / 4:.2f}
- Defauts a corriger : {defect_text}

Analyse specifique niche :
1. Score de fiabilite (1-10) avec justification
2. Prix vs benchmark niche ($1.50-12.00 selon complexite)
3. Capacite a corriger les defauts identifies ?
4. Red flags specifiques
5. Questions supplementaires a poser
6. Recommandation : GO / PRUDENCE / NO-GO"""

        try:
            response_text = await self._call_llm(prompt, context)
            context.add_message("agent", response_text)

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

        opp = context.opportunity_data
        rp = context.review_profile or {}
        sb = context.spec_bundle or {}

        prompt = f"""L'utilisateur demande : "{user_input}"

## Contexte sourcing
- Produit: {opp.get('title', 'Unknown')}
- Prix Amazon: ${opp.get('amazon_price', 0)}
- COGS max (regle du quart): ${opp.get('amazon_price', 0) / 4:.2f}
- Avis Amazon: {opp.get('review_count', 0)} avis, note {opp.get('rating', 'N/A')}/5
- Defauts a corriger: {', '.join(d.get('defect_type', '') for d in rp.get('top_defects', [])[:3]) or 'Non analysé (backfill requis)'}
- Spec OEM: {'Disponible (' + str(sb.get('total_requirements', 0)) + ' exigences)' if sb.get('total_requirements') else 'Non disponible'}
- Fournisseurs evalues: {len(context.sourcing_options)}

Reponds en expert sourcing niche Car Phone Mounts. Utilise ta connaissance des materiaux (PC+ABS, silicone, N52), des certifications, et des prix typiques.

Si l'utilisateur est pret a negocier, suggere de passer a l'Agent Negotiator."""

        try:
            response_text = await self._call_llm(prompt, context)
            context.add_message("agent", response_text)

            next_stage = None
            if any(kw in user_input.lower() for kw in ["negocier", "negociation", "prix final", "negotiate"]):
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
