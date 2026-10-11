import csv
import io
from pathlib import Path

import pytest
from sqlalchemy import text

from conftest import SAMPLE_CSV, login, make_user
from dukaanlens import csv_import, sandbox
from dukaanlens.extensions import db
from dukaanlens.models import UploadedTable

SAMPLE = Path(__file__).resolve().parent.parent / "sample_data" / "sales_sample.csv"


def upload(client, content, filename="sales.csv", name=""):
    return client.post("/uploads/", {"file": (io.BytesIO(content), filename), "name": name},
                       content_type="multipart/form-data")


@pytest.fixture()
def sales(app, client):
    uid = make_user(app)
    login(client)
    assert upload(client, SAMPLE.read_bytes()).status_code == 302
    with app.app_context():
        return uid, UploadedTable.query.filter_by(user_id=uid).one().id


def test_upload_creates_typed_sql_table(app, client, sales):
    uid, table_id = sales
    with SAMPLE.open(newline="", encoding="utf-8") as f:
        expected_rows = len(list(csv.DictReader(f)))
    with app.app_context():
        table = db.session.get(UploadedTable, table_id)
        types = {c["name"]: c["type"] for c in table.columns}
        assert types == {"order_date": "DATE", "product": "TEXT", "category": "TEXT",
                         "city": "TEXT", "quantity": "INTEGER", "unit_price": "INTEGER",
                         "amount": "INTEGER"}
        assert table.row_count == expected_rows
        count = db.session.execute(text(f'SELECT COUNT(*) FROM "{table.table_name}"')).scalar()
        assert count == expected_rows
    assert client.get(f"/uploads/{table_id}").status_code == 200


def test_messy_csv_types_and_headers():
    raw = ("Name;Amount (Rs);Joined;Phone\n"
           "Ravi;1,200;15/03/2026;0987654321\n"
           "Sita;₹ 800.50;01/04/2026;0123456789\n").encode()
    headers, rows = csv_import.parse_csv(raw)
    assert headers == ["name", "amount_rs", "joined", "phone"]
    columns, converted = csv_import.infer_columns(headers, rows)
    assert {c["name"]: c["type"] for c in columns} == {
        "name": "TEXT", "amount_rs": "REAL", "joined": "DATE", "phone": "TEXT"}
    assert converted[0][1] == 1200.0 and converted[0][2] == "2026-03-15"
    assert converted[1][1] == 800.5 and converted[1][2] == "2026-04-01"
    assert converted[0][3] == "0987654321"          # leading zero kept as text


@pytest.mark.parametrize("raw, message", [
    (b"", "empty"),
    (b"only,header\n", "at least one data row"),
    (b"a,b\n1,2,3\n", "more values"),
])
def test_bad_csv_rejected(raw, message):
    with pytest.raises(csv_import.CsvError, match=message):
        csv_import.parse_csv(raw)


def test_upload_validation_and_duplicates(app, client, sales):
    assert b"already have a table" in upload(client, SAMPLE.read_bytes(), name="sales").data
    assert b"Only .csv files" in upload(client, b"a,b\n1,2\n", "notes.txt").data


def test_hostile_header_becomes_safe_column_name(app, client):
    make_user(app)
    login(client)
    raw = b'"x"" ; DROP TABLE users; --",b\n1,2\n'
    assert upload(client, raw, "weird.csv").status_code == 302
    with app.app_context():
        table = UploadedTable.query.one()
        assert [c["name"] for c in table.columns] == ["x_drop_table_users", "b"]
        assert db.session.execute(text("SELECT COUNT(*) FROM users")).scalar() == 1


def test_delete_drops_physical_table(app, client, sales):
    uid, table_id = sales
    with app.app_context():
        name = db.session.get(UploadedTable, table_id).table_name
    assert client.post(f"/uploads/{table_id}/delete").status_code == 302
    with app.app_context():
        assert db.session.get(UploadedTable, table_id) is None
        assert db.session.execute(
            text("SELECT name FROM sqlite_master WHERE name = :n"), {"n": name}).first() is None


def test_other_user_cannot_see_or_delete_table(app, client, sales):
    uid, table_id = sales
    make_user(app, "mallory")
    client.post("/logout")
    login(client, "mallory")
    assert client.get(f"/uploads/{table_id}").status_code == 404
    assert client.post(f"/uploads/{table_id}/delete").status_code == 404


def test_sandbox_only_reads_the_allowed_upload(app, client, sales):
    uid, table_id = sales
    with app.app_context():
        mine = db.session.get(UploadedTable, table_id).table_name
        with pytest.raises(sandbox.SqlRejected):
            sandbox.run_select('SELECT * FROM "users"', {mine})
        # a second table of another user exists but is not in the allowed set
        db.session.execute(text('CREATE TABLE "ut_99_other" (x INTEGER)'))
        db.session.commit()
        with pytest.raises(sandbox.SqlRejected):
            sandbox.run_select('SELECT * FROM "ut_99_other"', {mine})
        _, rows, _ = sandbox.run_select(f'SELECT COUNT(*) FROM "{mine}"', {mine})
        assert rows[0][0] > 0


def test_sample_csv_constant_parses():
    headers, rows = csv_import.parse_csv(SAMPLE_CSV)
    assert headers == ["order_date", "product", "city", "price"] and len(rows) == 3
