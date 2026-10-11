"""Runs SQL that an AI wrote, safely.

We do not trust the generated SQL. Three layers protect the data:
 1. check_sql(): one statement, must start with SELECT/WITH, no write keywords or comments.
 2. A SQLite *authorizer*: SQLite itself refuses anything except reading the tables we
    list, and only a short list of harmless functions.
 3. A time limit and a row limit, so a bad query cannot hang the server.
"""
import re
import sqlite3
import time

from .extensions import db

MAX_ROWS = 200
TIMEOUT_SECONDS = 3.0

ALLOWED_FUNCTIONS = {
    "count", "sum", "avg", "min", "max", "total", "round", "abs", "coalesce", "ifnull", "nullif",
    "lower", "upper", "length", "substr", "substring", "trim", "ltrim", "rtrim", "replace", "instr",
    "strftime", "date", "datetime", "time", "julianday", "typeof", "group_concat", "printf",
    "like", "glob", "iif", "cast", "sign", "random",
}

_STRING_RE = re.compile(r"'(?:[^']|'')*'")
_FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|ATTACH|DETACH|PRAGMA|REPLACE INTO|VACUUM|"
    r"REINDEX|ANALYZE|SAVEPOINT|RELEASE|BEGIN|COMMIT|ROLLBACK|LOAD_EXTENSION)\b", re.I)


class SqlRejected(Exception):
    """The SQL was refused before or while running (unsafe, or touches a forbidden table)."""


def check_sql(sql):
    """Returns the cleaned single statement, or raises SqlRejected."""
    statement = (sql or "").strip().rstrip(";").strip()
    if not statement:
        raise SqlRejected("The query was empty.")
    outside_strings = _STRING_RE.sub("''", statement)
    if ";" in outside_strings:
        raise SqlRejected("Only one statement is allowed.")
    if "--" in outside_strings or "/*" in outside_strings:
        raise SqlRejected("SQL comments are not allowed.")
    if not re.match(r"(SELECT|WITH)\b", statement, re.I):
        raise SqlRejected("Only SELECT queries are allowed.")
    if _FORBIDDEN.search(outside_strings):
        raise SqlRejected("The query contains a keyword that is not allowed.")
    return statement


def run_select(sql, allowed_tables, params=None, max_rows=MAX_ROWS):
    """Run one read-only query. Returns (columns, rows, truncated)."""
    statement = check_sql(sql)
    allowed = {t.lower() for t in allowed_tables}

    def authorizer(action, arg1, arg2, dbname, source):
        if action == sqlite3.SQLITE_SELECT:
            return sqlite3.SQLITE_OK
        if action == sqlite3.SQLITE_FUNCTION:
            return sqlite3.SQLITE_OK if (arg2 or "").lower() in ALLOWED_FUNCTIONS else sqlite3.SQLITE_DENY
        if action == sqlite3.SQLITE_READ and (arg1 or "").lower() in allowed:
            return sqlite3.SQLITE_OK
        return sqlite3.SQLITE_DENY

    deadline = time.monotonic() + TIMEOUT_SECONDS

    def too_slow():
        return 1 if time.monotonic() > deadline else 0   # non-zero aborts the query

    raw = db.session.connection().connection.dbapi_connection
    raw.set_authorizer(authorizer)
    raw.set_progress_handler(too_slow, 10000)
    cursor = raw.cursor()
    try:
        cursor.execute(statement, params or {})
        columns = [d[0] for d in cursor.description or []]
        fetched = cursor.fetchmany(max_rows + 1)
    except sqlite3.Error as exc:
        raise SqlRejected(str(exc)) from exc
    finally:
        cursor.close()
        raw.set_progress_handler(None, 0)
        raw.set_authorizer(None)
    return columns, [list(r) for r in fetched[:max_rows]], len(fetched) > max_rows
