"""Small helpers that clean and check form input. Each returns (value, error)."""
import math
import re
from datetime import date, datetime

MAX_AMOUNT = 1_000_000_000_000  # 1 trillion; stops silly numbers
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def clean_text(value, label, max_len, required=True):
    value = (value or "").strip()
    if required and not value:
        return value, f"{label} is required."
    if len(value) > max_len:
        return value, f"{label} must be at most {max_len} characters."
    return value, None


def parse_amount(value, label, required=True):
    value = (value or "").strip().replace(",", "")
    if not value:
        return (None, f"{label} is required.") if required else (0.0, None)
    try:
        number = float(value)
    except ValueError:
        return None, f"{label} must be a number."
    if math.isnan(number) or math.isinf(number):
        return None, f"{label} must be a number."
    if number < 0:
        return None, f"{label} cannot be negative."
    if number > MAX_AMOUNT:
        return None, f"{label} is too large."
    return round(number, 2), None


def parse_date(value, label, allow_future=True):
    value = (value or "").strip()
    if not value:
        return None, f"{label} is required."
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None, f"{label} must be a valid date (YYYY-MM-DD)."
    if parsed.year < 1900:
        return None, f"{label} is too far in the past."
    if not allow_future and parsed > date.today():
        return None, f"{label} cannot be in the future."
    return parsed, None


def parse_month(value, label):
    value = (value or "").strip()
    if not MONTH_RE.match(value):
        return None, f"{label} must look like 2026-03."
    return value, None


def collect_errors(*results):
    """Takes several (value, error) pairs, returns (values, errors)."""
    values = [r[0] for r in results]
    errors = [r[1] for r in results if r[1]]
    return values, errors
