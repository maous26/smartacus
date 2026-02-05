"""
Discovery Agent
===============

Agent #1 - PRIORITE MAXIMALE
"Si Discovery est faux, tout est faux."

Role :
- Presenter les opportunites detectees a l'utilisateur
- Expliquer pourquoi chaque opportunite existe
- Aider a qualifier et prioriser
- Repondre aux questions sur les opportunites

L'agent Discovery est le premier contact de l'utilisateur avec une opportunite.
Il doit etre clair, convaincant, et honnete sur les risques.
"""

import logging
from typing import Dict, Any, Optional, List

from .base import (
    BaseAgent,
    AgentResponse,
    AgentContext,
    AgentType,
    AgentStatus,
    compute_confidence,
)

logger = logging.getLogger(__name__)


DISCOVERY_SYSTEM_PROMPT = """Tu es l'Agent Discovery de Smartacus, expert en detection d'opportunites Amazon FBA dans la niche **Car Phone Mounts / Supports Telephone Voiture**.

TON ROLE :
Tu presentes des opportunites de produits a vendre sur Amazon FBA.
Tu expliques POURQUOI chaque opportunite existe et si elle vaut la peine d'etre poursuivie.

## EXPERTISE NICHE — Car Phone Mounts (Marche Amazon FR)
Tu maitrises parfaitement cette niche sur le marche francais :
- **COGS typique** : 3-8 EUR/unite (PC+ABS, silicone, aimants N52)
- **Fees FBA** : ~15% referral + 3.00-4.50 EUR fulfillment fee (petit/leger)
- **PPC moyen** : 0.30-1.00 EUR CPC (moins cher qu'US), ACoS cible 20-30%
- **Marge nette cible** : 20-35% apres tous frais
- **BSR benchmark** : <3000 en High-tech > Accessoires = bon volume (marche plus petit qu'US)
- **Saisonnalite** : pic Q4 (cadeaux), leger creux ete
- **Tendances** : MagSafe en forte croissance, ventouse en declin, grille aeration stable
- **Particularites FR** : TVA 20% incluse dans le prix, clients sensibles aux avis FR

## SCORING SMARTACUS (100 pts)
Tu connais la decomposition exacte du score :
- **Margin** (0-30) : marge brute estimee par rapport aux concurrents
- **Velocity** (0-25) : vitesse de vente / demande
- **Competition** (0-20) : intensite concurrentielle (faible = mieux)
- **Gap** (0-15) : ecart qualite / features vs la concurrence
- **TimePressure** (0-10) : urgence de la fenetre d'opportunite
- Le **time_multiplier** (x0.5-2.0) ajuste le score base selon la fenetre

## PRINCIPES :
1. CLARTE : Explique simplement, meme les concepts complexes
2. HONNETETE : Sois transparent sur les risques et incertitudes
3. PRAGMATISME : Focus sur l'actionnable, pas la theorie
4. CONVICTION : Si tu crois en l'opportunite, montre-le. Sinon, dis-le aussi.
5. DONNEES : Cite les chiffres concrets du scoring et des reviews

## FORMAT DE REPONSE :
- Conversationnel mais professionnel
- Chiffres concrets toujours cites
- Structure avec points cles
- Propose toujours une prochaine action

Tu parles en francais."""


def _format_component_scores(opp: Dict[str, Any]) -> str:
    """Format component scores for prompt injection."""
    cs = opp.get("component_scores", {})
    if not cs:
        return "Non disponible"
    lines = []
    for name, data in cs.items():
        score = data.get("score", 0)
        max_s = data.get("max_score", 1)
        pct = (score / max_s * 100) if max_s else 0
        lines.append(f"  - {name}: {score}/{max_s} ({pct:.0f}%)")
    return "\n".join(lines)


def _format_review_intelligence(rp: Dict[str, Any], opp: Optional[Dict[str, Any]] = None) -> str:
    """Format review intelligence data for prompt injection."""
    if not rp:
        rc = (opp or {}).get("review_count", 0) or 0
        rt = (opp or {}).get("rating", 0) or 0
        if rc > 0:
            return (f"Analyse detaillee non disponible (backfill requis), "
                    f"mais le produit a {rc:,} avis Amazon (note {rt}/5). "
                    f"Utilise ces donnees pour ton analyse.")
        return "Aucun avis sur ce produit."
    lines = [
        f"- Improvement Score: {rp.get('improvement_score', 0):.1%}",
        f"- Pain dominant: {rp.get('dominant_pain', 'Aucun')}",
        f"- Avis analyses: {rp.get('reviews_analyzed', 0)} (dont {rp.get('negative_reviews_analyzed', 0)} negatifs)",
    ]
    defects = rp.get("top_defects", [])
    if defects:
        lines.append("- Top defauts:")
        for d in defects[:3]:
            lines.append(f"  * {d.get('defect_type', '?')}: {d.get('frequency', 0)} mentions, severite {d.get('severity_score', 0):.2f}")
    wishes = rp.get("missing_features", [])
    if wishes:
        lines.append("- Top wishes clients:")
        for w in wishes[:3]:
            lines.append(f"  * \"{w.get('feature', '?')}\" ({w.get('mentions', 0)} mentions, strength {w.get('wish_strength', 0):.1f})")
    fragment = rp.get("thesis_fragment")
    if fragment:
        lines.append(f"- Resume: {fragment}")
    return "\n".join(lines)


