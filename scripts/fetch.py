#!/usr/bin/env python3
"""
Fetch merged open source contributions for a given month.

Usage:
    python scripts/fetch.py --year 2025 --month 3

Environment variables (required):
    GH_PAT        GitHub Personal Access Token (repo + read:user scopes)
    GH_USERNAME   Your GitHub username

Environment variables (optional):
    GH_EXCLUDED_ORGS   Comma-separated org names to exclude e.g. "my-company,my-startup"

Writes:
    data/contributions/YYYY-MM.json
"""

import argparse
import json
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from github import Github, GithubException, RateLimitExceededException
from github.Auth import Token

# Constants

# Seconds to wait between PR detail fetches within the rate limit window
FETCH_DELAY = 0.75

# Seconds to sleep when rate limited before retrying
RATE_LIMIT_SLEEP = 60

# Path to the data directory relative to the repo root
REPO_ROOT = Path(__file__).parent.parent
DATA_DIR = REPO_ROOT / "data" / "contributions"


# Helpers


def last_day_of_month(year: int, month: int) -> int:
    """Return the last calendar day of the given month."""
    if month == 12:
        return 31
    return (date(year, month + 1, 1) - timedelta(days=1)).day


def iso(dt: datetime) -> str:
    """Normalise a datetime to a UTC ISO-8601 string ending in Z."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def with_rate_limit_retry(fn, *args, retries: int = 3, **kwargs):
    """Call fn(*args, **kwargs), sleeping and retrying if rate-limited."""
    for attempt in range(retries):
        try:
            return fn(*args, **kwargs)
        except RateLimitExceededException:
            if attempt == retries - 1:
                raise
            print(f"  [rate limit] sleeping {RATE_LIMIT_SLEEP}s …", flush=True)
            time.sleep(RATE_LIMIT_SLEEP)


# Core fetch


def fetch_month(
    year: int, month: int, username: str, token: str, excluded_orgs: set[str]
) -> dict:
    """
    Query GitHub for all merged PRs authored by `username` in the given month,
    excluding repos/orgs the user owns, and return a fully shaped data dict.
    """
    auth = Token(token)
    g = Github(auth=auth, per_page=100)

    # Validate the token works and the user exists
    try:
        _ = g.get_user(username).login
    except GithubException as exc:
        sys.exit(f"[error] Could not authenticate as '{username}': {exc}")

    month_str = f"{year}-{month:02d}"
    last_day = last_day_of_month(year, month)
    date_range = f"{year}-{month:02d}-01..{year}-{month:02d}-{last_day:02d}"
    query = f"is:pr is:merged author:{username} merged:{date_range}"

    print(f"[fetch] {month_str}  query: {query}", flush=True)

    # GitHub Search API returns Issue objects for PRs
    results = with_rate_limit_retry(
        g.search_issues, query, sort="updated", order="desc"
    )

    contributions = []
    repos_touched: set[str] = set()
    languages: set[str] = set()
    total_lines = 0
    skipped = 0

    try:
        total_found = results.totalCount
    except Exception:
        total_found = "?"
    print(f"[fetch] {total_found} PR(s) found, filtering ...", flush=True)

    for issue in results:
        time.sleep(FETCH_DELAY)

        try:
            pr = with_rate_limit_retry(issue.as_pull_request)
            repo = pr.base.repo
        except GithubException as exc:
            print(f"  [skip] could not load PR #{issue.number}: {exc}", flush=True)
            skipped += 1
            continue

        owner_login = repo.owner.login

        # Exclude the user's own repos
        if owner_login.lower() == username.lower():
            skipped += 1
            continue

        # Exclude specified orgs
        if owner_login.lower() in {o.lower() for o in excluded_orgs}:
            skipped += 1
            continue

        repo_lang = repo.language or "Unknown"
        lines_added = pr.additions
        lines_removed = pr.deletions
        lines_changed = lines_added + lines_removed

        entry = {
            "id": pr.node_id,
            "title": pr.title,
            "repo": repo.full_name,
            "repo_language": repo_lang,
            "pr_number": pr.number,
            "pr_url": pr.html_url,
            "merged_at": iso(pr.merged_at),
            "lines_added": lines_added,
            "lines_removed": lines_removed,
            "lines_changed": lines_changed,
            "labels": [label.name for label in pr.labels],
        }

        contributions.append(entry)
        repos_touched.add(repo.full_name)
        if repo_lang != "Unknown":
            languages.add(repo_lang)
        total_lines += lines_changed

        print(f"  ✓ {repo.full_name} #{pr.number}: {pr.title[:60]}", flush=True)

    # Sort by merge date ascending (oldest first)
    contributions.sort(key=lambda c: c["merged_at"])

    # Dedup languages in order by frequency of appearance in contributions
    lang_order = []
    seen = set()
    for c in contributions:
        lg = c["repo_language"]
        if lg != "Unknown" and lg not in seen:
            lang_order.append(lg)
            seen.add(lg)

    stats = {
        "total_prs": len(contributions),
        "repos_touched": sorted(repos_touched),
        "languages": lang_order,
        "total_lines_changed": total_lines,
    }

    payload = {
        "month": month_str,
        "generated_at": iso(datetime.now(timezone.utc)),
        "contributions": contributions,
        "stats": stats,
    }

    print(
        f"[fetch] total {len(contributions)} contribution(s), {skipped} skipped",
        flush=True,
    )
    return payload


# Write output


def write_json(payload: dict, year: int, month: int) -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out = DATA_DIR / f"{year}-{month:02d}.json"
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    print(f"[write] {out.relative_to(REPO_ROOT)}", flush=True)
    return out


# CLI


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch monthly open source contributions from GitHub."
    )
    parser.add_argument(
        "--year", type=int, required=True, help="Four-digit year e.g. 2025"
    )
    parser.add_argument(
        "--month",
        type=int,
        required=True,
        choices=range(1, 13),
        metavar="MONTH",
        help="Month number 1-12",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    token = os.environ.get("GH_PAT")
    username = os.environ.get("GH_USERNAME")

    if not token:
        sys.exit("[error] GH_PAT environment variable is not set.")
    if not username:
        sys.exit("[error] GH_USERNAME environment variable is not set.")

    raw_excluded = os.environ.get("GH_EXCLUDED_ORGS", "")
    excluded_orgs = {o.strip() for o in raw_excluded.split(",") if o.strip()}

    if excluded_orgs:
        print(
            f"[config] excluding orgs: {', '.join(sorted(excluded_orgs))}", flush=True
        )

    payload = fetch_month(
        year=args.year,
        month=args.month,
        username=username,
        token=token,
        excluded_orgs=excluded_orgs,
    )

    write_json(payload, args.year, args.month)


if __name__ == "__main__":
    main()
