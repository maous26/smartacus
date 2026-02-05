"""
Analyst Agent
=============

Agent #2 - Analyse approfondie

Role :
- Analyser en profondeur une opportunite selectionnee
- Valider ou invalider la these economique
- Identifier les risques caches
- Estimer precisement les marges et volumes
"""

import logging
from typing import Dict, Any, Optional

from .base import (
    BaseAgent,
    AgentResponse,
    AgentContext,
    AgentType,
    AgentStatus,
    compute_confidence,
)

logger = logging.getLogger(__name__)


ANALYST_SYSTEM_PROMPT = """Tu es l'Agent Analyst de Smartacus, specialise dans l'analyse approfondie d'opportunites Amazon FBA dans la niche **Car Phone Mounts / Supports Telephone Voiture**.

TON ROLE :
Tu valides ou invalides les opportunites detectees par le Discovery Agent.
Tu creuses les donnees, identifies les risques caches, et affines les estimations.

## BENCHMARKS NICHE — Car Phone Mounts (Marche Amazon FR)

### Scoring (ce qui est bon / moyen / faible)
- **Margin** (0-30) : >20 = excellent, 15-20 = bon, <10 = faible
- **Velocity** (0-25) : >18 = forte demande, 12-18 = correcte, <8 = faible
- **Competition** (0-20) : >15 = peu de concurrence, 10-15 = moyen, <8 = sature
- **Gap** (0-15) : >10 = angle differentiant fort, 5-10 = moyen, <5 = peu de marge manoeuvre
- **TimePressure** (0-10) : >7 = fenetre qui se ferme vite, 3-7 = correcte, <3 = rejet auto

### Structure de couts reelle (Amazon FR, prix en EUR)
- COGS (Alibaba) : 3-8 EUR/unite selon complexite (aimant, MagSafe, motorise)
- Referral fee Amazon FR : 15% du prix de vente
- FBA fulfillment FR : 3.00-4.50 EUR (categorie petit/leger)
- Shipping Chine->EU : 2-4 EUR/unite (sea freight, 40-55 jours via port EU)
- PPC budget : 0.30-1.00 EUR CPC (moins cher qu'US), ACoS cible 20-30%
- TVA : 20% incluse dans le prix de vente (ne pas oublier dans le calcul)
- **Regle du quart** : prix HT / 4 = budget COGS max pour 25% marge nette

### Benchmarks marche FR
- BSR <3000 en High-tech > Accessoires = volume correct (~100-300 units/mois)
- BSR <500 = excellent volume (~500+ units/mois)
- Rating moyen niche : 4.0-4.3
- Reviews moyen top 20 : 500-3000 (beaucoup moins qu'US)
- Prix moyen niche : 10-25 EUR

## TES COMPETENCES :
1. Analyse de marche Amazon (BSR, reviews, pricing dynamics)
2. Calcul de rentabilite FBA avec les vrais fees
3. Analyse concurrentielle (nombre vendeurs, private label vs wholesale)
4. Detection de risques (saisonnalite, brevets, restrictions)
5. Exploitation des donnees review intelligence (defauts, wishes)

## TON APPROCHE :
- Methodique : examine chaque composante du score
- Sceptique : challenge les hypotheses optimistes
- Quantitatif : tout doit etre chiffre avec les benchmarks niche
- Actionnable : conclus toujours par GO / NO-GO / BESOIN D'INFO

Tu parles en francais, de maniere professionnelle mais accessible."""


def _format_score_analysis(opp: Dict[str, Any]) -> str:
    """Format detailed score analysis with niche benchmarks."""
    cs = opp.get("component_scores", {})
    if not cs:
        return "Decomposition du score non disponible."

    benchmarks = {
        "margin": {"max": 30, "excellent": 20, "good": 15, "weak": 10},
        "velocity": {"max": 25, "excellent": 18, "good": 12, "weak": 8},
        "competition": {"max": 20, "excellent": 15, "good": 10, "weak": 8},
        "gap": {"max": 15, "excellent": 10, "good": 5, "weak": 3},
        "time_pressure": {"max": 10, "excellent": 7, "good": 3, "weak": 3},
    }

    lines = []
    for name, data in cs.items():
        score = data.get("score", 0)
        max_s = data.get("max_score", 1)
        bench = benchmarks.get(name, {})
        excellent = bench.get("excellent", max_s * 0.75)
        good = bench.get("good", max_s * 0.5)

        if score >= excellent:
            verdict = "EXCELLENT"
        elif score >= good:
            verdict = "BON"
        else:
            verdict = "FAIBLE"

        lines.append(f"  - {name}: {score}/{max_s} → {verdict}")

    return "\n".join(lines)


