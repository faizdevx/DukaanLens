"""The ONLY SQL this app runs for the assistant and dashboard.

Every query is a fixed, read-only SELECT template. Users never type SQL:
the assistant only picks a template by name and fills in :parameters.
Every template must filter on :user_id, so one user can never see another's data.
"""
import re
from dataclasses import dataclass

from sqlalchemy import text

from .extensions import db

_BUDGET_BODY = """
SELECT b.category AS category,
       b.month AS month,
       b.limit_amount AS limit_amount,
       ROUND(COALESCE(SUM(r.actual_amount), 0), 2) AS spent
FROM budgets b
LEFT JOIN financial_records r
       ON r.user_id = b.user_id
      AND lower(r.category) = lower(b.category)
      AND r.transaction_type IN ('expense', 'cogs')
      AND strftime('%Y-%m', r.date) = b.month
WHERE b.user_id = :user_id
  AND b.month >= :start_month AND b.month <= :end_month
GROUP BY b.id
"""

TEMPLATES = {
    "totals": {
        "params": ["start", "end"],
        "sql": """
SELECT ROUND(COALESCE(SUM(CASE WHEN transaction_type = 'revenue' THEN actual_amount END), 0), 2) AS revenue,
       ROUND(COALESCE(SUM(CASE WHEN transaction_type = 'cogs' THEN actual_amount END), 0), 2) AS cogs,
       ROUND(COALESCE(SUM(CASE WHEN transaction_type = 'expense' THEN actual_amount END), 0), 2) AS expenses,
       ROUND(COALESCE(SUM(CASE WHEN transaction_type = 'withdrawal' THEN actual_amount END), 0), 2) AS withdrawals
FROM financial_records
WHERE user_id = :user_id AND date >= :start AND date < :end
""",
    },
    "monthly_revenue": {
        "params": ["start", "end"],
        "sql": """
SELECT strftime('%Y-%m', date) AS month,
       ROUND(SUM(actual_amount), 2) AS revenue
FROM financial_records
WHERE user_id = :user_id AND transaction_type = 'revenue'
  AND date >= :start AND date < :end
GROUP BY month
ORDER BY month
""",
    },
    "monthly_summary": {
        "params": ["start", "end"],
        "sql": """
SELECT strftime('%Y-%m', date) AS month,
       ROUND(COALESCE(SUM(CASE WHEN transaction_type = 'revenue' THEN actual_amount END), 0), 2) AS revenue,
       ROUND(COALESCE(SUM(CASE WHEN transaction_type IN ('cogs', 'expense') THEN actual_amount END), 0), 2) AS costs
FROM financial_records
WHERE user_id = :user_id AND date >= :start AND date < :end
GROUP BY month
ORDER BY month
""",
    },
    "category_spend": {
        "params": ["category", "start", "end"],
        "sql": """
SELECT category,
       ROUND(SUM(actual_amount), 2) AS total_spent,
       COUNT(*) AS entries
FROM financial_records
WHERE user_id = :user_id
  AND transaction_type IN ('expense', 'cogs')
  AND lower(category) = lower(:category)
  AND date >= :start AND date < :end
GROUP BY lower(category)
""",
    },
    "expenses_by_category": {
        "params": ["start", "end"],
        "sql": """
SELECT category,
       ROUND(SUM(actual_amount), 2) AS total_spent
FROM financial_records
WHERE user_id = :user_id
  AND transaction_type IN ('expense', 'cogs')
  AND date >= :start AND date < :end
GROUP BY lower(category)
ORDER BY total_spent DESC
""",
    },
    "budget_status": {
        "params": ["start_month", "end_month"],
        "sql": _BUDGET_BODY + "ORDER BY b.month, b.category\n",
    },
    "budget_exceeded": {
        "params": ["start_month", "end_month"],
        "sql": _BUDGET_BODY
        + "HAVING COALESCE(SUM(r.actual_amount), 0) > b.limit_amount\n"
        + "ORDER BY b.month, b.category\n",
    },
    "categories": {
        "params": [],
        "sql": """
SELECT DISTINCT category
FROM financial_records
WHERE user_id = :user_id
ORDER BY lower(category)
""",
    },
}

_FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|ATTACH|DETACH|PRAGMA|REPLACE|VACUUM)\b", re.I)


def _check_templates():
    """Runs at import time: refuse to start if a template is unsafe."""
    for name, template in TEMPLATES.items():
        sql = template["sql"].strip()
        assert sql.upper().startswith("SELECT"), f"{name}: must start with SELECT"
        assert ";" not in sql, f"{name}: no semicolons allowed"
        assert not _FORBIDDEN.search(sql), f"{name}: contains a write keyword"
        assert ":user_id" in sql, f"{name}: must filter by :user_id"


_check_templates()


@dataclass
class QueryResult:
    name: str
    sql: str
    params: dict
    columns: list
    rows: list

    def as_dicts(self):
        return [dict(zip(self.columns, row)) for row in self.rows]


def run_template(name, user_id, **params):
    """Run one approved template. Unknown names or wrong parameters are refused."""
    template = TEMPLATES.get(name)
    if template is None:
        raise ValueError(f"Query '{name}' is not an approved template.")
    if set(params) != set(template["params"]):
        raise ValueError(f"Query '{name}' needs parameters {template['params']}.")

    clean = {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in params.items()}
    result = db.session.execute(text(template["sql"]), {"user_id": user_id, **clean})
    columns = list(result.keys())
    rows = [list(row) for row in result.fetchall()]
    return QueryResult(name, template["sql"].strip(), {"user_id": user_id, **clean}, columns, rows)
