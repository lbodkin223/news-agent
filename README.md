# news-agent

Automated intelligence briefing system for datacenter networking, hardware interconnects, and AI infrastructure news.

Collects articles from RSS feeds, Reddit, Hacker News, and NewsAPI, scores them for relevance using Claude, and produces structured daily or weekly briefings delivered via file and/or email.

## Pipeline

```
collect → extract → score → summarise → deliver
```

| Stage | What it does |
|---|---|
| **Collect** | Pull articles from RSS feeds (`feedparser`), subreddits (`praw`), Hacker News (REST API), and NewsAPI (`newsapi-python`). Deduplicate by URL. |
| **Extract** | Fetch full article text from each URL using `trafilatura`, with `newspaper3k` as fallback. |
| **Score** | Send title + body to Claude and get a 1–5 relevance score. Articles scoring 3+ are flagged for summarisation. |
| **Summarise** | Batch all flagged articles into a single prompt and generate a structured briefing with sections for Top Stories, Datacenter Networking, Hardware & Interconnects, AI Demand Signals, and Worth Watching. |
| **Deliver** | Save the briefing as a dated markdown file. Optionally send via SMTP or SendGrid. |

## Project structure

```
news-agent/
├── main.py                          # Full pipeline entry point (cron-compatible)
├── requirements.txt
├── .env.template                    # Environment variable template
├── data_collector/
│   ├── __init__.py
│   ├── config.py                    # All settings (env-configurable)
│   ├── database.py                  # SQLite schema, queries, migrations
│   ├── rss_collector.py             # RSS feed collector
│   ├── reddit_collector.py          # Reddit collector (PRAW)
│   ├── hn_collector.py              # Hacker News API collector
│   ├── newsapi_collector.py         # NewsAPI collector
│   ├── extractor.py                 # Article text extraction
│   ├── scorer.py                    # Claude relevance scoring (1–5)
│   ├── pipeline.py                  # Extract + score orchestration
│   ├── summarizer.py                # Briefing generation via Claude
│   ├── delivery.py                  # File + email delivery
│   └── collector.py                 # Collection-only CLI
├── scripts/
│   └── notify_slack.py              # Slack health-check notifications
└── .github/
    └── workflows/
        └── daily-briefing.yml       # GitHub Actions scheduled workflow
```

## Quick start

```bash
# Clone and install
git clone <repo-url> && cd news-agent
pip install -r requirements.txt

# Configure
cp .env.template .env
# Edit .env — at minimum set ANTHROPIC_API_KEY

# Run the full pipeline
python main.py --daily
```

The briefing markdown file is written to `output/` by default.

## Configuration

All settings are read from environment variables (or a `.env` file loaded by your shell). See `.env.template` for the full list.

### Required

| Variable | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` | Claude API key for scoring and summarisation |

### Optional

| Variable | Default | Purpose |
|---|---|---|
| `NEWSAPI_API_KEY` | *(empty — NewsAPI skipped)* | NewsAPI API key |
| `REDDIT_CLIENT_ID` | *(empty — Reddit skipped)* | Reddit app client ID |
| `REDDIT_CLIENT_SECRET` | *(empty)* | Reddit app client secret |
| `REDDIT_USER_AGENT` | `news-agent/0.1 ...` | PRAW user-agent |
| `NEWS_AGENT_DB` | `news_agent.db` | SQLite database path |
| `NEWS_AGENT_OUTPUT_DIR` | `output` | Briefing output directory |
| `NEWS_AGENT_SUMMARY_DIR` | `briefings` | Summariser working directory |
| `ANTHROPIC_MODEL` | `claude-sonnet-4-5-20250929` | Model for scoring + summarisation |
| `EMAIL_BACKEND` | *(empty — email skipped)* | `smtp` or `sendgrid` |
| `EMAIL_FROM` / `EMAIL_TO` | *(empty)* | Sender and recipient addresses |
| `SMTP_HOST` | `smtp.gmail.com` | SMTP server |
| `SMTP_PORT` | `587` | SMTP port |
| `SMTP_USER` / `SMTP_PASSWORD` | *(empty)* | SMTP credentials |
| `SENDGRID_API_KEY` | *(empty)* | SendGrid API key |
| `SLACK_WEBHOOK_URL` | *(empty)* | Slack incoming webhook for alerts |

## Usage

### Full pipeline (recommended)

```bash
# Daily briefing (articles from the last 24 hours)
python main.py --daily

# Weekly briefing (articles from the last 7 days)
python main.py --weekly

# Skip data collection, just re-process and summarise what's in the DB
python main.py --daily --skip-collect