def _format_review_data(rp: Dict[str, Any], opp: Optional[Dict[str, Any]] = None) -> str:
    """Format review intelligence for analyst."""
    if not rp:
        rc = (opp or {}).get("review_count", 0) or 0
        rt = (opp or {}).get("rating", 0) or 0
        if rc > 0:
            return (f"Analyse detaillee non disponible (backfill requis), "
                    f"mais le produit a {rc:,} avis Amazon (note {rt}/5). "
                    f"Analyse basee sur ces metriques. Recommander un backfill pour analyse des defauts.")
        return "Aucun avis sur ce produit. Recommander un backfill."
    lines = [
        f"- Improvement Score: {rp.get('improvement_score', 0):.1%}",
        f"- Pain dominant: {rp.get('dominant_pain', 'Aucun detecte')}",
        f"- Avis analyses: {rp.get('reviews_analyzed', 0)} total, {rp.get('negative_reviews_analyzed', 0)} negatifs",
    ]
    defects = rp.get("top_defects", [])
    if defects:
        lines.append("- Defauts identifies:")
        for d in defects[:5]:
            freq_rate = d.get("frequency_rate", d.get("frequency", 0) / max(1, rp.get("negative_reviews_analyzed", 1)))
            lines.append(f"  * {d.get('defect_type')}: {d.get('frequency')} mentions, severite {d.get('severity_score', 0):.2f}, taux {freq_rate:.1%}")
    wishes = rp.get("missing_features", [])
    if wishes:
        lines.append("- Features demandees par les clients:")
        for w in wishes[:5]:
            lines.append(f"  * \"{w.get('feature')}\": {w.get('mentions')} mentions, strength {w.get('wish_strength', 0):.1f}")
    return "\n".join(lines)


