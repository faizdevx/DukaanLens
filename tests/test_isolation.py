from datetime import date

from conftest import add_record, login, make_user
from dukaanlens.extensions import db
from dukaanlens.models import Budget, FinancialRecord


def two_users(app):
    alice = make_user(app, "alice")
    bob = make_user(app, "bob")
    add_record(app, alice, "expense", "Alice Cat", 111, date.today(), description="alice-only")
    add_record(app, bob, "expense", "Bob Stuff", 222, date.today(), description="bob-only")
    return alice, bob


def test_record_list_only_shows_own_data(app, client):
    two_users(app)
    login(client, "alice")
    html = client.get("/records/").data.decode()
    assert "alice-only" in html and "bob-only" not in html
    csv_text = client.get("/records/export.csv").data.decode()
    assert "alice-only" in csv_text and "bob-only" not in csv_text


def test_cannot_edit_or_delete_other_users_record(app, client):
    alice, bob = two_users(app)
    with app.app_context():
        bob_record = FinancialRecord.query.filter_by(user_id=bob).one().id
    login(client, "alice")
    assert client.get(f"/records/{bob_record}/edit").status_code == 404
    assert client.post(f"/records/{bob_record}/edit", {"category": "x"}).status_code == 404
    assert client.post(f"/records/{bob_record}/delete").status_code == 404
    with app.app_context():
        assert db.session.get(FinancialRecord, bob_record) is not None


def test_cannot_touch_other_users_budget(app, client):
    alice, bob = two_users(app)
    with app.app_context():
        budget = Budget(user_id=bob, category="Rent", month="2026-01", limit_amount=100)
        db.session.add(budget)
        db.session.commit()
        budget_id = budget.id
    login(client, "alice")
    assert client.get(f"/budgets/{budget_id}/edit").status_code == 404
    assert client.post(f"/budgets/{budget_id}/delete").status_code == 404


def test_assistant_only_sees_own_data(app, client):
    two_users(app)
    login(client, "alice")
    r = client.post_json("/assistant/ask", {"message": "how much did I spend on bob stuff?"})
    assert "couldn't find a category" in r.get_json()["answer"]
    r = client.post_json("/assistant/ask", {"message": "total expenses this year"})
    assert "111.00" in r.get_json()["answer"]