# File output only, no email
python main.py --daily --skip-email

# Verbose logging
python main.py --daily -v
```

### Individual stages

The `collector.py` module exposes finer-grained control:

```bash
# Collect only (no processing or summarisation)
python -m data_collector.collector

# Collect from specific sources
python -m data_collector.collector --sources rss hackernews newsapi

# Collect + extract + score (no briefing)
python -m data_collector.collector --process

# Only extract + score already-collected articles
python -m data_collector.collector --process-only

# Only generate a briefing from already-scored articles
python -m data_collector.collector --summarize-only --mode weekly
```

## Data sources

### RSS feeds (configurable in `config.py`)

- Ars Technica — Technology Lab
- Datacenter Knowledge
- The Register
- ServeTheHome
- Light Reading

### Subreddits

`r/datacenter`, `r/networking`, `r/homelab`, `r/sysadmin`, `r/hardware`

### Hacker News

Scans top and new stories for keyword matches: `datacenter`, `networking`, `switch`, `optical interconnect`, `AI infrastructure`.

### NewsAPI

Searches the `/v2/everything` endpoint for keyword matches: `datacenter networking`, `optical interconnect`, `silicon photonics`, `AI infrastructure`, `switch ASIC`, `co-packaged optics`. Requires a `NEWSAPI_API_KEY` (free tier available at [newsapi.org](https://newsapi.org)).

## Database

SQLite with the following schema:

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER | Primary key |
| `title` | TEXT | Article title |
| `source` | TEXT | e.g. `rss:https://...`, `reddit:r/networking`, `hackernews`, `newsapi` |
| `url` | TEXT | Unique — used for deduplication |
| `published_date` | TEXT | ISO format from the source |
| `raw_text` | TEXT | Summary/body from the feed |
| `extracted_text` | TEXT | Full article text from trafilatura/newspaper3k |
| `relevance_score` | INTEGER | 1–5 from Claude |
| `processed` | INTEGER | 0 = awaiting work, 1 = done |
| `created_at` | TEXT | When the row was inserted |

Articles scoring 3+ stay at `processed=0` until consumed by the summariser.

## Relevance scoring

Claude rates each article 1–5 against three topics:

1. **Datacenter networking infrastructure** — buildouts, topology, deployments
2. **Networking/switch hardware** — optical interconnects, silicon photonics, switch ASICs
3. **AI compute demand impacts** — training clusters, inference scaling, power/cooling

Only articles scoring **3 or higher** are included in briefings.

## Briefing format

```
## Top Stories
3–5 most important developments (2–3 sentences each)

## Datacenter Networking
Infrastructure buildouts, topology changes, new deployments

## Hardware & Interconnects
Switch ASICs, optical transceivers, silicon photonics, cables

## AI Demand Signals
Training clusters, inference scaling, power/cooling constraints

## Worth Watching
Emerging trends, rumors, discussion threads
```

All sections include inline source links.

## GitHub Actions

The workflow in `.github/workflows/daily-briefing.yml` runs the full pipeline daily at **7:00 AM Pacific** (15:00 UTC).

### Features

- **Scheduled + manual dispatch** — runs on cron and via the Actions tab
- **Database persistence** — SQLite DB is uploaded/downloaded as a workflow artifact (90-day retention) to maintain dedup history across runs
- **DB integrity check** — verifies the restored database before running
- **Briefing artifact** — each run's output is saved as a downloadable artifact
- **Slack alerts** — posts to a webhook on success or failure with a link to the run
- **30-minute timeout** — prevents runaway jobs

### Required GitHub Secrets

| Secret | Required | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | Yes | Scoring + summarisation |
| `SLACK_WEBHOOK_URL` | Yes | Pipeline health alerts |
| `NEWSAPI_API_KEY` | No | NewsAPI collection |
| `REDDIT_CLIENT_ID` | No | Reddit collection |
| `REDDIT_CLIENT_SECRET` | No | Reddit collection |
| `EMAIL_BACKEND` | No | `smtp` or `sendgrid` |
| `SMTP_USER` / `SMTP_PASSWORD` | No | SMTP delivery |
| `SENDGRID_API_KEY` | No | SendGrid delivery |
| `EMAIL_FROM` / `EMAIL_TO` | No | Email addresses |

### Cron (alternative to GitHub Actions)

```crontab
# Daily at 07:00 UTC
0 7 * * * cd /opt/news-agent && python3 main.py --daily

# Weekly on Monday at 08:00 UTC
0 8 * * 1 cd /opt/news-agent && python3 main.py --weekly
```

## License

MIT
