"""
Review Signal Extractor (Deterministic)
========================================

Extracts product defect signals from review text using a niche-specific
keyword lexicon. No LLM required — fast, explainable, reproducible.

Usage:
    extractor = ReviewSignalExtractor()
    defects = extractor.extract_defects(reviews)
    wishes = extractor.extract_wish_patterns(reviews)
"""

import math
import re
import logging
from collections import defaultdict
from difflib import SequenceMatcher
from typing import List, Dict, Tuple, Optional

from .review_models import DefectSignal, FeatureRequest

logger = logging.getLogger(__name__)


# =============================================================================
# NICHE-SPECIFIC DEFECT LEXICON — Car Phone Mounts
# =============================================================================
# Each defect type maps to (keywords, severity_weight).
# severity_weight: how critical this defect is for purchase decision (0.0-1.0)
# Keywords are matched case-insensitively in review text.

DEFECT_LEXICON: Dict[str, Tuple[List[str], float]] = {
    "mechanical_failure": (
        [
            "broke", "broken", "snapped", "cracked", "fell apart",
            "stopped working", "collapsed", "shattered", "split",
        ],
        0.9,  # high severity — product failure
    ),
    "poor_grip": (
        [
            "slips", "slides", "falls off", "doesn't hold", "loose",
            "phone fell", "dropped my phone", "can't hold", "keeps falling",
            "doesn't stay", "won't grip", "no grip",
        ],
        0.85,  # high — core function failure
    ),
    "installation_issue": (
        [
            "hard to install", "difficult to mount", "instructions",
            "confusing setup", "can't attach", "won't stick",
            "doesn't stick", "suction doesn't hold", "suction cup failed",
            "won't stay on windshield", "won't stay on dash",
        ],
        0.6,  # medium — usability issue
    ),
    "compatibility_issue": (
        [
            "doesn't fit", "too small", "too big", "case too thick",
            "won't fit my phone", "not compatible", "blocks camera",
            "blocks buttons", "can't charge", "magsafe doesn't work",
            "doesn't work with case", "phone too heavy",
        ],
        0.7,  # medium-high — purchase regret
    ),
    "material_quality": (
        [
            "cheap plastic", "feels flimsy", "low quality", "thin",
            "feels cheap", "poor quality", "plastic broke",
            "rubber peeled", "paint chipped", "creaks",
        ],
        0.5,  # medium — perception issue
    ),
    "vibration_noise": (
        [
            "vibrates", "rattles", "shakes", "buzzes", "noisy",
            "wobbles", "jiggles", "unstable on bumps",
        ],
        0.55,  # medium — daily annoyance
    ),
    "heat_issue": (
        [
            "overheats", "gets hot", "phone heats up", "too hot",
            "blocks airflow", "heat damage",
        ],
        0.65,  # medium-high — safety concern
    ),
    "size_fit": (
        [
            "too bulky", "blocks view", "obstructs", "takes too much space",
            "too large", "sticks out", "in the way",
        ],
        0.4,  # lower — preference issue
    ),
    "durability": (
        [
            "after a month", "after a week", "few months later",
            "didn't last", "wore out", "degraded", "stopped sticking",
            "adhesive wore off", "suction lost over time",
        ],
        0.75,  # high — longevity failure
    ),
}

# =============================================================================
# "I WISH" PATTERNS — regex-based feature request detection
# =============================================================================

WISH_PATTERNS = [
    re.compile(r"i (?:\w+ )?wish (?:it )?(?:had|was|were|could|would)(.*?)(?:\.|!|$)", re.IGNORECASE),
    re.compile(r"would be (?:nice|great|better|awesome) if(.*?)(?:\.|!|$)", re.IGNORECASE),
    re.compile(r"should (?:have|come with|include)(.*?)(?:\.|!|$)", re.IGNORECASE),
    re.compile(r"needs? (?:a |an |to have )(.*?)(?:\.|!|$)", re.IGNORECASE),
    re.compile(r"(?:missing|lacks?) (?:a |an )?(.*?)(?:\.|!|$)", re.IGNORECASE),
    re.compile(r"if only (?:it )?(.*?)(?:\.|!|$)", re.IGNORECASE),
]


# =============================================================================
# WISH NORMALISATION (V1.5) — stopwords + fuzzy grouping
# =============================================================================

