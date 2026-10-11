"""Ask DukaanLens: a very simple rule-based "NLP" parser.

How it works (no AI service, no paid API):
 1. Lowercase the question and look for keywords  -> the INTENT
 2. Look for words like "last month" or "2025"    -> the PERIOD
 3. Look for one of the user's own category names -> the CATEGORY
 4. Run the matching approved SQL template from queries.py with those values.

If something needed is missing we ask a follow-up question instead of guessing.
If nothing matches we say so. We never build SQL from the user's text.
"""
import re

from . import finance, queries
from .periods import ALL_TIME, parse_period

SUGGESTIONS = [
    "What were my total expenses last month?",
    "Which budget categories exceeded their limits?",
    "How much profit did I make this year?",
    "Show monthly revenue",
    "How much did I spend on inventory?",
]

PERIOD_CHOICES = ["this month", "last month", "this year", "last year", "all time"]

# Intents that give a wrong answer without a period, so we ask for one.
NEEDS_PERIOD = {"total_expenses", "net_profit", "gross_profit", "total_revenue", "withdrawals"}


def money(value):
    return finance.format_money(value)


def _has(text, *patterns):
    return any(re.search(r"\b" + p, text) for p in patterns)


def find_category(text, categories):
    """Return the user's category named in the text (longest match wins), or None."""
    for category in sorted(categories, key=len, reverse=True):
        if re.search(r"\b" + re.escape(category.lower()) + r"\b", text):
            return category
    return None


def detect_intent(text):
    if _has(text, "budget", "limit"):
        if _has(text, "exceed", "over", "above", "cross", "breach", "overspen"):
            return "budget_exceeded"
        return "budget_status"
    if _has(text, "monthly", "per month", "each month", "by month", "month by month", "month wise") \
            and _has(text, "revenue", "sales", "income"):
        return "monthly_revenue"
    if _has(text, "top", "biggest", "highest", "most") and _has(text, "categor", "spend", "expens"):
        return "expenses_by_category"
    if _has(text, "profit", "loss"):
        return "gross_profit" if "gross" in text else "net_profit"
    if _has(text, "withdraw", "drawing", "took out"):
        return "withdrawals"
    if _has(text, "cash"):
        return "cash"
    if _has(text, "spend", "spent", "spending", "expens", "cost"):
        return "total_expenses"
    if _has(text, "revenue", "sales", "income", "turnover", "sold"):
        return "total_revenue"
    return None


def _reply(answer, result=None, **extra):
    reply = {
        "answer": answer,
        "sql": result.sql if result else None,
        "params": result.params if result else None,
        "columns": result.columns if result else [],
        "rows": result.rows if result else [],
        "needs_clarification": False,
        "suggestions": [],
        "pending": None,
    }
    reply.update(extra)
    return reply


def _ask_period(intent):
    return _reply(
        "Which time period do you mean?",
        needs_clarification=True,
        suggestions=PERIOD_CHOICES,
        pending={"intent": intent},
    )


def _unsupported():
    return _reply(
        "Sorry, I can't answer that yet. I only understand a fixed set of questions about "
        "your revenue, expenses, profit, withdrawals, cash estimate and budgets. "
        "I never run free-form SQL. Try one of these:",
        suggestions=SUGGESTIONS,
    )


def answer_question(user_id, message, today, pending=None):
    """Main entry point. Returns a dict that the chat page shows."""
    text = (message or "").strip().lower()
    if not text:
        return _reply("Please type a question.", suggestions=SUGGESTIONS)
    if len(text) > 300:
        return _reply("That question is too long. Please keep it under 300 characters.")

    period = parse_period(text, today)
    intent = detect_intent(text)

    categories = [r[0] for r in queries.run_template("categories", user_id).rows]
    category = find_category(text, categories)

    # A category name beats the generic "expenses" intent: "spend on inventory".
    if category and intent in (None, "total_expenses"):
        intent = "category_spend"
    # "spend on <something unknown>": say that we don't know that category.
    unknown = re.search(r"\b(?:spen[dt]|spending)\s+(?:\w+\s+)?on\s+(?:the\s+)?([a-z][a-z &-]*?)"
                        r"(?:\s+(?:last|this|in|during|for)\b|\?|$)", text)
    if intent in (None, "total_expenses") and not category and unknown:
        shown = ", ".join(categories) if categories else "none yet"
        return _reply(
            f"I couldn't find a category called '{unknown.group(1).strip()}' in your records. "
            f"Your categories: {shown}.",
            needs_clarification=True,
        )

    # Follow-up answer to an earlier clarification, e.g. just "last month".
    if intent is None and pending and period:
        intent = pending["intent"]
    if intent is None:
        return _unsupported()

    if intent in NEEDS_PERIOD and period is None:
        return _ask_period(intent)
    period = period or ALL_TIME

    handler = HANDLERS[intent]
    return handler(user_id, period, category)


