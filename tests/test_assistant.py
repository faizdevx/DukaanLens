from datetime import date

import pytest

from conftest import add_record, make_user
from dukaanlens import queries
from dukaanlens.assistant import answer_question, detect_intent
from dukaanlens.extensions import db
from dukaanlens.models import Budget
from dukaanlens.periods import parse_period

TODAY = date(2026, 6, 15)


@pytest.fixture()
def uid(app):
    user_id = make_user(app)
    add_record(app, user_id, "revenue", "Sales", 5000, date(2026, 5, 10))
    add_record(app, user_id, "revenue", "Sales", 3000, date(2026, 6, 2))
    add_record(app, user_id, "cogs", "Inventory", 2000, date(2026, 5, 12))
    add_record(app, user_id, "expense", "Rent", 800, date(2026, 5, 1))
    add_record(app, user_id, "expense", "Electricity", 300, date(2026, 5, 20))
    add_record(app, user_id, "withdrawal", "Owner", 500, date(2026, 5, 25))
    with app.app_context():
        db.session.add(Budget(user_id=user_id, category="Electricity", month="2026-05",
                              limit_amount=200))
        db.session.add(Budget(user_id=user_id, category="Rent", month="2026-05",
                              limit_amount=1000))
        db.session.commit()
    return user_id


def ask(app, uid, text, pending=None):
    with app.app_context():
        return answer_question(uid, text, TODAY, pending)


def test_period_parser():
    assert parse_period("expenses last month", TODAY).start == date(2026, 5, 1)
    assert parse_period("profit this year", TODAY).start == date(2026, 1, 1)
    assert parse_period("in march 2025", TODAY).start == date(2025, 3, 1)
    assert parse_period("what is my profit", TODAY) is None


def test_intents():
    assert detect_intent("which budget categories exceeded their limits?") == "budget_exceeded"
    assert detect_intent("show monthly revenue") == "monthly_revenue"
    assert detect_intent("how much profit did i make") == "net_profit"
    assert detect_intent("tell me a joke") is None


def test_total_expenses_last_month(app, uid):
    r = ask(app, uid, "What were my total expenses last month?")
    assert "₹1,100.00" in r["answer"]
    assert r["sql"].startswith("SELECT") and r["params"]["user_id"] == uid


def test_profit_this_year(app, uid):
    r = ask(app, uid, "How much profit did I make this year?")
    # revenue 8000 - cogs 2000 - expenses 1100
    assert "₹4,900.00" in r["answer"]


def test_missing_period_asks_clarification_then_follow_up_works(app, uid):
    first = ask(app, uid, "What were my total expenses?")
    assert first["needs_clarification"] and first["pending"] == {"intent": "total_expenses"}
    second = ask(app, uid, "last month", pending=first["pending"])
    assert "₹1,100.00" in second["answer"]


def test_budget_exceeded(app, uid):
    r = ask(app, uid, "Which budget categories exceeded their limits?")
    assert [row[0] for row in r["rows"]] == ["Electricity"]


def test_monthly_revenue(app, uid):
    r = ask(app, uid, "Show monthly revenue")
    assert r["rows"] == [["2026-05", 5000.0], ["2026-06", 3000.0]]


def test_category_spend(app, uid):
    r = ask(app, uid, "How much did I spend on inventory?")
    assert "₹2,000.00" in r["answer"]


def test_unknown_category_and_unsupported(app, uid):
    r = ask(app, uid, "how much did I spend on pizza?")
    assert "couldn't find a category" in r["answer"]
    r = ask(app, uid, "Write me a poem")
    assert "can't answer" in r["answer"] and r["suggestions"]


def test_sql_injection_text_is_just_text(app, uid):
    r = ask(app, uid, "'; DROP TABLE financial_records; -- total expenses last month")
    assert "₹1,100.00" in r["answer"]
    r = ask(app, uid, "DROP TABLE users")
    assert "can't answer" in r["answer"]
    with app.app_context():
        totals = queries.run_template("totals", uid, start=date(1900, 1, 1), end=date(9999, 12, 31))
        assert totals.rows


def test_only_approved_templates_run(app, uid):
    with app.app_context():
        with pytest.raises(ValueError):
            queries.run_template("DROP TABLE users", uid)
        with pytest.raises(ValueError):
            queries.run_template("totals", uid, start="x")  # wrong parameters


def test_all_templates_are_read_only_selects():
    for name, template in queries.TEMPLATES.items():
        sql = template["sql"].strip().upper()
        assert sql.startswith("SELECT"), name
        assert ":USER_ID" in sql, name
        assert not queries._FORBIDDEN.search(sql), name
