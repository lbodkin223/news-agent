#!/usr/bin/env python3
"""Post a health-check message to a Slack incoming webhook.

Usage (from GitHub Actions):
    python scripts/notify_slack.py --failure  --run-url <url>
    python scripts/notify_slack.py --success  --run-url <url>

Requires the SLACK_WEBHOOK_URL environment variable.  If the variable
is not set the script exits silently (exit 0) so that workflows still
succeed when Slack is not configured.
"""

import argparse
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone


def _post_slack(webhook_url: str, payload: dict) -> bool:
    """POST a JSON payload to a Slack webhook.  Returns True on success."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        webhook_url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return 200 <= resp.status < 300
    except Exception as exc:
        print(f"Slack notification failed: {exc}", file=sys.stderr)
        return False


def _build_failure_payload(run_url: str) -> dict:
    ts = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return {
        "text": ":red_circle: *News Agent pipeline failed*",
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        ":red_circle: *News Agent — daily pipeline failed*\n"
                        f"Time: {ts}\n"
                        f"<{run_url}|View workflow run>"
                    ),
                },
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": (
                            "Check the Actions log for details.  Common causes: "
                            "expired API keys, rate limits, network timeouts."
                        ),
                    }
                ],
            },
        ],
    }


def _build_success_payload(run_url: str) -> dict:
    ts = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return {
        "text": ":large_green_circle: News Agent pipeline succeeded",
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        ":large_green_circle: *News Agent — daily briefing delivered*\n"
                        f"Time: {ts}\n"
                        f"<{run_url}|View workflow run>"
                    ),
                },
            },
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Post pipeline status to Slack")
    status = parser.add_mutually_exclusive_group(required=True)
    status.add_argument("--failure", action="store_true", help="Report a failure")
    status.add_argument("--success", action="store_true", help="Report success")
    parser.add_argument(
        "--run-url",
        default="",
        help="URL to the GitHub Actions workflow run",
    )
    args = parser.parse_args()

    webhook_url = os.environ.get("SLACK_WEBHOOK_URL", "").strip()
    if not webhook_url:
        print("SLACK_WEBHOOK_URL not set — skipping Slack notification.")
        return 0

    if args.failure:
        payload = _build_failure_payload(args.run_url)
    else:
        payload = _build_success_payload(args.run_url)

    ok = _post_slack(webhook_url, payload)
    if ok:
        print("Slack notification sent.")
        return 0
    else:
        print("Slack notification failed.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