# ---- one small function per intent -------------------------------------------

def _totals(user_id, period):
    revenue, cogs, expenses, withdrawals, result = finance.get_totals(user_id, period)
    return finance.compute_metrics(revenue, cogs, expenses, withdrawals), result


def _empty_note(result):
    return " (No records were found for this period.)" if not any(result.rows[0]) else ""


def _total_expenses(user_id, period, category):
    metrics, result = _totals(user_id, period)
    return _reply(
        f"Your operating expenses for {period.label} were {money(metrics['expenses'])}. "
        f"COGS is separate: {money(metrics['cogs'])}." + _empty_note(result),
        result,
    )


def _total_revenue(user_id, period, category):
    metrics, result = _totals(user_id, period)
    return _reply(f"Your revenue for {period.label} was {money(metrics['revenue'])}."
                  + _empty_note(result), result)


def _net_profit(user_id, period, category):
    metrics, result = _totals(user_id, period)
    return _reply(
        f"Net profit for {period.label}: {money(metrics['net_profit'])} "
        f"(revenue {money(metrics['revenue'])} - COGS {money(metrics['cogs'])} "
        f"- expenses {money(metrics['expenses'])}). Owner withdrawals are not counted."
        + _empty_note(result),
        result,
    )


def _gross_profit(user_id, period, category):
    metrics, result = _totals(user_id, period)
    return _reply(
        f"Gross profit for {period.label}: {money(metrics['gross_profit'])} "
        f"(revenue {money(metrics['revenue'])} - COGS {money(metrics['cogs'])})."
        + _empty_note(result),
        result,
    )


def _withdrawals(user_id, period, category):
    metrics, result = _totals(user_id, period)
    return _reply(f"Owner withdrawals for {period.label}: {money(metrics['withdrawals'])}."
                  + _empty_note(result), result)


def _cash(user_id, period, category):
    shop = _shop_capital(user_id)
    revenue, cogs, expenses, withdrawals, result = finance.get_totals(user_id, ALL_TIME)
    metrics = finance.compute_metrics(revenue, cogs, expenses, withdrawals, shop)
    return _reply(
        f"Estimated cash: {money(metrics['estimated_cash'])}. This is only an estimate: "
        "starting capital + net profit - owner withdrawals, assuming every sale and cost "
        "was paid in cash.",
        result,
    )


def _shop_capital(user_id):
    from .models import Shop
    shop = Shop.query.filter_by(user_id=user_id).first()
    return shop.starting_capital if shop else 0.0


def _category_spend(user_id, period, category):
    result = queries.run_template("category_spend", user_id, category=category,
                                  start=period.start, end=period.end)
    total = result.rows[0][1] if result.rows else 0
    return _reply(f"You spent {money(total)} on {category} ({period.label}).", result)


def _expenses_by_category(user_id, period, category):
    result = queries.run_template("expenses_by_category", user_id,
                                  start=period.start, end=period.end)
    if not result.rows:
        return _reply(f"No expense records found for {period.label}.", result)
    top = result.rows[0]
    return _reply(f"Your biggest spending category for {period.label} is {top[0]} "
                  f"at {money(top[1])}.", result)


def _monthly_revenue(user_id, period, category):
    result = queries.run_template("monthly_revenue", user_id, start=period.start, end=period.end)
    if not result.rows:
        return _reply(f"No revenue records found for {period.label}.", result)
    return _reply(f"Monthly revenue for {period.label}:", result)


def _budget(user_id, period, category, only_exceeded):
    name = "budget_exceeded" if only_exceeded else "budget_status"
    result = queries.run_template(name, user_id, start_month=period.start_month,
                                  end_month=period.end_month)
    if not result.rows:
        if only_exceeded:
            return _reply(f"No budget category exceeded its limit ({period.label}). "
                          "Nice! (If you have not set budgets yet, add some under Budget Sheets.)",
                          result)
        return _reply(f"You have no budget limits for {period.label}. "
                      "Add some under Budget Sheets.", result)
    if only_exceeded:
        return _reply(f"{len(result.rows)} budget(s) went over the limit ({period.label}):", result)
    return _reply(f"Budget status for {period.label}:", result)


def _budget_exceeded(user_id, period, category):
    return _budget(user_id, period, category, True)


def _budget_status(user_id, period, category):
    return _budget(user_id, period, category, False)


HANDLERS = {
    "total_expenses": _total_expenses,
    "total_revenue": _total_revenue,
    "net_profit": _net_profit,
    "gross_profit": _gross_profit,
    "withdrawals": _withdrawals,
    "cash": _cash,
    "category_spend": _category_spend,
    "expenses_by_category": _expenses_by_category,
    "monthly_revenue": _monthly_revenue,
    "budget_exceeded": _budget_exceeded,
    "budget_status": _budget_status,
}
