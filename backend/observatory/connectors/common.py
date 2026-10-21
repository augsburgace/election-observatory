"""Small, auditable parsing primitives shared by primary-source adapters."""
from __future__ import annotations

import csv
import io
import re
import xml.etree.ElementTree as ET
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

from observatory.domain import Observation
from observatory.registry import ELECTION_DATES


def document_text(doc: Any) -> str:
    return doc.text if doc.text is not None else Path(doc.path).read_text(encoding="utf-8-sig", errors="replace")


def soup(doc: Any) -> BeautifulSoup:
    return BeautifulSoup(document_text(doc), "html.parser")


def iso_date(value: str) -> str:
    value = value.strip()
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d", "%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            pass
    raise ValueError(f"Unrecognized source date: {value!r}")


def number(value: str) -> int:
    value = value.strip().replace(",", "")
    if not re.fullmatch(r"\d+(?:\.0+)?", value):
        raise ValueError(f"Not a reported integer: {value!r}")
    return int(float(value))


def geo_id(state: str, name: str, kind: str = "county") -> str:
    if kind == "state":
        return state
    normalized = re.sub(r"\s+", " ", name.strip()).upper()
    return f"{state}:{normalized}"


def observation(source: dict, doc: Any, *, name: str, value: float, metric: str, date_: str,
                kind: str = "county", mode: str = "all", dimension: str | None = None,
                category: str | None = None, basis: str | None = None, metadata: dict | None = None,
                published_at: str | None = None, cycle: int | None = None) -> Observation:
    cycle = cycle or source.get("cycle", 2026)
    return Observation(state=source["state"], cycle=cycle, election_date=ELECTION_DATES[cycle],
                       date=date_, metric=metric, value=value, geography_id=geo_id(source["state"], name, kind),
                       geography_name=name, geography_type=kind, mode=mode,
                       category_dimension=dimension, category=category,
                       time_basis=basis or ("reported" if cycle == 2026 else "final"),
                       published_at=published_at,
                       metadata={"source_url": doc.url, "source_sha256": doc.sha256,
                                 "retrieved_at": doc.retrieved_at, "parser_version": "1.0",
                                 **(metadata or {})})


def read_csv(doc: Any, delimiter: str = ","):
    # Stream disk files; NC aggregate exports can contain hundreds of thousands of rows.
    with Path(doc.path).open(encoding="utf-8-sig", errors="replace", newline="") as f:
        yield from csv.DictReader((line.replace("\x00", "") for line in f), delimiter=delimiter)


def xlsx_rows(data: bytes) -> list[list[str]]:
    """Read first-sheet values without executing formulas or requiring Excel."""
    ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            shared = ["".join(x.itertext()) for x in ET.fromstring(z.read("xl/sharedStrings.xml"))]
        result = []
        for row in ET.fromstring(z.read("xl/worksheets/sheet1.xml")).findall(".//s:row", ns):
            values: dict[int, str] = {}
            for cell in row:
                letters = re.match(r"[A-Z]+", cell.get("r", "A1"))[0]
                col = 0
                for c in letters:
                    col = col * 26 + ord(c) - 64
                v = cell.find("s:v", ns)
                value = v.text if v is not None else "".join(cell.itertext())
                values[col - 1] = shared[int(value)] if cell.get("t") == "s" else value or ""
            result.append([values.get(i, "") for i in range(max(values, default=0) + 1)])
        return result


def excel_date(value: str) -> str:
    try:
        return iso_date(value)
    except ValueError:
        return (date(1899, 12, 30) + timedelta(days=number(value))).isoformat()