def _format_economic_events(opp: Dict[str, Any]) -> str:
    """Format economic events for prompt injection."""
    events = opp.get("economic_events", [])
    if not events:
        return "Aucun evenement economique detecte."
    lines = []
    for ev in events[:5]:
        lines.append(f"- [{ev.get('event_type', '?')}] {ev.get('thesis', '')} (confiance: {ev.get('confidence', '?')})")
    return "\n".join(lines)


def _build_dynamic_actions(opp: Dict[str, Any], rp: Dict[str, Any]) -> list:
    """Build data-driven suggested actions based on available data."""
    final_score = opp.get("final_score", 0)
    improvement_score = rp.get("improvement_score", 0) if rp else 0
    reviews_analyzed = rp.get("reviews_analyzed", 0) if rp else 0

    actions = [
        {
            "action": "analyze_deeper",
            "label": "Analyser en profondeur",
            "description": "Passer a l'Analyst pour validation detaillee",
        },
    ]

    if improvement_score > 0.6:
        actions.append({
            "action": "view_specs",
            "label": "Voir les specifications OEM",
            "description": f"Spec prete (score amelioration {improvement_score:.0%})",
        })

    if final_score >= 50:
        actions.append({
            "action": "find_suppliers",
            "label": "Chercher des fournisseurs",
            "description": "Passer au sourcing Alibaba",
        })
    else:
        actions.append({
            "action": "analyze_risks",
            "label": "Analyser les risques d'abord",
            "description": f"Score {final_score}/100 — validation requise",
        })

    if reviews_analyzed < 5:
        actions.append({
            "action": "backfill_reviews",
            "label": "Lancer le backfill reviews",
            "description": "Collecter les avis pour enrichir l'analyse",
        })

    actions.append({
        "action": "skip",
        "label": "Passer a la suivante",
        "description": "Voir une autre opportunite",
    })

    return actions


class DiscoveryAgent(BaseAgent):
    """
    Agent de decouverte et qualification des opportunites.
    """

    agent_type = AgentType.DISCOVERY
    name = "Discovery Agent"
    description = "Detection et qualification des opportunites Amazon"

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
        Presente une nouvelle opportunite a l'utilisateur.
        """
        context.asin = opportunity.get("asin")
        context.opportunity_data = opportunity
        context.thesis = thesis
        context.current_stage = "discovery"

        rp = context.review_profile or {}
        sb = context.spec_bundle or {}

        # Compute confidence from actual data
        confidence_val, caveat = compute_confidence(context)

        prompt = f"""Presente cette opportunite a l'utilisateur de maniere engageante et informative.

## Donnees Opportunite
- ASIN: {opportunity.get('asin')}
- Titre: {opportunity.get('title')}
- Marque: {opportunity.get('brand', 'N/A')}
- Rang: #{opportunity.get('rank', '?')}
- Prix Amazon: ${opportunity.get('amazon_price', 0)}
- Score final: {opportunity.get('final_score', 0)}/100
- Score base: {opportunity.get('base_score', 0):.2f}
- Multiplicateur temps: x{opportunity.get('time_multiplier', 1):.2f}
- Fenetre: {opportunity.get('window_days', 0)} jours
- Urgence: {opportunity.get('urgency_level', 'N/A')} ({opportunity.get('urgency_label', '')})
- Rating: {opportunity.get('rating', 'N/A')}/5 ({opportunity.get('review_count', 0)} avis)

## Decomposition du score
{_format_component_scores(opportunity)}

## Valeur economique
- Profit mensuel estime: ${opportunity.get('estimated_monthly_profit', 0):,.0f}
- Valeur annuelle: ${opportunity.get('estimated_annual_value', 0):,.0f}
- Ajuste risque: ${opportunity.get('risk_adjusted_value', 0):,.0f}

## These economique
{thesis.get('headline') if thesis else 'Non disponible'}
{thesis.get('thesis') if thesis else ''}

## Review Intelligence (Voice of Customer)
{_format_review_intelligence(rp, opportunity)}

## Evenements economiques
{_format_economic_events(opportunity)}

## Spec OEM disponible
{"Oui — " + str(sb.get('total_requirements', 0)) + " exigences, " + str(sb.get('total_qc_tests', 0)) + " tests QC" if sb.get('total_requirements') else "Non disponible"}

## Confiance dans l'analyse: {confidence_val:.0%}{' (' + caveat + ')' if caveat else ''}

