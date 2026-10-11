"""Turns words like "last month" into date ranges. Ranges are [start, end)."""
import calendar
import re
from datetime import date, timedelta
from typing import NamedTuple, Optional

ALL_START = date(1900, 1, 1)
ALL_END = date(9999, 12, 31)

MONTH_NAMES = {name.lower(): i for i, name in enumerate(calendar.month_name) if name}
MONTH_NAMES.update({name.lower(): i for i, name in enumerate(calendar.month_abbr) if name})


class Period(NamedTuple):
    label: str
    start: date
    end: date  # exclusive

    @property
    def start_month(self):
        return self.start.strftime("%Y-%m")

    @property
    def end_month(self):
        return (self.end - timedelta(days=1)).strftime("%Y-%m")


def month_period(year, month):
    start = date(year, month, 1)
    end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return Period(f"{calendar.month_name[month]} {year}", start, end)


def year_period(year):
    return Period(str(year), date(year, 1, 1), date(year + 1, 1, 1))


ALL_TIME = Period("all time", ALL_START, ALL_END)


def this_month(today):
    p = month_period(today.year, today.month)
    return Period("this month", p.start, p.end)


def last_month(today):
    year, month = (today.year - 1, 12) if today.month == 1 else (today.year, today.month - 1)
    p = month_period(year, month)
    return Period(f"last month ({p.label})", p.start, p.end)


def this_year(today):
    p = year_period(today.year)
    return Period("this year", p.start, p.end)


def last_year(today):
    p = year_period(today.year - 1)
    return Period(f"last year ({p.label})", p.start, p.end)


def period_from_key(key, today):
    """Used by the dashboard filter: all / month / year."""
    if key == "month":
        return this_month(today)
    if key == "year":
        return this_year(today)
    return ALL_TIME


def parse_period(text, today) -> Optional[Period]:
    """Find a period in a sentence. Returns None when none is mentioned."""
    t = text.lower()
    if re.search(r"\b(all time|overall|ever|since (the )?(start|beginning))\b", t):
        return ALL_TIME
    if re.search(r"\b(last|previous) month\b", t):
        return last_month(today)
    if re.search(r"\b(this|current) month\b", t):
        return this_month(today)
    if re.search(r"\b(last|previous) year\b", t):
        return last_year(today)
    if re.search(r"\b(this|current) year\b", t):
        return this_year(today)

    year_match = re.search(r"\b(19|20)\d{2}\b", t)
    year = int(year_match.group(0)) if year_match else None
    for word in re.findall(r"[a-z]+", t):
        # "may" is also a normal English word, so only accept it with a year or "in may".
        if word in MONTH_NAMES and (word != "may" or year or re.search(r"\bin may\b", t)):
            month = MONTH_NAMES[word]
            if year is None:
                year = today.year if month <= today.month else today.year - 1
            return month_period(year, month)
    if year:
        return year_period(year)
    return None
