import subprocess
import sys
import tempfile
import unittest
import zipfile
from datetime import date
from decimal import Decimal
from pathlib import Path

from report.expenses import Expense, ReportError, parse_row, read_expenses, summary

ROW = {"date": "2026-10-03", "description": "Taxi", "amount": "12.50", "currency": "usd"}


def write_csv(text: str) -> Path:
    f = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8")
    f.write(text)
    f.close()
    return Path(f.name)


NS = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
EXPECTED = [Expense(date(2026, 10, 3), "Taxi", Decimal("12.50"), "USD")]


def write_file(name: str, data: str | bytes) -> Path:
    path = Path(tempfile.mkdtemp()) / name
    path.write_bytes(data.encode("utf-8") if isinstance(data, str) else data)
    return path


def inline(text: str) -> str:
    return f'<c t="inlineStr"><is><t>{text}</t></is></c>'


def write_xlsx(amount: str = "12.50") -> Path:
    head = "".join(inline(h) for h in ("date", "description", "amount", "currency"))
    row = inline("2026-10-03") + '<c t="s"><v>0</v></c>' + f"<c><v>{amount}</v></c>" + inline("USD")
    sheet = f'<worksheet {NS}><sheetData><row>{head}</row><row>{row}</row></sheetData></worksheet>'
    shared = f'<sst {NS}><si><t>Taxi</t></si></sst>'
    path = Path(tempfile.mkdtemp()) / "data.xlsx"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("xl/worksheets/sheet1.xml", sheet)
        z.writestr("xl/sharedStrings.xml", shared)
    return path


JSON_OK = '[{"date": "2026-10-03", "description": "Taxi", "amount": 12.50, "currency": "usd"}]'
XML_OK = ("<expenses><expense><date>2026-10-03</date><description>Taxi</description>"
          "<amount>12.50</amount><currency>usd</currency></expense></expenses>")


class Formats(unittest.TestCase):
    def test_json_matches_csv(self) -> None:
        self.assertEqual(read_expenses(write_file("a.json", JSON_OK)), EXPECTED)

    def test_xml_matches_csv(self) -> None:
        self.assertEqual(read_expenses(write_file("a.xml", XML_OK)), EXPECTED)

    def test_xlsx_matches_csv(self) -> None:
        self.assertEqual(read_expenses(write_xlsx()), EXPECTED)

    def test_extension_is_case_insensitive(self) -> None:
        self.assertEqual(read_expenses(write_file("A.JSON", JSON_OK)), EXPECTED)
        csv_text = "date,description,amount,currency\n2026-10-03,Taxi,12.50,usd\n"
        self.assertEqual(read_expenses(write_file("DATA.CSV", csv_text)), EXPECTED)

    def test_unsupported_extension_names_it(self) -> None:
        for name in ("a.txt", "a.xls"):
            with self.assertRaisesRegex(ReportError, Path(name).suffix.replace(".", r"\.")):
                read_expenses(write_file(name, "x"))

    def test_bad_record_names_line_2(self) -> None:
        bad = {
            "a.json": JSON_OK.replace("2026-10-03", "nope"),
            "a.xml": XML_OK.replace("12.50", "x"),
            "a.xlsx": write_xlsx("x"),
        }
        for name, content in bad.items():
            path = content if isinstance(content, Path) else write_file(name, content)
            with self.subTest(name), self.assertRaisesRegex(ReportError, "line 2"):
                read_expenses(path)

    def test_malformed_input_is_a_report_error(self) -> None:
        for name, content in (("a.json", "{"), ("a.json", "{}"), ("a.json", "[1]"),
                              ("a.xml", "<a>"), ("a.xlsx", "not a zip")):
            with self.subTest(name, content=content), self.assertRaises(ReportError):
                read_expenses(write_file(name, content))


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


class Cli(unittest.TestCase):
    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([sys.executable, "-m", "report", *args], capture_output=True, text=True)

    def test_prints_the_summary(self) -> None:
        out = self.run_cli("data/sample.csv")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("expenses from", out.stdout)

    def test_bad_file_exits_1(self) -> None:
        self.assertEqual(self.run_cli("missing.csv").returncode, 1)

    def test_reads_json(self) -> None:
        out = self.run_cli(str(write_file("a.json", JSON_OK)))
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("1 expenses from", out.stdout)

    def test_unsupported_extension_exits_1(self) -> None:
        out = self.run_cli(str(write_file("a.txt", "x")))
        self.assertEqual(out.returncode, 1)
        self.assertIn("error:", out.stderr)


if __name__ == "__main__":
    unittest.main()
