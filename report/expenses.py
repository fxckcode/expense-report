"""Read expenses (date,description,amount,currency) from a CSV, JSON, XLSX or XML file and summarise them."""

from __future__ import annotations

import csv
import json
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path


@dataclass(frozen=True)
class Expense:
    day: date
    description: str
    amount: Decimal
    currency: str


class ReportError(ValueError):
    """A row the report cannot use; the message names its line in the file."""


def parse_row(row: dict[str, str], line: int) -> Expense:
    try:
        day = date.fromisoformat(row["date"].strip())
        amount = Decimal(row["amount"].strip())
    except (KeyError, AttributeError, ValueError, InvalidOperation) as exc:
        raise ReportError(f"line {line}: cannot read date or amount ({exc})") from exc
    currency = (row.get("currency") or "").strip().upper()
    if len(currency) != 3 or not currency.isalpha():
        raise ReportError(f"line {line}: currency must be a 3-letter code, got {currency!r}")
    return Expense(day, (row.get("description") or "").strip(), amount, currency)


def _csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _json_rows(path: Path) -> list[dict[str, str]]:
    data = json.loads(path.read_text(encoding="utf-8"), parse_float=str)
    if not isinstance(data, list):
        raise ReportError("JSON top level must be an array of objects")
    for n, record in enumerate(data, start=2):
        if not isinstance(record, dict):
            raise ReportError(f"line {n}: record must be an object")
    return [{k: "" if v is None else str(v) for k, v in rec.items()} for rec in data]


def _xml_rows(path: Path) -> list[dict[str, str]]:
    root = ET.parse(path).getroot()
    return [{field.tag: field.text or "" for field in record} for record in root]


def _xlsx_rows(path: Path) -> list[dict[str, str]]:
    with zipfile.ZipFile(path) as z:
        sheet = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
        names = z.namelist()
        shared = ET.fromstring(z.read(_SHARED)) if _SHARED in names else None
    strings = ["".join(si.itertext()) for si in shared] if shared is not None else []
    rows = [[_cell_text(c, strings) for c in row] for row in sheet.iter(f"{_NS}row")]
    return [dict(zip(rows[0], values)) for values in rows[1:]]


def _cell_text(cell: ET.Element, strings: list[str]) -> str:
    kind, value = cell.get("t"), cell.findtext(f"{_NS}v") or ""
    if kind == "s":
        return strings[int(value)]
    if kind == "inlineStr":
        return "".join(cell.find(f"{_NS}is").itertext())
    return value


_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_SHARED = "xl/sharedStrings.xml"
_READERS = {".csv": _csv_rows, ".json": _json_rows, ".xml": _xml_rows, ".xlsx": _xlsx_rows}


def read_expenses(path: Path) -> list[Expense]:
    reader = _READERS.get(path.suffix.lower())
    if reader is None:
        raise ReportError(f"unsupported file format {path.suffix!r}; use csv, json, xlsx or xml")
    try:
        rows = reader(path)
    except ReportError:
        raise
    except (ValueError, KeyError, IndexError, AttributeError, ET.ParseError, zipfile.BadZipFile) as exc:
        raise ReportError(f"cannot read {path.name} as {path.suffix.lower()[1:]} ({exc})") from exc
    return [parse_row(row, n) for n, row in enumerate(rows, start=2)]


def summary(expenses: list[Expense]) -> str:
    if not expenses:
        return "No expenses."
    days = sorted(e.day for e in expenses)
    return f"{len(expenses)} expenses from {days[0].isoformat()} to {days[-1].isoformat()}"
