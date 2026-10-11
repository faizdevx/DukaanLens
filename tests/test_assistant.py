"""Ask DukaanLens with a FAKE Gemini (no network). Real Gemini output is not tested here."""
import io
import json
import urllib.error
from datetime import date

import pytest

from conftest import add_record, login, make_user
from dukaanlens import ai_sql, apikeys, sandbox
from dukaanlens.extensions import db
from dukaanlens.models import ApiKey, Budget, FinancialRecord, UploadedTable

TODAY = date(2026, 6, 15)


class FakeGemini:
    """Replaces ai_sql.call_gemini. `script` items are returned one per call."""

    def __init__(self, monkeypatch, script):
        self.script, self.calls = list(script), []
        monkeypatch.setattr(ai_sql, "call_gemini", self)

    def __call__(self, api_key, model, system, prompt, want_json=True, timeout=45):
        self.calls.append({"api_key": api_key, "model": model, "system": system, "prompt": prompt})
        item = self.script.pop(0)
        return json.dumps(item) if isinstance(item, dict) else item


def sql_reply(sql, why="test"):
    return {"sql": sql, "explanation": why}


@pytest.fixture()
def shop(app):
    alice = make_user(app, "alice")
    bob = make_user(app, "bob")
    add_record(app, alice, "revenue", "Sales", 5000, date(2026, 5, 10))
    add_record(app, alice, "expense", "Rent", 800, date(2026, 5, 1))
    add_record(app, alice, "cogs", "Inventory", 2000, date(2026, 5, 12))
    add_record(app, bob, "expense", "BobSecretCategory", 999, date(2026, 5, 3))
    with app.app_context():
        db.session.add(Budget(user_id=alice, category="Rent", month="2026-05", limit_amount=500))
        db.session.commit()
        apikeys.save_key(alice, "AIza-fake-key-for-tests-0000", "gemini-test")
    return alice, bob


def ask(app, uid, text, source="records", history=None):
    with app.app_context():
        return ai_sql.answer_question(uid, source, text, TODAY, history)


# ---- keys ----------------------------------------------------------------------------

def test_no_key_asks_user_to_add_one(app):
    uid = make_user(app)
    reply = ask(app, uid, "total revenue?")
    assert reply["needs_key"] and "API key" in reply["answer"]


def test_key_is_stored_encrypted_and_roundtrips(app, shop):
    alice, _ = shop
    with app.app_context():
        stored = ApiKey.query.filter_by(user_id=alice).one()
        assert "AIza-fake-key" not in stored.encrypted_key
        assert stored.key_hint == "0000"
        assert apikeys.get_credentials(alice) == ("AIza-fake-key-for-tests-0000", "gemini-test")


def test_settings_saves_key_after_verification(app, client, monkeypatch):
    uid = make_user(app)
    login(client)
    seen = {}
    monkeypatch.setattr(ai_sql, "verify_key", lambda k, m: seen.update(key=k, model=m))
    r = client.post("/settings", {"action": "gemini_save", "api_key": "k" * 39,
                                  "model": "gemini-2.5-flash"})
    assert r.status_code == 302 and seen["key"] == "k" * 39
    page = client.get("/settings").data.decode()
    assert "…" + "kkkk" in page and "k" * 39 not in page      # never shown again
    client.post("/settings", {"action": "gemini_remove"})
    with app.app_context():
        assert ApiKey.query.filter_by(user_id=uid).count() == 0


def test_invalid_key_not_saved(app, client, monkeypatch):
    uid = make_user(app)
    login(client)

    def reject(key, model):
        raise ai_sql.AiError("Gemini says the API key is not valid.")
    monkeypatch.setattr(ai_sql, "verify_key", reject)
    r = client.post("/settings", {"action": "gemini_save", "api_key": "x" * 39})
    assert b"Key not saved" in r.data
    with app.app_context():
        assert ApiKey.query.filter_by(user_id=uid).count() == 0


# ---- question -> SQL -> answer -----------------------------------------------------

