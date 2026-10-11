"""Turn an uploaded CSV into a real SQLite table.

Safety rules:
 * Table and column names are cleaned to [a-z0-9_] and always double-quoted.
 * Row values are only ever sent as bound parameters.
 * Questions about the data run through sandbox.py (read-only, this user's table only).
"""
import csv
import io
import json
import re
from datetime import datetime

from sqlalchemy import text

from .extensions import db
from .models import UploadedTable

MAX_ROWS = 20000
MAX_COLUMNS = 50
MAX_TABLES_PER_USER = 10
MAX_DISTINCT_VALUES = 50

NAME_RE = re.compile(r"^[a-z0-9_]+$")
DATE_FORMATS = ["%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d", "%d-%b-%Y", "%d %b %Y",
                "%d %B %Y", "%b %d, %Y"]


class CsvError(Exception):
    """A problem with the uploaded file that we can explain to the user."""


# ---- reading the file -----------------------------------------------------------

def parse_csv(raw):
    """bytes -> (headers, rows). Rows are lists of strings, same length as headers."""
    if not raw.strip():
        raise CsvError("The file is empty.")
    try:
        content = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        content = raw.decode("latin-1")
    if "\x00" in content:
        raise CsvError("This does not look like a text CSV file.")
    try:
        dialect = csv.Sniffer().sniff(content[:4096], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    try:
        all_rows = [r for r in csv.reader(io.StringIO(content, newline=""), dialect)
                    if any(cell.strip() for cell in r)]
    except csv.Error as exc:
        raise CsvError(f"Could not read the CSV: {exc}") from exc
    if len(all_rows) < 2:
        raise CsvError("The CSV needs a header row and at least one data row.")

    header_row, data_rows = all_rows[0], all_rows[1:]
    if len(header_row) > MAX_COLUMNS:
        raise CsvError(f"Too many columns (maximum {MAX_COLUMNS}).")
    if len(data_rows) > MAX_ROWS:
        raise CsvError(f"Too many rows (maximum {MAX_ROWS:,}).")

    width = len(header_row)
    rows = []
    for number, row in enumerate(data_rows, start=2):
        if len(row) > width:
            if any(cell.strip() for cell in row[width:]):
                raise CsvError(f"Row {number} has more values than the header has columns.")
            row = row[:width]
        rows.append(row + [""] * (width - len(row)))
    return clean_headers(header_row), rows


def clean_headers(headers):
    """'Unit Price (Rs)' -> 'unit_price_rs'; blanks and duplicates get safe names."""
    names, seen = [], set()
    for i, header in enumerate(headers):
        name = re.sub(r"[^a-z0-9]+", "_", header.strip().lower()).strip("_")[:50]
        if not name:
            name = f"column_{i + 1}"
        if name[0].isdigit():
            name = "c_" + name
        base, n = name, 2
        while name in seen:
            name = f"{base}_{n}"
            n += 1
        seen.add(name)
        names.append(name)
    return names


# ---- guessing column types ---------------------------------------------------------

def _number_text(value):
    value = value.strip()
    value = re.sub(r"^(rs\.?|inr)\s*", "", value, flags=re.I)
    return re.sub(r"[\u20b9$,]", "", value).strip()


def _as_int(value):
    s = _number_text(value)
    if re.fullmatch(r"[+-]?\d+", s) and not re.fullmatch(r"[+-]?0\d+", s) and len(s) < 18:
        return int(s)
    return None


def _as_float(value):
    s = _number_text(value)
    if re.fullmatch(r"[+-]?(\d+\.?\d*|\.\d+)", s) and not re.fullmatch(r"[+-]?0\d+", s):
        return float(s)
    return None


def _as_date(value):
    value = value.strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def infer_columns(headers, rows):
    """Returns (columns metadata, converted rows). Empty cells become NULL."""
    columns, converted_columns = [], []
    for index, name in enumerate(headers):
        cells = [row[index].strip() for row in rows]
        filled = [c for c in cells if c != ""]
        kind, convert = "TEXT", (lambda c: c)
        if filled:
            if all(_as_int(c) is not None for c in filled):
                kind, convert = "INTEGER", _as_int
            elif all(_as_float(c) is not None for c in filled):
                kind, convert = "REAL", _as_float
            elif all(_as_date(c) is not None for c in filled):
                kind, convert = "DATE", _as_date
        values = [convert(c) if c != "" else None for c in cells]
        converted_columns.append(values)

        known = None
        if kind == "TEXT":
            distinct = sorted({v for v in values if v}, key=str.lower)
            if 0 < len(distinct) <= MAX_DISTINCT_VALUES and all(len(v) <= 60 for v in distinct):
                known = distinct
        columns.append({"name": name, "type": kind, "values": known})
    converted_rows = [list(row) for row in zip(*converted_columns)]
    return columns, converted_rows


# ---- storing / dropping -------------------------------------------------------------

def table_slug(display_name):
    slug = re.sub(r"[^a-z0-9]+", "_", display_name.lower()).strip("_")[:40]
    return slug or "data"


def store_table(user, display_name, filename, headers, rows):
    columns, converted = infer_columns(headers, rows)
    table_name = f"ut_{user.id}_{table_slug(display_name)}"
    assert NAME_RE.match(table_name)

    if UploadedTable.query.filter_by(user_id=user.id, table_name=table_name).first():
        raise CsvError(f"You already have a table called '{display_name}'. "
                       "Delete it first or choose another name.")

    sql_types = {"INTEGER": "INTEGER", "REAL": "REAL", "TEXT": "TEXT", "DATE": "TEXT"}
    column_sql = ", ".join(f'"{c["name"]}" {sql_types[c["type"]]}' for c in columns)
    binds = [f"c{i}" for i in range(len(columns))]
    insert_sql = (f'INSERT INTO "{table_name}" ({", ".join(chr(34) + c["name"] + chr(34) for c in columns)}) '
                  f'VALUES ({", ".join(":" + b for b in binds)})')
    try:
        conn = db.session.connection()
        conn.execute(text(f'CREATE TABLE "{table_name}" ({column_sql})'))
        for start in range(0, len(converted), 1000):
            chunk = [dict(zip(binds, row)) for row in converted[start:start + 1000]]
            conn.execute(text(insert_sql), chunk)
        record = UploadedTable(user_id=user.id, display_name=display_name,
                               table_name=table_name, original_filename=filename[:200],
                               row_count=len(converted), columns_json=json.dumps(columns))
        db.session.add(record)
        db.session.commit()
    except Exception:
        db.session.rollback()
        db.session.execute(text(f'DROP TABLE IF EXISTS "{table_name}"'))
        db.session.commit()
        raise
    return record


def drop_table(record):
    name = record.table_name
    if not re.fullmatch(rf"ut_{record.user_id}_[a-z0-9_]+", name):
        raise ValueError("Refusing to drop an unexpected table name.")
    db.session.execute(text(f'DROP TABLE IF EXISTS "{name}"'))
    db.session.delete(record)
    db.session.commit()
