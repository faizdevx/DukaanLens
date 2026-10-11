"""Profit and cash calculations. Pure functions, easy to test."""
from . import queries
from .periods import ALL_TIME


def format_money(value):
    """1234.5 -> '₹1,234.50' (negative: '-₹1,234.50')."""
    value = value or 0
    sign = "-" if value < 0 else ""
    return f"{sign}₹{abs(value):,.2f}"


def compute_metrics(revenue, cogs, expenses, withdrawals, starting_capital=0.0):
    """
    gross profit = revenue - COGS
    net profit   = revenue - COGS - operating expenses
    Owner withdrawals are NOT an expense, so they never change profit.
    Estimated cash is a rough guess: it assumes every sale was paid in cash
    and every cost was paid immediately.
    """
    gross_profit = revenue - cogs
    net_profit = gross_profit - expenses
    estimated_cash = starting_capital + net_profit - withdrawals
    return {
        "revenue": round(revenue, 2),
        "cogs": round(cogs, 2),
        "gross_profit": round(gross_profit, 2),
        "expenses": round(expenses, 2),
        "net_profit": round(net_profit, 2),
        "withdrawals": round(withdrawals, 2),
        "starting_capital": round(starting_capital, 2),
        "estimated_cash": round(estimated_cash, 2),
    }


def get_totals(user_id, period=ALL_TIME):
    """Sum the user's records for a period, using the approved 'totals' query."""
    result = queries.run_template("totals", user_id, start=period.start, end=period.end)
    revenue, cogs, expenses, withdrawals = result.rows[0]
    return revenue, cogs, expenses, withdrawals, result


def get_metrics(user_id, starting_capital=0.0, period=ALL_TIME, include_capital=True):
    revenue, cogs, expenses, withdrawals, _ = get_totals(user_id, period)
    capital = starting_capital if include_capital else 0.0
    return compute_metrics(revenue, cogs, expenses, withdrawals, capital)
