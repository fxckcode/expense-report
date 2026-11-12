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
    monthly_report,
    monthly_totals,
    parse_row,
    read_expenses,
    summary,
)

ROW = {"date": "2026-10-03", "description": "Taxi", "amount": "12.50", "currency": "usd"}


def expense(day: str, amount: str, currency: str) -> Expense:
    return Expense(date.fromisoformat(day), "x", Decimal(amount), currency)


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


class MonthlyTotals(unittest.TestCase):
    def test_sums_same_month_and_currency_as_decimal(self) -> None:
        totals = monthly_totals([expense("2026-09-02", "4.20", "EUR"), expense("2026-09-02", "6.80", "EUR")])
        self.assertEqual(totals, {"2026-09": {"EUR": Decimal("11.00")}})
        self.assertEqual(str(totals["2026-09"]["EUR"]), "11.00")

    def test_one_total_per_currency_without_mixing(self) -> None:
        totals = monthly_totals([expense("2026-10-01", "5", "EUR"), expense("2026-10-02", "7", "USD")])
        self.assertEqual(totals, {"2026-10": {"EUR": Decimal("5"), "USD": Decimal("7")}})

    def test_different_months_are_zero_padded_keys(self) -> None:
        totals = monthly_totals([expense("2026-09-30", "1", "USD"), expense("2026-10-01", "2", "USD")])
        self.assertEqual(sorted(totals), ["2026-09", "2026-10"])

    def test_same_month_in_different_years_is_not_merged(self) -> None:
        totals = monthly_totals([expense("2025-10-05", "1", "USD"), expense("2026-10-05", "2", "USD")])
        self.assertEqual(totals, {"2025-10": {"USD": Decimal("1")}, "2026-10": {"USD": Decimal("2")}})

    def test_empty_list_gives_empty_dict(self) -> None:
        self.assertEqual(monthly_totals([]), {})


class MonthlyReport(unittest.TestCase):
    def test_months_are_chronological_for_unsorted_input(self) -> None:
        text = monthly_report([expense("2026-10-01", "1", "USD"), expense("2026-09-01", "1", "USD")])
        self.assertLess(text.index("2026-09"), text.index("2026-10"))

    def test_currencies_are_sorted_alphabetically(self) -> None:
        text = monthly_report([expense("2026-10-01", "1", "USD"), expense("2026-10-02", "1", "EUR")])
        self.assertLess(text.index("EUR"), text.index("USD"))

    def test_exact_rendered_text(self) -> None:
        text = monthly_report(
            [
                expense("2026-10-19", "210.00", "GBP"),
                expense("2026-09-02", "4.20", "EUR"),
                expense("2026-09-02", "6.80", "EUR"),
                expense("2026-09-15", "120.00", "USD"),
            ]
        )
        self.assertEqual(
            text,
            "2026-09\n  EUR 11.00\n  USD 120.00\n\n2026-10\n  GBP 210.00",
        )

    def test_empty_list(self) -> None:
        self.assertEqual(monthly_report([]), "No expenses.")


class Cli(unittest.TestCase):
    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([sys.executable, "-m", "report", *args], capture_output=True, text=True)

    def test_by_month_prints_totals_for_the_sample(self) -> None:
        out = self.run_cli("--by-month", "data/sample.csv")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(
            out.stdout,
            "2026-09\n  EUR 11.00\n  USD 470.00\n\n2026-10\n  EUR 130.90\n  GBP 210.00\n  USD 15.00\n",
        )

    def test_by_month_flag_works_before_and_after_the_path(self) -> None:
        before = self.run_cli("--by-month", "data/sample.csv")
        after = self.run_cli("data/sample.csv", "--by-month")
        self.assertEqual(after.returncode, 0, after.stderr)
        self.assertEqual(before.stdout, after.stdout)

    def test_without_the_flag_the_summary_is_unchanged(self) -> None:
        out = self.run_cli("data/sample.csv")
        self.assertIn("expenses from", out.stdout)
        self.assertNotIn("2026-09\n", out.stdout)

    def test_by_month_without_a_path_exits_2(self) -> None:
        self.assertEqual(self.run_cli("--by-month").returncode, 2)

    def test_by_month_with_a_bad_file_exits_1(self) -> None:
        self.assertEqual(self.run_cli("--by-month", "missing.csv").returncode, 1)

    def test_prints_the_summary(self) -> None:
        out = self.run_cli("data/sample.csv")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("expenses from", out.stdout)

    def test_bad_file_exits_1(self) -> None:
        self.assertEqual(self.run_cli("missing.csv").returncode, 1)


if __name__ == "__main__":
    unittest.main()
