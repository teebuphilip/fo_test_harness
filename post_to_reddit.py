#!/usr/bin/env python3
"""
post_to_reddit.py

Reads the latest harness summary file from harness_summaries/ and posts
it to r/microsaas.

Required env vars:
  REDDIT_CLIENT_ID
  REDDIT_CLIENT_SECRET
  REDDIT_USERNAME
  REDDIT_PASSWORD

Usage:
  python post_to_reddit.py                  # posts latest summary
  python post_to_reddit.py --dry-run        # prints what would be posted, no submission
"""

import os
import sys
import argparse
from pathlib import Path

try:
    import praw
except ImportError:
    print("Error: praw not installed. Run: pip install praw")
    sys.exit(1)


SUBREDDIT   = "microsaas"
HARNESS_DIR = Path(__file__).parent / "harness_summaries"


def latest_summary_file() -> Path:
    files = sorted(HARNESS_DIR.glob("harness_summary_*.txt"))
    if not files:
        print(f"Error: no summary files found in {HARNESS_DIR}")
        sys.exit(1)
    return files[-1]


def parse_summary(path: Path) -> tuple[str, str]:
    """Extract title and body from a harness summary file."""
    text = path.read_text(encoding="utf-8").strip()
    lines = text.splitlines()

    title = ""
    body_lines = []
    in_body = False

    for line in lines:
        if line.startswith("Title:"):
            title = line.removeprefix("Title:").strip()
        elif line.startswith("Body:"):
            in_body = True
        elif in_body:
            body_lines.append(line)

    body = "\n".join(body_lines).strip()

    if not title or not body:
        print(f"Error: could not parse title/body from {path}")
        sys.exit(1)

    return title, body


def post(title: str, body: str, dry_run: bool = False):
    if dry_run:
        print("=== DRY RUN — nothing will be submitted ===\n")
        print(f"Subreddit : r/{SUBREDDIT}")
        print(f"Title     : {title}")
        print(f"\nBody:\n{body}")
        return

    client_id     = os.environ.get("REDDIT_CLIENT_ID")
    client_secret = os.environ.get("REDDIT_CLIENT_SECRET")
    username      = os.environ.get("REDDIT_USERNAME")
    password      = os.environ.get("REDDIT_PASSWORD")

    missing = [k for k, v in {
        "REDDIT_CLIENT_ID":     client_id,
        "REDDIT_CLIENT_SECRET": client_secret,
        "REDDIT_USERNAME":      username,
        "REDDIT_PASSWORD":      password,
    }.items() if not v]

    if missing:
        print(f"Error: missing env vars: {', '.join(missing)}")
        sys.exit(1)

    reddit = praw.Reddit(
        client_id=client_id,
        client_secret=client_secret,
        username=username,
        password=password,
        user_agent=f"fo_harness_bot/1.0 by u/{username}",
    )

    submission = reddit.subreddit(SUBREDDIT).submit(
        title=title,
        selftext=body,
    )
    print(f"Posted: https://reddit.com{submission.permalink}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Print post without submitting")
    parser.add_argument("--file", help="Use a specific summary file instead of the latest")
    args = parser.parse_args()

    summary_file = Path(args.file) if args.file else latest_summary_file()
    print(f"Using: {summary_file.name}")

    title, body = parse_summary(summary_file)
    post(title, body, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
