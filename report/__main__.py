"""python3 -m report <file.csv>"""

from __future__ import annotations

import sys
from pathlib import Path

from report.expenses import ReportError, read_expenses, summary, totals_by_currency


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: python3 -m report <file.csv>", file=sys.stderr)
        return 2
    try:
        expenses = read_expenses(Path(argv[0]))
    except (OSError, ReportError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(summary(expenses))
    for code, total in totals_by_currency(expenses).items():
        print(f"{code} {total:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
