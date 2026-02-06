"""
Agent Guardrails - Anti-Bullshit by Design
==========================================

Rules that structurally prevent agents from becoming dream sellers.

Philosophy: "Un agent n'a pas le droit de conclure sans expliciter une limite.
            Si une réponse ne contient aucune incertitude, elle est invalide."

Usage:
    from src.ai.guardrails import validate_agent_response, FORBIDDEN_PHRASES

    # Validate agent output
    is_valid, errors = validate_agent_response(agent_output)
    if not is_valid:
        # Handle invalid response
"""

import re
from typing import List, Tuple


# =============================================================================
# FORBIDDEN PHRASES (absolute)
# =============================================================================

FORBIDDEN_PHRASES = [
    # Absolute certainty
    "c'est une excellente opportunité",
    "c'est une bonne opportunité",
    "excellente opportunité",
    "opportunité évidente",
    "opportunité certaine",

    # Direct recommendations
    "tu devrais lancer",
    "vous devriez lancer",
    "je recommande de lancer",
    "je vous recommande",
    "je te recommande",
    "lancez ce produit",
    "lance ce produit",

    # False certainty
    "le succès est très probable",
    "le succès est garanti",
    "succès garanti",
    "succès assuré",
    "peu de risques",
    "sans risque",
    "risque minimal",
    "fortement recommandé",
    "hautement recommandé",

    # Over-promising
    "produit gagnant",
    "coup sûr",
    "opportunité en or",
    "ne ratez pas",
    "dernière chance",
    "opportunité unique",

    # False authority
    "je suis certain",
    "je suis sûr",
    "avec certitude",
    "sans aucun doute",
    "il est évident que",
    "il est clair que",
]


# =============================================================================
# REQUIRED UNCERTAINTY MARKERS
# =============================================================================

UNCERTAINTY_MARKERS = [
    # Explicit limits
    "incertain",
    "limite",
    "limitation",
    "manque",
    "manquant",
    "partiel",
    "partiellement",
    "incomplet",
    "non validé",
    "non confirmé",
    "à confirmer",
    "à valider",

    # Risk language
    "risque",
    "risques",
    "mais",
    "cependant",
    "toutefois",
    "néanmoins",

    # Conditional language
    "dépend",
    "si",
    "pourrait",
    "possible",
    "potentiel",
    "estimé",
    "estimation",
    "approximatif",

    # Data quality
    "données partielles",
    "analyse incomplète",
    "informations manquantes",
]


# =============================================================================
# VALIDATION RULES
# =============================================================================

def contains_forbidden_phrase(text: str) -> List[str]:
    """
    Check if text contains forbidden phrases.

    Returns:
        List of forbidden phrases found (empty if none)
    """
    text_lower = text.lower()
    found = []

    for phrase in FORBIDDEN_PHRASES:
        if phrase in text_lower:
            found.append(phrase)

    return found


def contains_uncertainty_marker(text: str) -> bool:
    """
    Check if text contains at least one uncertainty marker.

    Returns:
        True if uncertainty is expressed
    """
    text_lower = text.lower()

    for marker in UNCERTAINTY_MARKERS:
        if marker in text_lower:
            return True

    return False


def validate_score_contextualization(text: str) -> bool:
    """
    If a score is mentioned, it must be contextualized.

    Rule: Score without "mais" or "cependant" is invalid.
    """
    text_lower = text.lower()

    # Check if score is mentioned
    score_patterns = [
        r"score[:\s]+\d+",
        r"score de \d+",
        r"score économique",
        r"\d+/100",
        r"\d+ points",
    ]

    has_score = any(re.search(p, text_lower) for p in score_patterns)

    if not has_score:
        return True  # No score mentioned, rule doesn't apply

    # If score is mentioned, must have qualifying language
    qualifiers = ["mais", "cependant", "toutefois", "néanmoins", "avec", "bien que"]
    return any(q in text_lower for q in qualifiers)


