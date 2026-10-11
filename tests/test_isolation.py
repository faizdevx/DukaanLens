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


def test_assistant_only_sees_own_data(app, client, monkeypatch):
    from dukaanlens import ai_sql, apikeys
    alice, _ = two_users(app)
    with app.app_context():
        apikeys.save_key(alice, "k" * 30, "test-model")
    replies = iter(['{"sql": "SELECT SUM(actual_amount) AS total FROM shop_records", '
                    '"explanation": "sum"}', "Total is 111."])
    prompts = []

    def fake(api_key, model, system, prompt, want_json=True, timeout=45):
        prompts.append(prompt)
        return next(replies)
    monkeypatch.setattr(ai_sql, "call_gemini", fake)
    login(client, "alice")
    body = client.post_json("/assistant/ask", {"message": "total?", "source": "records"}).get_json()
    assert body["rows"] == [[111.0]]                    # Bob's 222 is not included
    assert "Bob Stuff" not in prompts[0]