def test_full_flow_uses_ai_sql_and_ai_answer(app, shop, monkeypatch):
    alice, _ = shop
    fake = FakeGemini(monkeypatch, [
        sql_reply("SELECT ROUND(SUM(actual_amount), 2) AS total_expenses FROM shop_records "
                  "WHERE transaction_type = 'expense'"),
        "Your expenses were 800.",
    ])
    r = ask(app, alice, "What were my total expenses?")
    assert r["rows"] == [[800.0]] and r["answer"] == "Your expenses were 800."
    assert r["sql"].startswith("SELECT ROUND")
    # first call is the SQL request, second is the summary; the key comes from the user
    assert fake.calls[0]["api_key"] == "AIza-fake-key-for-tests-0000"
    assert "shop_records" in fake.calls[0]["prompt"]
    assert "Today's date: 2026-06-15" in fake.calls[0]["prompt"]


def test_ai_only_sees_own_rows(app, shop, monkeypatch):
    alice, bob = shop
    fake = FakeGemini(monkeypatch, [sql_reply("SELECT category FROM shop_records ORDER BY 1"), "ok"])
    r = ask(app, alice, "list categories")
    assert [row[0] for row in r["rows"]] == ["Inventory", "Rent", "Sales"]
    assert "BobSecretCategory" not in fake.calls[0]["prompt"]       # not even in the schema hints


def test_temp_tables_are_cleaned_up(app, shop, monkeypatch):
    alice, _ = shop
    FakeGemini(monkeypatch, [sql_reply("SELECT COUNT(*) AS n FROM shop_records"), "3"])
    ask(app, alice, "how many")
    with app.app_context():
        left = db.session.execute(db.text(
            "SELECT name FROM sqlite_temp_master WHERE name LIKE 'shop_%'")).fetchall()
        assert left == []


def test_clarifying_question_is_passed_through(app, shop, monkeypatch):
    alice, _ = shop
    FakeGemini(monkeypatch, [{"clarify": "Which month do you mean?"}])
    r = ask(app, alice, "how much did I spend")
    assert r["needs_clarification"] and r["answer"] == "Which month do you mean?"
    assert r["sql"] is None


def test_history_is_sent_for_follow_ups(app, shop, monkeypatch):
    alice, _ = shop
    fake = FakeGemini(monkeypatch, [{"clarify": "x"}])
    ask(app, alice, "last month", history=[{"q": "how much did I spend", "a": "Which month?"}])
    assert "how much did I spend" in fake.calls[0]["prompt"]


def test_sql_error_is_sent_back_once_to_fix(app, shop, monkeypatch):
    alice, _ = shop
    fake = FakeGemini(monkeypatch, [
        sql_reply("SELECT SUM(amount) FROM shop_records"),                  # no such column
        sql_reply("SELECT SUM(actual_amount) AS total FROM shop_records"),
        "Total is 7800.",
    ])
    r = ask(app, alice, "total of everything")
    assert r["rows"] == [[7800.0]]
    assert "no such column" in fake.calls[1]["prompt"].lower()


@pytest.mark.parametrize("bad_sql", [
    "DELETE FROM shop_records",
    "SELECT 1; DROP TABLE users",
    "UPDATE shop_records SET actual_amount = 0",
    "SELECT * FROM users",
    "SELECT * FROM financial_records",
    "SELECT * FROM sqlite_master",
    "SELECT * FROM shop_records -- comment",
    "PRAGMA table_info(users)",
])
def test_unsafe_sql_from_ai_never_runs(app, shop, monkeypatch, bad_sql):
    alice, _ = shop
    FakeGemini(monkeypatch, [sql_reply(bad_sql), sql_reply(bad_sql)])
    r = ask(app, alice, "do something bad")
    assert r["rows"] == [] and "could not produce a safe" in r["answer"]
    with app.app_context():
        assert FinancialRecord.query.count() == 4
        assert db.session.execute(db.text("SELECT COUNT(*) FROM users")).scalar() == 2


def test_gemini_errors_become_friendly_messages(app, shop, monkeypatch):
    alice, _ = shop

    def boom(*args, **kwargs):
        raise ai_sql.AiError("Gemini rate limit or quota reached. Wait a bit and try again.")
    monkeypatch.setattr(ai_sql, "call_gemini", boom)
    r = ask(app, alice, "anything")
    assert "rate limit" in r["answer"]


# ---- the HTTP call itself --------------------------------------------------------------

