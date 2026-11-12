"""python3 -m report <file.csv>"""

from __future__ import annotations

import sys
from pathlib import Path

from report.expenses import ReportError, monthly_report, read_expenses, summary

USAGE = "usage: python3 -m report [--by-month] <file.csv>"


def main(argv: list[str]) -> int:
    by_month = "--by-month" in argv
    paths = [a for a in argv if a != "--by-month"]
    if len(paths) != 1 or argv.count("--by-month") > 1:
        print(USAGE, file=sys.stderr)
        return 2
    try:
        expenses = read_expenses(Path(paths[0]))
    except (OSError, ReportError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(monthly_report(expenses) if by_month else summary(expenses))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
