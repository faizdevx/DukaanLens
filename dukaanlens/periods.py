"""Date ranges for the dashboard filter. Ranges are [start, end)."""
import calendar
from datetime import date, timedelta
from typing import NamedTuple

ALL_START = date(1900, 1, 1)
ALL_END = date(9999, 12, 31)


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


ALL_TIME = Period("all time", ALL_START, ALL_END)


def month_period(year, month):
    start = date(year, month, 1)
    end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return Period(f"{calendar.month_name[month]} {year}", start, end)


def period_from_key(key, today):
    """Used by the dashboard filter: all / month / year."""
    if key == "month":
        p = month_period(today.year, today.month)
        return Period("this month", p.start, p.end)
    if key == "year":
        return Period("this year", date(today.year, 1, 1), date(today.year + 1, 1, 1))
    return ALL_TIME
