import subprocess
import sys
import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

from report.expenses import Expense, ReportError, parse_row, read_expenses, summary, totals_by_currency

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
    return parse_row({**ROW, "amount": amount, "currency": currency}, 2)


class TotalsByCurrency(unittest.TestCase):
    def test_sums_each_currency_separately(self) -> None:
        expenses = [expense("10.50", "USD"), expense("5", "EUR"), expense("2.25", "USD"), expense("1", "EUR")]
        self.assertEqual(totals_by_currency(expenses), {"EUR": Decimal("6"), "USD": Decimal("12.75")})

    def test_keys_are_sorted_by_code(self) -> None:
        expenses = [expense("1", "USD"), expense("1", "EUR"), expense("1", "GBP")]
        self.assertEqual(list(totals_by_currency(expenses)), ["EUR", "GBP", "USD"])

    def test_uses_decimal_without_float_error(self) -> None:
        totals = totals_by_currency([expense("0.10", "USD"), expense("0.20", "USD")])
        self.assertEqual(totals["USD"], Decimal("0.30"))

    def test_lowercase_currency_is_grouped_with_uppercase(self) -> None:
        totals = totals_by_currency([expense("1", "usd"), expense("2", "USD")])
        self.assertEqual(totals, {"USD": Decimal("3")})

    def test_empty_gives_empty_totals(self) -> None:
        self.assertEqual(totals_by_currency([]), {})


class Cli(unittest.TestCase):
    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([sys.executable, "-m", "report", *args], capture_output=True, text=True)

    def test_prints_totals_per_currency_after_summary(self) -> None:
        out = self.run_cli("data/sample.csv")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(
            out.stdout.splitlines(),
            ["8 expenses from 2026-09-02 to 2026-10-19", "EUR 141.90", "GBP 210.00", "USD 485.00"],
        )

    def test_totals_have_two_decimals(self) -> None:
        path = write_csv("date,description,amount,currency\n2026-10-05,Lunch,9,EUR\n")
        self.assertIn("EUR 9.00", self.run_cli(str(path)).stdout.splitlines())

    def test_no_expenses_prints_no_currency_lines(self) -> None:
        path = write_csv("date,description,amount,currency\n")
        out = self.run_cli(str(path))
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(out.stdout.splitlines(), ["No expenses."])

    def test_prints_the_summary(self) -> None:
        out = self.run_cli("data/sample.csv")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("expenses from", out.stdout)

    def test_bad_file_exits_1(self) -> None:
        self.assertEqual(self.run_cli("missing.csv").returncode, 1)


if __name__ == "__main__":
    unittest.main()
