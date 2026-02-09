"""Extract article body text from URLs.

Primary: trafilatura
Fallback: newspaper3k
"""

import logging
from typing import Optional

import trafilatura
from newspaper import Article

logger = logging.getLogger(__name__)


def extract_with_trafilatura(url: str) -> Optional[str]:
    """Download and extract main text using trafilatura."""
    try:
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            return None
        text = trafilatura.extract(downloaded)
        return text if text and text.strip() else None
    except Exception:
        logger.debug("trafilatura failed for %s", url, exc_info=True)
        return None


def extract_with_newspaper(url: str) -> Optional[str]:
    """Download and extract main text using newspaper3k."""
    try:
        article = Article(url)
        article.download()
        article.parse()
        text = article.text
        return text if text and text.strip() else None
    except Exception:
        logger.debug("newspaper3k failed for %s", url, exc_info=True)
        return None


def extract_text(url: str, existing_raw: Optional[str] = None) -> Optional[str]:
    """Extract article body text from a URL.

    Strategy:
      1. Try trafilatura (best quality).
      2. Fall back to newspaper3k.
      3. If both fail, return the existing raw_text from the feed/API
         (which may be a summary or HTML snippet — better than nothing).
    """
    text = extract_with_trafilatura(url)
    if text:
        logger.debug("Extracted %d chars via trafilatura: %s", len(text), url)
        return text

    text = extract_with_newspaper(url)
    if text:
        logger.debug("Extracted %d chars via newspaper3k: %s", len(text), url)
        return text

    if existing_raw and existing_raw.strip():
        logger.debug("Using existing raw_text (%d chars): %s", len(existing_raw), url)
        return existing_raw.strip()

    logger.warning("No text extracted for %s", url)
    return None
