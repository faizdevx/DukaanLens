from conftest import login, make_user
from dukaanlens.models import FinancialRecord, Shop, User


def test_register_hashes_password_and_redirects_to_setup(app, client):
    r = client.post("/register", {"username": "bob", "email": "bob@example.com",
                                  "password": "secret123", "confirm": "secret123"})
    assert r.status_code == 302 and r.headers["Location"].endswith("/setup")
    with app.app_context():
        user = User.query.filter_by(username="bob").one()
        assert user.password_hash != "secret123"
        assert user.check_password("secret123")


def test_register_rejects_bad_input_and_duplicates(app, client):
    make_user(app)
    bad = client.post("/register", {"username": "x", "email": "nope", "password": "short",
                                    "confirm": "different"})
    assert bad.status_code == 400
    dup = client.post("/register", {"username": "ALICE", "email": "new@example.com",
                                    "password": "password123", "confirm": "password123"})
    assert dup.status_code == 400
    assert b"already taken" in dup.data


def test_login_logout_flow(app, client):
    make_user(app)
    assert client.get("/dashboard").status_code == 302          # login required
    assert login(client, password="wrong").status_code == 401
    assert login(client).status_code == 302
    assert client.get("/dashboard").status_code == 200
    client.post("/logout")
    assert client.get("/dashboard").status_code == 302


def test_login_does_not_redirect_to_other_sites(app, client):
    make_user(app)
    r = client.post("/login?next=https://evil.example/",
                    {"identity": "alice", "password": "password123"})
    assert r.headers["Location"].endswith("/dashboard")


def test_post_without_csrf_token_is_rejected(app):
    raw = app.test_client()
    assert raw.post("/login", data={"identity": "a", "password": "b"}).status_code == 400


def test_first_login_requires_shop_setup(app, client):
    make_user(app, with_shop=False)
    login(client)
    r = client.get("/dashboard")
    assert r.status_code == 302 and r.headers["Location"].endswith("/setup")
    r = client.post("/setup", {"name": "Corner Shop", "established_on": "2023-05-01",
                               "starting_capital": "50000", "revenue": "20000", "cogs": "8000",
                               "operating_expenses": "5000", "owner_withdrawals": "2000"})
    assert r.status_code == 302
    with app.app_context():
        shop = Shop.query.one()
        assert shop.name == "Corner Shop" and shop.starting_capital == 50000
        assert FinancialRecord.query.count() == 4
    assert client.get("/dashboard").status_code == 200


def test_setup_rejects_negative_numbers(app, client):
    make_user(app, with_shop=False)
    login(client)
    r = client.post("/setup", {"name": "Shop", "established_on": "2023-05-01",
                               "starting_capital": "-5"})
    assert r.status_code == 200
    with app.app_context():
        assert Shop.query.count() == 0
