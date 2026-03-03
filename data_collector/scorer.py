"""Score article relevance using weighted keyword matching.

No external API required.  Keywords are grouped into tiers that mirror
the original 1-5 scoring rubric:

  5 = Extremely relevant (optical interconnects, silicon photonics,
      AI-driven network architecture)
  4 = Highly relevant (datacenter networking, switch hardware, AI infra)
  3 = Moderately relevant (adjacent: cloud, general networking, power)
  2 = Tangentially related (tech industry, vendor names, servers)
  1 = No keyword matches at all
"""

import logging

logger = logging.getLogger(__name__)

# ── keyword tiers (all matched case-insensitively) ───────────────────────────

TIER_5_KEYWORDS = [
    "silicon photonics",
    "co-packaged optics",
    "optical interconnect",
    "coherent optics",
    "photonic integrated circuit",
]

TIER_4_KEYWORDS = [
    "datacenter networking",
    "data center networking",
    "switch asic",
    "network fabric",
    "spine-leaf",
    "spine leaf",
    "leaf-spine",
    "top of rack",
    "tor switch",
    "optical transceiver",
    "400g",
    "800g",
    "1.6t",
    "nvlink",
    "infiniband",
    "ultra ethernet",
    "smartnic",
    "ai infrastructure",
    "ai cluster",
    "gpu cluster",
    "training cluster",
    "inference cluster",
    "network switch",
    "dpu",
]

TIER_3_KEYWORDS = [
    "datacenter",
    "data center",
    "colocation",
    "networking",
    "ethernet",
    "cloud infrastructure",
    "hyperscaler",
    "hyperscale",
    "accelerator",
    "fiber optic",
    "wavelength",
    "multiplexing",
    "power delivery",
    "network architecture",
]

TIER_2_KEYWORDS = [
    "semiconductor",
    "server",
    "broadcom",
    "arista",
    "cisco",
    "juniper",
    "nvidia",
    "intel",
    "cloud computing",
]

_TIERS = [
    (5, TIER_5_KEYWORDS),
    (4, TIER_4_KEYWORDS),
    (3, TIER_3_KEYWORDS),
    (2, TIER_2_KEYWORDS),
]


def score_article(title: str, text: str) -> int:
    """Return a 1-5 relevance score for an article using keyword matching.

    Strategy:
      1. Find the highest keyword tier that matches in the title or body.
      2. If the highest-tier match appears in the *title*, boost by 1
         (capped at 5) since title mentions are a strong signal.
      3. No matches at all -> score 1.
    """
    title_lower = title.lower()
    text_lower = (text or "").lower()

    max_tier = 0
    title_match_tier = 0

    for tier, keywords in _TIERS:
        for kw in keywords:
            if kw in title_lower:
                if tier > max_tier:
                    max_tier = tier
                if tier > title_match_tier:
                    title_match_tier = tier
            elif kw in text_lower:
                if tier > max_tier:
                    max_tier = tier

    if max_tier == 0:
        return 1

    score = max_tier
    if title_match_tier >= max_tier and score < 5:
        score += 1

    return min(score, 5)