# Common English stopwords to strip from wish text before grouping.
# Kept minimal to avoid over-normalising domain-specific terms.
_ENGLISH_STOPWORDS = {
    "a", "an", "the", "it", "its", "is", "was", "were", "be", "been",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "can", "may", "might", "shall", "to", "of", "in", "on",
    "for", "with", "at", "by", "from", "that", "this", "these", "those",
    "and", "or", "but", "not", "so", "if", "then", "also", "just",
    "very", "really", "too", "more", "much", "some", "any", "all",
    "my", "your", "their", "our", "i", "me", "you", "we", "they",
    "came", "come", "came", "built", "one", "like",
}

# Niche-specific stopwords for Car Phone Mounts.
# These words appear in almost every wish and create artificial overlaps
# during fuzzy grouping (e.g. "phone mount wireless" vs "phone mount clip").
_NICHE_STOPWORDS = {
    "phone", "mount", "car", "holder", "dashboard", "windshield",
    "stand", "cradle", "bracket", "device",
}

WISH_STOPWORDS = frozenset(_ENGLISH_STOPWORDS | _NICHE_STOPWORDS)

# Minimum similarity ratio (0–1) to merge two wish keys into one group.
WISH_SIMILARITY_THRESHOLD = 0.6

# Minimum number of shared tokens (after normalisation) required before
# SequenceMatcher is even considered. Prevents merging unrelated wishes
# that happen to have a high character-level ratio (e.g. "wireless charging"
# vs "fast charging cable included").
MIN_SHARED_TOKENS = 1


def normalize_wish_key(text: str) -> str:
    """
    Normalize wish text for grouping:
    1. Lowercase
    2. Strip punctuation
    3. Remove stopwords
    4. Collapse whitespace
    """
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s]", "", text)
    words = [w for w in text.split() if w not in WISH_STOPWORDS and len(w) > 1]
    return " ".join(words)


def group_similar_wishes(
    wish_hits: Dict[str, Dict],
    threshold: float = WISH_SIMILARITY_THRESHOLD,
) -> Dict[str, Dict]:
    """
    Merge wish entries whose normalized keys are similar.

    Uses SequenceMatcher for fuzzy matching. O(n²) but n is small
    (typically <50 distinct wish keys per ASIN).

    Returns:
        Merged dict where each canonical key aggregates counts and quotes
        from all similar keys.
    """
    # Build normalized key → original keys mapping
    norm_to_originals: Dict[str, List[str]] = defaultdict(list)
    for raw_key in wish_hits:
        norm = normalize_wish_key(raw_key)
        if norm:
            norm_to_originals[norm].append(raw_key)

    # Group normalized keys by similarity (with token overlap guard)
    norm_keys = list(norm_to_originals.keys())
    merged_groups: List[List[str]] = []
    used = set()

    for i, k1 in enumerate(norm_keys):
        if k1 in used:
            continue
        group = [k1]
        used.add(k1)
        tokens1 = set(k1.split())
        for j in range(i + 1, len(norm_keys)):
            k2 = norm_keys[j]
            if k2 in used:
                continue
            # Guard: require MIN_SHARED_TOKENS common words before fuzzy match
            tokens2 = set(k2.split())
            if len(tokens1 & tokens2) < MIN_SHARED_TOKENS:
                continue
            ratio = SequenceMatcher(None, k1, k2).ratio()
            if ratio >= threshold:
                group.append(k2)
                used.add(k2)
        merged_groups.append(group)

    # Rebuild wish_hits with merged groups
    merged: Dict[str, Dict] = {}
    for group in merged_groups:
        # Collect all original keys in this group
        all_originals = []
        for norm_key in group:
            all_originals.extend(norm_to_originals[norm_key])

        # Aggregate counts, quotes, and helpful_votes
        total_count = 0
        total_helpful = 0
        all_quotes = []
        for orig in all_originals:
            total_count += wish_hits[orig]["count"]
            total_helpful += wish_hits[orig].get("helpful_votes", 0)
            all_quotes.extend(wish_hits[orig]["quotes"])

        # Canonical key selection (V1.6):
        # 1. Most frequent original phrasing
        # 2. Tie-break: longest after stopword removal (most informative)
        # 3. Final tie-break: shortest raw (most concise)
        canonical = max(
            all_originals,
            key=lambda k: (
                wish_hits[k]["count"],
                len(normalize_wish_key(k)),
                -len(k),
            ),
        )
        merged[canonical] = {
            "count": total_count,
            "quotes": all_quotes[:3],  # cap quotes
            "helpful_votes": total_helpful,
        }

    return merged


