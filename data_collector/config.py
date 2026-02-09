"""Configuration for data collection sources and database."""

import os

# --- Database ---
DATABASE_PATH = os.environ.get("NEWS_AGENT_DB", "news_agent.db")

# --- RSS Feeds ---
RSS_FEEDS = [
    "https://feeds.arstechnica.com/arstechnica/technology-lab",
    "https://www.datacenterknowledge.com/rss.xml",
    "https://www.theregister.com/headlines.atom",
    "https://feeds.feedburner.com/servethehomecom",
    "https://lightreading.com/rss.xml",
]

# --- Reddit (PRAW) ---
# Set these environment variables or override in a local config.
REDDIT_CLIENT_ID = os.environ.get("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET = os.environ.get("REDDIT_CLIENT_SECRET", "")
REDDIT_USER_AGENT = os.environ.get(
    "REDDIT_USER_AGENT", "news-agent/0.1 by YourRedditUsername"
)

SUBREDDITS = [
    "datacenter",
    "networking",
    "homelab",
    "sysadmin",
    "hardware",
]

REDDIT_POST_LIMIT = 25  # posts per subreddit

# --- Hacker News ---
HN_API_BASE = "https://hacker-news.firebaseio.com/v0"

HN_KEYWORDS = [
    "datacenter",
    "networking",
    "switch",
    "optical interconnect",
    "AI infrastructure",
]

HN_MAX_STORIES = 500  # how many top/new stories to scan

# --- Anthropic API (relevance scoring) ---
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929")
