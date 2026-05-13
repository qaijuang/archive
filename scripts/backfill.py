#!/usr/bin/env python3
"""
Fetch all historical open source contributions from a given year.

Walks every month from --from-year January (or --from-month) up to and including
the last fully completed month. Skips any month that already has a JSON file.
Safe to re-run: skipped months are never overwritten.

Usage:
    python scripts/backfill.py --from-year 2020
    python scripts/backfill.py --from-year 2022 --from-month 6

Environment variables (required):
    GH_PAT        GitHub Personal Access Token (repo + read:user scopes)
    GH_USERNAME   Your GitHub username

Environment variables (optional):
    GH_EXCLUDED_ORGS   Comma-separated org names to exclude e.g. "my-company,my-startup"

Writes:
    data/contributions/YYYY-MM.json  (one per month, only if it doesn't exist yet)
"""

import argparse
import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path

# Reuse all fetch logic
sys.path.insert(0, str(Path(__file__).parent))
from fetch import fetch_month, write_json, DATA_DIR

# Constants

# Extra pause between months to let the GitHub Search API breathe.
# PR-level delays (0.75s each) are already handled inside fetch_month.
INTER_MONTH_DELAY = 4.0


# Month range


def last_complete_month() -> tuple[int, int]:
    """
    Return (year, month) of the last fully completed calendar month.

    If today is 2026-05-13, returns (2026, 4).
    If today is 2026-05-01, returns (2026, 4), therefore current month is still in progress.
    """
    today = date.today()
    last = today.replace(day=1) - timedelta(days=1)
    return last.year, last.month


def month_range(
    from_year: int,
    from_month: int,
    to_year: int,
    to_month: int,
) -> list[tuple[int, int]]:
    """
    Return a list of (year, month) tuples from start to end inclusive,
    ordered chronologically (oldest first).
    """
    months = []
    year, month = from_year, from_month
    while (year, month) <= (to_year, to_month):
        months.append((year, month))
        month += 1
        if month > 12:
            month = 1
            year += 1
    return months


# Progress tracking


class Progress:
    def __init__(self, total: int) -> None:
        self.total = total
        self.fetched = 0
        self.skipped = 0
        self.failed = 0
        self.empty = 0
        self._start = time.monotonic()

    def elapsed(self) -> str:
        s = int(time.monotonic() - self._start)
        return f"{s // 60}m {s % 60}s"

    def summary(self) -> str:
        lines = [
            f"\n{'-' * 52}",
            f"  Backfill complete in {self.elapsed()}\n",
            f"  Total months processed : {self.total}",
            f"  Fetched                : {self.fetched}",
            f"  Skipped                : {self.skipped}",
        ]
        if self.failed:
            lines.append(
                f"  Failed                 : {self.failed}  <- re-run to retry"
            )
        lines.append(f"{'-' * 52}")
        return "\n".join(lines)


# Core backfill


def backfill(
    from_year: int,
    from_month: int,
    username: str,
    token: str,
    excluded_orgs: set[str],
) -> None:
    end_year, end_month = last_complete_month()
    months = month_range(from_year, from_month, end_year, end_month)

    if not months:
        print(
            f"[backfill] No months to process. "
            f"Start ({from_year}-{from_month:02d}) is after "
            f"last complete month ({end_year}-{end_month:02d})."
        )
        return

    print(
        f"[backfill] {from_year}-{from_month:02d} -> {end_year}-{end_month:02d} "
        f"({len(months)} month(s))",
        flush=True,
    )
    if excluded_orgs:
        print(
            f"[backfill] excluding orgs: {', '.join(sorted(excluded_orgs))}", flush=True
        )
    print(flush=True)

    progress = Progress(total=len(months))

    for i, (year, month) in enumerate(months, start=1):
        slug = f"{year}-{month:02d}"
        outfile = DATA_DIR / f"{slug}.json"
        prefix = f"[{i:>{len(str(len(months)))}}/{len(months)}]"

        # Skip months that already have a JSON file
        if outfile.exists():
            print(f"{prefix} {slug}  -> already exists, skipping", flush=True)
            progress.skipped += 1
            continue

        print(f"{prefix} {slug}  fetching ...", flush=True)

        try:
            payload = fetch_month(
                year=year,
                month=month,
                username=username,
                token=token,
                excluded_orgs=excluded_orgs,
            )
            write_json(payload, year, month)

            count = payload["stats"]["total_prs"]
            if count == 0:
                progress.empty += 1
            progress.fetched += 1

        except KeyboardInterrupt:
            print(
                "\n[backfill] interrupted by user, progress so far is on disk",
                flush=True,
            )
            print(progress.summary())
            sys.exit(1)

        except Exception as exc:
            print(f"{prefix} {slug}  ERROR: {exc}", flush=True)
            progress.failed += 1
            # recover and continue with the next month

        # Breathe between months
        if i < len(months):
            print(f"           sleeping {INTER_MONTH_DELAY}s ...\n", flush=True)
            time.sleep(INTER_MONTH_DELAY)

    print(progress.summary(), flush=True)

    if progress.failed > 0:
        sys.exit(1)


# CLI


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill historical open source contributions from GitHub."
    )
    parser.add_argument(
        "--from-year",
        type=int,
        required=True,
        help="Start year e.g. 2020. Backfill begins at January of this year.",
    )
    parser.add_argument(
        "--from-month",
        type=int,
        default=1,
        choices=range(1, 13),
        metavar="MONTH",
        help="Start month 1-12 (default: 1). Use with --from-year to start mid-year.",
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

    backfill(
        from_year=args.from_year,
        from_month=args.from_month,
        username=username,
        token=token,
        excluded_orgs=excluded_orgs,
    )


if __name__ == "__main__":
    main()
