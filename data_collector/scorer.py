"""Score article relevance using the Anthropic API."""

import logging
import os
import re
from typing import Optional

import anthropic

from data_collector.config import ANTHROPIC_MODEL

logger = logging.getLogger(__name__)

SCORING_PROMPT = """\
You are a relevance classifier for a news monitoring system focused on
datacenter and networking infrastructure.

Rate the following article on a scale of 1-5 for relevance to THESE topics:
  • Datacenter networking infrastructure (design, buildouts, operations)
  • Networking / switch hardware — especially optical interconnects and
    silicon photonics
  • AI compute demand and its impact on networking infrastructure

Scoring guide:
  1 = Completely unrelated
  2 = Tangentially related (mentions tech industry but not the topics above)
  3 = Moderately relevant (discusses adjacent topics like cloud, general
      networking, or datacenter power/cooling)
  4 = Highly relevant (directly about datacenter networking, switch
      hardware, or AI infra networking)
  5 = Extremely relevant (deep coverage of optical interconnects, silicon
      photonics, or AI-driven network architecture changes)

Respond with ONLY a single integer (1-5) and nothing else.

Article title: {title}

Article text (truncated):
{text}
"""

# Keep the text sent to the API under ~6 000 tokens worth of characters.
_MAX_TEXT_CHARS = 12_000


def _build_prompt(title: str, text: str) -> str:
    truncated = text[:_MAX_TEXT_CHARS] if text else "(no body text available)"
    return SCORING_PROMPT.format(title=title, text=truncated)


def _parse_score(response_text: str) -> Optional[int]:
    """Extract the first integer 1-5 from the model response."""
    match = re.search(r"[1-5]", response_text.strip())
    if match:
        return int(match.group())
    return None


def score_article(
    title: str,
    text: str,
    client: anthropic.Anthropic | None = None,
) -> int:
    """Return a 1-5 relevance score for an article.

    Falls back to score 1 if the API call fails.
    """
    api_client = client or anthropic.Anthropic()  # reads ANTHROPIC_API_KEY env var

    prompt = _build_prompt(title, text)

    try:
        message = api_client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=8,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = message.content[0].text
        score = _parse_score(raw)
        if score is None:
            logger.warning("Could not parse score from API response: %r", raw)
            return 1
        return score
    except Exception:
        logger.exception("Anthropic API call failed for article: %s", title)
        return 1
