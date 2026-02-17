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

# --- NewsAPI ---
NEWSAPI_API_KEY = os.environ.get("NEWSAPI_API_KEY", "")

NEWSAPI_KEYWORDS = [
    "datacenter networking",
    "optical interconnect",
    "silicon photonics",
    "AI infrastructure",
    "switch ASIC",
    "co-packaged optics",
]

# --- Anthropic API (relevance scoring & summarization) ---
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929")

# --- Summarization ---
SUMMARY_OUTPUT_DIR = os.environ.get("NEWS_AGENT_SUMMARY_DIR", "briefings")
# Maximum characters of article text to include per article in the prompt.
SUMMARY_MAX_ARTICLE_CHARS = 4_000
# Maximum total characters of article text sent in one summarization request.
SUMMARY_MAX_TOTAL_CHARS = 80_000

# --- Delivery ---
OUTPUT_DIR = os.environ.get("NEWS_AGENT_OUTPUT_DIR", "output")

# Email via SMTP (set EMAIL_BACKEND=smtp)
EMAIL_BACKEND = os.environ.get("EMAIL_BACKEND", "")  # "smtp" or "sendgrid"
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT") or "587")
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")

# Email via SendGrid (set EMAIL_BACKEND=sendgrid)
SENDGRID_API_KEY = os.environ.get("SENDGRID_API_KEY", "")

# Common email settings
EMAIL_FROM = os.environ.get("EMAIL_FROM", "")
EMAIL_TO = os.environ.get("EMAIL_TO", "")  # comma-separated for multiple
