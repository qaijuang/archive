#!/usr/bin/env python3
"""
Check whether today is the last day of the current month.

Used in the monthly workflow to gate the fetch step, because the cron schedule
runs on days 28-31 but not every month has 31 (or even 30) days.

Writes a GitHub Actions output variable:
    is_last_day=true | false

If GITHUB_OUTPUT is not set (local run), prints to stdout instead.
"""

import os
from datetime import date, timedelta


def is_last_day_of_month() -> bool:
    today = date.today()
    tomorrow = today + timedelta(days=1)
    # If tomorrow is a different month, today is the last day
    return tomorrow.month != today.month


def main() -> None:
    result = is_last_day_of_month()
    value = "true" if result else "false"

    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a") as fh:
            fh.write(f"is_last_day={value}\n")
    else:
        # Local run? just print
        print(f"is_last_day={value}")

    if not result:
        today = date.today()
        print(
            f"[skip] Today is {today.isoformat()}, not the last day of "
            f"{today.strftime('%B')}. Exiting early.",
            flush=True,
        )


if __name__ == "__main__":
    main()