class AnalystAgent(BaseAgent):
    """
    Agent d'analyse approfondie.
    """

    agent_type = AgentType.ANALYST
    name = "Analyst Agent"
    description = "Analyse approfondie et validation des opportunites"

    @property
    def system_prompt(self) -> str:
        return ANALYST_SYSTEM_PROMPT

    async def deep_analysis(
        self,
        context: AgentContext,
    ) -> AgentResponse:
        """
        Effectue une analyse approfondie de l'opportunite.
        """
        opp = context.opportunity_data
        thesis = context.thesis or {}
        rp = context.review_profile or {}
        sb = context.spec_bundle or {}

        confidence_val, caveat = compute_confidence(context)

        prompt = f"""Effectue une analyse approfondie de cette opportunite en utilisant TOUTES les donnees disponibles.

## Donnees Produit
- ASIN: {opp.get('asin')}
- Titre: {opp.get('title')}
- Prix Amazon: ${opp.get('amazon_price', 0)}
- Rating: {opp.get('rating', 'N/A')}/5 ({opp.get('review_count', 0)} avis)
- Fenetre: {opp.get('window_days', 0)} jours
- Urgence: {opp.get('urgency_level')} ({opp.get('urgency_label', '')})

## Score final: {opp.get('final_score', 0)}/100
- Base: {opp.get('base_score', 0):.2f} x Multiplicateur temps: {opp.get('time_multiplier', 1):.2f}

## Analyse par composante (avec benchmarks niche)
{_format_score_analysis(opp)}

## Valeur economique estimee
- Profit mensuel: ${opp.get('estimated_monthly_profit', 0):,.0f}
- Valeur annuelle: ${opp.get('estimated_annual_value', 0):,.0f}
- Ajuste risque: ${opp.get('risk_adjusted_value', 0):,.0f}

## Evenements economiques
{chr(10).join(f"- [{ev.get('event_type')}] {ev.get('thesis')} (confiance: {ev.get('confidence')})" for ev in opp.get('economic_events', [])) or 'Aucun'}

## These initiale
{thesis.get('headline', 'N/A')}
{thesis.get('thesis', '')}

## Review Intelligence (Voice of Customer)
{_format_review_data(rp, opp)}

## Spec OEM
{'Disponible: ' + str(sb.get('total_requirements', 0)) + ' exigences, ' + str(sb.get('total_qc_tests', 0)) + ' tests QC' if sb.get('total_requirements') else 'Non generee'}

## Confiance donnees: {confidence_val:.0%}{' — ' + caveat if caveat else ''}

---

Analyse les points suivants en utilisant les benchmarks niche Car Phone Mounts :

1. **VALIDATION DU SCORE**
   - Chaque composante est-elle coherente ? Compare aux benchmarks
   - Le time_multiplier est-il justifie par les events ?
   - Y a-t-il des signaux contradictoires ?

2. **CALCUL DE RENTABILITE (avec vrais couts)**
   - COGS estime ($3-8 selon complexite)
   - Referral fee (15%)
   - FBA fee ($3.50-5.00)
   - Shipping ($2-4/unite)
   - PPC budget (ACoS 20-30%)
   - Marge nette reelle
   - Appliquer la regle du quart : prix/${opp.get('amazon_price', 0)} / 4 = ${(opp.get('amazon_price', 0) or 1) / 4:.2f} COGS max

3. **ANALYSE REVIEW INTELLIGENCE**
   - Les defauts identifies sont-ils corrigeables a cout raisonnable ?
   - Les wishes clients representent-ils un angle differentiant viable ?
   - Le improvement_score justifie-t-il un investissement R&D ?

4. **RISQUES IDENTIFIES**
   - Composantes du score faibles (< benchmark "bon")
   - Risques legaux (brevets MagSafe si applicable)
   - Risques de marche (saturation, guerre des prix)

5. **VERDICT FINAL**
   - GO / NO-GO / BESOIN D'INFO
   - Confiance: {confidence_val:.0%}
   - Action recommandee"""

        try:
            response_text = await self._call_llm(prompt, context, max_tokens=2000)
            context.add_message("agent", response_text)

            # Dynamic actions based on analysis
            actions = []
            final_score = opp.get("final_score", 0)

            if final_score >= 60:
                actions.append({
                    "action": "proceed_sourcing",
                    "label": "Passer au sourcing",
                    "description": "Score solide — chercher des fournisseurs",
                })
            if rp.get("improvement_score", 0) > 0.5:
                actions.append({
                    "action": "view_specs",
                    "label": "Voir la spec OEM",
                    "description": "Consulter les exigences produit",
                })
            actions.append({
                "action": "calculate_profitability",
                "label": "Simuler la rentabilite",
                "description": "Calcul detaille avec prix fournisseur",
            })
            if final_score < 50:
                actions.append({
                    "action": "abandon",
                    "label": "Abandonner cette opportunite",
                    "description": "Les risques sont trop eleves",
                })
            actions.append({
                "action": "back_to_discovery",
                "label": "Retour a Discovery",
                "description": "Voir d'autres opportunites",
            })

            return AgentResponse(
                message=response_text,
                suggested_actions=actions,
                agent_type=self.agent_type,
                status=AgentStatus.COMPLETED,
                confidence=confidence_val,
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
        Calcule la rentabilite precise avec les couts reels.
        """
        opp = context.opportunity_data
        amazon_price = opp.get('amazon_price', 0)

        prompt = f"""Calcule la rentabilite precise pour ce Car Phone Mount avec ces donnees :

**Prix de vente Amazon**: ${amazon_price}
**Prix d'achat (Alibaba)**: ${purchase_price}
**Cout shipping/unite**: ${shipping_cost}

Applique les vrais couts niche :
1. Referral fee Amazon : 15% = ${amazon_price * 0.15:.2f}
2. FBA fulfillment fee : ~$4.00 (petit/leger)
3. COGS : ${purchase_price}
4. Shipping : ${shipping_cost}
5. PPC (estime 10% du CA) : ${amazon_price * 0.10:.2f}

**Cout total/unite** = ${purchase_price + shipping_cost + amazon_price * 0.15 + 4.0 + amazon_price * 0.10:.2f}
**Marge brute** = ${amazon_price - (purchase_price + shipping_cost + amazon_price * 0.15 + 4.0):.2f}
**Marge nette (apres PPC)** = ${amazon_price - (purchase_price + shipping_cost + amazon_price * 0.15 + 4.0 + amazon_price * 0.10):.2f}

Verifie la regle du quart : COGS ${purchase_price} vs max ${amazon_price / 4:.2f}
{'CONFORME' if purchase_price <= amazon_price / 4 else 'ATTENTION: COGS trop eleve'}

Donne un tableau recapitulatif clair avec :
- Marge par unite
- ROI sur 500 unites
- Break-even en mois
- Comparaison avec les benchmarks niche (marge cible 20-35%)"""

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

        opp = context.opportunity_data
        rp = context.review_profile or {}

        prompt = f"""L'utilisateur demande : "{user_input}"

## Contexte complet
- Produit: {opp.get('title', 'Unknown')}
- Prix: ${opp.get('amazon_price', 0)}
- Score: {opp.get('final_score', 0)}/100
- Decomposition: {', '.join(f"{k}={v.get('score',0)}/{v.get('max_score',0)}" for k, v in opp.get('component_scores', {}).items())}
- Profit mensuel: ${opp.get('estimated_monthly_profit', 0):,.0f}
- Avis Amazon: {opp.get('review_count', 0)} avis, note {opp.get('rating', 'N/A')}/5
- Review intelligence: {f"improvement {rp.get('improvement_score', 0):.1%}, pain \"{rp.get('dominant_pain', 'N/A')}\"" if rp else "backfill requis pour analyse detaillee"}

## Benchmarks niche Car Phone Mounts (Amazon FR)
- COGS 3-8 EUR, FBA 3-4.50 EUR, referral 15%, PPC CPC 0.30-1.00 EUR
- TVA 20% incluse, marge nette cible 20-35%
- Regle du quart: prix HT/4 = COGS max

Reponds en tant qu'analyste expert de la niche. Cite les benchmarks quand pertinent.
Si la question concerne la rentabilite, utilise les vrais couts.
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
