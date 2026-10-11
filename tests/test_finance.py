from datetime import date

from conftest import add_record, login, make_user
from dukaanlens import finance
from dukaanlens.models import FinancialRecord


def test_profit_formulas_and_withdrawals_stay_separate():
    m = finance.compute_metrics(revenue=10000, cogs=4000, expenses=1500, withdrawals=2000,
                                starting_capital=5000)
    assert m["gross_profit"] == 6000
    assert m["net_profit"] == 4500          # withdrawals do NOT reduce profit
    assert m["withdrawals"] == 2000
    assert m["estimated_cash"] == 5000 + 4500 - 2000


def test_loss_is_negative():
    assert finance.compute_metrics(100, 80, 50, 0)["net_profit"] == -30


def test_totals_come_from_records(app):
    uid = make_user(app)
    add_record(app, uid, "revenue", "Sales", 1000, date(2026, 1, 5))
    add_record(app, uid, "cogs", "Inventory", 400, date(2026, 1, 6))
    add_record(app, uid, "expense", "Rent", 100, date(2026, 1, 7))
    add_record(app, uid, "withdrawal", "Owner", 50, date(2026, 1, 8))
    with app.app_context():
        m = finance.get_metrics(uid, starting_capital=1000)
    assert (m["revenue"], m["gross_profit"], m["net_profit"]) == (1000, 600, 500)
    assert m["estimated_cash"] == 1000 + 500 - 50


def test_record_crud_and_validation(app, client):
    uid = make_user(app)
    login(client)
    good = {"transaction_type": "expense", "category": "Rent", "description": "March rent",
            "planned_amount": "500", "actual_amount": "550", "date": "2026-03-01", "notes": "n"}
    assert client.post("/records/new", good).status_code == 302
    with app.app_context():
        record = FinancialRecord.query.filter_by(user_id=uid).one()
        record_id = record.id
        assert record.actual_amount == 550
    assert client.post(f"/records/{record_id}/edit",
                       {**good, "actual_amount": "600"}).status_code == 302
    bad = client.post("/records/new", {**good, "actual_amount": "abc", "transaction_type": "hack"})
    assert bad.status_code == 200 and b"must be a number" in bad.data
    assert client.post(f"/records/{record_id}/delete").status_code == 302
    with app.app_context():
        assert FinancialRecord.query.filter_by(user_id=uid).count() == 0


def test_filters_and_csv_export(app, client):
    uid = make_user(app)
    add_record(app, uid, "revenue", "Sales", 100, date(2026, 1, 5))
    add_record(app, uid, "expense", "=HYPERLINK", 50, date(2026, 2, 5))
    login(client)
    html = client.get("/records/?type=revenue").data.decode()
    table = html.split("<tbody>")[1]
    assert "Sales" in table and "HYPERLINK" not in table
    csv_text = client.get("/records/export.csv?type=expense").data.decode()
    assert "date,transaction_type" in csv_text
    assert "'=HYPERLINK" in csv_text            # formula neutralised
    assert "Sales" not in csv_text
