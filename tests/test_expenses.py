import subprocess
import sys
import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

from report.expenses import Expense, ReportError, currency_totals, parse_row, read_expenses, summary

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


def expense(amount: str, currency: str) -> Expense:
    return Expense(date(2026, 10, 3), "Item", Decimal(amount), currency)


class CurrencyTotals(unittest.TestCase):
    def test_sums_per_currency_with_two_decimals(self) -> None:
        expenses = [expense("4.20", "EUR"), expense("6.80", "EUR"), expense("5", "USD")]
        self.assertEqual(currency_totals(expenses), ["EUR 11.00", "USD 5.00"])

    def test_sorted_by_currency_code(self) -> None:
        expenses = [expense("1", "USD"), expense("2", "EUR"), expense("3", "GBP")]
        self.assertEqual(currency_totals(expenses), ["EUR 2.00", "GBP 3.00", "USD 1.00"])

    def test_never_mixes_currencies(self) -> None:
        expenses = [expense("10", "EUR"), expense("20", "USD")]
        self.assertEqual(currency_totals(expenses), ["EUR 10.00", "USD 20.00"])

    def test_pads_whole_amounts(self) -> None:
        self.assertEqual(currency_totals([expense("9", "EUR")]), ["EUR 9.00"])

    def test_nothing_gives_no_lines(self) -> None:
        self.assertEqual(currency_totals([]), [])

    def test_lower_case_currency_is_grouped_with_upper_case(self) -> None:
        path = write_csv(
            "date,description,amount,currency\n2026-10-03,Taxi,1.50,usd\n2026-10-04,Lunch,2.50,USD\n"
        )
        self.assertEqual(currency_totals(read_expenses(path)), ["USD 4.00"])


class Cli(unittest.TestCase):
    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([sys.executable, "-m", "report", *args], capture_output=True, text=True)

    def test_prints_the_summary(self) -> None:
        out = self.run_cli("data/sample.csv")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("expenses from", out.stdout)

    def test_prints_totals_per_currency_after_the_summary(self) -> None:
        out = self.run_cli("data/sample.csv")
        self.assertEqual(out.returncode, 0, out.stderr)
        lines = out.stdout.splitlines()
        self.assertIn("expenses from", lines[0])
        self.assertEqual(lines[1:], ["EUR 141.90", "GBP 210.00", "USD 485.00"])

    def test_empty_file_prints_only_no_expenses(self) -> None:
        out = self.run_cli(str(write_csv("date,description,amount,currency\n")))
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(out.stdout.splitlines(), ["No expenses."])

    def test_bad_file_exits_1(self) -> None:
        self.assertEqual(self.run_cli("missing.csv").returncode, 1)


if __name__ == "__main__":
    unittest.main()