def validate_agent_response(
    text: str,
    require_uncertainty: bool = True,
    check_score_context: bool = True,
) -> Tuple[bool, List[str]]:
    """
    Validate an agent response against guardrails.

    Args:
        text: Agent response text
        require_uncertainty: If True, response must contain uncertainty marker
        check_score_context: If True, scores must be contextualized

    Returns:
        Tuple of (is_valid, list of error messages)
    """
    errors = []

    # Rule 1: No forbidden phrases
    forbidden_found = contains_forbidden_phrase(text)
    if forbidden_found:
        errors.append(f"Phrases interdites: {', '.join(forbidden_found)}")

    # Rule 2: Must express uncertainty
    if require_uncertainty and not contains_uncertainty_marker(text):
        errors.append("Aucune incertitude explicite. Ajoutez une limitation ou un risque.")

    # Rule 3: Scores must be contextualized
    if check_score_context and not validate_score_contextualization(text):
        errors.append("Score mentionné sans contextualisation (ajoutez 'mais' ou équivalent)")

    is_valid = len(errors) == 0
    return is_valid, errors


# =============================================================================
# SYSTEM PROMPT ADDITIONS
# =============================================================================

AGENT_GUARDRAIL_PROMPT = """
RÈGLES ABSOLUES (non négociables):

1. Tu ne dois JAMAIS utiliser ces phrases ou variations:
   - "C'est une excellente opportunité"
   - "Tu devrais lancer ce produit"
   - "Le succès est très probable"
   - "Peu de risques"
   - "Fortement recommandé"
   - "Produit gagnant"
   - Toute phrase qui supprime l'incertitude

2. Toute réponse DOIT contenir au moins UNE limite explicite:
   - "Cette analyse est partielle car…"
   - "Le principal risque identifié est…"
   - "Ces conclusions dépendent de…"
   - "Une validation supplémentaire est nécessaire sur…"

3. Si tu mentionnes un score, tu DOIS le qualifier:
   ❌ "Score: 72/100" (interdit seul)
   ✅ "Score: 72/100, mais les reviews n'ont pas été analysées en profondeur"

4. Formulations autorisées:
   - "Les signaux indiquent…"
   - "Sur la base des données disponibles…"
   - "Cette opportunité devient intéressante si…"
   - "Le principal risque identifié est…"

RAPPEL: Tu n'es pas un vendeur. Tu es une sonde économique.
Ton rôle est d'éclairer, pas de convaincre.
"""


def get_guardrail_prompt() -> str:
    """Return the guardrail prompt to append to agent system prompts."""
    return AGENT_GUARDRAIL_PROMPT


# =============================================================================
# TESTS (for CI/CD)
# =============================================================================

def test_forbidden_phrases():
    """Test that forbidden phrases are detected."""
    bad_responses = [
        "C'est une excellente opportunité pour vous!",
        "Je recommande de lancer ce produit immédiatement.",
        "Le succès est très probable avec cette niche.",
        "Peu de risques sur ce marché.",
    ]

    for response in bad_responses:
        found = contains_forbidden_phrase(response)
        assert len(found) > 0, f"Should detect forbidden phrase in: {response}"


def test_uncertainty_requirement():
    """Test that uncertainty markers are required."""
    # Bad: no uncertainty
    bad_response = "Ce produit a un score de 75 et une bonne demande."
    is_valid, errors = validate_agent_response(bad_response)
    assert not is_valid, "Should require uncertainty"

    # Good: has uncertainty
    good_response = "Ce produit a un score de 75, mais l'analyse reviews est incomplète."
    is_valid, errors = validate_agent_response(good_response)
    assert is_valid, f"Should be valid: {errors}"


def test_score_contextualization():
    """Test that scores must be contextualized."""
    # Bad: score without context
    bad_response = "Le score économique est de 82/100. La demande est forte."
    assert not validate_score_contextualization(bad_response)

    # Good: score with context
    good_response = "Le score économique est de 82/100, mais cela dépend des données reviews."
    assert validate_score_contextualization(good_response)


if __name__ == "__main__":
    # Run tests
    test_forbidden_phrases()
    test_uncertainty_requirement()
    test_score_contextualization()
    print("✅ All guardrail tests passed!")