---

Genere une presentation conversationnelle qui :
1. Accroche l'attention avec le point le plus differentiant (defaut client a corriger, wish non comble, ou marge exceptionnelle)
2. Explique pourquoi cette opportunite existe en citant les composantes du score
3. Donne les chiffres cles (prix, marge estimee, fenetre temporelle)
4. Si des reviews sont disponibles, mentionne le pain dominant et l'angle d'amelioration produit
5. Mentionne les risques principaux (composantes faibles du score, events negatifs)
6. Propose une action adaptee aux donnees disponibles"""

        try:
            response_text = await self._call_llm(prompt, context)

            actions = _build_dynamic_actions(opportunity, rp)

            context.add_message("agent", response_text)

            return AgentResponse(
                message=response_text,
                suggested_actions=actions,
                data={"opportunity": opportunity, "thesis": thesis},
                agent_type=self.agent_type,
                status=AgentStatus.WAITING,
                confidence=confidence_val,
                requires_input=True,
            )

        except Exception as e:
            logger.error(f"Discovery agent error: {e}")
            return AgentResponse(
                message=f"Desole, j'ai rencontre une erreur en analysant cette opportunite: {str(e)}",
                status=AgentStatus.ERROR,
                agent_type=self.agent_type,
            )

    async def process(
        self,
        user_input: str,
        context: AgentContext,
    ) -> AgentResponse:
        """
        Traite une question/reponse de l'utilisateur.
        """
        context.add_message("user", user_input)

        rp = context.review_profile or {}
        opp = context.opportunity_data

        prompt = f"""L'utilisateur a dit : "{user_input}"

## Contexte de l'opportunite actuelle
- ASIN: {context.asin}
- Produit: {opp.get('title', 'Unknown')}
- Score final: {opp.get('final_score', 'N/A')}/100
- Score base: {opp.get('base_score', 'N/A'):.2f} x{opp.get('time_multiplier', 1):.2f}
- Profit mensuel: ${opp.get('estimated_monthly_profit', 0):,.0f}
- Valeur ajustee risque: ${opp.get('risk_adjusted_value', 0):,.0f}

## Decomposition du score
{_format_component_scores(opp)}

## Review Intelligence
{_format_review_intelligence(rp, opp)}

## These
{context.thesis.get('headline') if context.thesis else 'Non disponible'}

---

Reponds a l'utilisateur. Si sa question concerne :
- L'opportunite : cite les composantes du score, les chiffres concrets
- Les reviews/defauts : utilise les donnees review intelligence ci-dessus
- Les risques : sois honnete, cite les composantes faibles
- La marge : utilise les benchmarks niche (COGS 3-8 EUR, FBA ~3-4.50 EUR, referral 15%)
- L'action suivante : guide-le vers l'etape appropriee

Si l'utilisateur veut avancer (sourcing, fournisseurs), indique qu'il peut passer a l'Agent Sourcing."""

        try:
            response_text = await self._call_llm(prompt, context)
            context.add_message("agent", response_text)

            next_stage = None
            if any(kw in user_input.lower() for kw in ["fournisseur", "sourcing", "supplier", "alibaba", "commander"]):
                next_stage = "sourcing"
            elif any(kw in user_input.lower() for kw in ["analyser", "analyse", "valider", "deep dive", "profondeur"]):
                next_stage = "analyst"

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
        Compare plusieurs opportunites pour aider l'utilisateur a choisir.
        """
        if len(opportunities) < 2:
            return AgentResponse(
                message="Il faut au moins 2 opportunites pour comparer.",
                status=AgentStatus.ERROR,
                agent_type=self.agent_type,
            )

        opps_text = "\n\n".join([
            f"""### Opportunite {i+1}: {opp.get('title', 'Unknown')[:50]}
- ASIN: {opp.get('asin')}
- Score: {opp.get('final_score')}/100
- Prix: ${opp.get('amazon_price')}
- Urgence: {opp.get('urgency_level')}
- Profit mensuel: ${opp.get('estimated_monthly_profit', 0):,.0f}
- Valeur ajustee: ${opp.get('risk_adjusted_value', 0):,.0f}/an"""
            for i, opp in enumerate(opportunities[:5])
        ])

        prompt = f"""Compare ces opportunites et aide l'utilisateur a choisir.

{opps_text}

Donne :
1. Un classement avec justification (cite les composantes du score)
2. Le meilleur choix pour un debutant (risque faible, marge correcte)
3. Le meilleur choix pour maximiser le profit
4. Ta recommandation personnelle avec niveau de confiance"""

        response_text = await self._call_llm(prompt, context)
        context.add_message("agent", response_text)

        return AgentResponse(
            message=response_text,
            agent_type=self.agent_type,
            status=AgentStatus.COMPLETED,
            data={"compared_opportunities": [o.get("asin") for o in opportunities]},
        )