class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_call_gemini_builds_correct_request(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["headers"] = {k.lower(): v for k, v in request.header_items()}
        captured["body"] = json.loads(request.data)
        payload = {"candidates": [{"content": {"parts": [{"text": '{"sql": "SELECT 1"}'}]}}]}
        return _Response(json.dumps(payload).encode())

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    out = ai_sql.call_gemini("SECRET-KEY-123456789012345", "gemini-2.5-flash", "sys", "hello")
    assert out == '{"sql": "SELECT 1"}'
    assert captured["url"].endswith("/models/gemini-2.5-flash:generateContent")
    assert captured["headers"]["x-goog-api-key"] == "SECRET-KEY-123456789012345"
    assert "SECRET-KEY" not in captured["url"]                       # key only in a header
    assert captured["body"]["generationConfig"]["responseMimeType"] == "application/json"
    assert captured["body"]["systemInstruction"]["parts"][0]["text"] == "sys"


def test_call_gemini_maps_http_errors(monkeypatch):
    def deny(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 403, "Forbidden", {}, None)
    monkeypatch.setattr("urllib.request.urlopen", deny)
    with pytest.raises(ai_sql.AiError) as exc:
        ai_sql.call_gemini("SECRET-KEY-123456789012345", "gemini-2.5-flash", "s", "p")
    assert "permission denied" in str(exc.value) and "SECRET-KEY" not in str(exc.value)


def test_model_name_is_validated():
    with pytest.raises(ai_sql.AiError):
        ai_sql.call_gemini("k" * 30, "../evil?x=", "s", "p")


# ---- sandbox ---------------------------------------------------------------------------

def test_sandbox_blocks_everything_but_allowed_reads(app, shop):
    with app.app_context():
        db.session.execute(db.text("CREATE TEMP TABLE shop_records AS SELECT 1 AS x"))
        try:
            ok = sandbox.run_select("SELECT x FROM shop_records", {"shop_records"})
            assert ok[1] == [[1]]
            for sql in ["SELECT * FROM users", "SELECT * FROM sqlite_master",
                        "SELECT load_extension('x')", "SELECT readfile('/etc/passwd')",
                        "WITH RECURSIVE r(n) AS (SELECT 1 UNION ALL SELECT n+1 FROM r) SELECT n FROM r"]:
                with pytest.raises(sandbox.SqlRejected):
                    sandbox.run_select(sql, {"shop_records"})
        finally:
            db.session.execute(db.text("DROP TABLE IF EXISTS temp.shop_records"))
            db.session.rollback()


def test_sandbox_row_cap(app, shop):
    with app.app_context():
        db.session.execute(db.text("CREATE TEMP TABLE shop_records AS SELECT 1 AS x"))
        try:
            _, rows, truncated = sandbox.run_select("SELECT x FROM shop_records", {"shop_records"},
                                                    max_rows=0)
            assert rows == [] and truncated
        finally:
            db.session.execute(db.text("DROP TABLE IF EXISTS temp.shop_records"))
            db.session.rollback()


# ---- endpoint ---------------------------------------------------------------------------

def test_ask_endpoint_and_uploaded_table(app, client, shop, monkeypatch):
    alice, _ = shop
    login(client, "alice")
    from conftest import SAMPLE_CSV
    r = client.post("/uploads/", {"file": (io.BytesIO(SAMPLE_CSV), "items.csv"), "name": ""},
                    content_type="multipart/form-data")
    assert r.status_code == 302
    with app.app_context():
        table = UploadedTable.query.filter_by(user_id=alice).one()
        table_id, table_name = table.id, table.table_name
    fake = FakeGemini(monkeypatch, [
        sql_reply(f'SELECT SUM("price") AS total FROM "{table_name}" WHERE lower("city") = \'delhi\''),
        "Delhi total is 300.",
    ])
    r = client.post_json("/assistant/ask", {"message": "total price in Delhi", "source": str(table_id)})
    body = r.get_json()
    assert body["rows"] == [[300]] and body["answer"] == "Delhi total is 300."
    assert table_name in fake.calls[0]["prompt"] and "'Delhi'" in fake.calls[0]["prompt"]

    # another user can not use this table id as a source
    make_user(app, "mallory")
    apikeys_ok = None
    client.post("/logout")
    login(client, "mallory")
    with app.app_context():
        apikeys.save_key(db.session.execute(db.text(
            "SELECT id FROM users WHERE username='mallory'")).scalar(), "k" * 30, "m-model")
    r = client.post_json("/assistant/ask", {"message": "x", "source": str(table_id)})
    assert r.get_json()["answer"] == "That data source was not found."
