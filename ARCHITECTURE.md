# News Agent Architecture

## Overview

News Agent is an automated news intelligence pipeline focused on **datacenter networking, optical interconnects, silicon photonics, and AI infrastructure**. It collects articles from multiple sources, uses Claude to score their relevance and generate structured briefings, and delivers the results via file and/or email.

## Pipeline Stages

The application runs a 4-stage pipeline: **Collect -> Extract + Score -> Summarize -> Deliver**

```
 RSS Feeds ─┐
 Reddit ────┤                    ┌──────────────┐    ┌─────────────┐    ┌──────────┐
 Hacker    ─┼─> SQLite DB ──────>│ Extract text │───>│ Score (1-5) │───>│Summarize │──> Briefing.md
 News       │   (dedup by URL)   │ (trafilatura │    │ via Claude  │    │ via      │    + Email
 NewsAPI ───┘                    │  / newspaper)│    │             │    │ Claude   │
                                 └──────────────┘    └─────────────┘    └──────────┘
                                       Stage 2              Stage 2        Stage 3      Stage 4
         Stage 1
```

### Stage 1: Collection (`data_collector/collector.py`)

Pulls articles from 4 sources:

- **RSS** (`rss_collector.py`): Parses 5 hardcoded feeds (Ars Technica, The Register, ServeTheHome, etc.) via `feedparser`.
- **Reddit** (`reddit_collector.py`): Fetches 25 hot posts per subreddit from r/datacenter, r/networking, r/homelab, r/sysadmin, r/hardware via PRAW. Skips gracefully if credentials are missing.
- **Hacker News** (`hn_collector.py`): Scans top 500 + new 500 stories from the HN Firebase API, keeping only those matching keywords like "datacenter", "optical interconnect", "AI infrastructure".
- **NewsAPI** (`newsapi_collector.py`): Searches the last 7 days for keywords like "datacenter networking", "silicon photonics", "co-packaged optics". Skips if API key is missing.

All articles are deduplicated by URL and stored in a SQLite database.

### Stage 2: Extract + Score (`pipeline.py`)

For each unprocessed article:

1. **Text extraction** (`extractor.py`): Downloads the full article body using `trafilatura` (primary), falling back to `newspaper3k`, then to the raw feed text.
2. **Relevance scoring** (`scorer.py`): Sends the title + truncated body (max 12K chars) to the Anthropic API (Claude Sonnet) with a prompt asking it to rate relevance 1-5 for datacenter/networking topics.
   - Score >= 3: article stays flagged for summarization (`processed=0`)
   - Score < 3: article is dismissed (`processed=1`)

### Stage 3: Summarize (`summarizer.py`)

- Queries all flagged articles (score >= 3, `processed=0`) within the lookback window (24h for daily, 7 days for weekly).
- Batches them into a single prompt (up to 80K chars total, 4K per article) sent to Claude with a system prompt defining 5 output sections:
  - **Top Stories** (3-5 most important)
  - **Datacenter Networking** (infrastructure, deployments, outages)
  - **Hardware & Interconnects** (ASICs, transceivers, silicon photonics)
  - **AI Demand Signals** (training clusters, GPU networking, power)
  - **Worth Watching** (emerging trends, rumors)
- Writes the markdown briefing to disk and marks consumed articles as processed.

### Stage 4: Deliver (`delivery.py`)

- **Always** saves the briefing as a timestamped markdown file.
- **Optionally** emails it via SMTP or SendGrid based on the `EMAIL_BACKEND` env var.

## Database Schema

SQLite with a single `articles` table:

| Column | Purpose |
|---|---|
| `url` (UNIQUE) | Deduplication key |
| `raw_text` | Feed summary/snippet from collection |
| `extracted_text` | Full article body from extraction |
| `relevance_score` | 1-5 from Claude |
| `processed` | 0 = needs work, 1 = done |
| `created_at` | Insertion timestamp for time-windowed queries |

**Article lifecycle:** Insert (processed=0) -> Extract text -> Score -> If score >= 3, keep processed=0 for summarizer -> Include in briefing -> Mark processed=1.

## Automation

- **GitHub Actions** (`.github/workflows/daily-briefing.yml`): Runs daily at 7 AM Pacific. Caches the SQLite DB between runs as an artifact (90-day retention). Uploads each briefing as an artifact (30-day retention).
- **Slack notifications** (`scripts/notify_slack.py`): Posts success/failure alerts to a Slack webhook after each run.

## Running

```bash
python main.py --daily               # Full daily pipeline
python main.py --weekly              # Full weekly pipeline
python main.py --daily --skip-collect  # Re-process existing articles only
python main.py --daily --skip-email    # File output only
python main.py --daily -v              # Verbose/debug logging
```

## Key Design Decisions

- **SQLite with URL dedup**: Simple, no external DB needed, persists between GitHub Actions runs via artifact caching.
- **Two-pass AI processing**: Cheap per-article scoring (8 max tokens) first, expensive summarization only on high-scoring articles -- keeps API costs down.
- **Graceful degradation**: All external sources are optional; missing API keys cause silent skips, not crashes.
- **Three-tier text extraction**: Prioritizes quality (trafilatura) with reliable fallbacks.