class ReviewSignalExtractor:
    """
    Deterministic defect and wish extractor using keyword matching.

    No LLM calls. Fast, reproducible, explainable.
    Suitable for running inside the main pipeline without breaking SLO.
    """

    def __init__(self, lexicon: Optional[Dict] = None):
        self.lexicon = lexicon or DEFECT_LEXICON

    def extract_defects(
        self,
        reviews: List[Dict],
        max_quotes: int = 3,
    ) -> List[DefectSignal]:
        """
        Extract defect signals from review texts.

        Args:
            reviews: List of dicts with at least 'body' and 'rating' keys.
            max_quotes: Max example quotes to keep per defect type.

        Returns:
            List of DefectSignal, sorted by severity_score descending.
        """
        # Filter to negative reviews only (rating <= 3)
        negative_reviews = [
            r for r in reviews
            if r.get("rating", 5) <= 3 and r.get("body")
        ]

        if not negative_reviews:
            logger.info("No negative reviews to analyze")
            return []

        # Count defect mentions
        defect_counts: Dict[str, Dict] = defaultdict(
            lambda: {"count": 0, "quotes": []}
        )

        for review in negative_reviews:
            text = review["body"].lower()
            for defect_type, (keywords, _weight) in self.lexicon.items():
                if any(kw in text for kw in keywords):
                    defect_counts[defect_type]["count"] += 1
                    if len(defect_counts[defect_type]["quotes"]) < max_quotes:
                        # Keep original case for quotes
                        snippet = review["body"][:300]
                        defect_counts[defect_type]["quotes"].append(snippet)

        # Build DefectSignal list
        total = len(reviews)
        negative = len(negative_reviews)
        signals = []

        for defect_type, data in defect_counts.items():
            if data["count"] == 0:
                continue

            _, base_weight = self.lexicon[defect_type]
            freq_rate = data["count"] / negative if negative > 0 else 0

            # severity = base_weight * frequency_factor
            # frequency_factor: 1.0 if 50%+ of negatives mention it, scaled linearly
            frequency_factor = min(1.0, freq_rate * 2)
            severity = round(base_weight * frequency_factor, 2)

            signals.append(DefectSignal(
                defect_type=defect_type,
                frequency=data["count"],
                severity_score=min(1.0, severity),
                example_quotes=data["quotes"],
                total_reviews_scanned=total,
                negative_reviews_scanned=negative,
            ))

        signals.sort(key=lambda s: s.severity_score, reverse=True)
        return signals

    def extract_wish_patterns(
        self,
        reviews: List[Dict],
        max_quotes: int = 3,
    ) -> List[FeatureRequest]:
        """
        Extract 'I wish' feature requests using regex patterns.

        V1.5: after raw extraction, applies stopword normalisation +
        fuzzy grouping (SequenceMatcher) to merge similar phrasings.
        e.g. "wireless charging built in" + "wireless charging" → same group.

        Args:
            reviews: List of dicts with at least 'body' key.
            max_quotes: Max example quotes per feature.

        Returns:
            List of FeatureRequest, sorted by mentions descending.
        """
        wish_hits: Dict[str, Dict] = defaultdict(
            lambda: {"count": 0, "quotes": [], "helpful_votes": 0}
        )

        for review in reviews:
            body = review.get("body", "")
            if not body:
                continue

            helpful = int(review.get("helpful_votes", 0) or 0)

            for pattern in WISH_PATTERNS:
                matches = pattern.findall(body)
                for match in matches:
                    feature = match.strip().rstrip(".,!?")
                    if len(feature) < 5 or len(feature) > 100:
                        continue  # skip noise

                    # Lowercase key (raw, before normalisation)
                    key = feature.lower().strip()
                    wish_hits[key]["count"] += 1
                    wish_hits[key]["helpful_votes"] += helpful
                    if len(wish_hits[key]["quotes"]) < max_quotes:
                        wish_hits[key]["quotes"].append(body[:300])

        # V1.5: fuzzy-group similar wishes before counting
        if wish_hits:
            wish_hits = group_similar_wishes(dict(wish_hits))

        # Build FeatureRequest list (only if mentioned 2+ times)
        requests = []
        total = len(reviews)

        for feature, data in wish_hits.items():
            if data["count"] < 2:
                continue  # skip one-offs

            helpful = data.get("helpful_votes", 0)
            confidence = min(1.0, data["count"] / max(1, total) * 10)
            strength = data["count"] + math.log1p(helpful)

            requests.append(FeatureRequest(
                feature=feature,
                mentions=data["count"],
                confidence=round(confidence, 2),
                source_quotes=data["quotes"],
                helpful_votes=helpful,
                wish_strength=round(strength, 2),
            ))

        requests.sort(key=lambda r: r.wish_strength, reverse=True)
        return requests
