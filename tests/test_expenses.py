import subprocess
import sys
import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

from report.expenses import (
    Expense,
    ReportError,
    by_month_report,
    parse_row,
    read_expenses,
    summary,
    totals_by_month,
)

ROW = {"date": "2026-10-03", "description": "Taxi", "amount": "12.50", "currency": "usd"}


def write_csv(text: str) -> Path:
    f = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8")
    f.write(text)
    f.close()
    return Path(f.name)


class ParseRow(unittest.TestCase):
    def test_reads_a_row(self) -> None:
        self.assertEqual(parse_row(ROW, 2), Expense(date(2026, 10, 3), "Taxi", Decimal("12.50"), "USD"))

    def test_bad_date_names_the_line(self) -> None:
        with self.assertRaisesRegex(ReportError, "line 7"):
            parse_row({**ROW, "date": "03/10/2026"}, 7)

    def test_bad_amount(self) -> None:
        with self.assertRaises(ReportError):
            parse_row({**ROW, "amount": "twelve"}, 2)

    def test_bad_currency(self) -> None:
        with self.assertRaisesRegex(ReportError, "3-letter"):
            parse_row({**ROW, "currency": "dollars"}, 2)


class ReadAndSummarise(unittest.TestCase):
    def test_reads_a_file(self) -> None:
        path = write_csv("date,description,amount,currency\n2026-10-03,Taxi,12.50,USD\n2026-10-05,Lunch,9,EUR\n")
        self.assertEqual([e.currency for e in read_expenses(path)], ["USD", "EUR"])

    def test_error_line_counts_the_header(self) -> None:
        path = write_csv("date,description,amount,currency\n2026-10-03,Taxi,x,USD\n")
        with self.assertRaisesRegex(ReportError, "line 2"):
            read_expenses(path)

    def test_summary(self) -> None:
        expenses = [parse_row(ROW, 2), parse_row({**ROW, "date": "2026-09-30"}, 3)]
        self.assertEqual(summary(expenses), "2 expenses from 2026-09-30 to 2026-10-03")

    def test_summary_of_nothing(self) -> None:
        self.assertEqual(summary([]), "No expenses.")


def exp(day: str, amount: str, currency: str) -> Expense:
    return Expense(date.fromisoformat(day), "x", Decimal(amount), currency)


class ByMonth(unittest.TestCase):
    def test_groups_by_month(self) -> None:
        totals = totals_by_month([exp("2026-09-02", "1", "EUR"), exp("2026-10-03", "2", "EUR")])
        self.assertEqual(list(totals), ["2026-09", "2026-10"])

    def test_sums_per_currency_within_a_month(self) -> None:
        totals = totals_by_month(
            [exp("2026-09-02", "1.50", "EUR"), exp("2026-09-03", "2.50", "EUR"), exp("2026-09-04", "7", "USD")]
        )
        self.assertEqual(totals["2026-09"], {"EUR": Decimal("4.00"), "USD": Decimal("7")})

    def test_same_currency_in_different_months_stays_separate(self) -> None:
        totals = totals_by_month([exp("2026-09-02", "5", "EUR"), exp("2026-10-02", "6", "EUR")])
        self.assertEqual(totals["2026-09"]["EUR"], Decimal("5"))
        self.assertEqual(totals["2026-10"]["EUR"], Decimal("6"))

    def test_decimal_exactness(self) -> None:
        totals = totals_by_month([exp("2026-09-02", "4.20", "EUR"), exp("2026-09-02", "6.80", "EUR")])
        total = totals["2026-09"]["EUR"]
        self.assertIsInstance(total, Decimal)
        self.assertEqual(total, Decimal("11.00"))
        self.assertEqual(str(total), "11.00")

    def test_months_are_chronological_whatever_the_input_order(self) -> None:
        totals = totals_by_month(
            [exp("2026-01-05", "1", "EUR"), exp("2025-12-31", "1", "EUR"), exp("2026-03-01", "1", "EUR")]
        )
        self.assertEqual(list(totals), ["2025-12", "2026-01", "2026-03"])

    def test_currencies_are_sorted_within_a_block(self) -> None:
        totals = totals_by_month([exp("2026-09-02", "1", "USD"), exp("2026-09-02", "1", "EUR")])
        self.assertEqual(list(totals["2026-09"]), ["EUR", "USD"])

    def test_report_text(self) -> None:
        expenses = [
            exp("2026-10-01", "15.00", "USD"),
            exp("2026-09-02", "4.20", "EUR"),
            exp("2026-09-03", "6.80", "EUR"),
            exp("2026-10-02", "210.00", "GBP"),
        ]
        expected = "2026-09\n  EUR 11.00\n\n2026-10\n  GBP 210.00\n  USD 15.00"
        self.assertEqual(by_month_report(expenses), expected)

    def test_report_of_nothing(self) -> None:
        self.assertEqual(by_month_report([]), "No expenses.")


class Cli(unittest.TestCase):
    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([sys.executable, "-m", "report", *args], capture_output=True, text=True)

    def test_by_month_prints_the_blocks(self) -> None:
        out = self.run_cli("--by-month", "data/sample.csv")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("2026-09", out.stdout)
        self.assertIn("2026-10", out.stdout)
        self.assertLess(out.stdout.index("2026-09"), out.stdout.index("2026-10"))

    def test_by_month_totals_for_the_sample(self) -> None:
        out = self.run_cli("--by-month", "data/sample.csv")
        expected = "2026-09\n  EUR 11.00\n  USD 470.00\n\n2026-10\n  EUR 130.90\n  GBP 210.00\n  USD 15.00\n"
        self.assertEqual(out.stdout, expected)

    def test_flag_position_does_not_matter(self) -> None:
        before = self.run_cli("--by-month", "data/sample.csv")
        after = self.run_cli("data/sample.csv", "--by-month")
        self.assertEqual(after.returncode, 0, after.stderr)
        self.assertEqual(before.stdout, after.stdout)

    def test_default_mode_is_unchanged(self) -> None:
        out = self.run_cli("data/sample.csv")
        self.assertIn("expenses from", out.stdout)
        self.assertNotIn("2026-09\n", out.stdout)

    def test_by_month_bad_file_exits_1(self) -> None:
        self.assertEqual(self.run_cli("--by-month", "missing.csv").returncode, 1)

    def test_flag_alone_exits_2(self) -> None:
        self.assertEqual(self.run_cli("--by-month").returncode, 2)

    def test_prints_the_summary(self) -> None:
        out = self.run_cli("data/sample.csv")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("expenses from", out.stdout)

    def test_bad_file_exits_1(self) -> None:
        self.assertEqual(self.run_cli("missing.csv").returncode, 1)


if __name__ == "__main__":
    unittest.main()
